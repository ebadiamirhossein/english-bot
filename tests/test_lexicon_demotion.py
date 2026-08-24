"""W4a: only evidence of not-knowing may lower a state, and the repair for the
rows W4 already demoted.

The fault this covers was invisible to 1050 passing tests. It needed production
data with real history to surface: every W4 test wrote a state onto a row it had
just created, and none put an exposure on top of a frequency-floor row — which
is the one combination the old rule got backwards.
"""

from __future__ import annotations

import pytest

from core.lexicon.states import (
    AUTHORITATIVE_SOURCES,
    MAY_LOWER,
    SOURCE_RANK,
    SOURCE_STATES,
)
from core.services import lexicon as svc
from core.services.lexicon import LedgerEntry

# The connection fixture, the lexeme helper and the two readers are W4's and are
# reused deliberately: a second copy would be a second definition of "what a
# ledger row looks like", and this slice exists because two definitions of a
# rule drifted apart.
from tests.test_lexicon_ledger import (  # noqa: E402
    add_lexeme,
    conn,  # noqa: F401  — used as a pytest fixture
    snapshot,
    state_of,
)

TEST_USER = -940_402


@pytest.fixture
def user(conn):
    # Internal id, not the invented Telegram id: they differ since W4b.
    row = conn.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded)
        VALUES (%s, 'W4a fixture', 'lt', TRUE)
        RETURNING id
        """,
        (TEST_USER,),
    ).fetchone()
    assert row is not None
    return int(row[0])


# ── the sets are related, and are not the same thing ────────────────────────


def test_may_lower_is_a_strict_superset_of_the_authoritative_sources() -> None:
    """They answer different questions and must not be collapsed.

    AUTHORITATIVE asks "may this write ignore rank?"; MAY_LOWER asks "may this
    write lower a state?". `tapped` is in one and not the other.
    """
    assert AUTHORITATIVE_SOURCES < MAY_LOWER
    assert MAY_LOWER - AUTHORITATIVE_SOURCES == {"tapped"}


def test_no_exposure_or_inference_source_may_lower() -> None:
    assert not MAY_LOWER & {
        "assumption", "v2_encountered", "v2_studied", "skipped_easy",
        "v2_produced", "correction",
    }


# ── exposure cannot demote ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source,state", [("v2_encountered", "seen"), ("v2_studied", "learning")]
)
def test_exposure_cannot_demote_an_assumed_known_word(conn, user, source, state) -> None:
    """The W4 fault, in one assertion.

    A word appearing in a reading the bot sent is evidence the learner has *met*
    it — never evidence they have failed to learn it. Under W4's rank-only rule
    `v2_encountered` at rank 1 outranked the rank-0 floor and pulled `known`
    down to `seen`, so the more a learner had used the app the lower their
    coverage read.
    """
    lemma = f"w4a{source}"
    add_lexeme(conn, lemma, freq_rank=17)
    svc.record(conn, user, [LedgerEntry(lemma, "known", "assumption")])
    before = snapshot(conn, user)
    counts = svc.record(conn, user, [LedgerEntry(lemma, state, source)])
    assert state_of(conn, user, lemma) == "known"
    assert counts.changed == 0
    assert snapshot(conn, user) == before


def test_exposure_can_still_insert_and_raise(conn, user) -> None:
    add_lexeme(conn, "w4aexposure")
    assert svc.record(
        conn, user, [LedgerEntry("w4aexposure", "seen", "v2_encountered")]
    ).inserted == 1
    assert state_of(conn, user, "w4aexposure") == "seen"
    # A second exposure says nothing new.
    assert svc.record(
        conn, user, [LedgerEntry("w4aexposure", "seen", "v2_encountered")]
    ).changed == 0
    # Study is a raise, and still applies.
    svc.record(conn, user, [LedgerEntry("w4aexposure", "learning", "v2_studied")])
    assert state_of(conn, user, "w4aexposure") == "learning"


# ── a tap is evidence of not-knowing ────────────────────────────────────────


def test_a_tap_can_demote_an_assumed_known_word(conn, user) -> None:
    """W13's tap means the learner stopped because they did not recognise it."""
    add_lexeme(conn, "w4atap", freq_rank=18)
    svc.record(conn, user, [LedgerEntry("w4atap", "known", "assumption")])
    svc.record(conn, user, [LedgerEntry("w4atap", "seen", "tapped")])
    assert state_of(conn, user, "w4atap") == "seen"


