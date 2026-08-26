# W10b — Grammar lessons: the teaching the syllabus never had

**Archived plan. Intent, not state — `BUILD_PROGRESS.md` is the record of what is
built.**

**Mode: PLAN. APPROVED 2026-08-26. NOT IMPLEMENTED — nothing below exists.**
No code, no migration, no `.sql` file, no `packages/core` change, no frontend
change, no server step. `schema_version` stays at **15**.

**Gated on W10, which has not started.** Implementation begins by reading what
W10 actually shipped — the block-3 contract, whether items carry any grammar-target
association, the session route's serialisation — and reconciling this plan against
it, per §1. **The 017 renumber is owed at implementation time, not now**:
`docs/TASKS-v3-web.md` is deliberately unchanged, because claiming a number for an
unwritten slice is the fragility filed as a known issue in §4.

Three things this plan established outlive it and are filed in the record rather
than left in this file: the **global vs per-learner line** (§3), the **typed-SVG
diagram ruling** with the image-model option declined (§6), and the
**migration-numbering fragility** (§4).

---

## Context

The syllabus carries 24 can-dos and **82 grammar targets**, and nothing teaches
any of them. Unit 2 says *"I can say whether I've done something before, and
when"*, names four targets, and then the learner practises and sits a 12-item
checkpoint on grammar the app never explained. Until 2026-08-26 a Murphy range
stood in for the teaching; W8g ruled that out (#164), because most users own no
copy and a page number is meaningless to them. That is **#182**, filed `high`,
and this slice is it.

Two things found while reading make this smaller and better-founded than it looks:

1. **PRD §4.1 already specifies it.** Block 3 · Focus reads *"This week's grammar
   target: **90-second explanation** + 8 generated items."* The explanation half
   has never been built. So this is a **return to §4.1, not a revision of it** —
   the same shape #160's ruling had, and it means **no PRD amendment is needed**.
2. **W8's check 5 is a positive that sharpens the gap.** The checkpoints
   genuinely test their unit's targets and weight by difficulty. So the
   checkpoint is good at finding out that a learner does not know something, and
   the app has nothing to say next.

**#182's fork is already decided by the prompt**: shape (a), *explanation
generated once and stored* — with one variant recorded, that it is generated
**ahead of the session** rather than on demand, because nothing may be generated
while a learner waits (W10's own criterion).

---

## The constraint that shaped every decision below

**The operator cannot verify the English.** He has said so directly. Every other
slice ended with a person reading the output — the leaked answer (#152), the
deploy vocabulary, the `mid` collision (#180) were all caught by someone looking.
For grammar lessons that instrument does not exist: a wrong explanation of the
present perfect reaches two B1 learners who cannot tell it is wrong, and they
will believe it.

So verification is not a step at the end. It is the slice, and the generator is
built around it. Three consequences run through everything below:

- The generator never sees the answer it will be judged against (§5).
- Every model check is asked to **produce** an answer independently, never to
  **confirm** one — W5a's whole lesson: *"what is your answer?"* proves
  recoverability and can never prove correctness, and a leading question gets a
  yes.
- **One thing the operator CAN verify is the diagram's layout.** A timeline that
  reads confusingly on a phone is a visual judgement, not an English one. That
  asymmetry is why §6 is worth its cost.

---

## 1. Scope — three units, and the dependency that gates the slice

**Three lessons: units 2, 9 and 20** — one each from stages 1, 3 and 5, the same
three W8's check A read on 2026-08-26. The remaining 21 are a separate slice,
gated on these three being read and good.

**W10b cannot be implemented until W10 ships.** W10 is not started; `sessions`
migration 016, `GET /session/today` and the five hydrated blocks do not exist.
Building the lesson before its surface is exactly how 1,560 syllabus lexemes came
to sit in a table nothing reads (#165). The first implementation step is
therefore: **read what W10 actually shipped** — the block contract, whether items
carry any grammar-target association, the session route's serialisation — and
reconcile this plan against it before writing code. The floor this plan assumes
is only that block 3 exists and can hydrate a payload for a unit.

---

## 2. What a lesson is

One lesson **per unit**, not per target (24 lessons, not 82). A lesson has one
**section per grammar target** (3–5, matching `syllabus_units`' own CHECK), which
is what makes §5's per-section checks possible at all.

Each **section** carries:

| Field | What |
|---|---|
| `target` | the grammar target's exact text, from `data/syllabus_units.json` |
| `explanation` | short, plain English at the learner's level |
| `when_to_use` | when you'd reach for it |
| `when_not_to` | and when you wouldn't — the part textbooks skip |
| `examples` | 2–3 real sentences, each demonstrating this target |
| `wrong_example` | one natural-sounding mistake, `corrected`, and `why` in one line |

Each **lesson** carries 1–3 `diagrams` (§6), each attached to exactly one of its
targets, and a link to the unit's practice block.

**A lesson is English only.** No L1 gloss, ever — a gloss is per-learner by
nature (#159), and putting one on a lesson would make the lesson per-learner and
break the line in §3. Per-learner adaptation is named as not-this-slice.

**Keying.** A section binds to a target by the target's **exact text**, which is
already the key the shipped content model uses: `checkpoint.per_target` is a map
keyed by target string and `blueprint.validate_checkpoint` refuses a key that is
not one of the unit's targets. This is the established convention, not a new one.

### Targets and sections are a bijection, and it is enforced in code

**Every one of the unit's targets has exactly one section, and every section
names one of the unit's targets.** Both directions, as a generation failure —
never a warning.

The one-directional version is the trap. Unit 2 has four targets; a lesson with
three sections satisfies `grammar_lessons_sections_three_to_five` (3–5) *and*
`syllabus_units_three_to_five_grammar_targets` (3–5) while the counts disagree.
It would pass C1 on each of its three sections, pass C2, pass C3, and have no
orphan section — and leave *present perfect or past simple: is the time
finished?* untaught. **That target carries 4 of unit 2's 12 checkpoint items**
after W8d's redistribution, so the learner would sit a third of a checkpoint on
grammar the lesson never mentioned. Orphan detection looks the wrong way for
this; the missing direction is the one that hurts.

Enforced in `core/lessons/checks.py`, where the unit's authored targets are in
hand. **The SQL CHECK deliberately cannot express it** — the lesson row does not
know its unit's target count — and the migration comment says so and says why,
rather than leaving a reader to assume the constraint is the guarantee. That is
`blueprint.validate_checkpoint`'s own situation: the blocks-sum invariant lives
in code because 014 could not mirror it (#167).

This is the fifth appearance of **a guarantee whose predicate cannot see the
thing it is about** — #152, #164, #167, #180, and now this — and it is counted
rather than met freshly for the fifth time.

**`murphy_units` is never given to the generator.** #171's worry about W10 —
*"embed the assumption in the item, where being wrong is invisible"* — lands
harder here: a lesson built around Murphy 38 would inherit the unexplained
contradiction #164 records, invisibly. Asserted by a test over the prompt-builder's
output, not left as an intention.

---

## 3. The architectural line: global vs per-learner

**Present perfect is present perfect for every learner.** So:

| Global — generated once, stored once, served to everyone | Per-learner |
|---|---|
| lessons, lesson sections, diagrams | cards, FSRS schedules, L1 glosses |
| the grammar spine (`syllabus_units`) | the ledger (`user_lexemes`), coverage |
| | `user_unit_state`, item attempts |

`grammar_lessons` therefore has **no `user_id` column at all**.

**PRODUCT-PRINCIPLES §2 position, stated as every slice adding a table must:**
this table is not user-keyed, so it neither depends on nor enlarges the identity
established by 011. §2 is satisfied trivially and the record says so rather than
leaving it inferred.

**PRODUCT-PRINCIPLES §3 position:** this is the *cheap* direction of the same
flag #93 and #165 stand on. One row per unit, 24 rows forever, regardless of how
many learners arrive. Nothing here scales per-user × per-anything.

---

## 4. Migration 017 — and the renumbering it forces

`docs/TASKS-v3-web.md`'s authoritative table has 015 applied (W8f), 016 → W10,
017 → W12, 018 → W13a, 019 → W14, 020 → W18. W10b sits **after W10**, so it takes
**017**, and every unwritten slice below shifts by one:

| # | was | becomes |
|---|---|---|
| 017 | W12 | **W10b** |
| 018 | W13a | W12 |
| 019 | W14 | W13a |
| 020 | W18 | W14 |
| 021 | — | W18 |

This is **W4b's documented procedure, not #49**. W12/W13a/W14/W18 have nothing on
disk, nothing applied, no `schema_version` row moved — renumbering a row in a
planning table is bookkeeping. Taking a number above everything claimed (say 021)
would work on production and break replay on a fresh database, for the reason the
table already records. **Both halves are corrected in the same commit**, and both
must be, because #130 is still open: nothing checks that the per-slice Build
columns agree with the authoritative table. Adding that test is #130's, targeted
W19 — named here, not absorbed.

**And the third renumber gets filed as a pattern, `low`, with no target slice.**
W4b renumbered, W8f renumbered five rows, W10b renumbers four. Three occurrences
is not coincidence: **the planning table assigns migration numbers to slices that
have not been written, and unplanned slices are how this project actually
proceeds.** Every such slice shifts every unwritten number below it, and every
shift touches two documents that nothing reconciles. The alternative is recorded
for whoever picks it up — **a migration number is assigned when the file is
written, not when the slice is planned**, leaving the table to record what was
taken rather than to reserve what might be — and so is the consequence that
adopting it would make **#130's test easier rather than harder**, because there
would be nothing unwritten left to disagree about. The renumber itself stands;
this files the fragility that keeps producing it.

```sql
CREATE TABLE grammar_lessons (
    unit_number    SMALLINT PRIMARY KEY
                       REFERENCES syllabus_units(unit_number) ON DELETE RESTRICT,
    sections       JSONB NOT NULL,       -- one per grammar target
    diagrams       JSONB NOT NULL,       -- 1..3 typed specs (§6)
    verification   JSONB NOT NULL,       -- how it passed; mirrors items.validation
    lesson_version SMALLINT NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- DELIBERATELY WEAKER THAN THE CODE CHECK, and the gap is named rather
    -- than left to be discovered. The real rule is a BIJECTION: one section per
    -- grammar target, both directions. This row cannot express it -- it does
    -- not know its unit's target count, and 3-5 here can be satisfied while
    -- 3-5 there is satisfied by a different number. `core.lessons.checks`
    -- enforces the bijection where the unit's targets are in hand. Same
    -- situation as the blocks-sum invariant living in
    -- `blueprint.validate_checkpoint` because 014 could not mirror it (#167).
    CONSTRAINT grammar_lessons_sections_three_to_five
        CHECK (jsonb_typeof(sections) = 'array'
               AND jsonb_array_length(sections) BETWEEN 3 AND 5),
    CONSTRAINT grammar_lessons_one_to_three_diagrams
        CHECK (jsonb_typeof(diagrams) = 'array'
               AND jsonb_array_length(diagrams) BETWEEN 1 AND 3),
    -- "A lesson that fails verification is regenerated, never shipped with a
    -- warning", made unforgeable rather than promised.
    CONSTRAINT grammar_lessons_only_verified_rows_exist
        CHECK ((verification ->> 'verdict') = 'passed')
);
```

**Diagrams are a JSONB column, not a child table**, and the reason is a
correctness one: a lesson that fails verification is regenerated **whole**,
because §5's contradiction check spans prose and diagram together. A separate
table makes it possible for a diagram row to survive a regeneration and contradict
the new prose — which is precisely the failure the check exists to catch.

No `ALTER TABLE users`, so #48 does not fire — stated rather than omitted, since
#48 has recurred by each case looking like the exception.

`lesson_version` mirrors `VALIDATOR_VERSION`'s role exactly: bumped whenever a
check tightens, so the 21-unit slice can tell which rows were verified under which
rules. Retrofitting it is impossible. Starts at **1**.

---

## 5. Verification — the slice

Reuses `core.items.gates`, `core.items.naturalness`, `core.lexicon.coverage` and
`tests/support/no_guilt` rather than writing a second judge. Cheapest first,
exactly as `gates.validate` orders its stages: **every free check runs before any
call costs money.**

### 5a. What the existing seam can check, unchanged

| Reused | On what | Cost |
|---|---|---|
| `naturalness.jargon_hits` / `textbook_hits` / `uncontracted` | every example sentence | free |
| `lexicon.compute_coverage` | explanation prose | free |
| `no_guilt.offenders` | every generated string | free |
| `gates.judge_naturalness` | the example sentences, **as one batch** | 1 call |

**The naturalness judge sees the examples and never the explanation.** Its prompt
asks *"would a real person say this to a friend?"* — a correct answer for an
example sentence and a meaningless one for a paragraph of teaching. Handing it the
explanation would be #115's mistake with the polarity flipped: the right gate over
the wrong string. This is W5c's finding applied rather than rediscovered.

**Track for the jargon rule.** Units 18–21 are `work`; every other unit is `life`.
Not a `topic` field on `syllabus_units` — #161 ruled that out — but a constant in
the lesson module, and the mapping is quoted from #161's own reading: *"the only
units with a real topic are 18–21 — work, price and terms, email, collocations."*
Unit 20's lesson is a Work lesson and would otherwise be rejected for its own
subject matter.

**Level.** `compute_coverage(explanation, reference)` where `reference` is
`{lemma : freq_rank ≤ 2000} ∪ {lemma : cefr ∈ A1/A2/B1}` read from
`normalize.lexeme_rows()` — pure, no database, and deliberately **not a learner's
ledger**, because the lesson is global. **Gate: ≥ 95%**, fixed here with its
reason before any number exists, and never lowered afterwards (CLAUDE.md §3 rule
7). The observed score for each of the three lessons goes in the record so the
21-unit slice can tighten it on evidence rather than on feel.

### 5b. What the existing seam cannot check, and the three new checks

`gates.py` answers *"is this item ambiguous?"* and *"does this sound like a
person?"*. It has no question about whether prose teaches what it claims. Three
checks are genuinely new. All three live in `core/lessons/gates.py` — **the only
module in `core.lessons` that imports `core.llm`**, mirroring `core.items`'
structure and the boundary test that holds it.

**C1 · It teaches the target it claims.** A blind classifier. It sees one
section's explanation, when/when-not, examples and diagram-as-text with **the
target name removed**, and a candidate list of the unit's own 3–5 targets plus 3
decoys from other units. It ranks, best first, the way `item_probe.txt` does.

*Pass: the claimed target ranks first.* The decoys that matter are the **sibling
targets of the same unit** — the nearest neighbours — which is what makes this
catch a drift to an adjacent point. A section on *must and can't for what you're
fairly sure of* that has slid into obligation ranks a sibling first and fails. A
sibling ranking second is **recorded, not failed** — that diagnostic is #119's
lesson, and it tells the next reader which distinction the prose blurred.

**C2 · Every example actually shows the structure.** Per example, **one call, not
batched** — and for exactly `probe_acceptable`'s reason: this asks the model to
recover an answer, so a neighbouring sentence from the same section would leak it.
The judge receives **the sentence alone** — no label, no target name, no section
around it — and names which target from the candidate list it demonstrates. *Pass:
the section's own target ranks first.* This is W5c's rule stated as a bar: the
judge must receive the thing itself, never the claim about it.

No deterministic grammar detector is written. Eighty-two hand-written structure
matchers would be a second grammar engine, and one that is wrong is worse than
none. Said plainly rather than implied by an absent check.

**C3 · It contradicts nothing.** One call over the whole lesson — every section's
prose, every example, the wrong example and its correction, and each diagram
rendered to text. It is asked to **list contradictions, not to rate the lesson**;
*pass: the list is empty*, and a non-empty list is stored so the regeneration is
informed rather than blind.

### 5c. The negative control — the half that makes the rest mean anything

`verify.py`'s central lesson, carried: **a gate that rejects nothing passes the
catch direction perfectly.** So `--live` runs a committed fixture,
`tests/fixtures/lessons/drifted.json` — a section claiming *must and can't for
what you're fairly sure of* and written entirely about obligation, the operator's
own example — through C1, three times. **If the control passes C1, the run is a
failure regardless of what the three real lessons did**, and the module says so
and exits non-zero. Nothing is written.

### 5d. Failure is regeneration, with a cap

A lesson failing any check is regenerated whole, with the failing check's
diagnostics fed back into the prompt. **Cap: 2 regenerations**, the same number as
`gates.MAX_REPAIRS` and for the same reason. A lesson still failing after two is
**reported as unshippable and the run stops** — never shipped with a warning,
never with a bar adjusted (rule 7). The `grammar_lessons_only_verified_rows_exist`
CHECK makes that unforgeable rather than merely intended.

### 5e. What verification cannot do — recorded plainly, not as an aside

1. **It is a model checking a model** — plausibly the same model, with correlated
   blind spots. A wrong-but-fluent explanation of a fine distinction can pass C1,
   C2 and C3 together. This is **not equivalent to a human reading it**, and no
   number of checks makes it so.
2. **One sample per check of a stochastic system.** A fail is decisive; a pass is
   not proof. `verify.py`'s caveat, carried verbatim in the module docstring.
3. **Nothing checks that the lesson is useful.** A section can teach its target,
   contradict nothing, sit at 97% coverage, and still not help anybody.
4. **Nothing checks the diagram reads** (§6).
5. **A frontier model resolves distinctions a B1 learner will miss**, so a clean
   C1 is weaker evidence about a learner than it looks — the same asymmetry the
   record already states for STT and for the blind solver.

Each becomes a known issue with a severity and a slice, rather than a paragraph
nobody can act on.

---

## 6. Diagrams — typed data, rendered by us

**Ruled 2026-08-26: the model emits a typed spec through the existing `core.llm`
wrapper; `apps/web` renders it as SVG.** No image model, no second provider SDK,
no new environment variable, no amendment to CLAUDE.md §2. The alternative was
raised once and declined for three reasons: a raster diagram cannot be checked
without rasterisation plus a vision call; an image model is a wrapper this
codebase does not have; and the licence answer would have to be established from
scratch for image output.

**A closed set of five kinds**, chosen to cover all twelve targets in units 2, 9
and 20:

| kind | shows | fits |
|---|---|---|
| `timeline` | a line, one `now`, ordered points/spans | present perfect vs past simple, future forms |
| `contrast_pair` | one situation, two forms, one line on what changes | will vs going to, formal vs informal |
| `form_build` | labelled slots — `subject + have/has + past participle` | the form of a tense |
| `decision_tree` | a question, 2–3 branches, each to a form | *is the time finished?* |
| `annotated_example` | one sentence with callouts on its parts | unit 20's writing targets |

**The schema has no colour field, no font field and no coordinates.** The renderer
owns all of it. "No red in the lesson UI" is therefore structural — the model
cannot choose a colour — and the `.tsx` scan covers the renderer with the same
banned list `test_no_red_reaches_the_correction_screen` already uses.

### What is checked, and what is not

**Deterministic, free, real:**
- the kind is one of five; required parts present; counts in range;
- **every label appears in the section's own prose** (a diagram naming a form the
  lesson never mentions is a diagram inventing content);
- per-kind ordering invariants — a `timeline`'s points are monotonic and exactly
  one is marked `now`; a `decision_tree`'s branches are exhaustive and distinct;
- banned phrases; the target named exists in the unit.

**By model, at no extra cost:** the spec renders to a textual description that is
included in C1's section payload and in C3's whole-lesson payload. So a diagram
that teaches a different point, or contradicts the prose beside it, fails the same
two checks the prose does.

**Not checked, and this is the honest part: whether the picture reads.** No check
touches legibility, clarity, or whether a timeline helps a B1 learner on a phone.
**The instrument for that is the operator's eyes, and unlike the English, this is
a check he can actually run.** It is the reason a diagram earns its cost here
rather than being deferred.

**Fewer rather than false.** If a target admits no fitting kind, no diagram is
produced for it and the generator **reports the count**. The floor is one diagram
per lesson; the prediction is ~2. A lesson that ends with zero diagrams is
reported as a number, not smoothed over by forcing a timeline onto *"email
openings and closings"*.

---

## 7. The generator — human-run, dry by default

`python -m core.lessons.generate [--units 2,9,20] [--live] [--apply]`

Modelled directly on `core.cards.probe_cloze`, which is the best-behaved billed
script in the repo:

- **Dry by default.** Reaches the database, prints the exact system prompt, the
  exact per-unit payload, the model, `max_tokens`, the pre-registered predictions,
  the coverage reference size, and **the exact billed call count** — and sends
  nothing.
- **`--live` asks first**, and the confirmation is *typed* (`type 3 to continue`),
  the shape `rewrite_checkpoints` uses.
- **`logging.basicConfig(level=INFO)` at entry — #140.** `core/llm.py` logs exact
  per-call token usage at INFO on every call, and a script that leaves the root
  logger bare drops every line through `lastResort`. That is how W8's tagger had
  138 calls and $6.60 reconstructed after the fact against a $1–2 estimate. This
  module does not repeat it. **#140 stays open** and still names `judge_observe`
  and `verify`.
- **`--live` verifies and prints; `--apply` writes.** Separating them means the
  operator can read three lessons before a row exists.
- **No SQL in this module** — it goes through `core.services.lessons`, so
  `test_no_sql_outside_services` stays unexempted and #59 remains the only
  exemption.

**Cost, stated before the run:** ~15 billed calls per lesson (1 generation + 4 C1
+ ~8 C2 + 1 naturalness batch + 1 C3), ×3 = 45, plus 3 for the negative control,
plus a 15-call allowance for one regeneration. **≤ 65 calls.** Comparable to
W5b's 76.

The naturalness batch of ~8 sentences is the **first caller to actually use
`JUDGE_BATCH`** — every existing call site passes a list of one. It does **not**
close #120, which is about `gates.validate`'s per-item call; it demonstrates the
path works.

---

## 8. Pre-registered predictions — written before the run (#57, W5b)

Written into the module docstring before `--live` is ever executed, and **`--live`
evaluates its own branch rules and prints the verdict**, so the reading cannot
bend after the number arrives. W8b's transferable finding is carried with them:
*a pre-registered prediction constrains honesty about the axis it names and says
nothing about an axis it does not* — so each axis gets its own number.

| # | Prediction | Branch rules |
|---|---|---|
| **P1** | **0–1 of 3** lessons fail verification on the first pass | **0** → the checks may be too weak at n=3; P4 is what decides whether the result is believed. **1** → expected; regenerate, record which check caught it. **2–3** → the generator prompt is wrong, not the gate (rule 7). Fix the prompt, re-run, do not loosen a check. |
| **P2** | **0–3 of ~24** example sentences fail C2 | **≥ 6** → the prompt is asking for examples rather than for demonstrations; rewrite the prompt. |
| **P3** | **0–1 of ~6** diagrams fail the deterministic label/order checks | **≥ 3** → the diagram schema is under-specified; tighten the schema, not the check. |
| **P4** | **the drifted control fails C1 in all 3 of 3 runs** | **Pass bar: 2 of 3.** Fails in **< 2 of 3 → the run is a FAILURE**, whatever the three lessons did: C1 does not discriminate and nothing is written. See the note below — the prediction and the bar are deliberately different numbers. |
| **P5** | **0–4 of ~24** examples rejected by `judge_naturalness` | **≥ 10** → read them before touching anything; #115 recorded 6/11 on items and the judge is strict. |
| **P6** | explanation coverage lands **95–99%** against the B1 reference | below the 95% gate → regenerate, report the number, do not move the gate. |

**P4's prediction and P4's pass bar are different numbers on purpose, and the
gap is stated once here rather than silently reconciled.** The prediction is
**3 of 3**; the bar is **2 of 3**. They answer different questions: the
prediction is what I expect a working C1 to do, and the bar is what constitutes
evidence that C1 discriminates at all. Demanding 3 of 3 from a single sample of
three would be its own error — one stochastic miss on a borderline classification
is not the same event as a gate that cannot tell obligation from deduction.

So **2 of 3 is recorded as `prediction NOT MET, run acceptable`**, with that
reason, and `--live` prints exactly those words rather than picking whichever
reading is more comfortable. This is W8b's finding applied in advance: a
pre-registered prediction constrains honesty about the axis it names, and the
axis P4 names (*does C1 discriminate?*) is not the axis its number describes
(*how reliably?*). Both go in the record.

Reasoning is recorded with each so a **wrong** prediction is informative. P1 is
low because prose is a far easier target than a gapped stem and the generator sees
the full target text; it is not zero because C1's sibling decoys within one unit
are genuinely close and a false rejection there is the most likely single failure.

---

## 9. Licence gate — run before any code, as W4's, W7's, W8's and W8c's were

`data/LICENCES.md` gains a W10b section. The gate is **run first and its verbatim
quote goes in the decisions log**; PRODUCT-PRINCIPLES §3 requires the answer to
hold for a commercial product, not only a private one, and *"it's fine"* is the
shape of an answer nobody can re-check.

The typed-SVG ruling means the artefact is **model text output**, so the question
is the one W8 already answered for the syllabus topic column — *Anthropic's terms
assign output to the customer* — but **the current terms must be re-read and the
clause quoted verbatim, not carried over as a summary.** The reasoning must be
recorded twice over:

- what the model produces is a **JSON diagram spec**, not an image;
- the **rendered SVG is our own code's output** from that spec, and the renderer
  and its five kinds are original work in this repository;
- **no third-party image, font or illustration enters the repo.** The seven faces
  already in the app are OFL 1.1 and unchanged from W8c.

**If the terms do not hold, the slice reports it and stops** rather than shipping
the lessons.

---

## 10. The surface — a block, never a duty

**#160 governs it**: the lesson is part of the daily session and never a separate
obligation with a counter. Concretely:

- **No new bottom-nav item, no badge, no count anywhere.**
  `test_today_still_offers_one_button` must keep passing untouched.
- The lesson renders **inside block 3**, before that block's 8 generated items,
  and links to them at **unit granularity** (ruled 2026-08-26 — no new column on
  `items`; the per-target link is filed as a known issue against #169's family
  rather than absorbed here).
- It is **re-readable without a counter** from the unit on the map — reachable,
  never owed. A lesson read yesterday shows no badge today.
- **Never present a backlog** (CLAUDE.md §4): three unread lessons do not
  accumulate anywhere.

`GET /lessons/{unit_number}` in `apps/api/routers/lessons.py` — a **plain `def`**
(standing rule 6), parsing, authorising, calling one service function,
serialising. No business logic.

---

## 11. Tests

Every test names the user action it exercises (rule 4), and no test derives its
expected value from the function under test (rule 5).

**Python**
- `tests/test_migration_017.py` — the four CHECKs compared against
  `core.lessons`' constants, the way `test_migration_014` does for `UNIT_STATES`.
- `tests/test_lessons_schema.py` — the pydantic shapes; **the diagram schema has
  no colour, font or coordinate field** (asserted, because that is what makes "no
  red" structural).
- `tests/test_lessons_checks.py` — every deterministic check, both directions,
  with hand-authored good and bad fixtures. **Including the bijection in both
  directions**: a four-target unit with a three-section lesson is refused (the
  case the SQL CHECK cannot see), and a section naming a target the unit does not
  have is refused. The four-target fixture is unit 2's real target list, so the
  test is about the content that actually ships.
- `tests/test_lessons_gates.py` — C1/C2/C3 with the model seam monkeypatched at
  `_chat`, driven **in both directions**, including the drifted control. The
  fail-open trap `NaturalnessVerdict` documents is asserted against for each new
  verdict type.
- `tests/test_lessons_service.py` — insert, re-run writes nothing, orphan-section
  detection, `lesson_version` filtering.
- `tests/test_lessons_route.py` — **through the ASGI transport**, not a direct
  service call (rule 1).
- **`murphy_units` never reaches the generator** — asserted over the
  prompt-builder's output.
- **#171's owed constraint**: no surface renders `grammar_targets[].murphy_units`.
  If W10 already shipped this test, it is **extended** to cover the lesson route
  and renderer — not copied into a second version.
- **No-guilt over generated content**: `no_guilt.offenders` run over the stored
  lesson fixture. This closes the **lesson half** of #110; #110 stays open for
  item content.
- Boundary: `core.lessons` imports no web framework; `core/lessons/gates.py` is
  the only module in the package importing `core.llm`.

**Vitest** — the lesson renderer and each of the five diagram kinds; the banned
colour list (`line-through`, `text-destructive`, `bg-destructive`, `text-red`,
`bg-red`, `border-red`, `❌`); the wrong example is visually subordinate to the
correct one, never the headline.

**Baseline to hold:** 1762 passed / 6 skipped / 0 failing; Vitest 74 across 7
files.

---

## 12. Not this slice — named, not absorbed

The other 21 units · **#183**'s four live Murphy surfaces (they need a ruling, not
a fix) · per-learner adaptation of a lesson · audio for lessons · the checkpoint's
own content · #165's `syllabus_unit_lexemes` removal · #130's TASKS-table
reconciliation test · #120 · #140.

---

## 13. Files

| File | Purpose |
|---|---|
| `migrations/017_lessons.sql` | `grammar_lessons` |
| `packages/core/lessons/__init__.py` | `LESSON_VERSION`, `DIAGRAM_KINDS`, `WORK_UNITS`, `COVERAGE_FLOOR`, `SCOPE_UNITS`, `MAX_REGENERATIONS` |
| `packages/core/lessons/schema.py` | pydantic: `Lesson`, `Section`, `Example`, the five diagram specs |
| `packages/core/lessons/checks.py` | every deterministic check. Pure. |
| `packages/core/lessons/gates.py` | C1, C2, C3. The only module importing `core.llm`. |
| `packages/core/lessons/generate.py` | human-run CLI, dry by default, `--live`, `--apply` |
| `packages/core/services/lessons.py` | every query against `grammar_lessons` |
| `packages/core/prompts/lesson_generate.txt` | the generator |
| `packages/core/prompts/lesson_on_target.txt` | C1 |
| `packages/core/prompts/lesson_structure.txt` | C2 |
| `packages/core/prompts/lesson_contradiction.txt` | C3 |
| `tests/fixtures/lessons/drifted.json` | the negative control |
| `apps/api/routers/lessons.py` | `GET /lessons/{unit_number}`, plain `def` |
| `apps/web/components/lessons/lesson.tsx` | the lesson block |
| `apps/web/components/lessons/diagram.tsx` | the five kinds as SVG |
| `data/LICENCES.md` | + the W10b section |
| `docs/TASKS-v3-web.md` | 017 → W10b; W12/W13a/W14/W18 shift by one, **both halves** |

---

## 14. How this is verified end to end

1. `pip install -e packages/core && pytest -q` → baseline held, new tests green.
2. `pnpm test` in `apps/web` → Vitest green.
3. `python -m core.lessons.generate` (dry) → prints the exact requests, the typed
   call count, the predictions and the coverage reference. **Sends nothing.**
4. **The billed run is a human step**, on the operator's instruction, and its full
   output — per-lesson, per-check, the coverage numbers, every prediction marked
   MET or NOT MET, and the control's verdict — is pasted **verbatim** into the
   decisions log. W8b's rule: a measurement nobody can re-read has to be bought
   twice.
5. Server steps are written as **explicit commands for the human**: backup → pull
   → `pip install -e packages/core` → migrate → `core.lessons.generate --apply` →
   restart `english-api` only. `english-bot` is deliberately not restarted.
6. **The check this slice turns on: the operator reads the three lessons.** That
   is what closes #182 — not a green suite, not a passing gate.

---

## 15. BUILD_PROGRESS.md update block

Slice row **🟡**, never ✅. Decisions log: the lesson shape and why; the
global-vs-per-learner line; the image licence answer quoted verbatim; the typed-SVG
ruling and the image-model option declined with its reason; what verification
checks and what it cannot; the target↔section bijection and why the SQL CHECK is
deliberately weaker; P4's prediction and pass bar being different numbers on
purpose; the three-unit scope and its reason; the migration renumbering; **and
the operator's inability to verify the English recorded as the constraint that
shaped the slice, not as an aside.** Known issues for each of §5e's five limits,
**for the migration-numbering fragility (`low`, no target)**, and for anything the
run surfaces. Full file inventory. Next
action carrying **every** earlier unrun check reproduced in full — the W8f phone
checks, W8c's slang card, W8b's two, the twenty-one still-unrun items, the
typography pick — plus this slice's: **the operator reads the three lessons.**

**#182 closes only when three verified lessons are live and have been read.**
