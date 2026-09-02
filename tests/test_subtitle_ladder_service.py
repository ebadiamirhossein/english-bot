"""W13a: the ladder's persistence, against a real database.

`core/video/ladder.py` decides what a check DOES; this module is the only place
that reads or writes where a learner is. **One producer (#190)** — nothing else
in the tree may write `subtitle_ladder`, and a test below holds that
structurally rather than by convention.

**THE TWO ASSERTIONS THAT MATTER MOST HERE ARE ABOUT WHAT IS *NOT* WIRED.**
`record_check` and `record_reveal` have **no production caller today**, and that
is a stated fact rather than an oversight: the comprehension check that would
call the first does not exist (it needs generation, gated on §1a) and the reveal
control that would call the second is unbuildable on R12's cue boundaries.
`test_nothing_in_the_tree_calls_the_ladder_yet` pins that, so the day someone
wires it they must delete an assertion on purpose — the alternative is a slice
quietly acquiring a caller nobody reviewed.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services import subtitle_ladder as svc
from core.video.ladder import FIRST_STEP, LadderState

#: Fixed instants. Nothing here reads the wall clock (CLAUDE.md §3 rule 6).
T0 = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=1)

YOUTUBE = "youtube_curated"
SERIES = "native_series"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w13a-svc', 'fa', %s, TRUE) RETURNING id",
        (f"w13a-svc-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


# ── the default is a fact about no row, not a row ───────────────────────────


def test_a_learner_who_has_never_been_checked_is_on_step_one(learner) -> None:
    assert svc.ladder_for(learner, track_kind=YOUTUBE) == LadderState(
        step=FIRST_STEP, passes_at_step=0
    )


def test_reading_a_ladder_writes_nothing(db, learner) -> None:
    """**A read path that writes is how a refetch becomes a state change.**

    `GET /session/today` earns its create-once write by needing the row before
    it can pace block 3; nothing needs a ladder row to exist, so nothing here
    creates one. The first INSERT is the first movement.
    """
    svc.ladder_for(learner, track_kind=YOUTUBE)
    svc.ladder_for(learner, track_kind=SERIES)
    rows = db.execute(
        "SELECT count(*) FROM subtitle_ladder WHERE user_id = %s", (learner,)
    ).fetchone()
    assert rows[0] == 0


# ── movement, round-tripped ─────────────────────────────────────────────────


def test_the_first_pass_is_stored_and_read_back(learner) -> None:
    move = svc.record_check(learner, track_kind=YOUTUBE, score_pct=85, now=T0)
    assert move.state == LadderState(step=1, passes_at_step=1)
    assert move.direction is None
    assert svc.ladder_for(learner, track_kind=YOUTUBE) == LadderState(1, 1)


def test_two_passes_promote_and_the_promotion_is_announced(learner) -> None:
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=88, now=T0)
    move = svc.record_check(learner, track_kind=YOUTUBE, score_pct=91, now=T1)
    assert move.state == LadderState(step=2, passes_at_step=0)
    assert move.direction == "up"
    assert move.announce is True
    assert svc.ladder_for(learner, track_kind=YOUTUBE) == LadderState(2, 0)


def test_a_failing_check_demotes_silently(learner) -> None:
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=90, now=T0)
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=90, now=T0)
    assert svc.ladder_for(learner, track_kind=YOUTUBE).step == 2

    move = svc.record_check(learner, track_kind=YOUTUBE, score_pct=55, now=T1)
    assert move.state == LadderState(step=1, passes_at_step=0)
    assert move.direction == "down"
    assert move.announce is False
    assert svc.ladder_for(learner, track_kind=YOUTUBE).step == 1


def test_the_two_ladders_move_independently(learner) -> None:
    """PRD §7.5's whole reason for two ladders: *"you will reach step 5 on BBC
    Learning English long before you reach it on How I Met Your Mother."*"""
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=90, now=T0)
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=90, now=T0)
    assert svc.ladder_for(learner, track_kind=YOUTUBE) == LadderState(2, 0)
    assert svc.ladder_for(learner, track_kind=SERIES) == LadderState(1, 0)


def test_entered_step_at_moves_only_when_the_step_does(db, learner) -> None:
    """A clock that restarted on every check could not tell a long step from a
    new one, which is the only thing it is for."""
    svc.record_check(learner, track_kind=YOUTUBE, score_pct=85, now=T0)
    first = db.execute(
        "SELECT entered_step_at FROM subtitle_ladder WHERE user_id = %s", (learner,)
    ).fetchone()[0]

    svc.record_check(learner, track_kind=YOUTUBE, score_pct=70, now=T1)
    unmoved = db.execute(
        "SELECT entered_step_at FROM subtitle_ladder WHERE user_id = %s", (learner,)
    ).fetchone()[0]
    assert unmoved == first, "a middling check is not an arrival"

    svc.record_check(learner, track_kind=YOUTUBE, score_pct=99, now=T1)
    moved = db.execute(
        "SELECT entered_step_at, step FROM subtitle_ladder WHERE user_id = %s",
        (learner,),
    ).fetchone()
    assert moved[1] == 2
    assert moved[0] == T1


