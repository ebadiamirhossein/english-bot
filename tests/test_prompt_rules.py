"""W3: the single-language / no-transliteration rule reaches all five prompts.

**Known issue #45.** S26c fixed this for the conversation close-out by writing
the rule inline, and left the other four explanation paths without it — so the
same learner could get a Farsi explanation in Latin letters from `/diary` and a
correct one from `/talk` on the same day.

These tests assert the rendered system prompt, not the constant. A constant that
exists but never reaches `.format()` fixes nothing, and that is the failure mode
worth catching: every check below builds the real prompt for a real learner
shape and looks for the rule in the text the model would receive.
"""

from __future__ import annotations

import pytest

from core.prompt_rules import (
    ENGLISH_ONLY_RULE,
    SINGLE_LANGUAGE_RULE,
    single_language_clause,
)
from core.services.users import User

# The five paths #45 names. Each entry builds the system prompt the model is
# actually sent for that feature.
PROMPT_BUILDERS = {}


def _register() -> None:
    from apps.bot.handlers import capture, conversation, diary, voice
    from core.services import correction

    PROMPT_BUILDERS.update(
        {
            "correction": correction.build_system_prompt,
            "diary": diary.build_diary_system_prompt,
            # voice's builder also decides whether this is the closing turn;
            # the explanation rule is the same either way.
            "voice": lambda user: voice.build_voice_system_prompt(
                user, final_turn=True
            ),
            "capture": capture.build_system_prompt,
            "conversation_close": conversation.build_conversation_close_prompt,
        }
    )


def _learner(*, fallback: bool, native: str = "fa") -> User:
    from datetime import time

    return User(
        telegram_user_id=7222549221,
        name="Test",
        native_language=native,
        cefr_level="B1",
        explanation_language_fallback=fallback,
        efset_baseline=None,
        work_domain="general",
        why_statement=None,
        track_weights={"life": 50, "curiosity": 30, "work": 20},
        morning_time=time(8, 0),
        evening_time=time(21, 0),
        onboarded=True,
    )


@pytest.fixture(autouse=True)
def builders():
    if not PROMPT_BUILDERS:
        _register()


def test_all_five_paths_are_covered() -> None:
    """A guard for everything below: a shrinking dict passes every check."""
    assert set(PROMPT_BUILDERS) == {
        "correction",
        "diary",
        "voice",
        "capture",
        "conversation_close",
    }


@pytest.mark.parametrize(
    "name",
    ["correction", "diary", "voice", "capture", "conversation_close"],
)
def test_the_rule_reaches_the_rendered_prompt_when_fallback_is_on(name) -> None:
    """The learner has asked for explanations in their own language.

    This is the case #45 is about: without the rule the model mixes languages
    and writes Farsi in Latin letters, which is unreadable to someone who reads
    the script.
    """
    prompt = PROMPT_BUILDERS[name](_learner(fallback=True))
    expected = single_language_clause(fallback_enabled=True, native_language="fa")
    assert expected in prompt, f"{name} does not carry the single-language rule"
    assert "never Latin transliteration" in prompt
    assert "ONE language only" in prompt


@pytest.mark.parametrize(
    "name",
    ["correction", "diary", "voice", "capture", "conversation_close"],
)
def test_the_rule_reaches_the_rendered_prompt_when_fallback_is_off(name) -> None:
    """Explanations stay English. The remaining failure is drifting into the
    learner's language unasked, so the shorter clause still has to be there."""
    prompt = PROMPT_BUILDERS[name](_learner(fallback=False))
    assert ENGLISH_ONLY_RULE in prompt, f"{name} lacks the English-only clause"


@pytest.mark.parametrize(
    "name",
    ["correction", "diary", "voice", "capture", "conversation_close"],
)
def test_the_native_language_placeholder_is_filled(name) -> None:
    """An unfilled `{native_language}` would ship a literal brace to the model.

    Cheap to introduce — the clause carries the placeholder — and invisible
    without a rendered-prompt assertion.
    """
    prompt = PROMPT_BUILDERS[name](_learner(fallback=True, native="lt"))
    assert "{native_language}" not in prompt
    assert "lt" in prompt


def test_the_two_learners_get_their_own_language_named(  ) -> None:
    """PRD §2.5: two learners, two L1s, one taxonomy. The rule names whichever
    language belongs to the learner it was built for."""
    farsi = PROMPT_BUILDERS["correction"](_learner(fallback=True, native="fa"))
    lith = PROMPT_BUILDERS["correction"](_learner(fallback=True, native="lt"))
    assert "fa" in farsi and "lt" not in farsi.split("Standard English")[0][-200:]
    assert "lt" in lith


def test_the_clause_is_defined_once() -> None:
    """The point of #45's fix. Five copies drift; one does not.

    Asserted structurally: no handler and no service may re-state the wording
    that `core.prompt_rules` owns.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    owner = repo / "packages" / "core" / "prompt_rules.py"
    offenders: list[str] = []
    for path in sorted((repo / "apps").rglob("*.py")) + sorted(
        (repo / "packages" / "core").rglob("*.py")
    ):
        if path == owner or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "never Latin transliteration" in node.value:
                    offenders.append(f"{path.relative_to(repo)}:{node.lineno}")
    assert offenders == [], (
        "the single-language rule belongs to core/prompt_rules.py alone: "
        + "; ".join(offenders)
    )


def test_the_conversation_close_wording_did_not_change() -> None:
    """S26c's text, pinned.

    `conversation_close` already had the rule inline and was already correct.
    W3 replaced that inline text with the shared constant, which must be a pure
    refactor — a template that was correct and is now *differently* correct
    would be an accidental behaviour change on a live feature.
    """
    from apps.bot.handlers import conversation

    assert conversation._FALLBACK_RULE_TRUE.endswith(SINGLE_LANGUAGE_RULE)
    assert conversation._FALLBACK_RULE_FALSE.endswith(ENGLISH_ONLY_RULE)
    assert conversation._FALLBACK_RULE_TRUE.startswith(
        "BUT when the error type is abstract grammar"
    )


def test_captures_own_wording_survived() -> None:
    """capture's rule is bespoke — glosses and a 25-word cap, not error types.

    W3 appended the shared clause rather than replacing capture's wording. If a
    later change swaps the whole rule for the shared one, capture silently
    loses its word cap, which is the kind of prompt regression that shows up as
    "the app got chattier" and is never traced back.
    """
    from apps.bot.handlers import capture

    assert "max 25 words" in capture._FALLBACK_RULE_TRUE
    assert "gloss" in capture._FALLBACK_RULE_TRUE
    assert capture._FALLBACK_RULE_TRUE.endswith(SINGLE_LANGUAGE_RULE)
