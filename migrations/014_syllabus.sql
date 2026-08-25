-- W8: the 24-week road as data -- `syllabus_units`, `syllabus_unit_lexemes`,
-- `user_unit_state`. PRD §3 and §2.3.
--
-- Plain, non-idempotent DDL, per 009's note, 010's, 012's and 013's:
-- core.db.migrate wraps each file in one transaction and gates it on
-- schema_version, which is what makes a re-run impossible. Guards would only
-- buy the impression that a re-run is safe. This file writes NO schema_version
-- row -- the runner does that (core/db.py), and only 001 inserts one itself.
--
-- NOTHING IS SEEDED HERE, following 010 and 013. The 24 units and their ~1,440
-- candidate lexemes arrive from `python -m core.syllabus.seed`, which reads
-- `data/syllabus_units.json` and `data/syllabus_lexemes.tsv`. Three reasons,
-- all of them W4's and W7's: a migration is not a content pipeline; content
-- that will be CORRECTED wants a re-runnable path, and a syllabus will be
-- corrected; and "run it twice, the second run writes nothing" is not a
-- testable criterion for a file schema_version physically cannot run twice.
--
-- THIS FILE SHIPS THREE TABLES WHERE `docs/TASKS-v3-web.md`'s authoritative
-- migration table names two. The third, `syllabus_unit_lexemes`, is recorded as
-- a departure rather than slipped in. The reason is the acceptance criterion
-- "every target lexeme resolves to a real `lexemes` row": as a child table with
-- a foreign key that is a SCHEMA FACT, unbreakable by a bad seed. As an
-- INTEGER[] column on `syllabus_units` -- the two-table shape -- it could carry
-- no foreign key at all, and the guarantee would degrade to something a test
-- asserts after the fact. The migration table is authoritative about NUMBERING;
-- this is an addition inside 014.
--
-- #48 IS NOT TRIGGERED. There is no ALTER TABLE users in this file, so the
-- paired `CREATE OR REPLACE VIEW approved_onboarded_users` is not required and
-- is deliberately absent. Stated rather than omitted silently: #48 has recurred
-- because each case looked like the one where the rule did not apply.
--
-- PRODUCT-PRINCIPLES §2 position, which every slice adding a user-keyed table
-- must state: `user_unit_state` references `users(id)`, the identity 011
-- established. **It does not enlarge an identity migration** -- 011 shipped on
-- 2026-08-24, #92 is closed, and 012 and 013 both already use this pattern.
-- §2's own text still reads "Today the schema does not meet it", which has been
-- false since that date; the document is corrected in this commit.
--
-- PRODUCT-PRINCIPLES §3 position: the per-learner target list is COMPUTED, not
-- stored. See `syllabus_unit_lexemes` below.

