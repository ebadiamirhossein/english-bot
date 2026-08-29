"""W10: `GET /session/today` and the block-complete route, through the real
ASGI transport.

Nothing here calls a route function or a service directly; every request goes
through `httpx.ASGITransport` into the app `uvicorn apps.api.main:app` serves —
CLAUDE.md §3 rule 1, and the descendant of v2's most expensive lesson.

**The assertion this file exists for is `test_nothing_is_generated_while_the_
learner_waits`.** ARCHITECTURE §7: items are produced and gated the night
before, never in the request path. W10 generates nothing at all, so the property
is trivially true today — and it is asserted anyway, because it stops being
trivial the moment the generation slice lands, and because a session that opens
in under a second is the criterion the whole design is arranged around.

`tests/support/netguard.py` is armed session-wide by `conftest.py`, so a
provider call inside a request would raise rather than pass silently. That is
how we know, rather than by reading the router.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.sessions import BLOCK_KINDS
from core.services import cards as cards_svc
from core.services import items as items_svc


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


@pytest.fixture
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W10 Route', 'lt', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            f"w10r-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W10 Route', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
        "VALUES (%s, %s, %s)",
        (
            hashlib.sha256(raw.encode()).digest(),
            user_id,
            datetime.now(timezone.utc) + timedelta(days=30),
        ),
    )
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def request(app, method, path, *, json_body=None, cookies=None, headers=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(
                method, path, json=json_body, headers=headers or {}
            )

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


def _seed_due_card(db, learner, **over) -> int:
    now = datetime.now(timezone.utc)
    spec = dict(
        card_type="production",
        front="to eat quickly",
        back="devour",
        register="neutral",
        register_source="import_default",
        meaning="to eat quickly",
        state=cards_svc.CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=now - timedelta(days=1),
            last_review=now - timedelta(days=11),
            lapses=0,
            reps=4,
        ),
    )
    spec.update(over)
    card_id = cards_svc.create_card(db, learner.user_id, **spec)
    db.commit()
    assert card_id is not None
    return card_id


# ── the route ───────────────────────────────────────────────────────────────


def test_the_session_requires_a_session(app) -> None:
    assert request(app, "GET", "/session/today").status_code == 401


def test_the_session_serves_prd_4_1s_five_blocks(app, db, learner) -> None:
    """User action: tapping *Start today's session* on home."""
    response = request(app, "GET", "/session/today", cookies=_as(learner))
    assert response.status_code == 200
    body = response.json()
    assert [b["kind"] for b in body["blocks"]] == list(BLOCK_KINDS)
    assert [b["n"] for b in body["blocks"]] == [1, 2, 3, 4, 5]


def test_nothing_is_generated_while_the_learner_waits(app, db, learner) -> None:
    """ARCHITECTURE §7, asserted rather than described.

    `tests/support/netguard.py` is armed for the whole session by `conftest.py`,
    so any outbound call — a model, a speech provider, anything — raises inside
    the request. This test passes because the route makes none, not because
    nobody looked.
    """
    assert request(app, "GET", "/session/today", cookies=_as(learner)).status_code == 200


def test_the_l1_is_on_the_envelope_and_is_the_learners_own(app, db, learner) -> None:
    """#159. This learner is `lt`, and before W10 a Lithuanian gloss would have
    been labelled English by a script test with no visible symptom."""
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert body["l1_language"] == "lt"


def test_no_murphy_citation_reaches_the_wire(app, db, learner) -> None:
    """#171 as extended by #183, at the HTTP boundary.

    Block 3 serialises a unit's grammar targets and every one of them carries a
    `murphy_units` in the database. The whole response is searched, not just the
    focus block, because a payload is the thing a surface renders and a surface
    cannot render what never arrived.
    """
    raw = request(app, "GET", "/session/today", cookies=_as(learner)).text
    assert "murphy" not in raw.lower()


def _seed_focus_item(db, learner, *, unit_number=1, **over) -> int:
    """One validated item in this learner's bank, through the real writer.

    `items_svc.insert_item` and not an INSERT: it refuses a report that is not
    `ok`, and `test_exactly_one_module_writes_an_item` holds that there is only
    one writer. A hand-rolled INSERT here would seed a row the real path could
    never have produced.
    """
    from core.items.gates import ValidationReport
    from core.items.schema import parse

    draft = {
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": "I ___ there twice last year.",
        "answer": "went",
        "accepted_variants": ["went"],
        "unit_number": unit_number,
        "grammar_target": "past simple: regular and irregular verbs",
        "explanation": "Past simple, because the time is finished.",
        "definition": "past of go",
        "l1_gloss": "nuvykau",
    }
    draft.update(over)
    item_id = items_svc.insert_item(
        learner.user_id, parse(draft),
        ValidationReport("passed", acceptable=("went",), canonical="went"),
        model="test-model",
    )
    db.commit()
    assert item_id is not None
    return item_id


