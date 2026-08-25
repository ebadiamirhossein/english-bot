"""Pure validation for the two authored structures: grammar targets and the
checkpoint blueprint.

Nothing here reaches a database or a model. Everything is a function of its
argument, so the whole authoring gate is testable without Postgres -- which is
what lets `python -m core.syllabus.seed` refuse bad content before it writes a
row rather than after.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.items import ITEM_TYPES
from core.syllabus import (
    CHECKPOINT_ITEM_COUNT,
    CHECKPOINT_PASS_PCT,
    MURPHY_MAX_UNIT,
)

# `error_types.murphy_units` (migration 001) already stores exactly this shape:
# '69-81', '5-6,11-14', '1-4'. Matching it means S11's existing range expansion
# reads a syllabus reference without a second parser.
_MURPHY_RE = re.compile(r"^\d{1,3}(-\d{1,3})?(,\s?\d{1,3}(-\d{1,3})?)*$")


class ContentError(ValueError):
    """An authored unit that must not reach the database."""


@dataclass(frozen=True, slots=True)
class GrammarTarget:
    target: str
    murphy_units: str | None


def parse_murphy(spec: str) -> tuple[tuple[int, int], ...]:
    """'29-38,42' -> ((29, 38), (42, 42)). Raises ContentError on anything else.

    Bounds are checked against MURPHY_MAX_UNIT, which is a fact about the book
    rather than about this repository. **There is no catalogue table to check
    against** -- `book_units` is a per-learner OCR log, not a list of Murphy's
    units -- so format and bounds are the whole of what can be verified here,
    and the record says so rather than implying a stronger check.
    """
    if not isinstance(spec, str) or not _MURPHY_RE.match(spec.strip()):
        raise ContentError(f"malformed Murphy reference: {spec!r}")
    spans: list[tuple[int, int]] = []
    for part in spec.split(","):
        lo_s, _, hi_s = part.strip().partition("-")
        lo = int(lo_s)
        hi = int(hi_s) if hi_s else lo
        if lo > hi:
            raise ContentError(f"descending Murphy range: {part.strip()!r}")
        if not (1 <= lo and hi <= MURPHY_MAX_UNIT):
            raise ContentError(
                f"Murphy range outside 1-{MURPHY_MAX_UNIT}: {part.strip()!r}"
            )
        spans.append((lo, hi))
    return tuple(spans)


def validate_grammar_targets(raw: object, *, unit_number: int) -> tuple[GrammarTarget, ...]:
    """3-5 targets, each with a non-empty name and an optional Murphy range.

    PRD §3 says "3-5"; the W8 row says ">=3". The tighter of the two is enforced,
    here and as a CHECK in migration 014.

    `murphy_units` is NULLABLE and that is not a lowered bar. Stage 6's PRD cell
    names no Murphy units at all, and `error_types.murphy_units` is already NULL
    for six of nineteen types -- among them `collocation` and the register and
    pronunciation types, which is Stage 6's entire content.
    """
    if not isinstance(raw, list):
        raise ContentError(f"unit {unit_number}: grammar_targets must be a list")
    if not 3 <= len(raw) <= 5:
        raise ContentError(
            f"unit {unit_number}: {len(raw)} grammar targets, PRD §3 requires 3-5"
        )
    out: list[GrammarTarget] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ContentError(f"unit {unit_number}: a grammar target must be an object")
        target = str(entry.get("target", "")).strip()
        if not target:
            raise ContentError(f"unit {unit_number}: a grammar target has no name")
        if target.lower() in seen:
            raise ContentError(f"unit {unit_number}: duplicate grammar target {target!r}")
        seen.add(target.lower())
        murphy = entry.get("murphy_units")
        if murphy is not None:
            parse_murphy(str(murphy))
            murphy = str(murphy).strip()
        out.append(GrammarTarget(target, murphy))
    return tuple(out)


def validate_checkpoint(raw: object, *, unit_number: int, targets: tuple[GrammarTarget, ...]) -> dict:
    """A blueprint, and the word is load-bearing.

    A blueprint SPECIFIES WHAT THE 12 ITEMS MUST TEST -- how many items per
    grammar target, how many on target lexemes, which item types are permitted,
    and the pass mark. **It contains no sentence, no answer, no cue and no
    item.** W8 authors zero items and writes zero rows to `items`.

    That distinction is not fastidiousness. Standing rule 4 of
    `docs/TASKS-v3-web.md`: "No slice ships an exercise item that has not passed
    the validator." An item authored here would carry a NULL `validator_version`
    and would never have seen the blind-solver or uniqueness gates -- which is
    precisely the population W10's `validator_version = VALIDATOR_VERSION`
    filter exists to exclude. W10 generates the items; W11 runs the checkpoint.
    """
    if not isinstance(raw, dict):
        raise ContentError(f"unit {unit_number}: checkpoint must be an object")

    if raw.get("item_count") != CHECKPOINT_ITEM_COUNT:
        raise ContentError(
            f"unit {unit_number}: checkpoint item_count must be "
            f"{CHECKPOINT_ITEM_COUNT} (PRD §3)"
        )
    if raw.get("pass_pct") != CHECKPOINT_PASS_PCT:
        raise ContentError(
            f"unit {unit_number}: checkpoint pass_pct must be "
            f"{CHECKPOINT_PASS_PCT} (PRD §3)"
        )

    known = {t.target for t in targets}
    per_target = raw.get("per_target")
    if not isinstance(per_target, dict) or not per_target:
        raise ContentError(f"unit {unit_number}: checkpoint needs a per_target map")
    for name, count in per_target.items():
        if name not in known:
            raise ContentError(
                f"unit {unit_number}: checkpoint tests {name!r}, which is not one "
                "of this unit's grammar targets"
            )
        if not isinstance(count, int) or count < 1:
            raise ContentError(
                f"unit {unit_number}: checkpoint count for {name!r} must be >= 1"
            )
    missing = known - set(per_target)
    if missing:
        raise ContentError(
            f"unit {unit_number}: checkpoint ignores grammar target(s) "
            f"{sorted(missing)} -- a target nothing checks is not a target"
        )

    lexeme_items = raw.get("lexeme_items")
    if not isinstance(lexeme_items, int) or lexeme_items < 0:
        raise ContentError(f"unit {unit_number}: checkpoint lexeme_items must be >= 0")

    total = sum(per_target.values()) + lexeme_items
    if total != CHECKPOINT_ITEM_COUNT:
        raise ContentError(
            f"unit {unit_number}: checkpoint blocks sum to {total}, not "
            f"{CHECKPOINT_ITEM_COUNT} -- a blueprint that does not add up "
            "cannot be generated against"
        )

    types = raw.get("item_types")
    if not isinstance(types, list) or not types:
        raise ContentError(f"unit {unit_number}: checkpoint needs item_types")
    unknown = [t for t in types if t not in ITEM_TYPES]
    if unknown:
        raise ContentError(
            f"unit {unit_number}: checkpoint names item type(s) {unknown} that "
            "core.items.ITEM_TYPES does not define"
        )
    if len(set(types)) != len(types):
        raise ContentError(f"unit {unit_number}: duplicate item_types")

    # No item in the blueprint. Asserted rather than assumed, because the
    # cheapest way for this rule to be broken later is a well-meaning author
    # pasting an example sentence in "just to show the shape".
    banned = {"prompt_text", "answer", "items", "sentence", "options", "tiles"}
    present = banned & set(raw)
    if present:
        raise ContentError(
            f"unit {unit_number}: checkpoint carries {sorted(present)} -- a "
            "blueprint specifies what items must test and never contains one "
            "(W10 generates them, past the validator)"
        )

    return {
        "item_count": CHECKPOINT_ITEM_COUNT,
        "pass_pct": CHECKPOINT_PASS_PCT,
        "per_target": dict(per_target),
        "lexeme_items": lexeme_items,
        "item_types": list(types),
    }


__all__ = [
    "ContentError",
    "GrammarTarget",
    "parse_murphy",
    "validate_checkpoint",
    "validate_grammar_targets",
]
