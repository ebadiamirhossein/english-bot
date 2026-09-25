-- ============================================================================
-- 032 — W18. The placement test: a fixed bank, each sitting, and what each
-- sitting served.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–031 with no
-- gaps and the development database reported `schema_version` 31. 032 is what
-- the authoritative table in `docs/TASKS-v3-web.md` reserved for W18.
--
-- **THREE TABLES WHERE THE TABLE ROW NAMED TWO** — `placement_run_items` is
-- ADDED TO THAT ROW in the same commit (019's and 022's precedent). It is the
-- table that makes the monthly re-run's rule — *two sittings draw disjoint
-- items* — a constraint rather than a hope: `UNIQUE (user_id, bank_id)`.
--
-- **THE BANK IS GLOBAL, NOT PER LEARNER.** `migrations/012_items.sql:35-40`
-- ruled that the fixed placement instrument does not live in `items` (which is
-- per-learner), because PRD §6 needs an instrument that does not change between
-- sittings. `placement_bank` is that shape.
--
-- **THE BANK IS GENERATED, AND IT IS LABELLED `uncalibrated` IN THE DATA**
-- (build run 2, ruling 0.1). TASKS' W18 row says *calibrated*; calibration
-- needs real learners' results, so that word is reported UNMET, never claimed.
-- The only value the CHECK admits today is `uncalibrated`: a row cannot claim
-- calibration until a later migration says what calibrating it meant.
--
-- **NO LEARNER TEXT IN ANY TABLE** (CLAUDE.md §5). A sitting stores which items
-- were served and whether each answer was right — never what was typed, never
-- what was said. The speaking answer is scored in the request and discarded;
-- only its band survives.
-- ============================================================================

