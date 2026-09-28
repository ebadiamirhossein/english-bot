-- Rollback for migration 036 (W32a, the global word dictionary).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_035.sql`'s precedent.
--
-- **NO LEARNER DATA IS LOST.** No card references `word_dictionary`: a save
-- copies the sense's text into `cards` (W32b), so every saved word keeps its
-- meaning. **WHAT IS LOST IS MONEY:** every row was a billed call. The backfill
-- printed its own cost when it ran (W32a's dry-run line); rebuilding costs that
-- again. Does not touch `schema_version`; removing the row is a separate
-- deliberate statement:
--     DELETE FROM schema_version WHERE version = 36;
--
-- **ONE TRANSACTION, AND IT STOPS AT THE FIRST ERROR** — 035's finding
-- (§5c): without `ON_ERROR_STOP` psql goes on past an error.
\set ON_ERROR_STOP on
BEGIN;
DROP INDEX IF EXISTS word_dictionary_by_source_and_time;
DROP TABLE word_dictionary;
COMMIT;
