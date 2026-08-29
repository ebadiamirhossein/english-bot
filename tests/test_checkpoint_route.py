"""W11: the checkpoint's routes, through the real ASGI transport.

Nothing here calls a route function or a service directly; every request goes
through `httpx.ASGITransport` into the app `uvicorn apps.api.main:app` serves --
CLAUDE.md §3 rule 1, and the descendant of v2's most expensive lesson, where 161
tests passed while the main feature was dead because every one of them called a
handler directly.

**The two assertions this file exists for:**

* `test_two_creations_on_one_day_produce_one_sitting` -- and it goes red by
  DROPPING MIGRATION 018's INDEX, not by changing Python, which is what makes
  the migration's load-bearingness a demonstrated fact rather than a claim. Two
  earlier drafts of this slice asserted it needed no migration.
* `test_a_failed_checkpoint_shows_no_score` -- *drops are silent, raises are
  announced*, held at the API boundary where a client cannot route around it.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.items.gates import ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import parse
from core.services import items as items_svc
from core.services import syllabus as syllabus_svc
from core.syllabus.checkpoint import quota_map

PASSED = ValidationReport("passed")

def _unit_1_quotas() -> dict[str, int]:
    """Unit 1's blueprint, READ FROM THE SYLLABUS rather than copied here.

    **This was a hardcoded `{4, 3, 3, 2}` literal until 2026-08-29**, and the
    operator's `per_target` ruling that day moved unit 1 to `{5, 4, 1, 2}` — so
    the fixture seeded a cohort the selector then refused, and two route tests
    failed for a reason that had nothing to do with the route. **A second
    hand-maintained copy of the syllabus is the defect**, not the stale numbers:
    the same shape `test_migration_014` avoids by comparing 014's CHECK against
    `UNIT_STATES` instead of restating it.

    **CLAUDE.md §3 rule 5 is respected and the distinction is worth stating.**
    This reads the DATA FILE, which is an input; the code under test is
    `checkpoint_items` and `quota_map`, which is a different artefact. The test
    asserts *a cohort built to the blueprint is served whole* — and the negative,
    *a cohort that does not match its plan is refused*, is asserted separately in
    `test_checkpoint_selector.py` against a deliberately mismatched cohort.
    """
    from core.syllabus.content import units

    return dict(units()[0].checkpoint["per_target"])


UNIT_1 = _unit_1_quotas()


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def app():
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
        VALUES (%s, 'W11 Route', 'fa', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, f"w11r-{abs(telegram_user_id)}@example.test", str(uuid.uuid4())),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W11 Route', 'approved')",
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
    db.execute("DELETE FROM item_attempts WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM items WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM user_unit_state WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def request(app, method, path, *, json_body=None, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(method, path, json=json_body)

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


def _seed_cohort(learner_id: int) -> None:
    for target, count in UNIT_1.items():
        for index in range(count):
            raw = {
                "item_type": "cloze_cued",
                "track": "life",
                "prompt_text": f"cp-{target[:14]}-{index} I ___ to the shops.",
                "answer": "went",
                "unit_number": 1,
                "grammar_target": target,
                "cohort": "checkpoint",
            }
            raw["accepted_variants"] = normalise_variants(raw["answer"])
            items_svc.insert_item(learner_id, parse(raw), PASSED, model="test-model")


def _enter(db, learner) -> None:
    syllabus_svc.record_unit_entry(
        db, learner.user_id, 1, now=datetime.now(timezone.utc)
    )
    db.commit()


def _answer_all(app, learner, sitting, *, correct: int) -> None:
    """Answer the sitting's items through `POST /items/{id}/answer`.

    **Answering is the ITEMS route, not a checkpoint route**, deliberately: a
    checkpoint item is an `items` row like any other, and a second grader would
    drift from `core.items.response`.
    """
    for index, item in enumerate(sitting["items"]):
        response = request(
            app,
            "POST",
            f"/items/{item['id']}/answer",
            json_body={
                "text": "went" if index < correct else "zzz-wrong",
                "session_id": sitting["session_id"],
            },
            cookies=_as(learner),
        )
        assert response.status_code == 200, response.text



def _answer_first(app, learner, sitting, n: int) -> None:
    """Answer only the first `n` of the sitting, leaving the rest untouched.

    Distinct from `_answer_all`, whose `correct` argument controls how many are
    RIGHT and not how many are ANSWERED — a partially-worked sitting is the
    whole subject of #269 and needs a helper that can produce one.
    """
    for item in list(sitting["items"])[:n]:
        response = request(
            app,
            "POST",
            f"/items/{item['id']}/answer",
            json_body={"text": "went", "session_id": sitting["session_id"]},
            cookies=_as(learner),
        )
        assert response.status_code == 200, response.text


# ── the sitting ─────────────────────────────────────────────────────────────


def test_the_checkpoint_is_not_ready_without_a_cohort(app, db, learner) -> None:
    """The honest empty state. **A short checkpoint is never served instead.**"""
    _enter(db, learner)
    response = request(app, "GET", "/checkpoint/today", cookies=_as(learner))
    assert response.status_code == 200
    assert response.json()["state"] == "not_ready"
    assert response.json()["items"] == []


def test_a_seeded_cohort_serves_twelve(app, db, learner) -> None:
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    body = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert body["state"] == "ready"
    assert len(body["items"]) == 12
    assert body["item_count"] == 12


def test_the_projection_never_names_the_target_or_the_cohort(app, db, learner) -> None:
    """`grammar_target` and `cohort` are both in `NEVER_VISIBLE`.

    Naming either on the wire would tell the blind solver -- which sees exactly
    what a learner sees -- the category of answer wanted, and `probe_target` is
    asked to recover that from the item alone.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    body = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    for item in body["items"]:
        assert "grammar_target" not in item["projection"]
        assert "cohort" not in item["projection"]
        assert "answer" not in item["projection"]


