"""W5b: the harness that observes the naturalness judge without changing it.

Every test here is offline and makes zero model calls — `netguard` is untouched.
They prove the harness measures what production measures; the behaviour itself is
observed by `python -m core.items.judge_observe --live`, which is human-run and
billed (CLAUDE.md §5b).

**The load-bearing test is `test_arm_a_is_byte_identical_to_what_validate_sends`.**
If `sentence_of` ever changes, the harness follows it or this suite fails. A
harness that drifted from the thing it reports on is the W5a `--live` bug, and
this slice exists to answer a question that bug's shape already cost a slice.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.items import gates, judge_observe
from core.items.checks import sentence_of
from core.items.schema import GAP

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "packages" / "core" / "items" / "judge_observe.py"
FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "items" / "valid.json").read_text(
        encoding="utf-8"
    )
)

#: The four whose judged string is defective, named rather than derived: a
#: derived list would silently agree with a harness that stopped filling gaps.
GAPPED = {"mcq", "cloze_cued", "collocation_pick", "error_spot"}


def _loaded() -> list[dict]:
    return judge_observe.load_fixtures()


def _by_name() -> dict:
    return {row["name"]: row["item"] for row in _loaded()}


# ── the arms ────────────────────────────────────────────────────────────────


def test_arm_a_is_byte_identical_to_what_validate_sends() -> None:
    """Arm A must BE `sentence_of`, not resemble it.

    `gates.validate` judges `sentence_of(item)` (gates.py:399). If the harness
    reported on any other string, its finding would describe a request
    production never makes.
    """
    for name, item in _by_name().items():
        assert judge_observe.arm_as_shipped(item) == sentence_of(item), name


def test_arm_a_hands_the_judge_a_gap_for_exactly_four_fixtures() -> None:
    """The finding, pinned. This is #115's cause stated as an assertion.

    Deliberately asserts the CURRENT broken behaviour rather than the desired
    behaviour: W5b is an investigation and may not fix the gate. When the fix
    lands this test flips to `GAP not in ...` for every fixture, and that
    inversion is the fix's own acceptance criterion.
    """
    gapped = {
        name
        for name, item in _by_name().items()
        if GAP in judge_observe.arm_as_shipped(item)
    }
    assert gapped == GAPPED - {"error_spot"}


def test_error_spot_hands_the_judge_its_own_deliberate_error() -> None:
    item = _by_name()["error_spot"]
    assert judge_observe.arm_as_shipped(item) == "I goed to the shops"


def test_arm_b_closes_every_gap() -> None:
    for name, item in _by_name().items():
        assert GAP not in judge_observe.arm_filled(item), name


def test_arm_b_corrects_the_wrong_tile_in_place() -> None:
    item = _by_name()["error_spot"]
    assert judge_observe.arm_filled(item) == "I went to the shops"


def test_arm_b_differs_from_arm_a_for_exactly_the_four() -> None:
    """The asymmetry IS the hypothesis, so it is asserted rather than assumed."""
    differ = {
        name
        for name, item in _by_name().items()
        if judge_observe.arm_filled(item) != judge_observe.arm_as_shipped(item)
    }
    assert differ == GAPPED


def test_arm_b_is_deterministic_and_costs_no_model_call(monkeypatch) -> None:
    monkeypatch.setattr(gates, "_chat", _forbidden)
    for item in _by_name().values():
        assert judge_observe.arm_filled(item) == judge_observe.arm_filled(item)


def test_the_partition_is_ten_judged_four_gapped_six_prose() -> None:
    """`match_pairs` is never judged: `sentence_of` returns "" and
    `gates.validate` skips the call (`if sentence.strip()`)."""
    judged, gapped, clean = judge_observe._partition(_loaded())
    assert [len(judged), len(gapped), len(clean)] == [10, 4, 6]
    assert "match_pairs" not in {r["name"] for r in judged}


# ── the recording seam ──────────────────────────────────────────────────────


def _forbidden(*_args, **_kwargs):
    raise AssertionError("no model call may be made here")


def test_the_shim_returns_exactly_what_it_wrapped(monkeypatch) -> None:
    payload = {"verdicts": [{"n": 1, "natural": False, "reason": "stilted"}]}
    monkeypatch.setattr(gates, "_chat", lambda *a, **k: payload)
    with judge_observe._recording() as calls:
        assert gates._chat([{"role": "user", "content": "1. hi"}]) is payload
    assert len(calls) == 1
    assert calls[0]["response"] is payload


def test_the_shim_restores_the_seam(monkeypatch) -> None:
    original = object()
    monkeypatch.setattr(gates, "_chat", original)
    with judge_observe._recording():
        assert gates._chat is not original
    assert gates._chat is original


def test_the_shim_restores_the_seam_when_the_call_raises(monkeypatch) -> None:
    """The path that matters: a provider error must not leave the gate wrapped."""
    original = _forbidden
    monkeypatch.setattr(gates, "_chat", original)
    with pytest.raises(AssertionError):
        with judge_observe._recording():
            gates._chat()
    assert gates._chat is original


# ── the reason `judge_naturalness` discards ─────────────────────────────────


def test_the_reason_survives_the_call_that_throws_it_away(monkeypatch) -> None:
    """The whole point of the module: gates.py:331 reads `natural` and drops
    `reason`, so the W6 run saw a bare `unnatural` and could not distinguish the
    two explanations. Verdict and reason must come from the SAME call."""
    monkeypatch.setattr(
        gates,
        "_chat",
        lambda *a, **k: {"verdicts": [{"n": 1, "natural": False, "reason": "stilted"}]},
    )
    assert judge_observe.judge_once("I ___ to the shops.", settings=None) == (
        False,
        "stilted",
    )


def test_a_missing_row_is_reported_and_not_silently_natural(monkeypatch) -> None:
    """`judge_naturalness` fails OPEN — a row the model omits defaults to natural
    (gates.py:335). That is a deliberate design choice and W5b does not change
    it, but a reader of this output must be able to see when it fired."""
    monkeypatch.setattr(gates, "_chat", lambda *a, **k: {"verdicts": []})
    verdict, reason = judge_observe.judge_once("anything", settings=None)
    assert verdict is True
    assert reason == "missing-row"


def test_a_wrong_shaped_response_does_not_read_as_a_verdict(monkeypatch) -> None:
    """`gates._chat` is ONE seam shared by the probe and the judge. A probe-shaped
    response reaching the judge parses to no rows at all, so every sentence fails
    open. The harness surfaces that rather than printing it as `ok`."""
    monkeypatch.setattr(gates, "_chat", lambda *a, **k: {"acceptable": ["went"]})
    assert judge_observe.judge_once("anything", settings=None) == (True, "missing-row")


# ── tallies and the pre-registered branch rules ─────────────────────────────


def test_the_thresholds_are_the_ones_the_predictions_were_written_with() -> None:
    assert (judge_observe.HIGH, judge_observe.LOW) == (0.8, 0.2)
    assert judge_observe.DEFAULT_RUNS == 5


@pytest.mark.parametrize(
    "results, natural, rejected",
    [
        ([(False, "stilted")] * 5, False, True),
        ([(True, "ok")] * 5, True, False),
        ([(True, "ok")] * 4 + [(False, "stilted")], True, False),
        ([(True, "ok")] * 3 + [(False, "stilted")] * 2, False, False),
    ],
)
def test_at_least_eighty_percent_means_eighty_percent(results, natural, rejected):
    assert judge_observe._mostly_natural(results) is natural
    assert judge_observe._mostly_rejected(results) is rejected


def test_the_summary_names_every_reason_the_model_gave() -> None:
    line = judge_observe._summarise(
        [(False, "stilted"), (False, "stilted"), (False, "textbook")]
    )
    assert line.startswith("0/3 natural")
    assert "stiltedx2" in line and "textbookx1" in line


# ── this module writes nothing, anywhere ────────────────────────────────────


def test_the_harness_reaches_no_database_and_no_provider_directly() -> None:
    """The machine-checkable form of "nothing is written to the database".

    `core.services` is where every query lives, so a module that imports none of
    it cannot write a row. `core.llm`/`core.speech` are excluded too: this module
    is not in `test_core_boundary.ITEMS_MODEL_CALLERS`, and it reaches the
    provider only through `gates`, which is the seam it observes.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.add(node.module)
    offenders = {
        m
        for m in imported
        if m.startswith("core.services.") and m != "core.services.paths"
    } | (imported & {"core.llm", "core.speech", "psycopg", "psycopg_pool"})
    assert offenders == set(), f"judge_observe reaches: {sorted(offenders)}"


