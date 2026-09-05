-- ============================================================================
-- 025 — W13b. The conversation surface.
--
-- **MIGRATION NUMBER: 025, READ FREE BEFORE IT WAS TAKEN.** `migrations/` ran
-- 001–024 with no gaps and the dev database reported `schema_version = 24`.
-- **025 IS WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, and W18 is
-- unwritten — nothing on disk, nothing applied — so **W18 SHIFTS 025 → 026 IN
-- BOTH HALVES OF `docs/TASKS-v3-web.md` IN THIS SAME COMMIT.** That is W4b's
-- recorded policy: take the next number, never one above everything claimed,
-- because a fresh database applies in ascending order and production applies by
-- set difference, and a file that skipped ahead would have to be correct against
-- two different parent schemas.
--
-- **#185's OCCURRENCE COUNT: THIS FILE USES THE *taken at implementation time*
-- COUNTING, ON WHICH THIS IS THE ELEVENTH.** On the *shifted an unwritten row*
-- counting it is the tenth. **The two do not reconcile and this file does not
-- resolve them** — #185 is open on which it means, and its own instruction is
-- that whoever takes a number says which counting they used. This one says.
--
-- ----------------------------------------------------------------------------
-- PRODUCT-PRINCIPLES §2 — the position this slice is required to state.
-- `conversations.user_id` references **`users(id)`**, the surrogate identity
-- migration 011 established. `telegram_user_id` is a nullable secondary and #92
-- is closed, so **this file adds a user-keyed table and enlarges no future
-- migration.** `conversation_turns` is user-keyed transitively through its
-- parent; `conversation_usage` keys on `users(id)` directly.
--
-- ----------------------------------------------------------------------------
-- **WHY `conversation_turns` IS A TABLE AND NOT `sessions.payload`.**
-- v2 put its transcript in `sessions.payload["messages"]` and **migration 016's
-- own header already refused that reuse** — *"it would make one column mean
-- seven things and each reader guess which."* #378 is what the JSONB shape
-- produces in practice: 8 sessions and 47 turns still on production in
-- September, written in August, because a blob has no deleter and nobody
-- notices. A table can be swept, counted and constrained. A payload key cannot.
--
-- **WHY `conversation_usage` IS MATERIALISED, WHICH IS THE ONE PLACE THIS SLICE
-- GOES AGAINST PRODUCT-PRINCIPLES §3's FIRST BULLET, DELIBERATELY.** §3 flags
-- rows that could be computed. These could not: the rows they would be computed
-- from are the turns, and **§2a destroys those on purpose.** A durable counter
-- and a deleted source are the same decision seen twice.
--
-- **NO COST COLUMN, AND THE ABSENCE IS THE RULE.** #321 measured a printed floor
-- under-reporting a real charge by ~4,900×, and its verdict is that the
-- estimator needs a different model rather than a correction. **A dollar figure
-- is not stored, computed or printed anywhere in this slice.** Tokens and
-- seconds are counted exactly; the charge is read from the provider console.
--
-- **NO `errors.source` WIDENING IS OWED.** `'conversation'` has been permitted
-- since migration 008 and 012 carried it into a thirteen-value CHECK. Verified
-- against the file rather than against the planning table, whose 012 row lists
-- six values and is an incomplete description of it.
--
-- **NO `speech_attempts.surface` WIDENING EITHER.** §8.6 question 3 is ruled
-- *neither scored nor shown*, so no conversation row is ever written there and
-- its CHECK stays one value wide. W15 is still the widener its own comment names.
-- ============================================================================


-- ---------------------------------------------------------------
-- 1. conversations — the durable half. Survives the turn delete.
-- ---------------------------------------------------------------
CREATE TABLE conversations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Nullable: a conversation opened from the home entry point belongs to no
    -- session. `ON DELETE SET NULL` for `item_attempts.session_id`'s reason —
    -- the conversation happened whether or not the session row survives.
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,

    -- **THE APP'S OWN ENGLISH, NOT THE LEARNER'S**, which is why it is kept
    -- when the turns are deleted. It is also load-bearing: PRD §8.6.1 says the
    -- topic ROTATES, and rotation cannot run against a history that was erased.
    topic_label     TEXT NOT NULL CHECK (length(btrim(topic_label)) > 0),

    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- What the expiry sweep reads. Bumped on every turn.
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- NULL means open. Set by the close-out, in the same transaction that
    -- writes the corrections and deletes the turns.
    closed_at       TIMESTAMPTZ,

    turns_learner   INTEGER NOT NULL DEFAULT 0 CHECK (turns_learner >= 0),
    turns_app       INTEGER NOT NULL DEFAULT 0 CHECK (turns_app     >= 0),

    -- §2c: ONE alternative, usable once. A column and not a boolean so the
    -- ceiling is arithmetic rather than a flag somebody can flip twice.
    alternatives_used SMALLINT NOT NULL DEFAULT 0
        CHECK (alternatives_used BETWEEN 0 AND 1)
);

-- The sweep's predicate and the rotation read, in one index.
CREATE INDEX idx_conversations_user_activity
    ON conversations (user_id, last_activity_at DESC);

