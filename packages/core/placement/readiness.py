"""When the placement check may be offered at all. **Pure.**

**THE READINESS RULE (launch 2026-09-26, B2).** A sitting is offered only when
every cell it draws from holds, UNSERVED TO THIS LEARNER, at least:

    vocabulary, each of the ten frequency bands   REAL_PER_BAND (4)
    vocabulary, pseudo-words                      PSEUDO_PER_SITTING (20)
    grammar, each of A2 B1 B2 C1                  ladder.HOLD_ITEMS (8)
    listening, each band, as LISTENING_ORDER      A2 1 · B1 2 · B2 2 · C1 1
    speaking                                      1

**Why these numbers.** Vocabulary, listening and speaking are drawn whole at the
start of their section, so their minimum is exactly what one sitting draws —
anything less and a band is skipped, which is how listening came to be able to
claim C1 from five clips that never included a C1 one. **Grammar is adaptive,**
and its worst case is not the minimum: exhaustive search over `ladder.replay`
(2026-09-26) found one sitting can serve at most **A2 17 · B1 21 · B2 19 · C1 16**
at a band. Demanding that would hold the check back for a path no learner walks,
and the ladder already has an honest answer to a thin band — it stops
(`bank_thin`, recorded on the run, never shown) and reads the band from what
was answered. So grammar asks for **`HOLD_ITEMS` per band: enough for the
ladder's own "held" verdict at any band without going thin**, and one row at
every band means a band the ladder steps DOWN into was always served before it
can be claimed.

**What it does to the monthly re-run.** The cells are counted per learner, over
rows they have never been served. A second sitting that cannot be drawn
disjointly at these minimums is **not offered** — *not ready* — rather than
served thin or served a repeat (`placement_run_items`' UNIQUE refuses a repeat
anyway; this makes the refusal a readable state instead of a 500).

**Today (the host's counts, 2026-09-26): NOT READY** — listening C1 holds 0 of
1. Every other cell passes (grammar A2 12 is the thinnest against its 8).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from core.placement import BANDS, ladder
from core.placement.scoring import (
    LISTENING_ORDER,
    PSEUDO_PER_SITTING,
    REAL_PER_BAND,
    VOCAB_BANDS,
)

#: Grammar rows per band, unserved to the learner.
GRAMMAR_READY_PER_BAND = ladder.HOLD_ITEMS


def minimums() -> dict[tuple, int]:
    """Every cell a sitting draws from, and the least it must hold. Keys are
    `core.services.placement._unserved_counts`' keys."""
    need: dict[tuple, int] = {
        ("vocabulary", "real", band): REAL_PER_BAND for band in range(VOCAB_BANDS)
    }
    need[("vocabulary", "pseudo")] = PSEUDO_PER_SITTING
    for band in BANDS:
        need[("grammar", band)] = GRAMMAR_READY_PER_BAND
    for band, n in Counter(LISTENING_ORDER).items():
        need[("listening", band)] = n
    need[("speaking", "any")] = 1
    return need


def shortfall(held: Mapping[tuple, int]) -> dict[tuple, int]:
    """Cell → how many rows it is short. Empty means a sitting may be offered."""
    return {
        cell: n - held.get(cell, 0)
        for cell, n in minimums().items()
        if held.get(cell, 0) < n
    }


def ready(held: Mapping[tuple, int]) -> bool:
    return not shortfall(held)
