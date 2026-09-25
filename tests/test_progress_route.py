"""W19: `GET /progress`, through the real ASGI transport, against the dev database.

CLAUDE.md §3 rule 1: every wire assertion goes through `httpx.ASGITransport`
into `create_app()`. The date-sensitive assertions (the six-month window, the
streak's today) call `progress_summary` with an injected `now`, because the
route reads the clock and a test must not (§3 rule 6); both paths run the same
service.

**THE ACCEPTANCE LINE THIS FILE EXISTS FOR:** *XP for a spoken sentence exceeds
XP for a tapped MCQ.* Asserted across two learners on hardcoded numbers (10 and
2, PRD §9's), never on a value derived from `XP_WEIGHTS` (§3 rule 5).

**RED DEMONSTRATIONS (2026-09-25):**
* `test_a_spoken_sentence_earns_more_than_a_tapped_mcq` — red with
  `XP_WEIGHTS["spoken"]` set to 2 (`assert 2 == 10`).
* `test_every_act_is_weighted_by_the_effort_the_ledger_evidences` — red with the
  `graded_by == "self"` downgrade removed (a self-marked speak item earned 10;
  total 58 ≠ 50), and separately with the `is_english` filter removed from the
  writing count (62 ≠ 50).
* `test_xp_never_goes_down_on_screen` — red with the service returning
  `computed_xp` instead of `shown_xp` (`0 == 2`).
* `test_the_known_word_count_is_evidenced_only` — red with the `source <>
  'assumption'` clause removed from `evidenced_known_count` (3 ≠ 2).
* `test_the_line_is_the_count_history_inside_six_months` — red with
  `HISTORY_DAYS` set to 400 (the 200-day-old point appeared).
* `test_practising_today_moves_the_streak_today` — red with `_streak_days`
  returning the stored streak alone (`4 == 5`).
* `test_two_learners_see_their_own_numbers` — red with `xp_counts`'s item query
  missing its `WHERE a.user_id` (every learner's attempts counted: `16 == 12`).
* `test_the_payload_carries_no_backlog_and_no_unmet_field` — red with a
  `missed_days: int = 0` field added to `ProgressOut`.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import date, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.services import progress as progress_svc
from tests.support import progress_seed as seed
from tests.test_session_route import BACKLOG_KEYS

TODAY = date(2026, 3, 12)
NOW = seed.at(TODAY, 18).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learners(db):
    made: list = []
    videos: list[int] = []

    def _make(label: str = "W19 progress", native_language: str = "lt"):
        learner = seed.make_learner(db, label, native_language=native_language)
        made.append(learner)
        return learner

    _make.videos = videos
    yield _make
    for learner in made:
        seed.drop_learner(db, learner.user_id)
    seed.drop_videos(db, videos)


def request(app, method, path, *, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(method, path)

    return asyncio.run(_go())


def _get(app, learner) -> dict:
    response = request(app, "GET", "/progress", cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 200, response.text
    return response.json()


def _lexemes(db, n: int) -> list[int]:
    rows = db.execute("SELECT id FROM lexemes ORDER BY id LIMIT %s", (n,)).fetchall()
    assert len(rows) == n, "the lexicon seed is required — run core.lexicon.seed"
    return [int(r[0]) for r in rows]


# ── the route ───────────────────────────────────────────────────────────────


def test_progress_requires_a_session(app) -> None:
    assert request(app, "GET", "/progress").status_code == 401


def test_the_payload_carries_no_backlog_and_no_unmet_field(app, learners) -> None:
    """User action: the learner taps the Progress tab.

    The key set is exact. **Every field it refuses is a number with nothing
    behind it, or a count of what was not done**: the radar and placement
    history (W18), the target line (no baseline), units mastered (#135), the
    couple leaderboard (scope ruling), and `sessions.xp`/`minutes`/`completed`
    (#349).
    """
    learner = learners()
    response = request(
        app, "GET", "/progress", cookies={SESSION_COOKIE_SECURE: learner.cookie}
    )
    body = response.json()
    assert set(body) == {
        "known_words",
        "known_history",
        "xp",
        "streak_days",
        "freezes",
        "units_passed",
    }
    text = response.text.lower()
    for key in BACKLOG_KEYS:
        assert key not in text, key
    for absent in (
        "radar", "placement", "target", "mastered", "partner", "leader", "rank",
        "minutes", "completed", "missed", "remaining", "behind", "lost",
    ):
        assert absent not in text, absent


def test_a_new_learner_reads_zeros_and_one_point(app, learners) -> None:
    """Week one: every number is an honest zero on the wire; the screen draws none."""
    body = _get(app, learners())
    assert body["known_words"] == 0
    assert body["xp"] == 0
    assert body["streak_days"] == 0
    assert body["freezes"] == 2  # `streaks.freeze_tokens` defaults to 2 (001)
    assert body["units_passed"] == 0
    assert len(body["known_history"]) == 1
    assert body["known_history"][0]["known_words"] == 0


def test_a_spoken_sentence_earns_more_than_a_tapped_mcq(app, db, learners) -> None:
    """THE ROW'S ACCEPTANCE: *XP for a spoken sentence exceeds XP for a tapped MCQ.*

    Two learners: one speaks one sentence in a talk (a voice turn, evidenced by
    its transcription), the other taps one MCQ.
    """
    speaker, tapper = learners("W19 speaker"), learners("W19 tapper")
    seed.turns(db, speaker.user_id, TODAY, voice=1)
    seed.attempt(db, tapper.user_id, "mcq", seed.at(TODAY, 9))

    spoken, tapped = _get(app, speaker)["xp"], _get(app, tapper)["xp"]
    assert spoken == 10
    assert tapped == 2
    assert spoken > tapped


def test_every_act_is_weighted_by_the_effort_the_ledger_evidences(app, db, learners) -> None:
    """One of each act, and the total hand-summed from PRD §9's scale.

        voice turn                       10
        typed turn                        6
        l1_to_l2_production (typed)       6
        mcq (tap)                         2
        speak_repeat, self-marked         2   — the ledger holds a tap, not speech
        card, typed answer                6
        card, button grade                2
        English journal entry            12
        Farsi journal entry               0   — not the learner's English
        video watched to the end          4
        video assigned, not finished      0
                                        ---
                                         50
    """
    learner = learners()
    uid = learner.user_id
    seed.turns(db, uid, TODAY, voice=1, typed=1)
    seed.attempt(db, uid, "l1_to_l2_production", seed.at(TODAY, 9))
    seed.attempt(db, uid, "mcq", seed.at(TODAY, 9))
    seed.attempt(db, uid, "speak_repeat", seed.at(TODAY, 9))
    seed.review(db, uid, seed.at(TODAY, 9), typed="went")
    seed.review(db, uid, seed.at(TODAY, 9))
    seed.written(db, uid, TODAY, is_english=True)
    seed.written(db, uid, TODAY, is_english=False)
    learners.videos.append(seed.watched(db, uid, TODAY, seed.at(TODAY, 20)))
    learners.videos.append(seed.watched(db, uid, TODAY - timedelta(days=1), None))

    assert _get(app, learner)["xp"] == 50


def test_xp_never_goes_down_on_screen(app, db, learners) -> None:
    """A fixture purge deletes items and their attempts cascade — correct, and
    it lowers the COMPUTED total. The screen keeps the mark."""
    learner = learners()
    item_id = seed.attempt(db, learner.user_id, "mcq", seed.at(TODAY, 9))
    assert _get(app, learner)["xp"] == 2

    db.execute("DELETE FROM items WHERE id = %s", (item_id,))
    db.commit()
    # Positive control: the ledger really did lose the act.
    assert db.execute(
        "SELECT count(*) FROM item_attempts WHERE user_id = %s", (learner.user_id,)
    ).fetchone()[0] == 0

    assert _get(app, learner)["xp"] == 2


def test_the_known_word_count_is_evidenced_only(app, db, learners) -> None:
    """W4's ruling: the floor (`assumption`) never inflates *words you know*."""
    learner = learners()
    a, b, c, d = _lexemes(db, 4)
    for lexeme_id, state, source, rank in (
        (a, "known", "review", 5),
        (b, "mastered", "tapped", 2),
        (c, "known", "assumption", 0),
        (d, "learning", "review", 5),
    ):
        db.execute(
            "INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank) "
            "VALUES (%s, %s, %s, %s, %s)",
            (learner.user_id, lexeme_id, state, source, rank),
        )
    db.commit()
    body = _get(app, learner)
    assert body["known_words"] == 2
    assert body["known_history"][-1]["known_words"] == 2


def test_units_passed_counts_the_ledger(app, db, learners) -> None:
    learner = learners()
    db.execute(
        """
        INSERT INTO user_unit_state
            (user_id, unit_number, state, entered_at, passed_at, last_checkpoint_score)
        VALUES (%s, 1, 'passed', now() - interval '4 days', now(), 92)
        """,
        (learner.user_id,),
    )
    db.execute(
        "INSERT INTO user_unit_state (user_id, unit_number, state, entered_at) "
        "VALUES (%s, 2, 'in_progress', now())",
        (learner.user_id,),
    )
    db.commit()
    assert _get(app, learner)["units_passed"] == 1


def test_two_learners_see_their_own_numbers(app, db, learners) -> None:
    """The two learners' ledgers differ, and so do their screens."""
    farsi, lithuanian = learners("W19 fa", "fa"), learners("W19 lt", "lt")
    seed.written(db, farsi.user_id, TODAY)
    seed.attempt(db, lithuanian.user_id, "mcq", seed.at(TODAY, 9))
    seed.attempt(db, lithuanian.user_id, "mcq", seed.at(TODAY, 10))
    assert _get(app, farsi)["xp"] == 12
    assert _get(app, lithuanian)["xp"] == 4


def test_a_second_read_the_same_day_keeps_one_point(app, db, learners) -> None:
    learner = learners()
    _get(app, learner)
    _get(app, learner)
    assert db.execute(
        "SELECT count(*) FROM progress_snapshots WHERE user_id = %s", (learner.user_id,)
    ).fetchone()[0] == 1


# ── the service, with the clock injected ────────────────────────────────────


def test_the_line_is_the_count_history_inside_six_months(db, learners) -> None:
    """Points are what the screen read on those days, ascending, and a point
    older than six months is outside the line."""
    learner = learners()
    for days_ago, known in ((200, 1), (40, 3), (1, 5)):
        db.execute(
            "INSERT INTO progress_snapshots (user_id, local_date, known_words, xp) "
            "VALUES (%s, %s, %s, 0)",
            (learner.user_id, TODAY - timedelta(days=days_ago), known),
        )
    db.commit()
    summary = progress_svc.progress_summary(learner.user_id, now=NOW)
    assert summary is not None
    assert [(p.local_date, p.known_words) for p in summary.known_history] == [
        (date(2026, 1, 31), 3),
        (date(2026, 3, 11), 5),
        (TODAY, 0),
    ]


def test_practising_today_moves_the_streak_today(db, learners) -> None:
    """The rollover evaluates yesterday at 03:00 today; practice today is added
    now, not tomorrow. An unpractised unevaluated day subtracts nothing."""
    learner = learners()
    db.execute(
        "UPDATE streaks SET current_streak = 4, last_evaluated_date = %s WHERE user_id = %s",
        (TODAY - timedelta(days=2), learner.user_id),
    )
    db.commit()
    summary = progress_svc.progress_summary(learner.user_id, now=NOW)
    assert summary is not None and summary.streak_days == 4

    seed.attempt(db, learner.user_id, "mcq", seed.at(TODAY, 9))
    summary = progress_svc.progress_summary(learner.user_id, now=NOW)
    assert summary is not None and summary.streak_days == 5
    assert summary.freezes == 2


def test_an_unknown_user_has_no_progress() -> None:
    assert progress_svc.progress_summary(-1, now=NOW) is None

