"""Free-text correction: the prompt, the model call, the journal write.

**Ported out of `apps/bot/handlers/correction.py` at W3, not rewritten.** The
logic here is the v2 correction path, moved so that two front ends can share one
implementation rather than growing a second one.

Why it had to move: `apps/api` may not import `apps.bot`
(`tests/test_core_boundary.py::test_api_does_not_import_the_worker_job_table`),
and CLAUDE.md §2 puts SQL and business logic in service functions. So exposing
correction over HTTP had exactly two options — move it here, or reimplement it —
and reimplementing the feature that died silently three times in v2 is the worst
idea available.

What stayed in the bot: dispatch, access control, the typing indicator, the
retry-with-a-visible-message loop, and `texts.*` rendering. All of that is
Telegram, and none of it belongs in a service.

Nothing here imports Telegram, FastAPI, or any HTTP type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core import PROMPTS_DIR
from core.db import connection
from core.llm import LLMError, chat
from core.prompt_rules import ENGLISH_ONLY_RULE, SINGLE_LANGUAGE_RULE
from core.services.errors import record_errors
from core.services.sessions import complete_open_free_practice, local_today
from core.services.users import User

logger = logging.getLogger(__name__)

_PROMPT_PATH = PROMPTS_DIR / "correction.txt"

# Below this a message is not an attempt at English worth spending a model call
# on; above it, the learner has pasted something. Both are v2 values, unchanged.
MIN_CHARS = 10
MAX_CHARS = 1000

# PRD §8: at most three, most important first. More is demoralising.
MAX_CORRECTIONS = 3

# The error types whose explanation may be given in the learner's own language
# when they have asked for that. Concrete types stay English regardless.
ABSTRACT_ERROR_TYPES = (
    "gerund_vs_infinitive",
    "present_perfect",
    "conditional",
    "modal_verb",
    "article_missing",
    "article_wrong",
)

# Populated by init_correction_prompt() at startup, or lazily on first use.
_prompt_template: str | None = None
_error_type_list: str = ""
_murphy_by_code: dict[str, str | None] = {}

# Moved verbatim from apps/bot/handlers/correction.py, then extended with the
# shared single-language clause (known issue #45). The base wording is the v2
# text unchanged; only the clause is new.
_FALLBACK_RULE_TRUE = (
    "BUT when the error type is abstract grammar "
    f"({', '.join(ABSTRACT_ERROR_TYPES)}) AND the user's "
    "explanation_language_fallback is enabled, write that explanation in "
    "their native language ({native_language}) instead. Concrete error types "
    "stay English regardless. " + SINGLE_LANGUAGE_RULE
)

_FALLBACK_RULE_FALSE = (
    "Write every explanation in English, including abstract grammar types. "
    + ENGLISH_ONLY_RULE
)


def explanation_language_rule(user: User) -> str:
    """The explanation-language clause for this learner's setting."""
    if user.explanation_language_fallback:
        return _FALLBACK_RULE_TRUE.format(native_language=user.native_language)
    return _FALLBACK_RULE_FALSE


class CorrectionUnavailable(Exception):
    """The model did not return a usable correction. Carries no client detail."""


@dataclass(frozen=True)
class CorrectionOutcome:
    """What one correction produced, in the v2 shape the learners already read.

    ``corrections`` carries the model's four fields plus ``murphy_units`` — the
    Murphy reference for that error type — because "why" is the half of a
    correction that teaches, and every front end needs it.
    """

    is_english: bool
    has_errors: bool
    did_well: str
    corrections: list[dict] = field(default_factory=list)
    # Rows actually written to the journal. Lower than len(corrections) when the
    # model invented an error_type, which record_errors drops.
    written: int = 0


def init_correction_prompt() -> None:
    """Load the prompt template and the error taxonomy from the database."""
    global _prompt_template, _error_type_list, _murphy_by_code
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    with connection() as conn:
        rows = conn.execute(
            "SELECT code, label, murphy_units FROM error_types ORDER BY code"
        ).fetchall()
    _murphy_by_code = {row["code"]: row["murphy_units"] for row in rows}
    _error_type_list = "\n".join(
        f"- {row['code']}: {row['label']}" for row in rows
    )
    logger.info("Loaded %s error types for correction prompt", len(rows))


