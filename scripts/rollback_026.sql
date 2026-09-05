-- Rollback for migration 026 (W13b/2, the conversation summary).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_025.sql`'s precedent.
--
-- Does not touch `schema_version`; removing the row is a separate deliberate
-- statement, for the reason 025's rollback records.
--     DELETE FROM schema_version WHERE version = 26;
ALTER TABLE conversations DROP COLUMN IF EXISTS summary;
