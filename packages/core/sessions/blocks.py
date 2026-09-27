"""Pure block assembly: what a block IS, and the two projections it needs.

No SQL, no HTTP, no model call. `core/services/sessions.py` does the reads and
hands the rows here; this module decides shape, state and ordering.

**The learner-visible projection of a grammar target is the load-bearing thing
in this file** (#171). See `visible_target`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.sessions import BLOCK_COUNT, BLOCK_KINDS, BLOCK_STATES


class BlockError(ValueError):
    """A block shape that must not reach a learner."""


@dataclass(frozen=True, slots=True)
class Block:
    """One of PRD §4.1's five, as the learner receives it.

    `n` is the 1-based position and is derived from `BLOCK_KINDS`, never passed
    in beside a kind that could disagree with it -- see `assemble`.
    """

    n: int
    kind: str
    state: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in BLOCK_KINDS:
            raise BlockError(f"unknown block kind: {self.kind!r}")
        if self.state not in BLOCK_STATES:
            raise BlockError(f"unknown block state: {self.state!r}")
        if self.n != BLOCK_KINDS.index(self.kind) + 1:
            raise BlockError(
                f"block {self.n} cannot be {self.kind!r}: "
                f"{self.kind!r} is block {BLOCK_KINDS.index(self.kind) + 1}"
            )
        # An `empty` or `unavailable` block that carries content is the two
        # states collapsing by accident, which is exactly what this slice is
        # built to prevent. `done` keeps its payload: a finished review block
        # still shows what was reviewed.
        if self.state in ("empty", "unavailable") and self.payload:
            raise BlockError(
                f"block {self.n} is {self.state!r} and carries a payload"
            )


def assemble(payloads: dict[str, tuple[str, dict[str, Any]]]) -> tuple[Block, ...]:
    """``{kind: (state, payload)}`` -> the five blocks, in PRD §4.1's order.

    Exhaustive: every kind in `BLOCK_KINDS` must be present. A missing block is
    an error here rather than a four-block session on a phone, because the
    absence of a block and an empty block are different facts and the learner
    can only see one of them.
    """
    missing = [kind for kind in BLOCK_KINDS if kind not in payloads]
    if missing:
        raise BlockError(f"no payload for block(s): {', '.join(missing)}")
    unknown = [kind for kind in payloads if kind not in BLOCK_KINDS]
    if unknown:
        raise BlockError(f"unknown block(s): {', '.join(sorted(unknown))}")

    out: list[Block] = []
    for index, kind in enumerate(BLOCK_KINDS, start=1):
        state, payload = payloads[kind]
        out.append(Block(n=index, kind=kind, state=state, payload=payload))
    return tuple(out)


def first_open_block(blocks: tuple[Block, ...]) -> int:
    """Where the runner opens. The first block that is neither done nor skippable.

    **`empty` and `unavailable` are both skipped, and that is the ONE place the
    two are treated alike** -- a learner should not be parked on a block with
    nothing to do in it for either reason. Everywhere else they are distinct,
    because the two say different things on the screen.

    Returns `BLOCK_COUNT` when everything is finished, so the runner lands on
    Close rather than on nothing.
    """
    for block in blocks:
        if block.state == "ready":
            return block.n
    return BLOCK_COUNT


def completed_count(blocks: tuple[Block, ...]) -> int:
    return sum(1 for block in blocks if block.state == "done")


# ── #171: what a grammar target looks like to a learner ─────────────────────


#: The four blocks that serve work. `close` is a summary, never a task.
_WORK_KINDS = ("review", "input", "focus", "output")


def finished(blocks: tuple[Block, ...]) -> bool:
    """**W24e: today's session is finished** -- derived, never stored.

    Every work block that served something is `done`, and at least one was: an
    `empty` block served nothing and cannot hold the day open, but a day where
    every block was empty is not a session the learner finished. `unavailable`
    (a block we could not read) and `ready` both keep it open.

    **`sessions.completed` is not this and is not written by it.** It has had no
    writer for a `daily` row since W11 (#349, #361), and writing it would feed
    the nudge ladder's active-day count (#259) -- a behaviour change W24e was
    told not to make. Keep going reads THIS, computed from the blocks the
    learner can see, at hydration.

    **Block 4 is `done` only from `writing_submissions` (W16a).** A learner who
    talks on `/talk` instead of writing leaves block 4 `ready`, so their session
    never reads finished -- filed, not papered over (#463).
    """
    work = [b for b in blocks if b.kind in _WORK_KINDS]
    return any(b.state == "done" for b in work) and all(
        b.state in ("done", "empty") for b in work
    )


def visible_target(target: Any) -> dict[str, str]:
    """A `GrammarTarget` as the learner receives it. **The citation is not here.**

    W8g ruled that the syllabus cannot cite an external book to a learner, and
    #183 extended it to `error_types.murphy_units`: most users own no copy, some
    own a different edition, and the number is meaningless to nearly everyone
    who reads it. `syllabus_units.grammar_targets[]` carries `murphy_units` and
    block 3 serialises those targets, so **this slice is the first that could
    put one on a screen.**

    This is a CAPABILITY rather than a rule, the same shape as
    `core.items.projection.visible_projection`: a route handed one of these
    cannot render a citation because it was never given one. Building the dict
    by naming the one field that may travel -- rather than copying and deleting
    -- means a second operator-only field added to `GrammarTarget` later is
    withheld by default instead of leaking by default.

    `tests/test_no_murphy_reaches_a_learner.py` asserts it here, at the
    serialisation seam, in addition to its scan over every rendering surface.
    """
    # A `GrammarTarget` from `core.syllabus.content` and a raw `grammar_targets`
    # element read back out of the JSONB column are both accepted, because the
    # SESSION serves what production holds — `stored_units` returns the row as it
    # actually is, deliberately, so a comparison against the file stays the
    # seed's job. Reading the field two ways here is cheaper than a conversion
    # layer whose only purpose would be to satisfy one getattr.
    if isinstance(target, dict):
        text = target.get("target")
    else:
        text = getattr(target, "target", None)
    if not isinstance(text, str) or not text.strip():
        raise BlockError(f"grammar target has no text: {target!r}")
    return {"target": text.strip()}


def visible_targets(targets: Any) -> tuple[dict[str, str], ...]:
    return tuple(visible_target(one) for one in targets)


# ── the resume state ────────────────────────────────────────────────────────


def breakdown_of(blocks: tuple[Block, ...]) -> dict[str, str]:
    """The five blocks' states, as `sessions.block_breakdown` stores them.

    Keys are the KIND and not the number. A number would silently re-point at a
    different block if PRD §4.1's order ever changed, and a stored breakdown
    outlives the deploy that wrote it.
    """
    return {block.kind: block.state for block in blocks}


def stored_state(breakdown: Any, kind: str) -> str | None:
    """What a stored breakdown says about one block, or None if it says nothing.

    Tolerant by design: a breakdown written by an older deploy, or hand-edited,
    must not stop a learner opening their session. An unrecognised value is read
    as "nothing stored" and the block is rebuilt from live data.
    """
    if not isinstance(breakdown, dict):
        return None
    value = breakdown.get(kind)
    if value not in BLOCK_STATES:
        return None
    return str(value)
