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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core import PROMPTS_DIR
from core.config import Settings
from core.items import (
    ANSWER_FAMILY,
    MAX_ACCEPTED_VARIANTS,
    PROBED_FAMILIES,
    TYPES_WITH_AUDIO,
    VALIDATOR_VERSION,
)
from core.items.checks import (
    Failure,
    answer_spoken_in,
    deterministic_failures,
    judged_sentence,
    probe_canonical,
    says_the_same,
    sentence_of,
    spoken_variant,
)
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
#: **THE FLOOR UNDER EVERY GATE BUDGET, AND IT EXISTS BECAUSE THINKING IS ON.**
#:
#: `claude-sonnet-5` runs **adaptive thinking by default** — `core/llm.py` sets no
#: `thinking` parameter anywhere, and on this model omitting it means thinking is
#: ON rather than off. **Thinking tokens count against `max_tokens`.**
#:
#: fill-4 is what that costs when the ceiling is too low: the probe returned
#: `stop_reason=max_tokens output_tokens=400 chars=0 blocks=['ThinkingBlock']`,
#: **twice**, so `probe_error` fired on an item no gate had found fault with. The
#: budget was spent before a text block could be emitted.
#:
#: **`max_tokens` IS A CEILING, NOT A SPEND.** Adaptive thinking uses what it
#: needs whatever the ceiling is, so raising it stops the truncation without
#: materially changing the bill — which is why the repair is the ceiling and not
#: the thinking configuration.
#:
#: **The thinking configuration is the BETTER repair and it is NOT made here.**
#: `chat()` has no `thinking` or `output_config` parameter, and the note below
#: says what to do about that: *if a gate ever needs a parameter `chat()` does not
#: have, the slice stops and says so rather than adding one quietly.* Filed #266.
THINKING_HEADROOM_TOKENS = 2000

SOLVER_MAX_TOKENS = 4000

# One verdict plus a one-word reason per sentence, up to a batch of 20.
JUDGE_MAX_TOKENS = 8000
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

    #: **The diagnostics the gates ask for and used to throw away (#119).**
    #: `item_naturalness.txt` asks for a one-word reason and `item_probe.txt`
    #: asks for a confidence; both were parsed and dropped one line later, so a
    #: `high` issue was opened that a stored word would have answered and a
    #: whole slice (W5b) was spent recovering it. The cost of dropping them was
    #: measured, so they are stored: the next unexplained verdict diagnoses
    #: itself out of `items.validation`.
    naturalness_reason: str | None = None
    probe_confidence: str | None = None

    #: **`probe_target`'s verdict, stored rather than printed (#194).** W10c's
    #: `TargetVerdict` carried the ranking, the claimed rank, the runner-up and a
    #: confidence; `--live` printed all four and then dropped them, so the
    #: evidence for *this item tests its target* survived only in a run's stdout.
    #:
    #: **The runner-up is the sharp loss.** On an item that PASSED, second place
    #: is the distinction it came closest to blurring -- the single most useful
    #: line for whoever rewrites the generator prompt.
    #:
    #: **This is #119's exact shape, one slice later and in a gate that was
    #: written knowing about #119**, which is why it was filed at `medium` rather
    #: than shrugged off. No migration: `items.validation` is JSONB and 012's
    #: CHECK requires three keys rather than forbidding a fourth.
    target_ranking: tuple[str, ...] = ()
    target_claimed_rank: int | None = None
    target_first: str | None = None
    target_runner_up: str | None = None
    target_confidence: str | None = None

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
            "naturalness_reason": self.naturalness_reason,
            "probe_confidence": self.probe_confidence,
            "target_ranking": list(self.target_ranking),
            "target_claimed_rank": self.target_claimed_rank,
            "target_first": self.target_first,
            "target_runner_up": self.target_runner_up,
            "target_confidence": self.target_confidence,
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