def test_an_unknown_track_kind_is_refused_before_it_reaches_sql(learner) -> None:
    with pytest.raises(ValueError):
        svc.record_check(learner, track_kind="tiktok", score_pct=90, now=T0)


# ── reveals: events, because the number has to go down ──────────────────────


def test_a_week_with_no_reveals_counts_none(learner) -> None:
    assert svc.reveals_between(
        learner, track_kind=YOUTUBE, start=T0, end=T1
    ) == 0


def test_reveals_are_counted_inside_the_window_and_not_outside_it(learner) -> None:
    """**This is what a lifetime counter could not do.** PRD §7.5 wants a number
    that goes down over weeks, so the count is per window and the window has two
    ends — a missing lower bound turns it into a lifetime total that only grows.
    """
    svc.record_reveal(learner, track_kind=YOUTUBE, step=4, video_id=None, now=T0)
    svc.record_reveal(learner, track_kind=YOUTUBE, step=4, video_id=None, now=T0)
    svc.record_reveal(
        learner, track_kind=YOUTUBE, step=4, video_id=None,
        now=T0 - timedelta(days=8),
    )
    assert svc.reveals_between(
        learner, track_kind=YOUTUBE, start=T0 - timedelta(days=1), end=T1
    ) == 2


def test_reveals_are_counted_per_ladder(learner) -> None:
    svc.record_reveal(learner, track_kind=YOUTUBE, step=4, video_id=None, now=T0)
    assert svc.reveals_between(
        learner, track_kind=SERIES, start=T0 - timedelta(days=1), end=T1
    ) == 0


def test_the_headline_number_is_step_fours_reveals_and_not_every_reveal(
    learner,
) -> None:
    """PRD §7.5 counts step 4. **Step 3's *tap any line* is the safety net and is
    explicitly not the measure**, so a log that could not tell them apart would
    have made the honest number unrecoverable."""
    svc.record_reveal(learner, track_kind=YOUTUBE, step=3, video_id=None, now=T0)
    svc.record_reveal(learner, track_kind=YOUTUBE, step=4, video_id=None, now=T0)
    svc.record_reveal(learner, track_kind=YOUTUBE, step=4, video_id=None, now=T0)
    window = dict(track_kind=YOUTUBE, start=T0 - timedelta(days=1), end=T1)
    assert svc.reveals_between(learner, step=4, **window) == 2
    # The positive control: the step-3 reveal WAS stored, so the 2 above is a
    # filter working and not a row that never landed (#345).
    assert svc.reveals_between(learner, **window) == 3


def test_a_reveal_on_an_unknown_step_is_refused(learner) -> None:
    with pytest.raises(ValueError):
        svc.record_reveal(learner, track_kind=YOUTUBE, step=6, video_id=None, now=T0)


def test_a_reveal_on_an_unknown_track_kind_is_refused(learner) -> None:
    with pytest.raises(ValueError):
        svc.record_reveal(learner, track_kind="dvd", step=4, video_id=None, now=T0)


# ── what is deliberately not wired ──────────────────────────────────────────


def test_nothing_in_the_tree_calls_the_ladder_yet() -> None:
    """**W13a's honest half, asserted rather than written in a comment.**

    `record_check`'s caller is the comprehension check (PRD §7.3), which does not
    exist and needs generation — gated on §1a, unruled, and not before T1.
    `record_reveal`'s caller is step 3/4's reveal control, which needs line
    boundaries a generated track does not have (R12: ~92% of consecutive cue
    pairs overlap, and all three assigned videos are generated).

    **So this slice ships a rule with no trigger, and says so here.** The day a
    caller lands, this test fails and has to be deleted on purpose — which is the
    review this record has repeatedly found missing when a path acquired a caller
    quietly. **It is NOT an assertion that the ladder should stay unwired.**
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    callers: list[str] = []
    for area in ("apps", "packages"):
        for path in sorted((root / area).rglob("*.py")):
            rel = str(path.relative_to(root))
            if rel.startswith("packages/core/services/subtitle_ladder.py"):
                continue
            raw = path.read_text(encoding="utf-8")
            for name in ("record_check", "record_reveal"):
                if f"{name}(" in raw:
                    callers.append(f"{rel}: {name}")
    assert callers == [], (
        "the ladder has a caller now — delete this test deliberately and say "
        "which surface calls it: " + "; ".join(callers)
    )


def test_exactly_one_module_writes_the_ladder() -> None:
    """#190, applied to state rather than to a card face. A ladder written from
    two places is the defect this record has filed nine times."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    writers: set[str] = set()
    for area in ("apps", "packages"):
        for path in sorted((root / area).rglob("*.py")):
            raw = path.read_text(encoding="utf-8")
            if "INSERT INTO subtitle_ladder" in raw or "UPDATE subtitle_ladder" in raw:
                writers.add(str(path.relative_to(root)))
    assert writers == {"packages/core/services/subtitle_ladder.py"}, writers
