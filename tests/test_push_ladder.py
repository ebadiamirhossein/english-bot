"""W20: the reminder ladder (`core.services.push`), against the dev database.

**The provider is replaced at its door and nowhere else** (standing rule 7):
`core.push_api.httpx.post` records each request and answers as a push service
would. Everything above it — the claim, the ceiling reservation, the
encryption, the decision rows — runs for real. Each recorded body is DECRYPTED
here with the browser's private key, on the receiving side of RFC 8291, so the
assertion is about what the learner's phone would show, not about what the
service meant to send.

**Every time is a Vilnius wall-clock instant injected as `now`** (§3 rule 6).
Expected values are hardcoded: the copy strings are quoted, not imported.

**THE ACCEPTANCE LINES THIS FILE EXISTS FOR:** *a push at the scheduled time
opens the session directly* (`test_the_reminder_goes_once_at_morning_time_and_opens_the_session`)
and *the 4th message of a day is never sent* (`test_the_fourth_message_of_a_day_is_never_sent`,
`test_the_slot_reservation_never_hands_out_a_fourth_under_contention`).

**RED DEMONSTRATIONS (2026-09-25)** — each by editing `core/services/push.py`
or `core/services/sessions.py`, running, and restoring:
* `..._opens_the_session` — red with `SESSION_URL = "/"` (`'/' == '/session'`).
* `test_a_learner_who_practised_today_is_never_reminded` — red with the
  `practised_on` branch removed (`('reminder', 'sent') == ('reminder', 'practised')`).
* `test_the_fourth_message_of_a_day_is_never_sent` — red with the ceiling's
  `WHERE bot_message_counts.count < %s` removed (the nudge was sent; count 4).
* `test_the_slot_reservation_never_hands_out_a_fourth_under_contention` — same
  edit (`12 == 3`).
* `test_the_bot_ladder_owns_the_nudges_on_a_day_it_delivered` — red with the
  `_bot_delivered_today` branch removed (`'sent' == 'bot_ladder'`).
* `test_a_learner_with_no_channel_at_all_is_logged_loud` — red with the ERROR
  line removed (no record at ERROR).
* `test_a_crash_after_the_claim_never_sends_twice` — red with the claim's
  `conn.commit()` removed before the send (the row rolled back with the crash,
  so the second tick sent again and died again: `RuntimeError` on the second call).
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import date, time, timedelta, timezone

import httpx
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import load_settings
from core.db import connection
from core.push import Vapid, generate_vapid_keys
from core.services import push as svc
from core.services.sessions import reserve_message_slot
from tests.support import progress_seed as seed

TODAY = date(2026, 3, 12)  # a Thursday


def at(hour: int, minute: int = 0, day: date = TODAY):
    return seed.at(day, hour, minute).astimezone(timezone.utc)


def _e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@pytest.fixture
def vapid() -> Vapid:
    private, public = generate_vapid_keys()
    return Vapid(private, public, "mailto:op@example.invalid")


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


class Browser:
    """One subscribed browser: it can decrypt what it is sent."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.point = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.auth = os.urandom(16)
        self.endpoint = f"https://push.example.test/{secrets.token_hex(12)}"

    def decrypt(self, body: bytes) -> dict:
        """RFC 8291's receiving side, written from the RFC, not from `core.push`."""
        salt, keylen = body[:16], body[20]
        server_point = body[21 : 21 + keylen]
        ciphertext = body[21 + keylen :]
        server = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_point)
        secret = self.key.exchange(ec.ECDH(), server)

        def hkdf(salt_, ikm, info, n):
            prk = hmac.new(salt_, ikm, hashlib.sha256).digest()
            return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]

        ikm = hkdf(self.auth, secret, b"WebPush: info\x00" + self.point + server_point, 32)
        cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
        plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
        assert plain.endswith(b"\x02")
        return json.loads(plain[:-1])


@pytest.fixture
def service(monkeypatch):
    """The push services, at the door: records each POST, answers `status`."""
    sent: list[tuple[str, bytes]] = []
    state = {"status": 201}

    def post(url, *, headers, content, timeout):
        assert headers["Content-Encoding"] == "aes128gcm"
        sent.append((url, content))
        return httpx.Response(state["status"])

    monkeypatch.setattr("core.push_api.httpx.post", post)
    return type("S", (), {"sent": sent, "state": state})()


