-- Migration 036 — W32: a global word dictionary, so every word on /watch has a
-- meaning the moment the page loads.
--
-- **Number taken when this file was written (2026-09-28): files 001–035 on
-- `main`, none on `w22-bot-reduction` beyond them, and the dev `schema_version`
-- 35; nothing had reserved 036 (#185).**
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY IT EXISTS
--
-- The operator, 2026-09-27 (~23:35 Vilnius, desktop): tapping *moving* or
-- *over* on /watch said *"No meaning for this one yet"*. Only the ~17
-- below-floor words of a video have a `video_glosses` row, and a live `explain`
-- call takes 4.4–8.0 s. **Under a second cannot come from a model call; it has
-- to be data that exists before the page loads.** This table is that data: one
-- short entry per word, written ahead of time in batches by
-- `python -m core.video.dictionary` (human-run, dry by default), topped up by
-- `WORD_DICTIONARY_JOB`, and on a rare miss by the one request-path lookup
-- (W32c, a scoped exception to the 2026-08-27 ruling).
--
-- **WHY GLOBAL — NO `user_id`, FOR `videos`' AND `lexeme_images`' REASON.** A
-- word's dictionary meaning does not depend on who reads it. A per-learner copy
-- would be exactly the per-user × per-lemma materialisation PRODUCT-PRINCIPLES
-- §3 says to flag. **§2's position, stated as it requires:** the table is not
-- user-keyed, so it carries no `users(id)` reference at all.
--
-- **§3's flag, stated rather than implied:** `l1` inside each sense holds the
-- languages of today's learners (`fa`, `lt`). A learner with a third language
-- means an L1-only top-up of global rows — filed with W32a.
--
-- **KEYED BY THE WORD'S TEXT, NOT `lexeme_id`.** Transcript words off the
-- 15,000-row list (*gonna*, rare words, slang) must have entries too. The key
-- is `core.services.glosses.gloss_key(surface)` — the coverage lemma, else the
-- casefolded surface — the function the gloss writer and reader already share
-- (#468). `cards.lexeme_id` is resolved at capture, as it is today (#469).
--
-- **`kind = 'name'`** records that the model said the word is only ever a
-- name, with no senses and no register — so a name is never bought twice, and
-- the popover can say *"a name"*.
--
-- **NO CARD REFERENCES THIS TABLE.** A save copies the sense's text into
-- `cards` (W32b), so dropping a row loses no learner data.
CREATE TABLE word_dictionary (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lemma               TEXT NOT NULL UNIQUE
                        CHECK (lemma ~ '^[a-z][a-z'']{0,39}$'),
    kind                TEXT NOT NULL CHECK (kind IN ('word', 'name')),
    -- `[{pos, definition, l1: {code: text}}]`, most common sense first. One
    -- by default (ruling C2); a second or third only where the word has more
    -- than one sense common at B1–B2 (*over*, *run*, *miss*).
    senses              JSONB NOT NULL DEFAULT '[]'::jsonb,
    register            TEXT
                        CHECK (register IN ('formal', 'neutral', 'informal', 'slang', 'taboo')),
    neutral_equivalent  TEXT,
    who_says_this       TEXT,
    model               TEXT NOT NULL,
    -- Who asked for it: the human-run backfill, the flagged top-up job, or a
    -- learner's miss. The two ceilings count by this (C2's shape, 035).
    source              TEXT NOT NULL CHECK (source IN ('backfill', 'topup', 'miss')),
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- **`CASE`, not `AND`, wherever a length is read:** PostgreSQL does not
    -- promise to evaluate `AND` left to right, and `jsonb_array_length` on an
    -- object RAISES rather than returning false — so a non-array would be
    -- refused by an error instead of by this CHECK (found by the schema test).
    CONSTRAINT word_dictionary_senses_are_an_array_of_at_most_three
        CHECK (CASE WHEN jsonb_typeof(senses) = 'array'
                    THEN jsonb_array_length(senses) <= 3 ELSE FALSE END),
    CONSTRAINT word_dictionary_every_sense_has_its_fields
        CHECK (NOT jsonb_path_exists(
            senses,
            '$[*] ? (!exists(@.pos) || !exists(@.definition) || !exists(@.l1))'
        )),
    CONSTRAINT word_dictionary_a_word_has_a_meaning
        CHECK (
            CASE WHEN jsonb_typeof(senses) <> 'array' THEN FALSE
                 WHEN kind = 'word' THEN register IS NOT NULL AND jsonb_array_length(senses) >= 1
                 ELSE register IS NULL AND jsonb_array_length(senses) = 0 END
        ),
    -- PRD §8.5.4 and 023's CHECK, mirrored: an informal or slang word carries
    -- the safe alternative and who says it to whom.
    CONSTRAINT word_dictionary_informal_carries_the_four_things
        CHECK (
            register IS NULL OR register NOT IN ('informal', 'slang')
            OR (neutral_equivalent IS NOT NULL AND who_says_this IS NOT NULL)
        )
);

-- The ceilings' read: today's rows of one source.
CREATE INDEX word_dictionary_by_source_and_time ON word_dictionary (source, generated_at);

COMMENT ON TABLE word_dictionary IS
    'W32: one short meaning per word, written ahead of time. Global: no user_id '
    '(a meaning does not depend on the reader). Keyed by glosses.gloss_key. '
    'No card references it; saves copy the text.';