def test_block_three_is_empty_of_items_until_someone_generates_them(
    app, db, learner
) -> None:
    """The ordinary state, and the one the second learner stays in.

    Items are per-learner and #159 is unresolved, so the generator was run for
    one learner only. Block 3 renders its targets and no practice section rather
    than an empty heading over nothing.
    """
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    focus = body["blocks"][2]
    assert focus["state"] == "ready"
    assert focus["payload"]["items"] == []
    assert focus["payload"]["can_do"]
    assert focus["payload"]["grammar_targets"]


def test_block_three_serves_the_unit_s_generated_items(app, db, learner) -> None:
    """User action: reaching block 3 of the daily session and answering an item.

    W10 shipped this block with `items: []` and a line reading *"Practice for
    this arrives with the exercise generator."* This is that block filled.
    """
    item_id = _seed_focus_item(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    focus = body["blocks"][2]
    assert [i["id"] for i in focus["payload"]["items"]] == [item_id]
    assert focus["payload"]["items"][0]["response_mode"] == "typed"
    assert focus["payload"]["items"][0]["projection"]["prompt_text"]


def test_block_three_serves_only_this_unit_s_items(app, db, learner) -> None:
    """`current_unit` returns 1 and cannot advance (#188), so an item generated
    for unit 3 must not appear in unit 1's focus block."""
    mine = _seed_focus_item(db, learner, unit_number=1)
    _seed_focus_item(
        db, learner, unit_number=3,
        prompt_text="I ___ smoke, but I gave up.", answer="used to",
        accepted_variants=["used to"],
    )
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert [i["id"] for i in body["blocks"][2]["payload"]["items"]] == [mine]


def test_block_three_leaks_no_part_of_the_hidden_half(app, db, learner) -> None:
    """The projection contract, at the HTTP boundary.

    Block 3 is a SECOND surface serving items — `/items` was the first — and the
    failure this guards against is a new block building an envelope of its own
    instead of going through `visible_projection`. The whole response is searched
    for the answer string, as a value and as a substring, exactly as
    `test_items_projection.py` does per type.
    """
    from core.items.projection import NEVER_VISIBLE

    _seed_focus_item(db, learner)
    response = request(app, "GET", "/session/today", cookies=_as(learner))
    focus = response.json()["blocks"][2]
    projection = focus["payload"]["items"][0]["projection"]

    assert not NEVER_VISIBLE & set(projection)
    assert "went" not in json.dumps(projection)
    assert "nuvykau" not in response.text, "cue material reached the wire"
    assert "Past simple, because" not in response.text, "explanation reached the wire"

    # The unit's targets ARE shown — that is block 3's job — but the ITEM must
    # not say which of them it tests. `grammar_target` is in NEVER_VISIBLE
    # because naming it would tell a learner what kind of answer is wanted, and
    # would hand `gates.probe_target` the answer to its own question.
    assert "grammar_target" not in json.dumps(projection)
    assert focus["payload"]["grammar_targets"], "the unit's targets are still served"


def test_serving_items_makes_no_model_call(app, db, learner) -> None:
    """W10's criterion, now that block 3 has content to serve.

    `netguard` is armed session-wide, so this passes because the route generates
    nothing — not because nobody looked. The generator is human-run and
    `assign_daily` still reaches neither `core.llm` nor `core.items`.
    """
    _seed_focus_item(db, learner)
    assert request(app, "GET", "/session/today", cookies=_as(learner)).status_code == 200


def test_block_one_is_empty_and_says_so_distinctly(app, db, learner) -> None:
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    review = body["blocks"][0]
    assert review["state"] == "empty"
    # `empty` is a fact, and it carries nothing. `unavailable` is a different
    # answer entirely and no block returns it here.
    assert review["payload"] == {}
    assert all(b["state"] != "unavailable" for b in body["blocks"])


def test_a_due_card_arrives_inside_block_one(app, db, learner) -> None:
    """#160: the deck lives in the session, not behind a tab with a counter."""
    card_id = _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    review = body["blocks"][0]
    assert review["state"] == "ready"
    assert [c["id"] for c in review["payload"]["cards"]] == [card_id]
    assert review["payload"]["cards"][0]["typed"] is True


def test_the_session_carries_no_backlog_number_anywhere(app, db, learner) -> None:
    """CLAUDE.md §4. Nothing in this payload counts what was not done."""
    _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert "counts" not in body
    for block in body["blocks"]:
        for banned in ("total_remaining", "due_now", "overdue", "carried"):
            assert banned not in block["payload"]


# ── resume ──────────────────────────────────────────────────────────────────



def test_opening_the_session_twice_returns_the_same_row(app, db, learner) -> None:
    first = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    second = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert first["session_id"] == second["session_id"]



def test_someone_elses_session_is_a_404(app, db, learner) -> None:
    """404 covers "no such session", "not yours" and "not a daily session" —
    telling a caller that an id exists but belongs to someone else is a fact
    about the other learner."""
    response = request(
        app, "POST", "/session/999999999/block/1/complete", cookies=_as(learner)
    )
    assert response.status_code == 404



def test_a_typed_attempt_is_graded_on_the_server(app, db, learner) -> None:
    card_id = _seed_due_card(db, learner)
    headers = {"content-type": "application/json"}
    right = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "Devour."}, cookies=_as(learner), headers=headers,
    )
    assert right.status_code == 200
    assert right.json() == {"matched": True}

    wrong = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "eat"}, cookies=_as(learner), headers=headers,
    )
    assert wrong.json() == {"matched": False}


