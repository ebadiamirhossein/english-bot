-- W14 (Speaking I -- shadow + score): `speech_attempts`.
--
-- Plain, non-idempotent DDL, per 009's note and every file since: core.db.migrate
-- wraps each file in one transaction and gates it on schema_version, which is
-- what makes a re-run impossible. This file writes NO schema_version row.
--
-- NOTHING IS SEEDED HERE AND THIS MIGRATION COSTS NOTHING. Rows arrive from a
-- learner speaking, one row per scored attempt. **Azure pronunciation
-- assessment is on the Free (F0) tier: the call is free, so unlike 023 no row
-- in this table represents a purchase.** The risk this table guards is a
-- QUOTA, not money -- see `audio_seconds` below.
--
-- ---------------------------------------------------------------
-- #185, TENTH OCCURRENCE ON THE *TAKEN AT IMPLEMENTATION TIME* COUNTING.
-- THE NUMBER IS TAKEN IN THIS COMMIT, AND IT SHIFTS NOTHING.
-- ---------------------------------------------------------------
-- 023 is the highest applied version; production is at schema_version 23, and
-- `migrations/` on disk runs 001..023 with no gaps. **Read, not assumed**:
-- `ls migrations/` and the host's own `core.db status`.
--
-- **WHICH COUNTING THIS IS, stated because #185 requires whoever next takes a
-- number to say:** on the *taken at implementation time* counting -- the one
-- these headers use -- 017 was fourth, 018 fifth, 019 sixth, 020 seventh, 021
-- eighth, 022 ninth and 023 tenth, so this is the ELEVENTH. On the *only takes
-- that SHIFTED an unwritten row* counting, 022 does not count and 023 was the
-- ninth, so this is the TENTH -- and **this take shifts nothing either**,
-- because both halves of docs/TASKS-v3-web.md ALREADY read 024 for W14 and 025
-- for W18, corrected on 2026-09-02 when W13-ii took 023. **Both countings are
-- stated; #185 stays open on which it means.**
--
-- **NO ROW BELOW W14 MOVES AND NO BUILD COLUMN IS EDITED IN THIS COMMIT.**
-- Verified before the file was written: the authoritative table at
-- docs/TASKS-v3-web.md:132 reads `| 024 | W14 | speech_attempts |` and :133
-- reads `| 025 | W18 | placement_bank, placement_runs |`. Renumbering an
-- APPLIED migration is #49; there is nothing here to renumber.
--
-- ---------------------------------------------------------------
-- PRODUCT-PRINCIPLES §2 -- STATED BECAUSE EVERY SLICE ADDING A USER-KEYED
-- TABLE MUST STATE ITS POSITION.
-- ---------------------------------------------------------------
-- `user_id` keys on **users(id)**, the surrogate identity migration 011
-- established. No Telegram id, and no new dependency on one. This table
-- neither depends on nor enlarges the identity work 011 did.
--
-- ---------------------------------------------------------------
-- THERE IS NO `transcript` COLUMN, AND THE ABSENCE IS THE PRIVACY RULE MADE
-- STRUCTURAL RATHER THAN DOCUMENTED.
-- ---------------------------------------------------------------
-- Azure's response carries a recognised transcript of what the learner said.
-- **It is discarded in-request, never persisted, never logged.** CLAUDE.md §5:
-- audio is transcribed or scored and discarded; a speech-recognition
-- mishearing is the machine's guess at a learner's voice and has no business
-- surviving the request. `docs/ARCHITECTURE-v3-web.md:133` already says of this
-- table: *"scores only -- never audio, never transcripts of the diary"*.
--
-- **A COLUMN THAT EXISTED WOULD EVENTUALLY BE FILLED**, which is why the rule
-- is expressed as an absent column rather than as a convention a later writer
-- can be unaware of. `tests/test_speech_attempts_shape.py` asserts from
-- `information_schema` that no column here can hold one.
--
-- ---------------------------------------------------------------
-- `reference_text` IS THE REFERENCE, NEVER THE RECOGNITION.
-- ---------------------------------------------------------------
-- What the app ASKED the learner to say -- the card's own sentence -- and never
-- what Azure heard. It denormalises `cards.context_sentence` deliberately: a
-- score is uninterpretable without the sentence it scored, and `card_id` is
-- ON DELETE SET NULL so the measurement survives the card being deleted.
--
-- ---------------------------------------------------------------
-- `phonemes` IS JSONB AND NOT A SECOND TABLE -- PRODUCT-PRINCIPLES §3 FLAG,
-- MADE AT THE MOMENT THE CHOICE IS MADE AND NOT LATER.
-- ---------------------------------------------------------------
-- §3 flags *data that scales per-user x per-lemma (or similar products) if it
-- materialises rows that could be computed*, and a phoneme-observation table
-- is exactly that shape. W17 -- the only reason this accumulates -- reads it
-- with a GROUP BY over `jsonb_array_elements`; at ~2,400 observations a week
-- for two learners (~125k/year) that is a sub-second scan with no index.
--
-- **IF W17 MEASURES OTHERWISE, A MATERIALISED TABLE IS A MIGRATION WITH A
-- BACKFILL FROM THESE SAME ROWS -- the JSONB loses nothing.** That is what
-- makes deferring it cheap rather than lazy. W7's `/audio` no-cache flag
-- (#106) is the standing precedent for recording the flag at the choice.
--
-- ---------------------------------------------------------------
-- NO `ALTER TABLE users`, SO #48's PAIRED VIEW RECREATE DOES NOT FIRE.
-- ---------------------------------------------------------------
-- This file creates one table and touches no existing one. Checked rather than
-- assumed: `approved_onboarded_users` is untouched.

CREATE TABLE speech_attempts (
    -- BIGINT GENERATED ALWAYS AS IDENTITY, not BIGSERIAL. **The approved plan
    -- said BIGSERIAL and the tree disagreed; the tree wins and the
    -- disagreement was reported before this file was written.** Every table
    -- since 011 uses this form (013_cards.sql:42, 001:104), and a lone
    -- BIGSERIAL would leave one sequence in the schema owned differently from
    -- every other.
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- **NULLABLE, AND IT IS §1e's WHOLE MECHANISM.** A shadow attempt made
    -- inside the daily session carries its sitting, which gives block 4 the
    -- first `session_id`-linked log it has ever had -- the shape `card_reviews`
    -- gives block 1 and `video_assignments.completed_at` gives block 2.
    --
    -- **IT DOES NOT BY ITSELF MAKE `output` REACH `done`, AND THAT IS CHECKED
    -- RATHER THAN ASSUMED (#361).** `_derive_done`'s `output` clause is about
    -- the WRITTEN task -- `POST /correct` records no `session_id` -- and marking
    -- the block done off a shadow log while the written task sits unanswered
    -- would claim a learner completed work they did not do, which is the
    -- collapse `BLOCK_STATES` forbids. Nullable also because a shadow attempt
    -- outside a sitting is possible and is not a defect.
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,

    -- ON DELETE SET NULL: see `reference_text` above. The measurement outlives
    -- the card, because it is evidence about the learner and not about the card.
    card_id         BIGINT REFERENCES cards(id) ON DELETE SET NULL,

    -- **ONE VALUE WIDE, DELIBERATELY, AND W15 WIDENS IT.** The move 012 §3 made
    -- for `errors.source`. It is what stops a retell or answer attempt landing
    -- in this table untagged before W15 has decided what those scores mean.
    surface         TEXT NOT NULL CHECK (surface IN ('shadow')),

    reference_text  TEXT NOT NULL CHECK (length(btrim(reference_text)) > 0),

    -- Azure's four aggregates, 0-100. **PERSISTED AND NOT RENDERED** (§2.6):
    -- PRD §7.3 asks for per-word colouring, and PRD §8 asks for these to be
    -- PERSISTED -- its stated payoff is W17's weak-spot surface, not a number
    -- on the attempt screen. A number on a person's voice is the shape
    -- CLAUDE.md §4 bans.
    accuracy        REAL NOT NULL CHECK (accuracy     BETWEEN 0 AND 100),
    fluency         REAL NOT NULL CHECK (fluency      BETWEEN 0 AND 100),
    completeness    REAL NOT NULL CHECK (completeness BETWEEN 0 AND 100),
    pron_score      REAL NOT NULL CHECK (pron_score   BETWEEN 0 AND 100),

    -- **NULLABLE AND NULL. The EUR0.264/hr prosody add-on is NOT BOUGHT.** The
    -- column exists because PRD §8 names prosody and a later purchase should
    -- not need DDL. **NULL means NOT MEASURED, never zero** -- #330's shape,
    -- the same distinction `_capture_source_ref` makes between an absent
    -- suffix and `@0.000`.
    prosody         REAL CHECK (prosody IS NULL OR prosody BETWEEN 0 AND 100),

    -- Our normalised shapes, not Azure's raw ones:
    --   words    [{"word": str, "accuracy": num, "error_type": str}]
    --   phonemes [{"phoneme": str, "accuracy": num}]     <- W17 reads this
    -- Arrays, asserted as arrays: a JSONB object here would still be valid
    -- JSONB and would break W17's `jsonb_array_elements` at read time instead
    -- of at write time.
    words           JSONB NOT NULL CHECK (jsonb_typeof(words)    = 'array'),
    phonemes        JSONB NOT NULL CHECK (jsonb_typeof(phonemes) = 'array'),

    -- **THE QUOTA LEDGER, AND IT IS COMPUTED FROM OUR OWN BYTES.**
    -- `len(pcm) / (sample_rate * 2)`, never from anything Azure returns --
    -- CLAUDE.md §3 rule 5: an expected value derived from the thing under test
    -- proves nothing, and a quota guard that trusts the provider's own
    -- accounting cannot detect the provider disagreeing.
    --
    -- **F0 IS 5 AUDIO HOURS PER MONTH. #320/#321 DO NOT CARRY OVER** -- the call
    -- is free, so there is no cost model to under-report; the risk is a quota,
    -- countable in seconds we produced ourselves. The soft ceiling lives in the
    -- service, not here, because it is a product rule and not a data integrity
    -- one.
    audio_seconds   REAL NOT NULL CHECK (audio_seconds >= 0),

    provider        TEXT NOT NULL CHECK (length(btrim(provider)) > 0),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

    -- **NO UNIQUE. Repeated attempts on the same card are the feature**, not a
    -- duplicate to be refused: v2's shadow gave one retry and the ladder is
    -- built on saying a line again.
);

-- W17's read path: every attempt for one learner, newest first. The monthly
-- quota sum uses the same index.
CREATE INDEX idx_speech_attempts_user_created
    ON speech_attempts (user_id, created_at DESC);
