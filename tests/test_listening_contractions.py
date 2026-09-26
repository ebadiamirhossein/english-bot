"""Launch 2026-09-26, B1: a listening answer matches its transcript modulo the
standard contractions, and a word that is not spoken still fails.

**The evidence (the host's `core.placement.bank --apply`, 2026-09-26):** all
six listening C1 items discarded with `['answer_not_in_transcript',
'stem_transcript_mismatch']`, and listening B2 slots 1 and 3 with
`answer_not_in_transcript` alone. The six C1 stems and the two B2 stems below
are the operator's paste, verbatim. **The answers are not in the paste** (they
are in the host's journal), so each is written here from the band's target —
C1: *could have or might have in fast speech*; B2: *the verb form in the result
half of an if-sentence* — and is a hardcoded expectation, never derived from
the checks under test (CLAUDE.md §3 rule 5).

**THE CAUSE, READ FROM THE CODE BEFORE ANYTHING CHANGED:** `answer_not_in_
transcript` compared the whole answer with ONE word of the transcript, so a
two-word answer could never pass it — B2's two failed on that alone (their stems
reconstructed the transcript exactly). Both checks were also literal about
contractions, which is C1's second code. `gates._audio_gate` and
`gates.audio_round_trip` had the same two defects one billed stage later.

User action: none directly — the operator's top-up `--apply` generates listening
items, and these checks decide which ones a learner can be served.

**RED DEMONSTRATIONS (2026-09-26, `python -B`, `__pycache__` cleared each run):**
the four comparison sites put back to their old literal form (the two checks,
the gapped-word test and the round-trip equality) and the spoken-variant step
removed: **27 of 34 red** — all eighteen C1 cases, all four B2 cases, both `'d`
positives, the `'s` test, the audio gate's two-word case and the heard-spelling
grade. The other seven are guards and passed there by construction; each was
shown red by its own mutation: `answer_spoken_in` returning `True` → the
absent-answer, fixture, different-modal, `'d`-never-the-other-word and `'s`
tests (5 red); `says_the_same` without its punctuation clause → the punctuation
test; `'d` always *would* → both `'d` participle tests; the `unhearable_gap`
block removed → `test_unhearable_gap_is_untouched`; the round-trip equality AND
the gapped-word test both forced true → the audio gate's refusal test.
"""

from __future__ import annotations

import pytest

from core.items import gates
from core.items.checks import deterministic_failures, says_the_same
from core.items.response import Submission, grade
from core.items.schema import parse

LISTENING_CODES = {"answer_not_in_transcript", "stem_transcript_mismatch"}


def item(stem: str, answer: str, transcript: str):
    return parse({
        "item_type": "listening_gap", "track": "life",
        "prompt_text": stem, "answer": answer, "accepted_variants": [answer],
        "transcript": transcript, "cohort": "placement", "error_type": "modal_verb",
        "grammar_target": "Listening, C1: hearing could have or might have in fast speech",
    })


def listening_codes(it) -> set[str]:
    return {f.code for f in deterministic_failures(it)} & LISTENING_CODES


# ── 1. the six C1 stems, contracted and uncontracted ────────────────────────

#: (stem, answer spelled out, the contracted form, the transcript's tail).
C1 = [
    ("She ___ been asleep.", "might have", "might've", "been asleep."),
    ("He ___ forgotten.", "might have", "might've", "forgotten."),
    ("I ___ left them at work.", "could have", "could've", "left them at work."),
    ("Something ___ happened on the line.", "might have", "might've", "happened on the line."),
    ("They ___ gone out.", "could have", "could've", "gone out."),
    ("Something ___ gone wrong at home.", "might have", "might've", "gone wrong at home."),
]


def _head(stem: str) -> str:
    return stem.split("___")[0]


@pytest.mark.parametrize("stem,full,short,tail", C1)
def test_c1_answer_spelled_out_against_contracted_audio(stem, full, short, tail) -> None:
    """The C1 target's own case: the audio says *might've*, the key *might have*."""
    it = item(stem, full, f"{_head(stem)}{short} {tail}")
    assert listening_codes(it) == set()


@pytest.mark.parametrize("stem,full,short,tail", C1)
def test_c1_contracted_answer_against_spelled_out_audio(stem, full, short, tail) -> None:
    """The other direction."""
    it = item(stem, short, f"{_head(stem)}{full} {tail}")
    assert listening_codes(it) == set()


@pytest.mark.parametrize("stem,full,short,tail", C1)
def test_c1_two_word_answer_with_no_contraction_anywhere(stem, full, short, tail) -> None:
    """Cause 1 alone: no contraction at all, and the old check still refused it."""
    it = item(stem, full, f"{_head(stem)}{full} {tail}")
    assert listening_codes(it) == set()


# ── 2. the two B2 if-sentences ──────────────────────────────────────────────

B2 = [
    ("If it rained tomorrow, we ___ the picnic.", "would cancel",
     "If it rained tomorrow, we would cancel the picnic.",
     "If it rained tomorrow, we'd cancel the picnic."),
    ("If I found her number, I ___ a text.", "would send",
     "If I found her number, I would send a text.",
     "If I found her number, I'd send a text."),
]


@pytest.mark.parametrize("stem,answer,spelled,contracted", B2)
def test_b2_if_sentence_as_the_generator_wrote_it(stem, answer, spelled, contracted) -> None:
    """Uncontracted: the stem reconstructed exactly, and the old check refused it."""
    assert listening_codes(item(stem, answer, spelled)) == set()