@pytest.fixture
def learners(db):
    made: list[int] = []

    def _make(*, telegram: bool = False, subscribed: bool = True, morning: time | None = None):
        learner = seed.make_learner(db, "W20 push")
        made.append(learner.user_id)
        if telegram:
            db.execute(
                "UPDATE users SET telegram_user_id = %s WHERE id = %s",
                (9_000_000_000 + secrets.randbelow(10**9), learner.user_id),
            )
        if morning is not None:
            db.execute("UPDATE users SET morning_time = %s WHERE id = %s", (morning, learner.user_id))
        browser = Browser()
        if subscribed:
            db.execute(
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) "
                "VALUES (%s, %s, %s, %s)",
                (learner.user_id, browser.endpoint, _e(browser.point), _e(browser.auth)),
            )
        db.commit()
        me = next(l for l in svc.list_push_learners() if l.id == learner.user_id)
        return me, browser

    yield _make
    for user_id in made:
        db.rollback()
        db.execute("DELETE FROM bot_message_counts WHERE user_id = %s", (user_id,))
        seed.drop_learner(db, user_id)


def _rows(db, user_id):
    db.rollback()
    return dict(
        db.execute(
            "SELECT kind, outcome FROM push_deliveries WHERE user_id = %s AND local_date = %s",
            (user_id, TODAY),
        ).fetchall()
    )


def _count(db, user_id):
    db.rollback()
    row = db.execute(
        "SELECT count FROM bot_message_counts WHERE user_id = %s AND local_date = %s",
        (user_id, TODAY),
    ).fetchone()
    return 0 if row is None else row[0]


# ── the reminder ─────────────────────────────────────────────────────────────


def test_nothing_is_due_before_morning_time(learners, service, vapid, db) -> None:
    me, _ = learners()
    assert svc.decide_and_send(me, at(7, 59), vapid) is None
    assert service.sent == [] and _rows(db, me.id) == {}


def test_the_reminder_goes_once_at_morning_time_and_opens_the_session(
    learners, service, vapid, db
) -> None:
    me, browser = learners()
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "sent")
    assert svc.decide_and_send(me, at(8, 7), vapid) is None
    assert len(service.sent) == 1
    url, body = service.sent[0]
    assert url == browser.endpoint
    assert browser.decrypt(body) == {
        "title": "Today’s session",
        "body": "It’s ready whenever you are.",
        "url": "/session",
    }
    assert _rows(db, me.id) == {"reminder": "sent"}
    assert _count(db, me.id) == 1


def test_a_learner_who_practised_today_is_never_reminded(learners, service, vapid, db) -> None:
    me, _ = learners()
    seed.turns(db, me.id, TODAY, typed=1)
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "practised")
    assert service.sent == [] and _count(db, me.id) == 0


def test_a_paused_learner_gets_nothing(learners, service, vapid, db) -> None:
    me, _ = learners()
    db.execute("UPDATE users SET paused_until = %s WHERE id = %s", (TODAY, me.id))
    db.commit()
    me = next(l for l in svc.list_push_learners() if l.id == me.id)
    assert me.paused_until == TODAY
    assert svc.decide_and_send(me, at(9, 0), vapid) is None
    assert service.sent == [] and _rows(db, me.id) == {}


# ── the nudges ───────────────────────────────────────────────────────────────


def test_the_ladder_nudges_at_three_and_six_hours_and_stops(learners, service, vapid, db) -> None:
    me, browser = learners()
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "sent")
    assert svc.decide_and_send(me, at(11, 1), vapid) is None
    assert svc.decide_and_send(me, at(11, 3), vapid) == ("nudge_1", "sent")
    assert svc.decide_and_send(me, at(14, 1), vapid) is None
    assert svc.decide_and_send(me, at(14, 3), vapid) == ("nudge_2", "sent")
    assert svc.decide_and_send(me, at(20, 0), vapid) is None
    bodies = [browser.decrypt(b)["body"] for _, b in service.sent]
    assert bodies == [
        "It’s ready whenever you are.",
        "Today’s session is still here whenever you have a few minutes.",
        "Short on time? One part of today’s session still counts.",
    ]
    assert _count(db, me.id) == 3


def test_practising_after_the_reminder_ends_the_ladder(learners, service, vapid, db) -> None:
    me, _ = learners()
    svc.decide_and_send(me, at(8, 2), vapid)
    seed.turns(db, me.id, TODAY, typed=1)
    assert svc.decide_and_send(me, at(11, 3), vapid) == ("nudge_1", "practised")
    assert svc.decide_and_send(me, at(14, 3), vapid) is None
    assert len(service.sent) == 1


def test_a_nudge_that_falls_due_after_nine_in_the_evening_is_dropped(
    learners, service, vapid, db
) -> None:
    me, _ = learners(morning=time(19, 0))
    assert svc.decide_and_send(me, at(19, 2), vapid) == ("reminder", "sent")
    assert svc.decide_and_send(me, at(22, 3), vapid) == ("nudge_1", "late")
    assert len(service.sent) == 1


def test_the_bot_ladder_owns_the_nudges_on_a_day_it_delivered(
    learners, service, vapid, db
) -> None:
    me, _ = learners(telegram=True)
    db.execute(
        "INSERT INTO sessions (user_id, date, task_type, delivered_at) VALUES (%s, %s, 'quiz', %s)",
        (me.id, TODAY, at(8, 0)),
    )
    db.commit()
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "sent")
    assert svc.decide_and_send(me, at(11, 3), vapid) == ("nudge_1", "bot_ladder")
    assert len(service.sent) == 1


