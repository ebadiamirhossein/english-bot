-- W7: the deck — `cards`, `card_reviews`. FSRS-6 scheduling, in-app.
--
-- Plain, non-idempotent DDL, per 009's note and 012's: core.db.migrate wraps
-- each file in one transaction and gates it on schema_version, which is what
-- makes a re-run impossible. Guards would only buy the impression that a re-run
-- is safe.
--
-- NOTHING IS SEEDED HERE, and that is a deliberate departure from 011, which
-- did its data rewrite inside the .sql. The chunk → cards pass is
-- `python -m core.cards.migrate_chunks`, a separate human-run command with a
-- dry run, for three reasons: the seeding is a Python computation (the v2
-- ladder, the difficulty clamp, py-fsrs' state enum); W4's seed and W4a's
-- repair are the precedent for a data pass over real learner rows; and "run it
-- twice, the second run writes nothing" is not a testable criterion for a file
-- that schema_version physically cannot run twice.
--
-- #48 IS NOT TRIGGERED. There is no ALTER TABLE users in this file, so the
-- paired `CREATE OR REPLACE VIEW approved_onboarded_users` is not required and
-- is deliberately absent. Stated rather than omitted silently: #48 has recurred
-- because each case looked like the one where the rule did not apply, so the
-- rule being considered is recorded even when it does not fire.

-- ---------------------------------------------------------------
-- 1. cards — the card AND its current FSRS state
-- ---------------------------------------------------------------
-- `docs/ARCHITECTURE-v3-web.md` §5 assigned the FSRS state to `card_reviews`
-- ("FSRS state: difficulty, stability, due, lapses, last_review"), i.e. one
-- mutable row per card, leaving no room for the individual reviews. That cell
-- is CORRECTED in the same commit as this file and the correction is named,
-- exactly as W6 corrected §6 rather than quietly reconciling it.
--
-- The reason is `item_attempts`' reason one table later: the state is derivable
-- and rewritable, the individual grades are not. Without a log, py-fsrs'
-- optimiser can never be fitted to these two learners, W19 has no review
-- history to show, and a mis-seeded stability can never be re-derived from what
-- actually happened. So: state here, events in `card_reviews`.
--
-- Per-learner fan-out, like `items` and for the same reason: a card carries a
-- learner's own captured sentence and its schedule is a fact about that person.
-- PRODUCT-PRINCIPLES §3, flagged at the moment of the choice.
CREATE TABLE cards (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Mirrored from core.cards.CARD_TYPES; test_migration_013 compares the
    -- CHECK against the constant the way test_migration_012 does for item
    -- types. ALL FIVE of PRD §5's card types ship here, widened once — the same
    -- move 012 §3 made for `errors.source`. W7 writes only `cloze` and
    -- `production`; `recognition`, `audio` and `collocation` have no writer for
    -- months. That is expected and is NOT to be fixed with a "every CHECK value
    -- has a writer" test, which would fail by design from the day it was
    -- written.
    card_type         TEXT NOT NULL CHECK (card_type IN (
                          'recognition', 'production', 'cloze', 'audio',
                          'collocation')),

    -- ── provenance ────────────────────────────────────────────────────────
    -- PRD §5: "every card carries the sentence it came from and where it came
    -- from". Mirrors `items.source_chunk_id` (012). SET NULL and not CASCADE: a
    -- card reviewed for six weeks is evidence about the learner even if the
    -- chunk it was derived from is later deleted. The card is not the chunk.
    source_chunk_id   BIGINT REFERENCES chunks(id) ON DELETE SET NULL,

    -- `chunks.source` verbatim: 'himym_s2e4', 'book_unit_12', 'prep_client_call'.
    source_ref        TEXT,

    -- ── the card face ─────────────────────────────────────────────────────
    front             TEXT NOT NULL,
    back              TEXT NOT NULL,

    -- PRD §5 "the sentence it came from"; PRD §8.5.4 "the line it came from".
    context_sentence  TEXT,
    meaning           TEXT,

    -- PRD §8.5.4's safe alternative, twice: as text for the card face, and as a
    -- lexeme so "is the neutral equivalent mastered" is a join against
    -- `user_lexemes` rather than a text match. ON DELETE RESTRICT because 010's
    -- rule is that lexemes are never deleted — RESTRICT makes that a schema
    -- fact instead of a comment, exactly as `items.lexeme_id` does.
    neutral_equivalent TEXT,
    neutral_lexeme_id INTEGER REFERENCES lexemes(id) ON DELETE RESTRICT,

    -- PRD §8.5.4's one line: "Friends and casual colleagues. Fine in Slack.
    -- Not in a client email."
    who_says_this     TEXT,

    -- The target lemma this card drills, when it has one. Migrated v2 chunks
    -- are phrases and carry none; W13's capture sets it. It is what
    -- `grade_card` writes the ledger from, with source='review'.
    lexeme_id         INTEGER REFERENCES lexemes(id) ON DELETE RESTRICT,

    -- Empty until a leech rewrite fills it (PRD §5: a leech is rewritten with
    -- an easier cue, NOT suspended). Built by core.items.repair.first_letter_cue.
    cue_text          TEXT,

    -- ── register (PRD §8.5.1) ─────────────────────────────────────────────
    -- NOT NULL WITH NO DEFAULT, and the divergence from `items.register`
    -- (which carries DEFAULT 'neutral') is deliberate. The generator sets an
    -- item's register in the same call that writes the item, so there is no
    -- untagged moment. `cards` are written by W13's capture, W23a's ad-hoc
    -- surface and the video pipeline, and a DEFAULT would let any of them
    -- insert an untagged card that silently reads 'neutral' — which is exactly
    -- what §8.5.1's "nothing enters the deck untagged" forbids.
    --
    -- THIS IS THE ACCEPTANCE CRITERION "no card exists without a register tag",
    -- enforced by the absence of a default rather than by convention. A count
    -- of zero untagged rows would not be evidence: on a small table it proves
    -- nothing. The absence of a default is checkable from information_schema
    -- and cannot be satisfied by luck.
    register          TEXT NOT NULL CHECK (register IN (
                          'formal', 'neutral', 'informal', 'slang', 'taboo')),

    -- HOW the tag was arrived at. 'migration_default' marks every card W7
    -- creates from a v2 chunk, because v2 had no register concept and 'neutral'
    -- is a stated default rather than an observation. A later re-tagging pass
    -- then finds exactly those rows with one WHERE — the same move
    -- `user_lexemes.source = 'assumption'` makes for the frequency floor (#93):
    -- a hypothesis stays identifiable, so unwinding it is a query and not
    -- archaeology.
    register_source   TEXT NOT NULL CHECK (register_source IN (
                          'migration_default', 'detected', 'operator')),

    -- Set ONLY by core.services.cards.promote_to_production, inside the same
    -- transaction that reads user_lexemes.state = 'mastered'. See the CHECK
    -- below for why the column exists at all.
    neutral_mastered_at TIMESTAMPTZ,

    -- ── FSRS state (mirrors fsrs.Card; see core/cards/fsrs.py) ────────────
    -- Mirrored from core.cards.FSRS_STATES. Lowercase here, capitalised in the
    -- library's IntEnum; core.cards owns the translation and a test asserts the
    -- two sets correspond.
    fsrs_state        TEXT NOT NULL CHECK (fsrs_state IN (
                          'learning', 'review', 'relearning')),
    fsrs_step         SMALLINT CHECK (fsrs_step IS NULL OR fsrs_step >= 0),
    stability         REAL CHECK (stability IS NULL OR stability > 0),
    difficulty        REAL CHECK (difficulty IS NULL OR
                                  difficulty BETWEEN 1 AND 10),
    due               TIMESTAMPTZ NOT NULL,
    last_review       TIMESTAMPTZ,
    lapses            INTEGER NOT NULL DEFAULT 0 CHECK (lapses >= 0),
    reps              INTEGER NOT NULL DEFAULT 0 CHECK (reps >= 0),

    -- PRD §5: "leech at 6 lapses → card is rewritten with an easier cue, not
    -- suspended". There is deliberately NO `suspended` column: a column nobody
    -- may set is an invitation, and the no-guilt rule (CLAUDE.md §4) is easier
    -- to hold when hiding a card is not expressible.
    leech_at          TIMESTAMPTZ,

    -- ── the seeding evidence (see core/cards/migrate_chunks.py) ───────────
    seeded_from_history BOOLEAN NOT NULL DEFAULT FALSE,

    -- The four v2 numbers copied verbatim onto the card, plus the mapping's
    -- name and version. Together with the fact that the migration never
    -- modifies `chunks`, this is what makes the whole slice reversible: if the
    -- mapping turns out wrong, a re-seed is an UPDATE with a stated formula
    -- rather than a reconstruction from nothing. A derived number whose inputs
    -- were discarded cannot be corrected, only guessed at again.
    seed_basis        JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- THE IDEMPOTENCY GUARANTEE, at the schema level rather than only in the
    -- code that happens to run the pass today. core.cards.migrate_chunks also
    -- anti-joins so a second run selects nothing before it inserts anything —
    -- two independent guarantees, because W4a's repair proved that the one you
    -- can test on the Mac is not always the one that holds on production.
    UNIQUE (user_id, source_chunk_id, card_type),

    -- The target of card_reviews' composite foreign key. Redundant against the
    -- primary key alone; it exists so the denormalised `user_id` on a review
    -- cannot disagree with the card's. Same construction as items(id, user_id).
    UNIQUE (id, user_id),

    -- PRD §8.5.1: taboo is "receptive only — never taught for production".
    -- Row-local, so a CHECK holds it. Mirrors items_taboo_is_never_productive.
    CONSTRAINT cards_taboo_is_never_productive CHECK (
        register <> 'taboo' OR card_type <> 'production'
    ),

    -- PRD §8.5.2, THE RECEPTIVE-FIRST RULE, and it is the ordering criterion:
    -- "no `slang` production card exists before its neutral equivalent is
    -- mastered."
    --
    -- **It bars three card types, not one.** §8.5.2 reads "`slang` and
    -- `informal` cards are created as RECOGNITION AND LISTENING CARDS ONLY",
    -- which permits exactly `recognition` and `audio`. An earlier draft of this
    -- constraint barred `production` alone — and a `cloze` card asks the learner
    -- to produce the phrase into a gap, so a slang cloze card breaks the
    -- receptive-first rule through the very constraint written to hold it.
    -- `collocation` is productive for the same reason. Found when the W7 census
    -- showed two learners whose entire v2 corpus is slang, so the case was
    -- about to stop being hypothetical.
    --
    -- Migration 012 left the slang half of this rule as "a service rule with a
    -- test", because a CHECK cannot see ledger state. It still cannot — but it
    -- can see whether someone recorded that they checked. Storing the promotion
    -- evidence ON THE CARD converts a cross-table rule into a row-local one, so
    -- the database becomes the backstop instead of the honour system.
    --
    -- This matters because the rule has to survive W10 and W13 creating cards.
    -- A guard living only in the code that creates cards today is a guard that
    -- the next writer does not know about; a CHECK is a guard the next writer
    -- cannot get past. `neutral_mastered_at` has exactly one writer,
    -- core.services.cards.promote_to_production, and a parse test says so.
    CONSTRAINT cards_receptive_first_until_the_neutral_is_mastered CHECK (
        card_type NOT IN ('production', 'cloze', 'collocation')
        OR register NOT IN ('slang', 'informal')
        OR neutral_mastered_at IS NOT NULL
    ),

    -- PRD §8.5.4: every informal/slang card shows FOUR things — the line it
    -- came from, the meaning, the neutral equivalent, and who says this to
    -- whom. All four are row-local, so the card face stops being a UI promise
    -- and becomes a schema fact: the component has no "if missing" branch to
    -- get wrong, because a card missing any of them cannot be inserted.
    --
    -- The consequence is deliberate and was ruled on: v2 `chunks` with
    -- source='slang' carry no neutral equivalent and no who-says-this, so they
    -- produce NO CARD at W7. A slang card showing the meaning but not the safe
    -- alternative is the card §8.5.4 calls "useless and slightly dangerous".
    CONSTRAINT cards_informal_shows_the_four_things CHECK (
        register NOT IN ('informal', 'slang')
        OR (context_sentence IS NOT NULL
            AND meaning IS NOT NULL
            AND neutral_equivalent IS NOT NULL
            AND who_says_this IS NOT NULL)
    ),

    -- py-fsrs asserts exactly this at the top of its State.Review and
    -- State.Relearning branches (fsrs/scheduler.py). Better an INSERT that
    -- fails here than an AssertionError raised inside a third-party library at
    -- grade time, on a learner's tap.
    CONSTRAINT cards_review_state_carries_both_parameters CHECK (
        fsrs_state = 'learning'
        OR (stability IS NOT NULL AND difficulty IS NOT NULL)
    ),

    -- A seeded stability must be able to say where it came from. Without this,
    -- `seeded_from_history` is a boolean anyone can set and the reversibility
    -- argument above is a comment rather than a guarantee.
    CONSTRAINT cards_seeded_rows_carry_their_basis CHECK (
        seeded_from_history = FALSE OR seed_basis <> '{}'::jsonb
    )
);

-- The reviewer's only hot query: "this learner's cards, soonest due first".
CREATE INDEX idx_cards_due ON cards (user_id, due);
CREATE INDEX idx_cards_neutral_lexeme ON cards (neutral_lexeme_id);
CREATE INDEX idx_cards_lexeme ON cards (lexeme_id);
CREATE INDEX idx_cards_chunk ON cards (source_chunk_id);

-- ---------------------------------------------------------------
-- 2. card_reviews — append-only, one row per grade
-- ---------------------------------------------------------------
-- The log, not the state. Every column records what was true BEFORE and AFTER
-- one grade, so a schedule can be re-derived without re-running the scheduler
-- and without trusting that the parameters never changed.
--
-- This is `item_attempts`' argument one table later: adding a column at 015 is
-- one line, but the months of history between 013 and that slice are gone
-- permanently. Here the loss would be worse — the individual grades are the
-- ONLY input py-fsrs' optimiser takes, so a state-only table would mean these
-- two learners' decks can never be fitted to their own data, ever.
CREATE TABLE card_reviews (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    card_id           BIGINT NOT NULL,

    -- Denormalised from `cards`, for the same reason `item_attempts.user_id`
    -- is: every W19 read is "this learner's reviews in a window", and going
    -- through `cards` puts a join on all of them. The composite FK is what
    -- makes the denormalisation unforgeable rather than merely conventional.
    user_id           BIGINT NOT NULL,
    FOREIGN KEY (card_id, user_id)
        REFERENCES cards (id, user_id) ON DELETE CASCADE,

    -- PASSED IN, never DEFAULT NOW(). The instant that scheduled the card and
    -- the instant that is logged must be the same instant; a column default
    -- makes them two different clock reads, and the difference is invisible
    -- until someone tries to replay the log and the intervals do not add up.
    reviewed_at       TIMESTAMPTZ NOT NULL,

    -- fsrs.Rating is an IntEnum: Again=1, Hard=2, Good=3, Easy=4. The same 1–4
    -- as item_attempts.grade's CHECK, deliberately — they are the same four
    -- buttons, on two different objects.
    rating            SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 4),

    -- Before and after, so the log stands alone. `state_before` +
    -- `stability_before IS NULL` is also how "was this card new at review
    -- time?" is answered, which is what the daily NEW-card cap counts.
    state_before      TEXT NOT NULL CHECK (state_before IN (
                          'learning', 'review', 'relearning')),
    stability_before  REAL,
    difficulty_before REAL,

    state_after       TEXT NOT NULL CHECK (state_after IN (
                          'learning', 'review', 'relearning')),
    stability_after   REAL,
    difficulty_after  REAL,
    due_after         TIMESTAMPTZ NOT NULL,

    -- Days since the previous review, and the interval that had been scheduled.
    -- Both are what the optimiser reads; both are cheap now and unrecoverable
    -- later, because they depend on a `last_review` this same write overwrites.
    elapsed_days      INTEGER CHECK (elapsed_days IS NULL OR elapsed_days >= 0),
    scheduled_days    INTEGER CHECK (scheduled_days IS NULL OR scheduled_days >= 0),

    -- Reveal → grade, reported by the browser. NOTHING IN W7 MAKES A
    -- SCHEDULING DECISION FROM IT — FSRS-6's inputs are exactly (state,
    -- stability, difficulty, elapsed days, rating) and latency is not among
    -- them in any branch. It is here for W19's effort-weighted XP and for a
    -- possible later "answered slowly → treat as Hard" heuristic, and it
    -- carries the same caveat as item_attempts.latency_ms (#108): a learner who
    -- backgrounds the app mid-card produces a real-but-meaningless number.
    review_duration_ms INTEGER CHECK (review_duration_ms IS NULL OR
                                      review_duration_ms >= 0)
);

CREATE INDEX idx_card_reviews_user ON card_reviews (user_id, reviewed_at DESC);
CREATE INDEX idx_card_reviews_card ON card_reviews (card_id);

-- No UNIQUE (card_id, reviewed_at): a card is legitimately reviewed again, and
-- two reviews in the same second are a double-tap to be handled in the service,
-- not a constraint violation to be surfaced to a learner mid-session.
