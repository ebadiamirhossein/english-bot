"""W18 — scoring a sitting and what the learner is shown. **Pure; no database.**

User action: the learner finishes a placement sitting (`POST /placement/finish`
reads these functions) or opens Progress (`GET /progress` reads `shown`).

Expected values are worked by hand from the formulas the module states — never
by calling the function under test for its own expectation (§3 rule 5).

**RED DEMONSTRATIONS (2026-09-25), each one edit, run, and restored:** the
false-alarm correction removed (`h` used as it is) turned
`test_saying_yes_to_pseudo_words_is_subtracted` red; `FALSE_ALARM_LIMIT = 1.0`
turned `test_yes_to_everything_is_not_read_at_all` red; `_higher` returning the
LATER band instead of the higher turned
`test_a_lower_sitting_changes_nothing_that_is_shown` red; `raised_from` set on
every second sitting turned `test_a_sitting_that_reads_the_same_announces_nothing`
red; the `real` membership check removed from `pseudowords` turned three
pseudo-word tests red.
**The rest, by a scripted mutation each (`python -B`, caches cleared):** hit
counts used instead of hit RATES (the perfect-sheet and hit-rate tests);
rounding to the thousand (`3750` read `4000`); the B1 threshold at 2,400; the
listening shares moved; `RETEST_DAYS = 30`; the vocabulary shown as the LAST
estimate; `shown([])` returning a view; a first sitting reporting a raise (two
tests); a raise not announced; the shape rule's ending check removed (the new
hand-written test — a generated sample never ends in *-ed*, which is why that
test exists); a short list returned instead of refused.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from core.placement import pseudowords, scoring
from core.placement.scoring import Sitting


def _real(hits_per_band: list[int]) -> list[tuple[int, bool]]:
    """Four words in each band; the first ``hits`` of them answered yes."""
    out = []
    for band, hits in enumerate(hits_per_band):
        for i in range(4):
            out.append((band * 1000 + 1 + i, i < hits))
    return out


def test_a_perfect_sheet_reads_ten_thousand() -> None:
    assert scoring.vocabulary_estimate(_real([4] * 10), [False] * 20) == 10_000


def test_the_estimate_is_the_bands_hit_rates_times_a_thousand() -> None:
    # 4,4,4,3,2,2,1,0,0,0 of four, no false alarms:
    # 1000+1000+1000+750+500+500+250 = 5000.
    assert scoring.vocabulary_estimate(_real([4, 4, 4, 3, 2, 2, 1, 0, 0, 0]), [False] * 20) == 5000


def test_saying_yes_to_pseudo_words_is_subtracted() -> None:
    # f = 4/20 = 0.2. Bands at 4/4: (1-0.2)/0.8 = 1 → 1000 each, three of them.
    # Bands at 2/4: (0.5-0.2)/0.8 = 0.375 → 375, two of them. Bands at 0: 0.
    # 3000 + 750 = 3750.
    real = _real([4, 4, 4, 2, 2, 0, 0, 0, 0, 0])
    assert scoring.vocabulary_estimate(real, [True] * 4 + [False] * 16) == 3800  # 3750 → nearest 100


def test_yes_to_everything_is_not_read_at_all() -> None:
    assert scoring.vocabulary_estimate(_real([4] * 10), [True] * 11 + [False] * 9) is None


def test_vocabulary_bands_follow_the_stated_thresholds() -> None:
    assert scoring.vocabulary_band(None) is None
    assert scoring.vocabulary_band(1200) == "A2"
    assert scoring.vocabulary_band(2499) == "A2"
    assert scoring.vocabulary_band(2500) == "B1"
    assert scoring.vocabulary_band(3249) == "B1"
    assert scoring.vocabulary_band(3250) == "B2"
    assert scoring.vocabulary_band(3750) == "C1"
    assert scoring.vocabulary_band(9000) == "C1"


ALL_SIX = ("A2", "B1", "B1", "B2", "B2", "C1")


def test_listening_reads_right_answers_up_the_order() -> None:
    assert scoring.listening_band([], served=[]) is None
    six = lambda n: [True] * n + [False] * (6 - n)  # noqa: E731
    assert [scoring.listening_band(six(n), served=ALL_SIX) for n in range(7)] == [
        "A2", "A2", "B1", "B1", "B2", "B2", "C1",
    ]


def test_listening_never_claims_a_band_no_clip_was_served_at() -> None:
    """Launch 2026-09-26, B2: production's bank has no listening C1. A sitting
    that skipped it and got the five clips it DID serve right read C1 — the
    share rule alone cannot see which bands were asked. Capped at the highest
    band served; the share still decides below it."""
    five = ("A2", "B1", "B1", "B2", "B2")
    assert scoring.listening_band([True] * 5, served=five) == "B2"
    assert scoring.listening_band([True] * 3, served=("A2", "B1", "B1")) == "B1"
    assert scoring.listening_band([True, True, False, False, False], served=five) == "B1"


def _sitting(day: int, cefr: str, **bands) -> Sitting:
    full = {"vocabulary": None, "grammar": None, "listening": None, "speaking": None}
    full.update(bands)
    return Sitting(date(2026, 10, day), cefr, full)


def test_nothing_is_shown_before_a_first_sitting() -> None:
    assert scoring.shown([]) is None


def test_a_first_sitting_is_shown_as_it_read_and_raises_nothing() -> None:
    view = scoring.shown([_sitting(1, "B1", grammar="B1", listening="B2")])
    assert view.where_to_start == "B1"
    assert view.radar == {"vocabulary": None, "grammar": "B1", "listening": "B2", "speaking": None}
    assert view.raised_from is None and view.raised_skills == ()
    assert [(p.finished_on.day, p.band) for p in view.history] == [(1, "B1")]


def test_a_higher_sitting_is_announced() -> None:
    view = scoring.shown([
        _sitting(1, "B1", grammar="B1", listening="B1"),
        _sitting(29, "B2", grammar="B2", listening="B1"),
    ])
    assert view.where_to_start == "B2"
    assert view.raised_from == "B1"
    assert view.raised_skills == ("grammar",)


def test_a_lower_sitting_changes_nothing_that_is_shown() -> None:
    view = scoring.shown([
        _sitting(1, "B2", grammar="B2", listening="B2"),
        _sitting(29, "B1", grammar="B1", listening="A2"),
    ])
    assert view.where_to_start == "B2"
    assert view.radar["grammar"] == "B2" and view.radar["listening"] == "B2"
    assert [p.band for p in view.history] == ["B2", "B2"]
    assert view.raised_from is None and view.raised_skills == ()


def test_a_sitting_that_reads_the_same_announces_nothing() -> None:
    view = scoring.shown([_sitting(1, "B1", grammar="B1"), _sitting(29, "B1", grammar="B1")])
    assert view.raised_from is None and view.raised_skills == ()


def test_the_vocabulary_shown_is_the_highest_read() -> None:
    first = Sitting(date(2026, 10, 1), "B1", {}, vocab_estimate=3100)
    second = Sitting(date(2026, 10, 29), "B1", {}, vocab_estimate=2800)
    assert scoring.shown([first, second]).vocab_estimate == 3100


def test_the_next_sitting_is_offered_twenty_eight_days_on() -> None:
    assert scoring.next_sitting_from(None) is None
    assert scoring.next_sitting_from(date(2026, 10, 1)) == date(2026, 10, 29)


# ── pseudo-words ────────────────────────────────────────────────────────────


def test_pseudo_words_are_deterministic_and_avoid_every_real_word() -> None:
    real = frozenset({"blorent", "festik"})
    one = pseudowords.pseudowords(40, seed=18, real=real)
    two = pseudowords.pseudowords(40, seed=18, real=real)
    assert one == two
    assert len(set(one)) == 40
    assert not set(one) & real


def test_a_real_word_the_generator_makes_is_refused() -> None:
    """**Red:** the membership check removed from `pseudowords` — the first
    candidate the seed makes comes back although it is declared real."""
    first = pseudowords.pseudowords(1, seed=18, real=frozenset())[0]
    assert first not in pseudowords.pseudowords(5, seed=18, real=frozenset({first}))


def test_pseudo_words_keep_the_shape_rules() -> None:
    for word in pseudowords.pseudowords(120, seed=18, real=frozenset()):
        assert re.fullmatch(r"[a-z]{5,9}", word), word
        assert not word.endswith(("s", "ed", "ing", "er", "ly")), word


def test_an_impossible_request_is_refused_rather_than_shortened() -> None:
    with pytest.raises(ValueError, match="pseudo-words could be made"):
        pseudowords.pseudowords(10, seed=1, real=_EVERYTHING())


class _EVERYTHING:
    def __contains__(self, _: object) -> bool:
        return True


def test_the_shape_rule_refuses_an_inflected_ending() -> None:
    """The syllable tables rarely produce *-ed*, so a sample of generated words
    cannot show this rule working — it is asserted on hand-written inputs.
    **Red:** `pronounceable` with the ending check removed."""
    assert pseudowords.pronounceable("flampet")
    assert not pseudowords.pronounceable("flamped")
    assert not pseudowords.pronounceable("tranking")
    assert not pseudowords.pronounceable("blorents")
    assert not pseudowords.pronounceable("glooom")  # three of one letter
    assert not pseudowords.pronounceable("brak")  # too short
