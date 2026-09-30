"""W33 (D) — retell becomes a short conversation (#491 → R2, the operator's ruling of 2026-09-30).

Through the real ASGI transport against the development database (CLAUDE.md §3
rule 1). **The model is scripted at the provider SDK** (`core.llm.anthropic.Anthropic`),
never at a service function, so each request asserted on is the one `core.llm`
would send — and nothing is billed. Every expected count is this file's own
query (§3 rule 5); the route's clock is pinned (§3 rule 6).

**The ruling:** 3–5 learner turns; after each turn below the limit, one short
follow-up question grounded in THIS video; the state stays `open` until the
learner presses *That's enough for now* or sends the fifth turn, and `closing` is
returned only at the fifth. `answer` is unchanged (one turn, then the close —
`test_conversation_rungs.py::test_a_rung_takes_one_turn_and_generates_no_reply`).
**#493 in the same commit:** a close whose model call fails says so (`checked:
false`) and journals nothing.
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from tests.test_conversation_rungs import (  # noqa: F401 — fixtures used by name
    LOCAL_DAY,
    NOW,
    RETELL_REPLY,
    TRANSCRIPT,
    _close,
    _open,
    _say,
    _video_today,
    app,
    auth_env,
    clock,
    count,
    db,
    learner,
)

Q1 = "Why do you think Anna waited so long by the pond?"
Q2 = "How do you think the owner felt when he saw his dog?"
Q3 = "What did Anna do after she took the dog home?"
Q4 = "Who came to get the dog in the end?"

T1 = "Anna see a small dog alone in the park."
T2 = "She wait for the owner one hour but nobody come."
T3 = "Then she take the dog home and call the number."
T4 = "The owner was an old man, he was very happy."
T5 = "He bring her flowers the same evening."

#: Another video's transcript — it must never reach this learner's follow-up.
OTHER = "Marco builds a wooden boat in his garage and sails it across the lake at dawn."


class _Script:
    """The Anthropic SDK answering from a script, in order, and keeping every request.

    A `str` is returned as the model's text; a `dict` as its JSON; an
    `Exception` is raised. Running past the script fails the test.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent: list[dict] = []

    def install(self, monkeypatch):
        script = self

        class _Messages:
            def create(self, **kwargs):
                script.sent.append(kwargs)
                if not script.replies:
                    raise AssertionError("a provider call the script did not expect")
                reply = script.replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                block = MagicMock()
                block.type = "text"
                block.text = reply if isinstance(reply, str) else json.dumps(reply)
                response = MagicMock()
                response.content = [block]
                response.stop_reason = "end_turn"
                response.usage = MagicMock(input_tokens=3500, output_tokens=30,
                                           cache_creation_input_tokens=0,
                                           cache_read_input_tokens=0)
                return response

        class _Client:
            def __init__(self, **kwargs):
                self.messages = _Messages()

        monkeypatch.setattr("core.llm.anthropic.Anthropic", _Client)
        monkeypatch.setattr("core.llm.time.sleep", lambda *_: None)
        return self


def _retell(db, app, learner) -> int:
    video_id = _video_today(db, learner, transcript=TRANSCRIPT)
    assert _open(app, learner, "retell").json()["state"] == "open"
    return video_id


def _open_row_count(db, learner) -> int:
    return count(db, "SELECT count(*) FROM conversations WHERE user_id = %s AND kind = 'retell'"
                     " AND closed_at IS NULL", learner.user_id)


def _dump(request: dict) -> str:
    return json.dumps(request, ensure_ascii=False, default=str)


# ── the turn flow ────────────────────────────────────────────────────────────


def test_one_retell_turn_stays_open_and_asks_a_follow_up(app, db, learner, monkeypatch) -> None:
    """**Red before W33 (D):** the turn answered `closing` with an empty reply and
    made no call."""
    script = _Script(Q1).install(monkeypatch)
    _retell(db, app, learner)
    body = _say(app, learner, T1).json()
    assert body["state"] == "open"
    assert body["reply"] == Q1
    assert len(script.sent) == 1, "one model call per turn"
    assert _open_row_count(db, learner) == 1, "nothing closed it"
    assert count(db, "SELECT count(*) FROM conversation_turns t JOIN conversations c"
                     " ON c.id = t.conversation_id WHERE c.user_id = %s AND t.role = 'app'",
                 learner.user_id) == 2, "the opener and the question"


