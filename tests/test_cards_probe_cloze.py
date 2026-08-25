"""W8a: the cloze uniqueness measurement, and the guarantees it rests on.

Every test here is recorded-response or source-reading. **None of them proves
model behaviour** — that is what `--live` is for, and it is a human step on the
production host because the calls are billed and the rows are production. What
they prove is that the module reuses W5a's probe rather than growing a second
one, that the learner's own sentence reaches the model unmodified, and that
nothing it does can write.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from core.cards import probe_cloze
from core.items import ANSWER_FAMILY, PROBED_FAMILIES
from core.items import gates
from core.items.projection import visible_projection
from core.items.schema import ClozeCuedItem

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "packages" / "core" / "cards" / "probe_cloze.py"

#: The production card the finding was reported from, verbatim, five underscores
#: and all. Hardcoded rather than computed from anything under test (§3 rule 5).
BROKEN_FRONT = '"I wish someone had warned me to ask about _____ upfront," she said.'
BROKEN_BACK = "hidden costs"


class _Card:
    """The three fields `as_item` reads. Not a `Card`: this asserts the mapping
    is narrow, and a full row would hide a fourth field creeping in."""

    def __init__(self, card_id=1, user_id=2, front=BROKEN_FRONT, back=BROKEN_BACK):
        self.id = card_id
        self.user_id = user_id
        self.card_type = "cloze"
        self.front = front
        self.back = back


# ── the mapping: a real item, not a fabricated one ─────────────────────────


def test_a_card_becomes_a_real_cloze_cued_item() -> None:
    item = probe_cloze.as_item(_Card())
    assert isinstance(item, ClozeCuedItem)
    assert item.item_type == probe_cloze.ITEM_TYPE == "cloze_cued"


def test_the_five_underscore_gap_reaches_the_model_unmodified() -> None:
    """The whole reason there is no normalising step.

    `core.services.anki.GAP` is `_____` and `core.items.schema.GAP` is `___`.
    Rewriting one into the other before the probe would send the model a
    sentence the learner never sees, which is exactly the defect W5b found and
    W5c fixed: the gate asked the right question about the wrong string.
    """
    item = probe_cloze.as_item(_Card())
    assert item.prompt_text == BROKEN_FRONT
    assert "_____" in item.prompt_text


def test_the_projection_carries_the_front_and_nothing_else() -> None:
    """What `probe_acceptable` sends, asserted at the shape rather than assumed.

    `probe_cloze` may not call `visible_projection` itself — three modules may,
    and `test_core_boundary.py::test_exactly_one_module_projects_an_item` holds
    that. The tests are outside that scan, which is why the assertion lives here.
    """
    projection = visible_projection(probe_cloze.as_item(_Card()))
    assert projection == {
        "item_type": "cloze_cued",
        "prompt_text": BROKEN_FRONT,
    }


def test_track_is_supplied_and_never_reaches_the_wire() -> None:
    """`track` is the one field a card does not carry.

    It is required by `BaseItem`, so it has to be something; it is a module
    constant rather than a per-card guess so that "it does not influence the
    measurement" is checkable rather than asserted. This is the check.
    """
    assert probe_cloze.TRACK == "life"
    for track in ("life", "work", "curiosity"):
        item = ClozeCuedItem(track=track, prompt_text=BROKEN_FRONT, answer=BROKEN_BACK)
        assert "track" not in visible_projection(item)
        assert visible_projection(item) == visible_projection(probe_cloze.as_item(_Card()))


def test_the_item_routes_to_the_family_that_is_actually_probed() -> None:
    """A `slot` item never widens: a second fitting form means the gap tests
    nothing — gate 3 failing, not gate 1 passing."""
    assert ANSWER_FAMILY[probe_cloze.ITEM_TYPE] == "slot"
    assert ANSWER_FAMILY[probe_cloze.ITEM_TYPE] in PROBED_FAMILIES


def test_the_mapping_reads_only_front_and_back() -> None:
    """A narrow mapping, held narrow. Anything else on a card — meaning,
    register, provenance, FSRS state — is not what the learner is looking at
    when they answer, so it may not reach the probe."""
    source = inspect.getsource(probe_cloze.as_item)
    for forbidden in ("meaning", "register", "context_sentence", "source_ref", "cue"):
        assert forbidden not in source, forbidden


# ── it reuses W5a's probe; there is no second one ──────────────────────────


def test_the_probe_call_goes_through_gates_and_nothing_else(monkeypatch) -> None:
    """One call, W5a's, at the `_chat` seam the rest of the suite already uses.

    A second prompt or a second call site would drift from the first exactly as
    the record says duplicated `chat()` call sites do.
    """
    sent: list[dict] = []

    def _fake(messages, *, system, **kwargs):
        sent.append({"messages": messages, "system": system})
        return {"acceptable": ["hidden costs", "the price", "fees"],
                "confidence": "low"}

    monkeypatch.setattr(gates, "_chat", _fake)
    result = probe_cloze.probe_one(_Card())

    assert len(sent) == 1, "exactly one billed call per card"
    # Decoded rather than substring-matched: the payload is JSON, so the card's
    # own double quotes arrive escaped and a substring test would pass on a
    # sentence that had been altered anywhere else.
    payload = json.loads(sent[0]["messages"][0]["content"])
    assert payload == {"item_type": "cloze_cued", "prompt_text": BROKEN_FRONT}
    # The system prompt is W5a's, read off disk, not one written here.
    assert sent[0]["system"] == gates._prompt("item_probe.txt")
    assert result.classes == 3
    assert result.confidence == "low"


def test_a_contraction_is_not_counted_as_a_second_answer(monkeypatch) -> None:
    """Counting is `grading.distinct_answers`, unchanged — the same function the
    live gate uses, so `I'll` and `I will` collapse here exactly as in
    production. If this module counted raw strings it would report a defect
    where the grader sees none."""
    monkeypatch.setattr(
        gates, "_chat",
        lambda *a, **k: {"acceptable": ["I'll", "I will"], "confidence": "high"},
    )
    assert probe_cloze.probe_one(_Card(back="I'll")).classes == 1


def test_a_card_whose_canonical_is_not_offered_is_flagged_separately(
    monkeypatch,
) -> None:
    """Not answerable as authored — a stronger defect than ambiguity, and a
    different fix. It is reported whatever the totals say."""
    monkeypatch.setattr(
        gates, "_chat",
        lambda *a, **k: {"acceptable": ["the price"], "confidence": "high"},
    )
    result = probe_cloze.probe_one(_Card())
    assert result.classes == 1
    assert result.recoverable is False


def test_a_uniquely_answerable_card_reports_one_class(monkeypatch) -> None:
    monkeypatch.setattr(
        gates, "_chat",
        lambda *a, **k: {"acceptable": ["hidden costs"], "confidence": "high"},
    )
    result = probe_cloze.probe_one(_Card())
    assert (result.classes, result.recoverable) == (1, True)


# ── the pre-registered prediction, and the branch it selects ───────────────


def test_the_prediction_is_registered_in_the_docstring_before_any_run() -> None:
    """#57 and W5b's precedent: the prediction is written down before the
    answer exists, so it cannot be adjusted to fit afterwards."""
    doc = probe_cloze.__doc__ or ""
    assert "Pre-registered prediction" in doc
    assert f"{probe_cloze.PREDICTED_LOW} to {probe_cloze.PREDICTED_HIGH}" in doc
    assert (probe_cloze.PREDICTED_LOW, probe_cloze.PREDICTED_HIGH) == (6, 11)


@pytest.mark.parametrize(
    "multi,expected",
    [(14, ">=10"), (10, ">=10"), (9, "4-9"), (4, "4-9"), (3, "<=3"), (0, "<=3")],
)
def test_the_branch_rules_are_applied_by_the_module(multi, expected) -> None:
    """`--live` evaluates its own predictions, so the reading is not left to
    whoever is looking at the output."""
    assert expected in probe_cloze.verdict(multi)


# ── it writes nothing, read off its own AST ────────────────────────────────

#: Every writer in `core.services.cards`, named as a set rather than inferred, so
#: the guarantee survives a new writer being added to that module.
WRITERS = frozenset(
    {
        "create_card",
        "grade_card",
        "promote_to_production",
        # W8b. A ban set that is not extended when a writer is added is a ban
        # that silently narrows — the failure #132 keeps producing.
        "delete_chunk_cloze_cards",
        "cursor",
        "connection",
    }
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


def _tree() -> ast.AST:
    return ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))


def test_the_module_holds_no_statement_that_could_write() -> None:
    """The guarantee `migrate_chunks` carries, in this module's shape.

    Prose *about* the rule is not a breach of it, so docstrings are skipped —
    this module's own docstring says "No UPDATE, no INSERT, no DELETE" and a
    scan that read it would be satisfied only by deleting the sentence.
    """
    tree = _tree()
    prose = _docstring_ids(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in prose:
                continue
            upper = " ".join(node.value.upper().split())
            for keyword in ("UPDATE ", "INSERT INTO ", "DELETE FROM "):
                if keyword in upper:
                    offenders.append(f"line {node.lineno}: {keyword.strip()}")
    assert offenders == [], (
        "core.cards.probe_cloze is a measurement and writes nothing: "
        + "; ".join(offenders)
    )


def test_the_module_calls_no_writer_in_the_cards_service() -> None:
    """Reading through a service is required by the purity rule; calling a
    *writer* through one would be the same defect wearing a service's coat."""
    tree = _tree()
    prose = _docstring_ids(tree)
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and id(node) in prose:
            continue
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None
            )
            if name in WRITERS:
                called.add(name)
    assert called == set(), f"probe_cloze may not call: {sorted(called)}"


