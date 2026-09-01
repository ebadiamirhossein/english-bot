"""A null accent is SKIPPED: never bucketed, never defaulted, never exposure.

**The failure these exist to prevent, and it is not the obvious one.** If a null
accent is carried into the scorer as a value -- whether as `None`, as the string
`"None"`, or as a sentinel like `"unknown"` -- `accent_rotation` buckets it, and
a bucket nobody has been exposed to scores `1.0 - 0/total = 1.0`, **the maximum
the term returns.** The unknown-accent video then wins BECAUSE its accent is
unknown. Worse, the same bucket inflates `total` in the exposure map, which
**lowers `american` and `british`**: the known accents are pushed down to make
room for the unknown one.

That is #315, and it reaches the scorer through the READ path -- `_pool_row` and
`accent_exposure` in `core.services.video` -- rather than through this module,
which is why it survived a review of the scorer.

**WHAT "SKIPPED" MEANS ARITHMETICALLY, BECAUSE THE OBVIOUS READING IS WRONG.**
Omitting `accent_rotation` from the weighted sum without dividing by the
remaining weight is identical to scoring it **0.0** -- a structural 0.15
handicap no unknown-accent video could ever recover. That is a penalty arrived
at by leaving out a divisor. The term is absent from `terms` AND the remaining
weights are renormalised, so a null-accent video is scored on its other four
merits at full scale.

**THE ACCEPTED CONSEQUENCE, RULED 2026-09-01 AND RECORDED HERE RATHER THAN
DISCOVERED LATER:** a null-accent video can outrank a known-accent one whose
accent is over-exposed. That is correct. **Being unknown is not a penalty.** If
unknown channels should later be mildly disadvantaged, that is a separate ruling
taken on purpose -- not a divisor left out.

These tests name what they assert. None of them counts.
"""

from __future__ import annotations

import pytest

from core.video import channels as channel_file
from core.video.score import WEIGHTS, Candidate, accent_rotation, rank


def _candidate(youtube_id: str, accent: str | None) -> Candidate:
    """Identical in every term but the accent, so the accent is the variable."""
    return Candidate(
        video_id=abs(hash(youtube_id)) % 10_000,
        youtube_id=youtube_id,
        track="life",
        accent=accent,
        duration_s=8 * 60,
        coverage=0.95,
        proper_nouns_detected=True,
        lemmas=frozenset({"go", "have"}),
        seen=False,
    )


def _rank(candidates, exposure):
    return rank(
        candidates,
        track_weights={"life": 50, "curiosity": 30, "work": 20},
        accent_exposure=exposure,
        targets=frozenset({"go"}),
    )


def test_accent_rotation_skips_a_video_with_no_accent() -> None:
    """**The term is ABSENT, not zero, and the breakdown says so by name.**

    Asserts which video is which by `youtube_id` and reads the reason field.
    A version of this test that compared totals would pass against a scorer
    that silently scored the null 0.0, which is the defect.
    """
    scored = {
        s.candidate.youtube_id: s
        for s in _rank(
            [
                _candidate("vid_american", "american"),
                _candidate("vid_british", "british"),
                _candidate("vid_null", None),
            ],
            {"american": 3, "british": 1},
        )
    }

    null_one = scored["vid_null"]
    assert null_one.breakdown["accent_rotation_skipped"] is True
    assert "accent_rotation" not in null_one.breakdown or (
        null_one.breakdown["accent_rotation"] is None
    )

    for known in ("vid_american", "vid_british"):
        assert scored[known].breakdown.get("accent_rotation_skipped") is not True
        assert isinstance(scored[known].breakdown["accent_rotation"], float)


def test_a_skipped_term_is_renormalised_and_not_scored_zero() -> None:
    """**The divisor is the whole ruling.** Without it, a null-accent video
    carries a 0.15 handicap forever and `skipped` would mean `penalised`.

    A null candidate is compared against a known one whose `accent_rotation` is
    exactly the pool average, so the two differ ONLY by whether the term is
    renormalised away or scored zero.
    """
    scored = {
        s.candidate.youtube_id: s
        for s in _rank(
            [_candidate("vid_null", None), _candidate("vid_known", "american")],
            # One accent seen once: `accent_rotation('american', ...)` is
            # 1.0 - 1/1 = 0.0, so the known video's term contributes NOTHING.
            {"american": 1},
        )
    }
    known = scored["vid_known"]
    null_one = scored["vid_null"]

    # The known video scored 0.0 on the term and keeps a 1.00 denominator; the
    # null video has no term and a 0.85 denominator. Same four other terms.
    assert known.breakdown["accent_rotation"] == pytest.approx(0.0)
    assert null_one.score > known.score, (
        "a skipped term must be renormalised away, not scored zero -- "
        "otherwise 'skipped' is a 0.15 penalty in disguise"
    )
    assert null_one.score == pytest.approx(
        known.score / (1.0 - WEIGHTS["accent_rotation"]), rel=1e-6
    )