def test_turns_two_to_four_stay_open_each_with_its_question(app, db, learner, monkeypatch) -> None:
    script = _Script(Q1, Q2, Q3, Q4).install(monkeypatch)
    _retell(db, app, learner)
    replies = [_say(app, learner, t).json() for t in (T1, T2, T3, T4)]
    assert [(r["state"], r["reply"]) for r in replies] == [
        ("open", Q1), ("open", Q2), ("open", Q3), ("open", Q4),
    ]
    assert len(script.sent) == 4
    assert _open_row_count(db, learner) == 1


def test_the_fifth_turn_returns_closing_and_makes_no_call(app, db, learner, monkeypatch) -> None:
    """The limit is the only `closing` (the ruling's (b)); the fifth turn asks nothing."""
    script = _Script(Q1, Q2, Q3, Q4).install(monkeypatch)
    _retell(db, app, learner)
    for t in (T1, T2, T3, T4):
        assert _say(app, learner, t).json()["state"] == "open"
    last = _say(app, learner, T5).json()
    assert last["state"] == "closing"
    assert last["reply"] == ""
    assert len(script.sent) == 4, "no follow-up is generated at the limit"
    assert count(db, "SELECT turns_learner FROM conversations WHERE user_id = %s"
                     " AND kind = 'retell'", learner.user_id) == 5


def test_thats_enough_for_now_after_one_turn_still_closes(app, db, learner, monkeypatch) -> None:
    """The ruling's (a): the learner's own action closes at any turn."""
    script = _Script(Q1, RETELL_REPLY).install(monkeypatch)
    _retell(db, app, learner)
    assert _say(app, learner, T1).json()["state"] == "open"
    response = _close(app, learner)
    assert response.status_code == 200
    assert response.json()["checked"] is True
    assert _open_row_count(db, learner) == 0
    assert len(script.sent) == 2, "the follow-up, then the close"


def test_the_follow_up_is_grounded_in_this_video_and_no_other(app, db, learner, monkeypatch) -> None:
    """The question's request carries THIS video's transcript — the source the
    close draws the video's points from — fenced as data in the user message,
    never in the system prompt; another video in the pool never reaches it; the
    learner's words travel in `<user_text>`; the earlier question is the
    assistant's turn. **Red before W33 (D):** no request was made at all."""
    from core.services import video as video_svc

    other = video_svc.upsert_video(
        db, youtube_id=f"w15{secrets.token_hex(4)}", channel_id="UCw15rungs0000000000000",
        accent="american", track="life", title="The boat at dawn", duration_s=200,
        published_at=NOW - timedelta(days=3), now=NOW,
    )
    video_svc.record_transcript(db, video_id=other, text=OTHER, lang="en", kind="manual")
    db.commit()
    script = _Script(Q1, Q2).install(monkeypatch)
    _retell(db, app, learner)
    _say(app, learner, T1)
    _say(app, learner, T2)

    first, second = script.sent
    for sent in (first, second):
        assert "Marco" not in _dump(sent), "another video's transcript reached the request"
        system = sent["system"][0]["text"]
        assert "Anna was walking" not in system, "the transcript is data, never in the system prompt"
        assert "<<<VIDEO_TRANSCRIPT>>>" in system, "the prompt names the fence it reads"
    opening = first["messages"][0]["content"]
    head, rest = opening.split("<<<VIDEO_TRANSCRIPT>>>\n", 1)
    inside, after = rest.split("\n<<<END_VIDEO_TRANSCRIPT>>>", 1)
    assert head == "" and inside == TRANSCRIPT
    assert after.strip() == f"<user_text>\n{T1}\n</user_text>"
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert second["messages"][1]["content"] == Q1
    assert second["messages"][2]["content"] == f"<user_text>\n{T2}\n</user_text>"
    assert first["max_tokens"] == 300
    db.execute("DELETE FROM videos WHERE id = %s", (other,))
    db.commit()


