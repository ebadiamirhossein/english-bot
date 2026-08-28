"""`GET /lessons/{unit_number}` — one unit's grammar lesson.

Parse, authorise, call ONE service function, serialise. No business logic
(CLAUDE.md §2), and a plain `def` rather than `async def` (standing rule 6),
because every call below is blocking psycopg and an `async def` would block the
loop while pretending not to.

**What "authorise" means here, stated because a global resource makes it
genuinely ambiguous.** `grammar_lessons` has no `user_id`, so there is no
row-level check to make -- what is left is whether the caller is signed in at
all. This route requires a session, exactly as `/session/today` does and with the
same two dependencies, and `session` is used to AUTHORISE and never to SELECT:
the lesson served is the same for every learner, which is the global line on the
wire.

**Why the route exists when block 3 already carries the lesson.** Under #188 the
only unit a learner can reach is unit 1, so a lesson for unit 9 or 20 is
unreadable in the session. This route -- and the page that renders it -- is how
those lessons are read at all, which is what makes "the operator reads the three
lessons" an acceptance check rather than a claim.

**#160: reachable, never owed.** No bottom-nav entry, no badge, no count. The map
links here when W9 builds it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import LessonOut
from core.services import lessons as lessons_service
from core.services.auth import AuthenticatedUser
from core.syllabus import UNIT_COUNT

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.get(
    "/{unit_number}",
    response_model=LessonOut,
    dependencies=[
        Depends(
            rate_limit("lesson_read", per_client=200, overall=800, window_seconds=3600)
        )
    ],
)
def lesson(
    unit_number: int,
    session: AuthenticatedUser = Depends(require_current_user),
) -> LessonOut:
    if not 1 <= unit_number <= UNIT_COUNT:
        raise HTTPException(status_code=404, detail="not_found")
    stored = lessons_service.for_unit(unit_number)
    if stored is None:
        # A unit nobody has generated for has no lesson, and that is the correct
        # behaviour rather than a bug -- generation is human-run (#196). So is a
        # unit whose stored lesson predates the current `LESSON_VERSION`: the
        # service refuses it rather than serving teaching checked by rules that
        # no longer exist.
        raise HTTPException(status_code=404, detail="not_found")
    return LessonOut(
        unit_number=stored.unit_number,
        sections=[s.model_dump(mode="json") for s in stored.sections],
        diagrams=[d.model_dump(mode="json") for d in stored.diagrams],
    )
