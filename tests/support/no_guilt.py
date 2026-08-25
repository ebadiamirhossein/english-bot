"""The banned-phrase pattern, in one place.

CLAUDE.md §4: "no 'you failed', no broken-streak message, no disappointed
emoji", and the test must cover **every** user-facing string, backend and
frontend.

**This file is not the fix for known issue #46.** #46 is that the Python suite
carries five hand-copied versions of this regex over eight hand-maintained
string lists, and that widening it to all copy will surface existing violations;
it stays open with its W19 target. What this file does is make sure W6 does not
add a **sixth** copy while bringing the frontend under the rule for the first
time.

The pattern is the union of the three existing Python copies
(`test_hardening.py`, `test_motivation.py`, `test_shadow.py`) plus the terms an
item renderer specifically invites. Eleven components' worth of wrong-answer
feedback is the highest-risk copy in the app so far, and the phrasings that come
naturally — "Wrong", "Incorrect", "You missed it" — are exactly the ones to
refuse. The verdict belongs to the attempt, never to the person.
"""

from __future__ import annotations

import re

#: Terms the three existing Python copies already ban.
_CARRIED = r"\bmissed\b|\bfailed\b|\bbroke\b|wrong!|should have"

#: Added by W6, for the answer-feedback surface.
_ITEM_RENDERERS = r"\bwrong\b|\bincorrect\b|try harder|you lost"

#: Disappointed faces, plus the two failure marks a renderer reaches for.
_SAD = r"😞|😢|😔|☹️|🙁|😟|😤|😠|❌|✗"

BANNED = re.compile(
    f"{_CARRIED}|{_ITEM_RENDERERS}|{_SAD}", re.IGNORECASE
)


def offenders(sources: dict[str, str]) -> list[str]:
    """``{path: text}`` → one entry per banned term found, sorted by path.

    Takes a mapping rather than reading files so the meta-test can feed it
    deliberate violations without writing any.
    """
    found: list[str] = []
    for path, text in sorted(sources.items()):
        for match in BANNED.finditer(text):
            found.append(f"{path}: {match.group(0)!r}")
    return found
