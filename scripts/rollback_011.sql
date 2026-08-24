-- rollback_011.sql — reverse W4b's identity re-key.
--
--   psql "$DATABASE_URL" --single-transaction -v ON_ERROR_STOP=1 \
--        -f scripts/rollback_011.sql
--
-- --single-transaction is not optional. This file moves two primary keys, and a
-- run that stops half way leaves the database in a state neither schema
-- describes -- worse than not rolling back at all.
--
-- WHAT THIS RESTORES: the exact pre-011 shape. `users` keyed on
-- telegram_user_id, `access_requests` keyed on telegram_user_id, both surrogate
-- ids gone, all 17 foreign keys back on users(telegram_user_id) with their
-- ORIGINAL ON DELETE semantics, and the view recreated as 005/009 wrote it.
-- Nothing here falls back to restore-from-dump: every value 011 overwrote is
-- recoverable from a column 011 preserved.
--
-- WHEN IT STOPS BEING AN OPTION: the moment a Telegram-less user or a
-- web-originated access request exists. Both are unrepresentable in the old
-- schema, so rolling back would have to invent or discard them. The guard below
-- refuses rather than choosing. After that point the only path is a restore from
-- the pre-migration dump.

-- ---------------------------------------------------------------
-- 0. The guard. Both halves, because both tables gained the ability to hold a
--    row the old schema cannot express.
-- ---------------------------------------------------------------
DO $g$
DECLARE n BIGINT; msg TEXT;
BEGIN
    SELECT count(*) INTO n FROM users WHERE telegram_user_id IS NULL;
    IF n > 0 THEN
        msg := 'rollback_011 REFUSED: ' || n || ' users have no telegram_user_id. '
            || 'They cannot exist in the pre-011 schema. Restore from the '
            || 'pre-migration dump instead.';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;

    SELECT count(*) INTO n FROM access_requests WHERE telegram_user_id IS NULL;
    IF n > 0 THEN
        msg := 'rollback_011 REFUSED: ' || n || ' access_requests rows have no '
            || 'telegram_user_id (web-originated). They cannot exist in the '
            || 'pre-011 schema. Restore from the pre-migration dump instead.';
        RAISE EXCEPTION USING MESSAGE = msg;
    END IF;
END
$g$;

-- ---------------------------------------------------------------
-- 1. Drop the view first: it joins on access_requests.user_id, which goes away
--    below. CREATE OR REPLACE cannot drop the trailing `id` column that 011
--    appended, so this is a genuine DROP and recreate rather than a replace.
--    Ten call sites read it and none names a column, so nothing outside this
--    transaction sees the gap.
-- ---------------------------------------------------------------
DROP VIEW approved_onboarded_users;

-- ---------------------------------------------------------------
-- 2. Drop every foreign key pointing at users(id).
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
ALTER TABLE access_requests           DROP CONSTRAINT access_requests_user_id_fkey;

-- shared_content.created_by only has a foreign key if the pre-flight in the
-- deploy runbook came back clean and a follow-up migration added one. Tested by
-- name rather than assumed either way.
DO $sc$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
                WHERE conname = 'shared_content_created_by_fkey'
                  AND conrelid = 'shared_content'::regclass) THEN
        ALTER TABLE shared_content DROP CONSTRAINT shared_content_created_by_fkey;
    END IF;
END
$sc$;

-- ---------------------------------------------------------------
-- 3. Map every child value back through users.id -> users.telegram_user_id.
--    NULL-preserving for the same reason 011's forward pass was: an inner-join
--    UPDATE never touches a NULL winner or a NULL challenge user.
-- ---------------------------------------------------------------
UPDATE errors                    t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE chunks                    t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE book_units                t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE sessions                  t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE streaks                   t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE interests                 t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE readings                  t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE couple_challenges         t SET winner_user_id = u.telegram_user_id FROM users u WHERE t.winner_user_id = u.id;
UPDATE couple_scores             t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE calibration_log           t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE bot_message_counts        t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE shared_content_deliveries t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE auth_credentials          t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE auth_sessions             t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE auth_claim_tokens         t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE auth_challenges           t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE user_lexemes              t SET user_id        = u.telegram_user_id FROM users u WHERE t.user_id        = u.id;
UPDATE shared_content            t SET created_by     = u.telegram_user_id FROM users u WHERE t.created_by     = u.id;

