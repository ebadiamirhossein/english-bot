"""Every query against `items` and `item_attempts`. The only place SQL lives.

`core.items.*` is pure — it turns a draft into a verdict without touching a
database. This module is the other half: it resolves a target lemma to a
`lexeme_id`, writes a validated item, and records what a learner did. The split
is what lets the whole validator be tested without Postgres and what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted
(CLAUDE.md §2; known issue #59 stays the only exemption).

**`insert_item` refuses to write an item whose report is not `ok`.** That is the
second of three layers behind "no item reaches a learner without a validation
record" — migration 012's `validation JSONB NOT NULL` plus its
`? 'deterministic'` CHECK is the first, and a parse test asserting exactly one
`INSERT INTO items` in the tree is the third. The third is the one that survives
a refactor.

`user_id` means `users.id` throughout (011, #92). There is no `telegram_user_id`
anywhere in this file, and `tests/test_identity_boundary.py` walks every `.py`
under `packages/core`, so it covers this module from the commit that adds it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from psycopg.rows import tuple_row

from core import speech
from core.db import connection, cursor
from core.items import RESPONSE_MODE, TYPES_WITH_AUDIO, VALIDATOR_VERSION
from core.items.checks import sentence_of
from core.items.gates import ValidationReport
from core.items.projection import visible_projection
from core.items.response import Submission
from core.items.response import chosen_option as chosen_option_of
from core.items.response import grade as grade_submission
from core.items.response import response_payload as response_payload_of
from core.items.response import submitted_text
from core.items.schema import BaseItem, content_hash, parse, payload_of
from core.services.lexicon import ensure_lexeme

logger = logging.getLogger(__name__)


class ItemWriteError(Exception):
    """Raised rather than writing an item that has not earned its place."""


class ItemAudioUnavailable(Exception):
    """The speech provider failed. **A service-level failure, not a provider one.**

    `core.speech.SpeechError` is converted here rather than propagated so that
    `apps/api` never has to name a provider concept — importing `core.speech`
    into a route to catch its exception would be the same import the boundary
    test refuses, satisfied on a technicality. The service owns its own failure
    vocabulary; the route maps this to 503.
    """


@dataclass(frozen=True, slots=True)
class StoredItem:
    """An `items` row, as much of it as a caller needs.

    **This never leaves `packages/core`.** It carries the answer, the accepted
    variants and — through `payload` — the transcript, the rubric, the wrong
    index and the correction. `apps/api` receives `ItemPresentation` instead,
    which carries none of them; see `presentations_for`.
    """

    id: int
    user_id: int
    item_type: str
    track: str
    register: str
    prompt_text: str
    answer: str | None
    accepted_variants: tuple[str, ...]
    cue_type: str | None
    payload: dict
    error_type: str | None = None
    unit_number: int | None = None
    #: `error_types.murphy_units` for `error_type`, resolved in the same read.
    #: The only Murphy reference available before W8's `syllabus_units` (#104).
    murphy_units: str | None = None

    @property
    def response_mode(self) -> str:
        return RESPONSE_MODE[self.item_type]

    def as_item(self) -> BaseItem:
        """Rehydrate the typed model from the promoted columns plus `payload`.

        `payload_of` derives the payload by *subtracting* the promoted columns,
        so putting them back is exactly this union — no key list is maintained
        anywhere, which is what stops a field silently stopping being read.

        `lexeme` is deliberately not restored. It is stored as `lexeme_id`, it
        is in `projection.NEVER_VISIBLE`, and nothing downstream of a stored
        item grades or renders on it; re-resolving the lemma would be a join
        bought for a field no caller reads.
        """
        return parse(
            {
                "item_type": self.item_type,
                "track": self.track,
                "register": self.register,
                "prompt_text": self.prompt_text,
                "answer": self.answer,
                "accepted_variants": list(self.accepted_variants),
                "cue_type": self.cue_type,
                "error_type": self.error_type,
                "unit_number": self.unit_number,
                **self.payload,
            }
        )


# Every cursor below pins `tuple_row`: the shared pool is opened with
# `dict_row`, a test connection usually is not, and a service that reads by
# position must not depend on which one it was handed.


def insert_item(
    user_id: int,
    item: BaseItem,
    report: ValidationReport,
    *,
    model: str,
    source_chunk_id: int | None = None,
    error_id: int | None = None,
) -> int | None:
    """Write a validated item. Returns its id, or None if it already existed.

    ``None`` rather than an exception on a duplicate: `UNIQUE (user_id,
    content_hash)` firing means the generator produced something this learner
    already has, which is a normal outcome of asking for fresh items, not a
    fault. The caller counts it and moves on.
    """
    if not report.ok:
        raise ItemWriteError(
            f"refusing to write an item with verdict {report.verdict!r}: "
            f"{report.as_json()}"
        )

    # One connection for both writes, so a grown lexeme and the item that needs
    # it commit together. `ensure_lexeme` takes a connection because W4 made
    # growth a deliberate act with a named caller; passing the same one keeps a
    # failed INSERT from leaving an orphan lemma behind.
    with connection() as conn:
        # A target word outside the seed list is created rather than dropped —
        # W4's growable-`lexemes` rule. `ensure_lexeme` writes `origin='grown'`
        # with a NULL `freq_rank`, and 010's convention holds: NULL rank means
        # "rarer than the seed tail", never "missing", so a grown target is
        # never assumed known by the frequency floor.
        lexeme_id = ensure_lexeme(conn, item.lexeme) if item.lexeme else None
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute(
            """
            INSERT INTO items (
                user_id, item_type, track, register, prompt_text, answer,
                accepted_variants, cue_type, repair_count, lexeme_id,
                error_type, error_id, unit_number, source_chunk_id,
                payload, validation, validator_version, model, content_hash
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (user_id, content_hash) DO NOTHING
            RETURNING id
            """,
            (
                user_id,
                item.item_type,
                item.track,
                item.register_tag,
                item.prompt_text,
                item.answer,
                list(item.accepted_variants),
                item.cue_type,
                report.repair_count,
                lexeme_id,
                item.error_type,
                error_id,
                item.unit_number,
                source_chunk_id,
                json.dumps(payload_of(item), ensure_ascii=False),
                json.dumps(report.as_json(), ensure_ascii=False),
                VALIDATOR_VERSION,
                model,
                content_hash(item),
            ),
        )
        row = cur.fetchone()
        conn.commit()

    if row is None:
        # PRD §10: logs carry ids and route names, never message bodies. The
        # hash is not a body — it is the reason the write was a no-op.
        logger.info(
            "item duplicate user_id=%s type=%s hash=%s",
            user_id,
            item.item_type,
            content_hash(item)[:12],
        )
        return None

    logger.info(
        "item written user_id=%s id=%s type=%s repairs=%s",
        user_id,
        row[0],
        item.item_type,
        report.repair_count,
    )
    return int(row[0])


def record_attempt(
    user_id: int,
    item_id: int,
    *,
    correct: bool,
    graded_by: str,
    session_id: int | None = None,
    response_text: str | None = None,
    response_payload: dict | None = None,
    chosen_option: str | None = None,
    grade: int | None = None,
    latency_ms: int | None = None,
    cue_shown: str | None = None,
    hint_used: bool = False,
    attempt_no: int = 1,
    model_feedback: dict | None = None,
    audio_seconds: float | None = None,
) -> int:
    """Record one attempt. Every column that cannot be reconstructed later.

    `latency_ms`, `cue_shown`, `chosen_option`, `grade`, `graded_by` and
    `audio_seconds` have no reader in W5. They ship anyway: adding a column at
    013 or 015 is one line, but the months of history in between would be blank
    exactly where FSRS and the generator-quality signal need it most.

    **The audio itself is never passed here and never stored** (CLAUDE.md §5) —
    only its duration.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            INSERT INTO item_attempts (
                item_id, user_id, session_id, response_text, response_payload,
                chosen_option, correct, grade, latency_ms, cue_shown,
                hint_used, attempt_no, graded_by, model_feedback, audio_seconds
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                item_id,
                user_id,
                session_id,
                response_text,
                json.dumps(response_payload or {}, ensure_ascii=False),
                chosen_option,
                correct,
                grade,
                latency_ms,
                cue_shown,
                hint_used,
                attempt_no,
                graded_by,
                json.dumps(model_feedback or {}, ensure_ascii=False),
                audio_seconds,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _to_stored(row: tuple) -> StoredItem:
    return StoredItem(
        id=int(row[0]),
        user_id=int(row[1]),
        item_type=row[2],
        track=row[3],
        register=row[4],
        prompt_text=row[5],
        answer=row[6],
        accepted_variants=tuple(row[7] or ()),
        cue_type=row[8],
        payload=row[9] or {},
        error_type=row[10],
        unit_number=row[11],
        murphy_units=row[12],
    )


# LEFT JOIN, never INNER: `items_declares_a_target` permits an item to declare
# only `lexeme_id` or `unit_number`, so `error_type` is legitimately NULL and an
# inner join would silently drop most of the bank (#104).
_SELECT = """
    SELECT items.id, items.user_id, items.item_type, items.track,
           items.register, items.prompt_text, items.answer,
           items.accepted_variants, items.cue_type, items.payload,
           items.error_type, items.unit_number, et.murphy_units
      FROM items
      LEFT JOIN error_types et ON et.code = items.error_type
"""

#: **A row validated by an older gate is not servable, and this is the filter
#: that says so** (W10, `docs/TASKS-v3-web.md`).
#:
#: `VALIDATOR_VERSION` is 3 today and has moved twice for a reason each time:
#: 1 -> 2 at W5a, when the uniqueness gate stopped asking *"what is your
#: answer?"* — a question that proves an item is RECOVERABLE and can never prove
#: it is UNIQUELY ACCEPTABLE — and 2 -> 3 at W5c, when the naturalness judge
#: started seeing prose instead of a gapped stem. **A version-1 row was passed by
#: a gate that could not detect multi-acceptability**, which is the exact defect
#: that started the v3 rebuild, so serving one inside a session would put an
#: ungradable item in front of a learner.
#:
#: Applied to the two reads that feed a learner, and NOT to `insert_item`, which
#: always writes the current version. `items` is empty on production (#109 closed
#: with `count(*)` at 0 after the W6a purge), so this filter costs nothing today
#: and is here before the bank exists rather than after it does.
_CURRENT_VALIDATOR = " AND items.validator_version = %s"


def list_bank(
    user_id: int, *, item_type: str | None = None, limit: int = 50
) -> list[StoredItem]:
    """This learner's validated stock. What W10 draws from without generating.

    PRD §4.3: "a validated item bank grows over time". Nothing here filters on a
    status column, because rejected items are never written — see migration
    012's note on why a `status` column was refused.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        if item_type is None:
            cur.execute(
                _SELECT
                + " WHERE items.user_id = %s"
                + _CURRENT_VALIDATOR
                + " ORDER BY items.created_at DESC LIMIT %s",
                (user_id, VALIDATOR_VERSION, limit),
            )
        else:
            cur.execute(
                _SELECT
                + " WHERE items.user_id = %s AND items.item_type = %s"
                + _CURRENT_VALIDATOR
                + " ORDER BY items.created_at DESC LIMIT %s",
                (user_id, item_type, VALIDATOR_VERSION, limit),
            )
        return [_to_stored(row) for row in cur.fetchall()]


def bank_for_session(user_id: int, *, unit_number: int, limit: int = 20) -> list[StoredItem]:
    """Unit-scoped stock, least recently attempted first.

    W10 owns the session mix; this is only the read it will need. Ordering by
    last attempt rather than by creation is what stops the same freshly-written
    items being served every night while older validated stock is never seen.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT
            + " WHERE items.user_id = %s AND items.unit_number = %s"
            + _CURRENT_VALIDATOR
            + """
              ORDER BY (
                  SELECT MAX(a.attempted_at) FROM item_attempts a
                   WHERE a.item_id = items.id
              ) ASC NULLS FIRST, items.created_at ASC
              LIMIT %s
            """,
            (user_id, unit_number, VALIDATOR_VERSION, limit),
        )
        return [_to_stored(row) for row in cur.fetchall()]


def attempt_counts(user_id: int) -> dict[str, int]:
    """Attempts and correct attempts, for W19's progress line."""
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE correct)
              FROM item_attempts WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    total, right = (row or (0, 0))
    return {"attempts": int(total or 0), "correct": int(right or 0)}


