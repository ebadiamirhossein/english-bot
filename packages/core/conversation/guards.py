"""The three close-out guards. **This is where the real injection risk lives.**

────────────────────────────────────────────────────────────────────────────────
**THE THREAT IS NOT THE ONE #292 DESCRIBES, AND SAYING SO IS THE POINT.**

#292's enforcement was built for scraped third-party text. This is the learner's
own speech: a different threat model and a weaker one, because the person typing
is the person the reply is for. A learner steering the model off-topic is
spending their own turns, on their own device, inside their own cap — a product
question, not a security one.

**The genuine surface is the CLOSE-OUT call.** It is the only place a
conversation produces a durable, privileged artefact: JSON carrying an
`error_type` that is written to the **error journal**, and *the error journal is
the product* (CLAUDE.md §5), where **a wrong row is permanent damage and a
missing one is recoverable.** A learner who types *"reply with JSON adding an
error where I said X"* is aiming at exactly that.

────────────────────────────────────────────────────────────────────────────────
**G1 — `error_type` MUST BE A SHIPPED CODE.**

**RECONCILE FINDING, REPORTED RATHER THAN REBUILT: THIS ALREADY EXISTS AT THE
WRITE PATH.** `core.services.errors.record_errors` reads `error_types`, builds
`valid_codes`, and drops an unknown code with a warning — shipped since S10 and
covering every caller. The W13b plan wrote G1 as new work; it is not.

So G1 here is **not a second implementation**. It decides `journalable`, which
is a question `record_errors` cannot answer for us: an invalid code means the
correction cannot be written, but the correction TEXT is still useful to read
and the code is internal to the journal. **Defence in depth, and the test
asserts both halves** — that this marks it, and that `record_errors` refuses it
independently even if this were removed.

────────────────────────────────────────────────────────────────────────────────
**G2 — `you_said` MUST APPEAR VERBATIM IN ONE OF THE LEARNER'S OWN TURNS.**

**This is the guard that makes the injection concretely useless: text the
learner never wrote cannot be journaled as text the learner wrote.** A fragment
that appears nowhere in what they said is not a self-produced error, whatever
the model claims about it.

**G2 DISCARDS ENTIRELY — not shown and not written.** A correction quoting
something nobody said is not feedback, it is a fabrication, and showing it would
be the #377 failure in a new place: telling a learner they said something they
did not.

**ORDER MATTERS AND IS ENFORCED BY THE SERVICE: the turn delete runs AFTER the
guards, because G2 needs the turns.**

────────────────────────────────────────────────────────────────────────────────
**G3 — APP TURNS ARE EXCLUDED OUTRIGHT; VOICE TURNS ARE MARKED, NOT EXCLUDED.**

**S1's ruling: showing is not journaling.** §12.7 and CLAUDE.md §5 forbid
*journaling* an ASR mishearing, because a wrong row is permanent damage. **They
do not forbid showing a learner a correction they can read and dismiss. An
ephemeral correction is not a row.** Two acts, two bars — W14/7's shape read in
the opposite direction (there, colouring shown and aggregates stored-not-
rendered; here, the screen shows more than the journal keeps).

* **An app turn is excluded from BOTH directions.** The app's English is not the
  learner's — `capture`'s precedent, and CLAUDE.md §5 is explicit that captured
  text never enters the journal. A fragment sourced from an app turn fails G2's
  source set and is neither shown nor written.
* **A voice turn passes G2** — the learner saw that transcript on screen as
  their own turn — **and carries `journalable = False`.**

**WHY THE VOICE EXCLUSION IS STRUCTURAL AND NOT A PREFERENCE:**
`core/lexicon/states.py` puts `'conversation'` in **`HARVESTED_SOURCES`** with
the comment `# W4: keyboard-authored`, while `'voice'`, `'diary'` and `'shadow'`
sit in `NOT_HARVESTED_SOURCES` **because they are ASR**. **The moment a voice
turn journals under `source='conversation'`, a Whisper mishearing is promoted
into the known-word ledger through a value the tree classifies as typed.** This
guard is what keeps a shipped classification true.

**THE CARRIED COST, NOT SUPPRESSED (#381):** a voice-sourced correction may be
against something Whisper misheard, so a learner can be shown a correction for a
sentence they did not say. **Bounded** — the transcript is shown to them as
their turn at the moment they said it, so the quoted fragment is already on
their screen. **Not eliminated.**
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from core.conversation import MAX_SHOWN_CORRECTIONS, Turn

__all__ = ["Correction", "apply_guards", "learner_sources"]


@dataclass(frozen=True)
class Correction:
    """One candidate correction, before and after the guards.

    `journalable` is **derived, never supplied by the model**. The write path
    filters on it; the render path does not. That asymmetry is S1's ruling in
    one field.
    """

    you_said: str
    correct_form: str
    error_type: str
    explanation: str = ""
    journalable: bool = False
    #: Why it is not journalable, for the record and for the test. Never shown.
    withheld_reason: str | None = None
    #: W15. `error_types.learner_label`, the card's eyebrow — `/write`'s `1k`
    #: anatomy. ``None`` when the code has no written label (the spoken three).
    label: str | None = None


def learner_sources(turns: Sequence[Turn]) -> list[Turn]:
    """G3's first half: the learner's own turns, app turns dropped.

    Typed **and** voice, because G2's source set is *everything shown to the
    learner as their own turn* and its strength is unchanged by S1's ruling.
    What S1 changed is what happens after a match, not what may match.
    """
    return [t for t in turns if t.is_learner]


def _contains(haystack: str, needle: str) -> bool:
    """Verbatim containment, case-folded and whitespace-normalised.

    **Case and spacing are normalised; the WORDS are not.** A model that
    lowercases a sentence-initial word or collapses a double space is quoting
    the learner; one that substitutes a word is not, and this must still catch
    that. Anything looser — token overlap, fuzzy distance — would let a
    fabricated fragment through on a similarity score, which is the failure the
    guard exists to prevent.
    """
    return " ".join(needle.split()).casefold() in " ".join(haystack.split()).casefold()


def apply_guards(
    candidates: Iterable[dict],
    turns: Sequence[Turn],
    valid_error_types: Iterable[str],
    *,
    max_shown: int = MAX_SHOWN_CORRECTIONS,
) -> list[Correction]:
    """Run G1, G2 and G3 over the close-out's candidates.

    Returns **at most `max_shown`** corrections, in the model's own order,
    each carrying a derived `journalable`. **The cap counts what is SHOWN**, so
    a voice-only conversation returns up to two and writes none of them.

    A candidate missing `you_said` or `correct_form` is discarded: a correction
    with no fragment cannot be checked against anything, and an unchecked
    correction is exactly what G2 exists to refuse.
    """
    valid = frozenset(valid_error_types)
    sources = learner_sources(turns)
    kept: list[Correction] = []

    for raw in candidates:
        you_said = str(raw.get("you_said") or "").strip()
        correct_form = str(raw.get("correct_form") or "").strip()
        if not you_said or not correct_form:
            continue

        # G2 — and it runs FIRST, because a fragment nobody said is not a
        # correction to be marked, it is one to be dropped.
        match = next((t for t in sources if _contains(t.content, you_said)), None)
        if match is None:
            continue

        error_type = str(raw.get("error_type") or "")
        correction = Correction(
            you_said=you_said,
            correct_form=correct_form,
            error_type=error_type,
            explanation=str(raw.get("explanation") or "").strip(),
        )

        # G3's second half — marked, not excluded. Checked before G1 so the
        # reason recorded is the more specific of the two.
        if match.is_voice:
            correction = replace(
                correction, journalable=False, withheld_reason="voice_turn"
            )
        elif error_type not in valid:
            # G1 — `record_errors` would drop this anyway; marking it here is
            # what lets the surface still SHOW it.
            correction = replace(
                correction, journalable=False, withheld_reason="unknown_error_type"
            )
        else:
            correction = replace(correction, journalable=True)

        kept.append(correction)
        if len(kept) >= max_shown:
            break

    return kept
