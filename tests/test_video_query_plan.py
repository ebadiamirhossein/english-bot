"""The actor query is built PER VIDEO from the free listing. #324.

**THE DEFECT THIS FILE EXISTS FOR, AND IT COST FOUR VIDEOS AND MOST OF A BILL.**
`fetch_transcripts` sent one payload for the whole batch:

    {"youtube_url": [...], "transcript_type": "manual"}

`languages` was never set, so the actor's documented default `["en"]` applied,
and the question actually asked was **"a manual track whose language code is
exactly `en`"**. Of the five videos in the first billed run, **one** had such a
track. Three have only auto-generated `en`. `9sSD2IFGSLw`'s manual track is
**`en-GB`** -- the only human-written English captions in the set, and the
pipeline asked for them in a way that could not match. Five outcomes, five
predicted, no residual.

**CONFIRMED ON PRODUCTION, 2026-09-01**, before a line of this was written: the
same video, the same actor, the same minute, with `transcript_type: "any"`
returned **HTTP 201, success True, 10,373 characters**. There was never an IP
block (#322's diagnosis, refuted by #324).

**WHAT THESE TESTS ASSERT IS THE REQUEST PAYLOAD**, not a return value and not a
count. The defect was invisible in every result-shaped assertion: the actor
answered the question it was asked, correctly, and the answer was "no". The only
place the fault is legible is in what we sent -- so that is what is pinned, key
by key, derived from the committed `list_only` fixture that the billed run
produced (#317, #323).

**A HAND-BUILT LISTING WAS REFUSED FOR THE MAIN ASSERTION.** A fixture composed
from the fields we already read would encode our assumptions rather than the
actor's behaviour, which is #271's shape and is the defect one level up. The
listing is parsed by the real `list_transcripts` from
`tests/fixtures/transcripts/actor.list.001.json`. Constructed listings appear
only where a shape the recorded run does not contain is under test, and each
says so.

No socket is opened: `httpx.MockTransport` answers in process and the
session-scoped `netguard` in `tests/conftest.py` is satisfied.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from core import video_api

#: Captured at import, so a second `_mock_actor` in one test re-wraps the
#: REAL client rather than the already-patched one.
_REAL_CLIENT = httpx.Client

ACTOR = "johnvc/YoutubeTranscripts"
FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "transcripts" / "actor.list.001.json"
)

#: The five ids of the recorded run, in the order the actor returned them.
AUTO_ONLY = ("y_525lzqbg0", "5E5tNu4NsxM", "ScmC5E7titM")
MANUAL_EN_GB = "9sSD2IFGSLw"
MANUAL_EN = "QyRqlTV60zM"


def _mock_actor(monkeypatch, body: bytes, seen: list[dict]):
    """Answer every Apify POST with `body`, recording each request payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    def client_on_mock_transport(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_CLIENT(*args, **kwargs)

    monkeypatch.setattr(video_api.httpx, "Client", client_on_mock_transport)


@pytest.fixture
def listings(monkeypatch) -> dict[str, "video_api.TrackListing"]:
    """The REAL listing reader over the REAL recorded response."""
    seen: list[dict] = []
    _mock_actor(monkeypatch, FIXTURE.read_bytes(), seen)
    ids = [row["video_id"] for row in json.loads(FIXTURE.read_bytes())]
    return video_api.list_transcripts(ids, token="tok", actor=ACTOR)


@pytest.fixture
def fetch_payloads(monkeypatch, listings) -> list[dict]:
    """Drive the real `fetch_transcripts` and return what it actually sent."""
    seen: list[dict] = []
    _mock_actor(monkeypatch, b"[]", seen)
    video_api.fetch_transcripts(
        list(listings), token="tok", actor=ACTOR, listings=listings
    )
    return seen


def _plan(payloads: list[dict]) -> dict[tuple[str | None, tuple[str, ...]], set[str]]:
    """The payloads as `(transcript_type, languages) -> {video ids}`."""
    out: dict[tuple[str | None, tuple[str, ...]], set[str]] = {}
    for payload in payloads:
        key = (
            payload.get("transcript_type"),
            tuple(payload.get("languages") or ()),
        )
        ids = {
            url.split("v=", 1)[1].split("&", 1)[0]
            for url in payload["youtube_url"]
        }
        out.setdefault(key, set()).update(ids)
    return out


# ---------------------------------------------------------------------------
# 1a + 1b -- the request payload, per video, from the listing
# ---------------------------------------------------------------------------
def test_the_request_payload_is_derived_per_video_from_the_listing(
    fetch_payloads,
) -> None:
    """**THE TEST THAT MATTERS. Three groups, and each is a different question.**

    A single batch payload cannot ask three questions, so the fetch groups the
    videos by the query their listing implies and makes one call per group. That
    is the whole fix: the actor's input has one `transcript_type` and one
    `languages` per run, so *per video* means *per group*.
    """
    assert _plan(fetch_payloads) == {
        ("manual", ("en",)): {MANUAL_EN},
        ("manual", ("en-GB",)): {MANUAL_EN_GB},
        ("any", ("en",)): set(AUTO_ONLY),
    }


def test_the_video_with_en_gb_captions_is_never_asked_for_a_manual_en_track(
    fetch_payloads,
) -> None:
    """**`9sSD2IFGSLw` IS THE VIDEO THE OLD QUERY LOST, AND IT IS NAMED HERE.**

    Its manual track is `en-GB`. The old payload asked for `manual` and left
    `languages` unset, so the actor's `["en"]` default applied and the one track
    PRD §7.2 exists to prefer could not match. The assertion is on the pairing,
    not on either half: `manual` is right, `["en"]` is right for other videos,
    and **together they are the defect.**
    """
    for payload in fetch_payloads:
        if any(MANUAL_EN_GB in url for url in payload["youtube_url"]):
            assert payload.get("languages") == ["en-GB"], (
                "the language must come from the track list, not the default"
            )
            assert payload.get("transcript_type") == "manual"


def test_a_video_with_only_generated_captions_is_fetched_and_not_discarded(
    fetch_payloads,
) -> None:
    """**THE RULING, 2026-09-01: PREFER MANUAL, DO NOT REQUIRE IT.**

    §7.2's preference is implemented as a preference. A video whose only track
    is auto-generated is asked for with `any` and **is fetched** -- #288's
    coverage inflation is compensable downstream, where discarding the video
    loses it permanently. The old code asked for `manual`, got nothing, and
    wrote a terminal verdict.
    """
    asked = _plan(fetch_payloads)
    assert set(AUTO_ONLY) <= asked[("any", ("en",))]


def test_the_manual_preference_is_not_dropped_to_make_the_fetch_succeed(
    fetch_payloads,
) -> None:
    """**WHAT MUST NOT CLOSE #324: asking `any` for everything.**

    That would fetch all five and silently abandon §7.2. On a video with a
    manual AND an auto track under the same language code, "first available
    matching" is undefined and the auto track can win -- which switches the
    proper-noun rule off and inflates coverage (#288) with nothing saying so.
    Every video that HAS a manual track is asked for `manual`.
    """
    for payload in fetch_payloads:
        for url in payload["youtube_url"]:
            if MANUAL_EN in url or MANUAL_EN_GB in url:
                assert payload.get("transcript_type") == "manual"


# ---------------------------------------------------------------------------
# 1c -- include_metadata
# ---------------------------------------------------------------------------
def test_metadata_is_switched_off_on_every_actor_call(
    monkeypatch, listings, fetch_payloads
) -> None:
    """**`include_metadata` RUNS yt-dlp PER VIDEO FOR FIELDS NOBODY READS.**

    Title, description and channel name all come from the YouTube Data API,
    which costs quota and not money; not one of them is read by
    `fetch_transcripts` or by `_read_kind`. On the first billed run the actor
    fetched them twice over -- once on the listing call and once on the fetch --
    and the Actors line was 60% of the bill (#321).

    **Asserted on BOTH calls**, because the listing rows in the recorded fixture
    carry `channel_name`, `video_duration_seconds` and `upload_date`: the free
    check was paying for metadata too.
    """
    for payload in fetch_payloads:
        assert payload.get("include_metadata") is False

    seen: list[dict] = []
    _mock_actor(monkeypatch, FIXTURE.read_bytes(), seen)
    video_api.list_transcripts(["abc123"], token="tok", actor=ACTOR)
    assert seen and seen[0].get("include_metadata") is False


# ---------------------------------------------------------------------------
# 1d -- what "terminal" means
# ---------------------------------------------------------------------------
def test_an_empty_actor_response_is_retryable_and_never_terminal(
    monkeypatch, listings
) -> None:
    """**#322's SURVIVING HALF. AN EMPTY RESPONSE IS THE ACTOR SAYING NOTHING.**

    It is not the claim *this video has no captions*, and the code must stop
    inferring one from the other. `TranscriptUnavailable` is terminal --
    `record_transcript_failure` writes `unavailable` and
    `videos_needing_transcript` never offers the row again -- so a wrong verdict
    here is silent, permanent pool shrinkage.

    Both empty shapes are pinned: **no row at all**, and **a row with no text.**
    """
    seen: list[dict] = []
    _mock_actor(monkeypatch, b'[{"video_id":"y_525lzqbg0","non_timestamped":""}]', seen)
    results = video_api.fetch_transcripts(
        ["y_525lzqbg0", "5E5tNu4NsxM"], token="tok", actor=ACTOR, listings=listings
    )
    for video_id, outcome in results.items():
        assert isinstance(outcome, video_api.TranscriptFetchFailed), (
            f"{video_id} got {outcome!r}; an empty response is retryable"
        )
        assert not isinstance(outcome, video_api.TranscriptUnavailable)


def test_the_only_terminal_verdict_comes_from_a_listing_with_no_tracks() -> None:
    """**TERMINAL REQUIRES POSITIVE EVIDENCE, AND THE LISTING IS THE ONLY SOURCE
    OF IT.**

    The listing is free (#318b) and it enumerates the tracks. A row with an
    empty `available_transcripts` is the actor stating that nothing exists; that
    is the one fact that justifies never asking again.

    **Constructed listings, and they are constructed on purpose:** the recorded
    run contains no video with an empty track list, so this shape cannot come
    from the fixture. What comes from the fixture is every assertion above.
    """
    empty = video_api.TrackListing(youtube_id="x", tracks=(), kind=None)
    listed = video_api.TrackListing(
        youtube_id="y",
        tracks=(video_api.Track(language_code="en", language="English",
                                is_generated=True),),
        kind="generated",
    )

    assert isinstance(
        video_api.terminal_from_listing(empty), video_api.TranscriptUnavailable
    )
    assert video_api.terminal_from_listing(listed) is None
    # No listing at all is NOT evidence of absence. The free check can fail, and
    # an actor with no `list_only` mode returns nothing for every video.
    assert video_api.terminal_from_listing(None) is None


def test_a_video_with_no_listing_states_its_query_rather_than_inheriting_it(
    monkeypatch,
) -> None:
    """**THE FREE CHECK CAN FAIL, AND THE PAID RUN CONTINUES WITHOUT IT.**

    `refresh` catches what `list_transcripts` raises so an advisory diagnostic
    cannot kill a billed run. The fetch then has no track list, and the query it
    sends must be **written down rather than left to the actor's defaults** --
    the old code's silent `["en"]` is exactly what #324 is.

    `any` and not `manual`: with nothing known, requiring a manual track is the
    defect itself. The delivered kind is read back off the fetch row, so #288's
    rule still applies to whatever arrives.
    """
    seen: list[dict] = []
    _mock_actor(monkeypatch, b"[]", seen)
    video_api.fetch_transcripts(["abc123"], token="tok", actor=ACTOR, listings=None)
    assert seen == [
        {
            "youtube_url": ["https://www.youtube.com/watch?v=abc123"],
            "transcript_type": "any",
            "languages": ["en"],
            "include_metadata": False,
        }
    ]


def test_a_listing_with_tracks_but_no_english_one_is_not_terminal() -> None:
    """**1d's `FULL STOP`, HELD AGAINST THE OBVIOUS WIDENING.**

    A video listing only Burmese captions has no English transcript to fetch,
    and it is tempting to call that terminal too. **The ruling is that terminal
    means the listing shows NO TRACK**, and this row shows tracks. Widening it
    is a decision nobody has taken; it is filed as #325 instead.

    Constructed, because the recorded run has no such video.
    """
    non_english = video_api.TrackListing(
        youtube_id="z",
        tracks=(video_api.Track(language_code="my", language="Burmese",
                                is_generated=False),),
        kind="manual",
    )
    assert video_api.terminal_from_listing(non_english) is None
    adapter = video_api.adapter_for(ACTOR)
    assert video_api.plan_query(non_english, adapter) == video_api.Query(
        transcript_type="any", languages=("en",)
    )


# ---------------------------------------------------------------------------
# The listing reader keeps #323's answers while gaining the track detail
# ---------------------------------------------------------------------------
def test_the_listing_still_reports_the_kinds_number_323_fixed(listings) -> None:
    """#323's assertions must not move. The listing reader gained tracks; the
    kind it derives from them is unchanged, and `9sSD2IFGSLw` is still the row
    that discriminates *any* from *first*, *last* and *all*."""
    assert listings[MANUAL_EN_GB].kind == "manual"
    assert listings[MANUAL_EN].kind == "manual"
    for video_id in AUTO_ONLY:
        assert listings[video_id].kind == "generated"


def test_the_listing_carries_the_language_code_of_every_track(listings) -> None:
    """The half #323 did not need and #324 cannot work without.

    `9sSD2IFGSLw` is the case: two tracks, and **the codes differ from each
    other**. A reader that kept only the kind would have thrown away the one
    fact that made the query wrong.
    """
    assert [t.language_code for t in listings[MANUAL_EN_GB].tracks] == ["en-GB", "en"]
    assert [t.is_generated for t in listings[MANUAL_EN_GB].tracks] == [False, True]
