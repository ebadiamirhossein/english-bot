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

#: **Which POPULATION a row belongs to, read from the declared tag.** W11.
#:
#: `coalesce(..., 'focus')` is the whole backfill and there is nothing to back
#: fill: the fourteen live rows carry no `cohort` key because they were written
#: by the 8-slot block-3 run, so *absent means focus* is what they ARE rather
#: than a default chosen for convenience.
_COHORT = "coalesce(items.payload ->> 'cohort', 'focus')"

#: An item nobody has answered yet. The reserve is computed over exactly these.
_UNATTEMPTED = """
    AND NOT EXISTS (
        SELECT 1 FROM item_attempts a
         WHERE a.item_id = items.id AND a.user_id = items.user_id
    )
"""



#: **THE CHECKPOINT RESERVE'S PREDICATE, IN ONE PLACE, READ BY BOTH CONSUMERS.**
#:
#: `checkpoint_items` SELECTS from it and `checkpoint_held` COUNTS it, and they
#: must never disagree about what "the learner already holds" means: a filter
#: added to one and not the other makes `--fill` plan against a set the selector
#: would refuse, and the symptom is a checkpoint that never becomes ready while
#: the generator insists the bank is full.
#:
#: **Composing the two readers from ONE constant is the guarantee** -- sharing
#: `_COHORT` and `_UNATTEMPTED` separately was the earlier shape and it is the
#: weaker one, because nothing stops a third clause being added to one caller.
#: `test_checkpoint_held_cannot_diverge_from_checkpoint_items` is demonstrated
#: red by giving `checkpoint_held` its own copy of this text.
_CHECKPOINT_STOCK = (
    " WHERE items.user_id = %s AND items.unit_number = %s"
    + _CURRENT_VALIDATOR
    + " AND " + _COHORT + " = 'checkpoint'"
    + _UNATTEMPTED
)


#: **THE FOCUS BANK'S PREDICATE, W10d COMMIT 2 — and `_COHORT` is doing the
#: single most expensive thing in this file.**
#:
#: The four live focus rows carry **no `cohort` key at all**; Q1 confirmed it on
#: the host on 2026-08-31, where `payload ->> 'cohort'` was blank on all 14 focus
#: rows and only the 24 checkpoint rows carried an explicit key. **A counter
#: keyed on `payload ->> 'cohort' = 'focus'` would see 0 instead of 4, plan the
#: 52-item shortfall as a 56-item one, and buy those four items twice.** That is
#: a paid-for duplicate run, not a tidiness question, and it is why this composes
#: from `_COHORT` rather than writing its own comparison.
#:
#: **NO `_UNATTEMPTED`, AND THE ASYMMETRY WITH `_CHECKPOINT_STOCK` IS THE POINT.**
#: A checkpoint sitting needs items nobody has answered, so the reserve is
#: unattempted-only. **The focus bank is a seven-day cycle and an item a learner
#: saw on Monday is still in it** — `bank_for_session` orders by least recently
#: attempted rather than excluding what was attempted. Counting only unattempted
#: rows would report the bank as empty the day after a session and buy a second
#: 56 every week.
_FOCUS_STOCK = (
    " WHERE items.user_id = %s AND items.unit_number = %s"
    + _CURRENT_VALIDATOR
    + " AND " + _COHORT + " = 'focus'"
)

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
    """Unit-scoped stock, least recently attempted first. **Block 3's read.**

    W10 owns the session mix; this is only the read it will need. Ordering by
    last attempt rather than by creation is what stops the same freshly-written
    items being served every night while older validated stock is never seen.

    **W11: AN UNATTEMPTED CHECKPOINT ITEM IS WITHHELD, AND THE WITHHOLDING IS
    SUSPENDED WHEN IT WOULD LEAVE BLOCK 3 EMPTY.**

    The problem it solves is this function's own ordering: `NULLS FIRST` means
    unattempted items come first, so a checkpoint cohort generated on Friday is
    *exactly* what block 3 reaches for, and one session eats eight of the twelve.

    **The reserve is read from the declared `cohort` tag, not inferred from
    recency.** A recency proxy -- withhold the newest twelve -- holds only while
    the checkpoint run is the unit's most recent generation, and a unit needs
    8 + 12 = 20 items, so there are TWO runs. A block-3 top-up after the
    checkpoint run makes the newest twelve *eight top-up items plus four
    checkpoint ones*, and the reserve then protects the wrong rows SILENTLY.

    **THE PRECEDENCE RULE: daily practice beats a weekly checkpoint.** If the
    unit holds nothing but the reserve, this serves the reserve and the
    checkpoint refuses that week -- loudly, on a not-ready surface. A learner
    with an empty block 3 has lost their day; a learner with no checkpoint has
    lost a Saturday, and only one of those is recoverable.

    **The reserve releases itself three ways** and nothing has to remember to do
    it: the sitting gives the twelve `item_attempts` rows so they leave the
    unattempted set and become ordinary practice stock; a pass advances
    `current_unit` so this unit's reserve stops being consulted; and the
    suspension bounds the case where a cohort is generated and never sat.
    """
    reserved = " AND NOT (" + _COHORT + " = 'checkpoint'" + _UNATTEMPTED + ")"
    order = """
              ORDER BY (
                  SELECT MAX(a.attempted_at) FROM item_attempts a
                   WHERE a.item_id = items.id
              ) ASC NULLS FIRST, items.created_at ASC
              LIMIT %s
            """
    # **W17: a drill is never unit practice.** A drill has no `unit_number`, so
    # the unit predicate already excludes it; the cohort is named as well so that
    # a drill written WITH a unit could never leak into block 3's eight. It is in
    # `where` and not in `reserved`, because the suspension below drops
    # `reserved` -- `test_a_drill_is_never_unit_practice` found exactly that.
    where = (
        " WHERE items.user_id = %s AND items.unit_number = %s" + _CURRENT_VALIDATOR
        + " AND " + _COHORT + " <> 'drill'"
    )
    args = (user_id, unit_number, VALIDATOR_VERSION, limit)
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(_SELECT + where + reserved + order, args)
        rows = cur.fetchall()
        if not rows:
            # The suspension. Withholding would have left block 3 empty, so the
            # reserve yields -- and `checkpoint_items` will find these attempted
            # and refuse, which is the loud failure this trade prefers.
            cur.execute(_SELECT + where + order, args)
            rows = cur.fetchall()
        return [_to_stored(row) for row in rows]


