"""W14 / #377 — **the learner is shown the REFERENCE, never the transcript.**

────────────────────────────────────────────────────────────────────────────────
THE DEFECT, OBSERVED LIVE 2026-09-04

Reference: *"the model was incapable of handling inputs longer than its context
window"* — **one `was`.** The scored result rendered *"the model **was was**
incapable of handling inputs longer than its context window"* — **two**, the
first marked weak.

**THE COMPONENT WAS RENDERING AZURE'S `Words` ARRAY, WHICH IS WHAT AZURE HEARD.**
With `EnableMiscue: true` that array carries the reference words **plus
`Insertion` entries for words the learner said that are not in the reference** —
a stutter, a repetition, a filler. Rendering it verbatim **puts the learner's
disfluency into the sentence they were asked to read.**

**WHY THAT IS WORSE THAN A COSMETIC BUG.** The line on screen is the learner's
only record of what they were meant to say. **A learner who stutters is shown a
sentence containing their stutter, with the stutter marked as an error in the
text** — so the reference itself appears wrong, and the next attempt is read off
a corrupted target.

**THE SPLIT THIS LOCKS IN:** `speech_attempts.words` keeps **everything** — it is
the measurement, and an insertion is a real thing the learner did. **What the
learner is SHOWN excludes `Insertion`**, because by definition those words are
not in the reference.

**`Omission` STAYS VISIBLE, and the asymmetry is the point:** an omitted word
**is** a reference word — it is how the learner sees they stopped early (#370) —
while an inserted word is not.
"""

from __future__ import annotations

import json
import struct
from unittest.mock import patch

import httpx
import pytest

REFERENCE_WORDS = ["the", "model", "was", "incapable"]


def _response(words: list[tuple[str, float, str]]) -> dict:
    return {
        "RecognitionStatus": "Success",
        "NBest": [
            {
                "AccuracyScore": 90.0,
                "FluencyScore": 88.0,
                "CompletenessScore": 100.0,
                "PronScore": 89.0,
                "Words": [
                    {
                        "Word": word,
                        "AccuracyScore": accuracy,
                        "ErrorType": error_type,
                        "Phonemes": [
                            {"Phoneme": word[0], "AccuracyScore": accuracy}
                        ],
                    }
                    for word, accuracy, error_type in words
                ],
            }
        ],
    }


#: The live shape: a repeated word, returned as an `Insertion`.
STUTTER = _response(
    [
        ("the", 97.0, "None"),
        ("model", 95.0, "None"),
        ("was", 62.0, "None"),
        ("was", 40.0, "Insertion"),
        ("incapable", 93.0, "None"),
    ]
)


def test_the_parser_keeps_the_insertion_because_it_is_a_measurement() -> None:
    """**Nothing is dropped at the parser.** The learner did say it."""
    from core.speech import parse_assessment

    result = parse_assessment(STUTTER)
    assert [w.word for w in result.words] == [
        "the", "model", "was", "was", "incapable",
    ]
    assert [w.error_type for w in result.words][3] == "Insertion"
    # Its phonemes are excluded, as an unmeasured word's are (#370).
    assert [p.phoneme for p in result.phonemes] == ["t", "m", "w", "i"]


def test_what_the_learner_is_shown_reconstructs_the_reference_exactly() -> None:
    """**The rendered line must be the reference — one `was`, not two.**

    Asserted by VALUE against the reference word list, not by length: a count
    check would pass on any four words in any order.
    """
    from core.services.shadow_score import display_words
    from core.speech import parse_assessment

    shown = display_words(parse_assessment(STUTTER).words)
    assert [w["word"] for w in shown] == REFERENCE_WORDS


def test_an_omitted_word_stays_visible_and_that_asymmetry_is_deliberate() -> None:
    """An `Omission` IS a reference word — it is how a learner sees they
    stopped early (#370). Only `Insertion` is not."""
    from core.services.shadow_score import display_words
    from core.speech import parse_assessment

    payload = _response(
        [
            ("the", 97.0, "None"),
            ("model", 0.0, "Omission"),
            ("was", 95.0, "None"),
        ]
    )
    shown = display_words(parse_assessment(payload).words)
    assert [w["word"] for w in shown] == ["the", "model", "was"]
    assert shown[1]["error_type"] == "Omission"


def test_a_clean_attempt_is_unchanged_by_the_filter() -> None:
    """**The positive control.** Without it the filter could drop everything."""
    from core.services.shadow_score import display_words
    from core.speech import parse_assessment

    payload = _response([(w, 95.0, "None") for w in REFERENCE_WORDS])
    shown = display_words(parse_assessment(payload).words)
    assert [w["word"] for w in shown] == REFERENCE_WORDS