CREATE TABLE placement_bank (
    id            BIGSERIAL   PRIMARY KEY,
    section       TEXT        NOT NULL
                  CHECK (section IN ('vocabulary', 'grammar', 'listening', 'speaking')),

    -- The CEFR band the item is pitched at. NULL only for a pseudo-word, which
    -- is not English at any level (checked below).
    cefr          TEXT        CHECK (cefr IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),

    -- The 19-code taxonomy (migration 001). Grammar and listening items name the
    -- pattern they turn on; a yes/no word and a speaking prompt are not an
    -- error pattern, and inventing one for them would be a tag with nothing
    -- behind it (checked below).
    error_type    TEXT        REFERENCES error_types(code),

    -- Vocabulary only: the string shown, whether it is a real lemma, and — for
    -- a real one — the frequency rank it was drawn from (`lexemes.freq_rank`).
    word          TEXT,
    is_word       BOOLEAN,
    freq_rank     INTEGER     CHECK (freq_rank > 0),

    -- Grammar and listening: the item exactly as `core.items.schema` parsed it
    -- (answer included — grading is server-side). Speaking: the prompt.
    item          JSONB,
    -- The gates' report for a generated item (`gates.ValidationReport`).
    validation    JSONB,
    model         TEXT,

    content_hash  TEXT        NOT NULL UNIQUE,
    calibration   TEXT        NOT NULL DEFAULT 'uncalibrated'
                  CHECK (calibration IN ('uncalibrated')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT placement_bank_vocabulary_shape CHECK (
        section <> 'vocabulary' OR (
            word IS NOT NULL AND is_word IS NOT NULL AND item IS NULL
            AND error_type IS NULL
            AND (
                (is_word AND freq_rank IS NOT NULL AND cefr IS NOT NULL)
                OR (NOT is_word AND freq_rank IS NULL AND cefr IS NULL)
            )
        )
    ),
    CONSTRAINT placement_bank_generated_shape CHECK (
        section NOT IN ('grammar', 'listening') OR (
            item IS NOT NULL AND validation IS NOT NULL AND cefr IS NOT NULL
            AND error_type IS NOT NULL
            AND word IS NULL AND is_word IS NULL AND freq_rank IS NULL
        )
    ),
    CONSTRAINT placement_bank_speaking_shape CHECK (
        section <> 'speaking' OR (
            item IS NOT NULL AND cefr IS NOT NULL AND error_type IS NULL
            AND word IS NULL AND is_word IS NULL AND freq_rank IS NULL
        )
    )
);

CREATE INDEX placement_bank_section_cefr_idx ON placement_bank (section, cefr);

COMMENT ON TABLE placement_bank IS
    'W18: the fixed placement instrument, global rather than per learner. '
    'Generated through the item gates (build run 2, ruling 0.1) and labelled '
    'uncalibrated: calibration needs real results. A row that has been served '
    'cannot be deleted (placement_run_items references it without cascade).';

-- One row per sitting. **At most one open sitting per learner** (the partial
-- unique index below), so a second tap on Start resumes rather than forks.
CREATE TABLE placement_runs (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,

    -- Where the sitting is. `done` means every section has been answered; the
    -- result is computed and `finished_at` set by `POST /placement/finish`.
    section         TEXT        NOT NULL DEFAULT 'vocabulary'
                    CHECK (section IN ('vocabulary', 'grammar', 'listening', 'speaking', 'done')),

    -- The result. NULL until finished, and each band NULL when that skill was
    -- not measured (speaking skipped, a vocabulary answer pattern too unreliable
    -- to read). `cefr` is the grammar ladder's band: the adaptive section, and
    -- the one the syllabus's units are written against.
    cefr            TEXT CHECK (cefr IN ('A2', 'B1', 'B2', 'C1')),
    vocabulary_band TEXT CHECK (vocabulary_band IN ('A2', 'B1', 'B2', 'C1')),
    grammar_band    TEXT CHECK (grammar_band IN ('A2', 'B1', 'B2', 'C1')),
    listening_band  TEXT CHECK (listening_band IN ('A2', 'B1', 'B2', 'C1')),
    speaking_band   TEXT CHECK (speaking_band IN ('A2', 'B1', 'B2', 'C1')),
    vocab_estimate  INTEGER     CHECK (vocab_estimate BETWEEN 0 AND 20000),
    -- What was written to `users.known_word_floor` through
    -- `core.services.lexicon.set_known_word_floor`, or NULL when nothing was.
    floor_written   INTEGER     CHECK (floor_written BETWEEN 0 AND 20000),
    speaking_mode   TEXT        CHECK (speaking_mode IN ('voice', 'typed', 'skipped')),
    -- Why the grammar ladder stopped (`core.placement.ladder`).
    grammar_stop    TEXT        CHECK (grammar_stop IN (
                        'oscillation', 'held', 'boundary', 'max_items', 'bank_thin')),
    -- error_type code -> grammar items missed on it. **For the operator and a
    -- later slice; never rendered** — a tally of misses shown to a learner is a
    -- score. Nothing here is written to the error journal: a wrong choice in a
    -- test item is not a self-produced error (CLAUDE.md §5).
    error_profile   JSONB       NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT placement_runs_finished_means_done
        CHECK (finished_at IS NULL OR section = 'done'),
    -- `speaking_band` and `speaking_mode` are written when the speaking item is
    -- answered (the answer is placed in that request and discarded), so they
    -- are not in this list; every band read from the served items is.
    CONSTRAINT placement_runs_result_only_when_finished
        CHECK (finished_at IS NOT NULL OR (
            cefr IS NULL AND vocabulary_band IS NULL AND grammar_band IS NULL
            AND listening_band IS NULL
            AND vocab_estimate IS NULL AND floor_written IS NULL
        ))
);

CREATE UNIQUE INDEX placement_runs_one_open_idx
    ON placement_runs (user_id) WHERE finished_at IS NULL;
CREATE INDEX placement_runs_user_idx ON placement_runs (user_id, finished_at);

COMMENT ON TABLE placement_runs IS
    'W18: one placement sitting. Bands, not scores: no percentage is stored or '
    'shown. error_profile is never rendered and never journaled.';

-- What each sitting served, in order, and whether each answer was right.
-- **`UNIQUE (user_id, bank_id)` IS THE MONTHLY RE-RUN'S RULE**: an item a
-- learner has been served is never served to them again, so two sittings are
-- disjoint by construction and a month apart they cannot share an item.
CREATE TABLE placement_run_items (
    run_id       BIGINT      NOT NULL REFERENCES placement_runs(id) ON DELETE CASCADE,
    user_id      BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bank_id      BIGINT      NOT NULL REFERENCES placement_bank(id),
    section      TEXT        NOT NULL
                 CHECK (section IN ('vocabulary', 'grammar', 'listening', 'speaking')),
    position     SMALLINT    NOT NULL CHECK (position >= 0),
    -- NULL until answered, and NULL for the speaking item (it is banded, not
    -- marked). Vocabulary: TRUE for "yes" to a real word or "no" to a pseudo.
    correct      BOOLEAN,
    answered_at  TIMESTAMPTZ,
    served_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (run_id, bank_id),
    CONSTRAINT placement_run_items_never_twice UNIQUE (user_id, bank_id),
    CONSTRAINT placement_run_items_one_per_position UNIQUE (run_id, section, position)
);

COMMENT ON TABLE placement_run_items IS
    'W18: what a sitting served and whether each answer was right. No answer '
    'text. UNIQUE (user_id, bank_id): no learner is served one item twice.';
