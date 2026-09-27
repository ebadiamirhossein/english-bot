"""Cues → display lines, and the display cleaning. **W31b.**

    python -m core.video.lines --report --video N [--sample 10]

Pure below the CLI: no SQL, no HTTP, no model — `core/video/`'s standing, so the
rule the study screen depends on is testable without Postgres and the package
stays inside the model ban (#292). The CLI reads through `core.services.video`.

────────────────────────────────────────────────────────────────────────────────
WHY LINES, AND WHAT THIS OVERRULES

The operator used `/watch` on 2026-09-27 and could not learn from it: one wall of
text, nothing showing which line was being spoken, `>>` and `[laughter]` and
ALL-CAPS on the screen. **The operator ruled lines** (W31, #397's question —
*timed paragraphs or lines* — answered: lines).

**That ruling overrules a refusal this record made twice, and says so here
rather than letting the code contradict the comment it sits under.**
`core/video/cues.py` (T5) and W14/B–W14/3 refused *"merging cues into synthetic
sentences (a generated artefact presented as the transcript's own structure)"*,
because a generated cue is a ~2.4 s rolling window that starts mid-clause. What
this module builds is narrower than what was refused, and the difference is the
whole of why it is honest:

* **a line is a grouping of WHOLE cues** — no cue is ever split, so every
  timestamp on the screen is one the track itself carries;
* **no word is reworded.** Every word of every cue survives, in order
  (`test_every_word_of_every_cue_survives_in_order`); the only changes are the
  ruled display cleaning below, and they are display only;
* **the stored transcript, `transcript_cues`, coverage and the purge are
  untouched.** This module returns new values and mutates nothing it is given.

WHAT A LINE IS (the plan's thresholds, Q2 — the operator's three-video
`--report` on the host is what confirms or retunes them, as a follow-up commit)

1. **A cue ends where the next begins.** The ~92% overlap T5 measured lives in
   `duration` only (the rolling window keeps the last words on screen); reading
   the next `start` instead removes it without dropping text.
2. **A repeated edge is stripped**: a cue that begins with a ≥2-word suffix of
   the one before loses that prefix. The md5 identity gate predicts it never
   fires on stored data (the joined cues ARE the transcript); `--report` counts
   it, so the prediction is measured rather than assumed.
3. **Break** at a speaker marker (`>>`), after sentence-final punctuation, at a
   silence (a cue starting later than the previous start + duration, beyond
   float noise), or before a line would pass **6 s or 14 words**.
4. **Merge** a line of fewer than 3 words into the next one — or the previous
   one, when it is last — never across a speaker change.

THE DISPLAY CLEANING (ruled, display only)

* `>>` is never shown: at a cue's start it breaks the line; inside a cue it
  becomes a dash (`—`) and still starts a new line.
* `[laughter]` and every bracketed tag stay as they are; the client renders
  them dimmed and untappable.
* **A run of ALL-CAPS words becomes sentence case, and names survive (C1,
  operator, 2026-09-27):** *"HEY, PETER! IT'S ME, ROSS"* → *"Hey, Peter! It's
  me, Ross"*. The run is lowercased; sentence starts and *I* are capitalised;
  **a word that appears capitalised in mixed-case text elsewhere in the same
  transcript keeps that form** — mid-sentence only, and only if it never also
  appears in lowercase there (*Will* the name against *will* the verb, which
  would otherwise capitalise every *I WILL*). A lone capitalised word (*TV*,
  *NHS*) is not a run and is untouched; mixed-case text is never recased.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from core.video.cues import normalise_cues

#: The plan's thresholds (Q2). Retuned only from the host's `--report`.
MAX_SECONDS = 6.0
MAX_WORDS = 14
MIN_WORDS = 3
#: Below this, a gap between one cue's end and the next start is float noise
#: (`7.003 + 4.713` is `11.716000000000001`), not a silence.
SILENCE_EPSILON_S = 0.05
#: A last cue with no `duration` still needs an end for loop-a-line.
DEFAULT_LAST_CUE_S = 2.0

SPEAKER = ">>"
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9']*")
_LETTERS = re.compile(r"[A-Za-z]")
_TAG = re.compile(r"\[[^\]]*\]")
_SENTENCE_END = re.compile(r"[.?!][\"'”’)\]]*\s*$")
#: Where a word starts a sentence inside a line: after `.?!` (and any closing
#: quote), or after the dash an inline speaker marker became.
_SENTENCE_BREAK_BEFORE = re.compile(r"(?:[.?!][\"'”’)\]]*|—)\s+$")
_I_FORMS = {"i", "i'm", "i'll", "i'd", "i've"}
#: W31e: a title's full stop is not a sentence end, so the word after it is a
#: name and not a sentence start — *"Thank you, Dr. Phillips."* (the first live
#: `explain` run glossed *phillips*). Read by `proper_forms` only, so the line
#: breaking and `_starts_sentence` are unchanged; the display gains the name
#: where a shouted line holds it mid-sentence, which is C1's own intent.
_TITLE_BEFORE = re.compile(r"(?:^|[\s(\"'“‘])(?:mr|mrs|ms|dr|prof)\.\s+$", re.IGNORECASE)


@dataclass(frozen=True)
class Line:
    """One display line. `start`/`end` are None for an untimed sentence."""

    start: float | None
    end: float | None
    text: str
    speaker_change: bool = False

    def wire(self) -> dict:
        return {"start": self.start, "end": self.end, "text": self.text}


@dataclass
class Derivation:
    """The lines, and what it took to make them — the `--report`'s numbers."""

    lines: list[Line]
    duplicates_stripped: int = 0
    breaks: dict[str, int] = field(
        default_factory=lambda: {"speaker": 0, "sentence": 0, "silence": 0, "cap": 0}
    )
    merged: int = 0


