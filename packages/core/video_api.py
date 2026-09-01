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
- The Apify actor costs MONEY, per video. `list_transcripts` uses the
  actor's `list_only` mode, which the actor documents as **not charged as a
  videoprocessed event** -- that is what makes PRD §7.2's human-captions
  preference verifiable without paying to find out.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
    #: Per-cue timings as the actor sent them: `[{text, start, duration}]`,
    #: seconds as floats. **None means the actor sent none, or sent a shape
    #: `normalise_cues` refuses** -- and that is a specified state downstream,
    #: not an error. **The service gates on identity before storing them**: if
    #: joining these does not reproduce `text`, the text is stored and the cues
    #: are refused (see `core.services.video.record_transcript`).
    #:
    #: **THIS FIELD EXISTS BECAUSE DISCARDING IT ONCE COST A WHOLE SLICE.**
    #: `_read_text`'s list branch joined each segment's `text` and dropped every
    #: `start`, so the timings had to be recovered from `--dump` files months
    #: later (R12, T5). A field the source supplies is carried.
    cues: tuple[dict, ...] | None = None


@dataclass(frozen=True, slots=True)
class Track:
    """One caption track, as the FREE `list_only` listing reports it."""

    language_code: str | None
    language: str | None
    #: True auto-generated, False human-written, None the actor did not say.
    #: **None is never read as either** -- see `_read_kind`'s docstring and #257.
    is_generated: bool | None


@dataclass(frozen=True, slots=True)
class TrackListing:
    """What the free check found for one video: the kind AND the tracks.

    **#323 needed only `kind` and #324 could not be fixed without `tracks`.**
    The kind decides which coverage algorithm runs (#288); the tracks decide
    what to ask the actor for. Keeping only the kind threw away the one fact
    -- `9sSD2IFGSLw`'s manual track is `en-GB` and not `en` -- that made the
    first billed run's query unanswerable for four videos out of five.
    """

    youtube_id: str
    tracks: tuple[Track, ...]
    #: 'manual' | 'generated' | None, by `_read_kind`'s ANY rule (#323).
    kind: str | None


