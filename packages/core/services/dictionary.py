"""`word_dictionary` — one short meaning per word, written ahead of time. W32.

**Every query against `word_dictionary` lives here and nowhere else** (#190, one
producer). The model is reached only through `core.video.explain.define_words`
— the one file on #292's allow-list — which this module imports and calls
nothing else that bills.

────────────────────────────────────────────────────────────────────────────────
WHY THIS EXISTS

The operator, 2026-09-27: hovering or tapping ANY word on /watch shows what it
means in under a second, and then the learner decides whether to keep it
(Trancy). Only the ~17 below-floor words of a video had a `video_glosses` row,
and a live call takes 4.4–8.0 s. **So the meaning is data that exists before
the page loads**: this table, filled in batches by the human-run backfill
(`python -m core.video.dictionary`, dry by default), topped up by a flagged job
(W32c), and — for a word nobody filled — by the one scoped request-path lookup
(W32c). The page reads it through `meanings_for` (W32b) in one request.

────────────────────────────────────────────────────────────────────────────────
THE KEY IS THE PAGE'S TOKEN, THROUGH THE GLOSS KEY

`TOKEN` is the client's word regex (`apps/web/components/video/lines.ts`'s
`PIECES`), so the server keys exactly the tokens the learner can tap; each is
keyed by `glosses.gloss_key` — the coverage lemma, else the casefolded surface —
the function the gloss writer and reader already share (#468). **A shared
contract file (`apps/web/lib/meaning-keys.contract.json`, W32b) pins the two
sides together**, as W31a's did for the save request.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

#: The client's word regex, verbatim (`lines.ts` `PIECES`, the word group).
TOKEN = re.compile(r"[A-Za-zÀ-ɏ0-9][A-Za-zÀ-ɏ0-9']*")
#: `PIECES`' other group: a sound tag is one piece and never a word.
SOUND_TAG = re.compile(r"\[[^\]]*\]")

#: Ruling C1 (2026-09-28): the backfill buys the pool's words plus the most
#: frequent TAGGED lexemes, by `lexemes.freq_rank`. Untagged rows — names and
#: abbreviations, 4,564 in `data/lexemes.tsv` — are reachable only through a
#: video or a miss.
TOP_LEXEMES = 5000

#: List price per million tokens (input, output), **checked 2026-09-28 against
#: the Claude API reference bundled with the session** — the same source W31e
#: used. A model not listed prints its token counts and no dollar figure.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

#: **Typical output tokens per word — an estimate, labelled as one.** A one-sense
#: entry with `fa` and `lt` carries what one W31e gloss carried, and W31e's live
#: gloss replies were 129–287 output tokens, thinking included (the two hard
#: re-runs 451 and 457). A dictionary call shares its thinking across 20 words,
#: so the typical figure is taken at 200. **The ceiling beside it is exact
#: arithmetic on `max_tokens` and is the number to budget against.**
TYPICAL_OUTPUT_PER_WORD = 200

#: C3: how long the run waits, in turn, when the provider is rate-limited or
#: overloaded after `chat()`'s own three attempts. **Never a refusal.** When
#: these are spent the words are DEFERRED — a re-run buys them — and the run
#: stops, since every other batch would meet the same weather.
TRANSIENT_WAITS_S = (30.0, 60.0, 120.0, 240.0, 480.0, 600.0)



# ── the key ──────────────────────────────────────────────────────────────────


def key_for(token: str) -> str | None:
    """One tapped token → its dictionary key, or `None` when no key can hold it
    (a number, a word with letters outside a–z)."""
    from core.services.glosses import gloss_key
    from core.video.explain import WORD_KEY

    key = gloss_key(token)
    return key if WORD_KEY.match(key) else None


def _lines(source: Any) -> list[Any]:
    from core.video.lines import lines_for, sentences_for

    return lines_for(source.cues) or sentences_for(source.transcript)


def page_tokens(text: str) -> list[str]:
    """The words the page makes tappable in one line, lower-cased as the client
    lower-cases them (`toLowerCase`, which `str.lower` matches and `casefold`
    does not: *straße*). **Pinned against the client by
    `apps/web/lib/meaning-keys.contract.json`**, read by both suites."""
    return [t.lower() for t in TOKEN.findall(SOUND_TAG.sub(" ", text))]


def keys_of_lines(texts: Iterable[str], names: frozenset[str]) -> dict[str, str]:
    """`{page token: key}` for every token the page shows, names left out."""
    forms: dict[str, str] = {}
    for text in texts:
        for token in page_tokens(text):
            if token in forms or token in names:
                continue
            key = key_for(token)
            if key is not None:
                forms[token] = key
    return forms


def video_keys(conn: Any, video_id: int) -> tuple[dict[str, str], frozenset[str]]:
    """One video's `{token: key}` over its display lines, and its names (C1's
    set, W31e's rule: a name is never bought)."""
    from core.services import glosses as glosses_service
    from core.video.lines import names_for

    source = glosses_service.source_for(conn, video_id)
    if source is None or not source.transcript:
        return {}, frozenset()
    names = names_for(source.cues, source.transcript)
    return keys_of_lines((line.text for line in _lines(source)), names), names


