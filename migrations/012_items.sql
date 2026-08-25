-- W5: the unit of practice — `items`, `item_attempts`, and the v3 error sources.
--
-- Plain, non-idempotent DDL, per 009's note: core.db.migrate wraps each file in
-- one transaction and gates it on schema_version, which is what makes a re-run
-- impossible. Guards would only buy the impression that a re-run is safe.
--
-- NOTHING IS SEEDED HERE. W5 defines the shape and proves the validator;
-- filling the table is a later slice. Items are generated per learner by
-- W10's `assign_daily`, overnight, and only after passing every gate in
-- `core.items`.
--
-- #48 IS triggered by this file, unlike 010's. Section 4 runs an
-- `ALTER TABLE users`, so the paired `CREATE OR REPLACE VIEW
-- approved_onboarded_users` is at section 5, in this same file. A DEFAULT
-- change does not alter the view's frozen column list, so the recreate is not
-- strictly required — and that reasoning is exactly what let #48 recur twice.
-- Three idempotent lines, no judgement call left on the table.

-- ---------------------------------------------------------------
-- 1. items — one row per learner, never a shared library
-- ---------------------------------------------------------------
-- Fan-out, and it is not the S24 trade-off repeated blindly. An item is not
-- shareable BY CONSTRUCTION: PRD §3 says the content inside a unit is generated
-- against your error profile, your interests and your known-word ledger, so an
-- item built from `errors.id` 47 means nothing to the other learner. The
-- coverage gate is per-learner too, which makes VALIDITY ITSELF user-scoped —
-- the same sentence can be inside one learner's comprehensible band and outside
-- the other's. A shared row would therefore need a per-user validation record,
-- which is a delivery table with extra steps, and the shared row would hold
-- nothing but a string.
--
-- PRODUCT-PRINCIPLES §3, flagged rather than skipped: this materialises rows
-- per learner. It does not trip §3's first bullet (data that could be
-- computed) because items are generated per learner and cannot be recomputed.
-- The real note points the other way — a FIXED AUTHORED BANK DOES NOT GO HERE.
-- PRD §6 requires the placement instrument not to change, and W18's
-- `placement_bank` (019) is the shape that takes. W5 must not blur into it.
-- If multi-tenancy later wants a shared library it arrives as its own table
-- plus one nullable FK; `content_hash` is the key such a migration would need,
-- which is why it exists from day one.
CREATE TABLE items (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Mirrored from core.items.ITEM_TYPES; test_migration_012 compares the
    -- CHECK against the constant, the way test_migration_010 does for states
    -- and sources. PRD §4 names exactly these eleven and gives no others.
    item_type         TEXT NOT NULL CHECK (item_type IN (
                          'mcq', 'cloze_cued', 'word_bank_order', 'error_spot',
                          'l1_to_l2_production', 'dictation', 'listening_gap',
                          'speak_repeat', 'speak_answer', 'match_pairs',
                          'collocation_pick')),

    -- NOT NULL is load-bearing, not tidiness. PRD §4.6 rule 2 bans domain
    -- jargon *unless the item's track is Work*, so the rule is conditional on
    -- this column: a NULL track would silently skip the jargon gate and the
    -- slice's own acceptance criterion would stop being enforceable. The
    -- production corpus demonstrates the failure mode — 24 of 29 surviving
    -- `chunks` carry a NULL track, so 83% of them would have skipped it.
    -- Values match `chunks.track` (001) rather than inventing a second spelling.
    track             TEXT NOT NULL CHECK (track IN ('work', 'life', 'curiosity')),

    -- PRD §8.5.1 names `items` explicitly, alongside `cards` and
    -- `user_lexemes`. NOT NULL here, unlike `user_lexemes.register`: 010
    -- carried that one nullable and inert because W13 writes it later, whereas
    -- the generator sets this one in the same call that writes the item. There
    -- is no inert period, so there is no reason to permit an untagged row —
    -- "Nothing enters the deck untagged" (§8.5.1).
    register          TEXT NOT NULL DEFAULT 'neutral' CHECK (register IN (
                          'formal', 'neutral', 'informal', 'slang', 'taboo')),

    -- The learner-visible stem. Out of `payload` because three separate things
    -- operate on it: the naturalness gate, the blind-solver projection, and
    -- `content_hash`.
    prompt_text       TEXT NOT NULL,

    -- Canonical answer in display form; see the present-iff CHECK below.
    answer            TEXT,

    -- Stored ALREADY NORMALISED, so grading is `= ANY()` rather than a loop of
    -- folds at grade time, and so the blind-solver gate and the grader cannot
    -- drift into two different notions of "same answer". TEXT[] and not JSONB:
    -- it is a flat list of strings and `ANY` is a plain operator.
    accepted_variants TEXT[] NOT NULL DEFAULT '{}',

    -- Exactly PRD §4.3's five repair cues. NULL means no repair was needed.
    -- A column and not a payload key because "which cue does the generator keep
    -- needing" is the metric that tells you the generator prompt is wrong.
    cue_type          TEXT CHECK (cue_type IS NULL OR cue_type IN (
                          'first_letter_length', 'l1_gloss', 'definition',
                          'word_bank', 'converted_mcq')),

    -- The repair cap as a SCHEMA fact rather than a Python constant. §4.3 ends
    -- "if a repaired item still fails the blind-solver gate, it is discarded",
    -- and an uncapped retry loop is a cost leak that bills per item. If a later
    -- slice loosens the loop, the INSERT fails instead of the loop running on.
    repair_count      SMALLINT NOT NULL DEFAULT 0
                          CHECK (repair_count BETWEEN 0 AND 2),

    -- Target lexeme. A foreign key and never a string, for the same reason
    -- `user_lexemes` is keyed on `lexeme_id`: "items targeting words this
    -- learner does not know yet" is a join, not a text match. ON DELETE
    -- RESTRICT because 010's rule is that lexemes are never deleted — RESTRICT
    -- makes that a schema fact instead of a comment. A target outside the seed
    -- list is created by `ensure_lexeme` with a NULL `freq_rank`, and 010's
    -- convention holds: NULL rank means "rarer than the seed tail", not
    -- "missing".
    lexeme_id         INTEGER REFERENCES lexemes(id) ON DELETE RESTRICT,

    -- Grammar target, for PRD §4.3 gate 3 and W11's missed-target re-queue.
    error_type        TEXT REFERENCES error_types(code),

    -- The journal row this item drills. SET NULL and not CASCADE: an attempt on
    -- this item stays valid evidence about the learner even if the error row is
    -- resolved away. The error journal is the product; the attempt history is
    -- how we know whether the journal is being worked off.
    error_id          BIGINT REFERENCES errors(id) ON DELETE SET NULL,

    -- NOT `unit_id`. `syllabus_units` does not exist until 014, and PRD §3's
    -- 24-unit sequence is fixed data, so the number is stable and needs no
    -- table to point at.
    --
    -- CROSS-SLICE CONTRACT: W8 must give `syllabus_units` a UNIQUE
    -- `unit_number` and add the foreign key in 014. Written here because a
    -- contract discovered at 014 is a contract broken at 014.
    unit_number       SMALLINT CHECK (unit_number IS NULL OR
                                      unit_number BETWEEN 1 AND 24),

    -- PRD §5: the sentence it came from. Mirrors `cards.source_chunk_id` at 013.
    source_chunk_id   BIGINT REFERENCES chunks(id) ON DELETE SET NULL,

    -- Type-specific shape: options, tiles, bank tokens, the pair mapping, cue
    -- text, explanation, Murphy reference, audio text. One JSONB rather than
    -- eleven tables (W6 and W10 would need an 11-way UNION to render one
    -- session) and rather than thirty typed columns (~70% NULL, and the bank
    -- and the mapping are JSON either way). The keys are declared once in
    -- `core.items.schema` and validated on write by a discriminated union.
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- THE STORED VALIDATION RECORD (PRD §4.3: "items are cached with their
    -- validation record"). No DEFAULT, deliberately: the absence of a default
    -- is what makes "no item reaches a learner without a validation record" a
    -- schema fact rather than a convention someone can forget.
    validation        JSONB NOT NULL,

    -- Mirrors core.items.VALIDATOR_VERSION. When a later slice tightens a gate
    -- this is the only way to know which of the accumulated bank was validated
    -- under the old rules. It cannot be retrofitted: rows written before the
    -- column existed would all have to be guessed at.
    validator_version SMALLINT NOT NULL,

    -- settings.llm_model at validation time. A validated bank outlives the
    -- model that validated it.
    model             TEXT NOT NULL,

    validated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- sha256 over item_type, the folded prompt_text and a per-type
    -- discriminator (core.items.schema.hash_contribution). See the UNIQUE below.
    content_hash      TEXT NOT NULL,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- §4.3's freshness instruction lives in a generator prompt, and a prompt
    -- does not bind. This does.
    UNIQUE (user_id, content_hash),

    -- The target of item_attempts' composite foreign key. Redundant against the
    -- primary key on its own; it exists so the denormalised `user_id` on the
    -- attempt cannot disagree with the item's.
    UNIQUE (id, user_id),

    -- Exactly two of the eleven types have no single canonical answer string:
    -- `speak_answer` is open production scored against a rubric, and
    -- `match_pairs`' answer is a bijection that lives in `payload`. Written as
    -- an equality rather than two ORs so both exceptions are documented in the
    -- schema, and so a twelfth item type cannot be added without someone
    -- deciding which side it falls on.
    CONSTRAINT items_answer_present_iff_type_has_one CHECK (
        (answer IS NOT NULL) =
        (item_type NOT IN ('speak_answer', 'match_pairs'))
    ),

    -- PRD §4.3 gate 3 in DDL. An item with no declared target can never have
    -- "the gap tests the unit's target" verified by anything, ever.
    CONSTRAINT items_declares_a_target CHECK (
        lexeme_id IS NOT NULL OR error_type IS NOT NULL OR unit_number IS NOT NULL
    ),

    -- Without this, '{}'::jsonb satisfies NOT NULL and the acceptance criterion
    -- is a lie. The three keys are the three gates.
    CONSTRAINT items_validation_records_every_gate CHECK (
        validation ? 'deterministic'
        AND validation ? 'naturalness'
        AND validation ? 'blind_solver'
    ),

    -- PRD §8.5.1: taboo is "receptive only — never taught for production".
    -- Row-local, so a CHECK can hold it. The `slang` half of the rule —
    -- productive only once the neutral equivalent is mastered — depends on
    -- ledger state that a CHECK cannot see, so it stays a service rule with a
    -- test. The split is stated rather than fudged.
    CONSTRAINT items_taboo_is_never_productive CHECK (
        register <> 'taboo' OR
        item_type NOT IN ('l1_to_l2_production', 'speak_answer', 'speak_repeat')
    )
);

CREATE INDEX idx_items_type ON items (user_id, item_type);
CREATE INDEX idx_items_unit ON items (user_id, unit_number);
CREATE INDEX idx_items_lexeme ON items (lexeme_id);
CREATE INDEX idx_items_error ON items (error_id);

-- No `status` column, and rejected items are NOT stored. A
-- `status IN ('ready','rejected')` would put a filter in every consumer's WHERE
-- clause, and a filter everyone must remember is a filter someone forgets —
-- which here means a rejected item reaching a learner. The validator returns a
-- ValidationReport and the caller decides; nothing that failed a gate is
-- written at all.

-- ---------------------------------------------------------------
-- 2. item_attempts — what actually happened, captured once
-- ---------------------------------------------------------------
-- This table records the response, the latency, the cue on screen and the
-- distractor chosen — not correct/incorrect only. Adding a column at 013 or 015
-- is one line; the months of history between 012 and that slice are gone
-- permanently, and that history is exactly what seeds FSRS. Several columns
-- below therefore ship with no reader yet, on purpose, and that is the reason.
CREATE TABLE item_attempts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    item_id         BIGINT NOT NULL,

    -- Denormalised from `items`. Every W7 / W10 / W19 read is "this learner's
    -- attempts in a window", and going through `items` puts a join on all of
    -- them. The composite FK below is what makes the denormalisation
    -- unforgeable rather than merely conventional — the same move
    -- `user_lexemes_source_rank_agrees` makes for rank: prove the agreement,
    -- do not trust it.
    --
    -- `users.id` since 011 (#92). A foreign key to `telegram_user_id` here
    -- would re-open that issue two days after it closed, and
    -- tests/test_identity_boundary.py does NOT scan migrations/ — it walks
    -- packages/core, apps/bot and apps/api only. Nothing in the suite would
    -- have caught it, which is why test_migration_012 asserts the FK target
    -- read back out of pg_constraint.
    user_id         BIGINT NOT NULL,
    FOREIGN KEY (item_id, user_id)
        REFERENCES items (id, user_id) ON DELETE CASCADE,

    -- Nullable: an attempt can happen outside a session — rescue quiz, free
    -- practice. W10 needs it for `block_breakdown`.
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,

    attempted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- VERBATIM, unnormalised. Storing only the folded form destroys the
    -- evidence W7's leech rewrite needs — "what did they actually type" cannot
    -- be recovered from "did it match".
    response_text   TEXT,

    -- Structured response: the submitted permutation, the pair mapping, the
    -- tapped tile index.
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Promoted out of payload for `mcq` / `collocation_pick` / `error_spot`.
    -- "Which distractor pulls people" is the most actionable generator-quality
    -- signal there is, it is asked across item types, and it cannot be
    -- reconstructed after the fact from a boolean.
    chosen_option   TEXT,

    -- PRD §3: the checkpoint is 80% of *correct*.
    correct         BOOLEAN NOT NULL,

    -- FSRS Again / Hard / Good / Easy. The column ships at 012 so the history
    -- in between is not blank where FSRS most needs it.
    --
    -- CORRECTED AT W7, 2026-08-25: this comment read "W7 fills it", and W7 does
    -- not. W7's four-button UI reviews CARDS, and its grades land in
    -- `card_reviews.rating` (migration 013). Cards and items are different
    -- objects with different schedulers: a card carries FSRS state, an item is
    -- a validated exercise served from a bank. No item attempt reaches a
    -- scheduler at W7, so a `grade` written here would be a number with no
    -- consumer — and deriving one from the `correct` boolean is exactly what W6
    -- refused, because a made-up number is worse than a blank one.
    --
    -- **W10 is the writer.** Its Review block delivers a due card INSIDE a
    -- session, which is the first moment an attempt and a review genuinely
    -- coincide. Until then this column stays NULL, deliberately.
    grade           SMALLINT CHECK (grade IS NULL OR grade BETWEEN 1 AND 4),

    -- Render → submit. Not derivable from timestamps later.
    -- `core.lexicon.states` already argues that `learning` is precisely the
    -- state where a learner cannot retrieve at speed; that distinction is
    -- invisible without this column.
    latency_ms      INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),

    -- Which cue was ON SCREEN AT THIS ATTEMPT. `items.cue_type` is the item's
    -- CURRENT state, and W7's leech rule rewrites an item "with an easier cue,
    -- not suspended" — the moment that happens, every past attempt silently
    -- re-reads as if it had carried the new cue. Unrecoverable retrofit.
    cue_shown       TEXT CHECK (cue_shown IS NULL OR cue_shown IN (
                        'first_letter_length', 'l1_gloss', 'definition',
                        'word_bank', 'converted_mcq')),

    -- Separates "solved with a cue offered" from "solved after asking for one".
    hint_used       BOOLEAN NOT NULL DEFAULT FALSE,

    -- W6 gives instant feedback and may allow one retry.
    attempt_no      SMALLINT NOT NULL DEFAULT 1 CHECK (attempt_no >= 1),

    -- Typed items grade by string match; `speak_answer` and free production
    -- need a rubric; a learner may self-mark. Without this column an accuracy
    -- number silently mixes three instruments, and W19's progress line stops
    -- being comparable over time — the same argument PRD §6 makes for keeping
    -- the placement instrument fixed.
    graded_by       TEXT NOT NULL CHECK (graded_by IN (
                        'deterministic', 'model', 'self')),

    -- Rubric output when graded_by = 'model'.
    model_feedback  JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- For `speak_*` and `dictation`. THE AUDIO ITSELF IS DISCARDED — CLAUDE.md
    -- §5: transcribed or scored in-request, never written to disk. Only the
    -- duration survives, for W19's effort-weighted XP. Pronunciation scores
    -- belong to W14's `speech_attempts` (018), which adds its own FK then;
    -- pre-empting that shape here would create the duplication W5 exists to
    -- avoid.
    audio_seconds   REAL CHECK (audio_seconds IS NULL OR audio_seconds >= 0)
);

