"""The eleven committed fixtures, through the real validator, into `items`.

**Human-run. Never an acceptance check.** CLAUDE.md §5b bars a slice from making
a billed call, and `tests/conftest.py` makes that structural — `netguard` is
autouse and session-scoped. This module is the deliberate exception, the same
category as `verify.py`:

    python -m core.items.seed_fixtures --user 7          # dry run, sends nothing
    python -m core.items.seed_fixtures --user 7 --live   # validates and inserts
    python -m core.items.seed_fixtures --user 7 --purge  # removes exactly those rows

**Why this exists at all.** `items` is empty by design until W10's
`assign_daily`, so W6 — the first slice whose output a human can look at — has no
data to look at. The alternative considered and rejected was rendering the
fixtures in the browser with no database: that verifies the eleven renderers and
*nothing else* — not the projection path, not the route, not the leak
assertions, not the grader — and would report "W6 works" having measured only the
half that was never in doubt. That is precisely the trap W5a cost a slice to
learn.

**Nothing is weakened to make this work.** `insert_item` still refuses a report
that is not `ok`; there is no `status` column; no migration. The command goes
through the real `gates.validate` and the real `insert_item`, which is the point:
the rows it writes carry genuine validation records.

**What a `--live` run licenses.** Eleven items, one sample each, of a stochastic
system. It is the first real **accept rate** anyone has for the W5a probe, which
the W10 row says is missing — and it licenses **no claim about the gate's rate**,
in either direction. A fail is decisive; a pass is not proof.

**These rows are permanent and they belong to a learner.** `items` is
per-learner fan-out and W10's `assign_daily` reads that table, so a fixture left
in place can end up inside a real session — including an `l1_to_l2_production`
whose canonical is *trusted, not verified* (#102). Hence `--purge`, which ships
in the same slice rather than being promised, the typed confirmation below, and
known issue #109 tracking that the purge was actually run.

No SQL lives here: every write goes through `core.services.items`, so
`tests/test_core_boundary.py::test_items_package_is_pure` stays unexempted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.config import load_settings
from core.items import gates
from core.items.grading import normalise_variants
from core.items.schema import content_hash, parse
from core.services import items as service
from core.services.paths import repo_root

#: The committed fixtures — the same file `tests/test_items_projection.py` and
#: the TypeScript renderer tests read. One source, three consumers; a private
#: copy here would be a twelfth item type nobody rendered.
FIXTURES = Path("tests") / "fixtures" / "items" / "valid.json"


def _fixture_path() -> Path:
    return repo_root() / FIXTURES


def load_fixtures() -> list[dict]:
    """The eleven drafts, parsed and variant-normalised, in file order."""
    rows = json.loads(_fixture_path().read_text(encoding="utf-8"))
    out = []
    for row in rows:
        draft = dict(row["item"])
        if draft.get("answer") is not None and "accepted_variants" not in draft:
            draft["accepted_variants"] = normalise_variants(draft["answer"])
        out.append({"name": row["name"], "item": parse(draft)})
    return out


def _confirm(user_id: int, action: str) -> bool:
    """Name the account out loud and make someone type the id back.

    There is no default `--user` and there is no `--yes`. The failure this
    guards against is seeding a *learner's* bank, which is silent, permanent,
    and only discovered at W10 when a real session is built from test fixtures.
    """
    print(f"\nAbout to {action} for users.id = {user_id}.")
    print(
        "This must NOT be one of the two learners. Confirm the id against the\n"
        "users table before continuing — the exact command is the deployment\n"
        "step in BUILD_PROGRESS.md, and it is not printed here because this\n"
        "package carries no SQL of any kind (CLAUDE.md §2)."
    )
    typed = input(f"Type the id ({user_id}) to continue, anything else to stop: ")
    return typed.strip() == str(user_id)


def dry_run(user_id: int) -> int:
    """Print what would happen. Send nothing, write nothing."""
    settings = load_settings()
    fixtures = load_fixtures()
    print(f"model:  {settings.llm_model}")
    print(f"target: users.id = {user_id}")
    print(f"source: {_fixture_path()}\n")
    for row in fixtures:
        item = row["item"]
        print(
            f"  {row['name']:22} would validate "
            f"(hash {content_hash(item)[:12]})"
        )
    print(
        f"\n{len(fixtures)} items. Nothing was sent and nothing was written.\n"
        "Re-run with --live to validate and insert, and see #109: these rows "
        "must be purged before W10's first assign_daily run."
    )
    return 0


def live(user_id: int) -> int:
    """Validate each fixture for real and insert the ones that pass."""
    if not _confirm(user_id, "validate and insert 11 items"):
        print("Stopped. Nothing was sent and nothing was written.")
        return 1

    settings = load_settings()
    fixtures = load_fixtures()
    accepted = duplicates = rejected = 0

    print(f"\n{'item':22} {'verdict':11} {'repairs':>7}  {'cue':18} written")
    print("-" * 72)
    for row in fixtures:
        item = row["item"]
        result = gates.validate(item, settings=settings)
        report = result.report
        written = "-"
        if report.ok and result.item is not None:
            item_id = service.insert_item(
                user_id, result.item, report, model=settings.llm_model
            )
            if item_id is None:
                duplicates += 1
                written = "duplicate"
            else:
                accepted += 1
                written = str(item_id)
        else:
            rejected += 1
            written = ", ".join(
                report.deterministic + report.naturalness + report.blind_solver
            ) or "discarded"
        print(
            f"{row['name']:22} {report.verdict:11} {report.repair_count:>7}  "
            f"{str(report.cue_applied or '-'):18} {written}"
        )

    total = len(fixtures)
    print("-" * 72)
    print(
        f"accept rate: {accepted}/{total} written, {duplicates} already present, "
        f"{rejected} rejected."
    )
    print(
        "\nELEVEN ITEMS, ONE SAMPLE EACH, of a stochastic system. This is the "
        "first real\naccept-rate datum for the W5a probe and it licenses NO "
        "claim about the gate's\nrate in either direction. A fail is decisive; "
        "a pass is not proof.\n"
        "\n#109: purge these rows before W10's first assign_daily run —\n"
        f"  python -m core.items.seed_fixtures --user {user_id} --purge"
    )
    return 0


def purge(user_id: int) -> int:
    """Delete exactly the rows a seeding run inserted, by content hash."""
    hashes = [content_hash(row["item"]) for row in load_fixtures()]
    if not _confirm(user_id, f"delete up to {len(hashes)} fixture items"):
        print("Stopped. Nothing was deleted.")
        return 1
    deleted = service.delete_items_by_hash(user_id, hashes)
    print(f"\npurged {deleted} rows (attempts against them cascaded).")
    print(
        "Confirm the remaining row count against the items table — the command\n"
        "is the last deployment step in BUILD_PROGRESS.md."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user",
        type=int,
        required=True,
        help="users.id to seed. No default, deliberately — see #109.",
    )
    parser.add_argument(
        "--live", action="store_true", help="validate for real and insert"
    )
    parser.add_argument(
        "--purge", action="store_true", help="delete the rows a --live run wrote"
    )
    args = parser.parse_args(argv)
    if args.live and args.purge:
        parser.error("--live and --purge are opposites; run one at a time")
    if args.purge:
        return purge(args.user)
    if args.live:
        return live(args.user)
    return dry_run(args.user)


if __name__ == "__main__":
    sys.exit(main())
