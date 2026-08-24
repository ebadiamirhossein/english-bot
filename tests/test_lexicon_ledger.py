"""W4: the ledger, the conflict rule, growth and the v2 harvest.

Every test runs inside a transaction that is rolled back, on a connection of
its own rather than the app's pool — the same shape as `test_migration_009`.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.lexicon.states import SOURCE_RANK, SOURCE_STATES, STATE_RANK
from core.services import lexicon as svc
from core.services.lexicon import LedgerEntry

TEST_USER = -940_401


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 10, (
            "run `python -m core.db migrate` — 010 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def user(conn):
    conn.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded)
        VALUES (%s, 'W4 fixture', 'fa', TRUE)
        """,
        (TEST_USER,),
    )
    return TEST_USER


def add_lexeme(conn, lemma: str, freq_rank: int | None = None) -> int:
    row = conn.execute(
        """
        INSERT INTO lexemes (lemma, freq_rank, freq_band, origin)
        VALUES (%s, %s, %s, 'seed') RETURNING id
        """,
        (lemma, freq_rank, None if freq_rank is None else 1),
    ).fetchone()
    return row[0]


def state_of(conn, user_id: int, lemma: str) -> str | None:
    row = conn.execute(
        """
        SELECT ul.state FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id
         WHERE ul.user_id = %s AND l.lemma = %s
        """,
        (user_id, lemma),
    ).fetchone()
    return row[0] if row else None


def snapshot(conn, user_id: int):
    return conn.execute(
        """
        SELECT lexeme_id, state, source, source_rank, register,
               first_seen_at, updated_at
          FROM user_lexemes WHERE user_id = %s ORDER BY lexeme_id
        """,
        (user_id,),
    ).fetchall()


# ── the conflict rule ───────────────────────────────────────────────────────


def test_a_tap_cannot_demote_what_a_correction_proved_known(conn, user) -> None:
    add_lexeme(conn, "w4alpha")
    svc.record(conn, user, [LedgerEntry("w4alpha", "known", "correction")])
    svc.record(conn, user, [LedgerEntry("w4alpha", "seen", "tapped")])
    assert state_of(conn, user, "w4alpha") == "known"