# ── the cleaning ─────────────────────────────────────────────────────────────


def _words(text: str) -> list[str]:
    return _WORD.findall(_TAG.sub(" ", text))


def _is_caps(word: str) -> bool:
    return bool(_LETTERS.search(word)) and word.upper() == word and word.lower() != word


def _caps_runs(text: str) -> list[list[re.Match]]:
    """Maximal runs of ALL-CAPS words outside tags. A run qualifies with ≥2
    words, at least one of them ≥2 letters — so a lone *TV* or *I* is not one."""
    runs: list[list[re.Match]] = []
    current: list[re.Match] = []
    masked = _TAG.sub(lambda m: " " * len(m.group(0)), text)
    for match in _WORD.finditer(masked):
        if _is_caps(match.group(0)):
            current.append(match)
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)
    return [
        run for run in runs
        if len(run) >= 2 and any(len(_LETTERS.findall(m.group(0))) >= 2 for m in run)
    ]


def _starts_sentence(text: str, index: int) -> bool:
    before = text[:index]
    return not before.strip() or bool(_SENTENCE_BREAK_BEFORE.search(before))


def proper_forms(texts: Iterable[str]) -> dict[str, str]:
    """casefold → the form a word takes in MIXED-CASE text, mid-sentence.

    Read from the whole transcript, so *PETER* in a shouted line becomes
    *Peter* because the same video says *Peter* elsewhere (C1). A word that is
    capitalised only at a sentence start (*So we left*) is not a name; a word
    also seen in lowercase is ambiguous and left out (*Will* / *will*).
    """
    seen: dict[str, str] = {}
    lower: set[str] = set()
    for raw in texts:
        text = raw.replace(SPEAKER, ".")
        # By position, never by `id()` of a match object: a first draft keyed
        # on `id(match)` from a separate `finditer`, and CPython reuses the ids
        # of freed objects, so real names were dropped at random — found when a
        # whole-transcript fixture came back with no names at all.
        run_spans = [(run[0].start(), run[-1].end()) for run in _caps_runs(text)]
        masked = _TAG.sub(lambda m: " " * len(m.group(0)), text)
        for match in _WORD.finditer(masked):
            if any(a <= match.start() < b for a, b in run_spans):
                continue
            word = match.group(0)
            key = word.casefold()
            if key in _I_FORMS:
                continue
            if word == word.lower():
                lower.add(key)
                continue
            letters = len(_LETTERS.findall(word))
            titled = word[0].isupper() and word[1:] == word[1:].lower()
            if (
                titled
                and _starts_sentence(masked, match.start())
                and not _TITLE_BEFORE.search(masked[: match.start()])
            ):
                continue
            if titled or (_is_caps(word) and letters >= 2):
                seen.setdefault(key, word)
    return {k: v for k, v in seen.items() if k not in lower}