def test_a_tap_still_cannot_demote_what_outranks_it(conn, user) -> None:
    add_lexeme(conn, "w4ataprank")
    svc.record(conn, user, [LedgerEntry("w4ataprank", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4ataprank", "seen", "tapped")])
    assert state_of(conn, user, "w4ataprank") == "known"


# ── amendment A is untouched ────────────────────────────────────────────────


def test_review_over_placement_still_applies_in_both_directions(conn, user) -> None:
    add_lexeme(conn, "w4apromote")
    svc.record(conn, user, [LedgerEntry("w4apromote", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4apromote", "mastered", "review")])
    assert state_of(conn, user, "w4apromote") == "mastered"

    add_lexeme(conn, "w4alapse")
    svc.record(conn, user, [LedgerEntry("w4alapse", "known", "placement")])
    svc.record(conn, user, [LedgerEntry("w4alapse", "learning", "review")])
    assert state_of(conn, user, "w4alapse") == "learning"


def test_the_generated_sql_carries_both_lists(conn) -> None:
    assert "EXCLUDED.source IN ('placement', 'review')" in svc._CONFLICT
    assert "EXCLUDED.source IN ('placement', 'review', 'tapped')" in svc._CONFLICT


def test_the_python_rule_agrees_with_the_sql_under_the_new_gate(conn, user) -> None:
    """All 169 ordered source × state pairs, driven through the database."""
    lemma = "w4asweep"
    add_lexeme(conn, lemma)
    pairs = [
        (source, state)
        for source, states in SOURCE_STATES.items()
        for state in sorted(states)
    ]
    assert len(pairs) ** 2 == 169
    for existing_source, existing_state in pairs:
        for source, state in pairs:
            conn.execute("DELETE FROM user_lexemes WHERE user_id = %s", (user,))
            svc.record(conn, user, [LedgerEntry(lemma, existing_state, existing_source)])
            svc.record(conn, user, [LedgerEntry(lemma, state, source)])
            expected = state if svc.wins(
                LedgerEntry(lemma, state, source),
                LedgerEntry(lemma, existing_state, existing_source),
            ) else existing_state
            assert state_of(conn, user, lemma) == expected, (
                f"{existing_source}/{existing_state} then {source}/{state}"
            )


# ── the repair ──────────────────────────────────────────────────────────────


def _demote_a_floor_row(conn, user_id: int, lemma: str) -> None:
    """Reproduce what W4's rule did, by writing the row the old rule allowed."""
    lexeme_id = conn.execute(
        "SELECT id FROM lexemes WHERE lemma = %s", (lemma,)
    ).fetchone()[0]
    conn.execute(
        """
        UPDATE user_lexemes SET state = 'seen', source = 'v2_encountered',
                                source_rank = 1
         WHERE user_id = %s AND lexeme_id = %s
        """,
        (user_id, lexeme_id),
    )


def test_the_repair_restores_demoted_floor_rows(conn, user) -> None:
    svc.assume_top_frequency_known(conn, user, 5)
    target = conn.execute(
        "SELECT lemma FROM lexemes WHERE freq_rank = 1"
    ).fetchone()[0]
    _demote_a_floor_row(conn, user, target)
    assert state_of(conn, user, target) == "seen"

    assert svc.count_demoted_floor_rows(conn, 5) == [(user, 1)]
    assert svc.restore_demoted_floor_rows(conn, 5) == [(user, 1)]

    row = conn.execute(
        """
        SELECT ul.state, ul.source, ul.source_rank
          FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id
         WHERE ul.user_id = %s AND l.lemma = %s
        """,
        (user, target),
    ).fetchone()
    assert row == ("known", "assumption", 0)


def test_the_repair_does_not_move_first_seen_at(conn, user) -> None:
    svc.assume_top_frequency_known(conn, user, 5)
    target = conn.execute("SELECT lemma FROM lexemes WHERE freq_rank = 2").fetchone()[0]
    before = snapshot(conn, user)
    _demote_a_floor_row(conn, user, target)
    svc.restore_demoted_floor_rows(conn, 5)
    assert [row[5] for row in snapshot(conn, user)] == [row[5] for row in before]


def test_the_repair_is_idempotent(conn, user) -> None:
    svc.assume_top_frequency_known(conn, user, 5)
    target = conn.execute("SELECT lemma FROM lexemes WHERE freq_rank = 3").fetchone()[0]
    _demote_a_floor_row(conn, user, target)
    svc.restore_demoted_floor_rows(conn, 5)
    after = snapshot(conn, user)
    assert svc.restore_demoted_floor_rows(conn, 5) == []
    assert svc.count_demoted_floor_rows(conn, 5) == []
    assert snapshot(conn, user) == after


def test_the_repair_leaves_self_produced_rows_alone(conn, user) -> None:
    """Self-produced English outranks the floor's hypothesis. Raising those
    would be a second bug, not a repair."""
    svc.assume_top_frequency_known(conn, user, 5)
    target = conn.execute("SELECT lemma FROM lexemes WHERE freq_rank = 4").fetchone()[0]
    svc.record(conn, user, [LedgerEntry(target, "known", "v2_produced")])
    assert svc.count_demoted_floor_rows(conn, 5) == []
    svc.restore_demoted_floor_rows(conn, 5)
    row = conn.execute(
        """
        SELECT ul.source FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id
         WHERE ul.user_id = %s AND l.lemma = %s
        """,
        (user, target),
    ).fetchone()
    assert row == ("v2_produced",)


def test_the_repair_ignores_lemmas_outside_the_floor(conn, user) -> None:
    svc.assume_top_frequency_known(conn, user, 5)
    add_lexeme(conn, "w4aoutside", freq_rank=99_000)
    svc.record(conn, user, [LedgerEntry("w4aoutside", "seen", "v2_encountered")])
    assert svc.count_demoted_floor_rows(conn, 5) == []


# ── the regression test for the whole slice ─────────────────────────────────


def test_a_harvest_on_a_fresh_floor_demotes_nothing(conn, user) -> None:
    """The shape of the production failure, end to end.

    Seed the floor, run the harvest over v2 content that mentions floor words,
    and coverage must not fall. Under W4's rule this dropped below the floor
    size; that is the number that reached production.
    """
    floor_size = 200
    svc.assume_top_frequency_known(conn, user, floor_size)
    floor_lemmas = [
        row[0]
        for row in conn.execute(
            "SELECT lemma FROM lexemes WHERE freq_rank <= %s ORDER BY freq_rank",
            (floor_size,),
        ).fetchall()
    ]
    exposure = " ".join(floor_lemmas[:60])
    conn.execute(
        """
        INSERT INTO readings (user_id, title, body, questions)
        VALUES (%s, 'W4a fixture', %s, '[]'::jsonb)
        """,
        (user, exposure),
    )
    conn.execute(
        """
        INSERT INTO chunks (user_id, chunk, full_sentence, presented_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (user, floor_lemmas[3], exposure),
    )

    covered_before = len(svc.known_lemmas(conn, user))
    svc.harvest_v2(conn, user)
    covered_after = len(svc.known_lemmas(conn, user))

    assert covered_before == floor_size
    assert covered_after >= floor_size, (
        f"the harvest demoted {covered_before - covered_after} floor lemmas"
    )


def test_every_source_that_may_lower_is_a_declared_source() -> None:
    assert MAY_LOWER <= set(SOURCE_RANK)
