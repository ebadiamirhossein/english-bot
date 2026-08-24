"""The gates that need a model, and the orchestration that runs them last.

**This is the only module in `core.items` that imports `core.llm` or
`core.speech`.** Everything else is pure, which is what lets the deterministic
half of the validator be tested with no network and no recorded fixtures.

`_chat`, `_synthesize` and `_transcribe` are module-level seams. Tests
monkeypatch them; nothing else should. They exist because patching
`core.llm.chat` directly would also patch it for every other caller in the same
process, and because a stable patch target is what keeps the recorded-response
tests from breaking on an unrelated refactor.

**No call in this module is made by the test suite.** `tests/conftest.py`
installs `netguard` autouse and session-scoped, so a test that reached the
provider would raise rather than spend money — that is structural, not a
promise. The one human-run verification lives in `verify.py`.

**CLAUDE.md §3 rule 2 does not fire for this slice.** Rule 2 is scoped to *"any
change to `llm.py` or `speech.py` request construction"*, and there is none:
`system` + `json_mode` + `max_tokens` + `reject_truncation` all already exist and
are exercised by five shipped features, and the audio round-trip is a new
*composition* of two unmodified calls rather than a new request shape. If
implementation ever needs a new parameter on `chat()`, rule 2 fires and the
slice stops and says so rather than adding it quietly.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from core import PROMPTS_DIR
from core.config import Settings
from core.items import TYPES_WITH_AUDIO, VALIDATOR_VERSION
from core.items.checks import Failure, deterministic_failures, sentence_of
from core.items.grading import fold, fold_answer, matches, normalise_variants
from core.items.naturalness import (
    contract,
    jargon_hits,
    textbook_hits,
    uncontracted,
)
from core.items.projection import visible_projection
from core.items.repair import apply_cue, available_cues
from core.items.schema import BaseItem, DictationItem, ListeningGapItem
from core.llm import LLMError, chat
from core.speech import SpeechError, synthesize, transcribe

# The solver's required output is `{"answer": ..., "confidence": ...}` and the
# prompt forbids reasoning. This ceiling is a design constraint, not a guess: a
# solver that narrates has reasoned about what the item "probably wants", which
# is not what a learner does, and truncating it is the correct outcome.
SOLVER_MAX_TOKENS = 200

# One verdict plus a one-word reason per sentence, up to a batch of 20.
JUDGE_MAX_TOKENS = 1000
JUDGE_BATCH = 20

# PRD §4.3: "if a repaired item still fails the blind-solver gate, it is
# discarded and regenerated." Two repairs, then stop. Migration 012 carries the
# same number as a CHECK on `items.repair_count` so the cap survives someone
# loosening this loop.
MAX_REPAIRS = 2

# `l1_to_l2_production` widens instead of cueing (see `_solve_and_repair`), and
# a third distinct correct translation means the prompt is genuinely
# under-specified rather than merely varied.
MAX_WIDENINGS = 2


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ── seams ───────────────────────────────────────────────────────────────────


def _chat(*args, **kwargs):
    return chat(*args, **kwargs)


def _synthesize(*args, **kwargs):
    return synthesize(*args, **kwargs)


def _transcribe(*args, **kwargs):
    return transcribe(*args, **kwargs)


# ── the report ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The verdict and how it was reached. Stored as `items.validation`.

    Acceptance asserts on this object, never on a log line: a log line is not a
    return value and a test that greps one is testing the logger.
    """

    verdict: str  # "passed" | "repaired" | "discarded"
    deterministic: tuple[str, ...] = ()
    naturalness: tuple[str, ...] = ()
    blind_solver: tuple[str, ...] = ()
    #: How far up the cue ladder this item had to go. 0 means no repair.
    repair_count: int = 0
    cue_applied: str | None = None
    #: What the solver answered on its last attempt, and what was canonical.
    solver_answer: str | None = None
    canonical: str | None = None
    solver_calls: int = 0
    validator_version: int = VALIDATOR_VERSION

    @property
    def ok(self) -> bool:
        return self.verdict in ("passed", "repaired")

    def as_json(self) -> dict:
        """The three keys migration 012's CHECK requires, plus provenance."""
        return {
            "verdict": self.verdict,
            "deterministic": list(self.deterministic),
            "naturalness": list(self.naturalness),
            "blind_solver": list(self.blind_solver),
            "repair_count": self.repair_count,
            "cue_applied": self.cue_applied,
            "solver_answer": self.solver_answer,
            "canonical": self.canonical,
            "solver_calls": self.solver_calls,
            "validator_version": self.validator_version,
        }


@dataclass(frozen=True, slots=True)
class Validated:
    """A repaired-or-not item and the record of how it got there."""

    item: BaseItem | None
    report: ValidationReport


# ── gate 1: the blind solver ────────────────────────────────────────────────


