"""PRD §4.3's repair-before-rejection ladder. Deterministic, no model call.

"**Repair before rejection** — add a cue rather than discard." The five cues are
PRD's, in PRD's order of increasing help, and the ladder walks them.

**Why deterministic matters here specifically.** A model-chosen cue would be a
billed call per repair *and* would make the acceptance fixtures repair
differently on each run, so a test asserting "this ambiguous item is repaired"
would be asserting on a coin flip. Cue *material* that cannot be derived — a
definition, an L1 gloss — is authored by the generator in the call that produced
the item (`schema.BaseItem.definition` / `.l1_gloss`), so the ladder only ever
selects, never invents.

**Where the word bank comes from.** PRD's own example is `I'll · I'd · I'm` —
the plausible alternatives for its broken item. Those are exactly what the blind
solver produced when it failed. So the solver's wrong answers become the
distractors: the gate's failure output is the repair's input, and the item ends
up cued against the ambiguity that was actually observed rather than one
imagined in advance.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.items.grading import fold_answer, normalise_variants
from core.items.schema import GAP, BaseItem, MCQItem

# PRD §4.3's table, top to bottom. Order is "least help first": a first letter
# narrows the field, a word bank hands over the candidate set, and an MCQ makes
# it a three-way choice. Giving more help than the ambiguity requires is how a
# validated item becomes a trivial one.
LADDER: tuple[str, ...] = (
    "first_letter_length",
    "definition",
    "l1_gloss",
    "word_bank",
    "converted_mcq",
)

# `converted_mcq` needs four options and `word_bank` needs a set worth showing.
_MIN_BANK = 2
_MCQ_OPTIONS = 4


def _is_gapped(item: BaseItem) -> bool:
    return GAP in (item.prompt_text or "") and item.answer is not None


def available_cues(
    item: BaseItem, distractors: Sequence[str] = ()
) -> tuple[str, ...]:
    """Which rungs this item can actually take, in ladder order.

    An unavailable rung is skipped rather than failed: a cue that cannot be
    rendered is not a repair, and pretending otherwise would burn one of the two
    permitted attempts on nothing.
    """
    usable = [d for d in distractors if fold_answer(d) != fold_answer(item.answer)]
    out: list[str] = []
    for cue in LADDER:
        if cue == "first_letter_length" and _is_gapped(item):
            out.append(cue)
        elif cue == "definition" and item.definition:
            out.append(cue)
        elif cue == "l1_gloss" and item.l1_gloss:
            out.append(cue)
        elif cue == "word_bank" and _is_gapped(item) and len(usable) >= _MIN_BANK:
            out.append(cue)
        elif (
            cue == "converted_mcq"
            and item.answer is not None
            and len(usable) >= _MCQ_OPTIONS - 1
        ):
            out.append(cue)
    return tuple(out)


def first_letter_cue(answer: str) -> str:
    """PRD's `I'_ _ _` (4) shape: first character, then a blank per character."""
    stripped = answer.strip()
    if not stripped:
        return ""
    rest = " ".join("_" for _ in stripped[1:])
    return f"{stripped[0]}{(' ' + rest) if rest else ''} ({len(stripped)})"


def apply_cue(
    item: BaseItem, cue: str, distractors: Sequence[str] = ()
) -> BaseItem:
    """Return a repaired copy carrying the cue. Never mutates — models are frozen.

    `repair_count` is not tracked here: it belongs to the orchestration in
    `gates.py`, and migration 012 caps it at 2 as a CHECK so the cap survives
    someone loosening the loop.
    """
    answer = item.answer or ""
    usable = [d for d in distractors if fold_answer(d) != fold_answer(answer)]

    if cue == "first_letter_length":
        return item.model_copy(
            update={"cue_type": cue, "cue_text": first_letter_cue(answer)}
        )
    if cue == "definition":
        return item.model_copy(
            update={"cue_type": cue, "cue_text": f"({item.definition})"}
        )
    if cue == "l1_gloss":
        return item.model_copy(
            update={"cue_type": cue, "cue_text": f"({item.l1_gloss})"}
        )
    if cue == "word_bank":
        # Sorted so the bank is reproducible run to run; the answer's position
        # carries no information because the whole set is shown.
        bank = sorted({answer, *usable[: _MCQ_OPTIONS - 1]}, key=fold_answer)
        return item.model_copy(
            update={"cue_type": cue, "cue_text": " · ".join(bank)}
        )
    if cue == "converted_mcq":
        # A genuine type change: the item stops being what it was. This is the
        # last rung for exactly that reason -- an `mcq` tests recognition where
        # a cloze tested production, and PRD §4 is explicit that
        # `l1_to_l2_production` is the highest-value drill *because* it forces
        # production. Converting is better than discarding and worse than any
        # rung above it.
        options = tuple(sorted({answer, *usable[: _MCQ_OPTIONS - 1]}, key=fold_answer))
        return MCQItem(
            track=item.track,
            register=item.register_tag,
            prompt_text=item.prompt_text,
            answer=answer,
            accepted_variants=normalise_variants(answer),
            cue_type=cue,
            cue_text=None,
            lexeme=item.lexeme,
            error_type=item.error_type,
            unit_number=item.unit_number,
            explanation=item.explanation,
            definition=item.definition,
            l1_gloss=item.l1_gloss,
            options=options,
        )
    raise ValueError(f"unknown cue type: {cue!r}")