-- ---------------------------------------------------------------
-- 4. users: key back onto telegram_user_id, surrogate gone.
-- ---------------------------------------------------------------
ALTER TABLE users DROP CONSTRAINT users_reachable;
ALTER TABLE users DROP CONSTRAINT users_telegram_user_id_key;
ALTER TABLE users ALTER COLUMN telegram_user_id SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_pkey;
ALTER TABLE users ADD  CONSTRAINT users_pkey PRIMARY KEY (telegram_user_id);
ALTER TABLE users DROP COLUMN id;

-- ---------------------------------------------------------------
-- 5. access_requests: key back onto telegram_user_id, both added columns gone.
--    access_requests_telegram_user_id_key is dropped too -- 005 never had it,
--    and the primary key supplies the uniqueness that ON CONFLICT needs.
-- ---------------------------------------------------------------
ALTER TABLE access_requests DROP CONSTRAINT access_requests_identified;
ALTER TABLE access_requests DROP CONSTRAINT access_requests_user_id_key;
ALTER TABLE access_requests DROP CONSTRAINT access_requests_telegram_user_id_key;
ALTER TABLE access_requests DROP CONSTRAINT access_requests_pkey;
ALTER TABLE access_requests ALTER COLUMN telegram_user_id SET NOT NULL;
ALTER TABLE access_requests ADD  CONSTRAINT access_requests_pkey PRIMARY KEY (telegram_user_id);
ALTER TABLE access_requests DROP COLUMN user_id;
ALTER TABLE access_requests DROP COLUMN id;

-- ---------------------------------------------------------------
-- 6. Re-add all 17 foreign keys against users(telegram_user_id), each with the
--    ON DELETE semantics it had before 011. Sixteen cascade; couple_challenges
--    is NO ACTION and always was -- re-adding them uniformly would silently
--    convert a DELETE FROM users from "errors" into "takes the challenge
--    history with it".
-- ---------------------------------------------------------------
ALTER TABLE errors                    ADD CONSTRAINT errors_user_id_fkey                    FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE chunks                    ADD CONSTRAINT chunks_user_id_fkey                    FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE book_units                ADD CONSTRAINT book_units_user_id_fkey                FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE sessions                  ADD CONSTRAINT sessions_user_id_fkey                  FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE streaks                   ADD CONSTRAINT streaks_user_id_fkey                   FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE interests                 ADD CONSTRAINT interests_user_id_fkey                 FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE readings                  ADD CONSTRAINT readings_user_id_fkey                  FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE couple_challenges         ADD CONSTRAINT couple_challenges_winner_user_id_fkey  FOREIGN KEY (winner_user_id) REFERENCES users(telegram_user_id);
ALTER TABLE couple_scores             ADD CONSTRAINT couple_scores_user_id_fkey             FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE calibration_log           ADD CONSTRAINT calibration_log_user_id_fkey           FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE bot_message_counts        ADD CONSTRAINT bot_message_counts_user_id_fkey        FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE shared_content_deliveries ADD CONSTRAINT shared_content_deliveries_user_id_fkey FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE auth_credentials          ADD CONSTRAINT auth_credentials_user_id_fkey          FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE auth_sessions             ADD CONSTRAINT auth_sessions_user_id_fkey             FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE auth_claim_tokens         ADD CONSTRAINT auth_claim_tokens_user_id_fkey         FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE auth_challenges           ADD CONSTRAINT auth_challenges_user_id_fkey           FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;
ALTER TABLE user_lexemes              ADD CONSTRAINT user_lexemes_user_id_fkey              FOREIGN KEY (user_id)        REFERENCES users(telegram_user_id) ON DELETE CASCADE;

-- ---------------------------------------------------------------
-- 7. Recreate the view exactly as 005 and 009 wrote it.
-- ---------------------------------------------------------------
CREATE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.telegram_user_id = u.telegram_user_id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';

-- ---------------------------------------------------------------
-- 8. Un-stamp the version, so `core.db status` reports the truth and a later
--    `migrate` re-applies 011 rather than skipping it.
-- ---------------------------------------------------------------
DELETE FROM schema_version WHERE version = 11;
