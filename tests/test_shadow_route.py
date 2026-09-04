"""W14 tests 1, 2, 3, 5, 6, 10, 12, 13 — through the real ASGI transport.

**CLAUDE.md §3 rule 1: every route that writes is tested through the ASGI
transport.** In v2, 161 tests passed while the main feature was dead because
every test called handlers directly.

**MOCKED AT THE TRANSPORT (`httpx.post` inside `core.speech_api`), NEVER AT THE
SERVICE FUNCTION** — standing rule 7. So the route, the body cap, the streaming
read, `score_attempt`, the quota ledger, the WAV parse, the wrapper's retry and
status mapping, **and the parser written against P0a's recording** all execute.
Patching `score_attempt` would leave every one of those unexercised — #345's
fifth instance in W13-ii.

**THE FIXTURE IS THE REAL RECORDED RESPONSE**, `tests/fixtures/azure_pronunciation/`,
captured live on 2026-09-03. Nothing here is a hand-written guess at Azure's
shape.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import struct
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.main import create_app
from core.config import load_settings
from apps.api.deps import SESSION_COOKIE_SECURE

FIXTURES = Path(__file__).parent / "fixtures" / "azure_pronunciation"
RECORDED = json.loads((FIXTURES / "assess_native_48000.json").read_text())

SENTENCE = "I'll grab a coffee before the meeting."


def wav(seconds: float = 1.7, rate: int = 48000) -> bytes:
    """A real WAV header plus silence. **Parsed by the service, not trusted.**"""
    frames = int(seconds * rate)
    data = b"\x00\x00" * frames
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(data))
    )
    return header + data


class _Response:
    status_code = 200

    def json(self):
        return RECORDED


def _ok_post(url, **kwargs):
    return _Response()


@pytest.fixture(autouse=True)
def rate_limit_reset():
    """Clear this route's rate-limit buckets around every test.

    **The limiter counts in Postgres, not in memory** — deliberately, because
    the API runs `--workers 2` — so its counters **survive the test that made
    them and the run that made them**, for the whole hour. This module issues
    ~20 scored attempts against one client key; a second full-suite run inside
    the same hour then crosses `per_client=60` and **every test here returns
    429**, which is what happened on the first full run.

    **Cleared here rather than by loosening the route.** Tuning a production
    abuse guard to suit a test suite would be adjusting the thing under test
    until it agrees with us; the test owns its preconditions instead.
    """
    def _clear() -> None:
        with psycopg.connect(load_settings().database_url) as conn:
            # **The whole table, because the bucket key is a SALTED HASH** --
            # `auth.check_rate_limit` hashes route + client with
            # `auth_rate_limit_salt`, so there is no prefix to match on and a
            # targeted delete is not available. Safe here: the suite is serial,
            # and no other test asserts over carried rate-limit state
            # (`grep auth_rate_limits tests/` finds only this file).
            conn.execute("DELETE FROM auth_rate_limits")
            conn.commit()

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def azure_configured(monkeypatch):
    """Dummy Azure credentials, **exported, never a scratch `.env`.**

    CLAUDE.md §3 rule 3 — test configuration the way it is really set — and
    known issue #64: `load_dotenv()` resolves relative to
    `packages/core/config.py`, so a temp `.env` elsewhere is silently ignored
    and the real configuration loads instead. Exported variables win over
    `.env`, which is why exporting is the only reliable method.

    **This fixture is why the route tests reach the mocked transport at all**:
    without both variables `assess_pronunciation` refuses before building a
    request — *absent means the surface refuses to run, not that it runs
    degraded* — and every test here returned 502. That refusal is asserted
    directly in `test_speech_pronunciation.py`; here it is configured away so
    the rest of the path can be exercised.

    **These are not real values and no real value exists in this repository.**
    """
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key-not-real")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "test-region")


@pytest.fixture(autouse=True)
def consented(learner, monkeypatch):
    """Put the test learner on the consent allowlist (#364).

    **The allowlist is empty by default and that is deliberate**, so every test
    in this file must opt its learner in explicitly. `tests/test_shadow_consent_gate.py`
    asserts the closed default and the refusal; this fixture is what lets the
    rest of the surface be exercised at all.
    """
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", str(learner.user_id))
    # §B reaches `speech.synthesize`, which refuses without a key before it
    # builds any request. Exported, never a scratch `.env` (#64).
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W14 Route', 'fa', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, f"w14r-{abs(telegram_user_id)}@example.test",
         str(uuid.uuid4())),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name,"
        " status) VALUES (%s, %s, 'W14 Route', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at)"
        " VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id,
         datetime.now(timezone.utc) + timedelta(days=30)),
    )
    card = db.execute(
        """
        INSERT INTO cards (user_id, card_type, front, back, context_sentence,
                           register, register_source, fsrs_state, fsrs_step,
                           due, lapses, reps)
        VALUES (%s, 'production', 'coffee', 'kahve', %s, 'neutral',
                'migration_default', 'learning', 0, CURRENT_DATE, 0, 0)
        RETURNING id
        """,
        (user_id, SENTENCE),
    ).fetchone()
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw, "card_id": int(card[0])})()
    db.execute("DELETE FROM speech_attempts WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def post(app, path, *, body: bytes, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.post(
                path, content=body, headers={"Content-Type": "audio/wav"}
            )

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


# --- test 1 -----------------------------------------------------------------

def test_the_route_writes_exactly_one_row_and_returns_per_word_colouring(
    app, learner, db
) -> None:
    """**Exact values from the recording, and `== 1`, never `>= 1`** (#345)."""
    with patch("core.speech_api.httpx.post", _ok_post):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 200, response.text
    body = response.json()

    assert [w["word"] for w in body["words"]] == [
        "i'll", "grab", "a", "coffee", "before", "the", "meeting",
    ]
    assert [w["accuracy"] for w in body["words"]] == [
        97.0, 100.0, 97.0, 97.0, 100.0, 94.0, 100.0
    ]
    assert all(w["clean"] for w in body["words"])
    # First attempt: `None`, not False. Drops and firsts are indistinguishable.
    assert body["improved"] is None

    rows = db.execute(
        "SELECT accuracy, fluency, completeness, pron_score, prosody,"
        " words, phonemes, audio_seconds, provider, surface, reference_text"
        " FROM speech_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchall()
    assert len(rows) == 1
    (acc, flu, comp, pron, prosody, words, phonemes, seconds, provider,
     surface, reference) = rows[0]
    assert (acc, flu, comp, pron) == (98.0, 100.0, 100.0, 98.8)
    assert prosody is None, "the prosody add-on is not bought"
    assert len(words) == 7 and len(phonemes) == 23
    assert provider == "azure" and surface == "shadow"
    assert reference == SENTENCE
    # From OUR bytes, not Azure's `Duration` (1.65 s in the recording).
    assert abs(seconds - 1.7) < 0.01


def test_the_four_aggregates_never_cross_the_wire(app, learner) -> None:
    """§2.6. **A client cannot render what it was never given.**"""
    with patch("core.speech_api.httpx.post", _ok_post):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    body = response.json()
    assert set(body) == {"attempt_id", "words", "improved"}
    blob = response.text
    for banned in ("98.8", "fluency", "completeness", "pron_score", "accuracy_score"):
        assert banned not in blob, f"{banned!r} reached the browser"


# --- tests 2 and 3 ----------------------------------------------------------
#
# **THE EROSION RULE, S3, AND IT LIVES HERE RATHER THAN IN A COMMENT.**
#
# These two are the first tests in this suite whose result depends on what else
# is running -- W13-i/6 already produced that failure once (two pytest processes
# against one database; three failures, none of them real).
#
# **A SPURIOUS FAILURE IS RESOLVED BY NARROWING THE SNAPSHOT'S *ROOT*, NEVER BY
# NARROWING *WHAT IT LOOKS FOR*, AND IT IS RE-RUN SERIALLY BEFORE IT IS
# BELIEVED.** The two repairs feel identical and only one keeps the instrument:
# a test whose scope has been trimmed stays green while asserting nothing, which
# is #345's family arriving by erosion, with no author to catch it.
#
# The root here is a per-test `tmp_path` the test itself creates, so a
# concurrent writer anywhere else in the tree cannot appear in it.
#
# **`tests/test_speech_no_disk.py` IS THE REDUNDANCY THAT MAKES THAT SURVIVABLE**
# -- it reads SOURCE, so it cannot flake and cannot be weakened by a trimmed
# root. Two instruments, different failure modes, and that is the design.


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_no_file_appears_anywhere_on_the_success_path(
    app, learner, tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)
    with patch("core.speech_api.httpx.post", _ok_post):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 200
    assert _snapshot(tmp_path) == before, "audio or a temp file reached the disk"


def test_no_file_appears_on_the_failure_path_and_no_row_is_written(
    app, learner, tmp_path, monkeypatch, db
) -> None:
    """**An error path that writes a temp file breaks the rule as surely as a
    success path does** — which is why this exists separately."""
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)

    def _boom(url, **kwargs):
        raise httpx.ConnectError("no route to host")

    with patch("core.speech_api.httpx.post", _boom), patch(
        "core.speech.time.sleep", return_value=None
    ):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 502
    assert _snapshot(tmp_path) == before
    count = db.execute(
        "SELECT count(*) FROM speech_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()[0]
    assert count == 0, "a failed attempt must leave no row that reads as a score"


# --- test 5 -----------------------------------------------------------------

def test_the_recognised_transcript_is_never_persisted_or_logged(
    app, learner, db, caplog
) -> None:
    """The recording carries `DisplayText`, `Lexical`, `ITN` and `MaskedITN`.

    **Four spellings of what Azure heard, and none may survive the request.**
    """
    sentinel = "ZZQQ sentinel transcript XXYY"
    doctored = json.loads(json.dumps(RECORDED))
    doctored["DisplayText"] = sentinel
    doctored["NBest"][0]["Lexical"] = sentinel
    doctored["NBest"][0]["ITN"] = sentinel
    doctored["NBest"][0]["MaskedITN"] = sentinel

    class _R:
        status_code = 200

        def json(self):
            return doctored

    with caplog.at_level("DEBUG"), patch(
        "core.speech_api.httpx.post", lambda url, **kw: _R()
    ):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 200

    row = db.execute(
        "SELECT * FROM speech_attempts WHERE user_id = %s", (learner.user_id,)
    ).fetchone()
    assert sentinel not in json.dumps(row, default=str)
    assert sentinel not in response.text
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert logs, "the request must log something, or this cannot fail"
    assert sentinel not in logs


# --- test 6 -----------------------------------------------------------------

def test_phoneme_scores_accumulate_per_user(app, learner, db) -> None:
    """**W17's read path, run over two real attempts.**

    Expected phonemes are **hardcoded from the recording**, never recomputed
    from the writer — CLAUDE.md §3 rule 5.
    """
    with patch("core.speech_api.httpx.post", _ok_post):
        for _ in range(2):
            assert post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner)).status_code == 200

    rows = db.execute(
        """
        SELECT p->>'phoneme' AS phoneme,
               count(*)::int  AS seen,
               avg((p->>'accuracy')::float8) AS mean
          FROM speech_attempts,
               LATERAL jsonb_array_elements(phonemes) AS p
         WHERE user_id = %s
         GROUP BY 1 ORDER BY mean ASC, phoneme ASC
        """,
        (learner.user_id,),
    ).fetchall()
    by_phoneme = {r[0]: (r[1], r[2]) for r in rows}
    # 23 phonemes per attempt, 17 distinct; `l` is the weakest at 81.
    assert len(by_phoneme) == 17
    assert by_phoneme["l"] == (2, 81.0)
    assert by_phoneme["ay"] == (2, 100.0)
    assert rows[0][0] == "l", "the weakest phoneme must sort first for W17"
    assert sum(seen for seen, _ in by_phoneme.values()) == 46


def test_a_second_attempt_that_improves_says_so_and_a_worse_one_says_nothing(
    app, learner, db
) -> None:
    """**Raises announced, drops silent** (CLAUDE.md §4), both directions."""
    lower = json.loads(json.dumps(RECORDED))
    lower["NBest"][0]["PronScore"] = 60.0

    class _Low:
        status_code = 200

        def json(self):
            return lower

    with patch("core.speech_api.httpx.post", lambda url, **kw: _Low()):
        first = post(app, f"/shadow/{learner.card_id}/score",
                     body=wav(), cookies=_as(learner))
    assert first.json()["improved"] is None

    with patch("core.speech_api.httpx.post", _ok_post):
        better = post(app, f"/shadow/{learner.card_id}/score",
                      body=wav(), cookies=_as(learner))
    assert better.json()["improved"] is True, "a raise is announced"

    with patch("core.speech_api.httpx.post", lambda url, **kw: _Low()):
        worse = post(app, f"/shadow/{learner.card_id}/score",
                     body=wav(), cookies=_as(learner))
    assert worse.json()["improved"] is None, "a drop is SILENT, never False"


# --- test 10 ----------------------------------------------------------------

def test_quota_exhaustion_says_so_and_writes_nothing(app, learner, db) -> None:
    """Both directions: **our own ceiling, and the provider's refusal.**"""
    from core.services import shadow_score

    # (a) our ledger. One row already past the soft ceiling.
    db.execute(
        "INSERT INTO speech_attempts (user_id, surface, reference_text,"
        " accuracy, fluency, completeness, pron_score, words, phonemes,"
        " audio_seconds, provider) VALUES (%s, 'shadow', %s, 90, 90, 90, 90,"
        " '[]'::jsonb, '[]'::jsonb, %s, 'azure')",
        (learner.user_id, SENTENCE, shadow_score.SOFT_CEILING_SECONDS + 1),
    )
    db.commit()
    with patch("core.speech_api.httpx.post", side_effect=_ok_post) as called:
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 409
    assert called.call_count == 0, "the ceiling must refuse BEFORE the provider"

    db.execute("DELETE FROM speech_attempts WHERE user_id = %s", (learner.user_id,))
    db.commit()

    # (b) the provider refuses anyway. **Same face to the learner.**
    class _Refused:
        status_code = 403

        def json(self):
            return {}

    with patch("core.speech_api.httpx.post", lambda url, **kw: _Refused()):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 409
    count = db.execute(
        "SELECT count(*) FROM speech_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()[0]
    assert count == 0


def test_an_oversized_upload_is_refused_before_it_is_scored(app, learner) -> None:
    with patch("core.speech_api.httpx.post", side_effect=_ok_post) as called:
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=b"\x00" * 2_000_001, cookies=_as(learner))
    assert response.status_code == 413
    assert called.call_count == 0


def test_an_utterance_the_provider_cannot_hear_is_not_a_low_score(
    app, learner, db
) -> None:
    """**422, and no row.** Storing a zero would invent a measurement."""
    class _NoMatch:
        status_code = 200

        def json(self):
            return {"RecognitionStatus": "NoMatch", "NBest": []}

    with patch("core.speech_api.httpx.post", lambda url, **kw: _NoMatch()):
        response = post(app, f"/shadow/{learner.card_id}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 422
    count = db.execute(
        "SELECT count(*) FROM speech_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()[0]
    assert count == 0


def test_another_learners_card_is_not_scorable(app, learner, db) -> None:
    other = db.execute(
        """
        INSERT INTO cards (user_id, card_type, front, back, context_sentence,
                           register, register_source, fsrs_state, fsrs_step,
                           due, lapses, reps)
        SELECT id, 'production', 'x', 'y', %s, 'neutral', 'migration_default',
               'learning', 0, CURRENT_DATE, 0, 0
          FROM users WHERE id <> %s LIMIT 1
        RETURNING id
        """,
        (SENTENCE, learner.user_id),
    ).fetchone()
    db.commit()
    if other is None:
        pytest.skip("no second user in this database")
    with patch("core.speech_api.httpx.post", side_effect=_ok_post) as called:
        response = post(app, f"/shadow/{other[0]}/score",
                        body=wav(), cookies=_as(learner))
    assert response.status_code == 404
    assert called.call_count == 0
    db.execute("DELETE FROM cards WHERE id = %s", (other[0],))
    db.commit()


# --- tests 12 and 13 --------------------------------------------------------

def test_output_does_not_reach_done_from_a_shadow_attempt_alone(
    app, learner, db
) -> None:
    """§1e / #361, asserted rather than trusted.

    **The row must exist** — otherwise this passes because the attempt silently
    failed, which is an assertion unable to fail for the reason it claims.
    """
    from core.services import sessions as sessions_service

    with patch("core.speech_api.httpx.post", _ok_post):
        assert post(app, f"/shadow/{learner.card_id}/score",
                    body=wav(), cookies=_as(learner)).status_code == 200
    written = db.execute(
        "SELECT count(*) FROM speech_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()[0]
    assert written == 1, "the precondition: an attempt WAS recorded"

    session = sessions_service.today(
        learner.user_id, now=datetime.now(timezone.utc)
    )
    assert session is not None
    output = [b for b in session.blocks if b.kind == "output"][0]
    assert output.state != "done", (
        "`output` must not self-report from a shadow log: the WRITTEN task is "
        "what the block asks for and `POST /correct` still records no "
        "session_id (#361). #259 does not close here."
    )


def test_the_shadow_line_is_served_in_block_four_and_nowhere_else(
    app, learner
) -> None:
    """§1e: one place decides today's line, so there is no second producer."""
    from core.services import sessions as sessions_service

    session = sessions_service.today(
        learner.user_id, now=datetime.now(timezone.utc)
    )
    output = [b for b in session.blocks if b.kind == "output"][0]
    assert output.payload["shadow"] == {
        "card_id": learner.card_id,
        "sentence": SENTENCE,
    }
    paths = {
        getattr(r, "path", "") for r in create_app().routes
    } | {"/shadow/{card_id}/score"}
    assert not any(
        p.startswith("/shadow") and p != "/shadow/{card_id}/score" for p in paths
    ), "there must be no second route serving a shadow target"


# --- §B: listen to the line -------------------------------------------------
#
# **MOCKED AT THE OPENAI TRANSPORT, not at `speech.synthesize`** (standing rule
# 7), so the wrapper's provider selection, credential check, retry and response
# extraction all execute. `test_items_route.py:654` stubs the service function
# for the older `/items/{id}/audio` route; that predates the rule and is not
# followed here.


def _tts(payload: bytes):
    class _R:
        content = payload

    return _R()


def get(app, path, *, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.get(path)

    return asyncio.run(_go())


def test_the_line_audio_route_returns_bytes_and_never_the_text(app, learner) -> None:
    """**Bytes in, bytes out** — `items.audio`'s standing rule since W6.

    Mocked at `core.speech.synthesize`, which is where `shadow_score` reaches
    the wrapper. The route must not hold the sentence: it is the learner's own
    card content and CLAUDE.md §5 keeps message bodies out of `apps/api`.
    """
    with patch("core.speech.openai.OpenAI") as client_cls:
        client = client_cls.return_value
        client.audio.speech.create.return_value = _tts(b"ID3-audio-bytes")
        response = get(app, f"/shadow/{learner.card_id}/audio", cookies=_as(learner))
    assert response.status_code == 200
    assert response.content == b"ID3-audio-bytes"
    assert response.headers["content-type"] == "audio/mpeg"
    # **THIS card's sentence and nothing else**, read at the transport so the
    # wrapper's own request construction runs (standing rule 7).
    assert client.audio.speech.create.call_args.kwargs["input"] == SENTENCE


def test_a_learner_not_on_the_allowlist_cannot_hear_the_line_either(
    app, learner, monkeypatch
) -> None:
    """**#364 must not leak through the quieter door.**

    A blocked learner who could hear the line would learn the feature exists.
    404, the same answer an absent line gives — never 403.
    """
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", "")
    with patch("core.speech.openai.OpenAI") as client_cls:
        response = get(app, f"/shadow/{learner.card_id}/audio", cookies=_as(learner))
    assert response.status_code == 404
    assert client_cls.call_count == 0, "no provider call for a blocked learner"


def test_a_provider_failure_is_503_and_leaks_no_detail(app, learner) -> None:
    """The service is up; its dependency is not. `items.audio`'s ruling."""
    with patch("core.speech.openai.OpenAI") as client_cls:
        client_cls.return_value.audio.speech.create.side_effect = RuntimeError(
            "upstream said quota exceeded for key sk-xyz"
        )
        response = get(app, f"/shadow/{learner.card_id}/audio", cookies=_as(learner))
    assert response.status_code == 503
    assert "sk-xyz" not in response.text
    assert "quota" not in response.text.lower()


def test_another_learners_card_cannot_be_heard(app, learner, db) -> None:
    other = db.execute(
        "SELECT id FROM cards WHERE user_id <> %s LIMIT 1", (learner.user_id,)
    ).fetchone()
    if other is None:
        pytest.skip("no other learner's card in this database")
    with patch("core.speech.openai.OpenAI") as client_cls:
        response = get(app, f"/shadow/{other[0]}/audio", cookies=_as(learner))
    assert response.status_code == 404
    assert client_cls.call_count == 0
