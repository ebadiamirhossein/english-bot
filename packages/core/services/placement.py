"""W18 — the placement test's SQL, and the one function each route calls.

PRD §6. A sitting is four sections in order — **vocabulary** (60 yes/no: 40
real words across ten frequency bands and 20 pseudo-words), **grammar** (up to
25, adaptive: `core.placement.ladder`), **listening** (6 gap-fills in rising
band order) and **speaking** (one prompt, spoken or typed) — then a result.

**What is stored, and what is not (CLAUDE.md §5):** which bank items a sitting
served and whether each answer was right. **Never** what was typed, never what
was said; the speaking answer is placed in the request and discarded, and only
its band is written. Logs carry user ids, run ids and bank ids.

**Two sittings never share an item.** `placement_run_items`'
`UNIQUE (user_id, bank_id)` is the rule, and every draw here selects only rows
this learner has never been served — so the constraint is what would catch a
bug in the draw, not the mechanism.

**A placement is never a score on the learner.** The result is a band, *where
to start*; no percentage is computed for the wire. What is shown is the
high-water mark across sittings (`core.placement.scoring.shown`): raises are
announced, drops are silent (CLAUDE.md §4).

**The result seeds `users.known_word_floor` through
`core.services.lexicon.set_known_word_floor`** — the function W13c's
`python -m core.lexicon.floor --apply` calls — never with its own UPDATE. A wrong
placement is therefore corrected the way any floor is.

**What the result does NOT write, deliberately:**

* **No `errors` row.** A wrong choice in a test item is recognition, not a
  self-produced error (CLAUDE.md §5: *"a wrong entry is permanent damage; a
  missing one is recoverable"*). The per-error-type profile is kept on the run
  for the operator and a later slice, and never rendered.
* **No `user_lexemes` row.** A *yes* on a word list is a self-report; W19's
  *words you know* counts evidence only, and forty self-reports would move it.
  The ledger is seeded through the floor.
* **No `users.cefr_level` and no syllabus position.** Both are read by paths
  this slice does not own (the v2 bot reads `cefr_level`), and moving a
  learner's unit is a decision about their course, not a measurement. The
  skill-map entry point is REPORTED UNMET in the record.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb

from core.db import connection
from core.items.checks import sentence_of
from core.items.response import Submission, grade
from core.items.schema import BaseItem, parse
from core.placement import ladder, readiness, scoring
from core.services.items import present_bank_item
from core.placement.scoring import (
    BAND_SIZE,
    LISTENING_ORDER,
    PSEUDO_PER_SITTING,
    REAL_PER_BAND,
    VOCAB_BANDS,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AudioUnavailable",
    "NoSitting",
    "NotConsented",
    "NotDone",
    "NotReady",
    "NotYet",
    "Overview",
    "PlacementError",
    "Result",
    "StaleAnswer",
    "Step",
    "Submission",
    "answer",
    "answer_voice",
    "finish",
    "item_audio",
    "overview",
    "shown_for",
    "start",
]

SECTIONS = ("vocabulary", "grammar", "listening", "speaking")


class PlacementError(Exception):
    """Base for every refusal a route turns into a status."""


class NotReady(PlacementError):
    """The bank cannot supply a whole sitting for this learner (409)."""


class NotYet(PlacementError):
    """A sitting finished less than `RETEST_DAYS` ago (409)."""


class NoSitting(PlacementError):
    """Nothing is open to answer or finish (404)."""


class StaleAnswer(PlacementError):
    """The item answered is not the one being asked (409): a double tap, or a
    second tab. The client re-reads `GET /placement`."""


class NotDone(PlacementError):
    """Finish was called before every section was answered (409)."""


class NotConsented(PlacementError):
    """Voice is not enabled for this learner (#364) — the route answers 404."""


class AudioUnavailable(PlacementError):
    """The speech provider failed (503)."""


@dataclass(frozen=True, slots=True)
class Step:
    """What to show next. ``item`` is the learner-visible face only — never an
    answer, never whether a word is real."""

    section: str
    item: dict | None = None


@dataclass(frozen=True, slots=True)
class Result:
    """A finished sitting, as the learner is shown it."""

    shown: scoring.Shown
    next_from: date | None


@dataclass(frozen=True, slots=True)
class Overview:
    """`GET /placement`."""

    #: none · open · finished
    state: str
    #: The bank can supply a whole sitting for this learner.
    ready: bool
    #: A new sitting may be started now (ready, nothing open, not too soon).
    available: bool
    next_from: date | None
    step: Step | None = None
    shown: scoring.Shown | None = None
    #: Whether the speaking item may take a recording (#364).
    voice: bool = False


# ── time ────────────────────────────────────────────────────────────────────


def _tz(conn, user_id: int) -> ZoneInfo:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT timezone FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if row is None:
        raise NoSitting(f"no user {user_id}")
    return ZoneInfo(str(row[0] or "Europe/Vilnius"))


# ── the bank, for the build command ─────────────────────────────────────────


def vocabulary_hash(word: str) -> str:
    return hashlib.sha256(f"vocabulary\x1f{word}".encode()).hexdigest()


def speaking_hash(prompt: str) -> str:
    return hashlib.sha256(f"speaking\x1f{prompt}".encode()).hexdigest()


def generated_hash(section: str, content_hash: str) -> str:
    """A generated item's `schema.content_hash`, namespaced by section."""
    return hashlib.sha256(f"{section}\x1f{content_hash}".encode()).hexdigest()


def bank_rows(conn) -> list[dict]:
    """Every bank row's planning columns. The build command's view of the bank."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, section, cefr, error_type, word, is_word, freq_rank,
                   content_hash, item
              FROM placement_bank
             ORDER BY id
            """
        )
        return list(cur.fetchall())


