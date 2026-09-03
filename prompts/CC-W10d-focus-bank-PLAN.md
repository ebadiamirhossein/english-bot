# W10d — the bank the generator is never told about. **PLAN. NO CODE.**

**REVISION 2, 2026-09-02.** Two send-backs answered — **S1** (the planner
returning five is not a run yielding five) in **§6a**, and **S2** (the row's
status between the two commits) in **§2a**. Two further statements the operator
asked for, not send-backs: **§3.1** records the combination as a RULING rather
than a repair, and **§5.4** states #169's fate commit by commit.

**Revision 1's accepted content is unchanged and is not re-argued:** the
four-way `unit_plan` measurement (§1), two banks / one row / two commits (§2),
the refusal of *make `--fill` imply the retake map* (§3), the refusal to touch
`checkpoint_items`'s early return (§5.1/3), and Q3 answered *fixed, not designed
out* (§4).

**Mode `PLAN`, from `docs/TASKS-v3-web.md`'s Mode column and `BUILD_PROGRESS.md`'s
slice row, which agree.** This document is the whole deliverable. Nothing is
implemented, nothing is generated, no billed call is made, and `--apply` is not
run.

**This is the first W10d plan. `prompts/` held none** — the series runs W10,
W10b, W10c and stops — which is itself the reason the Mode is `PLAN`.

---

# §0 — RECONCILE. WHERE THE TREE DISAGREES WITH THE ROW AND WITH THE PROMPT

**Numbered, because an empty reconcile is a claim.**

**1. The row is titled *The focus bank*; the prompt calls the slice *the
checkpoint generator*. These are different banks.** W10d's Build cell is about
block 3's `focus` cohort — 56 items per unit per learner, `focus_held`, a focus
`--fill`, `ITEMS_PER_UNIT` versus `FOCUS_ITEM_COUNT`. **#352 is the `checkpoint`
cohort**, a different selector (`checkpoint_items`), a different demand map
(`quota_map`), and a different reserve rule. The prompt's framing is not the
row's. **§2 settles which of them W10d is.**

**2. Seven open issues resolve to W10d, not the three the prompt names.**
By W12r/4's method — parse the Slice cell, take the final target after the last
arrow: **#267, #276 (🟡), #299, #304, #305, #306, #309, #352.** That is eight
rows of which #276 is partial. The prompt named #299, #276 and #267; **#304,
#305, #306, #309 and #352 are also W10d's and two of them bear directly on any
cost figure this slice prints.**

**3. THE FINDING THAT REFRAMES THE WHOLE SLICE, AND IT IS §1's SUBJECT: on the
CHECKPOINT path the demand-aware planner ALREADY EXISTS AND IS COMPLETE.** It is
unreachable from the command line. **Measured, not read** — see §1.

**4. `_expected_calls` and `_expected_checkpoint_calls` are in opposite states,
and #305 names only one of them.** `_expected_checkpoint_calls(plan)` derives
every term **from the actual slot plan**, so a five-slot run is costed correctly
today. `_expected_calls(numbers)` hardcodes `len(SLOT_TYPES)` and is the one
#305 is about. **The checkpoint path's cost line is already right; the focus
path's is not.**

**5. `focus_held` does not exist.** `checkpoint_held` does
(`services/items.py:563`). The row's F3 proposes the focus counterpart and it has
never been written. **So the two halves of the row are not equally ready and
never were.**

**6. `bank_for_session` is not cohort-blind in the way the row says.** Its
reserve reads the declared `cohort` tag and withholds unattempted checkpoint
rows, **suspending the withholding when that would leave block 3 empty**. The
row's *cohort-blind except for the unattempted-checkpoint reserve* is accurate;
the shorter phrase *cohort-blind*, used in later prose, is not. **The
consequence #276 describes — a SAT checkpoint's twelve becoming ordinary
practice stock — is real and is a property of the release rule, not of
blindness.**

**7. No migration is needed and no number is taken.** Everything §5 proposes
writes `items` rows through `insert_item` and reads existing columns. **`items`
has carried `payload`, `unit_number` and `validator_version` since 012, and
`cohort` arrived with no DDL because `payload_of` derives it.** If this changes
during implementation it is a stop point, not a number quietly claimed.

---

# §1 — THE MEASUREMENT THIS PLAN IS BUILT ON

