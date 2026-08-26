"""W8f: one captured word → the cards it becomes. **Pure.**

No database, no clock beyond an injected `now`, no model call. The same split
`core.cards.migrate_chunks` uses and for the same reason (CLAUDE.md §3 rule 5):
the fan-out table is the thing most likely to be wrong, and it should be
testable without Postgres.

---

## This is the creator W13 reuses, and that is a design decision, not a hope

`docs/ARCHITECTURE-v3-web.md` §6 already routes card creation through
`POST /video/{id}/save-word`; PRD §7.3 has the player's *Add to deck* build cards
"with this exact sentence and timestamp"; and `migrations/013_cards.sql:88` says
of `lexeme_id`, in its own comment, *"W13's capture sets it."*

A row from a Language Reactor export and a word tapped in the transcript player
carry **identical inputs** — lemma, sentence, gloss, source title, captured-at.
They are the same event arriving through two doors. So there is one planner, and
W13 supplies a `CaptureRecord` from a transcript line instead of from a file.
Two creators would mean two fan-out tables, and the second one drifts.

## The fan-out: two cards, and NO CLOZE

`CAPTURE_CARD_TYPES` is `("recognition", "production")`.

**The missing cloze card is not W8b's ruling repeated.** W8b removed the chunk
cloze because a v2 chunk is an *idiom* and a gap that swallows a whole phrase
cannot be reconstructed from what is left — an argument about phrases, which does
not apply to a single word sitting in a real sentence. A capture cloze would be
a good card.

The blocker is **#147**, which is live: `make_sentence_with_gap` replaces a
*substring*, not a whole word, so it gaps *tier* out of *tiers* and strands the
`s`. Building capture cloze on it would inherit an open defect onto every new
card. Cloze arrives at W13 together with a whole-word gapper, and until then this
module does not import the broken one.

**The production card carries no context hint for the same reason** — the hint
*is* `make_sentence_with_gap`'s output. `migrate_chunks` already has a
`production_no_hint` bucket; this is that shape, deliberately.

## Register

`neutral` / `import_default`. There is no model call in this slice, so there is
no detection, and neither existing `register_source` value is true:
`migration_default` means "v2 had no register concept" and `operator` claims a
human judged this row. Migration 015 adds the fourth value so these rows are
findable in one `WHERE` when W13's register detection lands — the same move
`user_lexemes.source = 'assumption'` makes for the frequency floor (#93).

**The cost, stated:** a slang line captured from a series is tagged `neutral` and
becomes a production card. That is **#126** already, and TASKS W13's "register
detection on save" is where it is fixed.

## What does NOT filter here

**There is no frequency floor, and its absence is a ruling.** A capture is the
strongest statement of intent this system receives: the learner met the word, did
not know it, and looked it up. Rejecting `psychosis` (rank 14,342, from a
documentary) would be the app declining to teach a word its learner asked for.

And `freq_rank IS NULL` does not mean rare — `tier` and `bootstrap` are absent
from a 15,000-lemma OpenSubtitles-derived list, which is a fact about the list.
Migration 010's "NULL sorts last" is a **sorting** rule; using it to reject
silently upgrades *absent from our list* into *too rare to learn*.

`SKIP_TOO_RARE` is kept in `BUCKETS` and is **always zero**, and a test asserts
it. Two buckets here have no writer — see `SKIP_NO_SENTENCE` too — and that is
stated rather than left to be discovered, because an unexplained empty column
reads as a bug. A bucket reading zero on
every run records that the decision was made; a deleted bucket reads as one never
considered, and reinstating a floor later becomes plumbing instead of a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.cards import CAPTURE_CARD_TYPES
from core.cards.exports import CaptureRecord
from core.cards.fsrs import CardState, initial_state

#: PRD §8.5.1's own default, and the safe direction: `neutral` PERMITS
#: production, whereas a wrong `slang` tag would bar a card from production
#: forever behind `cards_receptive_first_until_the_neutral_is_mastered`.
CAPTURE_REGISTER = "neutral"

#: Migration 015's fourth `register_source`. See the docstring.
CAPTURE_REGISTER_SOURCE = "import_default"

#: LR gives senses comma-separated (`بلعیدن, خوردن, فرو بردن`); Trancy gives them
#: semicolon-separated with a part-of-speech prefix (`n. … ; v. …`). Per format,
#: because the formats genuinely differ — one splitter would have to guess.
SENSE_SEPARATOR: dict[str, str] = {"language_reactor": ",", "trancy": ";"}

# Row-level verdicts. Exactly one per row, so the accounting identity holds.
IMPORTED = "imported"
SKIP_ALREADY_KNOWN = "skipped_already_known"
SKIP_DUPLICATE = "skipped_duplicate"
SKIP_NO_GLOSS = "skipped_no_gloss"
#: Also always zero, and for a different reason than SKIP_TOO_RARE: a record
#: with no sentence is not refused, it degrades to the Trancy shape (see `_face`).
#: Kept so the report answers "what happened to the sentence-less rows?" with a
#: number rather than with silence.
SKIP_NO_SENTENCE = "skipped_no_sentence"
SKIP_TOO_RARE = "skipped_too_rare"

#: Every bucket a row can land in. `migrate_chunks`' accounting property: the
#: buckets must sum to the rows read, so "nothing was silently lost" is a
#: subtraction anyone can do rather than a claim the importer makes about itself.
BUCKETS: tuple[str, ...] = (
    IMPORTED,
    SKIP_ALREADY_KNOWN,
    SKIP_DUPLICATE,
    SKIP_NO_GLOSS,
    SKIP_NO_SENTENCE,
    SKIP_TOO_RARE,
)


@dataclass(frozen=True, slots=True)
class Plan:
    """What one row becomes: zero or more card specs, and exactly one bucket."""

    lemma: str
    cards: tuple[dict, ...]
    bucket: str


def first_sense(gloss: str, source_format: str) -> str:
    """The one sense that goes on the card face.

    A card front wants one gloss, not three. The full string is kept in
    `meaning`, so nothing is discarded and a later slice can re-choose without
    re-importing.

    **This rests on an assumption, filed as one:** that Language Reactor orders
    senses by relevance to the captured context. Two records cannot establish
    that, and the fallback if it is wrong is mild — the learner sees a valid but
    less apt sense, with the full list one column away.
    """
    separator = SENSE_SEPARATOR.get(source_format, ",")
    return gloss.split(separator)[0].strip() or gloss.strip()


def _face(record: CaptureRecord, card_type: str, sense: str) -> tuple[str, str]:
    """(front, back) for one card type. PRD §5's table.

    A Trancy record has no sentence, so its recognition card fronts the word
    itself with its phonetic — the smaller card the format can actually support.
    **No sentence is generated to fill the gap**; that generator is the measured
    cause of the deck's 50% work bias (#99).
    """
    if card_type == "recognition":
        if record.sentence:
            return record.sentence, sense
        front = record.lemma
        if record.phonetic:
            front = f"{record.lemma}  {record.phonetic}"
        return front, sense
    # production — the one PRD §5 calls "the one that matters": L1 → English.
    return sense, record.lemma


def plan_for_capture(
    record: CaptureRecord,
    *,
    now: datetime,
    known_lemmas: frozenset[str] = frozenset(),
    lemmas_with_a_card: frozenset[str] = frozenset(),
    lexeme_id: int | None = None,
) -> Plan:
    """One record → its cards, or the reason it produced none.

    `now` must be timezone-aware UTC — `core.cards.fsrs` refuses anything else,
    and it is right to: a scheduler that accepted a local offset would give a
    different answer in summer and winter.

    `known_lemmas` and `lemmas_with_a_card` are passed in rather than queried,
    which is what keeps this function pure and its table testable without a
    database. The caller reads them once per run, not once per row.

    The skip is **row-level**: any existing card for this lemma skips the whole
    row. A lemma that already has a production card does not gain a recognition
    card here — filed as a cost, because W13 owns whether a partially-carded word
    is topped up, and because the alternative turns a verification run into a
    nine-card write.
    """
    lemma = record.lemma.strip()
    folded = lemma.lower()

    if not record.gloss.strip():
        # No meaning is no card. The learner would see a word and a blank.
        return Plan(lemma, (), SKIP_NO_GLOSS)

    if folded in lemmas_with_a_card:
        return Plan(lemma, (), SKIP_DUPLICATE)

    if folded in known_lemmas:
        # `known` or `mastered` in the ledger. A word at `seen` or `learning`
        # falls through and is imported: having met a word and not yet learned
        # it is precisely the case a card exists for.
        return Plan(lemma, (), SKIP_ALREADY_KNOWN)

    sense = first_sense(record.gloss, record.source_format)
    state: CardState = initial_state(due=now)

    cards: list[dict] = []
    for card_type in CAPTURE_CARD_TYPES:
        front, back = _face(record, card_type, sense)
        cards.append(
            dict(
                card_type=card_type,
                front=front,
                back=back,
                # The full gloss, never the trimmed sense. `first_sense` chooses
                # what to SHOW; this keeps what was captured.
                meaning=record.gloss.strip(),
                context_sentence=record.sentence,
                source_ref=source_ref(record),
                source_title=record.source_title,
                captured_at=record.captured_at,
                lexeme_id=lexeme_id,
                register=CAPTURE_REGISTER,
                register_source=CAPTURE_REGISTER_SOURCE,
                state=state,
            )
        )

    return Plan(lemma, tuple(cards), IMPORTED)


def source_ref(record: CaptureRecord) -> str:
    """The provenance slug, in `chunks.source`'s shape.

    `cards.source_ref` is documented as "`chunks.source` verbatim", so a capture
    keeps that convention rather than inventing a second one the card face would
    have to learn. The readable title goes in `source_title` (migration 015),
    which is what the face should render; this stays a slug.

    Deliberately NOT prefixed `prep_` — `refuse_forbidden_prep_register` matches
    on that prefix, and a capture is not prep material.
    """
    parts = ["capture", record.source_format]
    if record.source_id:
        parts.append(record.source_id)
    return "_".join(parts)
