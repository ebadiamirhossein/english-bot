# W8a — Rulings: Anki out, Telegram confirmed, cloze measured, record folded · PLAN MODE

Archived per CLAUDE.md §0: `prompts/` records the intent a slice was given, never
its state. `BUILD_PROGRESS.md` is the only record of what was built.

**Mode:** PLAN. This slice removes a public API route, edits three source
documents and adds a module that spends money — none of which is additive or
self-contained.

---

## What this slice was

Four rulings made on 2026-08-25, handed over in `docs/RULINGS-2026-08-25.md`,
plus the record work that closes them out. Not W9. The skill map was not touched.

**No migration.** `schema_version` stays at 14; production was taken there by
W8's deploy on 2026-08-25, and the record correction (W8r, `5d17ffd`) landed
first as its own commit.

### Part 1 — Anki is out of the web app

Remove `GET /cards/export.tsv`, the *Download your deck for Anki* link on
`/review`, and `core/cards/anki.py`. Correct PRD §5, ARCHITECTURE §6 and the
TASKS W7 row, each **naming** the correction rather than quietly reconciling it.

**The reasoning previously given for this was wrong, and the plan had to record
that rather than repeat it.** The handover note said the W7 row contradicted the
PRD and that the PRD wins. It does not contradict it — PRD §5's Rules line
specified the export, ARCHITECTURE §6 listed the route, and W7's row carried it
in both columns. All three agreed with each other and with the code, so this is a
**product change across three consistent documents**, not the correction of one
stale row.

`core/services/anki.py` — the v2 Telegram chunk exporter, a ✅-verified live path
two learners use weekly — is **not** touched, and the diff proves it.

Add a permanent test asserting `apps/api` and `apps/web` contain no Anki export
path. #129 closes.

### Part 2 — Confirm no Telegram surface is referenced by any web screen

Grep both trees, report the raw output, and make the confirmation permanent with
a test. Nothing designed or built for Telegram. If there are hits, report and
file them rather than removing them.

### Part 3 — Reviewer typography: build three, ship none

The current type is *"not good look and not soft."* Build three complete,
coherent candidates and an unlinked preview page to choose from on a phone. No
red, no ✗, no strike-through. Farsi coverage is a hard requirement with an
explicit fallback in every stack. Licence gate before any code, terms quoted.
The gap `___` must stay unmistakable at phone width. Ship no default change.

### Part 4 — Cloze cards have never passed a uniqueness gate: measure, then propose

Build a read-only, human-run module that runs W5a's existing probe over the
existing cloze cards and reports how many admit more than one answer. Dry by
default, `--live` for the billed run, writes nothing (AST-asserted), reuses the
existing probe, configures logging (#140), predictions pre-registered before the
run. Then **propose** A (gate at creation) and B (cue on the card face) with
their real blast radius. Implement neither.

### Part 5 — Fold the rulings into the record

Every ruling into the decisions log dated 2026-08-25, each with its reason —
including Part 1's corrected premise, the most valuable one to write down because
it is a ruling whose stated premise was false. Delete `RULINGS-2026-08-25.md`.

---

## Review, and what it changed

The first plan was approved subject to nine numbered changes, two of them
blocking and both answerable from the tree rather than by writing code:

1. **Prove `ClozeCuedItem` accepts a five-underscore gap before relying on it.**
   Answered: `schema.py` carries no validators at all, and both construction
   routes were run against the real card sentence with `prompt_text` byte-identical
   afterwards. `str.count` is non-overlapping, so the count concern was never
   live either.
2. **Confirm `core/cards/` may import the gates at all.** Answered:
   `test_cards_package_is_pure` bans a driver import and a SQL-looking string
   constant and nothing else; `ITEMS_MODEL_CALLERS` is scoped to `core/items/`.
   No test loosened — the package was **tightened** with a named
   `CARDS_MODEL_CALLERS` where it previously had no provider boundary at all.
3. Make the Anki scan strip comments, as the Telegram scan does; keep the PRD
   quote at `card-face.tsx:10`; record the symmetry as a rule.
4. `noindex` on `/type`, and file its removal now, stating the deliberate absence
   of Vitest coverage in the same row.
5. Name Step 1 as #141's fix and re-target #141 to the deploy runbook.
6. State why `english-bot` is not restarted.
7. Correct the `t.me` reading — `-F` means literal, so it is a substring
   coincidence, not a regex artefact.
8. Report #130's status.
9. Report the net test count split, and do not pad a drop.

---

## Standing rules this slice ran under

- Slice row to 🟡. Never ✅ — that column is the human's alone.
- Both ban tests demonstrated **red** before being accepted, and the output goes
  in the record.
- Suite reported **split**: baseline, deleted with names, added with names,
  final. A final below 1630 would have been the correct outcome.
- Nothing in Part 4 implemented beyond the measurement module.
- No default typography change.
- Every server step written for the human. Claude Code has no SSH access to the
  production host and is not to be given any.
- Stop when the `BUILD_PROGRESS.md` update block is written. Do not start W9.
