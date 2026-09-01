"""PRD §7.2's selection score. Pure: no SQL, no HTTP, no model, no I/O.

    score = coverage_fit    x 0.40
          + topic_match     x 0.20
          + accent_rotation x 0.15
          + target_hit      x 0.15
          + length_fit      x 0.10
          - seen_penalty

Every term returns 0.0..1.0 so the weights mean what they say, and **every
constant below is traced to a document rather than chosen here.** A tuning
number with no source is a number the next reader cannot argue with.

TWO THINGS THIS MODULE DELIBERATELY DOES NOT DO:

1. **`target_hit` reads lexis and never grammar** (operator ruling). Nothing in
   this tree detects a grammar target in running text, and #212 shows the model
   is uneven at it. A grammar term that returned a constant would be worse than
   an absent one, because it would look like a measurement.

2. **It does not choose a segment.** Under the operator's ruling of 2026-08-30
   the full video is shown, so `length_fit` still prefers shorter videos but
   feeds no segment chooser. PRD §7.2's "segmentable to 3" is struck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# --- the band -------------------------------------------------------------
#
# 93-98%, ruled by the operator, resolving #88's three-way disagreement between
# PRD §2.1 (95-98%), PRD §7.2's formula (0.95-0.98) and TASKS' W12b acceptance
# criterion (93-98%). All three PRD sites are corrected to this in the same
# commit.
#
# **THE BAND IS RULED BUT NOT YET VALIDATED** (#289). It was ruled on figures
# produced BEFORE W12a corrected the lemmatiser, and W12a moved one real
# transcript 88.24% -> 75.76%. A band selects a SET, and the set of videos
# landing inside 93-98% on the corrected instrument is not the set the ruling
# imagined. Phase B re-validates it against real transcripts; until then this
# constant is the ruling, not a measurement.
BAND_LOW = 0.93
BAND_HIGH = 0.98

# PRD §2.1, verbatim: "Below 90% the learner drowns; above 99% they learn
# nothing." The falloff is anchored on those two numbers rather than on a taste
# for how steep a curve should be. 1.00 rather than 0.99 as the upper zero so a
# fully-known transcript scores 0 and not a small negative.
DROWN_FLOOR = 0.90
NOTHING_LEARNED_CEILING = 1.00

# PRD §7.2, verbatim: "length_fit(prefer 4-12 min)".
LENGTH_IDEAL_LOW_S = 4 * 60
LENGTH_IDEAL_HIGH_S = 12 * 60
# Not from a document, and said so. The outer bound at which a video scores 0 on
# length alone; 30 minutes is roughly the point at which PRD §4.1's 45-minute
# session cannot hold one video and the rest of the blocks.
LENGTH_ZERO_S = 30 * 60

WEIGHTS: dict[str, float] = {
    "coverage_fit": 0.40,
    "topic_match": 0.20,
    "accent_rotation": 0.15,
    "target_hit": 0.15,
    "length_fit": 0.10,
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One video, with everything the score needs and nothing it does not."""

    video_id: int
    youtube_id: str
    track: str
    #: **None means NOT A RELIABLE ACCENT SIGNAL (migration 020)**, and
    #: `score_one` SKIPS `accent_rotation` for it, renormalising the remaining
    #: weights. Never bucketed, never defaulted, never counted as exposure.
    accent: str | None
    duration_s: int | None
    coverage: float
    #: From CoverageReport. False means the proper-noun rule was switched off
    #: because the captions are not conventionally cased, so `coverage` is
    #: inflated by however many names the frequency floor holds (#288).
    proper_nouns_detected: bool
    #: The distinct lemmas of the transcript, for `target_hit`.
    lemmas: frozenset[str] = frozenset()
    #: Has this learner been assigned this video before?
    seen: bool = False


@dataclass(frozen=True, slots=True)
class Scored:
    """A candidate's score, its five terms, and why it was excluded if it was.

    `breakdown` is written to `video_assignments.score_breakdown` so a bad
    assignment stays diagnosable after the pool has been refreshed or purged --
    by which time the inputs that produced it are gone.
    """

    candidate: Candidate
    score: float
    breakdown: dict[str, float | None | bool] = field(default_factory=dict)
    excluded: str | None = None

    @property
    def is_selectable(self) -> bool:
        return self.excluded is None


def coverage_fit(coverage: float) -> float:
    """1.0 inside the band, falling linearly to 0 at PRD §2.1's two edges."""
    if coverage <= DROWN_FLOOR or coverage >= NOTHING_LEARNED_CEILING:
        return 0.0
    if BAND_LOW <= coverage <= BAND_HIGH:
        return 1.0
    if coverage < BAND_LOW:
        return (coverage - DROWN_FLOOR) / (BAND_LOW - DROWN_FLOOR)
    return (NOTHING_LEARNED_CEILING - coverage) / (
        NOTHING_LEARNED_CEILING - BAND_HIGH
    )


