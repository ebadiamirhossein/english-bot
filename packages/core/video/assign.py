"""Score the pool and assign this week's three videos.

    python -m core.video.assign --user 1 --week-of 2026-09-07           # dry
    python -m core.video.assign --user 1 --week-of 2026-09-07 --apply   # writes

Makes no external call and spends no money: coverage is recomputed locally over
transcripts already stored. There is no `--live`, because there is nothing live
to do.

PRD §7.1 puts curated video on **Monday, Wednesday and Friday**; the two series
episodes on Tuesday and Thursday are the Language Reactor / Trancy import path
and are not this command's.

**IT REFUSES RATHER THAN ASSIGNING FEWER THAN THREE.** The pool empties itself
if it is not refreshed -- the 30-day purge runs on every refresh and there is no
cron -- so "two videos this week" is a symptom with a cause the learner cannot
see, and a silent short week is exactly the shape of a backlog that CLAUDE.md §4
forbids presenting.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

#: PRD §7.1: three curated videos a week, Mon/Wed/Fri.
WEEKDAYS = (0, 2, 4)
VIDEOS_PER_WEEK = len(WEEKDAYS)


def week_dates(week_of: date) -> list[date]:
    """The Mon/Wed/Fri of the week containing ``week_of``."""
    monday = week_of - timedelta(days=week_of.weekday())
    return [monday + timedelta(days=offset) for offset in WEEKDAYS]


def _ranking_line(entry) -> str:
    """One ranked candidate, as a line. **EXTRACTED SO IT CAN BE TESTED (#328).**

    It was four inline f-strings inside `main()`, reachable only by running the
    command against a database, which is why nothing caught the crash below.

    **`f"{None:<9}"` RAISES AND `f"{None}"` DOES NOT, WHICH IS THE WHOLE BUG.**
    `format(None, "<9")` is `TypeError: unsupported format string passed to
    NoneType.__format__`; the bare interpolation two columns to its left is
    fine. `Candidate.accent` is `str | None` by migration 020 -- `accent IS
    NULL` means *this channel is not a reliable accent signal* -- and TED-Ed is
    a by-ruling null in the committed pool. **So `assign` could not finish a dry
    run whenever TED-Ed was ranked, which is every run that lists it.**

    **THE SAME LINE WAS ALREADY FIXED ONE FILE OVER, IN PHASE A.**
    `refresh.py`'s channel-pool print carries a comment naming this exact
    `TypeError`. The sweep that produced it stopped at the file it was in, so
    the fix reached the command that LISTS the pool and not the one that RANKS
    it.

    **`--`, NEVER `str(accent)`.** `str(None)` is the string `"None"`, which
    reads as an accent somebody authored -- #315's failure mode arriving in the
    output instead of in the exposure map. `--` is what `refresh.py` prints, so
    the two commands describe the same pool the same way.
    """
    candidate = entry.candidate
    mark = "  " if entry.is_selectable else "x "
    accent = candidate.accent if candidate.accent is not None else "--"
    return (
        f"{mark}{candidate.youtube_id:<14} {entry.score:>6.3f}  "
        f"cov={candidate.coverage:.1%} {candidate.track:<9} "
        f"{accent:<9}"
        + (f"  [{entry.excluded}]" if entry.excluded else "")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Assign the week's three videos. Dry by default; --apply writes. "
            "Makes no external call and spends nothing."
        )
    )
    parser.add_argument("--user", required=True, type=int, help="users.id")
    parser.add_argument(
        "--week-of",
        required=True,
        help="any date in the target week, YYYY-MM-DD",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the assignments (default is a dry run that writes nothing)",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help=(
            "also consider videos whose coverage was computed with the "
            "proper-noun rule switched off. Inflated numbers (#288); the "
            "operator rules on this, it is never a silent fallback"
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    try:
        week_of = datetime.strptime(args.week_of, "%Y-%m-%d").date()
    except ValueError:
        print(f"--week-of must be YYYY-MM-DD (got {args.week_of!r})")
        return 2

    from core.db import connection
    from core.lexicon.normalize import lemmatize, lexicon_digest, tokenize
    from core.services import video as svc
    from core.services.lexicon import coverage_for
    from core.services.syllabus import unit_target_lexemes
    from core.video.score import BAND_HIGH, BAND_LOW, Candidate, rank

    dates = week_dates(week_of)
    print(
        f"Week of {dates[0]} -- assigning {VIDEOS_PER_WEEK} video(s) on "
        f"{', '.join(d.isoformat() for d in dates)}\n"
    )

    with connection() as conn:
        weights = svc.track_weights(conn, args.user)
        if weights is None:
            print(f"no user with id {args.user}")
            return 1

        taken = svc.assigned_dates(conn, args.user, dates)
        open_dates = [d for d in dates if d not in taken]
        if not open_dates:
            print("Every date this week already has an assignment. Nothing to do.")
            return 0
        if taken:
            print(f"  ({len(taken)} date(s) already assigned, leaving them alone)")

        rows = svc.selectable(conn)
        if not rows:
            print(_empty_pool_message())
            return 1

        digest = lexicon_digest()
        exposure = svc.accent_exposure(conn, args.user)
        seen = svc.seen_video_ids(conn, args.user)
        targets = _targets(conn, args.user, svc, unit_target_lexemes)

        candidates = []
        for row in rows:
            if not row.transcript:
                continue
            # Recomputed, never read back from video_coverage. The stored row is
            # an audit record; this is the number selection actually uses.
            report = coverage_for(conn, args.user, row.transcript)
            # WRITTEN ONLY UNDER --apply, and the guard is load-bearing rather
            # than tidy. `core.db.connection()` yields from the psycopg pool,
            # whose context manager COMMITS ON CLEAN EXIT -- verified, not
            # assumed. So an unguarded write here would be committed on the way
            # out of the `with` block below and a dry run would persist rows
            # while printing "nothing was written". A command that lies about
            # its own dryness is worse than one that has no dry mode.
            if args.apply:
                svc.record_coverage(
                    conn,
                    user_id=args.user,
                    video_id=row.video_id,
                    report=report,
                    lexicon_digest=digest,
                )
            candidates.append(
                Candidate(
                    video_id=row.video_id,
                    youtube_id=row.youtube_id,
                    track=row.track,
                    accent=row.accent,
                    duration_s=row.duration_s,
                    coverage=report.coverage,
                    proper_nouns_detected=report.proper_nouns_detected,
                    lemmas=_lemmas(row.transcript, tokenize, lemmatize),
                    seen=row.video_id in seen,
                )
            )
        if args.apply:
            conn.commit()
        else:
            # Belt and braces against the same pool-commits-on-exit behaviour:
            # nothing above wrote anything, and this makes that true even if a
            # later edit adds a write without noticing the guard.
            conn.rollback()

        scored = rank(
            candidates,
            track_weights=weights,
            accent_exposure=exposure,
            targets=targets,
            require_proper_nouns=not args.allow_degraded,
        )
        selectable = [s for s in scored if s.is_selectable and s.score > 0]
        excluded = [s for s in scored if not s.is_selectable]
        out_of_band = [s for s in excluded if "outside the ruled" in (s.excluded or "")]
        degraded = [s for s in excluded if "proper-noun rule" in (s.excluded or "")]

        print(f"Candidates: {len(candidates)}  selectable: {len(selectable)}")
        if degraded:
            print(
                f"  {len(degraded)} excluded: coverage computed with the "
                "proper-noun rule OFF (#288)."
            )
        if out_of_band:
            print(
                f"  {len(out_of_band)} excluded: coverage outside the ruled "
                f"{BAND_LOW:.0%}-{BAND_HIGH:.0%} band."
            )
        if excluded and len(excluded) > len(selectable):
            print(
                "  *** MORE CANDIDATES WERE EXCLUDED THAN KEPT. That is a\n"
                "      FINDING, not a threshold to relax. Report it and get a\n"
                "      ruling; #289 re-validates the band on real transcripts. ***"
            )

        print("\nRanking:")
        for entry in scored[:10]:
            print(_ranking_line(entry))

        if len(selectable) < len(open_dates):
            print(_short_pool_message(len(selectable), len(open_dates)))
            return 1

        chosen = selectable[: len(open_dates)]
        print("\nAssigning:")
        for when, entry in zip(open_dates, chosen):
            print(
                f"  {when}  {entry.candidate.youtube_id}  "
                f"score {entry.score:.3f}  cov "
                f"{entry.candidate.coverage:.1%}"
            )
            if args.apply:
                svc.assign_video(
                    conn,
                    user_id=args.user,
                    video_id=entry.candidate.video_id,
                    assigned_for=when,
                    score_breakdown=entry.breakdown,
                )
        if args.apply:
            conn.commit()
            print(
                "\nWritten. Confirm the rows independently, in psql -- a count "
                "this command prints about its own work is not verification "
                "of it."
            )
        else:
            print("\nDRY RUN -- nothing was written. Re-run with --apply.")

    return 0


def _targets(conn, user_id: int, svc, unit_target_lexemes) -> frozenset[str]:
    """This learner's current unit's target lexemes. Lexis only, never grammar.

    Returns empty rather than raising when the learner has no unit in progress:
    `target_hit` is then 0 for every candidate and drops out of the ranking,
    which is the honest behaviour when there is no target to hit.
    """
    unit = svc.current_unit(conn, user_id)
    if unit is None:
        return frozenset()
    return frozenset(unit_target_lexemes(conn, user_id, unit))


def _lemmas(text: str, tokenize, lemmatize) -> frozenset[str]:
    """The transcript's distinct lemmas, through the ONE tokeniser.

    Not a second word-splitting regex: `core/lexicon/normalize.py` is the only
    place in the codebase that tokenises, and an AST test enforces it.
    """
    out = set()
    for token in tokenize(text):
        lemma = lemmatize(token.surface)
        if lemma:
            out.add(lemma)
    return frozenset(out)


def _empty_pool_message() -> str:
    return (
        "\nTHE POOL IS EMPTY -- nothing has a usable transcript.\n\n"
        "  Run:  python -m core.video.refresh --live --apply\n\n"
        "  This is expected rather than surprising if the pool has not been\n"
        "  refreshed for 30 days: the retention purge nulls stored metadata and\n"
        "  transcripts on every refresh run, and there is no cron and no worker\n"
        "  to run one. A POOL THAT IS NOT REFRESHED EMPTIES ITSELF.\n\n"
        "  Refusing here is deliberate. Assigning nothing silently would show a\n"
        "  learner an empty block with no cause they could see."
    )


def _short_pool_message(available: int, needed: int) -> str:
    return (
        f"\nREFUSED: {available} selectable video(s) for {needed} open date(s).\n\n"
        "  Nothing was written. A short week is not assigned silently -- the\n"
        "  learner would see a day with no video and no reason for it.\n\n"
        "  Run:  python -m core.video.refresh --live --apply\n\n"
        "  If the shortfall is because most candidates were excluded for\n"
        "  degraded casing, that is a finding for the operator to rule on and\n"
        "  not a reason to pass --allow-degraded."
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
