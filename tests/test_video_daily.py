"""W24d — a video every day, **daily when available: never a repeat, never below band.**

**The user action:** a learner opening Tuesday's session and finding a video in
block 2 — which, before W24d, could only ever happen on a Monday, Wednesday or
Friday (`WEEKDAYS = (0, 2, 4)`). Operator decision 2 of 2026-09-27 and R3
(Sunday too).

Everything that touches Postgres runs on a connection this module opens and
rolls back; nothing reads the wall clock (CLAUDE.md §3 rule 6) — `NOW` and the
dates are fixed. Rankings are built from `core.video.score.rank` over
hand-written `Candidate`s where the test is about the choice, and injected
where the test is about the write, so no test here needs a transcript that
happens to land at 93–98% for a fixture learner.

**RED BEFORE THE CODE (2026-09-27):** `week_dates` returned three dates, and
`assign_day`, `choose` and `assign_today_for_all` did not exist — every test
here failed on the old `core.video.assign`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services import video as svc
from core.video import assign
from core.video.score import Candidate, rank

TEST_USER = -1_224_004
NOW = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)  # Tuesday, 06:00 in Vilnius
TUESDAY = date(2026, 9, 29)


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def user(conn) -> int:
    return conn.execute(
        "INSERT INTO users (telegram_user_id, name, native_language, onboarded) "
        "VALUES (%s, 'W24d fixture', 'fa', TRUE) RETURNING id",
        (TEST_USER,),
    ).fetchone()[0]


def _video(conn, youtube_id: str) -> int:
    return svc.upsert_video(
        conn, youtube_id=youtube_id, channel_id="UCw24d000000000000000000",
        accent="british", track="life", title="W24d probe", duration_s=300,
        published_at=NOW, now=NOW,
    )


def _candidate(video_id: int, youtube_id: str, *, coverage: float = 0.955,
               seen: bool = False) -> Candidate:
    return Candidate(
        video_id=video_id, youtube_id=youtube_id, track="life", accent="british",
        duration_s=300, coverage=coverage, proper_nouns_detected=True, seen=seen,
    )


def _ranked(*candidates: Candidate):
    return rank(candidates, track_weights={"life": 50, "curiosity": 30, "work": 20},
                accent_exposure={}, targets=frozenset())


# ── the cadence ─────────────────────────────────────────────────────────────


def test_every_day_of_the_week_is_a_video_day() -> None:
    """Seven dates, Monday to Sunday, hardcoded (§3 rule 5). R3: Sunday too."""
    assert assign.week_dates(date(2026, 9, 30)) == [
        date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1),
        date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4),
    ]


# ── the choice: never a repeat, never below band ───────────────────────────


def test_a_seen_video_is_never_chosen_even_when_it_scores_best() -> None:
    """`seen` is the only difference between the two, and the seen one has the
    better coverage fit — it must still lose."""
    scored = _ranked(_candidate(1, "seen000001", coverage=0.955, seen=True),
                     _candidate(2, "fresh00002", coverage=0.935))
    assert [s.candidate.video_id for s in assign.choose(scored, 1)] == [2]


def test_nothing_below_or_above_the_band_is_chosen() -> None:
    scored = _ranked(_candidate(1, "low0000001", coverage=0.90),
                     _candidate(2, "high000002", coverage=0.99))
    assert assign.choose(scored, 1) == []


def test_choose_returns_fewer_than_asked_rather_than_repeating() -> None:
    """Daily when available: two dates open, one video in band — one chosen."""
    scored = _ranked(_candidate(1, "only000001"), _candidate(2, "seen000002", seen=True))
    assert [s.candidate.video_id for s in assign.choose(scored, 2)] == [1]


# ── the write ───────────────────────────────────────────────────────────────


def test_a_tuesday_gets_a_daily_video(conn, user) -> None:
    video = _video(conn, "w24dtue001")
    chosen = assign.assign_day(conn, user, TUESDAY, ranked=_ranked(_candidate(video, "w24dtue001")))
    assert chosen is not None and chosen.candidate.video_id == video
    today = svc.today_for(conn, user, on=TUESDAY)
    assert today is not None and today.video_id == video


def test_no_video_in_band_writes_nothing(conn, user) -> None:
    video = _video(conn, "w24dlow001")
    assert assign.assign_day(
        conn, user, TUESDAY, ranked=_ranked(_candidate(video, "w24dlow001", coverage=0.80))
    ) is None
    assert svc.today_for(conn, user, on=TUESDAY) is None


def test_a_date_that_has_its_video_is_left_alone(conn, user) -> None:
    first, second = _video(conn, "w24dday001"), _video(conn, "w24dday002")
    assign.assign_day(conn, user, TUESDAY, ranked=_ranked(_candidate(first, "w24dday001")))
    assert assign.assign_day(
        conn, user, TUESDAY, ranked=_ranked(_candidate(second, "w24dday002"))
    ) is None
    assert svc.today_for(conn, user, on=TUESDAY).video_id == first


def test_an_extra_is_not_the_days_video(conn, user) -> None:
    """Block 2 reads the `daily` row only; W24e's extra sits beside it."""
    daily, extra = _video(conn, "w24dkind01"), _video(conn, "w24dkind02")
    assign.assign_day(conn, user, TUESDAY, ranked=_ranked(_candidate(daily, "w24dkind01")))
    assign.assign_day(conn, user, TUESDAY, kind="extra",
                      ranked=_ranked(_candidate(extra, "w24dkind02")))
    assert svc.today_for(conn, user, on=TUESDAY).video_id == daily
    assert svc.today_for(conn, user, on=TUESDAY, kind="extra").video_id == extra


