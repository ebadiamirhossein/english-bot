"""W16a — the writing surface: today's task, one correction, the log.

**THE BOT'S CORRECTION PATH IS NOT TOUCHED, AND THAT IS WHY THIS FILE EXISTS.**
`core.services.correction.correct`, `apply_result` and `prompts/correction.txt`
are imported by `apps/bot/handlers/correction.py` and rendered as
`👍 {did_well}` by `apps/bot/texts.py`. Ruling 2 removes `did_well`'s
`"Nice."` fallback for the web; doing it in the shared function would put a bare
👍 into live Telegram replies. So the web gets its own prompt, its own gates and
its own service, and the bot stays byte-identical — `git diff --name-only` is
the proof, not this sentence.

What IS shared, deliberately: the error taxonomy list and the explanation-
language clause (`correction.error_type_list_text`,
`correction.explanation_language_rule`), because two copies of either is how
the single-language rule came to be missing from four prompts (#45).

**WHAT THE LOG IS FOR (migration 027).** One `writing_submissions` row per
completed model call. The ceiling counts today's rows; block 4's `done` is an
`EXISTS` over the session's rows with `is_english`. Nothing counts a clean
entry by its `errors` rows, because a clean entry has none.

**THE SUBMISSION ROW AND THE JOURNAL ROWS ARE TWO TRANSACTIONS, NOT ONE, AND
THE PLAN SAID ONE.** `record_errors` opens and owns its own transaction and is
on the bot path, so it is called as it is rather than widened. The submission
row is written FIRST: the call has already been billed, and a log that
under-reports spend is #321's defect. If the journal write then fails, the
learner has a counted submission and no journal rows — the recoverable
direction (CLAUDE.md §5: *a missing entry is recoverable*).

Nothing here imports FastAPI, Telegram or any HTTP type.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from core import PROMPTS_DIR
from core.config import Settings, load_settings
from core.db import connection
from core.llm import LLMError, chat
from core.services import correction
from core.services.errors import record_errors
from core.services.sessions import complete_open_free_practice, local_today
from core.services.users import User
from core.sessions import DAILY_TASK_TYPE
from core.writing import gates, offers, rules
from core.writing.rules import DayKind

logger = logging.getLogger(__name__)

_PROMPT_PATH = PROMPTS_DIR / "writing_correction.txt"
#: W16b. A second template rather than a branch inside the first: `str.format`
#: has no conditionals, and a paragraph asks for `structure` and `keep`, which the
#: journal must never be asked for.
_PARAGRAPH_PROMPT_PATH = PROMPTS_DIR / "writing_paragraph.txt"

#: `pg_advisory_xact_lock(W16_LOCK_CLASS, user_id)` serialises one learner's
#: `POST /write/keep` calls. 015's partial UNIQUE ignores a NULL `lexeme_id`, so a
#: multi-word phrase card has no DB uniqueness and a double tap would otherwise
#: race the `lower(front)` pre-check into two cards.
W16_LOCK_CLASS = 16

#: `errors.source` for both kinds. v2's `'diary'` is the VOICE diary and would
#: mislabel a typed entry; widening the CHECK for a new value buys nothing.
JOURNAL_SOURCE = "text"


class WritingUnavailable(Exception):
    """The model did not return a usable correction. Carries no client detail."""


class CeilingReached(Exception):
    """Today's submissions are used. Carries no count — nothing may show one."""


class WrongDayKind(Exception):
    """A kind posted outside the day that serves it (finding (c)). No spend, no row."""


class NoParagraphTask(Exception):
    """A paragraph was asked for and the learner's unit has no task (unseeded)."""


class NotOfferable(Exception):
    """`POST /write/keep` was sent a phrase the offer rule would never have offered."""


@dataclass(frozen=True)
class WritingToday:
    day_kind: DayKind
    session_id: int | None
    ceiling_reached: bool
    #: W16b. The unit's `output_task_written`, verbatim, on a paragraph day only.
    prompt: str | None = None