-- **ONE OPEN CONVERSATION PER LEARNER.** Without this, a double-tap on the
-- opener creates two and the turn loop has two heads. 016's and 018's partial
-- UNIQUE are the precedent, and the reason is the same one 018 recorded: a
-- refetch must not create a second sitting.
CREATE UNIQUE INDEX conversations_one_open_per_user
    ON conversations (user_id) WHERE closed_at IS NULL;


-- ---------------------------------------------------------------
-- 2. conversation_turns — the EPHEMERAL half. This is what is deleted.
-- ---------------------------------------------------------------
--
-- **THE RETENTION RULE IS ENFORCED BY THREE DELETERS AND NONE OF THEM IS A
-- SCHEDULED JOB**, because `english-worker` is not installed (#69) and nothing
-- scheduled has ever fired on this host. A rule enforced by a worker that has
-- never run is a hope. The three: the close-out, an unconditional expiry sweep
-- at the top of every entry point, and the human-run `core.conversation.sweep`.
--
-- **`ON DELETE CASCADE` IS NOT ONE OF THE THREE.** Nothing deletes a
-- `conversations` row in normal operation; the cascade exists for a learner
-- deletion, where `users` cascades to `conversations` and must reach here too.
CREATE TABLE conversation_turns (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id BIGINT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,

    -- Order within the conversation. Explicit rather than derived from `id`,
    -- so a read does not depend on an identity sequence's allocation order.
    seq             INTEGER NOT NULL CHECK (seq >= 0),

    role            TEXT NOT NULL CHECK (role IN ('learner', 'app')),

    -- **NULL FOR AN APP TURN, AND THE CHECK ENFORCES THE PAIRING RATHER THAN
    -- TRUSTING THE WRITER.** `input_mode` is what G3 reads to decide whether a
    -- correction sourced from this turn may be journaled: `'voice'` means the
    -- content is Whisper's guess at speech, and §12.7 plus CLAUDE.md §5 forbid
    -- journaling an ASR mishearing. A nullable column with no CHECK would let
    -- an app turn arrive tagged `'typed'` and become a journal source.
    input_mode      TEXT CHECK (
                        (role = 'learner' AND input_mode IN ('typed', 'voice'))
                     OR (role = 'app'     AND input_mode IS NULL)
                    ),

    content         TEXT NOT NULL,

    -- **RECORDED, NEVER ENFORCED (§8.6 question 1, ruled SHIP AND RECORD).**
    -- Only an app turn carries a band: it is a property of what the app
    -- generated, and measuring the learner's own English against their own
    -- ledger would be a score on a person.
    coverage_band   TEXT CHECK (
                        coverage_band IS NULL
                     OR (role = 'app' AND coverage_band IN ('below','in','above'))
                    ),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (conversation_id, seq)
);

CREATE INDEX idx_conversation_turns_conversation
    ON conversation_turns (conversation_id, seq);


-- ---------------------------------------------------------------
-- 3. conversation_usage — per (user, local date). SURVIVES the delete.
-- ---------------------------------------------------------------
--
-- **PER-USER FROM DAY ONE, AND THAT IS THE EXPENSIVE HALF BOUGHT NOW.** A
-- global counter would be free today and a migration later — and it is also
-- WRONG today: with two learners it cannot answer *which of them*, which is the
-- only question the metering ruling asks.
--
-- **THE LINE THIS TABLE MAY NOT CROSS, AND IT DOES NOT BEND FOR ABUSE
-- DETECTION:** CLAUDE.md §5 — logs carry user ids and route names, never
-- message bodies; PRD §12.8 — the operator panel shows activity, never content.
-- **Turns, seconds, tokens and call counts are metrics. What was said is not.**
-- Every column here is an integer or a float. `tests/test_conversation_metering.py`
-- asserts that against `information_schema`, so a TEXT column added later fails
-- the commit rather than the review.
CREATE TABLE conversation_usage (
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- The learner's LOCAL date, computed server-side from their timezone the
    -- way `local_today` already does it. A cap that rolled at UTC midnight
    -- would cut a learner off mid-evening in Vilnius.
    local_date        DATE NOT NULL,

    turns_learner     INTEGER NOT NULL DEFAULT 0 CHECK (turns_learner     >= 0),
    turns_app         INTEGER NOT NULL DEFAULT 0 CHECK (turns_app         >= 0),
    llm_calls         INTEGER NOT NULL DEFAULT 0 CHECK (llm_calls         >= 0),

    -- BIGINT because input tokens are quadratic in turn count: the history is
    -- re-sent every turn, so a 30-turn day is not 30× a 1-turn day.
    llm_input_tokens  BIGINT  NOT NULL DEFAULT 0 CHECK (llm_input_tokens  >= 0),
    llm_output_tokens BIGINT  NOT NULL DEFAULT 0 CHECK (llm_output_tokens >= 0),

    stt_seconds       REAL    NOT NULL DEFAULT 0 CHECK (stt_seconds       >= 0),
    stt_calls         INTEGER NOT NULL DEFAULT 0 CHECK (stt_calls         >= 0),
    tts_calls         INTEGER NOT NULL DEFAULT 0 CHECK (tts_calls         >= 0),

    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, local_date)
);
