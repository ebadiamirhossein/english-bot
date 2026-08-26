# W8c — The card face: the answer is printed on the front

Mode: PLAN. Changes a learner-visible surface and backfills production rows. Produce a plan, stop, wait for approval.
No migration. `schema_version` stays at 14. No `.sql` file added or edited.

## Read first

`CLAUDE.md`, `docs/PRODUCT-PRINCIPLES.md`, `BUILD_PROGRESS.md` in full — the W8b row, #124, #142, #143, #147, and the W8a decisions on the `/type` candidates. Then `apps/web/components/cards/card-face.tsx`, `apps/web/app/type/candidates.ts` and `packages/core/cards/migrate_chunks.py`.

Verify every claim below against the tree and the database. Where this prompt states a number, confirm it before building on it.

## What was found, on a phone, in ten seconds

The `/review` screen on production, card 38's face, before tapping Show me:

```
extra expenses that are not obvious at first
"I wish someone had warned me to ask about _____ upfront," she said.

  ""I wish someone had warned me to ask about hidden costs
  upfront," she said." — reading_1
```

The source line prints the answer. The gloss asks for it, the gap marks where it goes, and the line underneath supplies it. This is not a hard question; it is not a question.

Neither code review nor the uniqueness probe found this. The probe measured whether the gap was answerable and never asked what else was on the card. A person looked at the screen. Record that as the finding: a gate that examines one field cannot see a leak from another, and #116 is the same shape — the answer arriving before it is asked for.

The cause is a correct rule applied to the wrong card type. PRD §8.5.4 requires the source line on the face, and for a `recognition` card that is right: you read the sentence and recall the meaning, so the sentence is the question. On a `production` card the source line contains the answer, so it must be withheld until reveal exactly as the back is.

## Part 1 — Withhold the source line on production cards

`card-face.tsx` shows the source line on the front for every card type. Change:

* `recognition` — source line stays on the front. Unchanged, and the plan says why so nobody "fixes" it later.
* `production` — source line moves behind the reveal, with the back.
* Any other type that carries one: state the ruling per type in the plan rather than writing a default.

A test asserts the leak is closed at the component level, in the shape of W6's per-type leak assertions: for a `production` card, the rendered front must not contain the card's `back` value as a substring. That is a value-level check, not a key-level one — #116 exists because the first version of those assertions checked key names.

Also check the register panel (`INFORMAL` / safe-anywhere / who-says-this) and the `cue_text` field against the same rule. If either can carry the answer on a `production` front, it is the same defect and belongs in the same fix.

## Part 2 — The card face's Farsi, since this slice opens the file anyway

#142 and #143 are both `high`, both live on nine cards, and both live in this component. Fixing the leak here and leaving them would be two visits to one file. State that as the reason for the widening rather than letting it look like scope creep.

#142 — the declared Farsi fallback never fires. W8a established the mechanism and the fix: `next/font` inserts its own metric-adjusted local fallback immediately after each Latin family, and that fallback has Arabic coverage, so the browser never reaches Vazirmatn. The `--tp-l1` token in `apps/web/app/type/candidates.ts` is the working version. Apply the same approach to the real app, not a second invention.

Verify by measuring, not by reading CSS. `getComputedStyle` reports the declared stack and would show this passing while it fails. W8a measured rendered width at 40px — Figtree alone and the declared stack both 201.54px, Vazirmatn 250.55px. Use the same method and report the numbers.

#143 — no `lang`, no `dir="auto"` on any field. Card 17's front is `سطح ردیف; چیدمان در سطوح طبقه‌بندی (/tɪər/)` above an English sentence — RTL and LTR on one face, with a semicolon and a phonetic bracket exactly where mixed-direction text goes wrong. `components/items/presentation/l1-to-l2-production.tsx:22` already does this correctly (`<div dir="auto" lang={language}>`); follow it rather than inventing a second pattern.

Nine cards carry Farsi, confirmed on production:

```sql
SELECT card_type, count(*) FROM cards WHERE front ~ '[؀-ۿ]' OR back ~ '[؀-ۿ]' GROUP BY 1;
-- production | 9
```

## Part 3 — The five English-gloss cards, and card 17's hint

#124's other half, now measured. 9 of 14 production cards carry a real Farsi gloss — they came from the Trancy `vocabulary` import, whose CSV has a `Translation` column. The other 5 came from `reading_1` chunks and have an English gloss on the front, so they drill English → English rather than L1 → English. Confirm the split by query before acting on it.

