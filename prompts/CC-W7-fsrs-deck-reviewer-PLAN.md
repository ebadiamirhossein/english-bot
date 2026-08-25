# W7 — FSRS deck + reviewer · PLAN MODE

Produce a plan. **Write no code, change nothing.** Stop and wait for approval.

This is the first slice since W4b to touch **real learner data**. Both learners
have v2 chunks and two years of review history behind them. Nothing in this slice
may lose any of it.

---

## 0. Read first

`BUILD_PROGRESS.md` — all of it, including the W5b and W5c entries and the issues
table · `CLAUDE.md` · `docs/PRODUCT-PRINCIPLES.md` · `docs/TASKS-v3-web.md` (the
**W7 row**, the **authoritative migration table**, the W8 and W10 rows, the
standing rules) · `docs/PRD-v3-web.md` **§8.5** (register) and the FSRS sections ·
`docs/ARCHITECTURE-v3-web.md` §5 and §6.

Then the tree, which is the authority (#82): the v2 `chunks` schema and every
table holding review history · `migrations/012_items.sql` as the shape precedent ·
`packages/core/items/` · `packages/core/services/` · `apps/api/routers/` ·
`apps/web/components/items/` (W6's presentation/answer split, which the reviewer
either reuses or deliberately does not).

---

## 1. #100 — settle it before anything else

`docs/TASKS-v3-web.md:32` says W7 is **"Migration 012 (`cards`, `card_reviews`)"**.
It is not. 012 is W5's, applied to production on 2026-08-24. The authoritative
table at `:90` says W7 is **013**, and `:124` already rules the table wins.

**#100 is filed with the target "before W7". W7 is now.** The plan must:

1. Take **013**. `schema_version` goes 12 → 13.
2. **Correct the stale Build columns in `docs/TASKS-v3-web.md`** — W7's, and check
   every other row against the authoritative table, because W10's row says "014"
   where the table says 015. Report how many rows are wrong before deciding scope;
   if the drift is systematic, correct all of it in this commit and close #100.
3. Never edit the authoritative table to match the Build columns. The table wins.

---

## 2. What W7 builds

From the row, verbatim, so nothing is quietly dropped:

> Migration 013 (`cards`, `card_reviews`, `register` on `cards`,
> `cards.source_chunk_id` FK). `py-fsrs` wrapper. **Migrate every existing `chunk`
> into cloze + production cards, seeding stability from v2 review history.**
> Reviewer UI with 4 grades, caps, leech handling. Anki export retained.
> **Register tag on every card (PRD §8.5)**; `slang`/`informal` created as
> recognition-only; card face shows source line, neutral equivalent, and
> who-says-this.

Acceptance, verbatim:

> Deck is non-empty on day one from migrated chunks; grading changes due dates per
> FSRS; daily caps hold; export produces a valid Anki TSV; **no card exists
> without a register tag; no `slang` production card exists before its neutral
> equivalent is mastered; `/prep` output contains zero `slang`/`taboo` items.**

---

## 3. The chunk migration is the risky half — plan it like W4b

W4b is the precedent and it is a good one: rehearse against a **real restored
dump** before touching production, and verify with a query written **separately
from the migration's own assertions**.

The plan must answer:

1. **What is in `chunks` today, and how much?** Row counts per learner, from the
   record or from a query the human runs. A migration whose input size nobody has
   stated is a migration nobody has planned.
2. **What is the v2 review history, exactly?** Which table, which columns, what
   they mean. "Seed stability from review history" is not implementable until the
   plan says what maps to FSRS stability and difficulty, and what happens to a
   chunk with **no** history — a real case that must not silently produce a card
   with a fabricated stability.
3. **One chunk becomes how many cards?** The row says cloze **and** production.
   State the fan-out, and what happens when a chunk cannot produce one of the two.
4. **Is it idempotent?** Run it twice; the second run writes nothing. W4a and W4's
   seed both had to prove this and both did.
5. **Rehearsal plan**: restore a real dump to a scratch database, run 013 against
   it, time it, and state the ceiling above which the slice stops and re-plans.
   W4b's 011 took 0.330s against a ~30s ceiling; name yours.
6. **The independent verification query** — counts and spot checks written
   separately from the migration, run on both the scratch copy and production.

---

## 4. Register — the acceptance criterion with teeth

Three of the eight acceptance clauses are about register, and one of them is a
constraint on **ordering across time**: *no `slang` production card exists before
its neutral equivalent is mastered.*

The plan must say:

- where the register tag comes from for a **migrated** card, when v2 chunks may
  carry none — and what happens to a chunk whose register is unknown. "Default to
  neutral" is a decision with consequences; say it rather than letting it happen.
- how "mastered" is defined, in a column or a query, and what enforces the
  ordering — a CHECK, a service-level guard, or a test. A rule enforced only by
  the code that happens to create cards today will not survive W10 creating them
  too.
- how `/prep` is proved to contain zero `slang`/`taboo` items, given `/prep` is a
  v2 Telegram surface and Telegram is legacy. If that criterion is now checked
  somewhere else, say where.

---

## 5. `py-fsrs` — a new runtime dependency

The first new third-party runtime dependency since W4 chose a committed lookup
table specifically to avoid one.

- **Licence, verified before code** — the W4 gate caught the plan's own table
  wrong in both rows. `PRODUCT-PRINCIPLES.md` §3: any third-party dependency whose
  licence must hold for a commercial product gets flagged now, not at W25.
- Pinned version, and whether it pulls transitive dependencies.
- Whether it goes in `packages/core` — which imports no web framework and has kept
  its dependency list short deliberately.
- A wrapper, so FSRS is called from one place. The single-call-site rule exists
  because duplicated construction drifts and tests cannot see it.

---

## 6. Issues targeted at W7 — each gets a ruling, not silence

Five issues name W7 as their target. The plan states, for each: **fixed here,
re-targeted with a reason, or explicitly deferred.** "It belongs to a later slice"
is a reason to re-target with a target, never a reason to say nothing.

- **#118** — `match_pairs` cannot show its correct pairing; the fix is the answer
  route returning the mapping post-grading, an API change W6a was barred from
  making. W7 touches the API. Is this the slice?
- **#105** — no "show me a cue" affordance; `hint_used` is always FALSE. Adding one
  needs a route that reveals `definition`/`l1_gloss` — a second-serialiser hazard
  that must be designed, not improvised.
- **#116** — for the six types where the answer is on screen, the leak test checks
  JSON **keys** only; `word_bank_order`'s permutation and `match_pairs`' mapping
  are asserted by key name alone. Tiles arriving pre-sorted would pass.
- **#117** — the `API built origins=… routes=…` log line named as deployment
  evidence does not exist. Emit it or correct the step.
- **#102** — no gate is structurally shown both sides of the
  `l1_to_l2_production` relation; the judge sees only the English half.

And two that are not W7's but bear on it:

- **#108** — `latency_ms` is client-supplied and clamped, and **W7's FSRS reads
  it**. A learner who backgrounds the app mid-item produces a real-but-meaningless
  number. Say what the reviewer does with it.
- **#122** — `contract()` is a no-op on every gapped stem because `_EMPHASIS`
  matches a literal `_` and `GAP` is `___`, so PRD §4.6 rule 4 has **never
  executed** on three of the eleven types. Not failed — never ran.

**A question worth asking once, out loud, in the plan:** twice this week a gate
turned out not to be doing what the record said — the judge reading gapped stems,
and rule 4 never running. Both were found by looking at what a function is
actually handed. Is there a cheap offline check that would tell us which *other*
rules have never executed? If there is, say what it costs; if not, say so.

---

## 7. `item_attempts.grade` gets its writer here

W5 shipped six unread columns arguing the intervening history is unrecoverable.
W6 wrote four; `grade` and `audio_seconds` stayed NULL with reasons — `grade`
because FSRS's four-button UI is W7's.

**W7 is that slice.** Say what writes `grade`, and confirm `graded_by` stays
honest: a self-marked attempt (`'self'`, from W6's spoken types) must not enter an
FSRS calculation as though it were measured. W19 will have to decide whether
self-marked attempts enter the progress line at all, and that is easier decided
before there are months of rows.

---

## 8. Constraints

- `packages/core` imports no web framework; SQL only in service functions; a route
  parses, authorises, calls **one** service function, serialises.
- No browser storage beyond the one permitted `"theme"` key.
- Every route writing to the journal or the deck has an integration test through
  the ASGI transport.
- No test derives its expected value from the function under test; none depends on
  wall-clock date. **FSRS is a date calculation** — this constraint is load-bearing
  here in a way it has not been before. Say how due dates are tested without
  freezing time badly or asserting against the scheduler's own arithmetic.
- The acceptance bar is never quietly lowered. Report the number and stop.
- Claude Code has **no SSH access** and is never to be given any. Every server step
  is an explicit command for the human; no server action is a criterion this slice
  can satisfy on its own.
- Deployment sequence, settled: backup → pull → `pip install -e packages/core` →
  migrate → restart.
- The host is shared with `fonderis-worker`. No broad upgrades, no reboots, no
  Caddy rewrite, no destructive Postgres command without naming the database.
- `validator_version` is **3** as of W5c. Filtering the bank on it is **W10's**,
  not W7's — do not pull it forward.

---

## 9. Acceptance criteria

Propose them from the row, sharpened, never loosened. At minimum the eight clauses
in §2, plus:

- migration 013 applied, `schema_version` **13**, `Applied: 001–013, Pending:
  (none)`;
- the chunk migration idempotent, proven by a second run writing nothing;
- **no card without a register tag** — enforced by a CHECK, not by convention;
- suite no fewer than **1381 passing, 0 failing**; Vitest **52** or higher;
- every count verified by a query written separately from the migration.

Write each criterion so that what verifies it measures the thing it reports on.

---

## 10. Human checks and deployment

Explicit copy-paste commands, each with the evidence it should produce: the
rehearsal against a restored dump, the pre-migration backup with its byte count,
the migration, `core.db status`, the independent verification query, the service
restart, and the Vercel redeploy.

Human checks on a phone, proposed deliberately — W6 taught that the suite does not
find these. At minimum: a real review session with all four grades, a due date
that visibly moves, a daily cap that actually stops, and the Anki export opened.

---

## 11. `BUILD_PROGRESS.md` update block

Slice row **W7** at 🟡 — never ✅. Decisions log with reasons, including every
§6 ruling. Known issues: new ones with severity and target; **#100 closed** if the
document drift is corrected; every open issue carried — the authority is each
row's Status column, not the summary line (#111). File inventory.

**Next action** — this slice's human checks **plus every earlier check still
unrun**, named individually, including the two W6 criteria still open: the typed
answer with correct words, wrong capitalisation and a trailing full stop on a live
phone keyboard; and `dictation` audio on a phone, on silent and on mobile data.

---

Return the plan. **Do not implement. Do not start W8.**
