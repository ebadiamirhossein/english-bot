"""W13-i's two routes. ARCHITECTURE §6, PRD §7.3.

Each parses, authorises, calls **one** service function, and serialises
(CLAUDE.md §2). No business logic here and no SQL: the queries are in
`core/services/video.py`, which is what `test_no_sql_outside_services` holds.

**BOTH ARE PLAIN `def`.** Standing rule 6 / #7: these block on a psycopg pool
checkout, and `GET /video/today` takes one while recomputing coverage over a
whole transcript. An `async def` would put that on the event loop and stall
every other request the worker is serving. Neither route reaches a model today
and the rule is followed anyway, because the slice that adds one
(**W13-ii**, gated on the operator's §1a ruling) must not have to remember to.

**NOTHING IS GENERATED WHILE THE LEARNER WAITS.** No `core.llm`, no
`core.speech`, no provider SDK. The coverage recomputation is pure CPU over text
already stored -- which is the argument migration 019's header rests
`video_coverage`'s *audit record, not a cache* ruling on, applied one layer up.
**`video_coverage` is not read here**: `assign` recomputes on every run and so
does this, so nothing consults the stored row and it keeps needing no
invalidation rule.

**NO PERCENTAGE CROSSES THIS BOUNDARY.** `core.video.badge` hands out a band
token or nothing; the figure itself never enters a response model, so no client
can render one it was never given (#288, #334, #330 -- written out at
`core/video/badge.py`).

~~**THE ROUTE THIS SLICE DOES NOT SHIP: `POST /video/{id}/save-word`.** It is
W13-ii's, it is the one that reaches a model, and shipping its route here would
be a route with no caller -- a defect class this record has named twice.~~
*(Stale since W13-ii shipped the route below; corrected by W31a, old text kept.
The route reaches no model: §1a was ruled PRE-GENERATE and a tap reads a stored
`video_glosses` row. **Its request contract** -- the content type and body the
web sends -- is held by `apps/web/lib/web-requests.contract.json` from both
sides since #465.)*
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import (
    SaveWordIn,
    SaveWordOut,
    VideoProgressIn,
    VideoTodayOut,
    WordLookupOut,
)
from core.services import cards as cards_service
from core.services import dictionary as dictionary_service
from core.services import words as words_service
from core.services import video as video_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


def _out(assigned: video_service.TodayVideo) -> VideoTodayOut:
    return VideoTodayOut(
        video_id=assigned.video_id,
        youtube_id=assigned.youtube_id,
        title=assigned.title,
        duration_s=assigned.duration_s,
        resume_position_s=assigned.resume_position_s,
        completed=assigned.completed_at is not None,
    )


@router.get(
    "/today",
    response_model=VideoTodayOut,
    dependencies=[
        Depends(
            rate_limit(
                "video_today", per_client=200, overall=800, window_seconds=3600
            )
        )
    ],
)
def today(
    session: AuthenticatedUser = Depends(require_current_user),
) -> VideoTodayOut:
    """Today's assigned video, without the transcript.

    **THE TRANSCRIPT AND THE BADGE COME THROUGH BLOCK 2, NOT THROUGH HERE, AND
    THAT IS DELIBERATE.** `GET /session/today` already hydrates the player's
    whole payload -- transcript, unknown lemmas, band -- so serving it a second
    time here would be a **second producer of one contract**, which is #190's
    defect exactly: two call sites assembling one shape, one of them incomplete,
    both suites green because the halves never meet.

    So this route answers a different question -- *is there a video today, where
    did I stop, have I finished it* -- which is what a client needs to resume
    without re-hydrating five blocks. **It has a caller**: the player polls it
    after a progress write to confirm what was stored.

    404 when nothing is assigned for the learner's date -- since W24d, a day the
    pool had nothing in band and unseen for (it read *"the ordinary state on four
    days in seven (PRD §7.1 is Mon/Wed/Fri)"* until video became daily). The client reads
    it as *no video today*, never as a failure -- block 2 says the same thing
    with `empty`.
    """
    assigned = video_service.today_for_user(
        session.id, now=datetime.now(timezone.utc)
    )
    if assigned is None:
        raise HTTPException(status_code=404, detail="no_video_today")
    return _out(assigned)


@router.post(
    "/{video_id}/progress",
    response_model=VideoTodayOut,
    dependencies=[
        Depends(
            rate_limit(
                "video_progress", per_client=600, overall=2400, window_seconds=3600
            )
        )
    ],
)
def progress(
    video_id: int,
    body: VideoProgressIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> VideoTodayOut:
    """Where the learner stopped -- and, when they reached the end, that they did.

    **THIS IS BLOCK 2's LOG, AND IT IS WHY THERE IS NO COMPLETION BUTTON
    (#258).** The operator ruled block completion automatic on 2026-08-29 and
    deleted the manual control, its route and its service function; the per-kind
    rule turns on whether a block has a per-attempt log keyed on the session.
    `input` had none because it served nothing. **This route is that log.**

    **ONE SERVICE CALL WRITES BOTH COLUMNS** (#190, #291). The route does not
    decide whether the video is finished -- `core.video.watch.is_complete` does,
    it is pure, and a route that made that judgement would be a second producer
    of the same fact.

    **THE RATE LIMIT IS HIGHER THAN THE OTHER ROUTES' AND STILL BOUNDED.** A
    ping every fifteen seconds through a twelve-minute video is ~48 writes; 600
    an hour is far above real use for three videos a week and far below anything
    that would let a stolen session write in a loop. The client throttles as
    well -- but a limit that lives only in the client is not a limit.

    404 when the video is not assigned to this learner. **It is never a silent
    success**: a ping that wrote nothing and reported that it wrote something is
    the shape #298 spent a whole row establishing was NOT happening to card
    grading, and it is not going to start here.
    """
    updated = video_service.save_progress_for_user(
        session.id,
        video_id,
        position_s=body.position_s,
        now=datetime.now(timezone.utc),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    return _out(updated)


@router.post(
    "/{video_id}/save-word",
    response_model=SaveWordOut,
    dependencies=[
        # A learner taps a handful of words per video. Well above real use and
        # far below anything that would make the server work for a stolen
        # session. **This read bills nothing**: §1a is ruled PRE-GENERATE, so
        # the definition is already a `video_glosses` row.
        Depends(
            rate_limit("save_word", per_client=120, overall=400, window_seconds=3600)
        )
    ],
)
def save_word(
    video_id: int,
    body: SaveWordIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> SaveWordOut:
    """One tap on a transcript word → two cards. W13-ii, PRD §7.3.

    Parses, authorises, calls **one** service function, serialises. **PLAIN
    `def` (#7)**: it blocks on a psycopg pool checkout, and an `async def` would
    put that on the event loop. The rule matters more here than anywhere else on
    this router, because this is the slice whose sibling command reaches a
    model -- and `core.services.cards.save_captured_word` deliberately does not.

    **NOTHING IS GENERATED WHILE THE LEARNER WAITS.** No `core.llm`, no
    `core.speech`, no provider SDK on this path. `tests/test_video_route.py`
    asserts it through the network guard rather than by reading this docstring.

    **A SECOND TAP IS A 200, NOT A 500** (#178). The service returns
    `already_saved` and this route serialises it; the `UNIQUE` index stays the
    guarantee underneath.
    """
    # **W31c: through `core.services.words.save`.** A word with a stored gloss
    # is saved as two cards (W13-ii's path); a word without one is written as
    # PENDING and a worker job explains it later — this request still reaches
    # no model. A video that is not this learner's is a 404, which W31a's copy
    # says plainly.
    result = words_service.save(
        session.id,
        video_id=video_id,
        word=body.word,
        line=body.line,
        now=datetime.now(timezone.utc),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    return SaveWordOut(
        state=result.state, card_ids=list(result.card_ids), meaning_soon=result.meaning_soon
    )


@router.get(
    "/{video_id}/word",
    response_model=WordLookupOut,
    response_model_exclude_none=True,
    dependencies=[
        # Every tap opens the sheet, so this sits well above save-word's limit
        # and still far below anything a stolen session could use. A read.
        Depends(rate_limit("word_lookup", per_client=600, overall=2000, window_seconds=3600))
    ],
)
def word_lookup(
    video_id: int,
    w: str = Query(min_length=1, max_length=80),
    line: int | None = Query(default=None, ge=0, le=100_000),
    session: AuthenticatedUser = Depends(require_current_user),
) -> WordLookupOut:
    """W31c: what the word sheet shows. **Reads; reaches no model.**

    Parses, authorises, calls **one** service function, serialises. Plain `def`
    (#7). The netguard fixture is armed for its tests, so a model call here
    would fail them rather than pass silently.
    """
    found = words_service.lookup(session.id, video_id=video_id, word=w, line=line)
    if found is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    return WordLookupOut(
        word=found.word,
        lemma=found.lemma,
        line=found.line,
        meaning=found.meaning,
        image=found.image,
        saved=found.saved,
    )


@router.get(
    "/{video_id}/meanings",
    dependencies=[
        # Once per page load, and a reload is the only repeat. Far above that,
        # far below anything a stolen session could use. A read.
        Depends(rate_limit("meanings", per_client=300, overall=1000, window_seconds=3600))
    ],
)
def meanings(
    video_id: int,
    request: Request,
    session: AuthenticatedUser = Depends(require_current_user),
) -> Response:
    """**W32b: every meaning `/watch` can show, in one request.** Hover and tap
    then need no network at all (the operator's *under a second*, 2026-09-27).

    Parses, authorises, calls **one** service function, serialises. Plain `def`
    (#7). **Reaches no model** — the map is stored rows; the netguard is armed
    for its tests.

    **IT GZIPS ITS OWN BODY** when the browser accepts it: the API has no
    compression layer and Caddy's config is not this repo's, and the map is the
    largest response the app sends (hundreds of KB raw for a long video). **Here
    and not app-wide**, so no other response — streaming ones included — changes.
    **`no-store`**, because the map carries this learner's saved words and a
    cached copy would show a word as unsaved after a Save.
    """
    body = dictionary_service.meanings_for(session.id, video_id)
    if body is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Cache-Control": "private, no-store", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        headers["Content-Encoding"] = "gzip"
        raw = gzip.compress(raw, mtime=0)
    return Response(content=raw, media_type="application/json", headers=headers)
