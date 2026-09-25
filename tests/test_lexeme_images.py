"""W13d — image cards for concrete vocabulary (migration 033, PRD §2.6.3).

What each block proves, and the user action it stands for (CLAUDE.md §3 rule 4):

- **the schema** — the asset table is GLOBAL (no `user_id`, read from
  `information_schema`), and the licence gate is a CHECK the loader cannot
  get round;
- **the gate** — `core.images.judge` over the metadata Commons really returned
  on 2026-09-25 (`tests/fixtures/commons/recorded-2026-09-25.json`), with the
  expected verdicts HARDCODED from reading that file, never derived from the
  function (rule 5);
- **the Wikimedia door** — the recorded exchanges replayed through
  `httpx.MockTransport`: exact-label matching, a 429 modelled on the one
  really received, `maxlag` sent to Commons and not to Wikidata, the contact in
  the User-Agent;
- **the card** — a learner opening `/review` (`GET /review/queue` through the
  ASGI transport) sees the picture and its credit on a picturable word's card,
  and nothing on an abstract word's, a phrase card's or a collocation card's;
  the browser then fetching the picture (`GET /lexeme-images/{id}.{ext}`);
- **the loader** — the operator's `--load --apply` against the dev database,
  including the refusals (a re-uploaded file, a changed licence) and a
  withdrawal.

**RED, each demonstrated before this file was committed** (`python -B`, caches
cleared — the W18 lesson): the image line removed from `card_face` (the queue
tests fail on `KeyError: 'image'`); `shows_picture` returning True for
`collocation` (the collocation test fails); `judge` admitting any licence (the
`Attribution` and NonCommercial cases fail); the 429 branch removed (the 429
test raises `CommonsError`); the author's-own-credit-line refusal removed (its
parametrised case passes the file); `maxlag` sent to Wikidata (the parameter test fails);
the SHA-1 comparison removed from `apply_line` (the re-upload test stores the
row); `lexeme_images.replace` updating in place (the new-id test fails); the
`--lemmas` lexicon check removed (the operator's-list test proposes a ghost).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.cards.fsrs import CardState
from core.config import load_settings
from core.images import (
    ALLOWED_LICENCES,
    IMAGE_CARD_TYPES,
    bytes_match,
    judge,
    licence_url,
    plain_text,
    shows_picture,
)
from core.images import bank
from core.images.commons_api import CommonsClient, CommonsError, user_agent
from core.services import cards as cards_svc
from core.services import lexeme_images

REPO = Path(__file__).resolve().parents[1]
RECORDED = REPO / "tests" / "fixtures" / "commons" / "recorded-2026-09-25.json"

#: Test lemmas are lower-case letters (the lexicon's `GROWABLE` shape) and
#: carry this prefix, so the global tables' teardown can name them (#340).
LEMMA_PREFIX = "zzwimg"

#: A JPEG's first bytes and some filler: enough for `bytes_match` and the
#: route, which never decode the picture.
JPEG = b"\xff\xd8\xff\xe0" + b"w13d-test-picture" * 20

SPOON_SHA1 = "91572801d525fd5607d45c86b6b89aaf8ed78b32"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


def _lemma() -> str:
    return LEMMA_PREFIX + "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))


def _purge_test_lexemes(db) -> None:
    db.execute(
        "DELETE FROM lexeme_images li USING lexemes l "
        "WHERE l.id = li.lexeme_id AND l.lemma LIKE %s",
        (f"{LEMMA_PREFIX}%",),
    )
    db.execute("DELETE FROM lexemes WHERE lemma LIKE %s", (f"{LEMMA_PREFIX}%",))
    db.commit()


@pytest.fixture
def lexemes(db):
    """Three test lemmas: `picturable`, `abstract` (no picture) and `other`."""
    made = {}
    for key in ("picturable", "abstract", "other"):
        lemma = _lemma()
        made[key] = (
            lemma,
            db.execute(
                "INSERT INTO lexemes (lemma, pos, origin) VALUES (%s, 'NOUN', 'grown') RETURNING id",
                (lemma,),
            ).fetchone()[0],
        )
    db.commit()
    yield made
    _purge_test_lexemes(db)


def _store(lexeme_id: int, **over) -> int:
    spec = dict(
        lexeme_id=lexeme_id,
        commons_file="File:SpoonCollection.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
        original_sha1=SPOON_SHA1,
        author="THOR",
        licence="CC BY 2.0",
        licence_url="https://creativecommons.org/licenses/by/2.0",
        mime="image/jpeg",
        width=330,
        height=215,
        data=JPEG,
    )
    spec.update(over)
    return lexeme_images.replace(**spec)


# ---------------------------------------------------------------------------
# the schema
# ---------------------------------------------------------------------------


def test_the_asset_table_has_no_user_id(db) -> None:
    """TASKS' W13d acceptance: *"the asset table has no `user_id`"*. Read from
    the database's own catalogue, not from the migration's text."""
    columns = {
        r[0]
        for r in db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'lexeme_images'"
        )
    }
    assert "lexeme_id" in columns and "bytes" in columns
    assert "user_id" not in columns


def test_the_licence_check_admits_exactly_the_gates_eight(db) -> None:
    definition = db.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'lexeme_images'::regclass AND conname = 'lexeme_images_licence_check'"
    ).fetchone()[0]
    in_check = set(re.findall(r"'([^']+)'::text", definition))
    assert in_check == set(ALLOWED_LICENCES)
    assert in_check == {
        "CC0", "Public domain", "CC BY 2.0", "CC BY 2.5", "CC BY 3.0",
        "CC BY 4.0", "CC BY-SA 3.0", "CC BY-SA 4.0",
    }


def test_the_schema_refuses_an_uncredited_cc_by_picture(db, lexemes) -> None:
    """Even a loader bug cannot store a CC BY picture without its credit."""
    _, lexeme_id = lexemes["picturable"]
    with pytest.raises(psycopg.errors.CheckViolation):
        _store(lexeme_id, author="  ")
    with pytest.raises(psycopg.errors.CheckViolation):
        _store(lexeme_id, licence="CC BY-NC 2.0")


def test_a_replaced_picture_takes_a_new_id(lexemes) -> None:
    """The route serves `immutable` for a year, so a replacement must never
    reuse the old URL."""
    _, lexeme_id = lexemes["picturable"]
    first = _store(lexeme_id)
    second = _store(lexeme_id, commons_file="File:Other.jpg")
    assert second != first
    assert lexeme_images.image_file(first) is None
    assert lexeme_images.image_file(second) == (JPEG, "image/jpeg")


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def _recorded() -> list[dict]:
    return json.loads(RECORDED.read_text(encoding="utf-8"))


def _extmetadata_of(title_fragment: str) -> tuple[dict[str, str], str]:
    for entry in _recorded():
        if "commons.wikimedia.org" in entry["url"] and title_fragment in entry["url"]:
            info = entry["json"]["query"]["pages"][0]["imageinfo"][0]
            return {k: v["value"] for k, v in info["extmetadata"].items()}, info["mime"]
    raise AssertionError(title_fragment)


def test_the_gate_on_what_commons_really_returned() -> None:
    """Expected verdicts read from the recorded responses by a person."""
    spoon = judge(*_extmetadata_of("SpoonCollection"))
    assert spoon.admitted
    assert (spoon.licence, spoon.author, spoon.licence_url) == (
        "CC BY 2.0", "THOR", "https://creativecommons.org/licenses/by/2.0",
    )
    elbow = judge(*_extmetadata_of("Elbow"))
    assert elbow.admitted and (elbow.licence, elbow.author) == ("Public domain", "KoS")
    ladder = judge(*_extmetadata_of("Nationaldenkmal"))
    assert not ladder.admitted
    assert ladder.reason == "licence not admitted: Attribution"


@pytest.mark.parametrize(
    "meta, mime, reason",
    [
        ({"LicenseShortName": "CC BY-NC 2.0", "Artist": "a", "LicenseUrl": "https://creativecommons.org/licenses/by-nc/2.0"},
         "image/jpeg", "licence not admitted: CC BY-NC 2.0"),
        ({"LicenseShortName": "CC BY-ND 4.0", "Artist": "a"}, "image/jpeg", "licence not admitted: CC BY-ND 4.0"),
        ({"LicenseShortName": "GFDL", "Artist": "a"}, "image/jpeg", "licence not admitted: GFDL"),
        ({"LicenseShortName": "CC BY-SA 3.0 de", "Artist": "a"}, "image/jpeg", "licence not admitted: CC BY-SA 3.0 de"),
        ({}, "image/jpeg", "licence not admitted: (none)"),
        ({"LicenseShortName": "CC BY 4.0", "Artist": "a", "LicenseUrl": "https://creativecommons.org/licenses/by/4.0",
          "Restrictions": "personality"}, "image/jpeg", "non-copyright restriction: personality"),
        ({"LicenseShortName": "CC BY 4.0", "Artist": "", "LicenseUrl": "https://creativecommons.org/licenses/by/4.0"},
         "image/jpeg", "attribution required and no author named"),
        ({"LicenseShortName": "CC BY 4.0", "Artist": "a"}, "image/jpeg", "attribution required and no licence URL"),
        ({"LicenseShortName": "CC0", "Artist": ""}, "image/svg+xml", "format not admitted: image/svg+xml"),
        ({"LicenseShortName": "CC BY 4.0", "Artist": "a", "LicenseUrl": "https://creativecommons.org/licenses/by/4.0",
          "Attribution": "Photo: A. Author, www.example.org"}, "image/jpeg",
         "the author specifies their own credit line"),
    ],
)
def test_the_gate_refuses_with_its_reason(meta, mime, reason) -> None:
    verdict = judge(meta, mime)
    assert not verdict.admitted
    assert verdict.reason == reason


def test_public_domain_needs_no_author() -> None:
    assert judge({"LicenseShortName": "Public domain"}, "image/png").admitted


def test_the_credit_is_plain_text_and_the_licence_link_is_https() -> None:
    assert plain_text('<a href="//commons.wikimedia.org/wiki/User:X">Pierre Andr&eacute;</a>') == "Pierre André"
    assert licence_url("//creativecommons.org/licenses/by-sa/4.0") == "https://creativecommons.org/licenses/by-sa/4.0"
    assert licence_url("http://creativecommons.org/licenses/by/3.0") == "https://creativecommons.org/licenses/by/3.0"
    assert licence_url("https://example.org/licence") is None


def test_bytes_must_be_what_commons_said() -> None:
    assert bytes_match("image/jpeg", JPEG)
    assert not bytes_match("image/png", JPEG)
    assert not bytes_match("image/gif", b"GIF89a")


def test_which_cards_may_carry_a_picture() -> None:
    """PRD §2.6.3: a phrase card and a collocation card never do."""
    assert IMAGE_CARD_TYPES == {"recognition", "production", "cloze", "audio"}
    assert shows_picture("recognition", 1)
    assert not shows_picture("recognition", None)  # a phrase has no lexeme
    assert not shows_picture("collocation", 1)
    assert not shows_picture("something_new", 1)


# ---------------------------------------------------------------------------
# the Wikimedia door, replayed
# ---------------------------------------------------------------------------


class Replay:
    """Serves the recorded exchanges in order, checking each request matches."""

    def __init__(self, entries: list[dict]) -> None:
        self.entries = list(entries)
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        entry = self.entries.pop(0)
        want, got = urlsplit(entry["url"]), request.url
        assert (want.netloc, want.path) == (got.host, got.path)
        if entry["json"] is not None:
            assert parse_qs(want.query) == parse_qs(got.query.decode())
            return httpx.Response(
                entry["status"], json=entry["json"],
                headers={"Retry-After": "4"} if entry["status"] == 429 else {},
            )
        if entry["status"] == 429:
            return httpx.Response(429, headers={"Retry-After": "4"}, text="ratelimited")
        return httpx.Response(200, content=JPEG)


def _client(entries: list[dict], sleeps: list[float]) -> CommonsClient:
    return CommonsClient(
        "operator@example.test",
        transport=httpx.MockTransport(Replay(entries)),
        sleep=sleeps.append,
    )


def test_the_recorded_run_proposes_what_it_proposed_live() -> None:
    """The four lemmas the build rehearsed, 2026-09-25, replayed request for
    request."""
    sleeps: list[float] = []
    client = _client(_recorded(), sleeps)
    got = {lemma: bank.propose_one(client, lemma) for lemma in ("spoon", "ladder", "elbow", "trust")}
    assert got["spoon"].line == bank.Line(
        "spoon", "File:SpoonCollection.jpg", SPOON_SHA1, "CC BY 2.0", "THOR",
        "https://creativecommons.org/licenses/by/2.0",
        "https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
    )
    assert got["elbow"].line.licence == "Public domain"
    assert got["elbow"].line.commons_file == "File:Elbow coude.JPG"
    assert got["ladder"].line is None
    assert got["ladder"].reason.endswith("licence not admitted: Attribution")
    assert got["trust"].line is None
    assert got["trust"].reason == "Q111224165 has no image (P18)"
    # 3 + 3 + 3 + 2 (trust has an item and no P18, so no file read).
    assert client.requests == 11


def test_a_429_is_waited_out_as_the_robot_policy_asks() -> None:
    """**Modelled on the 429 the first live rehearsal really drew** (2026-09-25,
    Wikidata, the ninth request at one per second: `HTTP/2 429`,
    `retry-after: 4`, `x-envoy-ratelimited: true`). The re-recording after the
    `Attribution` field was added drew none, so the exchange is synthesised
    here with the observed headers rather than replayed."""
    answers = iter([
        httpx.Response(429, headers={"retry-after": "4", "x-envoy-ratelimited": "true"}),
        httpx.Response(200, json=_recorded()[0]["json"]),
    ])
    sleeps: list[float] = []
    client = CommonsClient(
        "x@example.test", transport=httpx.MockTransport(lambda r: next(answers)), sleep=sleeps.append
    )
    assert client.item_for("spoon") == "Q81895"
    assert client.requests == 2
    assert 4.0 in sleeps


def test_a_429_that_never_clears_stops_the_run() -> None:
    client = CommonsClient(
        "x@example.test",
        transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"retry-after": "4"})),
        sleep=lambda s: None,
    )
    with pytest.raises(CommonsError, match="429"):
        client.item_for("spoon")
    assert client.requests == 6


def test_the_exact_label_beats_the_top_hit() -> None:
    """The top Wikidata hit for `spoon` was a rock band (recorded)."""
    search = _recorded()[0]["json"]["search"]
    assert search[0]["label"] == "Spoon"  # the band
    client = _client(_recorded()[:1], [])
    assert client.item_for("spoon") == "Q81895"


def test_maxlag_goes_to_commons_and_not_to_wikidata() -> None:
    replay = Replay(_recorded()[:3])
    client = CommonsClient("x@example.test", transport=httpx.MockTransport(replay), sleep=lambda s: None)
    bank.propose_one(client, "spoon")
    wikidata, commons = replay.seen[0], replay.seen[2]
    assert "maxlag" not in wikidata.url.params
    assert commons.url.params["maxlag"] == "5"


def test_a_maxlag_refusal_is_waited_out_then_stops() -> None:
    lagged = {"error": {"code": "maxlag", "info": "Waiting for db: 7 seconds lagged."}}
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=lagged, headers={"Retry-After": "5"})

    sleeps: list[float] = []
    client = CommonsClient("x@example.test", transport=httpx.MockTransport(handler), sleep=sleeps.append)
    with pytest.raises(CommonsError, match="maxlag"):
        client.file_info("File:SpoonCollection.jpg")
    assert len(calls) == 6  # the first try and five retries
    assert sleeps.count(5.0) == 5


def test_a_server_error_stops_the_run() -> None:
    client = CommonsClient(
        "x@example.test",
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        sleep=lambda s: None,
    )
    with pytest.raises(CommonsError, match="503"):
        client.item_for("spoon")


def test_the_user_agent_carries_the_operators_contact() -> None:
    assert user_agent("ops@example.test").startswith("english-bot-image-bank/1.0 (ops@example.test) httpx/")
    with pytest.raises(ValueError):
        user_agent("  ")


def test_a_download_only_goes_to_wikimedias_media_hosts() -> None:
    client = _client([], [])
    with pytest.raises(CommonsError, match="evil.example"):
        client.download("https://evil.example/x.jpg")


# ---------------------------------------------------------------------------
# the card, through the real entry point
# ---------------------------------------------------------------------------


def _make_learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    user_id = int(
        db.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                               cefr_level, auth_email, auth_user_id, timezone)
            VALUES (%s, 'W13d pictures', 'fa', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
            RETURNING id
            """,
            (telegram_user_id, f"w13d-{abs(telegram_user_id)}@example.test", str(uuid.uuid4())),
        ).fetchone()[0]
    )
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, status) "
        "VALUES (%s, %s, 'W13d pictures', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id, datetime.now(timezone.utc) + timedelta(days=30)),
    )
    db.commit()
    return type("L", (), {"user_id": user_id, "cookie": raw})()


