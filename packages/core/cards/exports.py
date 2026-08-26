"""W8f: the two vocabulary export formats, parsed from real files.

**Pure.** No database, no clock, no network, no model. Every function here takes
text and returns `CaptureRecord`s. `core.services.cards` does the writing and
`core.cards.import_vocab` is the human-run command.

---

## Why this module exists beside `core.services.watch_import`

`watch_import` is v2's CSV engine and it dies with the bot at W22. It is not
touched. It is also, measurably, unable to read a real Language Reactor export —
which is the defect **known issue #27** has carried, unverified, since S15a, and
which this module closes with a number instead of a shrug:

    parse_csv_bytes + classify_csv_format, on the real LR export
      → 7 headers, 9 data rows, classify → None → the file is refused

    the actual file
      → 0 headers, 2 records, 24 tab-separated columns

Three independent reasons that path cannot work, all visible in the fixture:

1. **A Language Reactor export has NO HEADER ROW.** `csv.DictReader` therefore
   eats the first *record* as headers, and `is_language_reactor_headers` looks
   for a `Phrase` column that is not there and never was.
2. **It is TAB-separated**, and `watch_import` reads commas, so a single record
   comma-splits into seven fragments.
3. **Its context columns contain literal newlines inside quoted fields**, so a
   line-oriented reader sees ten physical lines where there are two records.

`tests/test_vocab_exports.py` asserts **both halves** — that the v2 path still
refuses the fixture and that this module accepts it — so #27 cannot silently
reopen by someone re-pointing the importer at the old detector.

## Detection is structural, never by header

The LR file has no headers to match on, so `detect_export_format` matches on the
**shape of the data**: tab-delimited, every record exactly `LR_COLUMNS` fields,
and field 0 matching `LR_ID`. Trancy keeps a header signature because it has one.

`classify_csv_format`'s own rule is kept exactly: collect the matches, and return
a format only when there is **exactly one**. Zero or several → `None`, never a
guess. A mis-detected file writes the wrong learner's language into a deck.

## What is deliberately not read

Two records is not a sample, and a field whose meaning cannot be established from
the file is left alone rather than given an invented semantics:

- **column 14** — `6` and `0`. A familiarity score and a byte offset look the
  same at n=2.
- **column 4** — identical to the lemma in both records, so "surface form" is a
  guess. `LR_LEMMA` (5) is read and `LR_SURFACE` is defined but unused, so the
  next person with a bigger export can tell the two apart without re-deriving
  which column was which.
- **columns 7, 12, 13, 20, 21, 22** — empty in every record.
- **`gb_` in column 15** — an unresolved provider prefix.

**Column 23 is the audio filename and nothing is built for it.** It is carried as
a string so the record is complete. Note for whoever does build it: the file *is*
in the export (in `media/`), and in the sample `1787736123635.mp3` is **Ogg/Opus
data, not MPEG** — the extension lies about the container, so do not trust it.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Literal

# ── Language Reactor ───────────────────────────────────────────────────────
#: Every record in a real export has exactly this many fields. Used as half of
#: the structural signature, so a future format change fails detection loudly
#: instead of silently mis-indexing every column after the one that moved.
LR_COLUMNS = 24

#: Field 0, e.g. `WORD|swain|en`. `PHRASE` is accepted because LR exports both
#: and the id is the only place the distinction is not guessed — column 1 also
#: carries it, but only `Word` has ever been seen, so the id is the safer half.
LR_ID = re.compile(r"^(WORD|PHRASE)\|.+\|[a-z]{2}$")

LR_SENTENCE = 2
LR_SURFACE = 4  # NOT READ — see the module docstring
LR_LEMMA = 5
LR_POS = 6
LR_GLOSS = 8
LR_SOURCE_LANG = 10
LR_TARGET_LANG = 11
LR_SOURCE_ID = 15
LR_SOURCE_TITLE = 16
LR_CAPTURED_AT = 17
LR_AUDIO = 23

# ── Trancy ─────────────────────────────────────────────────────────────────
#: Whole-header signature, never token presence — S24's rule, and the reason is
#: still live: token matching would let a Language Reactor file look like a
#: Trancy one and fan Persian glosses into a Lithuanian speaker's deck.
TRANCY_HEADERS = frozenset({"word", "phonetic", "translation", "date"})

ExportFormat = Literal["language_reactor", "trancy"]


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    """One captured word, in the shape `core.cards.capture` plans from.

    The same shape W13's transcript tap produces, which is the point: a row from
    a CSV and a word tapped in the player are the same event, so they are the
    same record and go through the same creator.

    `sentence` is `None` for Trancy, which carries no sentence and from which
    **none is generated** — that generator is the measured cause of the deck's
    50% work bias (#99). A card without a sentence is a smaller card, not a
    reason to invent one.
    """

    lemma: str
    gloss: str
    source_format: ExportFormat
    sentence: str | None = None
    phonetic: str | None = None
    pos: str | None = None
    target_language: str | None = None
    source_title: str | None = None
    source_id: str | None = None
    captured_at: str | None = None
    audio_filename: str | None = None


def _rows(text: str, delimiter: str) -> list[list[str]]:
    """A real CSV reader, so quoted fields with embedded newlines survive.

    `newline=""` on the StringIO is required and is not decoration: without it
    the module splits on newlines *before* the CSV reader sees them, which is
    the third of the three reasons the v2 path cannot read this file.
    """
    return [
        row
        for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        if row
    ]


def is_language_reactor(text: str) -> bool:
    """Structural signature: tab-delimited, 24 fields, and a well-formed id.

    All three, on **every** record. A file where one record has 24 fields and
    another 23 is a file this module does not understand, and saying so is
    better than importing the part that happened to line up.
    """
    rows = _rows(text, "\t")
    if not rows:
        return False
    return all(
        len(row) == LR_COLUMNS and LR_ID.match(row[0]) is not None for row in rows
    )


def is_trancy(text: str) -> bool:
    """Whole-header signature. The set must match exactly, not merely overlap."""
    rows = _rows(text, ",")
    if not rows:
        return False
    return {cell.strip().lower() for cell in rows[0]} == TRANCY_HEADERS


def detect_export_format(text: str) -> ExportFormat | None:
    """Exactly one match, or ``None``. Never a guess.

    `classify_csv_format`'s rule, kept deliberately: zero or several matches
    return `None` and the caller refuses the file. The cost of guessing wrong is
    a learner's deck filled with a language they do not read.
    """
    matches: list[ExportFormat] = []
    if is_language_reactor(text):
        matches.append("language_reactor")
    if is_trancy(text):
        matches.append("trancy")
    return matches[0] if len(matches) == 1 else None


def _clean(value: str | None) -> str | None:
    """Strip, and treat an empty field as absent.

    Six of the 24 LR columns are empty in every sample record, so "" and "not
    present" must not be two different things downstream.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_language_reactor(text: str) -> list[CaptureRecord]:
    """A real LR export → records. **No header row is expected or skipped.**

    Raises `ValueError` on a record that does not carry `LR_COLUMNS` fields,
    rather than reading past the end and silently producing a record whose gloss
    is actually its category. A partial import is worse than a refused one: the
    refusal is visible and the partial one looks like a success.
    """
    out: list[CaptureRecord] = []
    for index, row in enumerate(_rows(text, "\t")):
        if len(row) != LR_COLUMNS:
            raise ValueError(
                f"record {index}: {len(row)} fields, expected {LR_COLUMNS} — "
                "this is not a Language Reactor export this module understands"
            )
        lemma = _clean(row[LR_LEMMA])
        if lemma is None:
            raise ValueError(f"record {index}: no lemma in column {LR_LEMMA}")
        out.append(
            CaptureRecord(
                lemma=lemma,
                # The gloss is kept WHOLE here. Choosing one sense of three is
                # the card's business (`core.cards.capture`), not the parser's —
                # a parser that discards data makes a later re-choice a re-import.
                gloss=row[LR_GLOSS].strip(),
                source_format="language_reactor",
                sentence=_clean(row[LR_SENTENCE]),
                pos=_clean(row[LR_POS]),
                target_language=_clean(row[LR_TARGET_LANG]),
                source_title=_clean(row[LR_SOURCE_TITLE]),
                source_id=_clean(row[LR_SOURCE_ID]),
                captured_at=_clean(row[LR_CAPTURED_AT]),
                audio_filename=_clean(row[LR_AUDIO]),
            )
        )
    return out


def parse_trancy(text: str) -> list[CaptureRecord]:
    """A Trancy export → records. Header row, then `Word,Phonetic,Translation,Date`.

    `Date` is read as `captured_at`; it is a date with no time, and it is the
    only capture instant this format carries.

    **`sentence` stays `None`.** Trancy has no sentence column and cannot be
    configured to add one, which is exactly why S24a generated one — and that
    generator wrote the deploy-and-staging sentences #99 measures. Nothing here
    generates.
    """
    rows = _rows(text, ",")
    if not rows:
        return []
    header = [cell.strip().lower() for cell in rows[0]]
    index = {name: position for position, name in enumerate(header)}

    def cell(row: list[str], name: str) -> str | None:
        position = index.get(name)
        if position is None or position >= len(row):
            return None
        return _clean(row[position])

    out: list[CaptureRecord] = []
    for row in rows[1:]:
        lemma = cell(row, "word")
        translation = cell(row, "translation")
        if lemma is None or translation is None:
            # Counted by the caller as `skipped_no_gloss`; a row with no word or
            # no meaning has no card in it.
            continue
        out.append(
            CaptureRecord(
                lemma=lemma,
                gloss=translation,
                source_format="trancy",
                phonetic=cell(row, "phonetic"),
                captured_at=cell(row, "date"),
            )
        )
    return out


def parse_export(text: str) -> tuple[ExportFormat, list[CaptureRecord]]:
    """Detect, then parse. Raises `ValueError` when the format is not exactly one."""
    detected = detect_export_format(text)
    if detected is None:
        raise ValueError(
            "the file matches neither a Language Reactor export (tab-separated, "
            f"{LR_COLUMNS} columns, no header) nor a Trancy export "
            "(Word,Phonetic,Translation,Date) — refusing rather than guessing"
        )
    if detected == "language_reactor":
        return detected, parse_language_reactor(text)
    return detected, parse_trancy(text)
