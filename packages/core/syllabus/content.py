"""The single door to `data/syllabus_units.json` and `data/syllabus_lexemes.tsv`.

`core/lexicon/normalize.py` is the only module that may read the lexicon data
files, and the reason given there applies unchanged here: what drifts is the
PARSE, so one module reads the files and every other call site goes through it.
`tests/test_core_boundary.py` asserts it for both pairs.

Nothing here touches a database. `core/services/syllabus.py` resolves lemmas to
`lexemes.id` and writes rows; this module returns validated Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.syllabus import (
    CANDIDATE_CEFR,
    CANDIDATE_MIN_FREQ_RANK,
    UNIT_CANDIDATE_TARGET,
    UNIT_COUNT,
    stage_of,
)
from core.syllabus.blueprint import (
    ContentError,
    GrammarTarget,
    validate_checkpoint,
    validate_grammar_targets,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
UNITS_FILE = DATA_DIR / "syllabus_units.json"
LEXEMES_FILE = DATA_DIR / "syllabus_lexemes.tsv"


@dataclass(frozen=True, slots=True)
class Unit:
    unit_number: int
    stage: int
    can_do: str
    grammar_targets: tuple[GrammarTarget, ...]
    output_task_spoken: str
    output_task_written: str
    checkpoint: dict


@lru_cache(maxsize=1)
def units() -> tuple[Unit, ...]:
    """All 24 units, validated. Raises ContentError on anything unshippable."""
    raw = json.loads(UNITS_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ContentError("syllabus_units.json must be a list of units")
    if len(raw) != UNIT_COUNT:
        raise ContentError(f"{len(raw)} units in the file, PRD §3 requires {UNIT_COUNT}")

    out: list[Unit] = []
    for index, entry in enumerate(raw, start=1):
        number = entry.get("unit_number")
        if number != index:
            raise ContentError(
                f"units must be listed 1..{UNIT_COUNT} in order; position "
                f"{index} carries unit_number {number!r}"
            )
        targets = validate_grammar_targets(entry.get("grammar_targets"), unit_number=index)
        for field in ("can_do", "output_task_spoken", "output_task_written"):
            if not str(entry.get(field, "")).strip():
                raise ContentError(f"unit {index}: {field} is empty")
        out.append(
            Unit(
                unit_number=index,
                stage=stage_of(index),
                can_do=entry["can_do"].strip(),
                grammar_targets=targets,
                output_task_spoken=entry["output_task_spoken"].strip(),
                output_task_written=entry["output_task_written"].strip(),
                checkpoint=validate_checkpoint(
                    entry.get("checkpoint"), unit_number=index, targets=targets
                ),
            )
        )
    return tuple(out)


@lru_cache(maxsize=1)
def unit_lexemes() -> dict[int, tuple[str, ...]]:
    """unit_number -> its candidate lemmas, validated for size and uniqueness.

    The floor checked here is UNIT_CANDIDATE_TARGET (60), the CANDIDATE count --
    **not** TARGET_LEXEME_FLOOR (30), which is a per-learner number and can only
    be measured after the ledger diff. Confusing the two is how a shared file
    would come to be checked against a per-learner bar and pass for the wrong
    reason.
    """
    rows = _read_tsv(LEXEMES_FILE)
    by_unit: dict[int, list[str]] = {n: [] for n in range(1, UNIT_COUNT + 1)}
    seen: dict[str, int] = {}
    for line_no, row in enumerate(rows, start=1):
        if len(row) < 5:
            raise ContentError(f"syllabus_lexemes.tsv:{line_no}: expected 5 columns")
        lemma, unit_s, rank_s, _band, cefr = row[0], row[1], row[2], row[3], row[4]
        lemma = lemma.strip()
        unit = int(unit_s)
        if unit not in by_unit:
            raise ContentError(f"syllabus_lexemes.tsv:{line_no}: unit {unit} out of range")
        if lemma in seen:
            raise ContentError(
                f"syllabus_lexemes.tsv:{line_no}: {lemma!r} is already in unit "
                f"{seen[lemma]} -- a lemma belongs to one unit"
            )
        if cefr not in CANDIDATE_CEFR:
            raise ContentError(
                f"syllabus_lexemes.tsv:{line_no}: {lemma!r} is {cefr or 'untagged'}, "
                f"the pool is {'/'.join(CANDIDATE_CEFR)}"
            )
        if int(rank_s) <= CANDIDATE_MIN_FREQ_RANK:
            raise ContentError(
                f"syllabus_lexemes.tsv:{line_no}: {lemma!r} is rank {rank_s}, inside "
                f"the top-{CANDIDATE_MIN_FREQ_RANK} assumption floor -- every learner "
                "is assumed to know it, so it can never be a target"
            )
        seen[lemma] = unit
        by_unit[unit].append(lemma)

    short = {u: len(v) for u, v in by_unit.items() if len(v) < UNIT_CANDIDATE_TARGET}
    if short:
        raise ContentError(
            f"units below the {UNIT_CANDIDATE_TARGET}-candidate target: {short}. "
            "The bar is not lowered (CLAUDE.md §3 rule 7) -- report the number "
            "and widen the pool or re-run the tagger."
        )
    return {u: tuple(v) for u, v in by_unit.items()}


def _read_tsv(path: Path) -> list[list[str]]:
    """Comment lines, then one header row, then data -- `normalize.py`'s format."""
    rows: list[list[str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            rows.append(line.split("\t"))
    return rows[1:] if rows else []


__all__ = ["LEXEMES_FILE", "UNITS_FILE", "Unit", "unit_lexemes", "units"]