@pytest.fixture
def learner(db, lexemes):
    person = _make_learner(db)
    yield person
    uid = person.user_id
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM auth_sessions WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM users WHERE id = %s", (uid,))
    db.commit()


def _due() -> CardState:
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    return CardState(
        fsrs_state="review", fsrs_step=None, stability=10.0, difficulty=5.0,
        due=yesterday, last_review=yesterday - timedelta(days=10), lapses=0, reps=4,
    )


def _card(db, learner, **spec) -> int:
    base = dict(
        register="neutral", register_source="migration_default", state=_due(),
        meaning="a thing", context_sentence="There it is.",
    )
    base.update(spec)
    card_id = cards_svc.create_card(db, learner.user_id, **base)
    db.commit()
    return card_id


def _get(path: str, cookie: str | None) -> httpx.Response:
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(), client=("127.0.0.1", 51234))
        cookies = {SESSION_COOKIE_SECURE: cookie} if cookie else None
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", cookies=cookies) as http:
            return await http.get(path)

    return asyncio.run(_go())


@pytest.fixture
def deck(db, learner, lexemes):
    """Four cards a learner could meet in one review, and one approved picture."""
    picturable, pic_id = lexemes["picturable"]
    abstract, abs_id = lexemes["abstract"]
    image_id = _store(pic_id)
    ids = {
        "picturable": _card(db, learner, card_type="recognition", front=picturable,
                            back="a picturable thing", lexeme_id=pic_id,
                            context_sentence=f"Pass me the {picturable}, please."),
        "abstract": _card(db, learner, card_type="recognition", front=abstract,
                          back="an idea", lexeme_id=abs_id,
                          context_sentence=f"It's all about {abstract}."),
        "phrase": _card(db, learner, card_type="production", front="give up (stop trying)",
                        back="give up", lexeme_id=None,
                        context_sentence="Don't give up now."),
        "collocation": _card(db, learner, card_type="collocation",
                             front=f"___ a {picturable}", back="hold", lexeme_id=pic_id,
                             context_sentence=f"Hold a {picturable} like this."),
    }
    return type("D", (), {"ids": ids, "image_id": image_id, "lemma": picturable})()