def vocabulary_candidates(conn, lo: int, hi: int) -> list[tuple[str, int, str]]:
    """Real words a band may draw: content words with a CEFR tag, ranks lo–hi.

    **A CEFR tag is required** (the spec: *"drawn from `lexemes` by `freq_rank`
    and CEFR tag"*), which also keeps out names — the frequency list's proper
    nouns carry no tag and no part of speech. Lower-case letters only, three or
    more, so a symbol or an abbreviation is never shown as a word.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT lemma, freq_rank, cefr
              FROM lexemes
             WHERE freq_rank BETWEEN %s AND %s
               AND cefr IS NOT NULL
               AND pos IN ('NOUN', 'VERB', 'ADJ', 'ADV')
               AND lemma ~ '^[a-z]{3,}$'
             ORDER BY freq_rank
            """,
            (lo, hi),
        )
        return [(str(r[0]), int(r[1]), str(r[2])) for r in cur.fetchall()]


def lexeme_lemmas(conn) -> frozenset[str]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT lemma FROM lexemes")
        return frozenset(str(r[0]) for r in cur.fetchall())


def insert_vocabulary(conn, word: str, *, is_word: bool, freq_rank: int | None,
                      cefr: str | None) -> int | None:
    """One yes/no row. ``None`` if an identical row is already in the bank."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO placement_bank (section, word, is_word, freq_rank, cefr, content_hash)
            VALUES ('vocabulary', %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            (word, is_word, freq_rank, cefr, vocabulary_hash(word)),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def insert_speaking(conn, prompt: str, *, cefr: str) -> int | None:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO placement_bank (section, cefr, item, content_hash)
            VALUES ('speaking', %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            (cefr, Jsonb({"prompt_text": prompt}), speaking_hash(prompt)),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def insert_generated(conn, section: str, *, cefr: str, error_type: str,
                     item: BaseItem, validation: dict, model: str,
                     content_hash: str) -> int | None:
    """One gated grammar or listening item. The item is stored whole — the
    answer included, because grading is server-side — exactly as
    `core.items.schema.parse` reads it back."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO placement_bank
                   (section, cefr, error_type, item, validation, model, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            (
                section, cefr, error_type,
                Jsonb(item.model_dump(mode="json", by_alias=True)),
                Jsonb(validation), model, generated_hash(section, content_hash),
            ),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def vocabulary_real_words(conn) -> list[dict]:
    """Every real-word row, with whether ANY learner has been served it. For
    `core.placement.prune` (launch 2026-09-26, B4); oldest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.id, b.word, b.freq_rank,
                   EXISTS (SELECT 1 FROM placement_run_items r
                            WHERE r.bank_id = b.id) AS served
              FROM placement_bank b
             WHERE b.section = 'vocabulary' AND b.is_word
             ORDER BY b.id
            """
        )
        return list(cur.fetchall())


