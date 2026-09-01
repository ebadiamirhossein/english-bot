"""W13-i: the watch signal and the coverage badge. **Pure — no database.**

Both modules are in `core/video/`, which the boundary suite pins as unable to
reach a model, and both are pure arithmetic — so the rules block 2 depends on
are assertable without Postgres and without a fixture, the same standing
`core/video/score.py` has.

THE THREE QUESTIONS:

1. **What does this fixture supply that production does not?** Nothing. There is
   no fixture. Every value here is a literal, and no test reads the wall clock.
2. **Does the production caller supply it?** The two callers are
   `core.services.video.save_progress` and `core.services.sessions._input_block`,
   and the values below are the ones they pass: a clamped position and a stored
   `duration_s` for the first, a `CoverageReport`'s three fields for the second.
3. **Does the assertion name the thing, or count it?** It names it: which band,
   which boundary, and — for the two suppressions — *withheld*, which is a
   fourth answer and not a fourth band.
"""

from __future__ import annotations

import pytest

from core.video.badge import BANDS, MIN_COUNTED_TOKENS, band_for
from core.video.score import BAND_HIGH, BAND_LOW
from core.video.watch import WATCH_COMPLETE_FRACTION, clamp_position, is_complete


# ── the watch signal (#291) ─────────────────────────────────────────────────


def test_a_video_watched_to_the_end_is_complete() -> None:
    assert is_complete(720, 720) is True


def test_the_last_tenth_does_not_have_to_be_watched() -> None:
    """Titles, an outro and a subscribe card. A learner who stops there has
    watched it — which is why the constant is not 1.0."""
    assert is_complete(int(720 * WATCH_COMPLETE_FRACTION), 720) is True
    assert is_complete(int(720 * WATCH_COMPLETE_FRACTION) - 1, 720) is False


def test_half_watched_is_not_complete() -> None:
    assert is_complete(360, 720) is False


def test_an_unknown_duration_is_never_complete_and_that_is_the_documented_gap() -> None:
    """**#330, and the assertion is the gap rather than a workaround.**

    `length_fit` collapses "half an hour or more" with "we never fetched a
    duration"; here they are not collapsed, because one has a denominator and
    the other has none. **The cost is real and is stated at `is_complete`:** such
    a video can never reach `done`, so block 2 stays `ready` and returns the
    learner to it tomorrow. Inferring a completion from nothing is what #258
    forbids, and back-filling the duration from the browser is an unaudited
    write to a column the purge owns.
    """
    assert is_complete(10_000, None) is False
    assert is_complete(0, 0) is False


@pytest.mark.parametrize(
    "position,duration,expected",
    [
        (-5, 600, 0),          # a seek that fired mid-scrub
        (None, 600, 0),        # a player that has not started
        (700, 600, 600),       # past the end
        (300, 600, 300),       # ordinary
        (10_000, None, 10_000),  # no duration bounds nothing
    ],
)
def test_a_reported_position_is_bounded_by_what_is_known(
    position, duration, expected
) -> None:
    """**The browser is the source and the browser is not trusted.** The clamp
    is in the pure module rather than in the SQL so a second writer cannot be
    added without meeting it."""
    assert clamp_position(position, duration) == expected


# ── the badge (#288, #334, #330) ────────────────────────────────────────────


def test_the_three_bands_are_the_three_tokens() -> None:
    assert BANDS == ("below", "in", "above")


@pytest.mark.parametrize(
    "coverage,expected",
    [
        (0.80, "below"),
        (BAND_LOW - 0.0001, "below"),
        (BAND_LOW, "in"),
        (0.95, "in"),
        (BAND_HIGH, "in"),
        (BAND_HIGH + 0.0001, "above"),
        (0.995, "above"),
    ],
)
def test_the_band_is_read_off_the_same_constants_selection_ranks_on(
    coverage, expected
) -> None:
    """`BAND_LOW`/`BAND_HIGH` are imported from `score.py`, not restated. Two
    copies of one number is how the badge a learner reads and the term selection
    ranks on come to disagree."""
    assert band_for(coverage, counted_tokens=500) == expected


def test_no_percentage_can_be_returned() -> None:
    """**The whole point of the module.** The figure never crosses the boundary,
    so no client can render a number it was never given — the same shape as
    `visible_projection` withholding an answer by never handing it over."""
    for coverage in (0.0, 0.5, 0.9312, 0.94, 1.0):
        assert band_for(coverage, counted_tokens=500) in BANDS


def test_a_short_transcript_gets_no_badge_at_all() -> None:
    """**#330.** `5E5tNu4NsxM` is 17 seconds long with a 234-character
    transcript — roughly forty counted tokens, a granularity of 2.5%, so the
    whole five-point band is two distinguishable steps. Below the floor the
    answer is *withheld*, which is a fourth answer and not a fourth band."""
    assert band_for(0.95, counted_tokens=MIN_COUNTED_TOKENS - 1) is None
    assert band_for(0.95, counted_tokens=MIN_COUNTED_TOKENS) == "in"


def test_a_degraded_basis_withholds_and_it_is_a_provider_change_guard() -> None:
    """**This branch has never fired on this actor and, on the 2026-09-01
    measurement, will not.**

    Six stored transcripts including three from auto-generated tracks:
    `proper_nouns_detected` TRUE on all six, `casing` conventional on all six,
    `degraded_288 = 0`. `johnvc/YoutubeTranscripts` returns conventionally cased
    text even for auto-generated tracks, so the borrowed premise is true of
    YouTube's own payloads and false of this actor's output.

    **So this asserts a BEHAVIOUR and not a live condition**, and the branch is
    kept for #288's own stated reason: the premise is about an ACTOR, and
    `codepoetry/youtube-transcript-ai-scraper` is in the adapter table and has
    never been measured. **It does not address #288**, whose inflation now
    applies to every row equally and which nothing keyed on casing can reach.
    """
    assert band_for(0.95, counted_tokens=500, proper_nouns_detected=False) is None
    assert band_for(0.95, counted_tokens=500, proper_nouns_detected=True) == "in"