def test_the_review_queue_pictures_the_picturable_word_only(learner, deck) -> None:
    """A learner opens /review: the picturable word's card carries the picture
    and its visible credit; the abstract word, the phrase (a phrasal verb) and
    the collocation are unchanged — `image` is null and every other field is
    what it was."""
    response = _get("/review/queue?limit=20", learner.cookie)
    assert response.status_code == 200
    faces = {c["id"]: c for c in response.json()["cards"]}
    picture = faces[deck.ids["picturable"]]["image"]
    assert picture == {
        "id": deck.image_id,
        "ext": "jpg",
        "width": 330,
        "height": 215,
        "alt": deck.lemma,
        "author": "THOR",
        "licence": "CC BY 2.0",
        "licence_url": "https://creativecommons.org/licenses/by/2.0",
        "source_url": "https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
    }
    # No card loses its sentence context.
    assert faces[deck.ids["picturable"]]["context_sentence"] == f"Pass me the {deck.lemma}, please."
    for key in ("abstract", "phrase", "collocation"):
        assert faces[deck.ids[key]]["image"] is None, key


def test_an_unpictured_face_is_the_old_face_plus_a_null(learner, deck) -> None:
    """*Demonstrably unchanged*: the keys before W13d, hardcoded, plus `image`."""
    before_w13d = {
        "id", "card_type", "front", "back", "cue", "context_sentence", "source_ref",
        "meaning", "register", "neutral_equivalent", "who_says_this", "typed", "intervals",
    }
    faces = {c["id"]: c for c in _get("/review/queue?limit=20", learner.cookie).json()["cards"]}
    for key in ("abstract", "phrase", "collocation"):
        face = faces[deck.ids[key]]
        assert set(face) == before_w13d | {"image"}
        assert face["image"] is None


