-- W2: passkey authentication.
--
-- Plain, non-idempotent DDL throughout. PostgreSQL has no IF NOT EXISTS for
-- ADD CONSTRAINT, so a half-guarded file fails on its second statement anyway
-- and the guards would buy nothing but the impression that a re-run is safe.
-- core.db.migrate wraps each file in one transaction and gates it on
-- schema_version; that is what actually makes a re-run impossible.
--
-- Tables are namespaced auth_. `sessions` already exists and holds LEARNING
-- sessions; an auth table called `sessions` beside it is a trap.

-- ---------------------------------------------------------------
-- users — the three auth columns
-- ---------------------------------------------------------------
-- Both identifiers are nullable AND unique: PostgreSQL permits many NULLs in a
-- unique constraint, which is exactly the semantics wanted — a row with neither
-- is a Telegram-era user who has not enrolled.
ALTER TABLE users
    ADD COLUMN auth_user_id           UUID,
    ADD COLUMN auth_email             TEXT,
    ADD COLUMN l1_pronunciation_seed  JSONB;

ALTER TABLE users ADD CONSTRAINT users_auth_user_id_key UNIQUE (auth_user_id);
ALTER TABLE users ADD CONSTRAINT users_auth_email_key   UNIQUE (auth_email);

-- The service lowercases on both write and lookup. This makes the database
-- agree: an operator UPDATE with a capital letter fails loudly rather than
-- creating an address nobody can ever sign in with.
ALTER TABLE users ADD CONSTRAINT users_auth_email_lower
    CHECK (auth_email IS NULL OR auth_email = lower(auth_email));

-- l1_pronunciation_seed is inert until W14/W17 (PRD §2.5 per-L1 seeds), shape
--   {"contrasts": ["th/s", "w/v"], "source": "l1_default", "set_at": "..."}
-- It is added here because known issue #48 makes every ALTER TABLE users cost a
-- view recreate against the production journal; one inert nullable column in the
-- migration that is already recreating the view is cheaper than a second
-- users-ALTER later for one column.

-- ---------------------------------------------------------------
-- approved_onboarded_users — recreated in the SAME file (issue #48)
-- ---------------------------------------------------------------
-- Body byte-identical to 005_access_requests.sql. This works because CREATE OR
-- REPLACE VIEW may ADD columns to the end of a view's column list (it may not
-- rename, reorder or retype existing ones), SELECT u.* re-expands at replace
-- time, and ADD COLUMN appends to users. Hence the ALTER above must come first,
-- and nothing in this file may reorder users.
CREATE OR REPLACE VIEW approved_onboarded_users AS
SELECT u.*
  FROM users u
  INNER JOIN access_requests ar
          ON ar.telegram_user_id = u.telegram_user_id
 WHERE u.onboarded = TRUE
   AND ar.status = 'approved';

-- ---------------------------------------------------------------
-- auth_credentials — one row per passkey, MANY per user
-- ---------------------------------------------------------------
-- Two learners x (phone + laptop) is four credentials before anyone does
-- anything unusual. A one-credential-per-user schema is wrong on day one.
CREATE TABLE auth_credentials (
    credential_id           BYTEA PRIMARY KEY,      -- raw bytes, not base64url
    user_id                 BIGINT NOT NULL
                              REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    public_key              BYTEA NOT NULL,         -- COSE
    sign_count              BIGINT NOT NULL DEFAULT 0,
    transports              TEXT[],
    aaguid                  TEXT,
    -- py_webauthn 2.8 reports these as credential_device_type
    -- ('single_device' | 'multi_device') and credential_backed_up.
    credential_device_type  TEXT,
    backed_up               BOOLEAN,
    nickname                TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at            TIMESTAMPTZ
);
CREATE INDEX idx_auth_credentials_user ON auth_credentials(user_id);

-- ---------------------------------------------------------------
-- auth_sessions — the browser session behind the cookie
-- ---------------------------------------------------------------
-- token_hash is sha256 of the raw cookie value. The raw value exists ONLY in
-- the cookie; a database disclosure yields nothing usable.
CREATE TABLE auth_sessions (
    token_hash    BYTEA PRIMARY KEY,
    user_id       BIGINT NOT NULL
                    REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    credential_id BYTEA REFERENCES auth_credentials(credential_id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at    TIMESTAMPTZ
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

-- ---------------------------------------------------------------
-- auth_claim_tokens — the first-enrolment gate
-- ---------------------------------------------------------------
-- With no email channel a pre-seeded auth_email is not an authentication
-- factor: if typing an existing address were sufficient, whoever typed it first
-- would own the error journal behind it.
CREATE TABLE auth_claim_tokens (
    token_hash         BYTEA PRIMARY KEY,
    user_id            BIGINT NOT NULL
                         REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ NOT NULL,
    used_at            TIMESTAMPTZ,
    used_credential_id BYTEA
);
CREATE INDEX idx_auth_claim_tokens_user ON auth_claim_tokens(user_id);

-- ---------------------------------------------------------------
-- auth_challenges — in-flight ceremonies
-- ---------------------------------------------------------------
-- In Postgres, never in process memory: english-api runs uvicorn --workers 2,
-- and a module-level dict works perfectly on one laptop process while failing
-- roughly half of all real ceremonies.
CREATE TABLE auth_challenges (
    challenge    BYTEA PRIMARY KEY,
    ceremony     TEXT NOT NULL
                   CHECK (ceremony IN ('registration', 'authentication')),
    user_id      BIGINT REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    auth_user_id UUID,                 -- registration only: the handle to be written
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    consumed_at  TIMESTAMPTZ
);
CREATE INDEX idx_auth_challenges_expiry ON auth_challenges(expires_at);

-- ---------------------------------------------------------------
-- auth_rate_limits — two learners, one public surface, no email verification
-- ---------------------------------------------------------------
-- One table holds both halves: the per-client key is
--   sha256(salt || client_ip || route)
-- and the global key is
--   sha256(salt || 'global' || route)
-- A HASH, never a raw IP: CLAUDE.md §5 keeps personal data out of the record,
-- and a salted digest is enough to count with.
CREATE TABLE auth_rate_limits (
    bucket       TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0
);
