# W8 — Syllabus data · PLAN MODE

Produce a plan. **Write no code, change nothing.** Stop and wait for approval.

---

## 0. Mode — the row says AGENT, and I am asking for PLAN

`docs/TASKS-v3-web.md` lists W8 as **AGENT**. Run it as **PLAN**, and record the
deviation with its reason: W8 carries a migration, authors roughly a thousand
rows of content two learners will live inside for six months, and has at least
one unresolved design question (§3) that AGENT mode would settle silently. The
Mode column is not the authoritative migration table, so this is not a #49-class
problem — but it is a departure from a written row and is recorded as one.

---

## 1. Read first

`BUILD_PROGRESS.md` — all of it, including the W7 entry and the issues table ·
`CLAUDE.md` · `docs/PRODUCT-PRINCIPLES.md` · `docs/TASKS-v3-web.md` (the **W8
row**, the **authoritative migration table**, the W9 and W10 rows) ·
`docs/PRD-v3-web.md` **§3** in full, and whatever else defines checkpoints.

Then the tree, which is the authority (#82): `migrations/` — especially 010
(`lexemes`, `user_lexemes`), 013 (`cards`) as the freshest shape precedent, and
whichever migration created `book_units` · `packages/core/lexicon/` ·
`packages/core/services/lexicon.py` · `data/lexemes.tsv`.

**Note:** W7 corrected seven stale Build columns, so W8's row should now read
**014**. Verify that in the repo rather than trusting this prompt or the table
from memory.

---

## 2. What PRD §3 actually gives, and what it does not

§3 gives **six stages** — can-do goal, grammar cluster with Murphy ranges,
lexical field — and then says *"Each stage = 4 weekly units."*

**The 24 units do not exist.** §3 names six clusters and leaves the units to be
authored. So W8 is not transcription; it is authoring. Per unit, §3 specifies:

- one can-do statement
- 3–5 grammar targets with Murphy references
- ~40 target lexemes
- 3 video/audio items at 95–98% coverage
- 1 output task, spoken and written
- 1 checkpoint, 12 items, 80% to pass

The row's acceptance asks for a **checkpoint blueprint**, not a checkpoint. State
what a blueprint is and what it is not — W8 authors no items, and W10 generates
them.

**Say explicitly which of those six the slice ships and which it defers**, with a
target for each deferral. The video items belong to W12 (`videos`, migration
016); if W8 stores nothing for them, say so rather than leaving a reader to infer
it from an absent column.

---

## 3. The question AGENT mode would have settled silently

§3: *"~40 target lexemes chosen by frequency band ∩ topic ∩ **not already in your
known-word ledger**."*

That last clause is **per learner**. The row's acceptance — *"unit lexemes are
diffable against the known-word ledger"* — reads the same way. But a
`syllabus_units` row is shared: two learners on Unit 7 have different ledgers and
must see different target words.

The plan must state the resolution and its consequence. The obvious reading is
that a unit carries a **candidate set** and the diff happens per learner at read
time, computed rather than materialised — which is also what
`PRODUCT-PRINCIPLES.md` §3 asks for. If the plan takes another reading, say why.

Then say how many candidates a unit needs so that a learner with a large ledger
still clears the ≥30 bar. The learner with the most v2 history has ~2,000 known
lemmas out of a 15,000-lemma table; a 40-candidate unit that diffs down to 12 for
that learner fails the criterion silently, and it fails for exactly the learner
who has used the app most. **That is #91's shape**, and it is worth checking
before the units are authored rather than after.

---

## 4. Where the content actually comes from — the sizing question

24 units × ~40 lexemes is roughly a thousand rows, plus 24 can-do statements and
72–120 grammar targets. The plan must say, concretely, how each is produced.

**Target lexemes.** `lexemes` holds 15,000 lemmas with frequency rank and 5,727
CEFR tags. Frequency band is a column; CEFR is a column. **Topic is not.** So the
crux: how does "daily life, work routine, home, food, transport" become a set of
lemma ids?

State the method and its cost. If it is a model call, say how many calls, how
much money, and — given the last three slices — how the output is checked, since
a topic assignment nobody verifies is a thousand rows of unverified content. If
it is deterministic, say from what.

**Every target lexeme must resolve to a real `lexemes` row.** A unit referencing
a lemma that is not in the table is a foreign key that cannot be written. Say
what happens to a word that belongs in a unit and is not in the 15,000: the
`ensure_lexeme` path with an `origin` column exists for exactly this, and a
permanently closed vocabulary breaks the product.

**Murphy references.** §3 cites ranges — 5–20, 25–28, 72–79, 92–100, 19–24,
29–38, 42–47, 48–52, 38–41, 137–145 — and asserts they are *"already in
`book_units` from v2's OCR"*. **Verify that against the table, unit by unit.**
Twice this week a claim in the record turned out not to hold — the judge reading
gapped stems, and rule 4 never executing — and both were found by checking what
was actually there. If `book_units` does not cover a cited range, that is a
finding, and it is filed rather than worked around.

---

## 5. Migration 014

`syllabus_units`, `user_unit_state`, per the authoritative table. `schema_version`
goes 13 → 14.

- Follow 013's shape: constants mirrored from a `core` module and compared by a
  test; FK targets read back from `pg_constraint`, since
  `tests/test_identity_boundary.py` does not scan `migrations/`.
- **`user_unit_state` is a new user-keyed table.** `PRODUCT-PRINCIPLES.md` §2 is
  satisfied by 011, so this does not enlarge an identity migration — confirm that
  rather than assuming it, and say it in the record either way.
- The unit states are `locked → available → in_progress → passed → mastered`
  (PRD §2). Mastery requires a checkpoint pass **plus** retained performance 3+
  weeks later, so the state machine has a time-dependent transition. Say what
  holds the ordering, and note that `core.lexicon.states` already solved a
  related problem with `MAY_LOWER` — W4's lesson was that a conflict rule too
  broad blocks legitimate transitions.
- **Is the syllabus content itself in the migration, or in a separate seed?** W4
  put 15,000 lexemes in `data/` behind an idempotent seed command rather than in
  DDL, and that is the precedent: a migration is not a content pipeline, and
  content that will be corrected wants a re-runnable path. Say which you take.

---

## 6. Constraints

- `packages/core` imports no web framework; SQL only in service functions.
- No test derives its expected value from the function under test; none depends
  on wall-clock date — and unit **mastery is time-dependent**, so this constraint
  is load-bearing here the way it was for FSRS in W7.
- The acceptance bar is never quietly lowered. Report the number and stop.
- Claude Code has **no SSH access** and is never to be given any. Every server
  step is an explicit command for the human.
- Deployment: backup → pull → `pip install -e packages/core` → migrate → restart.
- The host is shared with `fonderis-worker`. No broad upgrades, no reboots, no
  Caddy rewrite, no destructive Postgres command without naming the database.
- **W9 is not started.** No skill map screen, no frontend at all unless the plan
  argues for it and the human agrees.
- W10's `assign_daily` is not started.

---

## 7. Acceptance criteria

From the row, sharpened, never loosened:

> 24 units in the DB; each has ≥3 grammar targets and ≥30 target lexemes; unit
> lexemes are diffable against the known-word ledger.

Plus, at minimum:

- migration 014 applied, `schema_version` **14**, `Applied: 001–014, Pending:
  (none)`;
- the ≥30 bar is met **per learner after the ledger diff**, not before it — §3;
- every target lexeme resolves to a real `lexemes` row, asserted by a join
  returning zero orphans;
- every Murphy reference resolves to a real `book_units` row, or the gap is filed;
- the content seed is idempotent — a second run writes nothing;
- suite no fewer than the W7 baseline, 0 failing; Vitest unchanged if no frontend.

Write each so that what verifies it measures the thing it reports on.

---

## 8. Human checks

W8 authors content, so the checks are about the content being **good**, not about
rows existing. Propose them. At minimum: the human reads several units end to end
— can-do statement, grammar targets, a sample of target lexemes — and judges
whether a B1 learner would recognise this as a week's work. No test can do that,
and it is the only check that matters for a content slice.

Note in the record: a criterion of "≥30 lexemes" is satisfiable by thirty bad
words. The count is machine-checkable; the quality is not, and the plan should
say plainly which of the two the criteria actually verify.

---

## 9. `BUILD_PROGRESS.md` update block

Slice row **W8** at 🟡 — never ✅. Decisions log with reasons, including the
PLAN-mode deviation and the §3 resolution. Known issues: new ones with severity
and target; every open one carried — the authority is each row's Status column,
not the summary line (#111). File inventory.

**Next action** — this slice's checks plus every earlier check still unrun, named
individually, including **W7's five phone checks** (four grades, a due date that
moves, the cap, the Anki export, a slang card's face) if they are still unrun
when this slice closes, and the two W6 criteria still open: the typed answer with
correct words, wrong capitalisation and a trailing full stop on a live phone
keyboard; and `dictation` audio on a phone, on silent and on mobile data.

---

Return the plan. **Do not implement. Do not start W9.**
