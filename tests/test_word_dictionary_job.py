"""W32c — `fill_word_dictionary`, the top-up job behind `WORD_DICTIONARY_JOB`.

It fills the dictionary for videos that are assigned or newly pooled **before
anyone watches them**, so a new video's words are instant too. **BILLED**, off
by default, a daily ceiling enforced inside the function whatever the caller
passes — W31c's shape.

**A NEW FILE, NOT AN EDIT OF `tests/test_worker.py`** — `w22-bot-reduction`
edits that file, and a test added here cannot conflict with the rebase.

**Nothing spends:** the transport is mocked at `core.llm.anthropic.Anthropic`
and the netguard refuses any socket. **The flag is read the way it is really
set, from a `.env` file** (CLAUDE.md §3 rule 3). **The clock is passed in** and
the rows the ceiling counts are stamped with the same instant (rule 6).

**RED BEFORE THE CODE (2026-09-28):** no flag, no job, no `topup`.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from apps.worker import jobs as worker_jobs
from apps.worker.main import build_scheduler
from core.config import load_settings
from core.services import dictionary
from core.services import video as video_svc
from core.video import explain
from tests.test_backup_r2 import write_dotenv

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PREFIX = "w32cjob"


@pytest.fixture
def no_flag_left_behind(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORD_DICTIONARY_JOB", "")
    monkeypatch.delenv("WORD_DICTIONARY_JOB")
    yield


def test_the_flag_is_off_unless_the_env_file_sets_it(tmp_path, no_flag_left_behind) -> None:
    from core import config as config_mod

    assert config_mod.load_settings(dotenv_path=write_dotenv(tmp_path)).word_dictionary_job is False
    on = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path, WORD_DICTIONARY_JOB="1"))
    assert on.word_dictionary_job is True


def _registered(**flags) -> set[str]:
    off = {"video_auto_refresh": False, "word_gloss_job": False,
           "video_pregen_glosses": False, "word_dictionary_job": False}
    settings = dataclasses.replace(load_settings(), **{**off, **flags})
    return {job.id for job in build_scheduler(worker_jobs.jobs_for(settings)).get_jobs()}


def test_the_job_registers_with_its_flag_only() -> None:
    assert "fill_word_dictionary" not in _registered()
    assert "fill_word_dictionary" in _registered(word_dictionary_job=True)
    assert "fill_word_dictionary" not in _registered(word_gloss_job=True)


def test_the_job_is_hourly() -> None:
    assert worker_jobs.FILL_WORD_DICTIONARY.interval_seconds == 60 * 60


# ── the run ─────────────────────────────────────────────────────────────────


@pytest.fixture
def world():
    """A learner with a video assigned today whose words nothing holds."""
    telegram = -secrets.randbelow(10**9) - 1
    with psycopg.connect(load_settings().database_url) as conn:
        user = conn.execute(
            "INSERT INTO users (telegram_user_id, name, native_language, onboarded, timezone) "
            "VALUES (%s, 'W32c job', 'fa', TRUE, 'UTC') RETURNING id",
            (telegram,),
        ).fetchone()[0]
        video = video_svc.upsert_video(
            conn, youtube_id=f"{PREFIX}{secrets.token_hex(2)}", channel_id="UCw32cjob000000000000000",
            accent="british", track="life", title="top-up probe", duration_s=30,
            published_at=NOW - timedelta(days=1), now=NOW,
        )
        video_svc.record_transcript(conn, video_id=video, lang="en", kind="manual",
                                    text="zqwalpha zqwbravo zqwcharlie. zqwdelta zqwecho.")
        conn.execute(
            "INSERT INTO video_assignments (user_id, video_id, assigned_for, score_breakdown) "
            "VALUES (%s, %s, %s, '{}')",
            (user, video, NOW.date()),
        )
        conn.commit()
    yield {"user": user, "video": video}
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute("DELETE FROM word_dictionary WHERE lemma LIKE 'zqw%%'")
        conn.execute("DELETE FROM video_assignments WHERE user_id = %s", (user,))
        conn.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (f"{PREFIX}%",))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))
        conn.commit()


def _answer(**kwargs):
    body = "".join(m["content"] for m in kwargs["messages"])
    words = body.split(explain.DICT_OPEN, 1)[1].split(explain.DICT_CLOSE, 1)[0].split()
    message = MagicMock()
    block = MagicMock()
    block.text = json.dumps({"entries": [
        {"word": w, "kind": "word", "register": "neutral", "neutral_equivalent": None,
         "who_says_this": None, "senses": [{"pos": "noun", "definition": f"a {w}", "l1": {}}]}
        for w in words
    ]})
    message.content = [block]
    message.stop_reason = "end_turn"
    message.usage = MagicMock(input_tokens=900, output_tokens=200,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return message


@pytest.fixture
def transport():
    with patch("core.llm.anthropic.Anthropic") as cls, patch("core.llm.time.sleep", return_value=None):
        yield cls.return_value


def _held(words):
    with psycopg.connect(load_settings().database_url) as conn:
        return dictionary.held(conn, words)


ZQW = ["zqwalpha", "zqwbravo", "zqwcharlie", "zqwdelta", "zqwecho"]


def test_an_assigned_videos_words_are_filled_before_anyone_watches(world, transport) -> None:
    transport.messages.create.side_effect = _answer
    report = dictionary.topup(NOW, video_ids=[world["video"]])
    assert _held(ZQW) == frozenset(ZQW)
    assert (report.written, report.deferred) == (5, 0)
    with psycopg.connect(load_settings().database_url) as conn:
        sources = {r[0] for r in conn.execute(
            "SELECT source FROM word_dictionary WHERE lemma = ANY(%s)", (ZQW,)).fetchall()}
    assert sources == {"topup"}


def test_the_run_and_the_day_are_capped_whatever_the_caller_passes(world, transport) -> None:
    transport.messages.create.side_effect = _answer
    report = dictionary.topup(NOW, limit=2, video_ids=[world["video"]])
    assert report.written == 2
    report = dictionary.topup(NOW, limit=10**6, video_ids=[world["video"]])
    assert report.written <= dictionary.TOPUP_PER_RUN


def test_the_daily_ceiling_counts_todays_topup_rows(world, transport, monkeypatch) -> None:
    transport.messages.create.side_effect = _answer
    monkeypatch.setattr(dictionary, "TOPUP_PER_DAY", 3)
    dictionary.topup(NOW, video_ids=[world["video"]])
    assert len(_held(ZQW)) == 3
    report = dictionary.topup(NOW, video_ids=[world["video"]])
    assert report.written == 0 and report.at_ceiling
    assert transport.messages.create.call_count == 1  # the first run's one call, and no more


def test_a_job_never_waits_on_the_provider(world, transport) -> None:
    """C3's long waits are the operator's backfill's; an hourly job that meets
    a 529 defers its words to the next hour and returns."""
    import anthropic

    response = MagicMock()
    response.status_code = 529
    response.headers = {}
    transport.messages.create.side_effect = anthropic.APIStatusError(
        message="overloaded", response=response, body={"error": {"message": "overloaded"}}
    )
    waits: list[float] = []
    report = dictionary.topup(NOW, video_ids=[world["video"]], sleep=waits.append)
    assert waits == []
    assert report.deferred == 5 and report.written == 0


def test_the_worker_line_is_counts_only(world, transport, caplog) -> None:
    transport.messages.create.side_effect = _answer
    caplog.set_level("INFO")
    with patch.object(dictionary, "_topup_video_ids", return_value=[world["video"]]):
        worker_jobs.fill_word_dictionary()
    line = next(r.message for r in caplog.records if r.message.startswith("fill_word_dictionary ok"))
    assert "written=5" in line and "at_ceiling=False" in line
    assert "zqw" not in line, "counts only, never a word (CLAUDE.md §5)"
