"""The speaking item's rubric: one billed call that places an answer in a band.

PRD §6: *"One prompt, free response, recorded. Scored by (a) Azure
pronunciation assessment … and (b) an LLM rubric against CEFR descriptors for
range, coherence, and accuracy."* **(a) is NOT done and is reported unmet**: the
Azure client was retired (`core/speech_api.py`), and there is no pronunciation
axis on the radar. **(b) is this module.**

**The answer is placed in the request and discarded (CLAUDE.md §5).** The
transcript — or the typed fallback — is held in memory for one call; only the
band survives, on `placement_runs.speaking_band`. The rubric's descriptors are
this project's own wording, not the CEFR's published descriptor text.

**`speaking_request` is the whole request, in one place** — the service calls
it, and `core.placement.speaking_probe` prints it, so the probe cannot print a
request production does not send (W15's `rung_request` shape).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.placement import BANDS

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "placement_speaking.txt"
#: The reply is two keys. Room for a model that pads, none for an essay.
MAX_TOKENS = 200
#: Ninety seconds of speech is ~250 words; a paste past this is not a spoken
#: answer, and the cut keeps a runaway typed fallback from buying a long call.
MAX_CHARS = 4000


def speaking_request(prompt_text: str, answer: str) -> dict[str, Any]:
    """The request the rubric sends. The answer is fenced as data (§6)."""
    from core.services.correction import wrap_user_text

    fenced = wrap_user_text(answer.strip()[:MAX_CHARS])
    return {
        "messages": [
            {"role": "user", "content": f"<prompt>\n{prompt_text}\n</prompt>\n\n{fenced}"}
        ],
        "system": PROMPT.read_text(encoding="utf-8"),
        "json_mode": True,
        "max_tokens": MAX_TOKENS,
        "reject_truncation": True,
    }


def band_from(raw: Any) -> str | None:
    """The rubric's answer, gated. **Anything off-shape is `None` — unplaced —
    and never a guess**: a band the model did not give is a band nobody
    measured."""
    if not isinstance(raw, dict):
        return None
    if raw.get("is_english") is False:
        return None
    band = raw.get("band")
    return band if isinstance(band, str) and band in BANDS else None


def place(prompt_text: str, answer: str, *, chat=None) -> str | None:
    """One billed call → a band, or ``None``. ``chat`` is the seam tests replace
    (it defaults to `core.llm.chat`, the only door to the provider)."""
    if not answer.strip():
        return None
    if chat is None:
        from core.llm import chat
    request = speaking_request(prompt_text, answer)
    raw = chat(
        request["messages"], system=request["system"], json_mode=request["json_mode"],
        max_tokens=request["max_tokens"], reject_truncation=request["reject_truncation"],
    )
    return band_from(raw)
