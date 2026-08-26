# W8d — Checkpoints: give the freed items back to grammar

Mode: PLAN. Changes `packages/core/syllabus/blueprint.py` and rewrites all 24 units' `checkpoint` blueprints on production. Produce a plan, stop, wait for approval.

## Read first

`CLAUDE.md`, `BUILD_PROGRESS.md` in full — #161's ruling, #165, #166, #167, and W8's row. Then `packages/core/syllabus/blueprint.py`, `migrations/014_syllabus.sql`, `tests/test_syllabus_blueprint.py`.

Verify every number below against the tree and the database.

## The ruling

#161 ruled option A: the 24 units are a grammar spine, vocabulary comes from the ledger and from what the learner meets. That leaves `lexeme_items` in every checkpoint with no source.

#166's arithmetic, confirm it before building on it: units 1–7 and 13 carry `lexeme_items: 3`, so removing the source leaves 9 grammar items against a 12-item, 80% checkpoint — 75%, unpassable at perfect grammar. Fifteen units carry 2 and land at 83.3% — zero errors tolerated. Unit 8 carries 1.

The ruling: `lexeme_items` goes to 0 and its items are redistributed across the unit's own `per_target` entries. Every checkpoint stays 12 items at 80%, and all 12 test that unit's grammar targets.

Distribution is a design question, not arithmetic. State the rule you chose and why — the existing weighting is deliberate (unit 2 gives 3 of 12 to present perfect or past simple, its hardest distinction), so the freed items must not flatten it. Whatever rule you pick, apply it to all 24 and show the before/after table for every unit in the plan.

## Constraints

* `blueprint.py:154` already raises unless `sum(per_target) + lexeme_items == item_count`. That invariant holds after the change with `lexeme_items: 0` — do not weaken it (#167 says the SQL layer does not mirror it, and that stays filed, not fixed here).
* The `syllabus_units_checkpoint_is_twelve_at_eighty` CHECK stays satisfied.
* `test_every_checkpoints_blocks_sum_to_twelve` covers all 24 units and must stay green.
* This rewrites `syllabus_units.checkpoint` for 24 production rows — a human-run, dry-by-default command that prints every before/after row, in `seed_fixtures --purge`'s shape. Backup immediately before it.

## Do not

* Touch `syllabus_unit_lexemes` — its removal is #165, sequenced after this and wanting its own slice plus a PRD §3 amendment.
* Choose #166's option 2. File it as the target once the deck is real: vocabulary items re-sourced from the learner's own FSRS due cards rather than from a unit list, which is truer to ruling A but couples the checkpoint to deck state and needs a fallback for an empty deck. Record that option 1 was taken now because it needs no new dependency, and that option 2 was assistant-recommended and operator-accepted as the later target.

## BUILD_PROGRESS.md update block

Slice row W8d 🟡, never ✅. Decisions log with the distribution rule and its reason. #166 closed by this slice, with option 2 filed as its successor. #165 and #167 carried unchanged. File inventory. Next action with every carried check reproduced in full — W8 check 4 is part-run and blocked on the book; check 2 is blocked; both stay listed with their reasons. Server steps written for the human.

Stop when the update block is written. Do not start W9.

---

## Operator's review of the plan — approved with three changes, folded in before implementation

1. **The before→after table could not be cross-checked by a reader.** It gave `per_target` positionally in authored order while the tie-break table named targets by name, and `grammar_targets` order is not recoverable from the database — `checkpoint` is JSONB, so `psql` returns keys in its own order. **Fix: name the targets beside the numbers for the seven tie-break units** (1, 2, 6, 8, 10, 11, 14). The other seventeen stay positional. This is the one place the slice judges rather than applies a rule, so it is the one place the record has to be checkable by eye.

2. **Four corrections to the server steps**, each of which would have stopped the deploy: the path is `/home/bot/english-bot`, not `/srv/english-bot`; `.venv/bin/python` and `.venv/bin/pip`, because there is no `python` on `bot`'s PATH; and the restart is **not** `sudo` as `bot` — `exit` back to root first. Also: `set +H` is harmless but unnecessary here, since no `!` appears in the verification SQL. Keep it for runbook uniformity, but **do not record it as a #151 case**, or that row starts collecting cases that were never at risk.

3. **File the consequence nobody had named:** every checkpoint now generates 12 items instead of 9–11, on 3–4 targets. Fourteen units have only three. Four or five items on one narrow grammar point in one sitting is where near-duplicates come from, **and W5a's uniqueness probe is per item, so it cannot see two items in the same checkpoint asking the same question in different words** — #164's family, fourth appearance. File `low`, target W11, **with the arithmetic and the two worst shapes named concretely** (unit 3's three targets at four items each; units 16–19 and 21–23 at five items on each of two targets) so the generation slice meets numbers rather than a warning. Do not solve it here.

Also confirmed in review, independently re-derived: the apportionment reproduces for units 2, 4, 8, 10 and 16 including the tie-breaks; unit 4 needs no tie-break (one seat, one clear remainder at .667) and the table correctly shows none; and the 82-target count matches what the Murphy citation query returned independently.

**Standing rules carried into the implementation:** slice row 🟡, never ✅; run `test_a_perfect_grammar_score_passes_every_checkpoint` **before** the data edit and record it red; the dry run's 24 rows go into the record verbatim; re-read from the database after `--apply` and verify in `psql` separately from the command's own count; report the exact pytest number; and **stop and report** if the dry run refuses with "a column other than checkpoint differs". Do not start W9.
