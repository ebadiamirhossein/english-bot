"""P0a — the owed rule-2 real call, and the S2 sample-rate question, in one run.

**CLAUDE.md §3 rule 2: any change to `speech.py` request construction requires
one real API call before shipping.** W14 adds a new provider, so it fires. **On
Azure's Free (F0) tier the call costs nothing**, so there is no reason to defer
it and every reason to make it a stop point: the pronunciation-assessment
response shape is the one thing in this slice no test can establish from our
side, and a mock built from a guessed shape is a mocked suite passing over a
malformed request.

**THIS RUN ANSWERS TWO QUESTIONS, NOT ONE, AND THE SECOND ONE MAY DELETE A
DESIGN PROBLEM.**

1. **The response shape.** Recorded verbatim to a fixture; the parser is written
   against the recording, never against this file's assumptions.
2. **S2 / #362 — does Azure accept the phone's NATIVE sample rate?** The two
   learners' phones emit 48 kHz. If 48 kHz is accepted, **the browser needs no
   resample at all**, `OfflineAudioContext`'s WebKit refusal stops mattering,
   and #362 closes on evidence rather than on a workaround. The probe sends the
   same utterance twice -- once at its native rate, once downsampled to 16 kHz --
   and reports which the provider accepted.

**WHOSE VOICE.** §1c's four data-processing questions are unanswered, so **this
runs on a synthetic or operator-owned recording and never on the other
learner's voice.** That is a rule, not a preference: a data question answered
after the data has been sent is not an answer.

**NO AUDIO IS WRITTEN.** The probe reads one WAV the operator already made and
writes only JSON. It never copies, caches or re-encodes to disk -- the same rule
the scored path holds, held here too so the probe cannot be the exception that
proves the instrument wrong.

Usage -- **dry by default; `--live` is what makes the call**::

    python -m core.speech_probe --wav ~/shadow.wav --text "I'll grab a coffee first."
    python -m core.speech_probe --wav ~/shadow.wav --text "I'll grab a coffee first." --live
"""

from __future__ import annotations

import argparse
import array
import io
import json
import logging
import sys
import wave
from pathlib import Path

from core import speech
from core.config import load_settings

logger = logging.getLogger(__name__)

#: Where a recorded response lands. The parser is written against these files.
DEFAULT_OUT_DIR = Path("tests/fixtures/azure_pronunciation")

TARGET_RATE_HZ = 16000


def read_wav_mono16(path: Path) -> tuple[array.array, int]:
    """Read a WAV into 16-bit mono samples plus its rate. **In memory only.**

    Refuses rather than repairs anything it does not understand: a probe that
    silently converted an unexpected input would answer a question about the
    conversion instead of about the provider.
    """
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise SystemExit(f"need 16-bit PCM WAV, got {width * 8}-bit")
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    if channels > 1:
        # Downmix by averaging, the same thing the browser's decode step does.
        mixed = array.array("h")
        for i in range(0, len(samples) - channels + 1, channels):
            mixed.append(int(sum(samples[i : i + channels]) / channels))
        samples = mixed
    return samples, rate


def downsample(samples: array.array, src_rate: int, dst_rate: int) -> array.array:
    """Linear interpolation with a box-average pre-filter.

    **THE PRE-FILTER IS NOT OPTIONAL AND THAT IS THE WHOLE POINT.** Downsampling
    48 kHz to 16 kHz without a low-pass stage ALIASES, and aliasing on a
    pronunciation scorer produces a WRONG score rather than a rough one -- a
    fricative folded down into the vowel band is not noise, it is a different
    sound. So the box average runs first even though it costs a line.

    **This is deliberately the SAME algorithm the browser fallback uses** if P0b
    finds `OfflineAudioContext` refuses 16 kHz on Safari (#362). Writing it here
    means the fallback is exercised by a real provider call before it is ever
    written in TypeScript.
    """
    if src_rate == dst_rate:
        return samples
    if src_rate < dst_rate:
        raise SystemExit(f"refusing to upsample {src_rate} -> {dst_rate}")
    ratio = src_rate / dst_rate
    width = max(1, int(ratio))
    out = array.array("h")
    n = len(samples)
    i = 0.0
    while int(i) < n:
        start = int(i)
        stop = min(n, start + width)
        out.append(int(sum(samples[start:stop]) / (stop - start)))
        i += ratio
    return out


def to_wav_bytes(samples: array.array, rate: int) -> bytes:
    """Wrap samples in a WAV container **in memory**. Never touches the disk."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        payload = array.array("h", samples)
        if sys.byteorder == "big":
            payload.byteswap()
        handle.writeframes(payload.tobytes())
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "P0a: one free Azure pronunciation-assessment call, at the native "
            "rate and at 16 kHz. Dry by default."
        )
    )
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Make the real call. Without it nothing leaves this machine.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()

    samples, native_rate = read_wav_mono16(args.wav)
    seconds = len(samples) / native_rate
    native_bytes = to_wav_bytes(samples, native_rate)
    resampled = downsample(samples, native_rate, TARGET_RATE_HZ)
    target_bytes = to_wav_bytes(resampled, TARGET_RATE_HZ)

    # The region is read but never printed: no region literal reaches a log, a
    # terminal capture, or this repository.
    # W14r: `Settings` no longer carries these, so this reads MISSING and the
    # probe refuses at `--live`. The script stays as the record of how the
    # provider was measured (#376), and it can no longer reach it.
    configured = bool(
        getattr(settings, "azure_speech_key", "")
        and getattr(settings, "azure_speech_region", "")
    )
    print(f"reference text : {args.text!r}")
    print(f"duration       : {seconds:.2f}s")
    print(f"native rate    : {native_rate} Hz, {len(native_bytes)} bytes")
    print(f"target rate    : {TARGET_RATE_HZ} Hz, {len(target_bytes)} bytes")
    print(f"credentials    : {'present' if configured else 'MISSING'}")

    if not args.live:
        print("\nDRY RUN — no call was made and nothing left this machine.")
        print("Re-run with --live to record the response.")
        return 0
    if not configured:
        print("\nREFUSING: AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not both set.")
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    for label, payload, rate in (
        ("native", native_bytes, native_rate),
        ("16k", target_bytes, TARGET_RATE_HZ),
    ):
        print(f"\n--- {label} ({rate} Hz) ---")
        try:
            response = speech.assess_pronunciation(
                payload, args.text, sample_rate_hz=rate, settings=settings
            )
        except speech.SpeechQuotaExceeded as exc:
            results[label] = f"REFUSED: {exc}"
            print(f"refused: {exc}")
            continue
        except speech.SpeechError as exc:
            results[label] = f"ERROR: {exc}"
            print(f"error: {exc}")
            continue
        destination = args.out / f"assess_{label}_{rate}.json"
        destination.write_text(
            json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        results[label] = f"ACCEPTED -> {destination}"
        print(f"accepted; recorded verbatim to {destination}")

    print("\n=== P0a RESULT ===")
    for label, outcome in results.items():
        print(f"{label:>7}: {outcome}")
    print(
        "\nIf 'native' was ACCEPTED, the browser needs NO resample: §1c's 16 kHz\n"
        "normalisation is dropped, P0b is unnecessary, and #362 closes on this\n"
        "evidence. If only '16k' was accepted, run P0b on both phones next."
    )
    print(
        "\nThe recorded JSON is the parser's only source. If its shape differs\n"
        "from the plan's assumption, the plan is wrong and says so."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI
    raise SystemExit(main())
