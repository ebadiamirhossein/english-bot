-- Migration 035 — W31c: a learner can save ANY word, and a gloss carries its
-- learner-language meaning and where it came from.
--
-- **Number taken when this file was written (2026-09-27): files 001–034 and
-- the dev `schema_version` 34; nothing had reserved 035 (#185).**
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. `word_saves_pending` — a tapped word that has no meaning yet.
--
-- The operator, 2026-09-27: *a word that isn't highlighted, or that has no
-- gloss, cannot be saved at all.* The standing ruling holds — **the app never
-- generates while a learner waits** — so a tap on a word with no
-- `video_glosses` row is written HERE, and a flag-gated worker job
-- (`WORD_GLOSS_JOB`) fills the meaning later and only then writes the cards.
--
-- **WHY A NEW TABLE, AND NOT ONE OF THE THREE THAT EXIST:**
--
-- * **Not `cards`.** Every row in `cards` is in the learner's deck —
--   `due_queue` filters on `user_id` and `due` and nothing else (W13-ii/2,
--   migration 023's header) — and `back`, `register` and `due` are NOT NULL
--   with no honest value for a word nobody has explained yet. **A gloss-less
--   row in `cards` is refused, for the reason recorded at W13-ii/2.**
-- * **Not a status column on `cards`.** Every deck reader would have to learn
--   to filter it, which is exactly the leak W13-ii/2 names.
-- * **Not `video_glosses`.** It is global per video — a candidate, not a
--   commitment — and has no learner. This row IS a commitment: *I want this
--   word*.
--
-- **User-keyed, referencing `users(id)`** (PRODUCT-PRINCIPLES §2), and
-- `ON DELETE CASCADE`: a learner's saved words are theirs and go with them.
-- The video is `RESTRICT`, as `video_assignments` is (019): videos are never
-- deleted, only purged, and the purge nulls text, not rows.
--
-- **`context_sentence` IS COPIED AT SAVE TIME** from `core.video.lines` — the
-- line the learner tapped — because the #335 purge nulls `videos.transcript`
-- after 30 days, and the job must not depend on text that may be gone.
CREATE TABLE word_saves_pending (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_id          BIGINT NOT NULL REFERENCES videos(id) ON DELETE RESTRICT,
    -- The tapped surface, casefolded, and the coverage lemma when it resolves:
    -- the gloss key is `lemma` when present, else `word` (see §2's comment).
    word              TEXT NOT NULL,
    lemma             TEXT,
    context_sentence  TEXT NOT NULL,
    -- NULL is the third state, never a zero (023's rule): no cues, no time.
    cue_start_s       NUMERIC(9,3),
    state             TEXT NOT NULL DEFAULT 'pending'
                      CHECK (state IN ('pending', 'carded', 'no_meaning')),
    -- Refusals so far. The job gives up at 3 (ruling Q6) and says so plainly.
    attempts          SMALLINT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at       TIMESTAMPTZ,
    CONSTRAINT word_saves_pending_resolved_iff_not_pending
        CHECK ((state = 'pending') = (resolved_at IS NULL)),
    CONSTRAINT word_saves_pending_one_per_word
        UNIQUE (user_id, video_id, word)
);

-- The job's read: the oldest open rows.
CREATE INDEX word_saves_pending_open
    ON word_saves_pending (created_at) WHERE state = 'pending';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. `video_glosses.l1` and `video_glosses.source`.
--
-- **`l1`** — the meaning in the learners' own languages, from the SAME
-- `explain` call as the English (ruling Q7): `{"fa": "…", "lt": "…"}`. Shown
-- in the word sheet only; card backs stay English. An object, or empty.
--
-- **`source`** — who asked for the gloss: `manual` (the operator's
-- `python -m core.video.explain --apply`), `pregen` (`VIDEO_PREGEN_GLOSSES`,
-- today's video) or `tap` (`WORD_GLOSS_JOB`, a learner's pending save). **The
-- two jobs have SEPARATE daily ceilings (C2: tap 60, pregen 40 per UTC day)
-- so pre-generation can never starve a learner's own taps**, and a ceiling
-- counted over every row could not tell them apart. Existing rows (none on
-- production) read `manual`.
ALTER TABLE video_glosses
    ADD COLUMN l1 JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual', 'pregen', 'tap'));

ALTER TABLE video_glosses
    ADD CONSTRAINT video_glosses_l1_is_an_object CHECK (jsonb_typeof(l1) = 'object');

-- The ceilings' count: rows of one source since midnight UTC.
CREATE INDEX video_glosses_by_source_and_time ON video_glosses (source, generated_at);

-- **THE KEY, RECONCILED (#468).** 023's comment on `word` says *"NOT a lemma"*,
-- while `core.video.explain` has always written `coverage.unknown_lemmas` —
-- the lemma when it resolves. From W31c the key is stated rather than implied:
-- **the coverage lemma when it resolves, else the casefolded surface**, and
-- the reader (`glosses.gloss_for`) tries the surface and then the same lemma.
-- 023's file is not edited (an applied migration is history); the column's
-- comment says what is true now.
COMMENT ON COLUMN video_glosses.word IS
    'The coverage lemma (core.lexicon.normalize.lemmatize) when it resolves, else the casefolded surface. Read by surface, then by lemma (W31c, #468).';