def test_two_creations_on_one_day_produce_one_sitting(app, db, learner) -> None:
    """**RED BY DROPPING MIGRATION 018's INDEX, not by changing Python.**

    `GET /checkpoint/today` creates the sitting with `INSERT ... ON CONFLICT DO
    NOTHING` -- and `ON CONFLICT` needs something to conflict ON. 016's index is
    partial `WHERE task_type = 'daily'` and does not reach a checkpoint row, so
    without 018 a refetch creates TWO sittings, both `completed = FALSE`, both
    claiming cleanly, and the writer reads them as two genuine retakes:
    `checkpoint_attempts` bumped twice and `retake_due_on` moved twice.

    A phone that backgrounds and resumes refetches -- the session route's own
    rate-limit comment records it as ordinary -- so this is not a rare race.

    **THE RED RUN WAS MEASURED, AND IT IS SHARPER THAN THE PREDICTION.** Dropping
    the index does not produce two sittings; it produces
    `psycopg.errors.InvalidColumnReference: there is no unique or exclusion
    constraint matching the ON CONFLICT specification` -- the route 500s on the
    first request. **So the failure is LOUD rather than silent**, which is better
    than predicted and is recorded rather than smoothed over, because the
    prediction ("two sittings, both claiming cleanly") is what the plan argued
    from and it was wrong about the mechanism while right about the need.

    The index is still load-bearing: `ON CONFLICT (user_id, date) WHERE
    task_type = 'checkpoint'` names it, and nothing else in the schema satisfies
    that specification.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    first = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    second = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert first["session_id"] == second["session_id"]
    count = db.execute(
        "SELECT count(*) FROM sessions WHERE user_id = %s AND task_type = 'checkpoint'",
        (learner.user_id,),
    ).fetchone()[0]
    assert count == 1


# ── the verdict ─────────────────────────────────────────────────────────────


def test_a_pass_marks_the_unit_and_announces_the_score(app, db, learner) -> None:
    """*Raises are announced.* A pass may say what it scored."""
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    sitting = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    _answer_all(app, learner, sitting, correct=12)
    body = request(
        app, "POST", f"/checkpoint/{sitting['session_id']}/complete",
        cookies=_as(learner),
    ).json()
    assert body["passed"] is True
    assert body["score_pct"] == 100
    assert body["retake_due_on"] is None
    state = db.execute(
        "SELECT state, passed_at FROM user_unit_state WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert state[0] == "passed" and state[1] is not None


def test_a_failed_checkpoint_shows_no_score(app, db, learner) -> None:
    """**RED IF THE FAIL PATH SERVES `score_pct`.** *Drops are silent.*

    `user_unit_state.last_checkpoint_score` is STORED because migration 014
    requires a `passed` row to name the score that passed. **Storing it is not
    licence to show it.** A fraction on the screen after a failed checkpoint is a
    punishment screen with no banned word in it, which is why this is asserted at
    the API boundary rather than left to the client.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    sitting = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    _answer_all(app, learner, sitting, correct=3)
    body = request(
        app, "POST", f"/checkpoint/{sitting['session_id']}/complete",
        cookies=_as(learner),
    ).json()
    assert body["passed"] is False
    assert body["score_pct"] is None, "a failure never reports a mark"
    assert body["retake_due_on"] is not None
    state = db.execute(
        "SELECT state, checkpoint_attempts FROM user_unit_state WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert state[0] == "in_progress"
    assert state[1] == 1


def test_the_same_sitting_scored_twice_bumps_nothing(app, db, learner) -> None:
    """**The attempt key.** `UNIQUE (user_id, unit_number)` is a ROW key.

    A second `complete` would otherwise `ON CONFLICT DO UPDATE`, bump
    `checkpoint_attempts` again and **move `retake_due_on` with it** -- so a
    double tap would shorten or lengthen the retake. The claim
    (`... WHERE completed = FALSE RETURNING id`) is what distinguishes *the same
    sitting submitted twice* from *a genuine retake*.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    sitting = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    _answer_all(app, learner, sitting, correct=3)
    path = f"/checkpoint/{sitting['session_id']}/complete"
    first = request(app, "POST", path, cookies=_as(learner)).json()
    second = request(app, "POST", path, cookies=_as(learner)).json()
    assert first["passed"] == second["passed"] is False
    row = db.execute(
        "SELECT checkpoint_attempts, retake_due_on FROM user_unit_state "
        " WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert row[0] == 1, "one sitting is one attempt, however many times it is sent"


def test_a_completed_sitting_reports_done_and_serves_no_items(app, db, learner) -> None:
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    sitting = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    _answer_all(app, learner, sitting, correct=12)
    request(
        app, "POST", f"/checkpoint/{sitting['session_id']}/complete",
        cookies=_as(learner),
    )
    again = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert again["state"] == "done"
    assert again["items"] == []


def test_the_checkpoint_requires_a_session(app) -> None:
    assert request(app, "GET", "/checkpoint/today").status_code == 401


# ── #269: the sitting is a stored fact, not a re-derived one ────────────────


def test_a_sitting_survives_an_answer_and_a_refetch(app, db, learner) -> None:
    """**RED BEFORE THE FIX. This is H4's blocking defect, reduced to one answer.**

    The runner fetched the twelve once into browser state and the server recorded
    nothing about which twelve it chose, so `today` re-selected on every call
    through `checkpoint_items` — whose predicate includes `_UNATTEMPTED`. **Every
    answer removed an item from the selectable set**, the selector refuses a
    cohort it cannot fill whole, and after the FIRST answer the sitting could
    never be re-hydrated. On a laptop that surfaced at question 10 of 12.

    Asserting the **ids**, not the count: a refetch that returned twelve
    different items would be just as broken and a length check cannot see it
    (#256's family, and this file has been bitten by it twice).
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)

    first = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert first["state"] == "ready"
    served = [one["id"] for one in first["items"]]
    assert len(served) == 12

    # One answer, through the real items route, exactly as the runner does it.
    _answer_first(app, learner, first, 1)

    again = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert again["state"] == "ready", "the sitting must survive being worked on"
    assert [one["id"] for one in again["items"]] == served, (
        "the same twelve, in the same order — a sitting is a stored fact"
    )


def test_the_stored_sitting_is_what_the_server_answers_from(app, db, learner) -> None:
    """The twelve live on the `sessions` row, so resume needs no browser state.

    `sessions.payload` and not a new column: §8 already established payload as
    where per-task-type facts live, and 018 is the only DDL this slice takes.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    body = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    served = [one["id"] for one in body["items"]]

    row = db.execute(
        "SELECT payload FROM sessions WHERE user_id = %s AND task_type = 'checkpoint'",
        (learner.user_id,),
    ).fetchone()
    assert row is not None
    assert list((row[0] or {}).get("item_ids") or []) == served


def test_answered_count_is_derivable_from_the_server(app, db, learner) -> None:
    """**The Finish button's condition stops living in the browser.**

    H4 could not finish because `answered >= items.length` was React state that
    the lost sitting took with it. The count comes from `item_attempts`, which is
    where `complete` already scores from.
    """
    _enter(db, learner)
    _seed_cohort(learner.user_id)
    first = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert first["answered"] == 0

    _answer_first(app, learner, first, 3)
    again = request(app, "GET", "/checkpoint/today", cookies=_as(learner)).json()
    assert again["answered"] == 3
