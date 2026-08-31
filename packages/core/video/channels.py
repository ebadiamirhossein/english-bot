"""Read and validate `data/video_channels.json`. Pure: no SQL, no HTTP, no model.

The single door to the channel pool, for the reason
`core/lexicon/normalize.py` is the single door to the lexicon data files: a
second parser is a second answer.

**Nothing here fills in a missing value.** An entry without a resolved channel
id, or without an authored accent, is REFUSED and named -- it is not defaulted,
not guessed and not silently dropped. A dropped entry would show up later as a
pool that is quietly one channel smaller, which is the shape of defect this
slice exists downstream of.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CHANNELS_FILE = DATA_DIR / "video_channels.json"

#: Two values, by operator ruling (2026-08-30). Kept in step with migration
#: 019's CHECK constraint; adding a third is a change to both and to nothing
#: else -- no selection logic moves.
ACCENTS = frozenset({"american", "british"})

#: The vocabulary of `users.track_weights` (migration 012), so `topic_match`
#: compares like with like rather than translating between two spellings.
TRACKS = frozenset({"life", "curiosity", "work"})

_REQUIRED = ("handle", "channel_id", "name", "accent", "track", "why")


@dataclass(frozen=True, slots=True)
class Channel:
    """One pollable channel. Every field is authored; none is inferred."""

    channel_id: str
    handle: str
    name: str
    accent: str
    track: str
    why: str


@dataclass(frozen=True, slots=True)
class Refusal:
    """An entry that cannot be polled, and the reason, in the file's own terms."""

    handle: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.handle}: {self.reason}"


@dataclass(frozen=True, slots=True)
class Pool:
    """What loaded, and what did not.

    Both halves are returned together on purpose. A loader that returned only
    the usable channels would let the pool shrink without anybody being told,
    and the caller is required to print `refusals` rather than to consult them
    at its discretion.
    """

    channels: tuple[Channel, ...]
    refusals: tuple[Refusal, ...]

    @property
    def is_empty(self) -> bool:
        return not self.channels


class ChannelFileError(Exception):
    """The file itself is unreadable or malformed. Not a per-entry refusal."""


def load(path: Path | None = None) -> Pool:
    """Parse the channel pool.

    ``path`` names the file to read; the default is the committed one. The
    parameter exists so a test can supply a constructed file without touching
    the real pool -- and so the real pool can still be the thing the default
    test reads, which is what makes `test_every_channel_declares_an_accent_and_a_track`
    a check on production data rather than on a fixture.
    """
    source = path or CHANNELS_FILE
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChannelFileError(f"no channel pool at {source}") from exc
    except json.JSONDecodeError as exc:
        raise ChannelFileError(f"{source} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("channels"), list):
        raise ChannelFileError(
            f"{source} must be an object with a `channels` array"
        )

    channels: list[Channel] = []
    refusals: list[Refusal] = []
    seen_ids: dict[str, str] = {}

    for index, entry in enumerate(raw["channels"]):
        handle = str(entry.get("handle") or f"<entry {index}>")
        reason = _refuse(entry, seen_ids)
        if reason is not None:
            refusals.append(Refusal(handle=handle, reason=reason))
            continue
        seen_ids[entry["channel_id"]] = handle
        channels.append(
            Channel(
                channel_id=entry["channel_id"],
                handle=entry["handle"],
                name=entry["name"],
                accent=entry["accent"],
                track=entry["track"],
                why=entry["why"],
            )
        )

    return Pool(channels=tuple(channels), refusals=tuple(refusals))


def _refuse(entry: object, seen_ids: dict[str, str]) -> str | None:
    """Return why this entry cannot be polled, or None if it can."""
    if not isinstance(entry, dict):
        return "not an object"

    missing = [key for key in _REQUIRED if key not in entry]
    if missing:
        return f"missing key(s): {', '.join(missing)}"

    channel_id = entry["channel_id"]
    if channel_id is None:
        return (
            "channel_id is null -- run `python -m core.video.resolve_channels` "
            "and paste the real id. It is NOT filled in by guessing"
        )
    if not isinstance(channel_id, str) or not channel_id.strip():
        return f"channel_id must be a non-empty string (got {channel_id!r})"
    # The check that catches the actual mistake. A handle looks enough like an
    # id to survive a code review and is rejected by the API, which would
    # surface as a mysterious empty poll rather than as a bad value.
    if channel_id.startswith("@"):
        return (
            f"channel_id is a handle ({channel_id!r}), not a channel id. "
            "Handles change; ids do not"
        )
    if channel_id in seen_ids:
        return f"duplicate channel_id, already used by {seen_ids[channel_id]}"

    accent = entry["accent"]
    if accent is None:
        return (
            "accent is null -- it is AUTHORED on the channel, never detected "
            "from a video, and authoring it means knowing it"
        )
    if accent not in ACCENTS:
        return (
            f"accent must be one of {sorted(ACCENTS)} (got {accent!r}). "
            "A third accent is a change to this file and to migration 019's "
            "CHECK, and to nothing else"
        )

    track = entry["track"]
    if track not in TRACKS:
        return (
            f"track must be one of {sorted(TRACKS)} (got {track!r}) -- the "
            "vocabulary of users.track_weights, migration 012"
        )

    if not str(entry["why"] or "").strip():
        return "why is empty -- every channel in the pool says why it is there"

    return None
