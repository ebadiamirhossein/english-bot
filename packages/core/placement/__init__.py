"""W18 — the placement test. PRD §6.

    ladder.py       the adaptive grammar ladder (pure)
    scoring.py      the vocabulary estimate, the bands, what the learner is shown (pure)
    pseudowords.py  pronounceable non-words for the yes/no section (pure)
    targets.py      what the bank asks the generator for, and the speaking prompts
    bank.py         `python -m core.placement.bank` — builds the bank; dry by default
    speaking.py     the speaking rubric's request, and the shape of its answer
    speaking_probe.py  §3 rule 2's probe for that request; dry by default

**No SQL here** (CLAUDE.md §2): `core.services.placement` owns every query.

**THE BANK IS GENERATED AND UNCALIBRATED** (build run 2, ruling 0.1). Every band
this package computes is an uncalibrated reading of an uncalibrated instrument;
the thresholds are named where they are declared, with their source, so a later
calibration changes numbers and not structure.
"""

#: The bands the instrument reads, lowest first. PRD §6: *"adaptive over an
#: A2–C1 bank"*. Nothing below A2 or above C1 is claimed.
BANDS: tuple[str, ...] = ("A2", "B1", "B2", "C1")

#: What the data says about every row this slice writes (ruling 0.1).
CALIBRATION = "uncalibrated"


def band_index(band: str) -> int:
    """Position in `BANDS`. Raises on anything else."""
    return BANDS.index(band)
