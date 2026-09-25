"""W17 — weak spots from the error journal: evidence, serving, and generation.

**The user action these tests exercise:** a learner opens today's session and
reaches block 3 (`GET /session/today`, through the real ASGI transport, against
the Mac dev database), and the operator runs `python -m core.items.drills`.

**Every test here states its red method in its docstring**, and each was run red
before it was trusted: the mutation named was applied to the code, the test was
seen to fail, and the mutation was reverted.

The journal rows below are seeded with a plain INSERT on purpose: these are
FIXTURES for the evidence rule, and `record_errors` stamps `created_at = now()`,
which cannot seed a row outside the window.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.items import drills as gen
from core.items import generate
from core.items.gates import ValidationReport
from core.items.schema import parse
from core.services import drills as drills_svc
from core.services import items as items_svc

NOW = datetime.now(timezone.utc)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


def _make_learner(db, name: str, l1: str):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    user_id = int(db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, %s, %s, TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, name, l1, f"w17-{abs(telegram_user_id)}@example.test",
         str(uuid.uuid4())),
    ).fetchone()[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, status)"
        " VALUES (%s, %s, %s, 'approved')",
        (telegram_user_id, user_id, name),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id, NOW + timedelta(days=30)),
    )
    db.commit()
    return type("L", (), {"user_id": user_id, "cookie": raw})()


def _drop_learner(db, user_id: int) -> None:
    for sql in (
        "DELETE FROM item_attempts WHERE user_id = %s",
        "DELETE FROM sessions WHERE user_id = %s",
        "DELETE FROM errors WHERE user_id = %s",
        "DELETE FROM items WHERE user_id = %s",
        "DELETE FROM access_requests WHERE user_id = %s",
        "DELETE FROM users WHERE id = %s",
    ):
        db.execute(sql, (user_id,))
    db.commit()


@pytest.fixture
def learner(db):
    one = _make_learner(db, "W17 Farsi", "fa")
    yield one
    _drop_learner(db, one.user_id)


@pytest.fixture
def other(db):
    one = _make_learner(db, "W17 Lithuanian", "lt")
    yield one
    _drop_learner(db, one.user_id)


def request(app, method, path, *, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     cookies=cookies) as http:
            return await http.request(method, path)

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


def _journal(db, learner, error_type: str, n: int, *, days_ago: int = 1,
             source: str = "text") -> None:
    for i in range(n):
        db.execute(
            """
            INSERT INTO errors (user_id, created_at, source, you_said, correct_form,
                                error_type, next_review)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE + 1)
            """,
            (learner.user_id, NOW - timedelta(days=days_ago, minutes=i), source,
             f"fixture {i}", f"fixture {i}.", error_type),
        )
    db.commit()


_N = iter(range(10_000))


def _item(db, learner, *, cohort: str = "drill", error_type: str | None = "article_missing",
          unit_number: int | None = None, prompt: str | None = None) -> int:
    """One validated item through the real writer (`insert_item`)."""
    n = next(_N)
    draft = {
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": prompt or f"She bought ___ umbrella on day {n}.",
        "answer": "an",
        "accepted_variants": ["an"],
        "grammar_target": gen.DRILL_TARGETS.get(error_type or "", "past simple"),
        "explanation": "An, because umbrella starts with a vowel sound.",
        "definition": "article before a vowel sound",
        "l1_gloss": "یک",
        "cohort": cohort,
    }
    if error_type:
        draft["error_type"] = error_type
    if unit_number is not None:
        draft["unit_number"] = unit_number
    item_id = items_svc.insert_item(
        learner.user_id, parse(draft),
        ValidationReport("passed", acceptable=("an",), canonical="an"),
        model="test-model",
    )
    db.commit()
    assert item_id is not None
    return item_id


def _focus(app, learner) -> dict:
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    return body["blocks"][2]


# ── the evidence rule ───────────────────────────────────────────────────────


def test_three_rows_evidence_a_pattern_and_two_do_not(db, learner) -> None:
    """**Red method:** set `EVIDENCE_MIN_ROWS = 2` — the two-row pattern appears
    and the first assertion fails. Expected values are hardcoded (§3 rule 5)."""
    _journal(db, learner, "article_missing", 2)
    assert drills_svc.evidenced_patterns(learner.user_id, now=NOW) == []
    _journal(db, learner, "article_missing", 1)
    [pattern] = drills_svc.evidenced_patterns(learner.user_id, now=NOW)
    assert (pattern.code, pattern.learner_label, pattern.evidence) == (
        "article_missing", "Articles", 3)


def test_evidence_outside_the_window_is_not_evidence(db, learner) -> None:
    """Rows older than 60 days do not count. **Red method:** delete the
    `created_at >= %s` predicate — the old rows evidence the pattern and the
    assertion fails. Time is passed in, never read from the clock (§3 rule 6)."""
    _journal(db, learner, "preposition", 5, days_ago=61)
    assert drills_svc.evidenced_patterns(learner.user_id, now=NOW) == []
    # The same rows ARE evidence when "now" is 61 days earlier.
    assert [p.code for p in drills_svc.evidenced_patterns(
        learner.user_id, now=NOW - timedelta(days=2))] == ["preposition"]


def test_someone_else_s_english_is_not_evidence(db, learner) -> None:
    """`capture` and `video` rows never evidence a pattern. **Red method:** empty
    `NOT_EVIDENCE_SOURCES` — the capture rows evidence the pattern."""
    _journal(db, learner, "collocation", 3, source="capture")
    _journal(db, learner, "collocation", 2, source="video")
    assert drills_svc.evidenced_patterns(learner.user_id, now=NOW) == []


def test_a_code_with_no_learner_label_is_never_a_pattern(db, learner) -> None:
    """The three spoken codes have no `learner_label` and are never drilled.
    **Red method:** drop `et.learner_label IS NOT NULL` — the filler row appears."""
    _journal(db, learner, "filler_overuse", 4)
    assert drills_svc.evidenced_patterns(learner.user_id, now=NOW) == []


def test_every_drill_target_is_a_labelled_code_and_every_labelled_code_has_one(db) -> None:
    """`DRILL_TARGETS` and migration 027's sixteen labels are the same set.
    **Red method:** delete one entry from `DRILL_TARGETS` — the sets differ."""
    labelled = {row[0] for row in db.execute(
        "SELECT code FROM error_types WHERE learner_label IS NOT NULL").fetchall()}
    assert len(labelled) == 16
    assert set(gen.DRILL_TARGETS) == labelled


# ── serving ─────────────────────────────────────────────────────────────────


def test_an_unevidenced_pattern_is_never_drilled(app, db, learner) -> None:
    """A learner who HOLDS drills but whose journal does not evidence the pattern
    is served none. **Silence is not mastery, and it is not a reason to drill
    either.** **Red method:** make `_weak_spot_drills` pass every code that has
    drills instead of the evidenced ones — the drill is served."""
    _item(db, learner, error_type="article_missing")
    _journal(db, learner, "article_missing", 2)  # one short of evidence
    items = _focus(app, learner)["payload"]["items"]
    assert items == []


def test_the_two_learners_receive_different_drills_for_their_different_journals(
    app, db, learner, other
) -> None:
    """**The TASKS acceptance, as the run prompt rules it: different journals,
    different drills.** Two seeded learners, each with evidence of a different
    pattern and a drill bank for both patterns; each is served only their own
    evidenced pattern, labelled with its plain label.
    **Red method:** serve drills without the evidence filter (pass all codes) —
    both learners receive both patterns and the label sets are equal."""
    for one in (learner, other):
        _item(db, one, error_type="article_missing")
        _item(db, one, error_type="verb_tense_past")
    _journal(db, learner, "article_missing", 3)
    _journal(db, other, "verb_tense_past", 4)

    mine = _focus(app, learner)["payload"]["items"]
    theirs = _focus(app, other)["payload"]["items"]
    assert [i["pattern"] for i in mine] == ["Articles"]
    assert [i["pattern"] for i in theirs] == ["Past tense"]
    assert {i["id"] for i in mine}.isdisjoint({i["id"] for i in theirs})


def test_no_count_crosses_the_wire(app, db, learner) -> None:
    """A drill carries its label and nothing that counts. **Red method:** add
    `"evidence": pattern.evidence` to the item dict — the key set differs and a
    digit appears in the drill's non-projection fields."""
    _item(db, learner, error_type="subject_verb_agreement")
    _journal(db, learner, "subject_verb_agreement", 7)
    [drill] = _focus(app, learner)["payload"]["items"]
    assert set(drill) == {"id", "response_mode", "projection", "seen", "pattern"}
    assert drill["pattern"] == "Subject and verb"
    assert not re.search(r"\d", drill["pattern"])
    assert "7" not in json.dumps({k: v for k, v in drill.items() if k != "projection"
                                  and k != "id"})