-- ---------------------------------------------------------------
-- 1. syllabus_units -- 24 fixed rows, shared by every learner
-- ---------------------------------------------------------------
-- Natural primary key, deliberately unlike 010/012/013's surrogate identity
-- PKs. `items.unit_number` (012) already stores this value as a SMALLINT and
-- 012's cross-slice contract requires it to be UNIQUE here; the row set is
-- fixed at 24 by PRD §3. A surrogate id would be a second identifier for the
-- same fixed thing, and `items` would then point at the wrong one.
--
-- 012 wrote the contract this discharges:
--   "CROSS-SLICE CONTRACT: W8 must give `syllabus_units` a UNIQUE
--    `unit_number` and add the foreign key in 014. Written here because a
--    contract discovered at 014 is a contract broken at 014."
--
-- NOTHING IS STORED FOR PRD §3's "3 video/audio items at 95-98% coverage", and
-- that is a decision rather than an omission to infer from an absent column.
-- W12 owns migration 016 (`videos`, `video_assignments`). More than scheduling:
-- selection is by COMPUTED coverage against a learner's own ledger (PRD §7.2),
-- so the three items are per-learner and could not sit on a shared unit row at
-- all. A nullable `video_ids` here would be a promise this table cannot keep.
CREATE TABLE syllabus_units (
    unit_number         SMALLINT PRIMARY KEY
                            CHECK (unit_number BETWEEN 1 AND 24),

    -- PRD §3: "Each stage = 4 weekly units." Held as arithmetic rather than as
    -- a comment, so a unit cannot be filed under a stage it does not belong to.
    stage               SMALLINT NOT NULL CHECK (stage BETWEEN 1 AND 6),

    -- "one can-do statement ("I can describe a change I made and why")".
    can_do              TEXT NOT NULL CHECK (length(trim(can_do)) > 0),

    -- [{"target": "...", "murphy_units": "5-10"|null}, ...]
    --
    -- JSONB and not a fourth table, because a grammar target has nothing to key
    -- to: Murphy has no catalogue in this database. `error_types.murphy_units`
    -- (001) is the established convention -- a TEXT range, expanded in code by
    -- the S11 matcher -- and `book_units` is NOT a catalogue despite PRD §3
    -- saying so: it is a per-learner OCR study log whose `unit_number` is free
    -- TEXT in a different namespace from this table's SMALLINT. Corrected in
    -- `docs/PRD-v3-web.md` in this commit and filed as a known issue.
    --
    -- `murphy_units` is nullable PER TARGET. Stage 6 (units 21-24) has no
    -- Murphy range in PRD §3 at all -- its cluster is "collocation depth,
    -- idiom, connected speech, self-repair strategies, B2 exam task formats" --
    -- and `error_types` already stores NULL for six of nineteen types, among
    -- them `collocation`, `false_friend` and `register_formality`. So 20 of 24
    -- units carry a reference, the number is reported rather than smoothed
    -- over, and the acceptance bar is untouched: it is ">=3 grammar targets",
    -- which never required a reference.
    grammar_targets     JSONB NOT NULL,

    -- PRD §3: "1 output task (spoken and written variant)". Shipped although
    -- the W8 row's Build column omits it -- one sentence per unit, authored
    -- beside the can-do, and adding it later is an ALTER TABLE. 010 carried
    -- `user_lexemes.register` nullable and inert until W13 for this reason.
    output_task_spoken  TEXT NOT NULL CHECK (length(trim(output_task_spoken)) > 0),
    output_task_written TEXT NOT NULL CHECK (length(trim(output_task_written)) > 0),

    -- The checkpoint BLUEPRINT: what the 12 items must test, per grammar target
    -- and on lexemes, with the permitted item types and the pass mark.
    -- **It contains no item.** W8 authors none and writes no row to `items`:
    -- standing rule 4 forbids shipping an item that has not passed the
    -- validator, and an item authored here would carry a NULL
    -- `validator_version` -- exactly the population W10's version filter
    -- exists to exclude. `core.syllabus.blueprint` enforces the shape,
    -- including a check that the blocks sum to 12 and that no item-shaped key
    -- is present.
    checkpoint          JSONB NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT syllabus_units_stage_matches_unit
        CHECK (stage = ((unit_number - 1) / 4) + 1),

    -- PRD §3 says "3-5 grammar targets"; the W8 row says ">=3". The tighter of
    -- the two is enforced, here and in core.syllabus.blueprint.
    CONSTRAINT syllabus_units_three_to_five_grammar_targets
        CHECK (jsonb_typeof(grammar_targets) = 'array'
               AND jsonb_array_length(grammar_targets) BETWEEN 3 AND 5),

    -- Mirrored from core.syllabus.CHECKPOINT_ITEM_COUNT and
    -- CHECKPOINT_PASS_PCT; test_migration_014 compares the constraint against
    -- the constants the way test_migration_013 does for the card types.
    CONSTRAINT syllabus_units_checkpoint_is_twelve_at_eighty
        CHECK ((checkpoint ->> 'item_count')::INT = 12
               AND (checkpoint ->> 'pass_pct')::INT = 80)
);

