-- 001_init.sql — English Learning System (PostgreSQL / Supabase)
-- Version 2.1 · 31 July 2026
-- Use this file INSTEAD of the SQLite version if using Supabase.

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- users
-- Nothing here is hardcoded to a specific language or country.
-- ---------------------------------------------------------------
CREATE TABLE users (
    telegram_user_id                BIGINT PRIMARY KEY,
    tenant_id                       INTEGER DEFAULT 1,
    plan                            TEXT DEFAULT 'owner',       -- owner|free|paid
    name                            TEXT NOT NULL,
    native_language                 TEXT NOT NULL,              -- 'fa','lt','es'
    target_language                 TEXT DEFAULT 'en',
    explanation_language_fallback   BOOLEAN DEFAULT TRUE,
    cefr_level                      TEXT DEFAULT 'B1',
    efset_baseline                  INTEGER,
    work_domain                     TEXT,
    why_statement                   TEXT,
    track_weights                   JSONB DEFAULT '{"work":40,"life":40,"curiosity":20}'::jsonb,
    timezone                        TEXT DEFAULT 'Europe/Vilnius',
    morning_time                    TIME DEFAULT '08:00',
    evening_time                    TIME DEFAULT '21:00',
    paused_until                    DATE,
    onboarded                       BOOLEAN DEFAULT FALSE,
    created_at                      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- error taxonomy (fixed list — the LLM must choose from this only)
-- ---------------------------------------------------------------
CREATE TABLE error_types (
    code            TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    murphy_units    TEXT
);

-- ---------------------------------------------------------------
-- errors — the core asset of the product
-- ---------------------------------------------------------------
CREATE TABLE errors (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT NOT NULL CHECK (source IN
                          ('quiz','voice','text','reading','diary','capture')),
    you_said            TEXT NOT NULL,
    correct_form        TEXT NOT NULL,
    error_type          TEXT NOT NULL REFERENCES error_types(code),
    explanation         TEXT,
    murphy_units        TEXT,
    times_wrong         INTEGER DEFAULT 1,
    times_right         INTEGER DEFAULT 0,
    streak_right        INTEGER DEFAULT 0,      -- 5 consecutive + 21 days => resolved
    next_review         DATE NOT NULL,
    resolved            BOOLEAN DEFAULT FALSE,
    resolved_at         DATE,
    unresolved_count    INTEGER DEFAULT 0       -- times it came back (M13)
);
CREATE INDEX idx_errors_due  ON errors(user_id, resolved, next_review);
CREATE INDEX idx_errors_type ON errors(user_id, error_type);

-- ---------------------------------------------------------------
-- chunks
-- ---------------------------------------------------------------
CREATE TABLE chunks (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    chunk               TEXT NOT NULL,
    full_sentence       TEXT,
    meaning             TEXT,
    source              TEXT,                   -- 'himym_s2e4'|'book_unit_12'
    track               TEXT CHECK (track IN ('work','life','curiosity')),
    exported_to_anki    BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chunks_export ON chunks(user_id, exported_to_anki);

-- ---------------------------------------------------------------
-- book_units (M5)
-- ---------------------------------------------------------------
CREATE TABLE book_units (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    book            TEXT NOT NULL,
    unit_number     TEXT,
    unit_title      TEXT,
    target_items    JSONB,
    studied_at      DATE DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_book_units ON book_units(user_id, book, studied_at);

-- ---------------------------------------------------------------
-- sessions
-- ---------------------------------------------------------------
CREATE TABLE sessions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    task_type       TEXT NOT NULL,
    delivered_at    TIMESTAMPTZ,
    completed       BOOLEAN DEFAULT FALSE,
    completed_at    TIMESTAMPTZ,
    score           REAL,
    nudges_sent     INTEGER DEFAULT 0
);
CREATE INDEX idx_sessions_open ON sessions(user_id, date, completed);

-- ---------------------------------------------------------------
-- streaks
-- ---------------------------------------------------------------
CREATE TABLE streaks (
    user_id             BIGINT PRIMARY KEY REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    current_streak      INTEGER DEFAULT 0,
    longest_streak      INTEGER DEFAULT 0,
    freeze_tokens       INTEGER DEFAULT 2,
    last_active_date    DATE,
    rescue_mode_until   DATE,
    total_active_days   INTEGER DEFAULT 0
);

-- ---------------------------------------------------------------
-- interests + readings (M4)
-- ---------------------------------------------------------------
CREATE TABLE interests (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    topic       TEXT NOT NULL,
    track       TEXT,
    weight      REAL DEFAULT 1.0,
    last_used   DATE
);
CREATE INDEX idx_interests ON interests(user_id, weight DESC);

CREATE TABLE readings (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    title       TEXT,
    body        TEXT,
    topic       TEXT,
    cefr_level  TEXT,
    questions   JSONB,
    sent_at     TIMESTAMPTZ,
    completed   BOOLEAN DEFAULT FALSE,
    score       REAL,
    rating      INTEGER CHECK (rating BETWEEN 1 AND 5)
);

-- ---------------------------------------------------------------
-- couple challenge (M8)
-- ---------------------------------------------------------------
CREATE TABLE couple_challenges (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date            DATE NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    winner_user_id  BIGINT REFERENCES users(telegram_user_id),
    answered_at     TIMESTAMPTZ
);

CREATE TABLE couple_scores (
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    week_start  DATE NOT NULL,
    points      INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, week_start)
);

-- ---------------------------------------------------------------
-- calibration log (M14)
-- ---------------------------------------------------------------
CREATE TABLE calibration_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    date        DATE DEFAULT CURRENT_DATE,
    accuracy_30 REAL,
    old_level   TEXT,
    new_level   TEXT
);

-- ---------------------------------------------------------------
-- seed: error taxonomy
-- ---------------------------------------------------------------
INSERT INTO error_types (code, label, murphy_units) VALUES
 ('article_missing',        'Missing article',              '69-81'),
 ('article_wrong',          'Wrong article',                '69-81'),
 ('plural_countable',       'Countable/uncountable',        '68-70'),
 ('verb_tense_past',        'Past tense',                   '5-6,11-14'),
 ('present_perfect',        'Present perfect',              '7-14'),
 ('conditional',            'Conditionals',                 '38-40'),
 ('modal_verb',             'Modal verbs',                  '26-37'),
 ('gerund_vs_infinitive',   'Gerund vs infinitive',         '53-68'),
 ('preposition',            'Prepositions',                 '121-136'),
 ('word_order',             'Word order',                   '109-111'),
 ('quantifier_modifier',    'Quantifiers and modifiers',    '85-90'),
 ('subject_verb_agreement', 'Subject-verb agreement',       '1-4'),
 ('phrasal_verb',           'Phrasal verbs',                '137-145'),
 ('collocation',            'Collocation',                  NULL),
 ('false_friend',           'False friend',                 NULL),
 ('register_formality',     'Register / formality',         NULL),
 ('pronunciation_vowel',    'Vowel pronunciation',          NULL),
 ('pronunciation_stress',   'Word stress',                  NULL),
 ('filler_overuse',         'Filler overuse',               NULL);

INSERT INTO schema_version (version) VALUES (1);

-- ---------------------------------------------------------------
-- NOTE for Phase 5 (multi-tenant):
-- Enable Row Level Security on every user-scoped table and add
-- policies keyed on tenant_id before the first external user.
-- Not needed now — the bot connects with a single service role
-- and scopes every query by user_id in application code.
-- ---------------------------------------------------------------