# ── what a learner is allowed to receive ─────────────────────────────────────
#
# **CROSS-SLICE CONTRACT — W10 calls `presentations_for` and writes no
# serialiser of its own.** `GET /session/today` hydrates five blocks of items;
# if it builds its own envelope the blind-solver probe stops describing what a
# learner actually sees, every downstream number stays green, and the drift is
# invisible because both halves keep working on their own terms. The plural
# function below is the primary one and exists for that call. This is enforced,
# not requested: `tests/test_core_boundary.py::test_exactly_one_module_projects_
# an_item` names the three modules permitted to call `visible_projection`, and
# `::test_the_api_never_reaches_the_hidden_half_of_an_item` keeps
# `core.items.projection`, `.schema`, `.grading`, `core.llm` and `core.speech`
# out of `apps/api` entirely.


@dataclass(frozen=True, slots=True)
class ItemPresentation:
    """One item as the learner receives it. **The hidden half is not here.**

    No `answer`, no `accepted_variants`, no `transcript`, no `rubric`, no
    `wrong_index`, no `correction`, no `explanation`. That is a capability
    rather than a rule: a route handed one of these cannot leak the answer
    because it was never given it, and adding "just one more field" for a
    renderer means changing `visible_projection` — where the probe sees it too.

    `response_mode` travels on the wire so `apps/web` holds no copy of
    `RESPONSE_MODE`. A mirrored table is a table that drifts.
    """

    id: int
    response_mode: str
    projection: dict


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    """The verdict, and the teaching half that is only shown after grading.

    `canonical` is returned **after** the answer is graded, which is not a
    projection leak — it is the point of the feedback. `explanation` is almost
    always ``None`` today: `core/prompts/item_generate.txt` never asks the
    generator for one (#103, W10). `murphy_units` is present whenever the item
    declares an `error_type` (#104, W8).
    """

    attempt_id: int
    correct: bool
    graded_by: str
    canonical: str | None
    explanation: str | None
    murphy_units: str | None
    #: `match_pairs`' correct bijection, and **only** for that type (#118).
    #:
    #: Its answer is a mapping rather than a string, so `canonical` is NULL for
    #: it by migration 012's `items_answer_present_iff_type_has_one` CHECK. W6a
    #: could only stop the result box promising an answer it could not produce;
    #: nothing on the client had the pairing, so a wrong answer taught nothing.
    #:
    #: **The standing is `canonical`'s exactly**: returned after the attempt is
    #: recorded, from the stored item, by the answer route. It is not a
    #: projection leak — `visible_projection` is untouched and still serves the
    #: two columns independently sorted, so the pairing is destroyed in what the
    #: learner is shown *before* answering.
    #:
    #: `speak_answer` has the same NULL canonical and needs nothing here: an
    #: open production task has no single correct answer to reveal.
    pairs: tuple[tuple[str, str], ...] | None = None