def test_the_picture_is_served_to_a_signed_in_browser(learner, deck) -> None:
    ok = _get(f"/lexeme-images/{deck.image_id}.jpg", learner.cookie)
    assert ok.status_code == 200
    assert ok.content == JPEG
    assert ok.headers["content-type"] == "image/jpeg"
    assert ok.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert _get(f"/lexeme-images/{deck.image_id}.png", learner.cookie).status_code == 404
    assert _get(f"/lexeme-images/{deck.image_id + 10_000_000}.jpg", learner.cookie).status_code == 404
    assert _get(f"/lexeme-images/{deck.image_id}.jpg", None).status_code == 401


# ---------------------------------------------------------------------------
# the loader
# ---------------------------------------------------------------------------


def test_the_committed_data_file_parses() -> None:
    """The file the host loads. Empty until the operator approves pictures."""
    lines = bank.read_lines(bank.DATA_FILE)
    assert all(l.licence in ALLOWED_LICENCES for l in lines)


def _write(tmp_path: Path, rows: list[list[str]], header=bank.COLUMNS) -> Path:
    path = tmp_path / "lexeme_images.tsv"
    path.write_text("\n".join("\t".join(r) for r in [list(header), *rows]) + "\n", encoding="utf-8")
    return path


def _row(lemma: str, **over) -> list[str]:
    line = dict(
        lemma=lemma, commons_file="File:SpoonCollection.jpg", original_sha1=SPOON_SHA1,
        licence="CC BY 2.0", author="THOR",
        licence_url="https://creativecommons.org/licenses/by/2.0",
        source_url="https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
    )
    line.update(over)
    return [line[c] for c in bank.COLUMNS]


