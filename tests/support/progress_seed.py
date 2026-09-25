"""W19 seeding: one learner's acts, written in the shapes the real writers produce.

Shared by `tests/test_practised_day.py` and `tests/test_progress_route.py`.
Items go through `core.services.items.insert_item` (a hand INSERT would seed a
row 012's CHECKs never accepted) and cards through `cards.create_card`. The
per-day logs (`conversation_usage`, `writing_submissions`) and the attempt /
review logs are INSERTed directly, because their writers are the billed paths
(`correct_submission`, `add_turn`) and the columns written here are exactly the
ones those writers set.

Every learner is created with a `streaks` row, as `identity.create_web_user`
does, and deleted with everything that cascades from `users`.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from core.items.gates import ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import parse

VILNIUS = ZoneInfo("Europe/Vilnius")

_VALID = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "items" / "valid.json").read_text(
        encoding="utf-8"
    )
)
_BY_TYPE = {row["item"]["item_type"]: row["item"] for row in _VALID}


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """A Vilnius wall-clock instant."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=VILNIUS)


def make_learner(db, label: str, *, native_language: str = "lt", with_session: bool = True):
    """A web learner with a `streaks` row and, optionally, a signed-in cookie."""
    row = db.execute(
        """
        INSERT INTO users (name, native_language, onboarded, cefr_level,
                           auth_email, auth_user_id, timezone)
        VALUES (%s, %s, TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            label,
            native_language,
            f"w19-{secrets.token_hex(6)}@example.invalid",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute("INSERT INTO streaks (user_id) VALUES (%s)", (user_id,))
    raw = None
    if with_session:
        db.execute(
            "INSERT INTO access_requests (user_id, display_name, status) "
            "VALUES (%s, %s, 'approved')",
            (user_id, label),
        )
        raw = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (
                hashlib.sha256(raw.encode()).digest(),
                user_id,
                datetime.now(timezone.utc) + timedelta(days=30),
            ),
        )
    db.commit()
    return type("L", (), {"user_id": user_id, "cookie": raw})()


def drop_learner(db, user_id: int) -> None:
    db.rollback()
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def item(db, user_id: int, item_type: str) -> int:
    """One item of ``item_type`` in this learner's bank, via the real writer."""
    from core.services import items as items_svc

    draft = dict(_BY_TYPE[item_type])
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    item_id = items_svc.insert_item(
        user_id, parse(draft), ValidationReport("passed"), model="w19-test"
    )
    db.commit()
    assert item_id is not None, item_type
    return int(item_id)


def _bank(db, user_id: int, item_type: str) -> int:
    """This learner's item of ``item_type``, written once and reused: 012 keeps
    `UNIQUE (user_id, content_hash)`, and an item is legitimately answered
    more than once (no UNIQUE on attempts)."""
    row = db.execute(
        "SELECT id FROM items WHERE user_id = %s AND item_type = %s LIMIT 1",
        (user_id, item_type),
    ).fetchone()
    return int(row[0]) if row else item(db, user_id, item_type)


def attempt(db, user_id: int, item_type: str, when: datetime, *, graded_by: str | None = None) -> int:
    """An answered item. ``graded_by`` defaults to what the type's grader writes."""
    from core.items import RESPONSE_MODE

    if graded_by is None:
        graded_by = "self" if RESPONSE_MODE[item_type] == "spoken" else "deterministic"
    item_id = _bank(db, user_id, item_type)
    db.execute(
        "INSERT INTO item_attempts (user_id, item_id, correct, graded_by, attempted_at) "
        "VALUES (%s, %s, TRUE, %s, %s)",
        (user_id, item_id, graded_by, when),
    )
    db.commit()
    return item_id


def review(db, user_id: int, when: datetime, *, typed: str | None = None) -> None:
    """A graded card; ``typed`` is the learner's typed answer, if the card asked."""
    from core.cards.fsrs import CardState
    from core.services import cards as cards_svc

    card_id = cards_svc.create_card(
        db,
        user_id,
        card_type="cloze",
        front=f"I _____ to the shops. {secrets.token_hex(4)}",
        back="went",
        register="neutral",
        register_source="migration_default",
        state=CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=when,
            last_review=when - timedelta(days=10),
            lapses=0,
            reps=3,
        ),
        meaning="past of go",
        context_sentence="I went to the shops.",
        source_ref="himym",
    )
    db.execute(
        """
        INSERT INTO card_reviews
            (card_id, user_id, reviewed_at, rating, state_before, state_after,
             due_after, typed_response, typed_matched)
        VALUES (%s, %s, %s, 3, 'review', 'review', %s, %s, %s)
        """,
        (
            card_id,
            user_id,
            when,
            when + timedelta(days=4),
            typed,
            None if typed is None else True,
        ),
    )
    db.commit()


def turns(db, user_id: int, day: date, *, typed: int = 0, voice: int = 0) -> None:
    """Learner turns on one local day, as `_bump_usage` records them."""
    db.execute(
        """
        INSERT INTO conversation_usage (user_id, local_date, turns_learner, stt_calls)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, local_date) DO UPDATE
           SET turns_learner = conversation_usage.turns_learner + EXCLUDED.turns_learner,
               stt_calls     = conversation_usage.stt_calls + EXCLUDED.stt_calls
        """,
        (user_id, day, typed + voice, voice),
    )
    db.commit()


def written(db, user_id: int, day: date, *, is_english: bool = True) -> None:
    """One `writing_submissions` row, as `correct_submission` writes it."""
    db.execute(
        """
        INSERT INTO writing_submissions
            (user_id, day_kind, local_date, is_english, llm_input_tokens,
             llm_output_tokens, llm_cache_creation_input_tokens,
             llm_cache_read_input_tokens)
        VALUES (%s, 'journal', %s, %s, 100, 50, 0, 0)
        """,
        (user_id, day, is_english),
    )
    db.commit()


def watched(db, user_id: int, day: date, when: datetime | None) -> int:
    """A video assigned for ``day``; ``when`` is its completion, or None."""
    vid = db.execute(
        """
        INSERT INTO videos (youtube_id, channel_id, accent, track,
                            transcript_status, metadata_refreshed_at)
        VALUES (%s, 'w19-chan', 'british', 'life', 'ok', now())
        RETURNING id
        """,
        (f"w19-{secrets.token_hex(5)}",),
    ).fetchone()[0]
    db.execute(
        """
        INSERT INTO video_assignments (user_id, video_id, assigned_for, completed_at,
                                       score_breakdown)
        VALUES (%s, %s, %s, %s, '{}'::jsonb)
        """,
        (user_id, vid, day, when),
    )
    db.commit()
    return int(vid)


def drop_videos(db, video_ids: list[int]) -> None:
    db.rollback()
    for vid in video_ids:
        db.execute("DELETE FROM video_assignments WHERE video_id = %s", (vid,))
        db.execute("DELETE FROM videos WHERE id = %s", (vid,))
    db.commit()
