"""The 24-week road (PRD §3) as data: stages, units, and what a unit ships with.

This package is the pure half of W8, the shape `core/lexicon/` and `core/items/`
already have: it turns the committed content files into validated structures
without touching a database. `core/services/syllabus.py` holds every query, which
is what keeps `tests/test_core_boundary.py::test_no_sql_outside_services`
unexempted -- known issue #59 stays the only exemption in this repository.

**PRD §3 gives six stages and one line: "Each stage = 4 weekly units."** The 24
units do not exist anywhere in the source documents, so W8 *authors* them rather
than transcribing them, exactly as W5 had to define eleven item shapes PRD named
and did not describe. That is the substance of this slice.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── the checkpoint, from PRD §3 and §4.2 ────────────────────────────────────
#
# "1 checkpoint (12 items, 80% to pass)". Both numbers are mirrored into
# migration 014's CHECK on `user_unit_state`, and `tests/test_migration_014.py`
# compares the constraint against these constants the way test_migration_013
# does for the card types. Two hand-maintained copies of a threshold is how a
# pass mark quietly stops meaning what the PRD says.
CHECKPOINT_ITEM_COUNT = 12
CHECKPOINT_PASS_PCT = 80

# PRD §2.3: "Mastery requires a checkpoint pass **plus** retained performance
# 3+ weeks later." Three weeks is the only number that sentence gives.
#
# **What "retained performance" MEANS is undefined in the PRD** -- no threshold,
# no metric, and `docs/ARCHITECTURE-v3-web.md` §5's `user_unit_state` row carries
# no column for a retention check. W8 supplies the interval and the two
# timestamps the interval is measured between; W11, which owns checkpoints,
# supplies the definition. Filed as a known issue rather than invented here,
# because a mastery rule guessed now would be indistinguishable from a specified
# one in six months.
MASTERY_RETENTION_DAYS = 21

# PRD §3's failure path: "the unit stays `in_progress`, the missed targets are
# injected into the next week's review queue, and **you retake in 4 days**."
#
# A constant rather than a literal in the writer, for `MASTERY_RETENTION_DAYS`'
# reason one line up: a number the PRD states is a number a test should be able
# to assert against its source.
CHECKPOINT_RETAKE_DAYS = 4

# ── target lexemes ──────────────────────────────────────────────────────────
#
# PRD §3 says "~40 target lexemes"; the W8 row says ">=30". They are not the
# same claim, and the difference is the whole design question of this slice:
# **the >=30 bar is measured AFTER the per-learner ledger diff, not before it.**
#
#     target_lexemes(user, unit) = unit_candidates(unit) - known_lemmas(user)
#
# A unit therefore carries a shared CANDIDATE set and the diff is computed at
# read time, never materialised -- `PRODUCT-PRINCIPLES.md` §3 asks for exactly
# that, and #93 is the same flag already standing against W4's frequency floor.
#
# Why 60 and not 40, which is what PRD §3 suggests. Measured, not assumed:
#
#   * the pool is 3,564 B1+B2 lemmas, of which 3,154 sit above `freq_rank` 2000
#     -- outside the assumption floor, so the floor removes none of them;
#   * TODAY the diff removes almost nothing. Post-#91 the heaviest learner has
#     2,003 covered lemmas and exactly THREE of them are above rank 2000. A
#     40-candidate unit would diff to ~40, pass, and measure nothing at all;
#   * BY MONTH SIX it removes a great deal. PRD §2.1 budgets 1,500-2,000 new
#     known words over the programme, landing in bands 3-6 -- precisely where
#     these units draw from. A learner who has acquired half the pool sees a
#     40-candidate unit fall to ~20 and fail the criterion SILENTLY, and fail it
#     for the learner who has used the app most.
#
# That last shape is #91's exactly: the more a learner uses the app, the worse
# the system serves them, invisibly.
#
# **65, and the number was raised from 60 by measurement rather than chosen.**
# A unit of N candidates tolerates (N - 30) / N of its own words becoming known
# before it drops below the floor. At 60 that is exactly 50%, and PRD §2.1's own
# vocabulary budget -- 1,500-2,000 new known words over the 24 weeks, against a
# 3,759-lemma candidate pool -- projects **40% to 53%** erosion by the end of the
# programme. So 60 held across most of the PRD's range and failed at the top of
# it: 2,000 new words leaves 28, and the last units a learner reaches are exactly
# the ones that have eroded longest.
#
# 65 raises the tolerance to 53.8% and covers the whole projected range. It is
# also the CEILING the content can support: stage 3 ("projects, travel,
# appointments, deadlines", the narrowest lexical field of the six) yields 263
# candidate lemmas, and four units at 65 need 260. Three words of headroom.
#
# The bar was not moved to fit the content (CLAUDE.md §3 rule 7). The content was
# widened -- A2 admitted to the pool, see CANDIDATE_CEFR -- and then the
# candidate count raised until the bar held.
TARGET_LEXEME_FLOOR = 30
UNIT_CANDIDATE_TARGET = 65

# The candidate pool's own definition, in one place because the build script,
# the seed and the tests must all mean the same thing by it.
#
# Two filters doing two different jobs:
#
#   `freq_rank > 2000` excludes what every learner is ASSUMED to know. It is the
#   exact complement of `assume_top_frequency_known`, so a word inside the floor
#   could never survive the per-learner diff and would inflate the shared count
#   while contributing nothing to the per-learner one.
#
#   a CEFR tag excludes PROPER NOUNS. `core.lexicon.normalize.cefr_tagged_lemmas`
#   exists for exactly this and its docstring gives the evidence: the frequency
#   list is lowercased, so `john` sits at rank 548 and `paris` at 1107, and
#   nothing but the CEFR tag distinguishes them from words.
#
# **A2 IS INCLUDED, and excluding it was a real error corrected at W8 by the
# shortfall gate firing.** The first pool was B1/B2 only, on the reasoning that
# the learners are B1 heading for B2. That conflates "this word is rated easy"
# with "this learner already knows it" -- which is precisely the conflation PRD
# §2.1 built the known-word ledger to avoid. An A2-tagged lemma at rank 3,500 is
# an uncommon word that happens to be simple in form; whether either learner has
# met it is a question the ledger answers per learner, not one the tag answers
# for both. Keeping it out threw away 605 legitimate candidates and left stage 3
# ("projects, travel, appointments, deadlines" -- the narrowest field of the six)
# 23 short of what its four units need.
#
# A1 stays out. A learner at B1 has A1 coverage by definition of being at B1, so
# the 208 A1 lemmas above the floor are the one group where the tag really does
# predict the ledger.
CANDIDATE_CEFR = ("A2", "B1", "B2")
CANDIDATE_MIN_FREQ_RANK = 2000

# ── Murphy references ───────────────────────────────────────────────────────
#
# `English Grammar in Use` has 145 units. Stored as TEXT ranges with no foreign
# key, which is the convention already in this repository:
# `error_types.murphy_units` (migration 001) holds `'69-81'` and `'5-6,11-14'`,
# and S11's range-expansion decision explains why they expand in code.
#
# **`book_units` is NOT the source, and PRD §3 says it is.** That table is a
# per-learner OCR study log (`user_id NOT NULL`, `unit_number TEXT`, free-form)
# recording "learner X photographed Murphy unit N on date D" -- roughly five
# units for one learner, deliberately left behind at the S18d re-onboard. It is
# a different namespace from `items.unit_number` (SMALLINT 1-24) despite the
# identical column name, and a shared syllabus row could not key to it in any
# case. The ranges below are authored from PRD §3's own table.
MURPHY_MAX_UNIT = 145

# ── the six stages, verbatim from PRD §3 ────────────────────────────────────
#
# Stage 6 carries NO Murphy range. That is not an omission here: PRD §3's cell
# reads "collocation depth, idiom, connected speech, self-repair strategies, B2
# exam task formats" and names no units. The repository already treats this as
# normal -- `error_types.murphy_units` is NULL for six of nineteen types, and
# they are `collocation`, `false_friend`, `register_formality`, both
# pronunciation types and `filler_overuse`. Collocation and idiom ARE Stage 6.
#
# So `murphy_units` is nullable per grammar target, 20 of 24 units carry one,
# and the acceptance bar is not lowered to accommodate it -- the bar is ">=3
# grammar targets", which never required a reference.
#
# Murphy unit 38 appears in BOTH stage 3 (29-38) and stage 5 (38-41). That is
# legal precisely because these are text ranges with no FK and no UNIQUE, and it
# is recorded here so that nobody later "tidies" it into a constraint.


@dataclass(frozen=True, slots=True)
class Stage:
    number: int
    title: str
    can_do: str
    lexical_field: str
    murphy_ranges: tuple[str, ...]


STAGES: tuple[Stage, ...] = (
    Stage(
        1,
        "Tell me what happened",
        "Tell a 2-minute story about something that happened to you, "
        "without freezing",
        "daily life, work routine, home, food, transport",
        ("5-20", "25-28"),
    ),
    Stage(
        2,
        "Describe and compare",
        "Compare two options and justify a choice out loud",
        "places, products, people, city life, apartments",
        ("72-79", "92-100"),
    ),
    Stage(
        3,
        "Plans and what-ifs",
        "Run a planning conversation: propose, hedge, commit, change plan",
        "projects, travel, appointments, deadlines",
        ("19-24", "29-38"),
    ),
    Stage(
        4,
        "Say what you think",
        "Hold a position for 2 minutes, disagree politely, concede a point",
        "opinions, news, arguments, culture",
        ("42-47", "48-52"),
    ),
    Stage(
        5,
        "Sound professional",
        "Run a client call and write a proposal email that doesn't read as "
        "translated",
        "marketing, pricing, negotiation, feedback, meetings",
        ("38-41", "137-145"),
    ),
    Stage(
        6,
        "Range and repair",
        "Speak for 4 minutes on an unprepared topic; self-correct mid-sentence",
        "everything; consolidation",
        (),
    ),
)

UNIT_COUNT = 24
UNITS_PER_STAGE = 4


def stage_of(unit_number: int) -> int:
    """PRD §3: "Each stage = 4 weekly units."

    Migration 014 carries the same arithmetic as a CHECK, so a unit cannot be
    stored under a stage it does not belong to.
    """
    if not 1 <= unit_number <= UNIT_COUNT:
        raise ValueError(f"unit_number out of range: {unit_number}")
    return (unit_number - 1) // UNITS_PER_STAGE + 1


__all__ = [
    "CANDIDATE_CEFR",
    "CANDIDATE_MIN_FREQ_RANK",
    "CHECKPOINT_ITEM_COUNT",
    "CHECKPOINT_PASS_PCT",
    "MASTERY_RETENTION_DAYS",
    "MURPHY_MAX_UNIT",
    "STAGES",
    "Stage",
    "TARGET_LEXEME_FLOOR",
    "UNIT_CANDIDATE_TARGET",
    "UNIT_COUNT",
    "UNITS_PER_STAGE",
    "stage_of",
]
