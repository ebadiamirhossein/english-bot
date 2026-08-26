"""Every query against `syllabus_units`, `syllabus_unit_lexemes` and
`user_unit_state`.

`core/syllabus/` is pure and holds the constants, the state machine and the
content validation; this module is the only place SQL touches those three
tables. The same split `core.lexicon` / `core.services.lexicon` uses, and for
the same reason: it is what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted --
#59 remains the only exemption in this repository.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from psycopg.rows import tuple_row

from core.lexicon.states import COVERED_STATES
from core.syllabus import TARGET_LEXEME_FLOOR, UNIT_COUNT
from core.syllabus.content import Unit

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SeedCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0

    def __str__(self) -> str:
        return (
            f"{self.inserted} inserted, {self.updated} updated, "
            f"{self.unchanged} unchanged, {self.deleted} deleted"
        )


# ── the 24 units ────────────────────────────────────────────────────────────


def upsert_units(conn, units: tuple[Unit, ...]) -> SeedCounts:
    """Insert or correct the 24 rows. Never deletes one.

    Idempotency is the `IS DISTINCT FROM` guard, exactly as `upsert_lexemes`
    does it: an unchanged row is not rewritten, so a second run reports
    `0 inserted, 0 updated` rather than 24 no-op UPDATEs with fresh timestamps.

    Never deletes: `items.unit_number` and `user_unit_state.unit_number` both
    point here, the second with ON DELETE RESTRICT. A "sync" that removed a unit
    absent from the file would either fail or take a learner's progress with it.
    """
    inserted = updated = unchanged = 0
    with conn.cursor(row_factory=tuple_row) as cur:
        for unit in units:
            targets = json.dumps(
                [
                    {"target": t.target, "murphy_units": t.murphy_units}
                    for t in unit.grammar_targets
                ]
            )
            checkpoint = json.dumps(unit.checkpoint)
            cur.execute(
                """
                INSERT INTO syllabus_units (
                    unit_number, stage, can_do, grammar_targets,
                    output_task_spoken, output_task_written, checkpoint
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                ON CONFLICT (unit_number) DO UPDATE SET
                    stage               = EXCLUDED.stage,
                    can_do              = EXCLUDED.can_do,
                    grammar_targets     = EXCLUDED.grammar_targets,
                    output_task_spoken  = EXCLUDED.output_task_spoken,
                    output_task_written = EXCLUDED.output_task_written,
                    checkpoint          = EXCLUDED.checkpoint
                WHERE (
                    syllabus_units.stage, syllabus_units.can_do,
                    syllabus_units.grammar_targets,
                    syllabus_units.output_task_spoken,
                    syllabus_units.output_task_written,
                    syllabus_units.checkpoint
                ) IS DISTINCT FROM (
                    EXCLUDED.stage, EXCLUDED.can_do, EXCLUDED.grammar_targets,
                    EXCLUDED.output_task_spoken, EXCLUDED.output_task_written,
                    EXCLUDED.checkpoint
                )
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    unit.unit_number,
                    unit.stage,
                    unit.can_do,
                    targets,
                    unit.output_task_spoken,
                    unit.output_task_written,
                    checkpoint,
                ),
            )
            row = cur.fetchone()
            if row is None:
                unchanged += 1
            elif row[0]:
                inserted += 1
            else:
                updated += 1
    return SeedCounts(inserted=inserted, updated=updated, unchanged=unchanged)


# ── the candidate sets ──────────────────────────────────────────────────────


