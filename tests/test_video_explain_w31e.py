"""W31e — the first live `explain --apply`'s two findings: the token budget and names.

The operator's run of 2026-09-27 (`--video 44 --user 3 --limit 20 --apply`)
wrote 15 glosses and refused 2, **both at `max_tokens=400`**: *shed* came back
`blocks=['ThinkingBlock'] chars=0` (the whole budget spent thinking) and
*dinosaur* `blocks=['ThinkingBlock','TextBlock'] chars=259`, its JSON cut off
inside the `fa` string. And it planned and glossed *phillips* — the name in
*"Thank you, Dr. Phillips."*.

**THE TRANSPORT IS MOCKED AT `core.llm.anthropic.Anthropic`** (standing rule
7), so `chat()`'s own truncation handling is what runs. **The mock enforces the
budget it is sent**: a reply that needs more output than `max_tokens` comes back
the way the live model's did — thinking first, then as much text as fits, with
`stop_reason="max_tokens"`. That is the property the old 400 failed and the
only one a mock can check; that the model's real replies fit is the operator's
re-run (Next action), not this file. **No billed call is made.**

**RED BEFORE THE CODE (2026-09-27):** `explain.MAX_TOKENS` did not exist and
`explain_one` sent 400; `plan_for` planned *phillips*; `fill_pending` spent a
call on it.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from core.config import load_settings
from core.services import video as video_svc
from core.services import words as words_svc
from core.video import explain

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PREFIX = "w31eexp"
TRANSCRIPT = "Welcome to the museum. Thank you, Dr. Phillips."

GOOD = {
    "definition": "a big old bone animal that lived long ago",
    "register": "neutral",
    "neutral_equivalent": None,
    "who_says_this": None,
    "l1": {"fa": "دایناسور", "lt": "dinozauras"},
}


# ── a transport that enforces `max_tokens` the way the model does ────────────


class ThinkingBlock:  # `type(b).__name__` is what `core.llm` logs and tests
    def __init__(self) -> None:
        self.thinking = ""


class TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


def _response(*, max_tokens: int, thinking: int, text: str, reply_tokens: int) -> MagicMock:
    """Thinking is spent first; the text gets what is left. Cut → `max_tokens`."""
    message = MagicMock()
    usage = MagicMock()
    usage.input_tokens = 640
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    if thinking >= max_tokens:
        message.content = [ThinkingBlock()]
        message.stop_reason = "max_tokens"
        usage.output_tokens = max_tokens
    elif thinking + reply_tokens > max_tokens:
        room = max_tokens - thinking
        cut = int(len(text) * room / reply_tokens)
        message.content = [ThinkingBlock(), TextBlock(text[:cut])]
        message.stop_reason = "max_tokens"
        usage.output_tokens = max_tokens
    else:
        message.content = [ThinkingBlock(), TextBlock(text)]
        message.stop_reason = "end_turn"
        usage.output_tokens = thinking + reply_tokens
    message.usage = usage
    return message


@pytest.fixture
def client():
    with patch("core.llm.anthropic.Anthropic") as cls:
        yield cls.return_value


def _model(client, *, thinking: int, reply_tokens: int, payload: dict = GOOD) -> list[int]:
    """Every call answers under the budget it was SENT. Returns the budgets."""
    sent: list[int] = []
    text = json.dumps(payload, ensure_ascii=False)

    def create(**kwargs):
        sent.append(kwargs["max_tokens"])
        return _response(max_tokens=kwargs["max_tokens"], thinking=thinking,
                         text=text, reply_tokens=reply_tokens)

    client.messages.create.side_effect = create
    return sent


# ── 1. the budget ────────────────────────────────────────────────────────────


def test_the_budget_is_thinking_headroom_plus_the_longest_reply() -> None:
    """Hardcoded, not derived from the module (rule 5): 2,000 of thinking
    headroom (`core.items.gates`), the 400 the English object had alone before
    W31c, and 200 characters for each of the two learner languages, at worst
    one token a character."""
    from core.items.gates import THINKING_HEADROOM_TOKENS

    assert THINKING_HEADROOM_TOKENS == 2000
    assert explain.MAX_TOKENS >= 2000 + 400 + 2 * 200
    assert explain.MAX_TOKENS >= THINKING_HEADROOM_TOKENS + explain.REPLY_TOKENS
    assert explain.REPLY_TOKENS >= 400 + 2 * explain.L1_MAX_CHARS


def test_explain_one_sends_that_budget(client) -> None:
    sent = _model(client, thinking=100, reply_tokens=200)
    explain.explain_one("dinosaur", "is that a dinosaur?", l1=("fa", "lt"),
                        settings=load_settings())
    assert sent == [explain.MAX_TOKENS]


def test_a_reply_that_needed_more_than_400_is_now_whole(client) -> None:
    """*dinosaur*'s shape: thinking plus a two-language reply past 400. At the
    old budget this came back cut inside `fa`; inside the new one it is whole."""
    _model(client, thinking=1500, reply_tokens=600)
    draft = explain.explain_one("dinosaur", "is that a dinosaur?", l1=("fa", "lt"),
                                settings=load_settings())
    assert draft.l1 == {"fa": "دایناسور", "lt": "dinozauras"}


# ── 2. what is refused is still refused, and never stored ───────────────────


@pytest.fixture
def world():
    telegram = -secrets.randbelow(10**9) - 1
    youtube_id = f"{PREFIX}{secrets.token_hex(3)}"
    with psycopg.connect(load_settings().database_url) as conn:
        user = conn.execute(
            "INSERT INTO users (telegram_user_id, name, native_language, onboarded, "
            "known_word_floor, timezone) VALUES (%s, 'W31e explain', 'fa', TRUE, 0, 'UTC') "
            "RETURNING id",
            (telegram,),
        ).fetchone()[0]
        video = video_svc.upsert_video(
            conn, youtube_id=youtube_id, channel_id="UCw31eexplain000000000000",
            accent="british", track="life", title="W31e probe", duration_s=30,
            published_at=NOW - timedelta(days=1), now=NOW,
        )
        video_svc.record_transcript(conn, video_id=video, text=TRANSCRIPT,
                                    lang="en", kind="manual")
        conn.commit()
    yield {"user": user, "video": video}
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute("DELETE FROM word_saves_pending WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM cards WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM videos WHERE youtube_id = %s", (youtube_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))
        conn.commit()


def _stored(video: int) -> int:
    with psycopg.connect(load_settings().database_url) as conn:
        return conn.execute(
            "SELECT count(*) FROM video_glosses WHERE video_id = %s", (video,)
        ).fetchone()[0]


def test_a_thinking_only_reply_is_refused_and_nothing_is_stored(client, world) -> None:
    """*shed*'s shape, at any budget: thinking used all of it."""
    _model(client, thinking=10**6, reply_tokens=200)
    assert explain.run(world["video"], world["user"], apply=True, limit=1) == 0
    assert _stored(world["video"]) == 0