@dataclass(frozen=True, slots=True)
class Query:
    """The actor input for ONE video, derived from its listing.

    `transcript_type=None` means *send no selector*, which is not the same as
    sending the actor's default: an adapter whose actor has no way to say "any"
    must omit the key rather than invent a value for it.
    """

    #: 'manual' | 'any' | None.
    transcript_type: str | None
    #: Ordered language codes, most-preferred first. The actor documents
    #: `languages` as *"the first available transcript matching one of these"*.
    languages: tuple[str, ...]


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
    #: Output keys, tried in order, holding the TIMESTAMPED variant: a list of
    #: `{text, start, duration}`. **Separate from `text_keys` and deliberately
    #: so** -- `text_keys` is ordered to prefer the flat `non_timestamped`
    #: string, and reusing it here would make the timed and untimed reads fight
    #: over one preference order.
    cues_keys: tuple[str, ...] = ()
    #: **A NESTED PATH, BECAUSE THE FLAT `kind_keys` TUPLE CANNOT EXPRESS THIS
    #: SHAPE AT ALL (#323).** The `list_only` response reports kinds inside
    #: `available_transcripts`, a LIST OF TRACK OBJECTS each carrying its own
    #: flag -- so `_read_kind`, which looked only at the row's top level,
    #: returned `None` for every video and the first billed run printed
    #: `unknown 5` about a response that stated every kind.
    #:
    #: **Adding `"available_transcripts"` to `kind_keys` was considered and is
    #: REFUSED on the record:** `_read_kind` would find a list where it expects a
    #: bool or a str, match neither branch, and return `None` -- the same wrong
    #: answer through a longer path, with the tuple now LOOKING as if it covered
    #: the case.
    tracks_key: str | None = None
    #: The per-track flag inside `tracks_key`. True means auto-generated.
    track_generated_key: str = "is_generated"
    #: The per-track language code inside `tracks_key`.
    track_language_key: str = "language_code"
    #: The per-track human-readable language name inside `tracks_key`.
    track_language_name_key: str = "language"
    #: Input key naming the ORDERED language preference, and the `kind_key`
    #: value meaning "either kind will do".
    #:
    #: **`languages_key` IS THE HALF THE FIRST BILLED RUN DID NOT SET (#324).**
    #: Leaving it unset does not mean "any language"; the actor documents a
    #: default of `["en"]`, so the query became *a manual track whose language
    #: code is exactly `en`* -- which four of the five videos do not have, and
    #: which rejects `en-GB` human captions in favour of nothing at all.
    languages_key: str | None = None
    any_value: str | None = None
    #: Input key that switches OFF the actor's per-video yt-dlp metadata fetch.
    #: Title, description and channel name all come from the YouTube Data API
    #: already, at quota cost and not money, and none of them is read here.
    metadata_key: str | None = None


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
        cues_keys=("timestamped",),
        tracks_key="available_transcripts",
        languages_key="languages",
        any_value="any",
        metadata_key="include_metadata",
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
        # **NAMED FROM THE ACTOR'S DOCUMENTED SHAPE AND NEVER MEASURED.** This
        # actor is the ruled fallback and has never been run (#288's shape: one
        # provider's premise inherited as a fact about all). If the key is
        # wrong, `_read_cues` returns None, the row lands in the
        # transcript-present-cues-absent state, and nothing breaks -- which is
        # why a guess is survivable HERE and is not survivable at the identity
        # gate, where it is measured instead.
        cues_keys=("timestamped", "segments"),
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
    # **THE KEY GOES IN A HEADER, NEVER IN THE QUERY STRING (#311).**
    #
    # It was `params={**params, "key": api_key}` until 2026-08-31, and
    # `httpx._client` logs the full URL at INFO -- so a production run of
    # `core.video.resolve_channels` printed the live key eleven times, once per
    # handle, into a shell history and a chat transcript.
    #
    # **THE COMMENT THAT USED TO BE HERE SAID THE KEY "MUST NEVER REACH A LOG
    # LINE", AND IT WAS TRUE OF THE CODE IT GUARDED.** The exception below does
    # not carry it. The leak came out of the HTTP library, which a comment about
    # our own raise statement could not see -- so the invariant is now enforced
    # by where the credential is PUT rather than asserted about where it is not
    # printed. `tests/test_video_api_credentials.py` holds it.
    #
    # **WHY NOT SILENCE httpx's LOGGER INSTEAD**, which was the other option
    # offered: setting this module's httpx logger to WARNING hides today's line
    # and leaves the credential in the URL for the next thing that prints one --
    # a proxy, an error report, a retry wrapper, a future httpx. A credential
    # absent from the URL cannot be logged by anything.
    #
    # Verified against the live API before it was written, not assumed:
    # `X-goog-api-key` alone returns **400 `API key expired`**, and no
    # credential at all returns **403 `Method doesn't allow unregistered
    # callers`**. 403 -> 400 is the proof the header was read.
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{YOUTUBE_API}/{path}",
            params=params,
            headers={"X-goog-api-key": api_key},
        )
    if response.status_code != 200:
        # `response.text` is the API's error body and carries no credential --
        # the key is in a request header, and this reads the RESPONSE.
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
def _dump_target(base: Path | None, label: str, index: int) -> Path | None:
    """One file per actor response, so each stays byte-identical to one call.

    `--dump /tmp/actor.json` yields `/tmp/actor.fetch.001.json`,
    `/tmp/actor.list.001.json`, and so on. **A single file could not be
    byte-identical to more than one response**, and a run of more than
    `_APIFY_BATCH` videos makes more than one call -- so the batch index is in
    the name rather than the last response silently winning.
    """
    if base is None:
        return None
    return base.with_name(f"{base.stem}.{label}.{index:03d}{base.suffix or '.json'}")