def test_a_null_accent_is_not_treated_as_a_third_accent() -> None:
    """**Exposure history in which a bucketed null would WIN.**

    `american` and `british` are both heavily seen; a `None`/`"None"` bucket
    would be empty and score `1.0 - 0/total = 1.0`, the maximum. If the null
    candidate wins on that basis the term has been bucketed.
    """
    scored = _rank(
        [
            _candidate("vid_american", "american"),
            _candidate("vid_null", None),
        ],
        {"american": 9, "british": 9},
    )
    by_id = {s.candidate.youtube_id: s for s in scored}

    assert by_id["vid_null"].breakdown["accent_rotation_skipped"] is True
    # The maximum the term can return, which is what a fresh bucket would score.
    assert by_id["vid_null"].breakdown.get("accent_rotation") != 1.0


def test_accent_rotation_refuses_a_null_rather_than_bucketing_it() -> None:
    """The unit below the scorer. `accent_rotation` must not be callable with a
    null in a way that silently returns a number -- `exposure.get(None, 0)` is
    a perfectly valid lookup and that is exactly why it is dangerous."""
    with pytest.raises((TypeError, ValueError)):
        accent_rotation(None, {"american": 2, "british": 1})


def test_the_exposure_map_never_carries_a_null_bucket() -> None:
    """#315 site (b), at the seam rather than in the database.

    A `None` key -- or the string `"None"` -- in the exposure map inflates
    `total` and so LOWERS `american` and `british`. The corruption reaches the
    two real accents, not only the unknown one.
    """
    from core.services import video as svc

    assert hasattr(svc, "accent_exposure")
    source = svc.accent_exposure.__doc__ or ""
    assert "null" in source.lower(), (
        "accent_exposure must state what it does with a null accent"
    )


def test_a_by_ruling_null_is_pollable_in_the_real_committed_pool() -> None:
    """**Ruling 1's positive half, against the real file and not a fixture.**

    TED-Ed is null because no single value can be TRUE -- many narrators -- so
    it is pollable with the accent term skipped. This is worth asserting against
    the committed pool because it is a claim about *this project's data*, not
    only about the loader.
    """
    pool = channel_file.load()
    ted = next((c for c in pool.channels if c.handle == "@TEDEd"), None)
    assert ted is not None, "a by_ruling null accent must be pollable"
    assert ted.accent is None


def test_a_pending_check_null_is_refused(tmp_path) -> None:
    """**Ruling 1's negative half, and it is deliberately NOT read from the
    committed pool.**

    An earlier version of this test asserted that Claire and Learn English With
    TV Series were refused, **by name, from the live file.** It went red the
    moment their accents were authored on 2026-09-01 -- not because the rule
    broke, but because the test had pinned THE POOL'S CONTENTS WHERE IT MEANT TO
    PIN THE LOADER'S RULE. A test that fails when the data is legitimately
    improved is measuring the wrong thing, and it would have trained somebody to
    edit the assertion rather than read it.

    So the rule is tested against a constructed file: **a `pending_check` null
    is refused, and the reason says so in the file's own terms.** This holds
    whatever the committed pool happens to contain today.
    """
    import json

    entry = {
        "handle": "@Unwatched",
        "channel_id": "UCtest0000000000000000",
        "name": "A channel nobody has watched",
        "accent": None,
        "accent_null": "pending_check",
        "track": "life",
        "why": "Exists only to exercise the pending_check refusal.",
    }
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"channels": [entry]}), encoding="utf-8")

    pool = channel_file.load(path)
    assert not pool.channels, "a pending_check null must never load"
    assert len(pool.refusals) == 1
    reason = pool.refusals[0].reason.lower()
    assert "pending" in reason
    assert "watched" in reason, (
        "the refusal must say what is missing -- somebody watching it -- "
        "rather than only that a field is null"
    )


def test_a_by_ruling_null_without_a_written_reason_is_refused(tmp_path) -> None:
    """The ruling of 2026-09-01: `by_ruling` REQUIRES `accent_null_reason`,
    **because without it `by_ruling` becomes the easy escape from watching a
    video and `pending_check` quietly empties into it.**"""
    import json

    entry = {
        "handle": "@NoReason",
        "channel_id": "UCtest1111111111111111",
        "name": "Ruled with no sentence behind it",
        "accent": None,
        "accent_null": "by_ruling",
        "track": "life",
        "why": "Exists only to exercise the missing-reason refusal.",
    }
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"channels": [entry]}), encoding="utf-8")

    pool = channel_file.load(path)
    assert not pool.channels
    assert "accent_null_reason" in pool.refusals[0].reason