CREATE INDEX idx_item_attempts_user ON item_attempts (user_id, attempted_at DESC);
CREATE INDEX idx_item_attempts_item ON item_attempts (item_id);
CREATE INDEX idx_item_attempts_session ON item_attempts (session_id);

-- No UNIQUE (item_id, attempt_no): an item is legitimately re-delivered later
-- under spacing, and `session_id` is nullable, so a composite unique would be
-- weakest exactly where it would matter.

-- ---------------------------------------------------------------
-- 3. errors.source — widened ONCE for the full v3 set
-- ---------------------------------------------------------------
-- Six new values, per the authoritative table in docs/TASKS-v3-web.md. Widening
-- once is deliberate: 008 widened for a single value and this would otherwise
-- be five more migrations, each one a chance to get the CHECK re-add wrong.
--
-- Five of the six have no writer for months. That is expected and is NOT to be
-- fixed with a "every CHECK value has a writer" test — such a test would fail
-- by design from the day it was written.
--
-- WHAT EACH VALUE MEANS FOR THE W4 HARVEST ALLOW-LIST, decided here rather than
-- left to the slice that first writes one. W4's axis is: did the learner TYPE
-- it, or did a recogniser GUESS it?
--
--   answer      harvested      keyboard-authored free written answer; `text`'s class
--   retell      harvested      keyboard-authored written retell; `text`'s class
--   item        NOT harvested  covers typed AND ASR-graded item responses under
--                              one value. Harvesting it would let a
--                              `speak_answer` mishearing promote a word to
--                              `known` — permanent damage, where a missing
--                              harvest is recoverable. W5 ships
--                              core.items.RESPONSE_MODE so W6/W7 can split
--                              typed from spoken with the trichotomy in hand.
--   shadow      NOT harvested  ASR. `voice`'s class.
--   video       NOT harvested  the source line is someone else's English.
--                              `capture`'s class.
--   placement   NOT harvested  PRD §6 requires the instrument not to change.
--                              Harvesting from it feeds the measurement back
--                              into the thing being measured.
--
-- The classification is machine-checked: core.lexicon.states carries
-- HARVESTED_SOURCES / NOT_HARVESTED_SOURCES, core.services.lexicon reads the
-- frozenset instead of an inline list, and a test asserts every value in this
-- CHECK falls in exactly one of them.
ALTER TABLE errors DROP CONSTRAINT IF EXISTS errors_source_check;
ALTER TABLE errors ADD CONSTRAINT errors_source_check
    CHECK (source IN (
        'quiz', 'voice', 'text', 'reading', 'diary', 'capture', 'conversation',
        'shadow', 'retell', 'answer', 'item', 'placement', 'video'
    ));

