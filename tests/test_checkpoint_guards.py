"""The guards W11 owes that do not fit the seam, the supply or the route.

Four things, each filed against this slice and each asserted here:

* **#194** -- `probe_target`'s verdict survives into `items.validation`.
* **the ceiling** -- computed from the slot plan, never a constant.
* **#107 / CLAUDE.md §5** -- the checkpoint writes nothing to the error journal.
* **the unfreeze** -- a `passed` row advances `current_unit`, through the route.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


# ── #194 ────────────────────────────────────────────────────────────────────


def test_the_target_verdict_survives_into_items_validation() -> None:
    """The ranking, the claimed rank, **the runner-up** and the confidence.

    W10c produced all four in `TargetVerdict`, printed them and dropped them, so
    the evidence for *this item tests its target* survived only in a run's
    stdout. **This is #119's exact shape in a gate written knowing about #119**,
    which is why it was filed at `medium`.

    The runner-up is the sharp loss: on an item that PASSED, second place is the
    distinction it came closest to blurring.

    **No migration**: `items.validation` is JSONB and 012's CHECK requires three
    keys rather than forbidding a fourth -- asserted below rather than assumed.
    """
    from core.items.gates import ValidationReport

    report = ValidationReport(
        verdict="passed",
        target_ranking=("past simple", "past continuous"),
        target_claimed_rank=1,
        target_first="past simple",
        target_runner_up="past continuous",
        target_confidence="high",
    )
    stored = report.as_json()
    assert stored["target_runner_up"] == "past continuous"
    assert stored["target_ranking"] == ["past simple", "past continuous"]
    assert stored["target_claimed_rank"] == 1
    assert stored["target_confidence"] == "high"
    # 012's CHECK requires exactly these three. A fourth key is permitted; a
    # missing one is not.
    for required in ("verdict", "deterministic", "naturalness"):
        assert required in stored


def test_the_migration_012_check_still_passes_with_the_new_keys() -> None:
    """The keys 012's CHECK names are present and JSON-serialisable together."""
    import json

    from core.items.gates import ValidationReport

    json.dumps(ValidationReport(verdict="repaired").as_json())


# ── the ceiling ─────────────────────────────────────────────────────────────


def test_the_ceiling_is_computed_from_the_slot_plan_not_a_constant() -> None:
    """**A ceiling that omits a call the run makes is the defect it exists to
    prevent**, and the first three drafts of this slice's plan omitted #169's
    cohort pass while describing it as *on the ceiling*.

    Every term is derived at call time, so narrowing the permitted types -- which
    #207's open half may do -- moves the number instead of leaving a stale
    literal behind.
    """
    from core.items.generate import _expected_checkpoint_calls, unit_plan

    wide = _expected_checkpoint_calls(unit_plan((1,), checkpoint=True))
    two_units = _expected_checkpoint_calls(unit_plan((1, 2), checkpoint=True))
    assert two_units > wide, "a second unit must cost more"
    assert wide > 12, "twelve slots cannot cost fewer than twelve calls"


def test_the_ceiling_moves_when_the_probed_families_move() -> None:
    """`match_pairs` is unprobed because its `ANSWER_FAMILY` is `exact` (#192).

    If that ever changes -- adding `exact` to `PROBED_FAMILIES` is one of the
    named options on that row -- the ceiling must rise on its own. A hardcoded
    `len(SLOT_TYPES) - 1` would not.
    """
    from core.items import gates
    from core.items.generate import _expected_checkpoint_calls, unit_plan

    plan = unit_plan((1,), checkpoint=True)
    before = _expected_checkpoint_calls(plan)
    original = gates.PROBED_FAMILIES
    try:
        gates.PROBED_FAMILIES = frozenset(original | {"exact"})
        after = _expected_checkpoint_calls(plan)
    finally:
        gates.PROBED_FAMILIES = original
    assert after > before


def test_the_cohort_uniqueness_pass_is_on_the_ceiling() -> None:
    """#169's checkpoint-level pass is ONE batched call per cohort, and it is a
    TERM rather than a comment beside the arithmetic."""
    import inspect

    from core.items import generate

    source = inspect.getsource(generate._expected_checkpoint_calls)
    assert "#169" in source


# ── #107 and CLAUDE.md §5: the journal is not written ───────────────────────


