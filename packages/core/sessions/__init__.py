"""The daily session's shape, as constants. PRD §4.1.

Pure. Nothing here reaches a database, a model or HTTP -- `core/sessions/` is to
`core/services/sessions.py` what `core/items/` is to `core/services/items.py`,
and for the same reason: the whole block-assembly rule is testable without
Postgres.

**The five blocks are PRD §4.1's five, unchanged, and W10 is a RETURN to that
section rather than a revision of it.** The standalone `/review` screen is what
diverged (#160); §4.1 has specified "Block 1 · Review -- FSRS due cards, capped"
inside the daily session all along. No PRD amendment is owed by this slice, and
that finding is recorded rather than left to be re-derived.
"""

from __future__ import annotations

#: The five blocks, in order, as PRD §4.1 names them. The ORDER is the tuple's
#: order and the NUMBER is the 1-based position -- there is no separate `n`
#: field to fall out of step with it.
BLOCK_KINDS: tuple[str, ...] = ("review", "input", "focus", "output", "close")

BLOCK_COUNT = len(BLOCK_KINDS)

#: What a block can be, and the two that must never collapse into one another.
#:
#: * ``ready``       -- it has content and has not been finished.
#: * ``done``        -- the learner completed it in this session.
#: * ``empty``       -- **a fact, computed after a SUCCESSFUL read.** The query
#:                      returned no rows, or the dependency does not exist yet
#:                      (blocks 2 and 3 today). Nothing is due; nothing failed.
#: * ``unavailable`` -- **only ever written from a caught exception** while
#:                      building that one block. One block's dependency falling
#:                      over must not take the session down, and must not read
#:                      to a learner as "nothing to do".
#:
#: A whole-route failure is an HTTP error and produces NEITHER of the last two.
#: A learner who is told "nothing's due, go watch something" because a query
#: timed out has been lied to, and the lie is indistinguishable from the truth
#: on the screen -- which is why this is a state machine and not a nullable
#: payload.
BLOCK_STATES: tuple[str, ...] = ("ready", "done", "empty", "unavailable")

#: PRD §4.1's header: "target 45 min, hard floor 12 min".
#:
#: **W10 records `minutes` and enforces no floor**, and the number is reported
#: rather than the bar being moved (CLAUDE.md §3 rule 7). Blocks 2 and 3 carry
#: no content in this slice, so a real session is block 1 + block 4 + close and
#: can honestly come in under twelve minutes. There is nothing to pad it with
#: that would not be invented work. Checkable once the video engine lands.
TARGET_MINUTES = 45
HARD_FLOOR_MINUTES = 12

#: A session longer than this is a phone that was put down, not a study session.
#: Mirrors `items.MAX_LATENCY_MS` and `cards.MAX_REVIEW_DURATION_MS`: an
#: implausible measurement is stored as NULL rather than as a lie (#108).
MAX_SESSION_MINUTES = 600

#: The task_type this slice writes into `sessions`.
#:
#: `sessions.task_type` is a bare TEXT with no CHECK (001:107), so this needed no
#: constraint widened -- unlike `errors.source`, whose CHECK had to be widened
#: once at 012 (#47). Checked in the tree rather than assumed.
DAILY_TASK_TYPE = "daily"
