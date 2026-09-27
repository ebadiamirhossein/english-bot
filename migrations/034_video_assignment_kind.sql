-- ============================================================================
-- 034 — W24d. A learner may hold TWO assignments on one date: the day's video
-- and, at most, one `extra` — the video W24e's *keep going* offers after the
-- session is finished (operator decision 1 of 2026-09-27; rulings R2, R3).
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–033 with no
-- gaps and the development database reported `schema_version` 33. Nothing in
-- `docs/TASKS-v3-web.md` reserved 034, so **no unwritten row shifts** — #185's
-- rule (take the next number when the file is written) with nothing to move.
--
-- ----------------------------------------------------------------------------
-- WHAT CHANGES
--
--   `kind` — 'daily' (the session's block 2, one per date, as 019 had it) or
--   'extra' (keep going's *watch another*, at most one per date). Every
--   existing row is a daily assignment and takes the default.
--
--   019's `UNIQUE (user_id, assigned_for)` becomes
--   `UNIQUE (user_id, assigned_for, kind)`: still ONE daily video per date —
--   019's reason (*the learner opens the day and finds one thing, not a
--   choice*) is unchanged for block 2 — and at most one extra.
--
-- WHAT DOES NOT CHANGE, AND IS THE POINT
--
--   **A video is still never assigned twice to one learner, whatever its kind.**
--   That is not a constraint here and never was: `seen_penalty` reads every
--   assignment row for the learner (`core.services.video.seen_video_ids`), so
--   an extra is as *seen* as a daily one. `save_progress` keys on
--   (user_id, video_id), which that rule keeps unique per learner.
--
-- PRODUCT-PRINCIPLES §2: the table already keys on `users(id)` (019); this adds
-- a column and changes a unique, and adds no dependency on a Telegram id.
-- ============================================================================

ALTER TABLE video_assignments
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'daily'
        CHECK (kind IN ('daily', 'extra'));

ALTER TABLE video_assignments
    DROP CONSTRAINT video_assignments_user_id_assigned_for_key;

ALTER TABLE video_assignments
    ADD CONSTRAINT video_assignments_one_per_kind_per_date
        UNIQUE (user_id, assigned_for, kind);

COMMENT ON COLUMN video_assignments.kind IS
    'W24d: daily = block 2 of the session (one per date); extra = keep going''s '
    'watch-another (at most one per date). Never the same video twice per learner, '
    'whatever the kind: seen_penalty reads every row.';
