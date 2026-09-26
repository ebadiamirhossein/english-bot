"""Scoring a sitting, and what a learner is shown of it. **Pure.**

**A placement is never shown as a score.** It is shown as *where to start* — a
CEFR band, with no percentage anywhere, on the wire or on the screen (the build
run's rule). The per-skill radar is drawn in bands too.

**Raises are announced, drops are silent (CLAUDE.md §4).** Every figure a
learner sees is the HIGH-WATER mark across their finished sittings — W19's XP
precedent (029): a monthly re-run that reads lower changes nothing on screen,
and one that reads higher is said out loud. The measured values are all kept on
`placement_runs` for the record; only what is SHOWN is held.

**UNCALIBRATED (ruling 0.1).** Every threshold below names its source. None has
been checked against these learners' results, because there are none yet.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from core.placement import BANDS

# ── the vocabulary section ──────────────────────────────────────────────────

#: PRD §6: *"40 real words sampled across frequency bands + 20 pseudowords"*.
#: Ten bands of a thousand ranks (`lexemes.freq_rank` 1–10,000), four words each.
VOCAB_BANDS = 10
BAND_SIZE = 1000
REAL_PER_BAND = 4
PSEUDO_PER_SITTING = 20

#: Above this rate of "yes" to non-words, the section is not read at all: the
#: learner was saying yes to everything, and a correction for guessing cannot
#: recover a size from that. **Nothing is written to the floor and nothing is
#: shown**; the sitting still gives its other bands.
FALSE_ALARM_LIMIT = 0.5

#: Vocabulary size → band. **Source: Milton (2010), *The development of
#: vocabulary breadth across the CEFR levels*, X-Lex figures (A2 ≈ 1,500–2,500,
#: B1 ≈ 2,750–3,250, B2 ≈ 3,250–3,750, C1 ≈ 3,750–4,500).** Our estimate reads a
#: 10,000-word range where X-Lex read 5,000, so above ~5,000 this is a clamp to
#: C1, not a claim of C2. Below 2,500 reads A2: the instrument claims nothing
#: lower.
VOCAB_THRESHOLDS: tuple[tuple[int, str], ...] = ((3750, "C1"), (3250, "B2"), (2500, "B1"))


def vocab_band_of(rank: int) -> int:
    """Which of the ten frequency bands a rank falls in, 0-based."""
    if rank < 1 or rank > VOCAB_BANDS * BAND_SIZE:
        raise ValueError(f"rank {rank} is outside 1–{VOCAB_BANDS * BAND_SIZE}")
    return (rank - 1) // BAND_SIZE


def vocabulary_estimate(
    real: Iterable[tuple[int, bool]], pseudo: Iterable[bool]
) -> int | None:
    """Words known, from ``(freq_rank, said yes)`` on the real words and
    ``said yes`` on the pseudo-words. ``None`` when it cannot be read.

    Per band: the hit rate, corrected for guessing by the false-alarm rate
    ``f`` — ``(h - f) / (1 - f)``, floored at 0 — times the band's thousand
    words. Summed, and rounded to the nearest hundred (PRD §6's *±300* is the
    honest precision; a figure to the unit would claim more).
    """
    pseudo = list(pseudo)
    if not pseudo:
        return None
    f = sum(pseudo) / len(pseudo)
    if f > FALSE_ALARM_LIMIT:
        return None
    hits: dict[int, list[bool]] = {}
    for rank, yes in real:
        hits.setdefault(vocab_band_of(rank), []).append(yes)
    if not hits:
        return None
    total = 0.0
    for answers in hits.values():
        h = sum(answers) / len(answers)
        total += max(0.0, (h - f) / (1 - f)) * BAND_SIZE
    return int(round(total / 100.0)) * 100


def vocabulary_band(estimate: int | None) -> str | None:
    if estimate is None:
        return None
    for threshold, band in VOCAB_THRESHOLDS:
        if estimate >= threshold:
            return band
    return BANDS[0]


# ── the listening section ───────────────────────────────────────────────────

#: PRD §6: *"6 short clips, increasing"* in difficulty. The sitting serves them
#: in this band order, so a count of right answers reads as how far up the
#: order the learner kept up.
LISTENING_ORDER: tuple[str, ...] = ("A2", "B1", "B1", "B2", "B2", "C1")


def listening_band(answers: Sequence[bool], *, served: Sequence[str]) -> str | None:
    """Right answers as a share of the clips served → a band.

    Under a third A2, under two thirds B1, all but full B2, every one C1 — on
    six clips: 0–1, 2–3, 4–5, 6. ``None`` when no clip was served.

    **Never above the highest band a clip was served at** (``served``: each
    clip's band; launch 2026-09-26, B2). A sitting that skipped an empty C1
    cell and got its five clips right read C1 — a band it never asked about.
    Keyword-only and required, so no caller can forget it.
    """
    if not answers:
        return None
    share = sum(answers) / len(answers)
    if share >= 1:
        band = "C1"
    elif share * 3 >= 2:
        band = "B2"
    elif share * 3 >= 1:
        band = "B1"
    else:
        band = "A2"
    ceiling = max(served, key=BANDS.index, default=BANDS[0])
    return min(band, ceiling, key=BANDS.index)


# ── what the learner is shown ───────────────────────────────────────────────

#: The radar's axes, in drawing order. **PRD §6 names five: listening, reading,
#: grammar, production, pronunciation.** The instrument measures four skills and
#: they are drawn under their own names. **Reading and pronunciation are NOT
#: drawn and are reported unmet**: the bank has no reading section, and
#: pronunciation needed the Azure assessment that was retired (`speech_api.py`).
SKILLS: tuple[str, ...] = ("vocabulary", "grammar", "listening", "speaking")

#: A new sitting is offered this many days after the last one finished. PRD §6:
#: *"Re-run monthly"*.
RETEST_DAYS = 28


@dataclass(frozen=True, slots=True)
class Sitting:
    """One finished sitting, as measured."""

    finished_on: date
    cefr: str
    bands: dict[str, str | None]
    vocab_estimate: int | None = None


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    finished_on: date
    #: The band as SHOWN after this sitting: the high-water mark so far.
    band: str


@dataclass(frozen=True, slots=True)
class Shown:
    """Everything a learner sees of their placements. **Bands; no percentage.**"""

    where_to_start: str
    radar: dict[str, str | None]
    history: tuple[HistoryPoint, ...]
    vocab_estimate: int | None
    #: The band the latest sitting RAISED the learner from, when it did. None
    #: otherwise — a sitting that read the same or lower says nothing.
    raised_from: str | None = None
    #: Skills the latest sitting raised on the radar.
    raised_skills: tuple[str, ...] = field(default_factory=tuple)


def _higher(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if BANDS.index(a) >= BANDS.index(b) else b


def shown(sittings: Sequence[Sitting]) -> Shown | None:
    """The high-water view of ``sittings`` (oldest first). None when there are
    none."""
    if not sittings:
        return None
    best: str | None = None
    radar: dict[str, str | None] = {s: None for s in SKILLS}
    vocab: int | None = None
    history: list[HistoryPoint] = []
    before_best: str | None = None
    before_radar: dict[str, str | None] = dict(radar)
    for n, sitting in enumerate(sittings):
        if n == len(sittings) - 1:
            before_best, before_radar = best, dict(radar)
        best = _higher(best, sitting.cefr)
        for skill in SKILLS:
            radar[skill] = _higher(radar[skill], sitting.bands.get(skill))
        if sitting.vocab_estimate is not None:
            vocab = max(vocab or 0, sitting.vocab_estimate)
        history.append(HistoryPoint(sitting.finished_on, best))
    assert best is not None
    raised_from = (
        before_best
        if before_best is not None and BANDS.index(best) > BANDS.index(before_best)
        else None
    )
    raised_skills = tuple(
        s for s in SKILLS
        if before_radar[s] is not None and radar[s] is not None
        and BANDS.index(radar[s]) > BANDS.index(before_radar[s])
    ) if len(sittings) > 1 else ()
    return Shown(best, radar, tuple(history), vocab, raised_from, raised_skills)


def next_sitting_from(last_finished: date | None) -> date | None:
    """The first day a new sitting is offered. None: offered now (never sat)."""
    if last_finished is None:
        return None
    from datetime import timedelta

    return last_finished + timedelta(days=RETEST_DAYS)
