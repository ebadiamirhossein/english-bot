"""The deck: card types, FSRS grades, caps, and the leech threshold.

The pure half of W7. `core.services.cards` holds every query and `fsrs.py` is
the only module in this repository permitted to `import fsrs` — the same split
`core.items` / `core.services.items` uses, and the same single-call-site rule
`core.llm` and `core.speech` follow. Duplicated construction drifts, and tests
cannot see the drift.

**A card is not an item.** An item is a validated exercise served from a bank
(W5, W10); a card is a phrase with a schedule attached. They share the 1–4 grade
scale because they are the same four buttons, and they share nothing else. In
particular no code path turns an `item_attempts` row into a card review — see
`tests/test_cards_service.py::test_no_path_converts_an_item_attempt_into_a_card_rating`,
which exists because `graded_by = 'self'` on an item attempt means "nothing
checked this", whereas a card rating is self-reported *by design*. Conflating
them would put a measurement and a self-assessment into one scheduler.
"""

from __future__ import annotations

from core.lexicon.states import REGISTERS

# PRD §5's card table, in order. Migration 013's CHECK is asserted against this
# tuple rather than maintained beside it.
#
# All five ship at 013, widened once — 012 §3's precedent for `errors.source`.
# W7 writes only `cloze` and `production`; the other three arrive with W13's
# capture (`recognition`, `audio`) and the collocation drills. A CHECK value
# with no writer is expected here and is not a defect to be tested away.
CARD_TYPES: tuple[str, ...] = (
    "recognition",
    "production",
    "cloze",
    "audio",
    "collocation",
)

#: What an ordinary v2 chunk becomes: ONE production card, and **never a cloze
#: one**. The fan-out is one constant rather than a shape implied by the loop
#: that builds it, so this is where the ruling is enforceable.
#:
#: **W8b removed `cloze` from this tuple, and it read `("cloze", "production")`
#: from W7 until 2026-08-25.** `probe_cloze --live` measured the 14 migrated
#: cloze cards on production: 6 multi-acceptable, **9 not answerable as
#: authored**, and exactly 2 sound on the uniqueness rule — both of which turned
#: out to be Work-track content, which §4 caps at 20%. The dominant cause is
#: structural rather than a bug: a v2 chunk is an idiom, so a chunk cloze gaps a
#: whole phrase, and a slot that swallows a phrase cannot be reconstructed from
#: the sentence around it. No cue repairs that and a gate at creation would
#: reject nearly all of them. See `core.cards.migrate_chunks` for the three
#: causes and `core.cards.retire_chunk_cloze` for the rows already created.
CHUNK_CARD_TYPES: tuple[str, ...] = ("production",)

#: What a `slang`-sourced v2 chunk becomes — ONE recognition card, and never a
#: cloze or a production one.
#:
#: PRD §8.5.2: "`slang` and `informal` cards are created as recognition and
#: listening cards only." A cloze card asks the learner to produce the phrase
#: into a gap, which is the thing the receptive-first rule exists to prevent, so
#: it is not a milder form of a production card — it is a production card with a
#: sentence around it. Migration 013's
#: `cards_receptive_first_until_the_neutral_is_mastered` bars all three.
SLANG_CHUNK_CARD_TYPES: tuple[str, ...] = ("recognition",)

#: Every card type this migration can create. The anti-join that makes the pass
#: idempotent reads this, not `CHUNK_CARD_TYPES` — a slang chunk's recognition
#: card must count as already-migrated on the second run, and a list that knew
#: about only one of the two would re-create it every time.
#:
#: `cloze` left this tuple with W8b, and dropping it is correct rather than
#: merely tidy: this is "what the pass can create", and an anti-join for a card
#: type the pass cannot create is asking the database a question about a row
#: nobody will write. W13's video cloze cards carry no `source_chunk_id`, which
#: `migrated_card_keys` filters on, so they are outside this set by construction.
MIGRATION_CARD_TYPES: tuple[str, ...] = CHUNK_CARD_TYPES + SLANG_CHUNK_CARD_TYPES

#: What ONE CAPTURED WORD becomes (W8f, and W13's transcript tap) — a
#: recognition card and a production card, and never a cloze one. It lives here
#: beside `CHUNK_CARD_TYPES` because this module is the single place a reader
#: looks for "what turns into what", and a fan-out defined next to the loop that
#: builds it is one nobody finds.
#:
#: **The absent `cloze` is NOT W8b's ruling repeated.** W8b removed the chunk
#: cloze because a v2 chunk is an idiom and a gap swallowing a whole phrase
#: cannot be reconstructed from what is left — an argument about phrases. A
#: single word sitting in a real sentence is exactly what cloze is for, and a
#: capture cloze would be a good card. The blocker is **#147**, still open:
#: `make_sentence_with_gap` replaces a SUBSTRING, not a whole word, so it gaps
#: *tier* out of *tiers* and strands the `s`. Building on it would inherit a
#: live defect onto every new card. Capture cloze lands at W13, with a
#: whole-word gapper beside it.
CAPTURE_CARD_TYPES: tuple[str, ...] = ("recognition", "production")

