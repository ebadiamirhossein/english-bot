-- rollback_019.sql — reverse W12b's video pipeline.
--
--   psql "$DATABASE_URL" --single-transaction -v ON_ERROR_STOP=1 \
--        -f scripts/rollback_019.sql
--
-- --single-transaction is not optional. This file drops three tables with two
-- foreign keys between them, and a run that stops half way leaves the database
-- in a state neither schema describes -- worse than not rolling back at all.
--
-- WHAT THIS RESTORES: the exact pre-019 shape. `videos`, `video_coverage` and
-- `video_assignments` gone, their indexes and constraints with them, and
-- schema_version back to 18 so `core.db status` reports the truth. 019 adds no
-- column to any existing table and rewrites no existing value, so there is
-- nothing else to put back -- which is the whole reason this rollback is short
-- and rollback_011 is not.
--
-- WHEN IT STOPS BEING AN OPTION: the moment a single video has been assigned to
-- a learner. The guard below refuses rather than choosing, for the reason in
-- section 0. After that point the only path is a restore from the pre-migration
-- dump.
--
-- ---------------------------------------------------------------
-- WHAT THIS ROLLBACK CANNOT REVERSE, AND ITEM 4 IS THE ONE NOBODY PREDICTS
-- ---------------------------------------------------------------
-- Stated here rather than discovered afterwards. A rollback that is believed to
-- be total is more dangerous than one whose limits are written down.
--
-- 1. BILLED APIFY CALLS. Money spent is spent. Nothing in this schema is a cache
--    that survives the drop, so re-running the pipeline after re-migrating pays
--    the same bill a second time.
--
-- 2. YOUTUBE DATA API QUOTA already consumed for the day. Not money, but not
--    returnable either, and the daily ceiling is 10,000 units.
--
-- 3. ASSIGNMENT HISTORY. Which video was served to which learner on which date
--    exists in `video_assignments` and NOWHERE ELSE -- no session row, no
--    journal entry, no log line records it. This is why section 0 refuses
--    instead of proceeding.
--
-- 4. THE 30-DAY CLOCK RESTARTS, AND THIS IS NOT OBVIOUS.
--    `metadata_refreshed_at` is destroyed with the table, so the next refresh
--    after a rollback re-fetches every video and stamps TODAY. A video first
--    stored twenty-five days ago silently receives a fresh thirty-day window it
--    is not entitled to. THE ROLLBACK CANNOT RESTORE COMPLIANCE STATE. If this
--    file is run after the pool has been live for more than a few days, the
--    honest remedy is to note the date of the original fetch before dropping,
--    and to purge on the ORIGINAL clock after re-migrating.
--
-- 5. It reverses no `data/` file. `data/video_channels.json` and the licence
--    clauses added to `data/LICENCES.md` are git-reverted, not psql-reverted.

-- ---------------------------------------------------------------
-- 0. The guard. One table gained the ability to hold something nothing else
--    records, and dropping it is not a schema change but a data loss.
-- ---------------------------------------------------------------
DO $g$
DECLARE n BIGINT; msg TEXT;
BEGIN
    SELECT count(*) INTO n FROM video_assignments;
    IF n > 0 THEN
        msg := 'rollback_019 REFUSED: ' || n || ' video assignment(s) exist. '
            || 'Dropping them discards which video was served to which learner '
            || 'on which date, which no other table, journal or log records. '
            || 'Restore from the pre-migration dump instead.';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;
END $g$;

-- ---------------------------------------------------------------
-- 1. Children first, so no foreign key is dropped out from under a row.
--
--    `video_assignments` before `videos` because of its ON DELETE RESTRICT --
--    which the guard above has already established is holding nothing back.
--    `video_coverage` is CASCADE on both sides and would follow `videos` on its
--    own, but it is dropped explicitly rather than left to a cascade: a rollback
--    that relies on an implicit drop hides what it removed.
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS video_assignments;
DROP TABLE IF EXISTS video_coverage;

-- ---------------------------------------------------------------
-- 2. The pool itself. Its two indexes go with it.
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS videos;

-- ---------------------------------------------------------------
-- 3. Un-stamp the version, so `core.db status` reports the truth and a later
--    `core.db migrate` RE-APPLIES 019 rather than skipping it.
--
--    core/db.py computes pending as a SET DIFFERENCE, not as "> max", so a
--    leftover row here would make 019 invisible to migrate for good while the
--    tables it describes did not exist -- a database that reports itself
--    migrated and is not.
-- ---------------------------------------------------------------
DELETE FROM schema_version WHERE version = 19;
