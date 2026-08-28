-- W10b: grammar lessons. `grammar_lessons` is the teaching behind the 82
-- syllabus targets (#182) -- one row per unit, one section per grammar target.
-- PRD §4.1 block 3, which has always read "90-second explanation + 8 generated
-- items" and whose explanation half has never existed.
--
-- Plain, non-idempotent DDL, per 009's note and 010's, 012's, 013's, 014's,
-- 015's and 016's: core.db.migrate wraps each file in one transaction and gates
-- it on schema_version, which is what makes a re-run impossible. Guards would
-- only buy the impression that a re-run is safe. This file writes NO
-- schema_version row -- the runner does that (core/db.py), and only 001 inserts
-- one itself.
--
-- NOTHING IS SEEDED HERE, following 010, 013, 014, 015 and 016. Lessons are
-- written by `python -m core.lessons.generate --apply`, which is human-run and
-- dry by default. A unit nobody has generated for serves no lesson, and block 3
-- says so in one line a learner can read.
--
-- THIS FILE TAKES 017, WHICH `docs/TASKS-v3-web.md`'s AUTHORITATIVE TABLE
-- RESERVED FOR W12. W10b sits after W10, so it takes the next number and every
-- unwritten slice below shifts by one -- W12 to 018, W13a to 019, W14 to 020,
-- W18 to 021 -- corrected in BOTH halves of that document in this same commit,
-- the authoritative table and the per-slice Build columns, because nothing
-- reconciles them (#130). Taking a number above everything claimed (say 022)
-- would work on production and break replay on a fresh database, for the reason
-- that table already records.
--
-- **FOURTH OCCURRENCE OF #185.** W4b renumbered eight rows, W8f five, W10b four.
-- The planning table assigns migration numbers to slices that have not been
-- written, and unplanned slices are how this project actually proceeds. The
-- alternative is recorded on the issue: assign a number when the FILE is
-- written, not when the slice is planned.
--
-- #48 IS NOT TRIGGERED. There is no ALTER TABLE users in this file, so the
-- paired `CREATE OR REPLACE VIEW approved_onboarded_users` is not required and
-- is deliberately absent. Stated rather than omitted silently: #48 has recurred
-- because each case looked like the one where the rule did not apply.
--
-- PRODUCT-PRINCIPLES §2: THIS TABLE IS NOT USER-KEYED. There is no `user_id`
-- column at all -- present perfect is present perfect for every learner -- so it
-- neither depends on nor enlarges the identity established by migration 011.
-- §2 is satisfied trivially and the record says so rather than leaving it
-- inferred. §3: one row per unit, 24 rows forever, however many learners arrive.
-- Nothing here scales per-user by per-anything.

CREATE TABLE grammar_lessons (
    -- The unit IS the key. A surrogate id would permit two lessons for one unit
    -- and make "which one does block 3 serve?" a question the schema cannot
    -- answer.
    unit_number    SMALLINT PRIMARY KEY
                       REFERENCES syllabus_units(unit_number) ON DELETE RESTRICT,
    sections       JSONB NOT NULL,       -- one per grammar target
    diagrams       JSONB NOT NULL,       -- 0..5 typed specs, at most one per target
    verification   JSONB NOT NULL,       -- how it passed; mirrors items.validation
    lesson_version SMALLINT NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- DELIBERATELY WEAKER THAN THE CODE CHECK, and the gap is named here rather
    -- than left to be discovered. The real rule is a BIJECTION: one section per
    -- grammar target, both directions. This row cannot express it -- it does not
    -- know its unit's target count, and 3-5 here is satisfiable while 3-5 there
    -- is satisfied by a different number. `core.lessons.checks.bijection_failures`
    -- enforces it where the unit's targets are in hand. Same situation as the
    -- blocks-sum invariant living in `blueprint.validate_checkpoint` because 014
    -- could not mirror it (#167).
    --
    -- MEASURED, so the weakness is a number rather than a hand-wave: across the
    -- 24 units the target counts are 3 (fourteen units) and 4 (ten units), and
    -- NO UNIT HAS FIVE. So for EVERY unit, two of the three section counts this
    -- CHECK permits are wrong, and a five-section lesson is wrong for all 24.
    -- It is nonetheless left mirroring `syllabus_units_three_to_five_grammar_targets`
    -- rather than tightened to 3-4: that constraint is itself 3-5, so a unit
    -- gaining a fifth target is legal in the syllabus, and tightening here would
    -- encode today's data as a schema rule and break on the lesson side only.
    CONSTRAINT grammar_lessons_sections_three_to_five
        CHECK (jsonb_typeof(sections) = 'array'
               AND jsonb_array_length(sections) BETWEEN 3 AND 5),

    -- BOTH ENDS OF THIS RANGE WERE WRONG ONCE, IN TWO SUCCESSIVE DRAFTS, AND
    -- BOTH ARE #213's SHAPE: a contract excluding a state its own design
    -- produces.
    --
    -- ZERO IS PERMITTED. "Fewer rather than false": if no target of a unit suits
    -- one of the five kinds, the correct output is no diagram and a REPORTED
    -- COUNT. A floor of 1 -- which the approved plan carried -- would make that
    -- legitimate state unstorable, and the run would die on an INSERT with a
    -- diagnostic naming Postgres rather than the condition the design
    -- anticipated.
    --
    -- FIVE IS THE CEILING because the real rule is ONE DIAGRAM PER TARGET AT
    -- MOST, so the maximum is the unit's own target count -- 3 to 5 above. A cap
    -- of 3 forbids the four diagrams a four-target unit naturally produces,
    -- which is the floor's defect at the other end; a cap of 4 would encode
    -- today's measured maximum as a rule, which the sections CHECK immediately
    -- above deliberately declines to do, and the two must not reason differently
    -- about the same data.
    --
    -- LIKE THE SECTIONS CHECK, THIS ROW CANNOT SEE ITS UNIT'S TARGET COUNT, so
    -- 0-5 is satisfiable while the per-target rule is broken.
    -- `core.lessons.checks.diagram_failures` enforces it where the targets are
    -- in hand: every diagram names a real target of this unit, and no target
    -- twice.
    CONSTRAINT grammar_lessons_zero_to_five_diagrams
        CHECK (jsonb_typeof(diagrams) = 'array'
               AND jsonb_array_length(diagrams) BETWEEN 0 AND 5),

    -- "A lesson that fails verification is regenerated, never shipped with a
    -- warning", made unforgeable rather than promised. Mirrors `items`' own
    -- refusal to hold an unvalidated row.
    --
    -- WHAT THIS CHECK CANNOT SEE, said here so nobody reads it as more than it
    -- is: it cannot see WHICH RULES the verdict was reached under. A row
    -- verified by checks that no longer exist still passes it forever. That is
    -- what `lesson_version` is for, and the refusal lives in
    -- `core.services.lessons.for_unit`, which filters on the current version --
    -- the same policy `bank_for_session` applies to `validator_version`.
    CONSTRAINT grammar_lessons_only_verified_rows_exist
        CHECK ((verification ->> 'verdict') = 'passed')
);

-- Diagrams are a COLUMN, not a child table, and the reason is a correctness one:
-- a lesson that fails verification is regenerated WHOLE, because C3's
-- contradiction check spans prose and diagram together. A separate table makes
-- it possible for a diagram row to survive a regeneration and contradict the new
-- prose -- precisely the failure that check exists to catch.

COMMENT ON TABLE grammar_lessons IS
    'W10b. One lesson per syllabus unit, one section per grammar target. '
    'GLOBAL: no user_id, ever -- present perfect is present perfect for every '
    'learner. Written only by python -m core.lessons.generate --apply.';
