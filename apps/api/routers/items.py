"""The three item routes. Each one parses, authorises, calls **one** service
function, and serialises.

Three properties are load-bearing rather than stylistic:

* **Nothing here ever holds the hidden half of an item.** Not a `StoredItem`,
  not a `BaseItem`, and — the clause that actually matters — not any string that
  is or contains an answer. A `str` is what leaks: through an exception handler
  that echoes context, a debug log line, or a 500 body. So the read routes
  receive `ItemPresentation` (which has no answer to leak) and `/audio` receives
  **bytes** from `items.item_audio`, never text to synthesise itself.
  `tests/test_core_boundary.py::test_the_api_never_reaches_the_hidden_half_of_an_item`
  fails the commit that imports `core.items.projection`, `.schema`, `.grading`,
  `core.llm` or `core.speech` into `apps/api`.

* **Plain `def`, all three.** `/audio` reaches `core.speech.synthesize` through
  the service, and the read and answer routes block on a psycopg pool checkout.
  Standing rule 6 (issue #7 with a wider blast radius): an `async def` here puts
  a multi-second call on the event loop and stalls every other request the
  worker is serving.

* **JSON only on the write, and rate limited.** W2 recorded that `SameSite=Lax`
  is not the CSRF barrier — the barrier is that every state-changing route is a
  JSON `POST`, which always preflights, and the preflight is answered only for
  the two allowed origins.

**`POST /items/{id}/answer` writes nothing to `errors`.** That reverses
`docs/ARCHITECTURE-v3-web.md` §6, which is corrected in the same commit as this
file; the reasoning is in `core.services.items.answer_item` and the decision is
revisited at W11 (#107).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import (
    ItemAnswerRequest,
    ItemAnswerResult,
    ItemPresentationOut,
)
from core.services import items
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

JSON_CONTENT_TYPE = "application/json"

#: One page of the bank. A learner works through a handful at a time and W10
#: hydrates five blocks; nothing needs more, and an unbounded limit on a
#: continuously-probed API is a free way to make the server do work.
MAX_LIMIT = 50


def require_json(request: Request) -> None:
    """Refuse anything that is not JSON, explicitly.

    FastAPI would answer 422 for a form body against a JSON model, but that is
    the right outcome for an incidental reason. Making the refusal the route's
    own decision is what survives someone later adding a `Form(...)` parameter,
    which would silently turn this into a simple request and delete the CSRF
    barrier described in the module docstring.
    """
    media_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if media_type.lower() != JSON_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="json_required",
        )


@router.get(
    "",
    response_model=list[ItemPresentationOut],
    dependencies=[
        Depends(rate_limit("items_list", per_client=120, overall=600, window_seconds=3600))
    ],
)
def list_items(
    limit: int = Query(default=20, ge=1, le=MAX_LIMIT),
    item_type: str | None = Query(default=None, max_length=32),
    session: AuthenticatedUser = Depends(require_current_user),
) -> list[ItemPresentationOut]:
    """This learner's validated bank, learner-visible halves only.

    Not superseded by W10: `GET /session/today` is a different resource — a
    session, with blocks and progress — built from the same
    `items.presentations_for`. This is the bank, and `item_attempts.session_id`
    is nullable precisely because migration 012 named free practice as a
    first-class path.

    An unknown `item_type` yields an empty list rather than a 400: the value is
    a filter, and `core.items.ITEM_TYPES` is the authority on what exists.
    """
    return [
        ItemPresentationOut(
            id=row.id, response_mode=row.response_mode, projection=row.projection
        )
        for row in items.presentations_for(
            session.id, item_type=item_type, limit=limit
        )
    ]


@router.get("/{item_id}", response_model=ItemPresentationOut)
def get_item(
    item_id: int,
    session: AuthenticatedUser = Depends(require_current_user),
) -> ItemPresentationOut:
    """One item. 404 covers both "no such item" and "not yours".

    Collapsing the two is deliberate: telling a caller that an id exists but
    belongs to someone else is a fact about the other learner.
    """
    row = items.presentation_for(session.id, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return ItemPresentationOut(
        id=row.id, response_mode=row.response_mode, projection=row.projection
    )


@router.post(
    "/{item_id}/answer",
    response_model=ItemAnswerResult,
    dependencies=[
        Depends(require_json),
        # A learner answering an item every ten seconds for an hour would use
        # 360. Anything past 600 is not practice. Grading costs nothing, so the
        # limit is a guard against a stolen session rather than against cost.
        Depends(rate_limit("items_answer", per_client=600, overall=2000, window_seconds=3600)),
    ],
)
def answer(
    item_id: int,
    body: ItemAnswerRequest,
    session: AuthenticatedUser = Depends(require_current_user),
) -> ItemAnswerResult:
    """Grade one response and record the attempt.

    The route does not decide which field of the body is the answer — that is
    `core.items.response`, from the item's own type. A client that sends the
    wrong field grades as wrong, which is correct for a response that answers
    nothing.
    """
    outcome = items.answer_item(
        session.id,
        item_id,
        submission=items.Submission(
            text=body.text,
            option=body.option,
            tile_index=body.tile_index,
            order=tuple(body.order),
            pairs=body.pairs,
            self_marked=body.self_marked,
        ),
        latency_ms=body.latency_ms,
    )
    if outcome is None:
        raise HTTPException(status_code=404, detail="not_found")
    return ItemAnswerResult(
        correct=outcome.correct,
        graded_by=outcome.graded_by,
        canonical=outcome.canonical,
        explanation=outcome.explanation,
        murphy_units=outcome.murphy_units,
        # #118: `match_pairs`' correct mapping, after grading. NULL for every
        # other type. This is the API change W6a was barred from making, and it
        # is the reason a wrong `match_pairs` answer stopped teaching nothing.
        pairs=list(outcome.pairs) if outcome.pairs else None,
    )


@router.get(
    "/{item_id}/audio",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
    dependencies=[
        Depends(rate_limit("items_audio", per_client=200, overall=800, window_seconds=3600))
    ],
)
def audio(
    item_id: int,
    session: AuthenticatedUser = Depends(require_current_user),
) -> Response:
    """The item's sentence as speech, for the three types whose content is audio.

    Bytes in, bytes out. **The text is never seen here** — for `listening_gap`
    the spoken sentence *is* the answer, and holding it in `apps/api` is what
    the module docstring refuses. `items.item_audio` synthesises and returns
    audio; this route serialises it.

    Fetched on tap, never on page load, so nothing about a session opening in
    under a second changes. Synthesised per request with no cache: correct and
    cheapest at two learners, and a cache keyed on `items.content_hash` before
    real tenancy (#106).

    A provider failure is a 503 and not a 500: the service is up and answering,
    its dependency is not, and the client offers the learner another tap.
    """
    try:
        data = items.item_audio(session.id, item_id)
    except items.ItemAudioUnavailable:
        # No detail crosses the wire — a provider message is a free map of the
        # backend (PRD §10).
        logger.warning("Item audio unavailable user_id=%s id=%s", session.id, item_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audio_unavailable",
        ) from None
    if data is None:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(content=data, media_type="audio/mpeg")
