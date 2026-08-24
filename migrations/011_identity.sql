-- 011_identity.sql — W4b. Identity stops being a Telegram id.
--
-- `users.telegram_user_id BIGINT PRIMARY KEY` was the identity of every learner
-- and 17 foreign keys pointed at it, so a person without a Telegram account
-- could not be represented at all (known issue #92, contradicting
-- docs/PRODUCT-PRINCIPLES.md §2). This file gives `users` a surrogate key,
-- demotes `telegram_user_id` to a nullable secondary identifier, and repoints
-- every child table.
--
-- WHAT THIS FILE DESTROYS: nothing. There is no DELETE, no DROP TABLE and no
-- DROP COLUMN anywhere below. It drops and recreates TWO primary keys
-- (`users_pkey`, `access_requests_pkey`) and 17 foreign keys, all inside the one
-- transaction core/db.py wraps every migration in. Because nothing is ever
-- deleted, the ON DELETE CASCADE on sixteen of those keys is never armed while
-- they are in flight.
--
-- WHY VALUES ARE REWRITTEN RATHER THAN SEEDED. `users.id` starts at 1 and is NOT
-- seeded from `telegram_user_id`. A seeded id would make `id == telegram_user_id`
-- for exactly the learners we test with and differ only for the first web user,
-- so a stray Telegram id passed where an internal id belongs would pass every
-- test and break months later. With fresh small ids the same mistake fails
-- immediately: a 10-digit value matches no `users.id` and the FK re-add below
-- aborts the whole transaction.
--
-- No explicit BEGIN/COMMIT (the runner owns the transaction) and no
-- CONCURRENTLY (illegal inside one).

-- ---------------------------------------------------------------
-- 1. Snapshot, per table AND per user.
--
-- A per-table total is preserved by a bug that swaps two learners' rows; a
-- per-user count is not. This is the check that matters, and it is taken before
-- a single value moves. `remapped = FALSE` marks the one table whose key is
-- preserved rather than rewritten.
-- ---------------------------------------------------------------
CREATE TEMP TABLE _w4b_before (
    tbl       TEXT   NOT NULL,
    old_uid   BIGINT,
    n         BIGINT NOT NULL,
    remapped  BOOLEAN NOT NULL
) ON COMMIT DROP;

INSERT INTO _w4b_before (tbl, old_uid, n, remapped)
             SELECT 'errors',                    user_id,        count(*), TRUE  FROM errors                    GROUP BY user_id
   UNION ALL SELECT 'chunks',                    user_id,        count(*), TRUE  FROM chunks                    GROUP BY user_id
   UNION ALL SELECT 'book_units',                user_id,        count(*), TRUE  FROM book_units                GROUP BY user_id
   UNION ALL SELECT 'sessions',                  user_id,        count(*), TRUE  FROM sessions                  GROUP BY user_id
   UNION ALL SELECT 'streaks',                   user_id,        count(*), TRUE  FROM streaks                   GROUP BY user_id
   UNION ALL SELECT 'interests',                 user_id,        count(*), TRUE  FROM interests                 GROUP BY user_id
   UNION ALL SELECT 'readings',                  user_id,        count(*), TRUE  FROM readings                  GROUP BY user_id
   UNION ALL SELECT 'couple_challenges',         winner_user_id, count(*), TRUE  FROM couple_challenges         GROUP BY winner_user_id
   UNION ALL SELECT 'couple_scores',             user_id,        count(*), TRUE  FROM couple_scores             GROUP BY user_id
   UNION ALL SELECT 'calibration_log',           user_id,        count(*), TRUE  FROM calibration_log           GROUP BY user_id
   UNION ALL SELECT 'bot_message_counts',        user_id,        count(*), TRUE  FROM bot_message_counts        GROUP BY user_id
   UNION ALL SELECT 'shared_content_deliveries', user_id,        count(*), TRUE  FROM shared_content_deliveries GROUP BY user_id
   UNION ALL SELECT 'auth_credentials',          user_id,        count(*), TRUE  FROM auth_credentials          GROUP BY user_id
   UNION ALL SELECT 'auth_sessions',             user_id,        count(*), TRUE  FROM auth_sessions             GROUP BY user_id
   UNION ALL SELECT 'auth_claim_tokens',         user_id,        count(*), TRUE  FROM auth_claim_tokens         GROUP BY user_id
   UNION ALL SELECT 'auth_challenges',           user_id,        count(*), TRUE  FROM auth_challenges           GROUP BY user_id
   UNION ALL SELECT 'user_lexemes',              user_id,        count(*), TRUE  FROM user_lexemes              GROUP BY user_id
   UNION ALL SELECT 'shared_content',            created_by,     count(*), TRUE  FROM shared_content            GROUP BY created_by
   UNION ALL SELECT 'access_requests',    telegram_user_id,      count(*), FALSE FROM access_requests    GROUP BY telegram_user_id
   UNION ALL SELECT 'users',              telegram_user_id,      count(*), FALSE FROM users              GROUP BY telegram_user_id;

