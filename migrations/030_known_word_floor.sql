-- ============================================================================
-- 030 — W13c. The known-word floor becomes a NUMBER PER LEARNER, and the
-- covered set it implies is COMPUTED at read time from `freq_rank <= floor`.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–029 with no
-- gaps and the development database reported `schema_version` 29. **030 IS
-- WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, and W18 is unwritten
-- (blocked on its item bank), so **W18 SHIFTS 030 → 031 IN BOTH HALVES OF
-- `docs/TASKS-v3-web.md` IN THIS SAME COMMIT.** #185's rule: take the next
-- number when the file is written.
--
-- ----------------------------------------------------------------------------
-- THE RULING (build run, 2026-09-25): options (c) AND (d) together.
--
--   (c) a default with a correction path — the default is 2000, the value the
--       global `LEXICON_ASSUMED_KNOWN_TOP_N` has held since W4; the correction
--       path is an operator CLI, `python -m core.lexicon.floor`, dry by
--       default. The learner's own path arrives with W18.
--   (d) store the number and COMPUTE the covered set. PRODUCT-PRINCIPLES §3's
--       first bullet: ~2,000 `user_lexemes` rows per learner were rows that
--       could be computed. **No `source = 'assumption'` row is written from
--       this migration on**, by anything.
--
-- **EXISTING `assumption` ROWS ARE KEPT, NOT DELETED** — this migration touches
-- none of them. Reads stop consulting them (`core.services.lexicon`), and the
-- before/after table `python -m core.lexicon.floor` prints is what shows the
-- switch changed no covered set. A delete would be the one step here that
-- cannot be taken back, and nothing needs it.
--
-- **NO LEARNER-VISIBLE COUNT MOVES.** *Words you know* is
-- `evidenced_known_count`, which has excluded `assumption` rows since W4, and
-- the floor is not a row — so neither the old floor nor the new one ever
-- reached that number.
--
-- ----------------------------------------------------------------------------
-- #48: `approved_onboarded_users` is `SELECT u.*`, which freezes its column list
-- at creation. **An `ALTER TABLE users` is therefore paired with the view
-- recreate in this same file.** CREATE OR REPLACE is legal because the column
-- is APPENDED: the view's existing columns keep their names, types and order,
-- and the replacement only adds one at the end.
--
-- PRODUCT-PRINCIPLES §2: a column on `users(id)`'s own row, no Telegram id.
-- **NO TEXT IS STORED.** One integer.
-- ============================================================================

ALTER TABLE users
    ADD COLUMN known_word_floor INTEGER NOT NULL DEFAULT 2000
        CONSTRAINT users_known_word_floor_in_range
        CHECK (known_word_floor BETWEEN 0 AND 20000);

COMMENT ON COLUMN users.known_word_floor IS
    'W13c: this learner is assumed to know every lexeme with freq_rank <= this '
    'number, unless the ledger holds evidence otherwise. Computed at read time '
    '(core.services.lexicon); never materialised. Default 2000 = W4''s global '
    'floor. Corrected by `python -m core.lexicon.floor`, dry by default.';

CREATE OR REPLACE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.user_id = u.id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';
