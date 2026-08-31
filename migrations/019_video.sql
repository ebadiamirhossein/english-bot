-- W12b: the video pipeline's three tables. `videos`, `video_coverage`,
-- `video_assignments`.
--
-- Plain, non-idempotent DDL, per 009's note and 010's, 012's, 013's, 014's,
-- 015's, 016's, 017's and 018's: core.db.migrate wraps each file in one
-- transaction and gates it on schema_version, which is what makes a re-run
-- impossible. Guards would only buy the impression that a re-run is safe. This
-- file writes NO schema_version row -- the runner does that (core/db.py), and
-- only 001 inserts one itself.
--
-- NOTHING IS SEEDED HERE. The channel pool is `data/video_channels.json`, read
-- by core.video.channels, and no part of it enters the database except as the
-- `channel_id`, `accent` and `track` of a video the refresh path fetched.
--
-- ---------------------------------------------------------------
-- #185, SIXTH OCCURRENCE. THE NUMBER IS TAKEN IN THIS COMMIT.
-- ---------------------------------------------------------------
-- Not when W12b was planned, and not when W12 was split. 018 (W11) is the
-- highest applied version; the authoritative table in docs/TASKS-v3-web.md runs
-- 019 W12b -> 020 W13a -> 021 W14 -> 022 W18 and is unchanged by this file.
--
-- THAT TABLE GAINS A THIRD TABLE NAME IN THIS SAME COMMIT. It reads
-- "`videos`, `video_assignments`" and this file ships THREE tables. A file
-- shipping a table the authoritative table does not know about is #49's defect,
-- and that table is declared to win any disagreement -- so it is corrected here
-- rather than left for whoever notices next.
--
-- ---------------------------------------------------------------
-- TYPES, AND A CLAIM THAT WAS WITHDRAWN ON MEASUREMENT
-- ---------------------------------------------------------------
-- `users.id` is BIGINT GENERATED ALWAYS AS IDENTITY (011:71, made the primary
-- key at 011:139), so every `user_id` here is BIGINT. `SERIAL` appears in NO
-- migration in this repository; the house idiom is
-- `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` (013:42, 014:197) and it is
-- followed rather than extended with a third convention.
--
-- The plan's first draft wrote `user_id INTEGER` and justified the correction by
-- claiming the mismatch "would have failed at CREATE TABLE, not silently."
-- THAT CLAIM IS FALSE AND WAS WITHDRAWN AFTER BEING RUN. PostgreSQL requires the
-- referencing and referenced types to be COMPARABLE, not identical:
--
--     CREATE TABLE p (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);
--     CREATE TABLE c (parent_id INTEGER REFERENCES p(id));
--
-- both succeed -- measured on PostgreSQL 16.14 on 2026-08-31, inside a
-- transaction that was rolled back. The consequence of the mismatch is the
-- SILENT kind: it can prevent index use on joins. That is worse than the failure
-- that was asserted, not better. Recorded here because a behavioural claim
-- nobody ran is exactly the family this record keeps re-filing, and because the
-- correct type below rests on the house convention above and never on the
-- withdrawn claim.
--
-- ---------------------------------------------------------------
-- #48 IS NOT TRIGGERED
-- ---------------------------------------------------------------
-- There is no ALTER TABLE users in this file, so the paired
-- `CREATE OR REPLACE VIEW approved_onboarded_users` is not required and is
-- deliberately absent. Stated rather than omitted silently: #48 has recurred
-- because each case looked like the one where the rule did not apply, so the
-- rule being considered is recorded even when it does not fire.
--
-- ---------------------------------------------------------------
-- PRODUCT-PRINCIPLES §2 and §3
-- ---------------------------------------------------------------
-- §2, which every slice adding a user-keyed table must state. Identity was
-- re-keyed by migration 011 on 2026-08-24: `users.id` is the surrogate key,
-- `telegram_user_id` a nullable unique secondary, and #92 is closed. The two
-- user-keyed tables here -- `video_coverage` and `video_assignments` --
-- reference `users(id)` directly and carry no Telegram id, so they ENLARGE NO
-- FUTURE MIGRATION. The pre-011 "this enlarges the eventual migration" clause is
-- deliberately NOT written: §2 records that W8 nearly wrote it into a document
-- that had already been overtaken, and calls that #82's pattern in a fourth
-- document.
--   `videos` HAS NO user_id AT ALL. The candidate pool is shared between both
-- learners, on migration 014's reasoning for `syllabus_unit_lexemes`: the
-- per-learner number is computed against a shared pool rather than stored per
-- learner on the pool itself.
--
-- §3, which requires a flag when data materialises per-user rows that could be
-- computed. `video_coverage` IS such a table and the flag is raised here.
--
--   IT IS AN AUDIT RECORD AND IT IS NOT A CACHE. It is never read back:
--   `core.video.assign` recomputes coverage on every run. It therefore has NO
--   INVALIDATION RULE, and that is the honest statement rather than a rule
--   nothing consults -- a guarantee nobody checks is a family this record has
--   already filed repeatedly, most recently at #281.
--
--   `lexicon_digest` is PROVENANCE, not an invalidation key. Recomputation over
--   stored text is pure CPU and costs no external call, so the staleness class
--   is REMOVED rather than managed; the digest exists so a number already
--   written can be told apart from one produced by a different instrument.
--   W12a is exactly that event -- it moved a real transcript 88.24% -> 75.76% --
--   and every coverage figure recorded before it means something else.
--
-- `data/video_channels.json` is the other §3 flag, and it is not a table: it is
-- GLOBAL CONFIGURATION THAT BECOMES PER-USER IF THE TWO LEARNERS' INTERESTS
-- DIVERGE. Today both share the pool and `users.track_weights` does the
-- per-learner work. When it diverges it gains a users-keyed table, not a second
-- file. Flagged at the moment of the choice, as §3 requires.
--
-- ---------------------------------------------------------------
-- OPERATOR RULING, 2026-08-30: THE FULL VIDEO IS SHOWN, NOT A SEGMENT
-- ---------------------------------------------------------------
-- In the operator's words: cutting part of a video out leaves the learner
-- without the topic, and a learner who does not understand the subject learns
-- nothing from clean audio. PRD §7.2's "return one 3-minute segment, not a whole
-- video" is overruled and corrected in place in this same commit, with the old
-- text quoted there rather than deleted.
--   So there is NO segment_start_s and NO segment_end_s here.
-- `video_assignments` carries a RESUME POSITION instead, coverage is computed
-- over the whole transcript, and `length_fit` still prefers shorter videos but
-- feeds no segment chooser. ARCHITECTURE §5 lists "segment start/end" on this
-- table and is corrected in the same commit.
--
-- ---------------------------------------------------------------
-- THE 30-DAY CLOCK, AND WHAT IT IS AND IS NOT
-- ---------------------------------------------------------------
-- This is a category distinction, and getting it wrong in the obvious direction
-- would leave a false permission in the record, so it is stated at length.
--
-- Developer Policies §III.E.4.d caps "Non-Authorized Data", which the same
-- document DEFINES as "API Data accessible by an API Client without User
-- Credentials". It governs the YouTube METADATA stored here -- `title`,
-- `duration_s`, `published_at` -- and the purge covers them for that reason.
--
-- A SCRAPED TRANSCRIPT IS NOT API DATA. Under the operator's ruling of
-- 2026-08-30 it is obtained outside the API entirely, which is precisely why the
-- licence gate refused the API route: `captions.download` requires permission to
-- edit the video, and `captions.list` requires OAuth and returns no caption
-- text, so no licit route to a third party's captions exists at any permission
-- level.
--
-- THE PURGE IS EXTENDED TO `transcript` AS CONSERVATIVE POLICY -- because
-- storing scraped text indefinitely is worse than storing it briefly -- AND NOT
-- AS §III.E.4.d COMPLIANCE, because that clause does not reach it. Written out
-- because a reader who finds the purge and not this paragraph concludes
-- §III.E.4.d licenses transcript caching for thirty days, which is the OPPOSITE
-- of what the gate found. The verbatim clauses are in `data/LICENCES.md`.
--
-- `youtube_id` AND `video_assignments` SURVIVE THE PURGE. A video id is a public
-- identifier the learner reads off the URL, and the purge exists to bound stored
-- CONTENT; nulling them would destroy `seen_penalty` and the learner's own
-- history for no compliance gain.
--
-- A POOL THAT IS NOT REFRESHED EMPTIES ITSELF. There is no cron, no timer and no
-- worker -- the CLIs are human-run by operator ruling, and Apify bills per run --
-- so thirty-one days without a refresh leaves nothing selectable. That is why
-- `core.video.assign` REFUSES LOUDLY rather than assigning fewer than three.