def test_a_question_the_gates_refuse_becomes_a_written_one_and_the_turn_is_kept(
    app, db, learner, monkeypatch
) -> None:
    """A banned phrase, a reply that is not a question, and a provider failure
    each keep the learner's turn and the conversation open, and ask a question a
    person wrote — never silence and never a 500."""
    from core.services import conversations as conv

    from core.llm import LLMError

    script = _Script(
        "You got it wrong, didn't you?",
        "Anna took the dog home.",
        LLMError("provider down"),
    ).install(monkeypatch)
    _retell(db, app, learner)
    replies = [_say(app, learner, t).json() for t in (T1, T2, T3)]
    assert all(r["state"] == "open" for r in replies)
    assert all(r["reply"] in conv.RETELL_FALLBACK_QUESTIONS for r in replies)
    assert count(db, "SELECT turns_learner FROM conversations WHERE user_id = %s"
                     " AND kind = 'retell'", learner.user_id) == 3
    assert len(script.sent) >= 3


# ── the close reads every turn ───────────────────────────────────────────────


def test_the_close_reads_every_learner_turn_and_scores_the_points_over_all(
    app, db, learner, monkeypatch
) -> None:
    script = _Script(Q1, Q2, Q3, RETELL_REPLY).install(monkeypatch)
    _retell(db, app, learner)
    for t in (T1, T2, T3):
        _say(app, learner, t)
    body = _close(app, learner).json()
    close = script.sent[-1]
    user = close["messages"][0]["content"]
    assert len(close["messages"]) == 1, "the close is one call over the whole retelling"
    _, told = user.split("<<<END_VIDEO_TRANSCRIPT>>>", 1)
    assert told.strip() == f"<user_text>\n{T1}\n\n{T2}\n\n{T3}\n</user_text>"
    for question in (Q1, Q2, Q3):
        assert question not in user, "the app's questions are not the learner's English"
    assert "may come in a few parts" in close["system"][0]["text"], "the close is told"
    assert body["covered"] == ["A woman finds a small dog alone in the park.",
                               "She takes the dog home."]


def test_three_retell_turns_count_toward_block_four(app, db, learner, monkeypatch) -> None:
    """#462 unchanged: three learner turns on the day finish block 4."""
    from core.services import sessions as sessions_svc

    _Script(Q1, Q2, Q3).install(monkeypatch)
    _retell(db, app, learner)
    for t in (T1, T2, T3):
        _say(app, learner, t)
    assert count(db, "SELECT turns_learner FROM conversation_usage WHERE user_id = %s"
                     " AND local_date = %s", learner.user_id, LOCAL_DAY) == 3
    try:
        session = sessions_svc.today(learner.user_id, now=NOW)
        assert next(b.state for b in session.blocks if b.kind == "output") == "done"
    finally:
        db.execute("DELETE FROM sessions WHERE user_id = %s", (learner.user_id,))
        db.commit()


# ── #493: a failed close is never praise ─────────────────────────────────────


def test_a_failed_close_says_it_was_not_checked_and_journals_nothing(
    app, db, learner, monkeypatch
) -> None:
    """**Red before W33 (D):** the body carried no `checked` and read like a clean
    retelling, which the screen rendered as *"That came across well."*"""
    from core.llm import LLMError

    _Script(Q1, LLMError("provider down")).install(monkeypatch)
    _retell(db, app, learner)
    _say(app, learner, T1)
    body = _close(app, learner).json()
    assert body["checked"] is False
    assert body["corrections"] == [] and body["covered"] == [] and body["did_well"] == ""
    assert count(db, "SELECT count(*) FROM errors WHERE user_id = %s", learner.user_id) == 0
    assert _open_row_count(db, learner) == 0, "the learner is released (S26a)"


def test_the_followup_copy_carries_no_banned_phrase() -> None:
    from core.copy_rules import BANNED
    from core.services import conversations as conv

    assert len(conv.RETELL_FALLBACK_QUESTIONS) >= 4
    for text in conv.RETELL_FALLBACK_QUESTIONS:
        assert not BANNED.search(text), text
        assert text.endswith("?")