def reconcile_unit_lexemes(conn, by_unit: dict[int, tuple[str, ...]]) -> SeedCounts:
    """Make each unit's candidate set match the file: insert missing, delete extra.

    **This deletes, and `core.lexicon.seed` deliberately does not.** The
    asymmetry is the point and it is not an oversight. Removing a lemma from
    `lexemes` would cascade into `user_lexemes` and destroy ledger history --
    evidence about a learner. Nothing points at `syllabus_unit_lexemes`: the
    per-learner target list is COMPUTED from it at read time, never stored. So a
    pair here is content, not evidence, and content that cannot be corrected is
    content that stays wrong. A syllabus WILL be corrected.

    Still idempotent by the criterion that matters: a second run inserts nothing
    and deletes nothing.
    """
    inserted = deleted = unchanged = 0
    with conn.cursor(row_factory=tuple_row) as cur:
        for unit in range(1, UNIT_COUNT + 1):
            wanted = list(by_unit.get(unit, ()))
            cur.execute(
                """
                WITH wanted AS (
                    SELECT l.id
                      FROM unnest(%s::TEXT[]) AS w(lemma)
                      JOIN lexemes l ON l.lemma = w.lemma
                ), added AS (
                    INSERT INTO syllabus_unit_lexemes (unit_number, lexeme_id)
                    SELECT %s, id FROM wanted
                    ON CONFLICT DO NOTHING
                    RETURNING 1
                ), removed AS (
                    DELETE FROM syllabus_unit_lexemes s
                     WHERE s.unit_number = %s
                       AND s.lexeme_id NOT IN (SELECT id FROM wanted)
                    RETURNING 1
                )
                SELECT (SELECT count(*) FROM added),
                       (SELECT count(*) FROM removed),
                       (SELECT count(*) FROM wanted)
                """,
                (wanted, unit, unit),
            )
            added, removed, total = cur.fetchone()
            inserted += added
            deleted += removed
            unchanged += total - added
    return SeedCounts(inserted=inserted, deleted=deleted, unchanged=unchanged)


