"""`video_glosses` — the pre-generated definition store. W13-ii, migration 023.

**Every query against `video_glosses` lives here and nowhere else** (#190, one
producer). `core.video.explain` produces the rows and holds no SQL of its own;
`apps/api/routers/video.py` reads them through `core.services.cards`'s capture
path and never touches this table directly.

────────────────────────────────────────────────────────────────────────────────
WHY THIS TABLE EXISTS AT ALL — §2g's OPTION (a) WAS RE-TESTED AND IS DEAD

The W13 plan's position was *write pre-generated definitions straight into
`cards` at generation time, and take no number*. It does not survive contact
with the tree:

    `core.services.cards.due_queue` filters on `user_id` and `due <= now`
    AND NOTHING ELSE. There is no status column on `cards`.

**So every row in `cards` is in the learner's deck.** A gloss exists before any
learner taps; a card exists only after a save. Writing unsaved glosses into
`cards` would put words in someone's deck they never chose, serve them in block
1 the same day, and count toward #170's deck-size trigger — and `cards.due` is
`NOT NULL`, so such a row would have to carry a due date, which is a lie with no
honest value.

**A gloss is a candidate; a card is a commitment.** Different objects, different
tables. Option (b) — the `video_coverage` row — stays refused: §1b ruled that
table an audit record and it is not repurposed.

────────────────────────────────────────────────────────────────────────────────
§1a IS RULED: PRE-GENERATE

Definitions and register tags are produced by a human-run command **before the
week**; a tap reads a stored row. Nothing in this module generates, and nothing
on the request path reaches a model — which is the standing ruling of
2026-08-27 (*the app never generates while a learner waits, and never while
nobody is watching*) held by construction rather than by care.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from core.db import connection

#: `cards.register` values that are receptive-only until the neutral equivalent
#: is mastered. **MEASURED AGAINST 013's CHECKS, NOT READ OFF THEM** — see
#: `core.services.cards.capture_card_types` for the run and the reasoning.
RECEPTIVE_REGISTERS = ("informal", "slang", "taboo")


@dataclass(frozen=True, slots=True)
class Gloss:
    """One pre-generated explanation of one word in one video's line.

    `cue_start_s` is `None` for a video whose cues were never stored or were
    refused by the identity gate. **That is the third state and not an error**
    (#330's shape): the card it produces carries the sentence and no timestamp.
    """

    id: int
    video_id: int
    word: str
    context_sentence: str
    cue_start_s: float | None
    definition: str
    register: str
    neutral_equivalent: str | None
    who_says_this: str | None
    #: W31c (035): the meaning in the learners' languages, `{"fa": …, "lt": …}`,
    #: from the same `explain` call. Shown in the word sheet only.
    l1: dict
    #: W31c (035): `manual` | `pregen` | `tap` — who asked for it.
    source: str


def _row(row: tuple) -> Gloss:
    """**AN EXPLICIT TUPLE CURSOR EVERYWHERE IN THIS MODULE**, for
    `core.services.cards.lemmas_with_a_card`'s reason: these functions run on a
    CALLER-OWNED connection and a caller's row factory is not ours to assume.
    `core.db.connection()` yields dict rows and a plain `psycopg.connect` yields
    tuples, and **both reach here** — the generator through the pool, the route
    through the pool, and the tests through their own connection. Found by the
    tests, which use the second kind.
    """
    start = row[4]
    return Gloss(
        id=int(row[0]),
        video_id=int(row[1]),
        word=str(row[2]),
        context_sentence=str(row[3]),
        cue_start_s=float(start) if isinstance(start, (int, float, Decimal)) else None,
        definition=str(row[5]),
        register=str(row[6]),
        neutral_equivalent=row[7],
        who_says_this=row[8],
        l1=dict(row[9] or {}),
        source=str(row[10]),
    )


_COLUMNS = """
    id, video_id, word, context_sentence, cue_start_s, definition,
    register, neutral_equivalent, who_says_this, l1, source
"""


def gloss_key(word: str) -> str:
    """The key a gloss for this tapped word is WRITTEN under (#468, 035).

    **The coverage lemma when it resolves, else the casefolded surface** — what
    `core.video.explain` has always written (it iterates
    `coverage.unknown_lemmas`), stated at last rather than implied. The same
    function the writer used, so the two cannot disagree; #162's hazard
    (`tier` → `ti`) was a ledger write through `lexeme_id`, W12a removed the
    `-er`/`-est` rules that produced it, and a key misread here shows a meaning
    — it never writes a ledger row.
    """
    from core.lexicon.normalize import lemmatize

    folded = word.casefold()
    return lemmatize(folded) or folded


def gloss_for(conn: Any, video_id: int, word: str) -> Gloss | None:
    """One video's gloss for one tapped word, or `None`.

    **Surface first, then the lemma (#468).** `explain` writes the coverage
    lemma, so a tap on *parties* against a gloss stored as *party* used to answer
    `no_gloss` even after generation. The surface is tried first so a gloss
    written under the exact form (a pending save whose word has no lemma) is
    found without a lemmatiser at all.
    """
    folded = word.casefold()
    keys = [folded]
    lemma = gloss_key(folded)
    if lemma != folded:
        keys.append(lemma)
    with conn.cursor(row_factory=tuple_row) as cur:
        for key in keys:
            cur.execute(
                f"SELECT {_COLUMNS} FROM video_glosses WHERE video_id = %s AND word = %s",
                (video_id, key),
            )
            row = cur.fetchone()
            if row is not None:
                return _row(row)
    return None


def glosses_for_video(conn: Any, video_id: int) -> list[Gloss]:
    """Every gloss this video holds — W32b's map carries them as "here", the
    meaning IN THIS VIDEO, shown before the dictionary's (context beats
    dictionary)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM video_glosses WHERE video_id = %s ORDER BY word",
            (video_id,),
        )
        return [_row(r) for r in cur.fetchall()]


def generated_since(conn: Any, *, source: str, since: Any) -> int:
    """How many glosses of one `source` were written since `since`.

    **The two jobs' daily ceilings read this (C2)**, by source, so the
    pre-generation job's count can never use up a learner's own taps.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT count(*) FROM video_glosses WHERE source = %s AND generated_at >= %s",
            (source, since),
        )
        row = cur.fetchone()
    return int(row[0])


def learner_languages(conn: Any) -> tuple[str, ...]:
    """The native languages of onboarded learners — what `explain` is asked
    for alongside the English (ruling Q7). Sorted, so a request is stable."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT DISTINCT native_language FROM users WHERE onboarded AND native_language IS NOT NULL"
        )
        rows = cur.fetchall()
    return tuple(sorted(str(r[0]) for r in rows if r[0]))


