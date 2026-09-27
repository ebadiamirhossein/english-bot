-- Rollback for migration 035 (W31c, pending word saves; gloss l1 and source).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_034.sql`'s precedent.
--
-- **IT REFUSES WHILE ANY PENDING SAVE EXISTS.** A row in `word_saves_pending`
-- is a word a learner chose to keep; dropping the table deletes it, and a
-- missing saved word is not recoverable from anywhere else. Once rows exist,
-- rolling back means a forward migration, not this file.
--
-- Dropping `video_glosses.l1` and `.source` loses the L1 meanings and the
-- provenance; the English glosses survive. The L1 text could only be rebuilt
-- by billed calls. Does not touch `schema_version`; removing the row is a
-- separate deliberate statement:
--     DELETE FROM schema_version WHERE version = 35;
--
-- **ONE TRANSACTION, AND IT STOPS AT THE FIRST ERROR.** Found by rehearsing it
-- (§5c): run as a plain `psql -f`, the refusal below printed its ERROR and psql
-- went on to the `DROP`s. `ON_ERROR_STOP` makes the refusal final, and the
-- transaction makes the rollback all-or-nothing.
\set ON_ERROR_STOP on
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM word_saves_pending) THEN
        RAISE EXCEPTION 'word_saves_pending holds learners'' saved words; refusing to drop it';
    END IF;
END
$$;
DROP TABLE word_saves_pending;
DROP INDEX IF EXISTS video_glosses_by_source_and_time;
ALTER TABLE video_glosses DROP CONSTRAINT IF EXISTS video_glosses_l1_is_an_object;
ALTER TABLE video_glosses DROP COLUMN IF EXISTS source;
ALTER TABLE video_glosses DROP COLUMN IF EXISTS l1;
COMMENT ON COLUMN video_glosses.word IS NULL;
COMMIT;
