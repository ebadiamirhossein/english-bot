"""The operator's slang gloss file: read strictly, or not at all.

**Why strictness matters more than convenience here.** A gloss file that
half-parses produces a deck where some slang cards carry a safe alternative and
some do not — and the ones that do not are exactly the rows nobody looked at.
PRD §8.5.4 calls a slang card without the neutral equivalent "useless and
slightly dangerous", so the failure mode of a lenient reader is shipping
precisely that, quietly. Every malformed input below is refused whole.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cards.slang_glosses import SlangGlossError, load, lookup

HEADER = "chunk\tneutral_equivalent\twho_says_this\n"
GOOD = HEADER + (
    "hard pass\tI'd rather not, thanks\tFriends and casual colleagues.\n"
    "no cap\thonestly\tFriends. Not in writing at work.\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "glosses.tsv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_well_formed_file_loads(tmp_path: Path) -> None:
    glosses = load(_write(tmp_path, GOOD))
    assert set(glosses) == {"hard pass", "no cap"}
    assert glosses["hard pass"].neutral_equivalent == "I'd rather not, thanks"


def test_lookup_normalises_both_sides(tmp_path: Path) -> None:
    """An apostrophe or a capital must not silently lose a row the operator
    did write — the symptom would be a skipped chunk with no explanation."""
    glosses = load(_write(tmp_path, GOOD))
    assert lookup(glosses, "Hard Pass") is not None
    assert lookup(glosses, "  hard   pass  ") is not None
    assert lookup(glosses, "soft pass") is None


def test_comments_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    text = "# W7 slang backfill, written 2026-08-25\n\n" + GOOD + "\n"
    assert len(load(_write(tmp_path, text))) == 2


def test_a_missing_header_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SlangGlossError, match="header"):
        load(_write(tmp_path, "hard pass\tI'd rather not\tFriends.\n"))


def test_a_row_with_the_wrong_number_of_fields_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SlangGlossError, match="3 tab-separated"):
        load(_write(tmp_path, HEADER + "hard pass\tI'd rather not\n"))


@pytest.mark.parametrize(
    "row",
    [
        "\tI'd rather not\tFriends.\n",
        "hard pass\t\tFriends.\n",
        "hard pass\tI'd rather not\t\n",
    ],
)
def test_an_empty_column_is_refused(tmp_path: Path, row: str) -> None:
    """A half-written row is the one that ships a card with no safe alternative."""
    with pytest.raises(SlangGlossError, match="required"):
        load(_write(tmp_path, HEADER + row))


def test_a_duplicate_chunk_is_refused(tmp_path: Path) -> None:
    """Two glosses for one phrase means one of them is silently discarded, and
    nobody would know which."""
    text = HEADER + "hard pass\tone\tFriends.\nHard  Pass\ttwo\tFriends.\n"
    with pytest.raises(SlangGlossError, match="duplicate"):
        load(_write(tmp_path, text))


def test_a_missing_file_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(SlangGlossError, match="no such file"):
        load(tmp_path / "not-here.tsv")


def test_an_empty_file_is_refused_rather_than_read_as_zero_glosses(
    tmp_path: Path,
) -> None:
    """`--slang-glosses` pointed at an empty file must not look like success:
    the outcome would be identical to not passing the flag at all, which on the
    2026-08-25 census is two learners with an empty deck."""
    with pytest.raises(SlangGlossError, match="no header"):
        load(_write(tmp_path, ""))


def test_a_header_only_file_loads_as_empty(tmp_path: Path) -> None:
    """Distinct from the empty file: the operator wrote the header and no rows,
    which is a deliberate state and reads as zero glosses."""
    assert load(_write(tmp_path, HEADER)) == {}
