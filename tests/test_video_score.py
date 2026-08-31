"""W12b: PRD §7.2's selection score.

THE THREE QUESTIONS, for the fixtures in this file:

1. WHAT DOES THIS FIXTURE SUPPLY THAT PRODUCTION DOES NOT?
   Constructed `Candidate` values, and this is the one place in the slice where
   that is right: these are pure functions of numbers, and a real transcript
   would add nothing to a test of arithmetic while hiding which number caused a
   failure. **The seam this does not cross is named rather than left implied:**
   nothing here proves the numbers arriving from production are well-formed --
   `coverage` comes from `coverage_for` and `duration_s` from the Data API, and
   `tests/test_video_service.py` is where those two seams are crossed.

2. DOES THE PRODUCTION CALLER SUPPLY IT?
   Yes, and each is named per test. `assign.main()` builds every `Candidate`
   field: `coverage`/`proper_nouns_detected` from `CoverageReport`, `seen` from
   `svc.seen_video_ids`, `accent_exposure` from `svc.accent_exposure`,
   `track_weights` from `svc.track_weights`, `targets` from
   `syllabus.unit_target_lexemes`.

3. DOES THE ASSERTION NAME THE THING, OR COUNT IT?
   It names it. `test_accent_rotation_prefers_the_least_exposed_accent` asserts
   WHICH video wins, not that a number moved -- a count could not see the wrong
   twelve in W11.

**EVERY EXPECTED VALUE HERE IS HAND-COMPUTED AND WRITTEN DOWN**, never taken
from what the function returns (CLAUDE.md §3 rule 5). Where a weight appears it
is the literal from PRD §7.2, not `WEIGHTS[...]`.
"""

from __future__ import annotations

import pytest

from core.video.score import (
    BAND_HIGH,
    BAND_LOW,
    WEIGHTS,
    Candidate,
    accent_rotation,
    coverage_fit,
    length_fit,
    rank,
    score_one,
    seen_penalty,
    target_hit,
    topic_match,
)

#: Migration 012's default, written out rather than imported.
DEFAULT_WEIGHTS = {"life": 50, "curiosity": 30, "work": 20}


def candidate(**overrides) -> Candidate:
    values = {
        "video_id": 1,
        "youtube_id": "vid00000001",
        "track": "life",
        "accent": "british",
        "duration_s": 8 * 60,
        "coverage": 0.95,
        "proper_nouns_detected": True,
        "lemmas": frozenset(),
        "seen": False,
    }
    values.update(overrides)
    return Candidate(**values)


# ── the weights are PRD §7.2's, not whatever the module says ────────────────


def test_the_five_weights_are_the_prd_numbers_and_sum_to_one() -> None:
    assert WEIGHTS["coverage_fit"] == 0.40
    assert WEIGHTS["topic_match"] == 0.20
    assert WEIGHTS["accent_rotation"] == 0.15
    assert WEIGHTS["target_hit"] == 0.15
    assert WEIGHTS["length_fit"] == 0.10
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_the_band_is_the_ruled_ninety_three_to_ninety_eight() -> None:
    """#88's resolution. Hardcoded here so a silent edit to the module fails."""
    assert (BAND_LOW, BAND_HIGH) == (0.93, 0.98)


# ── coverage_fit ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("coverage", [0.93, 0.95, 0.98])
def test_coverage_inside_the_band_scores_a_full_point(coverage: float) -> None:
    assert coverage_fit(coverage) == 1.0


def test_coverage_at_prd_2_1_s_drowning_floor_scores_zero() -> None:
    """PRD §2.1: "Below 90% the learner drowns"."""
    assert coverage_fit(0.90) == 0.0
    assert coverage_fit(0.85) == 0.0


def test_a_fully_known_transcript_scores_zero_not_a_negative() -> None:
    """PRD §2.1: "above 99% they learn nothing"."""
    assert coverage_fit(1.00) == 0.0


def test_coverage_between_the_floor_and_the_band_rises_linearly() -> None:
    """Hand-computed: (0.915 - 0.90) / (0.93 - 0.90) = 0.015/0.03 = 0.5."""
    assert coverage_fit(0.915) == pytest.approx(0.5)


def test_coverage_above_the_band_falls_linearly() -> None:
    """Hand-computed: (1.00 - 0.99) / (1.00 - 0.98) = 0.01/0.02 = 0.5."""
    assert coverage_fit(0.99) == pytest.approx(0.5)


