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
"""

from __future__ import annotations

import argparse
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


def _live(settings, pool, args) -> int:
    """Poll YouTube (quota only), then price or fetch the transcript step."""
    from core.db import connection
    from core.services import video as svc
    from core import video_api

    if not settings.youtube_api_key:
        print("YOUTUBE_API_KEY is not set. It lives on production only.")
        return 1
    if args.apply and not settings.apify_token:
        print("APIFY_TOKEN is not set. It lives on production only.")
        return 1

    now = datetime.now(timezone.utc)
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
        print(f"Fetching {len(pending)} transcript(s). THIS IS BILLED.")
        if pending:
            results = video_api.fetch_transcripts(
                [row.youtube_id for row in pending],
                token=settings.apify_token,
                actor=settings.apify_transcript_actor,
                prefer_manual=True,
            )
            ok = 0
            for row in pending:
                outcome = results.get(row.youtube_id)
                if isinstance(outcome, video_api.Transcript):
                    svc.record_transcript(
                        conn,
                        video_id=row.video_id,
                        text=outcome.text,
                        lang=outcome.lang,
                        kind=outcome.kind,
                    )
                    ok += 1
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
            print(f"  {ok} transcript(s) stored.")

        degraded = _recompute_coverage(conn, svc)
        purge = svc.purge_stale(conn, now=now)
        conn.commit()
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