def topic_match(track: str, track_weights: Mapping[str, int]) -> float:
    """The learner's own weight for this track, as a proportion of all of them.

    With migration 012's default `{"life": 50, "curiosity": 30, "work": 20}` a
    life video scores 0.5, a curiosity video 0.3 and a work video 0.2.

    **This is a preference, not a quota**, and PRD §4.6's 50/30/20 is not
    enforced anywhere -- it is one 0.20 term in a weighted sum. The realised mix
    runs roughly proportional to the pool, which by channel count is 55/36/9.
    """
    total = sum(max(0, int(w)) for w in track_weights.values())
    if total <= 0:
        return 0.0
    return max(0, int(track_weights.get(track, 0))) / total


def accent_rotation(accent: str, exposure: Mapping[str, int]) -> float:
    """Bonus for the accent this learner has seen least. PRD §7.2.

    With no history at all every accent scores 0.5: no accent is
    under-exposed when none has been seen, and returning 1.0 for both would let
    an empty history dominate a term meant to correct an imbalance.

    **A NULL ACCENT IS REFUSED HERE RATHER THAN HANDLED (migration 020).** The
    caller skips the term; this function never sees a null in the normal path,
    and raising is how a new caller that forgot to skip finds out immediately
    instead of silently. `exposure.get(None, 0)` is a perfectly valid lookup
    returning a perfectly plausible number -- which is exactly the danger, and
    is why this raises rather than returning something defensible.
    """
    if accent is None:
        raise ValueError(
            "accent_rotation received a null accent. A null is SKIPPED by the "
            "caller -- never bucketed, never defaulted, never counted as "
            "exposure. See score_one and migration 020."
        )
    total = sum(max(0, int(n)) for n in exposure.values())
    if total <= 0:
        return 0.5
    return 1.0 - (max(0, int(exposure.get(accent, 0))) / total)


def target_hit(lemmas: frozenset[str], targets: frozenset[str]) -> float:
    """Fraction of this week's TARGET LEXEMES the transcript actually contains.

    Lexis only, never grammar -- see the module docstring.

    With no targets the term is 0.0 for every candidate, so it drops out of the
    ranking rather than distorting it. That is why it is not 0.5: a neutral
    value would still be a *weighted* neutral value and would compress the
    spread of every other term.
    """
    if not targets:
        return 0.0
    return len(lemmas & targets) / len(targets)


def length_fit(duration_s: int | None) -> float:
    """1.0 in PRD §7.2's 4-12 minute window, falling off both ways.

    An unknown duration scores 0.0 rather than a neutral value: a video whose
    length was never fetched is one the refresh path did not fully see, and it
    should lose to one it did.
    """
    if duration_s is None or duration_s <= 0:
        return 0.0
    if LENGTH_IDEAL_LOW_S <= duration_s <= LENGTH_IDEAL_HIGH_S:
        return 1.0
    if duration_s < LENGTH_IDEAL_LOW_S:
        return duration_s / LENGTH_IDEAL_LOW_S
    if duration_s >= LENGTH_ZERO_S:
        return 0.0
    return (LENGTH_ZERO_S - duration_s) / (LENGTH_ZERO_S - LENGTH_IDEAL_HIGH_S)


def seen_penalty(seen: bool) -> float:
    """1.0 for a video this learner already had, 0.0 otherwise.

    A full point, which is more than the sum of every weight, so a repeat can
    never outscore a fresh video however well it fits. PRD §7.4 assigns rather
    than offers, and being handed the same video twice reads as the app having
    lost track of you.
    """
    return 1.0 if seen else 0.0


