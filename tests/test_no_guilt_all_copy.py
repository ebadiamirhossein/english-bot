"""W19 / #46: ONE no-guilt test over every copy module, not eight per-slice lists.

#46: the banned-phrase checks were eight per-slice tests over hand-maintained
lists or name-prefix filters, so any string matching no prefix and named in no
list was unchecked — `apps/bot/texts.py` holds 411 constants. This walks EVERY
public string (and every string inside a public list or tuple) of each copy
module, with the one pattern `core.copy_rules.BANNED`.

**THE FRONTEND half already walks every shipped source file**
(`tests/test_web_shell.py::test_no_guilt_copy_anywhere_in_the_frontend`, over
`app/`, `components/`, `lib/`); W19 pins its own surface into that walk there.

**THE BOT HAS FIFTEEN EXISTING HITS AND THEY ARE FROZEN, NOT FIXED.** Fixing
them is an edit to `apps/bot/texts.py`, and the build run keeps the bot path
byte-identical until W22 — which deletes the file. So they are a BASELINE:
**a new offender fails this test, and so does a baseline entry that stops
offending** (the list may only shrink, and it must shrink in the same commit
that fixes one). Most are the bot blaming itself (*"something broke"*), which
the pattern cannot tell apart from blaming the learner; three are live
learner-facing marks (`❌` twice and a *wrong word* instruction) — see #46's row.

**RED DEMONSTRATIONS (2026-09-25):** `test_no_copy_module_gains_a_banned_phrase`
went red with `core.copy.SUNDAY_LEAD_KEEPING` temporarily edited to end
*"…you missed a day."* (`core.copy.SUNDAY_LEAD_KEEPING` reported); removing one baseline name (`LLM_FAILED`) turns the same test red;
`test_the_bot_baseline_only_shrinks` went red with a clean name
(`QUIZ_DONE`) added to `BOT_BASELINE`.
"""

from __future__ import annotations

import importlib

from core.copy_rules import BANNED, offenders

#: Every module whose constants are learner-facing copy.
COPY_MODULES = ("apps.bot.texts", "core.copy")

#: `apps/bot/texts.py`'s offenders on 2026-09-25, frozen until W22 deletes the
#: file. Names only; `offenders()` reports the matched term beside each.
BOT_BASELINE = frozenset(
    {
        "apps.bot.texts.ANKI_SEND_FAILED",
        "apps.bot.texts.BOOK_PROCESS_FAILED",
        "apps.bot.texts.CAPTURE_FAILED",
        "apps.bot.texts.GUIDE_SECTION_ANKI_WEEK",
        "apps.bot.texts.IMPORT_FAILED_HEADERS",
        "apps.bot.texts.INTERESTS_SAVE_FAILED",
        "apps.bot.texts.LLM_FAILED",
        "apps.bot.texts.ONBOARD_SAVE_FAILED",
        "apps.bot.texts.OPERATOR_CSV_VOCAB_LLM_FAILED",
        "apps.bot.texts.PREP_FAILED",
        "apps.bot.texts.QUIZ_HINT_SPOT",
        "apps.bot.texts.QUIZ_SPOT_PROMPT",
        "apps.bot.texts.QUIZ_YOU_SAID",
        "apps.bot.texts.READING_WRONG",
        "apps.bot.texts.SOFT_UNHANDLED",
    }
)


def _strings(module_name: str) -> dict[str, str]:
    module = importlib.import_module(module_name)
    found: dict[str, str] = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if isinstance(value, str):
            found[f"{module_name}.{name}"] = value
        elif isinstance(value, (list, tuple, frozenset, set)):
            for i, item in enumerate(sorted(value) if isinstance(value, (set, frozenset)) else value):
                if isinstance(item, str):
                    found[f"{module_name}.{name}[{i}]"] = item
    return found


def _offending_names() -> set[str]:
    hits: set[str] = set()
    for module_name in COPY_MODULES:
        for report in offenders(_strings(module_name), BANNED):
            hits.add(report.split(":", 1)[0].split("[", 1)[0])
    return hits


def test_every_copy_module_is_walked() -> None:
    """Positive control: the walk reaches the modules' real size, so a green
    result is not a walk over nothing."""
    assert len(_strings("apps.bot.texts")) > 400
    assert len(_strings("core.copy")) > 40


def test_no_copy_module_gains_a_banned_phrase() -> None:
    new = sorted(_offending_names() - BOT_BASELINE)
    assert new == [], "a banned phrase reached copy (CLAUDE.md §4): " + ", ".join(new)


def test_the_bot_baseline_only_shrinks() -> None:
    """A baseline entry that no longer offends must leave the list in the same
    commit, or the baseline stops describing anything."""
    stale = sorted(BOT_BASELINE - _offending_names())
    assert stale == [], "no longer offending — remove from BOT_BASELINE: " + ", ".join(stale)
