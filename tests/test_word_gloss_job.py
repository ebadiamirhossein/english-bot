"""W31c — the two billed gloss jobs, `fill_word_glosses` and `pregen_glosses`.

**Nothing here spends anything:** `core.video.explain.explain_one` — the only
function either job bills through — is replaced in process, and the
session-scoped netguard refuses any socket. **The flags are read the way they
are really set, from a `.env` file** (CLAUDE.md §3 rule 3). **The ceilings'
clock is passed in** and the rows they count are stamped with the same instant
(rule 6), so no assertion depends on today's date.

**A NEW FILE, NOT AN EDIT OF `tests/test_worker.py` OR
`tests/test_video_auto_refresh.py`:** `w22-bot-reduction` edits both, and a
test added here cannot conflict with the rebase.

**RED BEFORE THE CODE (2026-09-27):** the flags, `OPTIONAL_JOBS`, the two job
functions and `core.services.words` did not exist.
"""

from __future__ import annotations

import dataclasses
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from apps.worker import jobs as worker_jobs
from apps.worker.main import build_scheduler
from core.config import load_settings
from core.services import glosses as glosses_svc
from core.services import video as video_svc
from core.services import words as words_svc
from core.video import explain
from tests.test_backup_r2 import write_dotenv

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PREFIX = "w31cjob"


# ── the flags, from `.env` ───────────────────────────────────────────────────


@pytest.fixture
def no_flags_left_behind(monkeypatch: pytest.MonkeyPatch):
    for key in ("WORD_GLOSS_JOB", "VIDEO_PREGEN_GLOSSES"):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    yield


def test_both_flags_are_off_unless_the_env_file_sets_them(tmp_path, no_flags_left_behind) -> None:
    from core import config as config_mod

    settings = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path))
    assert (settings.word_gloss_job, settings.video_pregen_glosses) == (False, False)


def test_each_flag_is_read_from_the_env_file(tmp_path, no_flags_left_behind) -> None:
    from core import config as config_mod

    settings = config_mod.load_settings(
        dotenv_path=write_dotenv(tmp_path, WORD_GLOSS_JOB="1", VIDEO_PREGEN_GLOSSES="1")
    )
    assert (settings.word_gloss_job, settings.video_pregen_glosses) == (True, True)


# ── registration ─────────────────────────────────────────────────────────────


def _registered(**flags) -> set[str]:
    off = {"video_auto_refresh": False, "word_gloss_job": False, "video_pregen_glosses": False}
    settings = dataclasses.replace(load_settings(), **{**off, **flags})
    return {job.id for job in build_scheduler(worker_jobs.jobs_for(settings)).get_jobs()}


def test_no_billed_gloss_job_runs_without_its_flag() -> None:
    names = _registered()
    assert "fill_word_glosses" not in names and "pregen_glosses" not in names


def test_each_job_registers_with_its_own_flag_only() -> None:
    assert "fill_word_glosses" in _registered(word_gloss_job=True)
    assert "pregen_glosses" not in _registered(word_gloss_job=True)
    assert "pregen_glosses" in _registered(video_pregen_glosses=True)
    assert "fill_word_glosses" not in _registered(video_pregen_glosses=True)


