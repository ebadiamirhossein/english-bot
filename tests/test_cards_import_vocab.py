"""`core.cards.import_vocab` and `core.cards.backfill_lexemes`, against a real DB.

Every property here is about which rows a write touches and which rows a
predicate can SEE, and neither is a property of a function's arguments.

**The load-bearing test is
`test_a_chunk_derived_card_is_invisible_until_the_backfill_runs`.** It asserts
both directions of the defect W8f was built on: `migrate_chunks` set no
`lexeme_id` and always set `source_chunk_id`, so before the backfill every card
in the deck was invisible to the duplicate guarantee, and importing the very file
S24a had already imported would have written a second `tier` card. Asserting only
the fixed direction would let the blindness return unseen.
"""

from __future__ import annotations

import inspect
import secrets
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

from core.cards import backfill_lexemes, import_vocab
from core.cards.fsrs import initial_state
from core.config import load_settings
from core.services import cards as svc

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "vocab_import"
TRANCY = FIXTURES / "trancy.csv"
LR = FIXTURES / "languagereactor.csv"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    """A learner with `native_language='fa'`, matching both fixtures."""
    row = db.execute(
        "INSERT INTO users (name, native_language, cefr_level, auth_email, "
        "onboarded) VALUES ('w8f-import', 'fa', 'B1', %s, TRUE) RETURNING id",
        (f"w8f-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


def _cards(db, user_id):
    db.rollback()  # see a commit made on another connection
    return db.execute(
        "SELECT card_type, back, lexeme_id FROM cards WHERE user_id = %s "
        "ORDER BY id",
        (user_id,),
    ).fetchall()


def _typing(monkeypatch, value):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: str(value))


def _refuse_input(monkeypatch, why):
    def _boom(*_a, **_k):
        raise AssertionError(why)

    monkeypatch.setattr("builtins.input", _boom)


def _chunk_derived_card(db, user_id, *, back, card_type="production"):
    """A card in `migrate_chunks`' EXACT shape: a chunk, and no `lexeme_id`.

    Built by hand and not through `migrate_chunks` because the point is the
    shape of the rows already on production, and this test must keep asserting
    it even if that module changes.
    """
    chunk = db.execute(
        "INSERT INTO chunks (user_id, chunk, meaning, source) "
        "VALUES (%s, %s, 'gloss', 'vocabulary') RETURNING id",
        (user_id, back),
    ).fetchone()[0]
    state = initial_state(due=NOW)
    card = db.execute(
        """
        INSERT INTO cards (user_id, card_type, source_chunk_id, source_ref,
                           front, back, register, register_source,
                           fsrs_state, fsrs_step, due, lapses, reps)
        VALUES (%s, %s, %s, 'vocabulary', 'gloss', %s, 'neutral',
                'migration_default', %s, %s, %s, 0, 0) RETURNING id
        """,
        (user_id, card_type, chunk, back, state.fsrs_state, state.fsrs_step, NOW),
    ).fetchone()[0]
    db.commit()
    return int(card)


# ── the importer ───────────────────────────────────────────────────────────


def test_the_default_is_dry_and_never_prompts(db, learner, monkeypatch) -> None:
    _refuse_input(monkeypatch, "a dry run must not ask for confirmation")
    assert import_vocab.dry_run(TRANCY, user_id=learner, now=NOW) == 0
    assert _cards(db, learner) == []


def test_a_dry_run_grows_no_lexemes(db, learner) -> None:
    """`ensure_lexeme` INSERTs, so a dry run resolving the ordinary way would
    quietly add rows while reporting that it wrote nothing."""
    before = db.execute("SELECT count(*) FROM lexemes").fetchone()[0]
    import_vocab.dry_run(TRANCY, user_id=learner, now=NOW)
    db.rollback()
    assert db.execute("SELECT count(*) FROM lexemes").fetchone()[0] == before


def test_apply_creates_two_cards_per_word(db, learner, monkeypatch) -> None:
    _typing(monkeypatch, 9)
    assert import_vocab.apply(TRANCY, user_id=learner, now=NOW) == 0
    rows = _cards(db, learner)
    assert len(rows) == 18
    assert {r[0] for r in rows} == {"recognition", "production"}


def test_a_second_apply_writes_nothing(db, learner, monkeypatch) -> None:
    """Idempotency proved by running it, not asserted."""
    _typing(monkeypatch, 9)
    import_vocab.apply(TRANCY, user_id=learner, now=NOW)
    before = len(_cards(db, learner))

    _refuse_input(monkeypatch, "a second run has nothing to confirm")
    assert import_vocab.apply(TRANCY, user_id=learner, now=NOW) == 0
    assert len(_cards(db, learner)) == before == 18


def test_the_wrong_count_typed_back_writes_nothing(db, learner, monkeypatch) -> None:
    _typing(monkeypatch, 99)
    assert import_vocab.apply(TRANCY, user_id=learner, now=NOW) == 1
    assert _cards(db, learner) == []


def test_the_import_writes_the_ledger_as_a_tap(db, learner, monkeypatch) -> None:
    """A capture IS a tap — the learner met the word and looked it up. `tapped`
    already exists at rank 2, so the ledger needs no new source value."""
    _typing(monkeypatch, 9)
    import_vocab.apply(TRANCY, user_id=learner, now=NOW)
    db.rollback()
    rows = db.execute(
        "SELECT DISTINCT state, source, source_rank FROM user_lexemes "
        "WHERE user_id = %s",
        (learner,),
    ).fetchall()
    assert rows == [("seen", "tapped", 2)]


def test_a_native_language_mismatch_refuses_the_whole_file(db) -> None:
    """The user row wins over the export's own target-language column, and the
    refusal is whole-file: a gloss in a language the learner does not read is
    noise (S24's reason for never auto-sharing a Trancy import)."""
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w8f-lt', 'lt', %s, TRUE) RETURNING id",
        (f"w8f-lt-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        with pytest.raises(import_vocab.ImportRefused, match="native_language"):
            import_vocab.dry_run(LR, user_id=user_id, now=NOW)
        assert _cards(db, user_id) == []
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


def test_the_language_reactor_card_carries_its_real_sentence(
    db, learner, monkeypatch
) -> None:
    _typing(monkeypatch, 2)
    import_vocab.apply(LR, user_id=learner, now=NOW)
    db.rollback()
    row = db.execute(
        "SELECT context_sentence, source_title, captured_at, register_source "
        "FROM cards WHERE user_id = %s AND back = 'devour'",
        (learner,),
    ).fetchone()
    assert row[0].startswith("We Americans devour eagerly")
    assert row[1] == "Autobiography of Benjamin Franklin"
    assert row[2] is not None
    assert row[3] == "import_default"


def test_no_module_in_this_slice_can_reach_the_model(  ) -> None:
    """PRD §7.1's whole point: LR supplies the sentence, so nothing generates.

    S24a's generator is the measured cause of the deck's 50% work bias (#99),
    and #99's status says its remaining surface is the import paths. This is an
    import path, and it cannot inherit the bias because it makes no call.
    """
    for module in ("exports", "capture", "import_vocab", "backfill_lexemes"):
        source = Path(f"packages/core/cards/{module}.py").read_text()
        body = source.split('"""', 2)[2]
        assert "core.llm" not in body
        assert "import llm" not in body


def test_no_sql_lives_in_the_cards_package_modules() -> None:
    """#59 stays this project's only boundary exemption."""
    for module in (import_vocab, backfill_lexemes):
        body = inspect.getsource(module).split('"""', 2)[2]
        for banned in ("SELECT ", "INSERT ", "UPDATE ", "DELETE "):
            assert banned not in body, f"{module.__name__} holds SQL: {banned}"


# ── the backfill, and the blindness it exists to remove ────────────────────


def test_a_chunk_derived_card_is_invisible_until_the_backfill_runs(
    db, learner, monkeypatch
) -> None:
    """BOTH directions of W8f's founding defect, in one test.

    `migrate_chunks` set no `lexeme_id`, so before the backfill the anti-join
    cannot see this card and the import writes a SECOND `tier` production card.
    After the backfill it sees it and writes nothing. Asserting only the second
    half would let the blindness return unnoticed.
    """
    _chunk_derived_card(db, learner, back="tier")
    db.rollback()

    # BEFORE: blind. `tier` is not in the anti-join at all.
    assert "tier" not in svc.lemmas_with_a_card(db, learner)

    # AFTER: the backfill gives it a lemma, and the anti-join sees it.
    _typing(monkeypatch, 1)
    assert backfill_lexemes.apply() == 0
    db.rollback()
    assert "tier" in svc.lemmas_with_a_card(db, learner)

    # The other eight words are genuinely new and DO import. The property under
    # test is narrower and is the one that matters: `tier` gains no second card.
    _typing(monkeypatch, 8)
    import_vocab.apply(TRANCY, user_id=learner, now=NOW)
    db.rollback()
    backs = [r[1] for r in _cards(db, learner)]
    assert backs.count("tier") == 1, "a second `tier` card was written"

    # And the counterfactual, so the guarantee is not confused with luck: with
    # the lemma removed again the anti-join goes blind and the row comes back as
    # importable — which is exactly what would have shipped without the backfill.
    db.execute(
        "UPDATE cards SET lexeme_id = NULL WHERE user_id = %s AND back = 'tier'",
        (learner,),
    )
    db.commit()
    assert "tier" not in svc.lemmas_with_a_card(db, learner)


def test_tier_resolves_to_tier_and_never_to_ti(db, learner) -> None:
    """`lemmatize("tier") == "ti"` — a WRONG resolution, not a failed one.

    `tier` is absent from the seed list, so the suffix step strips `-er`,
    proposes `ti`, and `ti` IS a known lemma (rank 9,856, an OpenSubtitles
    artefact). Nothing was invented and the answer is still wrong. Migration 013
    says `lexeme_id` is what `grade_card` writes the ledger from, so a card
    pointing at `ti` would corrupt the ledger on every grade — and it would have
    read GREEN, because the importer makes the same error on the same input.
    """
    from core.lexicon.normalize import lemmatize

    # The defect this test guards, pinned so a future fix explains this file.
    assert lemmatize("tier") == "ti"

    lexeme_id, _path = svc.resolve_capture_lemma(db, "tier", grow=True)
    db.rollback()
    lemma = db.execute(
        "SELECT lemma FROM lexemes WHERE id = %s", (lexeme_id,)
    ).fetchone()[0]
    assert lemma == "tier"

    # The PATH is deliberately not asserted: whether `tier` is grown or already
    # present depends on whether an earlier capture added it, which is a fact
    # about this database and not about the rule. The rule is that the answer is
    # `tier`. The grown-versus-identity split IS checked, on a word no run can
    # have created — see `test_a_word_absent_from_the_dictionary_would_grow`.

    # `ti` must be untouched: still the seed row, never repurposed.
    ti = db.execute(
        "SELECT origin, freq_rank FROM lexemes WHERE lemma = 'ti'"
    ).fetchone()
    assert ti == ("seed", 9856)


def test_a_word_absent_from_the_dictionary_would_grow(db) -> None:
    """The dry run's two-way split, on a token nothing can have added.

    This is the check the deployment step reads: `7 identity + 2 grown` is the
    evidence, and a bare total of `9` hides a `tier` that resolved to `ti`.
    """
    nonsense = "qwvbxzzlemma"
    assert db.execute(
        "SELECT count(*) FROM lexemes WHERE lemma = %s", (nonsense,)
    ).fetchone()[0] == 0

    lexeme_id, path = svc.resolve_capture_lemma(db, nonsense, grow=False)
    db.rollback()
    assert (lexeme_id, path) == (None, "would_grow")
    assert db.execute(
        "SELECT count(*) FROM lexemes WHERE lemma = %s", (nonsense,)
    ).fetchone()[0] == 0, "grow=False must write nothing"


def test_a_phrase_reports_unresolved_rather_than_would_grow(db) -> None:
    """`GROWABLE` rejects a space, which is how phrase-backed cards stay out of
    the backfill without anyone filtering for them."""
    assert svc.resolve_capture_lemma(db, "a notch above", grow=False) == (
        None,
        "unresolved",
    )


def test_the_backfill_and_the_importer_resolve_identically() -> None:
    """An earlier draft had the importer growing lexemes while the backfill
    refused to, so the same word was a lemma on one path and not the other."""
    for module in (import_vocab, backfill_lexemes):
        assert "resolve_capture_lemma" in inspect.getsource(module)
    assert "lemmatize" not in inspect.getsource(svc.resolve_capture_lemma).split(
        '"""', 2
    )[2]


def test_a_phrase_back_is_never_grown(db, learner, monkeypatch) -> None:
    """A phrase has no lemma and never will. Permanent and correct, asserted as
    a positive so it does not read as an oversight someone should fix."""
    _chunk_derived_card(db, learner, back="a notch above")
    db.rollback()
    before = db.execute("SELECT count(*) FROM lexemes").fetchone()[0]

    _refuse_input(monkeypatch, "nothing resolves, so nothing is confirmed")
    backfill_lexemes.apply()
    db.rollback()
    assert db.execute("SELECT count(*) FROM lexemes").fetchone()[0] == before
    assert db.execute(
        "SELECT lexeme_id FROM cards WHERE user_id = %s", (learner,)
    ).fetchone()[0] is None


def test_the_backfill_refuses_a_collision_and_writes_nothing(
    db, learner, monkeypatch
) -> None:
    """Two cards resolving to one (user, lemma, card type) would violate 015's
    index. The pass counts those groups first and stops with the ids named,
    rather than applying most rows and failing on the one that collides."""
    a = _chunk_derived_card(db, learner, back="notch")
    b = _chunk_derived_card(db, learner, back="Notch")
    db.rollback()

    _refuse_input(monkeypatch, "a collision must stop before confirmation")
    assert backfill_lexemes.apply() == 1
    db.rollback()
    rows = db.execute(
        "SELECT lexeme_id FROM cards WHERE id IN (%s, %s)", (a, b)
    ).fetchall()
    assert [r[0] for r in rows] == [None, None]


def test_the_backfill_default_is_dry_and_writes_nothing(
    db, learner, monkeypatch
) -> None:
    _chunk_derived_card(db, learner, back="notch")
    db.rollback()
    _refuse_input(monkeypatch, "a dry run must not ask for confirmation")
    assert backfill_lexemes.dry_run() == 0
    db.rollback()
    assert db.execute(
        "SELECT lexeme_id FROM cards WHERE user_id = %s", (learner,)
    ).fetchone()[0] is None


def test_the_backfill_touches_only_lexeme_id(db, learner, monkeypatch) -> None:
    card = _chunk_derived_card(db, learner, back="notch")
    db.rollback()
    before = db.execute(
        "SELECT front, back, register, register_source, source_chunk_id, due "
        "FROM cards WHERE id = %s",
        (card,),
    ).fetchone()

    _typing(monkeypatch, 1)
    backfill_lexemes.apply()
    db.rollback()
    after = db.execute(
        "SELECT front, back, register, register_source, source_chunk_id, due "
        "FROM cards WHERE id = %s",
        (card,),
    ).fetchone()
    assert before == after


def test_the_backfill_never_modifies_chunks(db, learner, monkeypatch) -> None:
    _chunk_derived_card(db, learner, back="notch")
    db.rollback()
    before = db.execute(
        "SELECT id, chunk, meaning, source FROM chunks WHERE user_id = %s "
        "ORDER BY id",
        (learner,),
    ).fetchall()

    _typing(monkeypatch, 1)
    backfill_lexemes.apply()
    db.rollback()
    after = db.execute(
        "SELECT id, chunk, meaning, source FROM chunks WHERE user_id = %s "
        "ORDER BY id",
        (learner,),
    ).fetchall()
    assert before == after