def missing_lemmas(conn, lemmas: list[str]) -> list[str]:
    """Which of these have no `lexemes` row at all?

    The seed calls this before writing so a missing word is REPORTED rather than
    silently dropped by the join. `ensure_lexeme` is the path that would create
    one, and the build script never emits a lemma outside the pool -- a model
    proposing new vocabulary is exactly the guess path `ensure_lexeme`'s
    docstring bars it from.
    """
    if not lemmas:
        return []
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT w.lemma
              FROM unnest(%s::TEXT[]) AS w(lemma)
              LEFT JOIN lexemes l ON l.lemma = w.lemma
             WHERE l.id IS NULL
            """,
            (lemmas,),
        )
        return [row[0] for row in cur.fetchall()]


def orphan_unit_lexemes(conn) -> int:
    """Candidate rows whose lexeme does not exist. The foreign key makes this 0.

    Asserted anyway, and by a join rather than by trusting the constraint: the
    acceptance criterion is "every target lexeme resolves to a real `lexemes`
    row", and a criterion verified only by the mechanism that enforces it is a
    test of nothing.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT count(*)
              FROM syllabus_unit_lexemes s
              LEFT JOIN lexemes l ON l.id = s.lexeme_id
             WHERE l.id IS NULL
            """
        )
        return int(cur.fetchone()[0])


# ── the per-learner diff: PRD §3's "not already in your known-word ledger" ──


def unit_target_lexemes(conn, user_id: int, unit_number: int) -> list[str]:
    """This unit's candidates, minus what this learner already knows.

        target_lexemes(user, unit) = unit_candidates(unit) - known_lemmas(user)

    Computed here, never stored. Two learners on Unit 7 get different lists from
    the same row, which is what PRD §3 means by "Personalisation, not deviation".

    "Known" is `known` + `mastered` -- `core.lexicon.states.COVERED_STATES`, the
    same set `known_lemmas` and the coverage calculation use. `learning` does NOT
    count, and that is deliberate: a word the learner is still acquiring is
    exactly the word a unit should keep drilling.

    Ordered by frequency so the commonest survivor comes first: if a session
    takes only part of the list, it should take the part that pays soonest.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT l.lemma
              FROM syllabus_unit_lexemes s
              JOIN lexemes l ON l.id = s.lexeme_id
             WHERE s.unit_number = %s
               AND NOT EXISTS (
                     SELECT 1 FROM user_lexemes ul
                      WHERE ul.user_id = %s
                        AND ul.lexeme_id = s.lexeme_id
                        AND ul.state = ANY(%s)
                   )
             ORDER BY l.freq_rank NULLS LAST
            """,
            (unit_number, user_id, sorted(COVERED_STATES)),
        )
        return [row[0] for row in cur.fetchall()]


def target_counts(conn, user_id: int) -> list[tuple[int, int]]:
    """(unit_number, surviving target count) for all 24 units, for one learner.

    This is the acceptance criterion's own instrument. The criterion is
    ">=30 target lexemes", and it is met AFTER the ledger diff or it is not met
    -- so it is measured with the diff in it, per learner, rather than by
    counting the shared candidate rows and calling that the same thing.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT s.unit_number, count(*)
              FROM syllabus_unit_lexemes s
             WHERE NOT EXISTS (
                     SELECT 1 FROM user_lexemes ul
                      WHERE ul.user_id = %s
                        AND ul.lexeme_id = s.lexeme_id
                        AND ul.state = ANY(%s)
                   )
             GROUP BY s.unit_number
             ORDER BY s.unit_number
            """,
            (user_id, sorted(COVERED_STATES)),
        )
        return [(int(u), int(c)) for u, c in cur.fetchall()]


def below_floor(conn, user_id: int) -> list[tuple[int, int]]:
    """Units where this learner would see fewer than TARGET_LEXEME_FLOOR words."""
    return [(u, c) for u, c in target_counts(conn, user_id) if c < TARGET_LEXEME_FLOOR]


# ── the 012 cross-slice contract ────────────────────────────────────────────


def validate_items_fk(conn) -> bool:
    """VALIDATE the NOT VALID foreign key 014 added, then report whether it took.

    014 adds `items_unit_number_fkey` NOT VALID because `syllabus_units` is empty
    at migration time and a plain FK would have to validate against an empty
    parent. NOT VALID still enforces on every new row; it only skips the scan.

    This runs after the 24 rows exist and **returns what the catalogue says**,
    not what this function just tried to do. A NOT VALID constraint nobody ever
    validates is a silent hole, which is why the result is an acceptance
    criterion rather than a log line.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("ALTER TABLE items VALIDATE CONSTRAINT items_unit_number_fkey")
        cur.execute(
            """
            SELECT convalidated FROM pg_constraint
             WHERE conname = 'items_unit_number_fkey'
            """
        )
        row = cur.fetchone()
        return bool(row and row[0])


def unit_rows(conn) -> list[tuple[int, int, str, int, int]]:
    """(unit_number, stage, can_do, target count, candidate count) for all units.

    Written independently of `upsert_units` so the verification does not read
    from the function under test (CLAUDE.md §3 rule 5).
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT u.unit_number, u.stage, u.can_do,
                   jsonb_array_length(u.grammar_targets),
                   (SELECT count(*) FROM syllabus_unit_lexemes s
                     WHERE s.unit_number = u.unit_number)
              FROM syllabus_units u
             ORDER BY u.unit_number
            """
        )
        return [(int(a), int(b), c, int(d), int(e)) for a, b, c, d, e in cur.fetchall()]


@dataclass(frozen=True, slots=True)
class StoredUnit:
    """One `syllabus_units` row as it actually is, authored columns only.

    Deliberately not `core.syllabus.content.Unit`: that type is what the FILE
    says, and the whole purpose of reading this is to compare the two.
    """

    unit_number: int
    stage: int
    can_do: str
    grammar_targets: list
    output_task_spoken: str
    output_task_written: str
    checkpoint: dict


