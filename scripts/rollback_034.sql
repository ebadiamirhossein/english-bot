-- Rollback for migration 034 (W24d, `video_assignments.kind`).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_028.sql`'s precedent.
--
-- **Every `extra` assignment is DELETED first**, because 019's
-- `UNIQUE (user_id, assigned_for)` cannot be restored while a date holds a
-- daily and an extra. Those rows are keep going's extra videos (W24e): the
-- learner loses the record of having been given them, and with it their
-- `seen` status — so an extra video may be offered again after a rollback.
-- Daily rows are untouched. Does not touch `schema_version`; removing the row
-- is a separate deliberate statement:
--     DELETE FROM schema_version WHERE version = 34;
DELETE FROM video_assignments WHERE kind = 'extra';
ALTER TABLE video_assignments DROP CONSTRAINT IF EXISTS video_assignments_one_per_kind_per_date;
ALTER TABLE video_assignments ADD CONSTRAINT video_assignments_user_id_assigned_for_key UNIQUE (user_id, assigned_for);
ALTER TABLE video_assignments DROP COLUMN IF EXISTS kind;