def words_with_a_gloss(conn: Any, video_id: int) -> frozenset[str]:
    """Every word this video already has a gloss for.

    The generator's anti-join: a second run buys the shortfall rather than
    re-buying the video. `core.services.cards.lemmas_with_a_card`'s shape, and
    its reason — the `UNIQUE (video_id, word)` index stays the guarantee and
    this is the pre-check, so a re-run selects nothing before it spends
    anything.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT word FROM video_glosses WHERE video_id = %s", (video_id,))
        rows = cur.fetchall()
    return frozenset(str(r[0]) for r in rows)


def insert_gloss(
    conn: Any,
    *,
    video_id: int,
    word: str,
    context_sentence: str,
    cue_start_s: float | None,
    definition: str,
    register: str,
    neutral_equivalent: str | None,
    who_says_this: str | None,
    model: str,
    l1: dict | None = None,
    source: str = "manual",
) -> int | None:
    """Store one gloss. `None` when this video already has one for this word.

    **The conflict is a no-op rather than an error**, which is the second half
    of the generator's idempotency; the first is `words_with_a_gloss`. Two
    independent guarantees on the same path — `migrate_chunks`'s property, and
    the one 015's header says the capture path needed.

    **No copy gate is applied here and that is deliberate.** The gate belongs at
    the generator, before a billed draft is ever offered for storage, and
    applying it twice would put the rule in two places. See
    `core.video.explain`, which refuses a draft rather than repairing one.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO video_glosses
                (video_id, word, context_sentence, cue_start_s, definition,
                 register, neutral_equivalent, who_says_this, model, l1, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (video_id, word) DO NOTHING
            RETURNING id
            """,
            (
                video_id,
                word.casefold(),
                context_sentence,
                cue_start_s,
                definition,
                register,
                neutral_equivalent,
                who_says_this,
                model,
                Jsonb(l1 or {}),
                source,
            ),
        )
        row = cur.fetchone()
    return None if row is None else int(row[0])


def gloss_count(conn: Any, video_id: int) -> int:
    """How many glosses this video holds. The dry run's before-and-after."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT count(*) FROM video_glosses WHERE video_id = %s", (video_id,)
        )
        row = cur.fetchone()
    return int(row[0])


@dataclass(frozen=True, slots=True)
class GlossSource:
    """One video's text, its cues and its title — everything the generator reads.

    **It lives here because `core/video/explain.py` may hold no SQL and import
    no driver** (`test_no_sql_outside_services`, `test_video_package_is_pure`).
    Both refusals fired on the first draft of that module and both were correct:
    CLAUDE.md §2 puts SQL in service functions, and the video package's purity is
    what makes its one model-reaching file reviewable.
    """

    title: str | None
    transcript: str | None
    cues: Any


def source_for(conn: Any, video_id: int) -> GlossSource | None:
    """The video row the generator plans against, or `None` if there is no row."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT title, transcript, transcript_cues FROM videos WHERE id = %s",
            (video_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return GlossSource(title=row[0], transcript=row[1], cues=row[2])
