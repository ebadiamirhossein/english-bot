# W11 — Checkpoints + weekly rhythm. PLAN.

**APPROVED 2026-08-29**, with three binding conditions, all applied below.
**REVISION 4** = revision 3 plus those three.

## The three approval conditions, applied

**1. The retake's selector quotas — the one real design correction in this
round, and it was in the plan from revision 1.** §3.1(b) demanded the selector
fill the blueprint's 4/3/3/2 while §4.2 re-weights a **retake** toward the missed
targets. Both cannot hold: a 6/3/2/1 retake cohort cannot fill a 4/3/3/2
selector, so `checkpoint_items` refuses and **the retake never opens** — the fail
path, which is half of what W11 promises.
**Fixed by giving the quota map one producer with two callers**:
`checkpoint_slot_plan(unit, permitted, missed)` is pure and deterministic, the
generator calls it to build the cohort and the selector calls it to know what to
select, so the two cannot disagree. First sitting → `missed_targets` is empty →
the blueprint's map. Retake → the re-weighted map. **Twelve and 80% on both
paths** (rule 7); what changes is which targets the twelve are spread across.
A cohort that cannot fill its own plan is **refused whole**, never partially
served. Tests **17 and 18**, both RED — 17 against a selector that fills
`per_target`, 18 against one that takes any twelve.

**2. §12(a)'s slice row carried the withdrawn seam phrasing.** It said *one
service function, `record_checkpoint`, which calls `may_move` / `may_enter`* —
the version §5.1 corrected in revision 2, and the correction was load-bearing
because it decides which function each guard test exercises. The row now says
what §5.1 says: **one module, two functions**, `record_unit_entry` → `may_enter`,
`record_checkpoint` → `may_move`, no no-row branch. **#167's reason is recorded
as living in 018's header**, not only the decisions log.

**3. Two stale cross-references**, both from renumbers: test 9's body said *7a's
index* (now **test 8**), and §12(e) said the pacing tests were *§10 25–30* (now
**32–37**). Both fixed, and the whole list was re-parsed rather than hand-patched
— **38 tests, 20 RED**, since condition 1 added two.

*(Revision 3 answered two blocking send-backs and six corrections; revision 2
answered seven and eight. Both summaries are kept below, because some of their
answers are what later revisions had to withdraw.)*

---

## What changed in revision 3

**A — the reserve identified the wrong twelve.** Revision 2's
`created_at DESC LIMIT 12` is a **proxy** for the checkpoint cohort, and §3.2a's
own arithmetic breaks it: 8 + 12 = 20 means two runs, so a top-up after the
checkpoint makes the newest twelve *eight top-up items plus four checkpoint
ones*. It protects the wrong rows **silently**.
**Now: the cohort is DECLARED** — `cohort` as a field on `BaseItem`, persisted
into `items.payload` by `payload_of`'s subtraction, exactly as `grammar_target`
was at W10c. **No DDL, no ordering constraint, no proxy.** The ordering sentence
the send-back offered is deliberately **not** adopted: with a declared cohort it
is unnecessary, and an unnecessary constraint is one more thing to get wrong.
**The test the send-back specified is written as test 14 and is the one that
discriminates the two mechanisms** — red against recency, green against the
declared cohort.

**B — nothing said what creates the checkpoint's `sessions` row, and the attempt
key rests on it. THE ANSWER COSTS A MIGRATION, AND §8's POSITIVE FINDING IS
WITHDRAWN.** `GET /checkpoint/today` creates it with `INSERT … ON CONFLICT DO
NOTHING`, mirroring `_get_or_create_daily` — **but that statement's idempotency
is an INDEX, and 016's is partial `WHERE task_type = 'daily'`.** A refetch would
have created two sittings, both claiming cleanly, bumping `checkpoint_attempts`
twice and moving `retake_due_on` twice.
**W11 takes 018** — one partial unique index,
`sessions_one_checkpoint_per_user_per_date`. `schema_version` 17 → 18. **W12
019, W13a 020, W14 021, W18 022**, both halves of `docs/TASKS-v3-web.md`, same
commit. **#185's fifth occurrence, taken honestly.** Two consolations: 018 gives
**#167** the migration header its row asked for, and the mode change to `PLAN` is
what caught this — its third stated reason was *it may need DDL*, and it did.

**Where revision 2 went wrong is worth one line, because it is a shape:** it
checked that `sessions.task_type` has no CHECK to widen — true, #47 does not fire
— and read that as *no DDL*. **"Nothing forbids the value" and "nothing forbids
two rows" are different questions**, and only the first was asked.

C1–C6 applied: the guard tests are **1 and 2** in every section; **36 tests,
18 RED, numbered 1–36 with no gaps**, the #169 and #194 tests numbered rather
than named beside a count; §13a's 7b writes **`in_progress`** and records the
**one sanctioned bypass** of `may_enter` with the three conditions that make it
one; §13a's 7a says it is unscoped by unit and **correct only because no learner
has left unit 1** (V6, V7); the thin-block-3 residual becomes **H5b**; and #251
targets **the generator slice**, not an issue number.

---

## What changed in revision 2 *(kept for the record)*

**Nothing was written, edited, generated or run against a database or a model in
producing this. No file in the repository was touched.** Every number below is
either read from the tree or read from `BUILD_PROGRESS.md` and labelled as such.

## What changed in revision 2 — SUPERSEDED WHERE REVISION 3 SAYS SO

Each send-back is answered where the defect was, not in a summary. The seven:

| # | was | now |
|---|---|---|
| 1 | the checkpoint's reserve was **filed** as an issue, so Saturday would have refused every week by construction | solved in §3.2a — **but by a recency proxy, which revision 3 replaced with a declared cohort.** The arithmetic it forced out (8 + 12 = 20, two runs) stands and is what broke the proxy |
| 2 | #107 sat in a carried-forward line while W11 decided not to write to `errors` | **re-targeted W11 → W16** with the reason, in §4.2 and the decisions log |
| 3 | §5.1 said "the only writer", §5.2 gave a second one; `record_checkpoint` called `may_enter` on a branch that never runs | **two writers named**, each calling **its own** guard; `record_checkpoint`'s no-row branch **removed** and made a loud raise; **two RED tests**, one per guard. §5.2 answers where the entry write hangs and why it is not the read-path write §6.1 rejects |
| 4 | test 5 asserted idempotency against a **row** key | **an attempt key**: the checkpoint's `sessions` row, claimed with `WHERE completed = FALSE`. ~~No DDL.~~ **Revision 3: the row it claims needs 018's index to exist once** |
| 5 | #169's cohort call was "on the ceiling" in §10 and absent from the ceiling function | **added as a term**, with the top-up re-pass covered by the ×2 |
| 6 | the backfill was not addressed anywhere | **§6.1a** takes a position — backfill `entered_at` from the earliest daily session — and **§13a** is the three-command human-run step |
| 7 | four departures from the settled deploy sequence | **all four restored and evidenced**: `--ff-only`, `migrate` not `status`, #231's three-way status rule, and the host question **settled by reading** — `api.foundgrant.com`, because `app.` has no rewrite, no middleware, and is not served by Caddy. Filed as **#247** without an inference about what anyone typed |

The eight corrections are applied in place: #217/#219 marked **answered, closing
on verification** rather than closed; tests **renumbered 1–30 with no gaps and
the total reported**; the seven issues **numbered 246–252** and carried
identically into §14; the W11b row **checked against
`test_record_consistency.py`'s actual fixtures**; §12(b)'s claim about that
test's reach **read rather than asserted**; the generator's CLI flags **verified
against `generate.py:1766-1800`** — which turned up **#246**, that `--live` then
`--apply` bills twice and writes different items; the second learner's dead
Saturday **filed as #251 at `high`**; and block 3's key set **checked** — nothing
pins it.

**One thing the send-back's list did not ask for and this revision adds:** §3.3's
`--live`/`--apply` finding changes §13's billed sequence from *`--live` then
`--apply`* to *dry run then `--apply`*. It is called out here because it is a
change to a runbook step that was not among the seven.

---

## Context — why this slice exists and what it is actually for

Two learners are on unit 1 and cannot leave it. `user_unit_state` is empty on
production, nothing in the tree writes to it, and `core.services.syllabus
.current_unit` selects on `passed_at IS NOT NULL` — so it returns 1 for both
learners and keeps returning 1. Two shipped surfaces are frozen behind that:
block 4 shows the same writing task every morning (#188, confirmed on a screen
2026-08-28) and block 3 hands over the whole unit's teaching on day one (#245).
Both are the daily session showing a **weekly** artefact on a **daily** surface,
and both wait on one missing clock.

W11 is the slice that writes the first `user_unit_state` row. What it delivers
is the Saturday checkpoint (12 items, 80%, ceremony on pass, silent re-queue on
fail, retake in 4 days), the state write that unfreezes blocks 3 and 4, and the
**paced** block 3 that ruling of 2026-08-29 asks for. **The Sunday weekly report
is W11b**, split out by operator ruling on the same day and given a row of its
own so it is scheduled rather than deferred — but §7 still runs here, because
*what can a week of this system's data honestly say?* is answerable today and
answering it late is how a slice discovers at implementation time that half of
what it promised needs W12–W16.

What W11 must not do is invent the six things the operator has not ruled on
(§9).

**The finding that shapes everything below: the checkpoint has no items.**
Production holds 14 items in total, 4 of them in unit 1, all for one learner,
and they are the same four items block 3 has served that learner every day since
2026-08-27. A checkpoint drawn from them measures whether he remembers four
exercises. So the largest single piece of W11 is not the state machine and not
the surface — it is **an item supply for the checkpoint that does not exist
today**, and that is costed in §3.

---

# §1. VERIFICATION RESULTS — every item, including the ones that agreed

## V1 — the entry rule and the transition table (#217, #219)

**Read:** `packages/core/syllabus/states.py`, `migrations/014_syllabus.sql`.

### `may_enter` — the record is CORRECT

```python
def may_enter(incoming: str) -> bool:
    validate(incoming)
    return incoming == "available"
```

`states.py:94-102`. It admits **`available` and nothing else**, on the stated
reason that *"the `entered_at` of a row that skipped `available` would be a fact
about a moment that never happened, and W19's history reads these timestamps."*

### `ALLOWED_TRANSITIONS` — full contents, verbatim (`states.py:53-70`)

| from | may move to |
|---|---|
| `available` | `available`, `in_progress` |
| `in_progress` | `in_progress`, `passed` |
| `passed` | `passed`, `mastered` |
| `mastered` | `mastered` |

`UNIT_STATES = ("available", "in_progress", "passed", "mastered")`.
`LOCKED = "locked"` is deliberately **not** storable — it is the absence of a
row, and `validate()` raises a dedicated message for it.
`COMPLETED_STATES = SCORED_STATES = {"passed", "mastered"}`.

`passed → in_progress` is forbidden outright, with the reason written in the
module: *"a failed retake after a pass is not a demotion, because §3's failure
path applies to a unit that was never passed"*, and un-passing would make
`passed_at` meaningless.

### 014's five CHECK constraints — exact text

Three are on `syllabus_units`:

1. `syllabus_units_stage_matches_unit` —
   `CHECK (stage = ((unit_number - 1) / 4) + 1)`
2. `syllabus_units_three_to_five_grammar_targets` —
   `CHECK (jsonb_typeof(grammar_targets) = 'array' AND jsonb_array_length(grammar_targets) BETWEEN 3 AND 5)`
3. `syllabus_units_checkpoint_is_twelve_at_eighty` —
   `CHECK ((checkpoint ->> 'item_count')::INT = 12 AND (checkpoint ->> 'pass_pct')::INT = 80)`

Three are on `user_unit_state` (so the file carries **six** named CHECK
constraints plus the inline `state IN (...)`, not five — reported as read):

4. `user_unit_state_a_pass_needs_the_threshold` —
   `CHECK (state NOT IN ('passed','mastered') OR (passed_at IS NOT NULL AND last_checkpoint_score IS NOT NULL AND last_checkpoint_score >= 80))`
5. `user_unit_state_mastery_needs_a_pass_and_three_weeks` —
   `CHECK (state <> 'mastered' OR (passed_at IS NOT NULL AND mastered_at IS NOT NULL AND mastered_at >= passed_at + INTERVAL '21 days'))`
6. `user_unit_state_timestamps_match_the_state` —
   `CHECK ((mastered_at IS NULL OR state = 'mastered') AND (passed_at IS NULL OR state IN ('passed','mastered')))`

Plus the inline column CHECK `state IN ('available','in_progress','passed','mastered')`
(constraint name `user_unit_state_state_check`, which `tests/test_migration_014.py:178`
compares against `UNIT_STATES`), `checkpoint_attempts >= 0`, and
`last_checkpoint_score IS NULL OR BETWEEN 0 AND 100`.

**Does any of them constrain a row relative to its predecessor?**
**No. Not one.** Every CHECK above is a row-local predicate. A SQL `CHECK`
cannot see the previous version of the row — expressing a transition constraint
in Postgres requires a trigger, which nothing in this project uses. **This is
the load-bearing fact for §5:** the two layers cannot be reconciled by moving
the rule into SQL, because SQL as this project uses it is structurally incapable
of holding it.

Concretely, 014 permits both things `ALLOWED_TRANSITIONS` forbids:
- a **first** row in any of the four states (including `passed`, if
  `passed_at` and `last_checkpoint_score >= 80` are supplied);
- an `UPDATE` from `passed` to `in_progress` that nulls `passed_at` — every
  CHECK is satisfied by the resulting row.

### The grep — the record is CORRECT

```
grep -rn "syllabus.states|may_enter|may_move|ALLOWED_TRANSITIONS|UNIT_STATES" \
     packages apps scripts --include="*.py"
```

**Nothing under `packages/` or `apps/` imports `core.syllabus.states`.** The
only hits outside the module itself are a prose mention in
`packages/core/services/syllabus.py:415` and two test files:
`tests/test_syllabus_states.py` (the full import) and
`tests/test_migration_014.py:30` (`UNIT_STATES` alone). #219 stands exactly as
filed.

**Verdict: the record is correct on both halves of V1. Nothing is corrected in
this slice on V1's account.**

## V2 — `user_unit_state`'s real columns, from 014

| column | type | null | constraints |
|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | PRIMARY KEY |
| `user_id` | `BIGINT` | NOT NULL | `REFERENCES users(id) ON DELETE CASCADE` |
| `unit_number` | `SMALLINT` | NOT NULL | `REFERENCES syllabus_units(unit_number) ON DELETE RESTRICT` |
| `state` | `TEXT` | NOT NULL | `IN ('available','in_progress','passed','mastered')` |
| `entered_at` | `TIMESTAMPTZ` | NOT NULL | `DEFAULT NOW()` |
| `passed_at` | `TIMESTAMPTZ` | **NULL** | tied to state by constraint 6 |
| `mastered_at` | `TIMESTAMPTZ` | **NULL** | tied to state by constraints 5 and 6 |
| `checkpoint_attempts` | `SMALLINT` | NOT NULL | `DEFAULT 0`, `>= 0` |
| `last_checkpoint_score` | `SMALLINT` | **NULL** | `NULL OR BETWEEN 0 AND 100` |
| `retake_due_on` | `DATE` | **NULL** | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `DEFAULT NOW()` |

Plus `UNIQUE (user_id, unit_number)` — the idempotency key for every writer —
and `CREATE INDEX idx_user_unit_state_user ON user_unit_state (user_id, unit_number)`.

**PRODUCT-PRINCIPLES §2 position, stated as §2 requires:** `user_unit_state
.user_id` **references `users(id)`** — the surrogate identity migration 011
established. It adds no new dependency on a Telegram id. This is confirmed in
014's own header and asserted by
`tests/test_migration_014.py::test_user_unit_state_is_keyed_on_the_internal_id`.
W11 adds no user-keyed table and no user-keyed column (see §8), so its §2
position is: **it writes to a table that already keys on `users(id)` and
introduces no new keying at all.**

**Can any column hold a position within a unit? No.** There is no `day_index`,
no `section_index`, no `started_on`. The nearest thing is `entered_at`, which is
a timestamp for *when the row was created* — and under ruling 2 no row is ever
created before a pass, so today it would be created *at* the pass and carry no
information about the days before it. §6 turns on exactly this.

## V3 — what actually selects checkpoint items today

**Nothing does.**

Every reader of `checkpoint.per_target` in the tree:

| site | what it does |
|---|---|
| `core/syllabus/blueprint.py:201-255` | **validates** the map: keys must be the unit's own targets, counts ≥ 1, no target ignored, `sum(per_target) + lexeme_items == 12` |
| `core/syllabus/rewrite_checkpoints.py:68,88,183` | an operator reporting/rewriting tool over `data/syllabus_units.json` |
| `core/items/gates.py:511` | a *comment* referring to the validator's rule |
| `core/lessons/checks.py:120`, `core/lessons/schema.py:79` | comments — the lesson gate reuses the target-string convention |
| `tests/test_syllabus_content.py`, `test_lessons_keys.py`, `test_lessons_containment.py` | assertions about the data |

Every reader of `checkpoint.item_types`:

| site | what it does |
|---|---|
| `core/items/generate.py:1296-1305` | asserts every type in `SLOT_TYPES` is **permitted** by the unit, and raises if not. It does **not** read the list to choose anything. |
| `core/syllabus/blueprint.py:257-267` | validates the list against `core.items.ITEM_TYPES`, refuses duplicates |
| `tests/test_items_generate.py:145`, `test_syllabus_content.py:266` | assertions |

**So: nothing in this tree selects or generates items to a blueprint. Every
reader validates the blueprint's shape or reports on it.** The blueprint has
been a specification with no consumer since W8.

### Unit 1's allocation, verbatim from `data/syllabus_units.json`

```json
"checkpoint": {
  "item_count": 12,
  "pass_pct": 80,
  "per_target": {
    "past simple: regular and irregular verbs": 4,
    "past continuous for what was going on around it": 3,
    "past simple and past continuous in the same sentence": 3,
    "time linkers: then, after that, a bit later": 2
  },
  "lexeme_items": 0,
  "item_types": [
    "mcq", "cloze_cued", "word_bank_order", "error_spot",
    "match_pairs", "collocation_pick", "l1_to_l2_production"
  ]
}
```

Note the third key: `past simple and past continuous in the same sentence`
carries `"contains": ["past simple: regular and irregular verbs", "past
continuous for what was going on around it"]` in `grammar_targets` — the #237
ruling's declared containment — and it takes **3 of 12** items. That is #228's
open exposure, unchanged.

## V4 — the generator's slot plan

**The record is correct.** `core/items/generate.py`:

- `SLOT_TYPES` (`:231-240`) is **eight slots over five types**:
  `cloze_cued, word_bank_order, error_spot, match_pairs, l1_to_l2_production,
  cloze_cued, word_bank_order, error_spot`. `mcq` and `collocation_pick` are in
  `DROPPED_FOR_GRAMMAR` on the #207 ruling.
- `ITEMS_PER_UNIT = 8` (`:201`), sourced from PRD §4.1 block 3, **not** from the
  checkpoint's 12.
- `slot_plan()` (`:346-368`) assigns the target **by rotation offset by the unit
  number**: `targets[(index + unit_number) % len(targets)]`. Deterministic, not
  shuffled.
- `unit_plan()` (`:1290-1312`) reads `checkpoint.item_types` only to *refuse* a
  type the unit does not permit. It never reads `per_target`.

**Said plainly, as §1 asks: the existing generator cannot produce a checkpoint.**
It produces eight items in a fixed type sequence with targets spread evenly by
rotation; a checkpoint needs twelve items in the blueprint's per-target
proportions (4/3/3/2 for unit 1). Nothing in the tree bridges the two. §3 says
what does.

## V5 — what a "review queue" is, in code

**Block 1 is FSRS due cards and nothing else.** `core/services/sessions.py
:1143-1172` (`_review_block`): one call to `cards_service.due_queue(user_id,
now=now, limit=REVIEW_BLOCK_LIMIT)`, projected through `cards_service.card_face`.
Empty queue → state `empty`. There is no other input to block 1.