-- ---------------------------------------------------------------
-- 2. syllabus_unit_lexemes -- the CANDIDATE set, shared, never per learner
-- ---------------------------------------------------------------
-- **There is deliberately NO user_id here, and that is the central design
-- decision of W8.**
--
-- PRD §3 asks for "~40 target lexemes chosen by frequency band n topic n *not
-- already in your known-word ledger*". That last clause is per learner; this
-- row is shared. The resolution:
--
--     target_lexemes(user, unit) = unit_candidates(unit) - known_lemmas(user)
--
-- computed at read time by `core.services.syllabus.unit_target_lexemes`, which
-- reuses `core.services.lexicon.known_lemmas`. Two learners on Unit 7 see
-- different words from the same row, which is what PRD §3 means by
-- "Personalisation, not deviation".
--
-- PRODUCT-PRINCIPLES §3 flag, recorded at the moment of the choice as W7 did
-- for the daily caps: storing this per learner would be user x unit x lexeme --
-- textbook "data that scales per-user x per-lemma ... if it materialises rows
-- that could be computed" -- and #93 is that same flag already standing against
-- W4's frequency floor. It would also go stale the instant a card review
-- promotes a word.
--
-- ON DELETE RESTRICT on lexemes, following 013's `cards.lexeme_id`: lexemes are
-- never deleted, and that is made a schema fact rather than a habit. ON DELETE
-- CASCADE on the unit, because a unit that no longer exists has no candidates.
CREATE TABLE syllabus_unit_lexemes (
    unit_number SMALLINT NOT NULL
                    REFERENCES syllabus_units(unit_number) ON DELETE CASCADE,
    lexeme_id   INTEGER  NOT NULL
                    REFERENCES lexemes(id) ON DELETE RESTRICT,
    PRIMARY KEY (unit_number, lexeme_id)
);

-- The reverse direction: "which unit teaches this word?", which W10 asks per
-- generated item and W13 asks on a tap.
CREATE INDEX idx_syllabus_unit_lexemes_lexeme
    ON syllabus_unit_lexemes (lexeme_id);