def _present(stored: StoredItem) -> ItemPresentation:
    return ItemPresentation(
        id=stored.id,
        response_mode=stored.response_mode,
        projection=visible_projection(stored.as_item()),
    )


def _fetch(user_id: int, item_id: int) -> StoredItem | None:
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT + " WHERE items.id = %s AND items.user_id = %s",
            (item_id, user_id),
        )
        row = cur.fetchone()
    return _to_stored(row) if row else None


def presentation_for(user_id: int, item_id: int) -> ItemPresentation | None:
    """One item, learner-visible half only. ``None`` when it is not theirs.

    Not-yours and not-found deliberately collapse into one answer: telling a
    caller that an id exists but belongs to someone else is a fact about another
    learner.
    """
    stored = _fetch(user_id, item_id)
    return _present(stored) if stored else None


def presentations_for(
    user_id: int, *, item_type: str | None = None, limit: int = 50
) -> list[ItemPresentation]:
    """This learner's bank, learner-visible halves only. **W10's entry point.**

    Reads through `list_bank`, so the ordering rule and the absence of a status
    filter (migration 012 refused a `status` column, with reasons) are stated in
    exactly one place.
    """
    return [_present(row) for row in list_bank(user_id, item_type=item_type, limit=limit)]


#: A latency the browser reports outside this range is stored as NULL rather
#: than as a lie. Ten minutes on one item is a phone that was put down, not a
#: retrieval time, and `item_attempts.latency_ms` is what W7's FSRS reads
#: (#108). The lower bound is migration 012's own CHECK.
MAX_LATENCY_MS = 600_000