def test_drills_share_the_eight_and_come_after_the_unit_s_items(app, db, learner) -> None:
    """With a full unit bank, block 3 is still eight: six unit items then two drills.
    **Red method:** drop the `limit=FOCUS_ITEM_COUNT - len(drills)` argument —
    block 3 serves ten."""
    unit_ids = [
        _item(db, learner, cohort="focus", error_type=None, unit_number=1,
              prompt=f"I ___ to the market on Friday {k}.")
        for k in range(8)
    ]
    a = _item(db, learner, error_type="article_missing")
    b = _item(db, learner, error_type="preposition")
    _journal(db, learner, "article_missing", 3)
    _journal(db, learner, "preposition", 3)
    items = _focus(app, learner)["payload"]["items"]
    assert len(items) == items_svc.FOCUS_ITEM_COUNT == 8
    assert [i["id"] for i in items[:6]] == unit_ids[:6]
    assert {i["id"] for i in items[6:]} == {a, b}
    assert all("pattern" not in i for i in items[:6])
    assert sorted(i["pattern"] for i in items[6:]) == ["Articles", "Prepositions"]


def test_one_drill_per_pattern_before_any_pattern_gets_two(db, learner) -> None:
    """Rotation, not rank (#412): the pattern with more rows does not take both
    slots. **Red method:** remove the one-per-pattern pass in `drill_items` — the
    two oldest drills (both articles) are served."""
    first = _item(db, learner, error_type="article_missing")
    _item(db, learner, error_type="article_missing")
    third = _item(db, learner, error_type="word_order")
    served = items_svc.drill_items(learner.user_id,
                                   codes=["article_missing", "word_order"])
    assert [one.id for one in served] == [first, third]


