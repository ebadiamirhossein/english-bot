-- S18d: access approval (pending before users row) + single delivery predicate view
CREATE TABLE access_requests (
    telegram_user_id  BIGINT PRIMARY KEY,
    username          TEXT,
    display_name      TEXT,
    status            TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'declined', 'revoked')),
    decline_count     INTEGER NOT NULL DEFAULT 0,
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ
);

-- Existing learners stay approved without operator action
INSERT INTO access_requests (telegram_user_id, display_name, status, requested_at, resolved_at)
SELECT telegram_user_id, name, 'approved', created_at, created_at
  FROM users
ON CONFLICT DO NOTHING;

-- One delivery predicate — every bot-initiated list reads this, not raw users
CREATE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.telegram_user_id = u.telegram_user_id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';