def test_a_bad_data_file_is_refused_whole(tmp_path) -> None:
    path = _write(tmp_path, [
        _row("spoon"),
        _row("spoon"),
        _row("cup", licence="CC BY-NC 2.0"),
        _row("fork", author=""),
        _row("knife", original_sha1="nope"),
    ])
    with pytest.raises(bank.DataFileError) as err:
        bank.read_lines(path)
    text = str(err.value)
    assert "lemma appears twice" in text
    assert "licence not admitted: CC BY-NC 2.0" in text
    assert "CC BY 2.0 needs an author and a licence URL" in text
    assert "original_sha1 is not a SHA-1" in text
    with pytest.raises(bank.DataFileError, match="header"):
        bank.read_lines(_write(tmp_path, [], header=("lemma",)))


def _spoon_on_commons(sha1: str = SPOON_SHA1, licence: str = "CC BY 2.0") -> httpx.MockTransport:
    """Commons as it answered for SpoonCollection.jpg, with two knobs."""
    recorded = next(e for e in _recorded() if "SpoonCollection" in e["url"] and e["json"])
    body = json.loads(json.dumps(recorded["json"]))
    info = body["query"]["pages"][0]["imageinfo"][0]
    info["sha1"] = sha1
    info["extmetadata"]["LicenseShortName"]["value"] = licence

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(200, json=body)
        return httpx.Response(200, content=JPEG)

    return httpx.MockTransport(handler)


