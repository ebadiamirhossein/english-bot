"""Launch 2026-09-26, B2: the placement check with an empty or thin band.

**The evidence:** the host's bank after `--apply` holds listening **C1 0** and
**B2 4**, grammar **A2 12** (the operator's paste). The rule itself is stated in
`core.placement.readiness`.

**What this file establishes, each through the real routes where a learner can
reach it (CLAUDE.md §3 rule 1):**

* the rule, against today's counts — **not ready**, short listening C1 by one;
* a bank with an empty listening C1 cell is never offered, and answers 409 —
  never a 500;
* a cell emptied UNDER an open sitting (a row removed after the start) is
  skipped, never claimed: five clips all right read **B2**, not C1;
* the grammar ladder stepping up into an empty C1 stops as `bank_thin` and
  places at **B2**, the highest band it held — never C1;
* the monthly re-run, when a cell cannot be drawn disjointly: **not offered**,
  and no item is served twice.

User actions: the learner opens *Where to start* (`GET /placement`), taps Start
(`POST /placement/start`), answers a sitting and reads the result.

**RED DEMONSTRATIONS (2026-09-26, a scripted mutation each, `python -B`,
caches cleared, source restored and re-touched):** `_ready`'s pre-B2 body put
back (one clip of ANY band enough) → the empty-C1 and second-sitting tests red
(each read `ready: true`); `listening_band`'s ceiling removed → the
emptied-under-a-sitting test red (it read C1); the listening minimums dropped
from `readiness` → four red, today's-bank among them. **The grammar test
passed before B2 — the ladder already stopped honestly — so it pins behaviour
rather than proving a fix,** and was shown red twice: the `bank_id is None`
branch removed from `_next_step` (a `NULL` served, a 500), and `held_band`
counting an up-move's `to` as held (C1 claimed). `GRAMMAR_READY_PER_BAND = 1`
→ the two pure tests that state it.
"""

from __future__ import annotations

import pytest

from core.placement import readiness
from tests.support import placement_seed as ps
from tests.test_placement_route import bank, no_voice  # noqa: F401 — fixtures
from tests.test_progress_route import (  # noqa: F401 — fixtures used by name
    app,
    auth_env,
    db,
    learners,
)

# ── the rule, pure ──────────────────────────────────────────────────────────


def _host_counts_2026_09_26() -> dict[tuple, int]:
    """The operator's `section, cefr` paste after `--apply`, as the service
    keys it. Vocabulary: 240 real words, 24 per frequency band (the dry run's
    366 = 240 + 120 + 6), 120 pseudo-words."""
    held: dict[tuple, int] = {("vocabulary", "real", b): 24 for b in range(10)}
    held[("vocabulary", "pseudo")] = 120
    held.update({("grammar", "A2"): 12, ("grammar", "B1"): 21,
                 ("grammar", "B2"): 22, ("grammar", "C1"): 18})
    held.update({("listening", "A2"): 6, ("listening", "B1"): 10,
                 ("listening", "B2"): 4})
    held[("speaking", "any")] = 6
    return held


def test_the_rule_is_the_stated_numbers() -> None:
    need = readiness.minimums()
    assert {k: v for k, v in need.items() if k[0] == "grammar"} == {
        ("grammar", "A2"): 8, ("grammar", "B1"): 8, ("grammar", "B2"): 8, ("grammar", "C1"): 8,
    }
    assert {k: v for k, v in need.items() if k[0] == "listening"} == {
        ("listening", "A2"): 1, ("listening", "B1"): 2, ("listening", "B2"): 2,
        ("listening", "C1"): 1,
    }
    assert need[("vocabulary", "pseudo")] == 20
    assert [need[("vocabulary", "real", b)] for b in range(10)] == [4] * 10
    assert need[("speaking", "any")] == 1


def test_todays_bank_is_not_offered() -> None:
    assert readiness.shortfall(_host_counts_2026_09_26()) == {("listening", "C1"): 1}
    assert readiness.ready(_host_counts_2026_09_26()) is False


def test_one_c1_clip_is_enough_and_seven_a2_grammar_items_are_not() -> None:
    held = _host_counts_2026_09_26()
    held[("listening", "C1")] = 1
    assert readiness.ready(held) is True
    held[("grammar", "A2")] = 7
    assert readiness.shortfall(held) == {("grammar", "A2"): 1}


# ── through the routes ──────────────────────────────────────────────────────


def _ids(db, ids: list[int], section: str, cefr: str) -> list[int]:
    return [r[0] for r in db.execute(
        "SELECT id FROM placement_bank WHERE id = ANY(%s) AND section = %s AND cefr = %s",
        (ids, section, cefr)).fetchall()]


