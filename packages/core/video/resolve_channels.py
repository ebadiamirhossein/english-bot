"""Resolve the channel pool's handles to channel ids. Prints; writes nothing.

    python -m core.video.resolve_channels

Why this exists as a command rather than as a step inside `refresh`: handles
change and channel ids do not, so `data/video_channels.json` stores ids -- and
an id must not be typed from memory or inferred from a URL. This command is the
one place the mapping is established, the operator pastes the output into the
file, and `core.video.channels` refuses any entry still holding a null id or a
handle.

**It writes no file.** Editing `data/video_channels.json` is a human decision --
the accent and the track next to each id are authored, not derived, and a
command that rewrote the file would be a command that could quietly change them.

Costs YouTube Data API quota (one unit per handle) and no money.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve @handles to YouTube channel ids. Prints the mapping and "
            "writes nothing; paste the ids into data/video_channels.json."
        )
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="channel pool to read handles from (default: the committed one)",
    )
    parser.add_argument(
        "--handle",
        action="append",
        default=None,
        help="resolve this handle instead of reading the pool; repeatable",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    from core.config import ConfigError, load_settings
    from core.video import channels as channel_file
    from core.video_api import VideoApiError, resolve_handle

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    if not settings.youtube_api_key:
        print(
            "YOUTUBE_API_KEY is not set.\n\n"
            "  It lives on production, in /home/bot/english-bot/.env. This "
            "command cannot run without it and will not run degraded."
        )
        return 1

    if args.handle:
        handles = list(args.handle)
    else:
        try:
            pool = channel_file.load(args.file)
        except channel_file.ChannelFileError as exc:
            print(f"cannot read the channel pool: {exc}")
            return 1
        handles = [c.handle for c in pool.channels]
        handles += [r.handle for r in pool.refusals]

    if not handles:
        print("no handles to resolve.")
        return 1

    print(f"Resolving {len(handles)} handle(s). Quota only; nothing is billed.\n")
    failures = 0
    for handle in handles:
        try:
            ref = resolve_handle(handle, api_key=settings.youtube_api_key)
        except VideoApiError as exc:
            # Named and counted, never skipped: a handle that silently vanished
            # here would become a channel silently missing from the pool.
            print(f"  {handle:<32} !! {exc}")
            failures += 1
            continue
        print(f"  {handle:<32} -> {ref.channel_id}   ({ref.title})")

    print(
        "\nPaste each id into data/video_channels.json as `channel_id`.\n"
        "Nothing was written by this command."
    )
    if failures:
        print(f"{failures} handle(s) did not resolve and are listed above.")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
