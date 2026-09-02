-- W13 (the capture half, W13-ii in `BUILD_PROGRESS.md`): `video_glosses`.
--
-- Plain, non-idempotent DDL, per 009's note and every file since: core.db.migrate
-- wraps each file in one transaction and gates it on schema_version, which is
-- what makes a re-run impossible. This file writes NO schema_version row.
--
-- NOTHING IS SEEDED HERE AND THIS MIGRATION COSTS NO BILLED CALL. Rows arrive
-- from `python -m core.video.explain --apply`, which is human-run, dry by
-- default, and **has not been run**: the first billed run is a separate, later
-- operator decision gated on T1.
--
-- ---------------------------------------------------------------
-- THE SLICE ID HERE IS `W13` AND NOT `W13-ii`, AND THAT IS #346 FIRING EXACTLY
-- AS IT PREDICTED IT WOULD.
-- ---------------------------------------------------------------
-- #346 was filed against "the first slice that will need the row". This is that
-- slice. `tests/test_record_consistency.py`'s `_SLICE_ID` is
-- `^\*{0,2}(W\d+[a-z]?)\*{0,2}$` -- **it does not match a hyphen** -- so `W13-ii`
-- in the authoritative table trips an assert and takes every TASKS check down,
-- and in a Build column it is skipped SILENTLY, which is the worse of the two.
-- 021 met this and used `W13`; this file follows that precedent rather than
-- inventing a second one. **#346 STAYS OPEN: the workaround is what that row
-- says sidesteps it.**
--
-- ---------------------------------------------------------------
-- #185, NINTH OCCURRENCE. THE NUMBER IS TAKEN IN THIS COMMIT.
-- ---------------------------------------------------------------
-- 022 is the highest applied version; production is at schema_version 22, and
-- `migrations/` on disk runs 001..022 with no gaps. **Read, not assumed.**
--
-- **WHICH OF #185's TWO COUNTINGS THIS IS:** on the count of numbers TAKEN AT
-- IMPLEMENTATION TIME this is the TENTH (017 fourth, 018 fifth, 019 sixth, 020
-- seventh, 021 eighth, 022 ninth, this tenth). On the other reading -- only
-- takes that SHIFTED an unwritten row -- **this is the NINTH**, because 019 and
-- 022 shifted nothing. **The prompt called it the ninth and that is the second
-- counting; both are stated here, and #185 stays open on which it means.**
--
-- TWO UNWRITTEN SLICES SHIFT BY ONE IN THIS SAME COMMIT, in BOTH halves of
-- docs/TASKS-v3-web.md -- the authoritative table AND each slice's Build cell:
--
--     W14  `speech_attempts`                  023 -> 024
--     W18  `placement_bank`, `placement_runs` 024 -> 025
--
-- Neither is written: nothing on disk, nothing applied to any database.
--
-- ---------------------------------------------------------------
-- WHY A TABLE AT ALL -- §2g's OPTION (a) IS DEAD, AND IT WAS RE-TESTED RATHER
-- THAN INHERITED.
-- ---------------------------------------------------------------
-- The W13 plan's position was **(a): write pre-generated definitions straight
-- into `cards` at generation time, and take no number.** It does not survive
-- contact with the tree, and the reason is one query:
--
--     `core.services.cards.due_queue` filters on `cards.user_id` and
--     `cards.due <= now` AND NOTHING ELSE. There is no status column on
--     `cards` -- 012's note records that a `status` column was refused --
--     so **every row in `cards` IS in the learner's deck.**
--
-- A pre-generated gloss exists before any learner taps; a `cards` row exists
-- only after a save. Writing unsaved glosses into `cards` would put words in
-- someone's deck that they never chose, serve them in block 1 the same day, and
-- count toward #170's deck-size trigger. **`cards.due` is `NOT NULL`, so such a
-- row would also have to carry a due date -- there is no not-yet-chosen state
-- to write that is not a lie.**
--
-- Option (b) -- the `video_coverage` row -- is REFUSED and not re-argued: §1b
-- ruled that table an audit record and it is not repurposed.
--
-- So (c). **A gloss is a candidate, and a card is a commitment. They are
-- different objects and they get different tables.**

CREATE TABLE video_glosses (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- CASCADE, unlike `cards.source_chunk_id`'s SET NULL, and the difference is
    -- the point: a card is evidence about the learner and outlives its source,
    -- while a gloss is *about* one video's line and means nothing without it.
    video_id          BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,

    -- The surface word as it appears in the transcript, folded for lookup by
    -- the caller. NOT a lemma: `core.services.cards.resolve_capture_lemma`'s
    -- docstring records why `lemmatize` is not called on a captured word
    -- (`tier` -> `ti`, #162), and this table makes no identity claim a lemma
    -- would imply.
    word              TEXT NOT NULL,

    -- The transcript's OWN line, verbatim. Not generated, so #99's track-weight
    -- bias cannot enter here -- the generated free text is `definition`,
    -- `neutral_equivalent` and `who_says_this`, and those are what the
    -- naturalness gate reads.
    context_sentence  TEXT NOT NULL,

    -- Seconds into the video, from `core.video.cues.active_cue` over
    -- `videos.transcript_cues`. **NULLABLE, AND NULL IS THE THIRD STATE RATHER
    -- THAN AN ERROR** (#330's shape): a video whose cues were never stored or
    -- were refused by the identity gate yields a gloss with the sentence and no
    -- offset, and the card it produces carries the sentence and no timestamp.
    cue_start_s       NUMERIC(9,3),

    definition        TEXT NOT NULL,

    -- Mirrored from `cards.register` (013:110) so a gloss cannot be stored that
    -- no card could carry. `tests/test_migration_023.py` compares this CHECK
    -- against the one on `cards` -- two copies of one enum is how one of them
    -- stops matching (#132's family).
    register          TEXT NOT NULL CHECK (register IN (
                          'formal', 'neutral', 'informal', 'slang', 'taboo')),

    neutral_equivalent TEXT,
    who_says_this      TEXT,

    -- PRD §8.5.4's four things, mirrored from `cards_informal_shows_the_four_things`
    -- (013:222) ONE LAYER EARLIER. Without this a generator could store an
    -- informal gloss missing the safe alternative, and the failure would surface
    -- as a CheckViolation on a learner's TAP -- a 500 in front of someone doing
    -- a normal thing, which is #178's defect arriving from a different door.
    -- **Refusing it at generation time is refusing it while the operator is
    -- watching**, which is the whole shape of the pre-generate ruling.
    CONSTRAINT video_glosses_informal_carries_the_four_things CHECK (
        register NOT IN ('informal', 'slang')
        OR (neutral_equivalent IS NOT NULL AND who_says_this IS NOT NULL)
    ),

    -- Provenance. `model` is the id the row was produced by, so a re-run under
    -- a different model is identifiable with one WHERE -- `cards.register_source`'s
    -- own argument, and #93's.
    model             TEXT NOT NULL,
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One gloss per word per video. A word means what it means IN THIS LINE, so
    -- the key is (video, word) and not the word alone: the same word in two
    -- videos is two senses and two glosses, which is the sense problem #181
    -- leaves open, sidestepped here rather than solved.
    UNIQUE (video_id, word)
);

CREATE INDEX idx_video_glosses_video ON video_glosses (video_id);
