-- ============================================================================
-- 033 — W13d. Image cards for concrete vocabulary: one approved picture per
-- picturable lemma, shared by every learner.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–032 with no
-- gaps and the development database reported `schema_version` 32. TASKS' W13d
-- row took no number ("claimed by the commit that writes the `.sql`", #185),
-- and no unwritten row below it held 033, so nothing shifts.
--
-- **GLOBAL, NOT USER-KEYED, AND THERE IS NO `user_id` COLUMN** — PRD §2.6.3:
-- an image is a per-word asset shared across every learner, the reasoning
-- migration 019 gave `videos`. `tests/test_lexeme_images.py` asserts the
-- column's absence against `information_schema`, not against this file.
--
-- **A ROW IS AN OPERATOR'S APPROVAL, NOT A MACHINE'S CHOICE.** Rows are written
-- only by `python -m core.images.bank --load --apply`, from the committed
-- `data/lexeme_images.tsv`, and a line in that file is the operator's decision
-- that this picture shows this word. A proposal the operator has not copied into
-- the file never reaches this table (#271: a check can refuse a bad draft; only
-- a person can say the picture is right).
--
-- **THE LICENCE GATE IS IN THE SCHEMA, NOT ONLY IN THE LOADER.** `data/LICENCES.md`
-- (W13d) admits Wikimedia Commons files under exactly eight licences; the CHECK
-- below admits exactly those eight, so a loader bug cannot store a ninth. A
-- licence that requires attribution cannot be stored without an author and a
-- licence URL, because the card must show both (CC BY 4.0 §3(a)(1)).
--
-- **THE BYTES LIVE HERE, AND THAT IS A DECISION WITH A REASON.** Nothing in
-- this product serves stored bytes today; R2 holds backups only and there is no
-- object-store client in Python. A 330-pixel thumbnail is tens of kilobytes, the
-- CHECK caps one at 256 KiB, and the existing nightly `pg_dump` carries them
-- with no new credential and no new processor. If the set ever grows past what a
-- dump should carry, the bytes move and this comment says why they started here.
-- ============================================================================

CREATE TABLE lexeme_images (
    id             INTEGER     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- One picture per lemma. RESTRICT, like `cards.lexeme_id`: lexemes are
    -- never deleted, and a deletion that took pictures with it would be silent.
    lexeme_id      INTEGER     NOT NULL UNIQUE
                   REFERENCES lexemes(id) ON DELETE RESTRICT,

    -- The Commons file, by title (`File:SpoonCollection.jpg`) and by the page a
    -- viewer is sent to for the licence, the author and the history.
    commons_file   TEXT        NOT NULL CHECK (commons_file LIKE 'File:%'),
    source_url     TEXT        NOT NULL
                   CHECK (source_url LIKE 'https://commons.wikimedia.org/wiki/File:%'),

    -- The ORIGINAL file's SHA-1 as Commons reports it when the operator
    -- approved it. `--apply` refuses a file whose current SHA-1 differs: a new
    -- upload over the same title is a different picture nobody approved.
    original_sha1  TEXT        NOT NULL CHECK (original_sha1 ~ '^[0-9a-f]{40}$'),

    -- Plain text, tags stripped. Empty only where no attribution is required.
    author         TEXT        NOT NULL,
    licence        TEXT        NOT NULL
                   CHECK (licence IN (
                       'CC0', 'Public domain',
                       'CC BY 2.0', 'CC BY 2.5', 'CC BY 3.0', 'CC BY 4.0',
                       'CC BY-SA 3.0', 'CC BY-SA 4.0'
                   )),
    licence_url    TEXT,

    mime           TEXT        NOT NULL CHECK (mime IN ('image/jpeg', 'image/png')),
    width          SMALLINT    NOT NULL CHECK (width  BETWEEN 1 AND 2000),
    height         SMALLINT    NOT NULL CHECK (height BETWEEN 1 AND 2000),
    bytes          BYTEA       NOT NULL
                   CHECK (octet_length(bytes) BETWEEN 1 AND 262144),

    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT lexeme_images_attribution_is_complete CHECK (
        licence IN ('CC0', 'Public domain')
        OR (length(btrim(author)) > 0 AND licence_url LIKE 'https://creativecommons.org/%')
    )
);

COMMENT ON TABLE lexeme_images IS
    'W13d: one operator-approved Wikimedia Commons picture per picturable lemma. '
    'Global: no user_id. Licence allowlist and attribution enforced by CHECK. '
    'Written only by core.images.bank --load --apply from data/lexeme_images.tsv.';