def _run_actor(
    actor: str,
    payload: dict[str, Any],
    *,
    token: str,
    timeout: httpx.Timeout,
    dump_to: Path | None = None,
) -> list[dict]:
    """Run an actor synchronously and return its dataset items.

    **`dump_to` writes the response body VERBATIM, before anything reads it
    (#317).** Not `json.dumps(response.json())` -- that would re-serialise, and
    a re-serialised body has lost the actor's own formatting, its key order and
    every field this module's adapter does not name. **Those absent fields are
    exactly what a fixture is for**: the adapter table exists because two actors
    report the same facts under different names, so a fixture built from the
    fields we already read would encode our assumptions rather than test them
    (#271's shape).

    **It is written BEFORE the status checks, deliberately.** A 4xx body is the
    one an operator most needs and the one this function truncates to 300
    characters in the exception it raises. The dump keeps all of it.
    """
    if not token:
        raise VideoApiError(
            "APIFY_TOKEN is not set. It lives on production only; this command "
            "cannot run without it and does not run degraded."
        )
    endpoint = f"{APIFY_API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
    try:
        # **THE SAME DEFECT AS `_youtube_get`'s, FOUND BY LOOKING FOR THE CLASS
        # RATHER THAN FOR THE INSTANCE (#311).** This was
        # `params={"token": token}`. It has never been seen in a log because no
        # actor run has been made outside a test -- so it was a leak waiting for
        # its first production run, not one that had happened.
        #
        # Verified against the live API on the free `GET /v2/users/me`, which is
        # not an actor run and cost nothing: `Authorization: Bearer` returns
        # **200**, and no credential returns **401**.
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        # A transport failure is retryable by construction: nothing about the
        # video is known to be wrong.
        raise TranscriptFetchFailed(f"actor {actor} transport error: {exc}") from exc
    if dump_to is not None:
        dump_to.parent.mkdir(parents=True, exist_ok=True)
        dump_to.write_bytes(response.content)
        logger.info("actor response written verbatim to %s", dump_to)
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


