"""W19 / #46: ONE no-guilt test over every copy module, not eight per-slice lists.

#46: the banned-phrase checks were eight per-slice tests over hand-maintained
lists or name-prefix filters, so any string matching no prefix and named in no
list was unchecked — `apps/bot/texts.py` holds 411 constants. This walks EVERY
public string (and every string inside a public list or tuple) of each copy
module, with the one pattern `core.copy_rules.BANNED`.

**THE FRONTEND half already walks every shipped source file**
(`tests/test_web_shell.py::test_no_guilt_copy_anywhere_in_the_frontend`, over
`app/`, `components/`, `lib/`); W19 pins its own surface into that walk there.

**THE BOT HAD FIFTEEN EXISTING HITS AND THEY WERE FROZEN, NOT FIXED — W22 DELETED
FOURTEEN WITH THEIR HANDLERS AND ONE REMAINS (see `BOT_BASELINE`).** Fixing
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

#: `apps/bot/texts.py`'s offenders. Fifteen on 2026-09-25, frozen while the bot
#: path stayed byte-identical; **W22 deleted fourteen with the handlers that
#: sent them**, and the list shrank in the same commit, as the rule below
#: requires. The fourteen, quoted (#82's shape): `ANKI_SEND_FAILED`,
#: `BOOK_PROCESS_FAILED`, `CAPTURE_FAILED`, `GUIDE_SECTION_ANKI_WEEK`,
#: `IMPORT_FAILED_HEADERS`, `INTERESTS_SAVE_FAILED`, `LLM_FAILED`,
#: `ONBOARD_SAVE_FAILED`, `OPERATOR_CSV_VOCAB_LLM_FAILED`, `PREP_FAILED`,
#: `QUIZ_HINT_SPOT`, `QUIZ_SPOT_PROMPT`, `QUIZ_YOU_SAID`, `READING_WRONG`.
#: **What remains is the bot blaming itself** — the error handler's *"Something
#: broke on my side"* — which the pattern cannot tell from blaming the learner.
#: Kept as written: W22's brief was to shrink the baseline to what remains, not
#: to reword what the bot still says.
BOT_BASELINE = frozenset(
    {
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
    # W22: 411 names became 18 (was `> 400` strings). Every one left is
    # something the bot can still send; see `apps/bot/texts.py`.
    assert len(_strings("apps.bot.texts")) >= 18
    assert len(_strings("core.copy")) > 40


def test_no_copy_module_gains_a_banned_phrase() -> None:
    new = sorted(_offending_names() - BOT_BASELINE)
    assert new == [], "a banned phrase reached copy (CLAUDE.md §4): " + ", ".join(new)


def test_the_bot_baseline_only_shrinks() -> None:
    """A baseline entry that no longer offends must leave the list in the same
    commit, or the baseline stops describing anything."""
    stale = sorted(BOT_BASELINE - _offending_names())
    assert stale == [], "no longer offending — remove from BOT_BASELINE: " + ", ".join(stale)