def test_a_video_inside_the_band_outscores_one_outside_it() -> None:
    """Names both videos, rather than asserting that a number differs."""
    inside = candidate(youtube_id="inside", coverage=0.95)
    outside = candidate(youtube_id="outside", coverage=0.995, video_id=2)
    ranked = rank(
        [outside, inside],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert ranked[0].candidate.youtube_id == "inside"


# ── topic_match ─────────────────────────────────────────────────────────────


def test_topic_match_is_the_learners_own_weight_as_a_proportion() -> None:
    """50/30/20 sums to 100, so the three scores are 0.5, 0.3 and 0.2."""
    assert topic_match("life", DEFAULT_WEIGHTS) == pytest.approx(0.5)
    assert topic_match("curiosity", DEFAULT_WEIGHTS) == pytest.approx(0.3)
    assert topic_match("work", DEFAULT_WEIGHTS) == pytest.approx(0.2)


def test_topic_match_follows_a_learner_who_raised_work() -> None:
    """PRD §4.6 caps work at 20% "unless the user raises it" -- so it follows."""
    raised = {"life": 40, "curiosity": 20, "work": 40}
    assert topic_match("work", raised) == pytest.approx(0.4)


def test_an_unknown_track_scores_zero_rather_than_raising() -> None:
    assert topic_match("nonsense", DEFAULT_WEIGHTS) == 0.0


# ── accent_rotation ─────────────────────────────────────────────────────────


def test_accent_rotation_prefers_the_least_exposed_accent() -> None:
    """NAMES THE CHOSEN VIDEO. Production supplies exposure from
    `svc.accent_exposure`, which reads `video_assignments`, not the pool."""
    exposure = {"american": 3, "british": 1}
    american = candidate(youtube_id="american1", accent="american")
    british = candidate(youtube_id="british1", accent="british", video_id=2)
    ranked = rank(
        [american, british],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure=exposure,
        targets=frozenset(),
    )
    assert ranked[0].candidate.youtube_id == "british1"


def test_accent_rotation_is_hand_computed_from_the_exposure_counts() -> None:
    """3 american of 4 total: american = 1 - 3/4 = 0.25, british = 1 - 1/4."""
    exposure = {"american": 3, "british": 1}
    assert accent_rotation("american", exposure) == pytest.approx(0.25)
    assert accent_rotation("british", exposure) == pytest.approx(0.75)


def test_an_empty_history_does_not_make_every_accent_maximally_novel() -> None:
    """0.5, not 1.0: no accent is under-exposed when none has been seen, and
    1.0 would let week one's empty history dominate the whole score."""
    assert accent_rotation("british", {}) == 0.5


# ── target_hit ──────────────────────────────────────────────────────────────


def test_target_hit_names_the_lexemes_it_matched() -> None:
    """Two of four targets present -> 0.5. Counted by hand from the sets."""
    targets = frozenset({"commute", "landlord", "deposit", "tenancy"})
    lemmas = frozenset({"commute", "landlord", "the", "and"})
    assert target_hit(lemmas, targets) == pytest.approx(0.5)


def test_target_hit_with_no_targets_is_zero_for_everyone() -> None:
    """So the term drops out of the ranking instead of distorting it."""
    assert target_hit(frozenset({"anything"}), frozenset()) == 0.0


def test_target_hit_reads_lexis_and_has_no_grammar_input_at_all() -> None:
    """Operator ruling: lexis only, never grammar.

    Asserted structurally rather than by comment: `target_hit` takes two sets of
    LEMMAS and nothing else, so there is no parameter through which a grammar
    target could reach it. Nothing in this tree detects a grammar target in
    running text (#212), and a term returning a constant would look like a
    measurement.
    """
    import inspect

    params = list(inspect.signature(target_hit).parameters)
    assert params == ["lemmas", "targets"]


# ── length_fit ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seconds", [4 * 60, 8 * 60, 12 * 60])
def test_length_inside_prd_s_four_to_twelve_minutes_is_a_full_point(
    seconds: int,
) -> None:
    assert length_fit(seconds) == 1.0


def test_a_two_minute_video_scores_half_on_length() -> None:
    """Hand-computed: 120 / 240 = 0.5."""
    assert length_fit(120) == pytest.approx(0.5)


def test_an_unknown_duration_scores_zero_rather_than_a_neutral_value() -> None:
    """A video whose length was never fetched is one the refresh path did not
    fully see, and it should lose to one it did."""
    assert length_fit(None) == 0.0


def test_a_very_long_video_scores_zero_on_length() -> None:
    assert length_fit(45 * 60) == 0.0


# ── seen_penalty ────────────────────────────────────────────────────────────


def test_seen_penalty_removes_a_video_already_assigned() -> None:
    """NAMES THE EXCLUDED ID. The penalty is a full point -- more than every
    weight summed -- so a repeat can never outscore a fresh video."""
    assert seen_penalty(True) == 1.0
    fresh = candidate(youtube_id="fresh")
    repeat = candidate(youtube_id="repeat", video_id=2, seen=True)
    ranked = rank(
        [repeat, fresh],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert ranked[0].candidate.youtube_id == "fresh"
    assert ranked[1].score < 0


# ── the whole score ─────────────────────────────────────────────────────────


def test_one_score_is_the_hand_computed_sum_of_its_five_terms() -> None:
    """Worked out here rather than asked of the function.

      coverage 0.95 -> inside the band            -> 1.0  x 0.40 = 0.40
      track 'life', weights 50/30/20              -> 0.5  x 0.20 = 0.10
      accent 'british', exposure american 3 / 1   -> 0.75 x 0.15 = 0.1125
      2 of 4 targets present                      -> 0.5  x 0.15 = 0.075
      duration 8 min, inside 4-12                 -> 1.0  x 0.10 = 0.10
      not seen                                    -> penalty 0
                                                    total = 0.7875
    """
    scored = score_one(
        candidate(lemmas=frozenset({"commute", "landlord", "the"})),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={"american": 3, "british": 1},
        targets=frozenset({"commute", "landlord", "deposit", "tenancy"}),
    )
    assert scored.score == pytest.approx(0.7875)
    assert scored.is_selectable


def test_the_breakdown_carries_every_term_so_a_choice_stays_diagnosable() -> None:
    """It is written to `video_assignments.score_breakdown`, and the pool it was
    computed against may be purged before anybody asks why."""
    scored = score_one(
        candidate(),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert set(scored.breakdown) == {
        "coverage_fit",
        "topic_match",
        "accent_rotation",
        "target_hit",
        "length_fit",
        "seen_penalty",
        "total",
    }


# ── the #288 exclusion (operator ruling A4) ─────────────────────────────────


def test_a_degraded_casing_candidate_is_excluded_and_says_why() -> None:
    """Selecting on a number known to be inflated is what this slice exists to
    stop. The reason names #288 so the exclusion is traceable."""
    scored = score_one(
        candidate(proper_nouns_detected=False),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert not scored.is_selectable
    assert "#288" in (scored.excluded or "")


def test_an_excluded_candidate_is_returned_not_dropped() -> None:
    """So the CLI can COUNT them. Pool starvation must not present itself as
    "no videos to assign" with no visible cause."""
    ranked = rank(
        [candidate(proper_nouns_detected=False)],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert len(ranked) == 1
    assert not ranked[0].is_selectable


def test_excluded_candidates_sort_last_never_away() -> None:
    good = candidate(youtube_id="good")
    degraded = candidate(
        youtube_id="degraded", video_id=2, proper_nouns_detected=False
    )
    ranked = rank(
        [degraded, good],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert [r.candidate.youtube_id for r in ranked] == ["good", "degraded"]


def test_allow_degraded_lets_the_operator_override_the_exclusion() -> None:
    """A ruling the operator makes explicitly, never a silent fallback."""
    scored = score_one(
        candidate(proper_nouns_detected=False),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
        require_proper_nouns=False,
    )
    assert scored.is_selectable


def test_ranking_is_stable_for_two_identical_scores() -> None:
    """A selection that changes between runs over unchanged data is one nobody
    can reproduce, so ties break on youtube_id."""
    first = candidate(youtube_id="aaa", video_id=1)
    second = candidate(youtube_id="bbb", video_id=2)
    forward = rank(
        [first, second],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    backward = rank(
        [second, first],
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert [r.candidate.youtube_id for r in forward] == ["aaa", "bbb"]
    assert [r.candidate.youtube_id for r in backward] == ["aaa", "bbb"]


# ── the band is a GATE, not only a scoring term ─────────────────────────────
#
# Found by running the command, not by reading it: a first end-to-end run
# assigned a transcript at 89.1% coverage -- below PRD §2.1's drowning floor --
# because `coverage_fit` is only 0.40 of a weighted sum and the other four terms
# carried it. W12b's acceptance criterion is *three videos assigned, each
# between 93% and 98% coverage*, so ranking by score alone violated the
# criterion silently. CLAUDE.md §3 rule 7: the bar is never quietly lowered.


def test_a_video_below_the_band_is_excluded_not_merely_ranked_lower() -> None:
    """The exact defect: 0.891 scored 0.235 and was assigned."""
    scored = score_one(
        candidate(coverage=0.891),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert not scored.is_selectable
    assert "outside the ruled" in (scored.excluded or "")
    assert "89.1%" in (scored.excluded or "")


def test_a_video_above_the_band_is_excluded_too() -> None:
    """98.3% is 0.3 points past the ceiling and still fails the criterion."""
    scored = score_one(
        candidate(coverage=0.983),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert not scored.is_selectable


@pytest.mark.parametrize("coverage", [0.93, 0.95, 0.98])
def test_the_band_edges_are_inclusive(coverage: float) -> None:
    """93% and 98% are *in*, so the criterion's own numbers are assignable."""
    scored = score_one(
        candidate(coverage=coverage),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert scored.is_selectable


def test_the_gate_and_the_score_disagree_by_design() -> None:
    """`coverage_fit` is non-zero outside the band and the gate still refuses.

    Pinned because the two look redundant and are not: the score ORDERS what is
    admitted, the band decides WHAT IS ADMITTED. Collapsing them would restore
    the defect the moment someone notices `coverage_fit` already "handles" it.
    """
    assert coverage_fit(0.92) > 0
    scored = score_one(
        candidate(coverage=0.92),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
    )
    assert not scored.is_selectable


def test_require_band_false_is_available_for_a_ruled_override() -> None:
    """As with --allow-degraded: an explicit act, never a silent fallback."""
    scored = score_one(
        candidate(coverage=0.80),
        track_weights=DEFAULT_WEIGHTS,
        accent_exposure={},
        targets=frozenset(),
        require_band=False,
    )
    assert scored.is_selectable
