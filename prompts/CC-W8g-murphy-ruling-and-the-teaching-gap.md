# W8g — the Murphy ruling, and the gap it opens

**Archived prompt. Intent, not state — `BUILD_PROGRESS.md` is the record of what is built.**
Given 2026-08-26. Records only — no code, no migration, no server step.

---

Operator ruling, 2026-08-26: the syllabus cannot cite an external book to a learner.

The reason, in the operator's words: this is being built for users, not only for the operator. Some will own Murphy's 4th edition, some the 5th, and most will own no copy at all. A `murphy_units: "38"` is meaningful only to someone holding one specific printing, so as learner-facing content it is meaningless to nearly everyone.

This re-scopes #164 rather than answering it. #164 was filed as three citations contradicting each other (Murphy 19–20 across units 3 and 9; Murphy 38 across units 12 and 17), with W8 check 4 as its verification step. Under this ruling, verifying them against the book is no longer the fix. Whether Murphy 38 teaches must/can't or the third conditional cannot matter to a learner who has no Murphy.

Re-scope #164 to what remains true: `grammar_targets[].murphy_units` is an operator note, not learner-facing content, and nothing may render it to a learner. Record that the contradictions are still real and still unexplained, that they are now cosmetic rather than load-bearing, and that a uniform edition offset never explained them anyway. Do not close it — the field still exists and something could still show it.

#171 unblocks, and record why. It blocked W9 and W10 on the grounds that both surfaces show citations to a learner. Under this ruling neither does. W9 and W10 are no longer blocked by #164. State the new constraint that replaces it: no surface renders `murphy_units`, asserted by a test in the slice that builds the first one.

W8 check 4 is retired, not carried. It existed to verify citations against the operator's book. It has been part-run and blocked for six slices, and the ruling removes its purpose. Strike it with that reason — a check that disappears without a stated reason is indistinguishable from one that was forgotten. Record what it did establish before retirement: `lemmatize` was never its subject, but the three contradictions were found by query, not by the book, and that finding survives.

File the gap this opens, and it is the important one. If the app cannot point a learner at a book, the teaching must be in the app. A learner who fails the must/can't items in a checkpoint needs an explanation, not a page number — and nothing in PRD, TASKS or the syllabus currently writes one. The 82 grammar targets are labels for teaching that exists nowhere.

File it `high`. Two shapes, proposed, not chosen — this is the operator's ruling and it is not this record edit's to make:

* Explanation on demand — the learner gets stuck, the app explains that point, generated once and stored. Cheap per unit, needs a generator and a store.
* Targets carry their own teaching — 82 short explanations authored into the syllabus. No generator, no per-learner cost, but 82 pieces of writing.

Note which slice owns it: W10 generates items against these targets and is the first place a learner can fail one.

Records only. No code, no migration, no server step. Do not start W9 or W10.

---

## What the slice found that the prompt did not ask for

Writing #171's replacement constraint — *no surface renders `murphy_units`* — meant grepping for what would have to fail such a test. **Four live surfaces already render a Murphy citation to a learner**, all fed by `error_types.murphy_units` (seeded in `migrations/001_init_postgres.sql:190`) rather than by the syllabus field the ruling names:

* `apps/web/app/(app)/write/page.tsx:136` — the v3 correction screen, live since W3 on 2026-08-24
* `apps/web/components/items/explanation.tsx:37` — the v3 item result box (W6); `item-card.test.tsx:129` asserts the citation **is** shown
* `apps/bot/texts.py:689` — the v2 Telegram correction block, live daily
* `apps/bot/texts.py:646/650` — S11's weekly Murphy routing

Filed as **#183** `high`, for a ruling and not for a fix. The constraint written into #171 is scoped to `grammar_targets[].murphy_units` deliberately, because extending a ruling past what was ruled is not a record edit's to do.