def blind_solve(item: BaseItem, *, settings: Settings | None = None) -> dict:
    """One call. Sees `visible_projection(item)` and nothing else.

    The system prompt is byte-identical across a batch, so `llm.chat`'s
    `cache_control: ephemeral` block gets a real cache hit and the marginal cost
    per item is the projection alone.
    """
    projection = visible_projection(item)
    response = _chat(
        [{"role": "user", "content": json.dumps(projection, ensure_ascii=False)}],
        system=_prompt("item_blind_solver.txt"),
        json_mode=True,
        max_tokens=SOLVER_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise LLMError("blind solver did not return an object")
    return response


def _solver_agrees(item: BaseItem, answer: object) -> bool:
    """Pass = the solver's answer is the canonical one or an accepted variant.

    Uses `grading.matches`, which is the SAME comparison the grader uses. If the
    gate and the grader ever used different comparisons, an item would pass the
    gate and then be ungradable — the learner types the identical string and is
    marked wrong. One function, both callers.
    """
    if isinstance(answer, dict):
        # `match_pairs`: the whole mapping must match. A partial match is a
        # fail, because one ambiguous pair is the coin-flip bug at smaller scale.
        expected = {fold(left): fold(right) for left, right in item.pairs}  # type: ignore[attr-defined]
        got = {fold(str(k)): fold(str(v)) for k, v in answer.items()}
        return expected == got
    return matches(str(answer), item.accepted_variants)


# ── gate 2: naturalness (PRD §4.6) ──────────────────────────────────────────


def mechanical_naturalness(item: BaseItem) -> tuple[BaseItem, tuple[Failure, ...]]:
    """Rules 2, 3 and 4. Zero model calls. Rule 4 repairs rather than rejects.

    Returns the item possibly rewritten (contractions) and the failures that
    survived. Ordering matters: this runs before any model call, so a Life-track
    item containing "deploy" is rejected for free.
    """
    sentence = sentence_of(item)
    out: list[Failure] = []

    hits = jargon_hits(sentence, track=item.track)
    if hits:
        out.append(
            Failure("work_jargon", f"{list(hits)} on the {item.track} track")
        )

    textbook = textbook_hits(sentence)
    if textbook:
        out.append(Failure("textbook_english", f"{list(textbook)}"))

    # Rule 4 is the one mechanical failure with a mechanical fix, so it repairs
    # in place rather than costing a regeneration.
    repaired = item
    if item.register_tag != "formal" and uncontracted(sentence):
        fixed = contract(sentence)
        if fixed != sentence:
            field_name = _sentence_field(item)
            if field_name is not None:
                update = {field_name: fixed}
                if field_name == "answer":
                    update["accepted_variants"] = normalise_variants(
                        fixed, item.accepted_variants
                    )
                repaired = item.model_copy(update=update)
    return repaired, tuple(out)


def _sentence_field(item: BaseItem) -> str | None:
    """Which field `sentence_of` read, so a rewrite lands back in the right one."""
    if isinstance(item, DictationItem):
        return "answer"
    if isinstance(item, ListeningGapItem):
        return "transcript"
    if item.item_type in ("word_bank_order", "l1_to_l2_production"):
        # Rewriting these would desynchronise the bank or the translation pair,
        # so rule 4 declines rather than half-fixing them.
        return None
    if item.item_type in ("error_spot", "match_pairs"):
        return None
    return "prompt_text"


def judge_naturalness(
    sentences: Sequence[str], *, settings: Settings | None = None
) -> tuple[bool, ...]:
    """Rule 1, batched up to `JUDGE_BATCH` per call.

    Batching is safe here precisely because it is unsafe for the blind solver:
    the judge is not being asked to recover an answer, so a neighbouring
    sentence cannot leak one.
    """
    if not sentences:
        return ()
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    response = _chat(
        [{"role": "user", "content": numbered}],
        system=_prompt("item_naturalness.txt"),
        json_mode=True,
        max_tokens=JUDGE_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    verdicts = {}
    if isinstance(response, dict):
        for row in response.get("verdicts", []) or []:
            if isinstance(row, dict) and "n" in row:
                verdicts[int(row["n"])] = bool(row.get("natural"))
    # A sentence the judge failed to rule on is treated as natural. The judge is
    # a backstop behind three mechanical rules, and failing an item because a
    # model omitted a row would reject good content for a transport reason.
    return tuple(verdicts.get(i + 1, True) for i in range(len(sentences)))


# ── gate 3: the audio round-trip ────────────────────────────────────────────


def audio_round_trip(text: str, *, settings: Settings | None = None) -> tuple[bool, str]:
    """`synthesize` → `transcribe` → folded equality. 1 TTS + 1 STT, no LLM.

    The same instrument class as the blind solver: a second, independent process
    sees only what the learner will perceive, and has to recover the content.

    **A pass is necessary but not sufficient; a fail is decisive.** STT hears
    better than a B1 learner, so a clean round-trip does not prove the item is
    audible to a person — but a round-trip the recogniser itself cannot manage
    is one no learner will.
    """
    audio = _synthesize(text, settings=settings)
    heard = _transcribe(audio, settings=settings)
    return fold_answer(heard) == fold_answer(text), heard


# ── orchestration ───────────────────────────────────────────────────────────


def validate(
    item: BaseItem,
    *,
    known_lemmas: frozenset[str] | None = None,
    settings: Settings | None = None,
    judge: bool = True,
) -> Validated:
    """Run every gate, cheapest first, and return the verdict.

    Order is the design: mechanical checks → mechanical naturalness → batched
    judge → blind solver. Each stage can only cost money once every free stage
    has already said yes.
    """
    det = deterministic_failures(item, known_lemmas=known_lemmas)
    if det:
        return Validated(
            None,
            ValidationReport("discarded", deterministic=tuple(f.code for f in det)),
        )

    item, nat = mechanical_naturalness(item)
    if nat:
        return Validated(
            None,
            ValidationReport("discarded", naturalness=tuple(f.code for f in nat)),
        )

    # A contraction repair can invalidate a deterministic invariant it does not
    # own -- a shortened sentence changes word counts and, for a cloze, whether
    # the answer is still visible in the stem. Re-running is cheap and the
    # alternative is a repaired item that no longer passes its own checks.
    det = deterministic_failures(item, known_lemmas=known_lemmas)
    if det:
        return Validated(
            None,
            ValidationReport("discarded", deterministic=tuple(f.code for f in det)),
        )

    if judge:
        sentence = sentence_of(item)
        if sentence.strip() and not judge_naturalness([sentence], settings=settings)[0]:
            return Validated(
                None, ValidationReport("discarded", naturalness=("unnatural",))
            )

    if item.item_type in TYPES_WITH_AUDIO:
        return _audio_gate(item, settings=settings)

    if item.item_type == "speak_answer":
        # No blind solver: an open production task has no single answer to
        # recover. The deterministic answerability checks in `checks.py` are the
        # gate, and `rubric` is what makes gate 3 verifiable at all.
        return Validated(item, ValidationReport("passed"))

    return _solve_and_repair(item, settings=settings)


def _audio_gate(item: BaseItem, *, settings: Settings | None) -> Validated:
    text = sentence_of(item)
    try:
        ok, heard = audio_round_trip(text, settings=settings)
    except SpeechError as exc:
        return Validated(
            None, ValidationReport("discarded", blind_solver=(f"speech_error: {exc}",))
        )
    if not ok:
        return Validated(
            None,
            ValidationReport(
                "discarded",
                blind_solver=("audio_round_trip_failed",),
                solver_answer=heard,
                canonical=text,
            ),
        )
    if isinstance(item, ListeningGapItem):
        # The gapped word specifically must survive the round-trip. If the
        # recogniser did not hear it, a learner will not either.
        if fold_answer(item.answer) not in {
            fold_answer(w) for w in heard.split()
        }:
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    blind_solver=("gapped_word_not_heard",),
                    solver_answer=heard,
                    canonical=item.answer,
                ),
            )
    return Validated(item, ValidationReport("passed", solver_answer=heard))