Proposed, for the human to rule on rather than for this slice to choose: the operator authors five L1 glosses by hand, exactly as W7's `--slang-glosses` had the operator author the neutral equivalents for five slang phrases. Five lines, a person who knows both learners, no billed call, and W13 generates them from the real transcript line later. Do not implement before the ruling. State the alternative — leave them English-glossed until W13 — with its cost.

Card 17's malformed hint (#147). Its context hint reads `three _____s: dev, staging, and production.` — the gapper cut `tier` out of `tiers`. One card, named in #147. This slice does not fix `make_sentence_with_gap`: that lives in `packages/core/services/anki.py`, which is the W22 boundary and is live on the daily Telegram gap question. Either repair this one card's stored hint, or leave it and say so. Rule in the plan; do not open `services/anki.py`.

## Part 4 — The typography default

If the human has named a candidate, the one-line default change ships here: `apps/web/app/layout.tsx` (the `next/font` calls and the `<html>` className) and `apps/web/app/globals.css` (`--font-sans` / `--font-heading`, plus the ground and ink tokens if the candidate moves them). W8a's row names that surface exactly.

If no candidate has been named, this part does not happen and nothing is guessed. The `/type` page and its removal issue stay open either way.

## Acceptance criteria

1. A `production` card's rendered front contains neither the `back` value nor the source line — asserted at the component level, by value.
2. A `recognition` card still shows its source line on the front.
3. Farsi renders in Vazirmatn on the real card face, proved by measuring rendered width, not by reading the declared stack.
4. Every field carrying learner text has `lang` and `dir="auto"`.
5. The Farsi card count is confirmed at 9 by query before and after.
6. `packages/core/services/anki.py` byte-identical — `git diff --name-only` does not list it.
7. Suite green, reported split: baseline 1681, deleted with names, added with names, final. Vitest reported separately.
8. No migration, no `.sql` file.

## Server steps — for the human

Claude Code has no SSH access and is not to be given any.

Step 1 is `core.db status` compared against the record's claim (#141) — and note that W8b's two status reads were recorded as unreported, so this is the first chance to close that gap rather than carry it. Then backup, pull, install, no migrate, restart `english-api` only, Vercel.

`english-bot` stays running: nothing it imports changes, and a restart discards whatever a learner sent in that window.

Any gloss backfill is a separate human step after the deploy, dry-run first, listing every row before it writes.

## BUILD_PROGRESS.md update block

1. Slice row — W8c at 🟡. Never ✅.
2. Decisions log — the leak and how it was found (a person on a phone, after a probe that could not see it); the per-type source-line ruling with its reason; why Parts 2 and 3 widened the slice; the Farsi width measurements; the gloss ruling and its alternative; card 17's ruling.
3. Known issues — new: the source-line leak, filed at the severity it deserves and closed by this slice with its evidence. #142, #143 closed if measured shut; #124 updated with the 9/5 split and closed only if the five glosses land. #147 updated with card 17's disposition.
4. File inventory — every changed file.
5. Next action — every carried check reproduced in full. W8's five content checks stay first — carried through six slices now. Add: re-read a production card on the phone and confirm the answer is no longer on the front; look at card 17's Farsi.

Stop when the update block is written. Do not start W9.

---

## Rulings given during planning (2026-08-26)

* **Part 4 does not happen** — no typography candidate named.
* **Part 3's five L1 glosses are authored by the operator**, backfilled after the deploy.
* **Both additional leaks found during planning are in scope** — the register panel on the front, and the recognition card printing its mined sentence twice.

## Plan-review changes (2026-08-26)

1. **The gloss backfill guards in the `UPDATE`, not only in the `SELECT`.** Every statement carries `AND front !~ '[؀-ۿ]'` in its own `WHERE`, and each must report exactly 1 row — 0 or >1 stops the sequence.
2. **The server steps are reshaped around what actually writes.** The code deploy writes nothing, so: `core.db status` → `git pull` → Vercel → phone check → **backup** → the five `SELECT`/`UPDATE` pairs → the count. No `pip install -e`, no migrate, **no restart** — this slice's diff contains no Python, and the restart would drop in-flight requests for nothing. A frontend-only exception, recorded so it does not become a habit; the sequence is unchanged for any slice touching Python. Each Farsi count is stated with the step it belongs to (9 at the deploy, 14 after the backfill).
3. **`/type`'s production sample still prints the source line pre-reveal.** Left alone — a typography artefact on a page already filed for deletion — with one line added to that issue's row so the divergence does not read as a regression.
4. **#143 gains the Lithuanian line.** `BidiText` tags every non-Arabic-script line `lang="en"`, which is right for the whole deck today and wrong for Morkyte at W10 — a Lithuanian gloss labelled English, with no visible symptom. The second concrete case for the L1-language field that row already asks for.