def test_a_truncated_json_reply_is_refused_and_nothing_is_stored(client, world) -> None:
    """A reply cut inside a string is discarded, never repaired or half-stored."""
    _model(client, thinking=explain.MAX_TOKENS - 50, reply_tokens=600)
    assert explain.run(world["video"], world["user"], apply=True, limit=1) == 0
    assert _stored(world["video"]) == 0


def test_a_whole_reply_inside_the_new_budget_is_stored(client, world) -> None:
    _model(client, thinking=1500, reply_tokens=600)
    assert explain.run(world["video"], world["user"], apply=True, limit=1) == 1
    assert _stored(world["video"]) == 1


# ── 3. names: no gloss, no call ─────────────────────────────────────────────


def test_a_name_is_not_planned_and_an_ordinary_word_still_is(world) -> None:
    """*"Thank you, Dr. Phillips."* — W31b's per-video proper-noun set (C1)
    decides, not a second rule. *Phillips* follows *Dr.*, whose full stop is not
    a sentence end."""
    from core.db import connection

    with connection() as conn:
        plan = explain.plan_for(conn, world["video"], world["user"])
    planned = {word for word, _line, _start in plan.words}
    assert "museum" in planned
    assert "phillips" not in planned


def test_the_proper_noun_set_reads_a_name_after_a_title() -> None:
    from core.video.lines import names_for

    names = names_for(None, TRANSCRIPT)
    assert "phillips" in names
    assert "museum" not in names


def test_the_job_spends_no_call_on_a_name(world, monkeypatch) -> None:
    """A tap on *Phillips* still saves (today's path writes the pending row);
    the job resolves it without a call. *museum* is still explained."""
    made: list[str] = []

    def fake(word, line, *, l1=(), settings=None):
        made.append(word)
        return explain.Draft(word=word, definition="a place with old things to see",
                             register="neutral", neutral_equivalent=None,
                             who_says_this=None, l1={})

    monkeypatch.setattr(explain, "explain_one", fake)
    with psycopg.connect(load_settings().database_url) as conn:
        for word, sentence in (("phillips", "Thank you, Dr. Phillips."),
                               ("museum", "Welcome to the museum.")):
            conn.execute(
                "INSERT INTO word_saves_pending (user_id, video_id, word, context_sentence, "
                "created_at) VALUES (%s, %s, %s, %s, %s)",
                (world["user"], world["video"], word, sentence, NOW - timedelta(minutes=5)),
            )
        conn.commit()

    counts = words_svc.fill_pending(NOW)

    assert made == ["museum"]
    assert counts.names == 1
    with psycopg.connect(load_settings().database_url) as conn:
        states = dict(conn.execute(
            "SELECT word, state FROM word_saves_pending WHERE user_id = %s", (world["user"],)
        ).fetchall())
    assert states == {"phillips": "no_meaning", "museum": "carded"}