def test_a_drill_is_never_unit_practice(db, learner) -> None:
    """Even a drill written WITH a unit number is not served by `bank_for_session`.
    **Red method:** remove the `<> 'drill'` cohort exclusion — the drill is
    served as unit practice."""
    drill = _item(db, learner, error_type="article_missing", unit_number=1)
    served = items_svc.bank_for_session(learner.user_id, unit_number=1)
    assert drill not in [one.id for one in served]


def test_the_session_s_drills_survive_a_refetch(app, db, learner) -> None:
    """The eight are a stored fact (#275); the labels come back with them.
    **Red method:** read labels only at first hydration — the refetch loses
    `pattern`."""
    drill = _item(db, learner, error_type="modal_verb")
    _journal(db, learner, "modal_verb", 3)
    first = _focus(app, learner)["payload"]["items"]
    # Evidence ageing out mid-day does not re-shuffle a session already served.
    db.execute("DELETE FROM errors WHERE user_id = %s", (learner.user_id,))
    db.commit()
    again = _focus(app, learner)["payload"]["items"]
    assert [i["id"] for i in first] == [i["id"] for i in again] == [drill]
    assert again[0]["pattern"] == "Modal verbs"


def test_serving_drills_makes_no_model_call(app, db, learner) -> None:
    """`netguard` is armed session-wide: a provider call in the request would
    raise. Nothing is generated while the learner waits (W10's criterion)."""
    _item(db, learner, error_type="article_missing")
    _journal(db, learner, "article_missing", 3)
    assert _focus(app, learner)["state"] == "ready"


