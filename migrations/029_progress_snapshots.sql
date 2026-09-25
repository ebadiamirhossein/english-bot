-- ============================================================================
-- 029 — W19. Progress: one row per learner per local day the progress screen
-- was read, holding the two numbers that screen must never show going down or
-- must be able to draw over time.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–028 with no
-- gaps and the development database reported `Applied: 001 … 028`, `Pending:
-- (none)`. **029 IS WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, and W18 is
-- unwritten (blocked on its item bank), so **W18 SHIFTS 029 → 030 IN BOTH
-- HALVES OF `docs/TASKS-v3-web.md` IN THIS SAME COMMIT.** #185's rule: take the
-- next number when the file is written.
--
-- ----------------------------------------------------------------------------
-- PRODUCT-PRINCIPLES §2: **the table keys on `users(id)`**, ON DELETE CASCADE,
-- and adds no dependency on a Telegram id.
--
-- PRODUCT-PRINCIPLES §3, **FLAGGED AS THE PRINCIPLE ASKS: this materialises one
-- row per user per day.** It is not a row that could be computed instead:
--
--   * **The known-word line needs a HISTORY and none exists.** `user_lexemes`
--     keeps the current state only — its upsert overwrites `state` and moves
--     `updated_at`, so *how many words were known on 1 October* is not in the
--     database on 2 October. W11b's weekly count reads `updated_at` as a named
--     proxy for a one-week window; six months of a line drawn from that proxy
--     would be a reconstruction, and the run prompt's ruling is that the line
--     is drawn from the count's own history or reported unmet, **never
--     fabricated.** This table IS that history, from the day it ships.
--   * **XP must never go down on screen**, and the ledgers XP is computed from
--     can lose rows: `core.items.seed_fixtures --purge` deletes fixture items
--     and their attempts cascade (correct — an attempt on a test fixture is not
--     evidence). A computed total would then drop. `xp` here is the highest
--     total this learner has been shown, and the screen shows the larger of it
--     and the computed total.
--
-- At most 366 rows per learner per year, written only when the learner opens
-- the progress screen. The multi-tenant cost is linear and small.
--
-- **NO TEXT IS STORED.** Two integers and a date.
--
-- `sessions.xp` (016) STAYS NULL AND IS NOT THE HOME FOR THIS. W19 computes XP
-- from the ledgers (`item_attempts`, `card_reviews`, `conversation_usage`,
-- `writing_submissions`, `video_assignments`) rather than per session, because
-- half of what earns XP — a talk, a journal entry, a video — is not a `daily`
-- row's child. The column is documented as reserved below (#349's shape: a
-- column with no writer says so where a reader of the schema will see it).
-- ============================================================================

CREATE TABLE progress_snapshots (
    user_id      BIGINT  NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- The learner's LOCAL date, from `users.timezone` — the calendar the
    -- learner lives on, as `conversation_usage.local_date` is.
    local_date   DATE    NOT NULL,

    -- `core.services.lexicon.evidenced_known_count` at the moment of the read:
    -- `known`/`mastered` rows whose source is NOT `assumption` (W4's ruling).
    -- The LATEST read of the day wins; a word lapsing to `learning` is a real
    -- change and the history records it.
    known_words  INTEGER NOT NULL CHECK (known_words >= 0),

    -- The highest XP total the learner has been shown on this day. Written with
    -- GREATEST, so a second read the same day can only raise it.
    xp           INTEGER NOT NULL CHECK (xp >= 0),

    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, local_date)
);

COMMENT ON TABLE progress_snapshots IS
    'W19: one row per learner per local day the progress screen was read. '
    'The known-word history and the XP high-water mark. No text.';

COMMENT ON COLUMN sessions.xp IS
    'RESERVED, NO WRITER. W19 computes XP from the activity ledgers '
    '(core.services.progress), not per session. See #349.';