def test_the_write_ban_catches_a_real_violation() -> None:
    """The meta-test. A ban proven on nothing is a deleted ban with extra steps."""
    tree = ast.parse(
        'def go():\n'
        '    """Docstring naming UPDATE cards is fine."""\n'
        '    q = "UPDATE cards SET due = %s"\n'
        '    create_card(1)\n',
        filename="<synthetic>",
    )
    prose = _docstring_ids(tree)
    sql = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in prose
        and "UPDATE " in n.value.upper()
    ]
    assert sql == [3], "the literal is caught and the docstring is not"
    calls = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert calls & WRITERS == {"create_card"}


def test_the_module_configures_logging_because_it_spends(monkeypatch) -> None:
    """#140. `core/llm.py` logs exact per-call token usage at INFO on every
    call, and a script that leaves the root logger bare drops every one of those
    lines through `logging.lastResort`. That is how W8's tagger had 138 calls
    and $6.60 reconstructed afterwards against a $1-2 estimate."""
    configured: list[dict] = []
    monkeypatch.setattr(
        probe_cloze.logging, "basicConfig", lambda **kw: configured.append(kw)
    )
    monkeypatch.setattr(probe_cloze, "dry_run", lambda: 0)
    assert probe_cloze.main([]) == 0
    assert configured and configured[0]["level"] == probe_cloze.logging.INFO


def test_the_default_is_dry_and_live_is_opt_in(monkeypatch) -> None:
    """Same standing as `judge_observe` and `migrate_chunks`: nothing is spent
    unless it is asked for by name."""
    calls: list[str] = []
    monkeypatch.setattr(probe_cloze.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(probe_cloze, "dry_run", lambda: calls.append("dry") or 0)
    monkeypatch.setattr(probe_cloze, "live", lambda: calls.append("live") or 0)
    probe_cloze.main([])
    probe_cloze.main(["--live"])
    assert calls == ["dry", "live"]


def test_live_refused_at_the_prompt_spends_nothing(monkeypatch) -> None:
    monkeypatch.setattr(probe_cloze.cards_service, "cloze_cards", lambda: [_Card()])
    monkeypatch.setattr(probe_cloze, "_confirm", lambda calls: False)
    monkeypatch.setattr(
        gates, "_chat", lambda *a, **k: pytest.fail("a call was made after refusal")
    )
    assert probe_cloze.live() == 1