def test_the_loader_agrees_with_the_one_that_seeded_production() -> None:
    """Pinned against `seed_fixtures` rather than importing it.

    Importing it would pull `core.services` into this module and cost the test
    above. Two loaders that parse the same committed file cannot drift while
    this assertion holds.
    """
    from core.items.seed_fixtures import load_fixtures as seeded

    assert [r["name"] for r in _loaded()] == [r["name"] for r in seeded()]
    assert [r["item"] for r in _loaded()] == [r["item"] for r in seeded()]


def test_the_loader_reads_the_committed_fixture_file() -> None:
    assert [r["name"] for r in _loaded()] == [r["name"] for r in FIXTURES]


# ── the default sends nothing ───────────────────────────────────────────────


def test_the_dry_run_makes_no_call_and_is_the_default(monkeypatch, capsys) -> None:
    monkeypatch.setattr(gates, "_chat", _forbidden)
    monkeypatch.setattr(gates, "_synthesize", _forbidden)
    monkeypatch.setattr(gates, "_transcribe", _forbidden)
    assert judge_observe.main([]) == 0
    out = capsys.readouterr().out
    assert "Nothing was sent and nothing was written." in out
    assert "10 judged, 4 of them gapped or errored, 6 already prose." in out


def test_the_dry_run_shows_the_four_defective_strings(monkeypatch, capsys) -> None:
    """Most of the finding is legible before a single call is billed."""
    monkeypatch.setattr(gates, "_chat", _forbidden)
    judge_observe.main([])
    out = capsys.readouterr().out
    assert out.count("<-- GAPPED/ERRORED") == 4
    assert "'I ___ to the shops yesterday.'" in out
    assert "'I went to the shops yesterday.'" in out


def test_runs_must_be_at_least_one() -> None:
    with pytest.raises(SystemExit):
        judge_observe.main(["--runs", "0"])
