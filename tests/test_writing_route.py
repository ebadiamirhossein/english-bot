"""W16a: the journal's rulings, through the real ASGI transport.

Every request goes through `httpx.ASGITransport` into `create_app()`. Every
expected count is read back on this file's own connection with its own query,
never from the response under test (CLAUDE.md §3 rule 5). The model is stubbed
at `core.services.writing.chat`, and `core.llm._chat_anthropic` is replaced with
a guard so no test here can reach a provider.

**RED DEMONSTRATIONS, each run against a deliberate mutation before the test
was accepted (recorded in the decisions log):**
`JOURNAL_MAX_CORRECTIONS = 3` → the acceptance test; the `output` branch removed
from `_derive_done` → both Ruling 1 tests; `_own_session_today` returning the id
unchecked → the foreign-session test; the ceiling check removed → the sixth-
submission test; the submission row written before a 503 → the no-count test;
`response_model_exclude_none` removed → the absent-line test; `learner_label`
swapped for `label` → the label test; `logger.info(text)` added → the log test.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings

ENTRY = (
    "Today I go to the dentist in the morning. She only clean my teeth and it "
    "was fine. We watched two episodes from a series in the evening."
)


def correction(you_said, correct_form, code="verb_tense_past"):
    return {
        "you_said": you_said,
        "correct_form": correct_form,
        "error_type": code,
        "explanation": "It's already happened, so the verb moves into the past.",
    }


THREE = {
    "is_english": True,
    "corrections": [
        correction("Today I go to the dentist", "Today I went to the dentist"),
        correction("She only clean my teeth", "She only cleaned my teeth"),
        correction("two episodes from a series", "two episodes of a series", "preposition"),
    ],
    "did_well": "You say how the visit turned out, which rounds the day off.",
}

CLEAN = {"is_english": True, "corrections": [], "did_well": None}


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))
    monkeypatch.delenv("WRITING_MAX_SUBMISSIONS_PER_DAY", raising=False)


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    def _refuse(*args, **kwargs):
        raise AssertionError("a writing route test reached the real LLM transport")

    monkeypatch.setattr("core.llm._chat_anthropic", _refuse)


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


def _make_learner(db, name: str):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, explanation_language_fallback,
                           auth_email, auth_user_id, timezone)
        VALUES (%s, %s, 'fa', TRUE, 'B1', FALSE, %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, name, f"w16a-{abs(telegram_user_id)}@example.test", str(uuid.uuid4())),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        """
        INSERT INTO access_requests (telegram_user_id, user_id, display_name, status)
        VALUES (%s, %s, %s, 'approved')
        """,
        (telegram_user_id, user_id, name),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id, datetime.now(timezone.utc) + timedelta(days=30)),
    )
    db.commit()
    return type("L", (), {"user_id": user_id, "cookie": raw})()


def _drop_learner(db, learner) -> None:
    db.execute("DELETE FROM cards WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM errors WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (learner.user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (learner.user_id,))
    db.commit()


@pytest.fixture
def learner(db):
    one = _make_learner(db, "W16a Learner")
    yield one
    _drop_learner(db, one)


@pytest.fixture
def other(db):
    one = _make_learner(db, "W16a Other")
    yield one
    _drop_learner(db, one)


def request(app, method, path, *, json_body=None, cookies=None) -> httpx.Response:
    async def _go():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", cookies=cookies) as http:
            return await http.request(method, path, json=json_body)

    return asyncio.run(_go())


def jar(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


def stub_model(monkeypatch, payload, usage=(120, 80, 1721, 0)) -> list[dict]:
    seen: list[dict] = []

    def _chat(messages, **kwargs):
        seen.append({"messages": messages, **kwargs})
        if isinstance(payload, Exception):
            raise payload
        out = kwargs.get("usage_out")
        if out is not None:
            out["calls"] = out.get("calls", 0) + 1
            out["input_tokens"] = out.get("input_tokens", 0) + usage[0]
            out["output_tokens"] = out.get("output_tokens", 0) + usage[1]
            out["cache_creation_input_tokens"] = out.get("cache_creation_input_tokens", 0) + usage[2]
            out["cache_read_input_tokens"] = out.get("cache_read_input_tokens", 0) + usage[3]
        return payload

    monkeypatch.setattr("core.services.writing.chat", _chat)
    return seen


def post(app, learner, text=ENTRY, **extra):
    return request(app, "POST", "/correct", json_body={"text": text, **extra}, cookies=jar(learner))


def count(db, sql, *args) -> int:
    return int(db.execute(sql, args).fetchone()[0])


def block_four(app, learner) -> str:
    body = request(app, "GET", "/session/today", cookies=jar(learner)).json()
    return next(b["state"] for b in body["blocks"] if b["kind"] == "output")


# ── acceptance ───────────────────────────────────────────────────────────────


def test_journal_corrections_are_capped_at_two_on_screen_and_in_the_journal(
    app, db, learner, monkeypatch
) -> None:
    """**The TASKS Accept cell.** Three valid corrections from the model; two
    shown, two written — counted by a query of this test's own."""
    stub_model(monkeypatch, THREE)
    body = post(app, learner).json()
    assert len(body["corrections"]) == 2
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 2
    assert count(
        db, "SELECT count(*) FROM errors WHERE user_id = %s AND source = 'text'", learner.user_id
    ) == 2


