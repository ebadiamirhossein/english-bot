"""The one door to YouTube and to the transcript actor. W12b.

**This is the only file in `packages/core` permitted an HTTP client**, and the
exemption is written by name in `tests/test_core_boundary.py` rather than added
quietly to a frozenset. Every other file in core still fails on an `httpx`
import.

The shape is `llm.py`'s and `speech.py`'s, for CLAUDE.md §2's reason: one
declared door per external provider, so swapping the provider is one file and
one environment variable rather than a search across the tree.

THE ALTERNATIVE THAT WAS REJECTED, RECORDED SO IT IS NOT REDISCOVERED AS A GOOD
IDEA: the boundary test forbids `httpx`, `requests` and `aiohttp` by name, so
stdlib `urllib.request` would have passed it while putting an HTTP client in
core anyway. That is #257 exactly -- a scanner enforces the FORM of a claim and
not its truth -- and the test written to prevent this would have stayed green
while the thing it exists to prevent happened.

NOTHING HERE IS CALLED DURING A TEST. `tests/conftest.py` installs a
session-scoped network guard that fails any test opening a socket to a
non-loopback address, so these functions are exercised against recorded actor
output and never against the live services.

BILLING, STATED WHERE THE CALLS ARE:

- The YouTube Data API costs QUOTA, not money -- 10,000 units a day. `channels`,
  `playlistItems` and `videos` list calls are 1 unit each. `search.list` is 100,
  which is why the uploads playlist is walked instead.
- The Apify actor costs MONEY, per video. `list_transcript_kinds` uses the
  actor's `list_only` mode, which the actor documents as **not charged as a
  videoprocessed event** -- that is what makes PRD §7.2's human-captions
  preference verifiable without paying to find out.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
APIFY_API = "https://api.apify.com/v2"

#: The Data API caps a list call at 50 ids.
_YOUTUBE_PAGE = 50
#: The ruled actor caps a run at 250 urls; kept below it deliberately so one
#: failure costs a smaller re-run.
_APIFY_BATCH = 50

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
#: The actor is community-maintained and YouTube challenges datacentre IPs, so a
#: transcript run is given longer than a metadata call before it is called dead.
_ACTOR_TIMEOUT = httpx.Timeout(600.0, connect=15.0)

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?$"
)


class VideoApiError(Exception):
    """Anything this module could not do."""


class TranscriptUnavailable(VideoApiError):
    """TERMINAL. The video has no captions at all; retrying cannot help."""


class TranscriptFetchFailed(VideoApiError):
    """RETRYABLE. The scraper failed, was rate-limited, or was challenged.

    The distinction from `TranscriptUnavailable` is the whole reason the
    refresh path can tell a video worth trying again from one that is not, and
    it is why `videos.transcript_status` has four values rather than two.
    """


@dataclass(frozen=True, slots=True)
class ChannelRef:
    handle: str
    channel_id: str
    title: str
    uploads_playlist_id: str


@dataclass(frozen=True, slots=True)
class VideoMeta:
    youtube_id: str
    title: str
    duration_s: int | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class Transcript:
    youtube_id: str
    text: str
    lang: str | None
    #: 'manual' | 'generated' | None. None means the actor did not report a
    #: kind -- which is filed, never guessed at.
    kind: str | None


# --------------------------------------------------------------------------
# Per-actor adapters.
#
# The honest cost of CLAUDE.md §2's "swapping providers must be one environment
# variable": two actors report the same facts under different names, so the
# difference lives in ONE table rather than in branches scattered through the
# fetch path. An actor with no entry here is called anyway -- config.py warns
# rather than refusing -- and its output is read on the default adapter, which
# reports `kind=None` and so files the caption question rather than inventing an
# answer to it.
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Adapter:
    #: Input key naming the video url(s).
    url_key: str
    #: Input key selecting the caption kind, and the value meaning "human".
    kind_key: str | None
    manual_value: str | None
    #: Input key that turns on the free discovery mode.
    list_only_key: str | None
    #: Output keys, tried in order, for the transcript text and its kind.
    text_keys: tuple[str, ...]
    kind_keys: tuple[str, ...]
    lang_keys: tuple[str, ...]
    #: How the output reports 'this track is auto-generated'.
    generated_truthy: tuple[str, ...] = ("generated", "auto", "asr", "true", "True")


_DEFAULT_ADAPTER = _Adapter(
    url_key="youtube_url",
    kind_key=None,
    manual_value=None,
    list_only_key=None,
    text_keys=("transcript", "text", "non_timestamped", "captions"),
    kind_keys=(),
    lang_keys=("language", "lang", "language_code"),
)

_ADAPTERS: dict[str, _Adapter] = {
    # The actor ruled on 2026-08-31. Its published input schema is the reason it
    # was ruled for: transcript_type selects the caption kind, and list_only
    # reports that kind without being charged.
    "johnvc/YoutubeTranscripts": _Adapter(
        url_key="youtube_url",
        kind_key="transcript_type",
        manual_value="manual",
        list_only_key="list_only",
        text_keys=("non_timestamped", "transcript", "text"),
        kind_keys=("transcript_type", "is_generated", "generated"),
        lang_keys=("language_code", "language", "lang"),
    ),
    # The ruled fallback. Its selector is `subType`.
    "codepoetry/youtube-transcript-ai-scraper": _Adapter(
        url_key="startUrls",
        kind_key="subType",
        manual_value="manual",
        list_only_key=None,
        text_keys=("text", "transcript"),
        kind_keys=("subType", "captionType"),
        lang_keys=("language", "lang"),
    ),
}


def adapter_for(actor: str) -> _Adapter:
    return _ADAPTERS.get(actor, _DEFAULT_ADAPTER)


# --------------------------------------------------------------------------
# YouTube Data API v3. Quota, not money.
# --------------------------------------------------------------------------
def _youtube_get(path: str, params: dict[str, Any], *, api_key: str) -> dict:
    if not api_key:
        raise VideoApiError(
            "YOUTUBE_API_KEY is not set. It lives on production only; this "
            "command cannot run without it and does not run degraded."
        )
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{YOUTUBE_API}/{path}", params={**params, "key": api_key}
        )
    if response.status_code != 200:
        # The key is in `params` and must never reach a log line or an
        # exception message (CLAUDE.md §5).
        raise VideoApiError(
            f"YouTube {path} returned {response.status_code}: "
            f"{response.text[:300]}"
        )
    return response.json()


def resolve_handle(handle: str, *, api_key: str) -> ChannelRef:
    """`@handle` -> channel id + uploads playlist. One quota unit.

    The uploads playlist comes back on the same call, which is why this returns
    it: walking that playlist costs 1 unit per page, where `search.list` costs
    100 per page for the same videos.
    """
    wanted = handle if handle.startswith("@") else f"@{handle}"
    payload = _youtube_get(
        "channels",
        {"part": "id,snippet,contentDetails", "forHandle": wanted},
        api_key=api_key,
    )
    items = payload.get("items") or []
    if not items:
        raise VideoApiError(f"no channel for handle {wanted!r}")
    item = items[0]
    uploads = (
        item.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )
    if not uploads:
        raise VideoApiError(f"{wanted} has no uploads playlist")
    return ChannelRef(
        handle=wanted,
        channel_id=item["id"],
        title=item.get("snippet", {}).get("title", ""),
        uploads_playlist_id=uploads,
    )


def list_channel_videos(
    uploads_playlist_id: str, *, api_key: str, max_videos: int = 30
) -> list[str]:
    """Newest-first video ids from a channel's uploads playlist."""
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_videos:
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": min(_YOUTUBE_PAGE, max_videos - len(ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        payload = _youtube_get("playlistItems", params, api_key=api_key)
        for item in payload.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                ids.append(video_id)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return ids[:max_videos]


