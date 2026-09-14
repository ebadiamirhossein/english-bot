-- ============================================================================
-- 027 — W16a. The writing log, and the learner-facing name of an error type.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–026 with no
-- gaps. **027 IS WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, so **W18
-- SHIFTS 027 → 028 IN BOTH HALVES OF `docs/TASKS-v3-web.md` IN THIS SAME
-- COMMIT.** W4b's policy: take the next number, never one above everything
-- claimed.
--
-- **#185's THIRTEENTH on the *taken at implementation time* counting**, which
-- is the counting 025's and 026's headers use; on the *shifted an unwritten
-- row* counting it is the twelfth. **The two still do not reconcile and this
-- file does not resolve them.**
--
-- ----------------------------------------------------------------------------
-- 1. `writing_submissions` — ONE ROW PER COMPLETED MODEL CALL ON `/write`
-- ----------------------------------------------------------------------------
-- **A LOG, NOT A COUNTER (send-back S2, operator-ruled 2026-09-14).**
-- PRODUCT-PRINCIPLES §3's first bullet flags data that materialises what could
-- be computed, and a per-day counter stores a number the submissions
-- themselves give. The log serves BOTH rulings from one table:
--
--   * **Ruling 3 (the ceiling)** counts today's rows for the learner.
--   * **Ruling 1 (block 4 `done`)** is `EXISTS` a row for the session with
--     `is_english` — log-derived, which is #258's *record themselves from the
--     logs*. **No `sessions.payload` flag is written**: a flag a route sets is
--     the shape closest to the manual button #258 deleted.
--
-- **`is_english` IS ONE COLUMN SERVING TWO RULINGS IN OPPOSITE DIRECTIONS, AND
-- THE ASYMMETRY IS DELIBERATE.** A non-English submission SPENT a call, so it
-- counts toward the ceiling; it is not the learner's own English, so it does
-- not count toward `done`.
--
-- **NO TEXT COLUMN, AND THAT IS CLAUDE.md §5 RATHER THAN AN OMISSION.** What
-- the learner typed is held for the length of the screen and never stored;
-- `tests/test_migration_027.py` asserts the absence from `information_schema`.
-- **NO COST COLUMN (#321)** — counts and tokens only.
--
-- **`day_kind` ADMITS `'paragraph'` NOW, AND W16a NEVER WRITES IT.** Migration
-- 012's *widen the CHECK once* precedent, applied to a table that does not
-- exist yet, so W16b needs no DDL of its own for it. A test pins that W16a's
-- writer refuses the value.
--
-- **A ROW IS WRITTEN ONLY FOR A COMPLETED MODEL CALL.** A provider failure
-- writes nothing and counts nothing; a too-short submission never reaches the
-- model.
--
-- **PRODUCT-PRINCIPLES §2: keys on `users(id)`.** No Telegram id anywhere.
-- `session_id` follows 025's `conversations.session_id` exactly — nullable,
-- `ON DELETE SET NULL` — because `/write` is also reachable from home with no
-- session at all.
-- ----------------------------------------------------------------------------

CREATE TABLE writing_submissions (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id        BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    day_kind          TEXT NOT NULL
                      CHECK (day_kind IN ('journal', 'paragraph')),
    local_date        DATE NOT NULL,
    is_english        BOOLEAN NOT NULL,
    llm_input_tokens  INTEGER NOT NULL CHECK (llm_input_tokens  >= 0),
    llm_output_tokens INTEGER NOT NULL CHECK (llm_output_tokens >= 0),
    -- **ADDED BEFORE 027 LEFT THE MAC, ON THE §3 rule 2 CALL'S OWN NUMBERS.**
    -- Prompt caching is live on this request: call 1 reported input 140 with
    -- cache_creation 1,721, call 2 input 91 with cache_read 1,721. The two
    -- columns above alone would have logged 140 where 1,861 were sent — a ~13x
    -- undercount, #321's family. Two columns on a table that does not exist
    -- yet are free now and unbackfillable later.
    llm_cache_creation_input_tokens INTEGER NOT NULL
        CHECK (llm_cache_creation_input_tokens >= 0),
    llm_cache_read_input_tokens     INTEGER NOT NULL
        CHECK (llm_cache_read_input_tokens >= 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_writing_submissions_user_date
    ON writing_submissions (user_id, local_date);
CREATE INDEX idx_writing_submissions_session
    ON writing_submissions (session_id);

-- ----------------------------------------------------------------------------
-- 2. `error_types.learner_label` — THE CARD EYEBROW, FROM THE TAXONOMY
-- ----------------------------------------------------------------------------
-- **S3, OPTION (a), OPERATOR-ACCEPTED.** The design's `1u` proposed nineteen
-- strings hand-authored in TypeScript because no category label came over the
-- wire. **A client copy of a seeded database taxonomy is a second source of
-- truth** — #190's shape — so the name lives beside the code it names.
--
-- **A NEW COLUMN, NOT AN EDIT TO `label`.** `label` feeds `correction.txt`'s
-- type list, which **the live Telegram bot shares**; editing it would change
-- legacy request construction for a display concern. And `label` is not fit
-- to show a learner as it stands: **`'Wrong article'` matches `BANNED`'s
-- `\bwrong\b`** and would fail the no-guilt scan on the screen.
--
-- **THE THREE SPOKEN CODES STAY NULL**, and a NULL label makes the eyebrow
-- ABSENT — the card still reads (`1u`). A written entry has no vowel, no word
-- stress and no filler.
--
-- **THESE SIXTEEN STRINGS ARE AUTHORED TEACHING CONTENT (send-back S5).** The
-- no-guilt scan in `tests/test_migration_027.py` can refuse a banned word; it
-- cannot say whether *Words that go together* names collocation in a way a B1
-- learner understands. **The operator reads all sixteen before they ship** —
-- human check HW-L — and an amendment is an `UPDATE` in a later file.
-- ----------------------------------------------------------------------------

ALTER TABLE error_types ADD COLUMN learner_label TEXT
    CONSTRAINT error_types_learner_label_is_not_blank
    CHECK (learner_label IS NULL OR length(btrim(learner_label)) > 0);

UPDATE error_types SET learner_label = v.learner_label
  FROM (VALUES
    ('article_missing',        'Articles'),
    ('article_wrong',          'Articles'),
    ('plural_countable',       'Countable nouns'),
    ('verb_tense_past',        'Past tense'),
    ('present_perfect',        'Present perfect'),
    ('conditional',            'Conditionals'),
    ('modal_verb',             'Modal verbs'),
    ('gerund_vs_infinitive',   '-ing or to'),
    ('preposition',            'Prepositions'),
    ('word_order',             'Word order'),
    ('quantifier_modifier',    'Quantifiers'),
    ('subject_verb_agreement', 'Subject and verb'),
    ('phrasal_verb',           'Phrasal verbs'),
    ('collocation',            'Words that go together'),
    ('false_friend',           'Similar words, different meaning'),
    ('register_formality',     'Tone')
  ) AS v(code, learner_label)
 WHERE error_types.code = v.code;

-- Refuse to finish if a code was renamed since 001 and silently matched
-- nothing: sixteen written labels, three spoken NULLs, no more and no fewer.
DO $$
DECLARE
    labelled integer;
    unlabelled integer;
BEGIN
    SELECT count(*) FILTER (WHERE learner_label IS NOT NULL),
           count(*) FILTER (WHERE learner_label IS NULL)
      INTO labelled, unlabelled
      FROM error_types;
    IF labelled <> 16 OR unlabelled <> 3 THEN
        RAISE EXCEPTION
            '027: expected 16 labelled and 3 unlabelled error types, got % and %',
            labelled, unlabelled;
    END IF;
END $$;
