-- W10: the daily session. `sessions` gains the three columns the authoritative
-- table in docs/TASKS-v3-web.md reserves for this slice, plus the idempotency
-- guarantee that "the session opens each day" needs; `card_reviews` gains the
-- three columns #157's typed answer has nowhere else to live.
-- PRD §4.1, ARCHITECTURE §6.
--
-- Plain, non-idempotent DDL, per 009's note and 010's, 012's, 013's, 014's and
-- 015's: core.db.migrate wraps each file in one transaction and gates it on
-- schema_version, which is what makes a re-run impossible. Guards would only buy
-- the impression that a re-run is safe. This file writes NO schema_version row
-- -- the runner does that (core/db.py), and only 001 inserts one itself.
--
-- NOTHING IS SEEDED HERE, following 010, 013, 014 and 015. A daily session row
-- is created by `apps.worker.jobs.assign_daily` or, if that has not run, lazily
-- and idempotently by `GET /session/today`.
--
-- THIS FILE TAKES 016, WHICH IS THE NUMBER `docs/TASKS-v3-web.md`'s
-- authoritative table ALREADY ASSIGNS TO W10. Nothing is renumbered and that
-- table is deliberately unedited by this slice. W10b's plan takes 017 and owes
-- its own renumber at ITS implementation time, which is the fragility filed as
-- #185 -- a scheme that reserves numbers for unwritten slices. Recorded here so
-- a reader who arrives via #185 finds W10 named as the one case that cost
-- nothing.
--
-- #48 IS NOT TRIGGERED. There is no ALTER TABLE users in this file, so the
-- paired `CREATE OR REPLACE VIEW approved_onboarded_users` is not required and
-- is deliberately absent. Stated rather than omitted silently: #48 has recurred
-- because each case looked like the one where the rule did not apply, so the
-- rule being considered is recorded even when it does not fire.
--
-- #47 IS NOT TRIGGERED EITHER, and this one was checked rather than assumed.
-- `sessions.task_type` is a bare `TEXT NOT NULL` (001:107) with no CHECK, so the
-- new value 'daily' needs no constraint widened. That is the opposite of
-- `errors.source`, whose CHECK had to be widened once at 012 for the full v3
-- set.
--
-- PRODUCT-PRINCIPLES §2 position, in its POST-011 form. §2 stopped tracking
-- "the eventual identity migration" on 2026-08-24, when 011 met it and #92
-- closed. The rule is to confirm the keying and say so: `sessions.user_id`
-- (011:204) and `card_reviews.user_id` (013's composite FK through
-- `cards (id, user_id)`) BOTH already reference `users(id)`, and this file ADDS
-- NO USER-KEYED TABLE and no new dependency on a Telegram id.

-- ---------------------------------------------------------------
-- 1. sessions -- the three reserved columns
-- ---------------------------------------------------------------

-- The resume state, not a report. Holds per-block `state` and what was served,
-- so a phone locked mid-session reopens where it was.
--
-- `sessions.payload` is NOT reused for this, deliberately. It is v2's
-- per-task-type grab bag -- a Telegram message_id for `reading`, a pending list
-- for `fossil_sweep`, a turn count for `conversation` -- and overloading it
-- would make one column mean seven things and each reader guess which.
ALTER TABLE sessions ADD COLUMN block_breakdown JSONB;

-- Minutes of the session, COMPUTED SERVER-SIDE from delivered_at to
-- completed_at and clamped, never reported by the browser. #108 is the standing
-- lesson: `item_attempts.latency_ms` is the one value W6 wrote from a number the
-- client chose, and a phone put down mid-session produces a real-but-meaningless
-- figure. The ceiling is ten hours; anything past it is stored NULL rather than
-- as a lie.
ALTER TABLE sessions ADD COLUMN minutes INTEGER
    CONSTRAINT sessions_minutes_is_plausible
    CHECK (minutes IS NULL OR (minutes >= 0 AND minutes <= 600));

-- W10 WRITES NULL HERE, ALWAYS, and the column ships anyway.
--
-- PRD §9 and W19 own the effort weighting -- a spoken sentence must be worth
-- more than a tapped MCQ -- and inventing a scheme now would make the first
-- weeks of history incomparable with every week after it. Same reasoning that
-- left `item_attempts.grade` NULL at W6 rather than synthesising a 1-4 from a
-- boolean. The column exists so W19 has somewhere to backfill into.
ALTER TABLE sessions ADD COLUMN xp INTEGER
    CONSTRAINT sessions_xp_is_not_negative
    CHECK (xp IS NULL OR xp >= 0);