**Card types** (`core/cards/__init__.py:30`, mirrored into 013's CHECK):
`recognition`, `production`, `cloze`, `audio`, `collocation`. Three of the five
still have no writer, as 013 said they would.

**Is any card created from an `errors` row today, by any path? No.** There is
exactly one `INSERT INTO cards` in the tree — `core/services/cards.py:265` — and
it is fed by the chunk migration and by capture. Every reader of `errors` is a
`SELECT` (`services/errors.py`, `services/lexicon.py`, `services/stats.py`,
`apps/bot/services/couple.py`). **Nothing converts an error into a card, and no
"error card" exists as a thing this system can make.** PRD §4.1 block 1 names
"error cards"; they are unbuilt.

**`error_types` — the code list and the count.** Nineteen, seeded in
`migrations/001_init_postgres.sql:190-209`:

`article_missing`, `article_wrong`, `plural_countable`, `verb_tense_past`,
`present_perfect`, `conditional`, `modal_verb`, `gerund_vs_infinitive`,
`preposition`, `word_order`, `quantifier_modifier`, `subject_verb_agreement`,
`phrasal_verb`, `collocation`, `false_friend`, `register_formality`,
`pronunciation_vowel`, `pronunciation_stress`, `filler_overuse`.

**Do all four of unit 1's grammar targets map onto a single `error_types.code`?**
**Confirmed in substance, and the record's phrasing is sharpened rather than
contradicted — the sharpening makes the point stronger.**

- `past simple: regular and irregular verbs` → `verb_tense_past`
- `past continuous for what was going on around it` → `verb_tense_past`
- `past simple and past continuous in the same sentence` → `verb_tense_past`
- `time linkers: then, after that, a bit later` → **no code in the set fits.**
  There is no linker, discourse-marker or cohesion code among the nineteen.

So three of four collapse onto one code and the fourth has **no code at all**. A
re-queue keyed on `error_types.code` cannot say which target was missed, and for
one of unit 1's four targets it cannot say anything.

**AND A HARDER FINDING THE RECORD DOES NOT CARRY: `items.error_type` IS NULL ON
EVERY GENERATED ITEM.** `error_type` was added to
`core.items.schema.NOT_THE_GENERATORS` on 2026-08-27 (`schema.py:329`), because a
confirming call returned `error_type: "tense confusion"` on seven of eight
drafts — reasonable English, not one of the nineteen codes — which would raise a
`ForeignKeyViolation` inside `insert_item` after a whole run had been paid for.
`_draft_to_item` therefore never sets it, `insert_item` writes `item.error_type`
(None) into the column, and **all 14 production items carry `error_type IS
NULL`.** Corroborated locally: `w10c-journal.jsonl` has `error_type: null` on
every one of its 14 accepted rows.

What an item **does** carry is `grammar_target` — the target string verbatim, in
`items.payload` via `payload_of`'s subtraction (`schema.py:88-112`), set by
`_draft_to_item` from the slot. **That is the only handle in the system that can
name one of the 82 targets**, and §4 is built on it rather than on
`error_types`.

## V6 — the unfreeze path

`core/services/syllabus.py:392-438`, `current_unit(conn, user_id)`:

```sql
SELECT min(u.unit_number)
  FROM syllabus_units u
 WHERE NOT EXISTS (
         SELECT 1 FROM user_unit_state s
          WHERE s.user_id = %s
            AND s.unit_number = u.unit_number
            AND s.passed_at IS NOT NULL
       )
```

Defaults to 1 when there are no rows; returns `UNIT_COUNT` when every unit is
passed. **It selects on `passed_at IS NOT NULL` and never reads `state`.**

`unit_for_session(conn, unit_number)` (`:441-470`) is a plain read of the
`syllabus_units` row by number, returning `StoredUnit`. It is unconditioned on
any learner state.

**Confirmed: writing one row with `passed_at` set is sufficient to advance a
learner, with no change to W10's code.** `_current_unit_row` in
`services/sessions.py:1446` calls `current_unit` then `unit_for_session`, and
blocks 3 and 4 both consume the result. Ruling 2's cost is genuinely zero here.

## V7 — existing writers of `user_unit_state`

```
grep -rn "user_unit_state" packages apps scripts tests migrations
```

**Production paths: zero INSERTs and zero UPDATEs.** Every hit under `packages/`
and `apps/` is a comment or a `SELECT`:

- `services/syllabus.py:425` — the `SELECT` above
- `services/sessions.py:1260`, `:1397`, `items/generate.py:205`,
  `apps/web/components/session/blocks.tsx:213` — comments saying W11 owns it

**Test fixtures only, two of them**, both `INSERT`s written to exercise 014's
constraints rather than a code path:

- `tests/test_syllabus_service.py:279` — one insert, testing `ON DELETE RESTRICT`
  on `unit_number`
- `tests/test_syllabus_states.py:149` — the file's "database half", the 8 tests
  #219 correctly identifies as real enforcement evidence

**Confirmed: W11 is the first writer.**

## V8 — the migration table

`docs/TASKS-v3-web.md`'s authoritative table runs:
`009 W2 · 010 W4 · 011 W4b · 012 W5 · 013 W7 · 014 W8 · 015 W8f · 016 W10 ·
017 W10b · 018 W12 · 019 W13a · 020 W14 · 021 W18`. **There is no W11 row**, in
either half — the per-slice W11 Build column says so explicitly and gives the
policy: *"it claims no number, and if it needs DDL it takes the next one free at
the time its file is written."*

On disk, `migrations/` holds `001`–`017` and nothing above. **The lowest number
with no file is `018`, and `018` is *reserved* for W12.** So "unclaimed" has two
readings and they differ: unclaimed-on-disk is 018; unclaimed-in-the-table is
022. The renumbering rule (`TASKS-v3-web.md:123-146`) requires the on-disk
reading — taking 022 would work on production (`db.py`'s pending set is a set
difference) and break replay on a fresh database (ascending numeric order).

**§8 answers whether W11 needs a number at all. It does not.**

---

# §2. What W11 is — the settled frame, restated and not re-argued

Recorded here only so the plan can be checked against it, not to reopen anything.

- Saturday 12-item checkpoint, 80% to pass (**10 of 12**), ceremony on pass,
  silent re-queue on fail, retake in 4 days, no punishment copy. A failed
  checkpoint leaves the unit `in_progress` (PRD §3).
- **Saturday and Sunday only.** Mon–Fri deferred, not dropped. No PRD amendment
  is owed; §4.2 is unchanged.
- Sunday: no tasks, weekly report, free extensive input tracked and never
  required. **A Sunday that acquires a task is a defect.** *(Ruling 3 stands
  unchanged; the operator's split ruling of 2026-08-29 moves its DELIVERY to
  W11b and moves nothing else. No PRD amendment is owed — §4.2 is unchanged and
  still describes the target, exactly as ruling 3 recorded for Mon–Fri.)*
- Excluded from Saturday: couple challenge (Telegram, dies W22) and
  watch-together (W27).
- **W11 writes `passed` only, never `available`** (ruling 2).
- Checkpoints stay pure grammar. `lexeme_items` is 0 in all 24 units; #170 is
  W13's.
- Containment is read from `GrammarTarget.contains`, never re-derived from
  wording.
- Generation is human-run and never unattended, independent of #69.

---

# §3. THE ITEM SUPPLY — costed before anything that consumes it is designed

## 3.0 What exists, restated from the record

- **14 items total, ids 7–20, user 3 only.** Confirmed on the host by a read
  independent of the command that wrote them: unit 1: 4 · unit 2: 3 · unit 3: 7.
- **By type** (host census, 2026-08-28): `cloze_cued` 3 · `error_spot` 4 ·
  `match_pairs` 3 · `word_bank_order` 4 · `l1_to_l2_production` **0**.
- The second learner has **zero** items in every unit (#159 consumer 3 open).
- Unit 1's four items are what block 3 has served that learner every day since
  2026-08-27.
- W10c's yield: **24 slots attempted, 14 accepted, 3 of those slots structurally
  unpassable (#213)**. **No accept rate is derived from that run and none is
  derived here.** Its billed ceiling was **135** calls for 24 slots.

**One discrepancy found while verifying and reported rather than smoothed
over.** The committed `w10c-journal.jsonl`, reduced by the module's own
last-write-per-`(unit, slot)` rule, gives **14 accepted with a type census that
matches production exactly** (`word_bank_order` 4 · `match_pairs` 3 ·
`cloze_cued` 3 · `error_spot` 4) **but a per-unit split of 4 / 5 / 5**, against
production's confirmed 4 / 3 / 7. The applied rows were written across six
`--live` attempts with `ON CONFLICT (user_id, content_hash) DO NOTHING`, and a
second journal (`w10c-journal-attempt6.jsonl`) is also committed, so the
on-disk journal is not a faithful ledger of what production holds. **Consequence
for this plan: the *targets* unit 1's four live items were written against
cannot be established from the repository.** It is one free read-only query and
it is human check H1 in §11.

## 3.1 Where a checkpoint's 12 items come from — the answer

**They come from `items`, the same table and the same per-learner population
block 3 draws from, and today that population cannot supply them.** There is no
second bank, no checkpoint table, and creating one would be a new user-keyed
table for rows that are already user-keyed.

So the supply answer has three parts:

**(a) A new blueprint-driven generation mode, in the existing generator.**
Add `--checkpoint` to `python -m core.items.generate`, which replaces
`slot_plan()` with `checkpoint_slot_plan(unit, permitted)`:

```
checkpoint_slot_plan(unit, permitted) -> tuple[Slot, ...]
  # 12 slots, not 8.
  # Target per slot comes from checkpoint.per_target's counts, expanded in the
  # file's target order:   4x T1, 3x T2, 3x T3, 2x T4  for unit 1.
  # Type per slot is the permitted set, rotated across slots, offset by
  # unit_number — the same determinism slot_plan() already has and for the same
  # reason (a shuffled plan makes the run unrepeatable).
  # `permitted` defaults to SLOT_TYPES ∩ checkpoint.item_types and is a
  # PARAMETER, so #207's second half can set it without a code change (§3.5).
```

Everything downstream is reused unchanged: `build_payload`, `verify_cohort`, the
gate ladder, `probe_target`, the journal, `--report`, the negative control, the
top-up round, `services.items.insert_item`. **No new gate, no second generator,
no new prompt.** This is the smallest change that makes the blueprint a
specification something reads, which is what V3 found it has never been.

**(b) A selector that draws the 12 from the bank at delivery time.**
`core.services.items.checkpoint_items(user_id, unit_number)`, modelled exactly
on `bank_for_session` (the `_CURRENT_VALIDATOR` filter, unit scoping, one place
for the rule).

**THE QUOTAS IT FILLS ARE THE COHORT'S OWN, NOT THE BLUEPRINT'S — and revision 3
had this wrong in a way that would have killed the fail path.** This section said
the selector buckets by `grammar_target` to fill `per_target`'s **4/3/3/2
exactly**, while §4.2 says a **retake's** twelve are **re-weighted toward the
missed targets**. Both cannot hold: a retake cohort of 6/3/2/1 cannot fill a
selector demanding 4/3/3/2, so `checkpoint_items` refuses and **the retake never
opens** — and the retake is half of what W11 promises.

**The fix is that the quota map has ONE producer, called by both sides.**
`checkpoint_slot_plan(unit, permitted, missed)` is pure and deterministic, so the
selector calls the same function the generator called and cannot disagree with
it:

| | `missed` | quota map |
|---|---|---|
| first sitting | `missed_targets(...)` returns empty | the blueprint's `per_target` — 4/3/3/2 for unit 1 |
| retake | the targets failed in the last sitting | the re-weighted map, still summing to 12, still covering every target at least once |

**Reused rather than copied, and that is the whole point** — the same move
`core.items.generate` makes by importing `visible_targets` from the session
blocks rather than writing a second three-line strip. A quota map stored on the
item, or recomputed with a second expression here, is two hand-maintained copies
of one rule.

**The count stays twelve and the pass mark stays 80% on both paths** (rule 7).
What changes between a sitting and a retake is *which targets the twelve are
spread across*, never how many there are or what passes.

**A cohort that does not match its own plan is refused, not partially served.**
If the rows on disk cannot fill the map the plan produces — a cohort generated
before the last sitting, a run that came up short — `checkpoint_items` returns
nothing and the surface says not-ready. That is the same refusal as (c), reached
by a different route, and it is what stops a stale cohort being served as if it
were this week's.

The read:

```sql
SELECT ... FROM items
 WHERE user_id = %s AND unit_number = %s
   AND validator_version = %s
   AND payload ->> 'cohort' = 'checkpoint'
   AND NOT EXISTS (SELECT 1 FROM item_attempts a
                    WHERE a.item_id = items.id AND a.user_id = items.user_id)
 ORDER BY ...
```

— that is, **checkpoint-cohort items this learner has never attempted**,
bucketed by `payload->>'grammar_target'` and filled against **the quota map
`checkpoint_slot_plan` returns for this sitting**: the blueprint's `per_target`
when `missed_targets` is empty, the re-weighted map when it is not.

*(This paragraph read "**bucketed by `payload->>'grammar_target'` to fill
`per_target`'s 4/3/3/2 exactly**" until the approval conditions of 2026-08-29.
Quoted rather than deleted because it is the sentence that would have killed the
retake — a 6/3/2/1 retake cohort cannot fill a 4/3/3/2 demand, so
`checkpoint_items` would have refused and the fail path would never have
opened.)*

**(c) A refusal, when (b) cannot fill the map.** `checkpoint_items` returns
either **12 items in the proportions this sitting's own plan asks for** — the
blueprint's for a first sitting, the re-weighted map for a retake — or
**nothing**, and the surface renders "this week's checkpoint isn't ready" rather
than a short one. **The 12 and the 80% do not move on either path** (CLAUDE.md §3
rule 7); what differs between a sitting and a retake is which targets the twelve
are spread across. The number short is reported to the operator by the same
command that generates, never padded and never silently reduced.

*(This paragraph read "**either 12 items in the blueprint's proportions or
nothing**" until the approval conditions of 2026-08-29 — the same defect as (b)'s
quoted sentence, one clause on: a retake cohort is not in blueprint proportions,
so the refusal would have fired every time.)*

## 3.2 Same population as block 3? — yes, and the separation is by attempt

**Checkpoint items and block-3 items are the same population.** Both are
`items` rows for that learner and unit past the validator-version filter. There
is no column that could separate them today and this plan does not add one.

**What prevents a learner being tested on an item they have already answered:**
the `NOT EXISTS (item_attempts)` clause in (b). That is a real guarantee and it
is checkable — `item_attempts` is written by `record_attempt` on every block-3
answer, and by nothing else that could produce a false negative.

### 3.2a THE RESERVE — solved here, because filing it would ship a Saturday that never opens

**The contradiction, stated before the fix.** `focus_items` orders by
least-recently-attempted **nulls first** (`services/items.py:383-386`), so the
twelve freshly generated checkpoint items are exactly the ones block 3 reaches
for. Block 3 serves 8 a day. Generate on Friday, sit on Saturday: one Friday
session takes 8 of the 12, `checkpoint_items` finds 4, and §3.1(c) refuses.
**Not once — every week, by construction.** A Saturday surface that renders
*not ready* forever is indistinguishable from not shipping it, and filing that
against the slice that created it does not make Saturday work.

### Revision 2's answer was a recency proxy and it breaks. Recorded, because the failure is the argument for what replaces it

Revision 2 withheld *the newest `CHECKPOINT_ITEM_COUNT` unattempted items*, via
`ORDER BY created_at DESC LIMIT 12`. **That is a proxy for "the checkpoint
cohort", and it holds only while the checkpoint run is the most recent
generation for the unit — which this section's own arithmetic guarantees it is
not.** A unit needs 8 + 12 = 20, so there are two runs; run the checkpoint first
and the block-3 top-up second and the newest twelve are **eight top-up items
plus four of the checkpoint's twelve**. The reserve then withholds items block 3
was generated for and hands block 3 eight of the checkpoint's, which
`checkpoint_items` finds attempted on Saturday.

**It does not fail loudly. It silently protects the wrong rows**, which is worse
than the problem it was written for. An ordering constraint — *the checkpoint run
is always last* — would patch it, but it is a scheduling rule on a human-run
command with no mechanism behind it, and the reserve would be one out-of-order
evening away from being wrong again with nothing to say so.

### THE MECHANISM: the cohort is DECLARED on the item, in `items.payload`, with no DDL

`cohort: Literal["focus", "checkpoint"] | None = None` becomes a field on
`BaseItem`, set by `_draft_to_item` from the run's mode.

**This is `grammar_target`'s exact precedent, one slice on, and the precedent is
the argument.** W10c faced the same shape — `unit_number` and `error_type` could
not name one of the 82 targets — and the resolution was a field on `BaseItem`
that persists because **`payload_of` derives `items.payload` by SUBTRACTING the
promoted columns** (`schema.py:269-276`), so a field is stored from the moment it
exists and `StoredItem.as_item` rehydrates it through `**payload`. Verified in
the tree, not assumed. **`schema_version` is untouched by this**; the migration
§8 now takes is for a different reason entirely.

It goes in two existing frozensets, both for reasons already written there:

- **`NOT_THE_GENERATORS`** — beside `grammar_target`, `unit_number` and
  `error_type`. The run's mode is not the model's to choose.
- **`projection.NEVER_VISIBLE`** — beside `grammar_target`. Telling the learner
  (or the blind solver) that an item is a checkpoint item is a category hint.

Then the two reads are exact rather than approximate:

```sql
-- checkpoint_items:  AND items.payload ->> 'cohort' = 'checkpoint'
-- focus_items:       AND coalesce(items.payload ->> 'cohort', 'focus') <> 'checkpoint'
--                    (the exclusion applies to UNATTEMPTED rows only — see below)
```

**`coalesce(…, 'focus')` is the backfill, and there is nothing to backfill.** The
14 live items carry no `cohort` key, and they were generated by the 8-slot
block-3 run (`ITEMS_PER_UNIT = 8`) — so *absent means focus* is not a default, it
is what those rows are. No data pass, no migration, no re-generation.

**`content_hash` does not move**, checked rather than assumed: it is
`sha256(item_type, fold(prompt_text), hash_contribution(item))`
(`schema.py:608-613`) and does not read `payload`. So no existing row's hash
changes and `UNIQUE (user_id, content_hash)` keeps meaning what it meant. **One
consequence worth naming: a checkpoint item whose stem duplicates an existing
block-3 item is refused by that unique key and the slot comes back short** —
which is `insert_item` returning `None`, already counted and reported by the run.
That is the right outcome (the learner cannot be tested on a stem they already
have) and it is a reason the cohort can come in under twelve, so it is on the
short-cohort path, not a surprise.

**No ordering constraint is needed and none is imposed.** The cohort is a
declared fact about the run that produced the row, so a top-up run after the
checkpoint run cannot confuse the two. **§13's step order is therefore free**,
and revision 2's proposed *checkpoint-run-must-be-last* sentence is **not**
adopted — a constraint that is unnecessary is one more thing to get wrong.

**The precedence rule, and it is the part that matters: the withholding is
suspended when it would leave block 3 empty.** If the unit's bank holds nothing
but the reserve, `focus_items` serves the reserve and **the checkpoint refuses
that week**. Daily practice beats a weekly checkpoint, and the checkpoint fails
*loudly* — the not-ready surface — rather than the session failing silently.
A learner with an empty block 3 has lost their day; a learner with no checkpoint
has lost a Saturday, and only one of those is recoverable.

**THE RELEASE CONDITION, which the send-back correctly says any reserve needs.**
Three, and together they bound it:

1. **The sitting dissolves it.** Once sat, the twelve carry `item_attempts` rows.
   The exclusion applies to unattempted rows only, so **a sat checkpoint's items
   become ordinary practice stock** — which is the right end for them.
2. **A pass dissolves it.** The reserve is scoped to `items.unit_number` and
   `focus_items` is called with the learner's *current* unit, so the moment
   `current_unit` advances, unit 1's reserve stops being consulted at all.
3. **The empty-block-3 suspension bounds the un-sat case.** A cohort generated
   for a checkpoint nobody opens cannot starve block 3, because the suspension
   fires before block 3 reaches zero. It can make block 3 *thin* — that is the
   residual, it is visible on a screen, and it is **H5b**.

**THE TEST THE SEND-BACK SPECIFIED IS THE ONE THAT DISCRIMINATES THE TWO
MECHANISMS, and that is why it is worth writing.** *Generate a checkpoint cohort,
then a later top-up cohort, and assert the reserve still resolves to the
checkpoint's twelve.* Under `created_at DESC LIMIT 12` it **fails** — it resolves
to eight top-up items and four checkpoint ones. Under the declared cohort it
**passes** by construction. So it is written as **test 12**, demonstrated red
against a recency implementation, and it is the test that would have caught
revision 2's mechanism before a Saturday did.

**Declined: recency (`created_at DESC LIMIT 12`)** — revision 2's answer, broken
above. **Declined: a `created_at` window** — it needs a duration nobody has a
basis for choosing, goes stale when a run slips a day, and cannot express *these
twelve*, only *everything since Thursday*. **Still declined:
`reserved_for_checkpoint` as a COLUMN** — but the §3 reason is restated because
it does *not* apply to what is adopted, and the distinction matters. §3's flag is
against *materialising per-user rows that could be computed*. **The cohort cannot
be computed**: it is a fact about the intent of the generation run, which nothing
else in the system records — the same argument W10c made for `grammar_target`
against `unit_number` + `error_type`. And it is not a column: it is one key in an
existing JSONB column on a row that already exists and is already per-learner.

**THE ARITHMETIC THIS FORCES INTO THE OPEN, and it is the real cost of the
slice.** For a unit to serve block 3 *and* a checkpoint, its bank needs
**`FOCUS_ITEM_COUNT` + `CHECKPOINT_ITEM_COUNT` = 8 + 12 = 20 unattempted items**,
which is **two generation runs per unit** — the existing 8-slot block-3 run and
the new 12-slot checkpoint run. Unit 1 holds 4. **So unit 1 needs both runs
before its first Saturday, not one**, and §3.3's ceiling is stated per run with
that in mind. This was implicit in the plan and is now arithmetic on the page,
because a supply plan that quietly assumes one run is the same defect one level
up from the one this section fixes.

**What the reserve still does NOT prevent, said plainly:**

1. **A checkpoint item being a sentence the learner read in a lesson (#239).**
   Nothing prevents it. The lesson generator and the item generator do not read
   each other, unit 1's items predate any lesson, and a checkpoint draws 12 items
   against exactly the targets a lesson now teaches — so the overlap gets
   **larger**, which is what #239 says. **This plan does not build a
   cross-generator uniqueness check** (it needs one package to load the other's
   rows and a ruling on which side yields), and #239 is re-confirmed as open
   against W11 with the exposure now numbered: 12 items rather than 8.

## 3.3 The billed-call ceiling — computed in code, never written in a document

**No number is asserted here.** W10b and W10c both published the expected case
labelled as a ceiling and both were wrong; the instruction is followed by making
the ceiling a function and making the dry run print it.

`core/items/generate.py` gains, beside the existing `_expected_calls`:

```python
def _expected_checkpoint_calls(numbers, slots_by_unit) -> int:
    """The ceiling, itemised, for a --checkpoint run. Printed before any spend.

    Per unit, computed from the ACTUAL slot plan rather than from a constant:
        1                                   generation
      + 1                                   one batched naturalness call
      + n_probed                            probes; a slot whose type's
                                            ANSWER_FAMILY is not in
                                            PROBED_FAMILIES is not probed
                                            (match_pairs, #192)
      + MAX_REPAIRS * n_slot_family         cue re-probes
      + len(slots)                          probe_target, one per surviving item
      + n_l1_to_l2                          back-translation
      + 1                                   #169's checkpoint-level uniqueness
                                            pass over the 12 as a SET, one
                                            batched call per cohort
    times 2, which allows exactly one top-up round -- and the x2 covers the
    #169 re-pass as well, because a #169 rejection tops the cohort up and the
    replacement set must be re-checked as a set,
    plus CONTROL_RUNS for the negative control.
    """
```

**The #169 term was missing from the first draft of this docstring while §10
described the call as *on the ceiling*, and that is exactly the defect this
function is written to prevent — a ceiling that omits a call the run makes.**
Corrected here rather than at implementation time, and the correction is why the
ceiling is a function whose terms can be read line by line instead of a number.

**Two runs per unit, not one (§3.2a).** The ceiling is per *run*. A unit that
needs both the 8-slot block-3 cohort and the 12-slot checkpoint cohort pays both,
and the dry run prints each separately rather than a combined figure that hides
which half is expensive.

**`--live` AND `--apply` ARE TWO BILLED RUNS, AND THEY WRITE DIFFERENT ITEMS.**
Read rather than assumed: `main()` routes `--live` and `--apply` into the same
`run(...)`, which calls `verify_cohort` either way and differs only in whether it
writes (`generate.py:1443-1560`); `parser.error("--live and --apply are
alternatives; --apply implies --live")` confirms they are one pipeline, not a
preview and a commit. **So `--live` then `--apply` bills twice and the items the
operator read in the first run are not the items the second run writes** — the
model is stochastic and the cohort is regenerated. That is **#235's exact defect
in the item generator**, where the lesson generator has an `apply-from-journal`
path and this one does not. **Filed** (§12(d)), **and §13 is written around it**:
dry run → `--apply`, with the journal and `--report` as the record of what was
written, never `--live` followed by `--apply`.

Both terms `n_probed` and `n_slot_family` are derived from
`gates.ANSWER_FAMILY` and `gates.PROBED_FAMILIES` at call time, so a change to
either moves the ceiling automatically instead of leaving a stale constant.
`dry_run` prints it under a new `=== ceiling ===` heading, alongside the slot
plan, before a single call is made — and the operator reads the number there,
not here.

**A pre-registered structural expectation, stated as an expectation and not as a
ceiling:** a 12-slot checkpoint cohort is 1.5× W10c's 8-slot cohort on every
per-slot term, and the two per-unit constants (generation, naturalness) do not
scale. **The run is one unit for one learner**, against W10c's three units.

## 3.4 The second learner's position — stated, not discovered

**The second learner has no checkpoint until #159's consumer 3 lands, and this
plan does not carry it.**

Established rather than assumed: `generator_system_prompt()` substitutes only
`{contract}` into `item_generate.txt`; the template says *"`l1_gloss` must be
written in the learner's own script"* and **is never told which language that
is**; `L1ToL2ProductionItem.l1` defaults to `"fa"` (`schema.py:166`); and
`checks._l1_production` (`checks.py:611-621`) branches on that field. So
generating for the Lithuanian learner today writes Farsi glosses and, if
`l1_to_l2_production` ever passes, a Farsi prompt — the exact failure #159
describes, on the one consumer W10 explicitly left open.

**What W11 does:** generates the checkpoint for **user 3 only**, exactly as W10c
scoped items, and the Saturday surface renders the not-ready state for the
second learner. **What is filed:** #159's consumer 3 is re-targeted with W11
named as a second slice blocked on it, so the "which slice unblocks her" answer
is in the record rather than re-derived.

**The alternative was considered and rejected**: carrying consumer 3 inside W11
means changing `llm.py` request construction's inputs, which fires standing rule
3 (one real API call before shipping) inside a slice that already has a billed
generation run — and it is a generator change, which belongs with the generator.

## 3.5 `item_types` is a parameter, and what changes under each #207 ruling

The permitted set is **not assumed**. `checkpoint_slot_plan` takes `permitted`
and `unit_plan` computes the default as `checkpoint.item_types` intersected with
what the generator can actually produce. What changes under each possible ruling
on #207's open half:

| ruling on the checkpoint blueprint's `item_types` | what changes |
|---|---|
| **unchanged (seven types in all 24 units)** | `permitted` still resolves to the five in `SLOT_TYPES`, because `mcq` and `collocation_pick` are already out of the *generator's* mix on the 2026-08-27 ruling. **No code change.** The blueprint stays wider than anything that reads it — a standing inconsistency, not a defect this slice can fix. |
| **narrowed to the five `SLOT_TYPES`** | `data/syllabus_units.json` changes in 24 rows, `syllabus_units.checkpoint` is re-seeded, `unit_plan`'s permit check keeps working unchanged. A data pass, not a code pass. |
| **`match_pairs` dropped (the #192 argument)** | `permitted` becomes four types; the ceiling function's `n_probed` term rises to `len(slots)` because every remaining type is probed, so the run costs more and the ceiling reflects it automatically. Unit 1's live `match_pairs` items become ineligible for a checkpoint draw, which is 3 of the 14. |
| **`l1_to_l2_production` dropped** | the back-translation term disappears from the ceiling; the type that has never once been accepted stops consuming slots. |

**#192's consequence is named here so a plan does not discover it: permitting
`match_pairs` in a checkpoint permits an ungated type**, and 3 of the 14 live
items are of it. This plan does not narrow the set — that is the operator's
(§9).

---

# §4. THE RE-QUEUE — the noun before the verb

## 4.1 What a re-queued target *is* — the four candidates evaluated

A grammar target is one of 82 strings on `syllabus_units.grammar_targets`. A
review queue is block 1: FSRS due cards. **A target is not a card and nothing
converts one into the other** (V5).

### (a) an `errors` row plus a generated error card

**Cost:** #107's real error-classification step; a target→`error_types.code`
mapping that does not exist; **and, from V5, a code set that cannot express the
distinction** — three of unit 1's four targets are `verb_tense_past` and the
fourth has no code at all. Then an errors→cards path that does not exist either
(V5: one `INSERT INTO cards` in the tree, fed by chunks and capture).

**What it forecloses:** nothing, but it is the only candidate that writes to the
journal.

**What it writes to `errors`:** a row per missed target, with `you_said` and
`correct_form` that would have to be **synthesised from the item**, because a
checkpoint item is tapped or typed against a canonical answer and the learner's
response is a *selection*, not a self-produced sentence — which is #107's own
stated reason for having no writer.

**How a wrong row would be prevented: it could not be.** CLAUDE.md §5 —
*only genuine self-produced errors are written to `errors`; a wrong row is
permanent damage; a missing one is recoverable.* A tapped wrong option in a
`match_pairs` item is not a self-produced error. **Rejected.**

### (b) state on `user_unit_state` naming the missed targets, read by the generator

**Cost:** as originally shaped, one new column. **But it does not need one.**
The missed targets of the last checkpoint attempt are **computable** from rows
that already exist:

```sql
SELECT DISTINCT i.payload ->> 'grammar_target' AS target
  FROM item_attempts a
  JOIN items i ON i.id = a.item_id
 WHERE a.session_id = %s          -- the checkpoint session
   AND a.correct IS FALSE
```

`item_attempts.session_id` is a real FK (012), `correct` is `BOOLEAN NOT NULL`,
and `grammar_target` is the one handle that names one of the 82 (V5). Storing
the list would materialise per-user rows that could be computed — the flag
PRODUCT-PRINCIPLES §3 asks for at the moment of the choice — and it would go
stale the instant a retake happened.

**What it forecloses:** nothing. **What it writes to `errors`:** nothing.

### (c) item-level re-delivery — the missed items themselves are re-served

**Cost:** almost none; the retake selector already needs an ordering.
**What it forecloses:** it re-queues *items*, not *targets*, which is a narrower
promise than PRD §3's — and re-serving the exact items a learner just failed is
the recall-not-production failure #239 describes, one slice on.

### (d) nothing in W11

Honest but leaves the fail path with only bookkeeping.

## 4.2 THE DECISION

**W11 delivers (b), computed, scoped to the retake — and it does NOT deliver
PRD §3's "injected into the next week's review queue".**

Concretely:

- `core.services.syllabus.missed_targets(user_id, unit_number)` — the query
  above, over the learner's most recent **failed** checkpoint session for that
  unit. Pure read, no column, no journal write, no card.
- **`checkpoint_slot_plan` reads it when building a RETAKE.** The retake's 12
  slots are re-weighted toward the missed targets while still covering every
  target at least once — a target nothing checks is not a target
  (`blueprint.py:214-219`'s own rule, applied one level out).
- `core.items.generate --checkpoint --retake` passes it through.
- **And `checkpoint_items` calls the SAME function to know what to select**
  (§3.1(b)), so the selector's quotas are the cohort's own rather than the
  blueprint's. Without that, a re-weighted retake cohort could never be selected
  and the fail path would refuse every time — which is the mismatch the operator
  caught on the third round.

**What W11 does NOT deliver, and the acceptance criterion is corrected rather
than satisfied by an invented mechanism.** PRD §3 says the missed targets go
into **next week's review queue** — block 1, FSRS. That requires an
errors→card path, an error-card type with a writer, and #107's classification,
none of which exist, and the one bridge available (`error_types`) demonstrably
cannot name the target. **Building a plausible-looking version of it would write
rows to the error journal that are not genuine self-produced errors, and this
record already says why that is worse than an absent mechanism.**

**The correction to `docs/TASKS-v3-web.md`**, old text quoted in place per #82's
shape:

> W11 Accept, as it reads today:
> *"Passing marks the unit `passed`; failing re-queues targets and offers a
> retake in 4 days with no punishment copy."*
>
> Corrected to:
> *"Passing marks the unit `passed`. Failing leaves it `in_progress`, bumps
> `checkpoint_attempts`, records `last_checkpoint_score`, sets `retake_due_on`
> to four days out, and re-weights the retake's twelve items toward the targets
> that were missed — computed from `item_attempts`, with no journal write and no
> card. **Injecting missed targets into block 1's FSRS review queue is NOT in
> this slice**: it needs an `errors → card` path that does not exist and an error
> classification (#107) that `error_types` cannot express, since three of unit
> 1's four targets share one code and the fourth has none. Filed as a new issue
> against W16, the slice that next writes to the journal from a graded surface.
> No punishment copy either way."*

**PRD §4.2 and §3 are NOT amended.** §3 still describes the target; what changed
is which slice delivers that half, exactly as ruling 3 handled Mon–Fri.

### #107 IS RE-TARGETED — explicitly, with a successor and a reason

**#107 reads: *"W11 is the slice that writes the first `source = 'item'` row,
with a real error-classification step rather than by assuming the item's
target."* W11 decides it writes nothing to `errors`. That leaves #107 pointing at
a slice that shipped without it**, which is the drift W10 named when it
re-targeted six issues off itself, and it is not fixed by listing #107 in a
carried-forward line.

**RE-TARGETED W11 → W16**, in the decisions log and on the row, with the old
target quoted in place.

**The reason, and it is the same reason that decided §4.2:** #107's own text asks
for *a real error-classification step*, and V5 establishes that the classification
has nothing to classify into — three of unit 1's four targets share
`verb_tense_past`, the fourth has no code at all, and `items.error_type` is NULL
on every generated row because the field sits in `NOT_THE_GENERATORS`. A
checkpoint answer is a **selection against a canonical**, not a self-produced
sentence, so `you_said` and `correct_form` would have to be synthesised — which
is #107's own stated reason for having no writer.

**W16 and not W15, and not "a later slice".** W16 is Writing output: the daily
journal and the weekly paragraph task, both **free written production, corrected**
— the first surface after W3's `/correct` where a learner produces a sentence that
is genuinely theirs and a correction genuinely names what was wrong with it. That
is what `errors.source = 'item'` needs and what a tapped checkpoint answer cannot
supply. §4.2 already sends PRD §3's block-1 injection to W16; **this says so
rather than leaving it implied by proximity.**

**W15 was the live alternative and is declined**: it is ASR-scored speech, which
012's own harvest table classifies as *NOT harvested — a `speak_answer`
mishearing must never promote a word*, and the same objection applies to writing
a journal row from it.

## 4.3 Which half of the fail path W11 delivers

| half | W11? |
|---|---|
| unit stays `in_progress` | **yes** — the state write |
| `checkpoint_attempts` bumped | **yes** — column exists, no DDL |
| `last_checkpoint_score` recorded | **yes** — column exists, no DDL |
| `retake_due_on = local_today + 4` | **yes** — column exists, arithmetic on a `DATE` |
| no punishment copy | **yes** — banned-phrase test extended to the new strings |
| retake's items re-weighted to missed targets | **yes** — computed, §4.2 |
| missed targets in **next week's block 1 review queue** | **no** — filed, criterion corrected |

---

# §5. THE SEAM AND THE ENTRY RULE — decided explicitly

## 5.1 #219 — where the rule lives

**DECISION: every write to `user_unit_state` goes through ONE MODULE, and there
are TWO functions in it. Each calls the guard that applies to it, and neither
calls the other's.**

**The first draft of this section said `record_checkpoint` is "the only writer"
while §5.2 gave `record_unit_entry` a write. Both could not be true, and it was
wrong in the section that decides #219.** Corrected, and the correction is
load-bearing rather than cosmetic — it decides which function the guard test
must exercise.

| function | when it runs | which guard it calls | what it does on refusal |
|---|---|---|---|
| `record_unit_entry(conn, user_id, unit_number, *, now)` | the learner reaches a unit they have no row for | **`may_enter('in_progress')`** — the only caller of `may_enter` in production | raises |
| `record_checkpoint(conn, user_id, unit_number, *, session_id, score, passed, now)` | a checkpoint sitting is scored | **`may_move(current, incoming)`** — the only caller of `may_move` in production | raises |

**`record_checkpoint` has NO no-row branch, and that is the point.** The first
draft had it call `may_enter` "when there is no row" — which, once
`record_unit_entry` always creates the row first, is **a branch the real path
never reaches**, and #219's guard would have been reached only by a code path
that never runs. That is the eleventh-appearance family arriving inside the fix
for it, and it is removed rather than qualified. `record_checkpoint` **raises
loudly** when it finds no row: a checkpoint on a unit nobody entered is a bug in
the caller, not an occasion to invent an entry.

**So test 1 exercises `record_checkpoint` for `may_move`, and a new test
exercises `record_unit_entry` for `may_enter`** — each against the function that
actually calls it. See §10 tests 1 and 2.

### The attempt key — `record_checkpoint` needs one, and `UNIQUE (user_id, unit_number)` is not it

`UNIQUE (user_id, unit_number)` is a **row** key. A second call for the same
sitting would `ON CONFLICT DO UPDATE` and **bump `checkpoint_attempts` again —
and move `retake_due_on` with it**, so a double submit shortens or lengthens the
retake. Nothing in the first draft distinguished *the same sitting submitted
twice* from *a genuine retake*, and test 5 could not have held.

**The discriminator is the checkpoint's own `sessions` row** — and the send-back
is right that revision 2 never said what creates that row, which is the fact the
whole key rests on. **Answered in three parts below, and the answer costs a
migration.**

### What creates the sitting, on which verb, and what makes it idempotent

**`GET /checkpoint/today` creates it, with `INSERT … ON CONFLICT DO NOTHING`
followed by a re-read — the same statement, in the same shape, as
`_get_or_create_daily`.** It is an idempotent create-once, not an increment, so
it sits on the right side of §5.2's distinction rather than being a second read-
path write of a different kind.

**But `_get_or_create_daily`'s idempotency is an INDEX, not a statement, and that
index does not cover this.** Read rather than assumed:
`sessions_one_daily_per_user_per_date` is `ON sessions (user_id, date) WHERE
task_type = 'daily'` (016 §2). **A checkpoint row is constrained by nothing.**
Two refetches — and the route's own rate-limit comment records that *"a phone
that backgrounds and resumes refetches"* — create **two sittings**, both
`completed = FALSE`. Both claim cleanly. The attempt key reads them as two
genuine retakes: `checkpoint_attempts` bumped twice, `retake_due_on` moved twice.
**That is exactly the failure the attempt key exists to prevent, one layer below
where it was fixed**, and `ON CONFLICT DO NOTHING` without a unique constraint to
conflict *on* is a statement that never conflicts.

### SO §8's NO-MIGRATION FINDING FALLS. W11 TAKES 018.

```sql
CREATE UNIQUE INDEX sessions_one_checkpoint_per_user_per_date
    ON sessions (user_id, date)
 WHERE task_type = 'checkpoint';
```

One partial unique index, mirroring 016's instrument exactly and for the same
reason 016 gives: **partial and not a plain `UNIQUE (user_id, date)`, because the
other twelve task types legitimately have several rows on one date.** One
checkpoint per learner per **local** date is right — a retake is four days later
and is a different date, so the constraint separates a double tap from a retake
without needing to know which is which.

**This is #185's FIFTH occurrence and it is taken honestly rather than worked
around** (§8). The alternative was considered and is worse: reusing the daily
`sessions` row would overload `completed` — on a day that is both a session and a
checkpoint it would mean two things — and making Saturday's session *be* the
checkpoint would drop block 1 for a day, which is the same scheduler-change-by-
calendar-rule this plan rejects for Sunday in §7.4.

**A migration also gives #167 the file it was missing** — §8 said the reason for
leaving the sum invariant in the validator had nowhere to be recorded because W11
wrote no `.sql`. It does now, and 018's header carries it.

### The claim, unchanged

`POST /checkpoint/complete` claims the sitting before scoring it, in one
statement:

```sql
UPDATE sessions
   SET completed = TRUE, completed_at = %s
 WHERE id = %s AND user_id = %s AND task_type = 'checkpoint'
   AND completed = FALSE
RETURNING id
```

No row returned → this sitting was already scored → **`record_checkpoint` is not
called at all**, and the route returns the state that already exists. Race-free
by the same instrument `_get_or_create_daily` already relies on: the database
decides, not a read-then-write. `sessions.completed` and `completed_at` are
columns from 001 and `complete_session` already writes them.

**A genuine retake is a different `sessions` row**, so the key discriminates
exactly the two cases that must be told apart. Test 5 is rewritten against it.

`record_checkpoint` itself then:

1. `SELECT ... FOR UPDATE` the `user_unit_state` row — **raising if there is
   none**;
2. computes the incoming state (`passed` or `in_progress`);
3. calls `may_move(current, incoming)` and **raises** on a refusal;
4. `UPDATE`s the row.

**The reason, and it is the reason W8 chose an enumeration over an ordering:**
an ordering is what cost W4 231 of one learner's 2,000 floor lemmas (#91).
014's CHECKs are row-local and **structurally cannot express a transition** (V1)
— a `CHECK` never sees the predecessor row, and the only SQL construct that
could is a trigger, which this project does not use anywhere. So "let the
CHECKs be the only guard" is not a lighter option; it is *no* transition guard
at all, and it would leave `ALLOWED_TRANSITIONS` a caller-less enumeration for
an eleventh appearance.

**Declined: writing straight to SQL with 014's CHECKs as the only guard.**
Reason: it silently discards the transition rule, and specifically it permits
`passed → in_progress` nulling `passed_at` — the one move the module says must
never happen, because `passed_at` is the clock mastery is timed from.

**The layer disagreement is resolved, not left invisible.** It is resolved
**in Python, in one place, with the reason recorded** — because it cannot be
resolved in SQL without a trigger. 014's comment already says W9/W10/W11 write
the first row; W11's decisions-log entry records that the CHECKs remain the
row-local guard, the service is the transition guard, and the two are
deliberately not the same instrument.

**How #219 stops being decoration — TWO tests, one per guard, each through the
function that actually calls it, and both demonstrated RED.**
`test_may_move_is_reached_by_the_real_write_path` puts a real row at `passed` and
asserts `record_checkpoint` refuses; `test_may_enter_is_reached_by_the_real_entry_path`
asserts `record_unit_entry` refuses a state `may_enter` rejects. Both assert the
*service* refuses, never that the predicate returns False. Both go red by
stubbing the guard call out of the function under test. **A test that only
exercises `may_move` proves nothing new** — nine of `test_syllabus_states.py`'s
seventeen tests already do that, and #219 is filed precisely because they are all
there is.

**Also enforced structurally:** a boundary test in `tests/test_core_boundary.py`
naming **one module** — `core.services.syllabus` — as the only module permitted
to write `user_unit_state`, in the shape of the existing
`test_exactly_one_module_writes_an_item`. **The guard was always at module level
and covers both functions**; it is the prose that named one function, and that is
what has been corrected.

## 5.2 #217 — the entry rule

**OPERATOR RULING, 2026-08-29: candidate (b). `may_enter` widens to admit
`in_progress`, and `entered_at`'s meaning is restated.** Recorded as an operator
ruling with its date, not as an assistant decision.

`may_enter` becomes: the legal first states are `available` **and
`in_progress`**. `entered_at` is restated from *"the moment the unit became
available"* to **"when this learner first reached this unit"**, which is the
fact W19's history actually wants and the only one W11 can honestly write.

**WHAT `may_enter` NOW REFUSES — stated because a rule that admits everything is
not a rule.** It refuses three things, and each refusal does work:

| refused as a first state | why the refusal matters |
|---|---|
| **`passed`** | a first row in `passed` claims a checkpoint pass for a unit no row records the learner as ever having reached. It would satisfy every one of 014's CHECKs (V1) provided `passed_at` and `last_checkpoint_score >= 80` were supplied, so **the database will not stop it and this is the only thing that will.** It is also the exact write `record_checkpoint` would produce if the entry write were ever skipped, which is what makes the refusal load-bearing rather than theoretical. |
| **`mastered`** | same, one step worse: it would claim a 21-day retention interval on a row created seconds ago. 014's `user_unit_state_mastery_needs_a_pass_and_three_weeks` would refuse *this particular* row, but only because `mastered_at >= passed_at + 21 days` cannot hold when both are `NOW()` — a coincidence of the data, not a statement about entry. `may_enter` says the thing directly. |
| **`locked`** | `validate()` raises its own dedicated message before `may_enter` returns at all. `locked` is the absence of a row and remains unforgeable. |

So the widening moves exactly one value across the line, and the rule still
divides the four storable states two-and-two. The old docstring and the old
assertion are **quoted in place, not deleted** — see §10 test 3 and §12(c).

**When the row is written, and where from — established by reading the route
rather than assumed.** `record_unit_entry` is called from
`core.services.sessions.today()`, inside the connection it already holds, beside
`_current_unit_row`. That is `GET /session/today` — **a read path that already
writes.**

**The apparent contradiction with §6.1, and why it is not one.**
§6.1 rejects a stored `section_index` partly because *it would need a write on a
read path*. The send-back is right that the same objection appears to apply here,
and the distinction has to be made precisely rather than waved at:

| | `_get_or_create_daily` (**ships today**) | `record_unit_entry` (**proposed**) | a stored `section_index` (**rejected**) |
|---|---|---|---|
| shape | `INSERT … ON CONFLICT DO NOTHING` | `INSERT … ON CONFLICT DO NOTHING` | `UPDATE … SET index = index + 1` |
| how often it writes | once per learner per local date | once per learner per unit | **every request** |
| idempotent on a refetch | yes — 016's partial UNIQUE | yes — 014's `UNIQUE (user_id, unit_number)` | **no** |
| what a double fetch costs | nothing | nothing | a section skipped |

**The objection was never "no writes on a read path" — it was "no *mutating,
non-idempotent* write on a read path", and the shipped code makes that
distinction already.** `_get_or_create_daily`'s own docstring says it: *"Idempotent,
and idempotent by the DATABASE rather than by a read-then-write."*
`record_unit_entry` is the same statement against the same kind of index.
**And the counter case is not hypothetical**: the route's own rate-limit comment
records that *"a phone that backgrounds and resumes refetches"* — so an
incrementing write there would skip sections on a phone lock, which is precisely
the failure the #245 ruling exists to prevent.

**The alternative was checked and is worse.** The only POST on this router is
`POST /session/{id}/block/{n}/complete`, which fires after the learner has already
been served blocks 3 and 4 — so hanging the entry write on it would mean the
first session on a unit renders with no row, `unit_section_index` has no lower
bound to count from, and block 3's very first render is the one that cannot be
paced. **Entry must happen before the blocks are built, and `today()` is where
they are built.**

**Why (b):**

- It **does not touch ruling 2.** W11 still never writes `available`; the
  `available` predicate stays W9's.
- It gives PRD §3's fail path a row to write to, which is the hole #217 names.
- **It gives §6's clock its origin.** `entered_at` becomes the only timestamp in
  the system that says when a learner started a unit, and it is the lower bound
  the ruled pacing rule counts sessions from. Under (c) that timestamp exists
  only from the moment of the pass, so there is nothing to count from.
- `current_unit` is unaffected — it reads `passed_at`, never `state`.

**Declined, with reasons and with the ruling-2 flag:**

- **(a) W11 writes `available` after all.** **This one reverses operator ruling
  2 and is therefore the operator's call, not the plan's.** It is the tidiest
  against the state machine as written — no restatement of `entered_at`, no
  widening — but it puts W9's predicate in W11 with no surface to render it,
  which is what ruling 2 declined. **If the operator prefers (a), say so and the
  plan changes here only: `record_unit_entry` writes `available` and `may_enter`
  is untouched. Everything else in this plan is unchanged.**
- **(c) `available` and `passed` in one transaction, so the first state is never
  observed.** Declined for two reasons. It creates `entered_at` at the moment of
  the pass, so the timestamp is a fact about a moment that never happened —
  exactly the objection `may_enter`'s docstring raises against the thing it
  refuses. And **it has no story for the fail path at all**: a learner who fails
  their first checkpoint has no transaction that writes `passed`, so no row is
  created, so `in_progress` cannot be recorded and `retake_due_on` has nowhere
  to live.

**What this obliges:** `tests/test_syllabus_states.py::test_a_learner_enters_only_at_available`
is rewritten with its old assertion quoted in the docstring, and the restated
meaning of `entered_at` is written into `states.py` and into the decisions log.
A test asserting `may_enter("passed") is False` and `may_enter("mastered") is
False` keeps the widening narrow.

---

# §6. THE CLOCK — #245 and #188 are one missing clock, and it does not need to be a column

## 6.0 THE PACING RULING — operator, 2026-08-29

> **Section advances per completed session, not per calendar day** — a learner
> who skips a day loses nothing and sees the next section when they next open a
> session. **When sections run out before Saturday, block 3 shows practice only
> — no new teaching, no repeated section.**

This is neither of the two options the plan costed. It is better than both, and
the reason is worth recording because it is the reason CLAUDE.md §4 exists:
**a calendar clock makes a missed day a lost section, which is a backlog that
never gets presented and therefore never gets caught.** *Missed days shrink the
task; they never pile up* — under a calendar rule they do neither, they simply
delete teaching. A session counter makes the unit take as long as the learner
takes, and nothing is ever behind.

Everything in §6 below is rewritten to it. §6.3's two costed options are
**superseded** and kept only as the record of what was declined.

## 6.1 Does W11 introduce per-learner within-unit state?

**No new column and no new table.** The position is a **count of what already
happened**, bounded below by `entered_at`:

```python
def unit_section_index(conn, user_id, unit_number, *, now) -> int:
    """0-based section this learner has reached in this unit.

    The number of PRIOR daily sessions in which this learner completed the
    focus block, since they entered this unit. Zero on the first session.
    """
```

The query, over rows that already exist:

```sql
SELECT count(*)::int
  FROM sessions s, user_unit_state u
 WHERE s.user_id = %s AND u.user_id = s.user_id
   AND u.unit_number = %s
   AND s.task_type = 'daily'
   AND s.date >= (u.entered_at AT TIME ZONE %s)::date
   AND s.date <  %s                       -- strictly before today (local)
   AND s.block_breakdown ->> 'focus' = 'done'
```

**`block_breakdown->>'focus' = 'done'` and NOT `completed_at IS NOT NULL`, and
this is a strict reading of the ruling rather than a departure from it — flagged
so the operator can send it back if it is the wrong reading.** A learner can
complete a session having skipped block 3; counting that session would advance
them past a section they never saw, which is the one failure the ruling exists to
prevent, one layer down. `block_breakdown` is the resume state 016 shipped
(`{kind: state}`, keys are kinds not numbers), `stored_state` already reads it
tolerantly, and `focus = 'done'` is written by `complete_block` — so *"the
teaching block was actually finished"* is a fact the system already records.
**If you meant the looser reading — any completed session advances — say so and
this is a one-clause change.**

`s.date` is the learner's local date, which is how every `sessions.date` across
eleven task types is computed (`local_today(users.timezone, now)`,
`services/sessions.py:48`). `now` is injected as it is throughout, so a boundary
test walks local midnight without freezing the clock (CLAUDE.md §3 rule 6), and
**both sides of the comparison are computed the same way** — rule 6's other half,
which is what broke `test_vocabulary_due_and_anki`.

**PRODUCT-PRINCIPLES §3 position, flagged at the moment of the choice:** a
`section_index` column would materialise per-user-per-unit state for a value the
session log already determines, and it would need something to advance it — a job
that does not exist (#69) or a write on every session open, which is a write on a
read path. The computed form has neither problem, and it **self-heals**: a
session row corrected later moves the index with it.
**PRODUCT-PRINCIPLES §2 position:** no user-keyed table and no user-keyed column
is added; §2 is satisfied by `user_unit_state` and `sessions` already keying on
`users(id)`.

## 6.1a THE BACKFILL — both learners have already read unit 1's lesson in full

**Named because it is invisible in code and would land as four days of
re-reading.** `record_unit_entry` writes `entered_at = now` the first time a
learner opens a session with no row. Both learners have been in unit 1 since
2026-08-27 and one has read the whole lesson; on the day W11 ships, both get
`entered_at = <deploy day>`, the session count since then is 0, and **block 3
opens section 1 of a lesson they have finished.**

**POSITION: backfill `entered_at`, and do it as a one-off human-run data step,
not in code.**

The value to backfill is **the learner's earliest `sessions.date` for
`task_type = 'daily'`** — the first day they opened a session on unit 1, which is
what `entered_at`'s restated meaning (*when this learner first reached this
unit*) says it should hold. It is in the database already; nothing is invented.

**Why a data step and not code.** A backfill branch inside `record_unit_entry`
would be a permanent conditional serving two learners once, on one day — the
shape W4a's repair and W7's chunk pass were both deliberately kept out of their
migrations for. It runs once, it is idempotent (`ON CONFLICT DO NOTHING`
followed by a targeted `UPDATE … WHERE entered_at > <value>`), and it belongs in
§13 beside the other server commands with its own before-and-after read.

**Why not simply accept the restart, which was the live alternative.** It costs
the learner who has read unit 1 several sessions of teaching he has already read,
on the first days after a slice whose whole point is that the unit finally moves
— and **it would make H6 unreadable**, because the check that the pacing works
cannot be run on a learner whose section index is wrong for a reason the check
cannot see. The restart is not harmful; it is just indistinguishable from the
bug, and that is the reason to spend one command on it.

**What the backfill does NOT do:** it does not claim the learner completed the
focus block on those days. `unit_section_index` counts sessions whose
`block_breakdown.focus = 'done'`, and the historical rows say what they say —
so the index after the backfill is *whatever those learners actually did*, which
is the honest answer and may well be fewer than four. **The command prints the
resulting index for both learners before anything else runs**, so the number is
read rather than assumed, and H6 is run against a known starting point.

## 6.2 What block 3 serves, under the ruling

`_focus_block` gains the index and its payload gains **two** keys — two, because
running out of teaching and having no teaching are different facts and the
learner can only see one of them on the screen. This is `BLOCK_STATES`' own
`empty`-versus-`unavailable` reasoning applied one level in.

```
{ unit_number, can_do, grammar_targets: [{target}],
  lesson,                      # unchanged: the unit's stored lesson, or null
  lesson_section: int | null,  # which section to open; null when exhausted
  teaching_complete: bool,     # true only when the unit HAS a lesson and the
                               # learner has finished every section of it
  items: [...] }
```

| situation | `lesson` | `lesson_section` | `teaching_complete` | what the learner sees |
|---|---|---|---|---|
| unit has no lesson (most units) | `null` | `null` | `false` | four bare labels and *"the explanation is on its way"* — **unchanged from today** |
| section index < section count | the lesson | the index | `false` | that one section open, the others collapsed and reachable |
| index ≥ section count | the lesson | `null` | **`true`** | **practice only. No new teaching and no repeated section.** The sections stay reachable behind their labels; nothing is opened. |

`LessonBody` (`apps/web/components/lessons/lesson.tsx:120-148`) currently maps
**every** section and opens the first (`useState(0)`, single-open `onToggle`).
The change is: it opens `lesson_section`, and when `teaching_complete` it opens
none. **No section is hidden and none is repeated** — the ruling's two clauses,
one each.

**NOTHING PINS BLOCK 3's KEY SET — checked before proposing the two new keys,
not after.** Searched `tests/test_session_route.py` and
`tests/test_sessions_service.py` for an exact-key-set assertion on a block
payload (`set(payload) == …`, `payload.keys()`, a literal key tuple): **there is
none.** What does exist is `test_session_route.py:339`'s **negative** scan —
`for banned in ("total_remaining", "due_now", "overdue", "carried")` — which
asserts keys are *absent*, so adding keys cannot break it. On the client,
`apps/web/lib/api.ts` types the session as `blocks: SessionBlock[]` with a
payload object and **declares no `FocusPayload` shape at all**, so an added key
is not a type error either.

**So nothing moves in the same commit on this account** — and the one live
constraint is stated instead: **the two new keys must not collide with the
banned-key scan**, which `lesson_section` and `teaching_complete` do not. The
scan is extended to cover them by construction, not by name.

**The copy for the exhausted state must be neither guilt nor congratulation of a
thing that is not finished.** It is not "you've completed the unit" — the
checkpoint has not happened. Nearest honest line: *"You've been through all of
this week's grammar. Practice below."* It goes through
`tests/support/no_guilt.py` like every other string.

## 6.3 ~~What a learner sees on day three, under each pacing ruling~~ — SUPERSEDED

Kept as the record of what was declined, not as a live option.

~~**Ruling A — the accordion suffices.**~~ Zero build cost; #245 stays open
exactly as filed. **Declined.**

~~**Ruling B — one section per calendar day.**~~ Declined for the reason the
plan itself flagged as B's strongest counter-argument and the operator's ruling
answers: a learner who skips three days lands on section 4 and **never sees 2 and
3**, which is teaching deleted by a calendar. The ruled rule keeps every section
and simply takes longer.

**What the ruled rule costs that neither of these did, stated so it is not
discovered:** a learner who does five sessions in one day advances five sections
in one day, because the counter is sessions and not days. There is nothing in
this system that limits daily sessions to one — `sessions_one_daily_per_user_per_date`
is a **UNIQUE index on `(user_id, date) WHERE task_type = 'daily'`**, so there is
exactly one daily session row per local date and **the count cannot exceed one per
day by construction.** Verified rather than assumed (016, section 2). The concern
does not arise, and it is recorded as checked because the counter would otherwise
look unbounded to a later reader.

## 6.4 What unfreezes the moment a `passed` row is written — named in advance

This is the change to a shipped surface that has no code change of its own, and
it is the hardest kind to notice going wrong. On the first `passed` write for
unit 1, `current_unit` returns 2 and, with **no other code change**:

| surface | before | after the first pass |
|---|---|---|
| **block 3 · can-do + targets** | unit 1's, every day | unit 2's |
| **block 3 · lesson** | unit 1's live lesson renders | `lessons_service.for_unit(2)` returns **None** — unit 2 has no lesson, so block 3 falls back to the four bare labels and *"the explanation is on its way"* |
| **block 3 · items** | unit 1's 4 items | unit 2's **3** items (host census). Block 3 asks for 8 and gets 3. |
| **block 4** | unit 1's `output_task_written`, repeating | unit 2's, repeating (#188's symptom moves, it does not end) |
| **block 3 and 4 at unit 4+** | — | **empty of content**: zero items, no lesson. `_focus_block` returns `ready` with an empty items list, which block 3 renders as its honest empty state. |
| **`current_unit` for a learner who passes all 24** | — | returns `UNIT_COUNT` (24), not 25 — the end of the programme |

**Two of these are regressions in the learner's experience and are named as
costs, not discovered on a phone.** Passing unit 1 takes the only lesson that
exists away and halves the practice items. **The mitigation is scheduling, not
code:** the operator generates unit 2's lesson and its items *before* the first
checkpoint is offered. That is a human step, it is in §11, and it is the
condition on shipping Saturday at all.

**AND THE PACING RULING SHARPENS THIS RATHER THAN SOFTENING IT.** The section
counter is scoped to the unit, so **a learner who passes unit 1 restarts at
section 0 of unit 2** — correct, and it means the first session after a pass
would open unit 2's first section **if unit 2 had a lesson.** It has none. So the
day after a pass, block 3 is: unit 2's can-do, four bare labels, *"the
explanation is on its way"*, and three practice items. **That is the exact screen
H5 exists to look at**, and it is the strongest reason unit 2's lesson and items
are generated **before** the first checkpoint is offered rather than after it.

---

# §7. THE SUNDAY WEEKLY REPORT — costed, and handed to W11b

**OPERATOR RULING, 2026-08-29: the split is accepted. W11 is the checkpoint;
W11b is the Sunday report. W11b gets a row in `docs/TASKS-v3-web.md` in the same
commit as W11's archived plan, so it is a SCHEDULED SLICE and not a deferral.**

**§7 still runs in full**, and it runs here rather than in W11b's own planning
for one reason: the question *what can a week of this system's data honestly
say?* is answerable **today**, from tables that exist, and answering it late is
how a slice discovers at implementation time that half of what it promised needs
W12–W16. §7.1 and §7.2 below are the finding; §7.4 hands them over with a design
and a cost so W11b starts from evidence rather than from four words in the PRD.


## 7.1 What data exists to report on, enumerated from real tables

| table | columns a week's worth can honestly speak from | what it can say |
|---|---|---|
| `sessions` (001 + 016) | `task_type='daily'`, `date` | **how many days had a session — and ONLY that.** *(**CORRECTED 2026-08-29, #258. Old text quoted rather than deleted, per #82's shape:** this cell read `` `task_type='daily'`, `date`, `block_breakdown` JSONB, `minutes`, `completed_at`, `xp` `` / *"how many days had a session; which blocks were completed (`{kind: state}`, kinds not numbers); total minutes, clamped and server-computed"*.)* **`block_breakdown`, `minutes` AND `completed_at` ARE NULL ON EVERY `daily` ROW ON PRODUCTION** — all three of user 3's, 2026-08-26/27/28. Their only writer is `complete_block`, reached only by the *Done with this block* button (`runner.tsx:147`), which completes ONE block per tap and has never been tapped. **So a week the learner worked every day would render as zero blocks and zero minutes**, which on this surface is not a missing number but a false one — and §7.3's own rule says a zero on a report is a score. **This row was enumerated from the SCHEMA and not from the DATA**, which is the mistake §7.1's heading claims not to make: *what data exists to report on* was answered by *what columns exist*. **`xp` is NULL on every row too** — W10 writes NULL always, W19 owns the weighting — and that half was always stated. **W11b must treat all four as unavailable until #258 is ruled**, and `docs/TASKS-v3-web.md`'s W11b row carries the same correction. |
| `item_attempts` (012) | `attempted_at`, `correct`, `item_id`, `session_id`, `graded_by`, `cue_shown`, `hint_used` | items answered this week and how many were right. `graded_by` is `NOT NULL` with three values, so the number does not silently mix instruments. |
| `card_reviews` (013 + 016) | `reviewed_at`, `rating`, `session_id` | cards reviewed this week, inside a session and outside it. |
| `user_unit_state` (014) | `state`, `passed_at`, `entered_at` | **a unit passed this week** — after W11, for the first time ever. |
| `errors` (001) | `created_at`, `resolved`, `error_type` | errors written this week, by type. |
| `user_lexemes` (010) | `state`, `source`, `updated_at` | words that moved to `known` this week. |

## 7.2 What it cannot report on, named

- **XP** — W19, `sessions.xp` is NULL on every row that exists.
- **Input minutes / videos watched / subtitle ladder** — W12, W13, W13a. No
  `videos` table exists.
- **Speaking, pronunciation, retell** — W14–W16. No `speech_attempts`.
- **Mastery** — #135. There is no metric and nothing can write `mastered`.
- **Coverage trend** — #197 is unruled and coverage is measured, never enforced.
- **Free extensive input** — PRD §4.2 says it is *tracked*. **Nothing tracks
  it**, on any surface, and W11 does not build a tracker. Reported as an absence
  rather than filled with a number.

## 7.3 The constraints, which are rules and not preferences

1. **CLAUDE.md §4 no-guilt** — the banned-phrase test covers every user-facing
   string, backend and frontend. Every new string on this surface goes through
   `tests/support/no_guilt.py`.
2. **#160 — no surface presents a backlog count.** Held today by
   `tests/test_web_shell.py::test_no_surface_presents_a_backlog_count`, and by
   `test_session_route.py:339` which bans the literal keys `total_remaining`,
   `due_now`, `overdue`, `carried` from any block payload. **The weekly report's
   payload is added to that scan.** A "you missed 3 days" line is a backlog
   presented and is forbidden.
3. **Drops silent, raises announced.** A week worse than the last says nothing
   about the last. Only an improvement or an achievement is named.
4. **Sunday carries no task.** A report that asks the learner to do anything —
   including a "start your session" primary button — is a defect.

## 7.4 What is handed to W11b — the design, its cost, and its TASKS row

**Not a deferral: a scheduled slice with its findings already in hand.** The
recommendation below is W11b's starting design, not a decision W11b is bound to;
what it *is* bound to is §7.1's data list, §7.2's absences and §7.3's four rules,
all of which are established facts about the tree rather than opinions.

### The W11b row, to be added to `docs/TASKS-v3-web.md` in the same commit as W11's archived plan

Placed immediately after W11 in Phase C, with **no migration number claimed** —
every table it reads exists and it writes nothing:

> `| **W11b** | Sunday weekly report | AGENT | The Sunday surface PRD §4.2 gives
> four words to. **Read-only: it writes nothing and adds no table, no column and
> no migration.** `week_summary(user_id, week_ending, now)` over `sessions`,
> `item_attempts`, `card_reviews`, `user_unit_state` and `user_lexemes`; `GET
> /week`; the report page. **Sunday's home shows the report as the primary and
> does NOT show a session call-to-action** — §4.2 calls Sunday's emptiness
> deliberate and non-negotiable, so a Sunday that acquires a task is a defect.
> The session stays reachable behind a low-emphasis link: *free extensive input,
> tracked but never required.* **Block 1 is NOT suppressed on Sunday** — that
> would skip a day of the FSRS schedule for every card and shift every interval,
> a scheduler change made by a calendar rule; #160 already keeps `/review`
> reachable without a count and that shape is reused. **What it cannot report on
> is named in W11's plan §7.2 and is not to be filled with a substitute:** XP
> (W19, `sessions.xp` is NULL on every row), input minutes (W12/W13), speaking
> (W14–W16), mastery (#135, no metric), coverage trend (#197, unruled), and
> **free extensive input, which PRD §4.2 says is tracked and which nothing
> tracks.** | The report renders on a phone on a Sunday. **On an empty week it
> renders no numeric zero at all** — a zero on a report is a score, and a score
> of zero on a week nobody promised anything about is guilt with no banned word
> in it. No backlog count anywhere in the payload
> (`test_no_surface_presents_a_backlog_count` and `test_session_route.py`'s
> banned-key scan both extended to it). Nothing on the surface asks the learner
> to do anything. |`

### The design W11b starts from

**Ship it minimal, as a read-only surface that does not touch the daily
session's block machinery.**

- `core.services.sessions.week_summary(user_id, *, week_ending, now)` — one pure
  read returning: days with a completed session, total minutes, cards reviewed,
  items answered and how many were right, units passed this week (0 or 1), words
  moved to `known`. **No percentages against a target, no streak, no XP, no
  count of anything not done.**
- `GET /week` in `apps/api/routers/session.py` — plain `def`, one service call.
- `apps/web/app/(app)/week/page.tsx` — the report.
- **Home on Sunday:** the report is the primary. The session is reachable behind
  a low-emphasis link ("practise anyway"), which is *free extensive input,
  never required*. The "Start today's session" button is **not** shown on
  Sunday. Nothing on the surface asks for anything.

**Why not suppress block 1 on Sunday.** It was the live alternative. Forcing the
review block empty on Sunday would skip a day of the FSRS schedule for every
card and shift every interval — a change to the scheduler made by a calendar
rule. #160's ruling keeps `/review` reachable *without a count* for exactly this
case, and that is the shape reused rather than a second one invented.

**What it renders in week one — and this is both learners' state.**
Zero sessions, zero cards, zero items, no unit passed. **It must not render a
table of zeros.** The empty state is one line — *"Your first week is still
going. Nothing to report yet."* — and a test asserts the surface renders **no
numeric zero at all** when the week is empty, in the shape of the guilt test:
a zero on a report is a score, and a score of zero on a week nobody promised
anything about is guilt with no banned word in it.

**Cost:** one service function, one route, one page, four or five strings, and
its tests. Small — smaller than the checkpoint by a wide margin, which is part of
why the split costs nothing to make.

**What W11 itself builds of §7: nothing.** No `week_summary`, no `/week`, no
page, no Sunday change to home. The section is a finding and a handover.

**The one thing W11 must NOT do, said here because it is the way a split leaks.**
W11's checkpoint surface must not grow a "your week" summary of its own on the
ceremony screen. The pass ceremony says one unit was passed; it does not report
minutes, cards, items or days. If it did, W11b would arrive to find its surface
half-built somewhere else, and two surfaces would compute the same numbers two
ways. **Held by review, not by a test — there is nothing yet to assert against.**

---

# §8. DDL — the finding is WITHDRAWN. W11 takes 018.

**REVISION 2 SAID W11 NEEDS NO MIGRATION AND `schema_version` STAYS AT 17. THAT
WAS WRONG, AND IT WAS WRONG IN THE ONE PLACE A POSITIVE FINDING IS DANGEROUS: IT
WAS THE CELL THAT ASSERTED *the checkpoint sitting → `sessions` with `task_type =
'checkpoint'` → no DDL*, AND THAT CELL WAS LOAD-BEARING FOR THE ATTEMPT KEY.**

The error was in what it checked. Revision 2 verified that `sessions.task_type`
is a bare `TEXT` with **no CHECK to widen** — true, and #47 does not fire — and
read that as *no DDL needed*. **The constraint the checkpoint needs is not a
CHECK on the value; it is a UNIQUE on the row**, and 016's index is partial
`WHERE task_type = 'daily'`, so it does not reach. *Nothing forbids the value* and
*nothing forbids two rows* are different questions, and only the first was asked.

**W11 TAKES 018. `schema_version` 17 → 18.** One partial unique index (§5.1), and
nothing else — the file is one statement plus its header.

**THIS IS #185's FIFTH OCCURRENCE, and the count is verified against #185's own
row rather than copied from anywhere.** That row's title records **three**
(W4b renumbered eight rows, W8f five, W10b's plan four);
`docs/TASKS-v3-web.md:148` records the **fourth** once W10b actually took 017.
This is the fifth. **Taken honestly rather than avoided** — a fifth occurrence is
cheaper than a sitting counted twice, and the policy alternative #185 already
records (*assign a number when the FILE is written, not when the slice is
planned*) is restated in 018's header as the thing this occurrence is evidence
for, without adopting it here.

**Every row that shifts, in BOTH halves of `docs/TASKS-v3-web.md`, in the same
commit as the `.sql` file:**

| slice | was | becomes |
|---|---|---|
| **W11** | *(no row)* | **018** — `sessions_one_checkpoint_per_user_per_date` |
| W12 | 018 | **019** |
| W13a | 019 | **020** |
| W14 | 020 | **021** |
| W18 | 021 | **022** |

**Taking 022 instead — above everything claimed — is refused for W4b's recorded
reason**, restated because it is the whole point of the scheme: it would *work*
on production, where `db.py`'s pending set is a set difference, and **break
replay on a fresh database**, where the runner applies in ascending numeric order
— so W12's later 018 would run *before* 022 there and *after* it here, and its
file would have to be correct against two different parent schemas.

**This is not #49.** #49 was a slice shipping a number the table did not know
about. Here the table is corrected in the same commit and the renumbered slices
**have not been written**: nothing on disk, nothing applied to any database, no
`schema_version` row moved.

**PRODUCT-PRINCIPLES §2 position, restated for the migration:** 018 adds **no
table and no column** — it is an index on `sessions`, whose `user_id` has
referenced `users(id)` since 011. No user-keyed table is added and no new
dependency on a Telegram id. **PRODUCT-PRINCIPLES §3:** it materialises nothing;
it forbids a duplicate.

**#48 is not triggered** — there is no `ALTER TABLE users` in the file, so the
paired view recreate is not required and is deliberately absent. Stated rather
than omitted, because #48 has recurred by each case looking like the one where
the rule did not apply.

**#167 IS RECORDED IN 018's HEADER, which is what its row asked for.** Revision 2
had to record the reason in the decisions log *because there was no `.sql` file*;
there is now. The reason is unchanged: `blueprint.py:249` reads `sum(per_target)
+ lexeme_items`, `lexeme_items` is pinned at 0, and **#170 hands the second term
back at W13** — so a CHECK written now needs widening in two slices, over a table
whose only writer takes validated content. **The validator stays the only place
the invariant lives, and 018 says so in the file, beside a migration that had the
opportunity to do otherwise.**

## What still needs no DDL — the rest of the table stands

Everything else W11 stores already has a home, and this list is unchanged from
revision 2 apart from the one row that moved:

| what W11 stores | where | DDL? |
|---|---|---|
| the unit's state, per learner | `user_unit_state.state` | no — 014 |
| the pass and its clock | `user_unit_state.passed_at` | no — 014 |
| the score that passed | `user_unit_state.last_checkpoint_score` | no — 014 |
| attempt count | `user_unit_state.checkpoint_attempts` | no — 014 |
| the 4-day retake | `user_unit_state.retake_due_on` (`DATE`) | no — 014 |
| when the learner reached the unit | `user_unit_state.entered_at` | no — 014 |
| the checkpoint sitting itself | `sessions` with `task_type = 'checkpoint'`. The **value** needs nothing — `sessions.task_type` is a bare `TEXT NOT NULL` with no CHECK (001:107), so #47 does not fire, checked as 016 checked it for `'daily'`. **But ONE ROW PER SITTING needs 018's partial unique index**, and that is the cell revision 2 got wrong | **YES — 018** |
| which unit the sitting was for | `sessions.payload` JSONB — v2's per-task-type grab bag, which is exactly what a per-task-type fact belongs in (`reading` and `book_test` already use it this way) | no |
| the twelve answers | `item_attempts`, with `session_id` pointing at the checkpoint session | no — 012 |
| the missed targets | **computed** from `item_attempts` ⋈ `items.payload->>'grammar_target'` | no |
| the within-unit day | **computed** from `entered_at` and the learner's timezone | no |

**`sessions.task_type` gains a fourteenth value, `'checkpoint'`, with no
constraint to widen** — checked rather than assumed, as 016's header records for
`'daily'`, with the contrast being `errors.source`, whose CHECK *did* have to be
widened once at 012. **That check was right and is unchanged. What revision 2 did
was stop there**, and the row-uniqueness question was the one that mattered.

**#167 is ANSWERED, and now in the place its row asked for.** Its text offers
two options: mirror `sum(per_target) = 12` into a SQL CHECK, or **record in the
migration** why the validator is the only place it lives. Revision 2 could take
neither — it had no `.sql` file — and settled for the decisions log. **018 exists,
so the second option is taken as written**: the reason goes in 018's header,
beside a migration that had the opportunity to add the CHECK and declined. The
reason is #170's, unchanged: `blueprint.py:249` reads `sum(per_target) +
lexeme_items`, `lexeme_items` is pinned at 0 today, and **#170 hands the second
term back at W13** — so a CHECK written now needs widening in two slices, over a
table whose only writer (`upsert_units`) takes validated content. **Answered, not
closed:** the asymmetry that made it worth filing now has a stated reason in the
layer it was filed against.

---

# §9. WHAT THIS PLAN DOES NOT DECIDE

For each: what the plan needs, what it does under each possible answer, where it
stops.

**#135 — the mastery metric.**
*Needs:* a metric and a threshold for "retained performance 3+ weeks later".
*Does:* **nothing writes `mastered` in W11.** 014 supplies the interval and the
two timestamps; `record_checkpoint` never produces `mastered` and
`ALLOWED_TRANSITIONS["passed"]` keeps the move legal for whoever defines it.
*Stops:* the plan does not invent a rule. A guessed mastery rule is
indistinguishable from a specified one in six months.

**#197 — the coverage floor.**
*Needs:* raise the reference, lower the floor, or accept that a grammar item may
carry one word outside B1. **Now owed against two numbers** — W10c's P7 and
W10b's L7 (lowest 91.37%).
*Does:* the checkpoint run **measures and reports** coverage per item against
`coverage_reference()`, exactly as W10c does, and enforces nothing.
`test_a_low_coverage_item_is_reported_and_NOT_rejected` and
`test_the_floor_itself_is_not_lowered` both still hold.
*Stops:* no gate is added and 0.90 is not touched.

**#207's open half — the checkpoint blueprint's `item_types`.**
*Needs:* whether the seven permitted types in all 24 units narrow.
*Does:* `permitted` is a parameter with a default derived from the data (§3.5);
the four possible rulings and what each changes are tabulated there.
*Stops:* the plan narrows nothing and edits no `data/syllabus_units.json` row.
**Note the standing consequence: one of the seven, `match_pairs`, has no
reachable model gate (#192) and is 3 of the 14 live items.**

**#212 — unit 2's fourth grammar target.**
*Needs:* a ruling on whether *'present perfect or past simple: is the time
finished?'* is a teachable target or a label the classifier cannot separate.
*Does:* nothing. W11's checkpoint is unit 1's; unit 2's checkpoint is the next
one a learner reaches and the ruling is owed before then, not before this.
*Stops:* no target is reworded — that changes `data/syllabus_units.json`, every
`checkpoint.per_target` key referencing it, and the stored `syllabus_units` row.

**#228's two sub-questions.**
*Needs:* (i) whether a failed **composite** item re-queues its **components**
too; (ii) whether an 80% pass mark computed over **overlapping** targets means
what it says. Unit 1 allocates **3 of 12** items to a target that properly
contains two of the other three.
*Does:* `missed_targets` (§4.2) returns the composite's own string when a
composite item is failed, and **does not expand it into its components** —
because expanding is (i)'s answer and it has not been given. Containment is
**read from `GrammarTarget.contains`** wherever the plan needs it and is never
re-derived from wording, per the #237 ruling.
*Stops:* the 80% is not adjusted, reweighted or recomputed. If the operator
rules that overlap makes 80% mean something else, that is a change to
`per_target` or to the mark, and both are rule-7 territory.

**#188's unanswered half.**
*Needs:* whether the daily repeat is tolerable until W11 lands, or block 4 ships
empty in the meantime.
*Does:* nothing, and it is now nearly moot — #216 closed on 2026-08-28 with the
repeat **confirmed on a screen** and the judgement not given. W11 removes the
symptom for unit 1 and **reproduces it for unit 2** (§6.4), so the question
survives the slice.
*Stops:* the plan does not ship block 4 empty and does not add a rotation.

**#245 — RULED 2026-08-29 and therefore NOT on this list.** *Section advances per
completed session, not per calendar day; when sections run out before Saturday,
block 3 shows practice only — no new teaching, no repeated section.* Implemented
per §6.0–§6.3. **#245 closes when the paced block 3 has been read on a screen**,
not when the code lands — the row exists because a person read the live lessons
and judged the pacing, and only a person can judge whether the new pacing is
right. One sub-question is left open **inside** the ruling and is flagged rather
than assumed (§6.1): whether "completed session" means the session was completed
or the **focus block** was completed. The plan takes the strict reading — the
focus block — because the looser one advances a learner past a section they
never saw. **A one-clause change if that is the wrong reading.**

---

# §10. TEST LIST — with the red demonstrations marked

**RED** = the guard is demonstrated failing before it is accepted, and the red
run is reported in the update block. A recorded-response test proves a branch is
reachable, never that a model takes it.

### The state machine and its seam

**38 tests, 20 of them demonstrated RED. Numbered 1–38 with no gaps, including
the #169 and #194 tests, which revision 2 left named beside a count.** The count
is at the end of the list as well as here, and both are produced by parsing it —
revision 1 skipped 21 and 22 when the Sunday tests moved to W11b, which is the
kind of thing a stated-then-re-derived count exists to prevent.

1. **RED** `test_may_move_is_reached_by_the_real_write_path` — a real database
    row at `passed`; `record_checkpoint` attempting `in_progress` raises. Red by
    stubbing the guard out of the service. **This and test 2 together are #219's
    answer**, and they are the tests in this slice whose absence would leave the
    enumeration decoration for an eleventh time.
2. **RED** `test_may_enter_is_reached_by_the_real_entry_path` — `record_unit_entry`
    refuses a state `may_enter` rejects, asserted against **the function that
    actually calls it** (§5.1). Red the same way. **New in this revision:** the
    first draft had `record_checkpoint` call `may_enter` on a no-row branch that
    `record_unit_entry` guarantees is never reached, so the guard would have been
    exercised only by a path that never runs.
3. **RED** `test_only_one_module_writes_user_unit_state` — a boundary scan in
    `tests/test_core_boundary.py`, in the shape of
    `test_exactly_one_module_writes_an_item`. **Module level, so it covers both
    writers.** Red by adding a second writing module.
4. `test_a_learner_enters_at_available_or_in_progress` — the rewritten
    `test_a_learner_enters_only_at_available`, old assertion quoted in the
    docstring; **`passed` and `mastered` still refused, asserted explicitly**
    (§5.2), because a widened rule that is not shown to still refuse anything is
    not shown to be a rule.
5. `test_a_pass_is_never_undone` — through the service, both directions.
6. **RED** `test_the_same_sitting_scored_twice_bumps_nothing` — the attempt key
    (§5.1). Two `POST /checkpoint/complete` calls for one `sessions` row leave
    one increment and one `retake_due_on`. **Red by removing the `AND completed =
    FALSE` claim**, which is the whole guard. **Rewritten in this revision:** the
    first draft asserted this against `UNIQUE (user_id, unit_number)`, which is a
    row key and not an attempt key, so the test could not have held.
7. `test_a_genuine_retake_does_bump` — the other side of 6: a **different**
    checkpoint `sessions` row increments. Without this, 6 passes on a writer that
    never increments at all.
8. **RED** `test_two_creations_on_one_day_produce_one_sitting` — **the test the
    send-back asked for, and it is the one that makes 6 mean anything.** Two calls
    to `GET /checkpoint/today` for one learner on one local date leave **one**
    `sessions` row. Red by dropping **018's partial unique index**, not by
    changing Python: without the index, `ON CONFLICT DO NOTHING` has nothing to
    conflict on and both inserts succeed. **That red run is the evidence that the
    migration is load-bearing** rather than tidy — which is exactly the claim
    revision 2 got wrong, so it is proved rather than asserted.
9. `test_a_retake_four_days_later_is_a_second_sitting` — a **different local
    date** creates a second row, so test 8's index constrains a double tap and not a
    retake. Without this, test 8 passes on an index that forbids retakes.

### The checkpoint's shape

10. **RED** `test_a_checkpoint_is_twelve_items_in_the_blueprints_proportions` —
    `checkpoint_slot_plan(unit 1)` is 4/3/3/2 across the four targets. Red by
    returning `slot_plan`'s eight.
11. **RED** `test_a_short_bank_yields_no_checkpoint_rather_than_a_short_one` —
    `checkpoint_items` with 11 eligible returns empty. **Red by returning what it
    has**, which is the failure rule 7 exists to prevent.
12. **RED** `test_a_checkpoint_never_serves_an_item_this_learner_has_attempted` —
    with an `item_attempts` row present, that item is excluded. Red by dropping
    the `NOT EXISTS`.
13. **RED** `test_block_three_does_not_serve_the_checkpoint_cohort` — an
    unattempted `cohort = 'checkpoint'` item is absent from `focus_items`, and an
    item with **no** `cohort` key is present, which is what the 14 live rows are.
    Red by dropping the exclusion.
14. **RED** `test_a_later_top_up_run_does_not_move_the_reserve` — **the test the
    send-back specified, and the one that discriminates the two mechanisms.**
    Generate a checkpoint cohort, then a later block-3 cohort, then assert
    `checkpoint_items` still resolves to the checkpoint's twelve. **Red against a
    `created_at DESC LIMIT 12` implementation**, where it resolves to eight
    top-up items and four checkpoint ones; green against the declared cohort.
    Written this way round deliberately: the red run is what proves revision 2's
    recency proxy was broken rather than merely suspected.
15. `test_ten_of_twelve_passes_and_nine_does_not` — the 80% boundary, both sides,
    computed from `item_attempts.correct`.
16. `test_the_permitted_type_set_is_a_parameter` — passing a narrowed set
    changes the plan and the ceiling; nothing is hardcoded (§3.5).
17. **RED** `test_a_reweighted_retake_cohort_is_selected_whole` — a retake
    cohort in **6/3/2/1**, not the blueprint's 4/3/3/2, is selected complete.
    **Red against a selector that fills `per_target`**, where it returns nothing
    and the retake never opens. **This is the fail path's own test**, and its red
    run is what proves the two halves of the plan had disagreed.
18. **RED** `test_a_cohort_that_does_not_match_its_own_plan_is_refused` — rows
    that cannot fill the map `checkpoint_slot_plan` produces yield **nothing**,
    never a partial sitting. Red by serving what is there. Without 18, 17
    passes on a selector that simply takes any twelve.
19. **RED** `test_the_ceiling_is_computed_from_the_slot_plan_not_a_constant` —
    changing `PROBED_FAMILIES` or the slot count moves the printed number. Red by
    replacing the function with a literal.

### The fail path

20. `test_a_failed_checkpoint_leaves_the_unit_in_progress` — through the service.
21. `test_the_retake_is_four_days_out_in_the_learners_timezone` — injected `now`,
    walked across local midnight. **No wall-clock dependency** (CLAUDE.md §3
    rule 6): both sides computed the same way, no hardcoded date.
22. **RED** `test_missed_targets_come_from_attempts_and_not_from_error_types` —
    a failed composite item yields the composite's own target string, and the
    query returns nothing when `items.error_type` is NULL (which it is on every
    live row). Red by keying the query on `error_type`.
23. `test_nothing_is_written_to_errors_by_the_checkpoint` — a scan asserting no
    `INSERT INTO errors` is reachable from the checkpoint path. **This is the
    guard that keeps §4's decision honest** against a later slice that "adds it
    back".
24. **RED** `test_a_composite_targets_components_are_not_expanded` — #228(i) is
    unruled, so expansion must not happen by accident. Red by expanding.

### The unfreeze

25. **RED** `test_a_passed_row_advances_current_unit` — through
    `GET /session/today` on the ASGI transport (CLAUDE.md §3 rule 1), not through
    a direct service call. Red by writing `state='passed'` with a NULL
    `passed_at` — which 014 refuses, proving the constraint is reached.
26. `test_block_three_renders_its_empty_state_for_a_unit_with_no_lesson_or_items`
    — the day-after-the-pass shape, asserted rather than discovered (§6.4).

### The Sunday report — **W11b's, not W11's**

Listed so they are not lost in the split, and **not written in W11**:
`test_the_weekly_report_presents_no_backlog_count` (RED),
`test_an_empty_week_renders_no_zero` (RED),
`test_sunday_offers_no_task` (RED). They belong to the W11b row added in §7.4.

### Copy — W11's own

27. `test_no_banned_phrase_in_any_new_string` — every string W11 adds, through
    `tests/support/no_guilt.py`, backend and frontend. That is the ceremony
    copy, the silent-re-queue copy, the retake line, the not-ready line, and
    §6.2's teaching-complete line.
28. **RED** `test_a_failed_checkpoint_shows_no_score_and_no_bar` — the fail path
    renders nothing a learner reads as a mark: no "10 of 12", no fraction, no
    progress bar against 80%. Red by rendering the score. **`last_checkpoint_score`
    is stored because 014 requires a pass to name the score that passed; storing
    it is not licence to show it**, and *drops are silent* is the rule that
    settles which.

### Standing

29. `test_nothing_is_generated_while_the_learner_waits` — extended to the
    checkpoint route through session-wide `netguard`, structurally rather than by
    intention.
30. `test_the_floor_itself_is_not_lowered` and
    `test_a_low_coverage_item_is_reported_and_NOT_rejected` — unchanged and must
    stay green (#197).

### #194 — does W11 carry it?

**Yes, and it is cheap.** `TargetVerdict`'s ranking, claimed rank, runner-up and
confidence become four fields on `ValidationReport` and four keys in `as_json()`.
`items.validation` is JSONB and 012's CHECK **requires three keys rather than
forbidding a fourth**, so there is no migration. The runner-up is the sharp loss:
on an item that passed, second place is the distinction it came closest to
blurring.

31. `test_the_target_verdict_survives_into_items_validation` — the ranking, the
    claimed rank, **the runner-up** and the confidence are readable back out of
    `items.validation` after a write. Numbered rather than named (C2).

### The pacing clock (#245, ruled)

32. **RED** `test_a_skipped_day_loses_no_section` — a learner with `entered_at`
    five days ago and **two** completed focus blocks sees section index 2, not 5.
    Red by computing from the calendar. **This is the ruling's whole point and it
    is the one assertion that distinguishes it from what was declined.**
33. **RED** `test_a_session_completed_without_the_focus_block_does_not_advance` —
    `block_breakdown.focus != 'done'` does not move the index. Red by counting
    `completed_at IS NOT NULL`. *(If the looser reading is what was meant, this
    test is deleted rather than inverted, and the deletion is recorded.)*
34. **RED** `test_when_the_sections_run_out_block_three_shows_practice_only` —
    index ≥ section count yields `lesson_section: null`, `teaching_complete:
    true`, items unchanged, **and no section opened**. Red by repeating the last
    section, which is the behaviour the ruling names and forbids.
35. `test_no_lesson_and_teaching_complete_are_different_payloads` — a unit with
    no lesson and a unit whose teaching is finished must not render the same
    line. This is `empty`-versus-`unavailable`'s reasoning one level in, and it
    is the failure that would otherwise tell a learner *"the explanation is on
    its way"* about teaching they have already read.
36. `test_the_index_is_computed_in_the_learners_timezone` — injected `now`,
    walked across local midnight, both sides computed the same way (rule 6).
37. `test_the_section_index_restarts_at_zero_on_the_next_unit` — scoped to the
    unit, per §6.4.

### #169 — the checkpoint-level uniqueness pass

**Carried, and it is a new gate rather than a wider old one.** W5a's probe is
per item and is structurally unable to see two items in the same checkpoint
asking the same question in different words — and unit 1 puts 4 items on one
target and 3 on another. The pass runs **over the 12 as a set**, after every
item has passed its own gates, and asks a blind solver whether any two of them
test the same thing. It is one batched call per cohort, on the ceiling.
**It is not solved by lowering the item count** — that is the bar #166 was closed
to protect. If it rejects, the cohort is topped up, not trimmed.

38. `test_the_cohort_pass_sees_two_items_asking_one_question` — a fixture pair of
    distinct items testing the identical point is rejected as a **set**, where
    each passes on its own. **A recorded-response test: it proves the branch is
    reachable, never that a model takes it** — which is the standing rule for
    every gate in this project and is why the pass is also on the ceiling and in
    H3's reading.

### The numbered total

**38 tests, 20 of them demonstrated RED.** Numbered 1–38 with no gaps, and **the
#194 and #169 tests are numbered rather than left named beside a count** (C2):
**31** is #194's, **32–37** are the pacing clock's, **38** is #169's cohort pass.
Counted by parsing the list rather than by adding up section headings — this
record states counts and then has to re-derive them, and revision 3's own count
of *36* was one renumber out of date the moment condition 1 added two tests.

---

# §11. HUMAN CHECK LIST — what only a person can establish

**H1 (free, read-only, and it unblocks §3).** On the host, as `bot`:

```bash
sudo -u bot psql english_bot -c "SELECT id, unit_number, item_type, payload->>'grammar_target' AS target FROM items WHERE user_id = 3 ORDER BY unit_number, id;"
```

`set +H` first (#151). **This is the query that establishes which of unit 1's
four targets its four live items were written against** — the repository cannot
answer it (§3.0), and the whole 4/3/3/2 supply arithmetic depends on it.

**H2. Command 0a, re-run before anything ships.** Standing W11 precondition; its
answer changes every time anything is deployed. The record's last recorded
production SHA is `c353189`; `bddce38` is a record-only commit that appears
nowhere in `BUILD_PROGRESS.md`. **Do not reconcile either from a document — the
observed value is what is recorded.**

**H3. Read the 12 generated checkpoint items before a learner sees them.**
The acceptance step no gate replaces. (a) Does each read as a question rather
than a fragment; is the gap somewhere sensible; do twelve in a row feel like a
test or like a form? (b) **Are any two of them the same question in different
words** — #169's human half, and the only instrument that has ever caught this.
(c) **Is any of them a sentence the learner already read in unit 1's lesson**
(#239) — the operator has read that lesson and is the only person who can.
(d) The Farsi in any `l1_to_l2_production` prompt.

**H4. Take the checkpoint on a phone.** Twelve items, one sitting. Does the
ceremony on a pass read as celebration rather than a score report? Does a
**failure** say nothing that could be read as blame — no score shown as a
fraction of a bar, no "you needed 10", nothing about the four days that reads as
a punishment?

**H5b. The day after a checkpoint cohort is generated — count block 3's items.**
§3.2a's residual is that the reserve can leave block 3 *thin* rather than empty,
and revision 2 called that H-checked when no H check covered it. This is it:
open the session the morning after a `--checkpoint --apply` run and **count the
practice items.** Expect block 3 to serve what the unit holds **outside** the
checkpoint cohort — which, for unit 1 before a block-3 top-up, is **four**, not
eight. Fewer than that, or zero, means the suspension is not firing and the
reserve is starving the session; report it and do not sit the checkpoint.

**H5. The day after a pass.** Open the daily session and read blocks 3 and 4.
**Expect unit 2, no lesson, three practice items, a different writing task, and
the section counter restarted at zero.** This is §6.4's costed regression and it
is only visible on a second calendar day. If unit 2's lesson and items have not
been generated first, this is what a learner sees.

**H6. The paced block 3, on a screen, across two days — and this is what closes
#245.** Day one of a unit shows section 1 open and the rest collapsed. **Skip a
day deliberately**, then open a session: it must show section 2, not section 3.
Then keep going until the sections run out and confirm block 3 shows **practice
only** — no new teaching and no section re-opened. **No test can make this
judgement**: the row exists because a person read the live lessons and judged the
pacing, and only a person can judge whether the new pacing reads better than the
old one.

**H7. ~~The pacing ruling.~~ RULED 2026-08-29.** Retired from this list as a
question and replaced by H6, which is the check the ruling now owes. Recorded
rather than deleted, so a reader of an earlier draft does not go looking for it.

**H8 (W11b's, listed so the split does not lose it).** Sunday, on a phone: is
anything on the screen asking for something? Is there a number anywhere that
counts what was not done? On an empty week, is there a zero anywhere?

**Carried, and nothing drops off because it got old** — the full list is in the
update block's Next action, §12(f). **W10 check 4 is CLOSED** (#216, 2026-08-28)
and is the one thing that has left this list; **its second half — whether the
repeat was tolerable — was never answered** and stays with #188.

---

# §12. THE `BUILD_PROGRESS.md` UPDATE BLOCK — what implementation applies

## (a) The slice rows — **two**, and both new

There is no W11 row in the Slice status table today (verified by reading all 96
rows: the table ends at W10r). **Two rows are added**, per the split ruling:
W11 at 🟡, and **W11b at ⬜ not started** — a scheduled slice with a row, which
is what makes it a schedule rather than a deferral.

> `| W11b | Sunday weekly report | ⬜ not started | | Scheduled by operator
> ruling 2026-08-29 when W11's scope was split. **Read-only, no migration.**
> Its findings are already in hand: W11's plan §7.1 enumerates what a week of
> this system's data can honestly say and §7.2 names what it cannot, from real
> tables. **Free extensive input, which PRD §4.2 says is tracked, is tracked by
> nothing** — the report states the absence rather than filling it. |`

**Checked against `tests/test_record_consistency.py` before proposing the row,
because W10b's renumber already made that check fail once.** The relevant
fixtures were read:

- `slice_claims` takes rows between `## Slice status` and `Status key:`, skips
  any row with fewer than **5 cells**, and matches migrations in the **Notes**
  cell by `_MIGRATION_REF = migration\s*\**\s*(\d{3})` — **three digits
  required, immediately after the word.** The W11b row has 5 cells and its Notes
  say *"no migration"* with no digits, so it enters no claim. **Safe.**
- `build_columns` records a slice only if its **Build** cell matches that same
  regex. W11b's names no number, so it is absent from the fixture, and
  `test_every_authoritative_row_has_a_build_column_naming_it` iterates the
  *authoritative* rows, which W11b does not join. **Safe.**
- `test_every_migration_file_on_disk_has_an_inventory_row` — W11 adds no
  migration file. **Safe.**
- `_SLICE_ID = ^\*{0,2}(W\d+[a-z]?)\*{0,2}$` matches `W11b` and `**W11b**`.
  **Safe.**

**The constraint this puts on the edits, stated so implementation does not trip
it:** neither W11's nor W11b's row may contain the literal `migration NNN`. W11's
Build cell today says *"No migration number is claimed"* and *"016 W10 → 017
W10b → 018 W12"* — **the digits are not adjacent to the word, so it matches
nothing and W11 is not in `build_columns` today.** Any rewording that puts a
three-digit number straight after "migration" would enter a claim and could fail
`test_no_build_column_names_a_migration_the_table_does_not`.

And W11's own:

> `| W11 | Checkpoints | 🟡 code-complete | <date> | **The first
> writer of `user_unit_state`. Migration 018** (`sessions_one_checkpoint_per_user_per_date`,
> one partial unique index and nothing else) — **`schema_version` 17 → 18**, and
> **#185's FIFTH occurrence, taken honestly**: W12 018→019, W13a 019→020,
> W14 020→021, W18 021→022, in both halves of `docs/TASKS-v3-web.md` and in the
> same commit as the `.sql` file. The
> checkpoint's twelve items are generated by a new `--checkpoint` mode on the
> existing generator, human-run (#196, ruling 1), against the unit's blueprint —
> **the first thing in this tree ever to read `checkpoint.per_target` for
> anything but validation.** Entry rule: `may_enter` widens to admit
> `in_progress`; **ruling 2 is untouched — W11 still writes no `available` row.**
> Enforcement seam: **ONE MODULE, TWO FUNCTIONS** — `record_unit_entry` calls
> `states.may_enter`, `record_checkpoint` calls `states.may_move`, each before
> its SQL, and `record_checkpoint` has **no no-row branch**: it raises, because a
> checkpoint on a unit nobody entered is a bug in the caller. **#219's
> enumeration gets its first callers and BOTH guards are demonstrated red through
> the paths that actually call them.** The retake's selector fills **the cohort's
> own quotas**, produced by the same `checkpoint_slot_plan` the generator used —
> the blueprint's for a first sitting, the re-weighted map for a retake — so a
> re-weighted retake cohort can be selected at all. The fail path ships its
> bookkeeping half and **not** PRD §3's block-1 injection; the acceptance
> criterion in `docs/TASKS-v3-web.md` is corrected in place with its old text
> quoted, and the gap is filed. **#167 is ANSWERED in 018's header** — the
> migration its row asked for, which W11 now has — the validator staying the only
> place `sum(per_target) = 12` lives, because #170 hands `blueprint.py:249`'s
> second term back at W13. #194 is carried. **BLOCK 3 IS PACED** on the operator's ruling of 2026-08-29 — one
> section per **completed session**, not per calendar day, so a skipped day
> loses no teaching; when the sections run out block 3 shows practice only. The
> position is **computed from the session log**, not stored. **THE SUNDAY REPORT
> IS NOT IN THIS SLICE** — the scope was split by operator ruling on 2026-08-29
> and W11b carries it, with a row of its own added in the same commit as this
> plan's archive. **W11 STAYS 🟡 — the human owns that column, and nothing here
> is verified until the checkpoint has been taken on a phone and the paced block
> 3 has been read across two days.** |`

**`schema_version` moves 17 → 18.** Revision 2's slice row said it stays at 17
and that was wrong for the reason §8 now records: the checkpoint's sitting needs
one row per learner per date, 016's index is partial `WHERE task_type = 'daily'`,
and a value with no CHECK to widen is not the same fact as a row with no UNIQUE
to enforce.

**The slice's NAME changes with the split**, and it is changed rather than left
to read as a promise the row does not keep: `docs/TASKS-v3-web.md`'s W11 row is
titled *Checkpoints + weekly rhythm* and the Slice status row is added as
**Checkpoints**. The TASKS title is corrected in the same commit with its old
text quoted (see the edit list in §12(g)).

## (b) The #207 row correction, in place, old wording quoted

The row reads `⬜ open` and a decisions entry dated 2026-08-27 records `#207
RULED — option (c)`. **Both are half right and the row is stale.** Corrected to,
with the old Status text quoted in place:

> ~~`⬜ open — **blocks the type mix, not the run.**`~~ *(the Status as it read
> until \<date\>; quoted rather than deleted, per #82's shape)*
>
> `🟡 HALF RULED, 2026-08-27 — and the two halves are different questions.`
> **RULED:** the *generator's* draft slot mix, option (c) — `mcq` and
> `collocation_pick` dropped for grammar-targeted items, implemented in
> `core.items.generate.SLOT_TYPES` and named in `DROPPED_FOR_GRAMMAR`, with
> **#208 filed from the implementation** (dropping `mcq` from `SLOT_TYPES` stops
> one being drafted, not one being produced by `repair.LADDER`).
> **STILL OPEN AND STILL THE OPERATOR'S:** the *checkpoint blueprint's*
> `item_types` — **seven types permitted in all 24 units**, `match_pairs` among
> them, **which has no reachable model gate (#192) and is 3 of the 14 live
> items.** W11 makes the permitted set a parameter so the ruling can set it
> without a code change, and tabulates what changes under each answer; it
> narrows nothing.

**Which family this is a sighting of — determined by reading the family rows,
not asserted from a count.** #82 is *documents written as a plan and read as a
description* — not this: #207's Status was accurate when written and went stale
when a ruling landed **elsewhere in the same file**. #214 is *one row carrying
both halves of a contradiction, outside `test_record_consistency`'s reach because
there is no second artefact* — not this either: here there **are** two artefacts,
the known-issues Status column and the decisions log. **It is #132's family** —
*two hand-maintained records of one fact with nothing checking that they agree*,
the family #130 is explicitly named as sharing (`#132: "Same shape as #130"`)
and which #214 extends.

**It is a new site for that family — and the claim about the test's reach is now
READ rather than asserted, which the send-back was right to demand.**
`tests/test_record_consistency.py` was opened. Its four fixtures are
`progress_lines` (the file with `## Superseded` blocks stripped), `slice_claims`
(rows between `## Slice status` and `Status key:`), `inventory_claims` (rows
between `## File inventory` and `## Verification checklist`), and `tasks_lines`
plus its two halves. **There is no fixture, no regex and no assertion anywhere in
the file that opens the `## Known issues` table or the `## Decisions log`.** The
module docstring says what it is for in its own words — *"parse the slice table
and the inventory"* — and it does exactly that. **So the new row stands.**

**Filed as its own new row rather than reopening #130**, because #130 closed on a
check scoped to `docs/TASKS-v3-web.md` and this is a different document and a
different pair of artefacts. **Numbered 252.** Severity `low`, originating slice
W10c → target W19 (with the records work, beside #214's blind spot).

## (c) Decisions log entries — every one, with reasons and declined alternatives

Newest first, each dated, each with authorship recorded honestly (**assistant-recommended,
operator-accepted** where that is what happened; **never** as an operator ruling
that was not given):

0a. **OPERATOR RULING, 2026-08-29 — #245 IS RULED. SECTION ADVANCES PER
   COMPLETED SESSION, NOT PER CALENDAR DAY; WHEN SECTIONS RUN OUT BEFORE
   SATURDAY, BLOCK 3 SHOWS PRACTICE ONLY — NO NEW TEACHING, NO REPEATED
   SECTION.** *Recorded as the operator's ruling, with its date.* **It is
   neither of the two options the plan costed, and the third is better than
   both, for a reason worth keeping:** a calendar clock makes a missed day a
   *lost section* — teaching deleted by the calendar, never presented as a
   backlog and therefore never caught. CLAUDE.md §4 says missed days shrink the
   task and never pile up; under a calendar rule they do neither. A session
   counter makes the unit take as long as the learner takes and nothing is ever
   behind. **Declined by the ruling:** (A) the single-open accordion suffices —
   zero cost, but #245 stays open exactly as filed; (B) one section per calendar
   day — the option the plan costed and the one whose own strongest
   counter-argument the ruling answers. **The position is COMPUTED from the
   session log and stored nowhere** (PRODUCT-PRINCIPLES §3, flagged at the moment
   of the choice). **One sub-question is left open inside the ruling and is
   flagged rather than assumed:** the plan reads "completed session" strictly, as
   *the focus block was completed* (`block_breakdown->>'focus' = 'done'`),
   because the looser reading advances a learner past a section they never saw.
   A one-clause change if that is the wrong reading. **#245 closes on a screen,
   not on green tests** — the row exists because a person judged the pacing.

0b. **OPERATOR RULING, 2026-08-29 — W11's SCOPE IS SPLIT. W11 IS THE CHECKPOINT;
   W11b IS THE SUNDAY WEEKLY REPORT, AND IT GETS A ROW IN THE SAME COMMIT AS
   THIS PLAN'S ARCHIVE, SO IT IS A SCHEDULED SLICE AND NOT A DEFERRAL.**
   *Assistant-raised as a concern under CLAUDE.md §8, operator-ruled.* The two
   halves share no code: the report reads `sessions`, `item_attempts`,
   `card_reviews`, `user_unit_state` and `user_lexemes` and writes nothing.
   **The condition on the split, and it is the whole reason it is not a
   deferral: W11's §7 still ran.** The plan enumerates what a week of this
   system's data can honestly say and what it cannot — from real tables, today —
   and hands that to W11b, so W11b starts from evidence rather than from PRD
   §4.2's four words. **The failure this avoids** is a slice discovering at
   implementation time that half of what it promised needs W12–W16. **W11 builds
   none of it**, and specifically the pass ceremony does not grow a week summary
   of its own — that would half-build W11b's surface somewhere else and compute
   the same numbers two ways.

1. **W11 TAKES MIGRATION 018 — one partial unique index — AND THIS REVERSES A
   FINDING THIS PLAN PUBLISHED TWICE.** Revisions 1 and 2 recorded *W11 needs no
   migration* as a **positive finding**, on a check that was correct and
   insufficient: `sessions.task_type` is a bare `TEXT` with no CHECK to widen
   (001:107, checked as 016 checked it for `'daily'`), so **#47 does not fire**
   — and that answers *may the value exist*, not *may there be two rows*. 016's
   uniqueness index is partial `WHERE task_type = 'daily'` and does not reach a
   checkpoint row, so `GET /checkpoint/today`'s `ON CONFLICT DO NOTHING` had
   nothing to conflict on and a refetch would have created **two sittings**,
   each claiming cleanly, bumping `checkpoint_attempts` twice and moving
   `retake_due_on` twice. **The attempt key (4b) rested on a row the plan never
   said how to create.** Everything else in §8's table stands: the state, the
   score, the retake date, the twelve answers, the missed targets and the
   within-unit position all need no DDL, and the last two are **computed**,
   which is PRODUCT-PRINCIPLES §3's own preference.
   **#185's FIFTH occurrence**, verified against #185's own row (three in its
   title; the fourth at `TASKS-v3-web.md:148` when W10b took 017) — **taken
   rather than avoided**, because a number above everything claimed breaks
   replay on a fresh database (W4b's recorded reason) and because a fifth
   occurrence is cheaper than a sitting counted twice. W12 019, W13a 020,
   W14 021, W18 022, both halves, same commit.
   **A recorded positive finding that turns out to be wrong is worth more than
   an absence**: it was written down as a claim, so review could test it — which
   is what happened.
2. **THE ENFORCEMENT SEAM (#219) — ONE MODULE, TWO FUNCTIONS, each calling the
   guard that applies to it.** `record_unit_entry` calls `may_enter`;
   `record_checkpoint` calls `may_move` and has **no no-row branch** — it raises,
   because a checkpoint on a unit nobody entered is a bug in the caller, not an
   occasion to invent an entry. **Both guards are demonstrated red through the
   function that actually calls them** (tests 1 and 2). The boundary test names
   one **module** — `core.services.syllabus` — as the only writer of
   `user_unit_state`, which is what makes "one seam" true.
   *(This entry read "**one service function, calling the enumerated state
   machine**" until the approval conditions of 2026-08-29, and §5.1 had already
   corrected it. Quoted rather than deleted because the correction is
   load-bearing: it decides which function each guard test exercises, and the
   version it replaces would have left `may_enter` reached only by a branch that
   never runs — #219's own family arriving inside the fix for it.)*
   Declined: writing straight to SQL with 014's CHECKs as the only guard. Reason
   it was declined rather than preferred: **014's CHECKs are row-local and cannot
   express a transition at all** — a `CHECK` never sees the predecessor row and
   only a trigger could, which this project does not use — so "the CHECKs are
   enough" is not a lighter guard, it is no transition guard, and it permits the
   one move the module forbids outright (`passed → in_progress` nulling
   `passed_at`). Assistant-recommended, operator-accepted.
3. **OPERATOR RULING, 2026-08-29 — THE ENTRY RULE (#217) IS CANDIDATE (b):
   `may_enter` WIDENS TO ADMIT `in_progress`, AND `entered_at` IS RESTATED AS
   "WHEN THIS LEARNER FIRST REACHED THIS UNIT".** *Recorded as the operator's
   ruling with its date, not as an assistant decision.* **Ruling 2 (2026-08-27)
   is untouched — W11 still writes no `available` row.** Declined: **(a) W11
   writes `available`** — *this one would have REVERSED ruling 2 and was
   therefore the operator's alone*; tidiest against the machine as written, but
   it puts W9's availability predicate in W11 with no surface to render it,
   which is what ruling 2 declined. **(c) `available` + `passed` in one
   transaction** — it creates `entered_at` at the moment of the pass, which is
   the very objection `may_enter` raises against what it refuses, and **it has
   no story for the fail path**: a first-attempt failure writes no `passed`, so
   no row exists and `retake_due_on` has nowhere to live. (b) additionally gives
   §6's clock the lower bound it counts sessions from, which (a) also does and
   (c) does not.
   **THE OLD TEXT IS QUOTED IN PLACE, NOT DELETED, IN BOTH SITES:**
   `states.py:94-102`'s docstring (*"Only `available` is. A unit cannot be
   created already in progress: the `entered_at` of a row that skipped
   `available` would be a fact about a moment that never happened, and W19's
   history reads these timestamps."*) keeps that sentence as the quoted prior
   rule above the new one; and
   `tests/test_syllabus_states.py::test_a_learner_enters_only_at_available`
   keeps its old assertion quoted in the renamed test's docstring.
   **AND WHAT `may_enter` NOW REFUSES IS STATED, because a rule that admits
   everything is not a rule:** `passed` — which every one of 014's CHECKs would
   accept as a first row given `passed_at` and a score ≥ 80, so this is the only
   thing that stops it, and it is exactly the write `record_checkpoint` produces
   if the entry write is ever skipped; `mastered` — which would claim a 21-day
   retention interval on a row created seconds ago; and `locked`, which
   `validate()` refuses with its own message before `may_enter` is reached. The
   widening moves **one** value across the line and the rule still divides the
   four storable states two-and-two.
4. **THE RE-QUEUE — W11 delivers the bookkeeping half and computes the missed
   targets; it does NOT inject them into block 1.** Declined: **(a) errors + an
   error card** — `error_types` cannot name the target (three of unit 1's four
   are `verb_tense_past` and the fourth has no code), `items.error_type` is NULL
   on every generated row because the field is in `NOT_THE_GENERATORS`, no
   errors→card path exists, and a tapped wrong option is not a self-produced
   error, so **every row it wrote would be a wrong row and a wrong row is
   permanent damage.** **(c) re-serving the failed items** — re-queues items,
   not targets, and re-serving the exact items just failed is #239 one slice on.
   **(d) nothing** — leaves the fail path with bookkeeping only, which is what
   (b) improves on for the price of one computed query.
   `docs/TASKS-v3-web.md`'s W11 Accept is corrected in place with the old text
   quoted; PRD §3 and §4.2 are **not** amended.
4a. **THE CHECKPOINT'S RESERVE — the cohort is DECLARED on the item, as
   `cohort` in `items.payload`; `focus_items` excludes an unattempted checkpoint
   item and `checkpoint_items` selects one.** No DDL — `payload_of` derives
   `items.payload` by **subtracting** the promoted columns, so a new `BaseItem`
   field persists from the moment it exists. **This is `grammar_target`'s exact
   precedent (W10c), and the precedent is the argument.** It joins
   `NOT_THE_GENERATORS` and `projection.NEVER_VISIBLE` for the reasons already
   written beside `grammar_target` in both.
   **DECLINED, AND THIS ONE IS A CORRECTION TO REVISION 2 RATHER THAN AN
   ALTERNATIVE CONSIDERED: recency (`created_at DESC LIMIT 12`).** It is a proxy
   for the cohort that holds only while the checkpoint run is the unit's most
   recent generation, **which this slice's own arithmetic guarantees it is
   not** — 8 + 12 = 20 means two runs, and a top-up after the checkpoint makes
   the newest twelve *eight top-up items plus four checkpoint ones*. **It does
   not fail loudly; it silently protects the wrong rows.** An ordering constraint
   would patch it and is **not** adopted: a scheduling rule on a human-run
   command with no mechanism behind it is one out-of-order evening from being
   wrong again with nothing to say so. Declined: a **`created_at` window** —
   needs a duration nobody can justify. Declined: **`reserved_for_checkpoint` as
   a column** — but §3's flag is against materialising what could be *computed*,
   and **the cohort cannot be computed**: it is a fact about a run's intent that
   nothing else records, which is the same argument W10c made for
   `grammar_target`.
   **The precedence rule survives unchanged and is still the decision, not the
   mechanism:** daily practice beats a weekly checkpoint, so when the two compete
   block 3 wins and the checkpoint refuses *loudly*. **The arithmetic it forces
   into the open: a unit needs 8 + 12 = 20 unattempted items, TWO generation runs
   per unit.** Unit 1 holds four.

4b. **`record_checkpoint`'s ATTEMPT KEY is the checkpoint's own `sessions` row,
   claimed with `UPDATE … WHERE completed = FALSE RETURNING id`** — and **the row
   is created by `GET /checkpoint/today` with `INSERT … ON CONFLICT DO NOTHING`,
   made idempotent by 018's partial unique index** (decision 1). `UNIQUE
   (user_id, unit_number)` is a row key, not an attempt key: without the claim a
   double submit bumps `checkpoint_attempts` **and moves `retake_due_on`**.
   `sessions.completed` and `completed_at` are 001's columns, and the database
   decides rather than a read-then-write — the instrument `_get_or_create_daily`
   already relies on. **Revision 2 named the claim and never said what created
   the row it claims, which is the half that needed the migration.**

4c. **#107 IS RE-TARGETED W11 → W16**, old target quoted in place, because W11
   decides it writes nothing to `errors` and an issue left pointing at a slice
   that shipped without it is the drift W10 named when it re-targeted six issues
   off itself. **W16 is Writing output — free written production, corrected —
   the first surface where a learner produces a sentence that is genuinely
   theirs.** Declined: **W15**, whose surfaces are ASR-scored and which 012's own
   harvest table classifies as *not harvested*.

4d. **THE `entered_at` BACKFILL is a one-off human-run data step, not code.**
   Both learners have been in unit 1 since 2026-08-27 and would otherwise restart
   at section 1 of a lesson one of them has read in full. The value is their
   earliest `sessions.date` for `task_type = 'daily'`, which is already in the
   database. Declined: **a backfill branch inside `record_unit_entry`** — a
   permanent conditional serving two learners once, which is what W4a's repair
   and W7's chunk pass were both kept out of their migrations for. Declined:
   **accepting the restart** — not harmful, but indistinguishable from the bug,
   which would make H6 unreadable.

5. **THE ITEM SUPPLY — a `--checkpoint` mode on the existing generator, not a
   second generator.** Reason: every gate, the journal, the dry run, the control
   fixture, the top-up round and the single `insert_item` writer are reused, so
   `test_exactly_one_module_writes_an_item` stays unexempted and #59 remains the
   only boundary exemption. The ceiling is **computed in code and printed by the
   dry run**, never written in a document — W10b and W10c both published the
   expected case labelled as a ceiling and both were wrong.
6. **THE SECOND LEARNER HAS NO CHECKPOINT UNTIL #159's CONSUMER 3 LANDS**, and
   the plan states it rather than discovering it. Established from the tree:
   `generator_system_prompt()` substitutes only `{contract}`, the template asks
   for "the learner's own script" and is never told which, and
   `L1ToL2ProductionItem.l1` defaults to `"fa"`.
7. **#167 ANSWERED, AND IN THE PLACE ITS ROW ASKED FOR: the validator stays the
   only place `sum(per_target) = 12` lives, and the reason goes in 018's
   header.** #167 offers two options — mirror the sum into a SQL CHECK, or
   *record in the migration* why the validator is the only place it lives.
   Revisions 1 and 2 could take neither and settled for the decisions log,
   because W11 had no `.sql` file. **It has one now**, so the second option is
   taken as written, beside a migration that had the opportunity to add the
   CHECK and declined. The reason is unchanged: #170 hands `blueprint.py:249`'s
   second term back at W13, so a CHECK written now needs widening in two slices,
   over a table whose only writer takes validated content.
8. **#194 IS CARRIED:** four fields on `ValidationReport`, four keys in
   `as_json()`, no migration — 012's CHECK requires three keys rather than
   forbidding a fourth. The runner-up is the field the generator prompt's next
   author actually needs.
9. **THE SUNDAY REPORT'S DESIGN IS HANDED TO W11b, NOT BUILT** (see 0b). The
   design that goes with it, so W11b does not re-derive it: minimal, read-only,
   and it does **not** touch the daily session's block machinery. Declined
   there and recorded here because it was the live alternative: **suppressing
   block 1 on Sunday** — it would skip a day of the FSRS schedule for every card
   and shift every interval, a scheduler change made by a calendar rule. #160's
   ruling already keeps `/review` reachable without a count, and that shape is
   reused rather than a second one invented.
10. **THE CLOCK IS COMPUTED, NOT STORED.** PRODUCT-PRINCIPLES §3 flag recorded at
    the moment of the choice: a `section_index` column would materialise
    per-user-per-unit state the session log already determines, and it would need
    something to advance it — a job that does not exist (#69) or a write on a
    read path. The computed form also **self-heals**: a session row corrected
    later moves the index with it. **Verified rather than assumed while choosing
    it:** `sessions_one_daily_per_user_per_date` is a partial UNIQUE index
    (016 §2), so there is at most one daily session per learner per local date
    and a session counter cannot run away.

## (d) New known issues — severity, originating slice, target slice

**Numbered, not labelled `new`.** The highest issue number in the record is
**245**, counted by parsing the table rather than read off the last row, so these
take **246–252** in the order below and §14 carries the same numbers. Two of the
first draft's seven rows are gone: the block-3 reserve is **solved in §3.2a**
rather than filed, and the `entered_at` restatement is folded into #217's own
row where the ruling that caused it lives. Four are new to this revision.

| # | issue | sev | slice |
|---|---|---|---|
| **246** | **`--live` AND `--apply` ARE TWO BILLED RUNS AND THEY WRITE DIFFERENT ITEMS — #235's defect in the item generator, where the lesson generator has an `apply-from-journal` path and this one has none.** `main()` routes both into the same `run(...)`, which calls `verify_cohort` either way and differs only in whether it writes; the parser's own error says *"--live and --apply are alternatives; --apply implies --live"*. **So the items an operator reads in a `--live` run are not the items an `--apply` run writes** — the cohort is regenerated and the model is stochastic. #235 ruled that *the bytes the operator reads are the bytes that ship*; that ruling was implemented for lessons and the item generator was never brought to it. **Not fixed here:** an apply-from-journal path for items is a real piece of work (the journal stores outcomes, not the live `BaseItem`s `--apply` needs), and W11 works around it — dry run then `--apply`, never `--live` then `--apply`. | medium | W10c → **the generator slice** |
| **247** | **A DEPLOY LINE IN THIS RECORD CANNOT HAVE PRODUCED THE RESULT RECORDED AGAINST IT: W10b's liveness probe reads `https://app.foundgrant.com/session/today`, and that host cannot return `401` from `english-api`.** `app.` is a CNAME to Vercel; `apps/web/next.config.ts` declares **no `rewrites`** and there is **no `middleware.ts`** anywhere under `apps/web`, so the browser calls the API directly through `NEXT_PUBLIC_API_URL` and that path reaches a Next route that does not exist. Caddy serves `api.foundgrant.com` → `127.0.0.1:8000` and does not serve `app.`, so the recorded `502`-inside-the-startup-window is only producible on `api.` **`app.` appears exactly once in this record; `api.` is what every other probe uses, including three earlier ones at this identical path.** **#215's shape, and filed WITHOUT an inference about what anyone typed** — that inference is what #215 was corrected for on 2026-08-28. **What is asked is what was actually run**, not what the line says. | medium | W10b → **the deploy-runbook slice** |
| **248** | **PRD §3's "missed targets injected into the next week's review queue" has no mechanism and W11 does not build one** — it needs an `errors → card` path that does not exist (V5: one `INSERT INTO cards` in the tree, fed by chunks and capture), an error-card type with no writer, and #107's classification over a code set that cannot name the target. The acceptance criterion is corrected in place; this is the gap it leaves. | medium | W11 → **W16** |
| **249** | **Passing unit 1 removes the only lesson that exists and halves the practice items** (§6.4). Mitigated by a human generation step before the first checkpoint is offered, which is a **scheduling** mitigation and not a code one — so it holds only as long as someone runs it. | medium | W11 → W12 |
| **250** | **A learner who finishes a unit's teaching before Saturday sees block 3 with no new section, and nothing tells them a checkpoint is coming.** The ruled pacing produces a legitimate state — practice only — that reads as the lesson having run out rather than as the week having a destination. **Deliberately not fixed here:** a "checkpoint on Saturday" line is a *task presented in advance*, and whether that is motivation or pressure is a teaching judgement. | low | W11 → operator ruling |
| **251** | **ONE OF TWO LEARNERS HAS A PERMANENTLY NOT-READY SATURDAY, WITH NO DATE ON IT.** The Lithuanian learner has zero items in every unit and cannot be generated for until #159's consumer 3 lands, so **every Saturday renders the not-ready state indefinitely** — established, not predicted: `generator_system_prompt()` substitutes only `{contract}`, `item_generate.txt` asks for *"the learner's own script"* and is never told which, and `L1ToL2ProductionItem.l1` defaults to `"fa"`. **Filed as its own row rather than left as a scope note inside a plan section**, because *the second learner is out of scope* is a statement about the slice and *one learner has a dead surface every week* is a statement about a person. | **high** | W10 → **the generator slice** (the one that carries #159's consumer 3 — the generator prompt is where the L1 must be passed, so it is the generator's slice and not a records one) |
| **252** | **The known-issues Status column and the decisions log are two hand-maintained records of one fact and nothing checks they agree** — #207 read `⬜ open` for a day after a decisions entry recorded it ruled. **#132's family in a fourth site.** Outside `tests/test_record_consistency.py`'s reach by construction, **confirmed by reading the test rather than asserted**: its fixtures parse `## Slice status`, `## File inventory` and both halves of `docs/TASKS-v3-web.md`, and nothing in the file opens the `## Known issues` Status column or the `## Decisions log`. | low | W10c → W19 |

**Not filed, and why — recorded so their absence is a decision rather than an
omission.** The block-3 reserve is **solved in §3.2a**; filing it would have
shipped a Saturday that never opens. `entered_at`'s restatement is folded into
**#217's own row**, where the ruling that caused it lives, rather than given a
row that would be read without it. **Free extensive input going untracked** moves
to **W11b's row** with §7.2's other absences, since W11b is the slice that would
have reported it.

**Carried forward, still open, re-confirmed against W11:** #69, #82, #102,
#120, #130-family, #135, #159 (consumer 3 — now also blocking #251), #167
(**answered in this plan, closing on verification**), #168, #169, #170, #185,
#188 (its unanswered half), #192, #194, #197, #207 (half), #212, #214,
#222/#223/#232 (the deploy family), #228, #231, #235, #239, #241–#245.

**#107, #217 and #219 are NOT in that list and NOT closed — the first draft put
them in both places at once.** A decision in a plan closes nothing; W11 is 🟡
until the operator marks it.

- **#107 — RE-TARGETED W11 → W16**, with the old target quoted in place and the
  reason on the row (§4.2). It leaves W11 rather than being carried by it.
- **#217 — ANSWERED by the operator's ruling of 2026-08-29 (candidate b),
  closing on verification.** The answer is a ruling; what remains is the code
  landing and the entry test running green.
- **#219 — ANSWERED, closing on the guard being REACHED BY THE REAL WRITE PATH**
  — which is tests 1 and 2 green after §5.1's correction, and nothing less.
  #219 is the eleventh appearance of *a guarantee never evaluated against the
  thing it names*; closing it on a plan's intention would be the twelfth.

## (e) File inventory — every new file, with its purpose

| file | purpose |
|---|---|
| `packages/core/syllabus/checkpoint.py` | pure: `checkpoint_slot_plan`, the 12-slot expansion of `per_target`, the permitted-type parameter, the pass computation. No SQL, no HTTP, no model call. |
| `packages/core/services/checkpoints.py` *(or additions to `services/syllabus.py` and `services/items.py` — decided at implementation, one home, not two)* | `record_checkpoint`, `record_unit_entry`, `missed_targets`, `checkpoint_items`, `unit_section_index`. **The only writer of `user_unit_state`.** |
| `migrations/018_checkpoint.sql` | **The only DDL: `sessions_one_checkpoint_per_user_per_date`, a partial unique index.** Its header carries #167's reason (the validator stays the only place `sum(per_target) = 12` lives, because #170 hands `blueprint.py:249`'s second term back at W13), #185's fifth occurrence and the policy alternative that row already records, the #48 non-trigger, and the PRODUCT-PRINCIPLES §2/§3 positions (no table, no column, nothing materialised). |
| `apps/api/routers/checkpoint.py` | `GET /checkpoint/today` (creates the sitting idempotently, mirroring `_get_or_create_daily`), `POST /checkpoint/answer`, `POST /checkpoint/complete` (claims, then scores). Plain `def`. Parses, authorises, calls one service function, serialises. |
| `apps/web/app/(app)/checkpoint/page.tsx` + `components/checkpoint/*` | the sitting, the ceremony, the silent re-queue. Reuses the eleven item renderers. |
| `tests/test_checkpoint_states.py` | the seam and the entry rule, including the two RED guards. |
| `tests/test_checkpoint_supply.py` | the slot plan, the selector, the short-bank refusal, the ceiling function. |
| `tests/test_checkpoint_route.py` | through the ASGI transport, per CLAUDE.md §3 rule 1. |
| `tests/test_unit_pacing.py` | the six pacing tests, three of them RED (§10 32–37). |
| `prompts/CC-W11-checkpoints-PLAN.md` | this plan, archived per CLAUDE.md's `prompts/` exception. |

**NOT in W11's inventory, per the split:** `apps/web/app/(app)/week/page.tsx`,
`components/week/*`, `tests/test_week_report.py`, and `week_summary` in
`core/services/sessions.py`. They are W11b's, listed here only so the split does
not silently drop them.

**Modified, not new:** `core/items/generate.py` (the `--checkpoint` mode and the
ceiling function), **`core/items/schema.py`** (the `cohort` field on `BaseItem`,
plus `NOT_THE_GENERATORS`), **`core/items/projection.py`** (`NEVER_VISIBLE`),
**`core/services/items.py`** (`focus_items`' exclusion and `checkpoint_items`),
**`.gitignore`** (the checkpoint journal, beside the other two, under #231's
existing note), `core/items/gates.py` + `ValidationReport` (#194),
`core/syllabus/states.py` (`may_enter` widened, `entered_at` restated, both with
the old text quoted in place), `tests/test_syllabus_states.py` (the renamed entry
test, old assertion quoted), `core/services/sessions.py` (`_focus_block` takes
the section index and its payload gains `lesson_section` and `teaching_complete`),
`apps/web/components/lessons/lesson.tsx` (`LessonBody` opens the served section,
or none), `apps/web/components/session/blocks.tsx` and its copy file (the
teaching-complete line), `docs/TASKS-v3-web.md` (§12(g)).

## Document edits accompanying this block — `docs/TASKS-v3-web.md`

*(Not one of the required (a)–(f) items; listed here because the block is applied
in the same commit and a document edit made without being named is how the two
halves of this record drift.)*

**Six edits now, and two of them touch the authoritative migration table** —
revision 2 said none did, on the no-migration finding §8 has since withdrawn.
W11 takes **018**; W11b still claims no number.

0. **The authoritative migration table** gains a **W11 → 018** row and shifts
   **W12 018→019, W13a 019→020, W14 020→021, W18 021→022.**
0a. **The per-slice Build columns for W12, W13a, W14 and W18** shift by the same
   one, because nothing reconciles the two halves (#130's check asserts they
   agree, so a half-done renumber fails it — which is the check working).
   **W11's own Build column gains its number**, and the phrasing must keep
   `migration` and a three-digit number **non-adjacent** or it enters a claim in
   `build_columns` (see §12(a)).

1. **The W11 Accept column** — corrected per §4.2, old text quoted.
2. **The W11 title** — *"Checkpoints + weekly rhythm"* → *"Checkpoints"*, old
   title quoted in place, with the split ruling and its date named. A title
   promising a weekly rhythm on a slice that ships a checkpoint is the shape
   #82 describes.
3. **The W11 Build column** — the Sunday clause struck with its old text quoted
   (*"**Sunday: no tasks, weekly report, free extensive input, tracked and never
   required**"*) and re-pointed at W11b, **with ruling 3's finding restated so it
   is not re-derived: no PRD amendment is owed — §4.2 is unchanged and still
   describes the target; what changed is which slice delivers it.** That is the
   same move ruling 3 made for Mon–Fri, applied to Sunday.
4. **A new W11b row**, immediately after W11 in Phase C — text in §7.4.

**And the paragraph under the W11 row** gains one sentence: the three reasons the
slice was moved to `PLAN` mode on 2026-08-27 all held — it is the first writer of a
user-keyed table (confirmed by grep, V7), it changes a shipped surface's
behaviour (§6.4), and **it needed DDL after all** (§8) — recorded because
all three reasons for the mode change were vindicated, and the third only under
review: revision 2 asserted no migration and revision 3 withdrew it. **The mode
change is what caught it.**

## (f) Next action — this slice's checks plus every earlier check still unrun

Rewritten whole. **Nothing drops off because it got old, and nothing is carried
silently.**

- **Command 0a — the standing W11 precondition.** Re-run before anything ships;
  its answer changes every time anything is deployed. Last recorded production
  SHA `c353189`; `bddce38` is record-only and appears nowhere in this file.
  **Do not reconcile from a document.**
- **W10 check 4 — CLOSED 2026-08-28 (#216).** Its **second half — whether the
  repeat is tolerable — was never answered** and stays with #188. Recorded as a
  half-answered check rather than rounded into "check 4 done".
- **W10r's check 0b — grade a card in block 1, both paths — still UNRUN**, and
  still the one thing outstanding for W10r's completion.
- **W10c's six** — 1, 4, 5 and 6 unrun; 2 and 3 partly evidenced on the
  operator's report and **not run**.
- **W10's other five** (1, 2, 3, 5, 6) — unrun.
- **W10a's two** — unrun.
- **W8h's two** — both phone checks, unrun.
- **W8b's two** — unrun; check 2 has changed shape.
- **W8f's checks 4 and 5** — *nobody has looked at an imported card on a phone.*
- **W8's five content checks** — 1, 3 and 5 run · 2 blocked · **4 stays
  RETIRED**.
- **The 21 carried items — counted, not estimated**, including the typography
  pick at `https://app.foundgrant.com/type`. *(Implementation re-counts them from
  the carried-forward sections at the moment it writes this block and reports the
  number it found, whether or not it is 21.)*
- **W11's own: H1–H6 in §11 above.** H7 is retired as a question — **#245 was
  ruled on 2026-08-29** — and H6 is the check the ruling now owes.
- **H8 is W11b's** and is listed on this record from the moment W11b's row
  exists, not from the moment W11b starts.
- **W11's unruled operator questions, unchanged and still four: #135, #197,
  #207's open half, #212 — plus #228's two sub-questions.** **#245 is no longer
  among them.** Any implementation that assumes a value for one of the remaining
  six is wrong on that point.
- **One sub-question sits INSIDE a ruling and is flagged rather than assumed:**
  whether "completed session" in the #245 ruling means the session was completed
  or the **focus block** was. The plan takes the strict reading; a send-back
  changes one clause.

---

# §13. THE DEPLOY AND GENERATION SEQUENCE — for the operator

**Claude Code has no SSH access to this host and never will.** Every step below
is a command for the operator to run. Paths: `/home/bot/english-bot`, reached
with `sudo -u bot` from `root@78.46.240.136`. **Never `ssh bot@<host>`. Never
`/opt`. `english-worker` is not named — it is not installed (#69), and nothing
scheduled has ever run on this host.**

**Step 0 — push and verify, before anything else (#223).**
```bash
git push origin main && git log --oneline -1 origin/main
```
Must match local `HEAD`. Every deploy here pulls from `origin`; without this the
pull reports *already up to date* and exits 0 behind a green run.

**Step 0a — which commit is production actually running.** The standing
precondition. Re-read here; the answer changes every time anything ships.
```bash
cd /home/bot/english-bot && sudo -u bot git rev-parse --short HEAD && sudo -u bot git status --porcelain
```
The SHA must equal `origin/main` after step 0.

**THE STATUS RULE — #231's three-way split, carried in full.** The first draft of
this plan collapsed it back to *any non-empty status is a `high` finding*, which
is the rule #231 exists to correct, **and this slice is the one that most needs
the correction**: the checkpoint run writes its journal at the repo root, so the
collapsed rule would fire on every deploy after a run and train the operator to
wave past the one check that catches a genuine host edit.

- **`M`, `D`, `A`, or any tracked file modified → `high` finding, a NEW ISSUE,
  never a tidy-up.** Somebody has edited the deployed tree. Unchanged.
- **`??` at a known generator path — the journals named in `.gitignore` — is
  expected and is not a finding.**
- **`??` at any OTHER path is still a finding**: something is on this host that
  nobody put in the repository.

**Whoever runs this does not clean the tree either way.**

**`.gitignore` is edited in this slice** to add the checkpoint journal's default
path, beside `w10c-journal.jsonl` and `w10b-journal.jsonl`, which are already
there with #231's reasoning written above them. **Read rather than assumed: the
file already carries that block**, so this is one line in an existing section and
not a new policy.

**Step 1 — backup.**
```bash
cd /home/bot/english-bot && sudo -u bot ./scripts/backup.sh
```
Record the filename, the byte size and the R2 confirmation.

**Steps 2–4 — pull, install, migrate. The settled order, restored.**
```bash
cd /home/bot/english-bot && sudo -u bot git pull --ff-only
sudo -u bot .venv/bin/pip install -e packages/core
sudo -u bot .venv/bin/python -m core.db migrate
```

**`--ff-only`, and the first draft dropped it.** It fails rather than writing a
merge commit into the production checkout, and it is what every executed deploy
in this record used — #222 closed on *"fast-forward `d1a52db..97df56e`, five
files, no merge"*.

**`migrate`, not `status`, and revision 1 substituted the wrong one.** The
settled order is backup → pull → install → **migrate** → restart. Revision 2
restored it while still believing W11 had no migration, on #222's precedent that
the step verifies even when it applies nothing. **W11 now HAS one**, so the step
applies rather than verifies: expect **`Applied: 018`** and then **`Applied:
001–018, Pending: (none)`**, pasted verbatim. **This is the first migration since
017.**

**Step 1's backup is therefore not optional.** `pg_dump` before every migration
against production, and 018 is a migration — the same sentence W10b's sequence
carries for 017.

**Step 5 — restart `english-api` ONLY.**
```bash
sudo systemctl restart english-api
```
`english-bot` is deliberately not restarted. `english-worker` is not installed
and is not named (#69).

**Step 6 — prove it is live, with a retry. SEPARATE COMMAND (#232).**
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' https://api.foundgrant.com/session/today)
  echo "attempt $i: $code"
  [ "$code" = "401" ] && break
  sleep 2
done
```
Expect **`401`** within the first two or three attempts. Live is proven by the
`401`, never by `active (running)` — a service that dies on import is briefly
active too. If the loop finishes without a `401`, that is a real failure: read
`journalctl -u english-api -n 50 --no-pager` and stop.

**THE HOST QUESTION IS SETTLED BY READING, NOT BY CHOOSING — and the answer is
`api.foundgrant.com`.** The send-back is right that the record disagrees with
itself, and the disagreement resolves cleanly:

- **`app.foundgrant.com` appears exactly once in this record** — W10b's probe
  line — while **`api.foundgrant.com` is what every other probe uses, including
  three earlier ones at this identical path `/session/today`.**
- **`app.` is a CNAME to Vercel** (Environment table). **`apps/web/next.config.ts`
  declares no `rewrites`** — it is `reactStrictMode` plus the PWA wrapper and
  nothing else — **and there is no `middleware.ts` anywhere under `apps/web`**.
  The browser calls the API directly through `NEXT_PUBLIC_API_URL`. So
  `app.foundgrant.com/session/today` reaches a Next route that does not exist and
  **cannot return `401` from `english-api`.**
- **Caddy owns `api.foundgrant.com` and reverse-proxies it to `127.0.0.1:8000`;
  it does not serve `app.`** So the observed `502`-inside-the-startup-window —
  which the record attributes to Caddy answering into the gap — **is only
  producible on `api.`**

**The line as written could not have produced the result recorded against it.
That is #215's shape and it is filed as such — and it is filed WITHOUT an
inference about what anyone typed at the keyboard**, because that inference is
precisely what #215 was corrected for on 2026-08-28. The operator is asked what
was actually run; the plan states only what the line cannot have done.

**Step 7 — the backfill (§6.1a), before any learner opens a session.** Read
first, write second, read again. Written out in full in §13a below.

**Step 8 — H1, the free read (§11).**

**Step 9 — the dry run. Zero billed calls. Read the ceiling it prints.**
```bash
cd /home/bot/english-bot && sudo -u bot .venv/bin/python -m core.items.generate --checkpoint --user 3 --units 1
```
**Flags verified against `generate.py:1766-1800` rather than written from
memory:** `--user` (int, **required unless `--report`**, no default by design),
`--units` (comma-separated, default `1,2,3`), `--live`, `--apply`, `--journal`,
`--report`, `--skip-control` all exist today. **`--checkpoint` and `--retake` are
this slice's to add** and are the only two new ones.

**Step 10 — the billed run, on the host, attended.**
```bash
cd /home/bot/english-bot && sudo -u bot .venv/bin/python -m core.items.generate --checkpoint --user 3 --units 1 --apply
```
**Dry run then `--apply`. NOT `--live` then `--apply`, and the first draft had it
backwards.** `main()` routes both into the same `run(...)`, which calls
`verify_cohort` either way and differs only in whether it writes; the parser
itself says *"--live and --apply are alternatives; --apply implies --live"*. So
`--live` followed by `--apply` **bills twice and writes items nobody read** — the
cohort is regenerated and the model is stochastic. **Never on the Mac:** a local
`--apply` writes to the dev database, prints the same success, and its failure
mode is silence.

**A block-3 top-up run is a SECOND `--apply`** (§3.2a's arithmetic: a unit needs
8 + 12 = 20 unattempted items). Its ceiling is printed by its own dry run.

**Step 11 — count the rows independently of the command that wrote them**
(CLAUDE.md §3 rule 5). `set +H` first (#151).

**Step 12 — H3, before a learner sees anything.** Then H4, H5, H6.

## §13a. Step 7 in full — the `entered_at` backfill (§6.1a)

**Two learners, one unit, one row each. Read, write, read.** `set +H` first
(#151). All three as `bot`, from `/home/bot/english-bot`.

**7a — read what exists, before writing anything.**
```bash
sudo -u bot psql english_bot -c "SELECT u.id, min(s.date) AS first_daily, count(*) FILTER (WHERE s.block_breakdown->>'focus' = 'done') AS focus_done FROM users u LEFT JOIN sessions s ON s.user_id = u.id AND s.task_type = 'daily' GROUP BY u.id ORDER BY u.id;"
```

**THIS QUERY IS NOT SCOPED BY UNIT, AND IT IS ONLY CORRECT BECAUSE NO LEARNER HAS
EVER LEFT UNIT 1** — established by V6 (`current_unit` selects on `passed_at IS
NOT NULL`) and V7 (`user_unit_state` has no writer, so it is empty). Every daily
session either learner has ever had was a unit-1 session, so `min(s.date)` over
all of them *is* the date they reached unit 1. **Said in the step rather than
left to be inferred: run this after any learner has passed a unit and it gives
the wrong backfill**, silently — it would date unit 2's entry from their first
day in unit 1. This step is spent after it runs once and must not be re-run
later as if it were general.
**Paste the output.** `first_daily` is the value 7b writes; `focus_done` is the
section index each learner will land on. **If `focus_done` for either learner
exceeds the number of sections in unit 1's lesson, that learner lands in the
teaching-complete state on day one** — which is correct under the ruling and is
what H6 must be run against, so it is read here rather than discovered on a
phone.

**7b — the write. `state = 'in_progress'`, unit 1, both learners. Idempotent, and
it only ever moves `entered_at` BACKWARDS.** The exact statement is authored at
implementation time against 7a's output and reviewed before it runs; its shape:

```sql
INSERT INTO user_unit_state (user_id, unit_number, state, entered_at)
VALUES (%s, 1, 'in_progress', %s)          -- %s = that learner's first_daily
ON CONFLICT (user_id, unit_number) DO UPDATE
   SET entered_at = LEAST(excluded.entered_at, user_unit_state.entered_at)
```

**`'in_progress'` and not `'available'`**: it is what `record_unit_entry` would
have written under the ruled entry rule (b), and a backfilled row in a state W11
never writes would be a row no code path can explain. **`LEAST` is the
idempotency** — re-running cannot push a learner forward, and running it after
`record_unit_entry` has already fired is safe.

**THIS STATEMENT BYPASSES `may_enter`, DELIBERATELY, AND IT IS THE ONLY SANCTIONED
BYPASS IN THE SLICE.** Recorded here rather than left unremarked, because an
unremarked bypass **in the same slice that gives the guard its first caller** is
exactly how the guard stops meaning anything — which is #219's family arriving
through the back door of a data step. Three things make it acceptable and they
are stated as conditions, not as reassurance: the value it writes (`in_progress`,
unit 1) is a value `may_enter` **admits**, so the bypass changes nothing the
guard would have decided; it runs **once**, by hand, under review, and is spent;
and it is **not in the codebase**, so no code path acquires a way around the
seam. **If any of the three stops being true, this is not a data step any more.**

**7c — read again, and read the index rather than the timestamp.** Re-run 7a and
confirm `entered_at` now equals `first_daily` for both learners. **The number
that matters is the section index**, so print it: it is what H6 is checked
against, and a backfill verified only by its timestamp has not been verified
against the thing it was done for.

**If 7a shows either learner already has a `user_unit_state` row, STOP.** V7
establishes there are none today; a row that exists is something this plan does
not know about, and that is a finding, not an obstacle to work around.

---

**No production entrypoint is run at any point** — no `python -m apps.bot.main`,
no polling loop, no message sent on a learner's behalf. **No broad `apt
upgrade`, no reboot, no restart of a system-wide service, no Caddy change, and
no destructive Postgres command** — the host is shared with `fonderis-worker`
and PostgreSQL serves both projects.

---

# §14. Anything found and not fixed — filed with a severity and a target

**Seven, numbered 246–252, identical to §12(d)'s table** — restated as a list so
nothing lives only inside a table, and carrying the same numbers so the two
statements of the same seven cannot disagree (which is #252's own defect).

1. **#246** — `--live` and `--apply` are two billed runs and write different
   items; #235's ruling never reached the item generator. `medium`,
   W10c → the generator slice.
2. **#247** — W10b's liveness probe names a host that cannot return the result
   recorded against it. `medium`, W10b → the deploy-runbook slice.
3. **#248** — PRD §3's block-1 injection has no mechanism. `medium`, W11 → W16.
4. **#249** — passing unit 1 removes the only lesson and halves the items.
   `medium`, W11 → W12.
5. **#250** — a learner who finishes a unit's teaching before Saturday sees
   practice-only block 3 with nothing saying a checkpoint is coming. `low`,
   W11 → operator ruling.
6. **#251** — one of two learners has a permanently not-ready Saturday with no
   date on it. **`high`**, W10 → **the generator slice**, which is what carries
   #159's consumer 3. An issue is not a slice; the row answers *which slice
   unblocks her*, which is the reason the plan gives for filing it.
7. **#252** — the known-issues Status column against the decisions log; #132's
   family, fourth site, confirmed by reading the test. `low`, W10c → W19.

**And one re-target, which is not a new issue and is listed so it is not read as
one: #107 moves W11 → W16** (§4.2), with its old target quoted in place.

**Two things the first draft filed and this revision does not, because they were
solved rather than deferred:** the block-3 reserve (§3.2a) and `record_checkpoint`'s
missing attempt key (§5.1). **Filing either would have shipped a Saturday that
never opens or a counter that moves on a double tap** — and "it belongs to a later
slice" was not true of either.

Plus one reported observation that is not a defect and is recorded so it is not
re-derived: **the committed W10c journals do not reconstruct production's
per-unit item distribution** (§3.0), because six `--live` attempts wrote through
`ON CONFLICT DO NOTHING` and two journal files are committed. H1 is the read that
settles it.

*"It belongs to a later slice" is a reason to file it with a target, never a
reason not to file it.*
