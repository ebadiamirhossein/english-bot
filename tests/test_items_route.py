"""W6: the item routes through the real ASGI transport.

CLAUDE.md §3 rule 1, and ARCHITECTURE §10 rule 5. Nothing here calls a route
function or a service directly; every request goes through `httpx.ASGITransport`
into the app `uvicorn apps.api.main:app` serves. In v2, 161 unit tests were green
over a dead dispatch path because every one of them called the handler directly.

**The leak assertions are the point of this file.**
`tests/test_items_projection.py` already asserts, per type, that the answer is
absent from `visible_projection`. The route is where a *second* serialiser would
appear, so the assertion has to exist there too — against the bytes a browser
receives, not against the function that produced them.

No model call is made and none is stubbed: grading is
`core.items.grading.grade_text`, which is deterministic and free. The three
audio types are read but never synthesised — `netguard` would raise, which is
how we know.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.items import ITEM_TYPES, RESPONSE_MODE
from core.items.gates import ValidationReport
from core.items.grading import fold, normalise_variants
from core.items.schema import parse
from core.services import items as svc

FIXTURES = Path(__file__).parent / "fixtures" / "items" / "valid.json"
VALID = json.loads(FIXTURES.read_text(encoding="utf-8"))
BY_TYPE = {row["item"]["item_type"]: row["item"] for row in VALID}

PASSED = ValidationReport("passed")

# The six types whose answer is necessarily on screen, DERIVED and never written
# out. For the five `tap` types the task is *selecting* the answer, not recalling
# it, and a projection that hid it would be unanswerable; `speak_repeat`'s answer
# IS its prompt. Writing the list by hand is how it goes stale by one — which is
# a test that either fails a correct item or exempts the wrong one.
ANSWER_ON_SCREEN = {t for t in ITEM_TYPES if RESPONSE_MODE[t] == "tap"} | {
    "speak_repeat"
}


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unique rate-limit salt per test, so one test cannot 429 the next."""
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


