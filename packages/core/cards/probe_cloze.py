"""How many cloze cards in the deck admit more than one answer? Measure first.

**The finding this exists to size.** A card in production reads

    "I wish someone had warned me to ask about _____ upfront," she said.

and *hidden costs*, *the price*, *fees* and *the terms* all fit. The learner
cannot know which one is wanted, so a correct answer is marked wrong.

**This is not one bad card.** W5a built a multi-answer uniqueness probe for
exactly this failure and it applies to `items` only. Cloze *cards* are produced
by `core.cards.migrate_chunks`, gapped by `core.services.anki.make_sentence_with_gap`,
which removes the phrase and checks nothing. **Every cloze card in the deck was
created ungated.**

**What is established and what is not.** That they were created ungated is a
fact about the code. How many are *actually* multi-acceptable is not known, and
two of fourteen and fourteen of fourteen point at different fixes with very
different costs. So this module measures and proposes nothing. The ruling on how
a cloze gap gets a uniqueness check is the human's, after the number exists.

---

## What this module is, and is not

It **reuses W5a's probe**. It does not write a second one, and there is no second
prompt: `gates.probe_acceptable` is called directly, and the counting is
`grading.distinct_answers` over `grading.equivalence_key` — the same two
functions the live gate uses, so `I'll` and `I will` collapse into one class here
exactly as they do in production. A second probe would drift from the first the
way duplicated `chat()` call sites already have.

**A card maps onto a real `ClozeCuedItem`, not a fake one.** `probe_acceptable`
sends `visible_projection(item)` and nothing else, and for `cloze_cued` that is
exactly `{"item_type": "cloze_cued", "prompt_text": ...}`. `BaseItem` requires
`track` and `prompt_text`; `ClozeCuedItem` adds no fields of its own. So:

    prompt_text = card.front      answer = card.back      track = TRACK

`track` is the only field not taken from the card, and **`visible_projection`
never emits it** — asserted in `tests/test_cards_probe_cloze.py`. The model sees
the learner's own gapped sentence and nothing else.

This module never calls `visible_projection` itself. That function has exactly
three permitted callers, held by
`tests/test_core_boundary.py::test_exactly_one_module_projects_an_item`, because
a second serialiser makes the probe describe something other than what a learner
sees while every downstream number stays green. The projection is built inside
`probe_acceptable`, where it belongs, and the assertion about its shape is made
from the tests, which are outside that scan. The first draft of this module
imported it to pretty-print the dry run and the boundary caught it — recorded
here because the fix was to stop, not to widen the list.

**The gap is not rewritten.** `core.services.anki.GAP` is `_____` (five) and
`core.items.schema.GAP` is `___` (three). The card's front is passed through
byte-identical, because five underscores are what the learner is looking at, and
sending the model a normalised sentence nobody sees is precisely the defect W5b
found and W5c fixed — the gate asked the right question about the wrong string.
Nothing on this path counts gap tokens: `core.items.checks` does, but it runs
inside `gates.validate`, which this module does not call.

**It writes nothing.** No UPDATE, no INSERT, no DELETE, against `cards` or any
other table — asserted by a test that reads this module's own AST, the same
guarantee `migrate_chunks` carries.

---

## Pre-registered prediction — written before the run (#57, W5b)

Written down here, before `--live` was ever executed, so the answer cannot be
adjusted to fit afterwards. `--live` evaluates these rules itself and prints the
verdict, rather than leaving the reading to whoever is looking at the output.

**Prediction: 6 to 11 of the 14 cloze cards admit more than one answer class.**

Reasoning, so a wrong prediction is informative rather than merely wrong: v2
`chunks` are multi-word phrases mined from real sentences, and a gapped
multi-word phrase inside its own full sentence is far more constrained than a
gapped single word. That argues for the low end. Against it: the probe counts
*answer classes*, and near-synonymous phrases that a careful teacher would have
to mark correct are common in exactly the register these chunks come from. The
production example is at the ambiguous extreme, and it was found by reading one
card, which is weak evidence that it is typical.

**Branch rules, and the human rules on the approach either way:**

* **>= 10 multi-acceptable** — the defect is systemic. A cue on the card face is
  not enough for cards yet to be created; **A** (gate at creation) becomes the
  recommendation, plus a backfill for the ones already live.
* **4 to 9** — mixed. **B** (cue on the face) for the cards that already exist,
  because it works today and costs nothing; **A** for creation from W10.
* **<= 3** — the production card is an outlier. **B** alone, no gate, no
  per-card model call.
* **Any card whose canonical is not among the probe's classes** is reported
  separately as `not_recoverable`, whatever the totals say. That is a stronger
  defect than multi-acceptability — the card is not answerable as authored — and
  it has a different fix.

---

## Running it

Dry by default. The dry run reaches the database, reports what it found and the
prediction it is about to test, and spends nothing:

    python -m core.cards.probe_cloze

The billed run asks first, and is a human step on the production host — the
calls cost money and the rows are production:

    python -m core.cards.probe_cloze --live

`logging.basicConfig` is called at entry, which is **#140**: `core/llm.py` logs
exact per-call token usage at INFO on every call, and a script that never
configures logging drops every one of those lines through `logging.lastResort`.
That is how W8's tagger had to have its 138 calls and $6.60 reconstructed
afterwards against a $1-2 estimate. `core.items.judge_observe` and
`core.items.verify` both still spend without doing this; #140 stays open and
names them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from core.items import ANSWER_FAMILY, PROBED_FAMILIES
from core.items import gates
from core.items.grading import distinct_answers, equivalence_key
from core.items.schema import ClozeCuedItem
from core.services import cards as cards_service

logger = logging.getLogger(__name__)

#: The one field a card does not supply. `visible_projection` never emits it, so
#: it does not reach the model and cannot influence the measurement — but it is
#: a constant rather than a per-card guess so that fact is checkable.
TRACK = "life"

#: The type a gapped card is, in item terms. Its family is `slot`, which never
#: widens: a second fitting form means the gap tests nothing.
ITEM_TYPE = "cloze_cued"

#: Prediction, pre-registered above. Inclusive.
PREDICTED_LOW = 6
PREDICTED_HIGH = 11


@dataclass(frozen=True)
class Probed:
    """One card's result. `classes` is the count, `first` is what led the list."""

    card_id: int
    user_id: int
    card_type: str
    front: str
    back: str
    classes: int
    recoverable: bool
    confidence: str | None
    first_class: str | None


