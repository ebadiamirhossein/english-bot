"""Saving any word from a video, and the words a learner has saved. **W31c.**

The operator, 2026-09-27: *a word that isn't highlighted, or that has no gloss,
cannot be saved at all — the learner has no way to keep a word they didn't
know.* The reference named was Trancy / Language Reactor: any word can be
clicked, looked up and saved.

**THE STANDING RULING HOLDS: THE APP NEVER GENERATES WHILE A LEARNER WAITS.**
`lookup` and `save` are the request path and reach no model — the netguard
fixture fails the test that tries. A word with a stored gloss is saved as two
cards at once (W13-ii's path, `cards.capture_from_gloss`); a word without one
is written to `word_saves_pending` (migration 035) and **`fill_pending`**, a
worker job behind `WORD_GLOSS_JOB`, explains it later and only then writes the
cards. **`pregen_today`**, behind `VIDEO_PREGEN_GLOSSES`, explains today's
assigned video ahead of the taps. Both reach the model through
`core.video.explain`, the one file on #292's allow-list — this module imports it
and calls nothing else that bills.

**THE TWO JOBS HAVE SEPARATE DAILY CEILINGS (C2):** taps 60 and pre-generation
40 per UTC day, each counted from `video_glosses` by `source`, each enforced
with `min()` inside the function whatever the caller passes — so a scheduled
job can never spend a learner's allowance.

**THE SENTENCE IS THE SERVER'S.** The client sends the word and the INDEX of the
line it was tapped in; the line's text comes from `core.video.lines` over the
stored cues — the same function that built the screen — never from the client.
A client that could supply the sentence could supply any sentence
(`SaveWordIn`'s recorded reason).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import tuple_row

from core.config import load_settings
from core.db import connection

logger = logging.getLogger(__name__)

#: Ruling Q6 and C2 (2026-09-27). **Enforced with `min()` inside each job.**
TAP_PER_RUN = 20
TAP_PER_DAY = 60
PREGEN_PER_LEARNER = 20
PREGEN_PER_DAY = 40
#: Refusals before a pending word is marked `no_meaning` (Q6).
MAX_ATTEMPTS = 3
#: My words, one page. No total is ever computed (CLAUDE.md §4, #160).
PAGE = 30

_TOKEN = re.compile(r"[A-Za-z][A-Za-z']*")


# ── the line a word was tapped in ────────────────────────────────────────────


@dataclass(frozen=True)
class TappedLine:
    text: str
    start: float | None


def _video_text(conn: Any, user_id: int, video_id: int) -> tuple[str | None, Any] | None:
    """The video's transcript and cues — **only if it is assigned to this
    learner** (any date, any kind). `None` when it is not: the route answers
    404 `not_assigned`, which W31a's copy already says plainly."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT v.transcript, v.transcript_cues
              FROM videos v
             WHERE v.id = %s
               AND EXISTS (SELECT 1 FROM video_assignments va
                            WHERE va.video_id = v.id AND va.user_id = %s)
            """,
            (video_id, user_id),
        )
        row = cur.fetchone()
    return None if row is None else (row[0], row[1])


def _contains(text: str, word: str) -> bool:
    folded = word.casefold()
    return any(t.casefold() == folded for t in _TOKEN.findall(text))


def tapped_line(transcript: str | None, cues: Any, word: str, index: int | None) -> TappedLine | None:
    """The display line the word was tapped in, or the first that holds it.

    **`index` is trusted only if that line really contains the word**; an index
    that does not (a stale page, a forged request) falls back to the first line
    that does. `None` when the word is in no line — the transcript was purged
    (#335), or the word was never in it.
    """
    from core.video.lines import lines_for, sentences_for

    if not transcript:
        return None
    lines = lines_for(cues) or sentences_for(transcript)
    if index is not None and 0 <= index < len(lines) and _contains(lines[index].text, word):
        line = lines[index]
        return TappedLine(line.text, line.start)
    for line in lines:
        if _contains(line.text, word):
            return TappedLine(line.text, line.start)
    return None


# ── the sheet ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Lookup:
    word: str
    lemma: str
    line: str | None
    #: `None` when no gloss exists yet — the sheet then offers Save anyway.
    meaning: dict | None
    image: dict | None
    #: `none` | `in_deck` | `pending` | `no_meaning`
    saved: str


def _native_language(conn: Any, user_id: int) -> str | None:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT native_language FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    return None if row is None else row[0]


def _saved_state(conn: Any, user_id: int, video_id: int, word: str, key: str) -> str:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            # `video:<id>` or `video:<id>@<s>` — never a LIKE on the bare id,
            # which would let video 4 match video 44.
            "SELECT 1 FROM cards WHERE user_id = %s AND front IN (%s, %s) "
            "AND (source_ref = %s OR source_ref LIKE %s) LIMIT 1",
            (user_id, word, key, f"video:{video_id}", f"video:{video_id}@%"),
        )
        if cur.fetchone() is not None:
            return "in_deck"
        cur.execute(
            "SELECT state FROM word_saves_pending WHERE user_id = %s AND video_id = %s AND word = %s",
            (user_id, video_id, word),
        )
        row = cur.fetchone()
    if row is None:
        return "none"
    return {"carded": "in_deck"}.get(row[0], row[0])


def lookup(user_id: int, *, video_id: int, word: str, line: int | None) -> Lookup | None:
    """What the word sheet shows. **Reads only; reaches no model.**

    `None` when the video is not this learner's (404). The meaning is the stored
    gloss — English, plus the learner's own language when `explain` produced
    it (ruling Q7) — or `None`; the picture is `lexeme_images`' for the lemma,
    when one was approved (ruling Q9 (C)).
    """
    from core.services import glosses as glosses_service
    from core.services import lexeme_images as images_service

    folded = word.casefold()
    with connection() as conn:
        text = _video_text(conn, user_id, video_id)
        if text is None:
            return None
        transcript, cues = text
        tapped = tapped_line(transcript, cues, folded, line)
        key = glosses_service.gloss_key(folded)
        gloss = glosses_service.gloss_for(conn, video_id, folded)
        native = _native_language(conn, user_id)
        saved = _saved_state(conn, user_id, video_id, folded, key)
    lexeme = images_service.lexeme_ids([key]).get(key)

    meaning = None
    if gloss is not None:
        meaning = {
            "definition": gloss.definition,
            "register": gloss.register,
            "neutral_equivalent": gloss.neutral_equivalent,
            "who_says_this": gloss.who_says_this,
            "l1": gloss.l1.get(native) if native else None,
            "l1_language": native if native and gloss.l1.get(native) else None,
        }
    image = images_service.face_for("recognition", lexeme) if lexeme else None
    return Lookup(
        word=folded,
        lemma=key,
        line=tapped.text if tapped else None,
        meaning=meaning,
        image=image,
        saved=saved,
    )


# ── Save ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SaveOutcome:
    #: `saved` | `already_saved` | `pending` | `no_line`
    state: str
    card_ids: tuple[int, ...] = ()
    #: For `pending` only: is a meaning actually coming? **True only while
    #: `WORD_GLOSS_JOB` is on** — with it off, *"ready soon"* would be a promise
    #: nothing keeps, so the sheet says the plainer thing (C4).
    meaning_soon: bool | None = None


def save(user_id: int, *, video_id: int, word: str, line: int | None, now: datetime) -> SaveOutcome | None:
    """One Save in the word sheet. **The one function the save route calls.**

    `None` → 404 (not this learner's video). With a gloss: two cards now,
    through `cards.capture_from_gloss`, with the tapped line as the sentence.
    Without one: a `word_saves_pending` row, and `pending` — **the card enters
    the deck only once it has a meaning** (W13-ii/2). A second Save of a word
    already waiting answers `pending` again: nothing is duplicated.
    `no_line` when the word is in no line of the stored text (purged, #335) —
    there is no sentence to keep it with, and a card without its sentence is
    what PRD §2.6.3 forbids.
    """
    from core.services import cards as cards_service
    from core.services import glosses as glosses_service

    folded = word.casefold()
    with connection() as conn:
        text = _video_text(conn, user_id, video_id)
        if text is None:
            return None
        transcript, cues = text
        gloss = glosses_service.gloss_for(conn, video_id, folded)
        tapped = tapped_line(transcript, cues, folded, line)

        if gloss is not None:
            sentence = tapped.text if tapped else gloss.context_sentence
            start = tapped.start if tapped else gloss.cue_start_s
            result = cards_service.capture_from_gloss(
                conn, user_id, video_id=video_id, gloss=gloss,
                context_sentence=sentence, cue_start_s=start, now=now,
            )
            conn.commit()
            return SaveOutcome(result.state, tuple(result.card_ids))

        if tapped is None:
            return SaveOutcome("no_line")
        key = glosses_service.gloss_key(folded)
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                INSERT INTO word_saves_pending
                    (user_id, video_id, word, lemma, context_sentence, cue_start_s, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, video_id, word) DO NOTHING
                RETURNING id
                """,
                (user_id, video_id, folded, key if key != folded else None,
                 tapped.text, tapped.start, now),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT state FROM word_saves_pending WHERE user_id = %s AND video_id = %s AND word = %s",
                    (user_id, video_id, folded),
                )
                existing = cur.fetchone()
        conn.commit()
    if inserted is None and existing and existing[0] == "carded":
        return SaveOutcome("already_saved")
    return SaveOutcome("pending", meaning_soon=bool(load_settings().word_gloss_job))


# ── My words ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SavedWord:
    word: str
    sentence: str | None
    source_title: str | None
    #: `in_deck` | `pending` | `no_meaning`
    state: str
    saved_at: datetime


def my_words(user_id: int, *, before: datetime | None = None) -> list[SavedWord]:
    """The words this learner saved from videos, newest first, one page.

    **NO COUNT, NO TOTAL, NO "N LEFT"** (CLAUDE.md §4, #160): the page is a
    list and "show more" asks for the next one by time. A word in the deck is
    listed once per sentence (its two cards are one save); a pending word shows
    until its cards exist, then the cards represent it.
    """
    with connection() as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            WITH saved AS (
                SELECT DISTINCT ON (front, context_sentence)
                       front AS word, context_sentence AS sentence, source_title,
                       'in_deck' AS state, captured_at AS saved_at
                  FROM cards
                 WHERE user_id = %(u)s AND source_ref LIKE 'video:%%'
                       AND captured_at IS NOT NULL
                 ORDER BY front, context_sentence, captured_at
            ), waiting AS (
                SELECT p.word, p.context_sentence AS sentence, v.title AS source_title,
                       p.state, p.created_at AS saved_at
                  FROM word_saves_pending p JOIN videos v ON v.id = p.video_id
                 WHERE p.user_id = %(u)s AND p.state <> 'carded'
            )
            SELECT word, sentence, source_title, state, saved_at
              FROM (SELECT * FROM saved UNION ALL SELECT * FROM waiting) words
             WHERE %(before)s::timestamptz IS NULL OR saved_at < %(before)s::timestamptz
             ORDER BY saved_at DESC, word
             LIMIT %(page)s
            """,
            {"u": user_id, "before": before, "page": PAGE},
        )
        rows = cur.fetchall()
    return [SavedWord(str(r[0]), r[1], r[2], str(r[3]), r[4]) for r in rows]


# ── the jobs (worker only; BILLED; each behind its own flag) ─────────────────


def _utc_midnight(now: datetime) -> datetime:
    at = now.astimezone(timezone.utc)
    return at.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class JobCounts:
    carded: int = 0
    generated: int = 0
    refused: int = 0
    no_meaning: int = 0
    skipped_ceiling: int = 0
    notes: list[str] = field(default_factory=list)


def fill_pending(now: datetime, *, limit: int = TAP_PER_RUN) -> JobCounts:
    """`WORD_GLOSS_JOB`: explain the words learners saved with no meaning.

    Oldest first. A row whose word gained a gloss since (pre-generation, or
    another learner's tap on the same video) is carded **without a call**. A
    call is made only within `min(limit, TAP_PER_RUN, TAP_PER_DAY − today's
    tap glosses)`. A refusal counts an attempt; the third marks the word
    `no_meaning`, which My words says plainly. **One call per word, no call
    driven by another's output** (#292).
    """
    from core.llm import LLMError
    from core.services import cards as cards_service
    from core.services import glosses as glosses_service
    from core.video import explain

    counts = JobCounts()
    with connection() as conn:
        spent = glosses_service.generated_since(conn, source="tap", since=_utc_midnight(now))
        budget = max(0, min(limit, TAP_PER_RUN, TAP_PER_DAY - spent))
        languages = glosses_service.learner_languages(conn)
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, video_id, word, lemma, context_sentence, cue_start_s, attempts
                  FROM word_saves_pending
                 WHERE state = 'pending'
                 ORDER BY created_at, id
                 LIMIT 200
                 FOR UPDATE SKIP LOCKED
                """
            )
            rows = cur.fetchall()
        model_id = str(load_settings().llm_model)
        for row_id, user_id, video_id, word, lemma, sentence, start, attempts in rows:
            gloss = glosses_service.gloss_for(conn, video_id, word)
            if gloss is None:
                if budget <= 0:
                    counts.skipped_ceiling += 1
                    continue
                key = lemma or word
                budget -= 1
                try:
                    draft = explain.explain_one(key, sentence, l1=languages)
                except (LLMError, explain.GlossRejected) as exc:
                    counts.refused += 1
                    logger.warning("pending id=%s refused: %s", row_id, type(exc).__name__)
                    final = attempts + 1 >= MAX_ATTEMPTS
                    conn.execute(
                        "UPDATE word_saves_pending SET attempts = attempts + 1, "
                        "state = CASE WHEN %s THEN 'no_meaning' ELSE state END, "
                        "resolved_at = CASE WHEN %s THEN %s ELSE resolved_at END WHERE id = %s",
                        (final, final, now, row_id),
                    )
                    counts.no_meaning += int(final)
                    continue
                glosses_service.insert_gloss(
                    conn, video_id=video_id, word=key, context_sentence=sentence,
                    cue_start_s=float(start) if start is not None else None,
                    definition=draft.definition, register=draft.register,
                    neutral_equivalent=draft.neutral_equivalent,
                    who_says_this=draft.who_says_this, model=model_id,
                    l1=draft.l1, source="tap",
                )
                counts.generated += 1
                gloss = glosses_service.gloss_for(conn, video_id, word)
                if gloss is None:  # pragma: no cover - the insert just wrote it
                    continue
            cards_service.capture_from_gloss(
                conn, user_id, video_id=video_id, gloss=gloss,
                context_sentence=sentence,
                cue_start_s=float(start) if start is not None else None, now=now,
            )
            conn.execute(
                "UPDATE word_saves_pending SET state = 'carded', resolved_at = %s WHERE id = %s",
                (now, row_id),
            )
            counts.carded += 1
        conn.commit()
    return counts


def pregen_today(now: datetime, *, per_learner: int = PREGEN_PER_LEARNER) -> JobCounts:
    """`VIDEO_PREGEN_GLOSSES`: explain today's assigned daily video ahead of the
    taps (ruling Q5 (b): today's daily video only, ≤20 lemmas per learner).

    Uses `explain.plan_for` — the below-floor words of this learner, minus what
    the video already holds — so a second run buys nothing twice. **Capped at
    `min(per_learner, PREGEN_PER_LEARNER)` per learner and `PREGEN_PER_DAY −
    today's pregen glosses` overall**, whatever the caller passes.
    """
    from core.llm import LLMError
    from core.services import glosses as glosses_service
    from core.services import video as video_service
    from core.services.sessions import local_today
    from core.video import explain

    counts = JobCounts()
    each = max(0, min(per_learner, PREGEN_PER_LEARNER))
    with connection() as conn:
        spent = glosses_service.generated_since(conn, source="pregen", since=_utc_midnight(now))
        budget = max(0, PREGEN_PER_DAY - spent)
        languages = glosses_service.learner_languages(conn)
        model_id = str(load_settings().llm_model)
        for user_id, tz in video_service.learner_timezones(conn):
            if budget <= 0:
                counts.skipped_ceiling += 1
                continue
            today = video_service.today_for(conn, user_id, on=local_today(tz, now))
            if today is None or not today.transcript:
                continue
            plan = explain.plan_for(conn, today.video_id, user_id)
            for word, line, start in plan.words[: min(each, budget)]:
                budget -= 1
                try:
                    draft = explain.explain_one(word, line, l1=languages)
                except (LLMError, explain.GlossRejected) as exc:
                    counts.refused += 1
                    logger.warning("pregen video=%s refused: %s", today.video_id, type(exc).__name__)
                    continue
                if glosses_service.insert_gloss(
                    conn, video_id=today.video_id, word=draft.word, context_sentence=line,
                    cue_start_s=start, definition=draft.definition, register=draft.register,
                    neutral_equivalent=draft.neutral_equivalent,
                    who_says_this=draft.who_says_this, model=model_id,
                    l1=draft.l1, source="pregen",
                ) is not None:
                    counts.generated += 1
        conn.commit()
    return counts
