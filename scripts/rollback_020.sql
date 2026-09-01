-- rollback_020.sql — restore `videos.accent NOT NULL`.
--
--   psql "$DATABASE_URL" --single-transaction -v ON_ERROR_STOP=1 \
--        -f scripts/rollback_020.sql
--
-- --single-transaction is kept for the same reason every rollback in this
-- directory carries it, even though this one touches a single column: a run
-- that stops between the ALTER and the schema_version DELETE leaves
-- `core.db status` reporting a version the schema does not match, which is the
-- state #268 cost this project three days of confident wrong claims.
--
-- WHAT THIS RESTORES: the exact pre-020 shape. `videos.accent` NOT NULL again,
-- and schema_version back to 19 so `core.db status` reports the truth. 020
-- creates no table, drops no column and rewrites no value, so there is nothing
-- else to put back.
--
-- ---------------------------------------------------------------
-- 0. THE GUARD. It refuses with a COUNT rather than erroring obscurely.
-- ---------------------------------------------------------------
-- `ALTER COLUMN accent SET NOT NULL` fails on its own if any row holds a null,
-- but it fails as a bare constraint violation naming neither the column's
-- purpose nor how many rows are in the way. Somebody reading that message at
-- speed, mid-incident, learns almost nothing.
--
-- This refuses first and says how many, because the remedy depends on the
-- number: one or two rows may be worth authoring an accent for; a dozen means
-- the pool has moved on and the honest path is to leave 020 applied.
--
-- WHAT IT DOES NOT DO IS CHOOSE. It will not delete the rows, and it will not
-- invent an accent to make them fit -- inventing a value is the exact defect
-- migration 020 exists to stop the schema demanding. A rollback that
-- fabricated data to satisfy a constraint would be worse than no rollback.
-- ---------------------------------------------------------------
DO $g$
DECLARE n BIGINT; msg TEXT;
BEGIN
    SELECT count(*) INTO n FROM videos WHERE accent IS NULL;
    IF n > 0 THEN
        msg := 'rollback_020 REFUSED: ' || n || ' video(s) hold a null accent. '
            || 'SET NOT NULL cannot succeed while they exist. These are videos '
            || 'from a by_ruling channel -- one with no single true accent, '
            || 'such as TED-Ed -- so there is no correct value to fill in and '
            || 'this file will not invent one. Either author an accent for '
            || 'each and re-run, or leave 020 applied.';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;
END $g$;

-- ---------------------------------------------------------------
-- 1. The column. The CHECK is untouched here because it was untouched by 020 --
--    it already rejects every non-null value outside ('american','british'),
--    and a NULL passed it only because a CHECK passes on unknown.
-- ---------------------------------------------------------------
ALTER TABLE videos ALTER COLUMN accent SET NOT NULL;

-- ---------------------------------------------------------------
-- 2. The version, so `core.db status` stops claiming a migration that is no
--    longer applied.
-- ---------------------------------------------------------------
DELETE FROM schema_version WHERE version = 20;

-- ---------------------------------------------------------------
-- WHAT THIS ROLLBACK DOES NOT REVERSE
-- ---------------------------------------------------------------
-- 1. THE CODE. `core.video.channels` will still load a `by_ruling` null accent
--    and `core.video.refresh` will still try to write it, so the next refresh
--    after this rollback raises IntegrityError on the first such channel. The
--    code half is git-reverted, not psql-reverted, and reverting one without
--    the other is the half-state the single-commit ruling exists to prevent.
--
-- 2. `data/video_channels.json`. The `accent_null` fields are a git revert.
--
-- 3. ANY VIDEO ALREADY FETCHED from a by_ruling channel. The guard refuses
--    while such rows exist; deleting them to get past it discards fetched
--    metadata and restarts the 30-day purge clock described in rollback_019's
--    item 4. If that is the chosen path, note the original fetch dates first.
