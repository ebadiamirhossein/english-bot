"""W8: the per-learner diff and the seed, through the real queries.

The diff is the central claim of this slice — a shared candidate set, minus the
learner's own ledger, computed at read time — so it is tested against real
`user_lexemes` rows rather than against a Python set that happens to have the
same shape.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.services.syllabus import (
    missing_lemmas,
    orphan_unit_lexemes,
    reconcile_unit_lexemes,
    target_counts,
    unit_rows,
    unit_target_lexemes,
    upsert_units,
)
from core.syllabus import UNIT_COUNT
from core.syllabus.content import units


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 14, (
            "run `python -m core.db migrate` — 014 is not applied"
        )
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def seeded(conn):
    upsert_units(conn, units())
    return conn


@pytest.fixture
def user_id(conn):
    return conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES (%s, %s, %s, TRUE) RETURNING id",
        ("W8 service fixture", "lt", "w8-service@example.test"),
    ).fetchone()[0]


def _lexeme_ids(conn, lemmas):
    return {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT lemma, id FROM lexemes WHERE lemma = ANY(%s)", (list(lemmas),)
        ).fetchall()
    }


def _know(conn, user_id, lexeme_id, state="known"):
    conn.execute(
        """
        INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank)
        VALUES (%s, %s, %s, 'placement', 6)
        """,
        (user_id, lexeme_id, state),
    )


# ── the units ───────────────────────────────────────────────────────────────


def test_the_seed_writes_twenty_four_units(seeded) -> None:
    rows = unit_rows(seeded)
    assert len(rows) == UNIT_COUNT
    assert [r[0] for r in rows] == list(range(1, UNIT_COUNT + 1))
    assert all(3 <= r[3] <= 5 for r in rows)


def test_a_second_upsert_writes_nothing(seeded) -> None:
    """The idempotency criterion, and the reason `IS DISTINCT FROM` is there.

    Without the guard this would report 24 updated — 24 no-op UPDATEs with fresh
    row versions — which is indistinguishable from a real correction in a log.
    """
    counts = upsert_units(seeded, units())
    assert (counts.inserted, counts.updated) == (0, 0)
    assert counts.unchanged == UNIT_COUNT


def test_a_corrected_unit_is_rewritten_and_only_that_unit(seeded) -> None:
    """Idempotency must not become inertness: a real change must still land."""
    seeded.execute(
        "UPDATE syllabus_units SET can_do = 'stale' WHERE unit_number = 5"
    )
    counts = upsert_units(seeded, units())
    assert (counts.inserted, counts.updated, counts.unchanged) == (0, 1, 23)
    assert seeded.execute(
        "SELECT can_do FROM syllabus_units WHERE unit_number = 5"
    ).fetchone()[0] == units()[4].can_do


# ── the candidate sets ──────────────────────────────────────────────────────


def test_reconcile_inserts_then_writes_nothing(seeded) -> None:
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 6"
        ).fetchall()
    ]
    first = reconcile_unit_lexemes(seeded, {1: tuple(pool[:3]), 2: tuple(pool[3:])})
    assert first.inserted == 6
    second = reconcile_unit_lexemes(seeded, {1: tuple(pool[:3]), 2: tuple(pool[3:])})
    assert (second.inserted, second.deleted) == (0, 0)


def test_reconcile_removes_a_word_taken_out_of_the_file(seeded) -> None:
    """**This deletes, and `core.lexicon.seed` deliberately does not.**

    Nothing points at `syllabus_unit_lexemes` — the per-learner list is computed
    from it, never stored — so a pair here is content, not evidence about a
    learner. Content that cannot be corrected is content that stays wrong, and a
    syllabus will be corrected. The lexicon's no-delete rule protects ledger
    history, which is a different thing entirely.
    """
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 3"
        ).fetchall()
    ]
    reconcile_unit_lexemes(seeded, {1: tuple(pool)})
    counts = reconcile_unit_lexemes(seeded, {1: tuple(pool[:2])})
    assert counts.deleted == 1
    assert len(unit_target_lexemes(seeded, 0, 1)) == 2


def test_a_lemma_with_no_lexemes_row_is_named_not_dropped(seeded) -> None:
    """The join would silently drop it; the seed refuses instead."""
    assert missing_lemmas(seeded, ["zzzznotaword", "the"]) == ["zzzznotaword"]


def test_there_are_no_orphan_candidate_rows(seeded) -> None:
    assert orphan_unit_lexemes(seeded) == 0


# ── the diff: PRD §3's "not already in your known-word ledger" ─────────────


def test_a_known_word_drops_out_of_the_learners_targets(seeded, user_id) -> None:
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 4"
        ).fetchall()
    ]
    reconcile_unit_lexemes(seeded, {3: tuple(pool)})
    assert unit_target_lexemes(seeded, user_id, 3) == pool

    ids = _lexeme_ids(seeded, pool)
    _know(seeded, user_id, ids[pool[0]], "known")
    _know(seeded, user_id, ids[pool[1]], "mastered")
    assert unit_target_lexemes(seeded, user_id, 3) == pool[2:]


def test_a_word_still_being_learned_stays_a_target(seeded, user_id) -> None:
    """`learning` is NOT covered, and that is deliberate.

    `COVERED_STATES` is `known` + `mastered` — the same set the coverage
    calculation uses. A word the learner is still acquiring is exactly the word
    a unit should keep drilling, so dropping it would remove the target at the
    moment it is most useful.
    """
    lemma = seeded.execute(
        "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
        "ORDER BY freq_rank LIMIT 1"
    ).fetchone()[0]
    reconcile_unit_lexemes(seeded, {4: (lemma,)})
    ids = _lexeme_ids(seeded, [lemma])
    _know(seeded, user_id, ids[lemma], "learning")
    assert unit_target_lexemes(seeded, user_id, 4) == [lemma]


def test_two_learners_see_different_targets_from_one_shared_row(seeded, user_id) -> None:
    """PRD §3: "Two learners on Unit 7 see different sentences about the same
    grammar." The row is shared; the list is not.

    This is the whole reason `syllabus_unit_lexemes` has no `user_id`.
    """
    other = seeded.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES (%s, %s, %s, TRUE) RETURNING id",
        ("W8 second learner", "fa", "w8-service-2@example.test"),
    ).fetchone()[0]
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 3"
        ).fetchall()
    ]
    reconcile_unit_lexemes(seeded, {7: tuple(pool)})
    ids = _lexeme_ids(seeded, pool)
    _know(seeded, user_id, ids[pool[0]])
    _know(seeded, other, ids[pool[2]])

    assert unit_target_lexemes(seeded, user_id, 7) == pool[1:]
    assert unit_target_lexemes(seeded, other, 7) == pool[:2]
    assert unit_target_lexemes(seeded, user_id, 7) != unit_target_lexemes(seeded, other, 7)


def test_targets_come_back_commonest_first(seeded, user_id) -> None:
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 5"
        ).fetchall()
    ]
    reconcile_unit_lexemes(seeded, {9: tuple(reversed(pool))})
    assert unit_target_lexemes(seeded, user_id, 9) == pool


def test_target_counts_reports_every_unit_that_has_candidates(seeded, user_id) -> None:
    pool = [
        r[0]
        for r in seeded.execute(
            "SELECT lemma FROM lexemes WHERE cefr = 'B1' AND freq_rank > 2000 "
            "ORDER BY freq_rank LIMIT 2"
        ).fetchall()
    ]
    reconcile_unit_lexemes(seeded, {2: (pool[0],), 3: (pool[1],)})
    assert target_counts(seeded, user_id) == [(2, 1), (3, 1)]


# ── the 012 contract ────────────────────────────────────────────────────────


def test_the_items_foreign_key_validates(seeded) -> None:
    """The acceptance criterion for 014's NOT VALID constraint.

    014 adds `items_unit_number_fkey` NOT VALID because `syllabus_units` is
    empty at migration time. NOT VALID still enforces on every new row -- all
    W10 needs -- but a constraint nobody ever validates is a silent hole, so
    the seed runs VALIDATE and this asserts the catalogue agrees.

    Read back from `pg_constraint` rather than from the function's return value:
    a criterion verified by the thing that performed the action is a test of
    nothing (CLAUDE.md §3 rule 5).
    """
    from core.services.syllabus import validate_items_fk

    validate_items_fk(seeded)
    row = seeded.execute(
        "SELECT convalidated FROM pg_constraint WHERE conname = %s",
        ("items_unit_number_fkey",),
    ).fetchone()
    assert row is not None and row[0] is True


def test_a_unit_with_a_learner_on_it_cannot_be_deleted(seeded, user_id) -> None:
    """ON DELETE RESTRICT on `user_unit_state.unit_number`.

    The 24 units are fixed data. Deleting one out from under a learner's
    progress is a mistake to refuse, not to cascade -- cascading would silently
    destroy the only record that they had reached it.
    """
    seeded.execute(
        "INSERT INTO user_unit_state (user_id, unit_number, state) "
        "VALUES (%s, 12, 'in_progress')",
        (user_id,),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with seeded.transaction():
            seeded.execute("DELETE FROM syllabus_units WHERE unit_number = 12")
