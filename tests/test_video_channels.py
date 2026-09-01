"""W12b: the channel pool loads, and refuses what it cannot verify.

THE THREE QUESTIONS, asked of every fixture in this file (W12a's finding: the
tests build the world the code assumes, not the world a learner arrives in):

1. WHAT DOES THIS FIXTURE SUPPLY THAT PRODUCTION DOES NOT?
   For the first four tests: **NOTHING.** They read the real, committed
   `data/video_channels.json` through the real loader. That is deliberate and it
   is the point -- a pool file that has drifted out of the accent vocabulary, or
   that ships a handle where an id belongs, is caught by the suite rather than
   by a refresh run that quietly polls nothing.
   The constructed files appear only where a defect must be provoked that the
   committed file must never contain.

2. DOES THE PRODUCTION CALLER SUPPLY IT?
   `core.video.channels.load()` with no argument, called by `refresh.main()` and
   `resolve_channels.main()`. The `path` parameter exists for question 1's sake
   and defaults to the file production reads.

3. DOES THE ASSERTION NAME THE THING, OR COUNT IT?
   It names it. Every failure message carries the offending handle and value,
   because a count could not see the wrong twelve in W11.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.video.channels import (
    ACCENTS,
    TRACKS,
    ChannelFileError,
    load,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = REPO_ROOT / "data" / "video_channels.json"


def write(tmp_path: Path, channels: list[dict]) -> Path:
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({"channels": channels}), encoding="utf-8")
    return path


def good(**overrides) -> dict:
    entry = {
        "handle": "@probe",
        "channel_id": "UCprobeprobeprobeprobe00",
        "name": "Probe",
        "accent": "british",
        "track": "life",
        "why": "a fixture",
    }
    entry.update(overrides)
    return entry


# ── the committed pool itself ───────────────────────────────────────────────


def test_the_committed_pool_parses() -> None:
    """The real file, through the real loader. No fixture at all."""
    pool = load()
    assert pool.channels or pool.refusals, "the committed pool is empty"


def test_every_loaded_channel_declares_an_accent_and_a_track() -> None:
    """Names the offending handle rather than asserting a count.

    **WIDENED FOR MIGRATION 020, AND WIDENED PRECISELY RATHER THAN RELAXED.**
    This read `c.accent not in ACCENTS`, which was the pre-020 invariant: every
    loaded channel had one of two accents. A `by_ruling` null is now loadable --
    TED-Ed has many narrators and no per-channel value can be true -- so the
    invariant becomes *a real accent, or a null the loader has already
    established is `by_ruling`*.

    **What is NOT relaxed: a null still has to have got past `_refuse`**, which
    requires `accent_null: "by_ruling"` and a written `accent_null_reason`. So
    this still fails on a third accent, on a misspelt one, and on any null that
    reached the pool without a ruling behind it.
    """
    pool = load()
    wrong = [
        f"{c.handle}: accent={c.accent!r} track={c.track!r}"
        for c in pool.channels
        if (c.accent is not None and c.accent not in ACCENTS)
        or c.track not in TRACKS
    ]
    assert wrong == [], "channels with a bad accent or track: " + "; ".join(wrong)


def test_a_loaded_null_accent_is_by_ruling_and_carries_its_reason() -> None:
    """The other half of the widening above, so the pair is exhaustive.

    A null that loads must be `by_ruling` **with a written reason** -- the
    ruling of 2026-09-01, whose stated purpose is that without it `by_ruling`
    becomes the easy escape from watching a video and `pending_check` quietly
    empties into it.
    """
    import json
    from pathlib import Path

    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "video_channels.json")
        .read_text(encoding="utf-8")
    )
    by_handle = {e["handle"]: e for e in raw["channels"]}

    for channel in load().channels:
        if channel.accent is not None:
            continue
        entry = by_handle[channel.handle]
        assert entry.get("accent_null") == "by_ruling", (
            f"{channel.handle} loaded with a null accent that is not by_ruling"
        )
        assert str(entry.get("accent_null_reason") or "").strip(), (
            f"{channel.handle} is by_ruling with no written reason"
        )


def test_track_tags_use_the_track_weights_vocabulary() -> None:
    """`life | curiosity | work`, the literal set from migration 012.

    Written out here rather than imported from the module under test: an
    expectation derived from the code it checks would agree with any change to
    it (CLAUDE.md §3 rule 5).
    """
    assert TRACKS == {"life", "curiosity", "work"}


def test_accent_is_one_of_exactly_two_values() -> None:
    """Two, by operator ruling. Hardcoded, not read back from the module."""
    assert ACCENTS == {"american", "british"}


def test_no_loaded_channel_id_is_a_handle() -> None:
    """A handle where an id belongs polls nothing and reports no error."""
    pool = load()
    handles = [c.handle for c in pool.channels if c.channel_id.startswith("@")]
    assert handles == [], f"channel_id is a handle for: {handles}"


def test_the_committed_pool_names_every_entry_it_refuses() -> None:
    """A refusal must identify itself: a refused channel is not a smaller pool.

    Every entry of the committed file is either usable or refused BY NAME --
    nothing is dropped on the floor.
    """
    raw = json.loads(COMMITTED.read_text(encoding="utf-8"))
    pool = load()
    assert len(pool.channels) + len(pool.refusals) == len(raw["channels"])
    for refusal in pool.refusals:
        assert refusal.handle.startswith("@"), refusal
        assert refusal.reason.strip(), f"{refusal.handle} refused with no reason"


# ── refusals, each provoked by a file the committed one must never be ────────


def test_a_null_channel_id_is_refused_and_not_defaulted(tmp_path: Path) -> None:
    pool = load(write(tmp_path, [good(channel_id=None)]))
    assert pool.channels == ()
    assert "channel_id is null" in pool.refusals[0].reason


def test_a_handle_in_the_id_field_is_refused(tmp_path: Path) -> None:
    """The mistake that survives review: a handle looks enough like an id."""
    pool = load(write(tmp_path, [good(channel_id="@EnglishwithLucy")]))
    assert pool.channels == ()
    assert "not a channel id" in pool.refusals[0].reason


def test_a_null_accent_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    pool = load(write(tmp_path, [good(accent=None)]))
    assert pool.channels == ()
    assert "accent is null" in pool.refusals[0].reason


def test_a_third_accent_is_refused_until_the_check_constraint_moves(
    tmp_path: Path,
) -> None:
    """Naming the value, so the message tells the author what to change."""
    pool = load(write(tmp_path, [good(accent="australian")]))
    assert pool.channels == ()
    assert "australian" in pool.refusals[0].reason


def test_a_track_outside_track_weights_is_refused(tmp_path: Path) -> None:
    pool = load(write(tmp_path, [good(track="hobbies")]))
    assert "hobbies" in pool.refusals[0].reason


def test_a_duplicate_channel_id_is_refused_and_names_the_first_holder(
    tmp_path: Path,
) -> None:
    """Two entries for one channel would double that channel's weight."""
    pool = load(
        write(
            tmp_path,
            [good(handle="@first"), good(handle="@second")],
        )
    )
    assert [c.handle for c in pool.channels] == ["@first"]
    assert "@first" in pool.refusals[0].reason