def _apply(path: Path, transport: httpx.MockTransport) -> dict[str, str]:
    plan = bank.load_plan(bank.read_lines(path))
    client = CommonsClient("ops@example.test", transport=transport, sleep=lambda s: None)
    return bank.apply_plan(client, plan)


def test_load_apply_stores_replaces_and_withdraws(tmp_path, lexemes) -> None:
    """The operator's host step, against the dev database."""
    a, a_id = lexemes["picturable"]
    b, _ = lexemes["abstract"]
    path = _write(tmp_path, [_row(a), _row(b)])
    plan = bank.load_plan(bank.read_lines(path))
    assert [l.lemma for l in plan.add] == [a, b] and plan.withdraw == []
    assert _apply(path, _spoon_on_commons()) == {}
    assert set(lexeme_images.stored()) >= {a, b}
    stored_face = lexeme_images.face_for("recognition", a_id)
    assert stored_face["author"] == "THOR" and stored_face["ext"] == "jpg"

    # The operator removes b's line: --apply withdraws it and touches a not at all.
    path = _write(tmp_path, [_row(a)])
    plan = bank.load_plan(bank.read_lines(path))
    assert plan.add == [] and plan.replace == [] and len(plan.unchanged) == 1
    assert b in plan.withdraw
    before = lexeme_images.stored()[a].id
    bank.apply_plan(CommonsClient("ops@example.test", transport=_spoon_on_commons(), sleep=lambda s: None), plan)
    after = lexeme_images.stored()
    assert b not in after and after[a].id == before


