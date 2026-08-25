"""The deck's two routes. Each parses, authorises, calls **one** service
function, and serialises.

Three properties, load-bearing rather than stylistic:

* **Plain `def`, both.** Each blocks on a psycopg pool checkout and
  `/review/{id}/grade` also runs the scheduler. Standing rule 6 (issue #7 with a
  wider blast radius): an `async def` here puts that on the event loop and
  stalls every other request the worker is serving.

* **The clock is read exactly once per request, here.** Everything below the
  route takes `now` as an argument and no service function calls
  `datetime.now()`. That is what lets a due date be asserted in a test without
  freezing time (CLAUDE.md §3 rule 6), and it means the instant that schedules a
  card and the instant logged in `card_reviews` are provably the same instant.

* **No interval arithmetic leaves the server.** `CardFace.intervals` carries
  what each of the four buttons would schedule, computed by
  `core.cards.fsrs`. The frontend renders numbers it is given, the same rule W6
  established for grading with `grade_text`.

**There is no export route.** `GET /cards/export.tsv` lived here from W7 until
2026-08-25, when W8a ruled the in-app deck is the flashcard system and there is
no Anki hand-off from the web app at all. PRD §5, ARCHITECTURE §6 and the TASKS
W7 row all specified it and all three are corrected in the same commit — this
was a product change, not a stale row. `tests/test_web_shell.py` bans the path
from `apps/api` and `apps/web` so it cannot come back by someone reading a
cached copy of PRD §5.

The **v2 Telegram chunk exporter** (`core.services.anki`) is a different surface,
still live for two learners, and dies at W22. It is untouched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import (
    CardFace,
    DeckCountsOut,
    GradeRequest,
    GradeResult,
    ReviewQueueOut,
)
from core.cards import RATINGS
from core.cards.fsrs import review as schedule_review
from core.services import cards as cards_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cards"])

JSON_CONTENT_TYPE = "application/json"

#: One screenful of the queue. The daily caps bound the day; this bounds one
#: request, so a phone on a slow connection is not made to wait for eighty cards
#: it will not reach before the app is closed.
MAX_LIMIT = 50


def require_json(request: Request) -> None:
    """Refuse anything that is not JSON, explicitly.

    Same reasoning as the items router: FastAPI would answer 422 for the wrong
    body type, but for an incidental reason. Making the refusal the route's own
    decision is what survives someone later adding a `Form(...)` parameter,
    which would turn this into a simple request and delete the CSRF barrier
    (a JSON POST always preflights; the preflight is answered only for the two
    allowed origins).
    """
    media_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if media_type.lower() != JSON_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="json_required",
        )


def _intervals(card: cards_service.Card, *, now: datetime) -> dict[str, int]:
    """What each button would schedule, in days. Computed, never guessed.

    Four scheduler calls on frozen state — `core.cards.fsrs.review` copies the
    card before touching it, so asking "what would Easy do" cannot advance
    anything. Shown on the buttons because a learner choosing between Hard and
    Good is choosing between two intervals, and hiding them makes the choice
    arbitrary.
    """
    out: dict[str, int] = {}
    for name, rating in RATINGS.items():
        out[name] = schedule_review(card.state, rating, now=now).scheduled_days or 0
    return out


def _face(card: cards_service.Card, *, now: datetime) -> CardFace:
    return CardFace(**card.face(), intervals=_intervals(card, now=now))


def _counts(counts: cards_service.DeckCounts) -> DeckCountsOut:
    return DeckCountsOut(
        new_remaining=counts.new_remaining,
        review_remaining=counts.review_remaining,
        total_remaining=counts.total_remaining,
    )


@router.get(
    "/review/queue",
    response_model=ReviewQueueOut,
    dependencies=[
        Depends(rate_limit("review_queue", per_client=200, overall=800, window_seconds=3600))
    ],
)
def review_queue(
    limit: int = Query(default=20, ge=1, le=MAX_LIMIT),
    session: AuthenticatedUser = Depends(require_current_user),
) -> ReviewQueueOut:
    """Due cards, capped by PRD §5's two daily budgets.

    An empty list is the ordinary state on a day already finished, not an error.
    `counts` is what the reviewer's header reads, and it is the **capped**
    remainder rather than the raw overdue count: CLAUDE.md §4 — a backlog is
    never presented.
    """
    now = datetime.now(timezone.utc)
    queue = cards_service.due_queue(session.id, now=now, limit=limit)
    return ReviewQueueOut(
        cards=[_face(card, now=now) for card in queue],
        counts=_counts(cards_service.counts_today(session.id, now=now)),
    )


@router.post(
    "/review/{card_id}/grade",
    response_model=GradeResult,
    dependencies=[
        Depends(require_json),
        # A learner grading a card every five seconds for an hour would use 720,
        # and the daily cap stops them at 92 cards long before that. The limit
        # guards a stolen session, not cost — grading bills nothing.
        Depends(rate_limit("review_grade", per_client=600, overall=2000, window_seconds=3600)),
    ],
)
def grade(
    card_id: int,
    body: GradeRequest,
    session: AuthenticatedUser = Depends(require_current_user),
) -> GradeResult:
    """Grade one card. 404 covers both "no such card" and "not yours".

    Collapsing the two is deliberate and matches `GET /items/{id}`: telling a
    caller that an id exists but belongs to someone else is a fact about the
    other learner.
    """
    outcome = cards_service.grade_card(
        session.id,
        card_id,
        rating=RATINGS[body.rating],
        now=datetime.now(timezone.utc),
        duration_ms=body.duration_ms,
    )
    if outcome is None:
        raise HTTPException(status_code=404, detail="not_found")
    return GradeResult(
        due=outcome.due,
        interval_days=outcome.interval_days,
        counts=_counts(outcome.counts),
    )
