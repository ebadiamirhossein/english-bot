"""Per-cue timings: the active-cue rule, the offset map, the identity gate.

Pure: no SQL, no HTTP, no model, no I/O — the same standing `score.py` and
`watch.py` have, so the rule block 2 depends on is testable without Postgres and
`core/video/` stays inside the model ban.

────────────────────────────────────────────────────────────────────────────────
WHAT T5 MEASURED, AND WHY IT DECIDES THE SHAPE OF THIS FILE

Read from the host on 2026-09-01, from `--dump` output written verbatim by the
billed runs (#317's fix). Quoted, not re-derived:

* **The actor returns a timestamped variant** — key `timestamped`, a list of
  `{text, start, duration}`. **Every element carries a `start`**: 103/103, 9/9,
  21/21, 124/124, 70/70 in run2; 1039/1039, 1035/1035, 1706/1706, 1528/1528,
  715/715, 318/318 in run3. Units are **seconds, float** (`0`, `2.4`, `7.003`,
  `11.716`).
* **The text reproduces exactly.** `" ".join(seg["text"])` md5 equals the row's
  `non_timestamped` md5 in every row read, **and equals the stored transcript
  for all three assigned videos.** That three-way match is what makes
  `cue_offsets` EXACT rather than a guess, and it is the whole reason a
  character map is possible at all.
* **GENERATED TRACKS ARE ROLLING WINDOWS, NOT LINES.** Overlapping consecutive
  pairs: **1405/1527**, 655/714, 958/1038, 897/1034, 1471/1705, 272/317 —
  roughly **92% on every generated track measured**. Manual tracks are
  contiguous by contrast (TED-Ed: `7.003 + 4.713 = 11.716` exactly), **but all
  three assigned videos are `generated`.**

**THE 92% IS WHY LOOP-A-LINE AND PER-LINE 0.75x ARE NOT HERE.** A cue interval
is a display window, not a sentence, so "loop this line" would loop an arbitrary
~2.4 s slice beginning mid-clause. They are **reported unmet against W13's Build
column** rather than deferred, and two workarounds are refused on the record:
merging cues into synthetic sentences (a generated artefact presented as the
transcript's own structure) and shipping them for manual tracks only (a feature
that appears and disappears on a property no learner can see). Both are filed as
candidates against W13a.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

#: The separator the actor's own `non_timestamped` uses, and therefore the only
#: one that reproduces it. **Not a formatting choice** -- a different separator
#: makes `reproduces` false on every row and the offsets wrong by one per cue.
JOIN = " "


def normalise_cues(raw: Any) -> list[dict] | None:
    """Validate a cue list, or return None meaning **this track is unusable**.

    **ALL OR NOTHING, AND THAT IS THE POINT.** A partial timing set is not a
    timing set for a follow-along highlight: half a track would light some lines
    and silently skip others, which reads as a broken feature rather than an
    absent one. A rejected track lands in the *transcript present, cues absent*
    state, which is specified and survivable.

    **THREE REFUSALS, AND NONE OF THEM REPAIRS:**

    * a cue with no usable `start` -- the highlight has nothing to key on;
    * **descending `start`s** -- `active_cue`'s monotonicity assumes sorted
      input, and **re-ordering somebody else's cues is a repair**, refused on
      the same ground the identity gate refuses to repair a mismatch: a track
      that arrives out of order is a track we do not understand, and sorting it
      would hide that behind a plausible result;
    * anything that is not a non-empty list.

    `duration` is carried when present and **never required**: nothing in this
    module reads it, and demanding it would reject tracks the rule can serve.
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return None

    out: list[dict] = []
    previous: float | None = None
    for element in raw:
        if not isinstance(element, Mapping):
            return None
        start = element.get("start")
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            return None
        start = float(start)
        if previous is not None and start < previous:
            return None
        previous = start

        text = element.get("text")
        if not isinstance(text, str):
            return None

        cue: dict = {"text": text, "start": start}
        duration = element.get("duration")
        if not isinstance(duration, bool) and isinstance(duration, (int, float)):
            cue["duration"] = float(duration)
        out.append(cue)
    return out


def joined_text(cues: Sequence[Mapping]) -> str:
    """The cues as one string. **Must equal the stored `videos.transcript`.**"""
    return JOIN.join(str(cue["text"]) for cue in cues)


