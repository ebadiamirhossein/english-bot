"""W8f: the capture fan-out and the filter. **Pure — no database.**

`plan_for_capture` takes the ledger and the anti-join as arguments rather than
querying them, which is what makes this file possible. `migrate_chunks`'
`plan_for_chunk` is the precedent and the reason is CLAUDE.md §3 rule 5: the
fan-out table is the thing most likely to be wrong.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.cards import CAPTURE_CARD_TYPES, REGISTER_SOURCES
from core.cards.capture import (
    BUCKETS,
    IMPORTED,
    SKIP_ALREADY_KNOWN,
    SKIP_DUPLICATE,
    SKIP_NO_GLOSS,
    SKIP_TOO_RARE,
    first_sense,
    plan_for_capture,
    source_ref,
)
from core.cards.exports import CaptureRecord, parse_language_reactor, parse_trancy

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "vocab_import"
LR = parse_language_reactor((FIXTURES / "languagereactor.csv").read_text("utf-8-sig"))
TRANCY = parse_trancy((FIXTURES / "trancy.csv").read_text("utf-8-sig"))


def _by_lemma(records, lemma):
    return next(r for r in records if r.lemma == lemma)


# ── the fan-out ────────────────────────────────────────────────────────────


def test_one_capture_becomes_a_recognition_and_a_production_card() -> None:
    plan = plan_for_capture(_by_lemma(LR, "devour"), now=NOW)
    assert plan.bucket == IMPORTED
    assert [c["card_type"] for c in plan.cards] == list(CAPTURE_CARD_TYPES)


def test_no_capture_ever_produces_a_cloze_card() -> None:
    """#147, not W8b's ruling. Stated as a negative so it reads as intended.

    W8b removed the CHUNK cloze because a chunk is an idiom. A single word in a
    real sentence is exactly what cloze is for and would be a good card — the
    blocker is that `make_sentence_with_gap` replaces a substring, so it gaps
    *tier* out of *tiers*. Capture cloze arrives at W13 with a whole-word gapper.
    """
    for record in LR + TRANCY:
        plan = plan_for_capture(record, now=NOW)
        assert all(c["card_type"] != "cloze" for c in plan.cards)


def test_nothing_in_this_module_imports_the_broken_gapper() -> None:
    """The rule above, held by the import graph rather than by discipline."""
    source = Path("packages/core/cards/capture.py").read_text()
    assert "make_sentence_with_gap" not in source.split('"""', 2)[2]


def test_the_production_card_is_l1_to_english() -> None:
    """PRD §5: "Production | L1 gloss + context hint | the English word"."""
    plan = plan_for_capture(_by_lemma(LR, "devour"), now=NOW)
    production = next(c for c in plan.cards if c["card_type"] == "production")
    assert production["front"] == "بلعیدن"
    assert production["back"] == "devour"


def test_the_recognition_card_fronts_the_real_sentence() -> None:
    plan = plan_for_capture(_by_lemma(LR, "devour"), now=NOW)
    recognition = next(c for c in plan.cards if c["card_type"] == "recognition")
    assert recognition["front"].startswith("We Americans devour eagerly")
    assert recognition["back"] == "بلعیدن"


def test_a_trancy_card_carries_no_sentence_and_none_is_invented() -> None:
    """#99's constraint: a path that GENERATES context inherits §4's weights.

    This path generates nothing, so it cannot inherit the bias. A Trancy row
    becomes a smaller card — word plus phonetic — not an invented sentence.
    """
    plan = plan_for_capture(_by_lemma(TRANCY, "notch"), now=NOW)
    assert all(c["context_sentence"] is None for c in plan.cards)
    recognition = next(c for c in plan.cards if c["card_type"] == "recognition")
    assert recognition["front"] == "notch  /nɑːtʃ/"


def test_every_card_carries_a_register_and_its_source() -> None:
    """Migration 013: `register` is NOT NULL with no default, deliberately."""
    plan = plan_for_capture(_by_lemma(LR, "swain"), now=NOW)
    for card in plan.cards:
        assert card["register"] == "neutral"
        assert card["register_source"] == "import_default"
    assert "import_default" in REGISTER_SOURCES


def test_provenance_reaches_every_card() -> None:
    plan = plan_for_capture(_by_lemma(LR, "swain"), now=NOW)
    for card in plan.cards:
        assert card["source_title"] == "Autobiography of Benjamin Franklin"
        assert card["captured_at"] == "2026-08-26 09:22"
        assert card["source_ref"] == "capture_language_reactor_gb_20203"


def test_a_capture_source_ref_never_looks_like_prep() -> None:
    """`refuse_forbidden_prep_register` matches on the `prep_` prefix."""
    for record in LR + TRANCY:
        assert not source_ref(record).startswith("prep_")


# ── the gloss ──────────────────────────────────────────────────────────────


