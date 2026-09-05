"""W13b — the conversation surface. **The service: SQL and the provider calls.**

`HTTP route -> service function -> SQL` (CLAUDE.md §2). The routes parse,
authorise, call one function here and serialise. Every query in the slice lives
in this file, and so does every call to `core.llm` / `core.speech` --
`core/services/shadow_score.py`'s shipped shape, and the reason
`core/conversation/`'s model-caller pin is EMPTY rather than one member.

────────────────────────────────────────────────────────────────────────────────
**§1a IS AMENDED FOR CONVERSATION** (assistant-recommended, operator-accepted
2026-09-04). A reply IS generation and a learner IS waiting; there is no version
of conversation where that is untrue. **The second half of the 2026-08-27 ruling
is untouched: nothing here is scheduled and nothing generates unattended.**

**THE THREE ACCEPTED COSTS, AS COSTS.** (1) Unbounded per session, bounded here
only by a turn cap. (2) **No gate certifies a reply** -- the blind solver is
undefined on this object and the model half of the naturalness gate is refused
on cost; what runs is ONE refusing gate (guilt) and TWO measuring gates
(coverage, offline naturalness). (3) **The wait is the product** -- 2-4s per
turn, and nothing here pretends otherwise.

────────────────────────────────────────────────────────────────────────────────
**RETENTION (§2a): TURNS ARE DELETED AT CLOSE, AND BY TRAFFIC, NEVER BY A JOB.**
`english-worker` is not installed (#69) and nothing scheduled has ever fired on
this host, so a reaper would be a rule with no enforcer. The three deleters are
`sweep_expired_turns` (called at the top of EVERY entry point, for ALL users),
the close-out's own delete, and the human-run `python -m core.conversation.sweep`.
**The residual is filed as #384, not hidden in a comment:** if the surface is
never reopened, the last conversation's turns persist.

**METERING (§2b): counts only.** `conversation_usage` holds turns, calls, tokens
and seconds. **What was said is not a metric** (CLAUDE.md §5, PRD §12.8), and no
log line in this module carries a fragment of a turn. **No dollar figure is
stored, computed or printed** (#321).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from core import PROMPTS_DIR, llm, speech
from core.conversation import (
    CLOSE_MAX_TOKENS,
    HISTORY_MAX_MESSAGES,
    MAX_ALTERNATIVES,
    TURN_MAX_TOKENS,
    Turn,
    build_close_messages,
    build_system_prompt,
    build_turn_messages,
    cap_exceeded,
    topic_seed,
)
from core.conversation.guards import Correction, apply_guards
from core.config import load_settings
from core.copy_rules import content_offenders
from core.db import connection
from core.services.errors import record_errors
from core.services.lexicon import coverage_for
from core.video.score import BAND_LOW, BAND_HIGH

logger = logging.getLogger(__name__)


class ConversationError(Exception):
    """Base for every refusal this service makes."""


class NoConversation(ConversationError):
    """No open conversation for this learner. **Mapped to 404 at the route.**"""


class NotConsented(ConversationError):
    """Voice is not enabled for this learner (#364). **404, never 403.**"""


class CapReached(ConversationError):
    """The day's turns are spent. A stated condition, not an error."""


class AlternativeSpent(ConversationError):
    """The one topic swap has been used. §2c: one alternative, then it stands."""


#: **A REAL SENTENCE A PERSON WROTE, not a generated fallback.** Shown when a
#: reply trips the guilt scan twice. Bounded at two calls on a rare event, and
#: it is a constant rather than a third generation because the whole reason the
#: reply was refused is that the model produced something it should not have.
GUILT_FALLBACK_TURN = "Tell me a bit more about that — I'd like to hear it."

#: Below this the coverage number is noise: one unknown word in a five-word
#: reply reads as 80%. **NOT `core.video.badge.MIN_COUNTED_TOKENS`, which is 100
#: and would suppress the band on EVERY conversation turn** -- an instrument
#: switched off is #345's exact defect, and an assertion set carrying `None`
#: beside the real bands would then stay green forever. The band edges are
#: imported from `score.py` rather than restated, for `badge.py`'s own reason:
#: the number a reply is judged against and the number a video is selected on
#: must not be able to disagree.
MIN_REPLY_TOKENS = 12

_turn_template: str | None = None
_close_template: str | None = None


def _templates() -> tuple[str, str]:
    global _turn_template, _close_template
    if _turn_template is None:
        _turn_template = (PROMPTS_DIR / "conversation_v3.txt").read_text(
            encoding="utf-8"
        )
    if _close_template is None:
        _close_template = (PROMPTS_DIR / "conversation_close.txt").read_text(
            encoding="utf-8"
        )
    return _turn_template, _close_template


def voice_allowed_for(user_id: int, settings: Any = None) -> bool:
    """**One condition, one home** -- shared with the shadow surface (#364).

    Reads the SAME `SHADOW_ALLOWED_USER_IDS`, deliberately: the question that
    gate asks is *may this learner's voice leave her device*, and it is the same
    question whether the audio goes to Microsoft or to OpenAI. **The variable is
    not renamed in this slice** -- it fails closed, so a half-applied rename on a
    live `.env` would close a feature rather than open one, but it is still a
    production edit with no reason behind it.

    `core.services.shadow_score.scoring_allowed_for` delegates here so there is
    one predicate rather than two that can drift.

    **THE TYPED HALF IS NOT GATED.** Typed text already reaches Anthropic today
    from `POST /correct`, which both learners use, so gating it would withdraw a
    surface rather than protect one. **The second learner gets the conversation
    in text from day one; only the microphone waits on #364.**
    """
    cfg = settings or load_settings()
    return user_id in cfg.shadow_allowed_user_ids


def band_for_reply(coverage: float, counted_tokens: int) -> str | None:
    """Which side of PRD §2.1's band a generated turn falls, or None if short.

    **RECORDED, NEVER ENFORCED** -- §8.6 question 1 is ruled SHIP AND RECORD:
    regeneration bills a second call on every failure inside a loop already
    called unbounded and doubles the wait; simplification risks the unnatural
    English §4.6's gate exists to refuse. Shipping and recording costs nothing
    and buys the measurement nobody has.
    """
    if counted_tokens < MIN_REPLY_TOKENS:
        return None
    if coverage < BAND_LOW:
        return "below"
    if coverage > BAND_HIGH:
        return "above"
    return "in"


# ── retention ───────────────────────────────────────────────────────────────


def sweep_expired_turns(conn: Any, now: datetime, timeout_minutes: int) -> int:
    """Delete the turns of every conversation that is closed or gone cold.

    **ALL USERS, NOT JUST THE CALLER'S.** On a two-learner system the cost is
    nothing and the guarantee is much stronger: retention then does not depend
    on the affected learner being the next one to open the surface.

    Returns the number of turns deleted, so the caller can log a COUNT -- never
    a body.
    """
    row = conn.execute(
        """
        WITH gone AS (
            DELETE FROM conversation_turns t
             USING conversations c
             WHERE t.conversation_id = c.id
               AND (
                     c.closed_at IS NOT NULL
                  OR c.last_activity_at < %s::timestamptz
                                          - make_interval(mins => %s)
               )
         RETURNING t.id
        )
        SELECT count(*)::int AS n FROM gone
        """,
        (now, timeout_minutes),
    ).fetchone()
    n = int((row or {}).get("n") or 0)
    if n:
        logger.info("conversation turns swept n=%s", n)
    return n


def expired_turn_count(conn: Any, now: datetime, timeout_minutes: int) -> int:
    """How many turns the sweep would delete. **The dry run's number.**

    It lives here and not in `core/conversation/sweep.py` because SQL belongs in
    a service (CLAUDE.md §2) -- `test_no_sql_outside_services` caught the first
    draft holding this query in the CLI, and the fix was to move it rather than
    to take an exemption. `core/lessons/generate.py` is the precedent: a
    human-run module reaches the database only through a service.
    """
    row = conn.execute(
        """
        SELECT count(*)::int AS n
          FROM conversation_turns t JOIN conversations c
            ON c.id = t.conversation_id
         WHERE c.closed_at IS NOT NULL
            OR c.last_activity_at < %s::timestamptz - make_interval(mins => %s)
        """,
        (now, timeout_minutes),
    ).fetchone()
    return int((row or {}).get("n") or 0)


def _close_stale_conversations(conn: Any, now: datetime, timeout_minutes: int) -> None:
    """A cold conversation is over. Closing it is what frees the open slot.

    No close-out call and no corrections: nobody is there to read them, and
    generating for an absent learner is the half of the 2026-08-27 ruling this
    slice did NOT amend.
    """
    conn.execute(
        """
        UPDATE conversations
           SET closed_at = %s
         WHERE closed_at IS NULL
           AND last_activity_at < %s::timestamptz - make_interval(mins => %s)
        """,
        (now, now, timeout_minutes),
    )


def _entry(conn: Any, now: datetime, cfg: Any) -> None:
    """Every entry point begins here. **This is deleter number two.**"""
    _close_stale_conversations(conn, now, cfg.conversation_timeout_minutes)
    sweep_expired_turns(conn, now, cfg.conversation_timeout_minutes)


# ── metering ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Usage:
    turns_learner: int = 0
    turns_app: int = 0
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    stt_seconds: float = 0.0
    stt_calls: int = 0
    tts_calls: int = 0


def usage_today(conn: Any, user_id: int, local_date: date) -> Usage:
    row = conn.execute(
        """
        SELECT turns_learner, turns_app, llm_calls, llm_input_tokens,
               llm_output_tokens, stt_seconds, stt_calls, tts_calls
          FROM conversation_usage
         WHERE user_id = %s AND local_date = %s
        """,
        (user_id, local_date),
    ).fetchone()
    if row is None:
        return Usage()
    return Usage(**{k: row[k] for k in row})


def _bump_usage(conn: Any, user_id: int, local_date: date, **deltas: Any) -> None:
    """Add into today's counters. **Counts only -- never a fragment of a turn.**

    An UPSERT so the first turn of a day needs no separate insert, and so two
    workers cannot race a read-modify-write.
    """
    cols = (
        "turns_learner", "turns_app", "llm_calls", "llm_input_tokens",
        "llm_output_tokens", "stt_seconds", "stt_calls", "tts_calls",
    )
    vals = {c: deltas.get(c, 0) for c in cols}
    conn.execute(
        f"""
        INSERT INTO conversation_usage (
            user_id, local_date, {", ".join(cols)}
        ) VALUES (%s, %s, {", ".join(["%s"] * len(cols))})
        ON CONFLICT (user_id, local_date) DO UPDATE SET
            {", ".join(
                f"{c} = conversation_usage.{c} + EXCLUDED.{c}" for c in cols
            )},
            updated_at = now()
        """,
        (user_id, local_date, *[vals[c] for c in cols]),
    )


def _record_llm(conn: Any, user_id: int, local_date: date, usage_out: dict) -> None:
    _bump_usage(
        conn, user_id, local_date,
        llm_calls=int(usage_out.get("calls", 0)),
        llm_input_tokens=int(usage_out.get("input_tokens", 0)),
        llm_output_tokens=int(usage_out.get("output_tokens", 0)),
    )


# ── reading the learner and the topic sources ───────────────────────────────


def _learner(conn: Any, user_id: int) -> dict:
    row = conn.execute(
        """
        SELECT cefr_level, native_language, timezone, track_weights
          FROM users WHERE id = %s
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise NoConversation("no such learner")
    return dict(row)


def _track_for(track_weights: Any) -> str:
    """§4.6's weights, and **Work is capped at 20%**.

    The heaviest non-work track wins. **Work is never chosen here**: a cap of
    20% means at most one conversation in five, and a chooser that could pick it
    on a tie would drift above the cap invisibly. v2's biggest product failure
    was that everything sounded like a Slack message about a deploy; W13b does
    not reopen that door for a rounding reason.
    """
    weights = dict(track_weights or {})
    life = int(weights.get("life", 50) or 0)
    curiosity = int(weights.get("curiosity", 30) or 0)
    return "Life & Social" if life >= curiosity else "Curiosity"


def _topic_sources(conn: Any, user_id: int) -> dict[str, Any]:
    """This week's grammar target, the unit's lexis, and recent saved words.

    **Every read here is best-effort and says so.** A learner with no
    `user_unit_state` row, an empty deck or an un-authored unit still gets a
    conversation -- `topic_seed` renders "(none yet)" and the opener is asked to
    be concrete anyway. **A surface that refuses to open because the syllabus is
    thin would be #299's shape in a new place.**
    """
    target: str | None = None
    lexemes: list[str] = []
    row = conn.execute(
        """
        SELECT su.grammar_targets, su.target_lexemes
          FROM user_unit_state uus
          JOIN syllabus_units su ON su.unit_number = uus.unit_number
         WHERE uus.user_id = %s
      ORDER BY uus.unit_number DESC
         LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row is not None:
        targets = row["grammar_targets"] or []
        if targets:
            first = targets[0]
            target = first.get("label") if isinstance(first, dict) else str(first)
        lexemes = [str(x) for x in (row["target_lexemes"] or [])]

    recent = conn.execute(
        """
        SELECT DISTINCT lemma FROM cards
         WHERE user_id = %s AND captured_at >= now() - interval '7 days'
           AND lemma IS NOT NULL
         LIMIT 12
        """,
        (user_id,),
    ).fetchall()
    return {
        "grammar_target": target,
        "unit_lexemes": lexemes,
        "recent_words": [r["lemma"] for r in recent],
    }


# ── turns ───────────────────────────────────────────────────────────────────


def _open_row(conn: Any, user_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, topic_label, turns_learner, turns_app, alternatives_used
          FROM conversations
         WHERE user_id = %s AND closed_at IS NULL
        """,
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def _history(conn: Any, conversation_id: int) -> list[Turn]:
    rows = conn.execute(
        """
        SELECT seq, role, content, input_mode
          FROM conversation_turns
         WHERE conversation_id = %s
      ORDER BY seq
        """,
        (conversation_id,),
    ).fetchall()
    return [Turn(**dict(r)) for r in rows]


def _as_messages(turns: list[Turn]) -> list[dict[str, str]]:
    """Turns as provider messages. **Learner text becomes `content`, nothing else.**"""
    return [
        {"role": "user" if t.is_learner else "assistant", "content": t.content}
        for t in turns
    ]


def _append(
    conn: Any,
    conversation_id: int,
    seq: int,
    role: str,
    content: str,
    *,
    input_mode: str | None = None,
    coverage_band: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO conversation_turns
            (conversation_id, seq, role, content, input_mode, coverage_band)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (conversation_id, seq, role, content, input_mode, coverage_band),
    )


def _generate_reply(
    conn: Any,
    user_id: int,
    learner: dict,
    topic_label: str,
    sources: dict,
    history: list[Turn],
    learner_text: str | None,
) -> tuple[str, str | None, dict]:
    """One app turn: build, call, gate, band. Returns (text, band, usage).

    **THE GUILT GATE IS THE ONE THAT REFUSES.** `content_offenders` is a
    compiled regex, free and synchronous. A reply carrying a hit is not shown:
    ONE retry, then `GUILT_FALLBACK_TURN`, a sentence a person wrote. Bounded at
    two calls on a rare event.

    **THE COVERAGE BAND IS MEASURED AND SHIPPED ANYWAY** (§8.6 Q1, ruled).

    **THE OFFLINE NATURALNESS HALF IS RECORDED, NEVER ENFORCED** (#271): a guard
    can refuse a bad draft but never show the model understood the rule.
    """
    turn_template, _ = _templates()
    system = build_system_prompt(
        turn_template,
        cefr_level=learner["cefr_level"],
        native_language=learner["native_language"],
        topic_label=topic_label,
        **topic_seed(
            grammar_target=sources["grammar_target"],
            unit_lexemes=sources["unit_lexemes"],
            recent_words=sources["recent_words"],
            track=_track_for(learner["track_weights"]),
        ),
    )
    messages = (
        build_turn_messages(_as_messages(history), learner_text)
        if learner_text is not None
        else [{"role": "user", "content": "Start the conversation."}]
    )

    usage_out: dict = {}
    text = str(
        llm.chat(
            messages,
            system=system,
            max_tokens=TURN_MAX_TOKENS,
            usage_out=usage_out,
        )
    ).strip()

    if content_offenders(text):
        logger.warning("conversation reply tripped the guilt scan; retrying once")
        text = str(
            llm.chat(
                messages,
                system=system,
                max_tokens=TURN_MAX_TOKENS,
                usage_out=usage_out,
            )
        ).strip()
        if content_offenders(text):
            logger.warning("conversation reply tripped it twice; using the fallback")
            text = GUILT_FALLBACK_TURN

    report = coverage_for(conn, user_id, text)
    band = band_for_reply(report.coverage, report.counted_tokens)
    # Counts and a band. **No fragment of the reply and none of the learner's
    # text ever reaches a log line** (CLAUDE.md §5).
    logger.info(
        "conversation turn user_id=%s band=%s counted_tokens=%s",
        user_id, band, report.counted_tokens,
    )
    return text, band, usage_out


@dataclass(frozen=True)
class TurnResult:
    """What a route serialises. **`state` is the cap's only announcement.**"""

    conversation_id: int
    topic_label: str
    learner_text: str | None
    reply: str
    turns_learner: int
    #: `open` or `closing`. **No number crosses the wire** -- a remaining-turns
    #: count is a backlog running backwards and a tally is a score (#348).
    state: str


def _local_date(learner: dict, now: datetime) -> date:
    from core.services.sessions import local_today

    return local_today(learner["timezone"], now)


def open_conversation(
    user_id: int, now: datetime, *, session_id: int | None = None
) -> TurnResult:
    """Open today's conversation. **The opener IS the topic (§2c).**

    One call, not two: the app says something and the learner answers it, and
    the stored `topic_label` is derived from that opener. A separate
    topic-generation call would have doubled the per-conversation cost against
    §0's first accepted cost for no product gain.

    Re-opening while one is already open **returns it** rather than creating a
    second -- `conversations_one_open_per_user` would refuse the insert anyway,
    and a 500 on a double-tap is not a design.
    """
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)

        existing = _open_row(conn, user_id)
        if existing is not None:
            history = _history(conn, existing["id"])
            reply = history[-1].content if history else ""
            return TurnResult(
                conversation_id=existing["id"],
                topic_label=existing["topic_label"],
                learner_text=None,
                reply=reply,
                turns_learner=existing["turns_learner"],
                state="open",
            )

        used = usage_today(conn, user_id, today)
        if cap_exceeded(used.turns_learner, cfg.conversation_max_turns_per_day):
            raise CapReached("the day's conversation is done")

        sources = _topic_sources(conn, user_id)
        row = conn.execute(
            """
            INSERT INTO conversations (user_id, session_id, topic_label)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (user_id, session_id, "…"),
        ).fetchone()
        conversation_id = int(row["id"])

        reply, band, usage_out = _generate_reply(
            conn, user_id, learner, "today's topic", sources, [], None
        )
        _append(conn, conversation_id, 0, "app", reply, coverage_band=band)
        conn.execute(
            """
            UPDATE conversations
               SET topic_label = %s, turns_app = 1, last_activity_at = %s
             WHERE id = %s
            """,
            (_label_from(reply), now, conversation_id),
        )
        _bump_usage(conn, user_id, today, turns_app=1)
        _record_llm(conn, user_id, today, usage_out)
        conn.commit()
        return TurnResult(
            conversation_id=conversation_id,
            topic_label=_label_from(reply),
            learner_text=None,
            reply=reply,
            turns_learner=0,
            state="open",
        )


def _label_from(opener: str) -> str:
    """The topic as a short label, for rotation. **The app's own English.**

    Kept when the turns are deleted (§2a) precisely because PRD §8.6.1 says the
    topic ROTATES, and rotation cannot run against a history that was erased.
    """
    first = opener.strip().split("\n")[0].strip()
    return (first[:77] + "…") if len(first) > 78 else (first or "conversation")


def alternative_topic(user_id: int, now: datetime) -> TurnResult:
    """**One swap, then the topic stands.** §2c, and the ceiling is arithmetic.

    v2's three-button picker is deliberately not ported: a menu of three is a
    browsable list, refused by PRD §8.6.1, §7.4 and CLAUDE.md §4.
    """
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)
        row = _open_row(conn, user_id)
        if row is None:
            raise NoConversation("no open conversation")
        if row["alternatives_used"] >= MAX_ALTERNATIVES:
            raise AlternativeSpent("the topic stands")
        if row["turns_learner"] > 0:
            # Swapping after the learner has spoken would discard their turns.
            raise AlternativeSpent("the conversation has already started")

        sources = _topic_sources(conn, user_id)
        reply, band, usage_out = _generate_reply(
            conn, user_id, learner, "a different topic", sources, [], None
        )
        conn.execute(
            "DELETE FROM conversation_turns WHERE conversation_id = %s",
            (row["id"],),
        )
        _append(conn, row["id"], 0, "app", reply, coverage_band=band)
        conn.execute(
            """
            UPDATE conversations
               SET topic_label = %s, alternatives_used = alternatives_used + 1,
                   turns_app = turns_app + 1, last_activity_at = %s
             WHERE id = %s
            """,
            (_label_from(reply), now, row["id"]),
        )
        _bump_usage(conn, user_id, today, turns_app=1)
        _record_llm(conn, user_id, today, usage_out)
        conn.commit()
        return TurnResult(
            conversation_id=row["id"],
            topic_label=_label_from(reply),
            learner_text=None,
            reply=reply,
            turns_learner=0,
            state="open",
        )


def add_turn(
    user_id: int,
    learner_text: str,
    now: datetime,
    *,
    input_mode: str = "typed",
) -> TurnResult:
    """One learner turn and the app's reply.

    **THE CAP IS CHECKED BEFORE THIS TURN IS ACCEPTED, NEVER AFTER GENERATING
    THE REPLY**, so the learner's last message always gets an answer and there
    is no dangling question. When the cap is reached the route closes the
    conversation the way End does; it does not fail mid-exchange.
    """
    text = (learner_text or "").strip()
    if not text:
        raise ConversationError("empty turn")
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)
        row = _open_row(conn, user_id)
        if row is None:
            raise NoConversation("no open conversation")

        used = usage_today(conn, user_id, today)
        if cap_exceeded(used.turns_learner, cfg.conversation_max_turns_per_day):
            raise CapReached("the day's conversation is done")

        history = _history(conn, row["id"])
        seq = (history[-1].seq + 1) if history else 0
        _append(conn, row["id"], seq, "learner", text, input_mode=input_mode)

        sources = _topic_sources(conn, user_id)
        reply, band, usage_out = _generate_reply(
            conn, user_id, learner, row["topic_label"], sources, history, text
        )
        _append(conn, row["id"], seq + 1, "app", reply, coverage_band=band)
        conn.execute(
            """
            UPDATE conversations
               SET turns_learner = turns_learner + 1, turns_app = turns_app + 1,
                   last_activity_at = %s
             WHERE id = %s
            """,
            (now, row["id"]),
        )
        _bump_usage(conn, user_id, today, turns_learner=1, turns_app=1)
        _record_llm(conn, user_id, today, usage_out)
        conn.commit()

        turns_learner = used.turns_learner + 1
        state = (
            "closing"
            if cap_exceeded(turns_learner, cfg.conversation_max_turns_per_day)
            else "open"
        )
        return TurnResult(
            conversation_id=row["id"],
            topic_label=row["topic_label"],
            learner_text=text,
            reply=reply,
            turns_learner=turns_learner,
            state=state,
        )


def transcribe_turn(user_id: int, audio: bytes, now: datetime) -> str:
    """Voice in. **The audio is transcribed in-request and discarded (§12).**

    Gated by `voice_allowed_for` **before the provider call**, because a gate
    that refused after sending the audio would already have done the thing it
    prevents (#364's own reasoning, applied unchanged).

    The bytes are never written anywhere: they arrive in memory, go to one
    provider call, and are dropped when this returns. **The transcript is shown
    to the learner as their own turn**, which is what makes a voice-sourced
    correction quote a line they have already read (§2a.1, #381).
    """
    cfg = load_settings()
    if not voice_allowed_for(user_id, cfg):
        raise NotConsented("voice is not enabled for this learner")
    text = speech.transcribe(audio, settings=cfg).strip()
    with connection() as conn:
        learner = _learner(conn, user_id)
        _bump_usage(
            conn, user_id, _local_date(learner, now),
            stt_calls=1, stt_seconds=0.0,
        )
        conn.commit()
    return text


@dataclass(frozen=True)
class CloseResult:
    """What the learner sees at the end. **Shown ≠ written (§2a.1).**"""

    conversation_id: int
    corrections: list[Correction]
    did_well: str
    #: How many of `corrections` reached `errors`. **A count for the record and
    #: the tests, never rendered** -- a tally shown to a learner is a score.
    journaled: int


def _valid_error_types(conn: Any) -> frozenset[str]:
    rows = conn.execute("SELECT code FROM error_types").fetchall()
    return frozenset(r["code"] for r in rows)


def close_conversation(user_id: int, now: datetime) -> CloseResult:
    """End the conversation: guards, then the journal, then the delete.

    **THE ORDER IS LOAD-BEARING AND IS THE WHOLE REASON THIS IS ONE FUNCTION.**
    G2 checks `you_said` against the learner's own turns, so **the turns must
    still exist when the guards run** -- the delete is last. And the delete and
    the `errors` write share one transaction, so a conversation cannot end with
    the corrections written and the turns retained, nor the reverse.

    **A close with no history writes nothing and generates nothing.** There is
    no transcript to review and calling the model to say so would be a billed
    call for an empty conversation.

    **A GENERATION FAILURE RELEASES THE LEARNER.** v2's S26a lesson: losing ≤2
    corrections is better than trapping someone in a conversation they have
    ended. The turns are still deleted -- retention does not depend on the
    provider answering.
    """
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)
        row = _open_row(conn, user_id)
        if row is None:
            raise NoConversation("no open conversation")
        conversation_id = int(row["id"])
        turns = _history(conn, conversation_id)

        corrections: list[Correction] = []
        did_well = ""
        if turns and any(t.is_learner for t in turns):
            _, close_template = _templates()
            system = build_system_prompt(
                close_template,
                cefr_level=learner["cefr_level"],
                native_language=learner["native_language"],
                work_domain="general",
                error_type_list=", ".join(sorted(_valid_error_types(conn))),
                recurring_error_labels="(none yet)",
                explanation_language_rule="",
            )
            usage_out: dict = {}
            try:
                result = llm.chat(
                    build_close_messages(
                        _as_messages(turns), max_messages=HISTORY_MAX_MESSAGES
                    ),
                    system=system,
                    json_mode=True,
                    max_tokens=CLOSE_MAX_TOKENS,
                    reject_truncation=True,
                    usage_out=usage_out,
                )
            except Exception:  # noqa: BLE001 -- release the learner (S26a)
                logger.warning("conversation close failed user_id=%s", user_id)
                result = {}
            finally:
                _record_llm(conn, user_id, today, usage_out)

            if isinstance(result, dict):
                did_well = str(result.get("did_well") or "").strip()
                corrections = apply_guards(
                    list(result.get("errors") or []),
                    turns,
                    _valid_error_types(conn),
                )

        # **G3's write half. `journalable` is filtered HERE and nowhere in the
        # render path** -- that asymmetry is S1's ruling in one line.
        writable = [c for c in corrections if c.journalable]
        journaled = 0
        if writable:
            journaled = record_errors(
                user_id,
                "conversation",
                [
                    {
                        "you_said": c.you_said,
                        "correct_form": c.correct_form,
                        "error_type": c.error_type,
                        "explanation": c.explanation,
                    }
                    for c in writable
                ],
            )

        # **DELETER NUMBER ONE, AND IT RUNS AFTER THE GUARDS.**
        conn.execute(
            "DELETE FROM conversation_turns WHERE conversation_id = %s",
            (conversation_id,),
        )
        conn.execute(
            "UPDATE conversations SET closed_at = %s WHERE id = %s",
            (now, conversation_id),
        )
        conn.commit()

    logger.info(
        "conversation closed user_id=%s shown=%s journaled=%s",
        user_id, len(corrections), journaled,
    )
    return CloseResult(
        conversation_id=conversation_id,
        corrections=corrections,
        did_well=did_well,
        journaled=journaled,
    )
