"""#282. The generator must not re-emit the malformed `-e`-final comparatives.

**Why this file exists rather than only the data assertion in
`test_lexicon_coverage.py`.** W12a corrected eleven rows in
`data/inflections.tsv` by hand. A corrected `.tsv` with an uncorrected
generator regenerates the bug the next time anybody runs
`scripts/build_lexicon.py`, and the data test would then go red *after* the
damage rather than before it. The data test guards the artefact; this one
guards the thing that produces it. Both are needed, and neither substitutes.

`scripts/` is not an installed package, so it is loaded by path. The test
imports the pure helper alone and never runs the builder: `getAllInflections`
needs `lemminflect`, which CLAUDE.md §2 makes build-only, and a test that
downloads or rebuilds the lexicon is not a test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "scripts" / "build_lexicon.py"


def _repair_silent_e():
    """The helper, loaded from the real file — never a copy of it."""
    spec = importlib.util.spec_from_file_location("_build_lexicon_under_test", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.repair_silent_e


@pytest.mark.parametrize(
    ("lemma", "raw", "expected"),
    [
        # The two the ruling named, and they are the two that cost real
        # resolutions: `free` is rank 455 and `blue` is rank 717.
        ("free", "freeer", "freer"),
        ("blue", "blueest", "bluest"),
        # The other four lemmas of the eleven bad rows.
        ("true", "trueer", "truer"),
        ("wee", "weeer", "weer"),
        ("eerie", "eerieest", "eeriest"),
        ("vague", "vagueer", "vaguer"),
    ],
)
def test_an_e_final_comparative_drops_the_e(lemma: str, raw: str, expected: str) -> None:
    """`lemminflect` appends; English drops. Written out, not asked of it."""
    assert _repair_silent_e()(raw, lemma) == expected


@pytest.mark.parametrize(
    ("lemma", "form"),
    [
        # Already correct out of `lemminflect` — the fault is per-lemma, which
        # is why only six lemmas were affected and why nobody noticed.
        ("nice", "nicer"),
        ("true", "truest"),
        # NOT an `-e`-final lemma: nothing to drop.
        ("big", "bigger"),
        ("happy", "happier"),
        # `-ed` and `-ing` are deliberately out of scope. Every one of these is
        # correct English, and the scan that found the bug listed them only
        # because it matched the SHAPE `lemma + suffix`. Repairing them would
        # move rows with no defect behind them.
        ("be", "being"),
        ("age", "ageing"),
        ("queue", "queueing"),
        ("binge", "bingeing"),
        ("tie", "tieing"),
        ("blue", "blued"),
    ],
)
def test_nothing_else_is_touched(lemma: str, form: str) -> None:
    assert _repair_silent_e()(form, lemma) == form