def _confidence(response: dict) -> str | None:
    """The probe's own `confidence`, which `item_probe.txt` asks for (#119).

    *"Low confidence is a signal about the exercise, not about you"* — so it is
    evidence about the item and belongs in the stored validation record beside
    `acceptable`, under the same "from the LAST probe call" convention. It does
    not decide anything today: a verdict driven by a self-reported confidence
    would be a threshold, and this validator has none.
    """
    raw = response.get("confidence")
    return str(raw) if isinstance(raw, str) and raw.strip() else None


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

    **`checks.probe_canonical`, not `item.answer` (#210).** For `error_spot`
    they differ: `answer` is the wrong tile, and asking a probe to name it is a
    question with two defensible answers for any two-token error. The
    CORRECTION has one.
    """
    return equivalence_key(probe_canonical(item)) in classes


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


@dataclass(frozen=True, slots=True)
class NaturalnessVerdict:
    """One row of the judge's answer: the boolean AND the word it gave for it.

    **Read `.natural`, never the object.** A dataclass instance is always
    truthy, so `if not judge_naturalness(...)[0]` would silently never fire —
    a fail-open with no symptom, on the one gate whose whole failure mode this
    slice exists to fix. `test_items_judged_sentence.py` drives
    `validate(..., judge=True)` in both directions so the trap cannot be
    re-entered quietly; before W5c that path had no test at all, because every
    `validate` call in the suite passed `judge=False` (CLAUDE.md §3 rule 4).
    """

    natural: bool
    #: One of `item_naturalness.txt`'s words — ok, slack, textbook, stilted,
    #: jargon, written — or `MISSING_ROW` when the fail-open default fired.
    reason: str


#: What `reason` says when the model omitted the row entirely. The same string
#: `judge_observe._reason_of` has used since W5b, so the gate and the harness
#: that observes it name the fail-open case identically.
MISSING_ROW = "missing-row"


def judge_naturalness(
    sentences: Sequence[str], *, settings: Settings | None = None
) -> tuple[NaturalnessVerdict, ...]:
    """Rule 1, batched up to `JUDGE_BATCH` per call.

    Batching is safe here precisely because it is unsafe for the blind solver:
    the judge is not being asked to recover an answer, so a neighbouring
    sentence cannot leak one.

    **Callers must pass prose.** `checks.judged_sentence` is what produces it;
    `checks.sentence_of` is not, and handing this function a gapped stem is
    #115 (W5b: 0/5 natural as shipped, 5/5 filled).
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
    verdicts: dict[int, NaturalnessVerdict] = {}
    if isinstance(response, dict):
        for row in response.get("verdicts", []) or []:
            if isinstance(row, dict) and "n" in row:
                # The reason is asked for by the prompt and, until W5c, was
                # parsed and dropped on the next line (#119). It is the whole
                # diagnosis of a rejection and it costs nothing to keep.
                reason = row.get("reason")
                verdicts[int(row["n"])] = NaturalnessVerdict(
                    bool(row.get("natural")),
                    str(reason) if reason is not None else "",
                )
    # A sentence the judge failed to rule on is treated as natural. The judge is
    # a backstop behind three mechanical rules, and failing an item because a
    # model omitted a row would reject good content for a transport reason.
    return tuple(
        verdicts.get(i + 1, NaturalnessVerdict(True, MISSING_ROW))
        for i in range(len(sentences))
    )


# ── gate 3: does this item test the target it claims? (W10c) ────────────────


#: How many targets from OTHER units join the unit's own in the candidate list.
#: Three is enough to make a confident wrong answer visible without diluting the
#: siblings, which are the decoys that actually discriminate.
TARGET_DECOYS = 3

#: One ranking of a short candidate list, plus a confidence. No reasoning.
TARGET_MAX_TOKENS = 4000


@dataclass(frozen=True, slots=True)
class TargetVerdict:
    """What the classifier ranked, and where the item's own claim landed.

    **`ok` is `claimed_rank == 1` and nothing softer.** An item whose target
    comes second is an item that teaches something adjacent to what it says it
    teaches, and a learner answering it is scored on the wrong point.
    """

    #: As returned, best first, filtered to the candidates that were offered.
    ranking: tuple[str, ...]
    #: 1-based position of the claimed target, or None if it was not ranked.
    claimed_rank: int | None
    #: What ranked first, whatever that was.
    first: str | None
    #: What ranked SECOND. **Recorded, never failed** (#119): when the claimed
    #: target wins, the runner-up is the distinction the item came closest to
    #: blurring, and it is the single most useful line for whoever rewrites the
    #: generator prompt. Dropping a diagnostic the gate already has is what cost
    #: this project the whole of W5b.
    runner_up: str | None
    confidence: str | None

    @property
    def ok(self) -> bool:
        return self.claimed_rank == 1


def probe_ranked(
    subject: Mapping[str, Any],
    *,
    claimed: str,
    candidates: Sequence[str],
    system: str,
    max_tokens: int = TARGET_MAX_TOKENS,
    settings: Settings | None = None,
) -> TargetVerdict:
    """Rank a candidate list against a subject. **The engine, one implementation.**

    **W10b split this out of `probe_target` and changed nothing about it.** The
    record already ruled that W10b's C1 becomes `probe_target`'s SECOND CALLER
    and not a second implementation -- and then W10b found it could not simply
    call it: `probe_target` builds its payload from `visible_projection(item)`
    and `item.answer`, and **a lesson section is not an item and has no answer.**
    Pushing one through `visible_projection` would claim a section is a
    learner-visible ITEM, breaking that module's stated cross-slice contract and
    the name-list test that holds it.

    So the shape that honours the ruling is one engine and two entry points. What
    lives here is everything that is not item-specific and everything the
    discipline depends on: candidate normalisation, the sorted-not-shuffled rule,
    the refusal of a claim that is not on the list, dropping inventions, and the
    ranking parse. The callers supply only *what is being classified* and *which
    prompt asks the question*.

    **`max_tokens` is a parameter for the reason W10c recorded and W10b then
    proved again the hard way: THINKING TOKENS ARE BILLED AND COUNT AGAINST THE
    BUDGET.** An item probe ranks a short list about one exercise and 400 is
    ample; a lesson gate reasons over a whole section or a whole lesson, and on
    2026-08-28 one returned `output_tokens=1500 chars=0 blocks=['ThinkingBlock']`
    -- the entire budget spent thinking, with no text at all. The default keeps
    `probe_target` byte-identical; the lesson callers state their own.

    **Raising a cap costs nothing unless it is used.** Output tokens are billed
    as produced, so a larger ceiling buys headroom against truncation and not
    spend.

    **`system` is a parameter because the question is not the same question.**
    `item_target.txt` opens *"You are reading one language exercise"* and reasons
    throughout in terms of an exercise posed to a learner. A section is prose.
    Asking that prompt about prose would be asking a question about a thing it
    does not describe -- which is W5c's rule (the judge must receive the thing
    itself) failing at the prompt rather than at the payload.

    **The candidates are sorted, not shuffled.** Sorting destroys any information
    in the authored order just as thoroughly and keeps the call reproducible;
    a random shuffle would make the gate answer differently on each run, which is
    the property `visible_projection` sorts `match_pairs`' columns to avoid.
    """
    ordered = sorted({str(c).strip() for c in candidates if str(c).strip()})
    if claimed.strip() not in ordered:
        # Not a model failure and not recoverable by asking: a claim that is not
        # on the list can never rank first, so the call would be spent proving
        # something the caller already knows. `validate_checkpoint` refuses a
        # per_target key that is not one of the unit's targets for the same
        # reason, and this is that rule at generation time.
        #
        # **W10b's negative control was caught by exactly this.** The archived
        # plan's control claimed a target belonging to no unit in its own scope,
        # so it could never have executed -- the gate that was supposed to prove
        # the checks discriminate would have raised before spending a call.
        raise ValueError(
            f"claimed target {claimed!r} is not among the candidates offered; "
            "the caller built the list and the item from different units"
        )

    payload = {**dict(subject), "candidates": ordered}
    response = _chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=_prompt(system),
        json_mode=True,
        max_tokens=max_tokens,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise LLMError("target probe did not return an object")

    # Only candidates that were actually offered count. A model that invents a
    # grammar point has not ranked the list it was given, and silently keeping
    # the invention would let it occupy first place and fail every item.
    offered = {c.casefold(): c for c in ordered}
    ranking: list[str] = []
    for entry in response.get("ranking") or []:
        match = offered.get(str(entry).strip().casefold())
        if match is not None and match not in ranking:
            ranking.append(match)

    target = claimed.strip()
    rank = ranking.index(target) + 1 if target in ranking else None
    return TargetVerdict(
        ranking=tuple(ranking),
        claimed_rank=rank,
        first=ranking[0] if ranking else None,
        runner_up=ranking[1] if len(ranking) > 1 else None,
        confidence=_confidence(response),
    )


def probe_target(
    item: BaseItem,
    *,
    claimed: str,
    candidates: Sequence[str],
    settings: Settings | None = None,
) -> TargetVerdict:
    """One call. Which grammar point does this item test? **Ranked, not confirmed.**

    **The gap this closes, stated plainly because nothing else in this module
    closes it:** every other gate here asks whether an item is *well-formed*,
    *unambiguous* or *natural*. Not one of them asks whether it tests the thing
    it claims to test. `checks._shared`'s `no_target` is satisfied by a
    `unit_number` alone, so "this item belongs to unit 1" passes a check whose
    name suggests more; and `items.error_type` names one of nineteen coarse
    journal codes, so all four of unit 1's grammar targets collapse onto
    `verb_tense_past` and cannot be told apart by it at all.

    **Blind and PRODUCTIVE, never confirmatory** -- W5a's finding applied to a
    second question. The model is never asked *"does this test the present
    perfect?"*, because a leading question gets a yes and the gate becomes a
    rubber stamp exactly the way the single-answer solve did. It is handed the
    item and a list, and it produces a ranking.

    **What it is shown**: `visible_projection(item)` -- the learner-visible face,
    through the single serialiser, so this gate sees what the learner sees --
    plus the canonical answer, which a learner also sees, after grading. It is
    NOT shown `grammar_target`: that field is in `projection.NEVER_VISIBLE`
    precisely so this call cannot read the answer to its own question.

    **This is now the item ENTRY POINT and `probe_ranked` is the engine** (W10b).
    Everything above is unchanged and the payload it builds is byte-identical to
    the one this function built before the split -- `{item, answer, candidates}`,
    in that order. What moved out is only the part that was never about items.
    """
    return probe_ranked(
        {"item": visible_projection(item), "answer": item.answer},
        claimed=claimed,
        candidates=candidates,
        system="item_target.txt",
        settings=settings,
    )


def back_translate(
    item: BaseItem, *, settings: Settings | None = None
) -> str | None:
    """`l1_to_l2_production`'s English answer, rendered back into its own L1.

    **This produces evidence for a person; it does not decide anything, and the
    reason is a defect found while implementing the check that was planned.**

    #102 is that no gate is shown both sides of an L1→L2 relation, so a wrong
    translation with a plausible canonical passes everything. The planned fix was
    to back-translate and compare with `grading.equivalence_key`. **That
    comparison is structurally inert on the only language it would ever run
    against**: `equivalence_key` is `core.lexicon.normalize.tokenize`, whose word
    pattern is `[A-Za-z]`-based, so every Farsi string folds to the empty tuple
    and any two of them compare equal. The check would have passed a completely
    wrong back-translation, silently, forever -- the `match_pairs` shape (a
    guarantee never evaluated against the thing it names) reproduced inside the
    slice that filed it.

    The alternatives were both worse. Writing a Farsi normaliser here would be a
    second tokenisation layer for a language nothing in this pipeline can check,
    and #177 is what that looks like when it is wrong in effect while true
    literally. Asking a model *"do these mean the same?"* is the leading question
    `probe_target` exists not to ask.

    So the string is produced and PRINTED BESIDE THE ITEM'S OWN L1 PROMPT, and
    the comparison belongs to the operator -- who is the only Persian reader in
    this project and the only instrument that can make it. **#102 does not close
    and its severity is unchanged.**
    """
    if item.answer is None:
        return None
    payload = {"english": item.answer, "into": getattr(item, "l1", "fa")}
    response = _chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=_prompt("item_backtranslate.txt"),
        json_mode=True,
        max_tokens=TARGET_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise LLMError("back-translation did not return an object")
    rendered = response.get("l1")
    return str(rendered).strip() if isinstance(rendered, str) else None


# ── gate 4: the audio round-trip ────────────────────────────────────────────


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
    # Contractions read (B1): a recogniser writing *might have* for audio of
    # *might've* heard the sentence. A different word, or punctuation inside
    # the sentence, still fails — `says_the_same` is not fuzzy.
    return says_the_same(fold_answer(heard), fold_answer(text)), heard


# ── orchestration ───────────────────────────────────────────────────────────


def free_stages(
    item: BaseItem, *, known_lemmas: frozenset[str] | None = None
) -> tuple[BaseItem, Validated | None]:
    """Every gate that costs nothing, in order. **`validate`'s own head.**

    Returns ``(item, None)`` when the item survives -- the item POSSIBLY
    REWRITTEN, because rule 4 contracts in place -- and ``(item, Validated)``
    carrying the discard when it does not.

    **Extracted rather than copied, and the distinction is the whole point.**
    W10c validates a cohort of eight items and wants ONE batched naturalness
    call for the eight rather than eight calls of one (#120: `JUDGE_BATCH = 20`
    has been declared and uncalled since W5). To batch, a caller has to run the
    free stages itself first -- otherwise it pays the judge for items the free
    gates would have rejected for nothing, and `validate`'s cheapest-first
    ordering is lost at the cohort level.

    The obvious way to do that is to copy these three stages into the runner,
    and that is how two definitions of "is this item well-formed" start. So
    `validate` calls this and behaves byte-identically for every existing
    caller, and the batch path calls the same function.
    """
    det = deterministic_failures(item, known_lemmas=known_lemmas)
    if det:
        return item, Validated(
            None,
            ValidationReport("discarded", deterministic=tuple(f.code for f in det)),
        )

    item, nat = mechanical_naturalness(item)
    if nat:
        return item, Validated(
            None,
            ValidationReport("discarded", naturalness=tuple(f.code for f in nat)),
        )

    # A contraction repair can invalidate a deterministic invariant it does not
    # own -- a shortened sentence changes word counts and, for a cloze, whether
    # the answer is still visible in the stem. Re-running is cheap and the
    # alternative is a repaired item that no longer passes its own checks.
    det = deterministic_failures(item, known_lemmas=known_lemmas)
    if det:
        return item, Validated(
            None,
            ValidationReport("discarded", deterministic=tuple(f.code for f in det)),
        )

    return _with_spoken_variant(item), None


def _with_spoken_variant(item: BaseItem) -> BaseItem:
    """A listening answer the transcript SAYS differently is accepted as said.

    The checks admit *might have* against audio saying *might've* (B1). The
    learner types what they heard, so the heard spelling is stored beside the
    canonical — the convention `grading.matches` already rests on (*either is
    accepted because both are stored*). Widens grading only; never rewrites
    the answer, the stem or the audio.
    """
    if not isinstance(item, ListeningGapItem):
        return item
    heard = spoken_variant(item.answer, item.transcript)
    if heard is None:
        return item
    return item.model_copy(
        update={"accepted_variants": normalise_variants(
            item.answer, (*item.accepted_variants, heard))}
    )


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

    **`judge=False` is not a way to skip the naturalness gate**, and W10c is the
    first caller to pass it for its intended reason: the caller has already run
    `judge_naturalness` over a BATCH that included this item. `verify.py` passes
    it because its subject is the probe; `seed_fixtures.py` and every learner
    path leave it True.
    """
    item, failed = free_stages(item, known_lemmas=known_lemmas)
    if failed is not None:
        return failed

    if judge:
        # **`judged_sentence`, not `sentence_of` (W5c, #115).** The judge is
        # asked whether a real person would say this to a friend, by a prompt
        # that never mentions gaps, exercises or learners. Handed the gapped
        # stem it said no to `mcq`, `cloze_cued` and `collocation_pick`, and
        # handed the tiles with their deliberate error still in them it said no
        # to `error_spot` -- 0/5 natural as shipped, 5/5 filled, forty
        # observations with no exception. The judge was right and the input was
        # wrong. The mechanical rules above keep the stem, deliberately: rule 4
        # writes its repair BACK through `_sentence_field`, so reading a filled
        # sentence there would put prose into `prompt_text` and destroy the gap.
        sentence = judged_sentence(item)
        if sentence.strip():
            # `.natural`, never the object: a dataclass is always truthy and
            # `not verdict` would disable the gate silently.
            verdict = judge_naturalness([sentence], settings=settings)[0]
            if not verdict.natural:
                return Validated(
                    None,
                    ValidationReport(
                        "discarded",
                        naturalness=("unnatural",),
                        naturalness_reason=verdict.reason,
                    ),
                )

    if item.item_type in TYPES_WITH_AUDIO:
        # **The round-trip is the whole gate for these types (W5c, ruling R1).**
        #
        # W5a added a text-only uniqueness probe to `listening_gap` on the
        # correct observation that nothing had ever tested whether the gapped
        # word was the only one that fits. W5b measured what that probe could
        # actually do and the answer was nothing: `classes=0` on all six
        # attempts, bare and cued, three runs. It did not recover the wrong
        # word, it recovered no word.
        #
        # The reason is structural, not a tuning problem. PRD §4.3 defines the
        # gate as a call that sees *"only what the learner will see"* -- and
        # the learner HEARS this sentence. The probe is handed
        # `{"item_type": "listening_gap", "prompt_text": "She ___ like coffee
        # these days"}` and nothing else, so it is not blind, it is DEPRIVED:
        # it sees strictly less than the learner and is solving a harder
        # problem than the item poses. In text that slot admits `doesn't`,
        # `does not` and `might not`; with the audio it admits one.
        #
        # Making it genuinely blind has no shippable form today. Giving it the
        # transcript is giving it the answer, so the gate becomes
        # unfalsifiable. Giving it an STT reading of the synthesized audio is
        # exactly what `audio_round_trip` already computes. Giving it the audio
        # needs an audio-input model call `speech.py` does not expose -- that is
        # W14's problem, and #121 records it there. Until then this type's
        # uniqueness evidence IS the round-trip: a word the recogniser itself
        # cannot recover from the audio is not one a learner will.
        return _audio_gate(item, settings=settings)

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
        # recogniser did not hear it, a learner will not either. **A run of
        # words, contractions read (launch 2026-09-26, B1):** this compared the
        # whole answer with ONE heard word, so *would cancel* could never pass,
        # and *might have* failed against a recogniser that wrote *might've*.
        if not answer_spoken_in(item.answer, heard):
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
    #: The last probe call's self-reported confidence, carried to whichever
    #: report this loop returns. `None` until a probe has actually answered.
    confidence: str | None = None
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
        confidence = _confidence(response)

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
                        probe_confidence=confidence,
                    ),
                )
            return Validated(
                None,
                ValidationReport(
                    "discarded",
                    blind_solver=("mapping_mismatch",),
                    solver_calls=calls,
                    probe_confidence=confidence,
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
                    canonical=probe_canonical(current),
                    solver_calls=calls,
                    probe_confidence=confidence,
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
                    canonical=probe_canonical(current),
                    solver_calls=calls,
                    probe_confidence=confidence,
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
                        probe_confidence=confidence,
                        canonical=probe_canonical(current),
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
                    canonical=probe_canonical(current),
                    solver_calls=calls,
                    probe_confidence=confidence,
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
                canonical=probe_canonical(current),
                solver_calls=calls,
                probe_confidence=confidence,
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
