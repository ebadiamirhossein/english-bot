"""W8f: both export parsers, against the two REAL files.

`tests/fixtures/vocab_import/` holds the actual exports, byte-for-byte, and
these tests read them rather than an inline string that describes them. That is
the whole point of the slice: known issue #27 sat unverified from S15a to W8f
precisely because a parser was written against a format described in prose and
never fed a real file.

The fixtures are Project Gutenberg (`gb_20203`, *Autobiography of Benjamin
Franklin*) — public domain, so PRODUCT-PRINCIPLES §3's "licensing is checked
before any third-party data enters the repo" is satisfied and the answer is
recorded here as well as in BUILD_PROGRESS.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from core.cards.exports import (
    LR_COLUMNS,
    CaptureRecord,
    detect_export_format,
    parse_export,
    parse_language_reactor,
    parse_trancy,
)

FIXTURES = Path(__file__).parent / "fixtures" / "vocab_import"
LR_FILE = FIXTURES / "languagereactor.csv"
TRANCY_FILE = FIXTURES / "trancy.csv"

LR_TEXT = LR_FILE.read_text(encoding="utf-8-sig")
TRANCY_TEXT = TRANCY_FILE.read_text(encoding="utf-8-sig")

#: W8b's census counted nine `vocabulary` chunks. These are them, in file order.
#: Hardcoded, never derived from the parser under test (CLAUDE.md §3 rule 5).
TRANCY_WORDS = [
    "tier",
    "notch",
    "luckily",
    "frustrate",
    "bootstrap",
    "proper",
    "incapable",
    "psychosis",
    "convenient",
]


# ── the shape of the real files ────────────────────────────────────────────


def test_the_language_reactor_export_has_two_records_of_24_columns() -> None:
    records = parse_language_reactor(LR_TEXT)
    assert len(records) == 2
    assert [r.lemma for r in records] == ["swain", "devour"]


def test_the_language_reactor_export_has_no_header_row() -> None:
    """The single fact that made #27 unfixable for eleven slices.

    `csv.DictReader` — what the v2 path uses — consumes record 0 as headers, so
    a two-record file becomes a one-record file with nonsense column names.
    """
    first = LR_TEXT.split("\n", 1)[0]
    assert first.startswith("WORD|swain|en"), "record 0 is DATA, not a header"


def test_the_trancy_export_is_the_nine_words_w8b_counted() -> None:
    assert [r.lemma for r in parse_trancy(TRANCY_TEXT)] == TRANCY_WORDS


def test_frustrate_is_in_the_file_that_s24a_recorded_as_skipping_it() -> None:
    """S24a's row reads `9 words -> 8 imported / 1 skipped (frustrate)`.

    The file has nine rows INCLUDING `frustrate`, the census counted nine
    `vocabulary` chunks, and `frustrate` is the back of card 32. All nine
    landed; the reply's count was wrong. The record is corrected at W8f and
    this test is what keeps the correction checkable.
    """
    assert "frustrate" in [r.lemma for r in parse_trancy(TRANCY_TEXT)]


def test_tiers_translation_is_byte_identical_to_what_s24a_imported() -> None:
    """The provenance claim: this fixture IS the file S24a imported.

    Asserted on the RAW CSV field, before any stripping, because the claim is
    about the file — leading space and doubled space included. The parsed
    record's gloss is stripped, which is a separate and deliberate choice; see
    `test_the_parsed_gloss_is_stripped`.
    """
    rows = list(csv.reader(io.StringIO(TRANCY_TEXT, newline="")))
    tier = next(r for r in rows if r[0] == "tier")
    assert tier[2] == " سطح ردیف;  چیدمان در سطوح طبقه‌بندی"


def test_the_parsed_gloss_is_stripped() -> None:
    tier = next(r for r in parse_trancy(TRANCY_TEXT) if r.lemma == "tier")
    assert tier.gloss == "سطح ردیف;  چیدمان در سطوح طبقه‌بندی"


# ── the things a naive line-splitter destroys ──────────────────────────────


def test_embedded_newlines_inside_quoted_fields_survive() -> None:
    """The wider-context column carries three lines inside one field.

    The file is ten physical lines and two records. A line-oriented reader sees
    ten rows, which is the third of the three reasons the v2 path cannot read it.
    """
    assert LR_TEXT.count("\n") == 10
    records = parse_language_reactor(LR_TEXT)
    assert len(records) == 2


def test_a_sentence_containing_real_quote_characters_round_trips() -> None:
    """`swain`'s sentence is a Milton quotation, so it CONTAINS quote marks.

    The doubled quotes in the file are CSV escaping of real characters, not a
    parser quirk to be stripped.
    """
    swain = parse_language_reactor(LR_TEXT)[0]
    assert swain.sentence is not None
    assert swain.sentence.startswith('"Unknown, and like esteemed')
    assert swain.sentence.endswith('clouted shoon;"')


def test_every_field_that_matters_is_read_off_the_real_row() -> None:
    devour = parse_language_reactor(LR_TEXT)[1]
    assert devour == CaptureRecord(
        lemma="devour",
        gloss="بلعیدن, خوردن, فرو بردن",
        source_format="language_reactor",
        sentence=(
            "We Americans devour eagerly any piece of writing that purports "
            "to tell us the secret of success in life;"
        ),
        phonetic=None,
        pos="Verb",
        target_language="fa",
        source_title="Autobiography of Benjamin Franklin",
        source_id="gb_20203",
        captured_at="2026-08-26 09:21",
        audio_filename="1787736112873.mp3",
    )


def test_the_audio_filename_is_carried_and_nothing_else_is_done_with_it() -> None:
    """The file IS in the export (`media/`), contrary to the slice prompt.

    Recorded, and nothing is built for it. Note for whoever does build it: in
    this very sample `1787736123635.mp3` is Ogg/Opus data, not MPEG — the
    extension lies about the container.
    """
    assert [r.audio_filename for r in parse_language_reactor(LR_TEXT)] == [
        "1787736123635.mp3",
        "1787736112873.mp3",
    ]


# ── detection ──────────────────────────────────────────────────────────────


def test_each_real_file_detects_as_exactly_one_format() -> None:
    assert detect_export_format(LR_TEXT) == "language_reactor"
    assert detect_export_format(TRANCY_TEXT) == "trancy"


def test_an_unrecognised_file_is_refused_rather_than_guessed() -> None:
    assert detect_export_format("a,b,c\n1,2,3\n") is None
    with pytest.raises(ValueError, match="refusing rather than guessing"):
        parse_export("a,b,c\n1,2,3\n")


def test_a_record_with_the_wrong_column_count_is_refused() -> None:
    """A partial import looks like a success; a refusal does not."""
    short = "WORD|x|en\tWord\tsentence\n"
    with pytest.raises(ValueError, match=f"expected {LR_COLUMNS}"):
        parse_language_reactor(short)


# ── the regression that closes #27, asserted in BOTH directions ────────────


def test_the_v2_path_still_refuses_the_real_export_and_the_new_one_accepts_it() -> None:
    """#27, measured instead of described — and it cannot silently reopen.

    Both halves are asserted on purpose. Only asserting that the new parser
    works would let someone re-point the importer at `classify_csv_format` and
    still see green; only asserting the v2 refusal would not prove the fix.

    `watch_import` is v2's engine, is untouched by W8f, and dies at W22. This
    test does not ask it to change — it pins what it does, so the reason W8f
    exists stays visible.
    """
    from core.services.watch_import import classify_csv_format, parse_csv_bytes

    headers, rows = parse_csv_bytes(LR_FILE.read_bytes())

    # Seven nonsense headers and nine phantom rows, from a 2-record file.
    assert len(headers) == 7
    assert len(rows) == 9
    assert classify_csv_format(headers) is None

    # The same bytes, read correctly.
    assert len(parse_language_reactor(LR_TEXT)) == 2


def test_the_v2_path_still_reads_trancy_because_that_half_always_worked() -> None:
    """#27's Trancy half was fixed at S24a. Only the LR half was broken."""
    from core.services.watch_import import classify_csv_format, parse_csv_bytes

    headers, rows = parse_csv_bytes(TRANCY_FILE.read_bytes())
    assert classify_csv_format(headers) == "vocabulary"
    assert len(rows) == 9