def _make_learner(db, label: str):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, explanation_language_fallback,
                           auth_email, auth_user_id, timezone)
        VALUES (%s, %s, 'fa', TRUE, 'B1', TRUE, %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            label,
            f"w6-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, %s, 'approved')",
        (telegram_user_id, user_id, label),
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
    return user_id, raw


def _drop_learner(db, user_id: int) -> None:
    db.execute("DELETE FROM item_attempts WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM items WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM errors WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


@pytest.fixture
def learner(db):
    user_id, raw = _make_learner(db, "W6 Learner")
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    _drop_learner(db, user_id)


def _item(item_type: str):
    draft = dict(BY_TYPE[item_type])
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


@pytest.fixture
def bank(learner):
    """All eleven types in this learner's bank, written by the real service.

    Through `insert_item`, which refuses a report that is not `ok` — so the rows
    these tests read carry a real validation record, the same as a generated one.
    """
    ids: dict[str, int] = {}
    for item_type in ITEM_TYPES:
        item_id = svc.insert_item(
            learner.user_id, _item(item_type), PASSED, model="w6-test"
        )
        assert item_id is not None, item_type
        ids[item_type] = item_id
    return ids


def request(app, method, path, *, json_body=None, cookies=None, headers=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(
                method, path, json=json_body, headers=headers or {}
            )

    return asyncio.run(_go())


def _as(learner, extra=None):
    cookies = {SESSION_COOKIE_SECURE: learner.cookie}
    return cookies, {"content-type": "application/json", **(extra or {})}


# ── reading the bank ─────────────────────────────────────────────────────────


def test_the_bank_lists_every_type_as_a_projection(app, learner, bank) -> None:
    """User action: opening /practice."""
    cookies, _ = _as(learner)
    response = request(app, "GET", "/items?limit=50", cookies=cookies)
    assert response.status_code == 200
    body = response.json()
    assert {row["projection"]["item_type"] for row in body} == set(ITEM_TYPES)
    for row in body:
        assert row["response_mode"] == RESPONSE_MODE[row["projection"]["item_type"]]


def _envelope_text(app, learner, bank, item_type) -> tuple[str, str]:
    """This item's own envelope, from both read routes, as JSON text.

    **Scoped to the one envelope on purpose.** Four of the eleven fixtures share
    the answer `"went"` — it is `cloze_cued`'s answer, an `mcq` option, a
    `word_bank_order` bank token and `error_spot`'s correction — so scanning the
    whole list body for one item's answer would fail on a projection that is
    perfectly correct, and would be measuring what the *other* fixtures contain.
    A leak assertion has to measure the artefact it reports on.
    """
    cookies, _ = _as(learner)
    listed = request(app, "GET", "/items?limit=50", cookies=cookies).json()
    mine = next(
        row for row in listed if row["projection"]["item_type"] == item_type
    )
    single = request(
        app, "GET", f"/items/{bank[item_type]}", cookies=cookies
    ).json()
    assert single["projection"] == mine["projection"], (
        f"{item_type} serialises differently on the two read routes"
    )
    return (
        json.dumps(mine, ensure_ascii=False),
        json.dumps(single, ensure_ascii=False),
    )


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_no_response_body_carries_the_answer(app, learner, bank, item_type) -> None:
    """User action: opening any item — and the assertion that matters.

    Substring, not equality: an answer embedded in another field still leaks it.
    Every stored `accepted_variant` is checked too, because widening an item is
    exactly how a second acceptable string becomes invisible to a narrower test.
    """
    if item_type in ANSWER_ON_SCREEN:
        pytest.skip("the answer is necessarily on screen; see the test below")
    item = _item(item_type)
    for blob in _envelope_text(app, learner, bank, item_type):
        folded = fold(blob)
        if item.answer:
            assert fold(item.answer) not in folded, f"{item_type} leaks its answer"
        for variant in item.accepted_variants:
            assert fold(variant) not in folded, f"{item_type} leaks a variant"


@pytest.mark.parametrize("item_type", sorted(ANSWER_ON_SCREEN))
def test_the_discriminator_stays_hidden_where_the_answer_is_on_screen(
    app, learner, bank, item_type
) -> None:
    """The other half of the exemption, asserted per type rather than assumed.

    For these six the answer must be visible — the task is *selecting* it, and
    `speak_repeat`'s answer is its prompt. What must stay hidden is **which
    one**: the wrong tile's index and its correction, and the pairing.
    """
    for blob in _envelope_text(app, learner, bank, item_type):
        for hidden in (
            "wrong_index",
            "correction",
            "pairs",
            "transcript",
            "rubric",
            "cue_type",
            "accepted_variants",
        ):
            # As a JSON *key*: `"pairs"` is a substring of the value
            # `"match_pairs"`, and a bare-substring check would fail a
            # projection that is exactly right. The values are covered below and
            # by the answer-leak test above.
            assert f'"{hidden}":' not in blob, f"{item_type} projects {hidden}"

    if item_type == "error_spot":
        # The correction is the word the tile should have been — the answer
        # wearing a different hat, and absent from this item's own envelope.
        for blob in _envelope_text(app, learner, bank, item_type):
            assert fold(BY_TYPE["error_spot"]["correction"]) not in fold(blob)


# ── #116: value-level, where key-level was all there was ───────────────────
#
# The two tests above assert **key names**. For `word_bank_order` and
# `match_pairs` that is the weakest possible check exactly where the answer is
# on screen: tiles arriving pre-sorted into the correct order would pass both,
# and the item would be unanswerable-by-being-trivial rather than by leaking a
# field. `checks._word_bank`'s `bank_already_ordered` failure covers the
# generator's side; nothing covered the serving side. Verified not happening on
# production 2026-08-25 — the tiles came shuffled — but nothing enforced it.


def _projection(app, learner, bank, item_type: str) -> dict:
    cookies, _ = _as(learner)
    response = request(app, "GET", f"/items/{bank[item_type]}", cookies=cookies)
    assert response.status_code == 200
    return response.json()["projection"]


def test_the_word_bank_is_not_served_in_the_answer_order(app, learner, bank) -> None:
    """The whole task is ordering, so serving the order IS serving the answer.

    Asserted against the value the browser receives, not against the function
    that produced it — the route is where a second serialiser would appear.
    """
    bank_tokens = _projection(app, learner, bank, "word_bank_order")["bank"]
    answer = BY_TYPE["word_bank_order"]["answer"]
    assert bank_tokens != answer.rstrip(".?!").split(), (
        "the word bank arrived already in the correct order"
    )
    assert " ".join(bank_tokens) != answer


def test_the_match_pairs_columns_are_not_served_index_aligned(
    app, learner, bank
) -> None:
    """Two columns in the same order ARE the bijection, key or no key.

    `visible_projection` sorts each column independently, which destroys the
    pairing. This asserts the destruction rather than trusting the sort — a
    payload whose pairs happen to be alphabetical in both columns would be
    served solved, and only a value-level check sees it.
    """
    projection = _projection(app, learner, bank, "match_pairs")
    left, right = projection["left"], projection["right"]
    true_pairs = {l: r for l, r in BY_TYPE["match_pairs"]["pairs"]}
    if len(left) < 2:
        pytest.skip("a one-pair fixture cannot be mis-ordered")
    aligned = [true_pairs[l] for l in left]
    assert right != aligned, (
        "the two columns arrived index-aligned — the pairing was served intact"
    )


def test_another_learners_item_is_not_found(app, db, learner, bank) -> None:
    """User action: typing someone else's item id into the URL.

    404 rather than 403: telling a caller that an id exists but belongs to
    someone else is a fact about the other learner.
    """
    other_id, other_cookie = _make_learner(db, "W6 Other")
    try:
        response = request(
            app,
            "GET",
            f"/items/{bank['mcq']}",
            cookies={SESSION_COOKIE_SECURE: other_cookie},
        )
        assert response.status_code == 404
    finally:
        _drop_learner(db, other_id)


def test_the_routes_require_a_session(app, learner, bank) -> None:
    """User action: opening the app signed out."""
    for method, path in (
        ("GET", "/items"),
        ("GET", f"/items/{bank['mcq']}"),
        ("POST", f"/items/{bank['mcq']}/answer"),
        ("GET", f"/items/{bank['dictation']}/audio"),
    ):
        response = request(
            app, method, path, json_body={} if method == "POST" else None,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 401, path


# ── answering ────────────────────────────────────────────────────────────────


def _answer(app, learner, item_id, body):
    cookies, headers = _as(learner)
    return request(
        app, "POST", f"/items/{item_id}/answer",
        json_body=body, cookies=cookies, headers=headers,
    )


def test_a_typed_answer_ignores_case_and_trailing_punctuation(
    app, learner, bank
) -> None:
    """The task row's own criterion, through the real route.

    "Typed items never require punctuation or capitalisation to match" is about
    `fold_answer` being permissive on the server — **not** about the keyboard
    fixing things first, which is why the input refuses autocorrect and why the
    human check types it on a phone.
    """
    for typed in ("went", "WENT", "  Went. ", "went!"):
        response = _answer(app, learner, bank["cloze_cued"], {"text": typed})
        assert response.status_code == 200, typed
        assert response.json()["correct"] is True, typed


def test_the_verbatim_response_is_kept_unnormalised(app, db, learner, bank) -> None:
    """"What did they actually type" cannot be recovered from "did it match".

    W7's leech rewrite reads this column, so the folded form is not enough.
    """
    _answer(app, learner, bank["cloze_cued"], {"text": "  Went. "})
    row = db.execute(
        "SELECT response_text, graded_by, attempt_no, hint_used, grade, "
        "audio_seconds FROM item_attempts WHERE item_id = %s",
        (bank["cloze_cued"],),
    ).fetchone()
    assert row[0] == "  Went. "
    assert row[1] == "deterministic"
    # W6 fixes the meaning migration 012 left open: `attempt_no` counts attempts
    # within one encounter, and W6 allows no retry, because feedback reveals the
    # canonical answer and a second attempt then measures reading.
    assert row[2] == 1
    assert row[3] is False   # no cue affordance exists (#105)
    assert row[4] is None    # FSRS grade is W7's reviewer
    assert row[5] is None    # no audio is captured at all


def test_a_tapped_option_is_recorded_as_chosen_option(app, db, learner, bank) -> None:
    """User action: tapping a distractor.

    "Which distractor pulls people" is the most actionable generator-quality
    signal there is, and it cannot be reconstructed from a boolean.
    """
    response = _answer(app, learner, bank["mcq"], {"option": "goed"})
    assert response.json()["correct"] is False
    row = db.execute(
        "SELECT chosen_option, correct FROM item_attempts WHERE item_id = %s",
        (bank["mcq"],),
    ).fetchone()
    assert row[0] == "goed"
    assert row[1] is False


def test_a_tapped_tile_grades_by_index_and_records_the_word(
    app, db, learner, bank
) -> None:
    """User action: tapping the word that is the mistake.

    The client sends an index; the server resolves it against the stored tiles,
    so a client cannot submit a tile that was never shown.
    """
    assert _answer(app, learner, bank["error_spot"], {"tile_index": 1}).json()[
        "correct"
    ]
    assert not _answer(app, learner, bank["error_spot"], {"tile_index": 0}).json()[
        "correct"
    ]
    row = db.execute(
        "SELECT chosen_option, response_payload FROM item_attempts "
        "WHERE item_id = %s ORDER BY id",
        (bank["error_spot"],),
    ).fetchone()
    assert row[0] == "goed"
    assert row[1] == {"tile_index": 1}


def test_a_word_bank_ordering_grades_and_is_kept(app, db, learner, bank) -> None:
    """User action: building the sentence out of the bank."""
    right = ["I", "went", "to", "the", "shops"]
    assert _answer(app, learner, bank["word_bank_order"], {"order": right}).json()[
        "correct"
    ]
    wrong_order = ["shops", "I", "went", "to", "the"]
    assert not _answer(
        app, learner, bank["word_bank_order"], {"order": wrong_order}
    ).json()["correct"]
    row = db.execute(
        "SELECT response_payload, chosen_option FROM item_attempts "
        "WHERE item_id = %s ORDER BY id",
        (bank["word_bank_order"],),
    ).fetchone()
    assert row[0] == {"order": right}
    # No single option to name — NULL here is a decision, not a gap.
    assert row[1] is None


def test_a_pair_mapping_grades_as_a_bijection(app, learner, bank) -> None:
    """User action: joining every word to its meaning.

    `match_pairs` has `answer IS NULL` by schema rule, so `grade_text` would
    fold `None` and mark every submission wrong. It is compared as a mapping,
    folded with the same `grading.fold` — one fold, still no fourth.
    """
    pairs = {left: right for left, right in BY_TYPE["match_pairs"]["pairs"]}
    assert _answer(app, learner, bank["match_pairs"], {"pairs": pairs}).json()[
        "correct"
    ]
    swapped = dict(pairs)
    keys = list(swapped)
    swapped[keys[0]], swapped[keys[1]] = swapped[keys[1]], swapped[keys[0]]
    assert not _answer(app, learner, bank["match_pairs"], {"pairs": swapped}).json()[
        "correct"
    ]
    assert not _answer(app, learner, bank["match_pairs"], {"pairs": {}}).json()[
        "correct"
    ]


def test_a_spoken_item_is_self_marked_and_says_so(app, db, learner, bank) -> None:
    """User action: saying the sentence and marking yourself. Ruled 2026-08-25.

    `graded_by` is what keeps this separable from a string match. Without it an
    accuracy number silently mixes three instruments and W19's progress line
    stops being comparable over time.
    """
    for item_type in ("speak_repeat", "speak_answer"):
        body = _answer(app, learner, bank[item_type], {"self_marked": True}).json()
        assert body["correct"] is True
        assert body["graded_by"] == "self"
    assert not _answer(app, learner, bank["speak_answer"], {"self_marked": False}).json()[
        "correct"
    ]
    audio = db.execute(
        "SELECT DISTINCT audio_seconds FROM item_attempts WHERE user_id = %s",
        (learner.user_id,),
    ).fetchall()
    # No audio is captured in W6, so there is nothing to discard and nothing to
    # measure. `audio_seconds` belongs to the learner's speech, not to playback.
    assert audio == [(None,)]


def test_an_empty_submission_grades_as_wrong_rather_than_erroring(
    app, learner, bank
) -> None:
    """A client that sends the wrong field answers nothing, which is not correct."""
    response = _answer(app, learner, bank["mcq"], {"text": "went"})
    assert response.status_code == 200
    assert response.json()["correct"] is False


def test_the_answer_body_carries_the_canonical_only_after_grading(
    app, learner, bank
) -> None:
    """Returning the answer *with the verdict* is the feedback, not a leak.

    It arrives in a different type from the one the item was fetched with, which
    is what makes before-grading and after-grading two shapes rather than one
    shape with a nullable field somebody forgets to check.
    """
    body = _answer(app, learner, bank["cloze_cued"], {"text": "nope"}).json()
    assert body["correct"] is False
    assert body["canonical"] == "went"
    # Neither exists on any item today — see #103 and #104.
    assert body["explanation"] is None
    assert body["murphy_units"] is None


# ── the journal, and the ledger ──────────────────────────────────────────────


def test_answering_writes_no_errors_and_no_user_lexemes(
    app, db, learner, bank
) -> None:
    """**The sharpest assertion in the slice**, and it measures what it reports.

    `errors.source` was widened at 012 to include `item`, and after W6 that
    value still has no writer. A tapped wrong option is a *selection*, not
    self-produced English; a spoken response is not captured at all; and a typed
    miss is not necessarily a grammar error — a missed `dictation` is a
    listening failure, and an `l1_to_l2_production` canonical is trusted rather
    than verified (#102). A wrong journal row is permanent damage; a missing one
    is recoverable. W11 revisits it with a real classification step (#107).

    W5 also excluded `item` from the lexicon harvest allow-list. Rather than
    re-assert the classification, this answers every item both right and wrong
    and counts the rows.
    """
    before_errors = db.execute(
        "SELECT count(*) FROM errors WHERE user_id = %s", (learner.user_id,)
    ).fetchone()[0]
    before_lexemes = db.execute(
        "SELECT count(*) FROM user_lexemes WHERE user_id = %s", (learner.user_id,)
    ).fetchone()[0]

    for item_type, item_id in bank.items():
        item = _item(item_type)
        _answer(app, learner, item_id, {"text": item.answer or "something"})
        _answer(app, learner, item_id, {"text": "definitely not the answer"})
        _answer(app, learner, item_id, {"option": "goed", "tile_index": 0})
        _answer(app, learner, item_id, {"self_marked": False})

    assert (
        db.execute(
            "SELECT count(*) FROM errors WHERE user_id = %s", (learner.user_id,)
        ).fetchone()[0]
        == before_errors
    )
    assert (
        db.execute(
            "SELECT count(*) FROM user_lexemes WHERE user_id = %s",
            (learner.user_id,),
        ).fetchone()[0]
        == before_lexemes
    )


# ── the columns W6 is the first slice able to write ──────────────────────────


def test_cue_shown_comes_from_the_row_and_not_from_the_client(
    app, db, learner, bank
) -> None:
    """User action: answering a repaired item that carries a cue.

    `visible_projection` hides the cue's *category* — it is a hint about what
    kind of answer is wanted — so a client could not report it correctly even if
    asked. The server reads it off the row it just fetched.
    """
    _answer(app, learner, bank["cloze_cued"], {"text": "went"})
    row = db.execute(
        "SELECT cue_shown FROM item_attempts WHERE item_id = %s",
        (bank["cloze_cued"],),
    ).fetchone()
    assert row[0] == BY_TYPE["cloze_cued"]["cue_type"] == "definition"

    body = request(
        app, "GET", f"/items/{bank['cloze_cued']}", cookies=_as(learner)[0]
    ).json()
    # The cue's text is shown; its category never is.
    assert body["projection"]["cue"] == "(past of go)"
    assert "cue_type" not in body["projection"]


@pytest.mark.parametrize(
    "sent,stored",
    [
        (1200, 1200),
        (0, 0),
        (svc.MAX_LATENCY_MS, svc.MAX_LATENCY_MS),
        (svc.MAX_LATENCY_MS + 1, None),
        (None, None),
    ],
)
def test_latency_outside_its_range_is_stored_as_null(
    app, db, learner, bank, sent, stored
) -> None:
    """User action: answering after putting the phone down for an hour.

    This is the one column W6 writes from a value the browser chose (#108), and
    W7's FSRS reads it. Ten minutes on one item is not a retrieval time, and a
    NULL is worth more than a number that means something else.
    """
    body = {"text": "went"}
    if sent is not None:
        body["latency_ms"] = sent
    _answer(app, learner, bank["cloze_cued"], body)
    row = db.execute(
        "SELECT latency_ms FROM item_attempts WHERE item_id = %s ORDER BY id DESC",
        (bank["cloze_cued"],),
    ).fetchone()
    assert row[0] == stored


# ── audio ────────────────────────────────────────────────────────────────────


def test_audio_is_offered_only_for_the_types_whose_content_is_sound(
    app, learner, bank, monkeypatch
) -> None:
    """User action: tapping play.

    The provider is stubbed at `core.speech.synthesize`, which is the transport
    boundary for the wrapper. That proves the route, the session gate and the
    content type. It does **not** prove the provider contract — `verify.py
    --live-audio` is what does that, and CLAUDE.md §3 rule 2 does not fire here
    because no request construction changed.
    """
    monkeypatch.setattr(
        "core.services.items.speech.synthesize", lambda text, **kw: b"ID3-audio"
    )
    cookies, _ = _as(learner)

    for item_type in ("dictation", "listening_gap", "speak_repeat"):
        response = request(app, "GET", f"/items/{bank[item_type]}/audio", cookies=cookies)
        assert response.status_code == 200, item_type
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.content == b"ID3-audio"

    for item_type in ("mcq", "cloze_cued", "match_pairs", "speak_answer"):
        response = request(app, "GET", f"/items/{bank[item_type]}/audio", cookies=cookies)
        assert response.status_code == 404, item_type


def test_the_audio_route_answers_bytes_and_never_the_text(
    app, learner, bank, monkeypatch
) -> None:
    """`listening_gap`'s spoken sentence IS its answer.

    It reaches the learner as sound, which is the exercise — and never as text,
    which is why `item_audio` synthesises inside the service and hands the route
    bytes it cannot read.
    """
    spoken: list[str] = []

    def _capture(text, **kw):
        spoken.append(text)
        return b"ID3-audio"

    monkeypatch.setattr("core.services.items.speech.synthesize", _capture)
    response = request(
        app, "GET", f"/items/{bank['listening_gap']}/audio", cookies=_as(learner)[0]
    )
    assert response.status_code == 200
    # The transcript was spoken...
    assert spoken == [BY_TYPE["listening_gap"]["transcript"]]
    # ...and appears nowhere in what crossed the wire.
    assert fold(BY_TYPE["listening_gap"]["transcript"]) not in fold(
        response.content.decode("latin-1")
    )


def test_a_speech_failure_is_a_503_with_no_provider_detail(
    app, learner, bank, monkeypatch
) -> None:
    """The service is up and answering; its dependency is not.

    A provider message on the wire is a free map of the backend (PRD §10), and
    to the learner "it did not play, tap again" is the whole of the useful
    information.
    """
    from core.speech import SpeechError

    def _boom(text, **kw):
        raise SpeechError("openai: 429 quota exceeded for org-12345")

    monkeypatch.setattr("core.services.items.speech.synthesize", _boom)
    response = request(
        app, "GET", f"/items/{bank['dictation']}/audio", cookies=_as(learner)[0]
    )
    assert response.status_code == 503
    assert "openai" not in response.text
    assert "org-12345" not in response.text


# ── the write path's own rules ───────────────────────────────────────────────


def test_the_answer_route_refuses_a_form_encoding(app, learner, bank) -> None:
    """A form body would make this a simple request, remove the CORS preflight,
    and remove the CSRF barrier this API relies on."""
    cookies, _ = _as(learner)

    async def _go():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.post(
                f"/items/{bank['mcq']}/answer", data={"option": "went"}
            )

    assert asyncio.run(_go()).status_code == 415


# ── the committed projections describe the wire, not a function ──────────────

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "apps" / "web" / "lib" / "items" / "projections.fixture.json"
)


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_the_committed_projections_match_the_wire(app, learner, bank, item_type) -> None:
    """What the Vitest renderers are given equals what a browser receives.

    `apps/web/lib/items/projections.fixture.json` is what the eleven renderer
    tests render against. If it describes a *function* while the route serves
    something else, both suites stay green and the seam silently stops being a
    contract — so the comparison is made against a real ASGI response body.

    **An earlier version of this test compared the fixture against
    `visible_projection` directly**, which is the function it is generated from.
    It passed and proved nothing: a fixture checked against its own source
    agrees with itself forever. That is the W5a lesson — the thing that verifies
    must measure the thing it reports on — and it is recorded here because the
    mistake was made once in this slice before it was caught.
    """
    committed = next(
        e
        for e in json.loads(FIXTURE.read_text(encoding="utf-8"))
        if e["projection"]["item_type"] == item_type
    )
    served = request(
        app, "GET", f"/items/{bank[item_type]}", cookies=_as(learner)[0]
    ).json()

    assert set(committed) == set(served), "the envelope shape drifted"
    assert committed["response_mode"] == served["response_mode"]
    assert committed["projection"] == served["projection"], (
        f"{item_type}: the committed projection is not what the route serves. "
        "Re-run `python scripts/export_item_projections.py`."
    )