def delete_unserved_vocabulary(conn, ids: list[int]) -> list[int]:
    """Delete these vocabulary rows **unless served** — the refusal is in the
    statement, so a row served between the read and the delete stays. Returns
    the ids deleted. The caller commits."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            DELETE FROM placement_bank b
             WHERE b.id = ANY(%s) AND b.section = 'vocabulary'
               AND NOT EXISTS (SELECT 1 FROM placement_run_items r
                                WHERE r.bank_id = b.id)
            RETURNING b.id
            """,
            (ids,),
        )
        return sorted(int(r[0]) for r in cur.fetchall())


# ── the bank, for a sitting ─────────────────────────────────────────────────

_UNSERVED = """
    NOT EXISTS (SELECT 1 FROM placement_run_items r
                 WHERE r.user_id = %(user)s AND r.bank_id = b.id)
"""


def _unserved_counts(conn, user_id: int) -> Counter:
    """(section, key) → unserved rows, where key is the vocabulary band (0–9)
    and is_word for vocabulary, the CEFR band for the rest."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            f"""
            SELECT b.section, b.is_word,
                   CASE WHEN b.freq_rank IS NOT NULL
                        THEN (b.freq_rank - 1) / {BAND_SIZE} END AS vband,
                   b.cefr, COUNT(*)
              FROM placement_bank b
             WHERE {_UNSERVED}
             GROUP BY 1, 2, 3, 4
            """,
            {"user": user_id},
        )
        rows = cur.fetchall()
    out: Counter = Counter()
    for section, is_word, vband, cefr, n in rows:
        if section == "vocabulary":
            key = ("real", int(vband)) if is_word else ("pseudo",)
        else:
            key = (cefr,)
        out[(section, *key)] += int(n)
        out[(section, "any")] += int(n)
    return out


def _ready(conn, user_id: int) -> bool:
    """Can the bank supply a whole sitting to THIS learner, from rows they have
    never been served? `core.placement.readiness` states the rule and why.

    *(Launch 2026-09-26, B2. It read: every vocabulary band's four, the twenty
    pseudo-words, ONE grammar item at B1, ONE listening clip of any band and
    one speaking prompt — so production's bank, with no listening C1 at all,
    read ready, and a sitting would have skipped the C1 clip and could then
    claim C1 from five clips that never included one.)*"""
    return readiness.ready(_unserved_counts(conn, user_id))


def _pick(conn, user_id: int, section: str, *, cefr: str | None = None) -> int | None:
    """One unserved bank id in ``section`` (at ``cefr`` when given), at random."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            f"""
            SELECT b.id FROM placement_bank b
             WHERE b.section = %(section)s
               AND (%(cefr)s::text IS NULL OR b.cefr = %(cefr)s::text)
               AND {_UNSERVED}
             ORDER BY random()
             LIMIT 1
            """,
            {"section": section, "cefr": cefr, "user": user_id},
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def _serve(conn, run_id: int, user_id: int, bank_id: int, section: str, position: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO placement_run_items (run_id, user_id, bank_id, section, position)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, user_id, bank_id, section, position),
        )


def _draw_vocabulary(conn, run_id: int, user_id: int) -> None:
    """The sixty, drawn at once and shuffled: four real words from each band,
    twenty pseudo-words."""
    ids: list[int] = []
    with conn.cursor(row_factory=tuple_row) as cur:
        for band in range(VOCAB_BANDS):
            cur.execute(
                f"""
                SELECT b.id FROM placement_bank b
                 WHERE b.section = 'vocabulary' AND b.is_word
                   AND b.freq_rank BETWEEN %(lo)s AND %(hi)s
                   AND {_UNSERVED}
                 ORDER BY random() LIMIT %(n)s
                """,
                {"lo": band * BAND_SIZE + 1, "hi": (band + 1) * BAND_SIZE,
                 "n": REAL_PER_BAND, "user": user_id},
            )
            ids.extend(int(r[0]) for r in cur.fetchall())
        cur.execute(
            f"""
            SELECT b.id FROM placement_bank b
             WHERE b.section = 'vocabulary' AND NOT b.is_word AND {_UNSERVED}
             ORDER BY random() LIMIT %(n)s
            """,
            {"n": PSEUDO_PER_SITTING, "user": user_id},
        )
        ids.extend(int(r[0]) for r in cur.fetchall())
    random.shuffle(ids)
    for position, bank_id in enumerate(ids):
        _serve(conn, run_id, user_id, bank_id, "vocabulary", position)


def _draw_listening(conn, run_id: int, user_id: int) -> int:
    """Six clips in `LISTENING_ORDER`. A band with nothing unserved is skipped,
    never filled from another band (the order is the instrument)."""
    served = 0
    for band in LISTENING_ORDER:
        bank_id = _pick(conn, user_id, "listening", cefr=band)
        if bank_id is None:
            # Unreachable while `_ready` held at the start; a row deleted under
            # an open sitting can still land here. Skipped, logged, and never
            # claimed (`scoring.listening_band`'s `served`).
            logger.info("placement listening band_thin user_id=%s run=%s band=%s",
                        user_id, run_id, band)
            continue
        _serve(conn, run_id, user_id, bank_id, "listening", served)
        served += 1
    return served


# ── a sitting ───────────────────────────────────────────────────────────────


def _open_run(conn, user_id: int, *, lock: bool = False) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM placement_runs WHERE user_id = %s AND finished_at IS NULL"
            + (" FOR UPDATE" if lock else ""),
            (user_id,),
        )
        return cur.fetchone()


def _served(conn, run_id: int, section: str) -> list[dict]:
    """This run's items in ``section``, in serving order, with their bank row."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT r.bank_id, r.position, r.correct, r.answered_at,
                   b.cefr, b.error_type, b.word, b.is_word, b.freq_rank, b.item
              FROM placement_run_items r
              JOIN placement_bank b ON b.id = r.bank_id
             WHERE r.run_id = %s AND r.section = %s
             ORDER BY r.position
            """,
            (run_id, section),
        )
        return list(cur.fetchall())


def _advance(conn, run: dict, section: str, **columns: Any) -> None:
    sets = ", ".join([f"{k} = %s" for k in columns] + ["section = %s"])
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE placement_runs SET {sets} WHERE id = %s",
            (*columns.values(), section, run["id"]),
        )
    run["section"] = section
    run.update(columns)


def _face(row: dict, *, voice: bool) -> dict:
    """The learner-visible face of one served row. **No answer, and for a
    vocabulary row nothing that says whether the word is real.**"""
    if row["word"] is not None:
        return {"id": row["bank_id"], "word": row["word"]}
    item = row["item"]
    if "item_type" not in item:  # speaking
        return {"id": row["bank_id"], "prompt_text": item["prompt_text"], "voice": voice}
    # Projected by `core.services.items` — the module that serves every item's
    # face — so the learner sees what the gates' blind solver saw.
    face = present_bank_item(row["bank_id"], parse(item))
    return {"id": face.id, "response_mode": face.response_mode, "projection": face.projection}


def _grammar_history(rows: list[dict]) -> list[tuple[str, bool]]:
    return [(r["cefr"], bool(r["correct"])) for r in rows if r["answered_at"] is not None]


def _next_step(conn, run: dict, user_id: int, *, voice: bool) -> Step:
    """Serve whatever comes next, advancing sections as each one ends."""
    while True:
        section = run["section"]
        if section == "done":
            return Step("done")
        rows = _served(conn, run["id"], section)
        pending = next((r for r in rows if r["answered_at"] is None), None)
        if pending is not None:
            return Step(section, _face(pending, voice=voice))

        if section == "vocabulary":
            _advance(conn, run, "grammar")
        elif section == "grammar":
            history = _grammar_history(rows)
            state = ladder.replay(history)
            if state.stop:
                _advance(conn, run, "listening", grammar_stop=state.stop)
                continue
            bank_id = _pick(conn, user_id, "grammar", cefr=state.band)
            if bank_id is None:
                logger.info("placement grammar bank_thin user_id=%s run=%s band=%s",
                            user_id, run["id"], state.band)
                _advance(conn, run, "listening", grammar_stop="bank_thin")
                continue
            _serve(conn, run["id"], user_id, bank_id, "grammar", len(rows))
        elif section == "listening":
            if rows or _draw_listening(conn, run["id"], user_id) == 0:
                _advance(conn, run, "speaking")
        elif section == "speaking":
            bank_id = None if rows else _pick(conn, user_id, "speaking")
            if bank_id is None:
                _advance(conn, run, "done")
            else:
                _serve(conn, run["id"], user_id, bank_id, "speaking", 0)


def _voice(user_id: int) -> bool:
    from core.services.conversations import voice_allowed_for

    return voice_allowed_for(user_id)


def _finished_sittings(conn, user_id: int, tz: ZoneInfo) -> list[scoring.Sitting]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT finished_at, cefr, vocabulary_band, grammar_band, listening_band,
                   speaking_band, vocab_estimate
              FROM placement_runs
             WHERE user_id = %s AND finished_at IS NOT NULL
             ORDER BY finished_at, id
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return [
        scoring.Sitting(
            finished_on=r["finished_at"].astimezone(tz).date(),
            cefr=r["cefr"],
            bands={
                "vocabulary": r["vocabulary_band"],
                "grammar": r["grammar_band"],
                "listening": r["listening_band"],
                "speaking": r["speaking_band"],
            },
            vocab_estimate=r["vocab_estimate"],
        )
        for r in rows
    ]


def shown_for(conn, user_id: int) -> scoring.Shown | None:
    """What this learner is shown of every finished sitting — the high-water
    view. `core.services.progress` reads it for W19's radar and history."""
    return scoring.shown(_finished_sittings(conn, user_id, _tz(conn, user_id)))