-- ---------------------------------------------------------------
-- 2. one daily session per learner per LOCAL date
-- ---------------------------------------------------------------
--
-- WHOSE DATE: THE LEARNER'S. `sessions.date` is the learner's local calendar
-- date, derived from `users.timezone` (001:27, DEFAULT 'Europe/Vilnius') through
-- `core.services.sessions.local_today(tz, now)` -- which is already how every
-- other `sessions.date` in this table is computed, across eleven task types.
--
-- UTC was the live alternative and is rejected for a concrete reason: `date`
-- would then mean the learner's day for `quiz`, `reading`, `diary` and eight
-- others and the SERVER's day for `daily`, in one column. A learner opening the
-- session at 00:30 Vilnius would get a row dated yesterday, sitting beside a
-- `reading` row dated today.
--
-- THIS INDEX ENFORCES ONE ROW PER DATE AND CANNOT TELL YOU THE DATE WAS
-- COMPUTED WRONGLY. That is why the convention above is written here rather
-- than left to the service, and why `core.services.sessions.today()` takes an
-- injected `now` that a boundary test can move across local midnight.
--
-- PARTIAL, not a plain UNIQUE (user_id, date): the other eleven task types
-- legitimately have several rows on one date -- two voice exchanges, a quiz and
-- a reading -- and a total UNIQUE would refuse every one of them. Same
-- instrument and same reasoning as 015's `cards_one_card_per_lemma`.
CREATE UNIQUE INDEX sessions_one_daily_per_user_per_date
    ON sessions (user_id, date)
 WHERE task_type = 'daily';

-- ---------------------------------------------------------------
-- 3. card_reviews -- what a typed answer leaves behind (#157)
-- ---------------------------------------------------------------
--
-- A DEPARTURE FROM THE AUTHORITATIVE TABLE, NAMED RATHER THAN ABSORBED. That
-- table describes 016 as "`sessions` extension: block_breakdown, minutes, xp"
-- and these three columns are not on it. #157 was ruled at W8e -- `production`
-- and `cloze` take a typed answer -- after the table row was written, and the
-- typed attempt has nowhere else to live: `card_reviews` is the append-only log
-- W7 built precisely because the individual grades are the thing that cannot be
-- re-derived. The alternative was a 017 in the same slice, which buys a file and
-- no clarity.

-- Which session this review happened in. NULLABLE, because `/review` is still
-- reachable outside a session (#160 keeps it reachable and takes away its
-- count), exactly as `item_attempts.session_id` is nullable because 012 named
-- free practice a first-class path.
--
-- ON DELETE SET NULL and not CASCADE: deleting a session must never delete the
-- reviews that happened inside it. The review is evidence about a learner; the
-- session is a container.
--
-- Shipped now rather than when W19 needs it, for the reason W7 gave about
-- `item_attempts`' six unread columns: adding a column later is one line, but
-- the months of history in between are blank exactly where the reader needs
-- them.
ALTER TABLE card_reviews ADD COLUMN session_id BIGINT
    REFERENCES sessions (id) ON DELETE SET NULL;

-- What the learner typed, VERBATIM and unnormalised. "What did they actually
-- type" cannot be recovered from "did it match", which is the same reason
-- `item_attempts.response_text` is stored raw.
--
-- This is NOT the error journal. CLAUDE.md §5 governs `errors`, and nothing here
-- writes one: a missed production card is a retrieval failure, not necessarily a
-- grammar error, and a wrong journal row is permanent damage.
ALTER TABLE card_reviews ADD COLUMN typed_response TEXT;

-- Whether that string folded onto the card's back through
-- `core.items.grading.equivalence_key`. RECOMPUTED SERVER-SIDE at grade time
-- from `typed_response`; the client never supplies it (#108's shape -- a verdict
-- from the browser is a verdict the browser can choose).
--
-- NULL means "no typed answer was taken", which is the whole of the deck today
-- for `recognition` cards -- #157's exemption, because a recognition card's
-- answer is a MEANING and `equivalence_key` folds variants of a known answer
-- rather than judging whether a paraphrase is the same definition.
ALTER TABLE card_reviews ADD COLUMN typed_matched BOOLEAN;

-- A verdict with nothing it was a verdict about is unreadable a month later.
ALTER TABLE card_reviews
    ADD CONSTRAINT card_reviews_a_verdict_needs_its_answer
    CHECK (typed_matched IS NULL OR typed_response IS NOT NULL);

CREATE INDEX idx_card_reviews_session ON card_reviews (session_id)
 WHERE session_id IS NOT NULL;