def names_for(raw_cues: Sequence[Mapping] | None, transcript: str | None) -> frozenset[str]:
    """One video's names, casefolded — **the C1 set, from the text the lines use.**

    The same `proper_forms` over the same text `lines_for` / `sentences_for`
    read: the cues when there are usable ones, else the transcript. W31e: the
    gloss planner and `WORD_GLOSS_JOB` skip these, so a name costs no call
    (*phillips*, the first live run). One rule for the display and the planner,
    never a second.
    """
    cues = normalise_cues(raw_cues) if raw_cues else None
    if cues:
        return frozenset(proper_forms(c["text"] for c in cues))
    if transcript and transcript.strip():
        return frozenset(proper_forms([transcript]))
    return frozenset()


def clean(text: str, proper: Mapping[str, str]) -> str:
    """The display form of one line's text. **Display only.**"""
    out = text
    for run in reversed(_caps_runs(out)):
        pieces: list[tuple[int, int, str]] = []
        for match in run:
            word = match.group(0)
            key = word.casefold()
            if key in proper:
                new = proper[key]
            elif key in _I_FORMS:
                new = "I" + key[1:]
            else:
                new = word.lower()
            if _starts_sentence(out, match.start()):
                new = new[0].upper() + new[1:]
            pieces.append((match.start(), match.end(), new))
        for start, end, new in reversed(pieces):
            out = out[:start] + new + out[end:]
    return re.sub(r"\s+", " ", out).strip()


def _strip_markers(text: str) -> tuple[str, bool, bool]:
    """`(text, leading_marker, inner_marker)` with every `>>` removed from view."""
    stripped = text.strip()
    leading = stripped.startswith(SPEAKER)
    while stripped.startswith(SPEAKER):
        stripped = stripped[len(SPEAKER):].lstrip()
    inner = SPEAKER in stripped
    stripped = re.sub(r"\s*>>\s*", " — ", stripped)
    return re.sub(r"\s+", " ", stripped).strip(), leading, inner


# ── the grouping ─────────────────────────────────────────────────────────────


def _strip_repeated_edge(previous: str, current: str) -> tuple[str, bool]:
    prev_words = previous.split()
    cur_words = current.split()
    for k in range(min(len(prev_words), len(cur_words)), 1, -1):
        if [w.casefold() for w in prev_words[-k:]] == [w.casefold() for w in cur_words[:k]]:
            return " ".join(cur_words[k:]), True
    return current, False


def derive(raw_cues: Sequence[Mapping] | None) -> Derivation:
    """The lines for a stored cue list, with the counts `--report` prints."""
    cues = normalise_cues(raw_cues) if raw_cues else None
    if not cues:
        return Derivation(lines=[])

    proper = proper_forms(c["text"] for c in cues)
    result = Derivation(lines=[])

    # Each cue's own end: the next start (the overlap is in `duration` only).
    ends: list[float] = []
    for i, c in enumerate(cues):
        if i + 1 < len(cues):
            ends.append(cues[i + 1]["start"])
        else:
            ends.append(c["start"] + c.get("duration", DEFAULT_LAST_CUE_S))

    groups: list[dict] = []
    current: dict | None = None
    previous_raw: str | None = None

    def flush() -> None:
        nonlocal current
        if current and current["texts"]:
            groups.append(current)
        current = None

    for i, c in enumerate(cues):
        text, leading, inner = _strip_markers(c["text"])
        if previous_raw is not None:
            text, stripped = _strip_repeated_edge(previous_raw, text)
            result.duplicates_stripped += int(stripped)
        previous_raw = _strip_markers(c["text"])[0]
        if not text:
            continue

        words = len(_words(text))
        speaker = leading or inner
        silence = False
        if i > 0 and "duration" in cues[i - 1]:
            gap = c["start"] - (cues[i - 1]["start"] + cues[i - 1]["duration"])
            silence = gap > SILENCE_EPSILON_S

        if current is not None:
            reason = None
            if speaker:
                reason = "speaker"
            elif silence:
                reason = "silence"
            elif (
                current["words"] + words > MAX_WORDS
                or ends[i] - current["start"] > MAX_SECONDS
            ):
                reason = "cap"
            if reason:
                result.breaks[reason] += 1
                flush()

        if current is None:
            current = {"start": c["start"], "texts": [], "words": 0, "speaker": speaker}
        current["texts"].append(text)
        current["words"] += words
        current["end"] = ends[i]

        if _SENTENCE_END.search(text):
            result.breaks["sentence"] += 1
            flush()
    flush()

    # Merge short lines forward (or back, when last), never across a speaker.
    merged: list[dict] = []
    i = 0
    while i < len(groups):
        g = groups[i]
        nxt = groups[i + 1] if i + 1 < len(groups) else None
        if g["words"] < MIN_WORDS and nxt is not None and not nxt["speaker"]:
            nxt["texts"] = g["texts"] + nxt["texts"]
            nxt["words"] += g["words"]
            nxt["start"] = g["start"]
            nxt["speaker"] = g["speaker"]
            result.merged += 1
        elif g["words"] < MIN_WORDS and nxt is None and merged and not g["speaker"]:
            merged[-1]["texts"] += g["texts"]
            merged[-1]["words"] += g["words"]
            merged[-1]["end"] = g["end"]
            result.merged += 1
        else:
            merged.append(g)
        i += 1

    for k, g in enumerate(merged):
        end = merged[k + 1]["start"] if k + 1 < len(merged) else g["end"]
        result.lines.append(
            Line(
                start=g["start"],
                end=end,
                text=clean(" ".join(g["texts"]), proper),
                speaker_change=bool(g["speaker"]),
            )
        )
    return result


