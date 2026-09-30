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

from collections.abc import Iterable

import logging
from dataclasses import dataclass, replace
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
from core.copy_rules import BANNED, content_offenders
from core.db import connection
from core.services.errors import record_errors
from core.lexicon.normalize import cefr_tagged_lemmas, lemmatize
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


class NoRung(ConversationError):
    """W15. The rung asked for is not on offer today — no seeded unit for an
    answer, no video with a transcript for a retell. **404 at the route**: a
    rung that is not offered is absent, never refused with a reason."""


class NotOffered(ConversationError):
    """#408. A word whose offer token does not verify. **422 at the route.**"""


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


_close_v3_template: str | None = None


def _close_v3() -> str:
    """§C3's close prompt. **A NEW FILE, NOT AN EDIT TO THE SHARED ONE.**

    `conversation_close.txt` is the v2 Telegram bot's and is left untouched:
    adding a `summary` field to it would change a shipped surface's request for
    a caller that does not read the field.
    """
    global _close_v3_template
    if _close_v3_template is None:
        _close_v3_template = (PROMPTS_DIR / "conversation_close_v3.txt").read_text(
            encoding="utf-8"
        )
    return _close_v3_template


def voice_allowed_for(user_id: int, settings: Any = None) -> bool:
    """**One condition, one home** -- shared with the shadow surface (#364).

    Reads `VOICE_ALLOWED_USER_IDS`. The question this gate asks is *may this
    learner's voice leave her device*, and it is the same question whether the
    audio goes to Microsoft or to OpenAI.

    **RENAMED BY W14r, 2026-09-08, AND THE OLD REASONING IS QUOTED BECAUSE IT
    WAS RIGHT WHEN IT WAS WRITTEN** (#82's shape): *"Reads the SAME
    `SHADOW_ALLOWED_USER_IDS`, deliberately... **The variable is not renamed in
    this slice** -- it fails closed, so a half-applied rename on a live `.env`
    would close a feature rather than open one, but it is still a production
    edit with no reason behind it."*

    **THE REASON HAS NOW EXPIRED: there is no shadow surface.** The routes are
    unregistered, so a variable named after them gates a feature that does not
    exist while holding the one that does. **The half-applied risk it named is
    unchanged and is still real** — the gate fails closed, so a `.env` carrying
    neither name closes `/talk`'s microphone rather than opening it. That is the
    safe direction and it is still a surprise, which is why the deploy sets the
    new variable **before** the old one is removed.

    `core.services.shadow_score.scoring_allowed_for` delegates here so there is
    one predicate rather than two that can drift.

    **THE TYPED HALF IS NOT GATED.** Typed text already reaches Anthropic today
    from `POST /correct`, which both learners use, so gating it would withdraw a
    surface rather than protect one. **The second learner gets the conversation
    in text from day one; only the microphone waits on #364.**
    """
    cfg = settings or load_settings()
    return user_id in cfg.voice_allowed_user_ids


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

    **§A, 2026-09-05 — THIS FUNCTION 500'd ON PRODUCTION ON ITS FIRST CALL AND
    THE SURFACE HAD NEVER ONCE OPENED.** The first draft read
    `su.target_lexemes` from `syllabus_units`. **That column does not exist and
    never did.** It is not a rename: **the concept is a different table plus a
    subtraction.**

    * `syllabus_unit_lexemes` holds the CANDIDATE set — shared, no `user_id`,
      migration 014's central design decision.
    * The per-learner list is computed at read time:
      `target_lexemes(user, unit) = unit_candidates(unit) - known_lemmas(user)`,
      which is `core.services.syllabus.unit_target_lexemes`.

    **SO THE FIX IS TO CALL THE FUNCTION THAT ALREADY DOES IT**, and it is
    better than the column would have been: the words it returns are the ones
    this learner does NOT yet know, which is exactly what a topic should reach
    for.

    **THE SHAPE, RECORDED BECAUSE IT IS #355's AND THIS IS ITS FOURTH INSTANCE
    TODAY: the query was written from a document's description of a table rather
    than from the table.** `docs/TASKS-v3-web.md`'s W8 row says each unit has
    *"≥30 target lexemes"* — true, and it describes a DERIVED PER-LEARNER
    QUANTITY, not a column. #355's closing condition is that verification
    queries are written from a read of the migration or psql's own table
    listing, never from
    prose. **That rule was written for runbook queries and it applies to service
    code in exactly the same way**, which is what this instance adds to the row.

    **EVERY READ HERE IS BEST-EFFORT AND SAYS SO.** A learner with no
    `user_unit_state` row, an empty deck or an un-authored unit still gets a
    conversation. **A surface that refused to open because the syllabus is thin
    would be #299's shape in a new place** — and, as §A proved, a surface that
    RAISES because the syllabus is thin is worse still.
    """
    from core.services import syllabus as syllabus_service

    target: str | None = None
    lexemes: list[str] = []
    try:
        unit = syllabus_service.current_unit(conn, user_id)
        row = conn.execute(
            "SELECT grammar_targets FROM syllabus_units WHERE unit_number = %s",
            (unit,),
        ).fetchone()
        if row is not None:
            targets = row["grammar_targets"] or []
            if targets:
                first = targets[0]
                # **THE KEY IS `target`, READ FROM THE ROW.** The first draft
                # guessed `label` and got None on every unit -- the same defect
                # as §A one level down, and it would have degraded silently
                # instead of raising.
                #
                # **AND ONLY `target` IS TAKEN. `murphy_units` SITS BESIDE IT IN
                # THE SAME DICT AND MUST NOT REACH A PROMPT**: #164 re-scoped it
                # to an operator note and #171 asserts no surface renders it.
                # Passing the whole dict would have put a Murphy citation into
                # the model's context and, from there, potentially on a screen.
                target = (
                    str(first.get("target") or "") or None
                    if isinstance(first, dict)
                    else str(first)
                )
        lexemes = syllabus_service.unit_target_lexemes(conn, user_id, unit)[:12]
    except Exception:  # noqa: BLE001
        # **A THIN SYLLABUS MUST NOT BE A 500.** The topic falls back to
        # "(none yet)" and the conversation still opens -- which is the whole
        # lesson of §A, held here rather than only fixed.
        logger.warning("topic sources unavailable user_id=%s", user_id)

    recent = conn.execute(
        """
        SELECT DISTINCT front FROM cards
         WHERE user_id = %s AND captured_at >= now() - interval '7 days'
         LIMIT 12
        """,
        (user_id,),
    ).fetchall()
    return {
        "grammar_target": target,
        "unit_lexemes": lexemes,
        "recent_words": [r["front"] for r in recent],
    }


# ── turns ───────────────────────────────────────────────────────────────────


def _open_row(conn: Any, user_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, topic_label, turns_learner, turns_app, alternatives_used,
               kind, video_id
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


# ── W15: the two rungs ──────────────────────────────────────────────────────
#
# **WHAT W15 IS, FROM THE TASKS ROW AS W14r CORRECTED IT: two rungs ON TOP OF
# W13b's loop — retell and answer. Converse is struck: already shipped.** A rung
# is an exchange on the same tables, the same cap, the same voice gate and the
# same one-shot close; what differs is the opener (not generated) and the close
# prompt (gated by `core.writing.gates`, not by the conversation's guards).
#
# **ONE LEARNER TURN, THEN THE CLOSE.** PRD §8's rungs are a response, not a
# dialogue: *"Retell — ... say it in your own words. LLM scores content
# coverage + flags errors"*; *"Answer — respond to a prompt"*. So `add_turn`
# on a rung records the turn, generates NO reply, and answers `closing`, and the
# client closes. A follow-up turn from the app would be a billed call that
# turns a rung back into a talk.
#
# **W33 (D) — REVERSED FOR `retell` ONLY, BY THE OPERATOR'S RULING OF 2026-09-30
# (#491 → R2).** The operator used retell that day and could not continue
# talking: one message, and the close-out was on the screen. **A retell is now
# 3–5 learner turns**: after each turn below `RETELL_MAX_TURNS`, one short
# follow-up question grounded in THIS video's transcript (`retell_followup_request`,
# one billed call per turn, ≈ $0.0074 uncached); `closing` only at the fifth
# turn, or when the day's cap arrives — the cap is the talk's rule, not a new
# one. The paragraph above stays as written for `answer`, which is unchanged.

KINDS: tuple[str, ...] = ("talk", "answer", "retell")
RUNG_KINDS: frozenset[str] = frozenset({"answer", "retell"})

#: The retell's opener. **A sentence a person wrote, not a generated one** --
#: `GUILT_FALLBACK_TURN`'s reason. Covered by the backend banned-phrase test.
RETELL_OPENER = (
    "Tell me what happened in today’s video — in your own words, the way "
    "you’d tell a friend."
)
#: The goal line a retell's fallback prompt carries (see `_close_rung`).
RETELL_GOAL = "Tell a short story you've just watched, in your own words."
#: What the retell is labelled when the video's title was purged with its
#: metadata (019) but its transcript survived. Never the youtube id.
RETELL_LABEL_FALLBACK = "Today’s video"

#: `/write`'s journal cap, not v2's three: **two**, so every correcting surface
#: in the web app says the same thing about how much is too much.
RUNG_MAX_CORRECTIONS = 2
#: The retell's points. Enough for a short video's shape; few enough that the
#: list reads as a summary and not a checklist.
RUNG_MAX_POINTS = 5
#: `/write`'s journal budget (`rules.max_tokens("journal")`) is 2000 for the same
#: output shape; a retell adds at most five short points.
RUNG_MAX_TOKENS = 2000
#: A transcript longer than this is cut, and the prompt says it may be. ~2,000
#: words: comfortably over a five-minute video (`length_fit` prefers short ones)
#: and a bounded input on a learner-triggered call.
RETELL_TRANSCRIPT_MAX_CHARS = 12_000

#: W33 (D). The retell's turn limit (#491 → R2): the fifth learner turn answers
#: `closing` and asks nothing. Three is block 4's floor (#462) and is the
#: learner's to choose — *That's enough for now* closes at any turn.
RETELL_MAX_TURNS = 5
#: W33 (D). A follow-up is one sentence; the talk's own reply budget.
FOLLOWUP_MAX_TOKENS = TURN_MAX_TOKENS
#: W33 (D). The longest question the gate accepts, in words and characters.
FOLLOWUP_MAX_WORDS = 20
FOLLOWUP_MAX_CHARS = 200
#: W33 (D). **Questions a person wrote**, asked ONLY when the generated one
#: cannot be: the call failed, the reply was not one question, or it tripped the
#: copy rule. They are general by necessity; the alternative is a 500 that loses
#: the learner's turn, or silence. Chosen by turn, so two in a row differ.
RETELL_FALLBACK_QUESTIONS: tuple[str, ...] = (
    "What happened after that?",
    "Why do you think they did that?",
    "How do you think they felt about it?",
    "How did it end?",
)

#: The fence the transcript crosses the wire in. `core.video.explain`'s
#: `<<<TRANSCRIPT_LINE>>>` precedent (#292 part 1), one level up: the whole
#: transcript rather than one line. Constants so a test can assert the text
#: appears in the request ONLY between them.
TRANSCRIPT_OPEN = "<<<VIDEO_TRANSCRIPT>>>"
TRANSCRIPT_CLOSE = "<<<END_VIDEO_TRANSCRIPT>>>"


@dataclass(frozen=True)
class RungMaterial:
    """What a rung opens on. **Nothing here is generated.**"""

    kind: str
    label: str
    opener: str
    video_id: int | None = None


@dataclass(frozen=True)
class Rungs:
    """`GET /conversation/rungs`. **What is on offer today, and nothing that counts.**"""

    answer: RungMaterial | None
    retell: RungMaterial | None
    voice: bool


def _rung_material(conn: Any, user_id: int, today: date, kind: str) -> RungMaterial | None:
    """Today's answer or retell for this learner, or None if it is not on offer.

    **ANSWER: the current unit's `output_task_spoken`, VERBATIM, labelled with
    the unit's can-do** — the TASKS row's *"answer tied to the week's can-do"*.
    W14's block-4 docstring left the 24 strings unserved *"and W15 owns them"*.
    #406's four unfit written tasks are the WRITTEN column; the spoken strings
    are served as authored.

    **RETELL: today's assigned video, only while its transcript exists.** The
    30-day purge nulls a transcript while the assignment survives (#335), and a
    retell cannot be judged against a transcript that is gone — so the rung is
    absent that day rather than offered and then unable to answer.

    **Best-effort, like `_topic_sources`: a thin syllabus or an empty pool makes
    the rung ABSENT, never a 500** (§A's lesson).
    """
    if kind == "answer":
        from core.services import syllabus as syllabus_service

        try:
            unit = syllabus_service.unit_for_session(
                conn, syllabus_service.current_unit(conn, user_id)
            )
        except Exception:  # noqa: BLE001 -- absent, never a 500
            logger.warning("answer rung unavailable user_id=%s", user_id)
            return None
        if unit is None or not (unit.output_task_spoken or "").strip():
            return None
        return RungMaterial(
            kind="answer",
            label=unit.can_do,
            opener=unit.output_task_spoken.strip(),
        )
    if kind == "retell":
        from core.services import video as video_service

        try:
            video = video_service.today_for(conn, user_id, on=today)
        except Exception:  # noqa: BLE001 -- absent, never a 500
            logger.warning("retell rung unavailable user_id=%s", user_id)
            return None
        if video is None or not (video.transcript or "").strip():
            return None
        return RungMaterial(
            kind="retell",
            label=(video.title or "").strip() or RETELL_LABEL_FALLBACK,
            opener=RETELL_OPENER,
            video_id=video.video_id,
        )
    return None


def rungs_today(user_id: int, now: datetime) -> Rungs:
    """What `/talk` can offer besides the conversation. **No provider call.**

    **A READ OF ITS OWN, AND #399 IS WHY.** The page's only other first call is
    `POST /conversation/topics`, which is billed — the direct open onto topic
    cards was declined for exactly that reason. Showing the two rungs must cost
    nothing, so it is a database read the page makes on load. **It carries the
    voice gate too** (the same `voice_allowed_for`, #364), so a learner who goes
    straight to a rung without asking for topics still gets the microphone the
    gate allows and no other.

    **No count, no *done today* flag, no history** (#160): a rung that was
    answered this morning is offered again this afternoon, exactly like a talk.
    """
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)
        answer = _rung_material(conn, user_id, today, "answer")
        retell = _rung_material(conn, user_id, today, "retell")
        conn.commit()
    return Rungs(answer=answer, retell=retell, voice=voice_allowed_for(user_id, cfg))


#: §C1, operator ruling 2026-09-05. **THREE, OFFERED ONCE.**
TOPIC_SUGGESTIONS = 3


def suggest_topics(user_id: int, now: datetime) -> list[str]:
    """Three topics the learner picks from. **§C1 REVERSES §2c, DELIBERATELY.**

    **THE ORIGINAL RULING, QUOTED RATHER THAN DELETED (#82's shape):** *"one
    topic, produced with the opener, plus exactly one alternative... v2's
    three-button picker is a browsable list, refused by PRD §8.6.1, §7.4 and
    CLAUDE.md §4."*

    **THE OPERATOR'S RULING OF 2026-09-05 REVERSES IT, AND THE TENSION IS
    RESOLVED RATHER THAN FUDGED.** CLAUDE.md §4 forbids presenting a BACKLOG,
    and **a backlog is work that accumulates while you are away.** Three
    suggestions accumulate nothing: nothing is owed, nothing is unfinished,
    nothing counts up, and skipping all three leaves no trace. **#160's own
    ruling is that what it forbids is THE COUNTER** — *a tab whose counter
    accumulates while the learner is away is a backlog presented* — and there is
    no counter here.

    **WHAT WOULD MAKE IT A BACKLOG, AND IS THEREFORE FORBIDDEN:** a count of
    topics, a badge, a history of skipped topics, or a *topics you haven't
    tried* list. None of those is built and `TOPIC_SUGGESTIONS` is not rendered.

    **COST, RECORDED AGAINST §0's FIRST ACCEPTED COST:** this is **one more
    provider call per conversation** than §2c's shape, which produced the topic
    as a side effect of the opener. A reshuffle is one more again. P2's token
    prediction is unaffected — these are short completions with no history — but
    the CALL count per conversation rises from 1 + turns + 1 to **2 + turns + 1**.
    """
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)
        sources = _topic_sources(conn, user_id)
        turn_template, _ = _templates()
        system = build_system_prompt(
            turn_template,
            cefr_level=learner["cefr_level"],
            native_language=learner["native_language"],
            topic_label="(choosing a topic)",
            **topic_seed(
                grammar_target=sources["grammar_target"],
                unit_lexemes=sources["unit_lexemes"],
                recent_words=sources["recent_words"],
                track=_track_for(learner["track_weights"]),
            ),
        )
        usage_out: dict = {}
        raw = str(
            llm.chat(
                [{
                    "role": "user",
                    "content": (
                        f"Suggest {TOPIC_SUGGESTIONS} short, concrete things we "
                        "could talk about today, drawing on the material above. "
                        "One per line, no numbering, under eight words each. "
                        "Nothing else."
                    ),
                }],
                system=system,
                max_tokens=120,
                usage_out=usage_out,
            )
        )
        _record_llm(conn, user_id, today, usage_out)
        conn.commit()

    topics = [
        line.strip(" -•*0123456789.").strip()
        for line in raw.splitlines()
        if line.strip()
    ]
    # **THE GUILT SCAN REACHES THE SUGGESTIONS TOO** -- they are learner-facing
    # English like every other string in this surface (#348).
    topics = [x for x in topics if x and not content_offenders(x)]
    return topics[:TOPIC_SUGGESTIONS]


def open_conversation(
    user_id: int,
    now: datetime,
    *,
    session_id: int | None = None,
    topic_label: str | None = None,
    kind: str = "talk",
) -> TurnResult:
    """Open today's conversation — or, W15, one of its two rungs.

    **`talk`: the opener IS the topic (§2c).** One call, not two: the app says
    something and the learner answers it, and the stored `topic_label` is
    derived from that opener. A separate topic-generation call would have
    doubled the per-conversation cost against §0's first accepted cost for no
    product gain.

    **`answer` and `retell` (W15) are opened WITHOUT A PROVIDER CALL.** The
    opener is not generated: an answer's is the unit's `output_task_spoken`,
    verbatim (the TASKS row and the run prompt both say *verbatim*), and a
    retell's is `RETELL_OPENER`, a sentence a person wrote. Opening one costs a
    database read. `NoRung` when it is not on offer today.

    Re-opening while one of the SAME kind is open **returns it** rather than
    creating a second -- `conversations_one_open_per_user` would refuse the
    insert anyway, and a 500 on a double-tap is not a design. **Opening a
    DIFFERENT kind abandons the open one** (`_abandon`): the index holds one
    open exchange of any kind, and a learner who walked away from a talk and
    taps *Answer* has chosen the answer.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown conversation kind {kind!r}")
    cfg = load_settings()
    with connection() as conn:
        _entry(conn, now, cfg)
        learner = _learner(conn, user_id)
        today = _local_date(learner, now)

        existing = _open_row(conn, user_id)
        if existing is not None and existing["kind"] == kind:
            history = _history(conn, existing["id"])
            reply = history[-1].content if history and not history[-1].is_learner else ""
            return TurnResult(
                conversation_id=existing["id"],
                topic_label=existing["topic_label"],
                learner_text=None,
                reply=reply or (history[0].content if history else ""),
                turns_learner=existing["turns_learner"],
                state="open",
            )
        if existing is not None:
            _abandon(conn, existing["id"], now)

        used = usage_today(conn, user_id, today)
        if cap_exceeded(used.turns_learner, cfg.conversation_max_turns_per_day):
            raise CapReached("the day's conversation is done")

        if kind in RUNG_KINDS:
            rung = _rung_material(conn, user_id, today, kind)
            if rung is None:
                raise NoRung(f"no {kind} today")
            row = conn.execute(
                """
                INSERT INTO conversations
                    (user_id, session_id, topic_label, kind, video_id,
                     turns_app, last_activity_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s) RETURNING id
                """,
                (user_id, session_id, rung.label, kind, rung.video_id, now),
            ).fetchone()
            conversation_id = int(row["id"])
            # The opener is an APP turn and carries no coverage band: the band
            # measures what the app GENERATED, and nothing here was generated.
            _append(conn, conversation_id, 0, "app", rung.opener)
            _bump_usage(conn, user_id, today, turns_app=1)
            conn.commit()
            logger.info("conversation rung opened user_id=%s kind=%s", user_id, kind)
            return TurnResult(
                conversation_id=conversation_id,
                topic_label=rung.label,
                learner_text=None,
                reply=rung.opener,
                turns_learner=0,
                state="open",
            )

        sources = _topic_sources(conn, user_id)
        row = conn.execute(
            """
            INSERT INTO conversations (user_id, session_id, topic_label)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (user_id, session_id, "…"),
        ).fetchone()
        conversation_id = int(row["id"])

        chosen = (topic_label or "").strip()
        reply, band, usage_out = _generate_reply(
            conn, user_id, learner, chosen or "today's topic", sources, [], None
        )
        # **THE LEARNER'S CHOSEN TOPIC WINS OVER THE DERIVED LABEL** -- it is
        # what they picked, and rotation should record what they talked about
        # rather than how the opener happened to start.
        label = chosen or _label_from(reply)
        _append(conn, conversation_id, 0, "app", reply, coverage_band=band)
        conn.execute(
            """
            UPDATE conversations
               SET topic_label = %s, turns_app = 1, last_activity_at = %s
             WHERE id = %s
            """,
            (label, now, conversation_id),
        )
        _bump_usage(conn, user_id, today, turns_app=1)
        _record_llm(conn, user_id, today, usage_out)
        conn.commit()
        return TurnResult(
            conversation_id=conversation_id,
            topic_label=label,
            learner_text=None,
            reply=reply,
            turns_learner=0,
            state="open",
        )


def _abandon(conn: Any, conversation_id: int, now: datetime) -> None:
    """Close an open exchange with no close-out, the way a cold one is closed.

    **No close-out call and no journal write**, for `_close_stale_conversations`'
    reason: the learner has moved on and is not there to read corrections, and
    writing rows nobody was shown would be journaling in the dark. At most two
    corrections are lost — the recoverable direction (CLAUDE.md §5). The turns
    go at once, by the sweep's own rule (a closed conversation's turns are
    deleted), rather than waiting for the next entry point.
    """
    conn.execute(
        "UPDATE conversations SET closed_at = %s WHERE id = %s AND closed_at IS NULL",
        (now, conversation_id),
    )
    conn.execute(
        "DELETE FROM conversation_turns WHERE conversation_id = %s", (conversation_id,)
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

        if row["kind"] == "retell":
            # **W33 (D), #491 → R2: A RETELL IS A SHORT CONVERSATION.** The turn
            # is counted exactly as a rung's always was (#462 reads
            # `conversation_usage.turns_learner`); below the limit one follow-up
            # question is generated and the state stays `open`. `closing` only at
            # the fifth turn — or at the day's cap, the talk's own rule.
            turn_number = int(row["turns_learner"]) + 1
            conn.execute(
                """
                UPDATE conversations
                   SET turns_learner = turns_learner + 1, last_activity_at = %s
                 WHERE id = %s
                """,
                (now, row["id"]),
            )
            _bump_usage(conn, user_id, today, turns_learner=1)
            day_done = cap_exceeded(used.turns_learner + 1, cfg.conversation_max_turns_per_day)
            if turn_number >= RETELL_MAX_TURNS or day_done:
                conn.commit()
                return TurnResult(
                    conversation_id=row["id"], topic_label=row["topic_label"],
                    learner_text=text, reply="", turns_learner=used.turns_learner + 1,
                    state="closing",
                )
            question, _generated = _retell_followup(
                conn, user_id, today, learner["cefr_level"],
                _transcript_of(conn, row.get("video_id")),
                [*history, Turn(seq=seq, role="learner", content=text, input_mode=input_mode)],
                turn_number,
            )
            _append(conn, row["id"], seq + 1, "app", question)
            conn.execute(
                """
                UPDATE conversations
                   SET turns_app = turns_app + 1, last_activity_at = %s
                 WHERE id = %s
                """,
                (now, row["id"]),
            )
            _bump_usage(conn, user_id, today, turns_app=1)
            conn.commit()
            return TurnResult(
                conversation_id=row["id"], topic_label=row["topic_label"],
                learner_text=text, reply=question, turns_learner=used.turns_learner + 1,
                state="open",
            )

        if row["kind"] in RUNG_KINDS:
            # **W15: A RUNG TAKES ONE TURN AND GENERATES NO REPLY.** `closing`
            # tells the client to close, which is where the rung's one billed
            # call is made. The turn still counts against the day's cap — it is
            # the learner's own English reaching a model at close.
            conn.execute(
                """
                UPDATE conversations
                   SET turns_learner = turns_learner + 1, last_activity_at = %s
                 WHERE id = %s
                """,
                (now, row["id"]),
            )
            _bump_usage(conn, user_id, today, turns_learner=1)
            conn.commit()
            return TurnResult(
                conversation_id=row["id"],
                topic_label=row["topic_label"],
                learner_text=text,
                reply="",
                turns_learner=used.turns_learner + 1,
                state="closing",
            )

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
    #: §C2. Lemmas from the learner's own TYPED turns that are outside their
    #: ledger. Offered to the deck; **nothing is saved without a tap.**
    unknown_words: tuple[str, ...] = ()
    #: §C3. The app's own English about the conversation. Stored on the row and
    #: **not shown to the learner** -- it is a note the app keeps for itself.
    summary: str = ""
    #: How many of `corrections` reached `errors`. **A count for the record and
    #: the tests, never rendered** -- a tally shown to a learner is a score.
    journaled: int = 0
    #: #408. `unknown_words`, each with the token that proves it was offered.
    word_offers: tuple["WordOffer", ...] = ()
    #: W15. False when a rung's response was not English: nothing is corrected
    #: and nothing is written, and the screen says so without a verdict.
    is_english: bool = True
    #: W15, retell only. **What the retelling got across, as the video's own
    #: points — never a fraction of them** (the run prompt: *shown as what was
    #: covered, never as a percentage*). Neither list is stored.
    covered: tuple[str, ...] = ()
    #: W15, retell only. The video's other points, offered as content.
    also: tuple[str, ...] = ()
    #: `talk`, `answer` or `retell`, so the screen can name what just ended.
    kind: str = "talk"
    #: W33 (D), #493. **False when the close's model call failed** — nothing was
    #: read, so nothing may be praised; the screen says it could not check this
    #: one. True when the call answered, and when there was nothing to send.
    checked: bool = True


@dataclass(frozen=True)
class WordOffer:
    """One word offered to the deck, and the proof it was offered (#408)."""

    word: str
    token: str


def _word_offers(user_id: int, words: tuple[str, ...]) -> tuple[WordOffer, ...]:
    from core import offer_tokens

    return tuple(
        WordOffer(word=w, token=offer_tokens.mint(OFFER_SURFACE, user_id, w)) for w in words
    )


#: The offer-token surface name. A `/write` token never verifies here.
OFFER_SURFACE = "talk"


def unknown_words_from(conn: Any, user_id: int, turns: list[Turn]) -> tuple[str, ...]:
    """§C2. The words the learner did not know, from their own typed turns.

    **`coverage_for` ALREADY COMPUTES EXACTLY THIS** and is free and offline —
    `unknown_lemmas` is the field, and W12a is the slice that made the
    instrument trustworthy.

    **VOICE TURNS ARE EXCLUDED, FOR THE SAME REASON THEY CANNOT SOURCE A
    JOURNAL ROW: a Whisper mishearing must not become a card.** A misheard word
    is not a word the learner did not know; it is a word they did not say.
    **THE CONSEQUENCE, STATED RATHER THAN LEFT AS AN IMPLIED PASS: a
    conversation held entirely by voice captures no words**, exactly as it
    writes no journal rows.

    **AND THE APP'S OWN TURNS ARE EXCLUDED**, which is a different point and
    matters more than it looks: the app's reply is coverage-CHECKED against this
    learner's ledger, so words the app used that they do not know are a defect
    in the reply, not a capture opportunity. Harvesting them would turn a
    failed coverage check into deck content.
    """
    typed = " ".join(t.content for t in turns if t.is_learner and not t.is_voice)
    if not typed.strip():
        return ()
    report = coverage_for(conn, user_id, typed)
    return capturable(report.unknown_lemmas)


def capturable(lemmas: Iterable[str]) -> tuple[str, ...]:
    """The subset of an unknown-word list that may be offered to the deck.

    ────────────────────────────────────────────────────────────────────────
    **#402. THE CLOSE-OUT OFFERED ELEVEN WORDS TO A LEARNER AND TEN OF THEM
    WERE NOT WORDS:** `weed, w, experinence, iwth, trakai, lithuania,
    togehter, grom, brade, drunck, fo`. Eight misspellings, two place names,
    one real word. **Tapping *Keep* on any of them writes it into `cards` as
    vocabulary and FSRS drills it for months** — CLAUDE.md §5, where a wrong
    row is permanent damage and a missing one is recoverable.

    **THE CAUSE IS NOT A BUG IN `compute_coverage`. IT IS THE RIGHT
    INSTRUMENT READ FOR THE WRONG QUESTION.** An unresolved token counts as
    unknown there **deliberately** — its own comment says *"Never guessed at.
    An unresolved token counts unknown, so the number reads low rather than
    falsely high"* — because a learner who cannot read a token genuinely does
    not follow that part of the text. **Coverage must over-report; capture
    must not.** §C2 took a list built to be pessimistic and offered it as a
    list of things worth keeping. So the fix belongs HERE, at the capture
    boundary, and `compute_coverage` is deliberately not touched: changing it
    would bias W12's comprehensible-input band high, which is the drowning
    direction.

    **TWO CONDITIONS, AND THE SECOND IS THE ONE THAT ANSWERS PROPER NOUNS.**

    1. **It must resolve against the reference lexicon** — `lemmatize` with an
       empty vocabulary, so the learner's own grown lexemes cannot vouch for a
       token. A string no dictionary contains is a typo, not vocabulary. This
       alone removes nine of the eleven.

    2. **Its lemma must carry a CEFR tag.** This is not belt-and-braces; **a
       lexicon check cannot answer proper nouns and the codebase already
       knows it.** `cefr_tagged_lemmas`'s docstring: *"john at rank 548,
       sarah at 1221, paris at 1107. None of them carries a CEFR tag;
       internet carries A1. 'Is this in the lexeme table' cannot tell a name
       from a word here, and 'does a vocabulary syllabus level it' can."*
       `trakai` and `lithuania` fall to condition 1 only by luck — they sit
       outside the 15k table — and `paris` would not. It also removes `fo`,
       which IS in the table and is not a word anybody means.

    **WHAT THIS DELIBERATELY DOES NOT DO: catch a typo that lands on another
    real word.** `weed` survives, and in conversation 7 it was a misspelling
    of `wedding` or `we'd`. **Nothing about the token is wrong**, so only
    context could tell — and context is a model call, which the standing
    2026-08-27 ruling forbids on a learner's tap. **Eleven offers become one,
    and the one is real English.** That bound is pinned by a test rather than
    left for a later reader to mistake for a defect.

    **ERRING TOWARD OFFERING TOO LITTLE IS THE SAFE DIRECTION**, and it is the
    same choice `Transcript.surfaceKey` records for the same reason: a missed
    offer is a word the learner can save from the transcript instead; a wrong
    one is a permanent row in the journal.
    """
    tagged = cefr_tagged_lemmas()
    kept: list[str] = []
    for word in lemmas:
        lemma = lemmatize(word, frozenset())
        if lemma is None or lemma not in tagged:
            continue
        if lemma not in kept:
            kept.append(lemma)
    return tuple(kept)


def save_conversation_word(
    user_id: int, word: str, now: datetime, *, token: str | None = None
) -> str:
    """Save one word from a conversation to the deck. **No model call.**

    **THE SLICE PROMPT NAMED `cards.save_captured_word` AND IT CANNOT BE
    REUSED — REPORTED RATHER THAN WORKED AROUND.** That function is
    video-bound: it takes a `video_id` and reads a pre-generated `video_glosses`
    row for the definition, register, neutral equivalent and who-says-this. **A
    conversation word has no gloss row and no video.**

    **AND GENERATING ONE HERE WOULD BREACH THE HALF OF THE 2026-08-27 RULING
    §0's AMENDMENT EXPLICITLY LEFT STANDING:** *the app does not generate
    material a learner will study without a gate.* **A card IS study material.**
    A turn is not, which is why the amendment reached one and not the other.

    **SO THE PATH REUSED IS W8f's, NOT W13-ii's**, and it is the right one: the
    vocabulary import creates cards with **no model call at all**, at
    `register='neutral'` / `register_source='import_default'` — the value
    migration 015 widened the CHECK for precisely so a word can enter the deck
    without one. The learner's own sentence is the context.

    **THE ONE-CARD-PER-LEMMA GUARANTEE IS NOT FREE HERE, AND THE FIRST DRAFT OF
    THIS DOCSTRING SAID IT WAS. CORRECTED ON THE INDEX DEFINITION, NOT ON
    MEMORY — §A's defect attempted a third time in one commit.**

    015's `cards_one_card_per_lemma` is
    `UNIQUE (user_id, lexeme_id, card_type) WHERE lexeme_id IS NOT NULL`, **so
    it does not reach a card whose `lexeme_id` is NULL** — and a word the
    learner did not know is very often outside the frequency list and therefore
    has no `lexemes` row at all. **The index protects precisely the words this
    feature does NOT capture.** Measured: two saves of *aardvark* produced two
    cards, ids 79322 and 79323, on the dev database.

    **SO THE PRE-CHECK IS EXPLICIT AND IS THE ACTUAL GUARANTEE**, on
    `(user_id, lower(front))` — the video path's own shape (`resolve_capture` 
    pre-checks by `(user_id, context_sentence, front)` for the same reason). A
    second save returns `"already"`, which is #178's *already saved* behaving
    politely rather than erroring. **The index still holds for the words that DO
    have a lexeme row, so both guards are live and neither is redundant.**

    **NO TRACK WEIGHTING IS ATTEMPTED, AND #374 IS WHY: `cards` HAS NO `track`
    COLUMN.** A weighting here would be invented rather than applied.

    Returns `"saved"` or `"already"`.
    """
    from core.services.cards import CardState, create_card
    from core.services.lexicon import lexeme_ids

    lemma = (word or "").strip().lower()
    if not lemma:
        raise ConversationError("empty word")
    # **#408, CLOSED W15: THE WORD MUST CARRY THE TOKEN ITS OFFER WAS SIGNED
    # WITH.** This accepted any 1–80 character string, so a client could write
    # anything into `cards` as vocabulary. The close-out now signs each word it
    # offers (`_word_offers`) and this refuses a word it did not sign — for this
    # learner, on this surface. Checked BEFORE any read or write.
    from core import offer_tokens

    if not offer_tokens.verify(OFFER_SURFACE, user_id, token, lemma):
        raise NotOffered("that word was not offered")
    with connection() as conn:
        row = _open_row(conn, user_id)
        ref = f"conversation:{row['id']}" if row else "conversation"
        # **`lexeme_ids`, READ FROM `lexicon.py` RATHER THAN GUESSED.** The
        # first draft called `lemma_id_for`, which does not exist — §A's defect
        # attempted a second time in the same commit, caught here by importing
        # before writing. A lemma outside the frequency list has no row, and
        # `lexeme_id` is nullable for exactly that case (013).
        lexeme_id = lexeme_ids(conn, [lemma]).get(lemma)

        # **THE ACTUAL DUPLICATE GUARD.** See the docstring: 015's partial
        # UNIQUE cannot see a NULL `lexeme_id`, which is most of what lands
        # here.
        seen = conn.execute(
            "SELECT 1 FROM cards WHERE user_id = %s AND lower(front) = %s LIMIT 1",
            (user_id, lemma),
        ).fetchone()
        if seen is not None:
            return "already"

        card_id = create_card(
            conn,
            user_id,
            card_type="recognition",
            front=lemma,
            back=lemma,
            register="neutral",
            register_source="import_default",
            # **The same `CardState` the capture path builds** -- a new card in
            # `learning` at step 0, due now, with no FSRS parameters yet.
            # 013's `cards_review_state_carries_both_parameters` CHECK is what
            # makes `learning` the only state that may carry NULLs.
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
            source_ref=ref,
            lexeme_id=lexeme_id,
            captured_at=now,
            source_title="conversation",
        )
        conn.commit()
    return "saved" if card_id is not None else "already"


def _valid_error_types(conn: Any) -> frozenset[str]:
    rows = conn.execute("SELECT code FROM error_types").fetchall()
    return frozenset(r["code"] for r in rows)


def _learner_labels(conn: Any) -> dict[str, str | None]:
    """`error_types.code → learner_label` for EVERY code, spoken ones as None.

    W15 puts the label on the close-out's correction card (`/write`'s `1k`
    anatomy), which W13b/4's close-out reported unmet for want of a field.
    """
    rows = conn.execute("SELECT code, learner_label FROM error_types").fetchall()
    return {str(r["code"]): r["learner_label"] for r in rows}


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
        if row["kind"] in RUNG_KINDS:
            return _close_rung(conn, user_id, learner, today, row, now)
        conversation_id = int(row["id"])
        turns = _history(conn, conversation_id)

        corrections: list[Correction] = []
        did_well = ""
        summary = ""
        talk_checked = True
        # **§C2 RUNS BEFORE THE DELETE, LIKE THE GUARDS, AND FOR THE SAME
        # REASON: it reads the turns.**
        unknown = unknown_words_from(conn, user_id, turns)
        if turns and any(t.is_learner for t in turns):
            close_template = _close_v3()
            system = build_system_prompt(
                close_template,
                cefr_level=learner["cefr_level"],
                native_language=learner["native_language"],
                error_type_list=", ".join(sorted(_valid_error_types(conn))),
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
                talk_checked = False
            finally:
                _record_llm(conn, user_id, today, usage_out)

            if isinstance(result, dict):
                did_well = str(result.get("did_well") or "").strip()
                summary = str(result.get("summary") or "").strip()
                corrections = apply_guards(
                    list(result.get("errors") or []),
                    turns,
                    _valid_error_types(conn),
                )
                labels = _learner_labels(conn)
                corrections = [
                    replace(c, label=labels.get(c.error_type)) for c in corrections
                ]

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
        # **§C3. The summary is written in the SAME transaction that deletes
        # the turns.** It is the app's own English about the conversation, not
        # the conversation by another name -- §O2 stands and the turns go.
        conn.execute(
            "UPDATE conversations SET closed_at = %s, summary = %s WHERE id = %s",
            (now, summary or None, conversation_id),
        )
        conn.commit()

    logger.info(
        "conversation closed user_id=%s shown=%s journaled=%s words=%s",
        user_id, len(corrections), journaled, len(unknown),
    )
    return CloseResult(
        conversation_id=conversation_id,
        corrections=corrections,
        did_well=did_well,
        unknown_words=unknown,
        summary=summary,
        journaled=journaled,
        word_offers=_word_offers(user_id, unknown),
        checked=talk_checked,
    )


# ── W33 (D): the retell's follow-up question ────────────────────────────────


def _followup_template() -> str:
    return (PROMPTS_DIR / "rung_retell_followup.txt").read_text(encoding="utf-8")


def retell_followup_request(cefr_level: str, transcript: str, turns: list[Turn]) -> dict[str, Any]:
    """**The whole request one follow-up sends, in one place** — the service and
    `core.rung_probe` both call it, so the probe prints what production sends.

    The transcript is DATA (CLAUDE.md §6, #292 part 1): it travels ONCE, fenced
    between `TRANSCRIPT_OPEN` and `TRANSCRIPT_CLOSE` at the head of the first
    user message — never in the system prompt, where `str.format` would read it.
    Every learner turn is `<user_text>`-fenced (`correction.wrap_user_text`); the
    app's earlier questions are the assistant's turns. **The opener is not sent**:
    it is a sentence a person wrote, and the first message must be the user's.
    """
    from core.services.correction import wrap_user_text

    after_opener = [t for t in turns if t.is_learner or t.seq > 0]
    messages: list[dict[str, str]] = []
    for t in after_opener:
        if t.is_learner:
            content = wrap_user_text(t.content)
            if not messages:
                cut = transcript.strip()[:RETELL_TRANSCRIPT_MAX_CHARS]
                content = f"{TRANSCRIPT_OPEN}\n{cut}\n{TRANSCRIPT_CLOSE}\n\n{content}"
            messages.append({"role": "user", "content": content})
        elif messages:
            messages.append({"role": "assistant", "content": t.content})
    system = build_system_prompt(
        _followup_template(),
        cefr_level=cefr_level,
        transcript_open=TRANSCRIPT_OPEN,
        transcript_close=TRANSCRIPT_CLOSE,
        max_words=FOLLOWUP_MAX_WORDS,
    )
    return {"messages": messages, "system": system, "max_tokens": FOLLOWUP_MAX_TOKENS}


def shape_followup(raw: Any) -> str | None:
    """The generated question if it survives, else ``None``. **Never repaired.**

    One line, one question, ending with `?`; at most `FOLLOWUP_MAX_WORDS` words
    and `FOLLOWUP_MAX_CHARS` characters; free of `BANNED` — **the COPY rule, not
    the content one**, because the question is the app speaking to the learner.
    **What it cannot establish (#271): that the question is about this video and
    worth answering.** The request carries only this video; the reading is
    W33-P1's.
    """
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split()).strip().strip('"').strip()
    if not text or len(text) > FOLLOWUP_MAX_CHARS or not text.endswith("?"):
        return None
    if text.count("?") != 1 or len(text.split()) > FOLLOWUP_MAX_WORDS:
        return None
    if BANNED.search(text):
        return None
    return text


def _retell_followup(
    conn: Any, user_id: int, today: date, cefr_level: str, transcript: str | None,
    turns: list[Turn], turn_number: int,
) -> tuple[str, bool]:
    """One follow-up: ``(question, generated)``. **Never raises; never silent.**

    No transcript (purged mid-retell, #335) → a written question and no call.
    A provider failure, or a reply the gate refuses → a written question. The
    call's usage is recorded either way (#321: a billed call is counted).
    """
    fallback = RETELL_FALLBACK_QUESTIONS[(turn_number - 1) % len(RETELL_FALLBACK_QUESTIONS)]
    if not transcript:
        return fallback, False
    request = retell_followup_request(cefr_level, transcript, turns)
    usage_out: dict = {}
    try:
        raw = llm.chat(request.pop("messages"), **request, usage_out=usage_out)
    except Exception:  # noqa: BLE001 -- keep the learner's turn and the talk going
        logger.warning("conversation retell followup failed user_id=%s", user_id)
        raw = None
    finally:
        _record_llm(conn, user_id, today, usage_out)
    question = shape_followup(raw)
    # Counts only — never the question, never the learner's words (§5).
    logger.info(
        "conversation retell followup user_id=%s turn=%s generated=%s",
        user_id, turn_number, question is not None,
    )
    return (question, True) if question else (fallback, False)


# ── W15: the rung close ─────────────────────────────────────────────────────


def _rung_template(kind: str) -> str:
    return (PROMPTS_DIR / f"rung_{kind}.txt").read_text(encoding="utf-8")


def build_rung_system_prompt(
    user: Any, kind: str, *, task: str, can_do: str, type_list: str
) -> str:
    """The rung's close prompt for this learner. **Read fresh each call.**

    The learner's language goes in by NAME and an unmapped code raises (F5,
    W16a's `rules.language_name`); the explanation-language clause is the one
    `/write` and the bot share (`correction.explanation_language_rule`), formatted
    from a copy of the user carrying the name. `type_list` is F6's one list
    (`writing.written_type_list`): the codes offered are the codes the gates
    accept. **No learner text and no transcript reaches `str.format`** — both
    travel in the user message.
    """
    import dataclasses

    from core.services import correction
    from core.writing import rules

    named = dataclasses.replace(user, native_language=rules.language_name(user.native_language))
    fields: dict[str, Any] = {
        "cefr_level": user.cefr_level,
        "native_language": named.native_language,
        "error_type_list": type_list,
        "explanation_language_rule": correction.explanation_language_rule(named),
        "max_corrections": RUNG_MAX_CORRECTIONS,
    }
    if kind == "answer":
        fields.update(task=task, can_do=can_do)
    else:
        fields.update(
            max_points=RUNG_MAX_POINTS,
            transcript_open=TRANSCRIPT_OPEN,
            transcript_close=TRANSCRIPT_CLOSE,
        )
    return build_system_prompt(_rung_template(kind), **fields)


def rung_request(
    user: Any, kind: str, *, task: str, can_do: str, type_list: str,
    learner_text: str, transcript: str | None,
) -> dict[str, Any]:
    """**The whole request a rung's close sends, in one place** — the service and
    `core.rung_probe` both call this, so the probe prints what production sends.
    """
    return {
        "messages": [
            {"role": "user", "content": build_rung_user_message(kind, learner_text, transcript)}
        ],
        "system": build_rung_system_prompt(
            user, kind, task=task, can_do=can_do, type_list=type_list
        ),
        "json_mode": True,
        "max_tokens": RUNG_MAX_TOKENS,
        "reject_truncation": True,
    }


def rung_type_list() -> str:
    """F6's code list on a connection of its own, for `core.rung_probe` (which
    may hold no SQL, CLAUDE.md §2)."""
    from core.services import writing as writing_service

    with connection() as conn:
        return writing_service.written_type_list(conn)


def shape_rung(raw: Any, kind: str, submitted: str) -> tuple[Any, tuple[str, ...], tuple[str, ...]]:
    """The gates over one response: `/write`'s `shape`, then the points on a retell.

    Shared by `_close_rung` and the probe for the reason `rung_request` is.
    """
    from core.services import writing as writing_service
    from core.writing import gates

    shaped = gates.shape(raw, submitted, limit=RUNG_MAX_CORRECTIONS, labels=writing_service.labels())
    covered: tuple[str, ...] = ()
    also: tuple[str, ...] = ()
    if kind == "retell" and shaped.is_english:
        covered, also = _points(raw.get("points"))
    return shaped, covered, also


def build_rung_user_message(kind: str, learner_text: str, transcript: str | None) -> str:
    """The one user message. **Two fenced blocks for a retell, one for an answer.**

    The learner's text in `<user_text>` (`correction.wrap_user_text`, the fence
    every correcting prompt uses). The transcript between `TRANSCRIPT_OPEN` and
    `TRANSCRIPT_CLOSE`, cut at `RETELL_TRANSCRIPT_MAX_CHARS`: scraped text is
    DATA (CLAUDE.md §6, #292 part 1) and enters as one delimited block, never as
    a system-prompt field.
    """
    from core.services.correction import wrap_user_text

    fenced = wrap_user_text(learner_text)
    if kind != "retell" or not transcript:
        return fenced
    cut = transcript.strip()[:RETELL_TRANSCRIPT_MAX_CHARS]
    return f"{TRANSCRIPT_OPEN}\n{cut}\n{TRANSCRIPT_CLOSE}\n\n{fenced}"


def _points(raw: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The retell's points, gated. **Covered first, then the rest; never a count.**

    Each point is English a learner reads, so it takes `content_offenders` (the
    content rule, not the copy rule — a video may be about something that
    *failed*). A point that is not a non-empty string, runs past 200 characters,
    or trips the scan is DROPPED, not repaired. At most `RUNG_MAX_POINTS` survive.
    """
    covered: list[str] = []
    also: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if len(covered) + len(also) >= RUNG_MAX_POINTS:
            break
        if not isinstance(item, dict):
            continue
        point = str(item.get("point") or "").strip()
        if not point or len(point) > 200 or content_offenders(point):
            continue
        (covered if item.get("covered") is True else also).append(point)
    return tuple(covered), tuple(also)


def _close_rung(
    conn: Any, user_id: int, learner: dict, today: date, row: dict, now: datetime
) -> CloseResult:
    """Close an answer or a retell: one call, the gates, the journal, the delete.

    **THE GATES ARE `/write`'s, NOT THE CONVERSATION'S, AND THAT IS THE RUN
    PROMPT'S *G1 AND G2 APPLY*.** `core.writing.gates.shape` runs G1 (the
    original is a substring of what the learner said — self-produced), G2 (a
    changed token that is not an English word is a typo, never journaled), the
    code check against F6's one list, the explanation's content scan, the
    opening-line gate and the two-correction cap, in that order and in one place.

    **AND THE CONVERSATION'S G3 IS KEPT ON TOP: a voice turn is SHOWN, never
    JOURNALED.** `answer` and `retell` sit in `HARVESTED_SOURCES` as
    *keyboard-authored* (012's classification), so journaling a Whisper
    transcript under either would promote a mishearing into the ledger through
    a value the tree calls typed. A correction is written only if its original
    appears in a TYPED turn.

    **The order is W13b's and for its reason:** the turns are read, the call is
    made, the gates run, the journal is written, and only then are the turns
    deleted. A provider failure releases the learner (S26a): the turns still go.
    """
    from core.services import writing as writing_service
    from core.writing import gates

    kind = str(row["kind"])
    conversation_id = int(row["id"])
    turns = _history(conn, conversation_id)
    said = [t for t in turns if t.is_learner]
    submitted = "\n\n".join(t.content for t in said)
    typed = "\n\n".join(t.content for t in said if not t.is_voice)

    corrections: list[Correction] = []
    did_well = ""
    is_english = True
    covered: tuple[str, ...] = ()
    also: tuple[str, ...] = ()
    journaled = 0
    unknown = unknown_words_from(conn, user_id, turns)
    checked = True

    if said:
        # The opener IS the task: reading it back from the app's first turn keeps
        # the prompt on what the learner was shown, even if the unit moved on
        # between opening and closing.
        opener = turns[0].content if turns and not turns[0].is_learner else ""
        transcript = _transcript_of(conn, row.get("video_id")) if kind == "retell" else None
        # A retell whose transcript was purged between opening and closing
        # (#335) is still the learner's English: it is corrected as an answer to
        # its opener, and no points are drawn from a transcript that is gone.
        prompt_kind = "retell" if transcript else "answer"
        from core.services.users import get_user

        user = get_user(user_id)
        if user is None:
            raise NoConversation("no such learner")
        request = rung_request(
            user, prompt_kind, task=opener,
            can_do=str(row["topic_label"]) if kind == "answer" else RETELL_GOAL,
            type_list=writing_service.written_type_list(conn),
            learner_text=submitted, transcript=transcript,
        )
        usage_out: dict = {}
        raw: Any = {}
        try:
            raw = llm.chat(request.pop("messages"), **request, usage_out=usage_out)
        except Exception:  # noqa: BLE001 -- release the learner (S26a)
            logger.warning("conversation rung close failed user_id=%s kind=%s", user_id, kind)
            raw = {}
        finally:
            _record_llm(conn, user_id, today, usage_out)

        # #493: an empty or unusable answer read NOTHING, so it is not a clean
        # retelling and the screen must not call it one.
        checked = isinstance(raw, dict) and bool(raw)
        if isinstance(raw, dict) and raw:
            shaped, covered, also = shape_rung(raw, prompt_kind, submitted)
            is_english = shaped.is_english
            did_well = shaped.did_well or ""
            for c in shaped.corrections:
                spoken_only = not gates.is_self_produced(c["you_said"], typed)
                corrections.append(Correction(
                    you_said=c["you_said"],
                    correct_form=c["correct_form"],
                    error_type=c["error_type"],
                    explanation=c["explanation"],
                    journalable=not spoken_only,
                    withheld_reason="voice_turn" if spoken_only else None,
                    label=c.get("label"),
                ))
            if shaped.dropped:
                logger.info(
                    "conversation rung gates dropped user_id=%s kind=%s reasons=%s",
                    user_id, kind,
                    ",".join(f"{k}:{v}" for k, v in sorted(shaped.dropped.items())),
                )

    writable = [c for c in corrections if c.journalable]
    if writable:
        journaled = record_errors(
            user_id,
            kind,  # 'answer' | 'retell' -- 012's CHECK has admitted both since W5
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

    conn.execute(
        "DELETE FROM conversation_turns WHERE conversation_id = %s", (conversation_id,)
    )
    conn.execute(
        "UPDATE conversations SET closed_at = %s WHERE id = %s", (now, conversation_id)
    )
    conn.commit()
    logger.info(
        "conversation rung closed user_id=%s kind=%s shown=%s journaled=%s points=%s",
        user_id, kind, len(corrections), journaled, len(covered) + len(also),
    )
    return CloseResult(
        conversation_id=conversation_id,
        corrections=corrections,
        did_well=did_well,
        unknown_words=unknown,
        summary="",
        journaled=journaled,
        word_offers=_word_offers(user_id, unknown),
        is_english=is_english,
        covered=covered,
        also=also,
        kind=kind,
        checked=checked,
    )


def _transcript_of(conn: Any, video_id: int | None) -> str | None:
    """The retell's transcript, read at close. None if purged or never there."""
    if video_id is None:
        return None
    found = conn.execute(
        "SELECT transcript FROM videos WHERE id = %s", (video_id,)
    ).fetchone()
    text = (found or {}).get("transcript") if found else None
    return str(text) if text and str(text).strip() else None