@pytest.mark.parametrize("stem,answer,spelled,contracted", B2)
def test_b2_if_sentence_after_rule_4_contracts_the_audio(stem, answer, spelled, contracted) -> None:
    """Rule 4 rewrites *we would* → *we'd* in the transcript and re-runs the
    checks (`gates.free_stages`); the item must survive its own repair."""
    repaired, failed = gates.free_stages(item(stem, answer, spelled))
    assert failed is None, failed
    assert repaired.transcript == contracted
    assert listening_codes(repaired) == set()


# ── 3. a word that is not spoken is still refused ───────────────────────────


def test_a_word_that_is_not_spoken_is_still_refused() -> None:
    it = item("If it rained tomorrow, we ___ the picnic.", "would cancel",
              "If it rained tomorrow, we'd postpone the picnic.")
    assert listening_codes(it) == LISTENING_CODES


def test_the_committed_mismatch_fixture_is_still_refused() -> None:
    """`tests/fixtures/items/invalid.json`'s `listening_gap_stem_mismatch`."""
    it = item("I forgot my ___ this morning", "keys", "I lost my wallet this morning")
    assert listening_codes(it) == LISTENING_CODES


def test_a_different_modal_is_not_a_contraction() -> None:
    it = item("She ___ been asleep.", "might have", "She must've been asleep.")
    assert listening_codes(it) == LISTENING_CODES


# ── 4. `'d` — had or would, decided by the next word, never "either" ────────


def test_d_before_a_participle_is_had() -> None:
    assert listening_codes(item("She ___ been asleep.", "had", "She'd been asleep.")) == set()
    assert listening_codes(item("I ___ left them at work.", "had", "I'd left them at work.")) == set()
    assert listening_codes(
        item("I ___ already left.", "had", "I'd already left.")) == set()


def test_d_before_a_bare_verb_is_would() -> None:
    assert listening_codes(item("We ___ cancel it.", "would", "We'd cancel it.")) == set()
    assert listening_codes(item("I ___ rather stay.", "would", "I'd rather stay.")) == set()


def test_d_is_never_read_as_the_other_word() -> None:
    """``listening_gap`` has no text solver, so accepting "either" would let the
    wrong expansion reach a learner. Both directions refused."""
    assert listening_codes(item("She ___ been asleep.", "would", "She'd been asleep.")) == LISTENING_CODES
    assert listening_codes(item("We ___ cancel it.", "had", "We'd cancel it.")) == LISTENING_CODES


def test_s_is_has_before_a_participle_and_is_otherwise() -> None:
    assert listening_codes(item("She ___ gone out.", "has", "She's gone out.")) == set()
    assert listening_codes(item("It ___ raining again.", "is", "It's raining again.")) == set()
    assert listening_codes(item("She ___ gone out.", "is", "She's gone out.")) == LISTENING_CODES


def test_punctuation_inside_the_sentence_still_counts() -> None:
    assert not says_the_same("If it rained, we would cancel it.", "If it rained we'd cancel it.")
    assert says_the_same("If it rained, we would cancel it.", "If it rained, we'd cancel it.")


# ── the gate that is NOT loosened ───────────────────────────────────────────


def test_unhearable_gap_is_untouched() -> None:
    """The host's B2 slot 4, verbatim stem: *up* is reduced at speed."""
    it = item("He gave ___ smoking last year.", "up", "He gave up smoking last year.")
    assert "unhearable_gap" in {f.code for f in deterministic_failures(it)}


# ── what a learner is graded against, and the billed stage after ────────────


def test_the_heard_spelling_is_accepted_when_the_learner_types_it() -> None:
    """The learner hears *might've* and types it. Stored beside the canonical by
    the free stages; the answer, stem and audio are unchanged."""
    passed, failed = gates.free_stages(
        item("She ___ been asleep.", "might have", "She might've been asleep."))
    assert failed is None
    assert passed.answer == "might have"
    assert passed.transcript == "She might've been asleep."
    assert grade(passed, Submission(text="might've")) == (True, "deterministic")
    assert grade(passed, Submission(text="might have")) == (True, "deterministic")
    assert grade(passed, Submission(text="must have")) == (False, "deterministic")


def test_the_audio_gate_hears_a_two_word_answer(monkeypatch) -> None:
    """`gapped_word_not_heard` compared the whole answer with one heard word."""
    monkeypatch.setattr(gates, "_synthesize", lambda text, settings=None: b"audio")
    monkeypatch.setattr(gates, "_transcribe",
                        lambda audio, settings=None: "She might've been asleep.")
    verdict = gates._audio_gate(
        item("She ___ been asleep.", "might have", "She might have been asleep."),
        settings=None)
    assert verdict.report.verdict == "passed", verdict.report


def test_the_audio_gate_still_refuses_a_word_it_did_not_hear(monkeypatch) -> None:
    monkeypatch.setattr(gates, "_synthesize", lambda text, settings=None: b"audio")
    monkeypatch.setattr(gates, "_transcribe",
                        lambda audio, settings=None: "She must've been asleep.")
    verdict = gates._audio_gate(
        item("She ___ been asleep.", "might have", "She might have been asleep."),
        settings=None)
    assert verdict.report.verdict == "discarded"
