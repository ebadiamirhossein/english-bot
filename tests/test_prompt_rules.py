"""W3: the single-language / no-transliteration rule reaches every explanation prompt.

**W22: three paths, down from seven.** ``diary``, ``voice``, ``capture`` and
``conversation_close`` were the Telegram handlers' own prompt builders and were
deleted with them; what remains is the web's correction and writing prompts.
The two pins on those handlers' wording (S26c's close-out, capture's word cap)
went with the handlers they pinned.

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

from core import PROMPTS_DIR

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
    from core.services import correction, writing

    PROMPT_BUILDERS.update(
        {
            "correction": correction.build_system_prompt,
            # W16a. The web journal's own prompt. It shares the clause through
            # `correction.explanation_language_rule`, and this entry is what
            # proves it reaches the rendered text rather than the constant.
            "writing_correction": lambda user: writing.build_system_prompt(
                user, "journal"
            ),
            # W16b. The paragraph's own template, with a unit task.
            "writing_paragraph": lambda user: writing.build_system_prompt(
                user, "paragraph", "Write six sentences about yesterday."
            ),
        }
    )


def _learner(*, fallback: bool, native: str = "fa") -> User:
    from datetime import time

    return User(
        id=7222549221,
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


def test_all_three_paths_are_covered() -> None:
    """A guard for everything below: a shrinking dict passes every check."""
    assert set(PROMPT_BUILDERS) == {
        "correction",
        "writing_correction",
        "writing_paragraph",
    }


@pytest.mark.parametrize(
    "name",
    ["correction", "writing_correction", "writing_paragraph"],
)
def test_the_rule_reaches_the_rendered_prompt_when_fallback_is_on(name) -> None:
    """The learner has asked for explanations in their own language.

    This is the case #45 is about: without the rule the model mixes languages
    and writes Farsi in Latin letters, which is unreadable to someone who reads
    the script.
    """
    prompt = PROMPT_BUILDERS[name](_learner(fallback=True))
    # W16a F5: the writing prompt names the language ("Farsi") instead of
    # sending the column value; the five v2-era paths still format the code.
    native = "Farsi" if name.startswith("writing_") else "fa"
    expected = single_language_clause(fallback_enabled=True, native_language=native)
    assert expected in prompt, f"{name} does not carry the single-language rule"
    assert "never Latin transliteration" in prompt
    assert "ONE language only" in prompt


@pytest.mark.parametrize(
    "name",
    ["correction", "writing_correction", "writing_paragraph"],
)
def test_the_rule_reaches_the_rendered_prompt_when_fallback_is_off(name) -> None:
    """Explanations stay English. The remaining failure is drifting into the
    learner's language unasked, so the shorter clause still has to be there."""
    prompt = PROMPT_BUILDERS[name](_learner(fallback=False))
    assert ENGLISH_ONLY_RULE in prompt, f"{name} lacks the English-only clause"


@pytest.mark.parametrize(
    "name",
    ["correction", "writing_correction", "writing_paragraph"],
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


def test_the_no_inline_cue_rule_survived() -> None:
    """**The rule is the whole fix for P1's two rejections, so deleting it must
    fail rather than pass quietly.**

    Same instrument and same reason as the S26c and capture wording pins (both
    deleted at W22 with the handlers they pinned): a prompt rule with no
    check behind it is a convention, and this one was added because the prompt
    did **not** forbid the shape the judge rejected — the generator broke no rule
    it had.

    **This asserts the rule is PRESENT, and can never assert the model OBEYS
    it.** That is a live measurement on the next billed run, and the distinction
    is W5a's three-level lesson: a recorded-response test proves a branch is
    reachable and never that a model takes it.
    """
    text = (PROMPTS_DIR / "item_generate.txt").read_text(encoding="utf-8")
    assert "NEVER WRITE A CUE INTO THE SENTENCE" in text
    # The two rejected items, quoted in the prompt so the shape is unmistakable.
    assert "We ___ to the beach yesterday. (drive)" in text
    assert "I ___ to work when it started to rain. (walk)" in text
    # The reason must stay the cue-accounting one, not the aesthetic one.
    assert "cue_type" in text and "repair ladder" in text


def test_the_error_spot_prompt_convention_is_stated_to_the_generator() -> None:
    """**#271: the convention existed, the renderer implemented it, and it was
    written down nowhere the generator could read.**

    Stated in BOTH places a generator sees — the prompt template and the derived
    per-type contract block — because the item that reached a learner obeyed
    neither, and a rule in only one of them is a rule half the pipeline has.
    """
    from core.items.schema import constraint_block

    text = (PROMPTS_DIR / "item_generate.txt").read_text(encoding="utf-8")
    assert "`prompt_text` IS THE INSTRUCTION AND NEVER THE SENTENCE" in text

    contract = constraint_block(("error_spot",))
    assert "prompt_text is the INSTRUCTION and never the sentence" in contract