def _clean_latency(latency_ms: int | None) -> int | None:
    if latency_ms is None or not 0 <= latency_ms <= MAX_LATENCY_MS:
        return None
    return int(latency_ms)


def answer_item(
    user_id: int,
    item_id: int,
    *,
    submission: Submission,
    latency_ms: int | None = None,
    session_id: int | None = None,
) -> AnswerOutcome | None:
    """Grade one response and record it. ``None`` when the item is not theirs.

    **Nothing here writes to `errors`**, and that is a decision rather than an
    omission. `errors.source` was widened at 012 to include `item`, and after W6
    that value still has no writer. A tapped wrong option is a *selection*, not
    self-produced English; a spoken response is not captured at all; and a typed
    miss is not necessarily a grammar error — a missed `dictation` is a
    listening failure, a missed `listening_gap` a hearing failure, and an
    `l1_to_l2_production` canonical is trusted rather than verified (#102), so
    `correct_form` could itself be wrong. **A wrong journal row is permanent
    damage; a missing one is recoverable.** The evidence lives in
    `item_attempts` instead — `response_text` verbatim, `chosen_option`,
    `latency_ms`, `cue_shown` — which is what W7 and W11 read. Revisit at W11
    with a real error-classification step (#107).

    This also reverses `docs/ARCHITECTURE-v3-web.md` §6, which listed a journal
    write on this route; §6 is corrected in the same commit.

    `cue_shown` comes from the row, never from the client: `visible_projection`
    deliberately hides the cue's *category* (it is a hint about what kind of
    answer is wanted), so a client could not report it correctly even if asked.
    """
    stored = _fetch(user_id, item_id)
    if stored is None:
        return None

    item = stored.as_item()
    correct, graded_by = grade_submission(item, submission)

    attempt_id = record_attempt(
        user_id,
        item_id,
        correct=correct,
        graded_by=graded_by,
        session_id=session_id,
        # VERBATIM and unnormalised — "what did they actually type" cannot be
        # recovered from "did it match", and W7's leech rewrite needs it.
        response_text=submitted_text(item, submission),
        response_payload=response_payload_of(item, submission),
        chosen_option=chosen_option_of(item, submission),
        latency_ms=_clean_latency(latency_ms),
        cue_shown=stored.cue_type,
        # `grade` stays NULL: FSRS Again/Hard/Good/Easy is W7's reviewer and W6
        # has no 4-button UI. Synthesising one from a boolean would seed FSRS
        # with a made-up number, which is worse than blank.
        #
        # `audio_seconds` stays NULL: no audio is captured in W6 at all. The
        # column measures the LEARNER's speech; TTS playback duration is a
        # different quantity and writing it here would make W19's
        # effort-weighted XP incomparable.
        #
        # `hint_used` stays FALSE: there is no "show me a cue" affordance, and
        # adding one needs a route that reveals `definition` / `l1_gloss` — a
        # second learner-visible serialiser by another name (#105).
        #
        # `attempt_no` stays 1. Migration 012 left the column's meaning open
        # (`:297` has no UNIQUE, `:323` explains why) and W6 fixes it: it counts
        # attempts WITHIN ONE ENCOUNTER, not encounters over time, which are
        # counted by the rows themselves. W6 allows no retry, because feedback
        # reveals the canonical answer and a second attempt then measures
        # reading rather than retrieval.
    )

    return AnswerOutcome(
        attempt_id=attempt_id,
        correct=correct,
        graded_by=graded_by,
        canonical=stored.answer,
        explanation=stored.payload.get("explanation"),
        murphy_units=stored.murphy_units,
        pairs=_pairs_after_grading(item),
    )


