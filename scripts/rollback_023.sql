-- rollback_023.sql — reverse W13-ii's pre-generated gloss store.
--
--   psql "$DATABASE_URL" --single-transaction -v ON_ERROR_STOP=1 \
--        -f scripts/rollback_023.sql
--
-- WHAT THIS RESTORES: the exact pre-023 shape. `video_glosses` gone,
-- schema_version back to 22. 023 creates one table and touches no existing one.
--
-- ---------------------------------------------------------------
-- WHAT THIS ROLLBACK CANNOT REVERSE — AND HERE IT IS MONEY
-- ---------------------------------------------------------------
-- 1. **EVERY ROW IN THIS TABLE WAS PAID FOR.** Unlike 021's cues, which were
--    recoverable from dump files already on the host, a gloss exists only
--    because `python -m core.video.explain --apply` made a billed call.
--    **Dropping the table discards the purchase**, and the only way back is to
--    pay again. There is no dump, no cache and no second copy.
-- 2. **THE CARDS IT PRODUCED SURVIVE, AND THAT ASYMMETRY IS DELIBERATE.**
--    `cards` has no FK to `video_glosses`: a card is the learner's, is graded,
--    accumulates FSRS state, and is evidence about them. A gloss is a candidate
--    that was offered. Dropping the store leaves every saved card intact and
--    only removes what has not been chosen yet.
-- 3. It reverses no application change. The route, the service and the command
--    are git-reverted, not psql-reverted. A frontend calling `save-word`
--    against a database without this table gets `no_gloss` for every word --
--    which is a specified state, not a crash. **Revert the frontend anyway**,
--    so the two halves describe the same product.
--
-- ---------------------------------------------------------------
-- THE GUARD. Refuse if anything was bought.
-- ---------------------------------------------------------------
DO $$
DECLARE
    held BIGINT;
BEGIN
    SELECT count(*) INTO held FROM video_glosses;
    IF held > 0 THEN
        RAISE EXCEPTION
            'refusing: % gloss(es) would be destroyed, and every one of them '
            'was a billed call. There is no dump to re-read and no second '
            'copy. Export them first, or delete this guard deliberately.', held;
    END IF;
END $$;

DROP TABLE IF EXISTS video_glosses;

DELETE FROM schema_version WHERE version = 23;
