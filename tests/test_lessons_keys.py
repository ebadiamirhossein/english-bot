"""The target string is the bijection's identity AND a checkpoint key.

`blueprint.validate_checkpoint` compares `checkpoint.per_target` keys against
target text with plain set membership and plain set difference -- **it normalises
nothing**. So a lesson that normalised would drift from the checkpoint W11 reads,
and a reworded target would break one side silently. #212 makes that live:
rewording unit 2's fourth target is an open operator question.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.lessons.schema import parse_lesson
from core.syllabus import blueprint
from core.syllabus.content import units

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"


def test_the_checkpoint_keys_and_the_targets_already_agree_byte_exactly() -> None:
    """Measured across all 24 units, and the expected value is `no mismatches`."""
    mismatched = [
        u.unit_number
        for u in units()
        if sorted(t.target for t in u.grammar_targets)
        != sorted(u.checkpoint["per_target"])
    ]
    assert mismatched == []


def test_no_target_carries_stray_whitespace_or_non_ascii() -> None:
    """A verbatim copy has to be achievable for the bijection to be fair."""
    offenders = [
        t.target
        for u in units()
        for t in u.grammar_targets
        if t.target != t.target.strip() or not t.target.isascii()
    ]
    assert offenders == []


def test_no_target_text_repeats_across_units() -> None:
    """So a decoy from another unit can never collide with an own-unit candidate."""
    texts = [t.target for u in units() for t in u.grammar_targets]
    assert len(texts) == len(set(texts)) == 82


def test_the_target_counts_are_three_and_four_and_never_five() -> None:
    """**The measurement behind the migration comment.**

    Fourteen units at 3, ten at 4, none at 5 -- so for EVERY unit two of the
    three section counts the SQL CHECK permits are wrong, and a five-section
    lesson is wrong for all 24. Hardcoded because this list IS the finding.
    """
    counts = {u.unit_number: len(u.grammar_targets) for u in units()}
    assert sorted(counts.values()).count(3) == 14
    assert sorted(counts.values()).count(4) == 10
    assert 5 not in counts.values()
    assert sum(counts.values()) == 82


def test_validate_checkpoint_normalises_nothing() -> None:
    """Read from the source, so a later normalisation there fails HERE.

    If `validate_checkpoint` ever starts folding case or stripping whitespace,
    the lesson bijection must follow it in the same commit or the two drift.
    """
    source = inspect.getsource(blueprint.validate_checkpoint)
    assert "known = {t.target for t in targets}" in source
    for folding in (".casefold()", ".lower()", ".strip()"):
        assert folding not in source, (
            f"validate_checkpoint now uses {folding}; core.lessons.checks "
            "compares byte-exactly and must be changed in the same commit"
        )


def test_a_lesson_section_targets_equal_the_checkpoint_keys() -> None:
    """Both directions, byte-exact, expected value from the syllabus data."""
    lesson = parse_lesson(json.loads((FIXTURES / "specimen.json").read_text()))
    unit = next(u for u in units() if u.unit_number == lesson.unit_number)
    assert {s.target for s in lesson.sections} == set(unit.checkpoint["per_target"])