# ── the store ────────────────────────────────────────────────────────────────


def held(conn: Any, keys: Iterable[str]) -> frozenset[str]:
    """Which of these keys already have an entry — the anti-join, so a re-run
    buys the shortfall and nothing twice (`migrate_chunks`' property; the
    UNIQUE index is the second guarantee)."""
    wanted = sorted(set(keys))
    if not wanted:
        return frozenset()
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT lemma FROM word_dictionary WHERE lemma = ANY(%s)", (wanted,))
        return frozenset(str(r[0]) for r in cur.fetchall())


def insert_entry(conn: Any, entry: Any, *, model: str, source: str) -> bool:
    """Store one validated entry. `False` when the word already has one.

    **No gate here, deliberately** — `explain.validate_entry` refused anything
    that should not be stored before this was offered it (`insert_gloss`'s
    reason: the rule in one place)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO word_dictionary
                (lemma, kind, senses, register, neutral_equivalent, who_says_this, model, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (lemma) DO NOTHING
            RETURNING id
            """,
            (
                entry.word,
                entry.kind,
                Jsonb([s.wire() for s in entry.senses]),
                entry.register,
                entry.neutral_equivalent,
                entry.who_says_this,
                model,
                source,
            ),
        )
        return cur.fetchone() is not None


def generated_since(conn: Any, *, source: str, since: Any) -> int:
    """How many entries of one source were written since `since` — what the
    top-up job's and the miss path's daily ceilings count (C2's shape, 035)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT count(*) FROM word_dictionary WHERE source = %s AND generated_at >= %s",
            (source, since),
        )
        return int(cur.fetchone()[0])


def entries_for(conn: Any, keys: Iterable[str]) -> dict[str, dict]:
    """The stored entries for these keys, as plain dicts."""
    wanted = sorted(set(keys))
    if not wanted:
        return {}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT lemma, kind, senses, register, neutral_equivalent, who_says_this "
            "FROM word_dictionary WHERE lemma = ANY(%s)",
            (wanted,),
        )
        rows = cur.fetchall()
    return {
        str(r[0]): {
            "kind": r[1],
            "senses": list(r[2] or []),
            "register": r[3],
            "neutral_equivalent": r[4],
            "who_says_this": r[5],
        }
        for r in rows
    }


def entry_for(conn: Any, key: str) -> dict | None:
    """One stored entry, or `None`."""
    return entries_for(conn, [key]).get(key)


@dataclass(frozen=True)
class DictionaryGloss:
    """A dictionary entry in the shape `cards.capture_from_gloss` reads.

    **W32b (§D): ONE CARD WRITER, NOT TWO** (#190). A Save of a word the video
    never glossed but the dictionary holds goes through the same function a
    gloss does — so the register pairs, `lexeme_id` (#469) and the
    already-saved rules are the ones already measured, not a copy of them.

    **The sense on the card is the FIRST** — the model is asked for the most
    common first. The video's own gloss, when there is one, never reaches here:
    it wins before the dictionary is read (context beats dictionary, §C).
    """

    word: str
    definition: str
    register: str
    neutral_equivalent: str | None
    who_says_this: str | None


def as_gloss(key: str, entry: dict) -> DictionaryGloss | None:
    """A stored entry → the capture's input, or `None` for a name (no meaning
    to keep: the save stays pending, W31e's rule)."""
    if entry.get("kind") != "word" or not entry.get("senses"):
        return None
    return DictionaryGloss(
        word=key,
        definition=str(entry["senses"][0]["definition"]),
        register=str(entry["register"]),
        neutral_equivalent=entry.get("neutral_equivalent"),
        who_says_this=entry.get("who_says_this"),
    )


def meanings_for(user_id: int, video_id: int) -> dict | None:
    """**W32b — THE MAP: everything hover and tap need, in one request.** `None`
    when the video is not this learner's (the route answers 404). The reads;
    `assemble_meanings` is the shape."""
    from core.db import connection
    from core.services import glosses as glosses_service
    from core.services import lexeme_images as images_service

    with connection() as conn:
        found = _assigned_video(conn, user_id, video_id)
        if found is None:
            return None
        forms, names, native = found
        stored = entries_for(conn, forms.values())
        here = glosses_service.glosses_for_video(conn, video_id)
        saved = _saved_words(conn, user_id, video_id)

    keys = sorted(set(forms.values()))
    images: dict[str, dict] = {}
    ids = images_service.lexeme_ids(keys) if keys else {}
    if ids:
        faces = images_service.all_faces()
        images = {key: faces[i] for key, i in ids.items() if i in faces}
    return assemble_meanings(
        forms=forms, names=names, stored=stored, here=here, saved=saved,
        images=images, lang=native or None,
    )


def _assigned_video(
    conn: Any, user_id: int, video_id: int
) -> tuple[dict[str, str], frozenset[str], str | None] | None:
    """This learner's video, as `(forms, names, native language)` — or `None`
    when it is not assigned to them (any date, any kind: the 404 W31a's copy
    already says plainly)."""
    from types import SimpleNamespace

    from core.video.lines import names_for

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT v.transcript, v.transcript_cues, u.native_language
              FROM videos v JOIN users u ON u.id = %s
             WHERE v.id = %s
               AND EXISTS (SELECT 1 FROM video_assignments va
                            WHERE va.video_id = v.id AND va.user_id = u.id)
            """,
            (user_id, video_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    transcript, cues, native = row
    if not transcript:
        return {}, frozenset(), native
    names = names_for(cues, transcript)
    texts = [line.text for line in _lines(SimpleNamespace(cues=cues, transcript=transcript))]
    return keys_of_lines(texts, names), names, native


def assemble_meanings(
    *,
    forms: dict[str, str],
    names: frozenset[str],
    stored: dict[str, dict],
    here: list[Any],
    saved: dict[str, str],
    images: dict[str, dict],
    lang: str | None,
) -> dict:
    """The map's wire shape, from what `meanings_for` read. **Pure**, so the web
    fixture is built by this function and not by hand (#190's shape).

    Compact on purpose — it is the largest response the app sends:
    `entries` `{key: {k: "w"|"n", r, s: [[pos, definition, l1]], n?, w?}}` in
    the learner's own language only; `forms` `{page token: key}` where they
    differ, so the client does no lemmatising (`key = forms[t] ?? t`); `here`
    this video's own glosses (context beats dictionary); `names` the video's
    C1 set; `saved` what this learner already kept from this video; `images`
    the approved pictures' faces, by key.
    """
    entries = {key: wire_entry(entry, lang) for key, entry in sorted(stored.items())}

    here_wire: dict[str, dict] = {}
    for gloss in here:
        item: dict[str, Any] = {"d": gloss.definition, "r": gloss.register}
        if gloss.neutral_equivalent:
            item["n"] = gloss.neutral_equivalent
        if gloss.who_says_this:
            item["w"] = gloss.who_says_this
        l1 = gloss.l1.get(lang) if lang else None
        if l1:
            item["l1"] = l1
        here_wire[gloss.word] = item

    return {
        "l1": lang,
        "entries": entries,
        "forms": {t: k for t, k in sorted(forms.items()) if t != k},
        "here": here_wire,
        "names": sorted(names),
        "saved": dict(sorted(saved.items())),
        "images": images,
    }


def wire_entry(entry: dict, lang: str | None) -> dict:
    """One stored entry → the map's compact shape, in ONE language."""
    if entry["kind"] == "name":
        return {"k": "n"}
    wire: dict[str, Any] = {
        "k": "w",
        "r": entry["register"],
        "s": [
            [s.get("pos"), s.get("definition"), (s.get("l1") or {}).get(lang) if lang else None]
            for s in entry["senses"]
        ],
    }
    if entry.get("neutral_equivalent"):
        wire["n"] = entry["neutral_equivalent"]
    if entry.get("who_says_this"):
        wire["w"] = entry["who_says_this"]
    return wire


def _saved_words(conn: Any, user_id: int, video_id: int) -> dict[str, str]:
    """`{word: in_deck | pending | no_meaning}` for this learner and video —
    card fronts (a gloss's or an entry's key) and pending surfaces."""
    saved: dict[str, str] = {}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            # `video:<id>` or `video:<id>@<s>` — never a bare LIKE on the id,
            # which would let video 4 match video 44 (W31c's rule).
            "SELECT DISTINCT front FROM cards WHERE user_id = %s "
            "AND (source_ref = %s OR source_ref LIKE %s)",
            (user_id, f"video:{video_id}", f"video:{video_id}@%"),
        )
        for (front,) in cur.fetchall():
            saved[str(front)] = "in_deck"
        cur.execute(
            "SELECT word, state FROM word_saves_pending WHERE user_id = %s AND video_id = %s",
            (user_id, video_id),
        )
        for word, state in cur.fetchall():
            saved.setdefault(str(word), "in_deck" if state == "carded" else str(state))
    return saved


# ── the plan (C1) ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackfillPlan:
    pool: tuple[str, ...]
    lexemes: tuple[str, ...]
    union: tuple[str, ...]
    to_buy: tuple[str, ...]
    #: Lexemes carrying no POS tag, left out of (b). Reachable by video or miss.
    untagged_excluded: int
    #: Tagged lexemes in the top-N that no page token can equal (*t-shirt*).
    not_a_token_excluded: int
    pool_videos: int


def pool_keys(conn: Any, video_ids: list[int] | None = None) -> tuple[set[str], int]:
    """(a): every key in the lines of the `ok` pool's videos (or of these)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        if video_ids is None:
            cur.execute("SELECT id FROM videos WHERE transcript_status = 'ok' ORDER BY id")
        else:
            cur.execute(
                "SELECT id FROM videos WHERE transcript_status = 'ok' AND id = ANY(%s) ORDER BY id",
                (list(video_ids),),
            )
        ids = [int(r[0]) for r in cur.fetchall()]
    keys: set[str] = set()
    for vid in ids:
        forms, _names = video_keys(conn, vid)
        keys.update(forms.values())
    return keys, len(ids)


def top_lexemes(conn: Any, top: int) -> tuple[list[str], int, int]:
    """(b): the `top` most frequent lexemes that carry a POS tag, by
    `lexemes.freq_rank`; plus how many untagged rows the table holds, and how
    many of the chosen can never be a page token."""
    from core.video.explain import WORD_KEY

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT lemma FROM lexemes WHERE pos IS NOT NULL AND freq_rank IS NOT NULL "
            "ORDER BY freq_rank, lemma LIMIT %s",
            (max(0, top),),
        )
        chosen = [str(r[0]) for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM lexemes WHERE pos IS NULL")
        untagged = int(cur.fetchone()[0])
    words = [w for w in chosen if WORD_KEY.match(w)]
    return words, untagged, len(chosen) - len(words)


def plan_backfill(
    conn: Any, *, top: int = TOP_LEXEMES, video_ids: list[int] | None = None, scope: str = "c1"
) -> BackfillPlan:
    """C1's scope: (a) ∪ (b), minus what is held. `scope='all'` takes every
    tagged-or-not lexeme that can be a token — **for later, never the default**."""
    pool, n_videos = pool_keys(conn, video_ids)
    if scope == "all":
        top = 10**6
        lexemes, untagged, not_token = top_lexemes(conn, top)
        from core.video.explain import WORD_KEY

        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute("SELECT lemma FROM lexemes WHERE pos IS NULL")
            lexemes += [str(r[0]) for r in cur.fetchall() if WORD_KEY.match(str(r[0]))]
        untagged = 0
    else:
        lexemes, untagged, not_token = top_lexemes(conn, top)
    union = sorted(pool | set(lexemes))
    have = held(conn, union)
    return BackfillPlan(
        pool=tuple(sorted(pool)),
        lexemes=tuple(lexemes),
        union=tuple(union),
        to_buy=tuple(w for w in union if w not in have),
        untagged_excluded=untagged,
        not_a_token_excluded=not_token,
        pool_videos=n_videos,
    )


# ── the cost line ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Cost:
    words: int
    calls: int
    input_tokens: int
    typical_output_tokens: int
    ceiling_output_tokens: int
    typical_usd: float | None
    ceiling_usd: float | None


def _input_tokens_per_call(n_words: int) -> int:
    from core.video.explain import DICT_SYSTEM

    # ~4 characters a token for the English system prompt; ~4 tokens a word
    # line. An estimate; the ceiling below is dominated by `max_tokens`.
    return len(DICT_SYSTEM) // 4 + 40 + 4 * n_words


def estimate(n_words: int, *, n_langs: int, model: str) -> Cost:
    from core.video.explain import DICT_BATCH, dictionary_max_tokens

    calls = math.ceil(n_words / DICT_BATCH) if n_words else 0
    full, rest = divmod(n_words, DICT_BATCH)
    sizes = [DICT_BATCH] * full + ([rest] if rest else [])
    input_tokens = sum(_input_tokens_per_call(n) for n in sizes)
    ceiling_out = sum(dictionary_max_tokens(n, n_langs) for n in sizes)
    typical_out = n_words * TYPICAL_OUTPUT_PER_WORD
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return Cost(n_words, calls, input_tokens, typical_out, ceiling_out, None, None)
    p_in, p_out = price
    return Cost(
        words=n_words,
        calls=calls,
        input_tokens=input_tokens,
        typical_output_tokens=typical_out,
        ceiling_output_tokens=ceiling_out,
        typical_usd=(input_tokens * p_in + typical_out * p_out) / 1_000_000,
        ceiling_usd=(input_tokens * p_in + ceiling_out * p_out) / 1_000_000,
    )


def cost_line(cost: Cost, model: str) -> str:
    if cost.ceiling_usd is None:
        return (
            f"calls_at_most={cost.calls} input_tokens~{cost.input_tokens} "
            f"output_tokens_typical~{cost.typical_output_tokens} "
            f"output_tokens_ceiling={cost.ceiling_output_tokens} "
            f"(no list price recorded for {model}; no dollar figure)"
        )
    return (
        f"calls_at_most={cost.calls} model={model} "
        f"typical_usd~{cost.typical_usd:.2f} ceiling_usd={cost.ceiling_usd:.2f}"
    )


# ── the run ──────────────────────────────────────────────────────────────────


@dataclass
class RunReport:
    planned: int = 0
    written: int = 0
    already_held: int = 0
    refused: Counter = field(default_factory=Counter)
    deferred: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: str | None = None


_REASONS = (
    "not a single word", "not json", "no entries list", "no entry", "no-guilt",
    "truncated", "a name carries", "requires a neutral", "register", "definition",
    "pos", "kind", "senses", "l1",
)


def reason_key(message: str) -> str:
    """A refusal's message → a short bucket for the end line's count."""
    text = message.lower()
    for key in _REASONS:
        if key in text:
            return {"a name carries": "name", "requires a neutral": "four things",
                    "not json": "not JSON", "no entries list": "not JSON"}.get(key, key)
    return "other"


@dataclass
class _Outcome:
    batch: list[str]
    defined: Any = None
    refused_all: str | None = None
    deferred: bool = False
    stop: str | None = None
    usage: dict = field(default_factory=dict)


def _attempt(
    batch: list[str],
    *,
    languages: tuple[str, ...],
    sleep: Callable[[float], None],
    stopping: threading.Event,
) -> _Outcome:
    """One batch: call, and on the provider's weather WAIT and call again (C3)."""
    from core.llm import LLMError, LLMSpendLimit
    from core.video import explain

    outcome = _Outcome(batch)
    for attempt in range(len(TRANSIENT_WAITS_S) + 1):
        if stopping.is_set():
            outcome.deferred = True
            return outcome
        try:
            outcome.defined = explain.define_words(
                batch, l1=languages, usage_out=outcome.usage
            )
            return outcome
        except LLMSpendLimit:
            outcome.deferred = True
            outcome.stop = "spend limit"
            return outcome
        except LLMError as exc:
            if not explain.is_transient(exc):
                outcome.refused_all = str(exc)
                return outcome
            if attempt == len(TRANSIENT_WAITS_S):
                outcome.deferred = True
                outcome.stop = "provider unavailable"
                return outcome
            wait_s = TRANSIENT_WAITS_S[attempt]
            logger.warning(
                "provider busy (%s); waiting %.0fs before asking again for %s word(s)",
                type(exc.__cause__).__name__ if exc.__cause__ else "error", wait_s, len(batch),
            )
            sleep(wait_s)
    return outcome  # pragma: no cover - the loop always returns


def run_backfill(
    *,
    words: list[str],
    apply: bool,
    concurrency: int,
    source: str,
    model: str,
    languages: tuple[str, ...],
    sleep: Callable[[float], None] = time.sleep,
    pilot_out: Path | None = None,
    conn_factory: Callable[[], Any] | None = None,
) -> RunReport:
    """Buy these words' entries, `DICT_BATCH` a call. **A DRY RUN MAKES NO CALL.**

    With `pilot_out`, the entries are written to that JSONL file and **nothing
    is written to the database** — the Q1 pilot, read by a person before the
    model is chosen. Otherwise each batch is committed as it lands, so a run
    that is stopped keeps what it bought and a re-run buys the rest.

    `concurrency` calls are in flight at once; the database is written from
    this thread only. **The provider's weather waits (C3); the spend limit
    stops the run** — the one refusal no wait fixes.
    """
    from core.db import connection
    from core.video.explain import DICT_BATCH

    report = RunReport(planned=len(words))
    if not apply:
        logger.info("DRY RUN — no model call was made and nothing was written")
        return report

    batches = [words[i : i + DICT_BATCH] for i in range(0, len(words), DICT_BATCH)]
    stopping = threading.Event()
    pilot_rows: dict[str, dict] = {}
    open_conn = conn_factory or connection
    done = 0
    with open_conn() as conn, ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        queue = list(batches)
        running: set = set()

        def submit_next() -> None:
            if queue and not stopping.is_set():
                batch = queue.pop(0)
                running.add(pool.submit(_attempt, batch, languages=languages,
                                        sleep=sleep, stopping=stopping))

        for _ in range(max(1, concurrency)):
            submit_next()
        while running:
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                running.discard(future)
                outcome: _Outcome = future.result()
                done += 1
                report.calls += int(outcome.usage.get("calls", 0))
                report.input_tokens += int(outcome.usage.get("input_tokens", 0))
                report.output_tokens += int(outcome.usage.get("output_tokens", 0))
                wrote = 0
                if outcome.stop:
                    report.stopped = report.stopped or outcome.stop
                    stopping.set()
                if outcome.deferred:
                    report.deferred += len(outcome.batch)
                elif outcome.refused_all is not None:
                    report.refused[reason_key(outcome.refused_all)] += len(outcome.batch)
                    logger.warning("batch refused (%s word(s)): %s",
                                   len(outcome.batch), outcome.refused_all[:200])
                else:
                    for word, why in outcome.defined.refused.items():
                        report.refused[reason_key(why)] += 1
                        logger.info("refused %r: %s", word, why)
                        if pilot_out is not None:
                            pilot_rows[word] = {"word": word, "refused": why}
                    for word, entry in outcome.defined.entries.items():
                        if pilot_out is not None:
                            pilot_rows[word] = _pilot_row(entry, model)
                            continue
                        if insert_entry(conn, entry, model=model, source=source):
                            wrote += 1
                        else:
                            report.already_held += 1
                    if pilot_out is None:
                        conn.commit()
                report.written += wrote
                logger.info(
                    "batch %s/%s words=%s wrote=%s refused_so_far=%s deferred_so_far=%s "
                    "output_tokens_so_far=%s",
                    done, len(batches), len(outcome.batch), wrote,
                    sum(report.refused.values()), report.deferred, report.output_tokens,
                )
                submit_next()
        # Batches never started because the run stopped are deferred too.
        for batch in queue:
            report.deferred += len(batch)

    if pilot_out is not None:
        pilot_out.parent.mkdir(parents=True, exist_ok=True)
        with pilot_out.open("w", encoding="utf-8") as out:
            for word in words:
                if word in pilot_rows:
                    out.write(json.dumps(pilot_rows[word], ensure_ascii=False) + "\n")
        for word in words:
            row = pilot_rows.get(word)
            if row and "senses" in row:
                first = row["senses"][0] if row["senses"] else {}
                l1 = first.get("l1", {}) if first else {}
                logger.info("pilot %-14s %-9s %s | fa=%s | lt=%s", word, row["register"] or "name",
                            first.get("definition", "(a name)"), l1.get("fa", "-"), l1.get("lt", "-"))
        logger.info("pilot report written to %s — nothing was written to the database", pilot_out)

    logger.info(
        "done planned=%s written=%s already_held=%s refused=%s%s deferred=%s calls=%s "
        "input_tokens=%s output_tokens=%s%s",
        report.planned, report.written, report.already_held, sum(report.refused.values()),
        (" (" + ", ".join(f"{k}={v}" for k, v in sorted(report.refused.items())) + ")")
        if report.refused else "",
        report.deferred, report.calls, report.input_tokens, report.output_tokens,
        f" stopped={report.stopped!r}" if report.stopped else "",
    )
    return report


def _pilot_row(entry: Any, model: str) -> dict:
    return {
        "word": entry.word,
        "kind": entry.kind,
        "register": entry.register,
        "neutral_equivalent": entry.neutral_equivalent,
        "who_says_this": entry.who_says_this,
        "senses": [s.wire() for s in entry.senses],
        "model": model,
    }

