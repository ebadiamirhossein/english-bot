"""W14 test 4 — **no audio path may write to the filesystem, proved from source.**

────────────────────────────────────────────────────────────────────────────────
WHY THIS TEST EXISTS AT ALL, AND WHY IT IS THE ONE THAT SURVIVES

W14's acceptance is *no audio file exists on disk after the request*. Asking
what asserted that BEFORE W14 gave the answer **nothing** (#360): `speech.py`'s
docstring says *Audio never touches the filesystem*, `diary.py:4` says *Full
transcript discarded*, three live Telegram handlers rely on both, and **a
`tempfile.NamedTemporaryFile` added to any of those paths would pass the entire
suite.**

**THIS IS THE REDUNDANT INSTRUMENT, AND THE REDUNDANCY IS THE DESIGN (S3).**
W14's other two instruments are filesystem snapshots taken around a live
request, and snapshots are the first tests in this suite whose result depends on
what else is running — W13-i/6 already produced that failure once. When a
snapshot flakes, the tempting repair is to narrow what it looks at, and **an
eroded snapshot test stays green while asserting nothing.** This test reads
SOURCE. It cannot flake, it cannot be weakened by a trimmed root, and if the
snapshots are ever narrowed away the rule still has one instrument standing.

**CLAUDE.md §3 rule 4 — a green test over an unreachable path proves nothing.**
The rule has nothing to catch today, so the detector is proved non-inert against
a known offender before it is trusted over the real tree. That is
`test_api.py`'s `_OFFENDING_SOURCE`/`_COMPLIANT_SOURCE` shape, reused rather
than reinvented.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "packages" / "core"

#: Every module an audio byte can pass through on the W14 path.
AUDIO_PATH_MODULES = (
    CORE / "speech.py",
    CORE / "speech_api.py",
    CORE / "services" / "shadow_score.py",
)

#: Names that put bytes on a disk. `open` covers the builtin and every
#: `io.open` alias; the rest are the ways around it people actually reach for.
_WRITERS = frozenset(
    {
        "open",
        "NamedTemporaryFile",
        "TemporaryFile",
        "mkstemp",
        "mkdtemp",
        "write_bytes",
        "write_text",
        "copyfile",
        "copyfileobj",
        "copy2",
    }
)
_WRITER_MODULES = frozenset({"tempfile", "shutil", "os"})


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _writes_to_disk(source: str, label: str) -> list[str]:
    """Every filesystem-write call site in `source`, as `label:line name`."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name in _WRITERS:
                found.append(f"{label}:{node.lineno} {name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _WRITER_MODULES and alias.name != "os":
                    found.append(f"{label}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in _WRITER_MODULES and node.module != "os":
                found.append(f"{label}:{node.lineno} from {node.module}")
    return sorted(found)


_OFFENDING_SOURCE = '''
import tempfile


def assess(audio: bytes) -> dict:
    # The exact failure this test exists to catch: a temp file on the way to
    # the provider, or -- worse, because it is easy to miss in review -- one on
    # the ERROR path only.
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(audio)
    return {}
'''

_COMPLIANT_SOURCE = '''
import io


def assess(audio: bytes) -> dict:
    buffer = io.BytesIO(audio)
    return {"bytes": buffer.getbuffer().nbytes}
'''


def test_the_disk_detector_actually_detects() -> None:
    """The rule has nothing to catch yet, so prove the detector is not inert.

    **Both directions, because a detector that flags everything is as useless as
    one that flags nothing** -- and an in-memory `io.BytesIO`, which is exactly
    what the real code uses, must NOT be flagged. Flagging it would push the
    next author to hide the buffer rather than to keep it in memory.
    """
    assert _writes_to_disk(_OFFENDING_SOURCE, "fake.py") == [
        "fake.py:2 import tempfile",
        "fake.py:9 NamedTemporaryFile",
    ]
    assert _writes_to_disk(_COMPLIANT_SOURCE, "fake.py") == []


def test_no_audio_path_module_writes_to_the_filesystem() -> None:
    offenders: list[str] = []
    for path in AUDIO_PATH_MODULES:
        assert path.exists(), f"audio-path module missing: {path}"
        offenders += _writes_to_disk(
            path.read_text(encoding="utf-8"), path.name
        )
    assert offenders == [], (
        "Audio is transcribed or scored and DISCARDED (CLAUDE.md §5, PRD §8). "
        "No module an audio byte passes through may write to disk, on the "
        "success path or the error path: " + "; ".join(offenders)
    )