-- ---------------------------------------------------------------
-- 1. videos -- the shared candidate pool
-- ---------------------------------------------------------------
CREATE TABLE videos (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    youtube_id            TEXT NOT NULL UNIQUE,
    channel_id            TEXT NOT NULL,

    -- AUTHORED ON THE CHANNEL ENTRY, NEVER INFERRED FROM THE VIDEO. Two values
    -- only, by operator ruling: two accents that are actually rotated beat six
    -- with no channels behind them. Adding a third later is a DATA change -- one
    -- value in video_channels.json and one literal in this CHECK -- and no
    -- selection logic moves.
    accent                TEXT NOT NULL CHECK (accent IN ('american','british')),

    -- The same vocabulary as `users.track_weights` (migration 012, whose default
    -- is '{"life": 50, "curiosity": 30, "work": 20}'), so `topic_match` compares
    -- like with like instead of translating between two spellings of a track.
    track                 TEXT NOT NULL CHECK (track IN ('life','curiosity','work')),

    -- YouTube metadata. §III.E.4.d reaches THESE, and the purge nulls them.
    title                 TEXT,
    duration_s            INTEGER,
    published_at          TIMESTAMPTZ,

    -- Scraped, not API data. Purged as policy, not as compliance (see above).
    transcript            TEXT,
    transcript_lang       TEXT,

    -- IT HOLDS A KIND, WHICH IS WHY IT IS NOT CALLED `captions_type`.
    -- ARCHITECTURE §5 carries that name today and is corrected in this commit.
    -- A scanner enforces the FORM of a claim and not its truth, so a column
    -- holding a presence flag must not wear a kind's name. This one is created
    -- ONLY because the ruled actor genuinely reports the distinction, and
    -- reports it FREE: johnvc/YoutubeTranscripts takes transcript_type
    -- any|manual|generated, and its list_only mode returns each track's
    -- manual/generated status without charging a transcript event. Had no actor
    -- reported a kind, this column would not exist and PRD §7.2's "prefer
    -- human-written captions" would be FILED UNMET rather than worked around.
    --
    -- It is load-bearing beyond preference. core/lexicon/coverage.py switches the
    -- proper-noun rule OFF when casing is not conventional, and auto-generated
    -- captions are typically entirely lowercase -- so on a `generated` track the
    -- names sitting inside the top-2,000 frequency floor are counted KNOWN and
    -- coverage reads HIGH, the drowning direction (#288). On a `manual` track the
    -- rule fires and the same names are excluded. THE CAPTION KIND DECIDES WHICH
    -- COVERAGE ALGORITHM RUNS.
    captions_kind         TEXT CHECK (captions_kind IN ('manual','generated')),

    -- The retry-and-skip path. The actor is community-maintained, scrapers fail
    -- intermittently and YouTube challenges datacentre IPs, so a pipeline that
    -- stops on one failure is a pipeline that stops. `failed` is retryable and
    -- `unavailable` is terminal (the video has no captions at all); only `ok` is
    -- selectable, and a refresh run continues past every failure and prints a
    -- failure table rather than aborting halfway and leaving a pool that looks
    -- complete and is not.
    transcript_status     TEXT NOT NULL DEFAULT 'pending'
                          CHECK (transcript_status IN
                                 ('pending','ok','failed','unavailable')),
    transcript_attempts   SMALLINT NOT NULL DEFAULT 0,
    transcript_last_error TEXT,

    -- The 30-day clock. Set on every refresh that re-reads this video; a row
    -- older than thirty days has its metadata and transcript nulled by the next
    -- refresh run and returns to `pending`.
    metadata_refreshed_at TIMESTAMPTZ NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Selection asks for "candidates in this track and accent WITH A USABLE
-- TRANSCRIPT", so the index is partial on the state selection actually filters
-- by. An index on (track, accent) alone would carry every pending and failed row
-- as well, which is most of the table for as long as the pool is being built.
CREATE INDEX idx_videos_selectable ON videos (track, accent)
    WHERE transcript_status = 'ok';

-- The purge sweep's own predicate.
CREATE INDEX idx_videos_refreshed ON videos (metadata_refreshed_at);

-- ---------------------------------------------------------------
-- 2. video_coverage -- per learner x per video. AN AUDIT RECORD, NOT A CACHE.
-- ---------------------------------------------------------------
-- ARCHITECTURE §5 puts this on the `videos` row as a "coverage cache" column.
-- §5 is WRONG and is corrected in this same commit, named rather than quietly
-- reconciled: coverage is a fact about a learner AND a video, so a column on a
-- global row would have to mean one of the two learners' numbers.
CREATE TABLE video_coverage (
    user_id               BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_id              BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,

    coverage              NUMERIC(5,4) NOT NULL,
    counted_tokens        INTEGER NOT NULL,
    excluded_tokens       INTEGER NOT NULL,

    -- Straight off CoverageReport, and the reason this is stored at all rather
    -- than only displayed: a number computed with the proper-noun rule switched
    -- off is a DIFFERENT NUMBER, and without these two columns a stored 94% and
    -- a real 94% are indistinguishable in the very table selection reads.
    proper_nouns_detected BOOLEAN NOT NULL,
    casing                TEXT NOT NULL,

    -- PROVENANCE. See the §3 note in the header: nothing reads this table back,
    -- so nothing can be invalidated by this column. It is a digest of the
    -- lemmatiser's own inputs -- core/lexicon/normalize.py, data/lexemes.tsv and
    -- data/inflections.tsv -- so a row can be told apart from one produced by a
    -- different instrument.
    lexicon_digest        TEXT NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, video_id)
);

-- ---------------------------------------------------------------
-- 3. video_assignments -- user x video x date
-- ---------------------------------------------------------------
CREATE TABLE video_assignments (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- RESTRICT, not CASCADE, and the asymmetry with the line above is
    -- deliberate. The purge NULLS CONTENT AND NEVER DELETES ROWS, so nothing in
    -- this slice should ever delete a `videos` row -- but a cascade here would
    -- mean that the first time somebody later does, a learner's history goes
    -- with it silently. Deleting the USER is a different matter: their rows
    -- should go, which is why that side cascades.
    video_id          BIGINT NOT NULL REFERENCES videos(id) ON DELETE RESTRICT,

    assigned_for      DATE NOT NULL,

    -- OPERATOR RULING: the full video is shown. This is where the LEARNER
    -- stopped, not where a chooser cut. 0 until W13's player writes it.
    resume_position_s INTEGER NOT NULL DEFAULT 0,

    -- W12b DOES NOT DEFINE WHAT "ANSWERED" MEANS FOR BLOCK 2. No player exists,
    -- so no watch signal can be written, and a definition written now would be a
    -- guess pinned in a schema. That obligation is W13's, and block 2's `input`
    -- stays `empty` until then. THIS COLUMN HAS NO WRITER IN THIS SLICE,
    -- deliberately.
    completed_at      TIMESTAMPTZ,

    -- Why this video won: the five terms and the penalty as they were scored. So
    -- a bad assignment is diagnosable WITHOUT re-running selection against a pool
    -- that has since been refreshed or purged -- by which time the inputs that
    -- produced it are gone.
    score_breakdown   JSONB NOT NULL,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One assigned video per learner per date. The same shape 018 gave the
    -- checkpoint, and for the same reason: the learner opens the day and finds
    -- one thing, not a choice.
    UNIQUE (user_id, assigned_for)
);

-- `seen_penalty` asks "has this learner had this video before?" of every
-- candidate on every assign run.
CREATE INDEX idx_video_assignments_seen ON video_assignments (user_id, video_id);
