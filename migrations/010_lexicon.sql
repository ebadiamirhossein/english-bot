-- W4: the lexicon and the known-word ledger.
--
-- Plain, non-idempotent DDL, per 009's note: core.db.migrate wraps each file in
-- one transaction and gates it on schema_version, which is what makes a re-run
-- impossible. Guards would only buy the impression that a re-run is safe.
--
-- NOTHING IS SEEDED HERE. The ~15k rows of `lexemes` arrive from
-- `python -m core.lexicon.seed`, which reads `data/lexemes.tsv`. Fifteen
-- thousand INSERTs in this file would be unreviewable in a diff, would make it
-- ~1.5 MB that every future `migrate` re-reads, and would couple a data
-- correction to a schema version. Data lives in data/, schema lives here.
--
-- #48 was considered and is NOT triggered: this migration does not touch
-- `users`, so there is no paired CREATE OR REPLACE VIEW approved_onboarded_users.
-- The one tunable W4 introduces — how many top-frequency lemmas are assumed
-- known — is a core.config setting, not a users column: it has the same value
-- for both learners, and putting it on `users` would cost a view recreate for
-- something that is not a per-learner fact.

-- ---------------------------------------------------------------
-- lexemes — the static reference table, growable but never by guessing
-- ---------------------------------------------------------------
-- `origin` distinguishes a seeded row from one grown at runtime by an explicit
-- tap. A closed 15k list would cap the system's whole vocabulary forever:
-- `user_lexemes.lexeme_id` is a foreign key, so a lemma with no row here could
-- never be recorded, and W13's tap-to-define exists precisely for words outside
-- a frequency-ranked list. It is named `origin` and not `source` on purpose —
-- `user_lexemes.source` already means "what evidence wrote this ledger row",
-- and two `source` columns meaning different things in adjacent tables is a
-- naming trap of exactly the kind that has cost this project a slice before.
--
-- freq_rank / freq_band / cefr are NULL for a grown row. NULL rank means
-- "rarer than the seed list's tail", NOT "missing": the frequency floor filters
-- `freq_rank IS NOT NULL` so a grown lemma is never assumed known, and any
-- future banding must sort NULL last rather than coerce it to zero. A fake band
-- would be indistinguishable from a real one, so none is written.
--
-- No register column here. PRD §8.5.1 puts register on `cards`, `items` and
-- `user_lexemes` — not on the reference table. Register is a fact about how a
-- learner met a word, not about the word.
CREATE TABLE lexemes (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lemma       TEXT NOT NULL UNIQUE,
    pos         TEXT,
    freq_rank   INTEGER,
    freq_band   SMALLINT,
    cefr        TEXT CHECK (cefr IS NULL OR
                            cefr IN ('A1','A2','B1','B2','C1','C2')),
    origin      TEXT NOT NULL DEFAULT 'seed'
                    CHECK (origin IN ('seed','grown')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lexemes_rank ON lexemes (freq_rank);
CREATE INDEX idx_lexemes_cefr ON lexemes (cefr, freq_rank);

-- ---------------------------------------------------------------
-- user_lexemes — one row per lemma per learner (PRD §2.1)
-- ---------------------------------------------------------------
-- `unknown` is deliberately absent from the CHECK. It is the ABSENCE OF A ROW,
-- never a stored value, and leaving it out is what makes that unforgeable. A
-- row means "we have evidence about this lemma"; materialising ignorance would
-- give 15k rows per learner a fake first_seen_at and a fake source, turn every
-- ingestion into an UPDATE, and stop "how many lemmas do we have evidence for"
-- being COUNT(*). Forgetting lands at `seen` — a word cannot be un-encountered.
--
-- `source_rank` is denormalised from core.lexicon.states.SOURCE_RANK so the
-- conflict rule in the upsert is a plain numeric comparison against the stored
-- row. The CHECK below keeps the two honest.
--
-- `register` (PRD §8.5.1) is nullable and inert until W13 writes it. It is here
-- rather than in a later ALTER for the same reason 009 carried
-- l1_pronunciation_seed: adding one nullable column to a migration already
-- being written is strictly cheaper than a second ALTER for one column, and
-- W13 would otherwise have to widen itself to add it.
CREATE TABLE user_lexemes (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT  NOT NULL REFERENCES users(telegram_user_id)
                              ON DELETE CASCADE,
    lexeme_id     INTEGER NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
    state         TEXT    NOT NULL
                      CHECK (state IN ('seen','learning','known','mastered')),
    source        TEXT    NOT NULL
                      CHECK (source IN ('assumption','v2_encountered',
                                        'v2_studied','tapped','skipped_easy',
                                        'v2_produced','correction','review',
                                        'placement')),
    source_rank   SMALLINT NOT NULL CHECK (source_rank BETWEEN 0 AND 6),
    register      TEXT CHECK (register IS NULL OR
                              register IN ('formal','neutral','informal',
                                           'slang','taboo')),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- What makes re-running any ingestion a no-op rather than a duplicate.
    UNIQUE (user_id, lexeme_id),
    -- source and source_rank must agree, or the conflict rule silently stops
    -- meaning what core.lexicon.states says it means.
    CONSTRAINT user_lexemes_source_rank_agrees CHECK (
        source_rank = CASE source
            WHEN 'assumption'     THEN 0
            WHEN 'v2_encountered' THEN 1
            WHEN 'v2_studied'     THEN 2
            WHEN 'tapped'         THEN 2
            WHEN 'skipped_easy'   THEN 3
            WHEN 'v2_produced'    THEN 3
            WHEN 'correction'     THEN 4
            WHEN 'review'         THEN 5
            WHEN 'placement'      THEN 6
        END
    )
);

CREATE INDEX idx_user_lexemes_state ON user_lexemes (user_id, state);
CREATE INDEX idx_user_lexemes_lexeme ON user_lexemes (lexeme_id);