def fetch_video_metadata(
    youtube_ids: Sequence[str], *, api_key: str
) -> dict[str, VideoMeta]:
    """Title, duration and publication date. One quota unit per 50 ids."""
    out: dict[str, VideoMeta] = {}
    for batch in _chunks(youtube_ids, _YOUTUBE_PAGE):
        payload = _youtube_get(
            "videos",
            {"part": "snippet,contentDetails", "id": ",".join(batch)},
            api_key=api_key,
        )
        for item in payload.get("items", []):
            video_id = item.get("id")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            out[video_id] = VideoMeta(
                youtube_id=video_id,
                title=snippet.get("title", ""),
                duration_s=parse_iso8601_duration(
                    item.get("contentDetails", {}).get("duration")
                ),
                published_at=_parse_rfc3339(snippet.get("publishedAt")),
            )
    return out


def parse_iso8601_duration(value: str | None) -> int | None:
    """`PT12M34S` -> 754. None when absent or unparseable, never a guess.

    A live stream reports `P0D` with no time part; that is not a duration and is
    returned as None rather than as zero, so `length_fit` scores it 0 for being
    unknown rather than 0 for being instantaneous.
    """
    if not value:
        return None
    match = _ISO_DURATION.match(value)
    if not match:
        return None
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    total = (
        parts["days"] * 86400
        + parts["h"] * 3600
        + parts["m"] * 60
        + parts["s"]
    )
    return total or None


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Apify. Money.
# --------------------------------------------------------------------------
def _run_actor(
    actor: str, payload: dict[str, Any], *, token: str, timeout: httpx.Timeout
) -> list[dict]:
    """Run an actor synchronously and return its dataset items."""
    if not token:
        raise VideoApiError(
            "APIFY_TOKEN is not set. It lives on production only; this command "
            "cannot run without it and does not run degraded."
        )
    endpoint = f"{APIFY_API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint, params={"token": token}, json=payload
            )
    except httpx.HTTPError as exc:
        # A transport failure is retryable by construction: nothing about the
        # video is known to be wrong.
        raise TranscriptFetchFailed(f"actor {actor} transport error: {exc}") from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise TranscriptFetchFailed(
            f"actor {actor} returned {response.status_code} -- retryable"
        )
    if response.status_code >= 400:
        raise VideoApiError(
            f"actor {actor} returned {response.status_code}: {response.text[:300]}"
        )
    items = response.json()
    return items if isinstance(items, list) else []


