"""W16a/W16b — which writing task a day gets, and how much of a correction survives.

**W16b: THURSDAY IS THE PARAGRAPH, EVERY OTHER DAY IS THE JOURNAL.** PRD §4.2
already says so — send-back A1 left Tuesday and Thursday unamended on purpose —
so W16b makes the spec true and **owes no PRD amendment**. The W16a text below is
quoted rather than deleted (#82's shape):

**THE DAY KIND IS `journal` ON EVERY DATE, AND THAT IS W16a's WHOLE RULE.**
PRD §4.2 gives Tuesday the journal and Thursday the paragraph. The paragraph is
**W16b's** (operator ruling S1, 2026-09-14), so until W16b ships Thursday
serves the journal too. **That gap is reported UNMET in W16a's slice row and is
not written into the PRD** (send-back A1): editing the spec until the shipped
behaviour meets it would be the bar moving, which CLAUDE.md §3 rule 7 forbids.

`'paragraph'` is already a legal value — `writing_submissions.day_kind`'s CHECK
admits it, so W16b needs no DDL — but **nothing in W16a returns it**, and
`tests/test_writing_rules.py` pins that.

Mon/Wed/Fri's **speaking** output lost its surface when W14r retired the Azure
path and returns at W15; PRD §4.2's rows say so. This function is revisited
then, not guessed at now.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from core.services.correction import MIN_CHARS as _CORRECTION_MIN_CHARS

DayKind = Literal["journal", "paragraph"]

#: Every value the table accepts. W16b's `paragraph` is legal and unwritten.
DAY_KINDS: tuple[DayKind, ...] = ("journal", "paragraph")

#: Every value that may be written. **W16b adds `paragraph`**; W16a wrote only
#: `journal` and a test pinned it — that test is inverted, not deleted.
WRITTEN_DAY_KINDS: tuple[DayKind, ...] = ("journal", "paragraph")

#: `date.weekday()` is Monday-0, so Thursday is 3 (PRD §4.2).
PARAGRAPH_WEEKDAY = 3

#: The floor is W3's, UNCHANGED (CLAUDE.md §8 — the number was not re-argued).
#: Imported rather than restated so the two cannot drift apart.
MIN_CHARS = _CORRECTION_MIN_CHARS

#: Q-B, operator-approved 2026-09-14. **2,000 characters is roughly 350 words**,
#: which is design `1g`'s *300+ words* with room. The bot's `correction.MAX_CHARS`
#: stays 1,000 — it is v2's number on a path W16a does not touch.
MAX_CHARS = 2000

#: The TASKS row's number for the journal. **Its attribution there — *"max 2 —
#: v2 rule"* — is wrong and recorded as wrong**: v2's `/correct` capped at three
#: (`correction.MAX_CORRECTIONS`), and the two in this tree is `/talk`'s close-out.
#: The number is built as the Accept cell states it.
JOURNAL_MAX_CORRECTIONS = 2

#: **Q-D, operator-accepted 2026-09-14.** "Full correction" left unbounded is a
#: number nobody can test and an unbounded count of permanent journal rows; eight
#: bounds both. *"Four more below."* is not drawn: it is a count of mistakes on a
#: surface whose own design note says no count anywhere (D15).
PARAGRAPH_MAX_CORRECTIONS = 8

#: The model's output budget for one journal correction, and **a starting value
#: to be REPORTED against by the §3 rule 2 call, not tuned in advance.**
#: `reject_truncation` goes with it: a truncated JSON array would parse into
#: fewer corrections and a silent hole.
WRITING_MAX_TOKENS = 2000


#: **F5 (operator).** The prompt read *"whose first language is fa"* — the raw
#: column value. The model is told a language's NAME. `apps/bot/texts.py` holds
#: the same two names for the bot; `packages/core` may not import `apps.bot`, so
#: this is a second copy of two strings, recorded against #159 rather than
#: hidden. An unmapped code is an error, never the code sent as-is.
LANGUAGE_NAMES: dict[str, str] = {"fa": "Farsi", "lt": "Lithuanian"}


def language_name(code: str) -> str:
    """A learner's first language as a name, for a prompt. Refuses an unknown code."""
    try:
        return LANGUAGE_NAMES[code]
    except KeyError:
        raise ValueError(f"no language name for code {code!r}") from None


def day_kind(local_date: date) -> DayKind:
    """The writing task for the learner's LOCAL date: Thursday is the paragraph."""
    return "paragraph" if local_date.weekday() == PARAGRAPH_WEEKDAY else "journal"


def max_corrections(kind: DayKind) -> int:
    """How many corrections one submission may show and write (two, or Q-D's eight)."""
    if kind == "journal":
        return JOURNAL_MAX_CORRECTIONS
    if kind == "paragraph":
        return PARAGRAPH_MAX_CORRECTIONS
    raise ValueError(f"no correction ceiling is built for day kind {kind!r}")