def reproduces(cues: Sequence[Mapping], text: str) -> bool:
    """Does joining these cues give back exactly this text?

    **THE GATE, AND IT IS md5 RATHER THAN LENGTH.** A length comparison passes on
    any substitution -- `thanks` for `thankS` is the same length and a different
    transcript -- and the failure it would admit is the one that cannot be seen:
    coverage computed over one string and the highlight computed over another,
    **two instruments on one screen that agree until they do not.**

    **IT GUARDS BOTH DIRECTIONS OF TIME.** The backfill calls it before writing a
    stored row's cues; `record_transcript` calls it before storing a fetched
    row's. T5's identity was measured on **eleven rows from one actor**, which is
    evidence about that actor on those rows and **not a property of the
    pipeline** -- `codepoetry/youtube-transcript-ai-scraper` is the ruled
    fallback and has never been measured, and #288 is this project already
    inheriting one provider's premise as a fact about all of them.

    **One function, both callers**, so the two gates cannot drift into
    disagreeing about what identity means -- which is the defect the gate exists
    to prevent, one level up.
    """
    left = hashlib.md5(joined_text(cues).encode("utf-8")).hexdigest()
    right = hashlib.md5(text.encode("utf-8")).hexdigest()
    return left == right


def cue_offsets(cues: Sequence[Mapping]) -> list[tuple[int, int]]:
    """Each cue's `[start, end)` character range inside `joined_text(cues)`.

    **EXACT, AND EXACT ONLY BECAUSE OF THE THREE-WAY md5 MATCH.** The joined text
    IS the stored transcript, which IS the string the component renders -- so a
    character range computed here lands on the same characters on the screen.
    Without that identity these offsets would be a guess against a
    re-tokenisation, which is the second instrument this whole design refuses.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for index, cue in enumerate(cues):
        if index:
            cursor += len(JOIN)
        length = len(str(cue["text"]))
        spans.append((cursor, cursor + length))
        cursor += length
    return spans


def active_cue(cues: Sequence[Mapping], position_s: float) -> int | None:
    """The index of the cue the learner is hearing, or None before the first.

    **THE RULING (W13 cue-timings plan §1a): LATEST-STARTED WINS.** The active
    cue is the one with the greatest `start` at or before `position_s`.

    **THIS FUNCTION NEVER READS `duration`, AND THAT IS THE ARGUMENT RATHER THAN
    AN OPTIMISATION.** Two properties follow mechanically:

    * it is **total** for `position_s >= cues[0]["start"]` -- exactly one answer,
      never two, however many windows are live;
    * it is **monotone** in `position_s` -- as the video plays forward the index
      never decreases, so the highlight advances and **cannot jump backwards.**

    **The 92% overlap lives entirely in `duration`, so it cannot reach this
    rule.** The selection changes exactly once per cue, at that cue's `start`,
    and at no other instant -- so a track where two windows are live for seconds
    at a time cannot flicker.

    **DECLINED, WITH THEIR REASONS, so they are not re-proposed:**

    * **longest-remaining wins** -- reads `start + duration`, so when cue N
      outlasts cue N+1 the selection **jumps backwards**. At 92% overlap that is
      the normal state of a generated track, not an edge case. **This is the
      flicker, and it belongs to this candidate specifically.**
    * **highlight both** -- honest about the data and unusable: ~92% of the
      track lit in pairs is closer to *highlight everything* than to *show me
      where we are*.
    * **highlight none during an overlap** -- not a candidate: it would blank
      the highlight over most of the track.

    **THE THREE BOUNDARIES, because a rule is judged at them:**

    * **before the first `start`** -- None. Nothing is lit; on the measured
      tracks that is the first 0-2.4 s.
    * **after the last `start`** -- the final cue stays lit. Captions end
      **15-22 s before the video does** (`total_seconds` 3569.96 against a
      stored `duration_s` of 3592; 1611.37 against 1627), so this tail is real
      and a lit final line is more honest there than an unlit transcript.
    * **A GAP MID-TRACK** -- a cue stays lit through any silence until the next
      `start`. **This is the flipside of the property that makes the rule
      flicker-free and it is correct, not a defect:** the rule cannot see
      `duration`, so it cannot know a window closed. Nearly invisible on
      generated tracks at 92% overlap; **on a contiguous manual track a music
      break leaves the last spoken line highlighted throughout it.** Recorded so
      a reader who sees that does not file it.

    A linear scan rather than a bisect: the caller is a browser calling this per
    animation frame over a list of at most a few thousand, and the shipped
    implementation lives in TypeScript. **This is the Python side of the rule --
    the definition the tests hold** -- and the two must agree.
    """
    found: int | None = None
    for index, cue in enumerate(cues):
        if float(cue["start"]) <= position_s:
            found = index
        else:
            break
    return found
