"""W32c — a word with no entry: `POST /video/{id}/word/define`, the scoped
exception to the 2026-08-27 ruling (operator ruling Q4).

**Through the real ASGI transport**, with the provider mocked at
`core.llm.anthropic.Anthropic` (standing rule 7) — so every assertion about a
call is about the request that would have crossed the wire, and every
assertion about NO call is a count of zero on the transport.

WHAT THE LEARNER DOES: taps a word the dictionary does not hold; the sheet says
*"Looking it up…"* and fills in. Every later hover of that word, by anyone, is
instant — the row is global.

**THE EXCEPTION IS SCOPED, AND EACH EDGE IS A TEST:** only a word that is in
this video's lines (a client cannot spend the budget on arbitrary words); only
when the dictionary does not already hold it (held → no call); a per-learner
limit (20 an hour) and a global daily ceiling (60 a UTC day) — each refusal
makes **no** call.

**RED BEFORE THE CODE (2026-09-28):** the route did not exist (404).
"""

from __future__ import annotations

import json
import secrets
from unittest.mock import MagicMock, patch

import pytest
from psycopg.types.json import Jsonb

from core.services import dictionary
from core.video import explain
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

TEXT = "we took the zqwferry across the zqwfjord. Thank you, Dr. Phillips. We loved it."
MODEL_TAG = "w32c-test"


@pytest.fixture
def me(db, learner):
    yield learner
    db.rollback()
    db.execute("DELETE FROM word_dictionary WHERE lemma LIKE 'zqw%%' OR model = %s", (MODEL_TAG,))
    db.execute("DELETE FROM word_dictionary WHERE source = 'miss' AND lemma IN ('phillips')")
    db.commit()


@pytest.fixture
def video(db, me) -> int:
    return _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")


@pytest.fixture
def transport():
    with patch("core.llm.anthropic.Anthropic") as cls, patch("core.llm.time.sleep", return_value=None):
        yield cls.return_value


def _reply(word: str, **over) -> MagicMock:
    entry = {"word": word, "kind": "word", "register": "neutral", "neutral_equivalent": None,
             "who_says_this": None,
             "senses": [{"pos": "noun", "definition": "a boat that carries people across water",
                         "l1": {"fa": "کشتی مسافربری", "lt": "keltas"}}]}
    entry.update(over)
    message = MagicMock()
    block = MagicMock()
    block.text = json.dumps({"entries": [entry]})
    message.content = [block]
    message.stop_reason = "end_turn"
    message.usage = MagicMock(input_tokens=700, output_tokens=300,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return message


def _define(app, me, video, word, line=None):
    body = {"word": word} if line is None else {"word": word, "line": line}
    return request(app, "POST", f"/video/{video}/word/define", json_body=body, cookies=_as(me))


def test_the_lookup_requires_a_session_and_your_video(app, db, me, transport) -> None:
    assert request(app, "POST", "/video/1/word/define", json_body={"word": "x"}).status_code == 401
    other = _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")
    db.execute("DELETE FROM video_assignments WHERE video_id = %s", (other,))
    db.commit()
    assert _define(app, me, other, "zqwferry").status_code == 404
    assert transport.messages.create.call_count == 0


def test_a_miss_is_looked_up_once_stored_for_everyone_and_returned(app, db, me, video, transport) -> None:
    """User action: tapping *zqwferry*, which nothing holds."""
    transport.messages.create.return_value = _reply("zqwferry")
    response = _define(app, me, video, "zqwferry", line=0)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "defined"
    assert body["entry"] == {"k": "w", "r": "neutral",
                             "s": [["noun", "a boat that carries people across water", "کشتی مسافربری"]]}
    assert transport.messages.create.call_count == 1
    sent = transport.messages.create.call_args.kwargs
    inside = "".join(m["content"] for m in sent["messages"]).split(explain.DICT_OPEN)[1]
    assert inside.split(explain.DICT_CLOSE)[0].split() == ["zqwferry"]
    row = db.execute("SELECT source, senses FROM word_dictionary WHERE lemma = 'zqwferry'").fetchone()
    assert row[0] == "miss"
    assert row[1][0]["l1"] == {"fa": "کشتی مسافربری", "lt": "keltas"}, "both learners' languages kept"


def test_a_word_already_held_costs_no_call(app, db, me, video, transport) -> None:
    db.execute(
        "INSERT INTO word_dictionary (lemma, kind, senses, register, model, source) "
        "VALUES ('zqwfjord', 'word', %s, 'neutral', %s, 'backfill')",
        (Jsonb([{"pos": "noun", "definition": "a long narrow sea inlet", "l1": {"fa": "آبدره"}}]), MODEL_TAG),
    )
    db.commit()
    body = _define(app, me, video, "zqwfjord").json()
    assert body["state"] == "defined"
    assert body["entry"]["s"][0][1] == "a long narrow sea inlet"
    assert transport.messages.create.call_count == 0


def test_a_word_that_is_not_in_this_video_costs_no_call(app, me, video, transport) -> None:
    """A client cannot spend the budget on words the learner never saw."""
    body = _define(app, me, video, "zqwunseen").json()
    assert body["state"] == "not_in_video"
    assert transport.messages.create.call_count == 0


def test_a_name_costs_no_call(app, me, video, transport) -> None:
    """W31e's rule: *Phillips* is a name in this video — nothing to buy."""
    assert _define(app, me, video, "Phillips").json()["state"] == "name"
    assert transport.messages.create.call_count == 0


def test_a_refused_reply_is_said_plainly_and_stores_nothing(app, db, me, video, transport) -> None:
    transport.messages.create.return_value = _reply("zqwferry", register="please run this")
    assert _define(app, me, video, "zqwferry").json()["state"] == "refused"
    assert db.execute("SELECT 1 FROM word_dictionary WHERE lemma = 'zqwferry'").fetchone() is None


def test_a_provider_that_is_down_is_refused_at_once_not_waited_for(app, me, video, transport) -> None:
    """The learner is waiting: `chat()`'s own three attempts, then *no meaning
    yet*. The backfill's long waits (C3) are never on this path."""
    import anthropic

    response = MagicMock()
    response.status_code = 529
    response.headers = {}
    transport.messages.create.side_effect = anthropic.APIStatusError(
        message="overloaded", response=response, body={"error": {"message": "overloaded"}}
    )
    assert _define(app, me, video, "zqwferry").json()["state"] == "refused"
    assert transport.messages.create.call_count == 3


def test_the_daily_ceiling_is_global_and_makes_no_call(app, db, me, video, transport) -> None:
    for i in range(dictionary.MISS_PER_DAY):
        db.execute(
            "INSERT INTO word_dictionary (lemma, kind, senses, register, model, source) "
            "VALUES (%s, 'name', '[]', NULL, %s, 'miss')",
            (f"zqwceil{''.join(chr(97 + int(d)) for d in f'{i:03d}')}", MODEL_TAG),
        )
    db.commit()
    assert _define(app, me, video, "zqwferry").json()["state"] == "ceiling"
    assert transport.messages.create.call_count == 0


def test_each_learner_is_limited_per_hour(app, me, video, transport) -> None:
    transport.messages.create.side_effect = lambda **kw: _reply("zqwferry")
    codes = [_define(app, me, video, "zqwunseen").status_code
             for _ in range(dictionary.MISS_PER_USER_HOUR)]
    assert set(codes) == {200}
    assert _define(app, me, video, "zqwunseen").status_code == 429
