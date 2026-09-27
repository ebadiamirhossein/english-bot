"""W18 — the placement test through its real entry points (CLAUDE.md §3 rule 1).

Every test drives the six routes through the ASGI transport with a signed-in
cookie, against a small complete bank seeded by `tests/support/placement_seed.py`
through the service's own writers. Provider calls are replaced at the provider
DOOR (`core.llm.chat`, `core.speech.transcribe`, `core.speech.synthesize`), so
the request construction the service does is exercised, not skipped.

User actions: the learner opens *Where to start*, answers a whole sitting —
sixty yes/no words, the grammar ladder, six clips, one speaking prompt — and
reads the result; then opens Progress; a month later sits again.

**The development bank must be empty of anything but these tests' rows** (the
bank is built on the host; on the Mac the build is only ever dry). The fixture
asserts it rather than assuming it.

**RED DEMONSTRATIONS (2026-09-25), each one edit, run, and restored:** the
`_UNSERVED` clause dropped from `_pick` turned
`test_two_sittings_a_month_apart_share_no_item` red (the second sitting's
grammar draw re-served an item and hit `placement_run_items_never_twice`);
`set_known_word_floor` removed from `finish` turned
`test_a_whole_sitting_through_the_routes` red at the floor assert; the voice
gate moved after `transcribe` turned
`test_a_learner_without_voice_is_never_transcribed` red; `answer` given no
`_current` check (any id accepted) turned `test_an_answer_to_another_item_is_refused` red.
**The rest, by a scripted mutation each:** the router unregistered (401 became
404); `_ready` always true (the no-bank test); `start` never resuming (the
one-open index refused the second sitting: 500); the spoken answer written as
`typed`; the clip route reading the bank without the served-to-this-learner
join (an unserved clip played).
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest

from core.placement.scoring import LISTENING_ORDER
from tests.support import placement_seed as ps
from tests.test_progress_route import (  # noqa: F401 — fixtures used by name
    app,
    auth_env,
    db,
    learners,
)

#: Nothing that reads as a score may cross the wire (the build run's rule: a
#: placement is shown as where to start, never as a score).
SCORE_WORDS = re.compile(r"%|percent|score|correct|wrong|mistake|is_word|answer\b", re.I)


@pytest.fixture
def bank(db):
    others = db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0]
    assert others == 0, (
        "the development placement bank holds rows these tests did not write — "
        "it is built on the host; on the Mac the build is only run dry"
    )
    ids = ps.seed_bank(db)
    yield ids
    ps.drop_bank(db, ids)


@pytest.fixture(autouse=True)
def no_voice(monkeypatch):
    monkeypatch.setenv("VOICE_ALLOWED_USER_IDS", "")


def _clean(response) -> None:
    assert not SCORE_WORDS.search(response.text), response.text


def test_every_route_needs_a_session(app) -> None:
    for method, path in (
        ("GET", "/placement"), ("POST", "/placement/start"), ("POST", "/placement/answer"),
        ("POST", "/placement/finish"), ("POST", "/placement/speak/1"),
        ("GET", "/placement/items/1/audio"),
    ):
        body = {} if method == "POST" and path != "/placement/speak/1" else None
        assert ps.call(app, method, path, body=body).status_code == 401, path


def test_with_no_bank_nothing_is_offered(app, db, learners) -> None:
    assert db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0] == 0
    learner = learners()
    view = ps.call(app, "GET", "/placement", learner).json()
    assert view["state"] == "none"
    assert view["ready"] is False and view["available"] is False
    response = ps.call(app, "POST", "/placement/start", learner, body={})
    assert response.status_code == 409
    assert response.json()["detail"] == "bank_not_ready"


def test_a_whole_sitting_through_the_routes(app, db, bank, learners, monkeypatch) -> None:
    learner = learners()
    sent: list[dict] = []

    def fake_chat(messages, **kwargs):
        sent.append({"messages": messages, **kwargs})
        return {"band": "B2", "is_english": True}

    monkeypatch.setattr("core.llm.chat", fake_chat)
    spoken: list[str] = []
    monkeypatch.setattr("core.speech.synthesize", lambda text, **_: spoken.append(text) or b"ID3")

    view = ps.call(app, "GET", "/placement", learner)
    assert view.status_code == 200
    assert view.json() == {
        "state": "none", "ready": True, "available": True, "next_from": None,
        "voice": False, "step": None, "shown": None,
    }

    started = ps.call(app, "POST", "/placement/start", learner, body={})
    assert started.status_code == 200, started.text
    _clean(started)
    step = started.json()

    # ── vocabulary: yes to every real word in ranks 1–5000, no above; yes to
    # two of the twenty pseudo-words (f = 0.1). Worked by hand: bands 1–5 at
    # (1 - 0.1)/(1 - 0.1) = 1 → 5 × 1000; bands 6–10 at 0 → 0. Estimate 5000.
    said_yes_to_pseudo = 0
    for n in range(60):
        assert step["section"] == "vocabulary", n
        assert set(k for k, v in step["item"].items() if v is not None) == {"id", "word"}
        row = ps.bank_row(db, step["item"]["id"])
        if row["is_word"]:
            known = row["freq_rank"] <= 5000
        else:
            known = said_yes_to_pseudo < 2
            said_yes_to_pseudo += known
        response = ps.call(app, "POST", "/placement/answer", learner,
                           body={"item_id": step["item"]["id"], "known": known})
        assert response.status_code == 200, response.text
        _clean(response)
        step = response.json()
    assert said_yes_to_pseudo == 2

    # ── grammar: right, right (B1→B2), wrong, wrong (B2→B1), right, right
    # (B1→B2): three moves on one pair — oscillation — placed at B1.
    script = [(True, "B1"), (True, "B1"), (False, "B2"), (False, "B2"), (True, "B1"), (True, "B1")]
    for right, band in script:
        assert step["section"] == "grammar"
        assert step["item"]["response_mode"] == "typed"
        assert "___" in step["item"]["projection"]["prompt_text"]
        assert ps.bank_row(db, step["item"]["id"])["cefr"] == band
        step = ps.answer(app, learner, step, text=ps.RIGHT if right else ps.WRONG)

    # ── listening: five clips in rising band order (six until W24r (C) dropped
    # the C1 clip); four right, one wrong → 4/5 → B2.
    served_bands = []
    for n in range(5):
        assert step["section"] == "listening", n
        clip = step["item"]["id"]
        served_bands.append(ps.bank_row(db, clip)["cefr"])
        audio = ps.call(app, "GET", f"/placement/items/{clip}/audio", learner)
        assert audio.status_code == 200
        assert audio.headers["content-type"] == "audio/mpeg"
        assert audio.content == b"ID3"
        step = ps.answer(app, learner, step, text=ps.HEARD if n < 4 else "does")
    assert served_bands == list(LISTENING_ORDER)
    # The clip's sentence reached the synthesiser and never the wire.
    assert spoken == [ps.TRANSCRIPT] * 5

    # ── speaking: typed, placed by the rubric at the provider door.
    assert step["section"] == "speaking"
    assert step["item"]["voice"] is False
    typed = "On Saturdays I usually go to the market with my sister and we cook together."
    done = ps.call(app, "POST", "/placement/answer", learner,
                   body={"item_id": step["item"]["id"], "text": typed})
    assert done.status_code == 200, done.text
    assert done.json() == {"section": "done", "item": None}
    assert len(sent) == 1
    assert f"<user_text>\n{typed}\n</user_text>" in sent[0]["messages"][0]["content"]
    assert sent[0]["json_mode"] is True and sent[0]["max_tokens"] == 200

    finished = ps.call(app, "POST", "/placement/finish", learner, body={})
    assert finished.status_code == 200, finished.text
    _clean(finished)
    result = finished.json()
    shown = result["shown"]
    assert shown["where_to_start"] == "B1"
    assert {r["skill"]: r["band"] for r in shown["radar"]} == {
        "vocabulary": "C1",  # 5000 ≥ 3750 (Milton's C1 floor)
        "grammar": "B1",
        "listening": "B2",
        "speaking": "B2",
    }
    assert shown["vocab_estimate"] == 5000
    assert shown["raised_from"] is None and shown["raised_skills"] == []
    assert len(shown["history"]) == 1 and shown["history"][0]["band"] == "B1"
    assert result["next_from"] == str(
        date_of(shown["history"][0]["finished_on"]) + timedelta(days=28)
    )

    # The floor was written, through the W13c service, to the estimate.
    assert db.execute("SELECT known_word_floor FROM users WHERE id = %s",
                      (learner.user_id,)).fetchone()[0] == 5000
    run = db.execute(
        "SELECT floor_written, error_profile, grammar_stop, speaking_mode "
        "FROM placement_runs WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert run[0] == 5000
    assert run[1] == {"verb_tense_past": 2}
    assert run[2] == "oscillation"
    assert run[3] == "typed"
    # Nothing reached the error journal or the ledger (CLAUDE.md §5).
    assert db.execute("SELECT COUNT(*) FROM errors WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM user_lexemes WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == 0

    # Finished: a second finish returns the same result; a new sitting waits.
    assert ps.call(app, "POST", "/placement/finish", learner, body={}).json() == result
    view = ps.call(app, "GET", "/placement", learner).json()
    assert view["state"] == "finished" and view["available"] is False
    refused = ps.call(app, "POST", "/placement/start", learner, body={})
    assert refused.status_code == 409 and refused.json()["detail"] == "not_yet"

    # W19's radar and history are on — in bands, with no score on the wire.
    progress = ps.call(app, "GET", "/progress", learner)
    assert progress.json()["placement"] == shown
    _clean(progress)


def date_of(text: str):
    from datetime import date

    return date.fromisoformat(text)


def test_two_sittings_a_month_apart_share_no_item(app, db, bank, learners) -> None:
    """**The row's acceptance:** two sittings a month apart use non-overlapping
    items. Asserted on the served sets, and the table refuses a repeat anyway."""
    from core.services import placement as svc

    learner = learners()
    ps.run_sitting(app, db, learner)
    assert ps.call(app, "POST", "/placement/finish", learner, body={}).status_code == 200
    db.execute(
        "UPDATE placement_runs SET started_at = started_at - interval '29 days', "
        "finished_at = finished_at - interval '29 days' WHERE user_id = %s",
        (learner.user_id,),
    )
    db.commit()
    assert ps.call(app, "GET", "/placement", learner).json()["available"] is True

    ps.run_sitting(app, db, learner)
    second = ps.call(app, "POST", "/placement/finish", learner, body={})
    assert second.status_code == 200, second.text

    served = svc.served_sets(db, learner.user_id)
    assert len(served) == 2
    first_items, second_items = served.values()
    assert first_items and second_items
    assert not first_items & second_items
    # Both sat the whole vocabulary section: 60 each, none shared.
    for items in (first_items, second_items):
        sections = [ps.bank_row(db, i)["section"] for i in items]
        assert sections.count("vocabulary") == 60
    assert len(second.json()["shown"]["history"]) == 2


def test_a_sitting_resumes_on_the_same_item(app, db, bank, learners) -> None:
    learner = learners()
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    for _ in range(3):
        real = ps.bank_row(db, step["item"]["id"])["is_word"]
        step = ps.answer(app, learner, step, known=bool(real))
    view = ps.call(app, "GET", "/placement", learner).json()
    assert view["state"] == "open"
    assert view["step"] == step
    # A second Start resumes rather than forks.
    assert ps.call(app, "POST", "/placement/start", learner, body={}).json() == step
    assert db.execute("SELECT COUNT(*) FROM placement_runs WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == 1


def test_an_answer_to_another_item_is_refused(app, db, bank, learners) -> None:
    learner = learners()
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    other = ps.call(app, "POST", "/placement/answer", learner,
                    body={"item_id": step["item"]["id"] + 100_000, "known": True})
    assert other.status_code == 409 and other.json()["detail"] == "stale"
    wrong_shape = ps.call(app, "POST", "/placement/answer", learner,
                          body={"item_id": step["item"]["id"]})
    assert wrong_shape.status_code == 422
    assert ps.call(app, "POST", "/placement/finish", learner, body={}).status_code == 409


def _to_speaking(app, db, learner) -> dict:
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    while step["section"] != "speaking":
        section = step["section"]
        if section == "vocabulary":
            step = ps.answer(app, learner, step,
                             known=bool(ps.bank_row(db, step["item"]["id"])["is_word"]))
        else:
            step = ps.answer(app, learner, step, text=ps.RIGHT if section == "grammar" else ps.HEARD)
    return step


def test_a_learner_without_voice_is_never_transcribed(app, db, bank, learners, monkeypatch) -> None:
    """#364: the gate runs before the provider call, and answers 404."""
    learner = learners()

    def never(*_a, **_k):
        raise AssertionError("audio reached the provider without consent")

    monkeypatch.setattr("core.speech.transcribe", never)
    step = _to_speaking(app, db, learner)
    assert step["item"]["voice"] is False
    response = ps.call(app, "POST", f"/placement/speak/{step['item']['id']}", learner,
                       content=b"RIFF" + b"\0" * 64,
                       headers={"content-type": "audio/wav"})
    assert response.status_code == 404


