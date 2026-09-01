"""The watch signal, as pure arithmetic. No SQL, no HTTP, no model, no I/O.

**#291: this is where "answered" means something for block 2**, and it is here
rather than in the service so the rule is testable without Postgres -- the same
split `score.py` has from `core/services/video.py`.

**THE SIGNAL IS AUTOMATIC AND THERE IS NO CONTROL FOR IT (#258).** The operator
ruled on 2026-08-29 that block completion is automatic and deleted the manual
button, its route and its service function, on the ground that *a signal that
requires five taps below the fold is not a signal -- it is a form nobody fills
in.* That ruling's per-kind rule turns on whether a block has a per-attempt log
keyed on the session: `review` has `card_reviews`, `focus` has `item_attempts`,
and **`input` was `empty`, never `done`, because it SERVED NOTHING and therefore
had no log.**

**W13 builds the missing log. The progress ping is block 2's `card_reviews`.**
So the ruling is honoured by supplying the evidence it asks for, not by adding a
tap -- and the old clause is quoted rather than deleted (#82's shape):
*"``input`` -- serves nothing until W12/W13. **`empty`, never `done`.**"* That
was true of a block that served nothing. It stops being true here.
"""

from __future__ import annotations

#: How much of a video counts as watched.
#:
#: **Not 1.0, and the reason is the end of a video rather than a tuning taste:**
#: the last seconds are titles, an outro and a subscribe card, and a learner who
#: stops there has watched it. Not lower, because the band between "most of it"
#: and "watched it" is where a signal stops describing anything -- and this
#: number is the ONLY writer of a column the record treats as the product.
WATCH_COMPLETE_FRACTION = 0.90


def clamp_position(position_s: int | None, duration_s: int | None) -> int:
    """A reported position, bounded by what is known about the video.

    The browser is the source and the browser is not trusted: a negative
    position, a NaN that arrived as None, or a position past the end are all
    reachable from a player that was seeking when the ping fired. **The clamp is
    here and not in the SQL** so that a second writer cannot be added without
    meeting it.

    An unknown duration bounds nothing, so the value is floored and passed --
    `resume_position_s` is where the learner stopped, and a video whose length
    was never fetched still has a place a learner stopped.
    """
    if position_s is None:
        return 0
    position = int(position_s)
    if position < 0:
        return 0
    if duration_s is not None and duration_s > 0:
        return min(position, int(duration_s))
    return position


def is_complete(position_s: int | None, duration_s: int | None) -> bool:
    """Has this position finished the video?

    **`duration_s IS NULL` RETURNS FALSE, AND THAT IS A DOCUMENTED GAP RATHER
    THAN A DEFAULT (#330).** `length_fit` already collapses "half an hour or
    more" with "we never fetched a duration" and the score breakdown cannot tell
    them apart; here the two are not collapsed, because one of them has a
    denominator and the other has none.

    **What that costs, stated because a learner sees it:** a video with no stored
    duration can never reach `done`, so block 2 stays `ready` for it and
    `first_open_block` returns that learner to the same video the next day and
    the next, for as long as it is assigned. `resume_position_s` means it
    RESUMES rather than restarts, so it is not the app re-offering something
    already watched -- but it is a block that presents as unfinished forever,
    which is #188's *the app is not paying attention* on a new surface.

    **The fix is a free metadata re-read on the refresh path, not a control on
    the player**, and it is named here so it is not rediscovered as a UI problem.
    Two things refused in its place: writing `done` on the ping's mere existence
    -- position is not comprehension, and a block that served nothing being
    marked done is exactly what #258 forbids -- and back-filling `duration_s`
    from the browser, which is an unaudited write to a column the purge owns.
    """
    if duration_s is None or duration_s <= 0:
        return False
    return clamp_position(position_s, duration_s) >= duration_s * WATCH_COMPLETE_FRACTION