-- ---------------------------------------------------------------
-- 2. users gains its surrogate key.
--
-- Appended last, so `SELECT u.*` in approved_onboarded_users keeps its existing
-- column order and CREATE OR REPLACE at step 8 only has to append (#48).
-- ---------------------------------------------------------------
ALTER TABLE users ADD COLUMN id BIGINT GENERATED ALWAYS AS IDENTITY;

-- ---------------------------------------------------------------
-- 3. Drop all 17 foreign keys.
--
-- Dropped and recreated rather than deferred: deferral cannot help when the
-- constraint's TARGET COLUMN is what changes.
-- ---------------------------------------------------------------
ALTER TABLE errors                    DROP CONSTRAINT errors_user_id_fkey;
ALTER TABLE chunks                    DROP CONSTRAINT chunks_user_id_fkey;
ALTER TABLE book_units                DROP CONSTRAINT book_units_user_id_fkey;
ALTER TABLE sessions                  DROP CONSTRAINT sessions_user_id_fkey;
ALTER TABLE streaks                   DROP CONSTRAINT streaks_user_id_fkey;
ALTER TABLE interests                 DROP CONSTRAINT interests_user_id_fkey;
ALTER TABLE readings                  DROP CONSTRAINT readings_user_id_fkey;
ALTER TABLE couple_challenges         DROP CONSTRAINT couple_challenges_winner_user_id_fkey;
ALTER TABLE couple_scores             DROP CONSTRAINT couple_scores_user_id_fkey;
ALTER TABLE calibration_log           DROP CONSTRAINT calibration_log_user_id_fkey;
ALTER TABLE bot_message_counts        DROP CONSTRAINT bot_message_counts_user_id_fkey;
ALTER TABLE shared_content_deliveries DROP CONSTRAINT shared_content_deliveries_user_id_fkey;
ALTER TABLE auth_credentials          DROP CONSTRAINT auth_credentials_user_id_fkey;
ALTER TABLE auth_sessions             DROP CONSTRAINT auth_sessions_user_id_fkey;
ALTER TABLE auth_claim_tokens         DROP CONSTRAINT auth_claim_tokens_user_id_fkey;
ALTER TABLE auth_challenges           DROP CONSTRAINT auth_challenges_user_id_fkey;
ALTER TABLE user_lexemes              DROP CONSTRAINT user_lexemes_user_id_fkey;

-- ---------------------------------------------------------------
-- 4. Rewrite every child value through the mapping.
--
-- NULL-preserving by construction: an inner-join UPDATE never touches a NULL
-- `couple_challenges.winner_user_id` or `auth_challenges.user_id`, which is
-- exactly right — no winner and no user is still no winner and no user.
--
-- A row that fails to map keeps its 10-digit Telegram value, matches no
-- `users.id`, and aborts at step 7's FK re-add. It cannot pass silently.
-- ---------------------------------------------------------------
UPDATE errors                    t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE chunks                    t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE book_units                t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE sessions                  t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE streaks                   t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE interests                 t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE readings                  t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE couple_challenges         t SET winner_user_id = u.id FROM users u WHERE t.winner_user_id = u.telegram_user_id;
UPDATE couple_scores             t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE calibration_log           t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE bot_message_counts        t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE shared_content_deliveries t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE auth_credentials          t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE auth_sessions             t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE auth_claim_tokens         t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE auth_challenges           t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;
UPDATE user_lexemes              t SET user_id        = u.id FROM users u WHERE t.user_id        = u.telegram_user_id;

-- shared_content.created_by carries a Telegram id and has never had a foreign
-- key. Rewriting the VALUES is required — a stale Telegram id here is silently
-- wrong the moment identity moves. Whether the constraint is ADDED is decided by
-- the pre-flight in the deploy runbook, not here: see step 7.
UPDATE shared_content            t SET created_by     = u.id FROM users u WHERE t.created_by     = u.telegram_user_id;

-- ---------------------------------------------------------------
-- 5. Move the users key.
--
-- DROP NOT NULL is issued explicitly. Whether the implicit NOT NULL survives a
-- primary-key drop is version-dependent, and relying on it is how a nullable
-- column turns out not to be.
-- ---------------------------------------------------------------
ALTER TABLE users DROP CONSTRAINT users_pkey;
ALTER TABLE users ADD  CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE users ALTER COLUMN telegram_user_id DROP NOT NULL;
ALTER TABLE users ADD  CONSTRAINT users_telegram_user_id_key UNIQUE (telegram_user_id);

-- Every row stays reachable by something an operator can type. Not an
-- unconditional NOT NULL on auth_email: the legacy rows would have to be
-- backfilled by hand, and a Telegram id is a perfectly good handle for them.
ALTER TABLE users ADD CONSTRAINT users_reachable
    CHECK (telegram_user_id IS NOT NULL OR auth_email IS NOT NULL);

-- ---------------------------------------------------------------
-- 6. Re-key access_requests.
--
-- Its telegram_user_id is the PRIMARY KEY (005), and a primary-key column is
-- NOT NULL by definition — `ALTER COLUMN ... DROP NOT NULL` on it errors. The
-- key has to move off it first, which is what makes the order below load-bearing
-- rather than stylistic.
--
-- Nothing in the schema references access_requests (verified: no
-- `REFERENCES access_requests` exists in any migration), so moving its key
-- disturbs no other table's constraints.
-- ---------------------------------------------------------------
ALTER TABLE access_requests ADD COLUMN id      BIGINT GENERATED ALWAYS AS IDENTITY;
ALTER TABLE access_requests ADD COLUMN user_id BIGINT;

-- Rows whose Telegram id has no users row keep user_id NULL. That is CORRECT,
-- not a failure: pending and declined requests are precisely what 005 exists to
-- hold, and they have no account by definition.
UPDATE access_requests ar SET user_id = u.id
  FROM users u WHERE u.telegram_user_id = ar.telegram_user_id;

ALTER TABLE access_requests DROP CONSTRAINT access_requests_pkey;
ALTER TABLE access_requests ADD  CONSTRAINT access_requests_pkey PRIMARY KEY (id);

-- Only legal now that the key has moved.
ALTER TABLE access_requests ALTER COLUMN telegram_user_id DROP NOT NULL;

-- Not cosmetic. access_control.request_access and users.save_onboarding both use
-- ON CONFLICT (telegram_user_id), which needs a unique constraint on that column
-- and would otherwise start failing at RUNTIME, after a green migration.
ALTER TABLE access_requests ADD CONSTRAINT access_requests_telegram_user_id_key
    UNIQUE (telegram_user_id);
ALTER TABLE access_requests ADD CONSTRAINT access_requests_user_id_key
    UNIQUE (user_id);
ALTER TABLE access_requests ADD CONSTRAINT access_requests_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE access_requests ADD CONSTRAINT access_requests_identified
    CHECK (telegram_user_id IS NOT NULL OR user_id IS NOT NULL);

-- ---------------------------------------------------------------
-- 7. Re-add the 17 foreign keys against users(id).
--
-- Each keeps its ORIGINAL ON DELETE semantics. Sixteen cascade;
-- couple_challenges.winner_user_id has always been NO ACTION, which is why a
-- DELETE FROM users errors today instead of quietly taking the challenge history
-- with it. Re-adding them uniformly would lose that, silently.
--
-- shared_content.created_by is deliberately NOT given a foreign key here. If any
-- value fails to map, adding it would abort this entire identity migration over
-- a column that is not identity-critical. The deploy runbook's pre-flight
-- decides; a follow-up migration adds the constraint if the answer is clean.
-- ---------------------------------------------------------------
ALTER TABLE errors                    ADD CONSTRAINT errors_user_id_fkey                    FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE chunks                    ADD CONSTRAINT chunks_user_id_fkey                    FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE book_units                ADD CONSTRAINT book_units_user_id_fkey                FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE sessions                  ADD CONSTRAINT sessions_user_id_fkey                  FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE streaks                   ADD CONSTRAINT streaks_user_id_fkey                   FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE interests                 ADD CONSTRAINT interests_user_id_fkey                 FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE readings                  ADD CONSTRAINT readings_user_id_fkey                  FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE couple_challenges         ADD CONSTRAINT couple_challenges_winner_user_id_fkey  FOREIGN KEY (winner_user_id) REFERENCES users(id);
ALTER TABLE couple_scores             ADD CONSTRAINT couple_scores_user_id_fkey             FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE calibration_log           ADD CONSTRAINT calibration_log_user_id_fkey           FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE bot_message_counts        ADD CONSTRAINT bot_message_counts_user_id_fkey        FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE shared_content_deliveries ADD CONSTRAINT shared_content_deliveries_user_id_fkey FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE auth_credentials          ADD CONSTRAINT auth_credentials_user_id_fkey          FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE auth_sessions             ADD CONSTRAINT auth_sessions_user_id_fkey             FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE auth_claim_tokens         ADD CONSTRAINT auth_claim_tokens_user_id_fkey         FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE auth_challenges           ADD CONSTRAINT auth_challenges_user_id_fkey           FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE user_lexemes              ADD CONSTRAINT user_lexemes_user_id_fkey              FOREIGN KEY (user_id)        REFERENCES users(id) ON DELETE CASCADE;

-- ---------------------------------------------------------------
-- 8. Recreate the delivery predicate (#48).
--
-- Mandatory here, because step 2 was an ALTER TABLE users and the view is
-- SELECT u.* — which freezes its column list at creation. CREATE OR REPLACE is
-- legal because `id` was APPENDED to users: the view's existing 21 columns keep
-- their names, types and order, and the replacement only adds a 22nd.
--
-- The join moves to ar.user_id = u.id. Without that, a learner with no Telegram
-- id could never appear in the single predicate every delivery list reads, which
-- is the whole point of the slice.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.user_id = u.id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';

-- ---------------------------------------------------------------
-- 9. Assert, and abort the whole transaction on any mismatch.
--
-- The FK re-add at step 7 already makes an unmapped row impossible. This is the
-- second net, and it is the one that catches a SWAP — two learners' rows
-- exchanged preserves every per-table total and fails here.
-- ---------------------------------------------------------------
DO $w4b$
DECLARE
    bad     RECORD;
    n_bad   BIGINT;
    msg     TEXT;
BEGIN
    CREATE TEMP TABLE _w4b_after (
        tbl  TEXT   NOT NULL,
        key  TEXT   NOT NULL,
        n    BIGINT NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO _w4b_after (tbl, key, n)
                 SELECT 'errors', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM errors                    GROUP BY user_id
       UNION ALL SELECT 'chunks', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM chunks                    GROUP BY user_id
       UNION ALL SELECT 'book_units', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM book_units                GROUP BY user_id
       UNION ALL SELECT 'sessions', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM sessions                  GROUP BY user_id
       UNION ALL SELECT 'streaks', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM streaks                   GROUP BY user_id
       UNION ALL SELECT 'interests', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM interests                 GROUP BY user_id
       UNION ALL SELECT 'readings', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM readings                  GROUP BY user_id
       UNION ALL SELECT 'couple_challenges', COALESCE(winner_user_id::TEXT,'~NULL~'), count(*) FROM couple_challenges         GROUP BY winner_user_id
       UNION ALL SELECT 'couple_scores', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM couple_scores             GROUP BY user_id
       UNION ALL SELECT 'calibration_log', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM calibration_log           GROUP BY user_id
       UNION ALL SELECT 'bot_message_counts', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM bot_message_counts        GROUP BY user_id
       UNION ALL SELECT 'shared_content_deliveries', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM shared_content_deliveries GROUP BY user_id
       UNION ALL SELECT 'auth_credentials', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM auth_credentials          GROUP BY user_id
       UNION ALL SELECT 'auth_sessions', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM auth_sessions             GROUP BY user_id
       UNION ALL SELECT 'auth_claim_tokens', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM auth_claim_tokens         GROUP BY user_id
       UNION ALL SELECT 'auth_challenges', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM auth_challenges           GROUP BY user_id
       UNION ALL SELECT 'user_lexemes', COALESCE(user_id::TEXT,'~NULL~'),        count(*) FROM user_lexemes              GROUP BY user_id
       UNION ALL SELECT 'shared_content', COALESCE(created_by::TEXT,'~NULL~'),     count(*) FROM shared_content            GROUP BY created_by
       UNION ALL SELECT 'access_requests', COALESCE(telegram_user_id::TEXT,'~NULL~'),      count(*) FROM access_requests    GROUP BY telegram_user_id
       UNION ALL SELECT 'users', COALESCE(telegram_user_id::TEXT,'~NULL~'),      count(*) FROM users              GROUP BY telegram_user_id;

    -- Keys are compared as TEXT with an explicit sentinel for NULL. The obvious
    -- spelling -- joining on IS NOT DISTINCT FROM -- cannot be hashed, so the
    -- planner falls back to a nested loop and the check goes quadratic in the
    -- number of distinct users. That is invisible on production's handful of
    -- rows and took 34 seconds on a dev database carrying test residue. A
    -- sentinel string cannot collide with a user id, so equality is both correct
    -- and hashable.
    CREATE TEMP TABLE _w4b_expect (
        tbl  TEXT   NOT NULL,
        key  TEXT   NOT NULL,
        n    BIGINT NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO _w4b_expect (tbl, key, n)
    SELECT b.tbl,
           COALESCE(
               CASE WHEN b.remapped THEN u.id ELSE b.old_uid END::TEXT,
               '~NULL~'),
           b.n
      FROM _w4b_before b
      LEFT JOIN users u
             ON b.remapped AND u.telegram_user_id = b.old_uid;

    ANALYZE _w4b_before;
    ANALYZE _w4b_after;
    ANALYZE _w4b_expect;

    -- 9a. Per-table totals.
    FOR bad IN
        SELECT COALESCE(e.tbl, a.tbl) AS tbl,
               COALESCE(e.total, 0)   AS before_n,
               COALESCE(a.total, 0)   AS after_n
          FROM (SELECT tbl, sum(n) AS total FROM _w4b_expect GROUP BY tbl) e
          FULL JOIN
               (SELECT tbl, sum(n) AS total FROM _w4b_after  GROUP BY tbl) a
            ON a.tbl = e.tbl
         WHERE COALESCE(e.total, -1) IS DISTINCT FROM COALESCE(a.total, -1)
    LOOP
        msg := 'W4b/011 ABORT: row count changed for ' || bad.tbl
            || ' (before ' || bad.before_n || ', after ' || bad.after_n || ')';
        RAISE EXCEPTION USING MESSAGE = msg;
    END LOOP;

    -- 9b. Per-user counts, mapped old -> new. This is the one that catches a
    -- swap: two learners' rows exchanged preserves every per-table total and
    -- fails here. FULL JOIN, so a user appearing after the migration who was not
    -- there before is caught as well as one who vanished.
    FOR bad IN
        SELECT COALESCE(e.tbl, a.tbl) AS tbl,
               COALESCE(e.key, a.key) AS key,
               COALESCE(e.n, 0)       AS before_n,
               COALESCE(a.n, 0)       AS after_n
          FROM _w4b_expect e
          FULL JOIN _w4b_after a ON a.tbl = e.tbl AND a.key = e.key
         WHERE COALESCE(e.n, 0) IS DISTINCT FROM COALESCE(a.n, 0)
    LOOP
        msg := 'W4b/011 ABORT: per-user count changed in ' || bad.tbl
            || ' for user key ' || bad.key
            || ' (before ' || bad.before_n || ', after ' || bad.after_n || ')';
        RAISE EXCEPTION USING MESSAGE = msg;
    END LOOP;

    -- 9c. Orphans. The FK re-add already guarantees this for the 17; the two
    -- unenforced columns are the reason the check is written out anyway.
    SELECT count(*) INTO n_bad
      FROM shared_content sc
      LEFT JOIN users u ON u.id = sc.created_by
     WHERE u.id IS NULL;
    IF n_bad > 0 THEN
        msg := 'W4b/011 ABORT: ' || n_bad
            || ' shared_content rows have a created_by matching no user';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;

    SELECT count(*) INTO n_bad
      FROM access_requests ar
      LEFT JOIN users u ON u.id = ar.user_id
     WHERE ar.user_id IS NOT NULL AND u.id IS NULL;
    IF n_bad > 0 THEN
        msg := 'W4b/011 ABORT: ' || n_bad
            || ' access_requests rows point at a user that does not exist';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;

    -- 9d. Every learner who had a Telegram id still resolves through it.
    SELECT count(*) INTO n_bad FROM users WHERE telegram_user_id IS NULL;
    IF n_bad > 0 THEN
        msg := 'W4b/011 ABORT: ' || n_bad
            || ' pre-existing users lost their telegram_user_id';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;
END
$w4b$;
