"""W32b — instant meaning: `GET /video/{id}/meanings`, and Save from the dictionary.

**Through the real ASGI transport** (CLAUDE.md §3 rule 1). The netguard is armed
session-wide, so a model call on either request path raises inside the request.

WHAT THE LEARNER DOES, PER TEST: opens `/watch` (the map arrives in one
request), hovers or taps a word (no request — the web suite and Playwright
prove that half), and presses Save in the sheet.

**RED BEFORE THE CODE (2026-09-28):** the route did not exist (404), and a
word with a dictionary entry but no `video_glosses` row answered `pending`.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import secrets
from pathlib import Path

import httpx
import pytest
from psycopg.types.json import Jsonb

from core.services import dictionary
from core.services import glosses as glosses_svc
from tests.test_video_route import (  # noqa: F401 -- fixtures, by name
    ID_PREFIX,
    _as,
    _assign_today,
    app,
    auth_env,
    db,
    learner,
    request,
)

TEXT = (
    "we went out last night. the parties were great. I loved the band. "
    "Thank you, Dr. Phillips. It was zqwblip."
)
CONTRACT = Path(__file__).resolve().parents[1] / "apps" / "web" / "lib" / "meaning-keys.contract.json"
MODEL = "w32b-test"


@pytest.fixture
def me(db, learner):
    yield learner
    db.rollback()
    db.execute("DELETE FROM word_saves_pending WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (learner.user_id,))
    db.commit()


@pytest.fixture
def video(db, me) -> int:
    return _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")


@pytest.fixture
def entries(db):
    """Dictionary rows written by this file, removed after each test. **A word
    the dev dictionary already holds is not overwritten** — the test skips."""

    def add(lemma, register="neutral", senses=None, kind="word", neutral=None, who=None):
        if db.execute("SELECT 1 FROM word_dictionary WHERE lemma = %s", (lemma,)).fetchone():
            pytest.skip(f"the dev dictionary already holds {lemma!r}")
        senses = senses if senses is not None else [
            {"pos": "noun", "definition": f"what {lemma} means",
             "l1": {"fa": "فارسی", "lt": "lietuviškai"}}
        ]
        db.execute(
            "INSERT INTO word_dictionary (lemma, kind, senses, register, neutral_equivalent, "
            "who_says_this, model, source) VALUES (%s, %s, %s, %s, %s, %s, %s, 'backfill')",
            (lemma, kind, Jsonb(senses if kind == "word" else []),
             register if kind == "word" else None, neutral, who, MODEL),
        )
        db.commit()

    yield add
    db.rollback()
    db.execute("DELETE FROM word_dictionary WHERE model = %s", (MODEL,))
    db.commit()


def _get(app, path, *, cookies=None, headers=None) -> httpx.Response:
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.get(path, headers=headers or {})

    return asyncio.run(_go())


def _meanings(app, me, video, *, gzip_ok=True):
    headers = {"Accept-Encoding": "gzip" if gzip_ok else "identity"}
    return _get(app, f"/video/{video}/meanings", cookies=_as(me), headers=headers)


def _save(app, me, video, word, line=None):
    body = {"word": word} if line is None else {"word": word, "line": line}
    return request(app, "POST", f"/video/{video}/save-word", json_body=body, cookies=_as(me))


def _cards(db, me):
    return db.execute(
        "SELECT card_type, front, back, register, meaning, neutral_equivalent, who_says_this, "
        "lexeme_id, context_sentence FROM cards WHERE user_id = %s ORDER BY card_type",
        (me.user_id,),
    ).fetchall()


# ── the map ─────────────────────────────────────────────────────────────────


def test_the_map_requires_a_session_and_your_video(app, db, me) -> None:
    assert _get(app, "/video/1/meanings").status_code == 401
    other = _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")
    db.execute("DELETE FROM video_assignments WHERE video_id = %s", (other,))
    db.commit()
    assert _meanings(app, me, other).status_code == 404


def test_one_request_carries_every_meaning_the_page_can_show(app, db, me, video, entries) -> None:
    """User action: opening `/watch`. The learner is `fa` (the fixture's)."""
    entries("band")
    entries("party", senses=[
        {"pos": "noun", "definition": "a social event", "l1": {"fa": "مهمانی", "lt": "vakarėlis"}},
        {"pos": "noun", "definition": "a political group", "l1": {"fa": "حزب", "lt": "partija"}},
    ])
    glosses_svc.insert_gloss(
        db, video_id=video, word="band", context_sentence="I loved the band.", cue_start_s=None,
        definition="a group that plays music together", register="neutral",
        neutral_equivalent=None, who_says_this=None, model=MODEL,
        l1={"fa": "گروه موسیقی", "lt": "grupė"}, source="manual",
    )
    db.commit()
    response = _meanings(app, me, video)
    assert response.status_code == 200
    body = response.json()
    assert body["l1"] == "fa"
    assert body["entries"]["party"] == {
        "k": "w", "r": "neutral",
        "s": [["noun", "a social event", "مهمانی"], ["noun", "a political group", "حزب"]],
    }
    assert body["forms"]["parties"] == "party"          # the page taps the surface
    assert "phillips" in body["names"]                   # W31e's name rule
    assert body["here"]["band"]["d"] == "a group that plays music together"
    assert body["here"]["band"]["l1"] == "گروه موسیقی"
    assert "vakarėlis" not in response.text and "partija" not in response.text, (
        "only the learner's own language travels"
    )
    assert body["saved"] == {}


def test_the_map_is_gzipped_when_the_browser_asks(app, me, video, entries) -> None:
    entries("band")
    zipped = _meanings(app, me, video)
    assert zipped.headers.get("content-encoding") == "gzip"
    assert zipped.headers.get("vary", "").lower() == "accept-encoding"
    plain = _meanings(app, me, video, gzip_ok=False)
    assert "content-encoding" not in plain.headers
    assert zipped.json() == plain.json()
    assert "no-store" in plain.headers.get("cache-control", "")


def test_the_map_names_what_this_learner_already_saved(app, db, me, video, entries) -> None:
    entries("band")
    assert _save(app, me, video, "band").json()["state"] == "saved"
    assert _meanings(app, me, video).json()["saved"] == {"band": "in_deck"}


# ── Save from the dictionary (§D) ────────────────────────────────────────────


def test_a_neutral_dictionary_word_saves_at_once_with_its_lexeme(app, db, me, video, entries) -> None:
    """The operator's finding: *moving*, *over* — any word. Tapped as *parties*
    (the lemma's entry), saved in the line it was tapped in, no pending state."""
    entries("party")
    response = _save(app, me, video, "parties", line=1)
    assert (response.status_code, response.json()["state"]) == (200, "saved")
    rows = _cards(db, me)
    party = db.execute("SELECT id FROM lexemes WHERE lemma = 'party'").fetchone()[0]
    assert [r[0] for r in rows] == ["cloze", "production"]
    assert {(r[1], r[2], r[3], r[7], r[8]) for r in rows} == {
        ("party", "what party means", "neutral", party, "the parties were great.")
    }
    assert db.execute("SELECT count(*) FROM word_saves_pending WHERE user_id = %s",
                      (me.user_id,)).fetchone()[0] == 0


def test_a_word_off_the_list_saves_with_no_lexeme(app, db, me, video, entries) -> None:
    assert db.execute("SELECT 1 FROM lexemes WHERE lemma = 'zqwblip'").fetchone() is None
    entries("zqwblip")
    assert _save(app, me, video, "zqwblip", line=4).json()["state"] == "saved"
    assert {r[7] for r in _cards(db, me)} == {None}


@pytest.mark.parametrize(
    ("register", "types", "meaning_set"),
    [
        ("formal", ["cloze", "production"], False),
        ("informal", ["audio", "recognition"], True),
        ("slang", ["audio", "recognition"], True),
        ("taboo", ["audio", "recognition"], False),
    ],
)
def test_each_register_keeps_its_card_pair(app, db, me, video, entries, register, types, meaning_set) -> None:
    """The register rules, unchanged: informal, slang and taboo are receptive
    only, and informal/slang carry the four things (013's CHECKs)."""
    four = register in ("informal", "slang")
    entries("band", register=register,
            neutral="group" if four else None, who="friends, casually" if four else None)
    assert _save(app, me, video, "band", line=2).json()["state"] == "saved"
    rows = _cards(db, me)
    assert [r[0] for r in rows] == types
    assert all(r[3] == register for r in rows)
    assert all((r[4] is not None) == meaning_set for r in rows)
    if four:
        assert {(r[5], r[6]) for r in rows} == {("group", "friends, casually")}
    if register != "formal":
        assert {r[7] for r in rows} == {None}


def test_the_videos_own_gloss_beats_the_dictionary(app, db, me, video, entries) -> None:
    """Context beats dictionary (§C): the card carries the meaning IN THIS LINE."""
    entries("band")
    glosses_svc.insert_gloss(
        db, video_id=video, word="band", context_sentence="I loved the band.", cue_start_s=None,
        definition="a group that plays music together", register="neutral",
        neutral_equivalent=None, who_says_this=None, model=MODEL, l1={}, source="manual",
    )
    db.commit()
    _save(app, me, video, "band", line=2)
    assert {r[2] for r in _cards(db, me)} == {"a group that plays music together"}


def test_a_name_and_a_word_with_no_entry_still_wait(app, db, me, video, entries) -> None:
    entries("phillips", kind="name")
    assert _save(app, me, video, "phillips", line=3).json()["state"] == "pending"
    assert _save(app, me, video, "band", line=2).json()["state"] == "pending"
    assert _cards(db, me) == []


def test_saving_twice_is_already_saved(app, db, me, video, entries) -> None:
    entries("band")
    assert _save(app, me, video, "band", line=2).json()["state"] == "saved"
    assert _save(app, me, video, "band", line=2).json()["state"] == "already_saved"


def test_the_sheet_route_falls_back_to_the_dictionary(app, db, me, video, entries) -> None:
    """`GET /video/{id}/word` is the sheet's fallback when the map failed to
    load; it shows the dictionary's first sense when the video has no gloss."""
    entries("band")
    body = request(app, "GET", f"/video/{video}/word?w=band&line=2", cookies=_as(me)).json()
    assert body["meaning"]["definition"] == "what band means"
    assert (body["meaning"]["l1"], body["meaning"]["l1_language"]) == ("فارسی", "fa")


# ── the token contract, shared with the web suite ────────────────────────────


def test_the_server_reads_the_page_tokens_the_way_the_client_does() -> None:
    """`apps/web/lib/meaning-keys.contract.json` is read by this test AND by
    Vitest (`meanings.test.ts`): the same line text must yield the same tokens
    on both sides, or a hover finds nothing the server keyed (W31a's pattern)."""
    cases = json.loads(CONTRACT.read_text(encoding="utf-8"))["lines"]
    assert cases
    for case in cases:
        assert dictionary.page_tokens(case["text"]) == case["tokens"], case["text"]


def test_the_payload_bytes_can_be_measured_read_only(app, db, me, video, entries, caplog) -> None:
    """`--payload VIDEO --user U` (W32d's host line) prints raw and gzip bytes."""
    from core.video import dictionary as command

    entries("band")
    caplog.set_level("INFO")
    assert command.main(["--payload", str(video), "--user", str(me.user_id)]) == 0
    line = next(r.message for r in caplog.records if r.message.startswith(f"video={video} "))
    raw = int(line.split("raw_bytes=")[1].split()[0])
    zipped = int(line.split("gzip_bytes=")[1].split()[0])
    body = json.dumps(dictionary.meanings_for(me.user_id, video), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    assert raw == len(body)
    assert zipped == len(gzip.compress(body, mtime=0))


def test_the_web_fixture_has_the_wires_shape(app, db, me, video, entries) -> None:
    """The e2e and Vitest map (`write.fixture.json`'s `watch_meanings`) is built
    by `assemble_meanings`; this holds its keys to a real ASGI body's (#190)."""
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "apps" / "web" / "components" / "write"
         / "write.fixture.json").read_text(encoding="utf-8")
    )["watch_meanings"]
    entries("party", register="informal", neutral="event", who="friends")
    glosses_svc.insert_gloss(
        db, video_id=video, word="band", context_sentence="I loved the band.", cue_start_s=None,
        definition="a group", register="neutral", neutral_equivalent=None, who_says_this=None,
        model=MODEL, l1={"fa": "گروه"}, source="manual",
    )
    db.commit()
    wire = _meanings(app, me, video).json()
    assert set(fixture) == set(wire)
    assert set(fixture["entries"]["okay"]) == set(wire["entries"]["party"])
    assert set(fixture["here"]["mastodon"]) == set(wire["here"]["band"])
