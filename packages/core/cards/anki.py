"""The deck as an Anki TSV. PRD §5: "Anki export stays."

**Added beside `core.services.anki`, not replacing it.** The v2 chunk exporter
is a ✅-verified live Telegram path (S7) that two learners use weekly, and W7's
chunk migration does not consume `chunks` — cards are *derived*, chunks stay in
place untouched. Repointing the verified exporter at a table that came into
existence an hour earlier would put the one working export at risk to save a
file. The v2 path dies at W22 with the rest of the bot.

**The stated cost:** a phrase can now be exported twice, once from each path.
The chunk exporter emits only `exported_to_anki = FALSE` rows, so in practice
the overlap is whatever has not already been downloaded — but it is a real
duplicate and it is recorded rather than discovered.

Four fields, in the same order and with the same sanitiser as the v2 export, so
an existing Anki note type keeps working: prompt, answer, meaning, source. The
field map is `docs/GUIDE-saving-phrases.md`'s, and a learner should not have to
rebuild it because the deck moved house.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

# Reused, never reimplemented. `sanitize_tsv_field` neutralises tabs and
# newlines so one field cannot break a row — the failure this export meets for
# the first time on real learner sentences.
from core.services.anki import sanitize_tsv_field

#: Distinct from `english-bot-<date>.tsv` so a learner can tell the two exports
#: apart in their downloads folder while both paths exist.
FILENAME_PREFIX = "english-deck"


def card_fields(card) -> tuple[str, str, str, str]:
    """The four TSV fields for one card, already sanitised.

    `front` already carries the gap for a cloze card and the gloss for a
    production card, because that is what the reviewer shows — the export does
    not re-derive a prompt, which is how the two would drift.

    The register tag rides on the source field rather than getting a fifth
    column: adding a column would break every existing note type, and a learner
    reading `himym_s2e4 · slang` in Anki learns exactly what §8.5.1 wants them
    to know.
    """
    source = card.source_ref or ""
    if card.register and card.register != "neutral":
        source = f"{source} · {card.register}".strip(" ·")
    return (
        sanitize_tsv_field(card.front),
        sanitize_tsv_field(card.back),
        sanitize_tsv_field(card.meaning or ""),
        sanitize_tsv_field(source),
    )


def build_tsv(cards: Sequence) -> str:
    """A headerless UTF-8 TSV body. Empty deck → empty string, never a header."""
    lines = ["\t".join(card_fields(card)) for card in cards]
    return "\n".join(lines) + ("\n" if lines else "")


def filename_for(local_date: date) -> str:
    return f"{FILENAME_PREFIX}-{local_date.isoformat()}.tsv"
