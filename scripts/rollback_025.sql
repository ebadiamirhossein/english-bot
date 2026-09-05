-- Rollback for migration 025 (W13b, the conversation surface).
--
-- **DESTRUCTIVE. NAMES ITS TARGET AND MUST BE RUN AGAINST `english_bot` AND NO
-- OTHER DATABASE** (CLAUDE.md §5). `scripts/rollback_024.sql` is the precedent.
--
-- Drops in dependency order. `conversation_turns` first: it is the child, and
-- dropping the parent first would only work through CASCADE, which is a wider
-- instrument than this needs.
--
-- **IT DOES NOT TOUCH `schema_version`.** Removing the row is a separate,
-- deliberate statement, because a rollback that silently rewinds the version
-- makes `core.db status` disagree with the tables that are actually there.
--     DELETE FROM schema_version WHERE version = 25;
DROP TABLE IF EXISTS conversation_turns;
DROP TABLE IF EXISTS conversation_usage;
DROP TABLE IF EXISTS conversations;