#: Card types that ask the learner to PRODUCE the phrase. Mirrors the DDL in
#: migration 013 so the two cannot drift, and a test asserts they agree.
PRODUCTIVE_CARD_TYPES: frozenset[str] = frozenset(
    {"production", "cloze", "collocation"}
)

# Mirrors `fsrs.State`, which is an IntEnum (Learning=1, Review=2,
# Relearning=3). Stored lowercase because every other CHECK in this schema is
# lowercase; `core.cards.fsrs` owns the translation in both directions and
# `tests/test_cards_fsrs.py` asserts the two sets correspond by name.
FSRS_STATES: tuple[str, ...] = ("learning", "review", "relearning")

# Mirrors `fsrs.Rating`: Again=1, Hard=2, Good=3, Easy=4. The integers are the
# library's, not ours — they travel into `card_reviews.rating` unchanged so a
# stored log can be replayed through the scheduler without a lookup table.
RATINGS: dict[str, int] = {"again": 1, "hard": 2, "good": 3, "easy": 4}
RATING_NAMES: dict[int, str] = {v: k for k, v in RATINGS.items()}

# How the register tag on a card was arrived at. `migration_default` is the
# honest label for every card W7 creates: v2 had no register concept, so
# `neutral` is a stated assumption and not an observation. Keeping the two
# distinguishable is the same move `user_lexemes.source = 'assumption'` makes
# for the frequency floor (#93) — a hypothesis stays findable in one WHERE.
# W8f adds `import_default`, and the reason is that the other three are all
# false of an import. 'migration_default' says "v2 had no register concept";
# 'detected' says a model looked; 'operator' says a human judged this row. W8f
# makes no model call and the operator ran a file, not a review. Migration 015
# widens the CHECK to match; `test_migration_015` asserts the two agree.
REGISTER_SOURCES: tuple[str, ...] = (
    "migration_default",
    "detected",
    "operator",
    "import_default",
)

#: The register a v2 chunk's card is tagged with, and it is a decision with a
#: cost rather than an omission. `neutral` is PRD §8.5.1's own default
#: ("anywhere — the default") and the safe direction: a neutral tag *permits*
#: production, which is correct for phrases v2 was already drilling
#: productively, whereas a wrong `slang` tag would bar a card from production
#: forever. The cost is that a genuinely informal phrase is now taught for
#: production; `register_source` is what makes those rows re-taggable at W13.
MIGRATION_DEFAULT_REGISTER = "neutral"

#: Registers that may never come from a `/prep` source. PRD §8.5.2: "`/prep` and
#: any work-context generation filters out `slang` and `taboo` entirely. A
#: client-call prep sheet must never suggest *that's a hard pass*."
#:
#: The prompt asks the model not to produce them (`core/prompts/prep.txt`); this
#: is the half that does not depend on a model complying. `/prep` dies at W22,
#: the deck does not, so the durable rule is "prep material never becomes a
#: slang card" rather than "the prep prompt behaved".
PREP_SOURCE_PREFIX = "prep_"
PREP_FORBIDDEN_REGISTERS: frozenset[str] = frozenset({"slang", "taboo"})

#: Registers that are receptive-only until the neutral equivalent is mastered
#: (PRD §8.5.2). `taboo` is not here because it is never productive at all,
#: which migration 013 holds with its own row-local CHECK.
RECEPTIVE_FIRST_REGISTERS: frozenset[str] = frozenset({"slang", "informal"})

#: The ledger state that satisfies "the neutral equivalent is mastered".
#: `core.lexicon.states.STATES` already defines the ladder and `mastered` is its
#: top rung; W7 does not invent a second notion of mastery beside it.
MASTERED_STATE = "mastered"

# PRD §5's two caps. Constants and not `users` columns, deliberately: a column
# would be an ALTER TABLE users, which drags #48's paired view recreate into a
# slice that otherwise needs none.
#
# PRODUCT-PRINCIPLES §3 flag, recorded at the moment of the choice: these are
# global configuration that would need to be per-user, exactly like
# `LEXICON_ASSUMED_KNOWN_TOP_N` (#94). They become columns at multi-tenancy.
DAILY_NEW_CARD_CAP = 12
DAILY_REVIEW_CAP = 80

# PRD §5: "leech at 6 lapses → card is rewritten with an easier cue, not
# suspended". The second half is why migration 013 has no `suspended` column.
LEECH_LAPSES = 6

# PRD §5: "hits a target retention rate (set 0.90)".
DESIRED_RETENTION = 0.90

__all__ = [
    "CARD_TYPES",
    "CHUNK_CARD_TYPES",
    "SLANG_CHUNK_CARD_TYPES",
    "MIGRATION_CARD_TYPES",
    "PRODUCTIVE_CARD_TYPES",
    "FSRS_STATES",
    "RATINGS",
    "RATING_NAMES",
    "REGISTERS",
    "REGISTER_SOURCES",
    "MIGRATION_DEFAULT_REGISTER",
    "CAPTURE_CARD_TYPES",
    "PREP_SOURCE_PREFIX",
    "PREP_FORBIDDEN_REGISTERS",
    "RECEPTIVE_FIRST_REGISTERS",
    "MASTERED_STATE",
    "DAILY_NEW_CARD_CAP",
    "DAILY_REVIEW_CAP",
    "LEECH_LAPSES",
    "DESIRED_RETENTION",
]
