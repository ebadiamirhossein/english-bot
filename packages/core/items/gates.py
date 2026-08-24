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
from dataclasses import dataclass, replace

from core import PROMPTS_DIR
from core.config import Settings
from core.items import (
    ANSWER_FAMILY,
    MAX_ACCEPTED_VARIANTS,
    PROBED_FAMILIES,
    TYPES_WITH_AUDIO,
    VALIDATOR_VERSION,
)
from core.items.checks import Failure, deterministic_failures, sentence_of
from core.items.grading import (
    distinct_answers,
    equivalence_key,
    fold,
    fold_answer,
    normalise_variants,
)
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

# **W5a: the probe returns a LIST, so the ceiling doubles.** 400 is still a
# design constraint rather than a guess -- the required output is
# `{"acceptable": [...], "confidence": ...}` and the prompt forbids reasoning, so
# a response that needs more than this is narrating, and truncating it is the
# correct outcome.
#
# `max_tokens` is an existing parameter of `chat()`. **CLAUDE.md §3 rule 2 does
# not fire**: passing a different value to an existing parameter is not a change
# to request construction. If a gate ever needs a parameter `chat()` does not
# have, the slice stops and says so rather than adding one quietly.
SOLVER_MAX_TOKENS = 400

# One verdict plus a one-word reason per sentence, up to a batch of 20.
JUDGE_MAX_TOKENS = 1000
JUDGE_BATCH = 20

# PRD §4.3: "if a repaired item still fails the blind-solver gate, it is
# discarded and regenerated." Two repairs, then stop. Migration 012 carries the
# same number as a CHECK on `items.repair_count` so the cap survives someone
# loosening this loop.
MAX_REPAIRS = 2

# W5a deleted `MAX_WIDENINGS`. W5 discovered acceptable translations one per
# call, so it needed a loop bound; the probe returns the whole set in one call,
# so the bound that matters is now on the SET size —
# `core.items.MAX_ACCEPTED_VARIANTS`. More renderings than that means the L1
# prompt is under-specified rather than the English merely varied.


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
    #: **Everything the probe said it would accept, from the LAST probe call.**
    #: On every probe path, including a pass — so a reader of `items.validation`
    #: can see the evidence the verdict was reached on, and so a caller never
    #: has to probe a second time to find out. Probing twice and reporting one
    #: call's classes beside another call's verdict is exactly the bug W5a's own
    #: `--live` harness shipped with.
    acceptable: tuple[str, ...] = ()

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
            "acceptable": list(self.acceptable),
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


def probe_acceptable(item: BaseItem, *, settings: Settings | None = None) -> dict:
    """One call. Sees `visible_projection(item)` and nothing else.

    **This replaces the single-answer solve rather than following it**, and the
    reason is the whole of W5a. A solve asks "what is your answer?" and a correct
    answer proves the item is RECOVERABLE. Unmarkability is caused by
    MULTI-ACCEPTABILITY, which is a different property: PRD's own broken item
    yields `I'll` on every run because `I'll` genuinely is the best completion,
    while `I can`, `I'm gonna` and `let me` fit the same slot and a learner
    typing any of them is marked wrong.

    Appending a second call was rejected on two counts. Cost: it doubles the
    per-item spend for information the first call could have returned. And
    correctness: two calls would leave two definitions of "the answer" in a
    codebase where `grade_text` is deliberately one function, because two notions
    of *same answer* is how a gate and a grader silently disagree.

    The system prompt is byte-identical across a batch, so `llm.chat`'s
    `cache_control: ephemeral` block gets a real cache hit and the marginal cost
    per item is the projection alone.
    """
    projection = visible_projection(item)
    response = _chat(
        [{"role": "user", "content": json.dumps(projection, ensure_ascii=False)}],
        system=_prompt("item_probe.txt"),
        json_mode=True,
        max_tokens=SOLVER_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise LLMError("probe did not return an object")
    return response


def _candidates(response: dict) -> list[str]:
    """The probe's list, as strings. A bare mapping is one candidate."""
    raw = response.get("acceptable")
    if isinstance(raw, dict):  # match_pairs returns a mapping
        return [json.dumps(raw, sort_keys=True, ensure_ascii=False)]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            out.append(json.dumps(entry, sort_keys=True, ensure_ascii=False))
        elif entry is not None:
            out.append(str(entry))
    return out


def _mapping_matches(item: BaseItem, response: dict) -> bool:
    """`match_pairs` keeps exact-mapping comparison.

    "Every acceptable answer" is degenerate for a bijection, and serialising a
    set of candidate mappings buys nothing: a second defensible pairing is an
    authoring defect, which the deterministic `columns_overlap` and duplicate
    checks already catch.
    """
    raw = response.get("acceptable")
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], dict):
        raw = raw[0]
    if not isinstance(raw, dict):
        return False
    expected = {fold(left): fold(right) for left, right in item.pairs}  # type: ignore[attr-defined]
    got = {fold(str(k)): fold(str(v)) for k, v in raw.items()}
    return expected == got


