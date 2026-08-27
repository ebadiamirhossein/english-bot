# W10c — The item generator

**Mode: PLAN.** Billed model calls, content shown to learners. Approved and
implemented 2026-08-27; three changes were made at review and are marked in
§4/Q1, §8 P6 and §12 step 5. Two things in it turned out to be WRONG when
implemented — the #102 comparison and the ≤110 call ceiling — and both are
recorded in BUILD_PROGRESS.md rather than corrected here: this file archives
intent, not state.

---

## Context

PRD §4.1 block 3 is *"this week's grammar target: 90-second explanation + 8
generated items."* W10 shipped block 3 with `lesson: null` and `items: []` and a
line on the screen reading *"Practice for this arrives with the exercise
generator."* W10b is the explanation. **This is the eight items.**

`packages/core/services/sessions.py:1192` `_focus_block` returns the contract
verbatim as the prompt states it:
`{unit_number, can_do, grammar_targets: [{target}], lesson: None, items: []}`.
`apps/web/components/session/blocks.tsx:116` `FocusBlock` renders the can-do, the
target labels, and two apology lines from `copy.ts:66`.

**Verified, not assumed:** `items` is empty on production.
`core/services/items.py:_CURRENT_VALIDATOR`'s own comment records it — *"`items`
is empty on production (#109 closed with `count(*)` at 0 after the W6a purge)"* —
and #109 is marked ✅ closed with the purge's row count. Nothing this slice writes
lands beside older rows.

**The constraint that shapes the slice, recorded as a shaping constraint and not
an aside:** the operator cannot verify the English. Every defect this project has
caught late — the leaked answer (#152), the deploy vocabulary, the `mid`
collision (#180), the double-printed source line (#154) — was caught by a person
looking at a screen. For a generated grammar item that instrument is weaker than
it looks: a *plausible* item testing the wrong point reaches two B1 learners who
cannot tell. So verification is the slice, not a step at its end — **and what his
own reading is and is not for is split three ways in §12 step 5, rather than the
plan claiming the constraint and then leaning on the reading it rules out.**

**But this slice has an advantage W10b does not, and it is used rather than
rebuilt around:** the gates already exist, are shipped, and have been run live.
No second judge is written.

---

## 1. The six re-targeted issues — what is actually wrong, and the correction

The prompt's premise needs one correction, and the correction narrows the work.

All six (**#102, #103, #105, #110, #120, #168**) were re-targeted during W10's
planning onto a slice the decisions log then called **W10a — item generation**.
W10a shipped as the card-face hotfix instead, taking that letter under this
record's own W4a/W5a/W6a/W8a convention. **W10a already repaired five of the six
in prose**: `BUILD_PROGRESS.md:226` and the status cells of **#168, #120, #110,
#105, #102** all now read *"proposed **W10c — item generation** (renamed from
*W10a* by W10a itself…)"*. Six occurrences of the string `W10c — item generation`
exist in the file; zero of `W10a — item generation`.

**What is still wrong, and it is the half a reader actually navigates by:**

| Row | Slice column today | Body carries the W10c note? |
|---|---|---|
| #102 | `W5a → W5b → **W10**` | yes |
| #103 | `W6 → W10` | **no — never corrected** |
| #105 | `W6 → **W10**` | yes |
| #110 | `W6 → W10` | yes |
| #120 | `W5 → W5b → W10` | yes |
| #168 | `W8d → W10` | yes |

So: **all six Slice columns still point at W10 — a slice that has shipped, with
no generator in it — and #103 was missed entirely by W10a's sweep.** A pointer at
a shipped slice that never did the work is worse than no pointer, and one row
that was missed while five were fixed is #100's drift shape a fifth time.

**The correction this slice makes:** all six Slice columns move to `→ W10c`; the
word *proposed* is struck (the slice exists); **#103 gains the W10c note the
other five already carry**; and the **W10a letter collision is named in each**, so
the next reader understands why these rows moved twice and does not read the
second move as churn.

---

## 2. The reused seam — what each existing gate covers for a grammar-targeted
item, and what it does not

Nothing here is rewritten. `core/items/gates.py`, `checks.py`, `naturalness.py`,
`grading.py`, `repair.py`, `projection.py` are used as they stand. **They were
built for vocabulary items and the difference matters**, so it is stated per
gate.

| Gate | Covers, for a grammar item | Does **not** cover |
|---|---|---|
| `checks.deterministic_failures` | shape, length, gap count, option sets, script, bank permutation, coverage floor. `no_target` fires unless `lexeme`/`error_type`/`unit_number` is set. | **Whether the target is the *right* one.** `no_target` is satisfied by `unit_number` alone, so *"this item belongs to unit 1"* passes a check whose name suggests more. |
| `naturalness.jargon_hits` / `textbook_hits` / `uncontracted` | that the sentence sounds spoken and carries no Work jargon off the Work track. Free, runs before any spend. | nothing about grammar. A perfectly natural sentence can demonstrate the wrong tense. |
| `gates.judge_naturalness` | *"would a real person say this to a friend?"* over `checks.judged_sentence` — the **prose**, gap closed, wrong tile corrected (W5c, #115). | same. It is not shown, and never asks about, the target. |
| `gates.probe_acceptable` + `grading.distinct_answers`/`equivalence_key` | **multi-acceptability** — the defect that started the rebuild. A gap that admits `went` and `was going` is caught. Genuinely stronger for grammar than for vocabulary: a grammar gap is exactly where two forms fit. | whether the one acceptable answer is the one the target is about. `I ___ to the shops yesterday` → `went`, unique, correct — and it tests `past simple`, not `time linkers`, whatever the item claims. |
| `repair.LADDER` + `gates.MAX_REPAIRS` | cue-repair of a `slot` item, deterministic, using the probe's own wrong answers as distractors. | `fixed_option` and `message` are not cue-repairable by design — four of the seven permitted types get one probe and no second chance. |
| `projection.visible_projection` | the single learner-visible serialiser; the probe sees exactly what the learner sees. | — (this one carries over unchanged and is the reason the probe means anything). |
| `schema.content_hash` + `UNIQUE (user_id, content_hash)` | near-duplicate suppression **per learner**, on type + folded stem + folded answer. | two *distinct* items testing the identical point in different words — **#169**, which is a checkpoint-set property and stays W11's. |

**Two findings from reading the seam, both filed rather than absorbed:**

1. **`match_pairs` has no model gate at all, and the code that says it does is
   unreachable.** `gates._mapping_matches` and the `mapping_mismatch` verdict live
   inside `_probe_and_repair`, which `validate` only calls when
   `ANSWER_FAMILY[item_type] in PROBED_FAMILIES`. `ANSWER_FAMILY["match_pairs"]`
   is `"exact"` and `PROBED_FAMILIES` is `{slot, message, fixed_option}` — so the
   branch is dead, no test reaches it, and every `match_pairs` item passes
   `validate` on deterministic checks alone. `match_pairs` is one of the seven
   types permitted in **all 24** checkpoints. **New issue, `medium`.** It is
   evidence for #168 before a single call is made: a type whose uniqueness gate is
   structurally absent.

   **This is a family and it is counted as one — sixth appearance.** After
   `assert_path_outside_repo` (W1: green because the test derived its fixture
   from the broken function), `tier → ti` (#177: a docstring true literally and
   false in effect), `sentence_of` handing the judge a gapped stem (#115), the
   `intervals` crash (#190: one contract with two producers), and `JUDGE_BATCH`
   (#120: documented batching that never happens) — **a guarantee that was never
   once evaluated against the thing it names.** The row carries that sentence, so
   the seventh is recognised as the seventh.
2. **`gates.JUDGE_BATCH = 20` is still uncalled** — #120, exactly as filed.
   `validate` calls `judge_naturalness([sentence])`, one at a time.

---

## 3. The gap named honestly, and how it is closed without inventing it twice

**Nothing in the existing seam asks: does this item test the grammar target it
claims?** That is W10b's C1, one level down.

**It is needed here, and it is needed more than in W10b.** A lesson section that
drifts to a neighbouring point is confusing; an *item* that drifts is scored, and
a learner is marked wrong on a point the app never claimed to be testing. Unit 1
carries four targets that share one tense (*past simple*, *past continuous*, *the
two in one sentence*, *time linkers*) and `items.error_type` cannot separate them
— `error_types` has 19 coarse journal codes and all four of unit 1's targets map
to `verb_tense_past`. **There is no field in the tree that names one of the 82
grammar targets.** So without this check, "generated against the unit's own
grammar targets" is a claim with nothing behind it.

### It does not share W10b's check — it ships **first** and W10b shares this one

W10b is approved and **not started**; `core/lessons/gates.py` does not exist.
Writing C1 there and importing it here is impossible today, and waiting is worse.
So the direction reverses:

**`gates.probe_target(content, candidates) -> ranking`** lands in
`core/items/gates.py` — already *the* module in `core.items` that may reach a
model (`tests/test_core_boundary.py::ITEMS_MODEL_CALLERS`), so no boundary
exemption is created and `ITEMS_MODEL_CALLERS` stays a two-member tightening.

- It is **blind and productive, never confirmatory** — W5a's whole lesson. It is
  shown `visible_projection(item)` plus, for a graded item, the canonical answer
  (a learner-visible thing after grading), **with the target name removed**, and a
  candidate list. It **ranks**, best first, the way `item_probe.txt` does. It is
  never asked *"does this test X?"* — a leading question gets a yes.
- **Candidates = the unit's own 3–5 targets + 3 decoys drawn from other units.**
  The decoys that matter are the **siblings**: unit 1's four neighbouring
  past-tense points are the nearest neighbours and are what makes a drift
  catchable at all.
- **Pass: the claimed target ranks first. A sibling ranking second is recorded,
  never failed** — #119's lesson, and it tells the next reader which distinction
  the item blurred.
- New prompt `core/prompts/item_target.txt`. **W10b's C1 becomes the second
  caller of this function, not a second implementation** — written into the
  plan and into W10b's row so it is not invented twice.

**What it cannot do, stated plainly and filed:** it is a model checking a model,
plausibly the same model with correlated blind spots; one sample of a stochastic
system; and a frontier model resolves distinctions a B1 learner will miss, so a
clean pass is weaker evidence about a learner than it looks. Same asymmetry the
record already states for STT and for the blind solver.

---

## 4. The four design questions — proposals, for the operator to rule on

### Q1 · Which item types, and how many of each — and how #168 closes on a number

**Correction to the prompt's premise, from the file:** `checkpoint.item_types`
permits **seven in 14 units, six in eight units, seven-with-`listening_gap` in one
and eight in unit 23**. It is not seven everywhere. **Units 1, 2 and 3 all permit
the identical seven**, which is part of why they are the right scope:

`mcq · cloze_cued · word_bank_order · error_spot · match_pairs · collocation_pick · l1_to_l2_production`

**Proposal: the type per slot is prescribed by the runner, not chosen by the
model.** Eight slots per unit, cycling all seven permitted types plus one repeat
of `cloze_cued` (the only `slot`-family type here, and the only one the repair
ladder can rescue). Left to itself a generator writes three `mcq`s and five
`cloze_cued`s, and four types get zero evidence — which is precisely the evidence
#168 has been waiting three slices for.

**The confound that prescription creates, recorded here where the measurement is
defined and not as a caveat at the end.** A prescribed slot forces a type onto
whichever target the slot lands on, so a low yield measures **either** *this type
is weak* **or** *this type was asked to carry a target it does not suit*.
`collocation_pick` against *time linkers: then, after that, a bit later* is a
plausible item; `collocation_pick` against *past perfect in reported explanations*
probably is not, **and its rejection says nothing about the type.**

**So yield is reported as `type × target`, never as type alone.** The run holds
both fields (`item_type` and the new `grammar_target`), so the cross-tabulation
costs nothing but the table. A type that fails only against targets it was never
suited to is a **different finding** from a type that fails everywhere, and only
the second is an argument for narrowing `item_types`.

**#168's measurement, pre-registered before the run.** Per `type × target` cell,
across 3 units × 8 slots (each type drafted **3 times**, `cloze_cued` 6):

| Recorded | From |
|---|---|
| drafted | the run |
| accepted / repaired / discarded, **with the discarding stage and code** | `ValidationReport` |
| `probe_target` rank of the claimed target, per accepted item | the new gate |
| model calls spent per accepted item | `core/llm.py`'s INFO lines, captured (§7) |

### #168 does **not** close here, and the reason goes in the row

n is **3 per type** (6 for `cloze_cued`), and one cell per `type × target`. A type
that is genuinely bad gets 1 of 3 by luck often enough that no retention bar can
separate it from one that works. **#168 has waited three slices precisely because
nobody had evidence, and replacing *no evidence* with *three draws* and closing
the row is how a number becomes a fact.** No retention bar is written, because a
bar at this n would be a bar that decides on noise.

**So: every per-type and per-cell number is pre-registered and recorded, and #168
stays open with the count and the sample size stated in the row.** It closes on
the 21-unit run, where n reaches 24 per type. The reason is written into the row
so the next reader does not re-derive it: **closing on n=3 would be a claim true
of three draws, written as a claim about the type** — #82's shape, and this record
has counted five appearances of it already.

**One exception, and it is granted on a structural ground rather than a
statistical one:** a type that accepts **0 of 3** *and* carries a structural
finding against it may be recommended for removal now. That is `match_pairs` and
only `match_pairs` — its model gate is provably unreachable (§2), which is the
argument; a 0-of-3 would be corroboration, not the case.

`speak_repeat`, `speak_answer`, `dictation` and `listening_gap` are **not
permitted in units 1–3**, so this run makes **zero TTS and zero STT calls**. Said
explicitly because `_audio_gate` bills two providers.

### Q2 · Scope

**Proposal: three units — 1, 2 and 3 — for one learner. 24 items.**

The argument that gates W10b at three units holds here and is stronger: 24 items
is enough to judge quality per type and small enough that a person reads every
one. Units 1–3 rather than W10b's 2/9/20 because **`current_unit` returns 1 for
both learners and cannot advance** (#188 — `user_unit_state` is empty and W11 owns
every write to it), so unit 1 is the only unit a learner can actually reach.
Units 2 and 3 are generated so the bank is not one unit deep the moment W11 lands,
and so #168's per-type sample is 3 rather than 1.

**One learner, and this is the uncomfortable half.** `items` is per-learner
(`UNIQUE (user_id, content_hash)`), and **#159 is unresolved**: nothing carries a
learner's L1 onto the surfaces that write a gloss. `definition` and `l1_gloss` are
authored per item and `l1_to_l2_production`'s entire prompt is L1. Generating for
both learners today writes **Farsi for the Lithuanian learner**, which is exactly
what #159 predicts of W10.

So: generate for **one learner, `--user` required with no default and the id typed
back** (`seed_fixtures`' guard, and the same reason). The second learner's block 3
keeps its honest empty state until #159 is settled. **The alternative was
considered and is declined in the record**: copying the rows to the second
`user_id` costs nothing and ships a Farsi gloss to a Lithuanian speaker, and a
silently-wrong gloss is #159's stated failure, not a shortcut past it. #159 gains
this as its concrete blocker with the arithmetic.

### Q3 · What an item is bound to

**Proposal: the item binds to the unit *and* to the target — and the target needs
no migration.**

The tree today: `items.unit_number` (the W8 FK), `items.error_type` (FK to 19
coarse journal codes), `items.lexeme_id`. **None of them can name one of the 82
grammar targets**, which is why #169 records that block-3 items link at unit
granularity.

`schema.payload_of` derives `items.payload` by **subtracting** the promoted
columns, and `StoredItem.as_item` rehydrates with `**self.payload`. So adding
`grammar_target: str | None` to `BaseItem` persists it and reads it back **with no
DDL, no key list, and no plumbing** — the exact property `payload_of`'s docstring
was written to give. Consequences:

- **No migration.** `schema_version` stays at 16, and #185's numbering fragility
  is not touched at all. Said explicitly because it is the first thing a reader
  will check.
- `grammar_target` joins `projection.NEVER_VISIBLE`. `visible_projection` is a
  whitelist so it cannot leak, but the constant is what
  `test_items_projection.py` and `test_items_web_contract.py` assert against.
- **Binding to the target by its exact text** is the established convention, not a
  new one: `checkpoint.per_target` is a map keyed by target string and
  `blueprint.validate_checkpoint` already refuses a key that is not one of the
  unit's targets. The same validation is reused on write.
- `unit_number` is still set, so `bank_for_session` (already written, already
  ordered least-recently-attempted-first) needs **no change** and block 3's read
  is one existing function.
- Per-target grouping happens in Python. `#169`'s checkpoint-level uniqueness
  stays W11's and is not attempted here.

### Q4 · The repair path, and the accounting identity

**Proposal: repair where the ladder can, regenerate once at cohort level, never
drop silently, never lower the bar.**

1. **Repair** is `gates.MAX_REPAIRS = 2`, unchanged and untouched — it applies to
   `slot` items only, which is `cloze_cued` here. `fixed_option` and `message`
   items are discarded on the first probe by design.
2. **Regeneration is one top-up round per unit**, asking for exactly the
   shortfall, with the discarded drafts' **failure codes and the probe's own
   `acceptable` list** fed back into the prompt. One round, not a loop: an
   unbounded regenerate is an unbounded bill.
3. **A unit still short after the top-up ships short, and the number is
   reported.** Six good items beat eight with two bad ones. The criterion is *8
   items*; if a unit yields 6, the run prints `6/8` loudly, `--apply` still
   writes the six, and **the shortfall goes in the record as a shortfall** — the
   bar is not moved and no filler is generated (rule 7).

**The accounting identity `--live` prints and `--apply` re-prints, per unit and in
total:**

```
drafted = accepted + discarded + duplicate
accepted = passed + repaired
served   = accepted            (per unit, against a target of 8)
```

with `discarded` broken out by stage (`deterministic` / `mechanical_naturalness` /
`judge` / `probe` / `target`) and by code. A count that does not balance is a
finding printed as one, not a number quietly reconciled.

---

## 5. The two things the seam cannot do, closed here

### #110 · The no-guilt scan reaches generated content for the first time

`tests/support/no_guilt.BANNED` cannot be imported by `packages/core`. Moving it
is the fix, and it **reduces** the copy count #46 tracks rather than adding a
sixth:

- New `packages/core/copy_rules.py` holds the pattern. `tests/support/no_guilt.py`
  becomes a re-export shim, docstring intact. #46 is untouched in scope and
  narrowed by one copy.
- **Two patterns, and the split is the whole design.** `BANNED` (unchanged) is for
  *copy the app says*. `BANNED_IN_CONTENT` is for *English a learner reads* and
  drops the bare words `wrong / incorrect / missed / failed / broke`, keeping the
  second-person verdicts (`you failed`, `you missed it`, `try harder`, `you lost`,
  `should have`, `wrong!`) and the sad-emoji set. **The reason, in one line: a
  sentence a learner practises may contain the word "wrong"; a thing the app says
  about the learner may not.** Without the split the check fires on
  `error_spot`'s own shipped instruction — *"Tap the word that is wrong."* — which
  #110's own text calls fine, and a check that fires on correct content is a check
  someone turns off.
- A test asserts `BANNED_IN_CONTENT ⊆ BANNED`, so the two cannot drift in the
  wrong direction.
- It runs as a **free deterministic check inside `gates.validate`** (new failure
  code `guilt_phrase`), over the generated free-text fields — not only inside this
  runner — so **every item ever generated is covered, not just this run's 24.**
  That is what closes #110 rather than deferring it a sixth time.

### #120 · `JUDGE_BATCH` is called for the first time, and the row is narrowed

`validate`'s cheapest-first order must survive, so the free stages cannot simply
be skipped. **`gates.validate`'s head is extracted, not copied**, into
`gates.free_stages(item, known_lemmas) -> Validated | BaseItem`: the deterministic
pass, `mechanical_naturalness` (which may rewrite for contractions), and the
mandatory second deterministic pass. `validate` calls it and behaves
byte-identically for every existing caller.

The runner then: `free_stages` over all 8 drafts → **one** `judge_naturalness`
call over the survivors' `judged_sentence`s → `validate(survivor, judge=False)`
for the probe. **8 calls become 1 per unit; 24 become 3.** No second orchestration
seam, because the free stages are the same function.

**#120 is narrowed and stays open**, and the honest statement goes in the record:
`validate(judge=True)`'s per-item call is still there for `verify.py` and
`seed_fixtures.py`, which validate one item at a time and cannot batch.

### #103 · The generator prompt asks for an explanation

`core/prompts/item_generate.txt` is **rewritten** and this slice is its first
caller ever — no caller exists in the tree today. It gains: `explanation` on every
item (#103, and W8h's check 2 predicts the empty "Why" panel this fills); the
grammar-target framing; `grammar_target` echoed back verbatim; the no-guilt rule;
and the prescribed `item_type` per slot.

### #102 · offered as an option, not smuggled in

`l1_to_l2_production` is one of the seven and its meaning invariant is reachable
by no gate — `high`, open, targeted here. **Proposal, for the operator to accept
or decline:** a **back-translation check** for this type only. One call: the
stored English answer → L1, compared to the item's own L1 prompt by
`equivalence_key`/`distinct_answers`. ~3 items in this run, so ~3 calls.

**It reduces the risk; it does not remove it** — a back-translation is a third
model reading, not a truth. So **#102 does not close either way**, keeps its `high`
severity (raised once, not re-argued — CLAUDE.md §8), and gains this run's
`l1_to_l2_production` numbers. If the option is declined, that is recorded as a
decision with its reason, not as an omission.

### #105 · corrected to point here, then re-targeted forward, and the two acts are
different

#105's Slice column is corrected to `→ W10c` with the other five, because the
stale pointer is a record defect and must be fixed either way. **Then it is
re-targeted onward with a stated reason**, because that is a decision rather than
a correction: #105 needs a route that reveals `definition` / `l1_gloss` on
request, which the record itself calls *"a second learner-visible serialiser by
another name"* that must be designed against the projection contract. Building it
inside a generation slice is the widening CLAUDE.md §8 forbids.

**What this slice does discharge is its precondition:** until now nothing has ever
produced cue material, so `hint_used` could not have been anything but FALSE
whatever surface existed. After this run, `definition` and `l1_gloss` exist on
every item that has an answer. **#105 becomes buildable for the first time**, and
that is written into the row rather than left implicit.

---

## 6. Constraints held, each named with what holds it

| Constraint | How |
|---|---|
| **No Murphy citation, and none reachable** | The prompt builder is handed `core.sessions.blocks.visible_targets(unit.grammar_targets)` — **the existing #171 seam, reused, not a second one**. It builds `{"target": …}` by naming the one field that may travel, so `murphy_units` is never in the object the builder sees. `tests/test_no_murphy_reaches_a_learner.py` gains an assertion **over the built prompt string** (both fields, one test — the rule W8h set). An item generator importing a session-block helper reads oddly; it is deliberate, and the alternative — a second copy of the same three lines — is how #171's ruling stops holding. |
| **Nothing generated while a learner waits** | `GET /session/today` gains one **read**: `services.items.focus_items(user_id, unit_number)` = existing `bank_for_session` + existing `_present`. `tests/test_session_route.py::test_nothing_is_generated_while_the_learner_waits` stays green **unmodified** — it is armed by session-wide `netguard`, so a generating read raises rather than passes. |
| **`assign_daily` still generates nothing** | The generator stays **human-run**. `tests/test_worker.py::test_assign_daily_is_registered_and_creates_no_content` asserts by AST that the job's body names no `llm`, `speech`, `items` or `video`, and it stays green **unchanged**. Automating generation is a scheduled billed pipeline that writes learner-facing English unattended, on content whose quality this slice is the first to measure — that is its own slice, filed with a target. |
| **CLAUDE.md §5b** | No production entrypoint is run. Every call is inside `--live`, human-typed, on the operator's machine. |
| **No migration** | §4/Q3. `schema_version` stays at 16, no `.sql` file added or edited, #185 untouched. |
| **Licence gate** | Does not fire, and the reason is recorded rather than the gate silently skipped: nothing enters `data/`. Model output goes to the database, which is the case `data/LICENCES.md`'s W8 section already answered. |
| **Boundary tests** | `core/items/generate.py` joins `ITEMS_MODEL_CALLERS` (2 → 3) — the set is a **named list of impure modules**, and naming a third is what it is for. It carries **no SQL**: writes go through `services.items.insert_item`, so `test_no_sql_outside_services` and `test_exactly_one_module_writes_an_item` stay unexempted and #59 remains the only exemption. |

---

## 7. The generator — human-run, dry by default

```bash
python -m core.items.generate --user N                    # dry: prints, sends nothing
```
```bash
python -m core.items.generate --user N --units 1,2,3 --live    # billed, writes nothing
```
```bash
python -m core.items.generate --user N --units 1,2,3 --apply   # billed, writes
```

Modelled on `core.cards.probe_cloze` and `core.syllabus.rewrite_checkpoints`, the
two best-behaved billed scripts in the repo:

- **Dry by default**, and the dry run is the record: it prints the model, **the
  exact system prompt after the Murphy strip**, the exact per-unit user payload,
  `max_tokens`, the prescribed type-per-slot table, the coverage reference, the
  pre-registered predictions, and **the exact billed call count** — and sends
  nothing.
- **`--live` verifies and prints; `--apply` writes.** Separated so the operator
  reads 24 items before a row exists. `--apply` re-runs nothing: it writes what
  `--live` produced in the same process.
- **Typed confirmation**, no `--yes`: the call count for `--live`, the `--user` id
  for `--apply`. A flag that can be pasted out of a runbook is not a decision.
- **`logging.basicConfig(level=INFO)` at entry — #140.** `core/llm.py` logs exact
  per-call token usage on every call and a bare root logger drops all of it
  through `lastResort`; that is how W8's tagger had 138 calls and $6.60
  reconstructed after the fact. **#140 stays open** and still names
  `judge_observe.py` and `verify.py`, which both spend and both still leave the
  root logger bare.
- **`--live` prints its own verdict** against every branch rule below, so the
  reading cannot bend after the number arrives.

**Cost, stated before the run.** Per unit: 1 generation + 1 naturalness batch +
~7 probes (`match_pairs` is unprobed — §2) + up to 4 cue re-probes + ~8
`probe_target` ≈ **21**. ×3 = 63. One top-up round per unit ≈ **+30**. Negative
control **3**. Optional #102 back-translation **~3**. **Ceiling: ≤ 110 billed
calls**, comparable to W5b's 76 and W10b's ≤65. Zero TTS, zero STT. The exact
count is printed by the dry run and the actual count is read back off the INFO
lines.

---

## 8. Pre-registered predictions — written before the run (#57, W5b, W8b)

Written into the module docstring before `--live` is ever executed. **`--live`
evaluates its own branch rules and prints the verdict.** W8b's transferable
finding is carried: *a pre-registered prediction constrains honesty about the axis
it names and says nothing about an axis it does not* — **so each axis gets its own
number.**

| # | Axis | Prediction | Branch rules |
|---|---|---|---|
| **P1** | overall accept rate — the number `docs/TASKS-v3-web.md`'s W10 row asks for and W10 reported as unmeasurable | **12–18 of 24** accepted on the first pass | **≥19** → the gates may be weak at n=24; P5 decides whether the result is believed. **12–18** → expected; top up, record which stage caught what. **≤11** → **the generator prompt is wrong, not the gate.** Fix the prompt, re-run, **do not loosen a gate** (rule 7). |
| **P2** | `probe_target` rejections | **0–3 of 24** fail target-first | **≥7** → the prompt is asking for grammar-flavoured sentences rather than for demonstrations of a named point; rewrite the prompt, not the check. |
| **P3** | `judge_naturalness` rejections | **0–5 of 24** | **≥10** → read them before touching anything. #115 recorded 6/11 on hand-written fixtures and the judge is strict. |
| **P4** | probe outcomes | **3–8 of 24** come back `multi_acceptable` or `not_recoverable` before repair | **≥14** → grammar gaps are structurally more ambiguous than vocabulary gaps and the type mix is the fix, not the gate. |
| **P5** | **negative control** (§9) | the mis-targeted fixture fails `probe_target` in **3 of 3** runs | **Pass bar: 2 of 3.** Below 2 of 3 → **the run is a FAILURE whatever the 24 items did**: `probe_target` does not discriminate, nothing is written, exit non-zero. |
| **P6** | `type × target` yield — **#168's numbers, not #168's closure** | **no type accepts 0 of 3**; `match_pairs` is the most likely to | Every cell recorded; **#168 stays open with n stated** (§4/Q1). A type at 0 of 3 is recommended for removal **only** with a structural finding beside it — `match_pairs`. A type failing everywhere is reported as differing from a type failing only on targets it never suited, and the two are not merged. |

**P5's prediction and P5's bar are different numbers on purpose**, and the gap is
stated once rather than reconciled later. The prediction is what a working check
should do; the bar is what constitutes evidence it discriminates at all. One
stochastic miss on a borderline classification is not the same event as a check
that cannot tell *past simple* from *time linkers*. **2 of 3 prints as
`prediction NOT MET, run acceptable`, in those words**, and both go in the record.

Reasoning is recorded with each so a **wrong** prediction is informative. P1's
band is wide and low-centred because nothing has ever generated an item under the
v3 gates: the only accept-rate datum in existence is 6/11 on **hand-written**
fixtures (#115), and generated items will not be that good. P2 is low because the
generator is *given* the target text verbatim; it is not zero because unit 1's
four sibling targets share one tense and are genuinely close.

---

## 9. The negative controls

**`verify.py`'s lesson, carried: a check that rejects nothing passes the catch
direction perfectly.** Two checks here can be inert, and each gets a control.

1. **`probe_target` — the billed control.** Committed fixture
   `tests/fixtures/items/mistargeted.json`: an item that genuinely tests *used to
   for habits that have stopped* while claiming *for and since with the present
   perfect* — both real unit-3 targets, so the drift is to a sibling and not to
   something absurd. Run through `probe_target` **three times** at the head of
   `--live`. **If the control passes in ≥2 of 3, the whole run is void: nothing is
   written, the module says so, exit non-zero.** It runs *before* the 24 items, so
   a dead check costs three calls rather than a hundred.
2. **`guilt_phrase` — the free control.** A deliberately guilty draft
   (*"You failed that one — try harder."*) must be discarded by `validate` with
   code `guilt_phrase`, and a draft containing `error_spot`'s shipped *"Tap the
   word that is wrong."* must **not** be. Both are unit tests, both directions,
   free — the meta-test shape `no_guilt.offenders` already supports.

---

## 10. Tests

New, and each names the user action it exercises (rule 4):

- `tests/test_items_generate.py` — the runner: the dry run sends nothing (under
  `netguard`, structurally); the accounting identity balances on a seeded set of
  recorded verdicts; a short unit reports `6/8` and does **not** pad; the top-up
  asks for exactly the shortfall; `--apply` refuses when the control voided the
  run.
- `tests/test_items_target_gate.py` — `probe_target` against a recorded response:
  claimed-first passes; sibling-first fails; sibling-second is recorded and
  passes; candidate list = unit targets + 3 decoys, and **the claimed target's
  name is absent from what the model is shown**.
- `tests/test_items_guilt_gate.py` — §9 control 2, both directions, plus
  `BANNED_IN_CONTENT ⊆ BANNED`.
- `tests/test_items_batch_judge.py` — `free_stages` + `validate` compose to the
  same verdicts as `validate` alone on the eleven committed fixtures (the
  refactor is provably behaviour-preserving), and the batch path makes **one**
  judge call for eight sentences.
- `tests/test_no_murphy_reaches_a_learner.py` — **extended, not duplicated**: the
  built generator prompt carries no Murphy citation from either field.
- `tests/test_session_route.py` — block 3 serves items; every item is
  `visible_projection`-shaped and leaks nothing in `NEVER_VISIBLE`; the netguard
  test stays green unmodified.
- `apps/web/components/session/session.test.tsx` — `FocusBlock` renders items and
  no longer renders the `noItems` line; a focus block with zero items renders the
  honest empty state rather than a heading over nothing.

**Baseline to hold and report split: pytest 1861 passed / 6 skipped (1867
collected — verified on this tree), Vitest 96 across 9 files.**

---

## 11. Files

| File | New/changed | Purpose |
|---|---|---|
| `packages/core/items/generate.py` | **new** | The human-run runner. Dry by default, `--live`, `--apply`, typed confirmation, `logging.basicConfig`, predictions and their verdicts. No SQL. |
| `packages/core/items/gates.py` | changed | `probe_target`; `free_stages` extracted from `validate`'s head (behaviour-preserving); optional `probe_backtranslation`. |
| `packages/core/items/checks.py` | changed | `guilt_phrase` failure in `_shared`. |
| `packages/core/items/schema.py` | changed | `grammar_target` on `BaseItem`; persists via `payload_of`, rehydrates via `as_item`. **No migration.** |
| `packages/core/items/projection.py` | changed | `grammar_target` into `NEVER_VISIBLE`. |
| `packages/core/copy_rules.py` | **new** | `BANNED` + `BANNED_IN_CONTENT` + `offenders`, one definition. |
| `tests/support/no_guilt.py` | changed | re-export shim; no sixth copy (#46 narrowed by one). |
| `packages/core/prompts/item_generate.txt` | rewritten | first caller ever; explanation (#103), target framing, prescribed type, no-guilt rule. |
| `packages/core/prompts/item_target.txt` | **new** | `probe_target`'s system prompt. |
| `packages/core/services/items.py` | changed | `focus_items(user_id, unit_number)` = `bank_for_session` + `_present`. |
| `packages/core/services/sessions.py` | changed | `_focus_block` hydrates `items`. |
| `apps/web/components/session/blocks.tsx`, `copy.ts` | changed | `FocusBlock` renders `ItemCard`; `noItems` removed. |
| `tests/fixtures/items/mistargeted.json` | **new** | the negative control. |
| `prompts/CC-W10c-item-generator-PLAN.md` | **new** | this slice's prompt, archived (CLAUDE.md, `prompts/` exception). |

---

## 12. How this is verified end to end

1. `python3 -m pytest -q` → **1861 / 6 skipped**, plus the new tests; report the
   split, do not fold it into one number.
2. `npm test` in `apps/web` → **96 across 9 files**, plus the new focus assertions.
3. `python -m core.items.generate --user N` (dry) — read the exact prompt, confirm
   **no Murphy citation and no target-name leak into `probe_target`'s payload**,
   confirm the printed call count, paste the whole dry run into the decisions log
   **before `--live` is run**.
4. `python -m core.items.generate --user N --units 1,2,3 --live` — the control
   runs first; the module prints its own verdict on P1–P6; **paste the output
   verbatim into the record**.
5. **A person reads all 24 items — and what that reading is for is split three
   ways, because the plan opened by saying he cannot verify the English.** Both
   cannot be true at once. W10b drew the same line for diagrams (*"a timeline that
   reads confusingly on a phone is a visual judgement, not an English one"*); it
   is drawn here.

   **(a) What his reading genuinely establishes — and nothing else can:**
   - the item reads as a question and not as a fragment;
   - the gap sits somewhere sensible and is not `_____s`-shaped (#147);
   - **the Farsi in an `l1_to_l2_production` prompt is correct Persian and reads
     naturally.** He is the only instrument in this project that can check it:
     no gate is shown both sides of that relation (#102), and the probe reads the
     Farsi only to produce English from it;
   - the item is not tedious, and eight in a row feel like practice rather than
     a form.

   **(b) What only the gates establish — he reads the verdicts, not the English:**
   uniqueness (`probe_acceptable` + `distinct_answers`), naturalness
   (`judge_naturalness` over prose), target-first (`probe_target`), no-guilt
   (`guilt_phrase`). A stored `ValidationReport` per item is what he reads here.

   **(c) What neither establishes, said plainly rather than reassigned:**
   whether an item is **correct English teaching a correct point**. That rests on
   `probe_target` — a model checking a model, plausibly the same model with
   correlated blind spots, one sample of a stochastic system (§3). It is not
   quietly handed to a reader who has said he cannot do it, and it is not covered
   by (a) or (b). It is a filed limit with a severity and a slice, and it is the
   strongest reason the scope is 24 items and not 192.
6. `--apply`, then confirm the row count independently in `psql` — a count the
   command prints about its own work is not verification of it.
7. Deploy (backup → pull → `pip install -e packages/core` → **no migrate** →
   restart) written as explicit commands for the human; then block 3 on a phone.

---

## 13. Not this slice — named, not absorbed

Lesson content (W10b) · the checkpoint's 12 items and its set-level uniqueness
(#169, W11) · unit advancement and `user_unit_state` (W11) · video (W12/W13) ·
#186 · anything Telegram · **the remaining 21 units** (gated on these 24 being
read — and the run that closes #168, where n per type reaches 24) · **the second
learner** (gated on #159) · **automating the generator into
`assign_daily`** (filed with a target) · **#105's cue-reveal route** (§5).

---

## 14. BUILD_PROGRESS.md update block

1. **Slice row** `W10c` → 🟡, dated, one line. **Never ✅.**
2. **Decisions log**, each with its *why*: what each reused gate covers and what it
   does not for a grammar-targeted item (§2, as a table, not a sentence); the
   item-type ruling, the `type × target` confound stated where the measurement is
   defined, and **why #168 does not close on n=3**; the scope and its reason,
   including the one-learner ruling and
   #159 as its named blocker; the binding ruling and why it needs no migration;
   the repair/top-up policy and the accounting identity; every prediction with its
   verdict **in the module's own words**; the two negative controls and what a
   void run means; **the operator's inability to verify the English recorded as
   the shaping constraint the slice was built around, not as an aside — together
   with §12 step 5's three-way split, so the record does not both claim the
   constraint and rely on the reading it rules out**.
3. **Known issues.** Closed: **#110**, **#103**. Narrowed and open with the new
   statement: **#120**, **#102**, and **#168 — open, with every per-type and
   per-cell number attached, the sample size stated, and the closure deferred to
   the 21-unit run where n reaches 24**. Re-targeted forward with a reason:
   **#105**. New: the dead `match_pairs` gate (`medium`, filed as the **sixth**
   appearance of *a guarantee never evaluated against the thing it names*);
   `assign_daily` automation (`low`); every §3 limit of `probe_target` filed
   individually with a severity and a slice rather than left as a paragraph.
   **Every still-open issue carried forward.**
   **All six Slice columns corrected to `→ W10c`, the word *proposed* struck,
   #103 given the note it never received, and the W10a letter collision named in
   each so the next reader understands why they moved twice.**
4. **File inventory** — every file in §11, with its purpose, and the deploy state
   stated in the same words as the slice row (#184).
5. **Next action** — this slice's checks **plus every earlier check still unrun,
   reproduced in full**: W10's six (check 4 is the day-two one and cannot be run
   in the same sitting), W10a's two, W8h's two (check 2 becomes runnable for the
   first time — there are now generated items), W8f's 4 and 5, W8c's slang card,
   W8b's two, W7's five, W8's five content checks at their current states, and the
   twenty-one-item carried list. **W8's check 4 is RETIRED and is not carried** —
   struck in place with its reason, never silently dropped.

---

**Stop when the update block is written. Do not start W10b or W11.**