def lines_for(raw_cues: Sequence[Mapping] | None) -> list[Line]:
    """Timed display lines, or `[]` when there are no usable cues."""
    return derive(raw_cues).lines


def sentences_for(transcript: str | None) -> list[Line]:
    """The no-cue fallback: the transcript as untimed sentences, cleaned.

    Split after `.?!` and at every speaker marker; nothing else. A video with a
    transcript and no cues (none stored, or a track the identity gate refused)
    still shows its text as a list and every word stays tappable.
    """
    if not transcript or not transcript.strip():
        return []
    proper = proper_forms([transcript])
    pieces: list[str] = []
    for turn in re.split(r"\s*>>\s*", transcript):
        pieces.extend(p for p in re.split(r"(?<=[.?!])\s+", turn) if p.strip())
    return [Line(start=None, end=None, text=clean(p, proper)) for p in pieces]


# ── the report (read-only, the operator's Q2 check) ──────────────────────────


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def report(video_id: int, captions_kind: str | None, raw_cues: Sequence[Mapping] | None,
           sample: int = 10) -> str:
    """The derivation's numbers for one video, as text. Reads nothing itself."""
    cues = normalise_cues(raw_cues) if raw_cues else None
    if not cues:
        return f"video {video_id}: no usable cues — the no-cue fallback applies (untimed sentences)"
    overlapping = sum(
        1
        for a, b in zip(cues, cues[1:])
        if "duration" in a and b["start"] < a["start"] + a["duration"]
    )
    d = derive(cues)
    words = [float(len(_words(line.text))) for line in d.lines]
    secs = [float(line.end - line.start) for line in d.lines if line.start is not None]
    out = [
        f"video {video_id} ({captions_kind or 'unknown'}): cues {len(cues)}, "
        f"overlapping pairs {overlapping}",
        f"  lines {len(d.lines)}; repeated edges stripped {d.duplicates_stripped}; "
        f"merged short lines {d.merged}",
        f"  breaks: speaker {d.breaks['speaker']}, sentence {d.breaks['sentence']}, "
        f"silence {d.breaks['silence']}, cap {d.breaks['cap']}",
        f"  words per line: p50 {_pct(words, 0.5):.0f}, p90 {_pct(words, 0.9):.0f}, "
        f"max {max(words):.0f}",
        f"  seconds per line: p50 {_pct(secs, 0.5):.1f}, p90 {_pct(secs, 0.9):.1f}, "
        f"max {max(secs):.1f}, mean {statistics.fmean(secs):.1f}",
        f"  the first {min(sample, len(d.lines))} lines:",
    ]
    for line in d.lines[:sample]:
        out.append(f"    [{line.start:7.2f}–{line.end:7.2f}] {line.text}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true", required=True,
                        help="print the derivation's numbers (read-only)")
    parser.add_argument("--video", type=int, required=True, action="append",
                        help="a videos.id; repeat for several")
    parser.add_argument("--sample", type=int, default=10,
                        help="how many derived lines to print per video")
    args = parser.parse_args(argv)

    from core.db import connection
    from core.services import video as video_service  # the SQL lives there

    with connection() as conn:
        for video_id in args.video:
            row = video_service.cues_for_report(conn, video_id)
            if row is None:
                print(f"video {video_id}: no such video")
                continue
            print(report(video_id, row["captions_kind"], row["transcript_cues"], args.sample))
    return 0


if __name__ == "__main__":
    sys.exit(main())