def _canonical_offered(item: BaseItem, classes: tuple[tuple[str, ...], ...]) -> bool:
    """Recoverability: is the canonical answer among what the probe accepted?

    The old failure mode, preserved. An item whose canonical is not offered is
    not answerable as authored, whatever else the probe returned.
    """
    return equivalence_key(item.answer) in classes


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
        audio = _audio_gate(item, settings=settings)
        # **`listening_gap` needs BOTH gates, and W5 gave it only one.** It sits
        # in TYPES_WITH_AUDIO, so it never reached the solver: the round-trip
        # proved the gapped word was AUDIBLE and nothing ever proved it was the
        # only word that FITS. `"I forgot my ___ this morning"` round-trips
        # perfectly and admits wallet, phone, bag and purse. It was carrying
        # `cloze_cued`'s defect plus one more, and this is the one type where
        # W5a adds a call rather than swapping one.
        if not audio.report.ok or item.item_type != "listening_gap":
            return audio
        probed = _probe_and_repair(audio.item or item, settings=settings)
        return Validated(
            probed.item,
            replace(probed.report, solver_answer=audio.report.solver_answer),
        )

    if item.item_type == "speak_answer":
        # No blind solver: an open production task has no single answer to
        # recover. The deterministic answerability checks in `checks.py` are the
        # gate, and `rubric` is what makes gate 3 verifiable at all.
        return Validated(item, ValidationReport("passed"))

    if ANSWER_FAMILY[item.item_type] not in PROBED_FAMILIES:
        return Validated(item, ValidationReport("passed"))
    return _probe_and_repair(item, settings=settings)


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