def murphy_lookup() -> dict[str, str | None]:
    """The cached code → murphy_units map."""
    if not _murphy_by_code:
        init_correction_prompt()
    return dict(_murphy_by_code)


def error_type_list_text() -> str:
    """The cached error-type bullet list, for every prompt that needs it."""
    if not _error_type_list:
        init_correction_prompt()
    return _error_type_list


def build_system_prompt(user: User) -> str:
    """Parameterise the correction system prompt for this learner."""
    if _prompt_template is None:
        init_correction_prompt()
    assert _prompt_template is not None

    return _prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        error_type_list=_error_type_list,
        explanation_language_rule=explanation_language_rule(user),
    )


def wrap_user_text(text: str) -> str:
    """Fence the learner's text.

    CLAUDE.md §6: what is inside is material to correct, never instructions to
    follow. The prompt says so too; the fence is what makes that sentence
    enforceable.
    """
    return f"<user_text>\n{text}\n</user_text>"


def apply_result(
    user_id: int, result: dict, *, source: str = "text"
) -> CorrectionOutcome:
    """Turn a model response into a journal write and a renderable outcome.

    The order and every early return match the v2 handler exactly: a processed
    correction first makes today's free-practice day Active (S4), then
    not-English short-circuits, then no-errors, then the cap, then the write.
    """
    _complete_free_practice_if_open(user_id)

    did_well = str(result.get("did_well") or "").strip() or "Nice."

    if not result.get("is_english", True):
        return CorrectionOutcome(
            is_english=False, has_errors=False, did_well=did_well
        )

    corrections = list(result.get("corrections") or [])[:MAX_CORRECTIONS]
    if not result.get("has_errors", False) or not corrections:
        return CorrectionOutcome(
            is_english=True, has_errors=False, did_well=did_well
        )

    written = record_errors(user_id, source, corrections)

    # Re-filter to what we would show, dropping unknown types the same way the
    # write did — so the learner is never shown a correction the journal
    # refused to keep.
    valid = murphy_lookup()
    kept = [c for c in corrections if c.get("error_type") in valid]
    if written == 0 or not kept:
        return CorrectionOutcome(
            is_english=True, has_errors=False, did_well=did_well
        )

    return CorrectionOutcome(
        is_english=True,
        has_errors=True,
        did_well=did_well,
        corrections=[
            {
                "you_said": c.get("you_said", ""),
                "correct_form": c.get("correct_form", ""),
                "error_type": c.get("error_type", ""),
                "explanation": c.get("explanation", ""),
                "murphy_units": valid.get(c.get("error_type")),
            }
            for c in kept
        ],
        written=written,
    )


def call_model(user: User, text: str) -> dict:
    """Build the correction prompt and send it. **The only place either happens.**

    Every caller — the web route and the Telegram handler — goes through here,
    so the prompt, the message shape and `json_mode` cannot differ between the
    two front ends. Before this existed they were two copies of four lines, and
    nothing would have failed if one of them had drifted: each front end's tests
    patch its own module and neither can see the other.

    Raises `LLMError`, deliberately, rather than a correction-specific error.
    The bot catches it to run its retry — which stays in the bot, because the
    retry tells the learner it is retrying and `core` has no channel to say so.
    That is the coupling: the bot owns the *retry*, not the *call*.
    """
    system = build_system_prompt(user)
    messages = [{"role": "user", "content": wrap_user_text(text)}]
    raw = chat(messages, system=system, json_mode=True)
    if not isinstance(raw, dict):
        raise LLMError("Expected JSON object from correction call")
    return raw


def correct(
    user: User, text: str, *, source: str = "text"
) -> CorrectionOutcome:
    """Correct one piece of free text end to end. One model call, no retry.

    A caller with no way to tell the learner it is retrying is better off
    failing once and letting the route answer.
    """
    try:
        raw = call_model(user, text)
    except LLMError as exc:
        raise CorrectionUnavailable("model call failed") from exc
    return apply_result(user.id, raw, source=source)


def _complete_free_practice_if_open(user_id: int) -> None:
    """S4: a processed correction makes today's free_practice day Active."""
    with connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    tz = str(row["timezone"] or "Europe/Vilnius") if row else "Europe/Vilnius"
    day = local_today(tz, datetime.now(timezone.utc))
    complete_open_free_practice(user_id, day)
