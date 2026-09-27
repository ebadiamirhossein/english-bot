"""Refresh the candidate pool, fetch transcripts, compute coverage, purge.

    python -m core.video.refresh                 # dry. No network at all.
    python -m core.video.refresh --live          # QUOTA ONLY. Prices the billed
                                                 # step exactly. No money spent.
    python -m core.video.refresh --live --apply  # billed, attended, writes.

**A DELIBERATE DIVERGENCE FROM `core.lessons.generate`, RECORDED HERE RATHER
THAN LEFT TO BE NOTICED.** In that command `--live` is the billed step and
`--apply` writes what `--live` already paid for. Here `--live` alone makes only
YouTube Data API calls, which cost quota and no money, and **the Apify calls --
the only ones that cost money -- happen only under `--apply`.**

The reason is that this pipeline's cost is not knowable in advance. Apify's
per-event price excludes platform usage, and the number of transcripts actually
needed depends on what the channel poll returns. So `--live` exists to do the
free half completely and then price the paid half from real numbers rather than
from an estimate. Paying first and printing the total afterwards would make the
projection useless exactly when it matters -- the first run.

There is no `--dry` flag, matching every other CLI in this repository: dry is
what happens when you pass nothing.

**W24r (D): `run_scheduled` IS `--live --apply` FOR THE WORKER.** The weekly
`refresh_videos` job calls `_live` -- the same function this CLI's `--live
--apply` calls, the same purge, the same coverage recompute -- with a fixed
`now`, at most `AUTO_TRANSCRIPT_CEILING` transcripts, and the printout captured
rather than logged. A billed run the system makes on a schedule, on the
operator's ruling of 2026-09-27 (an exception to #196, scoped to that job).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Apify's published per-event price for the ruled actor, FREE tier, as read
#: from the actor's pricing on 2026-08-31: $0.0000116 per video processed plus
#: $0.00001 per dataset row stored. The actor-start event is per run per GB.
#:
#: THIS IS A FLOOR AND NOT A BILL. Per-event pricing EXCLUDES Apify platform
#: usage -- compute units, storage, proxy -- which on scraping actors is
#: routinely the larger line. The projection says so every time it prints, and
#: the multiplier between this floor and the real console charge is measured at
#: the first live run and recorded. Until then this number is a lower bound and
#: nothing else.
PRICE_PER_VIDEO_USD = 0.0000116
PRICE_PER_ROW_USD = 0.00001
PRICE_PER_RUN_USD = 0.00001

#: Videos listed per channel per refresh.
DEFAULT_PER_CHANNEL = 15
#: Transcripts fetched in one run. A ceiling on the bill, and on the blast
#: radius of a bad run.
DEFAULT_TRANSCRIPT_LIMIT = 40
#: W24r (D). The hard ceiling on one scheduled run, whatever a caller asks for:
#: the operator ruled the weekly job on a measured cost under $1 a run at 40.
AUTO_TRANSCRIPT_CEILING = 40


class RefreshFailed(Exception):
    """A scheduled refresh that could not run. The message carries the exit
    code only -- never the captured printout, which names videos."""


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.4f}"


def _projection(transcripts: int) -> str:
    floor = (
        transcripts * (PRICE_PER_VIDEO_USD + PRICE_PER_ROW_USD)
        + PRICE_PER_RUN_USD
    )
    return (
        f"  transcripts to fetch : {transcripts}\n"
        f"  projected cost       : {_fmt_usd(floor)}\n"
        f"  *** FLOOR -- EXCLUDES APIFY PLATFORM USAGE (compute, storage,\n"
        f"      proxy). THIS IS NOT A BILL. Read the real charge from the\n"
        f"      Apify console after the run and record the multiplier. ***"
    )


def _print_caption_kinds(youtube_ids: list[str], listings: dict) -> None:
    """What the FREE check found, named per bucket rather than counted alone.

    **`unknown` is its own bucket and is never folded into `generated`.** An
    absent field and an auto-generated track are different facts, and a line
    that reported them as one would be the column claiming a kind it is
    guessing -- #257's shape.

    An actor with no `list_only` mode returns `{}`, and this says so rather
    than printing three zeroes that read as "checked, found nothing".
    """
    if not listings:
        print(
            "\n  caption kinds: NOT CHECKED -- this actor has no free\n"
            "    discovery mode, so PRD §7.2's preference cannot be verified\n"
            "    before paying (#318)."
        )
        return
    kinds = {v: listing.kind for v, listing in listings.items()}
    manual = [v for v in youtube_ids if kinds.get(v) == "manual"]
    generated = [v for v in youtube_ids if kinds.get(v) == "generated"]
    unknown = [v for v in youtube_ids if v not in kinds or kinds.get(v) is None]
    print(
        f"\n  caption kinds, from the FREE list_only check (no per-video charge):\n"
        f"    manual    {len(manual)}\n"
        f"    generated {len(generated)}\n"
        f"    unknown   {len(unknown)}"
    )
    if generated or unknown:
        print(
            "    Auto-generated captions are lowercase, so the proper-noun rule\n"
            "    switches off and coverage comes back INFLATED (#288). These are\n"
            "    still fetched -- this line reports, it does not filter."
        )


def _print_query_plan(youtube_ids: list[str], listings: dict, actor: str) -> None:
    """The exact question this run will ask about each video, BEFORE paying.

    **THIS LINE EXISTS BECAUSE THE FIRST BILLED RUN ASKED AN UNANSWERABLE ONE
    AND NOTHING SHOWED IT (#324).** The payload was `transcript_type: "manual"`
    with `languages` unset, so the actor's `["en"]` default applied and four of
    five videos were being asked for a manual English track they do not have.
    The run printed a caption-kind mix, a cost floor and a stored count, and not
    one of them contained the request.

    **AND IT IS ALSO THE COST LINE MY OWN CHANGE OWES.** The actor takes ONE
    `transcript_type` per run, so asking different questions means more runs,
    and an actor run carries Apify platform usage whatever its per-event price
    (#321). The number of billed calls is therefore printed as a number, before
    the operator lets the run proceed.
    """
    from core import video_api

    adapter = video_api.adapter_for(actor)
    groups: dict[video_api.Query, list[str]] = {}
    for video_id in youtube_ids:
        groups.setdefault(
            video_api.plan_query(listings.get(video_id), adapter), []
        ).append(video_id)

    print(
        f"\n  the query, PER VIDEO, derived from the free listing (#324):\n"
        f"    {len(groups)} distinct question(s) -> {len(groups)} BILLED actor "
        f"call(s), plus the free listing call already made"
    )
    for query, ids in groups.items():
        kind = query.transcript_type or "(actor default)"
        langs = ", ".join(query.languages) or "(actor default)"
        print(f"    {kind:<8} {langs:<16} {len(ids):>3} video(s): {' '.join(ids)}")
    if not listings:
        print(
            "    NO LISTING WAS AVAILABLE, so every video gets the same written\n"
            "    -down default. That is not the old defect -- the old default was\n"
            "    `manual` + an unstated `[\"en\"]`, which cannot be satisfied by a\n"
            "    video with only auto-generated captions."
        )


def _print_pool(counts: dict[str, int], degraded: int | None) -> None:
    total = sum(counts.values())
    print(f"\nPool: {total} video(s)")
    for status in ("ok", "pending", "failed", "unavailable"):
        print(f"  {status:<12} {counts.get(status, 0)}")
    if degraded is not None:
        print(
            f"\n  coverage rows computed with the proper-noun rule OFF: {degraded}\n"
            "    Those candidates are EXCLUDED from selection: their coverage is\n"
            "    inflated by the names in the top-frequency floor (#288). If this\n"
            "    number is large the pool may starve, and that is a finding for\n"
            "    the operator to rule on -- not a fallback this command takes."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the video pool. Dry by default. --live makes quota-only "
            "YouTube calls and prices the billed step; --apply spends money."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="poll YouTube (quota, no money) and price the transcript step",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="fetch transcripts (BILLED), write rows, compute coverage, purge",
    )
    parser.add_argument(
        "--file", type=Path, default=None, help="channel pool file to read"
    )
    parser.add_argument(
        "--per-channel",
        type=int,
        default=DEFAULT_PER_CHANNEL,
        help=f"videos listed per channel (default {DEFAULT_PER_CHANNEL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_TRANSCRIPT_LIMIT,
        help=f"transcripts fetched this run (default {DEFAULT_TRANSCRIPT_LIMIT})",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        default=None,
        help=(
            "write every actor response VERBATIM beside this path, before any "
            "reduction (#317). One file per call: PATH.fetch.001.json, "
            "PATH.list.001.json. This is how transcript fixtures are made"
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.apply and not args.live:
        print(
            "--apply requires --live. Writing the pool means fetching it, and a\n"
            "silent no-op that printed a success is the failure mode this\n"
            "refuses to have."
        )
        return 2

    from core.config import ConfigError, load_settings
    from core.video import channels as channel_file

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    try:
        pool = channel_file.load(args.file)
    except channel_file.ChannelFileError as exc:
        print(f"cannot read the channel pool: {exc}")
        return 1

    print(f"Channel pool: {len(pool.channels)} usable, {len(pool.refusals)} refused")
    for channel in pool.channels:
        # **NOT `{channel.accent:<9}` -- that raises `TypeError: unsupported
        # format string passed to NoneType.__format__` on a by-ruling null
        # accent (migration 020), on the FIRST LINE THIS COMMAND PRINTS**, before
        # a single channel is polled. `--` is shown rather than the word "None",
        # which would read as a value.
        accent = channel.accent if channel.accent is not None else "--"
        print(f"  + {channel.handle:<30} {accent:<9} {channel.track}")
    for refusal in pool.refusals:
        # Named, never counted-and-dropped. A refused channel that only showed
        # up as a smaller number is a pool that shrank without anybody told.
        print(f"  ! {refusal.handle:<30} {refusal.reason}")

    if not pool.channels:
        print(
            "\nNo usable channel. Nothing to poll.\n"
            "Run `python -m core.video.resolve_channels`, paste the ids into\n"
            "data/video_channels.json, and author the null accents."
        )
        return 1

    if not args.live:
        return _dry(pool, args)

    return _live(settings, pool, args)


def _dry(pool, args) -> int:
    """No network. What the database holds, and what a live run would cost."""
    from core.db import connection
    from core.services import video as svc

    projected = len(pool.channels) * args.per_channel
    print(
        f"\nDRY RUN -- nothing was called and nothing was written.\n\n"
        f"  channels to poll     : {len(pool.channels)}\n"
        f"  videos to list       : up to {projected} "
        f"({args.per_channel} per channel, quota only)"
    )

    try:
        with connection() as conn:
            counts = svc.pool_counts(conn)
            needing = len(
                svc.videos_needing_transcript(conn, limit=args.limit)
            )
            degraded = svc.degraded_coverage_count(conn)
    except Exception as exc:  # noqa: BLE001 - no database configured
        print(f"\n  (no database reachable, so the pool is unknown: {exc})")
        print(_projection(projected))
        return 0

    _print_pool(counts, int(degraded))
    print("\nIf run with --live --apply:")
    print(_projection(min(needing, args.limit)))
    return 0


def run_scheduled(settings, *, now: datetime, limit: int = AUTO_TRANSCRIPT_CEILING) -> dict[str, int]:
    """The worker's weekly refresh: `--live --apply`, the same code, unattended.

    **Billed** (Apify), at most `AUTO_TRANSCRIPT_CEILING` transcripts however
    large ``limit`` is. ``now`` stamps every row and dates the 30-day purge.
    `_live`'s printout is captured and dropped -- the worker logs one line of
    counts (CLAUDE.md §5: no titles) -- and a run that cannot start (no keys,
    no channel file) raises `RefreshFailed` so `run_job` reports it to Sentry.

    Returns the pool's counts by status after the run, plus what this run did:
    ``stored``, ``channels_failed`` and ``purged``.
    """
    from core.db import connection
    from core.services import video as svc
    from core.video import channels as channel_file

    try:
        pool = channel_file.load(None)
    except channel_file.ChannelFileError as exc:
        raise RefreshFailed("the channel pool file could not be read") from exc
    if not pool.channels:
        raise RefreshFailed("no usable channel in the pool file")
    args = argparse.Namespace(
        per_channel=DEFAULT_PER_CHANNEL,
        limit=min(limit, AUTO_TRANSCRIPT_CEILING),
        dump=None,
        apply=True,
    )
    report: dict[str, int] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        code = _live(settings, pool, args, now=now, report=report)
    if code != 0:
        raise RefreshFailed(f"the refresh exited {code}")
    with connection() as conn:
        counts = svc.pool_counts(conn)
    return {
        **{status: counts.get(status, 0) for status in ("ok", "pending", "failed", "unavailable")},
        **report,
    }


def _live(settings, pool, args, *, now: datetime | None = None,
          report: dict[str, int] | None = None) -> int:
    """Poll YouTube (quota only), then price or fetch the transcript step.

    ``now`` and ``report`` are W24r's, for `run_scheduled`: the CLI passes
    neither and reads the wall clock, as it always did.
    """
    from core.db import connection
    from core.services import video as svc
    from core import video_api

    report = {} if report is None else report

    if not settings.youtube_api_key:
        print("YOUTUBE_API_KEY is not set. It lives on production only.")
        return 1
    if args.apply and not settings.apify_token:
        print("APIFY_TOKEN is not set. It lives on production only.")
        return 1

    now = now or datetime.now(timezone.utc)
    listed: list[tuple[str, object]] = []
    failures: list[str] = []

    print("\nPolling channels (YouTube Data API -- quota, no money)...")
    for channel in pool.channels:
        try:
            ref = video_api.resolve_handle(
                channel.handle, api_key=settings.youtube_api_key
            )
            ids = video_api.list_channel_videos(
                ref.uploads_playlist_id,
                api_key=settings.youtube_api_key,
                max_videos=args.per_channel,
            )
            metas = video_api.fetch_video_metadata(
                ids, api_key=settings.youtube_api_key
            )
        except video_api.VideoApiError as exc:
            # The run continues. A poll that stopped at the first bad channel
            # would leave a pool that looks complete and is not.
            failures.append(f"{channel.handle}: {exc}")
            print(f"  ! {channel.handle:<30} {exc}")
            continue
        print(f"  + {channel.handle:<30} {len(metas)} video(s)")
        for meta in metas.values():
            listed.append((channel, meta))

    report["channels_failed"] = len(failures)
    if failures:
        print(f"\n{len(failures)} channel(s) failed and are listed above.")

    if not args.apply:
        print(
            f"\nLIVE (quota only) -- NO MONEY WAS SPENT AND NOTHING WAS WRITTEN.\n"
            f"\n  videos listed        : {len(listed)}"
        )
        print(_projection(min(len(listed), args.limit)))
        print(
            "\nRe-run with --live --apply to write these rows and fetch their\n"
            "transcripts. That run is billed."
        )
        return 0

    with connection() as conn:
        written = 0
        for channel, meta in listed:
            svc.upsert_video(
                conn,
                youtube_id=meta.youtube_id,
                channel_id=channel.channel_id,
                accent=channel.accent,
                track=channel.track,
                title=meta.title,
                duration_s=meta.duration_s,
                published_at=meta.published_at,
                now=now,
            )
            written += 1
        conn.commit()
        print(f"\nWrote {written} pool row(s).")

        pending = svc.videos_needing_transcript(conn, limit=args.limit)
        # **A CANDIDATE COUNT, NOT YET A BILL.** The free listing runs next and
        # can remove videos from it -- see the terminal skip below -- so the
        # number that is actually paid for is the one `_projection` prints
        # after that, and it is never larger than this one.
        print(f"{len(pending)} candidate(s) for the BILLED fetch.")
        if pending:
            youtube_ids = [row.youtube_id for row in pending]

            # **THE FREE CHECK RUNS FIRST, WHICH IS THE ONLY ORDER IN WHICH IT
            # BUYS ANYTHING (#318b).** `list_transcripts` uses the actor's
            # `list_only` mode, which the actor documents as not charged as a
            # videoprocessed event -- it is what `video_api`'s own docstring
            # calls "what makes PRD §7.2's human-captions preference verifiable
            # without paying to find out", and until now it had NO PRODUCTION
            # CALLER. Called after the fetch it would be a diagnostic about
            # money already spent.
            #
            # **IT REPORTS AND DOES NOT DECIDE, AND SINCE #324 IT ALSO
            # CHOOSES THE QUERY -- WHICH IS NOT THE SAME THING.** Skipping the
            # generated-only videos would change what this run buys, and that
            # is a ruling nobody has taken -- #288 says auto-generated captions
            # inflate coverage, which argues for skipping, and a thin pool
            # argues against. **The 2026-09-01 ruling is the opposite: a video
            # with only auto-generated captions IS FETCHED**, asked for with
            # `any` instead of `manual`, and its kind recorded. So the listing
            # now decides HOW each video is asked for and still does not decide
            # WHETHER it is bought -- with the single exception below, where the
            # listing says there is nothing to buy.
            # **THE ADVISORY CHECK MUST NOT BE ABLE TO KILL THE PAID RUN.**
            # `list_transcripts` does not catch what `_run_actor` raises,
            # unlike `fetch_transcripts`, which absorbs a batch failure per
            # batch. Without this, an Apify hiccup during a FREE diagnostic
            # would abort a run before a single transcript was fetched -- a
            # check that costs nothing becoming the thing that costs the run.
            try:
                listings = video_api.list_transcripts(
                    youtube_ids,
                    token=settings.apify_token,
                    actor=settings.apify_transcript_actor,
                    dump_to=args.dump,
                )
            except (video_api.VideoApiError, video_api.TranscriptFetchFailed) as exc:
                print(
                    f"\n  caption kinds: CHECK FAILED ({exc}).\n"
                    "    The run continues -- this check is advisory and its\n"
                    "    failure says nothing about whether the transcripts\n"
                    "    can be fetched."
                )
                listings = {}
            else:
                _print_caption_kinds(youtube_ids, listings)

            # **THE ONE TERMINAL VERDICT, AND IT IS TAKEN BEFORE PAYING RATHER
            # THAN INFERRED AFTERWARDS (#322, #324, ruled 2026-09-01).** A
            # listing that enumerated a video's tracks and found NONE is the
            # actor stating absence. Everything else -- an empty fetch response,
            # a missing row, an exhausted retry counter -- is the pipeline
            # failing, and none of those may write `unavailable` any more.
            #
            # **AND THE FETCH IS SKIPPED FOR THEM, WHICH IS A DECISION AND NOT A
            # CONSEQUENCE.** #318b's rule is that the free check REPORTS and does
            # not DECIDE, and skipping the generated-only videos was refused
            # under it. This is a different case: there is nothing to buy. A
            # fetch for a video the free listing says has no track cannot return
            # a transcript, and every actor call carries platform usage (#321).
            # Named here so the operator can rule against it in one line.
            terminal = {
                row.youtube_id: verdict
                for row in pending
                if (
                    verdict := video_api.terminal_from_listing(
                        listings.get(row.youtube_id)
                    )
                )
                is not None
            }
            if terminal:
                print(
                    f"\n  {len(terminal)} video(s) have NO caption track at all, "
                    "by the free listing.\n"
                    "    These are recorded `unavailable` -- the one terminal "
                    "verdict this\n"
                    "    pipeline takes -- and are NOT fetched. Nothing to buy."
                )
                for video_id in terminal:
                    print(f"    - {video_id}")
                youtube_ids = [v for v in youtube_ids if v not in terminal]

            _print_query_plan(youtube_ids, listings, settings.apify_transcript_actor)

            # **THE BILLED RUN NOW PRINTS A COST LINE LIKE EVERY CHEAPER PATH
            # ALREADY DID (#318a).** `_projection` was called on the dry path
            # and on `--live`, and nowhere here -- so the operator saw a FLOOR
            # figure exactly when nothing would be spent, and no figure at all
            # when money would be. The banner it carries is the load-bearing
            # half: per-event pricing excludes Apify platform usage.
            print(_projection(len(youtube_ids)))
            if args.dump:
                print(
                    f"\n  actor responses will be written VERBATIM beside\n"
                    f"    {args.dump}\n"
                    f"  as {args.dump.stem}.fetch.NNN{args.dump.suffix or '.json'} "
                    f"-- this is what the fixtures are made from (#317)."
                )

            results: dict[str, object] = {}
            if youtube_ids:
                results.update(
                    video_api.fetch_transcripts(
                        youtube_ids,
                        token=settings.apify_token,
                        actor=settings.apify_transcript_actor,
                        listings=listings,
                        dump_to=args.dump,
                    )
                )
            # **THE TERMINAL VERDICTS ARE APPLIED LAST, AND THE OVERLAP THEY
            # GUARD AGAINST CANNOT HAPPEN ON THIS PATH** -- those ids were
            # removed from `youtube_ids` before the fetch, so no row can come
            # back for them. Written this way round anyway: if an actor ever
            # returned an unrequested row, the free listing's positive statement
            # about the tracks is the better evidence, and a verdict that
            # depended on dict-merge order would be the quietest possible bug.
            results.update(terminal)
            ok = 0
            cues_refused = 0
            for row in pending:
                outcome = results.get(row.youtube_id)
                if isinstance(outcome, video_api.Transcript):
                    stored_cues = svc.record_transcript(
                        conn,
                        video_id=row.video_id,
                        text=outcome.text,
                        lang=outcome.lang,
                        kind=outcome.kind,
                        cues=outcome.cues,
                    )
                    ok += 1
                    # **A REFUSED CUE LIST IS COUNTED WHERE THE OPERATOR SEES
                    # IT.** The transcript is stored either way; what is refused
                    # is a cue list whose join does not reproduce it. **A
                    # refusal nobody is shown is a silent fallback**, which is
                    # the shape `--allow-degraded` exists to avoid -- the
                    # operator rules on a degraded input rather than inheriting
                    # it. Printed in the summary below, on
                    # `degraded_coverage_count`'s precedent.
                    if not stored_cues:
                        cues_refused += 1
                else:
                    status = svc.record_transcript_failure(
                        conn,
                        video_id=row.video_id,
                        error=str(outcome or "no result returned"),
                        terminal=isinstance(
                            outcome, video_api.TranscriptUnavailable
                        ),
                    )
                    print(f"  ! {row.youtube_id}  -> {status}: {outcome}")
            conn.commit()
            report["stored"] = ok
            print(f"  {ok} transcript(s) stored.")
            if cues_refused:
                # **NAMED, NOT SUMMED INTO A SUCCESS COUNT.** These rows have a
                # transcript and no cue timings: they render, their words stay
                # tappable, the coverage badge still shows, and there is no
                # follow-along highlight. That is a specified state, and the
                # operator is told which rows are in it rather than finding out
                # from a screen.
                print(
                    f"  {cues_refused} of them stored NO cue timings: the "
                    "actor's timestamped variant did not reproduce the "
                    "transcript text, so the cues were refused rather than "
                    "stored against text they do not describe."
                )

        degraded = _recompute_coverage(conn, svc)
        purge = svc.purge_stale(conn, now=now)
        conn.commit()
        report.setdefault("stored", 0)
        report["purged"] = purge.purged
        print(
            f"\nPurge: {purge.purged} row(s) past {svc.RETENTION_DAYS} days had "
            f"their metadata and transcript nulled ({purge.scanned} scanned).\n"
            "  youtube_id and every assignment survived."
        )
        _print_pool(svc.pool_counts(conn), degraded)

    print(
        "\nConfirm the counts independently, in psql. A count this command "
        "prints about its own work is not verification of it."
    )
    return 0


def _recompute_coverage(conn, svc) -> int:
    """Recompute every learner's coverage over every usable transcript.

    ALWAYS RECOMPUTED, NEVER READ BACK. `video_coverage` is an audit record and
    not a cache, so there is no staleness to manage here -- the cost is CPU over
    text already stored, and no external call.
    """
    from core.lexicon.normalize import lexicon_digest
    from core.services.lexicon import coverage_for

    digest = lexicon_digest()
    rows = svc.selectable(conn)
    users = svc.onboarded_user_ids(conn)
    degraded = 0
    for user_id in users:
        for row in rows:
            if not row.transcript:
                continue
            report = coverage_for(conn, user_id, row.transcript)
            svc.record_coverage(
                conn,
                user_id=user_id,
                video_id=row.video_id,
                report=report,
                lexicon_digest=digest,
            )
            if not report.proper_nouns_detected:
                degraded += 1
    print(
        f"\nCoverage: {len(rows)} video(s) x {len(users)} learner(s) recomputed "
        f"on lexicon {digest}."
    )
    return degraded


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