@dataclass(frozen=True)
class WritingOutcome:
    is_english: bool
    did_well: str | None
    corrections: tuple[dict, ...]
    written: int
    #: W16b. Gated structure prose; ``None`` on the journal or when refused.
    structure: tuple[dict, ...] | None = None
    #: W16b. ``{phrase, sentence, in_deck}``, at most two, paragraph only.
    word_offers: tuple[dict, ...] = ()
    #: W33 (B). The journal's other notes — **shown on request, never journaled**.
    more: tuple[dict, ...] = ()
    #: W33 (B). The natural version as ``{text, changed}`` runs; ``None`` = absent.
    natural: tuple[dict, ...] | None = None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _timezone(conn: Any, user_id: int) -> str | None:
    row = conn.execute(
        "SELECT COALESCE(timezone, 'Europe/Vilnius') AS tz FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    return None if row is None else str(row["tz"])


def submissions_on(conn: Any, user_id: int, local_date: date) -> int:
    """Today's submissions, counted from the log. **Never leaves this service.**"""
    row = conn.execute(
        """
        SELECT count(*)::int AS n
          FROM writing_submissions
         WHERE user_id = %s AND local_date = %s
        """,
        (user_id, local_date),
    ).fetchone()
    return int(row["n"]) if row else 0


def _todays_daily_session(conn: Any, user_id: int, local_date: date) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM sessions
         WHERE user_id = %s AND date = %s AND task_type = %s
        """,
        (user_id, local_date, DAILY_TASK_TYPE),
    ).fetchone()
    return None if row is None else int(row["id"])


def _own_session_today(
    conn: Any, user_id: int, session_id: int | None, local_date: date
) -> int | None:
    """Ruling 1's authorisation. **A foreign or stale id is silently NULL.**

    The id is kept only if it is this learner's own `daily` row for their local
    today. Anything else — another learner's session, yesterday's tab left open
    — is stored as NULL and the correction still returns: refusing would leak
    whether the id exists, and a stale tab is not the learner's fault.
    """
    if session_id is None:
        return None
    row = conn.execute(
        """
        SELECT id FROM sessions
         WHERE id = %s AND user_id = %s AND task_type = %s AND date = %s
        """,
        (session_id, user_id, DAILY_TASK_TYPE, local_date),
    ).fetchone()
    return None if row is None else int(row["id"])


def _written_types(conn: Any) -> list[Any]:
    """The WRITTEN error types, one query for both halves of F6.

    **F6 (operator, on the first §3 rule 2 call).** The prompt listed all
    nineteen codes and then forbade the three spoken ones — *a code the model can
    see is a code it can pick.* So the model is shown only the codes that name a
    written category (`learner_label IS NOT NULL`, migration 027's own
    definition), **and the gates accept exactly the same set**: a spoken code
    coming back is a code this prompt never offered, and is refused as unknown
    rather than journalled with no eyebrow. One list for what is offered and
    what is accepted, not two.
    """
    return conn.execute(
        """
        SELECT code, label, learner_label
          FROM error_types
         WHERE learner_label IS NOT NULL
         ORDER BY code
        """
    ).fetchall()


def _labels(conn: Any) -> dict[str, str | None]:
    return {str(r["code"]): r["learner_label"] for r in _written_types(conn)}


def _type_list(conn: Any) -> str:
    return "\n".join(f"- {r['code']}: {r['label']}" for r in _written_types(conn))


def written_type_list(conn: Any) -> str:
    """F6's one list, for W15's rungs: the codes offered ARE the codes accepted.

    A second query in `conversations.py` would be a second copy of the rule that
    a spoken code is never offered; this is the same query, not a new one.
    """
    return _type_list(conn)


def _current_task(conn: Any, user_id: int) -> str | None:
    """The learner's current unit's `output_task_written`, verbatim. **Nothing generated.**

    #406's four unfit strings (units 18, 21, 22, 23) are served as they are if a
    learner reaches them; they are not rewritten here.
    """
    from core.services import syllabus as syllabus_service

    unit = syllabus_service.unit_for_session(conn, syllabus_service.current_unit(conn, user_id))
    return None if unit is None else unit.output_task_written


def _in_deck(conn: Any, user_id: int, phrases: list[str]) -> set[str]:
    if not phrases:
        return set()
    rows = conn.execute(
        "SELECT lower(front) AS front FROM cards WHERE user_id = %s AND lower(front) = ANY(%s)",
        (user_id, phrases),
    ).fetchall()
    return {str(r["front"]) for r in rows}


def labels() -> dict[str, str | None]:
    """``error_types.code → learner_label``, on a connection of its own.

    For `core.writing.probe`, which may hold no SQL of its own (CLAUDE.md §2 —
    `tests/test_core_boundary.py::test_no_sql_outside_services`).
    """
    with connection() as conn:
        return _labels(conn)


def today(user_id: int, *, now: datetime, settings: Settings | None = None) -> WritingToday | None:
    """`GET /write/today`. **Reads only — never creates a session.**

    ``session_id`` is today's `daily` row if the learner has opened the session;
    `/write` reached from home before that gets ``None`` and its correction
    marks nothing done. ``ceiling_reached`` is a boolean and the count behind it
    stays here (Ruling 3).
    """
    cfg = settings or load_settings()
    with connection() as conn:
        tz = _timezone(conn, user_id)
        if tz is None:
            return None
        local_date = local_today(tz, now)
        kind = rules.day_kind(local_date)
        prompt = _current_task(conn, user_id) if kind == "paragraph" else None
        if kind == "paragraph" and prompt is None:
            # An unseeded syllabus has no task to write a paragraph ON, so the
            # day falls back to the journal rather than showing an empty card.
            kind = "journal"
        return WritingToday(
            day_kind=kind,
            session_id=_todays_daily_session(conn, user_id, local_date),
            ceiling_reached=submissions_on(conn, user_id, local_date)
            >= cfg.writing_max_submissions_per_day,
            prompt=prompt,
        )


# ---------------------------------------------------------------------------
# The model call
# ---------------------------------------------------------------------------


def build_system_prompt(user: User, kind: DayKind, task: str | None = None) -> str:
    """The writing prompt for this learner and this kind. Read fresh each call.

    The paragraph template needs the unit's task, verbatim; asking for it
    without one is an error rather than a prompt with a hole in it.
    """
    if kind == "paragraph" and not task:
        raise ValueError("a paragraph prompt needs the unit's task")
    template = (_PARAGRAPH_PROMPT_PATH if kind == "paragraph" else _PROMPT_PATH).read_text(
        encoding="utf-8"
    )
    # F5: the NAME, never the column value — in this template AND inside the
    # shared clause, which formats `user.native_language` itself. A copy of the
    # user with the name substituted keeps `correction.py` byte-identical.
    named = dataclasses.replace(user, native_language=rules.language_name(user.native_language))
    with connection() as conn:
        type_list = _type_list(conn)
    return template.format(
        cefr_level=user.cefr_level,
        native_language=named.native_language,
        error_type_list=type_list,
        explanation_language_rule=correction.explanation_language_rule(named),
        max_corrections=rules.max_corrections(kind),
        # W33 (B): the journal's other notes; the paragraph template has no slot.
        max_more=rules.JOURNAL_MAX_MORE_NOTES,
        task=task or "",
    )


def call_model(
    user: User, text: str, kind: DayKind, *, usage_out: dict, task: str | None = None
) -> dict:
    """Build the request and send it. **The only place either happens.**

    `reject_truncation` because a truncated array would parse into fewer
    corrections and a silent hole; the budget is per kind (`rules.max_tokens`,
    finding (d)) and a starting value the §3 rule 2 call reports against, not a
    tuned one.
    """
    raw = chat(
        [{"role": "user", "content": correction.wrap_user_text(text)}],
        system=build_system_prompt(user, kind, task),
        json_mode=True,
        max_tokens=rules.max_tokens(kind),
        reject_truncation=True,
        usage_out=usage_out,
    )
    if not isinstance(raw, dict):
        raise LLMError("Expected JSON object from writing correction call")
    return raw


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------


def correct_submission(
    user: User,
    text: str,
    *,
    day_kind: DayKind,
    session_id: int | None,
    now: datetime,
    settings: Settings | None = None,
) -> WritingOutcome:
    """Correct one entry, log it, and journal what survives the gates.

    Order, and why:

    1. **Refuse a kind that does not exist**, then **a kind this day does not
       serve** (finding (c)): the client names the kind it was shown, and until
       review any client could post `paragraph` on any day for eight corrections.
       Refused before the ceiling read, so it spends nothing and writes nothing.
       *(Step 1 read "Refuse a kind W16a does not build (`paragraph` is W16b's)."
       — quoted, #82.)*
    2. **The ceiling, BEFORE the call.** A refused submission spends nothing and
       writes nothing. Two submissions racing the fifth place can both pass
       this read; the ceiling is a spend bound, not a security boundary, and one
       extra call on a race is accepted rather than a lock added.
    3. **The call, with no connection held** — a multi-second provider call must
       not pin a pool slot.
    4. **The log row**, only now that a call completed.
    5. **The gates, then the journal.**
    """
    if day_kind not in rules.WRITTEN_DAY_KINDS:
        raise ValueError(f"unknown day kind {day_kind!r}")
    cfg = settings or load_settings()

    with connection() as conn:
        tz = _timezone(conn, user.id) or "Europe/Vilnius"
        local_date = local_today(tz, now)
        if not rules.accepts_day_kind(day_kind, now.astimezone(ZoneInfo(tz))):
            raise WrongDayKind("this day does not serve that kind")
        if submissions_on(conn, user.id, local_date) >= cfg.writing_max_submissions_per_day:
            raise CeilingReached("today's writing is done")
        linked = _own_session_today(conn, user.id, session_id, local_date)
        labels = _labels(conn)
        task = _current_task(conn, user.id) if day_kind == "paragraph" else None
    if day_kind == "paragraph" and task is None:
        raise NoParagraphTask("no unit task to write a paragraph on")

    usage: dict = {}
    try:
        raw = call_model(user, text, day_kind, usage_out=usage, task=task)
    except LLMError as exc:
        raise WritingUnavailable("model call failed") from exc

    shaped = gates.shape(
        raw, text, limit=rules.max_corrections(day_kind), labels=labels, kind=day_kind
    )

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO writing_submissions (
                user_id, session_id, day_kind, local_date, is_english,
                llm_input_tokens, llm_output_tokens,
                llm_cache_creation_input_tokens, llm_cache_read_input_tokens
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user.id,
                linked,
                day_kind,
                local_date,
                shaped.is_english,
                int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)),
                # F3: caching is live on this request, so input_tokens alone
                # undercounts what was sent ~13x (#321's family).
                int(usage.get("cache_creation_input_tokens", 0)),
                int(usage.get("cache_read_input_tokens", 0)),
            ),
        )
        conn.commit()

    # S4, carried unchanged from W3's path: a processed correction makes today's
    # v2 free-practice day Active. Dropping it would silently change streaks for
    # a learner who writes on the web.
    complete_open_free_practice(user.id, local_date)

    if shaped.dropped:
        logger.info(
            "writing gates dropped user_id=%s reasons=%s",
            user.id,
            ",".join(f"{k}:{v}" for k, v in sorted(shaped.dropped.items())),
        )

    # **W33 (B): the journal takes `shaped.corrections` and NOTHING ELSE.** The
    # other notes and the natural version are display only — a spelling slip is
    # a typo and a phrasing note is not an error (CLAUDE.md §5).
    written = 0
    if shaped.is_english and shaped.corrections:
        written = record_errors(user.id, JOURNAL_SOURCE, list(shaped.corrections))

    word_offers: tuple[dict, ...] = ()
    if day_kind == "paragraph" and shaped.is_english:
        selected = offers.select(shaped.corrections)
        if selected:
            with connection() as conn:
                held = _in_deck(conn, user.id, [o.phrase for o in selected])
            # #419 (W15): each offer is signed, and `keep_phrase` requires it back.
            from core import offer_tokens

            word_offers = tuple(
                {
                    "phrase": o.phrase,
                    "sentence": o.sentence,
                    "in_deck": o.phrase in held,
                    "token": offer_tokens.mint(OFFER_SURFACE, user.id, o.phrase, o.sentence),
                }
                for o in selected
            )

    return WritingOutcome(
        is_english=shaped.is_english,
        did_well=shaped.did_well,
        corrections=shaped.corrections,
        written=written,
        structure=shaped.structure,
        word_offers=word_offers,
        more=shaped.more,
        natural=shaped.natural,
    )


# ---------------------------------------------------------------------------
# Keep — W16b
# ---------------------------------------------------------------------------


#: The offer-token surface name (#419). A `/talk` token never verifies here.
OFFER_SURFACE = "write"


def keep_phrase(
    user_id: int, phrase: str, sentence: str, *, now: datetime, token: str | None = None
) -> str:
    """`POST /write/keep`: one offered phrase into the deck. ``"saved"`` or ``"already"``.

    **#419, CLOSED W15: THE PAIR MUST CARRY THE TOKEN ITS OFFER WAS SIGNED
    WITH** (`core.offer_tokens`). The paragraph below records the limit this
    closes and is kept as written (#82's shape): an invented but consistent pair
    no longer verifies, because the server signed only what it offered. The
    offer rule's re-check still runs after it and still normalises the phrase.

    **THE OFFER RULE IS RE-APPLIED ON WRITE, AND IT NARROWS #408 ON THIS SURFACE;
    IT DOES NOT CLOSE IT (#419).** Every word must resolve and every content word
    must lemmatise to a word of `sentence`, so a non-word or a phrase absent from
    its sentence is refused. **But the client sends BOTH halves**, so a consistent
    invented pair is saved — `weed`/`weed`, or `the person` from *it depends on
    the person*, neither of which Q-E would have offered (the change condition
    needs the learner's original, which is never stored, CLAUDE.md §5).
    `test_stated_limit_keep_cannot_prove_a_phrase_was_offered` pins it.
    *(This paragraph read "SO A STRING THAT WOULD NOT HAVE BEEN OFFERED CANNOT BE
    SAVED — the gap … is closed on this surface" — quoted, #82; finding (a).)*
    The fix that would close it without storing text is a server-signed offer
    token on the wire, which is a contract change and is #419's, not this slice's.

    **The card:** `recognition`, `register='neutral'`, `register_source=
    'import_default'` — `/talk`'s precedent, and an imperfect name for a phrase
    kept from writing, recorded rather than widened — `context_sentence` is the
    app's corrected sentence, `source_title='writing'`. A new card in `learning`,
    due now. No model call.
    """
    from core.services.cards import CardState, create_card
    from core.services.lexicon import lexeme_ids

    from core import offer_tokens

    if not offer_tokens.verify(OFFER_SURFACE, user_id, token, phrase, sentence):
        raise NotOfferable("that pair was not offered")
    normal = offers.normal_phrase(phrase)
    sentence = " ".join((sentence or "").split())
    if normal is None or not sentence or not offers.is_offerable(normal, sentence):
        raise NotOfferable("phrase would not have been offered")

    with connection() as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (W16_LOCK_CLASS, user_id))
            seen = conn.execute(
                "SELECT 1 FROM cards WHERE user_id = %s AND lower(front) = %s LIMIT 1",
                (user_id, normal),
            ).fetchone()
            if seen is not None:
                return "already"
            lexeme_id = lexeme_ids(conn, [normal]).get(normal) if " " not in normal else None
            card_id = create_card(
                conn,
                user_id,
                card_type="recognition",
                front=normal,
                back=normal,
                register="neutral",
                register_source="import_default",
                state=CardState(
                    fsrs_state="learning",
                    fsrs_step=0,
                    stability=None,
                    difficulty=None,
                    due=now,
                    last_review=None,
                    lapses=0,
                    reps=0,
                ),
                source_ref="writing",
                context_sentence=sentence,
                lexeme_id=lexeme_id,
                captured_at=now,
                source_title="writing",
            )
    return "saved" if card_id is not None else "already"