def _probe_and_repair(item: BaseItem, *, settings: Settings | None) -> Validated:
    """Probe; on multi-acceptability widen or cue, then probe again. Cap of two.

    The widen-or-reject decision is `core.items.ANSWER_FAMILY` — a constant, not
    a runtime judgement and not a model call. A slot admits one filler; a message
    admits many phrasings; authored options admit exactly the one authored.
    """
    family = ANSWER_FAMILY[item.item_type]
    current = item
    calls = 0
    cue_applied: str | None = None
    tried: set[str] = set()
    distractors: list[str] = []

    for attempt in range(MAX_REPAIRS + 1):
        try:
            response = probe_acceptable(current, settings=settings)
        except LLMError as exc:
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    blind_solver=(f"probe_error: {exc}",),
                    solver_calls=calls,
                ),
            )
        calls += 1

        if current.item_type == "match_pairs":
            if _mapping_matches(current, response):
                return Validated(
                    current,
                    ValidationReport(
                        "passed" if not attempt else "repaired",
                        repair_count=attempt,
                        cue_applied=cue_applied,
                        canonical=None,
                        solver_calls=calls,
                    ),
                )
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    blind_solver=("mapping_mismatch",),
                    solver_calls=calls,
                ),
            )

        candidates = _candidates(response)
        classes = distinct_answers(candidates)

        # Recoverability, unchanged from W5: an item whose canonical answer is
        # not among what a careful reader would accept is not answerable as
        # authored, whatever else came back.
        if not _canonical_offered(current, classes):
            if attempt < MAX_REPAIRS:
                distractors.extend(candidates)
                cue = _next_cue(current, distractors, tried)
                if cue is not None:
                    cue_applied, current = cue[0], cue[1]
                    tried.add(cue_applied)
                    continue
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    acceptable=tuple(candidates),
                    blind_solver=("not_recoverable", *candidates),
                    repair_count=attempt,
                    cue_applied=cue_applied,
                    solver_answer=candidates[0] if candidates else None,
                    canonical=current.answer,
                    solver_calls=calls,
                ),
            )

        if len(classes) == 1:
            return Validated(
                current,
                ValidationReport(
                    "repaired" if attempt else "passed",
                    acceptable=tuple(candidates),
                    repair_count=attempt,
                    cue_applied=cue_applied,
                    solver_answer=candidates[0] if candidates else None,
                    canonical=current.answer,
                    solver_calls=calls,
                ),
            )

        # More than one class: the item is multi-acceptable.
        if family == "message":
            # The sentence is the answer and a sentence legitimately has several
            # correct renderings, so these are one answer said differently.
            # Widening in ONE call is what replaced W5's iterative
            # widen-on-mismatch loop, which could only ever discover as many
            # alternatives as it had attempts left.
            widened = normalise_variants(
                current.answer, [*current.accepted_variants, *candidates]
            )
            if len(widened) > MAX_ACCEPTED_VARIANTS:
                return Validated(
                    None,
                    ValidationReport(
                        "discarded",
                        acceptable=tuple(candidates),
                        blind_solver=("under_specified", *candidates),
                        repair_count=attempt,
                        solver_calls=calls,
                        canonical=current.answer,
                    ),
                )
            return Validated(
                current.model_copy(update={"accepted_variants": widened}),
                ValidationReport(
                    "repaired" if attempt or len(widened) > 1 else "passed",
                    acceptable=tuple(candidates),
                    blind_solver=("widened", *candidates),
                    repair_count=attempt,
                    cue_applied=cue_applied,
                    solver_answer=candidates[0],
                    canonical=current.answer,
                    solver_calls=calls,
                ),
            )

        # slot and fixed_option: never widen.
        #
        # A slot admits one filler by definition -- if two forms fit, the gap
        # tests nothing in particular, which is PRD §4.3 gate 3 failing rather
        # than gate 1 passing. Accepting all four modals for the PRD item would
        # make it gradable and worthless.
        #
        # For fixed_option a second correct option is not a fact about English,
        # it is a defect in the authored option set.
        #
        # A cue may still rescue a slot item, and PRD asks for it: §4.3's repair
        # table offers `I'_ _ _` (4) for this very item, and a first-letter cue
        # narrows the candidates the probe will accept.
        if attempt < MAX_REPAIRS:
            distractors.extend(candidates)
            cue = _next_cue(current, distractors, tried)
            if cue is not None:
                cue_applied, current = cue[0], cue[1]
                tried.add(cue_applied)
                continue

        return Validated(
            None,
            ValidationReport(
                "discarded",
                acceptable=tuple(candidates),
                blind_solver=("multi_acceptable", *candidates),
                repair_count=attempt,
                cue_applied=cue_applied,
                solver_answer=candidates[0] if candidates else None,
                canonical=current.answer,
                solver_calls=calls,
            ),
        )

    raise AssertionError("unreachable: the loop returns on every path")


def _next_cue(
    item: BaseItem, distractors: list[str], tried: set[str]
) -> tuple[str, BaseItem] | None:
    """The next unused rung, applied. None when the ladder is exhausted.

    **Only the `slot` family is cue-repairable.** A cue narrows which filler is
    acceptable, which is exactly what a gapped item needs. It cannot help a
    `fixed_option` item: the options are already on screen, and if two of them
    are correct then the authored set is defective and no cue changes that. A
    `message` item widens instead of cueing. So a fixed-option item that comes
    back multi-acceptable is discarded on the FIRST probe rather than paying two
    more calls to be told the same thing.
    """
    if ANSWER_FAMILY[item.item_type] != "slot":
        return None
    remaining = [c for c in available_cues(item, distractors) if c not in tried]
    if not remaining:
        return None
    cue = remaining[0]
    return cue, apply_cue(item, cue, distractors)
