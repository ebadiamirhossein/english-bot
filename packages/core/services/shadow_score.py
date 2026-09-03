"""W14 — the shadow line, and the scored attempt. **Not v2's `shadow.py`.**

`packages/core/services/shadow.py` is the v2 Telegram shadow and is untouched
until W22 (PRODUCT-PRINCIPLES §1). This module is the web surface's, and the two
share no code deliberately: v2's is a word-level ASR intelligibility diff with
no provider scoring, and this one is Azure pronunciation assessment. Merging
them would tie a surface that dies at W22 to one that does not.

────────────────────────────────────────────────────────────────────────────────
§1b — THE SHADOW TARGET IS A DECK SENTENCE AND NEVER A TRANSCRIPT CUE

**Assistant-recommended, operator-accepted 2026-09-03.**

R12 measured generated transcript tracks as ROLLING WINDOWS: ~92% of consecutive
cue pairs overlap (1405/1527, 655/714, 958/1038, 897/1034, 1471/1705, 272/317),
**and all three assigned videos are `generated`.** A cue is an arbitrary ~2.4 s
slice beginning mid-clause. W13-i reported loop-a-line and per-line 0.75x UNMET
on exactly this, and **W14 has a second reason W13-i did not have: Azure scores
against a REFERENCE TEXT, and `CompletenessScore` is defined as how much of the
reference was said.** A mid-clause fragment makes completeness meaningless by
construction and makes the boundary words noisy. **Shadowing a cue would ship an
unmet feature with a score attached to it** -- worse than the honest unmet
report.

**PRD §7.3's in-player *shadow this line* IS THEREFORE NOT DELIVERED, and #341
STAYS OPEN.** Reported, not approximated. The two standing refusals stand and
are not revisited: no merging cues into synthetic sentences, and no
manual-tracks-only behaviour.

**THE EXCLUSION IS A PREDICATE, NOT A HOPE.** W13-ii's `video.explain._line_for`
puts the CUE on a gloss, and `cards.save_captured_word` copies it straight onto
the card's `context_sentence` (`services/cards.py:1455`) -- so a video-sourced
card carries a rolling-window fragment, not a sentence. The same writer sets
`source_ref = 'video:<id>@<seconds>'` (`_capture_source_ref`, `:1363`), which is
what makes the exclusion exact rather than heuristic.

*(It selects nothing today: `python -m core.video.explain --apply` has never
run, so no video-sourced card exists. It is written now because the first one
appears the day T1 clears, and a selector written against an empty table is a
selector nobody checked.)*
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: §1b's exclusion, as one SQL fragment with one home. A second copy of this
#: predicate anywhere is the bug: the rule is *cue-derived sentences are not
#: shadowable*, and a caller that reimplemented it could drift silently.
NOT_CUE_DERIVED = "(cards.source_ref IS NULL OR cards.source_ref NOT LIKE 'video:%%')"

#: A sentence shorter than this is not worth scoring: `CompletenessScore` over
#: two words is dominated by its endpoints, and a one-word "line" is a
#: pronunciation drill, which is W17's and not this surface's.
MIN_SHADOW_CHARS = 12


@dataclass(frozen=True)
class ShadowLine:
    """One card's sentence, offered to be said aloud."""

    card_id: int
    sentence: str


def shadow_line(conn: Any, user_id: int) -> ShadowLine | None:
    """The line this learner shadows next, or ``None`` when the deck has none.

    **ORDERING: never-shadowed first, then least-recently-shadowed, then by
    `due`.** v2's `select_shadow_sentence` excluded the K most recent chunks;
    this expresses the same intent without inventing a K, by reading the log
    that now exists. A learner with one usable card gets it again, which is
    correct -- saying a line twice is the exercise, not a bug (`speech_attempts`
    carries no UNIQUE for this reason).

    **`None` IS A REAL STATE AND THE BLOCK SAYS SO PLAINLY.** A deck of cards
    that all came from a video, or all lack a context sentence, yields no line.
    That is *nothing to shadow today*, never an error and never a backlog.
    """
    row = conn.execute(
        f"""
        SELECT cards.id,
               cards.context_sentence,
               MAX(speech_attempts.created_at) AS last_said
          FROM cards
          LEFT JOIN speech_attempts
                 ON speech_attempts.card_id = cards.id
                AND speech_attempts.user_id = cards.user_id
         WHERE cards.user_id = %s
           AND cards.context_sentence IS NOT NULL
           AND length(btrim(cards.context_sentence)) >= %s
           AND {NOT_CUE_DERIVED}
         GROUP BY cards.id, cards.context_sentence, cards.due
         ORDER BY last_said ASC NULLS FIRST, cards.due ASC, cards.id ASC
         LIMIT 1
        """,
        (user_id, MIN_SHADOW_CHARS),
    ).fetchone()
    if row is None:
        return None
    return ShadowLine(card_id=int(row["id"]), sentence=str(row["context_sentence"]))
