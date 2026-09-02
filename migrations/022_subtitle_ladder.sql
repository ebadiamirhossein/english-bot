-- W13a (the subtitle ladder): `subtitle_ladder` and `subtitle_reveals`.
--
-- Plain, non-idempotent DDL, per 009's note and every file since: core.db.migrate
-- wraps each file in one transaction and gates it on schema_version, which is
-- what makes a re-run impossible. Guards would only buy the impression that a
-- re-run is safe. This file writes NO schema_version row -- the runner does that
-- (core/db.py), and only 001 inserts one itself.
--
-- NOTHING IS SEEDED HERE and this migration costs no billed call. A learner with
-- no row is on step 1 by construction; `core.services.subtitle_ladder.ladder_for`
-- does not write on a read, so the first INSERT is the first movement.
--
-- ---------------------------------------------------------------
-- #185: THE NUMBER IS TAKEN IN THIS COMMIT, AND FOR ONCE IT SHIFTS NOTHING.
-- ---------------------------------------------------------------
-- 021 is the highest applied version; production is at schema_version 21.
--
-- **WHICH OF #185's TWO COUNTINGS THIS IS, stated because that row's own note
-- requires whoever next takes a number to say:** on the count of numbers TAKEN
-- AT IMPLEMENTATION TIME this is the NINTH (017 fourth, 018 fifth, 019 sixth,
-- 020 seventh, 021 eighth, this ninth) -- the counting these headers use. On the
-- other reading -- only takes that SHIFTED an unwritten row -- **this take does
-- not count at all, because it shifts nothing**: `docs/TASKS-v3-web.md`'s
-- authoritative table already reserved 022 for W13a, W14 keeps 023 and W18 keeps
-- 024. **The first take since 016 that moves no other row.** Both countings are
-- stated; #185 stays open on which it means.
--
-- ---------------------------------------------------------------
-- TWO TABLES WHERE THE AUTHORITATIVE TABLE NAMED ONE, AND THE ROW IS AMENDED IN
-- THIS SAME COMMIT -- 019's precedent, applied deliberately.
-- ---------------------------------------------------------------
-- 019 shipped three tables where its row named two, and the record ruled that a
-- file shipping a table its row does not name is #49's defect from the other
-- side: the number right and the contents wrong. So the row is amended here
-- rather than left to disagree.
--
-- **WHY THE SECOND TABLE EXISTS AND A COLUMN WOULD NOT DO.** PRD §7.5:
-- *"Reveals in step 4 are counted and shown as a number that goes down over
-- weeks -- that number is the honest measure of listening progress."*
-- **A lifetime counter can only ever go up.** A number that goes down over weeks
-- is a count PER WINDOW, and a window count needs the events to be timestamped.
-- An `INTEGER reveals` column on the ladder row cannot produce it at any later
-- date without the history it never kept.
--
-- ---------------------------------------------------------------
-- WHAT THIS MIGRATION DOES NOT ADD, SAID SO IT IS NOT LOOKED FOR
-- ---------------------------------------------------------------
-- **No `videos.source_type`.** `track_kind` is a property of the LADDER, not a
-- column on the shared `videos` row, and adding one here would ship a change to
-- a table this row does not name. Every `videos` row is a YouTube one today, so
-- the mapping is a one-line fact in `core.services.subtitle_ladder` rather than
-- data; `native_series` has no producer until the series importer exists
-- (#172-#174).
--
-- **No `last_check_score`.** Nothing in PRD §7.5's rules reads a stored score,
-- and *drops are silent* means the one moment it would be shown is the one
-- moment it must not be. The checkpoint stores its score only because 014's
-- CHECK requires a `passed` row to name the score that passed; nothing here
-- does, so nothing is stored.

CREATE TABLE subtitle_ladder (
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Mirrored from `core.video.ladder.TRACK_KINDS`; `tests/test_migration_022.py`
    -- compares this CHECK against the constant, the way test_migration_012 does
    -- for item types. PRD §7.5 keeps the two ladders apart because the skills
    -- are different -- step 5 on BBC Learning English arrives long before step 5
    -- on a sitcom, and one ladder would stall a learner on the harder source.
    --
    -- `native_series` HAS NO PRODUCER TODAY and no row will carry it until the
    -- series import path exists. That is expected and is NOT to be fixed with a
    -- "every CHECK value has a writer" test, which would fail by design from the
    -- day it was written -- 013's note on `card_type`, same reasoning.
    track_kind      TEXT NOT NULL
                        CHECK (track_kind IN ('youtube_curated','native_series')),

    -- PRD §7.5's five rungs. A learner with NO ROW is on step 1; the DEFAULT and
    -- `core.video.ladder.FIRST_STEP` are two copies of one fact and
    -- `tests/test_migration_022.py` asserts they agree (#132's family).
    step            SMALLINT NOT NULL DEFAULT 1 CHECK (step BETWEEN 1 AND 5),

    -- **0 OR 1, NEVER 2, AND THE BOUND IS THE RULE ITSELF.** Two passes promote,
    -- and the promotion resets the counter in the same movement -- so a stored 2
    -- means the ladder stopped promoting. This is the invariant
    -- `core.video.ladder.apply_check` maintains, written where a hand `UPDATE`
    -- cannot get past it.
    passes_at_step  SMALLINT NOT NULL DEFAULT 0
                        CHECK (passes_at_step BETWEEN 0 AND 1),

    -- When this learner arrived on the step they are on. Not read by any rule;
    -- it is the clock a later "you have been here a while" question needs and
    -- the only way to tell a long step from a new one after the fact.
    entered_step_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, track_kind)
);

-- One row per reveal. See the header: a number that goes down over weeks is a
-- per-window count, and a per-window count needs events.
CREATE TABLE subtitle_reveals (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_kind  TEXT NOT NULL
                    CHECK (track_kind IN ('youtube_curated','native_series')),

    -- Provenance, and NULLABLE ON PURPOSE with SET NULL rather than CASCADE:
    -- `cards.source_chunk_id`'s reasoning exactly -- a reveal is evidence about
    -- the learner's listening even if the video row is later removed, and
    -- deleting the evidence with the video would make the weekly number drop for
    -- a reason that has nothing to do with the learner.
    video_id    BIGINT REFERENCES videos(id) ON DELETE SET NULL,

    -- **THE STEP THE REVEAL HAPPENED ON, AND IT IS NOT DECORATION.** PRD §7.5
    -- counts reveals *at step 4* -- step 3's *tap any line* is the safety net
    -- and is explicitly not the measure. Without this column every reveal is one
    -- undifferentiated event and the headline number could never be separated
    -- out again, which is the same history-you-did-not-keep argument that made
    -- this a table rather than a counter.
    step        SMALLINT NOT NULL CHECK (step BETWEEN 1 AND 5),

    revealed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The only read this table has: how many reveals in a window, for one learner
-- and one ladder.
CREATE INDEX idx_subtitle_reveals_window
    ON subtitle_reveals (user_id, track_kind, revealed_at);