def test_the_front_carries_one_sense_and_meaning_keeps_them_all() -> None:
    plan = plan_for_capture(_by_lemma(LR, "devour"), now=NOW)
    production = next(c for c in plan.cards if c["card_type"] == "production")
    assert production["front"] == "بلعیدن"
    assert production["meaning"] == "بلعیدن, خوردن, فرو بردن"


def test_each_format_splits_senses_its_own_way() -> None:
    """LR separates with commas; Trancy with semicolons and a POS prefix."""
    assert first_sense("a, b, c", "language_reactor") == "a"
    assert first_sense("n. a b; v. c d", "trancy") == "n. a b"
    # No separator at all: the whole gloss is the sense, never an empty front.
    assert first_sense("one", "trancy") == "one"


# ── the filter: the ledger, and NOT the frequency floor ────────────────────


def test_a_known_word_is_skipped() -> None:
    plan = plan_for_capture(
        _by_lemma(TRANCY, "proper"), now=NOW, known_lemmas=frozenset({"proper"})
    )
    assert plan.bucket == SKIP_ALREADY_KNOWN
    assert plan.cards == ()


def test_a_word_merely_seen_is_imported() -> None:
    """`seen`/`learning` are not in the covered set — having met a word and not
    yet learned it is precisely the case a card exists for."""
    plan = plan_for_capture(
        _by_lemma(TRANCY, "proper"), now=NOW, known_lemmas=frozenset()
    )
    assert plan.bucket == IMPORTED


def test_a_missing_freq_rank_is_never_a_rejection_reason() -> None:
    """D2's ruling, as a negative, because the first draft of this slice
    failed it by design.

    `tier` and `bootstrap` are absent from the 15,000-lemma seed list. That is a
    fact about an OpenSubtitles-derived list, not about the words, and migration
    010's "NULL sorts last" is a SORTING rule. Using it to reject would silently
    upgrade *absent from our list* into *too rare to be worth a card*.
    """
    for lemma in ("tier", "bootstrap"):
        assert plan_for_capture(_by_lemma(TRANCY, lemma), now=NOW).bucket == IMPORTED


def test_a_very_rare_captured_word_is_imported() -> None:
    """`swain` is rank 11,886 and `psychosis` 14,342. A capture is the
    strongest statement of intent this system receives: the learner met the
    word, did not know it, and looked it up."""
    assert plan_for_capture(_by_lemma(LR, "swain"), now=NOW).bucket == IMPORTED
    assert plan_for_capture(_by_lemma(TRANCY, "psychosis"), now=NOW).bucket == IMPORTED


def test_the_too_rare_bucket_exists_and_nothing_can_set_it() -> None:
    """Kept so reinstating a floor is a number, not new plumbing — and asserted
    empty so one cannot be reinstated by accident."""
    assert SKIP_TOO_RARE in BUCKETS
    for record in LR + TRANCY:
        assert plan_for_capture(record, now=NOW).bucket != SKIP_TOO_RARE


# ── duplicates ─────────────────────────────────────────────────────────────


def test_any_existing_card_skips_the_whole_row() -> None:
    """Row-level, not per card type. A word that already has a production card
    does not quietly gain a recognition one — filed as a cost against W13."""
    plan = plan_for_capture(
        _by_lemma(TRANCY, "tier"), now=NOW, lemmas_with_a_card=frozenset({"tier"})
    )
    assert plan.bucket == SKIP_DUPLICATE
    assert plan.cards == ()


def test_the_deck_wins_over_the_ledger_when_both_match() -> None:
    """Reported as a duplicate rather than as already-known: the card is the
    more specific fact, and the buckets must not double-count."""
    plan = plan_for_capture(
        _by_lemma(TRANCY, "tier"),
        now=NOW,
        known_lemmas=frozenset({"tier"}),
        lemmas_with_a_card=frozenset({"tier"}),
    )
    assert plan.bucket == SKIP_DUPLICATE


def test_a_row_with_no_gloss_makes_no_card() -> None:
    empty = CaptureRecord(lemma="x", gloss="   ", source_format="trancy")
    plan = plan_for_capture(empty, now=NOW)
    assert plan.bucket == SKIP_NO_GLOSS
    assert plan.cards == ()


# ── the accounting identity ────────────────────────────────────────────────


def test_every_row_lands_in_exactly_one_known_bucket() -> None:
    """`migrate_chunks`' property: the buckets sum to the rows read, so
    "nothing was silently lost" is a subtraction and not a claim."""
    plans = [plan_for_capture(r, now=NOW) for r in LR + TRANCY]
    assert len(plans) == 11
    assert all(p.bucket in BUCKETS for p in plans)
    assert sum(1 for p in plans if p.bucket == IMPORTED) == 11


def test_the_planner_reads_no_clock() -> None:
    """CLAUDE.md §3 rule 6. `now` is injected, so a due date is reproducible."""
    source = Path("packages/core/cards/capture.py").read_text()
    body = source.split('"""', 2)[2]
    assert "datetime.now" not in body and "utcnow" not in body
