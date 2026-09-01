"""The billed path must be the best-instrumented path, not the worst.

**THE STATE THIS FILE WAS WRITTEN AGAINST, AND IT WAS BACKWARDS IN THREE WAYS.**
`core.video.refresh --live --apply` is the only command in this project that
spends money, and before these tests:

1. **The raw actor response was discarded in process.** `_run_actor` returned
   `response.json()` and `fetch_transcripts` reduced every row to a `Transcript`
   dataclass immediately, dropping every key the adapter did not name. Nothing
   logged the body. So the run that Phase B's transcript fixtures were supposed
   to come from **could not produce them** (#317).
2. **It printed no cost line.** `_projection` was called on the dry path and on
   `--live`, and nowhere on `--apply` -- a FLOOR figure exactly when nothing
   would be spent, and no figure at all when money would be (#318a).
3. **`list_transcripts` had no production caller.** The free `list_only`
   mode that `video_api`'s own docstring calls *"what makes PRD §7.2's
   human-captions preference verifiable without paying to find out"* was built
   and unreached; the preference was expressed by paying (#318b).

**IT WAS CALLED `list_transcript_kinds` WHEN THESE TESTS WERE WRITTEN, AND THE
RENAME IS #324's.** It returned only the kind; the language codes it discarded
are what made the first billed run's query unanswerable. The assertions here are
about ORDER and OUTPUT on the billed path and are unchanged by that.

**WHAT THESE TESTS ASSERT, AND THE WORDING OF EACH MATTERS.** A test that a dump
file *exists* would pass against a file written from re-serialised JSON, which
is not the actor's bytes and is exactly the thing fixtures must not be. A test
that *some number* was printed would pass against any stray float. So:
byte-identity is asserted against the response body, and the cost line is
asserted by name.

No socket is opened -- `httpx.MockTransport` answers in process, so the
session-scoped `netguard` in `tests/conftest.py` is satisfied.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from core import video_api
from core.video import refresh


#: Deliberately NOT what `json.dumps` would produce from the parsed object:
#: odd spacing, a trailing newline, and a key the adapter never reads. A dump
#: written by re-serialising would differ from this in every one of those ways,
#: which is the point.
RAW_ACTOR_BODY = (
    b'[ {"videoId":"abc123",  "non_timestamped":"hello there",\n'
    b'   "language_code":"en", "transcript_type":"manual",\n'
    b'   "a_field_the_adapter_never_reads":{"nested":[1,2,3]}} ]\n'
)

ACTOR = "johnvc/YoutubeTranscripts"


@pytest.fixture
def actor_on_mock_transport(monkeypatch):
    """Answer every Apify POST with RAW_ACTOR_BODY, byte for byte."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("payloads", []).append(json.loads(request.content))
        return httpx.Response(
            200, content=RAW_ACTOR_BODY, headers={"content-type": "application/json"}
        )

    real_client = httpx.Client

    def client_on_mock_transport(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(video_api.httpx, "Client", client_on_mock_transport)
    return seen


# ---------------------------------------------------------------------------
# #317 -- the dump
# ---------------------------------------------------------------------------
def test_the_dump_file_is_byte_identical_to_the_actor_response(
    actor_on_mock_transport, tmp_path
) -> None:
    """**Byte-identical, not merely present and not merely parseable.**

    A fixture re-serialised through `json.dumps` has lost the actor's own
    formatting, its key order and every field the adapter does not read. It
    would still parse, still look like actor output, and **still encode this
    project's assumptions rather than the actor's behaviour** -- which is #271's
    defect, where a fixture quietly obeyed an unstated convention and made every
    test over it meaningless.
    """
    dump = tmp_path / "actor.json"
    video_api.fetch_transcripts(
        ["abc123"], token="tok", actor=ACTOR, dump_to=dump
    )

    written = sorted(tmp_path.glob("actor*.json"))
    assert written, "no dump file was written"
    assert len(written) == 1, f"expected one file for one batch, got {written}"
    assert written[0].read_bytes() == RAW_ACTOR_BODY, (
        "the dump must be the actor's bytes, not a re-serialisation of them"
    )


def test_the_dump_captures_a_failed_response_too(
    monkeypatch, tmp_path
) -> None:
    """A 4xx body is the one an operator most needs and the one the code
    truncates to 300 characters in the exception. The dump keeps all of it."""
    body = b'{"error":{"type":"actor-not-found","message":"' + b"x" * 800 + b'"}}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=body)

    real_client = httpx.Client
    monkeypatch.setattr(
        video_api.httpx,
        "Client",
        lambda *a, **k: real_client(*a, transport=httpx.MockTransport(handler), **k),
    )

    dump = tmp_path / "actor.json"
    results = video_api.fetch_transcripts(
        ["abc123"], token="tok", actor=ACTOR, dump_to=dump
    )
    assert isinstance(results["abc123"], Exception)

    written = sorted(tmp_path.glob("actor*.json"))
    assert written and written[0].read_bytes() == body, (
        "a failed actor response must be dumped whole -- the exception keeps "
        "only the first 300 characters"
    )


def test_no_dump_is_written_when_the_flag_is_absent(
    actor_on_mock_transport, tmp_path
) -> None:
    """Dumping is opt-in. A run that did not ask for a file must not leave one."""
    video_api.fetch_transcripts(["abc123"], token="tok", actor=ACTOR)
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# #318 -- the cost line and the free caption-kind check, on the billed path
# ---------------------------------------------------------------------------
def _billed_run(monkeypatch, capsys, *, dump=None, kinds_impl=None):
    """Drive `_live` with `--apply` over stubs, and return (stdout, call order).

    Every external is stubbed: no database, no YouTube, no Apify. What is under
    test is the ORDER and the OUTPUT of the billed path, not its plumbing.
    """
    from core.services import video as svc
    import core.db as db

    order: list[str] = []
    #: Which ids the BILLED call was actually asked for, and every terminal
    #: verdict written. Both are what #322 and #324 turn on.
    fetched: list[str] = []
    verdicts: list[tuple[str, bool]] = []

    class _Conn:
        def commit(self):
            pass

    class _ConnCtx:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db, "connection", lambda: _ConnCtx())
    monkeypatch.setattr(svc, "upsert_video", lambda *a, **k: None)
    monkeypatch.setattr(
        svc,
        "videos_needing_transcript",
        lambda conn, limit: [
            SimpleNamespace(video_id=1, youtube_id="abc123"),
            SimpleNamespace(video_id=2, youtube_id="def456"),
        ],
    )
    monkeypatch.setattr(svc, "record_transcript", lambda *a, **k: None)
    monkeypatch.setattr(
        svc,
        "record_transcript_failure",
        lambda conn, *, video_id, error, terminal: (
            verdicts.append((str(video_id), terminal)) or "unavailable"
        ),
    )
    monkeypatch.setattr(
        svc, "purge_stale", lambda *a, **k: SimpleNamespace(purged=0, scanned=0)
    )
    monkeypatch.setattr(svc, "pool_counts", lambda conn: {"ok": 2})
    monkeypatch.setattr(refresh, "_recompute_coverage", lambda *a, **k: 0)

    def fake_kinds(ids, **kw):
        order.append("list_transcripts")
        # `TrackListing`s, not bare kinds: the billed path now derives the
        # per-video QUERY from the tracks as well as the kind (#324), and a
        # stub that returned only kinds would exercise a shape production
        # never sees.
        return {
            "abc123": video_api.TrackListing(
                youtube_id="abc123",
                tracks=(
                    video_api.Track(
                        language_code="en", language="English", is_generated=False
                    ),
                ),
                kind="manual",
            ),
            "def456": video_api.TrackListing(
                youtube_id="def456",
                tracks=(
                    video_api.Track(
                        language_code="en",
                        language="English (auto-generated)",
                        is_generated=True,
                    ),
                ),
                kind="generated",
            ),
        }

    def fake_fetch(ids, **kw):
        order.append("fetch_transcripts")
        assert "listings" in kw, (
            "the billed fetch must be given the free listing -- without it the "
            "query falls back to a default, which is #324"
        )
        fetched.extend(ids)
        # **ONLY WHAT IT WAS ASKED FOR.** A stub that answers about videos the
        # caller excluded is not the actor, and it would hide exactly the thing
        # the terminal-skip test exists to check.
        answers = {
            "abc123": video_api.Transcript(
                youtube_id="abc123", text="hello", lang="en", kind="manual"
            ),
            "def456": video_api.TranscriptFetchFailed("actor said nothing"),
        }
        return {v: answers[v] for v in ids if v in answers}

    if kinds_impl is None:
        monkeypatch.setattr(video_api, "list_transcripts", fake_kinds)
    else:
        def wrapped(ids, **kw):
            order.append("list_transcripts")
            return kinds_impl(ids, **kw)

        monkeypatch.setattr(video_api, "list_transcripts", wrapped)
    monkeypatch.setattr(video_api, "fetch_transcripts", fake_fetch)
    monkeypatch.setattr(video_api, "resolve_handle", lambda *a, **k: SimpleNamespace(
        uploads_playlist_id="UU", channel_id="UC", handle="@x", title="x"
    ))
    monkeypatch.setattr(video_api, "list_channel_videos", lambda *a, **k: [])
    monkeypatch.setattr(video_api, "fetch_video_metadata", lambda *a, **k: [])

    settings = SimpleNamespace(
        youtube_api_key="yt", apify_token="ap",
        apify_transcript_actor=ACTOR,
    )
    args = SimpleNamespace(
        apply=True, live=True, per_channel=2, limit=5, file=None, dump=dump
    )
    pool = SimpleNamespace(channels=[], refusals=[])

    refresh._live(settings, pool, args)
    return capsys.readouterr().out, order, fetched, verdicts