# ── generation ──────────────────────────────────────────────────────────────


def test_a_drill_draft_is_bound_to_its_pattern_and_to_no_unit() -> None:
    """The runner sets `error_type`, `cohort` and a NULL unit; the model cannot.
    **Red method:** remove the drill branch in `_draft_to_item` — the item
    carries unit 0/None mismatch and no `error_type`."""
    [slot] = gen.drill_slots("article_missing", 1, ("cloze_cued",))
    raw = {"prompt_text": "She bought ___ umbrella.", "answer": "an",
           "error_type": "preposition", "unit_number": 7, "explanation": "x",
           "definition": "y", "l1_gloss": "z"}
    item = generate._draft_to_item(raw, slot, 0)
    assert (item.error_type, item.unit_number, item.cohort, item.track) == (
        "article_missing", None, "drill", "life")


def test_a_drill_slot_without_its_pattern_is_refused() -> None:
    """**Red method:** remove the `if not slot.error_type` guard — no error."""
    slot = generate.Slot(index=0, item_type="cloze_cued", target="t", cohort="drill")
    with pytest.raises(ValueError):
        generate._draft_to_item({"prompt_text": "a ___", "answer": "b"}, slot, 0)


def test_the_plan_buys_only_for_evidenced_patterns(db, learner) -> None:
    """`--codes` filters the evidenced list and can never extend it.
    **Red method:** set `EVIDENCE_MIN_ROWS = 2` — the two-row `word_order` enters
    the plan through `--codes` and the list differs."""
    _journal(db, learner, "article_missing", 3)
    _journal(db, learner, "word_order", 2)
    plan = gen.plan_for(learner.user_id, now=NOW, codes=["word_order", "article_missing"])
    assert [e.code for e in plan] == ["article_missing"]
    assert len(plan[0].slots) == items_svc.DRILL_BANK_TARGET
    assert plan[0].payload["learner_l1"] == "fa"


def test_the_payload_names_the_pattern_and_carries_no_journal_text(db, learner) -> None:
    """No learner sentence is sent. **Red method:** add `"example": "fixture 0"`
    (a journal `you_said`) to `drill_payload` — the fixture text appears."""
    _journal(db, learner, "article_missing", 3)
    [entry] = gen.plan_for(learner.user_id, now=NOW)
    sent = json.dumps(entry.payload)
    assert "fixture" not in sent
    assert gen.DRILL_TARGETS["article_missing"] in sent
    assert entry.candidates[0] == gen.DRILL_TARGETS["article_missing"]
    assert gen.DRILL_TARGETS["article_wrong"] in entry.candidates


