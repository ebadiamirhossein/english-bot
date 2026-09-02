-- rollback_022.sql — reverse W13a's subtitle ladder.
--
--   psql "$DATABASE_URL" --single-transaction -v ON_ERROR_STOP=1 \
--        -f scripts/rollback_022.sql
--
-- --single-transaction is kept even though this file makes two DROPs, because a
-- rollback that is sometimes atomic and sometimes not is a habit that fails on
-- the file where it matters. It also rolls schema_version back, and that last
-- statement must never land without the others.
--
-- WHAT THIS RESTORES: the exact pre-022 shape. Both tables gone, schema_version
-- back to 21 so `core.db status` reports the truth. 022 creates two new tables
-- and touches no existing one -- no column added anywhere else, no constraint
-- widened, no value rewritten -- so there is nothing else to put back.
--
-- ---------------------------------------------------------------
-- WHAT THIS ROLLBACK CANNOT REVERSE
-- ---------------------------------------------------------------
-- Stated rather than discovered afterwards, on 019's and 021's precedent: a
-- rollback believed to be total is more dangerous than one whose limits are
-- written down.
--
-- 1. **NOTHING, TODAY, AND THE REASON IS WORTH READING BEFORE RUNNING IT.**
--    Both tables are **empty on production and will stay empty** until a caller
--    exists: `record_check`'s caller is the comprehension check (generated,
--    gated on §1a) and `record_reveal`'s is step 3/4's reveal control (blocked
--    on R12's cue boundaries). `tests/test_subtitle_ladder_service.py::
--    test_nothing_in_the_tree_calls_the_ladder_yet` holds that there is no
--    caller, so on the day this file is written it destroys no learner data.
--
-- 2. **THAT CHANGES THE MOMENT A CALLER LANDS, AND THIS FILE DOES NOT KNOW.**
--    Once checks are recorded, `subtitle_ladder` holds where each learner is on
--    a five-step progression and `subtitle_reveals` holds the event history the
--    weekly reveal number is computed from -- **and NOTHING ELSE DOES.** A
--    learner who had climbed to step 4 lands back on step 1 with no record that
--    they were ever higher, and the reveal history that makes *"a number that
--    goes down over weeks"* meaningful is gone: a lifetime counter could be
--    re-derived from a total, and a per-window count cannot be re-derived from
--    nothing.
--
-- 3. **SO THE GUARD BELOW EXISTS, ON `rollback_019.sql`'s PRECEDENT.** 019
--    refuses once a video has been assigned, because `video_assignments`
--    records what was served to whom and nothing else does. The same test
--    applies here the day the first row is written, so the refusal is written
--    NOW rather than remembered LATER -- the whole reason this project files a
--    guard before the data exists rather than after the first loss.
--
-- 4. It reverses no application change. There is none: **W13a ships no
--    `apps/web` change at all**, so no frontend revert is owed and no Vercel
--    rebuild was ever needed. The service and the pure rules are git-reverted,
--    not psql-reverted.

-- ---------------------------------------------------------------
-- 0. THE GUARD. Refuse if either table holds anything.
-- ---------------------------------------------------------------
DO $$
DECLARE
    ladders BIGINT;
    reveals BIGINT;
BEGIN
    SELECT count(*) INTO ladders FROM subtitle_ladder;
    SELECT count(*) INTO reveals FROM subtitle_reveals;
    IF ladders > 0 OR reveals > 0 THEN
        RAISE EXCEPTION
            'refusing: % ladder row(s) and % reveal(s) would be destroyed, and '
            'nothing else records where a learner reached or how often they '
            'looked. Export them first, or delete this guard deliberately.',
            ladders, reveals;
    END IF;
END $$;

-- ---------------------------------------------------------------
-- 1. The tables. `subtitle_reveals` first: it is the one with the FK.
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS subtitle_reveals;
DROP TABLE IF EXISTS subtitle_ladder;

-- ---------------------------------------------------------------
-- 2. The version, so `core.db status` stops claiming a migration that is no
--    longer applied.
-- ---------------------------------------------------------------
DELETE FROM schema_version WHERE version = 22;