def score_one(
    candidate: Candidate,
    *,
    track_weights: Mapping[str, int],
    accent_exposure: Mapping[str, int],
    targets: frozenset[str],
    require_proper_nouns: bool = True,
    require_band: bool = True,
) -> Scored:
    """Score one candidate, or exclude it and say why.

    ``require_proper_nouns`` is the operator's ruling of 2026-08-31 (A4): a
    video whose captions are not conventionally cased has its coverage inflated
    by the names in the frequency floor, and selecting on a number known to be
    inflated is the thing this slice exists to stop. Excluded candidates are
    RETURNED, not dropped, so the caller can count them -- pool starvation must
    not show up as "no videos to assign" with no visible cause.
    """
    if require_proper_nouns and not candidate.proper_nouns_detected:
        return Scored(
            candidate=candidate,
            score=0.0,
            excluded=(
                "coverage computed with the proper-noun rule switched off "
                "(captions are not conventionally cased), so the number is "
                "inflated by the names in the top-frequency floor -- #288"
            ),
        )

    # THE BAND IS A GATE, NOT ONLY A SCORING TERM, AND THIS WAS FOUND BY RUNNING
    # THE COMMAND RATHER THAN BY READING IT.
    #
    # `coverage_fit` is 0.40 of a weighted sum, so a video far outside the band
    # still scores above zero on the other four terms and wins whenever nothing
    # better exists. A first end-to-end run assigned a transcript at **89.1%**
    # coverage -- below PRD §2.1's drowning floor -- on a total of 0.235, while
    # W12b's own acceptance criterion in `docs/TASKS-v3-web.md` reads *three
    # videos assigned, each between 93% and 98% coverage*.
    #
    # Ranking by score alone therefore VIOLATES THE ACCEPTANCE CRITERION
    # SILENTLY, which is CLAUDE.md §3 rule 7 -- the bar is never quietly
    # lowered. The band gates admission; the score only orders what is admitted.
    # A thin pool now REFUSES rather than serving something the learner drowns
    # in, and #289's re-validation is what says whether the band admits enough.
    if require_band and not (BAND_LOW <= candidate.coverage <= BAND_HIGH):
        return Scored(
            candidate=candidate,
            score=0.0,
            excluded=(
                f"coverage {candidate.coverage:.1%} is outside the ruled "
                f"{BAND_LOW:.0%}-{BAND_HIGH:.0%} band, which W12b's acceptance "
                "criterion requires of every assigned video"
            ),
        )

    terms = {
        "coverage_fit": coverage_fit(candidate.coverage),
        "topic_match": topic_match(candidate.track, track_weights),
        "target_hit": target_hit(candidate.lemmas, targets),
        "length_fit": length_fit(candidate.duration_s),
    }
    # **A NULL ACCENT IS SKIPPED: THE TERM IS ABSENT, NOT ZERO (migration 020).**
    #
    # `accent IS NULL` means *this channel is not a reliable accent signal* --
    # TED-Ed has many narrators and no per-channel field can hold the truth
    # about it. Rotating on a value somebody invented is worse than not
    # rotating, so the term does not apply and is not computed.
    skipped = candidate.accent is None
    if not skipped:
        terms["accent_rotation"] = accent_rotation(candidate.accent, accent_exposure)

    penalty = seen_penalty(candidate.seen)
    # **THE DIVISOR IS THE WHOLE RULING, AND LEAVING IT OUT WOULD BE A PENALTY
    # ARRIVED AT BY ACCIDENT (operator ruling, 2026-09-01).**
    #
    # `WEIGHTS` sums to 1.00. Dropping `accent_rotation` from the numerator
    # without dropping 0.15 from the denominator is ARITHMETICALLY IDENTICAL to
    # scoring the term 0.0 -- a structural handicap no unknown-accent video
    # could ever recover, which is a default and a penalty, and both are
    # forbidden. Renormalising over the terms that ARE present is what "skipped"
    # means. With all five present the divisor is 1.00 and every existing score
    # is unchanged, which is what makes this safe.
    #
    # THE ACCEPTED CONSEQUENCE, RULED AND RECORDED RATHER THAN DISCOVERED: a
    # null-accent video can outrank a known-accent one whose accent is
    # over-exposed. That is correct -- BEING UNKNOWN IS NOT A PENALTY. If
    # unknown channels should later be mildly disadvantaged, that is a separate
    # ruling taken on purpose, not a divisor left out.
    weight = sum(WEIGHTS[name] for name in terms)
    total = sum(WEIGHTS[name] * value for name, value in terms.items()) / weight
    total -= penalty

    breakdown: dict[str, float | None | bool] = dict(terms)
    if skipped:
        # Named in the breakdown, which is written to
        # `video_assignments.score_breakdown`, so an operator reading a past
        # assignment sees the term was SKIPPED and not scored zero.
        breakdown["accent_rotation"] = None
        breakdown["accent_rotation_skipped"] = True
    breakdown["seen_penalty"] = penalty
    breakdown["total"] = total
    return Scored(candidate=candidate, score=total, breakdown=breakdown)


def rank(
    candidates: Sequence[Candidate],
    *,
    track_weights: Mapping[str, int],
    accent_exposure: Mapping[str, int],
    targets: frozenset[str],
    require_proper_nouns: bool = True,
    require_band: bool = True,
) -> list[Scored]:
    """Every candidate scored, best first. Excluded ones sort last, not away.

    The tie-break is `youtube_id`, so two videos with identical scores rank in a
    stable order rather than in whatever order the query returned them. A
    selection that changes between two runs over unchanged data is one nobody
    can reproduce.
    """
    scored = [
        score_one(
            candidate,
            track_weights=track_weights,
            accent_exposure=accent_exposure,
            targets=targets,
            require_proper_nouns=require_proper_nouns,
            require_band=require_band,
        )
        for candidate in candidates
    ]
    scored.sort(
        key=lambda s: (s.excluded is not None, -s.score, s.candidate.youtube_id)
    )
    return scored