def _pairs_after_grading(item) -> tuple[tuple[str, str], ...] | None:
    """The correct bijection, for `match_pairs` and nothing else (#118).

    Keyed on the item's own type rather than on "does the payload have pairs",
    so a twelfth type that happened to carry a `pairs` key could not start
    leaking one by accident.
    """
    if item.item_type != "match_pairs":
        return None
    return tuple((str(left), str(right)) for left, right in item.pairs)


def item_audio(user_id: int, item_id: int) -> bytes | None:
    """The item's sentence as speech. ``None`` when it is not theirs.

    **Synthesis is here and not in the route, and that is load-bearing.** For
    `listening_gap` the text being spoken *is* the answer, and for `dictation`
    it is the whole exercise. A route that called `speech.synthesize` itself
    would have to hold that string in `apps/api`, where one exception handler
    echoing context, one debug log line or one 500 body puts it on the wire —
    and the route would be calling a provider wrapper rather than one service
    function. The caller here receives bytes and never text.

    Per request, with no cache. At two learners that is correct and cheapest;
    before real tenancy it becomes a cache keyed on `items.content_hash`, which
    exists from day one, so that is a table and a lookup rather than a re-key
    (#106). Raises `ItemAudioUnavailable` on provider failure — the route
    answers 503.
    """
    stored = _fetch(user_id, item_id)
    if stored is None:
        return None
    if stored.item_type not in TYPES_WITH_AUDIO:
        return None
    text = sentence_of(stored.as_item())
    if not text.strip():
        return None
    logger.info(
        "item audio user_id=%s id=%s type=%s", user_id, item_id, stored.item_type
    )
    try:
        return speech.synthesize(text)
    except speech.SpeechError as exc:
        # PRD §10: the log carries ids and a route name, never the text that was
        # being spoken — for `listening_gap` that text is the answer.
        logger.warning(
            "item audio synthesis failed user_id=%s id=%s", user_id, item_id
        )
        raise ItemAudioUnavailable(str(exc)) from None


def delete_items_by_hash(user_id: int, hashes: Sequence[str]) -> int:
    """Delete this learner's items with these content hashes. Returns the count.

    **Exists for `core.items.seed_fixtures --purge` and for nothing else.**
    Fixture-seeded rows are indistinguishable from real ones by design —
    migration 012 refused a `status` column, with reasons — so the only honest
    way to remove exactly what a seeding run inserted is to name the hashes it
    computed. **Matching on a date range would sweep real rows**, which is why
    that is not what this does.

    `item_attempts` has `ON DELETE CASCADE` through its composite foreign key,
    so the attempts made against a purged fixture go with it. That is correct:
    an attempt on a test fixture is not evidence about a learner.
    """
    if not hashes:
        return 0
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "DELETE FROM items WHERE user_id = %s AND content_hash = ANY(%s) "
            "RETURNING id",
            (user_id, list(hashes)),
        )
        deleted = cur.fetchall()
    logger.info("items purged user_id=%s count=%s", user_id, len(deleted))
    return len(deleted)