def test_a_spoken_answer_is_placed_and_discarded(app, db, bank, learners, monkeypatch) -> None:
    learner = learners()
    monkeypatch.setenv("VOICE_ALLOWED_USER_IDS", str(learner.user_id))
    heard = "I like to go to the old town because it is quiet and there are small cafes."
    monkeypatch.setattr("core.speech.transcribe", lambda audio, **_: heard)
    sent: list[str] = []
    monkeypatch.setattr("core.llm.chat",
                        lambda messages, **_: sent.append(messages[0]["content"])
                        or {"band": "B1", "is_english": True})
    step = _to_speaking(app, db, learner)
    assert step["item"]["voice"] is True
    response = ps.call(app, "POST", f"/placement/speak/{step['item']['id']}", learner,
                       content=b"RIFF" + b"\0" * 64, headers={"content-type": "audio/wav"})
    assert response.status_code == 200, response.text
    assert response.json()["section"] == "done"
    assert heard in sent[0]
    row = db.execute(
        "SELECT speaking_band, speaking_mode FROM placement_runs WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert row == ("B1", "voice")
    # No column anywhere could have kept the transcript (test_migration_032).


def test_audio_is_only_for_a_clip_this_learner_was_served(app, db, bank, learners, monkeypatch) -> None:
    learner = learners()
    monkeypatch.setattr("core.speech.synthesize", lambda text, **_: b"ID3")
    listening = db.execute(
        "SELECT id FROM placement_bank WHERE id = ANY(%s) AND section = 'listening' LIMIT 1",
        (bank,),
    ).fetchone()[0]
    assert ps.call(app, "GET", f"/placement/items/{listening}/audio", learner).status_code == 404
