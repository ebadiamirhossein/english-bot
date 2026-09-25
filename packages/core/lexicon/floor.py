"""`python -m core.lexicon.floor` — the per-learner known-word floor (W13c).

    python -m core.lexicon.floor                          # before/after table, every onboarded learner
    python -m core.lexicon.floor --user 3                 # the same, one learner
    python -m core.lexicon.floor --user 3 --set 2500      # DRY: what a correction would move
    python -m core.lexicon.floor --user 3 --set 2500 --apply

**READ-ONLY UNLESS `--apply`.** A dry `--set` really does write the new floor,
reads every figure back through the code the app runs, and then ROLLS BACK — so
what it prints is what the app would see, not an estimate of it.

**The before/after table is the ruling's gate.** Reads switched from the
materialised `assumption` rows to the computed floor; the rows were kept, so the
old reading can still be computed beside the new one. For every learner it
prints the covered set, all 24 units' target counts and every stored video
coverage figure, BEFORE (the whole table, as every reader read it until W13c)
and AFTER (the effective ledger), and ends each learner on `PARITY: yes` or on
the lemmas that differ with the reason they differ. **Run it on the host after
`migrate` and before the restart** — the running process still reads the old
way until then.

**No count a learner sees can move.** *Words you know* is
`evidenced_known_count`, which excludes the floor by construction (W4), and
this command prints it before and after a correction to show that rather than
assert it.

No SQL here — `core.services.lexicon` and `core.services.syllabus` own every
query (CLAUDE.md §2).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from core.lexicon.coverage import compute_coverage
from core.lexicon.states import COVERED_STATES

#: How many differing lemmas a report names before it only counts them.
_EXAMPLES = 12


@dataclass(frozen=True, slots=True)
class VideoFigure:
    video_id: int
    stored: float
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class LearnerTable:
    user_id: int
    floor: int
    kept_assumption_rows: int
    words_you_know: int
    covered_before: frozenset[str]
    covered_after: frozenset[str]
    targets_before: dict[int, int]
    targets_after: dict[int, int]
    videos: tuple[VideoFigure, ...] = field(default_factory=tuple)

    @property
    def only_before(self) -> frozenset[str]:
        return self.covered_before - self.covered_after

    @property
    def only_after(self) -> frozenset[str]:
        return self.covered_after - self.covered_before

    @property
    def units_differing(self) -> list[int]:
        units = sorted(set(self.targets_before) | set(self.targets_after))
        return [
            u for u in units
            if self.targets_before.get(u, 0) != self.targets_after.get(u, 0)
        ]

    @property
    def videos_differing(self) -> list[VideoFigure]:
        return [v for v in self.videos if round(v.before, 4) != round(v.after, 4)]

    @property
    def parity(self) -> bool:
        return not (
            self.only_before or self.only_after
            or self.units_differing or self.videos_differing
        )


def measure(conn, user_id: int) -> LearnerTable:
    """Every figure, before and after, for one learner. Reads only."""
    from core.services import lexicon as lex
    from core.services import syllabus

    before_ledger = lex.materialised_ledger(conn, user_id)
    before = frozenset(l for l, s in before_ledger.items() if s in COVERED_STATES)
    after = lex.known_lemmas(conn, user_id)

    candidates = syllabus.unit_candidates(conn)
    targets_before = {u: len(c - before) for u, c in candidates.items()}
    # AFTER is the SQL the app runs, not the same subtraction done twice: the
    # table is only evidence if its after column comes from the real path.
    targets_after = {u: 0 for u in candidates}
    targets_after.update(dict(syllabus.target_counts(conn, user_id)))

    videos = []
    for video_id, stored, transcript in lex.stored_video_coverage(conn, user_id):
        old = compute_coverage(
            transcript, before, ledger=before_ledger, vocabulary=frozenset(before_ledger)
        )
        new = lex.coverage_for(conn, user_id, transcript)
        videos.append(VideoFigure(video_id, stored, old.coverage, new.coverage))

    return LearnerTable(
        user_id=user_id,
        floor=lex.known_word_floor(conn, user_id),
        kept_assumption_rows=lex.kept_assumption_rows(conn, user_id),
        words_you_know=lex.evidenced_known_count(conn, user_id),
        covered_before=before,
        covered_after=after,
        targets_before=targets_before,
        targets_after=targets_after,
        videos=tuple(videos),
    )


def _names(lemmas: frozenset[str]) -> str:
    shown = sorted(lemmas)[:_EXAMPLES]
    more = len(lemmas) - len(shown)
    return ", ".join(shown) + (f", … and {more} more" if more > 0 else "")


def render(t: LearnerTable) -> str:
    lines = [
        f"learner {t.user_id}: floor {t.floor} · kept `assumption` rows "
        f"{t.kept_assumption_rows} (not read) · words you know {t.words_you_know}",
        f"  covered set       before {len(t.covered_before)}   after "
        f"{len(t.covered_after)}   only-before {len(t.only_before)}   "
        f"only-after {len(t.only_after)}",
    ]
    if t.only_before:
        lines.append(
            "    only-before — a kept `assumption` row for a lemma OUTSIDE this "
            f"learner's floor (or with no seed rank), no longer read: {_names(t.only_before)}"
        )
    if t.only_after:
        lines.append(
            "    only-after — inside the floor with NO row at all (never "
            f"materialised, e.g. the seed file changed after W4 ran): {_names(t.only_after)}"
        )
    units = len(t.targets_after)
    differing = t.units_differing
    lines.append(
        f"  unit targets      {units - len(differing)} of {units} units equal   "
        f"(before Σ {sum(t.targets_before.values())}   after Σ "
        f"{sum(t.targets_after.values())})"
    )
    for u in differing:
        lines.append(
            f"    unit {u}: before {t.targets_before.get(u, 0)}   after "
            f"{t.targets_after.get(u, 0)}"
        )
    lines.append(
        f"  stored video coverage  {len(t.videos)} rows   "
        f"{len(t.videos) - len(t.videos_differing)} equal before → after"
    )
    for v in t.videos:
        flag = "" if v not in t.videos_differing else "   ← differs"
        lines.append(
            f"    video {v.video_id}: stored {v.stored * 100:.2f}%   before "
            f"{v.before * 100:.2f}%   after {v.after * 100:.2f}%{flag}"
        )
    lines.append(f"  PARITY: {'yes' if t.parity else 'NO — every difference is listed above'}")
    return "\n".join(lines)


def _report(conn, user_ids: list[int]) -> int:
    tables = [measure(conn, uid) for uid in user_ids]
    for t in tables:
        print(render(t))
        print()
    same = sum(1 for t in tables if t.parity)
    print(f"SUMMARY: parity for {same} of {len(tables)} learners.")
    return 0


def _correct(conn, user_id: int, new_floor: int, *, apply: bool) -> int:
    from core.services import lexicon as lex

    old = measure(conn, user_id)
    lex.set_known_word_floor(conn, user_id, new_floor)
    new = measure(conn, user_id)
    print(
        f"learner {user_id}: floor {old.floor} → {new_floor}\n"
        f"  covered set       {len(old.covered_after)} → {len(new.covered_after)}"
        f"   (+{len(new.covered_after - old.covered_after)}"
        f" / −{len(old.covered_after - new.covered_after)})\n"
        f"  unit targets Σ    {sum(old.targets_after.values())} → "
        f"{sum(new.targets_after.values())}\n"
        f"  words you know    {old.words_you_know} → {new.words_you_know}"
        "   (the learner-visible count; the floor never reaches it)"
    )
    for v_old, v_new in zip(old.videos, new.videos, strict=True):
        print(
            f"  video {v_old.video_id}: {v_old.after * 100:.2f}% → {v_new.after * 100:.2f}%"
        )
    if old.words_you_know != new.words_you_know:
        conn.rollback()
        print("REFUSED: the learner-visible count moved. Nothing written.")
        return 1
    if apply:
        conn.commit()
        print("APPLIED.")
    else:
        conn.rollback()
        print("DRY: rolled back, nothing written. Re-run with --apply to write.")
    return 0


def main(argv: list[str] | None = None) -> int:
    from core.db import connection
    from core.services.lexicon import FLOOR_RANGE, onboarded_user_ids

    parser = argparse.ArgumentParser(description="The per-learner known-word floor.")
    parser.add_argument("--user", type=int, action="append", default=[])
    parser.add_argument("--set", type=int, default=None, dest="new_floor")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and args.new_floor is None:
        parser.error("--apply only applies to --set")
    if args.new_floor is not None and len(args.user) != 1:
        parser.error("--set takes exactly one --user")
    if args.new_floor is not None and args.new_floor not in FLOOR_RANGE:
        parser.error(
            f"--set is {FLOOR_RANGE.start}–{FLOOR_RANGE.stop - 1} (migration 030's CHECK)"
        )

    with connection() as conn:
        try:
            if args.new_floor is not None:
                return _correct(conn, args.user[0], args.new_floor, apply=args.apply)
            code = _report(conn, args.user or onboarded_user_ids(conn))
        except LookupError as exc:
            conn.rollback()
            print(f"REFUSED: {exc}. Nothing written.", file=sys.stderr)
            return 2
        conn.rollback()
        return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