def stored_units(conn) -> list[StoredUnit]:
    """The seven authored columns of every unit, ordered by unit_number.

    Written independently of `upsert_units` so a before/after report does not read
    from the function under test (CLAUDE.md §3 rule 5) -- the same reason
    `unit_rows` above is written the way it is. `unit_rows` cannot serve here: it
    projects to counts for the seed's acceptance line and never returns the
    `checkpoint` itself.

    `created_at` is excluded: nothing authored decides it and a rewrite must not
    be judged against it.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT unit_number, stage, can_do, grammar_targets,
                   output_task_spoken, output_task_written, checkpoint
              FROM syllabus_units
             ORDER BY unit_number
            """
        )
        return [
            StoredUnit(
                unit_number=int(row[0]),
                stage=int(row[1]),
                can_do=row[2],
                grammar_targets=row[3],
                output_task_spoken=row[4],
                output_task_written=row[5],
                checkpoint=row[6],
            )
            for row in cur.fetchall()
        ]


__all__ = [
    "SeedCounts",
    "StoredUnit",
    "below_floor",
    "missing_lemmas",
    "orphan_unit_lexemes",
    "reconcile_unit_lexemes",
    "stored_units",
    "target_counts",
    "unit_rows",
    "unit_target_lexemes",
    "upsert_units",
    "validate_items_fk",
]


def current_unit(conn, user_id: int) -> int:
    """Which unit this learner is on. **Read-only; W11 owns every write.**

    The lowest `unit_number` this learner has not passed, defaulting to 1.
    `passed_at IS NOT NULL` rather than `state IN ('passed', 'mastered')`,
    because 014's `user_unit_state_timestamps_match_the_state` CHECK already
    pins the two together and a timestamp is the fact the ordering needs.

    **It never writes, and that is the whole of why it is a query rather than an
    advance.** `user_unit_state` is W11's table -- `docs/TASKS-v3-web.md` gives
    it checkpoints and unit advancement -- and pulling progression into a surface
    slice is the widening CLAUDE.md §8 forbids.

    **THE CONSEQUENCE, STATED HERE RATHER THAN DISCOVERED ON A PHONE: today this
    returns 1 for every learner and keeps returning 1.** `user_unit_state` is
    empty on production and nothing in the repository writes to it, so the unit
    cannot advance until W11 ships. Blocks 3 and 4 of the daily session are
    frozen on unit 1 with it, and block 4 therefore shows unit 1's single
    `output_task_written` **every day** -- day two and day thirty are the same
    task. That is a stated cost of W10, filed against W11, and it is not a bug in
    this function.

    Defaulting to 1 rather than raising is deliberate: `locked` is the ABSENCE of
    a row (`core.syllabus.states`), so "no rows at all" means "has reached
    nothing", and unit 1 being where you start is the syllabus's own answer
    rather than a fallback.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT min(u.unit_number)
              FROM syllabus_units u
             WHERE NOT EXISTS (
                     SELECT 1 FROM user_unit_state s
                      WHERE s.user_id = %s
                        AND s.unit_number = u.unit_number
                        AND s.passed_at IS NOT NULL
                   )
            """,
            (user_id,),
        )
        row = cur.fetchone()
    # NULL only when every unit is passed, which is the end of the programme.
    # The last unit is the honest answer there -- there is no unit 25.
    if row is None or row[0] is None:
        return UNIT_COUNT
    return int(row[0])


def unit_for_session(conn, unit_number: int) -> StoredUnit | None:
    """One unit's authored row, for blocks 3 and 4. ``None`` if it is not seeded.

    Returns `StoredUnit` -- the row as it actually is -- rather than
    `core.syllabus.content.Unit`, because the session must serve what production
    holds, not what the file says. The two are compared by the seed's own
    acceptance check, which is where that comparison belongs.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT unit_number, stage, can_do, grammar_targets,
                   output_task_spoken, output_task_written, checkpoint
              FROM syllabus_units
             WHERE unit_number = %s
            """,
            (unit_number,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return StoredUnit(
        unit_number=int(row[0]),
        stage=int(row[1]),
        can_do=row[2],
        grammar_targets=row[3],
        output_task_spoken=row[4],
        output_task_written=row[5],
        checkpoint=row[6],
    )
