"""Fill `videos.transcript_cues` from `--dump` files already on the host.

    python -m core.video.backfill_cues --dumps /home/bot/phase-b-fixtures   # dry
    python -m core.video.backfill_cues --dumps /home/bot/phase-b-fixtures --apply

**MAKES NO NETWORK CALL AND SPENDS NOTHING. There is no `--live`, because there
is nothing live to do.** T5 established that the timings are already on disk, in
responses `--dump` wrote **verbatim** (`video_api.py`'s dump branch, the #317
fix) during runs that were billed months ago. **A billed re-fetch was the
alternative and it is not needed** -- if this command ever appears to need one,
it has gone wrong.

Human-run and **dry by default**, on `core.lessons.generate`'s precedent: the
dry run prints exactly what `--apply` would do, against the same database, so
the operator sees both and they are not the same claim.

────────────────────────────────────────────────────────────────────────────────
THE IDENTITY GATE IS THE WHOLE GUARANTEE

For each row: join the dump's cue texts with a single space, and compare **md5
against the stored `videos.transcript`**. **Write only on an exact match.**

**A MISMATCH IS REPORTED AND SKIPPED, NEVER REPAIRED.** It means the stored text
came from a different fetch than the cues, and writing anyway would put
**coverage over one string and the highlight over another** -- two instruments on
one screen, agreeing until they do not. That is the failure T5's fifth question
existed to prevent, and it is the reason this command compares hashes rather than
lengths: `thanks` and `thankS` are the same length and a different transcript.

**The same check runs on the fetch path** (`core.services.video.record_transcript`),
through the same function, so the two cannot drift into disagreeing about what
identity means.

────────────────────────────────────────────────────────────────────────────────
WHAT IT LEAVES BEHIND, AND THAT IS SPECIFIED RATHER THAN A GAP

This reaches only rows a dump covers. **`assign` selects from the pool, not from
the dumped subset**, so rows with a transcript and no cues are the ORDINARY case
until the pool turns over. Such a row renders, its words stay tappable, the
coverage badge still shows, and there is no follow-along highlight.

**It does not drain on its own.** The fetch path fills cues on re-fetch, but
**nothing refreshes on a schedule** -- no cron, no worker, the CLIs are human-run
by operator ruling (#69). So the command PRINTS THE REMAINDER as a number, and
the number is the operator's to act on by running a refresh, not this command's
to hide.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: The keys a dump row may carry its timestamped variant under. Mirrors the
#: adapters' `cues_keys` rather than restating a third opinion.
CUE_KEYS = ("timestamped", "segments")

#: The keys a dump row may carry its video id under. Mirrors `_row_video_id`.
ID_KEYS = ("video_id", "videoId", "id", "youtube_id")


def _video_id(row: dict) -> str | None:
    for key in ID_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _cues(row: dict) -> list | None:
    for key in CUE_KEYS:
        value = row.get(key)
        if isinstance(value, list) and value:
            return [v for v in value if isinstance(v, dict)]
    return None


def read_dumps(root: Path) -> dict[str, list]:
    """`youtube_id -> cue list`, from every `actor.fetch.*.json` under ``root``.

    **Reads, and does not copy.** The dumps are not brought into the repository:
    run3's single file is 828 KB of scraped third-party transcript text, and
    **#175** asks the licence question **before** third-party data enters a
    repository serving a commercial product (PRODUCT-PRINCIPLES §3). The one
    actor response this project has committed is a **listing** -- 6,900 bytes of
    language codes and `is_generated` flags, **no transcript text at all** -- so
    it is no precedent for these. The tests use a synthesised track carrying the
    measured shape instead.

    **Later files win on a duplicate id**, and the run order is the sorted file
    order, so a re-fetch recorded in a later dump supersedes an earlier one.
    """
    found: dict[str, list] = {}
    for path in sorted(root.rglob("actor.fetch.*.json")):
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, ValueError) as exc:
            print(f"  ! {path}: unreadable ({exc})")
            continue
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            youtube_id = _video_id(row)
            cues = _cues(row)
            if youtube_id and cues:
                found[youtube_id] = cues
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fill videos.transcript_cues from --dump files already on disk. "
            "Dry by default; --apply writes. Makes no network call and "
            "spends nothing."
        )
    )
    parser.add_argument(
        "--dumps",
        required=True,
        type=Path,
        help="directory holding the run dumps, searched recursively",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the cues (default is a dry run that writes nothing)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if not args.dumps.is_dir():
        print(f"--dumps is not a directory: {args.dumps}")
        return 2

    from core.db import connection
    from core.services import video as svc
    from core.video.cues import normalise_cues, reproduces

    print(f"Reading dumps under {args.dumps} ...")
    dumped = read_dumps(args.dumps)
    print(f"  {len(dumped)} video(s) with a timestamped variant.\n")

    written = matched = mismatched = unusable = 0

    with connection() as conn:
        candidates = svc.rows_needing_cues(conn)
        print(f"{len(candidates)} stored transcript(s) have no cues.\n")

        for video_id, youtube_id, text in candidates:
            raw = dumped.get(youtube_id)
            if raw is None:
                continue

            checked = normalise_cues(raw)
            if checked is None:
                # A `start` missing, a descending track, or a shape that is not
                # a list of mappings. **Refused whole**, never half-used: a
                # partial timing set would light some lines and skip others.
                unusable += 1
                print(f"  ! {youtube_id}: cue list unusable -- skipped")
                continue

            if not reproduces(checked, text):
                # **THE GATE. Reported and skipped, never repaired.**
                mismatched += 1
                print(
                    f"  ! {youtube_id}: {len(checked)} cue(s) do NOT reproduce "
                    f"the stored transcript ({len(text)} chars) -- skipped. "
                    "The stored text came from a different fetch than these "
                    "cues; writing them would describe text that is not there."
                )
                continue

            matched += 1
            if not args.apply:
                print(f"  = {youtube_id}: {len(checked)} cue(s) would be written")
                continue

            if svc.record_cues(conn, video_id=video_id, cues=raw, text=text):
                written += 1
                print(f"  + {youtube_id}: {len(checked)} cue(s) written")
            else:
                # The `WHERE transcript_cues IS NULL AND transcript = %s` guard
                # refused it: something else wrote cues, or the transcript
                # changed, between the read and the write.
                print(f"  ~ {youtube_id}: refused by the write guard -- skipped")

        if args.apply:
            conn.commit()

        remaining = len(svc.rows_needing_cues(conn))

    print(
        f"\n{matched} matched, {mismatched} mismatched, {unusable} unusable"
        + (f", {written} written." if args.apply else ", 0 written (dry run).")
    )
    print(
        f"{remaining} stored transcript(s) still have no cues. "
        "**They render, stay tappable and keep their coverage badge; they have "
        "no follow-along highlight.** Nothing drains this on a schedule (#69) "
        "-- a refresh fills them, and that is yours to run."
    )
    if not args.apply:
        print("\ndry run -- nothing was written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
