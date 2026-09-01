"""W13-i cue timings: the active-cue rule, the offset map, the identity gate.

**Pure — no database, no network, no fixture file.** Everything here is a
literal, and **no committed fixture holds anyone's subtitles**: the tracks below
are SYNTHESISED to carry the shape T5 measured on the host — overlapping
windows, float seconds, a `start` and a `duration` on every element. #175 is why
(scraped subtitle text in a product with paying users, checked before it enters
the repo), and it costs nothing: the property under test is the overlap, not the
content.

CLAUDE.md §3 rule 5: every expected value here is **hardcoded or computed
independently**, never derived from the function under test. The md5s are
computed by the test from its own literals.

THE THREE QUESTIONS:

1. **What does the fixture supply that production does not?** Nothing beyond
   shape. `ROLLING` reproduces the measured pattern — 92% of consecutive pairs
   overlapping, `start`s ascending, floats — and `CONTIGUOUS` reproduces a
   manual track (TED-Ed: `7.003 + 4.713 = 11.716` exactly).
2. **Does the production caller supply it?** `core.video_api._read_cues` on a
   fetch, and the backfill on a dump. Both hand a list of
   `{text, start, duration}` to the same functions called here.
3. **Does the assertion name the thing, or count it?** It names the cue index,
   the character range, and — for the gate — which side of the comparison
   differed.
"""

from __future__ import annotations

import pytest

from core.video.cues import (
    active_cue,
    cue_offsets,
    joined_text,
    normalise_cues,
    reproduces,
)

#: A generated track, in the measured shape. **Consecutive pairs overlap** —
#: cue 0 runs 0 → 3.84 while cue 1 starts at 2.4, which is the Friends pair T5
#: quoted verbatim.
ROLLING = [
    {"text": "hey", "start": 0.0, "duration": 3.84},
    {"text": "how are you", "start": 2.4, "duration": 3.5},
    {"text": "doing today", "start": 5.1, "duration": 2.9},
    {"text": "fine thanks", "start": 7.2, "duration": 4.0},
]

#: A manual track. Contiguous: `7.003 + 4.713 == 11.716` exactly, as measured.
CONTIGUOUS = [
    {"text": "first line", "start": 7.003, "duration": 4.713},
    {"text": "second line", "start": 11.716, "duration": 3.0},
]


# ── the active-cue rule (§1a) ───────────────────────────────────────────────


def test_before_the_first_cue_nothing_is_active() -> None:
    """A boundary, and the honest answer is None rather than cue 0."""
    assert active_cue(ROLLING, -1.0) is None
    assert active_cue(ROLLING, 0.0) == 0


@pytest.mark.parametrize(
    "position,expected",
    [
        (0.0, 0),
        (2.39, 0),
        (2.4, 1),    # the newer window opens; both are live from here
        (3.83, 1),   # cue 0 is still displayed and cue 1 still wins
        (3.84, 1),   # cue 0's window closes and NOTHING changes
        (5.1, 2),
        (7.2, 3),
        (99.0, 3),   # after the last start, the last cue stays lit
    ],
)
def test_latest_started_wins_at_every_instant(position, expected) -> None:
    """**The ruling.** The active cue is the one with the greatest `start` at or
    before `t` — and the rule never reads `duration`, which is what makes the
    92% overlap irrelevant to it."""
    assert active_cue(ROLLING, position) == expected


def test_the_selection_never_goes_backwards_over_a_real_track() -> None:
    """**Monotonicity is the property, not a happy accident.** Swept at 0.01 s
    over an overlapping track, the index must never decrease — which is exactly
    what `longest-remaining wins` could not promise, since cue N can outlast
    cue N+1 and the highlight would jump back."""
    previous = -1
    t = 0.0
    while t <= 12.0:
        index = active_cue(ROLLING, t)
        assert index is not None
        assert index >= previous, f"went backwards at t={t:.2f}"
        previous = index
        t += 0.01


def test_a_gap_mid_track_keeps_the_last_line_lit() -> None:
    """**The third boundary, and it is correct under the ruling.** The rule
    cannot see `duration`, so it cannot know a window closed. On a contiguous
    manual track a silence leaves the last spoken line highlighted throughout —
    written down so a reader who sees it does not file it."""
    assert active_cue(CONTIGUOUS, 30.0) == 1


def test_an_empty_track_has_no_active_cue() -> None:
    assert active_cue([], 5.0) is None


# ── the offset map (§1a's mechanism) ────────────────────────────────────────


def test_each_cue_owns_a_character_range_in_the_joined_text() -> None:
    """**Exact, not approximate** — and it is exact only because the join
    reproduces the stored transcript byte for byte (T5's three-way md5)."""
    text = joined_text(ROLLING)
    assert text == "hey how are you doing today fine thanks"

    spans = cue_offsets(ROLLING)
    assert len(spans) == len(ROLLING)
    for span, cue in zip(spans, ROLLING):
        start, end = span
        assert text[start:end] == cue["text"]


def test_the_offsets_are_computed_independently_of_the_function() -> None:
    """CLAUDE.md §3 rule 5: the expected values are built here, by hand, from
    the literals — never asked of the code under test."""
    assert cue_offsets(ROLLING) == [(0, 3), (4, 15), (16, 27), (28, 39)]


# ── the identity gate (§2, and S2's write-time half) ────────────────────────


def test_the_gate_passes_when_the_join_reproduces_the_text() -> None:
    assert reproduces(ROLLING, "hey how are you doing today fine thanks") is True


def test_the_gate_refuses_a_single_changed_character() -> None:
    """**md5, not length** — the plan refuses length-equality explicitly, and
    this pair is the reason: same length, different text."""
    same_length = "hey how are you doing today fine thankS"
    assert len(same_length) == len(joined_text(ROLLING))
    assert reproduces(ROLLING, same_length) is False


def test_the_gate_refuses_a_reordering(  ) -> None:
    reordered = list(reversed(ROLLING))
    assert reproduces(reordered, joined_text(ROLLING)) is False


# ── normalisation: what may become a cue at all ─────────────────────────────


def test_a_cue_without_a_start_makes_the_whole_track_unusable() -> None:
    """**All or nothing, deliberately.** A partial timing set is not a timing
    set for a follow-along highlight, and half a track would light some lines
    and silently skip others."""
    assert normalise_cues([{"text": "a", "start": 0.0}, {"text": "b"}]) is None


def test_normalisation_keeps_float_seconds_and_does_not_round() -> None:
    """`7.003` is what the actor sends. Rounding to integers would move every
    cue boundary by up to half a second."""
    cues = normalise_cues(CONTIGUOUS)
    assert cues is not None
    assert cues[0]["start"] == 7.003
    assert cues[1]["start"] == 11.716


def test_normalisation_refuses_a_track_whose_starts_descend() -> None:
    """The rule's monotonicity assumes sorted `start`s. A descending track is
    refused rather than sorted — re-ordering somebody else's cues is a repair,
    and the plan refuses repairs on the same ground the md5 gate does."""
    assert normalise_cues(
        [{"text": "a", "start": 5.0, "duration": 1.0},
         {"text": "b", "start": 1.0, "duration": 1.0}]
    ) is None


def test_normalisation_refuses_a_non_list_and_an_empty_list() -> None:
    assert normalise_cues(None) is None
    assert normalise_cues([]) is None
    assert normalise_cues("not a list") is None
