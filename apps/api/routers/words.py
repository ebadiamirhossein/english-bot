"""`GET /words` — the words a learner saved from videos. **W31c.**

*"I didn't find vocabulary flashcards"* (the operator, 2026-09-27). My words is
reached from `Review`: every word saved from a video, newest first, with the
ones still waiting for a meaning marked. **No count, no total, no backlog**
(CLAUDE.md §4, #160) — one page, and `next_before` for the next.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import MyWordsOut, SavedWordOut
from core.services import words as words_service
from core.services.auth import AuthenticatedUser

router = APIRouter(prefix="/words", tags=["words"])


@router.get(
    "",
    response_model=MyWordsOut,
    response_model_exclude_none=True,
    dependencies=[Depends(rate_limit("my_words", per_client=240, overall=800, window_seconds=3600))],
)
def my_words(
    before: datetime | None = Query(default=None),
    session: AuthenticatedUser = Depends(require_current_user),
) -> MyWordsOut:
    """Parses, authorises, calls **one** service function, serialises."""
    words = words_service.my_words(session.id, before=before)
    return MyWordsOut(
        words=[
            SavedWordOut(
                word=w.word,
                sentence=w.sentence,
                source_title=w.source_title,
                state=w.state,
                saved_at=w.saved_at,
            )
            for w in words
        ],
        next_before=words[-1].saved_at if len(words) == words_service.PAGE else None,
    )
