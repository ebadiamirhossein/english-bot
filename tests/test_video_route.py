"""W13-i: `GET /video/today`, `POST /video/{id}/progress`, and block 2 —
**through the real ASGI transport.**

Nothing here calls a route function or a service directly. CLAUDE.md §3 rule 1:
in v2, 161 tests passed while the main feature was dead, because every test
called handlers directly. `tests/support/netguard.py` is armed session-wide by
`conftest.py`, so a provider call inside one of these requests raises rather
than passing silently -- which is how the *nothing is generated while a learner
waits* property is known rather than read off a comment.

THE THREE QUESTIONS:

1. **What does the fixture supply that production does not?** An assigned video
   with a transcript, written through `svc.upsert_video`, `svc.record_transcript`
   and `svc.assign_video` -- the same three functions `refresh` and `assign`
   call, so no test asserts against a row those paths could not produce. And a
   ledger: since W13c that is `users.known_word_floor`, default 2000, which
   every learner row carries without a write -- what a real learner has.
2. **Does the production caller supply it?** Yes -- these rows are what a
   Monday looks like after `python -m core.video.refresh --live --apply` and
   `python -m core.video.assign --apply`.
3. **Does the assertion name the thing, or count it?** It names it: which band
   token, which column moved, which key is absent from the payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.services import video as svc
from core.services.sessions import local_today


#: Every `videos` row this file writes carries it, so the teardown in `learner`
#: can find them all without a per-test register that a new test would forget to
#: join. `youtube_id` is `TEXT NOT NULL UNIQUE` and real ids are 11 characters,
#: so this cannot collide with production data.
ID_PREFIX = "rt13"


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
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W13 Route', 'fa', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            f"w13r-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W13 Route', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
        "VALUES (%s, %s, %s)",
        (
            hashlib.sha256(raw.encode()).digest(),
            user_id,
            datetime.now(timezone.utc) + timedelta(days=30),
        ),
    )
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.execute(
        "DELETE FROM video_assignments WHERE user_id = %s", (user_id,)
    )
    db.execute("DELETE FROM video_coverage WHERE user_id = %s", (user_id,))
    # **`videos` HAS NO `user_id`, SO NOTHING ELSE HERE REACHES IT** -- migration
    # 019 keeps the candidate pool shared between both learners deliberately, on
    # 014's reasoning for `syllabus_unit_lexemes`. A user-keyed teardown
    # therefore leaves these rows behind **in a database every other test
    # shares**, and `test_only_ok_rows_are_selectable` asserts over the whole
    # table -- so the leak made a W12b test fail for a reason that had nothing to
    # do with W12b. Found by the full suite, and fixed here rather than by
    # loosening that assertion.
    #
    # **AFTER the assignments, never before:** `video_assignments.video_id` is
    # `ON DELETE RESTRICT` (019, deliberately), so this order is the schema's and
    # not a preference.
    db.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (f"{ID_PREFIX}%",))
    db.execute("DELETE FROM user_lexemes WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def request(app, method, path, *, json_body=None, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(method, path, json=json_body)

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


#: Long enough to clear `badge.MIN_COUNTED_TOKENS`, so the badge is exercised
#: rather than suppressed. **#330's suppression is asserted separately, on a
#: short one** -- a fixture that quietly landed under the floor would make every
#: badge assertion here vacuous.
#:
#: **CONVENTIONALLY CASED, AND THAT WAS A CORRECTION.** It was entirely
#: lowercase, which `casing_profile` reads as not conventional -- so
#: `proper_nouns_detected` came back False and `band_for` **withheld the badge
#: on every test in this file**. Every band assertion here was passing against
#: `None`. Found while adding the cue-timings cases, whose assertion was the
#: first to require a real band. **A fixture that trips a suppression makes the
#: assertions above it vacuous**, which is CLAUDE.md §3 rule 4's shape in a
#: fixture rather than in a test.
LONG_TRANSCRIPT = (
    "We were talking about the rent again and it went up which is not "
    "great but we will manage it somehow because we always do and the "
    "flat is close to work anyway so the trade is probably worth it. "
) * 12


def _assign_today(db, learner, *, transcript: str | None, youtube_id: str,
                  duration_s: int | None = 720) -> int:
    video_id = svc.upsert_video(
        db,
        youtube_id=youtube_id,
        channel_id="UCw13route000000000000",
        accent="british",
        track="life",
        title="A probe video",
        duration_s=duration_s,
        published_at=datetime.now(timezone.utc) - timedelta(days=2),
        now=datetime.now(timezone.utc),
    )
    if transcript is not None:
        svc.record_transcript(
            db, video_id=video_id, text=transcript, lang="en", kind="manual"
        )
    svc.assign_video(
        db,
        user_id=learner.user_id,
        video_id=video_id,
        assigned_for=local_today("Europe/Vilnius", datetime.now(timezone.utc)),
        score_breakdown={},
    )
    db.commit()
    return video_id


def _block_two(app, learner) -> dict:
    response = request(app, "GET", "/session/today", cookies=_as(learner))
    assert response.status_code == 200, response.text
    blocks = response.json()["blocks"]
    return next(b for b in blocks if b["kind"] == "input")


# ── GET /video/today ────────────────────────────────────────────────────────


def test_the_route_is_gated(app) -> None:
    """A 401 and not a 403: there is no session, so there is nobody to refuse."""
    assert request(app, "GET", "/video/today").status_code == 401
    assert request(app, "POST", "/video/1/progress").status_code == 401


def test_no_video_today_is_a_404_and_not_an_error(app, learner) -> None:
    """**The ordinary state on four days in seven.** PRD §7.1 assigns video on
    Mon/Wed/Fri; the client reads this as *no video today*."""
    response = request(app, "GET", "/video/today", cookies=_as(learner))
    assert response.status_code == 404
    assert response.json()["detail"] == "no_video_today"


def test_todays_video_comes_back_without_a_transcript_or_a_figure(
    app, learner, db
) -> None:
    """**One contract, one producer (#190).** The transcript and the band are
    block 2's; this route deliberately cannot carry them, so there is no second
    assembler of the player's payload to drift out of step."""
    _assign_today(db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13a00001")

    response = request(app, "GET", "/video/today", cookies=_as(learner))
    assert response.status_code == 200
    body = response.json()
    assert body["youtube_id"] == "rt13a00001"
    assert body["resume_position_s"] == 0
    assert body["completed"] is False
    assert "transcript" not in body
    assert "coverage" not in body and "coverage_band" not in body


# ── POST /video/{id}/progress ───────────────────────────────────────────────


def test_a_progress_ping_stores_the_position(app, learner, db) -> None:
    video_id = _assign_today(
        db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13b00001"
    )
    response = request(
        app,
        "POST",
        f"/video/{video_id}/progress",
        json_body={"position_s": 240},
        cookies=_as(learner),
    )
    assert response.status_code == 200
    assert response.json()["resume_position_s"] == 240
    assert response.json()["completed"] is False


def test_reaching_the_end_completes_the_video_and_block_two_goes_done(
    app, learner, db
) -> None:
    """**#291 and #258 in one assertion, through the real routes.**

    The ping is block 2's log. Nothing taps a completion control -- there is
    none -- and `_derive_done` reads what the ping wrote.
    """
    video_id = _assign_today(
        db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13c00001"
    )
    assert _block_two(app, learner)["state"] == "ready"

    response = request(
        app,
        "POST",
        f"/video/{video_id}/progress",
        json_body={"position_s": 700},
        cookies=_as(learner),
    )
    assert response.status_code == 200
    assert response.json()["completed"] is True
    assert _block_two(app, learner)["state"] == "done"


def test_a_ping_for_a_video_this_learner_does_not_have_is_a_404(
    app, learner, db
) -> None:
    """**Never a silent success.** A write that touched nothing must not report
    that it touched something."""
    other = svc.upsert_video(
        db,
        youtube_id="rt13d00001",
        channel_id="UCw13route000000000000",
        accent="british",
        track="life",
        title="Not assigned",
        duration_s=600,
        published_at=datetime.now(timezone.utc),
        now=datetime.now(timezone.utc),
    )
    db.commit()
    response = request(
        app,
        "POST",
        f"/video/{other}/progress",
        json_body={"position_s": 100},
        cookies=_as(learner),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "not_assigned"


def test_the_client_cannot_assert_a_completion(app, learner, db) -> None:
    """**A `completed` field in the body is ignored** -- `VideoProgressIn` has
    one field and pydantic drops the rest, so a browser can lie about a
    POSITION (which is clamped) and never about a VERDICT (#190, #291)."""
    video_id = _assign_today(
        db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13e00001"
    )
    response = request(
        app,
        "POST",
        f"/video/{video_id}/progress",
        json_body={"position_s": 10, "completed": True, "completed_at": "2020-01-01"},
        cookies=_as(learner),
    )
    assert response.status_code == 200
    assert response.json()["completed"] is False


def test_a_position_past_the_end_is_clamped_to_the_video(app, learner, db) -> None:
    video_id = _assign_today(
        db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13f00001",
        duration_s=600,
    )
    response = request(
        app,
        "POST",
        f"/video/{video_id}/progress",
        json_body={"position_s": 99_999},
        cookies=_as(learner),
    )
    assert response.json()["resume_position_s"] == 600


# ── block 2 ─────────────────────────────────────────────────────────────────


def test_block_two_is_empty_on_a_day_with_no_video(app, learner) -> None:
    """**`empty` and never `unavailable`.** The query ran and returned nothing;
    nothing failed. `BLOCK_STATES` keeps the two apart because the learner can
    only see one of them on the screen."""
    block = _block_two(app, learner)
    assert block["state"] == "empty"
    assert block["payload"] == {}


def test_block_two_carries_the_transcript_the_unknown_words_and_a_band(
    app, learner, db
) -> None:
    _assign_today(db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13g00001")
    # The learner's floor is `users.known_word_floor`, default 2000 (W13c):
    # a real learner's ledger with nothing written.

    block = _block_two(app, learner)
    assert block["state"] == "ready"
    payload = block["payload"]
    assert payload["youtube_id"] == "rt13g00001"
    assert payload["transcript_available"] is True
    assert payload["transcript"].startswith("We were talking about the rent")
    assert isinstance(payload["unknown_lemmas"], list)
    # **Not `… or None`.** The fixture is conventionally cased and long
    # enough, so a real band is the only correct answer here; allowing None
    # is what let the suppression hide behind this assertion.
    assert payload["coverage_band"] in ("below", "in", "above")


def test_no_coverage_percentage_reaches_the_client_anywhere(
    app, learner, db
) -> None:
    """**The ruling of §2c, asserted on the wire rather than on the screen.**

    #288 (proper nouns inside the assumed-known floor, inflating every figure by
    an uncounted amount), #334 (`coverage_fit` returns 1.0 across the band) and
    #330 (a percentage over 234 characters). The number is still computed, still
    stored and still printed by both CLIs; what is declined is DISPLAYING it.

    Asserted over the whole serialised session, not over one key, because the
    defect this guards against is a field somebody adds later.
    """
    _assign_today(db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13h00001")
    # The learner's floor is `users.known_word_floor`, default 2000 (W13c):
    # a real learner's ledger with nothing written.

    body = request(app, "GET", "/session/today", cookies=_as(learner)).text
    for banned in ("coverage_pct", "coverage_percent", '"coverage"', "percent"):
        assert banned not in body, banned


def test_a_purged_transcript_keeps_block_two_ready_and_playable(
    app, learner, db
) -> None:
    """**#335 on the wire.** The purge nulls the transcript and returns the row
    to `pending`; `youtube_id` survives by design, so the video is still
    watchable and nothing failed -- which is why this is `ready` with
    `transcript_available: false` and not `unavailable`."""
    _assign_today(db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13i00001")
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute(
            "UPDATE videos SET metadata_refreshed_at = %s WHERE youtube_id = %s",
            (datetime.now(timezone.utc) - timedelta(days=40), "rt13i00001"),
        )
        svc.purge_stale(conn, now=datetime.now(timezone.utc))
        conn.commit()

    block = _block_two(app, learner)
    assert block["state"] == "ready"
    assert block["payload"]["youtube_id"] == "rt13i00001"
    assert block["payload"]["transcript_available"] is False
    assert block["payload"]["transcript"] is None
    assert block["payload"]["coverage_band"] is None


def test_a_short_transcript_gets_no_band(app, learner, db) -> None:
    """**#330.** `5E5tNu4NsxM` is 17 seconds long with a 234-character
    transcript. A percentage over that measures one paragraph, so the badge is
    withheld -- which is a fourth answer and not a fourth band."""
    _assign_today(
        db, learner, transcript="we were talking about it", youtube_id="rt13j00001"
    )
    # The learner's floor is `users.known_word_floor`, default 2000 (W13c):
    # a real learner's ledger with nothing written.

    block = _block_two(app, learner)
    assert block["state"] == "ready"
    assert block["payload"]["transcript_available"] is True
    assert block["payload"]["coverage_band"] is None


# ── cue timings: the third state, and the purge (021) ───────────────────────


CUES = [
    {"text": "we", "start": 0.0, "duration": 1.5},
    {"text": "were talking", "start": 1.2, "duration": 2.0},
]


def test_a_transcript_with_no_cues_is_served_and_says_nothing_about_it(
    app, learner, db
) -> None:
    """**THE THIRD STATE, through the real route.** `assign` selects from the
    pool, not from the dumped subset, so a transcript with no cues is the
    ORDINARY case until the pool turns over. It renders, the badge still shows,
    and `transcript_cues` is null — no error, no flag, nothing for a client to
    apologise for."""
    _assign_today(db, learner, transcript=LONG_TRANSCRIPT, youtube_id="rt13k00001")
    # The learner's floor is `users.known_word_floor`, default 2000 (W13c):
    # a real learner's ledger with nothing written.

    before = _block_two(app, learner)["payload"]
    assert before["transcript_available"] is True
    assert before["transcript_cues"] is None
    assert before["coverage_band"] in ("below", "in", "above")

    # **THE CLAIM THIS TEST IS ACTUALLY ABOUT: the badge reads `transcript` and
    # is untouched by the cues.** Asserted by comparison rather than by value,
    # so it holds whatever the band happens to be.
    with psycopg.connect(load_settings().database_url) as conn:
        video_id = conn.execute(
            "SELECT id FROM videos WHERE youtube_id = %s", ("rt13k00001",)
        ).fetchone()[0]
        cues = [
            {"text": word, "start": float(i), "duration": 1.0}
            for i, word in enumerate(LONG_TRANSCRIPT.split(" ")[:-1])
        ]
        assert svc.record_cues(
            conn, video_id=video_id, cues=cues, text=LONG_TRANSCRIPT
        ) is False, "the join drops the trailing space, so the gate refuses"
        conn.commit()

    after = _block_two(app, learner)["payload"]
    assert after["coverage_band"] == before["coverage_band"]


def test_cues_reach_the_client_when_they_reproduce_the_transcript(
    app, learner, db
) -> None:
    text = " ".join(c["text"] for c in CUES)
    _assign_today(db, learner, transcript=text, youtube_id="rt13l00001")
    with psycopg.connect(load_settings().database_url) as conn:
        assert svc.record_cues(
            conn,
            video_id=conn.execute(
                "SELECT id FROM videos WHERE youtube_id = %s", ("rt13l00001",)
            ).fetchone()[0],
            cues=CUES,
            text=text,
        )
        conn.commit()

    payload = _block_two(app, learner)["payload"]
    assert payload["transcript_cues"] == CUES


def test_cues_that_do_not_reproduce_the_transcript_are_refused(
    app, learner, db
) -> None:
    """**The gate, and it refuses rather than repairing.** A row whose cues
    describe different text is coverage over one string and a highlight over
    another — silent, because the highlight would still land somewhere
    plausible."""
    _assign_today(db, learner, transcript="something else entirely",
                  youtube_id="rt13m00001")
    with psycopg.connect(load_settings().database_url) as conn:
        video_id = conn.execute(
            "SELECT id FROM videos WHERE youtube_id = %s", ("rt13m00001",)
        ).fetchone()[0]
        assert svc.record_cues(
            conn, video_id=video_id, cues=CUES, text="something else entirely"
        ) is False
        conn.commit()

    assert _block_two(app, learner)["payload"]["transcript_cues"] is None


def test_the_purge_nulls_the_cues_with_the_transcript_on_one_clock(
    app, learner, db
) -> None:
    """**021's ruling, asserted rather than commented.** The cues join the SAME
    `UPDATE` on the SAME `metadata_refreshed_at`. Cues outliving the text they
    index would be offsets into a string that is gone."""
    text = " ".join(c["text"] for c in CUES)
    _assign_today(db, learner, transcript=text, youtube_id="rt13n00001")
    with psycopg.connect(load_settings().database_url) as conn:
        video_id = conn.execute(
            "SELECT id FROM videos WHERE youtube_id = %s", ("rt13n00001",)
        ).fetchone()[0]
        svc.record_cues(conn, video_id=video_id, cues=CUES, text=text)
        conn.execute(
            "UPDATE videos SET metadata_refreshed_at = %s WHERE id = %s",
            (datetime.now(timezone.utc) - timedelta(days=40), video_id),
        )
        svc.purge_stale(conn, now=datetime.now(timezone.utc))
        row = conn.execute(
            "SELECT transcript, transcript_cues FROM videos WHERE id = %s",
            (video_id,),
        ).fetchone()
        conn.commit()

    assert row[0] is None, "the transcript is purged"
    assert row[1] is None, "and the cues go with it, on the same clock"


# ── W13-ii: POST /video/{id}/save-word ──────────────────────────────────────


def _gloss(db, video_id: int, **over) -> None:
    from core.services import glosses as glosses_svc

    spec = dict(
        video_id=video_id,
        word="mid",
        context_sentence="honestly that party was mid",
        cue_start_s=12.5,
        definition="disappointing, not as good as expected",
        register="slang",
        neutral_equivalent="disappointing",
        who_says_this="younger speakers, to friends",
        model="test-model",
    )
    spec.update(over)
    glosses_svc.insert_gloss(db, **spec)
    db.commit()


@pytest.fixture
def assigned(db, learner) -> int:
    """One assigned video with a transcript, through the real writers."""
    # **`ID_PREFIX`, and the first draft of this fixture did not use it.** This
    # module's teardown deletes videos by `youtube_id LIKE ID_PREFIX%`, so a
    # fixture that invents its own prefix leaves the video behind — and with it
    # every `video_glosses` row that would have cascaded. **#340's exact shape:
    # a global table whose test rows survive a cleanup keyed on something else.**
    # Found by `scripts/rollback_023.sql`'s guard refusing on three leftover
    # glosses, which is a rollback script catching a test-hygiene defect.
    return _assign_today(
        db, learner,
        transcript="honestly that party was mid",
        youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}",
    )


def test_saving_a_word_requires_a_session(app) -> None:
    assert request(
        app, "POST", "/video/1/save-word", json_body={"word": "mid"}
    ).status_code == 401


def test_a_tap_saves_two_cards_and_says_so(app, db, learner, assigned) -> None:
    """User action: tapping a word in the transcript beside the player."""
    _gloss(db, assigned)
    response = request(
        app,
        "POST",
        f"/video/{assigned}/save-word",
        json_body={"word": "mid"},
        cookies=_as(learner),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "saved"
    assert len(body["card_ids"]) == 2


def test_a_second_tap_is_two_hundred_and_not_five_hundred(
    app, db, learner, assigned
) -> None:
    """**#178 at the HTTP boundary, which is the only place it was ever a bug.**

    The service has always been able to return a state; the defect was that the
    raw `UniqueViolation` reached a learner as a 500 for doing a normal thing.
    """
    _gloss(db, assigned)
    first = request(
        app, "POST", f"/video/{assigned}/save-word",
        json_body={"word": "mid"}, cookies=_as(learner),
    )
    second = request(
        app, "POST", f"/video/{assigned}/save-word",
        json_body={"word": "mid"}, cookies=_as(learner),
    )
    # The positive control: the first tap really saved, so the second's state is
    # the pre-check firing rather than both taps failing (#345).
    assert (first.status_code, first.json()["state"]) == (200, "saved")
    assert (second.status_code, second.json()["state"]) == (200, "already_saved")
    assert second.json()["card_ids"] == []


def test_an_ungiossed_word_is_a_state_and_never_a_generation(
    app, db, learner, assigned
) -> None:
    """**§1a is PRE-GENERATE.** The netguard is armed session-wide, so a model
    call on this path would raise inside the request rather than pass silently —
    which is how we know this route generates nothing, rather than by reading
    it."""
    response = request(
        app, "POST", f"/video/{assigned}/save-word",
        json_body={"word": "nothinghasbeengeneratedforthis"}, cookies=_as(learner),
    )
    assert response.status_code == 200
    assert response.json()["state"] == "no_gloss"


def test_no_definition_crosses_the_route_boundary(app, db, learner, assigned) -> None:
    """The tap writes cards; the learner reads them in the deck, where
    `cards_service.card_face` is the single producer (#190). A definition on
    this response would be a second surface for the same content."""
    _gloss(db, assigned)
    raw = request(
        app, "POST", f"/video/{assigned}/save-word",
        json_body={"word": "mid"}, cookies=_as(learner),
    ).text
    assert "disappointing" not in raw
    assert "younger speakers" not in raw