def _solve_and_repair(item: BaseItem, *, settings: Settings | None) -> Validated:
    """Solve; on disagreement widen or cue, then solve again. Hard cap of two."""
    widening = item.item_type == "l1_to_l2_production"
    limit = MAX_WIDENINGS if widening else MAX_REPAIRS

    current = item
    calls = 0
    attempts: list[str] = []
    distractors: list[str] = []
    cue_applied: str | None = None
    # Every rung already used. Excluding only the LAST one would let a
    # three-rung ladder revisit rung one, which spends a capped attempt on a cue
    # the solver has already failed against.
    tried: set[str] = set()

    for attempt in range(limit + 1):
        try:
            result = blind_solve(current, settings=settings)
        except LLMError as exc:
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    blind_solver=(f"solver_error: {exc}",),
                    solver_calls=calls,
                ),
            )
        calls += 1
        answer = result.get("answer", "")
        attempts.append(str(answer))

        if _solver_agrees(current, answer):
            verdict = "repaired" if attempt else "passed"
            return Validated(
                current,
                ValidationReport(
                    verdict,
                    repair_count=attempt,
                    cue_applied=cue_applied,
                    solver_answer=str(answer),
                    canonical=current.answer,
                    solver_calls=calls,
                ),
            )

        if attempt == limit:
            break

        if widening:
            # For production, a second correct translation is a fact about
            # English, not a defect — so the solver's answer is ADDED rather
            # than used to reject. A third distinct output means the prompt is
            # genuinely under-specified and the item is discarded.
            current = current.model_copy(
                update={
                    "accepted_variants": normalise_variants(
                        current.answer, [*current.accepted_variants, str(answer)]
                    )
                }
            )
            continue

        distractors.append(str(answer))
        cues = available_cues(current, distractors)
        remaining = [c for c in cues if c not in tried]
        if not remaining:
            break
        cue_applied = remaining[0]
        tried.add(cue_applied)
        current = apply_cue(current, cue_applied, distractors)

    return Validated(
        None,
        ValidationReport(
            "discarded",
            blind_solver=("ambiguous", *attempts),
            repair_count=min(limit, calls - 1),
            cue_applied=cue_applied,
            solver_answer=attempts[-1] if attempts else None,
            canonical=item.answer,
            solver_calls=calls,
        ),
    )