def test_a_reuploaded_file_is_refused_and_nothing_changes(tmp_path, lexemes) -> None:
    a, a_id = lexemes["picturable"]
    refused = _apply(_write(tmp_path, [_row(a)]), _spoon_on_commons(sha1="0" * 40))
    assert refused == {a: "the file was re-uploaded since it was approved (SHA-1 differs)"}
    assert lexeme_images.face_for("recognition", a_id) is None


def test_a_licence_changed_on_commons_is_refused(tmp_path, lexemes) -> None:
    a, a_id = lexemes["picturable"]
    refused = _apply(_write(tmp_path, [_row(a)]), _spoon_on_commons(licence="CC BY-NC 2.0"))
    assert refused == {a: "licence not admitted: CC BY-NC 2.0"}
    refused = _apply(_write(tmp_path, [_row(a)]), _spoon_on_commons(licence="CC BY 4.0"))
    assert refused == {a: "Commons now reads CC BY 4.0, approved as CC BY 2.0"}
    assert lexeme_images.face_for("recognition", a_id) is None


def test_a_lemma_the_lexicon_lacks_is_never_created(tmp_path, lexemes) -> None:
    ghost = _lemma()
    plan = bank.load_plan(bank.read_lines(_write(tmp_path, [_row(ghost)])))
    assert plan.unknown == [ghost] and plan.add == []


def test_the_dry_run_sends_and_writes_nothing(tmp_path, lexemes, capsys) -> None:
    a, a_id = lexemes["picturable"]
    assert bank.main(["--load", "--file", str(_write(tmp_path, [_row(a)]))]) == 0
    out = capsys.readouterr().out
    assert "add: 1" in out and "dry run — nothing was sent and nothing was written." in out
    assert lexeme_images.face_for("recognition", a_id) is None


def test_a_live_run_needs_a_contact(capsys) -> None:
    with pytest.raises(SystemExit):
        bank.main(["--load", "--apply"])
    assert "--contact is required" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        bank.main(["--propose", "--apply", "--contact", "x"])


def test_proposals_are_written_outside_the_repository() -> None:
    with pytest.raises(Exception, match="inside the git repo"):
        bank.main(["--propose", "--live", "--contact", "x@example.test", "--out", str(REPO / "tmp-proposals")])


# ---------------------------------------------------------------------------
# the fixture the browser tests render (#190)
# ---------------------------------------------------------------------------

FIXTURE = REPO / "apps" / "web" / "components" / "cards" / "review-queue.fixture.json"


def test_the_committed_review_fixture_is_current() -> None:
    """Regenerated through the real `card_face` against the dev database and
    compared byte for byte, like `export_session_fixture.py --check`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_review_fixture", REPO / "scripts" / "export_review_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0


def test_the_committed_review_fixture_matches_the_wire(learner, deck) -> None:
    """Key for key against a real ASGI body — never against `card_face` itself,
    which would agree with its own output forever."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    wire = _get("/review/queue?limit=20", learner.cookie).json()
    assert set(fixture) == set(wire)
    wire_faces = {c["id"]: c for c in wire["cards"]}
    wire_pictured = wire_faces[deck.ids["picturable"]]
    wire_plain = wire_faces[deck.ids["abstract"]]
    fixture_pictured = next(c for c in fixture["cards"] if c["image"] is not None)
    fixture_plain = [c for c in fixture["cards"] if c["image"] is None]
    assert set(fixture_pictured) == set(wire_pictured)
    assert set(fixture_pictured["image"]) == set(wire_pictured["image"])
    assert len(fixture_plain) == 3
    for face in fixture_plain:
        assert set(face) == set(wire_plain)


def test_the_operators_own_list_is_proposed_and_never_invents_a_lemma(lexemes, capsys) -> None:
    a, _ = lexemes["picturable"]
    b, _ = lexemes["abstract"]
    assert bank.main(["--propose", "--lemmas", f"{a}, {b}"]) == 0
    out = capsys.readouterr().out
    assert f"2 lemma(s), up to 8 requests" in out and f"{a}, {b}" in out
    ghost = _lemma()
    assert bank.main(["--propose", "--lemmas", f"{a},{ghost}"]) == 1
    assert f"refused, not in the lexicon: {ghost}" in capsys.readouterr().out