def as_item(card) -> ClozeCuedItem:
    """A card as the item the probe already knows how to read.

    Byte-identical `prompt_text`: the five-underscore gap goes through untouched.
    """
    return ClozeCuedItem(
        track=TRACK,
        prompt_text=card.front,
        answer=card.back,
    )


def probe_one(card, *, settings=None) -> Probed:
    """One billed call. Returns the count, never a verdict on what to do."""
    item = as_item(card)
    response = gates.probe_acceptable(item, settings=settings)
    candidates = gates._candidates(response)
    classes = distinct_answers(candidates)
    return Probed(
        card_id=card.id,
        user_id=card.user_id,
        card_type=card.card_type,
        front=card.front,
        back=card.back,
        classes=len(classes),
        recoverable=equivalence_key(card.back) in classes,
        confidence=gates._confidence(response),
        first_class=candidates[0] if candidates else None,
    )


def verdict(multi: int) -> str:
    """The pre-registered branch rules, applied by the module and not by hand."""
    if multi >= 10:
        return (
            "Branch: >=10 -> systemic. A (gate at creation) from W10, plus a "
            "backfill for the cards already live."
        )
    if multi >= 4:
        return (
            "Branch: 4-9 -> mixed. B (cue on the face) for the live cards, "
            "A (gate at creation) from W10."
        )
    return (
        "Branch: <=3 -> the production card is an outlier. B alone, no gate "
        "and no per-card model call."
    )