**`unit_plan` already accepts both `missed` and `held` and already composes them
correctly.** `generate.py:1592-1602`:

```
demand = dict(unit.checkpoint["per_target"])
slots  = checkpoint_slot_plan(number, demand, permitted=…, missed=missed.get(number, ()))
if held is not None:
    slots = _shortfall_slots(slots, checkpoint_quotas(demand, missed.get(number, ())), held.get(number, {}))
```

`checkpoint_quotas` **is** `core.syllabus.checkpoint.quota_map` — the re-weighted
retake map when `missed` is non-empty, the blueprint when it is empty. So the
demand that applies and the subtraction of what is held are **already one
expression.**

**RUN AGAINST #352's REAL NUMBERS — pure, no database, no model, no charge:**

| invocation | slots | composition |
|---|---|---|
| `--checkpoint` (first sitting) | **12** | 5 past simple · 4 past continuous · 1 composite · 2 linkers |
| `--retake` only *(exists today)* | **12** | 1 · 5 · 5 · 1 — **buys twelve to get five** |
| `--fill` only *(exists today)* | **0** | blueprint demand 5/4/1/2 against held 5/4/1/2 |
| **both, which the parser refuses** | **5** | **1 past continuous · 4 composite** |

**That is #352's answer exactly: one past continuous, four composite, five
items, not twelve.** The capability is complete. **What blocks it is two lines
in `main()` — `held` computed only under `--fill`, `missed` only under
`--retake` — and one `parser.error` refusing the combination.**

**AND THE REFUSAL WAS DELIBERATE, NOT AN OVERSIGHT.** Its own message says
*"no combined meaning has been ruled"* and offers a workaround — *run the retake
plan, then `--fill` against what it leaves short* — **which does not reach this
case, because `--fill`'s demand is the blueprint's and not the retake's.** The
author left a decision open. **This plan's job on the checkpoint half is to make
that decision, not to build a planner.**

---

# §2 — QUESTION 1, SETTLED: **DOES W10d COVER ONE BANK OR TWO?**

## RULING: **TWO BANKS, ONE SLICE, AND THE CHECKPOINT HALF SHIPS FIRST AS ITS OWN COMMIT.**

**Authorship: recommended by the assistant; the operator's to accept or reject.
It is not settled until he does, and nothing is built before that.**

**The reasoning, and it turns on the readiness gap §0/3–5 measured rather than on
tidiness:**

- **The checkpoint half is a WIRING change.** The planner, the demand map, the
  subtraction and a plan-derived cost ceiling all exist and are correct. What is
  missing is a command line that can reach them.