def list_transcripts(
    youtube_ids: Sequence[str],
    *,
    token: str,
    actor: str,
    dump_to: Path | None = None,
) -> dict[str, TrackListing]:
    """Which caption tracks each video has, WITHOUT paying for a transcript.

    Returns `youtube_id -> TrackListing` for every video the actor answered
    about. **A video absent from the mapping is a video the actor said nothing
    about**, which is not the same fact as a video with no tracks -- see
    `terminal_from_listing`, where that distinction is the difference between a
    retry and a permanent exclusion.

    `TrackListing.kind` is `'manual' | 'generated' | None`, and **None is filed,
    never treated as 'generated'** -- an absent field and an auto-generated track
    are different facts, and #257's lesson is that a column must not claim to
    hold a kind it is guessing.

    An actor with no `list_only` mode returns an empty mapping rather than
    silently falling back to a paid call.

    **WAS `list_transcript_kinds`, AND THE RENAME IS THE POINT.** It returned
    only the kind, which is all #323 needed, and the discarded half is what
    #324 could not be fixed without: `9sSD2IFGSLw` has a human-written track
    and its language code is `en-GB`. A reader that answers "manual" and throws
    away "en-GB" hands the fetch exactly enough to ask an unanswerable question.
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

    listings: dict[str, TrackListing] = {}
    for index, batch in enumerate(_chunks(youtube_ids, _APIFY_BATCH), start=1):
        payload: dict[str, Any] = {
            adapter.url_key: [_watch_url(v) for v in batch],
            adapter.list_only_key: True,
        }
        # **THE FREE CHECK WAS PAYING FOR METADATA TOO.** The recorded listing
        # response carries `channel_name`, `video_duration_seconds` and
        # `upload_date` per row -- the actor ran yt-dlp per video to produce
        # them, on the call whose whole justification is that it is cheap. None
        # of the three is read by anything here, and all three come from the
        # YouTube Data API at quota cost rather than money.
        if adapter.metadata_key:
            payload[adapter.metadata_key] = False
        for row in _run_actor(
            actor,
            payload,
            token=token,
            timeout=_ACTOR_TIMEOUT,
            dump_to=_dump_target(dump_to, "list", index),
        ):
            video_id = _row_video_id(row) or ""
            if video_id:
                listings[video_id] = TrackListing(
                    youtube_id=video_id,
                    tracks=_read_tracks(row, adapter),
                    kind=_read_kind(row, adapter),
                )
    return listings


def terminal_from_listing(
    listing: TrackListing | None,
) -> TranscriptUnavailable | None:
    """The ONE fact that justifies never asking about a video again.

    **TERMINAL MEANS THE LISTING SHOWS NO TRACK. FULL STOP.** Operator ruling,
    2026-09-01, and it is a NARROWING of what the code used to do rather than a
    new rule: `fetch_transcripts` returned `TranscriptUnavailable` -- terminal,
    written to the database as `unavailable`, never offered again -- whenever the
    actor returned no row or an empty one. **That is the actor saying nothing,
    and the code read it as the actor saying "this video has no captions".**
    Four videos that do have captions were permanently excluded on it (#322),
    and #324 showed the fetch had simply been asked an unanswerable question.

    Three states, and only one of them is terminal:

    * **no listing at all** -> `None`. The free check can fail, and an actor
      with no `list_only` mode never produces one. Absence of evidence.
    * **a listing with tracks** -> `None`, *whatever* those tracks are. A video
      listing only Burmese captions has no English transcript to fetch and is
      still not terminal by this rule; widening it to "no USABLE track" is a
      decision nobody has taken and is filed as #325.
    * **a listing with an empty track list** -> terminal. The actor enumerated
      the tracks and there were none.
    """
    if listing is None or listing.tracks:
        return None
    return TranscriptUnavailable(
        "the free listing enumerated this video's caption tracks and there are "
        "none -- this is the actor stating absence, not failing to answer"
    )


def plan_query(listing: TrackListing | None, adapter: _Adapter) -> Query:
    """What to ask the actor for THIS video. PRD §7.2, as a preference.

    **THE DEFECT THIS REPLACES.** The old fetch sent one payload for the whole
    batch: `transcript_type: "manual"`, `languages` unset. The actor documents
    `languages` as defaulting to `["en"]`, so the question was *a manual track
    whose language code is exactly `en`* -- and the run's five videos gave five
    correct refusals-or-answers to it: three have only auto-generated `en`,
    `9sSD2IFGSLw`'s manual track is `en-GB`, and the single success is the only
    video in the set with a manual `en` track (#324).

    **THE RULING, AND IT IS THE WHOLE FUNCTION: PREFER MANUAL, DO NOT REQUIRE
    IT.** A video whose only captions are auto-generated **is fetched**, with
    `any`, and its kind is recorded. #288's coverage inflation is compensable
    downstream; discarding the video loses it permanently. The defect was never
    *preferring* manual -- it was asking for manual and taking nothing when there
    is none.

    **AND THE LANGUAGES COME FROM THE TRACK LIST, NOT FROM A DEFAULT.** Every
    code is one the listing actually reported, in the order the listing reported
    it, so the actor's "first available transcript matching one of these" is
    matching against tracks known to exist.

    With no listing the query is still WRITTEN DOWN rather than left to the
    actor's defaults -- `any` and `["en"]`. Inheriting a default silently is
    exactly what #324 is, and it costs nothing to say so in the payload.
    """
    english = [
        track
        for track in (listing.tracks if listing else ())
        if isinstance(track.language_code, str)
        and track.language_code.lower().split("-", 1)[0] == "en"
    ]
    # `is_generated is False` and not `not is_generated`: an unstated flag is
    # not evidence of a human-written track, and treating it as one would ask
    # for `manual` on a video that may not have any (#257, #323).
    manual = [track for track in english if track.is_generated is False]
    preferred = manual or english

    if manual and adapter.kind_key and adapter.manual_value:
        transcript_type = adapter.manual_value
    elif adapter.kind_key and adapter.any_value:
        transcript_type = adapter.any_value
    else:
        # The actor has no way to say "either kind will do". Omitting the key
        # is honest; inventing a value for it is not.
        transcript_type = None

    codes: list[str] = []
    for track in preferred:
        code = str(track.language_code)
        if code not in codes:
            codes.append(code)
    if not codes:
        # No listing, or a listing with no English track. English is what this
        # product is for, and saying so beats inheriting `["en"]` in silence.
        codes = ["en"]
    if adapter.languages_key is None:
        codes = []
    return Query(transcript_type=transcript_type, languages=tuple(codes))


def _payload_for(batch: Sequence[str], query: Query, adapter: _Adapter) -> dict:
    payload: dict[str, Any] = {adapter.url_key: [_watch_url(v) for v in batch]}
    if query.transcript_type is not None and adapter.kind_key:
        payload[adapter.kind_key] = query.transcript_type
    if query.languages and adapter.languages_key:
        payload[adapter.languages_key] = list(query.languages)
    if adapter.metadata_key:
        payload[adapter.metadata_key] = False
    return payload


def fetch_transcripts(
    youtube_ids: Sequence[str],
    *,
    token: str,
    actor: str,
    listings: "Mapping[str, TrackListing] | None" = None,
    dump_to: Path | None = None,
) -> dict[str, Transcript | Exception]:
    """Fetch transcripts. BILLED, one event per video.

    Returns one entry per requested id: a `Transcript`, or the exception that
    explains why there is not one. **Failures are returned, never raised past
    the batch**, because a refresh run that aborts on the first failure leaves a
    pool that looks complete and is not.

    **THE QUERY IS PER VIDEO, WHICH MEANS THE CALL IS PER QUERY (#324).** The
    actor's input carries ONE `transcript_type` and ONE `languages` list per
    run, so asking three different questions takes three runs. The videos are
    grouped by the query their listing implies and one call is made per group,
    which is the fewest calls that can ask the right question of each video.
    **This can increase the number of actor runs**, and an actor run is not
    free of Apify platform usage even when its per-event price is (#321) -- so
    `refresh` prints the groups before it spends anything.

    ``listings`` is the FREE `list_only` result (`list_transcripts`). Without
    it every video gets the same written-down default rather than an inherited
    one; see `plan_query`.

    **`prefer_manual` IS GONE, AND ITS REMOVAL IS NOT THE THING #324 FORBADE.**
    The flag expressed §7.2 by putting `transcript_type: "manual"` on the whole
    batch, which is the defect itself. The preference is now structural, in
    `plan_query`: a video with a human-written English track is asked for
    `manual` and no other video is. Dropping the *preference* would abandon
    §7.2 and feed #288; dropping the *flag* is what implementing it properly
    looks like.
    """
    adapter = adapter_for(actor)
    results: dict[str, Transcript | Exception] = {}

    # Grouping preserves first-appearance order, so the call sequence -- and the
    # dump file numbering with it -- is a function of the input and not of dict
    # iteration luck.
    groups: dict[Query, list[str]] = {}
    for video_id in youtube_ids:
        query = plan_query(
            (listings or {}).get(video_id), adapter
        )
        groups.setdefault(query, []).append(video_id)

    call = 0
    for query, ids in groups.items():
        for batch in _chunks(ids, _APIFY_BATCH):
            call += 1
            try:
                rows = _run_actor(
                    actor,
                    _payload_for(batch, query, adapter),
                    token=token,
                    timeout=_ACTOR_TIMEOUT,
                    dump_to=_dump_target(dump_to, "fetch", call),
                )
            except VideoApiError as exc:
                # The whole batch failed. Every id in it keeps the same
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
                    # **RETRYABLE, NOT TERMINAL (#322's surviving half, ruled
                    # 2026-09-01).** This used to be `TranscriptUnavailable`,
                    # which `record_transcript_failure` writes as `unavailable`
                    # and `videos_needing_transcript` never offers again. A row
                    # with no text is the actor declining to answer; the only
                    # positive evidence of absence is a listing that enumerated
                    # the tracks and found none -- see `terminal_from_listing`.
                    results[video_id] = TranscriptFetchFailed(
                        "actor returned a row with no transcript text -- that "
                        "is the actor saying nothing, not this video having no "
                        "captions"
                    )
                    continue
                results[video_id] = Transcript(
                    youtube_id=video_id,
                    text=text,
                    lang=_first_str(row, adapter.lang_keys),
                    kind=_read_kind(row, adapter),
                    cues=_read_cues(row, adapter),
                )

            for video_id in batch:
                results.setdefault(
                    video_id,
                    TranscriptFetchFailed(
                        "actor returned no row for this video. The query sent "
                        f"was {query.transcript_type or 'the actor default'} / "
                        f"{list(query.languages) or 'the actor default'}; "
                        "whether the video has captions is a question the FREE "
                        "listing answers, and this is not that answer"
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


def _read_cues(row: dict, adapter: _Adapter) -> tuple[dict, ...] | None:
    """The timestamped variant, or None.

    **Validation is NOT here.** `core.video.cues.normalise_cues` owns what a
    usable cue list is -- a `start` on every element, ascending, no repair -- and
    a second opinion in this module is the two-instruments shape one layer down.
    This function finds the list and hands it over.
    """
    for key in adapter.cues_keys:
        value = row.get(key)
        if isinstance(value, list) and value:
            return tuple(v for v in value if isinstance(v, dict))
    return None


def _read_tracks(row: dict, adapter: _Adapter) -> tuple[Track, ...]:
    """The listing's track list, in the order the actor reported it.

    **ORDER IS PRESERVED AND IS NOT MEANING.** `_read_kind`'s rule is ANY
    precisely because position says nothing about kind (#323). Here the order is
    kept for a different reason: it becomes the `languages` preference order,
    and the actor documents that as *"the first available transcript matching
    one of these"*. So position is load-bearing for the language question and
    irrelevant to the kind question, and the two must not be confused.
    """
    if not adapter.tracks_key:
        return ()
    raw = row.get(adapter.tracks_key)
    if not isinstance(raw, list):
        return ()
    tracks: list[Track] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        generated = entry.get(adapter.track_generated_key)
        tracks.append(
            Track(
                language_code=_first_str(entry, (adapter.track_language_key,)),
                language=_first_str(entry, (adapter.track_language_name_key,)),
                is_generated=generated if isinstance(generated, bool) else None,
            )
        )
    return tuple(tracks)


def _read_kind(row: dict, adapter: _Adapter) -> str | None:
    """'manual' | 'generated' | None. None when the actor did not say.

    **TWO SHAPES, AND THE FLAT ONE WINS WHEN BOTH ARE PRESENT.** A FETCH row
    carries `transcript_type` describing **the track actually delivered**; a
    `list_only` row carries `available_transcripts` describing **what exists**.
    When both appear the delivered track is the answer, so the flat keys are
    read first and the track list is the fallback.

    **THE TRACK RULE IS `ANY`, NOT `FIRST` AND NOT `ALL` (#323).** A video is
    `manual` if **any** track is human-written, `generated` only if tracks exist
    and **every** stated flag is true, and `None` if no track states one.

    *First* is wrong for two independent reasons, and the recorded fixture
    carries one of each. `9sSD2IFGSLw` lists its **manual** track first and an
    auto-generated one second, so *all* and *last* both answer `generated` where
    the truth is `manual`. `QyRqlTV60zM` lists **Arabic** first and English
    fourth, so a *first* reader is answering a LANGUAGE question when it was
    asked a KIND one -- and there it returns the right value **by luck**, which
    is worse than failing, because it passes while being wrong for the wrong
    reason.
    """
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

    # The nested fallback. Only reached when no flat key answered.
    if adapter.tracks_key:
        tracks = row.get(adapter.tracks_key)
        if isinstance(tracks, list):
            stated = [
                track.get(adapter.track_generated_key)
                for track in tracks
                if isinstance(track, dict)
                and isinstance(track.get(adapter.track_generated_key), bool)
            ]
            if stated:
                # ANY human-written track makes the video manual, wherever it
                # sits in the list and whatever language it is in.
                if any(flag is False for flag in stated):
                    return "manual"
                return "generated"
            # Tracks exist but none states a flag. That is the actor declining
            # to say, not evidence of a generated track -- and guessing
            # `generated` here would switch the proper-noun rule off and inflate
            # coverage (#288) on no evidence at all.
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
