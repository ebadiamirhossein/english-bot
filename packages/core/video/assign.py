"""Score the pool and assign videos -- **a video every day** (W24d).

    python -m core.video.assign --user 1 --date 2026-09-29             # dry: one day
    python -m core.video.assign --user 1 --date 2026-09-29 --apply     # writes
    python -m core.video.assign --user 1 --week-of 2026-09-28          # dry: the week
    python -m core.video.assign --user 1 --week-of 2026-09-28 --apply

Makes no external call and spends no money: coverage is recomputed locally over
transcripts already stored. There is no `--live`, because there is nothing live
to do. **The worker runs the same selection every hour** (`apps/worker/jobs.py`,
`assign_video` -> `assign_today_for_all`), for each learner's LOCAL today, so
the command is for a look or a catch-up, not the daily path.

**W24d (operator decision 2 of 2026-09-27, R3): every day of the week, Sunday
included.** The old text is quoted rather than deleted (#82's shape): *"PRD §7.1
puts curated video on **Monday, Wednesday and Friday**; the two series episodes
on Tuesday and Thursday are the Language Reactor / Trancy import path and are not
this command's."* Sunday's video is reachable only through keep going and
*practise anyway* (R3) -- Sunday's home still asks nothing of anyone.

**DAILY WHEN AVAILABLE: NEVER A REPEAT, NEVER BELOW BAND.** This read *"**IT
REFUSES RATHER THAN ASSIGNING FEWER THAN THREE.** … a silent short week is
exactly the shape of a backlog that CLAUDE.md §4 forbids presenting."* A week is
no longer a unit that can be short: each day either has an in-band, unseen video
or it does not, and a day without one shows block 2 `empty` -- **one day's fact,
never a count of missing days**, which is what the old refusal existed to
prevent. What the refusal protected -- no repeat, nothing below band -- is kept by
`choose`, which takes fewer than asked rather than widening either rule. **The
shortfall is still said out loud**: here as a SHORT line, and in the worker's log
line as `none_in_band=N`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

#: W24d: every day of the week (operator decision 2, R3). *(Read `(0, 2, 4)` --
#: "PRD §7.1: three curated videos a week, Mon/Wed/Fri" -- until 2026-09-27.)*
WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)


def week_dates(week_of: date) -> list[date]:
    """Every video day of the week containing ``week_of``, Monday first."""
    monday = week_of - timedelta(days=week_of.weekday())
    return [monday + timedelta(days=offset) for offset in WEEKDAYS]


def choose(scored, n: int) -> list:
    """The best ``n`` that may be assigned -- **or fewer, never a substitute.**

    Selectable means in band, not degraded, and scoring above zero; `seen_penalty`
    (1.0, more than every weight together) is what keeps a video the learner has
    already been given below zero. So a short pool yields a short list here, and
    nothing widens the band or re-offers a video to make up the number.
    """
    return [s for s in scored if s.is_selectable and s.score > 0][:n]


def rank_for(conn, user_id: int, *, allow_degraded: bool = False,
             record: bool = False):
    """``(scored, candidates_count)`` for one learner, or None if unknown.

    Coverage is recomputed over every stored transcript (about 10 ms each on
    the Mac, measured 2026-09-27) and written to `video_coverage` only when
    ``record`` -- the dry path must not persist (the pool commits on clean exit).
    """
    from core.lexicon.normalize import lemmatize, lexicon_digest, tokenize
    from core.services import video as svc
    from core.services.lexicon import coverage_for
    from core.services.syllabus import unit_target_lexemes
    from core.video.score import Candidate, rank

    weights = svc.track_weights(conn, user_id)
    if weights is None:
        return None
    digest = lexicon_digest()
    exposure = svc.accent_exposure(conn, user_id)
    seen = svc.seen_video_ids(conn, user_id)
    targets = _targets(conn, user_id, svc, unit_target_lexemes)
    candidates = []
    for row in svc.selectable(conn):
        if not row.transcript:
            continue
        report = coverage_for(conn, user_id, row.transcript)
        if record:
            svc.record_coverage(conn, user_id=user_id, video_id=row.video_id,
                                report=report, lexicon_digest=digest)
        candidates.append(Candidate(
            video_id=row.video_id, youtube_id=row.youtube_id, track=row.track,
            accent=row.accent, duration_s=row.duration_s, coverage=report.coverage,
            proper_nouns_detected=report.proper_nouns_detected,
            lemmas=_lemmas(row.transcript, tokenize, lemmatize),
            seen=row.video_id in seen,
        ))
    scored = rank(candidates, track_weights=weights, accent_exposure=exposure,
                  targets=targets, require_proper_nouns=not allow_degraded)
    return scored, len(candidates)


def assign_day(conn, user_id: int, on: date, *, kind: str = "daily",
               ranked=None, record: bool = False):
    """Assign ``on``'s video of ``kind`` if the date has none and one is in band.

    Returns the chosen `Scored`, or None -- the date already had its video, or
    nothing in the pool is in band and unseen. **Writes; the caller commits.**
    ``ranked`` lets a caller that has already ranked (or a test) skip the pass.
    """
    from core.services import video as svc

    if on in svc.assigned_dates(conn, user_id, [on], kind=kind):
        return None
    if ranked is None:
        got = rank_for(conn, user_id, record=record)
        if got is None:
            return None
        ranked = got[0]
    picked = choose(ranked, 1)
    if not picked:
        return None
    svc.assign_video(conn, user_id=user_id, video_id=picked[0].candidate.video_id,
                     assigned_for=on, score_breakdown=picked[0].breakdown, kind=kind)
    return picked[0]


def _learners() -> list[tuple[int, str]]:
    from core.db import connection
    from core.services import video as svc

    with connection() as conn:
        return svc.learner_timezones(conn)


def _assign_one(user_id: int, on: date) -> str:
    """One learner's day, in its own transaction: `assigned`, `already` or
    `none_in_band`."""
    from core.db import connection
    from core.services import video as svc

    with connection() as conn:
        if on in svc.assigned_dates(conn, user_id, [on]):
            return "already"
        chosen = assign_day(conn, user_id, on, record=True)
        conn.commit()
    return "assigned" if chosen is not None else "none_in_band"


def assign_today_for_all(now: datetime) -> dict[str, int]:
    """**The worker's pass (W24d).** Each learner's LOCAL today, idempotently.

    Hourly, so a learner in any timezone has their day's video within the hour
    their day starts, and a day the pool could not serve at 01:00 is tried again
    after an operator refresh. One learner failing never stops the others.
    Returns the counts the worker logs -- ids and outcomes only, never a title.
    """
    from core.services.sessions import local_today

    report = {"assigned": 0, "none_in_band": 0, "already": 0, "failed": 0}
    for user_id, tz in _learners():
        try:
            report[_assign_one(user_id, local_today(tz, now))] += 1
        except Exception:
            logger.exception("assign_video failed user_id=%s", user_id)
            report["failed"] += 1
    return report


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
            "Assign a day's video, or a week's. Dry by default; --apply writes. "
            "Makes no external call and spends nothing."
        )
    )
    parser.add_argument("--user", required=True, type=int, help="users.id")
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--date", help="one day, YYYY-MM-DD (W24d: the worker's unit)")
    when.add_argument(
        "--week-of",
        help="any date in the target week, YYYY-MM-DD: every day of it",
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

    raw = args.date or args.week_of
    try:
        anchor = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"the date must be YYYY-MM-DD (got {raw!r})")
        return 2

    from core.db import connection
    from core.services import video as svc
    from core.video.score import BAND_HIGH, BAND_LOW

    dates = [anchor] if args.date else week_dates(anchor)
    print(
        f"Assigning a video on {len(dates)} day(s): "
        f"{', '.join(d.isoformat() for d in dates)}\n"
    )

    with connection() as conn:
        if svc.track_weights(conn, args.user) is None:
            print(f"no user with id {args.user}")
            return 1

        taken = svc.assigned_dates(conn, args.user, dates)
        open_dates = [d for d in dates if d not in taken]
        if not open_dates:
            print("Every date already has its video. Nothing to do.")
            return 0
        if taken:
            print(f"  ({len(taken)} date(s) already assigned, leaving them alone)")

        if not svc.selectable(conn):
            print(_empty_pool_message())
            return 1

        # Recomputed, never read back from video_coverage: the stored row is an
        # audit record, written ONLY under --apply -- `core.db.connection()`
        # COMMITS ON CLEAN EXIT, so an unguarded write would persist on a dry
        # run while it printed "nothing was written".
        scored, n_candidates = rank_for(
            conn, args.user, allow_degraded=args.allow_degraded, record=args.apply
        )
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        selectable = choose(scored, len(scored))
        excluded = [s for s in scored if not s.is_selectable]
        out_of_band = [s for s in excluded if "outside the ruled" in (s.excluded or "")]
        degraded = [s for s in excluded if "proper-noun rule" in (s.excluded or "")]

        print(f"Candidates: {n_candidates}  selectable: {len(selectable)}")
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

        chosen = choose(scored, len(open_dates))
        if len(chosen) < len(open_dates):
            print(_short_pool_message(len(chosen), len(open_dates)))
        if not chosen:
            return 1
        print("\nAssigning:")
        for when, entry in zip(open_dates, chosen):
            print(
                f"  {when}  {entry.candidate.youtube_id}  "
                f"score {entry.score:.3f}  cov "
                f"{entry.candidate.coverage:.1%}"
            )
            if args.apply:
                assign_day(conn, args.user, when, ranked=[entry])
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
        f"\nSHORT: {available} selectable video(s) for {needed} open date(s).\n\n"
        "  Daily when available (W24d): the earliest dates get a video and the\n"
        "  rest show block 2 empty. Nothing repeats and nothing below band is\n"
        "  used to fill them.\n\n"
        "  Run:  python -m core.video.refresh --live --apply\n\n"
        "  If the shortfall is because most candidates were excluded for\n"
        "  degraded casing, that is a finding for the operator to rule on and\n"
        "  not a reason to pass --allow-degraded."
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
