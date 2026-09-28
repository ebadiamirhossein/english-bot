"""W32f — the bottom nav's **Watch**: today's video, reachable any day, never a new one.

**The user action:** a learner taps *Watch* in the menu (operator ruling,
2026-09-28 — the nav gains Watch and Words). `/watch` then asks
`GET /keep-going/watch` for **today's assigned video** — Sunday's included
(R3) — and plays it in block 2's player.

**WHY A GET, AND NOT W24e's POST.** `POST /keep-going/watch` is keep going's
*watch another*: on a weekday it reopens only today's EXTRA, and with none it
**assigns** one (one a day, migration 034). Pointed at from the nav, a tap on
Tuesday morning — before the session, whose block 2 is today's daily video —
would spend the day's one extra and never show the daily. The nav's Watch is
therefore a read: the daily (open first), else the day's extra, and **nothing
is ever written**. It is not a library (PRD §7.4, R2 unchanged): one video,
or a calm *nothing today*.

Service tests take a fixed ``now`` (CLAUDE.md §3 rule 6); the route test pins
the router's clock the same way.

**RED BEFORE THE CODE (2026-09-28):** `keep_going.today_watch` did not exist
and `GET /keep-going/watch` answered 405.
"""

from __future__ import annotations

from datetime import date

from apps.api.deps import SESSION_COOKIE_SECURE
from core.services import keep_going
from core.services import video as video_svc
from tests.test_keep_going import (  # noqa: F401 -- fixtures, by name
    SUNDAY,
    TUESDAY,
    _in_band_video,
    _request,
    app,
    auth_env,
    db,
    empty_pool,
    learner,
)

TUESDAY_LOCAL = date(2026, 9, 29)
SUNDAY_LOCAL = date(2026, 10, 4)


def _assignments(db, learner) -> list[tuple[str, int]]:
    return db.execute(
        "SELECT kind, video_id FROM video_assignments WHERE user_id = %s ORDER BY id",
        (learner.user_id,),
    ).fetchall()


def _assign(db, learner, video: int, on: date, kind: str = "daily") -> None:
    video_svc.assign_video(db, user_id=learner.user_id, video_id=video,
                           assigned_for=on, score_breakdown={}, kind=kind)
    db.commit()


def _complete(db, learner, kind: str) -> None:
    db.execute("UPDATE video_assignments SET completed_at = now()"
               " WHERE user_id = %s AND kind = %s", (learner.user_id, kind))
    db.commit()


def test_a_weekday_opens_todays_daily_video_and_assigns_nothing(db, learner) -> None:
    """Tuesday, before the session: the nav's Watch is block 2's own video —
    not an extra, which POST would have assigned."""
    daily = _in_band_video(db, "w24ekg0101")
    _assign(db, learner, daily, TUESDAY_LOCAL)
    found = keep_going.today_watch(learner.user_id, now=TUESDAY)
    assert found is not None
    assert found.video["video_id"] == daily
    assert found.l1_language == "fa"
    assert _assignments(db, learner) == [("daily", daily)]


def test_sunday_opens_sundays_own_video(db, learner) -> None:
    """R3: Sunday's video is reachable from the nav too."""
    daily = _in_band_video(db, "w24ekg0102")
    _assign(db, learner, daily, SUNDAY_LOCAL)
    assert keep_going.today_watch(learner.user_id, now=SUNDAY).video["video_id"] == daily


def test_an_open_extra_comes_before_a_finished_daily(db, learner) -> None:
    daily = _in_band_video(db, "w24ekg0103")
    extra = _in_band_video(db, "w24ekg0104")
    _assign(db, learner, daily, TUESDAY_LOCAL)
    _assign(db, learner, extra, TUESDAY_LOCAL, kind="extra")
    assert keep_going.today_watch(learner.user_id, now=TUESDAY).video["video_id"] == daily
    _complete(db, learner, "daily")
    assert keep_going.today_watch(learner.user_id, now=TUESDAY).video["video_id"] == extra


def test_a_finished_daily_is_still_todays_video(db, learner) -> None:
    """Watched already: it can be watched again. Never a new one."""
    daily = _in_band_video(db, "w24ekg0105")
    _assign(db, learner, daily, TUESDAY_LOCAL)
    _complete(db, learner, "daily")
    found = keep_going.today_watch(learner.user_id, now=TUESDAY)
    assert found is not None and found.video["video_id"] == daily
    assert found.video["completed"] is True
    assert _assignments(db, learner) == [("daily", daily)]


def test_yesterdays_video_is_not_todays(db, learner) -> None:
    daily = _in_band_video(db, "w24ekg0106")
    _assign(db, learner, daily, date(2026, 9, 28))
    assert keep_going.today_watch(learner.user_id, now=TUESDAY) is None


def test_nothing_assigned_is_none_even_with_a_candidate_in_the_pool(db, learner, monkeypatch) -> None:
    """A candidate that POST would assign as an extra: the nav's read never ranks."""
    from core.video import assign

    monkeypatch.setattr(assign, "rank_for", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the nav's Watch ranked the pool")))
    monkeypatch.setattr(assign, "assign_day", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the nav's Watch assigned a video")))
    assert keep_going.today_watch(learner.user_id, now=TUESDAY) is None
    assert _assignments(db, learner) == []


def test_an_unknown_learner_is_none() -> None:
    assert keep_going.today_watch(-1, now=TUESDAY) is None


# ── the route, through the ASGI transport (CLAUDE.md §3 rule 1) ─────────────


def test_the_get_needs_a_session(app) -> None:
    assert _request(app, "GET", "/keep-going/watch").status_code == 401


def test_the_get_answers_todays_video_in_the_players_shape(app, db, learner) -> None:
    daily = _in_band_video(db, "w24ekg0107")
    _assign(db, learner, daily, TUESDAY_LOCAL)
    response = _request(app, "GET", "/keep-going/watch",
                        cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["l1_language"] == "fa"
    assert body["video"]["video_id"] == daily
    # The player's payload, the same producer as block 2 and POST (#190).
    assert {"youtube_id", "lines", "lines_timed", "resume_position_s", "completed"} <= set(body["video"])
    assert _assignments(db, learner) == [("daily", daily)]


def test_nothing_today_is_a_404_and_writes_nothing(app, db, learner) -> None:
    response = _request(app, "GET", "/keep-going/watch",
                        cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 404
    assert response.json() == {"detail": "nothing_today"}
    assert _assignments(db, learner) == []