-- ---------------------------------------------------------------
-- 3. user_unit_state -- user x unit (PRD §2.3)
-- ---------------------------------------------------------------
-- `locked` IS DELIBERATELY ABSENT FROM THE CHECK. PRD §2.3 names five states;
-- four are storable. `locked` is the ABSENCE OF A ROW, never a stored value,
-- and leaving it out of the CHECK is what makes that unforgeable.
--
-- This mirrors 010's treatment of `unknown` in `user_lexemes` exactly, and the
-- reason carries over: a row means "this learner has REACHED this unit".
-- Materialising the negative would give every learner 23 rows of "not yet"
-- with a fake `entered_at`, turn every advance into an UPDATE, and stop "how
-- many units has this learner started" being COUNT(*).
--
-- W9 renders a locked unit from `syllabus_units LEFT JOIN user_unit_state`,
-- which it must do anyway to show all 24 with the learner's dot on one. What
-- UNLOCKS a unit is undefined in the PRD and needs no data: unit N is available
-- when N = 1 or unit N-1 is `passed`, derivable entirely from this table.
--
-- NO WRITER IN W8. W9, W10 and W11 write the first row. This is 013's situation
-- stated up front -- three of five `card_type` values shipped with no writer
-- for months -- and it is NOT to be fixed with an "every state has a writer"
-- test, which would fail by design the day it was written.
--
-- Mirrored from core.syllabus.states.UNIT_STATES; test_migration_014 compares
-- the CHECK against the constant.
CREATE TABLE user_unit_state (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit_number SMALLINT NOT NULL
                    REFERENCES syllabus_units(unit_number) ON DELETE RESTRICT,

    state       TEXT NOT NULL CHECK (state IN
                    ('available', 'in_progress', 'passed', 'mastered')),

    entered_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- The checkpoint pass, and the clock mastery is measured from.
    passed_at   TIMESTAMPTZ,
    -- The retention confirmation, >= 21 days after the pass.
    mastered_at TIMESTAMPTZ,

    -- PRD §3's failure path: "the unit stays `in_progress` ... and you retake
    -- in 4 days." Both facts are stored, because a retake date recomputed from
    -- `updated_at` would move every time anything else on the row changed.
    checkpoint_attempts   SMALLINT NOT NULL DEFAULT 0
                              CHECK (checkpoint_attempts >= 0),
    last_checkpoint_score SMALLINT
                              CHECK (last_checkpoint_score IS NULL
                                     OR last_checkpoint_score BETWEEN 0 AND 100),
    retake_due_on         DATE,

    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One row per learner per unit. The idempotency key for every writer.
    UNIQUE (user_id, unit_number),

    -- 80 is core.syllabus.CHECKPOINT_PASS_PCT. A `passed` row that cannot say
    -- which score passed is a claim with no evidence behind it.
    CONSTRAINT user_unit_state_a_pass_needs_the_threshold
        CHECK (state NOT IN ('passed', 'mastered')
               OR (passed_at IS NOT NULL
                   AND last_checkpoint_score IS NOT NULL
                   AND last_checkpoint_score >= 80)),

    -- PRD §2.3: "Mastery requires a checkpoint pass **plus** retained
    -- performance 3+ weeks later." 21 days is core.syllabus
    -- .MASTERY_RETENTION_DAYS.
    --
    -- **THIS COMPARES TWO STORED COLUMNS AND NEVER NOW().** A CHECK containing
    -- NOW() is not immutable: the row's validity would depend on when it is
    -- read, and every test touching it would fail on a calendar boundary rather
    -- than on a code change. That is CLAUDE.md §3 rule 6 -- the rule
    -- `test_vocabulary_due_and_anki` broke once already, and the one W7 made
    -- load-bearing by testing FSRS due dates with an injected clock. The clock
    -- is read exactly ONCE, in the service function that writes `mastered_at`.
    --
    -- What "retained performance" MEANS is undefined in the PRD and is NOT
    -- invented here: 014 supplies the interval and the two timestamps it is
    -- measured between, and W11 -- which owns checkpoints -- supplies the
    -- metric. Filed as a known issue.
    CONSTRAINT user_unit_state_mastery_needs_a_pass_and_three_weeks
        CHECK (state <> 'mastered'
               OR (passed_at IS NOT NULL
                   AND mastered_at IS NOT NULL
                   AND mastered_at >= passed_at + INTERVAL '21 days')),

    -- A timestamp that exists without the state it evidences is a row that
    -- disagrees with itself. The converse direction is covered above.
    CONSTRAINT user_unit_state_timestamps_match_the_state
        CHECK ((mastered_at IS NULL OR state = 'mastered')
               AND (passed_at IS NULL OR state IN ('passed', 'mastered')))
);

-- "Where is this learner on the map?" -- W9's only query.
CREATE INDEX idx_user_unit_state_user ON user_unit_state (user_id, unit_number);

-- ---------------------------------------------------------------
-- 4. The 012 cross-slice contract, discharged
-- ---------------------------------------------------------------
-- `items.unit_number` has been a SMALLINT with a range CHECK and no referent
-- since 012. It now has one.
--
-- NOT VALID, and the reason is ordering. `syllabus_units` is EMPTY when this
-- file commits -- the content arrives from the seed, which runs after
-- `migrate`. A plain FK would therefore have to validate against an empty
-- parent, and would fail on any database holding an `items` row with a non-null
-- `unit_number`. Production's `items` count is 0 (#109 closed with that
-- evidence), but the Mac dev database carries fixtures, and a migration that
-- depends on a precondition nobody checked is the shape of a bad night.
--
-- NOT VALID still enforces on EVERY NEW ROW, which is all W10 needs; it only
-- skips the scan of existing ones. `python -m core.syllabus.seed` runs
-- VALIDATE CONSTRAINT as its last step, once the 24 rows exist, and reports the
-- result -- because a NOT VALID constraint nobody ever validates is a silent
-- hole, and naming the validation as an acceptance criterion is what stops this
-- becoming one.
--
-- ON DELETE RESTRICT: the 24 units are fixed data. If one is ever deleted while
-- items point at it, that is a mistake to refuse rather than to cascade.
ALTER TABLE items
    ADD CONSTRAINT items_unit_number_fkey
    FOREIGN KEY (unit_number) REFERENCES syllabus_units(unit_number)
    ON DELETE RESTRICT
    NOT VALID;