def test_the_billed_path_prints_the_projection_by_name(monkeypatch, capsys) -> None:
    """**By name, not "some number was printed".**

    The FLOOR banner is the part that makes the figure honest -- per-event
    pricing excludes Apify platform usage, which on scraping actors is
    routinely the larger line. A cost line without it would be worse than none.
    """
    out, *_ = _billed_run(monkeypatch, capsys)
    assert "transcripts to fetch" in out
    assert "projected cost" in out
    assert "FLOOR" in out
    assert "EXCLUDES APIFY PLATFORM USAGE" in out


def test_the_caption_kind_is_checked_before_the_billed_fetch(
    monkeypatch, capsys
) -> None:
    """#318b. The free `list_only` mode must run FIRST, or it buys nothing.

    Asserting the order is the whole test: a call to `list_transcripts`
    after `fetch_transcripts` would be a diagnostic about money already spent.
    """
    out, order, *_ = _billed_run(monkeypatch, capsys)
    assert "list_transcripts" in order, (
        "the free caption-kind check never ran"
    )
    assert order.index("list_transcripts") < order.index("fetch_transcripts"), (
        "the caption kind must be checked BEFORE paying, not after"
    )
    assert "manual" in out.lower(), "the caption-kind mix must be reported"


def test_a_failed_caption_check_does_not_abort_the_billed_run(
    monkeypatch, capsys
) -> None:
    """**A fourth defect, found by re-reading the path after changing it, and
    introduced BY the change.**

    `list_transcripts` does not catch what `_run_actor` raises -- unlike
    `fetch_transcripts`, which absorbs a batch failure per batch. Adding the
    caller therefore put a FREE, ADVISORY diagnostic in a position to abort a
    paid run before a single transcript was fetched. The check that costs
    nothing must not become the thing that costs the run.
    """
    from core.services import video as svc
    import core.db as db

    def exploding_kinds(ids, **kw):
        raise video_api.VideoApiError("actor returned 503 -- retryable")

    monkeypatch.setattr(video_api, "list_transcripts", exploding_kinds)
    out, order, *_ = _billed_run(monkeypatch, capsys, kinds_impl=exploding_kinds)

    assert "CHECK FAILED" in out
    assert "fetch_transcripts" in order, (
        "a failed free check aborted the paid run"
    )
    assert "transcript(s) stored" in out