def list_transcript_kinds(
    youtube_ids: Sequence[str], *, token: str, actor: str
) -> dict[str, str | None]:
    """Which caption kinds each video has, WITHOUT paying for a transcript.

    Returns `youtube_id -> 'manual' | 'generated' | None`, where None means the
    actor reported no kind for it. **None is filed, never treated as
    'generated'** -- an absent field and an auto-generated track are different
    facts, and #257's lesson is that a column must not claim to hold a kind it
    is guessing.

    An actor with no `list_only` mode returns an empty mapping rather than
    silently falling back to a paid call.
    """
    adapter = adapter_for(actor)
    if adapter.list_only_key is None:
        logger.warning(
            "actor %s has no free discovery mode; caption kinds are unknown "
            "until a transcript is fetched, and PRD §7.2's human-captions "
            "preference cannot be checked before paying",
            actor,
        )
        return {}

    kinds: dict[str, str | None] = {}
    for batch in _chunks(youtube_ids, _APIFY_BATCH):
        payload = {
            adapter.url_key: [_watch_url(v) for v in batch],
            adapter.list_only_key: True,
        }
        for row in _run_actor(
            actor, payload, token=token, timeout=_ACTOR_TIMEOUT
        ):
            video_id = _row_video_id(row) or ""
            if video_id:
                kinds[video_id] = _read_kind(row, adapter)
    return kinds