def test_a_channel_with_no_reason_to_be_in_the_pool_is_refused(
    tmp_path: Path,
) -> None:
    pool = load(write(tmp_path, [good(why="  ")]))
    assert "why is empty" in pool.refusals[0].reason


def test_one_bad_entry_does_not_cost_the_good_ones(tmp_path: Path) -> None:
    """Named, and the run continues -- the refresh path's whole failure model."""
    pool = load(
        write(
            tmp_path,
            [
                good(handle="@ok", channel_id="UCok0000000000000000000"),
                good(handle="@bad", channel_id=None),
            ],
        )
    )
    assert [c.handle for c in pool.channels] == ["@ok"]
    assert [r.handle for r in pool.refusals] == ["@bad"]


# ── the file itself ─────────────────────────────────────────────────────────


def test_a_missing_pool_file_is_an_error_not_an_empty_pool(tmp_path: Path) -> None:
    """An empty pool and an absent pool are different facts.

    Returning `Pool((), ())` for a missing file would let `refresh` report "no
    usable channel" when the real problem is that the file was never deployed.
    """
    with pytest.raises(ChannelFileError):
        load(tmp_path / "does-not-exist.json")


def test_malformed_json_is_an_error_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "channels.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ChannelFileError) as exc:
        load(path)
    assert str(path) in str(exc.value)
