"""W14 §A / #370 — **an unspoken word contributes no phonemes to the store.**

────────────────────────────────────────────────────────────────────────────────
THIS IS A GUARD, NOT A REPAIR — AND THE ORIGINAL CLAIM HERE WAS WRONG.

**THE OLD TEXT IS QUOTED RATHER THAN DELETED (#82's shape):** *"Azure returns a
`Phonemes` array for an omitted word, at accuracy 0. W14's first writer
flattened those into `speech_attempts.phonemes` beside real measurements."*

**THE HOST READ ON 2026-09-04 REFUTES IT.** Attempt 1's three `Omission` words —
`staging`, `and`, `production` — each carry **`phonemes_on_word = 0`**. **Azure
returns no phonemes for an omitted word at all**, so the store was never
poisoned by that route and there was nothing to repair.

**WHAT THIS FILTER STILL DOES, stated honestly as prevention rather than fix:**
`core/speech.py` is provider-agnostic by design — CLAUDE.md §2 requires that
swapping providers be one environment variable — and **the parser is exactly
where a provider's shape variation should be absorbed.** A different adapter, or
Azure changing its granularity behaviour, could return phoneme rows for a word
nobody said. **A phoneme for an unspoken word is not a measurement, so the
parser refuses to produce one whether or not today's provider sends it.**

**AND THE PAYLOAD BELOW IS SYNTHETIC — IT IS NOT A SHAPE AZURE PRODUCES.**
`_payload` gives every word phonemes, including omitted ones, which is the whole
point of the guard and is also **CLAUDE.md §3 rule 4's territory: a green test
over a path that is currently unreachable.** It is kept because the cost is one
`continue` and the failure it prevents is permanent damage (PRODUCT-PRINCIPLES
§5) — **but it must not be read as evidence about Azure's behaviour, which is
the opposite of what it asserts.**

**WHAT THE READ DID FIND, AND IT INVERTS THE CAUTION:** phonemes at accuracy 0
**do** exist in the store — 2 of 37 on attempt 1, 2 of 54 on attempt 2, 1 of 49
on attempt 4 — **inside words that WERE spoken** (`deployment` at 10, `we` at
46). Those are individual sounds a learner attempted and did not make. **They are
real measurements and they are precisely the signal W17 exists to find.**
See #370.

**`words` IS DELIBERATELY UNCHANGED.** The omitted word stays in the per-word
list — **it is how the learner sees they stopped early.** Only `phonemes` was
poisoned, and only `phonemes` is filtered.
"""

from __future__ import annotations

import pytest

from core.speech import NOT_MEASURED, NO_ERROR, parse_assessment


def _payload(*words: tuple[str, float, str]) -> dict:
    """An Azure-shaped response. **Every word carries phonemes, as Azure does.**"""
    return {
        "RecognitionStatus": "Success",
        "NBest": [
            {
                "AccuracyScore": 52.0,
                "FluencyScore": 79.0,
                "CompletenessScore": 50.0,
                "PronScore": 55.0,
                "Words": [
                    {
                        "Word": word,
                        "AccuracyScore": accuracy,
                        "ErrorType": error_type,
                        "Phonemes": [
                            {"Phoneme": f"{word[0]}1", "AccuracyScore": accuracy},
                            {"Phoneme": f"{word[0]}2", "AccuracyScore": accuracy},
                        ],
                    }
                    for word, accuracy, error_type in words
                ],
            }
        ],
    }


def test_an_omitted_word_keeps_its_place_in_words_and_contributes_no_phonemes() -> None:
    """The exact shape production produced on attempt 1."""
    result = parse_assessment(
        _payload(
            ("we", 46.0, "Mispronunciation"),
            ("dev", 94.0, NO_ERROR),
            ("staging", 0.0, "Omission"),
            ("and", 0.0, "Omission"),
            ("production", 0.0, "Omission"),
        )
    )

    # **`words` IS UNCHANGED — all five, in order, omissions included.**
    assert [w.word for w in result.words] == [
        "we", "dev", "staging", "and", "production",
    ]
    assert [w.error_type for w in result.words] == [
        "Mispronunciation", NO_ERROR, "Omission", "Omission", "Omission",
    ]

    # **`phonemes` CARRIES ONLY THE TWO SPOKEN WORDS.** Two phonemes each,
    # asserted by value so the count alone cannot hide the wrong pair.
    assert [(p.phoneme, p.accuracy) for p in result.phonemes] == [
        ("w1", 46.0), ("w2", 46.0), ("d1", 94.0), ("d2", 94.0),
    ]
    assert not any(p.accuracy == 0.0 for p in result.phonemes), (
        "a phoneme at 0 for an unspoken word is a measurement that did not "
        "happen (PRODUCT-PRINCIPLES §5)"
    )


def test_a_mispronounced_word_DOES_contribute_its_phonemes() -> None:
    """**The positive control, and it is the one that matters.**

    Without it the filter could exclude everything and the test above would
    still pass (#345). A `Mispronunciation` at 10.0 **was** spoken — badly — and
    it is exactly what W17 exists to accumulate. Excluding it would throw away
    the signal along with the noise.
    """
    result = parse_assessment(_payload(("deployment", 10.0, "Mispronunciation")))
    assert [(p.phoneme, p.accuracy) for p in result.phonemes] == [
        ("d1", 10.0), ("d2", 10.0),
    ]


@pytest.mark.parametrize("error_type", sorted(NOT_MEASURED))
def test_every_not_measured_kind_is_excluded(error_type: str) -> None:
    """`Insertion` too: a word the learner said that is not in the reference has
    no reference phoneme to be scored against either."""
    result = parse_assessment(
        _payload(("real", 90.0, NO_ERROR), ("ghost", 0.0, error_type))
    )
    assert [w.word for w in result.words] == ["real", "ghost"]
    assert [p.phoneme for p in result.phonemes] == ["r1", "r2"]


def test_a_word_with_no_phonemes_key_is_survivable() -> None:
    """Azure may omit the array entirely; that must not raise."""
    payload = _payload(("solo", 88.0, NO_ERROR))
    del payload["NBest"][0]["Words"][0]["Phonemes"]
    result = parse_assessment(payload)
    assert [w.word for w in result.words] == ["solo"]
    assert result.phonemes == ()