# ── the ceiling ──────────────────────────────────────────────────────────────


def test_the_fourth_message_of_a_day_is_never_sent(learners, service, vapid, db) -> None:
    """The bot has sent two Telegram messages today; the reminder is the third;
    the first nudge would be the fourth and is dropped — not queued."""
    me, _ = learners(telegram=True)
    db.execute(
        "INSERT INTO bot_message_counts (user_id, local_date, count) VALUES (%s, %s, 2)",
        (me.id, TODAY),
    )
    db.commit()
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "sent")
    assert svc.decide_and_send(me, at(11, 3), vapid) == ("nudge_1", "ceiling")
    assert svc.decide_and_send(me, at(14, 3), vapid) is None
    assert len(service.sent) == 1
    assert _count(db, me.id) == 3
    assert _rows(db, me.id) == {"reminder": "sent", "nudge_1": "ceiling"}


def test_the_slot_reservation_never_hands_out_a_fourth_under_contention(learners, db) -> None:
    me, _ = learners(subscribed=False)

    def reserve(_):
        with connection() as conn:
            ok = reserve_message_slot(conn, me.id, TODAY)
            conn.commit()
            return ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        granted = list(pool.map(reserve, range(12)))
    assert sum(granted) == 3
    assert _count(db, me.id) == 3


# ── reachability ─────────────────────────────────────────────────────────────


def test_a_telegram_learner_with_no_browser_is_noted_quietly(
    learners, service, vapid, db, caplog
) -> None:
    me, _ = learners(telegram=True, subscribed=False)
    with caplog.at_level(logging.INFO, logger="core.services.push"):
        assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "no_subscription")
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert service.sent == [] and _count(db, me.id) == 0


def test_a_learner_with_no_channel_at_all_is_logged_loud(
    learners, service, vapid, db, caplog
) -> None:
    """#95: no browser AND no Telegram. Loud, once, and a user id only."""
    me, _ = learners(subscribed=False)
    with caplog.at_level(logging.INFO, logger="core.services.push"):
        assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "no_channel")
        assert svc.decide_and_send(me, at(8, 7), vapid) is None
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [f"push: no reachable channel user_id={me.id}"]


def test_a_gone_subscription_is_deleted_and_the_push_counts_as_failed(
    learners, service, vapid, db
) -> None:
    me, browser = learners()
    service.state["status"] = 410
    assert svc.decide_and_send(me, at(8, 2), vapid) == ("reminder", "failed")
    db.rollback()
    assert db.execute(
        "SELECT count(*) FROM push_subscriptions WHERE endpoint = %s", (browser.endpoint,)
    ).fetchone()[0] == 0


def test_a_crash_after_the_claim_never_sends_twice(learners, monkeypatch, vapid, db) -> None:
    """The decision row is committed before the send: a process that dies
    mid-send loses that push, and the next tick does not repeat it."""
    me, _ = learners()
    calls: list[str] = []

    def dies(url, **_k):
        calls.append(url)
        raise RuntimeError("the worker died mid-send")

    monkeypatch.setattr("core.push_api.httpx.post", dies)
    with pytest.raises(RuntimeError):
        svc.decide_and_send(me, at(8, 2), vapid)
    assert svc.decide_and_send(me, at(8, 7), vapid) is None
    assert len(calls) == 1
    assert _rows(db, me.id) == {"reminder": "sending"}


# ── the pass ─────────────────────────────────────────────────────────────────


def test_two_learners_get_their_own_decisions(learners, service, vapid, db, monkeypatch) -> None:
    a, a_browser = learners()
    b, b_browser = learners()
    seed.turns(db, a.id, TODAY, typed=1)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", vapid.private_key)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", vapid.public_key)
    monkeypatch.setenv("VAPID_SUBJECT", vapid.subject)
    everyone = svc.list_push_learners
    monkeypatch.setattr(svc, "list_push_learners", lambda: [l for l in everyone() if l.id in (a.id, b.id)])
    report = svc.run_push_pass(load_settings(), at(8, 2))
    assert sorted(report.decisions) == sorted(
        [(a.id, "reminder", "practised"), (b.id, "reminder", "sent")]
    )
    assert [url for url, _ in service.sent] == [b_browser.endpoint]


def test_the_pass_sends_nothing_without_vapid_and_says_so(service, monkeypatch, caplog) -> None:
    for key in ("VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "VAPID_SUBJECT"):
        monkeypatch.setenv(key, "")
    with caplog.at_level(logging.ERROR, logger="core.services.push"):
        report = svc.run_push_pass(load_settings(), at(8, 2))
    assert report.decisions == [] and service.sent == []
    assert any("VAPID keys are not set" in r.getMessage() for r in caplog.records)
