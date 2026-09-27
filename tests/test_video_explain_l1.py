"""W31c — `core.video.explain`'s learner-language meanings and its line lookup.

**THE TRANSPORT IS MOCKED AT `core.llm.anthropic.Anthropic`**, as
`tests/test_video_injection.py` does (standing rule 7): what is asserted is
what the wrapper really builds. **No billed call is made** — and no real call
either: the prompt change is not `llm.py` request construction (CLAUDE.md §3.2),
and the operator's first `explain --apply` is the live check (Next action).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from core.config import load_settings
from core.video import explain


def _reply(payload: dict) -> MagicMock:
    message = MagicMock()
    block = MagicMock()
    block.text = json.dumps(payload)
    message.content = [block]
    message.stop_reason = "end_turn"
    return message


@pytest.fixture
def client():
    with patch("core.llm.anthropic.Anthropic") as cls:
        yield cls.return_value


GOOD = {
    "definition": "a huge extinct animal like an elephant",
    "register": "neutral",
    "neutral_equivalent": None,
    "who_says_this": None,
}


# ── the request ─────────────────────────────────────────────────────────────


def test_the_languages_are_asked_for_outside_the_data_block(client) -> None:
    client.messages.create.return_value = _reply({**GOOD, "l1": {"fa": "ماموت"}})
    explain.explain_one("mastodon", "is that a mastodon?", l1=("fa", "lt"),
                        settings=load_settings())
    user = client.messages.create.call_args.kwargs["messages"][0]["content"]
    head, block = user.split(explain.OPEN, 1)
    assert "Meaning in: fa (Persian (Farsi)), lt (Lithuanian)" in head
    assert "Meaning in" not in block


def test_an_unknown_language_code_is_never_asked_for() -> None:
    content = explain.build_messages("epoch", "we call it Epoch", ("xx", "lt"))[0]["content"]
    assert "Meaning in: lt (Lithuanian)" in content
    assert "xx" not in content


def test_no_languages_means_no_request_for_any() -> None:
    content = explain.build_messages("epoch", "we call it Epoch")[0]["content"]
    assert "Meaning in" not in content


# ── the reply ───────────────────────────────────────────────────────────────


def test_the_requested_meanings_are_kept() -> None:
    draft = explain.validate(
        "mastodon", {**GOOD, "l1": {"fa": "ماموت", "lt": "mastodontas"}}, ("fa", "lt")
    )
    assert draft.l1 == {"fa": "ماموت", "lt": "mastodontas"}


def test_a_missing_or_unusable_language_is_absent_and_nothing_is_edited() -> None:
    draft = explain.validate(
        "mastodon",
        {**GOOD, "l1": {"fa": "  ", "lt": "x" * 201, "es": "mamut"}},
        ("fa", "lt"),
    )
    # fa empty, lt over-long, es never asked for: none of them is stored.
    assert draft.l1 == {}
    assert draft.definition == GOOD["definition"]


def test_an_l1_that_is_not_an_object_refuses_the_whole_draft() -> None:
    with pytest.raises(explain.GlossRejected):
        explain.validate("mastodon", {**GOOD, "l1": ["ماموت"]}, ("fa",))


def test_an_l1_nobody_asked_for_is_ignored() -> None:
    assert explain.validate("mastodon", {**GOOD, "l1": {"fa": "ماموت"}}).l1 == {}


# ── the line ────────────────────────────────────────────────────────────────


def test_the_line_is_the_display_line_and_a_lemma_finds_its_inflection() -> None:
    cues = [
        {"text": ">> HEY, ROSS! THE PARTIES", "start": 0.0, "duration": 2.4},
        {"text": "WERE GREAT.", "start": 1.8, "duration": 2.0},
        {"text": "I told Ross about them.", "start": 4.0, "duration": 2.0},
    ]
    text = " ".join(c["text"] for c in cues)
    line, start = explain._line_for(text, cues, "party")
    assert (line, start) == ("Hey, Ross! The parties were great.", 0.0)


def test_a_word_inside_another_word_is_not_a_match() -> None:
    cues = [{"text": "that party was fun.", "start": 0.0, "duration": 2.0}]
    assert explain._line_for("that party was fun.", cues, "part") == (None, None)


def test_without_cues_the_line_is_an_untimed_sentence() -> None:
    text = "we went out. the parties were great. then we left."
    assert explain._line_for(text, None, "party") == ("the parties were great.", None)


# ── the command writes what it was given ────────────────────────────────────


def test_apply_stores_the_meanings_and_says_manual(client) -> None:
    """User action: the operator runs `python -m core.video.explain --video N
    --user U --apply`. The model is the mocked transport; the rows are real."""
    from core.services import video as svc

    client.messages.create.return_value = _reply({**GOOD, "l1": {"fa": "ماموت"}})
    youtube_id = f"rt31x{secrets.token_hex(3)}"
    with psycopg.connect(load_settings().database_url) as conn:
        user_id = conn.execute(
            "INSERT INTO users (telegram_user_id, name, native_language, onboarded, "
            "known_word_floor) VALUES (%s, 'W31c explain', 'fa', TRUE, 0) RETURNING id",
            (-secrets.randbelow(10**9) - 1,),
        ).fetchone()[0]
        video_id = svc.upsert_video(
            conn, youtube_id=youtube_id, channel_id="UCw31cexplain00000000000",
            accent="british", track="life", title="probe", duration_s=30,
            published_at=datetime.now(timezone.utc) - timedelta(days=1),
            now=datetime.now(timezone.utc),
        )
        svc.record_transcript(conn, video_id=video_id, text="is that a mastodon?",
                              lang="en", kind="manual")
        conn.commit()
    try:
        written = explain.run(video_id, user_id, apply=True, limit=1)
        assert written == 1
        with psycopg.connect(load_settings().database_url) as conn:
            word, l1, source = conn.execute(
                "SELECT word, l1, source FROM video_glosses WHERE video_id = %s", (video_id,)
            ).fetchone()
        assert source == "manual"
        assert l1.get("fa") == "ماموت"
        assert word
    finally:
        with psycopg.connect(load_settings().database_url) as conn:
            conn.execute("DELETE FROM videos WHERE youtube_id = %s", (youtube_id,))
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
