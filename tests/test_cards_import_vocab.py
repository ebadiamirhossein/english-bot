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
    """A learner with `native_language='fa'`, matching both fixtures.

    **Floor 0** (W13c). This learner never had W4's materialised floor rows, so
    the mechanics below were written against an empty ledger; since W13c the
    floor is computed for every learner (default 2000), and `proper` (rank
    1833) would be skipped as known. Floor 0 keeps these tests about the
    import's mechanics; what a real floor does to a file is
    `test_a_word_inside_the_floor_is_skipped_as_known`.
    """
    row = db.execute(
        "INSERT INTO users (name, native_language, cefr_level, auth_email, "
        "onboarded, known_word_floor) "
        "VALUES ('w8f-import', 'fa', 'B1', %s, TRUE, 0) RETURNING id",
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


def _chunk_derived_card(db, user_id, *, back, card_type="production",
                        source="vocabulary"):
    """A card in `migrate_chunks`' EXACT shape: a chunk, and no `lexeme_id`.

    Built by hand and not through `migrate_chunks` because the point is the
    shape of the rows already on production, and this test must keep asserting
    it even if that module changes.
    """
    chunk = db.execute(
        "INSERT INTO chunks (user_id, chunk, meaning, source) "
        "VALUES (%s, %s, 'gloss', %s) RETURNING id",
        (user_id, back, source),
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


def test_a_word_inside_the_floor_is_imported_and_its_look_up_recorded(
    db, learner, monkeypatch
) -> None:
    """**#435, operator ruling 2026-09-25: a deliberate look-up overrides the
    known-word floor** — it is evidence of not-knowing (W4a: `tapped` is in
    `MAY_LOWER`). `proper` is rank 1833, inside the default floor of 2000; the
    import makes its cards AND writes the tap, which lowers the floor's virtual
    `known` to `seen` for this learner.

    Red, 2026-09-25, against the pre-fix `_plan_file` (it planned against
    `known_lemmas`, the floor included): `apply` printed 8 importable rows, the
    typed 9 did not match, it returned 1 and wrote nothing — `assert 1 == 0`.
    The test it replaces, `test_a_word_inside_the_floor_is_skipped_as_known`,
    pinned the old behaviour and was written to fail once this landed."""
    db.execute("UPDATE users SET known_word_floor = 2000 WHERE id = %s", (learner,))
    db.commit()
    _typing(monkeypatch, 9)
    assert import_vocab.apply(TRANCY, user_id=learner, now=NOW) == 0
    assert len(_cards(db, learner)) == 18
    assert db.execute(
        """
        SELECT COUNT(*) FROM cards c JOIN lexemes l ON l.id = c.lexeme_id
         WHERE c.user_id = %s AND l.lemma = 'proper'
        """,
        (learner,),
    ).fetchone()[0] == 2
    assert db.execute(
        """
        SELECT ul.state, ul.source FROM user_lexemes ul
          JOIN lexemes l ON l.id = ul.lexeme_id
         WHERE ul.user_id = %s AND l.lemma = 'proper'
        """,
        (learner,),
    ).fetchall() == [("seen", "tapped")]


def test_a_word_known_by_evidence_is_still_skipped(db, learner, monkeypatch) -> None:
    """The ruling overrides the FLOOR, which is a hypothesis — not evidence.
    A lemma this learner has an evidence row at `known` for (here a `review`
    row — the learner graded it known) is still planned as already known:
    no card, and the row is not touched. Red, 2026-09-25, against a `_plan_file`
    that planned against no known set at all (the fix taken one step too far):
    9 importable, the typed 8 did not match, `assert 1 == 0`."""
    db.execute(
        """
        INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank)
        SELECT %s, id, 'known', 'review', 5 FROM lexemes WHERE lemma = 'proper'
        """,
        (learner,),
    )
    db.commit()
    _typing(monkeypatch, 8)
    assert import_vocab.apply(TRANCY, user_id=learner, now=NOW) == 0
    assert len(_cards(db, learner)) == 16
    assert db.execute(
        """
        SELECT ul.state, ul.source FROM user_lexemes ul
          JOIN lexemes l ON l.id = ul.lexeme_id
         WHERE ul.user_id = %s AND l.lemma = 'proper'
        """,
        (learner,),
    ).fetchall() == [("known", "review")]


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
    """`lemmatize("tier")` — a WRONG resolution, not a failed one.

    `tier` is absent from the seed list, so the suffix step stripped `-er`,
    proposed `ti`, and `ti` IS a known lemma (rank 9,856, an OpenSubtitles
    artefact). Nothing was invented and the answer was still wrong. Migration 013
    says `lexeme_id` is what `grade_card` writes the ledger from, so a card
    pointing at `ti` would corrupt the ledger on every grade — and it would have
    read GREEN, because the importer makes the same error on the same input.

    **THE FIX ARRIVED IN W12a AND THIS IS THE FILE IT WAS ASKED TO EXPLAIN.**
    The pin read ``assert lemmatize("tier") == "ti"`` and was described as
    *pinned so a future fix explains this file*. W12a (#177) deleted the `-er`
    and `-est` branches of ``_suffix_candidates``, so `tier` no longer resolves
    at all and the assertion becomes ``is None``. **The pin is UPDATED, not
    deleted**: the surrounding test is the one that proves
    ``resolve_capture_lemma`` never routed through `lemmatize` in the first
    place, and that is still worth asserting.

    Why `None` and not `tier`: `lemmatize` resolves, it does not create. `tier`
    is not in the seed list, so the honest answer is *I cannot account for
    this*, and an unresolved token counts unknown — coverage reads low rather
    than falsely high. Growing `tier` into a lexeme is
    ``resolve_capture_lemma``'s job, which is what the rest of this test checks.
    """
    from core.lexicon.normalize import lemmatize

    # W12a. Was `== "ti"`; the artefact resolution is gone, not re-pointed.
    assert lemmatize("tier") is None

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


# ── the scope the production dry run forced ────────────────────────────────


def test_a_slang_card_is_out_of_reach_of_the_backfill(db, learner, monkeypatch) -> None:
    """#180. `mid` identity-matches a seed lexeme meaning *middle*.

    This is the failure mode neither existing guard was built for. #177's `ti`
    came through `lemmatize`'s SUFFIX step, so refusing that step fixed it.
    `mid` arrives through the IDENTITY step: the string is a real lemma, the
    match is exact, nothing is invented, and the answer is still wrong, because
    `lexemes` carries `pos` and no sense distinction at all.

    Migration 013 says `lexeme_id` is what `grade_card` writes the ledger from,
    so the card would have written evidence for *middle* on every grade of the
    slang sense. The backfill therefore reaches only `vocabulary`-sourced
    chunks, where one word means one thing.
    """
    card = _chunk_derived_card(
        db, learner, back="mid", card_type="recognition", source="slang"
    )
    db.rollback()

    assert card not in [r[0] for r in svc.cards_needing_a_lexeme(db)]

    _refuse_input(monkeypatch, "a slang card is out of scope; nothing to confirm")
    backfill_lexemes.apply()
    db.rollback()
    assert db.execute(
        "SELECT lexeme_id FROM cards WHERE id = %s", (card,)
    ).fetchone()[0] is None


def test_the_backfill_grows_no_slang_lemma_into_the_shared_dictionary(
    db, learner, monkeypatch
) -> None:
    """`lexemes` is GLOBAL — one row serves every learner — so growing it with
    `delulu` and `low-key` is a product decision, not a backfill's to make."""
    _chunk_derived_card(
        db, learner, back="delulu", card_type="recognition", source="slang"
    )
    db.rollback()
    before = db.execute("SELECT count(*) FROM lexemes").fetchone()[0]

    _refuse_input(monkeypatch, "nothing is in scope; nothing to confirm")
    backfill_lexemes.apply()
    db.rollback()
    assert db.execute("SELECT count(*) FROM lexemes").fetchone()[0] == before
    assert db.execute(
        "SELECT count(*) FROM lexemes WHERE lemma = 'delulu'"
    ).fetchone()[0] == 0


def test_the_scope_is_a_property_of_the_row_not_a_date_or_an_id_list(db) -> None:
    """`retire_chunk_cloze`'s rule, and the narrowing must not break it.

    A date range sweeps rows nobody looked at and an id list stops being true
    the moment the database changes. `chunks.source = 'vocabulary'` is neither:
    it is a statement about what the card teaches.
    """
    source = inspect.getsource(svc.cards_needing_a_lexeme)
    sql = source.split('"""', 2)[2]
    for banned in ("created_at", "id = ANY", "id IN (", "BETWEEN", "due <"):
        assert banned not in sql
    assert "k.source = 'vocabulary'" in sql


def test_a_captured_card_is_outside_the_backfill_by_construction(
    db, learner
) -> None:
    """W13's cards carry no `source_chunk_id` and set `lexeme_id` at creation,
    so no run of this command at any moment can reach one — a property of the
    predicate, not of when it is run."""
    state = initial_state(due=NOW)
    card = db.execute(
        "INSERT INTO cards (user_id, card_type, front, back, register, "
        "register_source, fsrs_state, fsrs_step, due) VALUES "
        "(%s, 'production', 'f', 'b', 'neutral', 'import_default', %s, %s, %s) "
        "RETURNING id",
        (learner, state.fsrs_state, state.fsrs_step, NOW),
    ).fetchone()[0]
    db.commit()
    assert card not in [r[0] for r in svc.cards_needing_a_lexeme(db)]


def test_card_17s_meaning_is_two_columns_of_the_same_trancy_row(db) -> None:
    """Finding 1, corrected: the provenance claim is STRONGER than first stated.

    `cards.meaning` is not the Translation column alone. S24a composed it with
    `watch_import.format_meaning`, which appends the phonetic:

        btrim(Translation) || ' (' || Phonetic || ')'

    So card 17 carries TWO columns from the same row, through a function whose
    source is in this repository — which is a tighter tie to this exact file
    than a single-column match would have been. The first deployment query
    asserted the Translation alone and failed for that reason.
    """
    import csv
    import io

    from core.services.watch_import import format_meaning

    text = (FIXTURES / "trancy.csv").read_text(encoding="utf-8-sig")
    row = next(r for r in csv.reader(io.StringIO(text, newline="")) if r[0] == "tier")
    translation, phonetic = row[2], row[1]

    # Hardcoded, never derived from the function under test (§3 rule 5).
    # `\u200c` is a ZERO WIDTH NON-JOINER and is written as an escape so it
    # cannot be lost to a copy-paste that strips invisible characters.
    expected = "سطح ردیف;  چیدمان در سطوح طبقه\u200cبندی (/tɪər/)"
    assert format_meaning(translation, phonetic) == expected
    # And the SQL form the deployment step uses, computed independently.
    assert translation.strip() + " (" + phonetic + ")" == expected