def test_the_request_asks_for_two_and_guards_truncation(app, learner, monkeypatch) -> None:
    seen = stub_model(monkeypatch, CLEAN)
    post(app, learner)
    assert seen[0]["max_tokens"] == 2000
    assert seen[0]["reject_truncation"] is True
    assert seen[0]["json_mode"] is True
    assert "At most 2 corrections" in seen[0]["system"]


# ── Ruling 1: block 4 reaches done, from the log ─────────────────────────────


def test_a_submission_from_the_session_finishes_block_four(app, db, learner, monkeypatch) -> None:
    stub_model(monkeypatch, THREE)
    assert block_four(app, learner) == "ready"
    today = request(app, "GET", "/write/today", cookies=jar(learner)).json()
    assert today["session_id"] is not None
    assert post(app, learner, session_id=today["session_id"]).status_code == 200
    assert block_four(app, learner) == "done"
    assert count(
        db,
        "SELECT count(*) FROM writing_submissions WHERE user_id = %s AND session_id = %s",
        learner.user_id, today["session_id"],
    ) == 1


def test_a_clean_entry_also_finishes_block_four(app, db, learner, monkeypatch) -> None:
    """A clean entry writes no `errors` row — which is why `errors` could never
    have carried Ruling 1 — and still finishes the block."""
    stub_model(monkeypatch, CLEAN)
    session_id = request(app, "GET", "/session/today", cookies=jar(learner)).json()["session_id"]
    post(app, learner, session_id=session_id)
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 0
    assert block_four(app, learner) == "done"


def test_a_non_english_entry_counts_but_does_not_finish_block_four(
    app, db, learner, monkeypatch
) -> None:
    stub_model(monkeypatch, {"is_english": False, "corrections": [], "did_well": None})
    session_id = request(app, "GET", "/session/today", cookies=jar(learner)).json()["session_id"]
    post(app, learner, text="salam chetori khoobi hastam", session_id=session_id)
    assert block_four(app, learner) == "ready"
    assert count(
        db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s AND NOT is_english", learner.user_id
    ) == 1


def test_a_foreign_session_id_is_stored_as_null_and_touches_nothing(
    app, db, learner, other, monkeypatch
) -> None:
    stub_model(monkeypatch, CLEAN)
    theirs = request(app, "GET", "/session/today", cookies=jar(other)).json()["session_id"]
    response = post(app, learner, session_id=theirs)
    assert response.status_code == 200
    assert count(
        db, "SELECT count(*) FROM writing_submissions WHERE session_id = %s", theirs
    ) == 0
    assert count(
        db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s AND session_id IS NULL", learner.user_id
    ) == 1
    assert block_four(app, other) == "ready"


def test_yesterdays_session_id_is_not_linked(app, db, learner, monkeypatch) -> None:
    stub_model(monkeypatch, CLEAN)
    row = db.execute(
        """
        INSERT INTO sessions (user_id, date, task_type, delivered_at, completed)
        VALUES (%s, (now() AT TIME ZONE 'Europe/Vilnius')::date - 1, 'daily', now(), FALSE)
        RETURNING id
        """,
        (learner.user_id,),
    ).fetchone()
    db.commit()
    post(app, learner, session_id=int(row[0]))
    assert count(
        db, "SELECT count(*) FROM writing_submissions WHERE session_id = %s", int(row[0])
    ) == 0


def test_write_today_never_creates_a_session(app, db, learner) -> None:
    body = request(app, "GET", "/write/today", cookies=jar(learner)).json()
    # The route reads the wall clock, so the kind depends on the weekday; W16b's
    # service-level test below freezes a Thursday.
    assert body["session_id"] is None and body["ceiling_reached"] is False
    assert (body["day_kind"], body["prompt"] is None) in {("journal", True), ("paragraph", False)}
    assert count(db, "SELECT count(*) FROM sessions WHERE user_id = %s", learner.user_id) == 0


