"""W33 (B) — the natural version's highlights: which words of the rewrite are new.

The operator asked for the learner's whole entry *"rewritten as a native speaker
would say it, with changed words highlighted"*. The rewrite is the model's (one
field of the one correction call); **which words changed is computed here, from
the two texts, and never asked of the model** — a model's own list of what it
changed is a claim, and a diff is a fact.

**Word by word, case-sensitive.** `i` → `I` and `im` → `I'm` are exactly what a
learner should see marked; quotes are straightened first so an iOS `’` is not a
change. Punctuation is never compared and never marked: a full stop added at the
end of a line is not a word the learner has to learn.

**STATED LIMIT: a word only REMOVED leaves nothing to mark** (`go to home` →
`go home` marks nothing — the rewrite has no word where `to` was). The other
notes and the corrections carry that kind of change; this view shows the new
wording, not the deletions.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

#: A word: letters or digits, with an inner apostrophe (`I'm`, `don’t`).
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_QUOTES = str.maketrans({"’": "'", "‘": "'"})


def _key(word: str) -> str:
    return unicodedata.normalize("NFC", word).translate(_QUOTES)


def segments(original: str, natural: str) -> tuple[dict, ...]:
    """The rewrite as runs of ``{"text", "changed"}``. **Joined, they are `natural` exactly.**

    A word is ``changed`` when the alignment of the two word sequences
    (`difflib.SequenceMatcher`, no autojunk) inserts or replaces it. Two changed
    words with only spaces between them are ONE run, so *getting ready* is one
    highlight and not two.
    """
    theirs = [_key(m.group()) for m in _WORD.finditer(original or "")]
    found = list(_WORD.finditer(natural or ""))
    ours = [_key(m.group()) for m in found]
    changed = [False] * len(ours)
    matcher = difflib.SequenceMatcher(a=theirs, b=ours, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            for j in range(j1, j2):
                changed[j] = True

    out: list[dict] = []

    def push(text: str, flag: bool) -> None:
        if not text:
            return
        if out and out[-1]["changed"] == flag:
            out[-1] = {"text": out[-1]["text"] + text, "changed": flag}
        else:
            out.append({"text": text, "changed": flag})

    pos = 0
    for n, match in enumerate(found):
        gap = natural[pos : match.start()]
        push(gap, n > 0 and changed[n - 1] and changed[n] and gap.isspace() and "\n" not in gap)
        push(match.group(), changed[n])
        pos = match.end()
    push(natural[pos:], False)
    return tuple(out)