def checkpoint_items(
    user_id: int, *, unit_number: int, quotas: dict[str, int]
) -> list[ItemPresentation]:
    """The twelve for one sitting, or **nothing**. Never a short checkpoint.

    `quotas` comes from `core.syllabus.checkpoint.quota_map` -- **the same
    producer `core.items.generate.checkpoint_slot_plan` called to build the
    cohort**, so the generator and the selector cannot disagree about what a
    sitting is made of. That is not tidiness:

        An earlier draft had this fill the BLUEPRINT's `per_target` while the
        fail path re-weighted a RETAKE toward the missed targets. Both cannot
        hold. A retake cohort in 6/3/2/1 cannot fill a 4/3/3/2 demand, so this
        would refuse and **the retake would never open** -- and the retake is
        half of what W11 promises.

    **The 12 and the 80% do not move** (CLAUDE.md SS3 rule 7). What differs
    between a first sitting and a retake is which targets the twelve are spread
    across.

    **A cohort that cannot fill its own plan is refused WHOLE.** A short return
    would be a checkpoint measuring something other than what it claims, and a
    stale cohort partially served would be last week's sitting wearing this
    week's name. The number short is the generator's to report, never padded
    here.

    Only `cohort = 'checkpoint'` rows, and only ones this learner has never
    attempted -- so a sat checkpoint is never re-served, and the reserve
    `bank_for_session` withholds is exactly the set this selects from.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT
            + _CHECKPOINT_STOCK
            + " ORDER BY items.created_at ASC, items.id ASC",
            (user_id, unit_number, VALIDATOR_VERSION),
        )
        stock = [_to_stored(row) for row in cur.fetchall()]

    by_target: dict[str, list[StoredItem]] = {}
    for one in stock:
        target = (one.payload or {}).get("grammar_target")
        if target:
            by_target.setdefault(str(target), []).append(one)

    chosen: list[StoredItem] = []
    for target, wanted in quotas.items():
        available = by_target.get(target, [])
        if len(available) < wanted:
            logger.info(
                "checkpoint not ready user_id=%s unit=%s target_short=%s "
                "have=%s want=%s",
                user_id, unit_number, target[:40], len(available), wanted,
            )
            return []
        chosen.extend(available[:wanted])

    # **Projected HERE, not by the caller.** `visible_projection` may be called
    # from exactly three modules
    # (`test_core_boundary::test_exactly_one_module_projects_an_item`), and the
    # bucketing above needs `payload['grammar_target']`, which is in
    # `NEVER_VISIBLE`. So the hidden half is read inside this function and never
    # leaves it -- the same shape `focus_items` has.
    return [_present(one) for one in chosen]


#: **HOW MANY ITEMS BLOCK 3 SERVES IN ONE SESSION.** `docs/PRD-v3-web.md:213`,
#: §4.1 block 3: *"90-second explanation + **8 generated items**"*.
#:
#: **THIS IS THE ONE CONSTANT ENTITLED TO CITE THAT LINE, AND W10d MADE THAT A
#: RULE RATHER THAN A CONVENTION.** `core.items.generate.ITEMS_PER_UNIT` cited
#: it too, and two different quantities pinned to one per-session sentence meant
#: the BANK was sized at one session -- so even at 100% yield a unit reached a
#: one-day cycle and a learner met the same items on day two (#299).
#:
#: Three numbers, not one: this is the SESSION size, `ITEMS_PER_UNIT` is the
#: COHORT size, and `FOCUS_BANK_TARGET` is how big the bank must be.
#: `test_the_bank_target_and_the_session_size_are_different_numbers` holds them
#: apart.
FOCUS_ITEM_COUNT = 8


def focus_items(
    user_id: int, *, unit_number: int, limit: int = FOCUS_ITEM_COUNT
) -> list[ItemPresentation]:
    """Block 3's items, learner-visible halves only. **W10c's entry point.**

    `bank_for_session` + `_present`, and nothing else -- so the unit scoping, the
    `validator_version` filter and the least-recently-attempted ordering are all
    stated in exactly one place, and this function cannot disagree with them.

    **THIS IS A READ AND ONLY A READ.** W10's criterion is that nothing is
    generated while a learner waits, and
    `tests/test_session_route.py::test_nothing_is_generated_while_the_learner_waits`
    holds it structurally: `netguard` is armed session-wide, so a generating read
    would raise rather than quietly pass. The generator is
    `python -m core.items.generate`, it is human-run, and `assign_daily` still
    reaches nothing.

    Fewer than `limit` rows is the ordinary case and not an error. A unit whose
    generation run came up short ships short -- the shortfall is reported by the
    generator, never padded (CLAUDE.md §3 rule 7) -- and a unit nobody has
    generated for yet returns an empty list, which block 3 renders as the honest
    empty state it has had since W10.
    """
    return [
        _present(row)
        for row in bank_for_session(user_id, unit_number=unit_number, limit=limit)
    ]



#: **W17: at most this many of block 3's eight are drills.** Two of eight keeps
#: the week's grammar target the block's main business (PRD §4.1) and gives a
#: weak spot a daily, bounded place. The session does not grow: the unit's share
#: shrinks to make room, so a drill is never an extra task (CLAUDE.md §4).
DRILLS_PER_SESSION = 2

#: **The drill bank per pattern the generator fills to.** One cohort of eight.
DRILL_BANK_TARGET = 8

_DRILL_STOCK = (
    " WHERE items.user_id = %s AND items.error_type = ANY(%s)"
    + _CURRENT_VALIDATOR
    + " AND " + _COHORT + " = 'drill'"
)


def drill_items(
    user_id: int, *, codes: Sequence[str], limit: int = DRILLS_PER_SESSION
) -> list[ItemPresentation]:
    """Up to `limit` drills for this learner's EVIDENCED patterns. **W17's read.**

    `codes` is `core.services.drills.evidenced_patterns`' output and nothing else
    — the caller cannot ask for a pattern the journal does not evidence, because
    this function never reads the journal itself; an empty `codes` returns
    nothing. **A pattern with no evidence is never drilled.**

    **Rotation, not rank (#412).** Candidates are ordered least-recently-attempted
    first — `bank_for_session`'s rule — and the pick is one per pattern before any
    pattern gets a second, so two evidenced patterns share the two slots rather
    than the one with more rows taking both.

    **A READ AND ONLY A READ**: drills are generated days earlier by the human-run
    `python -m core.items.drills` (#196), never while the learner waits.
    """
    if not codes or limit <= 0:
        return []
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT
            + _DRILL_STOCK
            + """
              ORDER BY (
                  SELECT MAX(a.attempted_at) FROM item_attempts a
                   WHERE a.item_id = items.id
              ) ASC NULLS FIRST, items.created_at ASC, items.id ASC
              LIMIT %s
            """,
            (user_id, list(codes), VALIDATOR_VERSION, limit * 10),
        )
        rows = [_to_stored(row) for row in cur.fetchall()]
    picked: list[StoredItem] = []
    used: set[str] = set()
    for row in rows:  # one per pattern first
        if row.error_type not in used:
            picked.append(row)
            used.add(row.error_type)
        if len(picked) >= limit:
            break
    for row in rows:  # then fill from the rest, in the same order
        if len(picked) >= limit:
            break
        if all(row.id != one.id for one in picked):
            picked.append(row)
    return [_present(row) for row in picked]


def drill_sentences(user_id: int, *, error_type: str) -> tuple[str, ...]:
    """The drill generator's avoid-list for one pattern: `prompt [answer]`.

    `core.items.generate._bank_sentences`' shape, over `_DRILL_STOCK`.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT items.prompt_text, items.answer FROM items" + _DRILL_STOCK
            + " ORDER BY items.id",
            (user_id, [error_type], VALIDATOR_VERSION),
        )
        out: list[str] = []
        for text, answer in cur.fetchall():
            text, answer = (text or "").strip(), (answer or "").strip()
            joined = f"{text} [{answer}]" if answer else text
            if joined and joined not in out:
                out.append(joined)
        return tuple(out)


def drills_held(user_id: int, *, error_type: str) -> int:
    """How many servable drills this learner holds for one pattern. **W17.**

    What `python -m core.items.drills` subtracts from `DRILL_BANK_TARGET`, and it
    shares `_DRILL_STOCK` with `drill_items` so the counter cannot count rows the
    read cannot serve (`focus_held`'s rule, #299).
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT count(*)::int FROM items" + _DRILL_STOCK,
            (user_id, [error_type], VALIDATOR_VERSION),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def focus_held(user_id: int, *, unit_number: int) -> int:
    """How many focus items this learner already holds in this unit. **W10d.**

    **What a focus `--fill` subtracts from `FOCUS_BANK_TARGET`**, so a second
    run buys the shortfall rather than re-buying the bank. Unit 1 holds four
    against a target of 56, so it needs 52 — and the difference between reading
    4 and reading 0 here is four items bought twice.

    **An int and not a per-target dict, unlike `checkpoint_held`, because the
    two banks are shaped differently.** A checkpoint is a quota per target — five
    past simple, four past continuous — and a shortfall must be computed per
    target or the sitting cannot be composed. **The focus bank has no quota: it
    is N items for a seven-day cycle**, and `slot_plan` already spreads types
    across the unit's targets. Returning a dict here would invent a demand
    structure the blueprint does not state.

    **It counts what `bank_for_session` can SERVE**, sharing `_FOCUS_STOCK`'s
    validator predicate, because a counter that included rows block 3 cannot
    reach would understate the purchase and leave #299 in place inside its own
    fix. `test_focus_held_cannot_diverge_from_bank_for_session` drives that
    property rather than the constant.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT count(*)::int FROM items" + _FOCUS_STOCK,
            (user_id, unit_number, VALIDATOR_VERSION),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def checkpoint_held(user_id: int, *, unit_number: int) -> dict[str, int]:
    """How many unattempted checkpoint items this learner already holds, per target.

    **What `--fill` subtracts from the blueprint's demand**, so a second
    generation run buys the SHORTFALL instead of re-buying the sitting. Unit 1
    after the first billed run holds 3 past simple, 2 past continuous, 1
    composite and 2 time linkers; against a 5/4/1/2 demand that is four items,
    not twelve.

    **It counts EXACTLY what `checkpoint_items` would select** -- same
    `_CHECKPOINT_STOCK` predicate, not a second copy of it -- because a counter
    that disagreed with the selector would let `--fill` plan against a set the
    selector refuses, and the symptom would be a checkpoint that never becomes
    ready while the generator reports the bank full.

    Rows with no `grammar_target` are not counted. They cannot fill a quota
    either -- `checkpoint_items` groups by that key and skips a row without one --
    so counting them would overstate the bank in exactly the direction that
    starves the fill.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT items.payload ->> 'grammar_target', count(*)::int"
            "  FROM items"
            + _CHECKPOINT_STOCK
            + " GROUP BY 1",
            (user_id, unit_number, VALIDATOR_VERSION),
        )
        return {row[0]: int(row[1]) for row in cur.fetchall() if row[0]}



def checkpoint_held_any_version(user_id: int, *, unit_number: int) -> dict[str, int]:
    """Every unattempted checkpoint row on each target, **validator version
    ignored.** W10d.

    **NOT a replacement for `checkpoint_held` and never subtracted from a
    demand.** That function counts exactly what `checkpoint_items` would SERVE,
    and its docstring's guarantee -- same predicate, not a second copy -- is what
    stops `--fill` planning against a set the selector refuses. **This one counts
    what EXISTS.**

    **The pair is the whole point.** Their difference is rows the code cannot
    serve, and it separates a GENERATION shortfall from a RE-VALIDATION one --
    two problems with completely different fixes, one a billed run and the other
    a re-gate. **On 2026-09-02 they were equal on all four of unit 1's targets**,
    which is an evidenced negative rather than an absent question: the query that
    established it needed both columns.

    Built from the same fragments as `_CHECKPOINT_STOCK` minus
    `_CURRENT_VALIDATOR`, so a change to the cohort predicate or the unattempted
    rule reaches both and cannot drift (#132's family).
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT items.payload ->> 'grammar_target', count(*)::int"
            "  FROM items"
            " WHERE items.user_id = %s AND items.unit_number = %s"
            + " AND " + _COHORT + " = 'checkpoint'"
            + _UNATTEMPTED
            + " GROUP BY 1",
            (user_id, unit_number),
        )
        return {row[0]: int(row[1]) for row in cur.fetchall() if row[0]}


def items_by_id(user_id: int, item_ids: Sequence[int]) -> list[ItemPresentation]:
    """The named items, **in the order asked for**. #269's read.

    A checkpoint sitting is a STORED fact: the twelve chosen for it live on the
    `sessions` row, and this reads them back. That is what lets a sitting survive
    being worked on — `checkpoint_items` filters `_UNATTEMPTED`, so re-selecting
    mid-sitting returns fewer items every time a learner answers one, and after
    the first answer the cohort can no longer fill its own quotas.

    **`_UNATTEMPTED` IS NOT RELAXED AND MUST NOT BE.** It is what stops a sat
    checkpoint being re-served as practice
    (`test_a_sat_checkpoint_becomes_ordinary_practice_stock`); the repair for
    #269 is to stop re-deriving the sitting, not to widen the selector.

    **Ordered in Python and not by the query.** `= ANY(%s)` returns rows in
    whatever order the planner likes, and the sitting's order is a fact about the
    sitting — question 7 must be question 7 on a resume. `validator_version` is
    NOT filtered here: these ids were chosen for this sitting and a mid-sitting
    validator bump must not make question 7 vanish.
    """
    wanted = list(dict.fromkeys(int(one) for one in item_ids))
    if not wanted:
        return []
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT + " WHERE items.user_id = %s AND items.id = ANY(%s)",
            (user_id, wanted),
        )
        found = {row[0]: _to_stored(row) for row in cur.fetchall()}
    return [_present(found[one]) for one in wanted if one in found]



def attempts_in_session(user_id: int, session_id: int) -> int:
    """How many items this learner has answered in one session. #269.

    **The Finish button's condition, moved off the browser.** H4 could not finish
    a sitting because `answered >= items.length` was React state that the lost
    sitting took with it. This is the same log `checkpoints.complete` scores
    from, so the count the learner is shown and the count they are graded on
    cannot disagree.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            "SELECT count(DISTINCT item_id)::int FROM item_attempts"
            " WHERE user_id = %s AND session_id = %s",
            (user_id, session_id),
        )
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


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
