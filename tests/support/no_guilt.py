"""The banned-phrase pattern, in one place — and that place is now `core`.

CLAUDE.md §4: "no 'you failed', no broken-streak message, no disappointed
emoji", and the test must cover **every** user-facing string, backend and
frontend.

**W10c moved the pattern to `packages/core/copy_rules.py` and this file
re-exports it.** The reason is #110: `prompt_text`, `cue_text`, options, tiles
and the canonical answer live in `items` and are model-generated from W10c, so
the rule has to be applicable by a **gate** and not only by a test — and a gate
in `packages/core` cannot import from `tests/`.

**This file is still not the fix for known issue #46**, and the move does not
widen it. #46 is that the Python suite carries five hand-copied versions of this
regex over eight hand-maintained string lists; that stays open with its W19
target and is narrowed by exactly one copy here. What this file has always done
is make sure no **sixth** copy is written, and re-exporting rather than
re-declaring is that rule applied to its own relocation.

`core.copy_rules` also carries `BANNED_IN_CONTENT`, which is **not** re-exported
here on purpose: it is the narrower rule for English a learner reads as
material, it is applied by `core.items.checks`, and a test reaching for it
through this module would be reaching for the wrong audience. Import it from
`core.copy_rules` directly and read the split's reasoning there.
"""

from __future__ import annotations

from core.copy_rules import BANNED, offenders

__all__ = ["BANNED", "offenders"]
