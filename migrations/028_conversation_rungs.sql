-- ============================================================================
-- 028 — W15. Retell and answer: two rungs on W13b's conversation loop.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–027 with no
-- gaps and the development database reported `schema_version = 27`. **028 IS
-- WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, and W18 is unwritten, so
-- **W18 SHIFTS 028 → 029 IN BOTH HALVES OF `docs/TASKS-v3-web.md` IN THIS SAME
-- COMMIT.** W4b's policy: take the next number, never one above everything
-- claimed. **#185's FOURTEENTH on the *taken at implementation time* counting**
-- (the counting 025–027 use); on the *shifted an unwritten row* counting it is
-- the thirteenth. The two still do not reconcile and this file does not
-- resolve them.
--
-- ----------------------------------------------------------------------------
-- PRODUCT-PRINCIPLES §2: **no new user-keyed table.** Two columns on
-- `conversations`, which already keys on `users(id)`.
--
-- ----------------------------------------------------------------------------
-- **WHY COLUMNS ON `conversations` AND NOT A TABLE OF THEIR OWN.** The TASKS row
-- as W14r corrected it: W15 is *two rungs ON TOP OF W13b's loop*. A retell or an
-- answer is opened, takes the learner's turn (typed, or voice through the same
-- gated route), meets the same per-day cap, and is closed by the same one-shot
-- close that deletes the turns. **Everything but the opener and the close
-- prompt is the loop's.** A second table would be a second open-slot rule, a
-- second retention sweep and a second cap — #190's defect in the schema.
--
-- **`conversations_one_open_per_user` STILL HOLDS ACROSS KINDS**: a learner has
-- one open exchange of any kind. Opening a different kind abandons the open one
-- the way a cold conversation is abandoned — closed, turns deleted by the
-- sweep, no close-out call (the service docstring says why).
--
-- **NO TEXT IS ADDED.** The rung's opener is the unit's `output_task_spoken`
-- (served verbatim from `syllabus_units`) or a fixed line naming the video; the
-- learner's turn lives in `conversation_turns` and is deleted at close exactly
-- as a conversation's is (§O2). **The retell's coverage result is not stored**:
-- it is derived from a scraped transcript under a 30-day purge (019), and a
-- stored copy would outlive the thing it was derived from.
--
-- **`speech_attempts.surface` IS NOT WIDENED**, though 024's comment names W15
-- as its widener. Nothing here scores pronunciation: PRD §8.6 question 3 was
-- ruled *neither scored nor shown* for conversation, W14's shadow surface is
-- retired (#376), and a rung's voice is transcribed by Whisper and discarded
-- (§12). A value nothing writes would be a CHECK wider than its writers.
-- ============================================================================

ALTER TABLE conversations
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'talk'
        CONSTRAINT conversations_kind_is_known
        CHECK (kind IN ('talk', 'answer', 'retell'));

-- The video a retell is OF. `ON DELETE SET NULL` for `video_assignments`'
-- reason: the exchange happened whether or not the pool row survives, and 019's
-- purge nulls a video's text but never deletes its row.
ALTER TABLE conversations
    ADD COLUMN video_id BIGINT REFERENCES videos(id) ON DELETE SET NULL;

-- **ONLY A RETELL NAMES A VIDEO.** Not the converse (a retell whose video row
-- was deleted keeps `kind = 'retell'` with a NULL here), so the constraint
-- survives the `SET NULL` above rather than blocking the delete.
ALTER TABLE conversations
    ADD CONSTRAINT conversations_only_a_retell_names_a_video
    CHECK (kind = 'retell' OR video_id IS NULL);

COMMENT ON COLUMN conversations.kind IS
    'W15. talk = W13b''s conversation; answer = the unit''s spoken task; retell = today''s video, retold.';