def test_a_tap_cannot_demote_what_a_placement_test_measured(conn, user) -> None:
    add_lexeme(conn, "w4beta")
    svc.record(conn, user, [LedgerEntry("w4beta", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4beta", "seen", "tapped")])
    assert state_of(conn, user, "w4beta") == "known"


def test_a_placement_test_can_correct_an_assumption_downwards(conn, user) -> None:
    """The floor is a hypothesis. Measurement must be able to overturn it."""
    add_lexeme(conn, "w4gamma")
    svc.record(conn, user, [LedgerEntry("w4gamma", "known", "assumption")])
    svc.record(conn, user, [LedgerEntry("w4gamma", "seen", "placement")])
    assert state_of(conn, user, "w4gamma") == "seen"


def test_an_equal_ranked_inference_may_raise_but_not_demote(conn, user) -> None:
    add_lexeme(conn, "w4delta")
    svc.record(conn, user, [LedgerEntry("w4delta", "seen", "tapped")])
    svc.record(conn, user, [LedgerEntry("w4delta", "learning", "v2_studied")])
    assert state_of(conn, user, "w4delta") == "learning"
    svc.record(conn, user, [LedgerEntry("w4delta", "seen", "tapped")])
    assert state_of(conn, user, "w4delta") == "learning"


def test_a_review_lapse_over_an_earlier_review_demotes(conn, user) -> None:
    """Same source, lower state. A rank-only rule discarded every FSRS lapse."""
    add_lexeme(conn, "w4epsilon")
    svc.record(conn, user, [LedgerEntry("w4epsilon", "mastered", "review")])
    svc.record(conn, user, [LedgerEntry("w4epsilon", "known", "review")])
    assert state_of(conn, user, "w4epsilon") == "known"


def test_a_second_placement_can_record_that_a_word_slipped(conn, user) -> None:
    """PRD §9 re-runs placement monthly. The instrument built to measure
    regression must be able to record one."""
    add_lexeme(conn, "w4zeta")
    svc.record(conn, user, [LedgerEntry("w4zeta", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4zeta", "learning", "placement")])
    assert state_of(conn, user, "w4zeta") == "learning"


def test_a_review_is_not_frozen_out_by_a_higher_ranked_placement(conn, user) -> None:
    """The commoner half of the same failure, and the more expensive one.

    `placement` outranks `review`, so a rank gate would drop every review of a
    word for the whole month after a placement test — promotions as well as
    lapses. W7's reviewer would appear to work while changing nothing.
    """
    add_lexeme(conn, "w4eta")
    svc.record(conn, user, [LedgerEntry("w4eta", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4eta", "mastered", "review")])
    assert state_of(conn, user, "w4eta") == "mastered"

    add_lexeme(conn, "w4theta")
    svc.record(conn, user, [LedgerEntry("w4theta", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4theta", "learning", "review")])
    assert state_of(conn, user, "w4theta") == "learning"


def test_a_lower_ranked_inference_over_a_placement_does_nothing(conn, user) -> None:
    add_lexeme(conn, "w4iota")
    svc.record(conn, user, [LedgerEntry("w4iota", "known", "placement")])
    before = snapshot(conn, user)
    counts = svc.record(conn, user, [LedgerEntry("w4iota", "seen", "tapped")])
    assert counts.changed == 0
    assert snapshot(conn, user) == before


# ── idempotency ─────────────────────────────────────────────────────────────


def test_the_same_ingestion_twice_leaves_the_table_byte_identical(conn, user) -> None:
    add_lexeme(conn, "w4kappa")
    add_lexeme(conn, "w4lambda")
    entries = [
        LedgerEntry("w4kappa", "known", "v2_produced"),
        LedgerEntry("w4lambda", "seen", "v2_encountered"),
    ]
    svc.record(conn, user, entries)
    before = snapshot(conn, user)
    counts = svc.record(conn, user, entries)
    assert counts.changed == 0
    assert counts.unchanged == 2
    # updated_at included: a re-run must not fire an UPDATE at all.
    assert snapshot(conn, user) == before


def test_re_running_an_authoritative_write_also_writes_nothing(conn, user) -> None:
    """The IS DISTINCT FROM guard carries idempotency alone for these sources,
    because nothing else gates them."""
    add_lexeme(conn, "w4mu")
    svc.record(conn, user, [LedgerEntry("w4mu", "mastered", "review")])
    svc.record(conn, user, [LedgerEntry("w4mu", "known", "review")])
    before = snapshot(conn, user)
    counts = svc.record(conn, user, [LedgerEntry("w4mu", "known", "review")])
    assert counts.changed == 0
    assert snapshot(conn, user) == before


def test_first_seen_at_never_moves(conn, user) -> None:
    add_lexeme(conn, "w4nu")
    svc.record(conn, user, [LedgerEntry("w4nu", "seen", "v2_encountered")])
    first = snapshot(conn, user)[0][5]
    svc.record(conn, user, [LedgerEntry("w4nu", "known", "placement")])
    assert snapshot(conn, user)[0][5] == first


def test_a_write_without_a_register_does_not_erase_one(conn, user) -> None:
    """Otherwise an equal-rank raise silently drops a slang tag W13 set."""
    add_lexeme(conn, "w4xi")
    svc.record(conn, user, [LedgerEntry("w4xi", "seen", "tapped", "slang")])
    svc.record(conn, user, [LedgerEntry("w4xi", "learning", "v2_studied")])
    row = conn.execute(
        "SELECT state, register FROM user_lexemes WHERE user_id = %s", (user,)
    ).fetchone()
    assert row == ("learning", "slang")


# ── the Python reduction and the SQL must be the same rule ──────────────────


def test_the_python_conflict_rule_agrees_with_the_sql_everywhere(conn, user) -> None:
    """A batch is de-duplicated in Python before it is sent, because one
    statement may not touch a row twice. Reducing by a different rule than the
    database applies is exactly the drift this project keeps paying for."""
    lexeme = "w4omicron"
    add_lexeme(conn, lexeme)
    pairs = [
        (source, state)
        for source, states in SOURCE_STATES.items()
        for state in sorted(states)
    ]
    for existing_source, existing_state in pairs:
        for source, state in pairs:
            conn.execute("DELETE FROM user_lexemes WHERE user_id = %s", (user,))
            svc.record(conn, user, [LedgerEntry(lexeme, existing_state, existing_source)])
            svc.record(conn, user, [LedgerEntry(lexeme, state, source)])
            expected = state if svc.wins(
                LedgerEntry(lexeme, state, source),
                LedgerEntry(lexeme, existing_state, existing_source),
            ) else existing_state
            assert state_of(conn, user, lexeme) == expected, (
                f"{existing_source}/{existing_state} then {source}/{state}"
            )


def test_the_generated_sql_matches_the_python_constants() -> None:
    for state, rank in STATE_RANK.items():
        assert f"WHEN '{state}' THEN {rank}" in svc._CONFLICT
    assert "EXCLUDED.source IN ('placement', 'review')" in svc._CONFLICT
    assert "IS DISTINCT FROM" in svc._CONFLICT


# ── the schema's own guarantees ─────────────────────────────────────────────


def test_unknown_cannot_be_stored(conn, user) -> None:
    """It is the absence of a row, and the CHECK is what makes that unforgeable."""
    lexeme_id = add_lexeme(conn, "w4pi")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank)
            VALUES (%s, %s, 'unknown', 'tapped', 2)
            """,
            (user, lexeme_id),
        )


def test_source_and_source_rank_cannot_disagree(conn, user) -> None:
    lexeme_id = add_lexeme(conn, "w4rho")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank)
            VALUES (%s, %s, 'seen', 'tapped', 6)
            """,
            (user, lexeme_id),
        )


def test_a_source_may_not_assert_a_state_it_has_no_standing_for(conn, user) -> None:
    add_lexeme(conn, "w4sigma")
    with pytest.raises(ValueError, match="may not set"):
        svc.record(conn, user, [LedgerEntry("w4sigma", "mastered", "tapped")])


# ── growth ──────────────────────────────────────────────────────────────────


def test_ensure_lexeme_grows_the_table_with_null_frequency(conn) -> None:
    lexeme_id = svc.ensure_lexeme(conn, "Kubernetes")
    row = conn.execute(
        "SELECT lemma, origin, freq_rank, cefr FROM lexemes WHERE id = %s", (lexeme_id,)
    ).fetchone()
    assert row == ("kubernetes", "grown", None, None)


def test_ensure_lexeme_refuses_anything_that_is_not_a_word(conn) -> None:
    for junk in ("", "  ", "123", "http://x.test", "a b", "-dash"):
        assert svc.ensure_lexeme(conn, junk) is None


def test_ensure_lexeme_is_idempotent_and_keeps_the_id(conn) -> None:
    first = svc.ensure_lexeme(conn, "zqxtau")
    assert svc.ensure_lexeme(conn, "zqxtau") == first


def test_a_grown_lexeme_is_never_assumed_known(conn, user) -> None:
    """NULL rank means rarer than the seed list's tail. It must not be assumed."""
    svc.ensure_lexeme(conn, "zqxupsilon")
    svc.assume_top_frequency_known(conn, user, 5)
    assert state_of(conn, user, "zqxupsilon") is None
    assert conn.execute(
        "SELECT COUNT(*) FROM user_lexemes WHERE user_id = %s", (user,)
    ).fetchone()[0] == 5


def test_a_reseed_enriches_a_grown_row_and_never_disturbs_its_ledger(conn, user) -> None:
    """A re-seed must be a delete-and-rerun-safe operation, not a rewrite.

    `id` is what `user_lexemes` points at, so the upsert preserving it is the
    whole reason a grown lemma's history survives the day its word finally
    makes the frequency list.
    """
    lexeme_id = svc.ensure_lexeme(conn, "zqxphi")
    svc.record(conn, user, [LedgerEntry("zqxphi", "known", "placement")])
    svc.upsert_lexemes(conn, [("zqxphi", "NOUN", 9_001, 10, "B2")])
    row = conn.execute(
        "SELECT id, origin, freq_rank, cefr FROM lexemes WHERE lemma = 'zqxphi'"
    ).fetchone()
    assert row == (lexeme_id, "seed", 9_001, "B2")
    assert state_of(conn, user, "zqxphi") == "known"


def test_the_seed_never_deletes_a_row_absent_from_the_file(conn, user) -> None:
    """A sync that removed them would cascade through `user_lexemes` and
    destroy ledger history — the one thing here that cannot be rebuilt."""
    svc.ensure_lexeme(conn, "zqxchi")
    svc.record(conn, user, [LedgerEntry("zqxchi", "known", "placement")])
    svc.upsert_lexemes(conn, [("zqxpsi", "NOUN", 9_002, 10, "B2")])
    assert state_of(conn, user, "zqxchi") == "known"


def test_upserting_the_same_reference_rows_twice_changes_nothing(conn) -> None:
    rows = [("w4omega", "NOUN", 9_003, 10, "B1")]
    assert svc.upsert_lexemes(conn, rows).inserted == 1
    second = svc.upsert_lexemes(conn, rows)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 1)


# ── the v2 harvest ──────────────────────────────────────────────────────────


def _journal(conn, user_id: int, source: str, said: str) -> None:
    conn.execute(
        """
        INSERT INTO errors (user_id, source, you_said, correct_form,
                            error_type, next_review)
        VALUES (%s, %s, %s, 'ignored', 'article_missing', CURRENT_DATE)
        """,
        (user_id, source, said),
    )


def test_the_harvest_reads_only_keyboard_authored_journal_rows(conn, user) -> None:
    """ASR output and captured English are not evidence the learner produces
    a word. A missing row is recoverable; a wrong one is permanent."""
    _journal(conn, user, "text", "I ate the pineapple")
    _journal(conn, user, "voice", "I saw a walrus")
    _journal(conn, user, "diary", "the hammock broke")
    _journal(conn, user, "capture", "an avalanche of cabbage")

    _, barred = svc.harvest_v2(conn, user)

    assert state_of(conn, user, "pineapple") == "known"
    assert state_of(conn, user, "walrus") is None
    assert state_of(conn, user, "hammock") is None
    assert state_of(conn, user, "avalanche") is None
    assert barred == 1


def test_presented_at_gates_both_chunk_columns(conn, user) -> None:
    """Two columns of one row. Crediting the sentence of a chunk that was never
    shown inverts the signal: exposure that provably did not happen."""
    conn.execute(
        """
        INSERT INTO chunks (user_id, chunk, full_sentence, presented_at)
        VALUES (%s, 'pineapple', 'she ate the sausage', NOW()),
               (%s, 'walrus', 'he sold the cabbage', NULL)
        """,
        (user, user),
    )
    svc.harvest_v2(conn, user)
    assert state_of(conn, user, "pineapple") == "learning"
    assert state_of(conn, user, "sausage") == "seen"
    assert state_of(conn, user, "walrus") is None
    assert state_of(conn, user, "cabbage") is None


def test_the_harvest_cannot_undo_a_placement_result(conn, user) -> None:
    """It will be re-run after W18 exists. It must be safe then too."""
    _journal(conn, user, "text", "the pelican")
    svc.record(conn, user, [LedgerEntry("pelican", "seen", "placement")])
    svc.harvest_v2(conn, user)
    assert state_of(conn, user, "pelican") == "seen"


def test_re_running_the_harvest_writes_nothing(conn, user) -> None:
    _journal(conn, user, "quiz", "a pineapple and a walrus")
    svc.harvest_v2(conn, user)
    before = snapshot(conn, user)
    counts, _ = svc.harvest_v2(conn, user)
    assert counts.changed == 0
    assert snapshot(conn, user) == before


# ── what the ledger is for ──────────────────────────────────────────────────


def test_learning_does_not_count_towards_coverage(conn, user) -> None:
    add_lexeme(conn, "w4known")
    add_lexeme(conn, "w4learning")
    svc.record(
        conn,
        user,
        [
            LedgerEntry("w4known", "known", "placement"),
            LedgerEntry("w4learning", "learning", "review"),
        ],
    )
    assert svc.known_lemmas(conn, user) == frozenset({"w4known"})
    assert svc.ledger(conn, user)["w4learning"] == "learning"


def test_words_you_know_counts_evidence_and_not_the_assumption(conn, user) -> None:
    """PRD §11 promises a real number. A counter that opens at the floor size
    before the learner has done anything is the theatre it was written
    against — and its first move after a placement test would be downward."""
    add_lexeme(conn, "w4assumed")
    add_lexeme(conn, "w4earned")
    svc.record(
        conn,
        user,
        [
            LedgerEntry("w4assumed", "known", "assumption"),
            LedgerEntry("w4earned", "known", "correction"),
        ],
    )
    assert svc.evidenced_known_count(conn, user) == 1


def test_coverage_for_a_user_reads_the_ledger(conn, user) -> None:
    svc.assume_top_frequency_known(conn, user, 2000)
    report = svc.coverage_for(conn, user, "The cat sat on the mat and I saw it.")
    assert report.counted_tokens == 10
    assert report.coverage > 0.8


def test_every_source_rank_is_inside_the_check_constraint() -> None:
    assert set(SOURCE_RANK.values()) <= set(range(0, 7))
