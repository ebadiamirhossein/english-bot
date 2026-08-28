# W10b — Grammar lessons. Reconciled plan.

**Mode: PLAN. Nothing below is implemented.** On approval this file is committed as
`prompts/CC-W10b-grammar-lessons-RECONCILED-PLAN.md`, superseding
`prompts/CC-W10b-grammar-lessons-PLAN.md` as intent. The archive is **not edited** — it is
the approved record of 2026-08-26 and this file records where it disagrees with the tree.

---

## Context

The syllabus carries 24 can-dos and **82 grammar targets**, and nothing teaches any of them
(**#182**, `high`). W10 shipped block 3 and did not paper over it: the block renders a can-do,
four grammar labels, and the line *"The written explanation for these is on its way."* The
operator hit that screen as a learner on **2026-08-28**. This slice is the teaching behind
those labels.

The archived plan was approved on 2026-08-26 against a W10 that had not started, so its
assumptions about how a lesson reaches block 3 were predictions. W10, W10a, W10c and W10r
have shipped since. **§1 is the reconcile; the plan below is corrected against the tree, not
the other way round.**

**The constraint that shapes the slice, carried unchanged from the archive and from W10c:
the operator cannot verify the English.** A wrong explanation of the present perfect reaches
two B1 learners who cannot tell it is wrong. Verification is therefore not a step at the end;
it is the slice.

---

## 0. Send-backs answered — 2026-08-28

Seven. Each resolved against the tree or the data, never by argument. **No scope change, no
ruling reopened.**

| # | Resolution | Where |
|---|---|---|
| **1** | **Allow zero.** The floor of 1 was the contradiction; §5's *"fewer rather than false"* is the rule that survives. The signal moves to the reported count and a new axis **L8**. The twelve real targets are mapped as evidence that zero is not *expected* here. *(This entry read `BETWEEN 0 AND 3` until send-back 8, which found the cap carried the same defect. The constraint is now `BETWEEN 0 AND 5`; the old value is quoted here rather than overwritten.)* | §4, §5.1, §8 |
| **2** | **Byte-exact, and this is read from the code, not assumed.** `blueprint.validate_checkpoint:129-148` uses `known = {t.target for t in targets}`, plain `in` and plain set difference — **no normalisation anywhere**, and it already enforces the bijection in both directions for `per_target`. The lesson bijection uses the identical comparison. The 24-unit table is measured, and it makes the SQL CHECK **weaker than §6.1 admitted**. | §3.1, §6.1 |
| **3** | **Staged: unit 1 alone, then 9 and 20.** `3 + 57 = 60`, read on the phone, then `114` with `--skip-control`. Total unchanged at 174. | §7, §15 |
| **4** | **Refuse, matching `bank_for_session`'s shipped precedent.** A below-current row is not served; block 3 falls back to `lesson: None` and the `noLesson` line. The dry run prints how many stored rows are below current, so a bump is never silent. | §4.1, §12 |
| **5** | **Logged-in only, identical to `/session/today`**, with a `401` asserted through the ASGI transport. | §13.1 |
| **6** | **Confirmed — the old assertion goes in the decisions log**, not only the commit. | §12, §17 |
| **7** | **Render 9 and 20 through the real component.** One page, `apps/web/app/(app)/lessons/[unit]/page.tsx`, reusing `lesson.tsx` and `diagram.tsx`. The alternative — accepting two lessons as JSON — is declined with its reason. | §13, §16 |

### Second round — 2026-08-28

| # | Resolution | Where |
|---|---|---|
| **8** | **The ceiling was the floor's defect at the other end.** Four targets each admitting a kind produces four diagrams against a cap of 3, so the natural first pass would have died on an INSERT and L8's *4 of 4* branch was unreachable. **`BETWEEN 0 AND 5`**, mirroring `syllabus_units` exactly as §6.1 argues the sections CHECK should — capping at 4 would encode a measurement as a schema rule and make the two constraints reason differently about the same data. **One diagram per target is now a stated rule**, enforced in `checks.py` where the target list is in hand. **L8 is untouched; L5's `~6` denominator is re-based.** | §3, §4, §5.1, §8, §12 |
| **9** | **§9 states the rule, not the values.** `--live` types that invocation's own ceiling, `--apply` its own `--units` list, **both computed and printed, never transcribed.** The unstaged literals are gone. §15 illustrates; §9 governs. | §9 |

**Both rounds found the same failure twice: the ceiling repeated the floor, and §9's literals
repeated #223's.** Recorded as such rather than as two tidy-ups — §8's pre-checks exist because
reading a contract is not the same as running something through it, and this plan has now
demonstrated that about itself three times (R13, the floor, the ceiling).

### Approval — 2026-08-28

**APPROVED.** Two corrections applied while writing, neither requiring re-proposal:

- **A.** The `diagrams` **column comment** still read `-- 1..3 typed specs` — the floor and the
  ceiling this plan removed, in an inline comment sitting directly above the block comment
  explaining why both were wrong. Now `-- 0..5 typed specs, at most one per target`. **This gets
  its own decisions-log line, not a silent fix:** the constraint was corrected twice and its own
  column comment was not, which is the migration-file version of a slice row disagreeing with its
  own notes — and this record has counted that family seven times (#82).
- **B.** `tests/test_lessons_checks.py` was listed twice in §12; folded, the same duplication
  already folded for `test_migration_017.py`.

**Implementation order, as approved:**

1. **The licence gate first** (§11), verbatim quote in the decisions log. **If the terms do not
   hold, report and stop.**
2. **§8's two structural pre-checks green before anything billed** — the field-subset assertion
   and the perfect specimen.
3. Everything else in this plan's own order.

**Stop at the dry run.** `--live` is the operator's, staged (§7.1, §15): unit 1 alone at ceiling
60, read on a phone in block 3, and **stage 2 is authorised by that reading, not by the axes going
green.**

**Slice row ⬜ → 🟡 when code-complete. Never ✅.** **Do not start or plan W11** — it stays gated
on **W10 check 4** (#216) and on **0a** reading the deployed SHA.

---

## 1. Reconcile report — the archive against the tree

Nineteen findings. Five were named in the slice prompt; **two of those five describe the
W10c plan, not this one.** Fourteen are new.

### 1.1 The four named disagreements

**R1 · `gates.probe_target` EXISTS. CONFIRMED — and the reuse is not a plain call.**
`packages/core/items/gates.py:454-535`. Archive §5b puts C1 in `core/lessons/gates.py` as a
new implementation; the record is explicit that *"W10b's C1 becomes its second caller, not a
second implementation"* (`BUILD_PROGRESS.md:300`).

The shape matters. `probe_target(item: BaseItem, *, claimed, candidates, settings)` builds
`{"item": visible_projection(item), "answer": item.answer, "candidates": ordered}` and calls
`item_target.txt`. **A lesson section is not an item and has no `answer`**, and pushing one
through `visible_projection` would claim it is a learner-visible *item* — breaking
`projection.py`'s stated cross-slice contract, which is pinned by name-list in
`tests/test_core_boundary.py:654` (`test_exactly_one_module_projects_an_item`).

**Correction:** `probe_target` is split into a shared engine and a thin item wrapper, in
`core/items/gates.py`, with no behaviour change:

```python
def probe_ranked(subject: Mapping[str, Any], *, claimed: str,
                 candidates: Sequence[str], system: str,
                 settings: Settings | None = None) -> TargetVerdict:
    """Candidate normalisation, the call, invention-dropping, the ranking parse."""

def probe_target(item, *, claimed, candidates, settings=None) -> TargetVerdict:
    return probe_ranked(
        {"item": visible_projection(item), "answer": item.answer},
        claimed=claimed, candidates=candidates,
        system="item_target.txt", settings=settings,
    )
```

One implementation, two entry points. `TargetVerdict`, the sorted-not-shuffled rule, the
`claimed not in candidates` `ValueError`, the casefold match against the offered set and the
`ok`/`claimed_rank == 1` bar are all one code path. C1 and C2 in `core/lessons/gates.py` call
`probe_ranked` with a section payload and a sibling prompt. **No boundary exemption:** see R2.

**A sibling prompt is required and is not a second implementation.** `item_target.txt` opens
*"You are reading one language exercise"* and reasons throughout in terms of an exercise
posed to a learner. A section is prose. Asking that prompt about prose is asking a question
about a thing it does not describe.

**R2 · The archive's boundary claim would be true only by accident.** Archive §5b: *"the only
module in `core.lessons` that imports `core.llm`"*. There is **no `test_lessons_package_is_pure`**.
`core/lessons/` inherits `test_no_sql_outside_services` and `test_core_imports_no_web_framework`
for free (both walk all of `CORE` with no per-package allowlist), but nothing would stop a
lessons module reaching a model. `test_cards_package_is_pure`'s own docstring says W8a existed
to fix exactly *"pure by accident rather than by rule"*.

**Correction:** the slice adds the test, in the established shape, using `_import_targets` and
the existing `MODEL_REACHING_MODULES = {core.llm, core.speech, core.items.gates}`:

```python
LESSONS_MODEL_CALLERS = {LESSONS / "gates.py", LESSONS / "generate.py"}
```

That is a **tightening, not an exemption** — #59 remains the only boundary exemption in the
repo, and `core.items.gates` is already in `MODEL_REACHING_MODULES`, so importing it from a
named module is the sanctioned direction rather than a new hole.

**R3 · The #102 back-translation comparison IS structurally inert — and it is not in this
plan.** `grep -in "back.transl|equivalence|#102"` over `prompts/CC-W10b-grammar-lessons-PLAN.md`
returns **nothing**. The back-translation check and the `≤110` ceiling are both from
`prompts/CC-W10c-item-generator-PLAN.md:396-400,476`. Both were already recorded as corrected
at `BUILD_PROGRESS.md:296` and in `gates.back_translate`'s docstring.

The finding itself is confirmed independently: `equivalence_key`
(`packages/core/items/grading.py:100-124`) returns `tuple(token.lower for token in tokenize(...))`,
and `normalize.TOKEN` (`packages/core/lexicon/normalize.py:103`) is
`[0-9]+(?:[.,:/][0-9]+)*|[A-Za-z](?:[A-Za-z'-]*[A-Za-z])?`. Persian script (U+0600–U+06FF) and
Persian digits (U+06F0–U+06F9) match neither arm, so **every Farsi string folds to `()` and any
two compare equal**.

**Nothing is carried and nothing replaces it: this slice produces no Farsi at all.** A lesson
is English-only, no L1 gloss ever (archive §2, on #159's ground: a gloss is per-learner by
nature and would break the global line). #102 is untouched by W10b and keeps its slice.

**R4 · The `≤110 → 135` correction is also W10c's. This plan's number was `≤65`, and it is
wrong in the same way.** Archive line 457: *"**≤ 65 calls.** Comparable to W5b's 76."*
Re-itemised for units 1/9/20 in §7: **ceiling 174, expected 48–60.** The archive's 65 is the
*expected* case labelled as a ceiling — the identical error, a different number. Stated, not
adjusted (CLAUDE.md §3 rule 7 applies to a cost estimate).

**R5 · `schema_version` is 16, not 15. CONFIRMED.** Archive line 8 and the W10b slice row
(`BUILD_PROGRESS.md:144`) and `:3878` all say 15; they were written before W10 took 016. The
current value is 16 at `BUILD_PROGRESS.md:10,146,148,1476,1547,3110`, and production confirmed
it on 2026-08-28: `Applied: 001–016, Pending: (none)`. **Corrected in both stale sites at
implementation.** After 017 it becomes 17.

### 1.2 Fourteen the prompt did not name

**R6 · #110 is CLOSED. The archive says it stays open.** Archive §11: *"This closes the lesson
half of #110; #110 stays open for item content."* W10c closed it whole
(`BUILD_PROGRESS.md:288`, `:146`). The pattern moved out of `tests/` into
`packages/core/copy_rules.py`, which now carries two: `offenders(sources, pattern)` — the wide
copy rule — and `content_offenders(text)` — the narrower one that drops
`wrong / incorrect / missed / failed / broke` because *"a sentence a learner practises may
contain the word 'wrong' and a thing the app says about the learner may not"*.
`tests/support/no_guilt.py` is now a re-export.

**Consequence for this slice, and it is load-bearing:** a lesson's `wrong_example` is
*supposed* to contain a mistake, and its `why` line explains it. The lesson gate uses
**`content_offenders`** over generated prose and **`offenders`** over the UI strings. Using the
wide rule on lesson content would reject the field the lesson exists to carry. #110 is not
reopened.

**R7 · A stored lesson reaches block 3's `lesson` field with no schema change anywhere.**
The archive never states the path; it assumes only *"that block 3 exists"*. Read from the code:

- `packages/core/services/sessions.py:1220-1240` — `_focus_block` returns
  `{"unit_number", "can_do", "grammar_targets", "lesson": None, "items": [...]}`.
  `"lesson": None` is set at **`:1231`** and that is the only assignment in the Python source.
- It already imports a sibling service locally: `from core.services import items as items_service`
  at `:1222`, then `items_service.focus_items(user_id, unit_number=unit.unit_number)`.
- `apps/api/schemas/__init__.py:308-317` — `BlockOut.payload` is `dict[str, Any]`. There is no
  `FocusPayload` model and no per-kind union.
- `apps/web/lib/api.ts:386-390` — `SessionBlock.payload` is `Record<string, unknown>`.

**So the change is one line in `_focus_block`:** `"lesson": lessons_service.for_unit(unit.unit_number)`,
returning `None` when no row exists. **Zero pydantic change, zero route change, zero
TypeScript type change.** `apps/api/routers/session.py` is untouched.

**R8 · Unit 1 has 4 items, not 8, and only for one learner.** `FOCUS_ITEM_COUNT = 8`
(`packages/core/services/items.py:394`); production holds 14 rows, ids 7–20 — unit 1: 4,
unit 2: 3, unit 3: 7 — for **user 3 only** (#159). So the block a learner opens tomorrow is a
four-section lesson over four items. **This slice generates no items** (W10c owns that); the
number is reported, not fixed.

**R9 · The five diagram kinds survive the scope change, and this is recorded as a positive.**
Archive §6 chose them *"to cover all twelve targets in units 2, 9 and 20"*. Re-checked against
unit 1's four: `past simple: regular and irregular verbs` → `form_build`;
`past continuous for what was going on around it` → `timeline`;
`past simple and past continuous in the same sentence` → `timeline`;
`time linkers: then, after that, a bit later` → `annotated_example`. The closed set is
unchanged. Written down so it is not re-derived.

**R10 · `WORK_UNITS` and `track_for` already exist — do not author a second copy.** Archive §5a
proposes *"a constant in the lesson module"*. `packages/core/items/generate.py` already carries
`WORK_UNITS = frozenset({18, 19, 20, 21})` and `track_for(unit_number) -> str`, on #161's own
reading. **Unit 20 is `work`; units 1 and 9 are `life`.** Imported, not re-declared — a second
copy of a mapping is how the two halves of `docs/TASKS-v3-web.md` came to disagree (#130).

**R11 · `coverage_reference()` already exists and its docstring names this slice.**
`packages/core/items/generate.py:271-302` — CEFR A1/A2/B1 ∪ `freq_rank ≤ 2000`, **4,344 lemmas**,
pure, no database, no per-learner read. Its own docstring: *"The same reference W10b's approved
plan specifies for lesson prose."* Archive §5a describes building it. Imported.

**R12 · The archive's `--live` self-evaluation predates #201 and #206, and would reproduce the
bug they fixed.** Archive §8 has `--live` print its own verdicts. `_band`
(`packages/core/items/generate.py:1105-1150`) now takes an `exercised` count and prints
`NOT EVALUATED — no item reached this gate. Not met, not unmet: never asked.` at zero and
`NOT COMPARABLE` at a partial denominator. Without it, a run where nothing reached C2 prints
`L3: 0 of 36 — MET`.

**Correction:** `_band` and `_confirm` are **promoted, not copied**, to a new pure
`packages/core/runs.py` as `band` and `confirm`; `core/items/generate.py` imports them and its
existing tests pin the behaviour unchanged. A second implementation of the exact function whose
bug the record has counted nine times is not a defensible saving.

**R13 · The archive's negative control cannot run under any scope, and could not run under the
old one either.** Archive §5c fixes the control on *must and can't for what you're fairly sure
of* — not a target of unit 2, 9 or 20. `probe_ranked` raises `ValueError` when `claimed` is not
among the candidates, so a control claiming an out-of-unit target against in-unit candidates
**cannot be executed**. This is #213's family: a check whose own contract excludes what it
requires.

**Correction:** the control drifts **within unit 1**, matching `tests/fixtures/items/mistargeted.json`'s
sibling shape — a section claiming `time linkers: then, after that, a bit later` and written
entirely about `past simple: regular and irregular verbs`. Both are real unit-1 targets and each
other's nearest neighbours, which is what makes a pass diagnostic rather than absurd.

**R14 · The ≥95% coverage gate is replaced by a reported axis. Ruled by the operator, 2026-08-28.**
Archive §5a fixes ≥95% as a gate triggering regeneration. Grammar prose must say *past
participle*, *auxiliary*, *time linker*; #197 measured **8 of 8** everyday sentences below the
0.90 **item** floor against the real 2,000-lemma ledger. Registering a 95% gate on grammar
metalanguage risks an axis no lesson can pass — #213's shape, which §8 exists to prevent.
Coverage is **computed per section and reported, never enforced**, exactly W10c's shipped
position (`test_a_low_coverage_item_is_reported_and_NOT_rejected`). **This is not a bar being
lowered under rule 7: the bar is being declined before it is set, with the number reported so
the 21-unit slice can set one on evidence.**

**R15 · The archive's test baseline is stale.** *"1762 passed / 6 skipped; Vitest 74 across 7
files."* Current, run by W10r on 2026-08-27 and matching W10c exactly: **pytest 2026 / 6 skipped
/ 0 failing; Vitest 103 across 9 files.**

**R16 · The 017 renumber is confirmed at four rows, in both halves, and is still owed.**
`docs/TASKS-v3-web.md` authoritative table `:107-110` reads 017 W12, 018 W13a, 019 W14, 020 W18.
The per-slice Build columns say the same at `:64`, `:66`, `:67`, `:78`. W11 claims no number
(`:44`). See §4.

**R17 · The archive's server steps are correct in shape and stale in three details.** §14 step 5
restarts `english-api` only, which is right — `english-worker` is **not installed** (#69) and
W10's step 9 was corrected for instructing a command that cannot succeed. Three corrections:
`/home/bot/english-bot`, not `/opt` (#215 — `/opt/english-bot` was evidenced absent on the host
2026-08-28); `sudo -u bot`, never `ssh bot@<host>` (#215 — those lines have never executed as
written); and **a push-and-verify step 0 before the pull** (#223 — `origin/main` was two commits
behind local `HEAD` when the last deploy began, and the pull would have reported *already up to
date* and exited 0).

**R18 · `--apply`'s typed confirmation has no user id to type, because lessons are global.**
`_confirm` (`generate.py:1474-1482`) makes `--live` type the call ceiling and `--apply` type the
`users.id`. A lesson has no user. **Correction:** `--live` types the ceiling (`174`); `--apply`
types the unit list (`1,9,20`). Both are decisions rather than pasteable flags, which is the
whole point of the guard.

**R19 · The archive has no journal, and the journal is what stopped W10c's failures being
re-bought.** `Journal`/`read_journal`/`--report` (`generate.py:804-855`) flush after every
outcome and rebuild the full report from disk with **zero calls**; five of six `--live` attempts
were read back rather than paid for again. Carried: `w10b-journal.jsonl`, `--report`.

---

## 2. Scope, and the exact target count

**Units 1, 9 and 20.** Operator-confirmed 2026-08-28.

| Unit | Stage | Targets | Track |
|---|---|---|---|
| 1 | 1 | 4 | life |
| 9 | 3 | 4 | life |
| 20 | 5 | 4 | work |

**Twelve grammar targets → twelve sections → three lessons.** Not an estimate: read from
`data/syllabus_units.json`.

Unit 1 replaces unit 2 because `core.services.syllabus.current_unit` returns 1 for both
learners and **cannot advance** — `user_unit_state` is empty and nothing in the tree writes to
it (#188, confirmed in the function's own docstring at
`packages/core/services/syllabus.py:392-438`). Under the approved scope, W10b would generate
teaching nobody can see and block 3's four bare labels would be unchanged. **9 and 20 keep the
three-stage range test** — whether one prompt and one gate set hold across the syllabus, which
three consecutive stage-1 units would not answer. Unit 1 also already has items, so lesson and
practice sit on the same targets.

**Stated honestly: only unit 1's lesson is reachable in the session.** Units 9 and 20 are stored
and readable only through `GET /lessons/{unit_number}`, which is how the operator reads all
three for the acceptance check. That is not a defect of this slice; it is #188, and this slice
does not fix it.

---

## 3. What a lesson is, concretely

One lesson **per unit**, one section **per grammar target** — a bijection, enforced in code
(§6.1). Not per target as a whole lesson: 24 lessons, not 82.

**Section fields and their limits** (the limits are what make the 90-second promise checkable):

| Field | Shape |
|---|---|
| `target` | the grammar target's **exact text** from `data/syllabus_units.json` — the key `checkpoint.per_target` and `blueprint.validate_checkpoint` already use |
| `explanation` | 40–70 words, plain English at the learner's level |
| `when_to_use` | ≤ 20 words |
| `when_not_to` | ≤ 20 words — the part textbooks skip |
| `examples` | 2–3 sentences, ≤ 12 words each (`checks.MAX_SENTENCE_WORDS`, reused) |
| `wrong_example` | `{wrong, corrected, why}` — `why` ≤ 20 words |

A section is ~110–160 words and reads in 40–60 seconds. A lesson is four sections, ~500 words.
Plus **0 to one diagram per target** — 0–4 for the three units in scope, 0–5 by the schema's
mirror of `syllabus_units` (§5.1, and send-backs 1 and 8).

### 3.1 `target` is the identity AND a checkpoint key — the comparison, read from the code

`blueprint.validate_checkpoint` (`packages/core/syllabus/blueprint.py:100-148`) is **byte-exact
and normalises nothing**:

```python
known = {t.target for t in targets}
...
    if name not in known:            # per_target key -> target
...
missing = known - set(per_target)    # target -> per_target key
```

Plain set membership and plain set difference over the raw strings. **It already enforces the
bijection in both directions for `per_target`** — which means the lesson bijection is not a new
kind of rule, it is the third instance of one the content model already runs.

**So the lesson comparison is byte-exact, deliberately, and matches it exactly.** Normalising on
one side and not the other is precisely how the two would drift.

**Measured, not assumed** (`data/syllabus_units.json`, 2026-08-28):

- **All 24 units already agree byte-exactly** between `grammar_targets[].target` and
  `checkpoint.per_target` keys. Zero mismatches.
- **No target carries leading or trailing whitespace, and none is non-ASCII** — so there is no
  curly apostrophe or stray space in the data today.
- **No target text repeats across units**, so a target string is globally unique and a decoy
  drawn from another unit can never collide with an own-unit candidate in `probe_ranked`'s
  `sorted({...})` dedupe.

**The test the send-back asks for:** `test_a_lesson_section_targets_equal_the_checkpoint_keys` —
for every unit in scope, `{s.target for s in lesson.sections}` is asserted equal to
`set(unit.checkpoint["per_target"])`, **both directions, byte-exact**, with the expected value
read from `data/syllabus_units.json` and never from the lesson (rule 5). It fails loudly the day
a target is reworded on one side only — which is #212's own live risk, since rewording unit 2's
fourth target is an open operator question.

**English only. No L1 gloss, ever** — a gloss is per-learner by nature (#159) and would break
the global line in §4.

**`murphy_units` never reaches the generator.** #171's constraint, and the seam already exists:
`core.sessions.blocks.visible_targets` builds the learner-visible dict by *naming* the one field
that may travel. `core.items.generate.unit_plan` already routes its targets through it
(`generate.py:1307-1327`); the lesson generator does the same. Asserted over the prompt-builder's
output, not left as an intention.

### What the four labels become — and what the string becomes

**Annotated, not replaced.** Each `<li>` in `apps/web/components/session/blocks.tsx:155-164`
becomes a disclosure header carrying its section. The label text is untouched and still arrives
through `visible_target`, so #171's serialisation guarantee is unchanged.

- `BLOCKS.focus.noLesson` — *"The written explanation for these is on its way."*
  (`apps/web/components/session/copy.ts:72`) — is **rendered only when `payload.lesson` is
  null.** Today it renders unconditionally. It stays in the file, correct, for the 21 units with
  no lesson.
- **The first section is expanded by default; the other three are collapsed.** Opening the
  section the block's items are actually on is not possible without leaking `grammar_target`,
  which is in `projection.NEVER_VISIBLE` precisely so `probe_target` cannot read the answer to
  its own question. **Filed as residue against #169's family, not absorbed.**
- No badge, no count, no nav item, no backlog. `test_today_still_offers_one_button` passes
  untouched (#160, CLAUDE.md §4).

---

## 4. Migration 017 and the store

**PRODUCT-PRINCIPLES §2 position, stated as every slice adding a table must:** `grammar_lessons`
has **no `user_id` column at all**. Present perfect is present perfect for every learner. The
table is not user-keyed, so it neither depends on nor enlarges the identity established by
migration 011, and **it does not enlarge the `users.telegram_user_id` migration in any way.** §2
is satisfied trivially and this says so rather than leaving it inferred.

**PRODUCT-PRINCIPLES §3 position:** one row per unit, 24 rows forever, regardless of how many
learners arrive. Nothing scales per-user × per-anything. **Nothing in the design is per-learner.**

```sql
CREATE TABLE grammar_lessons (
    unit_number    SMALLINT PRIMARY KEY
                       REFERENCES syllabus_units(unit_number) ON DELETE RESTRICT,
    sections       JSONB NOT NULL,       -- one per grammar target
    diagrams       JSONB NOT NULL,       -- 0..5 typed specs, at most one per target
    verification   JSONB NOT NULL,       -- how it passed; mirrors items.validation
    lesson_version SMALLINT NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- DELIBERATELY WEAKER THAN THE CODE CHECK, and the gap is named here rather
    -- than left to be discovered. The real rule is a BIJECTION: one section per
    -- grammar target, both directions. This row cannot express it -- it does not
    -- know its unit's target count, and 3-5 here is satisfiable while 3-5 there
    -- is satisfied by a different number. `core.lessons.checks` enforces the
    -- bijection where the unit's targets are in hand. Same situation as the
    -- blocks-sum invariant living in `blueprint.validate_checkpoint` because 014
    -- could not mirror it (#167).
    CONSTRAINT grammar_lessons_sections_three_to_five
        CHECK (jsonb_typeof(sections) = 'array'
               AND jsonb_array_length(sections) BETWEEN 3 AND 5),
    -- BOTH ENDS ARE THE SAME DEFECT AND BOTH ARE FIXED HERE.
    --
    -- ZERO IS PERMITTED. "Fewer rather than false": if no target of a unit
    -- admits one of the five kinds, the correct output is no diagram and a
    -- REPORTED COUNT. A floor of 1 would make that legitimate state unstorable
    -- -- the run would die on an INSERT and the diagnostic would point at
    -- Postgres instead of at the condition the design anticipated.
    --
    -- FIVE IS THE CEILING, and it MIRRORS `syllabus_units`' own 3-5 rather
    -- than capping on today's data. The real rule is ONE DIAGRAM PER TARGET AT
    -- MOST: a diagram attaches to exactly one target, and a target carries at
    -- most one, so the maximum is the unit's target count -- 3 to 5 by
    -- `syllabus_units_three_to_five_grammar_targets`. A cap of 3 or 4 would
    -- forbid the output a four- or five-target unit naturally produces, which
    -- is the floor's defect at the other end. Capping at today's measured
    -- maximum (4) would also encode a measurement as a schema rule, which the
    -- sections CHECK deliberately declines to do.
    --
    -- LIKE THE SECTIONS CHECK, THIS ROW CANNOT SEE ITS UNIT'S TARGET COUNT, so
    -- 0-5 here is satisfiable while the real per-target rule is broken.
    -- `core.lessons.checks` enforces it where the targets are in hand: every
    -- diagram names a real target of this unit, and no target is named twice.
    --
    -- Both ends are #213's shape -- a contract excluding a state its own
    -- design produces -- and both were caught before they cost anything. The
    -- signal lives in the reported count and in pre-registered axis L8, not in
    -- a constraint.
    CONSTRAINT grammar_lessons_zero_to_five_diagrams
        CHECK (jsonb_typeof(diagrams) = 'array'
               AND jsonb_array_length(diagrams) BETWEEN 0 AND 5),
    -- "A lesson that fails verification is regenerated, never shipped with a
    -- warning", made unforgeable rather than promised.
    CONSTRAINT grammar_lessons_only_verified_rows_exist
        CHECK ((verification ->> 'verdict') = 'passed')
);
```

**Diagrams are a JSONB column, not a child table**, for a correctness reason: a failing lesson is
regenerated **whole**, because C3 spans prose and diagram together. A separate table lets a
diagram row survive a regeneration and contradict the new prose — the exact failure C3 exists to
catch.

### 4.1 `lesson_version` — the read policy, stated and tested

`lesson_version` mirrors `VALIDATOR_VERSION`'s role: bumped whenever a check tightens, so the
21-unit slice can tell which rows were verified under which rules. Retrofitting it is impossible.
Starts at **1**.

**The send-back is right that a version with no read policy serves stale teaching silently.**
`grammar_lessons_only_verified_rows_exist` keeps passing on a row verified under retired rules —
the CHECK cannot see the version, and that is by construction.

**Policy: refuse. `core.services.lessons.for_unit` filters on `lesson_version = LESSON_VERSION`
and returns `None` otherwise.** This is not a new judgement; it is the shipped precedent copied.
`bank_for_session` (`packages/core/services/items.py:369-391`) already appends
`_CURRENT_VALIDATOR` and filters the bank on `validator_version = VALIDATOR_VERSION`, on W10's
stated reason that *a version-1 row was validated by a gate that could not detect
multi-acceptability and may be ungradable*. A lesson verified by checks that no longer exist is
the same claim.

**The consequence, stated rather than discovered:** bumping `LESSON_VERSION` empties every stored
lesson until it is regenerated, and block 3 falls back to `lesson: None` and the `noLesson` line —
which is honest, and is the same behaviour a unit with no lesson has. **So the bump is never
silent:** the dry run prints `stored lessons below LESSON_VERSION: n of m`, and the deploy step
reads that number before `--apply`. Asserted by
`test_a_lesson_below_the_current_version_is_not_served` and by a session test that block 3 shows
`lesson: None` in that case.

No `ALTER TABLE users`, so **#48 does not fire** — stated rather than omitted, since #48 has
recurred by each case looking like the exception.

### The renumber — owed, not done

`docs/TASKS-v3-web.md` reserves 017 for W12. W10b sits after W10, so it takes **017** and four
rows shift:

| # | was | becomes |
|---|---|---|
| 017 | W12 | **W10b** |
| 018 | W13a | W12 |
| 019 | W14 | W13a |
| 020 | W18 | W14 |
| 021 | — | W18 |

**Both halves in the same commit as the `.sql` file** — the authoritative table at `:107-110`
*and* the per-slice Build columns at `:64`, `:66`, `:67`, `:78`, because nothing reconciles them
(**#130**, open, targeted W19, named here rather than absorbed). W11 claims no number and this
slice does not give it one.

**This is #185's fourth occurrence** — W4b renumbered eight rows, W8f five, W10b four — and the
row is updated with a fourth sighting rather than a second issue being filed. **The renumber is
owed at implementation time and is not done by this plan** (#185); `docs/TASKS-v3-web.md` stays
unchanged today.

---

## 5. Diagrams — typed data, rendered by us

**Ruled 2026-08-26 and not re-argued:** the model emits a typed spec through the existing
`core.llm` wrapper and `apps/web` renders it as SVG. No image model, no second provider SDK, no
new environment variable, no CLAUDE.md §2 amendment. The image-model option was raised once and
declined: a raster diagram cannot be checked without rasterisation plus a vision call; an image
model is a wrapper this codebase does not have; and the licence answer would have to be
established from scratch for image output.

**Five kinds** — `timeline`, `contrast_pair`, `form_build`, `decision_tree`, `annotated_example`
(R9 confirms they cover units 1/9/20).

**The schema has no colour, font or coordinate field.** The renderer owns all of it, so *"no red
in the lesson UI"* is **structural** — the model cannot choose a colour — and the `.tsx` scan
covers the renderer with the same banned list `test_no_red_reaches_the_correction_screen` uses.

**Checked deterministically, free:** the kind is one of five; required parts present; counts in
range; **every label appears in the section's own prose** (a diagram naming a form the lesson
never mentions is a diagram inventing content); per-kind ordering — a `timeline`'s points are
monotonic with exactly one marked `now`, a `decision_tree`'s branches are exhaustive and
distinct; banned phrases; the named target exists in the unit.

**Checked by model at no extra cost:** the spec renders to a textual description included in C1's
section payload and C3's whole-lesson payload. A diagram teaching a different point, or
contradicting the prose beside it, fails the same two checks the prose does.

**Not checked, and this is the honest part: whether the picture reads.** Nothing touches
legibility or whether a timeline helps a B1 learner on a phone. **The instrument for that is the
operator's eyes, and unlike the English, this is a check he can actually run.** That asymmetry is
why diagrams earn their cost here.

### 5.1 Fewer rather than false — and the floor is removed, not the rule

If a target admits no fitting kind, **no diagram is produced and the generator reports the
count.** Never smoothed over by forcing a timeline onto *"email openings and closings"*.

**The archive paired that rule with a floor of one per lesson, and the two cannot both hold.**
A lesson whose targets all decline a kind — the state the rule declares legitimate — would have
zero diagrams and be **unstorable** under `BETWEEN 1 AND 3`. The run would die on an INSERT and
the diagnostic would name Postgres rather than the condition the design anticipated. That is R13
and #213's family: **a contract excluding a state its own design declares legitimate.**

**Resolved by allowing zero** (§4). The floor was the wrong half to keep: the rule is the thing
with a reason behind it, and *forcing* a diagram is the failure the rule names. **Zero is not
resolved by generating one.**

### The ceiling was the same defect at the other end, and it is fixed with it

**The first revision removed the floor and left the cap at 3.** With four targets per unit in
scope and all twelve admitting a kind (table below), **the natural first-pass output is four
diagrams and the INSERT fails** — on Postgres, with a diagnostic naming the database rather than
the cap. L8's own *4 of 4* branch would have been unreachable. Identical shape, caught once and
kept once.

**The rule, stated because it was previously a habit:** a diagram attaches to **exactly one**
target, and **a target carries at most one.** Two diagrams on one target is either redundancy or
the same point twice, and the deterministic *every label appears in the section's own prose* check
is defined per section — two diagrams against one section makes it ambiguous which prose the label
must appear in. A `contrast_pair` shared across two targets would have to name both and break the
one-target attachment.

**So the maximum is the unit's target count, and the CHECK mirrors `syllabus_units`' 3–5 at
`BETWEEN 0 AND 5`.** Capping at 3, or at today's measured maximum of 4, would encode a measurement
as a schema rule — which §6.1 explicitly declines to do for sections, and the two must not reason
differently about the same data. **The real per-target rule lives in `core.lessons.checks`** where
the target list is in hand: every diagram names a real target of this unit, and no target twice.
Same structure as the sections bijection, same reason, and the migration comment says so beside
the one that already explains it.

**The signal moves to where it can be read**: the reported per-lesson count, and pre-registered
**axis L8** (§8). A zero-diagram lesson is then a finding somebody reads, not a crash.

**And the floor is not needed here, on evidence.** The twelve targets in scope, mapped against
the five kinds by inspection:

| Unit | Target | Fitting kind |
|---|---|---|
| 1 | past simple: regular and irregular verbs | `form_build` |
| 1 | past continuous for what was going on around it | `timeline` |
| 1 | past simple and past continuous in the same sentence | `timeline` |
| 1 | time linkers: then, after that, a bit later | `annotated_example` |
| 9 | present continuous for arrangements | `timeline` |
| 9 | going to for plans and for what looks likely | `timeline` |
| 9 | will for decisions made as you speak | `contrast_pair` |
| 9 | will or going to: which one and why | `decision_tree` |
| 20 | email openings and closings that aren't translated | `annotated_example` |
| 20 | getting to the point in the first line | `annotated_example` |
| 20 | register: same message, formal and informal | `contrast_pair` |
| 20 | chasing without nagging | `contrast_pair` |

**All twelve admit a kind, so a zero-diagram lesson would be a surprise in this run** — which is
exactly why L8 predicts 2–3 and treats 0 as a reading rather than a pass. **This mapping is
evidence for a prediction, not a specification**: the generator chooses, and being handed this
table would make L8 confirmatory. It is not given to the model.

---

## 6. The gate set — every gate, and what each establishes

Cheapest first, exactly as `gates.validate` orders its stages: **every free check runs before any
call costs money.** All three model checks are **blind and productive, never confirmatory** — a
gate asked a leading question returns a yes (W5a's finding).

### 6.1 Free, deterministic, no call

| Check | On what | Reused from |
|---|---|---|
| **bijection** | one section per target, **both directions** | new, `core/lessons/checks.py` |
| `naturalness.jargon_hits(text, track=track_for(unit))` | every example sentence | `core.items.naturalness` |
| `naturalness.textbook_hits` / `uncontracted` | every example sentence | `core.items.naturalness` |
| `copy_rules.content_offenders` | every generated string (R6) | `core.copy_rules` |
| diagram structure, labels, ordering | every diagram | new, §5 |
| word/length limits | every field | `checks.MAX_SENTENCE_WORDS` reused |
| `compute_coverage(text, coverage_reference())` | section prose | **reported, never enforced** (R14) |

**The bijection is the one that hurts if it is one-directional.** Unit 1 has four targets; a
lesson with three sections satisfies `grammar_lessons_sections_three_to_five` (3–5) *and*
`syllabus_units_three_to_five_grammar_targets` (3–5) while the counts disagree. It would pass C1
on each of its three sections, pass C2, pass C3, have no orphan section — and leave one target
untaught, **carrying 2 of unit 1's 12 checkpoint items**. Orphan detection looks the wrong way.
Enforced in `core/lessons/checks.py` where the unit's authored targets are in hand; the SQL CHECK
deliberately cannot express it and the migration comment says so and says why. **Fifth appearance
of a guarantee whose predicate cannot see the thing it is about** — #152, #164, #167, #180, and
now this — counted rather than met freshly. Comparison byte-exact, per §3.1.

#### The SQL CHECK is weaker than this plan first admitted, and here is the number

The argument above was correct as reasoning and **unverified as arithmetic**. Measured from
`data/syllabus_units.json`:

| targets | units | which |
|---|---|---|
| **3** | **14** | 3, 5, 7, 10, 11, 13, 14, 16, 17, 18, 19, 21, 22, 23 |
| **4** | **10** | 1, 2, 4, 6, 8, 9, 12, 15, 20, 24 |
| **5** | **0** | — |

82 targets over 24 units, and **no unit has five.** So:

- **For every one of the 24 units, 2 of the 3 section counts the CHECK permits are wrong.** The
  CHECK admits the wrong count two times out of three, for every unit in the syllabus.
- **A five-section lesson is wrong for all 24 units today, and the CHECK permits it for all 24.**
- The three units in scope are all four-target units, so within this slice the CHECK's only
  correct value is 4 and it permits 3 and 5.

**The CHECK is nonetheless left at 3–5 rather than tightened to 3–4**, and the reason is stated so
it is not re-argued: `syllabus_units_three_to_five_grammar_targets` is itself 3–5, so a unit
gaining a fifth target is legal in the syllabus. Tightening the lesson CHECK to today's data would
encode a measurement as a schema rule and would break — on the lesson side only — the day the
syllabus exercises its own permitted range. **The mirror is the correct relationship; the
bijection in code is the guarantee.** What changes here is that the weakness is now a number in
the record instead of a hand-wave, and the migration comment carries it.

### 6.2 Model gates

**`gates.judge_naturalness(sentences)` — 1 call per lesson.** Sees **the examples and never the
explanation.** Its prompt asks *"would a real person say this to a friend?"* — correct for an
example, meaningless for a paragraph of teaching. Handing it the explanation would be #115's
mistake with the polarity flipped: the right gate over the wrong string. **12 sentences ≤
`JUDGE_BATCH` (20), so this is the first caller ever to actually use the batch path** — every
existing call site passes a list of one. It does **not** close **#120**, which is about
`gates.validate`'s per-item call; it demonstrates the path works.
**Its verdict fails open on a missing row (`MISSING_ROW`) and the lesson gate asserts against
that trap in both directions**, as `NaturalnessVerdict`'s own docstring warns.

**C1 · It teaches the target it claims — 1 call per section (4 per lesson).**
`probe_ranked` with a section payload: `explanation`, `when_to_use`, `when_not_to`, `examples`,
and the diagram-as-text, **with the target name removed**. Candidates are the unit's own 4
targets plus **3 decoys** from other units (`gates.TARGET_DECOYS`, and
`generate.target_candidates`'s nearest-unit rule reused). Sorted, not shuffled.
**Pass: the claimed target ranks first.** The decoys that matter are the **siblings** — unit 1's
four points are all past-tense and are each other's nearest neighbours. **A sibling ranking
second is recorded, never failed** (#119): it names the distinction the prose blurred.

**C2 · Every example actually shows the structure — 1 call per example, not batched.**
For `probe_acceptable`'s exact reason: this asks the model to recover an answer, so a
neighbouring sentence from the same section would leak it. **The judge receives the sentence
alone** — no label, no target name, no section around it — and ranks which target it
demonstrates. **Pass: the section's own target ranks first.** W5c's rule as a bar: the judge
receives the thing itself, never the claim about it.

**No deterministic grammar detector is written.** Eighty-two hand-written structure matchers
would be a second grammar engine, and one that is wrong is worse than none. Said plainly rather
than implied by an absent check.

**C3 · It contradicts nothing — 1 call per lesson.** Over the whole lesson: every section's
prose, every example, every wrong example and its correction, and each diagram rendered to text.
Asked to **list contradictions, not to rate the lesson**. **Pass: the list is empty.** A non-empty
list is stored so regeneration is informed rather than blind.

### 6.3 The negative control — the half that makes the rest mean anything

`verify.py`'s central lesson: **a check that rejects nothing passes the catch direction
perfectly.** `--live` runs `tests/fixtures/lessons/drifted.json` — a section claiming
*time linkers: then, after that, a bit later* and written entirely about
*past simple: regular and irregular verbs*, both real unit-1 targets (R13) — through C1
**three times, before any lesson**, so a dead C1 costs 3 calls rather than 174.

**Prediction 3 of 3; bar 2 of 3.** Below the bar the run is **VOID**: nothing is written whatever
the three lessons did, the module exits non-zero, and this is a finding to record. **2 of 3
prints, in exactly these words, `prediction NOT MET, run acceptable`** — asserted by a test so
neither reading can be quietly preferred after the fact. The two numbers are different on purpose:
the prediction is what a working C1 should do; the bar is what constitutes evidence that C1
discriminates **at all**, and one stochastic miss on a borderline classification is not the same
event as a gate that cannot tell one tense from another.

### 6.4 Failure is regeneration, with a cap

A lesson failing any check is regenerated **whole**, with the failing check's diagnostics fed back
into the prompt. **Cap: 2**, the same number as `gates.MAX_REPAIRS` and for the same reason. Still
failing after two → **reported as unshippable and the run stops**. Never shipped with a warning,
never with a bar adjusted (rule 7). `grammar_lessons_only_verified_rows_exist` makes that
unforgeable rather than intended.

---

## 7. Cost — itemised, and the number is a number

Per lesson, per pass, at the 3-example ceiling:

| | calls |
|---|---|
| generation | 1 |
| C1, one per section | 4 |
| C2, one per example (4 sections × 3) | 12 |
| `judge_naturalness`, one batch of 12 | 1 |
| C3, whole lesson | 1 |
| **per pass** | **19** |

Passes per lesson: 1 + `MAX_REGENERATIONS` (2) = **3** → **57 per lesson**.

**Ceiling: `3 (control) + 3 lessons × 19 × 3 = 174 billed calls.**
**Expected, first pass, no regeneration: 60** at 3 examples per section, **48** at 2.

### 7.1 The run is staged, and the ceiling is per stage

**Send-back 3, and it costs nothing but ordering.** Running all three units in one `--live` spends
the full amount before anyone reads a word — and W10c's history is **six `--live` attempts and 54
calls** before one wrote. `--units` already supports the split.

| Stage | Command | Ceiling | What it buys |
|---|---|---|---|
| **1** | `--live --units 1` | `3 + 57 = **60**` | The one lesson a learner can reach, read in block 3 **on a phone**. If the prompt is wrong it is wrong at a third of the cost. |
| **2** | `--live --units 9,20 --skip-control` | `2 × 57 = **114**` | The three-stage range test, once stage 1 has been read and is good. |
| | **total** | **174** | unchanged |

**What carries between stages:** the same `w10b-journal.jsonl`, appended. `read_journal`'s
last-write-per-`(unit, section)` rule means stage 2 cannot clobber stage 1 — different unit keys —
and `--report` rebuilds the whole run across both stages for **zero calls**.

**The control does not re-run in stage 2**, using the existing `--skip-control` flag and its
shipped guard (*"Only valid while that result stands"*). Three calls buy the same evidence about
the same `probe_ranked` in the same session against the same model. **One condition, stated:** if
stage 1's control lands at **2 of 3** — at the bar but below the prediction — **stage 2 re-runs
it**, because a control that has already missed once is not a banked result. At 3 of 3 it is
skipped and the banked verdict is cited by date.

**Stage 2 is not authorised by stage 1 passing its gates.** It is authorised by the operator
having read lesson 1.

This is a **true worst case** in `_expected_calls`' shape — it assumes every lesson exhausts both
regenerations — and it is printed by the dry run before anything is spent. The archive's `≤65` is
the expected case labelled as a ceiling (R4); **stated, not adjusted.**

**A re-run costs the same 174 ceiling.** A single failed lesson re-run costs **≤ 57**. `--report`
rebuilds the whole report from `w10b-journal.jsonl` for **zero calls** (R19).

**Zero TTS and zero STT**, asserted by a test rather than assumed: no lesson field is audio and
`gates._audio_gate` is unreachable from this module.

---

## 8. Pre-registered axes — with the structural-impossibility pre-check first

**#213's lesson, applied before the numbers.** #213 was found *"by running a PERFECT draft
through the gates rather than by reading the prompt"* — a contract that excluded the field its own
check required, nine straight failures with no stochastic component. **A contract that excludes
the field its own check requires is not a measurement.** So, as tests, before any billed call:

1. **`test_every_field_a_check_reads_is_a_field_the_contract_asks_for`** — the set of fields the
   deterministic checks and C1/C2/C3 payloads read is asserted a **subset** of the generated
   contract's keys. This is #213 as a test rather than as a memory.
2. **`test_a_perfect_specimen_lesson_passes_every_deterministic_check`** — a hand-authored
   `tests/fixtures/lessons/specimen.json` for unit 1, driven through every free check. A specimen
   that cannot pass means an axis is unpassable, and the run does not start.
3. **The control runs first at `--live`** and voids the run (§6.3), so a dead C1 costs 3 calls.
4. **Every axis carries an `exercised` denominator** through the promoted `runs.band` (R12), so
   an axis nothing reached prints `NOT EVALUATED — not met, not unmet: never asked` rather than
   MET.

**The axes.** Written into the module docstring before `--live` is ever executed; `--live`
evaluates its own branch rules and prints the verdict, so the reading cannot bend after the number
arrives. W8b's finding carried: *a pre-registered prediction constrains honesty about the axis it
names and says nothing about an axis it does not* — so each gets its own number.

| # | Prediction | Branch rules |
|---|---|---|
| **L1** | **0–1 of 3** lessons fail verification on the first pass | **0** → the checks may be too weak at n=3; L6 decides whether the result is believed. **1** → expected; regenerate, record which check caught it. **2–3** → the generator prompt is wrong, not the gate. Fix the prompt, re-run, **do not loosen a check** (rule 7). |
| **L2** | **0–2 of 12** sections fail C1 | **≥5** → rewrite the generator prompt, not C1. Low because the generator is *given* the target verbatim; not zero because unit 1's four targets share one tense and C1's sibling decoys are genuinely close. |
| **L3** | **0–4 of 24–36** examples fail C2 | **≥9** → the prompt is asking for examples rather than for *demonstrations*; rewrite the prompt. |
| **L4** | **0–6 of 24–36** examples rejected by `judge_naturalness` | **≥12** → read them before touching anything; #115 recorded 6/11 on hand-written items and the judge is strict. |
| **L5** | **0–2** diagrams fail the deterministic label/order checks, **of however many were produced** | **≥4** → tighten the diagram schema, not the check. **Re-based after send-back 8:** the archive's `~6` came from the old 1–3 cap. With twelve targets that all admit a kind and L8 predicting 2–3 per lesson, the denominator is **6–9 expected, 12 possible** — so the band is stated over *produced*, and `band(exercised=...)` supplies the real denominator rather than a guessed one. A band written over a denominator that did not happen is exactly what #201 and #206 fixed. |
| **L6** | **the drifted control fails C1 in 3 of 3** | **Bar: 2 of 3.** Below 2 → **RUN VOID**, whatever the three lessons did. Prediction and bar are different numbers on purpose (§6.3). |
| **L7** | section-prose coverage against the 4,344-lemma reference lands **88–96%** | **Reported, never enforced** (R14). Below 85% → the metalanguage cost is real and larger than predicted, and the ruling on #197 for prose is the operator's, owed against a number rather than an absence. **No regeneration is triggered by this axis and no lesson is rejected for it.** |
| **L8** | **2–3 diagrams per lesson**, of a possible 4 | **New, and it is where the removed floor's signal went** (§5.1). **0 for any lesson** → read the four targets and say which kind was declined and why: either the closed set is short a kind, or the prompt is not offering them. **4 of 4 on every lesson** → the generator is decorating rather than choosing, and *fewer rather than false* is not being exercised. **Zero is reported, never rejected** — a lesson with no diagram is storable by construction. |

---

## 9. The generator — human-run, dry by default

```
python -m core.lessons.generate [--units 1,9,20] [--live] [--apply]
                                [--journal PATH] [--report JOURNAL] [--skip-control]
```

Modelled directly on `core.items.generate`, which is the best-behaved billed script in the repo.

- **Dry by default.** Reaches the database, prints the model, `max_tokens`, the **substituted**
  system prompt via `lesson_system_prompt()` — never the raw template with a `{contract}`
  placeholder, which is W10c's own caught defect: *read the thing that changed from the path that
  will actually run* — the per-unit payload, the C1 candidate lists marked `own`/`decoy`, the
  coverage reference size, the control fixture, the journal path, the pre-registered axes, and
  **the exact billed-call ceiling.** Sends nothing.
- **Generation is human-run** (operator ruling, 2026-08-27, from #196). Nothing generates
  unattended. `assign_daily` is untouched and
  `test_assign_daily_is_registered_and_creates_no_content` stays green unchanged. This is
  independent of #69.
- **`--live` verifies and prints; `--apply` writes.** Separated so the operator reads three
  lessons before a row exists.
- **Typed confirmation, no `--yes`** (R18). A flag that can be pasted out of a runbook is not a
  decision. **The rule, not the values:** `--live` types **that invocation's own ceiling**, and
  `--apply` types **that invocation's own `--units` list** — both computed for the exact `--units`
  given and **printed by the dry run and by the confirmation prompt itself.**
  **The number is never transcribed from a document.** An earlier draft of this plan carried the
  unstaged literals here (`174` and `1,9,20`) while §15 carried the staged ones, which is two
  sources of truth for the string typed at the moment money is spent — #223's failure one field
  over, and worse than no guard, because the operator reads the document, is rejected, and
  reasonably concludes the guard is broken. §15's commands show what each stage prints; **§15
  illustrates, this rule governs.**
- **`logging.basicConfig(level=INFO)` at entry — #140.** `core/llm.py` logs exact per-call token
  usage at INFO; a script leaving the root logger bare drops every line through `lastResort`, which
  is how W8's tagger had 138 calls and $6.60 reconstructed after the fact against a $1–2 estimate.
  **#140 stays open** and still names `judge_observe.py` and `verify.py`.
- **`reject_truncation=True` on every call**, and `LESSON_MAX_TOKENS` set with headroom over the
  measured response size. W10c's attempt 1 died on `stop_reason=max_tokens` at 8,000; the
  correction there was that **thinking tokens are billed and count against `max_tokens`**.
- **Journal after every outcome, flushed** (R19).
- **No SQL in this module** — everything goes through `core.services.lessons`, so
  `test_no_sql_outside_services` stays unexempted and **#59 remains the only exemption**.

---

## 10. Verification — the three-way split, carried verbatim from W10c

Not reassigned to a reader who has said he cannot make the judgement.

**(a) HIS READING, and nothing else, establishes:** that the lesson reads as teaching and not as
a definition list; that the wrong example is recognisably a mistake someone would make; that the
**diagram reads on a phone** — a timeline that is confusing is a visual judgement, not an English
one, and this is the one instrument in this slice he actually has; and that four sections behind
four labels feel like an explanation rather than a form.

**(b) THE GATES, and not his reading, establish:** the bijection, target-first on every section
(C1), demonstration-not-decoration on every example (C2), internal consistency (C3), naturalness,
no-guilt, diagram structure. **He reads the stored verdicts, not the English.**

**(c) NEITHER establishes whether the lesson is correct English teaching a correct point.** That
rests on C1/C2/C3, which are a model checking a model, plausibly the same model, with correlated
blind spots. **It is not quietly reassigned to a reader who has said he cannot do it**, and it is
the strongest reason the scope is 3 lessons and not 24.

**Written into `core/lessons/generate.py`'s own docstring, not only here.**

### What verification cannot do — each filed, not left as a paragraph

1. **A model checking a model.** A wrong-but-fluent explanation of a fine distinction can pass C1,
   C2 and C3 together. Not equivalent to a human reading it, and no number of checks makes it so.
2. **One sample per check of a stochastic system.** A fail is decisive; a pass is not proof.
3. **Nothing checks that the lesson is useful.** A section can teach its target, contradict
   nothing, sit at 96% coverage, and help nobody.
4. **Nothing checks that the diagram reads** (§5).
5. **A frontier model resolves distinctions a B1 learner will miss**, so a clean C1 is weaker
   evidence about a learner than it looks — the asymmetry the record already states for STT and
   for the blind solver.

Each becomes a known issue with a severity and a slice. **1, 2 and 5 are the lesson-side siblings
of #194/#195 and are filed as an update to those rows where they are the same defect**, rather
than as duplicates.

---

## 11. Licence gate — run first, quote verbatim

`data/LICENCES.md` gains a W10b section, and **the gate is run before any code with its verbatim
quote in the decisions log.** PRODUCT-PRINCIPLES §3 requires the answer to hold for a commercial
product; *"it's fine"* is the shape of an answer nobody can re-check.

The typed-SVG ruling means the artefact is **model text output**, so this is the question W8
answered for the syllabus — *Anthropic's terms assign output to the customer* — but **the current
terms must be re-read and the clause quoted verbatim, not carried over as a summary.** Recorded
twice over: what the model produces is a **JSON diagram spec, not an image**; the **rendered SVG
is our own code's output**, and the renderer and its five kinds are original work in this
repository; and **no third-party image, font or illustration enters the repo** — the seven faces
in the app are OFL 1.1 and unchanged from W8c.

**If the terms do not hold, the slice reports it and stops.**

---

## 12. Tests

Every test names the user action it exercises (rule 4); no test derives its expected value from
the function under test (rule 5); no test depends on wall-clock date (rule 6).

**Python**
- `tests/test_migration_017.py` — the three CHECKs compared against `core.lessons`' constants, the
  way `test_migration_014` does for `UNIT_STATES`; **and both diagram-count edges driven against a
  real database rather than read off the DDL** — a **zero**-diagram lesson INSERTs successfully
  and a **five**-diagram lesson does too (§5.1), because those are the two states the first two
  drafts of this plan each made unstorable.
- `tests/test_lessons_schema.py` — the pydantic shapes; **the diagram schema has no colour, font
  or coordinate field**, asserted, because that is what makes "no red" structural.
- `tests/test_lessons_checks.py` — every deterministic check, both directions, hand-authored good
  and bad fixtures. **The bijection in both directions**, using unit 1's real four-target list: a
  three-section lesson is refused (the case the SQL CHECK cannot see), and a section naming a
  target the unit does not have is refused. **And the per-target diagram rule, both directions**
  (§5.1): a diagram naming a target the unit does not have is refused, and two diagrams on one
  target are refused — the rule the 0–5 CHECK deliberately cannot see, for the same reason and in
  the same place as the bijection.
- `tests/test_lessons_gates.py` — C1/C2/C3 with the model seam monkeypatched at `_chat`, driven
  **in both directions**, including the drifted control. The `NaturalnessVerdict` fail-open trap
  asserted against for each new verdict type.
- `tests/test_lessons_contract.py` — **§8's two pre-checks**: the field-subset assertion and the
  perfect-specimen run.
- `tests/test_lessons_service.py` — insert; a second `--apply` writes nothing;
  **`test_a_lesson_below_the_current_version_is_not_served`** (§4.1), and a session-level case
  that block 3 shows `lesson: None` for such a row.
- `tests/test_lessons_route.py` — **through the ASGI transport** (rule 1), not a direct service
  call: **`401` unauthenticated**, `200` signed in, `404` for a unit with no row and for a unit
  outside 1–24 (§13.1).
- `tests/test_lessons_keys.py` — **`test_a_lesson_section_targets_equal_the_checkpoint_keys`**
  (§3.1), both directions, byte-exact, expected values read from `data/syllabus_units.json`.
- `tests/test_sessions_service.py` — **extended, not replaced**:
  `test_block_three_carries_labels_a_null_lesson_and_no_items` keeps asserting `lesson is None` for
  a unit with no row, and a new case asserts a stored lesson arrives in the same field.
- `tests/test_no_murphy_reaches_a_learner.py` — **extended, not copied** (#171): the `.tsx` scan
  gains the lesson renderer, and `murphy_units` is asserted never to reach the lesson
  prompt-builder's output.
- `tests/test_core_boundary.py` — **`test_lessons_package_is_pure` added** (R2), with
  `LESSONS_MODEL_CALLERS` named; `test_core_imports_no_web_framework` and
  `test_no_sql_outside_services` cover `core/lessons/` free.
- `tests/test_runs.py` — the promoted `band`/`confirm` (R12), including the zero and partial
  `exercised` cases, so #201's and #206's fix cannot regress.
- **No-guilt over generated content** — `copy_rules.content_offenders` over the stored lesson
  fixture, **and** a test that the wide `offenders` rule is *not* used on lesson content (R6).

**Vitest** — the lesson renderer; **a lesson with zero diagrams renders without a hole** (§5.1);
the `/lessons/[unit]` page renders through the same components (send-back 7); each of the five
diagram kinds; the banned colour list
(`line-through`, `text-destructive`, `bg-destructive`, `text-red`, `bg-red`, `border-red`, `❌`);
the wrong example is visually subordinate to the correct one, never the headline; **`noLesson` still
renders when `payload.lesson` is null and does not render when it is not** — the existing
`"still says the written explanation is on its way (#182, W10b's half)"` test is **rewritten to
assert the null case**, with its old assertion quoted in the record rather than silently deleted.

**Baseline to hold: pytest 2026 passed / 6 skipped / 0 failing; Vitest 103 across 9 files** (R15).

---

## 13. Files

| File | Purpose |
|---|---|
| `migrations/017_lessons.sql` | `grammar_lessons` |
| `packages/core/lessons/__init__.py` | `LESSON_VERSION`, `DIAGRAM_KINDS`, `SCOPE_UNITS`, `MAX_REGENERATIONS`, the field limits |
| `packages/core/lessons/schema.py` | pydantic: `Lesson`, `Section`, `Example`, `WrongExample`, the five diagram specs |
| `packages/core/lessons/checks.py` | every deterministic check. Pure. |
| `packages/core/lessons/gates.py` | C1, C2, C3 over `probe_ranked`. Model-reaching, named. |
| `packages/core/lessons/generate.py` | human-run CLI: dry, `--live`, `--apply`, `--report` |
| `packages/core/services/lessons.py` | every query against `grammar_lessons` |
| `packages/core/runs.py` | **new**: promoted `band` and `confirm` (R12) |
| `packages/core/prompts/lesson_generate.txt` | the generator |
| `packages/core/prompts/lesson_on_target.txt` | C1 |
| `packages/core/prompts/lesson_structure.txt` | C2 |
| `packages/core/prompts/lesson_contradiction.txt` | C3 |
| `tests/fixtures/lessons/drifted.json` | the negative control (unit 1 sibling drift) |
| `tests/fixtures/lessons/specimen.json` | the perfect draft, for §8's pre-check |
| `apps/api/routers/lessons.py` | `GET /lessons/{unit_number}`, a **plain `def`**, parse → authorise → one service call → serialise (§13.1) |
| `apps/web/components/lessons/lesson.tsx` | the lesson block |
| `apps/web/components/lessons/diagram.tsx` | the five kinds as SVG |
| `apps/web/app/(app)/lessons/[unit]/page.tsx` | **new (send-back 7)** — renders any unit's lesson through the same two components |
| `data/LICENCES.md` | + the W10b section |
| `docs/TASKS-v3-web.md` | 017 → W10b; W12/W13a/W14/W18 shift by one, **both halves** |

### 13.1 `GET /lessons/{unit_number}` — what "authorise" means for a resource with no owner

**Send-back 5 is right that this is genuinely ambiguous.** `grammar_lessons` has no `user_id`, so
there is no row-level check to make. What is left is whether the caller is signed in at all.

**Pinned: logged-in only, identical to `/session/today`.** The same two dependencies, read from
`apps/api/routers/session.py:68-79` and copied rather than reinvented:

```python
@router.get(
    "/{unit_number}",
    response_model=LessonOut,
    dependencies=[Depends(rate_limit("lesson_read", per_client=200,
                                     overall=800, window_seconds=3600))],
)
def lesson(unit_number: int,
           session: AuthenticatedUser = Depends(require_current_user)) -> LessonOut:
```

`session` is used to authorise and **not** to select — the lesson served is the same for every
learner, which is §4's global line on the wire.

**Asserted, not asserted-in-passing:** `tests/test_lessons_route.py` drives the route **through
the ASGI transport** and asserts **`401` unauthenticated** and `200` signed in, plus `404` for a
unit with no row and for a `unit_number` outside 1–24. The 401 is the same evidence the deploy
uses for `english-api` being live — *proven by `HTTP/2 401`, not by the `active (running)` line*.

**Edited, not created:** `packages/core/items/gates.py` (the `probe_ranked` split, R1);
`packages/core/items/generate.py` (imports `runs.band`/`runs.confirm`, R12);
`packages/core/services/sessions.py:1231` (the one-line `lesson` read, R7);
`apps/web/components/session/blocks.tsx` + `copy.ts` (the conditional `noLesson`, §3);
`tests/test_core_boundary.py`; `tests/test_no_murphy_reaches_a_learner.py`.

---

## 14. Not this slice — named, not absorbed

- **Not W11.** No `user_unit_state` write, no unit advancement, no checkpoint. **#217 and #219 are
  unresolved and this slice does not touch the state machine.**
- **Not a fix for #188.** Unit 1's lesson is seen because unit 1 is where everyone is stuck, not
  because anything advances. Units 9 and 20 are unreachable in the session.
- **No new items.** W10c owns the item generator. Block 3 keeps its 4 unit-1 items.
- The other 21 units · **#183**'s four live Murphy surfaces · per-learner adaptation · audio for
  lessons · the checkpoint's own content · **#165**'s `syllabus_unit_lexemes` removal · **#130**'s
  TASKS reconciliation test · **#120** · **#140** · **#102** · **#169**'s per-target link ·
  **#194**/**#195** · the #197 ruling.

---

## 15. Server steps — written out, none run by this slice

Claude Code has no SSH access to this host and is not to be given any. Every step is a command for
the operator. `/home/bot/english-bot`, `sudo -u bot`, no `ssh bot@<host>`, no `/opt`, no
`english-worker` (#215, #221, #69).

**0. Push and verify before anything else (#223).**
```bash
git push origin main && git log --oneline -1 origin/main
```
Must match local `HEAD`. Every deploy here is a pull from `origin`; without this the pull reports
*already up to date* and exits 0 behind a green sequence.

**0a. Standing precondition — which commit is production running (#222).**
```bash
cd /home/bot/english-bot && sudo -u bot git rev-parse --short HEAD && sudo -u bot git status --porcelain
```
Must equal `origin/main` before step 0's push, and the status must be **empty**. A non-empty status
means somebody has edited files directly on the host: that is a `high` finding and a new issue,
never a tidy-up.

**1. Backup.** `pg_dump` before every migration against production, R2 upload confirmed, size
recorded.

**2–5. Deploy.** pull → `pip install -e packages/core` → migrate → **expect
`Applied: 001–017, Pending: (none)`, pasted verbatim.**

**6. Generate, dry.** `python -m core.lessons.generate` — reads the printed prompt, payload,
candidates, the 174 ceiling, and **`stored lessons below LESSON_VERSION: n of m`** (§4.1).
**Sends nothing.**

**7. The billed run is a human step, in two stages** (§7.1), on the operator's instruction.

**7a — unit 1 alone. Ceiling 60.**
```
python -m core.lessons.generate --live  --units 1     # types 60
python -m core.lessons.generate --apply --units 1     # types 1
```
**Then stop and read it in block 3, on a phone.** This is the gate on 7b — not the axes going
green.

**7b — units 9 and 20. Ceiling 114.** Only after 7a has been read and is good.
```
python -m core.lessons.generate --live  --units 9,20 --skip-control   # types 114
python -m core.lessons.generate --apply --units 9,20 --skip-control   # types 9,20
```
`--skip-control` is dropped and the control re-runs if 7a's control landed at 2 of 3 (§7.1).

Each stage's **full output** — per lesson, per check, the coverage numbers, the diagram counts,
every axis marked MET / NOT MET / NOT EVALUATED, and the control's verdict — is pasted
**verbatim** into the decisions log. W8b's rule: a measurement nobody can re-read has to be
bought twice.

**8. Restart `english-api` only.** `english-bot` is deliberately not restarted; `english-worker`
is not installed and is not named (#69).

**A server action is never an acceptance criterion this slice can satisfy on its own.**

---

## 16. How this is verified end to end

1. `pip install -e packages/core && pytest -q` → **2026 baseline held**, new tests green.
2. `pnpm test` in `apps/web` → **103 baseline held**, new Vitest green.
3. `python -m core.lessons.generate` (dry) → prints the exact requests, the 174 ceiling, the axes
   and the coverage reference. **Sends nothing.**
4. §8's two structural pre-checks are green **before** step 5 is authorised.
5. The billed run (§15 step 7), output pasted verbatim.
6. **The check this slice turns on: the operator reads the three lessons, all three rendered.**
   Unit 1 in block 3; units 9 and 20 at `/lessons/9` and `/lessons/20` in the app — **the page,
   not the JSON.** That is what closes #182 — not a green suite, not a passing gate.

**Why the page exists, and it is send-back 7's whole point.** §10(a) claims the operator's reading
establishes that the lesson *reads as teaching*, that the wrong example is *recognisable*, and
that **the diagram reads on a phone** — the one judgement in this slice he can actually make.
**None of that survives raw JSON.** A diagram spec is a typed object; whether it reads is a
property of the render. Accepting two of three lessons against `GET /lessons/{n}`'s payload would
have claimed three read lessons while two were read in a form that cannot support the claim —
the exact substitution this project keeps catching.

**So the render is not optional and it is cheap:** one Next.js page under the existing
`(app)` route group, fetching the route and passing the payload to `lesson.tsx` and
`diagram.tsx` — the same components block 3 uses, so what he sees at `/lessons/9` is what a
learner would see if they could reach unit 9. **Eight of the twelve targets carry their diagram
judgement only through this page.**

**#160 holds:** no nav entry, no badge, no count, not on the map. Reachable by URL, never owed.
`apps/web/app/(app)/map/page.tsx` is still W9's `ComingLater` placeholder; when W9 builds the map
it links here rather than inventing a second surface.

**The alternative was considered and declined:** accepting units 9 and 20 as structurally
inspected JSON, with the diagram judgement made for unit 1 alone. It is defensible and it is
worse — it discards two thirds of the only instrument the operator has, to save one page file.

---

## 17. BUILD_PROGRESS.md update block

**Slice row: ⬜, not 🟡.** This produces a plan and no code; 🟡 means code-complete. The row is
corrected in place where it is stale: **`schema_version` is 16, not 15** (R5), and the scope is
**units 1, 9 and 20**, not 2/9/20, with the reason and the operator's 2026-08-28 confirmation.

**Decisions, each with its reason:** the scope change and why unit 1 is mandatory; `probe_target`
split into `probe_ranked` + wrapper rather than reimplemented, and why a section cannot go through
`visible_projection`; the coverage gate declined before it was set, with #197's measurement as the
ground; `band`/`confirm` promoted rather than copied; the control moved into unit 1 because the
archive's could not execute; `content_offenders` not `offenders` on lesson prose, and why; the
labels annotated rather than replaced and the first section expanded by default; the global line
and the PRODUCT-PRINCIPLES §2 and §3 positions; the typed-SVG ruling and the image-model option
declined; the target↔section bijection and why the SQL CHECK is deliberately weaker; L6's
prediction and bar being different numbers on purpose; the 017 renumber owed; **and the operator's
inability to verify the English recorded as the constraint that shaped the slice, not as an aside.**

**Plus the seven send-back resolutions, each with its reason** (§0): the diagram floor removed
rather than the rule, and why forcing a diagram was the wrong repair; the byte-exact comparison
**read from `validate_checkpoint:129-148` rather than assumed**, with the measured 24-unit
distribution and the finding that **2 of the 3 permitted section counts are wrong for every unit
and a 5-section lesson is wrong for all 24**, and why the CHECK is still left mirroring the
syllabus at 3–5; the staged billed run and what authorises stage 2 (a lesson read, not a gate
passed); `lesson_version`'s refuse policy, the `bank_for_session` precedent it copies, and the
bump's cost stated; the route's authorisation pinned to `/session/today`'s and evidenced by a
`401`; **the old Vitest assertion for `noLesson` quoted in the log in full before its
replacement**, so a test whose meaning inverted does not read as a deletion in six weeks; and the
`/lessons/[unit]` page, with the JSON-acceptance alternative declined and its reason.

**New issues, with severity and slice:**
- **the diagram constraint excluded a state its own design produces — at BOTH ends, in two
  successive drafts** — `low`, W10b, as a plan defect of #213's family alongside R13. **Three
  occurrences in one plan** (the archive's control, the floor, the ceiling), and the third was
  introduced by the revision that fixed the second. That is the point of §8's pre-checks and it is
  filed as evidence for them, not as three tidy-ups: **reading a contract is not the same as
  running something through it, and fixing one end of a range does not check the other.**
- **§9 and §15 disagreed about the string typed when money is spent** — `low`, W10b, **#223's
  shape one field over.** Fixed by stating the rule and computing the value; filed because the
  fix's generalisation — *a value the operator must type is printed by the thing that will run,
  never transcribed from a document* — belongs with #141, #151, #215, #220 and #223 in the
  deploy-runbook family rather than only in this plan.
- **the SQL CHECK admits the wrong section count 2 times in 3 for every unit** (§6.1) — `low`,
  W10b, filed with its number and with the reason it is not tightened, so the next reader does
  not re-open it;
- the lesson-side limits of §10 — filed as **updates to #194 and #195** where they are the same
  defect, and as new rows only where they are not;
- **the archive's negative control could not have executed** (R13) — `low`, W10b, as a *plan*
  defect of the same family as #213: a check whose contract excludes what it requires;
- **the archive's `≤65` ceiling was the expected case labelled as a ceiling** (R4) — folded into
  the existing cost row rather than filed separately, since W10c already carries the pattern;
- **#185 gains a fourth sighting** (R16), updated in place, not re-filed;
- **the section the block's items are on cannot be opened without leaking `grammar_target`** (§3)
  — filed against **#169**'s family, `low`;
- anything the run surfaces.

**Full file inventory** — §13, every new file with its purpose, and every edited file named.

**Next action carrying every earlier unrun check in full, none silently:**
- **W10 check 4 — DAY TWO.** Head of the list. Blocks W11 (#216). Cannot be run retroactively.
- **Check 0b — grade a card in block 1**, both paths, closes #218. Unrun.
- **Block 3 still renders its practice items after the #222 deploy** — expect the same 14 items.
- **Command 0a** — standing W11 precondition, re-run before W11 is planned.
- **W10's other five** (1, 2, 3, 5, 6), **W10c's six** (1, 4, 5, 6 unrun; 2 and 3 partly evidenced
  on the human's report, not run), **W10a's two**, **W8h's two**, **W8b's two**, **W8f's checks 4
  and 5** — nobody has looked at an imported card on a phone — and **the 21 carried items,
  confirmed at 21 by count and not by impression**, including the typography pick at
  `https://app.foundgrant.com/type`.
- **Plus this slice's, and it is what closes #182: the operator reads the three lessons.**

**#182 closes only when three verified lessons are live and have been read.**
