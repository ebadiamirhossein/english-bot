"""W18 test seeding: a small, complete placement bank, and a sitting driven
through the real routes.

The bank is written through `core.services.placement`'s own writers
(`insert_vocabulary`, `insert_generated`, `insert_speaking`), so a row the
migration's CHECKs would refuse cannot be seeded. Every row carries a random
token so a run never collides with another, and every row is deleted after the
learners that were served it (`placement_run_items` references the bank
without cascade — the instrument is fixed).
"""

from __future__ import annotations

import asyncio
import secrets

import httpx

from apps.api.deps import SESSION_COOKIE_SECURE
from core.items.gates import ValidationReport
from core.items.schema import parse
from core.placement import BANDS
from core.placement.scoring import LISTENING_ORDER
from core.services import placement as svc

#: The right answer to every seeded grammar item, and a wrong one.
RIGHT, WRONG = "went", "goed"
#: Every seeded listening item's gapped word.
HEARD = "doesn't"
TRANSCRIPT = "She doesn't like coffee these days"


def seed_bank(db, *, sittings: int = 2, grammar_per_band: int = 12) -> list[int]:
    """Enough for ``sittings`` disjoint sittings. Returns the ids written."""
    token = secrets.token_hex(4)
    ids: list[int] = []

    def keep(row_id):
        assert row_id is not None
        ids.append(row_id)

    for band in range(10):
        for i in range(4 * sittings):
            keep(svc.insert_vocabulary(
                db, f"w18real{token}b{band}n{i}", is_word=True,
                freq_rank=band * 1000 + 1 + i, cefr="B1"))
    for i in range(20 * sittings):
        keep(svc.insert_vocabulary(db, f"w18fake{token}n{i}", is_word=False,
                                   freq_rank=None, cefr=None))
    for band in BANDS:
        for i in range(grammar_per_band):
            item = parse({
                "item_type": "cloze_cued", "track": "life",
                "prompt_text": f"I ___ to the shops yesterday ({token} {band} {i}).",
                "answer": RIGHT, "accepted_variants": [RIGHT],
                "cohort": "placement", "error_type": "verb_tense_past",
            })
            keep(svc.insert_generated(
                db, "grammar", cefr=band, error_type="verb_tense_past", item=item,
                validation=ValidationReport("passed").as_json(), model="w18-test",
                content_hash=f"{token}-g-{band}-{i}"))
    for n, band in enumerate(LISTENING_ORDER * sittings):
        item = parse({
            "item_type": "listening_gap", "track": "life",
            "prompt_text": f"She ___ like coffee these days ({token} {n})",
            "answer": HEARD, "accepted_variants": [HEARD],
            "transcript": TRANSCRIPT, "cohort": "placement", "error_type": "verb_tense_past",
        })
        keep(svc.insert_generated(
            db, "listening", cefr=band, error_type="verb_tense_past", item=item,
            validation=ValidationReport("passed").as_json(), model="w18-test",
            content_hash=f"{token}-l-{n}"))
    for i in range(sittings):
        keep(svc.insert_speaking(db, f"Tell me about your weekend ({token} {i}).", cefr="B1"))
    db.commit()
    return ids


def drop_bank(db, ids: list[int]) -> None:
    db.rollback()
    db.execute("DELETE FROM placement_bank WHERE id = ANY(%s)", (ids,))
    db.commit()


def call(app, method: str, path: str, learner=None, *, body=None, content=None,
         headers=None) -> httpx.Response:
    cookies = {SESSION_COOKIE_SECURE: learner.cookie} if learner is not None else None

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     cookies=cookies) as http:
            return await http.request(method, path, json=body, content=content,
                                      headers=headers)

    return asyncio.run(_go())


def bank_row(db, bank_id: int) -> dict:
    row = db.execute(
        "SELECT section, cefr, is_word, freq_rank FROM placement_bank WHERE id = %s",
        (bank_id,),
    ).fetchone()
    return {"section": row[0], "cefr": row[1], "is_word": row[2], "freq_rank": row[3]}


def answer(app, learner, step: dict, **fields) -> dict:
    response = call(app, "POST", "/placement/answer", learner,
                    body={"item_id": step["item"]["id"], **fields})
    assert response.status_code == 200, response.text
    return response.json()


def run_sitting(app, db, learner) -> dict:
    """Start and answer a whole sitting: every word known, every item right,
    speaking skipped. Returns the last step (``done``)."""
    response = call(app, "POST", "/placement/start", learner, body={})
    assert response.status_code == 200, response.text
    step = response.json()
    while step["section"] != "done":
        section = step["section"]
        if section == "vocabulary":
            real = bank_row(db, step["item"]["id"])["is_word"]
            step = answer(app, learner, step, known=bool(real))
        elif section == "grammar":
            step = answer(app, learner, step, text=RIGHT)
        elif section == "listening":
            step = answer(app, learner, step, text=HEARD)
        else:
            step = answer(app, learner, step, skip=True)
    return step