def overview(user_id: int, *, now: datetime) -> Overview:
    """`GET /placement`. **It may write**: an open sitting's next item is served
    (drawn and recorded) if none is pending, so a reload lands on the same item
    the next read will — `GET /session/today`'s precedent for a read that
    persists what it decided."""
    voice = _voice(user_id)
    with connection() as conn:
        tz = _tz(conn, user_id)
        today = now.astimezone(tz).date()
        sittings = _finished_sittings(conn, user_id, tz)
        shown = scoring.shown(sittings)
        next_from = scoring.next_sitting_from(sittings[-1].finished_on if sittings else None)
        run = _open_run(conn, user_id, lock=True)
        if run is not None:
            step = _next_step(conn, run, user_id, voice=voice)
            conn.commit()
            return Overview("open", True, False, next_from, step, shown, voice)
        ready = _ready(conn, user_id)
        conn.commit()
    available = ready and (next_from is None or today >= next_from)
    return Overview("finished" if shown else "none", ready, available, next_from, None,
                    shown, voice)


def start(user_id: int, *, now: datetime) -> Step:
    """`POST /placement/start`. Resumes an open sitting rather than forking one.

    Raises `NotYet` inside the re-test interval and `NotReady` when the bank
    cannot supply a whole sitting for this learner.
    """
    voice = _voice(user_id)
    with connection() as conn:
        tz = _tz(conn, user_id)
        run = _open_run(conn, user_id, lock=True)
        if run is None:
            sittings = _finished_sittings(conn, user_id, tz)
            next_from = scoring.next_sitting_from(
                sittings[-1].finished_on if sittings else None
            )
            if next_from is not None and now.astimezone(tz).date() < next_from:
                raise NotYet(str(next_from))
            if not _ready(conn, user_id):
                raise NotReady("the bank cannot supply a sitting")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO placement_runs (user_id, started_at) VALUES (%s, %s) RETURNING *",
                    (user_id, now),
                )
                run = cur.fetchone()
            _draw_vocabulary(conn, run["id"], user_id)
            logger.info("placement started user_id=%s run=%s", user_id, run["id"])
        step = _next_step(conn, run, user_id, voice=voice)
        conn.commit()
    return step