-- ---------------------------------------------------------------
-- 4. users.track_weights — the v3 default, existing rows untouched
-- ---------------------------------------------------------------
-- PRD §4.6: Life 50 / Curiosity 30 / Work 20, replacing v2's Work 40 / Life 40 /
-- Curiosity 20. This was the loudest product complaint about v2 and #56 names
-- the schema default as one of its four sources.
--
-- ONLY the default. Existing rows keep whatever the learner chose — §4.6 says
-- the mix is adjustable in settings, so rewriting a learner's chosen weights
-- would be a silent product change made by a migration, which is the worst
-- place to make one.
ALTER TABLE users ALTER COLUMN track_weights
    SET DEFAULT '{"life": 50, "curiosity": 30, "work": 20}'::jsonb;

-- ---------------------------------------------------------------
-- 5. The paired view recreate (#48)
-- ---------------------------------------------------------------
-- `approved_onboarded_users` is `SELECT u.*` and freezes its column list at
-- creation time. Section 4 is an ALTER TABLE users, so TASKS' rule fires:
-- every ALTER TABLE users is paired with a view recreate in the same .sql file.
--
-- A DEFAULT change adds no column, so this recreate is a no-op today. It is
-- here anyway. #48 has recurred because each individual case looked like the
-- one where the rule did not need to apply, and a rule with a judgement call
-- attached is not a rule. Identical to 011's definition, joining on u.id.
CREATE OR REPLACE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.user_id = u.id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';
