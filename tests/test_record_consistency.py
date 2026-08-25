"""The record must not contradict itself about which migrations are on production.

**Known issues #132 and #130.** #132 specified this check in its own text — *"parse
the slice table and the inventory, assert no row claims 'not applied to production'
for a migration another row records as deployed"* — after the same drift had been
corrected by hand twice. It was corrected by hand a third time on 2026-08-25, at
which point three occurrences in one day outranked its `low` rating and the check
was built. #130 is the same defect in a second document: `docs/TASKS-v3-web.md`
carries the migration numbering twice, once in an authoritative table and once
spread across per-slice **Build** columns, and nothing asserted the two agreed.

What this catches, concretely, is the shape of occurrences one and two: **one half
of the record moves and the other does not.** At W2 the `009` inventory row was
left saying "Mac dev DB only" after the deploy; at W7's record correction `010`,
`011` and `012` were all still saying it while their own slice rows recorded
production deploys with backup sizes and `Applied:` output.

**What it structurally cannot catch is #141**, and that is the shape of the third
occurrence: at W8 the inventory row said *not applied to production*, the slice row
said *nothing is on production*, the two agreed perfectly, and both were false.
This file compares the record against itself. Only the world can settle whether a
deploy happened, and the only closer for that is the human pasting `core.db status`
output into the update block.

Where the parsing is narrow, it says so rather than being widened until it passes:

* **Quoted spans are stripped before matching.** Four rows legitimately quote the
  stale wording while recording its correction — `010`'s and `011`'s inventory
  rows carry *The "Mac dev database only" wording was stale from before that
  deploy*, and W6's slice row carries *This row read "Not deployed" until
  2026-08-25*. Without the strip these read as live claims. **The cost of the
  strip is that a genuine claim written inside quotation marks is invisible to
  this check**; nothing in the file does that today.
* **Negative phrases are matched and blanked before the positives.** Every
  negative contains a positive as a substring — "not applied to production"
  contains "applied to production" — so the naive order passes every stale row
  in the file. `test_an_unquoted_stale_claim_is_still_read` pins it.
* **A slice row is matched to a migration by the literal phrase `migration NNN`**,
  bold markers allowed. A row that referred to its migration only as "the new
  tables" would not be matched at all and would pass silently.
* **`## Superseded` sections are excluded entirely.** They are dated snapshots and
  contain deliberately-false-today sentences such as "production is still at 12".
  Anything moved into a superseded block leaves this check's reach.
* **The Build-column half asserts numbering, not tables.** `014`'s authoritative
  row names two tables where the migration creates three — a departure recorded in
  the decisions log, not a drift, and out of this check's scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Resolved independently of anything under test, and independently of
# core.services.paths.repo_root — CLAUDE.md §3 rule 5: an expected value derived
# from the code under test proves nothing. tests/ → repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRESS = REPO_ROOT / "BUILD_PROGRESS.md"
TASKS = REPO_ROOT / "docs" / "TASKS-v3-web.md"

# A migration is on production, or it is not. Both directions are claims.
ON_PRODUCTION = (
    "applied to production",
    "deployed to production",
    "is live on production",
    "live on production",
)
OFF_PRODUCTION = (
    "not applied to production",
    "mac dev database only",
    "mac dev db only",
    "not on production",
    "nothing is on production",
    "not deployed",
)

_QUOTED = re.compile(r"[\"“”][^\"“”]*[\"“”]")
_MIGRATION_REF = re.compile(r"migration\s*\**\s*(\d{3})", re.IGNORECASE)
_MIGRATION_FILE = re.compile(r"migrations/(\d{3})_[a-z_]+\.sql")


def _strip_quotes(text: str) -> str:
    """Remove double-quoted spans so a *quoted* stale claim is not read as live."""
    return _QUOTED.sub(" ", text)


def _claims(cell: str) -> tuple[bool, bool]:
    """Return (claims_on_production, claims_off_production) for one table cell.

    The negatives are matched first and then blanked, because every one of them
    contains a positive as a substring: "not applied to production" would
    otherwise read as "applied to production" and every stale row would pass.
    """
    low = _strip_quotes(cell).lower()
    off = any(phrase in low for phrase in OFF_PRODUCTION)
    residue = low
    for phrase in OFF_PRODUCTION:
        residue = residue.replace(phrase, " ")
    on = any(phrase in residue for phrase in ON_PRODUCTION)
    return on, off


def _live_lines(text: str) -> list[str]:
    """Every line before the first `## Superseded` heading.

    Superseded blocks are dated snapshots kept deliberately verbatim; they hold
    sentences that were true when written and are false now.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## Superseded"):
            break
        out.append(line)
    return out