def _current(conn, user_id: int, bank_id: int) -> tuple[dict, dict]:
    """The open run (locked) and its pending row, which must be ``bank_id``."""
    run = _open_run(conn, user_id, lock=True)
    if run is None:
        raise NoSitting("nothing open")
    if run["section"] == "done":
        raise StaleAnswer("the sitting is waiting to finish")
    rows = _served(conn, run["id"], run["section"])
    pending = next((r for r in rows if r["answered_at"] is None), None)
    if pending is None or pending["bank_id"] != bank_id:
        raise StaleAnswer(f"bank {bank_id} is not the item being asked")
    return run, pending


def _mark(conn, run_id: int, bank_id: int, correct: bool | None, now: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE placement_run_items SET correct = %s, answered_at = %s
             WHERE run_id = %s AND bank_id = %s
            """,
            (correct, now, run_id, bank_id),
        )


def answer(
    user_id: int, bank_id: int, submission: Submission, *, now: datetime,
    known: bool | None = None, skip: bool = False, place=None,
) -> Step:
    """`POST /placement/answer`. Marks the pending item and returns the next.

    * vocabulary — ``known``: did the learner say they know the word;
    * grammar / listening — ``submission``, graded by `core.items.response.grade`,
      the grader every item in the app uses;
    * speaking — ``submission.text`` (the typed fallback), placed by one billed
      rubric call and discarded; or ``skip``.

    ``place`` is the rubric seam tests replace (`core.placement.speaking.place`).
    **Raises `ValueError` for an answer of the wrong shape** (422 at the route).
    """
    voice = _voice(user_id)
    with connection() as conn:
        run, pending = _current(conn, user_id, bank_id)
        section = run["section"]
        if section == "vocabulary":
            if known is None:
                raise ValueError("a vocabulary answer is known: true or false")
            _mark(conn, run["id"], bank_id, known == bool(pending["is_word"]), now)
        elif section in ("grammar", "listening"):
            correct, _ = grade(parse(pending["item"]), submission)
            _mark(conn, run["id"], bank_id, correct, now)
        else:
            text = (submission.text or "").strip()
            if skip:
                band, mode = None, "skipped"
            elif not text:
                raise ValueError("a typed speaking answer needs text, or skip")
            else:
                band, mode = _place(pending["item"]["prompt_text"], text, place), "typed"
            _advance(conn, run, "speaking", speaking_band=band, speaking_mode=mode)
            _mark(conn, run["id"], bank_id, None, now)
        step = _next_step(conn, run, user_id, voice=voice)
        conn.commit()
    logger.info("placement answer user_id=%s run=%s section=%s", user_id, run["id"], section)
    return step


def _place(prompt_text: str, text: str, place) -> str | None:
    """The rubric, or ``None`` when it could not be read. **A failed call is an
    unplaced skill, never a guess** — the sitting still finishes."""
    from core.llm import LLMError
    from core.placement import speaking

    try:
        return (place or speaking.place)(prompt_text, text)
    except LLMError:
        logger.warning("placement speaking rubric failed")
        return None


def answer_voice(user_id: int, bank_id: int, audio: bytes, *, now: datetime,
                 transcribe=None, place=None) -> Step:
    """`POST /placement/speak/{bank_id}` — the spoken answer.

    **Gated by `voice_allowed_for` BEFORE the provider call (#364)**: a gate
    that refused after sending the audio would already have done what it
    prevents. The bytes are transcribed in memory and dropped; the transcript
    is placed and dropped; only the band is written.
    """
    from core import speech

    if not _voice(user_id):
        raise NotConsented("voice is not enabled for this learner")
    with connection() as conn:
        run, pending = _current(conn, user_id, bank_id)
        if run["section"] != "speaking":
            raise StaleAnswer("not the speaking item")
        prompt_text = pending["item"]["prompt_text"]
        conn.rollback()  # release the lock across the provider calls
    try:
        text = (transcribe or speech.transcribe)(audio).strip()
    except speech.SpeechError:
        logger.warning("placement transcription failed user_id=%s", user_id)
        raise AudioUnavailable("transcription failed") from None
    if not text:
        raise ValueError("nothing was heard")
    band = _place(prompt_text, text, place)
    with connection() as conn:
        run, _ = _current(conn, user_id, bank_id)
        _advance(conn, run, "speaking", speaking_band=band, speaking_mode="voice")
        _mark(conn, run["id"], bank_id, None, now)
        step = _next_step(conn, run, user_id, voice=True)
        conn.commit()
    logger.info("placement spoken answer user_id=%s run=%s", user_id, run["id"])
    return step


def item_audio(user_id: int, bank_id: int) -> bytes | None:
    """A served listening clip as speech. ``None`` unless this bank row is a
    listening item this learner has been served. **Bytes out, never text**:
    the sentence is the answer (`core.services.items.item_audio`'s reason)."""
    from core import speech

    with connection() as conn:
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                SELECT b.item FROM placement_run_items r
                  JOIN placement_bank b ON b.id = r.bank_id
                 WHERE r.user_id = %s AND r.bank_id = %s AND b.section = 'listening'
                """,
                (user_id, bank_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    text = sentence_of(parse(row[0]))
    logger.info("placement audio user_id=%s bank=%s", user_id, bank_id)
    try:
        return speech.synthesize(text)
    except speech.SpeechError:
        logger.warning("placement audio synthesis failed user_id=%s bank=%s", user_id, bank_id)
        raise AudioUnavailable("synthesis failed") from None


def finish(user_id: int, *, now: datetime) -> Result:
    """`POST /placement/finish`. Reads the sitting, writes its result and the
    floor, and returns what the learner is shown.

    **Idempotent:** with nothing open and a finished sitting behind it, it
    returns that result again (a retried request after a dropped response).
    """
    from core.services.lexicon import FLOOR_RANGE, set_known_word_floor

    with connection() as conn:
        tz = _tz(conn, user_id)
        run = _open_run(conn, user_id, lock=True)
        if run is None:
            sittings = _finished_sittings(conn, user_id, tz)
            if not sittings:
                raise NoSitting("nothing to finish")
            return Result(
                scoring.shown(sittings),
                scoring.next_sitting_from(sittings[-1].finished_on),
            )
        if run["section"] != "done":
            raise NotDone(run["section"])

        vocab = _served(conn, run["id"], "vocabulary")
        estimate = scoring.vocabulary_estimate(
            ((r["freq_rank"], bool(r["correct"])) for r in vocab if r["is_word"]),
            (not r["correct"] for r in vocab if not r["is_word"]),
        )
        grammar = _served(conn, run["id"], "grammar")
        history = _grammar_history(grammar)
        state = (
            ladder.stop_for_thin_bank(history)
            if run["grammar_stop"] == "bank_thin"
            else ladder.replay(history)
        )
        grammar_band = state.result or ladder.held_band(history, state.moves)
        profile = Counter(r["error_type"] for r in grammar
                          if r["answered_at"] is not None and not r["correct"])
        heard = _served(conn, run["id"], "listening")
        listening = [bool(r["correct"]) for r in heard]

        floor = None
        if estimate is not None and estimate in FLOOR_RANGE:
            set_known_word_floor(conn, user_id, estimate)
            floor = estimate
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE placement_runs
                   SET finished_at = %s, cefr = %s, grammar_band = %s,
                       vocabulary_band = %s, listening_band = %s,
                       vocab_estimate = %s, floor_written = %s,
                       grammar_stop = %s, error_profile = %s
                 WHERE id = %s
                """,
                (
                    now, grammar_band, grammar_band,
                    scoring.vocabulary_band(estimate),
                    scoring.listening_band(listening, served=[r["cefr"] for r in heard]),
                    estimate, floor, state.stop or run["grammar_stop"],
                    Jsonb(dict(profile)), run["id"],
                ),
            )
        sittings = _finished_sittings(conn, user_id, tz)
        conn.commit()
    logger.info("placement finished user_id=%s run=%s floor_written=%s",
                user_id, run["id"], floor is not None)
    return Result(scoring.shown(sittings), scoring.next_sitting_from(sittings[-1].finished_on))


def served_sets(conn, user_id: int) -> dict[int, frozenset[int]]:
    """run id → the bank ids it served. For the disjointness check and the
    operator; never on the wire."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT run_id, bank_id FROM placement_run_items WHERE user_id = %s",
            (user_id,),
        )
        out: dict[int, set[int]] = {}
        for run_id, bank_id in cur.fetchall():
            out.setdefault(int(run_id), set()).add(int(bank_id))
    return {k: frozenset(v) for k, v in out.items()}


def dumps(value: Any) -> str:
    """JSON for the build command's print."""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
