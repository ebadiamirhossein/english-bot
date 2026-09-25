-- Rollback for migration 028 (W15, the conversation rungs).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_026.sql`'s precedent.
--
-- Every `answer` and `retell` row loses its kind and reads as a `talk` row
-- afterwards; the turns are already gone (deleted at close), so nothing else
-- is lost. Does not touch `schema_version`; removing the row is a separate
-- deliberate statement:
--     DELETE FROM schema_version WHERE version = 28;
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_only_a_retell_names_a_video;
ALTER TABLE conversations DROP COLUMN IF EXISTS video_id;
ALTER TABLE conversations DROP COLUMN IF EXISTS kind;