def test_the_dump_path_is_printed_on_the_billed_path(
    monkeypatch, capsys, tmp_path
) -> None:
    """A dump nobody can find is a dump nobody has."""
    out, *_ = _billed_run(monkeypatch, capsys, dump=tmp_path / "actor.json")
    assert str(tmp_path / "actor") in out


# ---------------------------------------------------------------------------
# #324 -- the query is visible before it is paid for
# ---------------------------------------------------------------------------
def test_the_query_plan_is_printed_before_the_billed_fetch(
    monkeypatch, capsys
) -> None:
    """**THE FIRST BILLED RUN PRINTED EVERYTHING EXCEPT THE REQUEST.**

    A caption-kind mix, a cost floor, a stored count -- and the one thing that
    was wrong, the payload, appeared nowhere. Four videos were asked for a
    manual English track they do not have, and the operator watching the run
    had no way to see it.

    The plan is asserted **by its content**, not by "something was printed": the
    two stubbed videos imply two different questions, so the line has to name
    `manual` and `any` and it has to say how many BILLED calls that costs.
    """
    out, order, *_ = _billed_run(monkeypatch, capsys)

    assert "the query, PER VIDEO" in out
    assert "2 distinct question(s) -> 2 BILLED actor call(s)" in out
    assert "manual" in out and "any" in out
    plan_at = out.index("the query, PER VIDEO")
    fetch_at = out.index("transcript(s) stored")
    assert plan_at < fetch_at, "the plan must be printed before the money is spent"


def test_a_video_with_no_caption_track_is_terminal_and_is_never_fetched(
    monkeypatch, capsys
) -> None:
    """**THE ONE TERMINAL VERDICT, AND THE ONLY PLACE IT MAY BE TAKEN (#322).**

    `unavailable` used to be written from an empty fetch response -- the actor
    saying nothing, read as the actor saying "this video has no captions" -- and
    from an exhausted retry counter. Both doors are closed. The verdict now
    comes from the FREE listing enumerating the tracks and finding none.

    **And the video is not fetched.** There is nothing to buy: a fetch for a
    video the free check says has no track cannot return a transcript, and every
    actor call carries Apify platform usage whatever its per-event price (#321).
    """

    def no_tracks(ids, **kw):
        return {
            "abc123": video_api.TrackListing(
                youtube_id="abc123", tracks=(), kind=None
            ),
            "def456": video_api.TrackListing(
                youtube_id="def456",
                tracks=(
                    video_api.Track(
                        language_code="en", language="English", is_generated=True
                    ),
                ),
                kind="generated",
            ),
        }

    out, order, fetched, verdicts = _billed_run(
        monkeypatch, capsys, kinds_impl=no_tracks
    )

    assert "abc123" not in fetched, (
        "a video the free listing says has no track must not be paid for"
    )
    assert fetched == ["def456"]
    assert ("1", True) in verdicts, "the no-track video must be recorded terminal"
    assert "NO caption track at all" in out