def _rows(lines: list[str], start: str, end: str) -> list[list[str]]:
    """Pipe-table rows between two headings, as split cells. Separators dropped."""
    rows: list[list[str]] = []
    inside = False
    for line in lines:
        if line.startswith(start):
            inside = True
            continue
        if inside and end and line.startswith(end):
            break
        if inside and line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


@pytest.fixture(scope="module")
def progress_lines() -> list[str]:
    return _live_lines(PROGRESS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def slice_claims(progress_lines: list[str]) -> dict[str, tuple[bool, bool]]:
    """migration number → (some slice row says on production, some says off)."""
    claims: dict[str, tuple[bool, bool]] = {}
    for row in _rows(progress_lines, "## Slice status", "Status key:"):
        if len(row) < 5:
            continue
        notes = row[4]
        on, off = _claims(notes)
        for number in set(_MIGRATION_REF.findall(notes)):
            was_on, was_off = claims.get(number, (False, False))
            claims[number] = (was_on or on, was_off or off)
    return claims


@pytest.fixture(scope="module")
def inventory_claims(progress_lines: list[str]) -> dict[str, tuple[bool, bool]]:
    """migration number → (inventory says on production, inventory says off)."""
    claims: dict[str, tuple[bool, bool]] = {}
    for row in _rows(progress_lines, "## File inventory", "## Verification checklist"):
        if len(row) < 3:
            continue
        match = _MIGRATION_FILE.search(row[0])
        if not match:
            continue
        on, off = _claims(row[2])
        was_on, was_off = claims.get(match.group(1), (False, False))
        claims[match.group(1)] = (was_on or on, was_off or off)
    return claims


# --------------------------------------------------------------------------
# The record against itself
# --------------------------------------------------------------------------


def test_the_two_tables_are_both_parseable(slice_claims, inventory_claims):
    """A silent parse failure would make every assertion below vacuously true."""
    assert len(inventory_claims) >= 5, f"inventory migrations: {inventory_claims}"
    assert len(slice_claims) >= 5, f"slice-row migrations: {slice_claims}"
    for number in ("010", "011", "012", "013", "014"):
        assert number in inventory_claims, f"{number} missing from the file inventory"
        assert number in slice_claims, f"{number} missing from the slice table"


def test_no_inventory_row_denies_a_deploy_its_slice_row_records(
    slice_claims, inventory_claims
):
    """#132's own wording. This is the W2 and W7 shape, in that direction."""
    bad = [
        number
        for number, (_, inv_off) in inventory_claims.items()
        if inv_off and slice_claims.get(number, (False, False))[0]
    ]
    assert not bad, (
        "file inventory says these migrations are not on production while their "
        f"slice row records the deploy: {sorted(bad)}"
    )


def test_no_slice_row_denies_a_deploy_its_inventory_row_records(
    slice_claims, inventory_claims
):
    """The reverse direction. #132 names it; neither hand correction hit it."""
    bad = [
        number
        for number, (_, slice_off) in slice_claims.items()
        if slice_off and inventory_claims.get(number, (False, False))[0]
    ]
    assert not bad, (
        "slice rows say these migrations are not on production while the file "
        f"inventory records the deploy: {sorted(bad)}"
    )


def test_no_row_claims_both_at_once(slice_claims, inventory_claims):
    """A cell asserting a deploy and denying it is the W4-row shape.

    W4's slice row read "Local only — not deployed" forty words before recording
    its own production deploy of 2026-08-24. Corrected 2026-08-25.
    """
    bad = {
        f"slice:{n}" for n, (on, off) in slice_claims.items() if on and off
    } | {
        f"inventory:{n}" for n, (on, off) in inventory_claims.items() if on and off
    }
    assert not bad, f"rows asserting and denying the same deploy: {sorted(bad)}"


def test_every_migration_file_on_disk_has_an_inventory_row(inventory_claims):
    """A migration with no inventory row cannot drift, because nobody records it."""
    on_disk = {
        p.name[:3] for p in (REPO_ROOT / "migrations").glob("*.sql")
    }
    missing = sorted(on_disk - set(inventory_claims))
    assert not missing, f"migrations on disk with no file-inventory row: {missing}"


def test_the_superseded_sections_are_excluded_from_the_live_region(progress_lines):
    """The exclusion is load-bearing, so it is asserted rather than assumed.

    Superseded blocks hold "production is still at 12" and similar, verbatim and
    deliberately. If the split ever stopped working, every test above would start
    failing on history rather than on drift.
    """
    full = PROGRESS.read_text(encoding="utf-8").split("\n")
    assert any(l.startswith("## Superseded") for l in full), "no superseded section"
    assert len(progress_lines) < len(full)
    assert not any(l.startswith("## Superseded") for l in progress_lines)


# --------------------------------------------------------------------------
# docs/TASKS-v3-web.md: the Build columns against the authoritative table
# --------------------------------------------------------------------------

_SLICE_ID = re.compile(r"^\*{0,2}(W\d+[a-z]?)\*{0,2}$")


@pytest.fixture(scope="module")
def tasks_lines() -> list[str]:
    return TASKS.read_text(encoding="utf-8").split("\n")


@pytest.fixture(scope="module")
def authoritative(tasks_lines: list[str]) -> dict[str, str]:
    """slice → migration number, from the table `:135` declares authoritative."""
    table: dict[str, str] = {}
    for row in _rows(tasks_lines, "## Migration numbering", "**Rule:"):
        if len(row) < 2 or not re.fullmatch(r"\d{3}", row[0]):
            continue
        match = _SLICE_ID.match(row[1].strip())
        assert match, f"unparsed slice id in the authoritative table: {row[1]!r}"
        table[match.group(1)] = row[0]
    return table


@pytest.fixture(scope="module")
def build_columns(tasks_lines: list[str]) -> dict[str, set[str]]:
    """slice → migration numbers named in its per-slice **Build** cell."""
    columns: dict[str, set[str]] = {}
    for line in tasks_lines:
        if line.startswith("## Migration numbering"):
            break  # the authoritative table and the prose below it are not slices
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        match = _SLICE_ID.match(cells[0])
        if not match:
            continue
        found = set(_MIGRATION_REF.findall(cells[3]))
        if found:
            columns[match.group(1)] = found
    return columns


def test_both_halves_of_tasks_are_parseable(authoritative, build_columns):
    assert len(authoritative) >= 10, authoritative
    assert len(build_columns) >= 10, build_columns
    assert authoritative.get("W8") == "014"


def test_no_build_column_names_a_migration_the_table_does_not(
    authoritative, build_columns
):
    """#130. The table wins — `docs/TASKS-v3-web.md:135` rules it, W7 applied it."""
    wrong = {
        slice_id: (sorted(numbers), authoritative.get(slice_id))
        for slice_id, numbers in build_columns.items()
        if numbers != {authoritative.get(slice_id)}
    }
    assert not wrong, (
        "per-slice Build columns disagreeing with the authoritative migration "
        f"table (slice: [build] vs table): {wrong}"
    )


def test_every_authoritative_row_has_a_build_column_naming_it(
    authoritative, build_columns
):
    """The other direction: a slice that stopped naming its migration at all."""
    missing = sorted(set(authoritative) - set(build_columns))
    assert not missing, (
        "slices the authoritative table gives a migration but whose Build column "
        f"names none: {missing}"
    )


def test_the_numbering_sets_agree(authoritative, build_columns):
    """Set equality, which catches a duplicate or a skipped number either side."""
    from_table = sorted(authoritative.values())
    from_columns = sorted(n for numbers in build_columns.values() for n in numbers)
    assert from_table == from_columns
    assert len(from_table) == len(set(from_table)), f"duplicate number: {from_table}"


def test_tasks_still_declares_which_half_wins(tasks_lines):
    """The assertions above encode a ruling. If the ruling moves, they are wrong."""
    text = "\n".join(tasks_lines)
    assert "**This table is authoritative.**" in text


# --------------------------------------------------------------------------
# The quote-stripping the parser depends on
# --------------------------------------------------------------------------


def test_quoted_stale_wording_is_not_read_as_a_live_claim():
    cell = (
        '✅ **applied to production 2026-08-24** (backup 68,586 bytes). '
        'The "Mac dev database only" wording was stale from before that deploy.'
    )
    assert _claims(cell) == (True, False)


def test_an_unquoted_stale_claim_is_still_read():
    cell = "\U0001f7e1 applied to the **Mac dev database only**; **not applied to production**"
    assert _claims(cell) == (False, True)


def test_a_row_that_says_both_is_reported_as_both():
    cell = "**Local only — not deployed.** … **Deployed to production 2026-08-24** — backup"
    assert _claims(cell) == (True, True)