def test_the_pending_job_runs_every_fifteen_minutes() -> None:
    assert worker_jobs.FILL_WORD_GLOSSES.interval_seconds == 15 * 60


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def world():
    """A learner, a video with a transcript assigned today, and cleanup."""
    telegram = -secrets.randbelow(10**9) - 1
    with psycopg.connect(load_settings().database_url) as conn:
        user = conn.execute(
            "INSERT INTO users (telegram_user_id, name, native_language, onboarded, "
            "known_word_floor, timezone) VALUES (%s, 'W31c job', 'fa', TRUE, 0, 'UTC') RETURNING id",
            (telegram,),
        ).fetchone()[0]
        # An APPROVED learner: the worker's passes read `approved_onboarded_users`.
        conn.execute(
            "INSERT INTO access_requests (telegram_user_id, user_id, display_name, status) "
            "VALUES (%s, %s, 'W31c job', 'approved')",
            (telegram, user),
        )
        video = video_svc.upsert_video(
            conn, youtube_id=f"{PREFIX}{secrets.token_hex(2)}", channel_id="UCw31cjob000000000000000",
            accent="british", track="life", title="job probe", duration_s=30,
            published_at=NOW - timedelta(days=1), now=NOW,
        )
        video_svc.record_transcript(conn, video_id=video, text="the band was loud. we left early.",
                                    lang="en", kind="manual")
        conn.commit()
    yield {"user": user, "video": video}
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute("DELETE FROM word_saves_pending WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM cards WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM video_assignments WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (f"{PREFIX}%",))
        conn.execute("DELETE FROM access_requests WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))
        conn.commit()


def _pending(world, word: str, sentence: str = "the band was loud.") -> None:
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute(
            "INSERT INTO word_saves_pending (user_id, video_id, word, context_sentence, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (world["user"], world["video"], word, sentence, NOW - timedelta(minutes=5)),
        )
        conn.commit()


def _draft(word="band", **over):
    base = dict(word=word, definition="a group of musicians", register="neutral",
                neutral_equivalent=None, who_says_this=None, l1={"fa": "گروه موسیقی"})
    base.update(over)
    return explain.Draft(**base)


@pytest.fixture
def calls(monkeypatch):
    made: list[str] = []

    def fake(word, line, *, l1=(), settings=None):
        made.append(word)
        return _draft(word)

    monkeypatch.setattr(explain, "explain_one", fake)
    return made


def _state(world, word):
    with psycopg.connect(load_settings().database_url) as conn:
        return conn.execute(
            "SELECT state, attempts, resolved_at IS NOT NULL FROM word_saves_pending "
            "WHERE user_id = %s AND word = %s", (world["user"], word),
        ).fetchone()


def _tap_glosses_today(n: int, video: int) -> None:
    with psycopg.connect(load_settings().database_url) as conn:
        for i in range(n):
            conn.execute(
                "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, "
                "model, source, generated_at) VALUES (%s, %s, 'x', 'y', 'neutral', 'm', 'tap', %s)",
                (video, f"prefill{i}", NOW),
            )
        conn.commit()


# ── the pending job ─────────────────────────────────────────────────────────


def test_a_pending_word_gets_a_meaning_and_then_its_cards(world, calls) -> None:
    _pending(world, "band")
    counts = words_svc.fill_pending(NOW)
    assert (counts.generated, counts.carded) == (1, 1)
    assert calls == ["band"]
    assert _state(world, "band") == ("carded", 0, True)
    with psycopg.connect(load_settings().database_url) as conn:
        source, l1 = conn.execute(
            "SELECT source, l1 FROM video_glosses WHERE video_id = %s AND word = 'band'",
            (world["video"],),
        ).fetchone()
        sentences = {r[0] for r in conn.execute(
            "SELECT context_sentence FROM cards WHERE user_id = %s", (world["user"],)).fetchall()}
    assert (source, l1) == ("tap", {"fa": "گروه موسیقی"})
    assert sentences == {"the band was loud."}


def test_a_word_that_gained_a_gloss_is_carded_without_a_call(world, monkeypatch) -> None:
    monkeypatch.setattr(explain, "explain_one", lambda *a, **k: pytest.fail("no call expected"))
    with psycopg.connect(load_settings().database_url) as conn:
        glosses_svc.insert_gloss(
            conn, video_id=world["video"], word="band", context_sentence="the band was loud.",
            cue_start_s=None, definition="a group of musicians", register="neutral",
            neutral_equivalent=None, who_says_this=None, model="m", source="pregen",
        )
        conn.commit()
    _pending(world, "band")
    counts = words_svc.fill_pending(NOW)
    assert (counts.generated, counts.carded) == (0, 1)


def test_three_refusals_mark_a_word_no_meaning(world, monkeypatch) -> None:
    def refuse(*a, **k):
        raise explain.GlossRejected("no")

    monkeypatch.setattr(explain, "explain_one", refuse)
    _pending(world, "band")
    for expected in ((("pending", 1, False)), ("pending", 2, False), ("no_meaning", 3, True)):
        words_svc.fill_pending(NOW)
        assert _state(world, "band") == expected


def test_one_run_makes_at_most_twenty_calls_whatever_it_is_asked(world, calls) -> None:
    for i in range(25):
        _pending(world, f"word{i}", sentence=f"word{i} is here.")
    counts = words_svc.fill_pending(NOW, limit=100)
    assert len(calls) == 20
    assert counts.skipped_ceiling == 5


def test_the_day_stops_at_sixty_tap_glosses(world, calls) -> None:
    _tap_glosses_today(60, world["video"])
    _pending(world, "band")
    counts = words_svc.fill_pending(NOW)
    assert calls == [] and counts.skipped_ceiling == 1
    assert _state(world, "band") == ("pending", 0, False)


def test_pregeneration_never_uses_up_the_taps_allowance(world, calls) -> None:
    """C2: the two ceilings are counted by source. With thirty tap glosses and
    forty pregen glosses today, taps still have thirty calls left — a shared
    count (seventy) would leave none. (Forty pregen alone could not tell the two
    apart; found by mutation.)"""
    _tap_glosses_today(30, world["video"])
    with psycopg.connect(load_settings().database_url) as conn:
        for i in range(40):
            conn.execute(
                "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, "
                "model, source, generated_at) VALUES (%s, %s, 'x', 'y', 'neutral', 'm', 'pregen', %s)",
                (world["video"], f"pre{i}", NOW),
            )
        conn.commit()
    _pending(world, "band")
    assert words_svc.fill_pending(NOW).generated == 1


# ── pre-generation ───────────────────────────────────────────────────────────


def _assign_today(world) -> None:
    from core.services.sessions import local_today

    with psycopg.connect(load_settings().database_url) as conn:
        video_svc.assign_video(conn, user_id=world["user"], video_id=world["video"],
                               assigned_for=local_today("UTC", NOW), score_breakdown={})
        conn.commit()


def test_pregeneration_explains_todays_video_and_says_pregen(world, calls) -> None:
    _assign_today(world)
    counts = words_svc.pregen_today(NOW)
    assert counts.generated == len(calls) > 0
    assert len(calls) <= words_svc.PREGEN_PER_LEARNER
    with psycopg.connect(load_settings().database_url) as conn:
        sources = {r[0] for r in conn.execute(
            "SELECT source FROM video_glosses WHERE video_id = %s", (world["video"],)).fetchall()}
    assert sources == {"pregen"}


def test_pregeneration_stops_at_forty_a_day(world, calls) -> None:
    _assign_today(world)
    with psycopg.connect(load_settings().database_url) as conn:
        for i in range(40):
            conn.execute(
                "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, "
                "model, source, generated_at) VALUES (%s, %s, 'x', 'y', 'neutral', 'm', 'pregen', %s)",
                (world["video"], f"pre{i}", NOW),
            )
        conn.commit()
    assert words_svc.pregen_today(NOW).generated == 0
    assert calls == []


def test_pregeneration_caps_each_learner_at_twenty_whatever_it_is_asked(world, calls) -> None:
    with psycopg.connect(load_settings().database_url) as conn:
        # Letter-only nonsense words: the line matcher reads `[A-Za-z']` tokens,
        # so `zqword7` would never match a line (found by mutation).
        long = " ".join(f"zq{chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(40)) + "."
        conn.execute("UPDATE videos SET transcript = %s WHERE id = %s", (long, world["video"]))
        conn.commit()
    _assign_today(world)
    words_svc.pregen_today(NOW, per_learner=100)
    assert len(calls) == 20