def fetch_transcripts(
    youtube_ids: Sequence[str],
    *,
    token: str,
    actor: str,
    prefer_manual: bool = True,
) -> dict[str, Transcript | Exception]:
    """Fetch transcripts. BILLED, one event per video.

    Returns one entry per requested id: a `Transcript`, or the exception that
    explains why there is not one. **Failures are returned, never raised past
    the batch**, because a refresh run that aborts on the first failure leaves a
    pool that looks complete and is not -- and the actor is community-maintained
    at 4.45 stars over nine reviews, so intermittent failure is the expected
    case rather than the exceptional one.

    ``prefer_manual`` implements PRD §7.2's human-captions requirement. It is
    not only a quality preference: `core/lexicon/coverage.py` switches the
    proper-noun rule off on lowercase text, so auto-generated captions produce
    an inflated coverage number (#288). The caption kind decides which coverage
    algorithm runs.
    """
    adapter = adapter_for(actor)
    results: dict[str, Transcript | Exception] = {}

    for batch in _chunks(youtube_ids, _APIFY_BATCH):
        payload: dict[str, Any] = {
            adapter.url_key: [_watch_url(v) for v in batch]
        }
        if prefer_manual and adapter.kind_key and adapter.manual_value:
            payload[adapter.kind_key] = adapter.manual_value
        try:
            rows = _run_actor(
                actor, payload, token=token, timeout=_ACTOR_TIMEOUT
            )
        except VideoApiError as exc:
            # The whole batch failed. Every id in it keeps the same retryable
            # verdict rather than being marked individually unavailable.
            for video_id in batch:
                results[video_id] = exc
            continue

        for row in rows:
            video_id = _row_video_id(row)
            if not video_id:
                continue
            text = _read_text(row, adapter)
            if not text:
                results[video_id] = TranscriptUnavailable(
                    "actor returned a row with no transcript text"
                )
                continue
            results[video_id] = Transcript(
                youtube_id=video_id,
                text=text,
                lang=_first_str(row, adapter.lang_keys),
                kind=_read_kind(row, adapter),
            )

        for video_id in batch:
            results.setdefault(
                video_id,
                TranscriptUnavailable(
                    "actor returned no row for this video -- it has no "
                    "captions in the requested language and kind"
                ),
            )

    return results


# --------------------------------------------------------------------------
# Reading an actor's row. Every one of these tolerates a missing field and
# reports absence rather than substituting a value.
# --------------------------------------------------------------------------
def _watch_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"


def _row_video_id(row: dict) -> str | None:
    for key in ("video_id", "videoId", "id", "youtube_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("url", "video_url", "youtube_url"):
        value = row.get(key)
        if isinstance(value, str) and "v=" in value:
            return value.split("v=", 1)[1].split("&", 1)[0]
    return None


def _read_text(row: dict, adapter: _Adapter) -> str:
    for key in adapter.text_keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
        # Some actors return the transcript as timestamped segments.
        if isinstance(value, list) and value:
            joined = " ".join(
                str(seg.get("text", "")) if isinstance(seg, dict) else str(seg)
                for seg in value
            ).strip()
            if joined:
                return joined
    return ""


def _read_kind(row: dict, adapter: _Adapter) -> str | None:
    """'manual' | 'generated' | None. None when the actor did not say."""
    for key in adapter.kind_keys:
        if key not in row:
            continue
        value = row[key]
        if isinstance(value, bool):
            # An `is_generated` style flag.
            return "generated" if value else "manual"
        if isinstance(value, str) and value.strip():
            normalised = value.strip().lower()
            if normalised in {"any", ""}:
                # The actor echoed the REQUEST, not the result. That is not a
                # finding about this video, so it is not treated as one.
                continue
            if any(
                token in normalised for token in adapter.generated_truthy
            ):
                return "generated"
            if "manual" in normalised or "human" in normalised:
                return "manual"
    return None


def _first_str(row: dict, keys: Iterable[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _chunks(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])
