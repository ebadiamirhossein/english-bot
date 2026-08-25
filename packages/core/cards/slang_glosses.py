"""The operator's neutral equivalents for v2 slang, read from a TSV.

**Why this exists.** PRD §8.5.4 requires every `informal`/`slang` card to show
four things — the line it came from, the meaning, **the neutral equivalent**, and
who says this to whom — and migration 013 holds that with a CHECK. v2 `chunks`
carry the first two and neither of the last two, so W7's first plan skipped
slang-sourced chunks entirely.

**The production census on 2026-08-25 made that unshippable.** Two of the three
learners' *entire* v2 corpus is the S24 slang fan-out: Navid 5 chunks / 5 slang,
Morkyte 5 / 5. Skipping slang gave them zero cards each and failed W7's first
acceptance criterion — "the deck is non-empty on day one" — for two learners out
of three. The criterion was not lowered; the migration was.

**Why a file the operator writes, and not a model call.** PRD §8.5.3 would have
permitted one: slang is *detected, never generated*, and these phrases were
already detected from real input — the model would only be explaining and
tagging, which §8.5.3 says it can do reliably. It is still the wrong instrument
here. The neutral equivalent is **the safe thing to say instead**, it is content
the learner will go on to produce, and there are roughly five distinct phrases.
A person who knows these two learners writes five better lines than a model
does, at no cost and with no gate to design. If the corpus were five hundred this
would be the other way round, and W13 generates them at capture time.

**The file is never committed.** It is a path passed on the command line. These
are five phrases from the learners' own shared library, and `data/` holds
reference data, not learner content.

Format — three tab-separated columns, a header row, `#` comments allowed::

    chunk<TAB>neutral_equivalent<TAB>who_says_this
    hard pass<TAB>I'd rather not, thanks<TAB>Friends and casual colleagues. Fine in Slack, not in a client email.

Matching is on the chunk text, normalised the same way `core.services.reading`
normalises for chunk lookup, so an apostrophe or a capital does not silently
lose a row. **A slang chunk with no entry is skipped and counted separately**,
never migrated with a NULL neutral equivalent — that is the card §8.5.4 calls
"useless and slightly dangerous", and the CHECK would refuse it anyway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.services.reading import normalize_for_match

logger = logging.getLogger(__name__)

EXPECTED_HEADER = ("chunk", "neutral_equivalent", "who_says_this")


class SlangGlossError(ValueError):
    """The file is not the shape this reads. Refused loudly, never half-read."""


@dataclass(frozen=True, slots=True)
class SlangGloss:
    chunk: str
    neutral_equivalent: str
    who_says_this: str


def load(path: Path | str) -> dict[str, SlangGloss]:
    """Read the operator's file. Keyed by normalised chunk text.

    Refuses the whole file on a malformed row rather than importing what parsed:
    a partially-read gloss file produces a deck where some slang cards carry a
    safe alternative and some do not, and the ones that do not are exactly the
    rows nobody looked at.
    """
    source = Path(path)
    if not source.is_file():
        raise SlangGlossError(f"no such file: {source}")

    rows: dict[str, SlangGloss] = {}
    lines = source.read_text(encoding="utf-8").splitlines()
    header_seen = False

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("\t")]
        if not header_seen:
            if tuple(f.lower() for f in fields) != EXPECTED_HEADER:
                raise SlangGlossError(
                    f"{source}:{number}: expected a header row "
                    f"{EXPECTED_HEADER}, got {tuple(fields)}"
                )
            header_seen = True
            continue
        if len(fields) != 3:
            raise SlangGlossError(
                f"{source}:{number}: expected 3 tab-separated fields, "
                f"got {len(fields)}"
            )
        chunk, neutral, who = fields
        if not chunk or not neutral or not who:
            # §8.5.4 wants all four things. An empty column here is a row the
            # operator started and did not finish, and finishing it later is
            # cheaper than discovering the gap on a phone.
            raise SlangGlossError(
                f"{source}:{number}: every column is required "
                f"(PRD §8.5.4 — the neutral equivalent is the point)"
            )
        key = normalize_for_match(chunk)
        if not key:
            raise SlangGlossError(f"{source}:{number}: chunk normalises to nothing")
        if key in rows:
            raise SlangGlossError(f"{source}:{number}: duplicate chunk {chunk!r}")
        rows[key] = SlangGloss(chunk, neutral, who)

    if not header_seen:
        raise SlangGlossError(f"{source}: no header row found")
    logger.info("Loaded %d slang glosses from %s", len(rows), source)
    return rows


def lookup(glosses: dict[str, SlangGloss], chunk: str) -> SlangGloss | None:
    """Find a gloss for a chunk, normalising both sides the same way."""
    return glosses.get(normalize_for_match(chunk))