def test_the_attempt_route_writes_nothing(app, db, learner) -> None:
    """It is a read. The attempt is recorded by the grade call, which recomputes
    the verdict rather than trusting one the client carries back."""
    card_id = _seed_due_card(db, learner)
    request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    reviews = db.execute(
        "SELECT count(*) FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert reviews == 0


def test_the_attempt_route_refuses_a_form_body(app, db, learner) -> None:
    """The CSRF barrier is that a state-changing route is a JSON POST, which
    always preflights, and the preflight is answered only for the two allowed
    origins. Making the refusal the route's own decision is what survives
    someone later adding a `Form(...)` parameter."""
    card_id = _seed_due_card(db, learner)
    response = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_a_grade_from_inside_the_session_carries_both(app, db, learner) -> None:
    card_id = _seed_due_card(db, learner)
    session_id = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["session_id"]

    response = request(
        app, "POST", f"/review/{card_id}/grade",
        json_body={
            "rating": "good",
            "session_id": session_id,
            "typed_response": "Devour",
        },
        cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200

    row = db.execute(
        "SELECT session_id, typed_response, typed_matched FROM card_reviews "
        "WHERE card_id = %s",
        (card_id,),
    ).fetchone()
    assert row[0] == session_id
    assert row[1] == "Devour"
    # Recomputed here, never taken from the client.
    assert row[2] is True


def test_a_grade_from_review_carries_no_session(app, db, learner) -> None:
    """#160 keeps `/review` reachable outside the session, which is why
    `card_reviews.session_id` is nullable — the same reason
    `item_attempts.session_id` is."""
    card_id = _seed_due_card(db, learner)
    request(
        app, "POST", f"/review/{card_id}/grade",
        json_body={"rating": "good"},
        cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    stored = db.execute(
        "SELECT session_id FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert stored is None


def test_an_attempt_on_someone_elses_card_is_a_404(app, db, learner) -> None:
    response = request(
        app, "POST", "/review/999999999/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 404


# ── #190: the two producers of a card face must agree on the wire ───────────


def test_the_session_serves_the_same_card_shape_as_the_review_queue(
    app, db, learner
) -> None:
    """**The check that would have caught #190, and it compares two RESPONSES.**

    `CardFace` in `apps/web/lib/api.ts` is one contract with two producers:
    `GET /review/queue` and block 1 of `GET /session/today`. W10 shipped the
    second one incomplete — `card.face()` without `intervals` — and the client
    read `card.intervals[rating]` unguarded, so the session crashed on the first
    card a learner graded.

    **Nothing could see it.** `BlockOut.payload` is `dict[str, Any]`, so pydantic
    validated an envelope it had no shape for, and Vitest hand-wrote its card
    fixtures, so the client's expectation and the server's output were never
    compared. Both suites were green.

    This asserts key-for-key against two real ASGI bodies. It is deliberately
    **not** a comparison against `card_face()` — a fixture checked against its own
    source agrees with itself forever, which is the trap
    `tests/test_items_route.py` records having fallen into once already.
    """
    _seed_due_card(db, learner)

    queue_card = request(
        app, "GET", "/review/queue", cookies=_as(learner)
    ).json()["cards"][0]
    session_card = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["blocks"][0]["payload"]["cards"][0]

    assert set(session_card) == set(queue_card), (
        "the session and /review/queue disagree about what a card face is — "
        "this is #190. Both must go through `core.services.cards.card_face`."
    )


def test_every_card_the_session_serves_carries_all_four_intervals(
    app, db, learner
) -> None:
    """The specific field, at the specific place a learner meets it.

    `GradeButtons` maps over the four ratings and reads one interval each, so a
    face carrying three of them crashes exactly as one carrying none does. The
    shape check above would pass on `"intervals": {}`; this one would not.
    """
    _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    cards = body["blocks"][0]["payload"]["cards"]
    assert cards, "no card was served; this check is reading nothing"
    for card in cards:
        assert set(card["intervals"]) == {"again", "hard", "good", "easy"}
        assert all(isinstance(v, int) for v in card["intervals"].values())


# ── #190: the committed fixture describes the wire, not a function ──────────

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "apps" / "web" / "components" / "session" / "session-today.fixture.json"
)
EXPORTER = Path(__file__).resolve().parents[1] / "scripts" / "export_session_fixture.py"


def test_the_session_exporter_and_fixture_both_exist() -> None:
    """A guard for the two checks below: a missing file passes an empty
    comparison, which is how a contract quietly stops being one."""
    assert EXPORTER.is_file()
    assert FIXTURE.is_file()


def test_the_committed_session_fixture_is_current() -> None:
    """Regenerate in memory and compare. **Not a note in a README.**

    Run through the exporter's own `--check`, in a subprocess, so what is
    verified is the command a human would run rather than a reimplementation of
    it that could drift from the command — `tests/test_items_web_contract.py`'s
    shape exactly.
    """
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, (
        "apps/web/components/session/session-today.fixture.json is stale — the "
        "session's Vitest tests are rendering a card face the server no longer "
        "serves. Re-run:\n  python scripts/export_session_fixture.py\n"
        + result.stderr
    )


def test_the_committed_session_fixture_matches_the_wire(app, db, learner) -> None:
    """**The assertion that makes the fixture a contract rather than a mock.**

    The exporter builds its card in memory. If it described a *function* while
    the route served something else, both suites would stay green and the seam
    would silently stop meaning anything — which is #190 in a new costume, and
    `tests/test_items_route.py` records that exact mistake being made once in
    this repository already.

    So the committed shape is compared against a real ASGI response body. Keys
    only, not values: the fixture's card is frozen at a fixed instant on purpose
    and a seeded card's `front` is a different string. **The shape is what
    crashed.**
    """
    _seed_due_card(db, learner)
    served = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["blocks"][0]["payload"]["cards"][0]
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]

    assert set(committed) == set(served), (
        "the committed session fixture is not the shape the route serves. "
        "Re-run `python scripts/export_session_fixture.py`."
    )
    assert set(committed["intervals"]) == set(served["intervals"])


# ── #258: a block records itself done; the manual button is gone ────────────
#
# OPERATOR RULING, 2026-08-29. Nobody tapped it in three days of real use, it sat
# below five blocks on a phone, and **a signal that requires five taps below the
# fold is not a signal — it is a form nobody fills in.**
#
# `block_breakdown->>'focus' = 'done'` keeps its meaning; what changed is who
# writes it. Two alternatives were refused and are recorded so they are not
# re-proposed: `completed_at IS NOT NULL`, for the reason `day_in_unit`'s own
# docstring gives — a learner can finish a session having skipped block 3 — and
# *any daily session advances*, because that makes opening the app mean
# practising and feeds #259 the same wrong signal.
#
# **WHAT "ANSWERED ITS ITEMS" MEANS PER KIND, because the five are not uniform:**
#   review  — every card it served has a `card_reviews` row for this session
#   input   — serves nothing until W12/W13; `empty`, never `done`
#   focus   — every item it served has an `item_attempts` row for this session
#   output  — CANNOT self-report: `POST /correct` records no session
#   close   — a summary, not a task; nothing to answer


def _breakdown(db, user_id: int) -> dict:
    row = db.execute(
        "SELECT block_breakdown FROM sessions WHERE user_id = %s "
        "AND task_type = 'daily' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict((row[0] if row else None) or {})


def test_focus_records_itself_done_when_every_item_is_answered(app, db, learner):
    """**RED BEFORE THE FIX. This is the pacing clock's only input (#258/#245).**

    `day_in_unit` counts sessions whose `focus` is `done`, and nothing on
    production had ever written that value — so the clock read 0 for both
    learners and block 3 was pinned to section 1 forever.
    """
    item_id = _seed_focus_item(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    focus = next(b for b in body["blocks"] if b["kind"] == "focus")
    assert [one["id"] for one in focus["payload"]["items"]] == [item_id]

    request(
        app, "POST", f"/items/{item_id}/answer",
        json_body={"text": "went", "session_id": body["session_id"]},
        cookies=_as(learner),
    )

    after = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert next(b for b in after["blocks"] if b["kind"] == "focus")["state"] == "done"
    assert _breakdown(db, learner.user_id)["focus"] == "done"


def test_focus_is_not_done_while_one_item_is_unanswered(app, db, learner):
    """Partial work is not completion — the point of an automatic signal."""
    first = _seed_focus_item(db, learner)
    _seed_focus_item(db, learner, prompt_text="A second ___ stem.")
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()

    request(
        app, "POST", f"/items/{first}/answer",
        json_body={"text": "went", "session_id": body["session_id"]},
        cookies=_as(learner),
    )

    after = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert next(b for b in after["blocks"] if b["kind"] == "focus")["state"] == "ready"
    assert _breakdown(db, learner.user_id).get("focus") != "done"


def test_a_block_that_served_nothing_is_empty_and_never_done(app, db, learner):
    """`empty` and `done` are different facts and must not collapse.

    Block 2 has no video engine until W12, so it serves nothing. Recording it
    `done` would say the learner completed work that does not exist — which is
    the collapse `_build_block` and `BLOCK_STATES` exist to prevent.
    """
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert next(b for b in body["blocks"] if b["kind"] == "input")["state"] == "empty"
    assert _breakdown(db, learner.user_id).get("input") != "done"


def test_output_cannot_self_report_and_that_is_a_stated_gap(app, db, learner):
    """**A named gap, not an oversight.**

    Block 4 hands the learner to `POST /correct`, which records no `session_id`,
    so nothing links a correction to the sitting it happened in. Until it does,
    block 4 cannot know it was answered and stays `ready`. That is why
    `sessions.completed` remains unreachable and why #259 is NARROWED rather
    than repaired by this ruling.
    """
    _seed_focus_item(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert next(b for b in body["blocks"] if b["kind"] == "output")["state"] == "ready"
    assert _breakdown(db, learner.user_id).get("output") != "done"


def test_the_manual_done_route_is_gone(app, learner):
    """The button went, so the route it called must go with it.

    A POST left behind with no caller is #219's family — an enumeration that
    constrains nothing, kept alive because deleting it felt riskier than leaving
    it. It is deleted.
    """
    # **Asserted on the ROUTE TABLE, not on a status code.** A request to
    # `/session/1/block/1/complete` returns 404 whether the route is gone or
    # merely refusing another learner's session — a status check here would pass
    # for the wrong reason and go on passing if the route came back.
    # **Asserted on the OpenAPI path table, not on a status code and not on
    # `app.routes`.** A request to `/session/1/block/1/complete` returns 404
    # whether the route is gone or merely refusing another learner's session, so
    # a status check passes for the wrong reason; and `app.routes` reports `None`
    # for included routers, so a walk over it passes vacuously. Both were tried
    # here before this line — a test that cannot fail is worse than no test.
    paths = set(app.openapi()["paths"])
    assert not [p for p in paths if "block" in p], sorted(
        p for p in paths if "block" in p
    )


def test_an_answer_stores_the_session_it_was_given(app, db, learner):
    """**#274: asserted on the STORED ROW, never on a 200.**

    The route has carried `session_id` since W11 and the checkpoint's runner sent
    it; **block 3's did not**, so every daily attempt stored NULL and
    `block_breakdown.focus` could never reach `done`. A test that asserted the
    call succeeded would have passed throughout — the call always succeeded.

    This is the server half of the guard. The client half is a render test, since
    the defect was a prop that was never passed.
    """
    item_id = _seed_focus_item(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()

    request(
        app, "POST", f"/items/{item_id}/answer",
        json_body={"text": "went", "session_id": body["session_id"]},
        cookies=_as(learner),
    )

    row = db.execute(
        "SELECT session_id FROM item_attempts WHERE item_id = %s AND user_id = %s",
        (item_id, learner.user_id),
    ).fetchone()
    assert row is not None
    assert row[0] == body["session_id"], "the attempt must carry its session"


def test_a_graded_card_stores_the_session_it_was_given(app, db, learner):
    """The review block's half of the same question, checked rather than assumed.

    `ReviewBlock` does pass `sessionId` to `CardRunner`, which does send it — so
    this is expected to pass. It is written because #254 was fixed on one route
    and the other was never checked, and *checked and correct* is evidence while
    *not checked* is indistinguishable from broken.
    """
    card_id = _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()

    request(
        app, "POST", f"/review/{card_id}/grade",
        json_body={"rating": "good", "session_id": body["session_id"]},
        cookies=_as(learner),
    )

    row = db.execute(
        "SELECT session_id FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == body["session_id"]