def _print_rows(results: list[Probed]) -> None:
    for row in sorted(results, key=lambda r: r.card_id):
        flag = "" if row.recoverable else "  ** NOT RECOVERABLE **"
        plural = "class" if row.classes == 1 else "classes"
        print(f"  {row.card_id} · {row.card_type} · {row.front!r} · "
              f"{row.classes} {plural}{flag}")


def _summarise(results: list[Probed]) -> int:
    multi = sum(1 for r in results if r.classes > 1)
    unrecoverable = sum(1 for r in results if not r.recoverable)
    print()
    print(f"{len(results)} cloze cards probed · {multi} multi-acceptable · "
          f"{unrecoverable} not_recoverable")
    met = PREDICTED_LOW <= multi <= PREDICTED_HIGH
    print(
        f"Prediction was {PREDICTED_LOW}-{PREDICTED_HIGH} multi-acceptable: "
        f"{'MET' if met else 'NOT MET'}."
    )
    print(verdict(multi))
    if unrecoverable:
        print(
            f"{unrecoverable} card(s) are not answerable as authored — a "
            "stronger defect than ambiguity, with a different fix. Listed above."
        )
    return multi


def dry_run() -> int:
    """Reach the database, report the population, spend nothing."""
    cards = cards_service.cloze_cards()
    print(f"{len(cards)} cloze cards in the deck.")
    print(f"Family for {ITEM_TYPE}: {ANSWER_FAMILY[ITEM_TYPE]} "
          f"(probed: {ANSWER_FAMILY[ITEM_TYPE] in PROBED_FAMILIES})")
    print()
    # The projection is NOT built here. `core.items.projection.visible_projection`
    # has exactly three permitted callers — `gates`, `verify` and
    # `core.services.items` — enforced by
    # `tests/test_core_boundary.py::test_exactly_one_module_projects_an_item`,
    # and the reason is that a second serialiser makes the probe describe
    # something other than what a learner sees while every number stays green.
    # So this prints the item's own `prompt_text`, and the assertion that the
    # projection is exactly `{item_type, prompt_text}` — and that `track` never
    # reaches the wire — is made in the tests, which are outside that scan.
    print("What each call would send — the learner's own front, gap intact:")
    for card in sorted(cards, key=lambda c: c.id)[:3]:
        print(f"  {card.id} · prompt_text={as_item(card).prompt_text!r}")
    if len(cards) > 3:
        print(f"  … and {len(cards) - 3} more")
    print()
    print(f"Prediction, registered before any run: {PREDICTED_LOW}-"
          f"{PREDICTED_HIGH} of {len(cards)} multi-acceptable.")
    print(f"--live would make {len(cards)} billed calls.")
    print("dry run — nothing written, nothing sent")
    return 0


def _confirm(calls: int) -> bool:
    print(f"\nAbout to make {calls} billed model calls. Nothing is written to")
    print("any database.")
    return input("Type y to continue, anything else to stop: ").strip().lower() == "y"


def live(*, settings=None) -> int:
    cards = cards_service.cloze_cards()
    if not cards:
        print("No cloze cards. Nothing to probe and nothing to spend.")
        return 0
    if not _confirm(len(cards)):
        print("Stopped. Nothing was sent.")
        return 1
    print()
    results = [probe_one(card, settings=settings) for card in cards]
    _print_rows(results)
    _summarise(results)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure how many cloze cards admit more than one answer. "
        "Dry by default; --live makes one billed call per card and writes "
        "nothing."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="make the calls and print the finding (billed)",
    )
    args = parser.parse_args(argv)
    # #140. This module spends money, and core/llm.py's per-call token lines are
    # dropped on the floor by any script that leaves the root logger bare.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.live:
        return live()
    return dry_run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