def test_an_assigned_extra_is_seen_for_every_later_day(conn, user) -> None:
    """An extra is as *seen* as a daily one: `seen_video_ids` reads every kind."""
    extra = _video(conn, "w24dseen01")
    assign.assign_day(conn, user, TUESDAY, kind="extra",
                      ranked=_ranked(_candidate(extra, "w24dseen01")))
    assert extra in svc.seen_video_ids(conn, user)


# ── the worker's pass ───────────────────────────────────────────────────────


def test_the_pass_assigns_each_learners_local_today(monkeypatch) -> None:
    """The date is the LEARNER's: 2026-09-28 23:30 UTC is already Tuesday in
    Vilnius (UTC+3) and still Monday in New York."""
    calls: list[tuple[int, date]] = []
    monkeypatch.setattr(assign, "_learners", lambda: [(7, "Europe/Vilnius"), (8, "America/New_York")])
    monkeypatch.setattr(assign, "_assign_one", lambda user_id, on: calls.append((user_id, on)) or "assigned")
    assign.assign_today_for_all(datetime(2026, 9, 28, 23, 30, tzinfo=timezone.utc))
    assert calls == [(7, date(2026, 9, 29)), (8, date(2026, 9, 28))]


def test_one_learner_failing_does_not_stop_the_others(monkeypatch) -> None:
    calls: list[int] = []

    def _one(user_id, on):
        calls.append(user_id)
        if user_id == 7:
            raise RuntimeError("boom")
        return "none_in_band"

    monkeypatch.setattr(assign, "_learners", lambda: [(7, "Europe/Vilnius"), (8, "Europe/Vilnius")])
    monkeypatch.setattr(assign, "_assign_one", _one)
    report = assign.assign_today_for_all(NOW)
    assert calls == [7, 8]
    assert report == {"assigned": 0, "none_in_band": 1, "already": 0, "failed": 1}


# ── what block 2 says on a day with no video ────────────────────────────────


def test_the_empty_video_line_promises_no_weekday() -> None:
    """**W24d, RED BEFORE THE COPY CHANGED:** the line read *"No video today.
    There'll be one on Monday, Wednesday and Friday."* — false from W24d on, and
    under daily-when-available no day can be promised at all. Read from the
    shipped source (`apps/web/components/session/copy.ts`), the `input` block's
    `empty` string, escapes decoded."""
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "apps/web/components/session/copy.ts").read_text(encoding="utf-8")
    block = src[src.index("  input: {"):]
    line = re.search(r'empty:\s*"([^"]*)"', block).group(1)
    line = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), line)
    assert line.startswith("No video today")
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday", "tomorrow"):
        assert day not in line, line