def test_the_dry_run_sends_nothing_and_says_so(db, learner, capsys, tmp_path) -> None:
    """The probe (ruling 0.5): dry by default. `netguard` would raise on a call.
    **Red method:** make `main` fall through to `run` without `--live` — the
    confirm prompt reads stdin and the test errors."""
    _journal(db, learner, "article_missing", 3)
    assert gen.main(["--user", str(learner.user_id),
                     "--journal", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "dry run — nothing was sent and nothing was written." in out
    assert "calls --live will make, at most: " in out
    assert '"learner_l1": "fa"' in out
    assert not (tmp_path / "j.jsonl").exists()


def test_the_ceiling_is_itemised_from_the_slots() -> None:
    """8 slots of block 3's types: generation 1 + judge 1 + 7 probed + 2x2 cue
    re-probes + 8 targets + 1 back-translation = 22. Hardcoded, derived by hand
    from `SLOT_TYPES` and `gates.ANSWER_FAMILY` (§3 rule 5). **Red method:** drop
    the back-translation term — 21."""
    slots = gen.drill_slots("article_missing", 8, generate.SLOT_TYPES)
    entry = gen.DrillPlan("article_missing", "Articles", 3, 0, slots, (), {}, ())
    assert gen.calls_for(entry) == 22


def _sdk_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.usage = MagicMock(input_tokens=10, output_tokens=10,
                               cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return response


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_the_generation_request_as_sent(mock_cls, _sleep) -> None:
    """Request construction, mocked at the SDK (TASKS standing rule 7).
    **Red method:** change `drill_payload` to omit `learner_l1` — the sent
    message lacks it."""
    client = mock_cls.return_value
    client.messages.create.return_value = _sdk_response('{"items": []}')
    slots = gen.drill_slots("preposition", 2, ("cloze_cued", "error_spot"))
    payload = gen.drill_payload("preposition", "Prepositions", "lt", slots)
    assert generate.generate_drafts(payload, avoid=("x [y]",)) == []
    kwargs = client.messages.create.call_args.kwargs
    sent = json.loads(kwargs["messages"][0]["content"])
    assert sent == {
        "can_do": "Practise prepositions of time and place, and after common verbs",
        "track": "life",
        "items": [
            {"item_type": "cloze_cued",
             "grammar_target": "Prepositions of time and place, and after common verbs"},
            {"item_type": "error_spot",
             "grammar_target": "Prepositions of time and place, and after common verbs"},
        ],
        "learner_l1": "lt",
    }
    assert kwargs["max_tokens"] == generate.GENERATE_MAX_TOKENS
    assert "x [y]" in kwargs["system"][0]["text"]


def test_apply_writes_drills_through_the_real_writer(db, learner, monkeypatch, tmp_path) -> None:
    """`--apply`'s write path, with the model and gates stubbed at the seams
    `test_focus_bank.py` uses. The rows land with `cohort = drill`, the pattern,
    and no unit — and `drill_items` can then serve them.
    **Red method:** make `run` skip `_write` under apply — zero rows."""
    _journal(db, learner, "article_missing", 3)
    [entry] = gen.plan_for(learner.user_id, now=NOW)
    entry = gen.DrillPlan(entry.code, entry.learner_label, entry.evidence, entry.held,
                          entry.slots[:1], entry.candidates,
                          gen.drill_payload(entry.code, entry.learner_label, "fa",
                                            entry.slots[:1]), ())
    monkeypatch.setattr(generate, "generate_drafts", lambda payload, **_: [{
        "prompt_text": "Can you pass me ___ apple?", "answer": "an",
        "explanation": "An before a vowel sound.", "definition": "article",
        "l1_gloss": "یک"}])

    def _passes(slots, drafts, **_):
        item = generate._draft_to_item(drafts[0], slots[0], 0)
        return [generate.Outcome(slot=slots[0], unit_number=0, item=item,
                                 report=ValidationReport("passed", acceptable=("an",),
                                                         canonical="an"),
                                 state="accepted")]

    monkeypatch.setattr(generate, "verify_cohort", _passes)
    settings = load_settings()
    gen.run(learner.user_id, [entry], apply=True, settings=settings,
            journal_path=tmp_path / "j.jsonl")
    row = db.execute(
        "SELECT error_type, unit_number, payload->>'cohort' FROM items WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert tuple(row) == ("article_missing", None, "drill")
    assert items_svc.drills_held(learner.user_id, error_type="article_missing") == 1


# ── the probe (build-run ruling 0.5) ────────────────────────────────────────


def test_the_drill_probe_is_dry_by_default_and_names_its_calls(capsys, monkeypatch) -> None:
    """**Red method:** make the loop call `generate_drafts` without `--live` —
    the stub raises and the test fails."""
    from core.items import drill_probe

    def _no_call(*_a, **_k):
        raise AssertionError("the dry probe made a call")

    monkeypatch.setattr(generate, "generate_drafts", _no_call)
    assert drill_probe.main([]) == 0
    out = capsys.readouterr().out
    assert "calls --live will make: 2" in out
    assert '"learner_l1": "lt"' in out and '"learner_l1": "fa"' in out
    assert "DRY RUN. Nothing was sent and nothing was written." in out


def test_the_drill_probe_reaches_no_writer_and_no_database() -> None:
    """The probe imports no service, no database module and holds no SQL.
    **Red method:** add `from core.services import items` to the probe."""
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "packages" / "core" / "items"
           / "drill_probe.py").read_text()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    assert not any(n.startswith(("core.services", "core.db")) for n in names), names
    assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", src)