- **The focus half is a BUILD.** `slot_plan` is fixed at eight, there is no
  `focus_held`, `--fill` is refused for focus, `_expected_calls` is hardcoded
  (#305), and the target is 56 items per unit per learner.
- **Putting them in one commit prices the cheap half at the expensive half's
  risk.** #352 blocks unit 1's retake **today**, and behind it sit #249 and unit
  2's entire content. A one-day wiring fix should not wait on a 52-item
  generation design.

**WHY NOT TWO SLICES — the declined alternative, named.** Splitting W10d the way
W11 became W11/W11b/W11c was considered and refused for one reason: **the two
banks share `unit_plan`, `_shortfall_slots`, `insert_item` and the run report,
and #169's *the generator is never told what the bank holds* is the same defect
in both.** Two rows would make one finding look like two, and the second row
would inherit a `--fill` semantics ruled without it in the room. **One row, two
commits, the second gated on the first — the shape W12b's Phase A / Phase B
already has in this record.**

**WHAT THIS MEANS FOR THE ROW'S TITLE.** *The focus bank* becomes wrong the
moment the checkpoint half ships under it. **The row is retitled *The bank the
generator is never told about*, with the old title struck and quoted (#82's
shape), in the same commit as the first implementation — the way W11 was
retitled when its scope split.** **Not retitled by this plan**, because a plan
that edits the authoritative document before approval has approved itself.

---

# §2a — S2: **WHAT W10d's ROW STATUS IS BETWEEN THE TWO COMMITS**

## The problem, stated before the answer

After commit 1 the checkpoint half is shipped and the focus half is not.
**`🟡` means code-complete and would be false.** **`⬜ not started` would make
shipped, deployed code invisible in the status table** — which is the condition
W12r spent a pass repairing on 019's inventory cell, and the shape
`test_record_consistency.py` exists to catch.

## RULING: **NEITHER FITS, AND SAYING SO IS THE ANSWER. THE ROW CARRIES `🟡 commit 1 of 2` AND THE STATUS COLUMN GAINS NOTHING NEW.**

**Authorship: recommended by the assistant; the operator's to accept.**

**The status stays inside the existing vocabulary — `🟡` — with the scope
qualified in the same cell**, exactly as the record already does for
`🟡 records only`, `🟡 code-complete`, `🟡 deployed 2026-08-27` and
`🟡 all acceptances met — awaiting the operator's ✅`. **The Status column has
never been a single token in this record and does not become one here.**

**Why `🟡` rather than `⬜`, in one line: `🟡` is the record's word for *code
exists and the operator has not signed it off*, and after commit 1 that is
exactly true — of half the row.** The qualifier carries the half.

**THREE ALTERNATIVES DECLINED:**

1. **A new status glyph for *partially shipped*.** Refused: a fourth symbol
   changes what every reader of the table must learn, for one row, for a few
   days. **`test_record_consistency.py` parses these cells; a new token is a
   parser change to carry a scheduling fact.**
2. **Split into two rows after all** — W10d and W10e — **so each can be `🟡`
   honestly.** Refused for §2's reason, unchanged: the two banks share
   `unit_plan`, `_shortfall_slots` and #169, and two rows make one finding look
   like two. **The status question is not a good enough reason to reverse a
   scope decision made on the readiness gap.**
3. **Leave `⬜` and rely on the decisions log.** Refused: **that is precisely the
   defect W12r repaired** — a deploy recorded in one artefact and denied in
   another. `test_no_inventory_row_denies_a_deploy_its_slice_row_records` would
   fire the moment commit 1's file-inventory cell records a deploy.

## The retitle: **COMMIT 1 MAKES IT**

*The focus bank* becomes wrong the moment commit 1 ships, so **commit 1 carries
the retitle to *The bank the generator is never told about*, with the old title
struck and quoted (#82's shape), in both halves of `docs/TASKS-v3-web.md`.**

**Named because a correction that waits for a later commit sits in the gap** —
the shape ARCHITECTURE §6's *segment* wording sat in for a week, and the shape
#350 was filed about. **The title and the code change in the same commit or the
document describes a slice that no longer exists.**

---

# §3 — QUESTION 2, SETTLED: **ONE NEW MODE, OR A CHANGE TO BOTH EXISTING ONES?**

## RULING: **NEITHER. NO NEW FLAG, AND NO CHANGE TO WHAT EITHER EXISTING FLAG MEANS. THE COMBINATION IS PERMITTED AND GIVEN THE MEANING IT ALREADY COMPUTES.**

**Authorship: recommended by the assistant; the operator's to accept.**

`--fill` keeps its meaning: **subtract what is banked from the demand that
applies.** `--retake` keeps its meaning: **the demand that applies is the
re-weighted map rather than the blueprint.** **They were never in conflict — they
answer different questions**, and the parser's *"both adjust the same twelve from
opposite directions"* is the sentence to withdraw: `--retake` adjusts **which**
twelve, `--fill` adjusts **how many of them still need buying.**

**So the change is: delete the `parser.error`, pass `missed` whenever `--retake`
is given and `held` whenever `--fill` is given, and let `unit_plan` compose them
as it already does.** The refusal is replaced by the ruling, **quoted at the
site with its date and its reason (#82)** — a refusal that is deleted without its
argument being answered is how the next person re-adds it.

## 3.1 **THIS IS A RULING, NOT A FIX, AND THE RECORD MUST BE ABLE TO TELL THEM APART**

**Stated at the operator's instruction, so a reader in six months is not left
inferring it.** The parser does not contain a bug. **Its message says
*"no combined meaning has been ruled"*, and it was right: nobody had ruled one.**
The author refused a combination whose semantics were undecided, which is the
correct thing to do with an undecided semantics.

**So `--fill --retake` is not repaired into existence. It is RULED into
existence** — assistant-recommended, **operator-accepted 2026-09-02**, with the
three alternatives below declined on the record. **A repair needs a defect to
point at; this has none, and a later reader who took it for a repair would go
looking for the bug that was fixed and find nothing.**

**The implementation carries this distinction into the diff:** the deleted
`parser.error` is quoted at the site with its own argument intact and the ruling
written beneath it (#82's shape). **A refusal deleted without its argument
answered is how the next person re-adds it.**

**THREE ALTERNATIVES DECLINED, EACH WITH ITS REASON:**

1. **A third flag — `--top-up`.** Refused: it is `--fill --retake` under a name,
   and a third flag whose behaviour is the composition of two others is a
   fourth thing to keep consistent. **The record already has `--live`/`--apply`
   as a pair that must not drift; a third is a third chance.**
2. **Make `--fill` imply the retake map when a retake is due.** Refused, and
   this is the dangerous one: **it makes a database read (is a retake due?)
   change what a flag means.** The same command would plan twelve on Monday and
   five on Tuesday with nothing in the invocation to say why, and the run report
   would be the only place the difference appeared. **A flag's meaning must not
   depend on state the operator cannot see at the moment they type it.**
3. **Change `--retake` to subtract held automatically.** Refused: it removes the
   operator's ability to buy a fresh twelve deliberately — which is what you
   want after a bank is purged, or when the held rows are suspect.

**AND THE PARSER GAINS ONE REFUSAL RATHER THAN LOSING ONE: `--fill` without
`--checkpoint` stays refused, and `--fill --retake` on a unit with NO failed
sitting must be refused too** — `--retake` already errors there (*"a retake
without a failure is a first sitting; drop --retake"*), and that error must keep
firing when `--fill` is present. **Named because deleting one `parser.error`
next to another is exactly how the second one gets deleted with it.**

---

# §4 — QUESTION 3, SETTLED: **IS #352's GENERALISATION DESIGNED OUT, OR FIXED FOR UNIT 1?**

## RULING: **FIXED, NOT DESIGNED OUT — AND SAID PLAINLY BECAUSE THE PROMPT ASKED FOR IT EITHER WAY.**

**Authorship: assistant's finding; no operator ruling is needed to state it,
and one IS needed for what §4.2 proposes about it.**

## 4.1 What is fixed and what is not

**#352's generalisation:** *a retake that misses a low-allocation target is
structurally unfillable from a bank built to the blueprint.* Unit 1's composite
target has a blueprint allocation of **1**; `quota_map` re-weights a missed
target to **5**; a bank built to the blueprint therefore holds at most 1 where
the retake needs 5.

**§3's change does not make that impossible. It makes it VISIBLE AND BUYABLE.**
After it, the run says *five short, here they are* and a billed run fills them.
**Before it, the same unit is simply stuck.** That is a real improvement and it
is not the class being eliminated: **the next failed retake on a low-allocation
target will be short again, and will need another billed run.**

**THE CLASS WOULD BE DESIGNED OUT BY BUILDING THE BANK TO THE WORST-CASE RETAKE
MAP RATHER THAN TO THE BLUEPRINT** — for unit 1 that is `max` per target across
every reachable missed-set, which is **5/5/5/5 = 20 items** against the
blueprint's 12. **THAT IS NOT PROPOSED HERE**, for two reasons:

- **It is a 67% larger bank per unit, bought before anyone has failed anything**
  — pre-buying for a failure that may not happen, on the money path, which is
  the opposite of every ruling this record has made about spend.
- **It changes what a checkpoint bank IS**, from *the twelve a sitting draws*
  to *the superset any retake could draw*, and that is a product decision about
  the checkpoint's cost model, not a generator change.

## 4.2 What is proposed instead, and it is a warning rather than a purchase

**A dry-run line that names the exposure before it is met, per unit:** for each
target, the blueprint allocation, the worst-case retake demand, and the gap.
**Free, printed, never enforced** — #197's shape, *measured and reported, never
gated*. It turns *this unit will be unfillable if that target is missed* from a
thing discovered on the Saturday into a thing on the screen the day the unit is
generated.

**Whether the bank is later built to the worst case is the operator's and is
explicitly NOT decided here. It is filed rather than answered.**

---

# §5 — WHAT THE FIRST COMMIT BUILDS, AND WHAT IT REPORTS UNMET

## 5.1 Built — the checkpoint half

1. **The parser permits `--fill --retake`**, with the old refusal and its
   argument quoted at the site.
2. **`main()` computes `held` whenever `--fill` is given and `missed` whenever
   `--retake` is given**, independently, and passes both to `unit_plan`.
   No planner change.
3. **The run report names the WHOLE shortfall, per target, never the first.**
   This is the prompt's own requirement and it is the one place a new function
   is genuinely owed: a shortfall table `{target: (demand, servable, short)}`
   for every target, printed dry. **`checkpoint_items`'s early return is NOT
   changed** — refusing the cohort whole on the first unfillable target is
   correct and is what stops a short checkpoint reaching a learner. **The
   defect was never the early return; it was that the only reader was an `INFO`
   line.** Changing the selector would fix a log message by weakening a guard.
4. **The count is of SERVABLE rows.** `checkpoint_held` already composes from
   `_CHECKPOINT_STOCK`, which carries `validator_version = VALIDATOR_VERSION` —
   so it is already servable-scoped. **The dry report prints both `servable` and
   `any_version` per target**, because #352's own host read needed both columns
   to establish that nothing was hidden, and a generator that counts rows the
   code cannot serve buys the wrong number.
5. **§4.2's exposure line.**

## 5.2 Reported unmet — the focus half, this commit

**`focus_held`, the focus `--fill`, F1's separation of `ITEMS_PER_UNIT` from
`FOCUS_ITEM_COUNT`, F2's avoid-list and the 56-item target are NOT in the first
commit.** They are the second, gated on the first. **#299 stays `high` and open,
and unit 1's block 3 still serves four items a day until then.** Reported, not
approximated, not flagged off.

## 5.4 **#169's FATE, COMMIT BY COMMIT — ASKED FOR EXPLICITLY**

**#169 is *a checkpoint generates 12 items across 3–4 targets and nothing can
see two of them asking the same question in different words*.** §2 argues both
banks share it, and that is the reason for one row — **so the row's fate under a
two-commit slice is stated rather than left to follow.**

## RULING: **OPEN THROUGHOUT. NEITHER COMMIT CLOSES IT, AND COMMIT 1 MAKES IT
SLIGHTLY WORSE BEFORE ANYTHING MAKES IT BETTER.**

- **Commit 1 does NOT close it and does not partially satisfy it.** Wiring
  `held` into the retake demand changes **how many** items are bought, not
  **whether the generator can see the ones already there.** #169 is about
  semantic duplication and `content_hash` is blind to it — **#169's own row
  proves that with ids 21 and 29, the same sentence in different clothes.**
- **AND COMMIT 1 RAISES THE EXPOSURE, WHICH IS THE HONEST HALF.** It buys items
  **into a target that already holds some** — four composite items alongside the
  one already banked — which is exactly the shape #169 describes, on the
  narrowest target in the unit. **Before commit 1 nothing could be bought at
  all, so the risk did not exist; after it, it does.** That is not an argument
  against commit 1; it is the argument for **P2** (§6), which is a person
  reading the five beside the twelve.
- **Commit 2 does not close it either.** F2's avoid-list — the unit's existing
  `prompt_text` and `answer` in the request — **reduces** duplication by telling
  the generator what the bank holds. **It cannot detect it.** #271's rule
  applies unchanged: a guard can refuse a bad draft and can never show the model
  understood the rule.
- **What would close it is a checkpoint-level uniqueness pass over the cohort as
  a SET**, which `_expected_checkpoint_calls` already budgets a call for
  (*"#169's checkpoint-level uniqueness pass … one batched call per cohort"*) —
  **so the ceiling is costed for a gate that is not written.** That is a finding
  in itself and it is filed at §8.

**#169 STAYS `⬜ open` ACROSS BOTH COMMITS, AND ITS SEVERITY IS NOT LOWERED.**

## 5.3 What no commit of W10d does

**It does not lower or widen the blueprint.** The shortfall is items, not a
threshold (CLAUDE.md §3 rule 7). **It writes nothing to `errors`** — a generated
item is not a self-produced error, and #107's reasoning applies unchanged.

---

# §6 — COST, AND THE PREDICTIONS REGISTERED BEFORE THE FIRST BILLED RUN

**The first commit's own cost is ZERO. A dry run makes NO model call at all** —
W13-ii's `explain.py` set that bar and it is stronger than making no write.

**THE CEILING FOR #352's RUN IS ALREADY COMPUTED CORRECTLY.**
`_expected_checkpoint_calls(plan)` derives from the actual slot plan, so a
five-slot plan is costed as five slots. **#305 is about `_expected_calls`, the
FOCUS path, and does not touch this run** — which is why the checkpoint half can
ship with an honest cost line while #305 stays open.

**REGISTERED PREDICTIONS, WRITTEN NOW AND JUDGED AFTER THE FIRST BILLED RUN
(#57's precedent). The run is the operator's and is not made by this slice.**

- **P1 — yield.** The five-slot plan produces **≥4 accepted of 5** on the first
  invocation. *Branch: ≤2 → the shortfall path shares W10c's yield problem and
  the top-up loop must be re-costed before unit 2. 3 → borderline, re-run once
  before concluding.*
- **P2 — duplication, and this is #169's own test.** **0 of the accepted items
  is a rephrasing of an item already in the bank**, judged by a person reading
  the five beside the twelve. *Branch: ≥1 → the avoid-list (F2) is not optional
  for the checkpoint half either, and it moves into the first commit.*
- **P3 — the shortfall report matches the host.** The dry run's per-target table
  equals the two `psql` reads #352 recorded: demand 1/5/5/1, servable 5/4/1/2,
  short 0/1/4/0. *Branch: any disagreement → the generator and the selector
  disagree about servability and NOTHING is bought until they agree.*

**P3 is the one that matters most and it is free.** It can be judged on the dry
run, before any spend, and **it is the check that would have caught the
`subtitle_ladder_state` class of error (#355) had it existed for that read.**

---

# §6a — S1: **THE PLANNER RETURNS FIVE. A RUN YIELDING FIVE IS A DIFFERENT CLAIM, AND THIS IS WHERE THE MONEY GOES.**

**The send-back is correct and revision 1 conflated the two.** §1's measurement
is a pure computation: `unit_plan` returns five *slots*. **#352 needs five
*items in the bank, past the gates*.** Revision 1 treated the first as settling
the second, and P1–P3 did not predict the difference.

**And the exposure is concentrated exactly where the evidence was thinnest:**
four of the five slots are the composite target, whose blueprint allocation is
**1**, so the generator's entire production history for it is one item per unit.

## 6a.1 **FREE EVIDENCE EXISTS, IT IS IN THE REPOSITORY, AND IT WAS READ**

The send-back asked whether a prior already exists. **It does, and it did not
need the host: `w10c-journal.jsonl` and `w10c-journal-attempt6.jsonl` are
committed in the repository root**, and they carry `target`, `state`, `stage`
and `codes` per `(unit, slot)`. **#342's ten untracked host journals were not
needed and were not reached.**

**Read the way W10d's row requires — last write per `(unit, slot)`, not raw
lines. THE METHOD WAS VALIDATED BEFORE THE NUMBERS WERE USED: it reproduces
#309's own published figure exactly — 4 / 5 / 5 of 8 on units 1, 2 and 3, total
14** — which is the independent check that the parse is the same one that row
was written from.

**PER-TARGET SURVIVAL, BOTH JOURNALS, UNIT 1's FOUR TARGETS:**

| target | `w10c-journal` | `attempt6` | pooled |
|---|---|---|---|
| past simple: regular and irregular | 2/2 | 1/2 | **3/4** |
| **past continuous** *(#352 needs 1)* | 0/2 | 0/2 | **0/4** |
| **composite — same sentence** *(#352 needs 4)* | **2/2** | **0/2** | **2/4** |
| time linkers | 0/2 | 0/2 | 0/4 |
| whole run | 14/24 | 6/24 | 20/48 |

**AND THE REJECTION CODES ARE MORE USEFUL THAN THE RATES.** Past continuous
failed the same two ways in **both** runs — `judge: unnatural, textbook` and
`deterministic: too_few_variants`. The composite's one rejection in `attempt6`
was **`target: ranked_2`** — the target-ranking gate placing a composite item
under one of its own component targets. **That is a MECHANICAL reason the
composite is at elevated risk and it is #241's family**: a sentence containing
both a past simple and a past continuous can legitimately rank into either
component, and the gate has no way to prefer the composite.

## 6a.2 **WHAT THIS PRIOR IS NOT, AND THE CAVEATS ARE LARGER THAN THE NUMBERS**

1. **#309: these journals describe runs whose items were DISCARDED.** They are
   not the history of the rows now in the bank. **The prior is about the
   generator, not about this unit's stock.**
2. **They are FOCUS runs, eight slots per unit — not checkpoint runs.** The gates
   are the same; the slot plan and the type mix are not. **Transferring the rate
   assumes survival is a property of the target against the gates rather than of
   the cohort, and that assumption is stated, not established.**
3. **`attempt6` is named an attempt in a series** — plausibly a prompt mid-tuning
   — which is one explanation for 6/24 against 14/24 and is **not** evidence that
   the generator is bimodal.
4. **n = 2 per target per run.** W10b's L8 entry refused to act on n = 2 and that
   refusal applies here. **This is a prior for a prediction, not a basis for a
   design.**

## 6a.3 **P4, REGISTERED — PER-TARGET SURVIVAL, COMPOSITE REPORTED SEPARATELY**

> **P4.** On the first billed five-slot run for user 3 / unit 1:
> **the composite target lands ≥ 2 of its 4**, and **past continuous lands its
> 1**. Counted from the run's own journal, per target, **with the composite
> reported on its own line and never folded into an aggregate**.
>
> **Predicted from the pooled prior: composite 2 of 4 (50%), past continuous 0 of
> 1 (0/4 historical).** **So the honest expectation for the run as a whole is
> ~2 of 5, not 5 of 5** — and that is stated before the spend rather than
> discovered after it.
>
> *Branch rules, written now:*
> **(a) composite ≥ 3 and past continuous 1** → the prior was pessimistic, the
> shortfall closes in one run, and the composite's `ranked_2` risk is not
> load-bearing.
> **(b) composite 2 and past continuous 0** → **the prediction held exactly**;
> the run lands 2 of 5 and §6a.4's rule fires.
> **(c) past continuous 0 across a second attempt as well** → **0 of 6
> historical**, and the target's two failure codes are stable across three runs.
> **That stops being a yield question and becomes a TARGET question** — #241's
> shape, and it is filed against the same reading rather than answered by
> another run.
> **(d) composite ≤ 1** → the `ranked_2` mechanism is dominant and **F2's
> avoid-list will not help**, because the failure is the target gate and not
> duplication.

## 6a.4 **THE BRANCH RULE FOR A SHORT LANDING, CHOSEN BEFORE THE MONEY**

**RULING: ONE top-up round, which is already inside the run's own ceiling. Then
STOP AND REPORT UNMET. NO SECOND DISCRETIONARY BILLED RUN.**

**Authorship: recommended by the assistant; the operator's to accept.**

- **The top-up is not a second decision.** `_expected_checkpoint_calls` already
  budgets `× 2` for one top-up round; it is inside the ceiling the operator
  authorises when they authorise the run.
- **A SECOND INVOCATION IS REFUSED, AND #299's THIRD CAUSE IS THE REASON.** The
  generator **is not told what the bank holds** — F2 is commit 2's — so a second
  run sends a near-identical request and buys either the same rejection or
  #169's duplicate. **Paying twice for one draft distribution is not a retry; it
  is the same run again.**
- **SO A SHORT LANDING PROMOTES F2 RATHER THAN TRIGGERING A RE-RUN.** If the run
  lands fewer than five, **the blocker for #352 becomes commit 2's avoid-list**,
  and that is the next thing built — not another purchase.
- **AND #352 DOES NOT CLOSE ON A SHORT LANDING.** It closes when five items
  exist. **Reported unmet, with the per-target counts, never adjusted** (§3
  rule 7).

**WHY THIS IS DECIDED HERE: the moment to choose is before the spend, because
after it the choice is made by whoever is looking at a half-filled bank and a
blocked retake.**

---

# §7 — TESTS, AND WHAT THEY CANNOT SHOW

**RED first, every one (CLAUDE.md §3 rule 4).**

1. **`unit_plan` with both arguments yields exactly #352's five slots** — the
   §1 table as an assertion, with the composition pinned per target, not the
   count alone. **A count of 5 would pass for the wrong five.**
2. **The three existing invocations are unchanged** — 12 / 12 / 0 for
   first-sitting, retake-only and fill-only. **The regression guard for §3's
   ruling: permitting a combination must not alter what either flag alone
   means.**
3. **The parser accepts `--fill --retake` and still refuses `--retake` with no
   failed sitting** — §3's named risk, asserted so deleting one refusal cannot
   take the other with it.
4. **The shortfall report names every short target, not the first.** Constructed
   from a unit short on two targets; **asserts both appear.** The failure this
   is written against is measured: this morning's log understated a shortfall of
   five as one, deterministically.
5. **The dry run makes no model call**, through the netguard, not by reading the
   code.

**#340 APPLIES AND IS NAMED BEFORE IT FIRES A THIRD TIME.** Any test writing
`items` rows needs teardown keyed on that table's own key — `items` has
`user_id`, so the convention works, **but `syllabus_units` and any global row a
fixture touches do not.** It has already fired twice on people who had just read
the row.

**WHAT THE TESTS DO NOT ESTABLISH, STATED RATHER THAN IMPLIED (#271):** that the
five generated items are five different teaching moments rather than five
rephrasings. **A guard can refuse a bad draft and can never show the model
understood the rule**, and `content_hash` is blind to it — #169 proved that with
ids 21 and 29, the same sentence in different clothes. **Only P2's reading
settles it, and P2 is a person, not an assertion.**

---

# §8 — WHAT THIS PLAN DOES NOT DECIDE

- **Whether the checkpoint bank is later built to the worst-case retake map**
  (§4.2). Filed, not answered.
- **#304's single fixed ladder.** A flag under PRODUCT-PRINCIPLES §3, and its
  own row says nothing is to be built for imagined users.
- **#309's journal ambiguity.** The committed `w10c-journal.jsonl` describes a
  different run from the one that wrote the bank. **The first commit does not
  rely on it for any number**, and that is why it can ship with #309 open.
- **#306's `JUDGE_BATCH`.** Read by no code path; `low`; unchanged here.
- **#169's uncosted gate.** `_expected_checkpoint_calls` budgets a call for
  *"#169's checkpoint-level uniqueness pass over the twelve as a SET"* — **and
  that pass is not written.** So the ceiling has always included a call for a
  gate that does not exist. **Filed, not fixed here**; it makes the ceiling
  conservative rather than wrong, which is the safe direction, and correcting it
  is a change to a cost function nobody has yet had reason to trust.
- **Whether #352's five items are bought at all, and when.** **This slice makes
  them producible by one command. Paying for them is the operator's, and T1
  still gates the spend.**

---

# §9 — CLAUDE.md §3 RULE 2

**`llm.py`'s request construction is NOT changed by anything in §5.** The
generator calls `chat()` through existing paths with the same parameter shapes;
the change is which slots are planned, which is upstream of every request.
**So no real API call is owed.** If implementation finds otherwise, that is a
stop point back to the operator before shipping.

---

# §10 — THE `BUILD_PROGRESS.md` UPDATE BLOCK THE IMPLEMENTATION APPLIES

**Slice row 🟡** with: the two-commit shape and which one shipped; **no migration
and no number taken**; **no `apps/web` change and therefore no Vercel rebuild**;
what is reported unmet (§5.2); and the retitle with the old title quoted.

**Decisions log:** §2, §3 and §4's rulings with their declined alternatives and
their authorship; §1's measurement; the suite figures, serial.

**Slice row after commit 1: `🟡 commit 1 of 2` with the retitle applied in the
same commit** (§2a).

**Known issues:** §4.2's exposure question and §8's uncosted #169 gate, each
filed with a target. **#169 stays open across both commits and its severity is
not lowered** (§5.4). **#352 does not
close on the first commit** — it closes when the five items exist, which is a
billed run and the operator's.

**Next action, none dropped:** W11b's check and #348's independent proof, both
2026-09-06; W13-i's four phone checks from 2026-09-07; T1; **#352's five-item
run, now producible by one command and still the operator's to pay for**;
#351's one-line edit to `docs/DEPLOYMENT.md:279-292`, applied by hand four times
and still unwritten; T2; T4; the carried set #335–#359; unit 2 held on
#299/#249; W11c awaiting the operator's ✅.

---

**NOTHING IS MARKED ✅. W10d STAYS `⬜ not started` UNTIL THE OPERATOR APPROVES
THIS PLAN — a plan is not an implementation, and this record has a row for the
difference.**