def test_nothing_in_the_checkpoint_path_writes_to_the_error_journal() -> None:
    """**The guard that keeps §4's decision honest against a later slice.**

    PRD §3 asks for the missed targets to be injected into the next week's review
    queue. W11 does not build it, and the reason is CLAUDE.md §5 rather than
    effort: `error_types` has nineteen coarse codes, three of unit 1's four
    grammar targets collapse onto `verb_tense_past` and the fourth has no code at
    all, `items.error_type` is NULL on every generated row, and **a tapped
    checkpoint answer is a selection, not a self-produced error.** Every row such
    a writer produced would be a wrong row, and a wrong row is permanent damage
    while a missing one is recoverable.

    So: no `INSERT INTO errors` is reachable from the checkpoint path. A scan,
    not a promise.
    """
    watched = [
        REPO / "packages" / "core" / "services" / "checkpoints.py",
        REPO / "packages" / "core" / "syllabus" / "checkpoint.py",
        REPO / "apps" / "api" / "routers" / "checkpoint.py",
    ]
    offenders = []
    for path in watched:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {
            id(node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and isinstance(getattr(node, "body", [None])[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            for node in [node.body[0].value]
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                if "insert into errors" in node.value.lower():
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], (
        "the checkpoint must not write to the error journal (#107, CLAUDE.md §5)"
        f": {offenders}"
    )


def test_missed_targets_reads_the_target_and_not_the_error_type() -> None:
    """**Keyed on `payload->>'grammar_target'`, never on `error_type`.**

    `items.error_type` is in `core.items.schema.NOT_THE_GENERATORS`, so every
    generated item carries NULL there -- a re-queue keyed on the journal's
    taxonomy could not name the target and, on the live rows, could not name
    anything at all.
    """
    import inspect
    import textwrap

    from core.services import syllabus

    tree = ast.parse(textwrap.dedent(inspect.getsource(syllabus.missed_targets)))
    function = tree.body[0]
    # Strip the docstring by AST rather than by splitting on triple quotes: the
    # SQL in this function is itself a triple-quoted string, so the naive split
    # returns the tail of the QUERY and the assertion below passes or fails on
    # the wrong text. (It failed, which is how this was found.)
    body_nodes = function.body[1:] if ast.get_docstring(function) else function.body
    body = "\n".join(ast.unparse(node) for node in body_nodes)
    assert "grammar_target" in body
    assert "error_type" not in body, "the coarse code cannot name one of the 82"


def test_error_type_is_still_withheld_from_the_generator() -> None:
    """The premise the whole re-queue decision rests on, asserted rather than
    remembered. If a later slice lets the generator set `error_type`, the
    argument in `missed_targets`' docstring stops being true and this fails."""
    from core.items.schema import NOT_THE_GENERATORS

    assert "error_type" in NOT_THE_GENERATORS
    assert "cohort" in NOT_THE_GENERATORS


# ── the unfreeze ────────────────────────────────────────────────────────────


def test_a_passed_row_advances_current_unit(monkeypatch) -> None:
    """The whole point of the slice, at the seam W10 left for it.

    `current_unit` selects on `passed_at IS NOT NULL` and never reads `state`, so
    a `passed` write alone advances the learner -- which is what made operator
    ruling 2 (*W11 writes `passed` only, never `available`*) cost nothing.
    """
    from datetime import datetime, timezone

    import psycopg

    from core.config import load_settings
    from core.services.syllabus import current_unit, record_checkpoint, record_unit_entry, upsert_units
    from core.syllabus.content import units

    now = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
    with psycopg.connect(load_settings().database_url) as conn:
        try:
            upsert_units(conn, units())
            user_id = conn.execute(
                "INSERT INTO users (name, native_language, auth_email, onboarded) "
                "VALUES ('w11-unfreeze', 'fa', 'w11-unfreeze@example.test', TRUE) "
                "RETURNING id"
            ).fetchone()[0]

            assert current_unit(conn, user_id) == 1, "everyone starts at 1"
            record_unit_entry(conn, user_id, 1, now=now)
            assert current_unit(conn, user_id) == 1, "entering is not passing"
            record_checkpoint(conn, user_id, 1, correct=10, item_count=12, now=now)
            assert current_unit(conn, user_id) == 2, "a pass advances the learner"
        finally:
            conn.rollback()