# ── Ruling 3: five a day, a boolean on the wire ──────────────────────────────


def test_the_sixth_submission_is_refused_without_a_call(app, db, learner, monkeypatch) -> None:
    seen = stub_model(monkeypatch, CLEAN)
    for _ in range(5):
        assert post(app, learner).status_code == 200
    assert request(app, "GET", "/write/today", cookies=jar(learner)).json()["ceiling_reached"] is True
    sixth = post(app, learner)
    assert sixth.status_code == 409
    assert sixth.json() == {"detail": "cap_reached"}
    assert len(seen) == 5
    assert count(db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s", learner.user_id) == 5


def test_a_provider_failure_writes_nothing_and_counts_nothing(app, db, learner, monkeypatch) -> None:
    from core.llm import LLMError

    stub_model(monkeypatch, LLMError("provider down"))
    assert post(app, learner).status_code == 503
    assert count(db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s", learner.user_id) == 0


def test_a_too_short_entry_counts_nothing(app, db, learner, monkeypatch) -> None:
    seen = stub_model(monkeypatch, CLEAN)
    assert post(app, learner, text="Tired").status_code == 422
    assert seen == []
    assert count(db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s", learner.user_id) == 0


def test_tokens_are_logged_per_submission(app, db, learner, monkeypatch) -> None:
    """F3: the cache counts are written too — the first live call sent 1,861
    input tokens and reported 140 as `input_tokens`. **Red demonstration:** the
    two cache values dropped from the INSERT turned this red."""
    stub_model(monkeypatch, CLEAN, usage=(140, 45, 1721, 12))
    post(app, learner)
    row = db.execute(
        """
        SELECT llm_input_tokens, llm_output_tokens, llm_cache_creation_input_tokens,
               llm_cache_read_input_tokens, day_kind
          FROM writing_submissions WHERE user_id = %s
        """,
        (learner.user_id,),
    ).fetchone()
    assert tuple(row) == (140, 45, 1721, 12, "journal")


def _ints(value, path=""):
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _ints(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _ints(v, f"{path}[{i}]")]
    return []


def test_no_number_crosses_the_wire_except_the_session_id(app, learner, monkeypatch) -> None:
    """Ruling 3 and CLAUDE.md §4: no count, no remaining, no reset time."""
    stub_model(monkeypatch, THREE)
    today = request(app, "GET", "/write/today", cookies=jar(learner)).json()
    corrected = post(app, learner).json()
    assert _ints(today) in ([], [".session_id"])
    assert _ints(corrected) == []


# ── Ruling 2: the opening line is absent, never a fallback ───────────────────


@pytest.mark.parametrize(
    "did_well",
    [None, "", "Nice.", "Good job!", "Nothing wrong in it.", "A 9/10 entry.", "Clear. And warm."],
)
def test_a_refused_opening_line_is_absent_from_the_wire(app, learner, monkeypatch, did_well) -> None:
    stub_model(monkeypatch, {"is_english": True, "corrections": [], "did_well": did_well})
    body = post(app, learner).json()
    assert "did_well" not in body
    assert "Nice." not in json.dumps(body)


def test_a_specific_opening_line_survives(app, learner, monkeypatch) -> None:
    stub_model(monkeypatch, THREE)
    assert post(app, learner).json()["did_well"] == THREE["did_well"]


# ── S3: the eyebrow comes from the taxonomy ──────────────────────────────────


def test_the_label_is_the_taxonomys_learner_label(app, db, learner, monkeypatch) -> None:
    stub_model(monkeypatch, THREE)
    expected = db.execute(
        "SELECT learner_label FROM error_types WHERE code = 'verb_tense_past'"
    ).fetchone()[0]
    assert post(app, learner).json()["corrections"][0]["label"] == expected


def test_a_spoken_code_is_refused_not_journalled(app, db, learner, monkeypatch) -> None:
    """**F6 FLIPPED THIS TEST, AND THE OLD ONE IS QUOTED (#82's shape).** It read
    `test_a_spoken_code_carries_no_label`, asserting such a correction was kept
    with no eyebrow. The prompt no longer shows the spoken codes, so one coming
    back is a code this prompt never offered: refused as unknown, never written.
    One list for what is offered and what is accepted."""
    stub_model(
        monkeypatch,
        {"is_english": True, "did_well": None,
         "corrections": [correction("Today I go to the dentist", "Today I went to the dentist", "filler_overuse")]},
    )
    assert post(app, learner).json()["corrections"] == []
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 0


# ── G1 / G2 at the route ─────────────────────────────────────────────────────


def test_a_correction_of_words_the_learner_did_not_write_is_not_journalled(
    app, db, learner, monkeypatch
) -> None:
    stub_model(
        monkeypatch,
        {"is_english": True, "did_well": None,
         "corrections": [correction("Yesterday I go to the cinema", "Yesterday I went to the cinema")]},
    )
    assert post(app, learner).json()["corrections"] == []
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 0


def test_a_misspelling_is_not_journalled(app, db, learner, monkeypatch) -> None:
    stub_model(
        monkeypatch,
        {"is_english": True, "did_well": None,
         "corrections": [correction("togehter", "together", "word_order")]},
    )
    post(app, learner, text="We went togehter to the dentist this morning.")
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 0


# ── W16b's kind is not W16a's ───────────────────────────────────────────────


def test_an_unknown_day_kind_is_refused(app, db, learner, monkeypatch) -> None:
    """**W16b inverted W16a's `test_w16a_refuses_a_paragraph`** (quoted, #82): the
    paragraph is now written, so the refusal moves to a kind that does not exist."""
    seen = stub_model(monkeypatch, CLEAN)
    assert post(app, learner, day_kind="essay").status_code == 422
    assert seen == []


# ── CLAUDE.md §5: the entry is never kept ────────────────────────────────────


def test_the_entry_reaches_no_log_line(app, learner, monkeypatch, caplog) -> None:
    marker = "zqxj-unique-w16a-marker"
    stub_model(monkeypatch, THREE)
    with caplog.at_level(logging.DEBUG):
        post(app, learner, text=f"{ENTRY} {marker}")
    assert marker not in caplog.text


# ── W16b: the paragraph ──────────────────────────────────────────────────────
#
# **RED DEMONSTRATIONS** (decisions log): `max_corrections("paragraph")` returning
# 9 → the cap test; `structure=` dropped from `result_out` → the structure test;
# `offers.select` bypassed → the offers test; `in_deck` hardcoded False → the
# in-deck test; the offer rule removed from `keep_phrase` → the refused-phrase
# keep test; the `lower(front)` pre-check removed → the second-keep test.

PARAGRAPH = (
    "I think is a good idea to move in another country for work, but it depends of "
    "the person. My cousin moved to Norway three years ago and now he earn much more "
    "money than before. But he told me that he miss his family very much, and in the "
    "winter he is alone."
)


def para_correction(you_said, correct_form, code, keep=None):
    return {
        "you_said": you_said, "correct_form": correct_form, "error_type": code,
        "explanation": "It reads more naturally this way.", "keep": keep,
    }


PARA = {
    "is_english": True,
    "did_well": "This is ignored on the paragraph.",
    "structure": [
        {"segments": [{"text": "You give your opinion first and then back it with one real example.", "quote": False}]},
        {"segments": [
            {"text": "The turn at ", "quote": False},
            {"text": "But he told me", "quote": True},
            {"text": " is the strongest part.", "quote": False},
        ]},
    ],
    "corrections": [
        para_correction("it depends of the person", "it depends on the person", "preposition", "to depend on"),
        para_correction("now he earn much more money", "now he earns much more money", "subject_verb_agreement"),
        para_correction("he miss his family", "he misses his family", "subject_verb_agreement", "to miss someone"),
    ],
}


def post_paragraph(app, learner, text=PARAGRAPH):
    return post(app, learner, text=text, day_kind="paragraph")


def test_the_paragraph_returns_structure_offers_and_no_opening_line(app, db, learner, monkeypatch) -> None:
    """**The W16 row's second criterion: structure feedback, and errors written to
    the journal** — counted by this test's own query."""
    seen = stub_model(monkeypatch, PARA)
    body = post_paragraph(app, learner).json()
    assert "At most 8 corrections" in seen[0]["system"]
    assert len(body["structure"]) == 2
    assert body["structure"][1]["segments"][1] == {"text": "But he told me", "quote": True}
    assert "did_well" not in body
    assert [o["phrase"] for o in body["word_offers"]] == ["to depend on", "to miss someone"]
    assert all(o["in_deck"] is False for o in body["word_offers"])
    assert body["word_offers"][0]["sentence"] == "it depends on the person"
    assert "keep" not in body["corrections"][0], "the nominated phrase never reaches the wire"
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s AND source = 'text'", learner.user_id) == 3
    assert count(
        db, "SELECT count(*) FROM writing_submissions WHERE user_id = %s AND day_kind = 'paragraph'", learner.user_id
    ) == 1


def test_the_paragraph_caps_at_eight(app, db, learner, monkeypatch) -> None:
    names = ["Anna", "Ben", "Carl", "Dora", "Emil", "Fay", "Gus", "Hana", "Ivo", "Jan"]
    text = " ".join(f"{n} go home." for n in names)
    stub_model(monkeypatch, {
        "is_english": True, "structure": [],
        "corrections": [para_correction(f"{n} go home", f"{n} goes home", "subject_verb_agreement") for n in names],
    })
    body = post_paragraph(app, learner, text=text).json()
    assert len(body["corrections"]) == 8
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 8


def test_an_invented_quote_makes_structure_absent_and_keeps_the_corrections(app, learner, monkeypatch) -> None:
    bad = {**PARA, "structure": [{"segments": [{"text": "But she said", "quote": True}]}]}
    stub_model(monkeypatch, bad)
    body = post_paragraph(app, learner).json()
    assert "structure" not in body
    assert len(body["corrections"]) == 3


def test_the_journal_carries_no_structure_and_no_offers(app, learner, monkeypatch) -> None:
    stub_model(monkeypatch, PARA)
    body = post(app, learner, text=PARAGRAPH).json()
    assert "structure" not in body
    assert body["word_offers"] == []


def test_a_kept_phrase_shows_as_in_deck_next_time(app, db, learner, monkeypatch) -> None:
    stub_model(monkeypatch, PARA)
    keep = request(app, "POST", "/write/keep", json_body={"phrase": "to depend on", "sentence": "it depends on the person"}, cookies=jar(learner))
    assert keep.json() == {"status": "saved"}
    offers = post_paragraph(app, learner).json()["word_offers"]
    assert offers[0] == {"phrase": "to depend on", "sentence": "it depends on the person", "in_deck": True}
    assert offers[1]["in_deck"] is False


def keep(app, learner, phrase, sentence):
    return request(app, "POST", "/write/keep", json_body={"phrase": phrase, "sentence": sentence}, cookies=jar(learner))


def test_keep_saves_one_card_with_its_sentence_and_then_says_already(app, db, learner) -> None:
    """Deck write through the real route (CLAUDE.md §3 rule 1)."""
    assert keep(app, learner, "to depend on", "it depends on the person").json() == {"status": "saved"}
    assert keep(app, learner, "To depend on", "it depends on the person").json() == {"status": "already"}
    rows = db.execute(
        """
        SELECT front, card_type, register, register_source, context_sentence, source_title, fsrs_state
          FROM cards WHERE user_id = %s
        """,
        (learner.user_id,),
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("to depend on", "recognition", "neutral", "import_default", "it depends on the person", "writing", "learning")
    ]
    db.execute("DELETE FROM cards WHERE user_id = %s", (learner.user_id,))
    db.commit()


@pytest.mark.parametrize(
    ("phrase", "sentence"),
    [
        ("to experinence", "I had experience"),  # a word that does not resolve
        ("to depend upon", "it depends on the person"),  # a word not in the sentence
        ("weed", "we'd like to come"),  # the learner's slip, not the app's text
        ("x" * 81, "it depends on the person"),  # too long for the request model
    ],
)
def test_keep_refuses_a_phrase_that_would_not_have_been_offered(app, db, learner, phrase, sentence) -> None:
    """**Closes on this surface the gap #408 records for `/talk`.**"""
    assert keep(app, learner, phrase, sentence).status_code == 422
    assert count(db, "SELECT count(*) FROM cards WHERE user_id = %s", learner.user_id) == 0


def test_keep_requires_a_session(app) -> None:
    response = request(app, "POST", "/write/keep", json_body={"phrase": "to depend on", "sentence": "it depends on the person"})
    assert response.status_code == 401


def test_thursday_serves_the_units_task_verbatim(db, learner) -> None:
    """Service level: the route reads the wall clock and a test must not (§3 rule 6).
    The expected string is read from `data/syllabus_units.json`, not from the service."""
    import json as _json
    from pathlib import Path as _Path

    from core.services import writing

    units = _json.loads((_Path(__file__).resolve().parents[1] / "data" / "syllabus_units.json").read_text(encoding="utf-8"))
    unit1 = next(u for u in units if u["unit_number"] == 1)["output_task_written"]
    thursday = writing.today(learner.user_id, now=datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc))
    assert (thursday.day_kind, thursday.prompt) == ("paragraph", unit1)
    wednesday = writing.today(learner.user_id, now=datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc))
    assert (wednesday.day_kind, wednesday.prompt) == ("journal", None)