def _remove(db, ids: list[int], section: str, cefr: str) -> None:
    """Delete this test's own unserved rows in one cell (a row served is
    referenced and cannot be deleted — the instrument is fixed)."""
    db.execute(
        """DELETE FROM placement_bank b WHERE b.id = ANY(%s) AND b.section = %s
             AND b.cefr = %s
             AND NOT EXISTS (SELECT 1 FROM placement_run_items r WHERE r.bank_id = b.id)""",
        (_ids(db, ids, section, cefr), section, cefr))
    db.commit()


def test_an_empty_listening_c1_is_not_offered(app, db, bank, learners) -> None:
    _remove(db, bank, "listening", "C1")
    learner = learners()
    view = ps.call(app, "GET", "/placement", learner)
    assert view.status_code == 200
    assert view.json()["ready"] is False and view.json()["available"] is False
    start = ps.call(app, "POST", "/placement/start", learner, body={})
    assert start.status_code == 409 and start.json()["detail"] == "bank_not_ready"


def _answer_until(app, db, learner, step: dict, section: str) -> dict:
    while step["section"] != section:
        if step["section"] == "vocabulary":
            real = ps.bank_row(db, step["item"]["id"])["is_word"]
            step = ps.answer(app, learner, step, known=bool(real))
        elif step["section"] == "grammar":
            step = ps.answer(app, learner, step, text=ps.RIGHT)
        elif step["section"] == "listening":
            step = ps.answer(app, learner, step, text=ps.HEARD)
        else:
            step = ps.answer(app, learner, step, skip=True)
    return step


def _radar(result: dict) -> dict:
    return {r["skill"]: r["band"] for r in result["shown"]["radar"]}


def test_a_listening_cell_emptied_under_an_open_sitting_is_never_claimed(
        app, db, bank, learners) -> None:
    learner = learners()
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    _remove(db, bank, "listening", "C1")  # after the start: `_ready` held then
    step = _answer_until(app, db, learner, step, "listening")
    served = []
    while step["section"] == "listening":
        served.append(ps.bank_row(db, step["item"]["id"])["cefr"])
        step = ps.answer(app, learner, step, text=ps.HEARD)
    assert served == ["A2", "B1", "B1", "B2", "B2"]
    step = _answer_until(app, db, learner, step, "done")
    finished = ps.call(app, "POST", "/placement/finish", learner, body={})
    assert finished.status_code == 200, finished.text
    assert _radar(finished.json())["listening"] == "B2"


def test_the_ladder_stepping_into_an_empty_c1_places_at_b2(app, db, bank, learners) -> None:
    """All right: B1 ✓✓ → B2 ✓✓ → C1, which has nothing. `bank_thin`; the
    highest band HELD is B2 (stepped up from). C1 was never served, so never
    claimed."""
    learner = learners()
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    _remove(db, bank, "grammar", "C1")
    step = _answer_until(app, db, learner, step, "grammar")
    bands = []
    while step["section"] == "grammar":
        bands.append(ps.bank_row(db, step["item"]["id"])["cefr"])
        step = ps.answer(app, learner, step, text=ps.RIGHT)
    assert bands == ["B1", "B1", "B2", "B2"]
    step = _answer_until(app, db, learner, step, "done")
    finished = ps.call(app, "POST", "/placement/finish", learner, body={})
    assert finished.status_code == 200, finished.text
    assert finished.json()["shown"]["where_to_start"] == "B2"
    assert _radar(finished.json())["grammar"] == "B2"
    assert db.execute("SELECT grammar_stop FROM placement_runs WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == "bank_thin"


def test_a_second_sitting_that_cannot_be_drawn_disjointly_is_not_offered(
        app, db, bank, learners) -> None:
    """The seed holds two sittings' worth, so two C1 clips. The first sitting
    is served one; the other is removed; a month on, the re-run finds none it
    has not been served. **Not offered** — never a repeat, never a 500."""
    learner = learners()
    ps.run_sitting(app, db, learner)
    assert ps.call(app, "POST", "/placement/finish", learner, body={}).status_code == 200
    db.execute(
        "UPDATE placement_runs SET started_at = started_at - interval '29 days', "
        "finished_at = finished_at - interval '29 days' WHERE user_id = %s",
        (learner.user_id,))
    db.commit()
    _remove(db, bank, "listening", "C1")  # removes only the unserved one
    assert len(_ids(db, bank, "listening", "C1")) == 1  # the served one stays

    view = ps.call(app, "GET", "/placement", learner).json()
    assert view["state"] == "finished"
    assert view["ready"] is False and view["available"] is False
    start = ps.call(app, "POST", "/placement/start", learner, body={})
    assert start.status_code == 409 and start.json()["detail"] == "bank_not_ready"
    assert db.execute("SELECT COUNT(*) FROM placement_runs WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == 1
