# W16 — Writing output — the prompt, the send-backs, the approval

Archived here per CLAUDE.md: `prompts/` documents the INTENT each slice was
given. It is not a record of build state and is never consulted for it —
`BUILD_PROGRESS.md` is.

The sequence, 2026-09-14:

1. **The slice prompt** — W16, PLAN mode (below, verbatim).
2. **Plan revision 1** — produced; not reproduced here. Its reconcile (ten
   items, eighteen disagreements) was accepted in full.
3. **Send-backs S1–S8** — verbatim below. S1 split the slice into W16a (the
   journal) and W16b (the paragraph); S2 replaced a per-day counter with a
   submission log.
4. **Two operator rulings in chat** on S1 and S2: *Split; Thursday = journal*
   and *Submission log*.
5. **Plan revision 2** — W16a alone. Appended at the foot of this file as
   approved.
6. **Approval with amendments A1 and A2** — verbatim below. A1: amend only PRD
   §4.2's Mon/Wed/Fri rows and report Thursday unmet in the slice row, never in
   the PRD. A2: give #409 a slice target.

---

## 1. The slice prompt

W16 — Writing output. PLAN mode.
Produce a plan. Write no implementation code, create no migration, make no billed call, and change nothing under `apps/` or `packages/` in this pass. The plan is reviewed and sent back with numbered changes before anything is built.
0. Read these first, in this order

1. `CLAUDE.md` — in particular §1a (design first), §3a (Playwright carries the screen checks), §2 (architecture), §3 (testing), §4 (content), §5 (data), §5b (no production entrypoint in a slice), §5c (rehearse every host block).
2. `docs/PRODUCT-PRINCIPLES.md`.
3. `BUILD_PROGRESS.md` — the slice table, the known-issues table, and the head of `## Next action`.
4. `docs/TASKS-v3-web.md` — the W16 row and the authoritative migration table.
5. `docs/PRD-v3-web.md` §4.1 and §4.2.
6. `specs/design/W16-writing-output.dc.html` — the design export. Read the real file. It is the specification for every screen in this slice. It is a bundled `.dc.html`; if it does not open as readable markup, decode the `__bundler/template` script block rather than planning around a description of it. Frame ids used below (`1c`, `1j`, `1k`, `1u`…) are that file's.

The mode is PLAN although the TASKS row says AGENT. This is on the operator's instruction, the precedent being W6, W5b and W8. The reason: W16 changes the contract of a shipped route, adds a generated field to a response, edits a screen that has been live since August, and builds the repository's first browser-level test harness.
1. The reconcile — do this before any planning, and report rather than fix
Everything in §2 and §3 below was written from `BUILD_PROGRESS.md`, not from the tree. Check each of the following against the repository and report what you find, including where the record and the tree disagree. A disagreement is a finding to write down, not something to quietly conform to.

1. `/write` as it exists today. The route, the page component, what it sends, what it renders, what it does with the response. The design's Q1 position is that W16 is this screen, restyled and handed the day's task — confirm that is what the code allows, and say plainly if it is not.
2. `POST /correct`'s request and response shape, and `requestCorrection()` in `apps/web/lib/api.ts`.
3. Does the correction path already carry a `session_id` anywhere? Does `errors` have a session column? This decides whether §2's ruling 1 is a route change or a route change plus DDL.
4. `structureFeedback` — is any structure-level field on the correction response today? The record's evidence says no: `/correct` is v2's M2 correction ported unchanged at W3, and v2 had no structure feedback. Confirm.
5. `error_types` — the seeded taxonomy table. Is a learner-facing label for an error type reachable from the correction path, and does the correction response carry the type at all? See §3, S3.
6. Block 4's current copy and current handoff. `copy.ts` and the block-4 component. The record says the copy was widened at W14 to cover shadow and that W14r then retired shadow — so block 4 may be naming a retired feature today. Report the exact current strings.
7. `capturable()` and the existing word-capture path from `/talk`, and `save_conversation_word` / the deck writer it uses.
8. The `/talk` and close-out components, since the design inherits their conventions rather than reinventing them: the mono eyebrow, the bordered pill, serif-for-app / sans-for-learner, the writing indicator, the full-width composer with its control beneath.
9. `specs/design/`'s existing three files, so the W16 export is read in the same way the W13b one was.
10. The next free migration number. 027 is W18's in the authoritative table. Verify by reading `migrations/` rather than by trusting a row (#185). Do not take a number in this pass; state whether one is needed and which is free.

2. Rulings already made — implement to these, do not re-argue them
All three are assistant-recommended, operator-accepted 2026-09-14, and all three go into the decisions log with that authorship.
Ruling 1 — `POST /correct` gains the session id, and block 4 can reach `done`. The design's frame `1p` returns to the session with block 4 marked done. Today nothing links a correction to the sitting it happened in — `_derive_done`'s `output` clause says so in as many words, and it is why `sessions.completed` has never been reachable (#259, #361). W16 closes the output half of that. The plan states whether this needs DDL or only a route and service change, and states what it does not close: `sessions.completed` has a second, independent cause — `complete_block` was removed at W11 and `minutes`/`completed_at` have no writer at all (#349). Do not claim `completed` becomes reachable.
Ruling 2 — the result opening line is generated, in the same correction call, with a silent branch. The design's `1m` note calls it a fixed string while `1k` and `1l` show two different ones; the note is wrong and is corrected. It is one sentence, folded into the correction response at no extra call, and it is the `did_well` shape that `/talk`'s close-out already ships. If there is nothing worth saying, the field is absent and the line does not render — an empty line, not a platitude. It is added to `1u`'s field list, it passes the no-guilt scan like every other string, and the plan says which gate refuses a bad one and what that gate can and cannot establish (#271: a gate can refuse what it caught; it can never show the model understood the rule).
Ruling 3 — a daily ceiling, five submissions per learner per day. Shaped exactly like `/talk`'s: a boolean reaches the screen, never a count, never a reset time, never a warning as it approaches. `1q`'s second card renders. One environment variable, and the plan flags it under PRODUCT-PRINCIPLES §3 as global configuration that becomes per-user at multi-tenancy — the flag `/talk`'s own cap already carries (#382).
3. The design's positions, accepted — and the five changes to it
Accepted as drawn, not to be re-opened: Q1 (W16 is `/write`, restyled and given the task — not a new route and not a view inside block 4), Q2 (corrections collected below the learner's text, on the same screen, never inline against their own words), Q3 (structure feedback as prose quoting the learner's own phrase, never named dimensions), Q5 (no history, no past entries, and therefore no raise line anywhere), Q6 (word offers on the paragraph only, at most two, taken from the app's own suggestions and never from the learner's spelling).
Five changes, on top of Ruling 2's correction to `1m`:
S3 — the nineteen learner-facing error-type strings do not get hand-authored in TypeScript. `1u` proposes a client lookup table because no category label comes over the wire. A hand-authored client copy of a seeded database taxonomy is a second source of truth and will drift from it — the shape #190 exists to prevent, and the shape that made a grammar-textbook citation live on four surfaces nobody had noticed. Plan for the label to come from `error_types`. If the reconcile finds the correction response does not carry the type at all, say so and cost both options — putting it on the wire, or dropping the card eyebrow, which `1u` already notes the card survives.
S4 — `wordOffer` selection is server-side, in `packages/core`. `1u` calls the selection rule "new client code". Filtering candidates against the known-word ledger is business logic over learner data and CLAUDE.md §2 keeps all of it out of routes and out of the client. Two further things the plan must state rather than assume: the offers are phrases, and the existing `capturable()` filter works on single words resolved against the reference lexicon with a CEFR tag — so this is a new rule, not a reuse of that one. The constraint it inherits from #402 is absolute: candidates come only from the app's own suggested text, never from what the learner typed.
S5 — `structureFeedback` is new request construction, so CLAUDE.md §3 rule 2 fires. One real API call before shipping, and it is the operator's to run because the key is on the host. State it as a stop point in the build order, not as a line in an acceptance list. The design's frame `1n` is the specification for what the model is asked to return.
S6 — the no-guilt scan must reach every new string in this slice, including the generated opening line, which is the first generated learner-facing sentence this surface has ever carried.
S7 — `1j`'s fold arithmetic becomes a test, not a note. The writing screen is a column of three: fixed head, flexible field, fixed button; only the field flexes, and it may not be given a viewport height. That is #395 written as a constraint, and #395 is the defect that put a composer below the fold on a shipped screen with nine green tests over it.
4. §3a — this slice builds the Playwright harness
There is no Playwright dependency, no config, no `e2e/` directory and no CI in this repository. W16 is the next slice to touch a screen, so it builds the harness, and its cost is named in the plan rather than discovered: a dev dependency, a config, a browser download, and — because there is no CI — a suite somebody has to remember to run. Say who runs it and when.
The five assertions owed by every state the design draws: the element is visible in the viewport, nothing overflows, the control is reachable and enabled, in both themes, at phone and desktop width. The design's frame notes are what these are written from — each frame carries `above the fold`, `primary` and `absent`, and `1j` and `1r` carry explicit `assert` lines. Use them.
State the boundary in the plan, in words, and do not let it be dropped later. Playwright proves a control is on screen and reachable. It cannot judge whether a screen is good, whether a correction teaches, or whether a generated sentence is worth a learner's time. Name the human checks that survive the harness and write them as human checks.
5. What the plan must contain

1. The reconcile's findings, including every disagreement between this prompt, the record, the design and the tree.
2. The position on PRODUCT-PRINCIPLES §2, stated either way: whether this slice adds a user-keyed table, and if so that it keys on `users(id)`.
3. Whether a migration is needed at all, and if so which number is free — verified by reading `migrations/`, not by trusting a row. Do not take a number in this pass.
4. The wire: every field added to or changed on the correction request and response, each one traced to a frame that renders it. `1u` is the reference — a field nothing renders, and a rendered value with no field, are both defects (#390, #398, #403).
5. The build order, with the rule 2 stop point in it.
6. The test plan: which assertions are Vitest, which are Playwright, which are Python, and which are human. Every new test demonstrated red before it is accepted (§3 rule 4).
7. Acceptance criteria, taken from the TASKS row — journal corrections capped at two; the paragraph task returns structure feedback and writes errors to the journal — plus what this slice reports unmet rather than approximating (§3 rule 7).
8. What W16 does not claim. Write it as its own section. W13b/4's row had to add one after the fact because it recorded what was built and never what was left, which is #82's pattern.

6. Standing constraints

* The error journal is the product. Only genuine self-produced errors are written to `errors`. A wrong row is permanent damage; a missing one is recoverable. A typed sentence the learner wrote is genuinely theirs, which is what makes this surface the right place for journal writes — and is why #107 and #248 target it.
* No billed call in this slice. Dry by default; `--apply` never run. The one real call rule 2 requires is a stop point run by the operator.
* Claude Code has no SSH access to the production host and is never to be given any. Every server step is written out as an explicit command for the operator to run, and a server action is never an acceptance criterion this slice can satisfy on its own.
* The production host is shared with another team's service. No broad upgrades, no reboots, no Caddy rewrite, no destructive PostgreSQL command without naming `english_bot`.
* `apps/web` changes need a Vercel rebuild. Every server check passes while the old screen is still up. Say so in the deploy sequence.
* Telegram is legacy and dies at W22. Nothing new is designed for it.

7. The `BUILD_PROGRESS.md` update block
End the plan with the update block it will owe: the W16 row at 🟡 — never ✅, that column is the operator's — every decision with its reason in the decisions log, new issues with severity and target slice, a file inventory for new files, and a Next action rewritten to this slice's human checks plus every earlier check still unrun. Nothing drops off for being old.
Carry this issue, filed by this slice and not fixed by it:
#404 — `docs/TASKS-v3-web.md` still carries a W21 row for work that shipped at W1c. W1c is titled "Off-site backup — pulled forward from W21", is ✅ done and verified (2026-08-24), and closed #6 with a restore drill, a proven freshness alarm and an unattended cron dump. W21's row is unstruck and carries the same Build and the same Accept text, so a reader counting remaining slices counts one that is done, and a planner reaching W21 would rebuild R2 backup. Not corrected here: striking a row is a scheduling change and the operator owns the schedule. `low`, target W19, where the record's other document-drift rows sit. Found by counting the remaining slices against the record rather than against a handover note.
Do not mark any slice ✅. Do not start the next slice. Produce the plan and stop.

---

## 3. The send-backs on plan revision 1

The reconcile is accepted in full, including the four places it contradicts the slice prompt. Three of those were the operator's errors and are corrected rather than absorbed: **D2** (`did_well` already exists; Ruling 2 is a contract change, and the `"Nice."` fallback survives only on the bot path); **#402's characterisation** (the shipped `/talk` code draws candidates from the learner's typed turns and excludes the app's; W16's app-text-only rule is new and adopted by this slice); **D3** (the *"max 2 — v2 rule"* attribution is wrong; build the two). Block 4 naming no retired feature is an evidenced negative.

- **S1 — The slice is too large for one commit. Split it.** W16a — the journal: `/write` restyled and given the day's task; `day_kind`; Ruling 1; Ruling 3; Ruling 2's contract change on `did_well`; G1 and G2; the `learner_label` eyebrow; and the Playwright harness. W16b — the paragraph: `structure`, `word_offers`, `POST /write/keep`, the paragraph prompt and its ceiling. The journal changes a response's contract; the paragraph adds generated content that has never existed, one field of which produces a card FSRS will drill for months. Different risks, separate approvals. Both halves still need the §3 rule 2 call — two calls measuring two constructions.
- **S2 — `writing_usage` materialises a count a log would compute.** A submission log — one row per submission, no text column — serves Ruling 3 by counting rows and makes Ruling 1 log-shaped, which is what #258 asked for; a payload flag written by a route is the shape closest to the manual button #258 deleted. Evaluate and rule; do not leave the §3 flag unraised.
- **S3 — The rule 2 call runs on the Mac, not on production.** Pulling and installing on the host with no backup, migration or restart leaves unreviewed backend code one restart from two learners. "The key is on the host" was the operator's error. W5b's precedent: the live observation ran on the Mac with only `ANTHROPIC_API_KEY` in the repo-root `.env`. Confirm the key is there first; if it is not, report it rather than falling back to production.
- **S4 — Q-A changes PRD §4.2 and the plan does not say so.** State whether an amendment is owed; if so, make it in the same commit with the old text quoted.
- **S5 — The sixteen `learner_label` strings are learner-facing content and owe a human read** before they ship.
- **S6 — `word_offers` writes to the deck, and no gate asks whether the phrase is good English.** Moves to W16b; the first run's offers are read by the operator before `POST /write/keep` is reachable from the screen.
- **S7 — #407's `/talk` half is another slice's live surface; give it its own row and a slice target**, never a prose target. Same for #406.
- **S8 —** D9 (*"Reading it"*) is the second application of the §1a brand rule; the bundled-export decode is a finding worth its own record line.

Approved unchanged: the reconcile; Rulings 1–3 subject to S2; Q1, Q2, Q3, Q5, Q6; Q-B (2,000 chars, `reject_truncation`); Q-C (drop `1p`'s card, home link rewording); Q-D (ceiling of eight, no *"Four more below."*); Q-E (the offer rule and the recorded refusal of a lemma-level ledger filter on phrases); Q-F (G1, G2); D6; D11; D12. §4's gate boundary, §8's *does not claim* and `test_writing_wiring.py`'s call-site deletion are the three strongest things in the plan.

---

## 6. The approval of revision 2, with amendments

Approved; implementation may begin subject to A1 and A2, applied in the implementation commit with no further plan round. Three send-backs were applied better than asked and are logged as such: `day_kind`'s CHECK admits `'paragraph'` now with a test pinning that W16a never writes it (012's *widen once* precedent); `is_english` on the log, counting toward the ceiling and not toward `done`, with the asymmetry argued at the site; the `.env` credential check was read-only and the value was not printed.

- **A1 — Amend PRD §4.2 to what is superseded, not to what shipped.** Writing *"the journal on every day (while W16a alone ships)"* into §4.2 puts build state into a spec (#82's pattern) and makes W16a meet §4.2 by definition — the bar moved, which §3 rule 7 forbids. Amend only the Mon/Wed/Fri rows, whose speaking output lost its surface at W14r and returns at W15, with the old text quoted. Leave Tuesday and Thursday exactly as they are. Report the gap in W16a's slice row: *Thursday serves the journal until W16b ships; §4.2's Thursday paragraph is unmet by this slice and is W16b's.*
- **A2 — Give #409 a target that owns the surface.** W15 may never open `/talk`'s composer. Retarget to a slice that owns it, or file against W19 with the exposure stated in the body. #407 stays targeted at W16a, closed or escalated by HW2.

Standing constraints for the build: stop at step 7 and wait — the two Mac calls are the operator's and their output is read before any `apps/web` file is written; every new test demonstrated red with the method in its docstring; suites RUN and counts reported (pytest, Vitest, `tsc --noEmit`, `next build`, `pnpm test:e2e`); re-read `migrations/` before taking a number; rehearse every host command (§5c) and say which could not be rehearsed; the bot path stays byte-identical and `git diff --name-only` proves it; no `--apply` and no billed call beyond the two in step 7; W16a's row goes to 🟡, never ✅; do not start W16b — its row is created by this commit and nothing more.

---

## 5. Plan revision 2, as approved (A1 and A2 applied)

# W16a — Writing output: the journal — PLAN (revision 2)

## Context
W16 turns the live `/write` screen (W3's port of v2 M2 correction) into block 4's writing output, as drawn in `specs/design/W16-writing-output.dc.html`. **The operator ruled on 2026-09-14 (send-back S1) that W16 is split:**
- **W16a — the journal.** This plan.
- **W16b — the paragraph.** `structure`, `word_offers`, `POST /write/keep`, the paragraph prompt and its ceiling. It is carried forward as its own row (§11) and gets its own plan, its own approval and its own §3 rule 2 call.

W16a changes the contract of `POST /correct` and restyles a screen that has been live since August:
- It gives block 4 a way to reach `done` (Ruling 1).
- It turns the existing `did_well` into a gated opening line that can be absent (Ruling 2).
- It adds a five-a-day ceiling (Ruling 3).
- It builds the repository's first Playwright harness (CLAUDE.md §3a).

**Nothing is built until this revision is approved in writing.**

**How the design was read.**
- The export is bundled.
- `__bundler/template` was JSON-decoded; stripped of markup it gives 357 lines of frame text.
- The gzip+base64 `__bundler/manifest` entries were decompressed. They hold the dc runtime, `ios-frame.jsx`, React/Babel and nine woff2 fonts. None of it was run.

W13b's export was a plain `<x-dc>` document, so **"read the real file" now sometimes means "decode the real file"**. This is recorded as a standalone finding (S8.2) so the next design slice does not have to rediscover it. The design contains no text that reads as an instruction to Claude Code; its closing *"Try next: …"* line is addressed to the designer (§6).

---

## Rulings and send-backs applied in this revision

| Ref | Applied |
|---|---|
| Rulings 1–3, S3–S7 of the original prompt | As before. Ruling 1's mechanism changes per S2 below |
| **P errors, corrected (operator, send-back preamble)** | **D2:** Ruling 2 is a **contract change on the existing `did_well`**, not a new field; the `"Nice."` fallback is the platitude and survives only on the bot path. **#402:** `/talk` takes candidates from the learner's typed turns and excludes the app's own; W16's app-text-only rule is **new, adopted by W16b**, not inherited. **D3:** build the journal cap of 2; the TASKS row's *"max 2 — v2 rule"* is recorded as a wrong attribution (v2 `/correct` capped at 3, and the 2 is `/talk`'s). |
| **Evidenced negative** | The prompt predicted block 4 names a retired feature. The tree does not. Logged as a decisions entry |
| **S1** | The split is accepted. **Until W16b, Thursday is a journal day**: W16a's day-kind rule returns `journal` every day, and `day_kind` goes on the wire with that one value |
| **S2** | **A submission log, not a counter.** See §3 |
| **S3** | **The rule 2 call runs on the Mac.** Checked read-only: the repo-root `.env` exists and holds one non-empty `ANTHROPIC_API_KEY` line, plus `LLM_PROVIDER`/`LLM_MODEL`. The value was not printed. There is no pull on production, and production is never contacted |
| **S4** | PRD §4.2 is amended in the W16a commit, with the old text quoted (§5 step 1) |
| **S5** | The operator reads all sixteen `learner_label` strings before they ship (HW-L) |
| **S6** | Moves to W16b's row: the operator reads the first run's offers before `POST /write/keep` is reachable from the screen |
| **S7** | #407 is split in two. The `/write` half is checked by HW2. The `/talk` half is **#409**, targeted at W15. #406 and #408 get slice targets |
| **S8** | D9 is recorded as the **second** application of the §1a brand rule. The bundle decode gets its own record line |
| Approved as written | Q-B (2,000 chars, `reject_truncation`); Q-C (drop `1p`'s card; home link says *"write"*); Q-F (G1, G2); D6 (collapse on overflow); D11 (fields nothing renders come off the wire); D12 (the `max-w-lg` shell beats `1s`'s grid, reported unmet). **Q-D and Q-E are approved and carried to W16b** |

---

## 1. The reconcile — accepted in full (summary; the full tables are carried into the decisions log)

**The ten items, as found:**
1. **`/write`** sends only `{text}` and renders `you_said`, `correct_form`, `explanation`, a truthy `did_well` with a 👍, and an `is_english:false` message. It shows a live `{remaining} left` counter and a numeral hint. It has `maxLength` 1000. It is reachable from block 4 and from home's *"write anything"*. It has no Vitest test.
2. **`POST /correct`** is a plain `def`. Its request is `{text: 10..1000}`; its response is `{is_english, has_errors, did_well: str, corrections[{you_said, correct_form, error_type, explanation, murphy_units}]}`. It calls `chat(json_mode=True)` with the default 1,000 `max_tokens` and no `reject_truncation`. It caps corrections at 3 and writes `source='text'`. There is no typo filter.
3. **No session linkage** exists anywhere on the correction path, and `errors` has no session column.
4. **There is no structure field** on the response. That is W16b's.
5. **`error_types`** has columns `(code, label, murphy_units)` and 19 rows. The label is used only in the prompt and never reaches the wire. **`'Wrong article'` matches `BANNED`.** Three codes are spoken categories.
6. **Block 4** renders *"Output"*, *"Say something of your own."*, the unit task and *"Write it"* → `/write`. It accepts `sessionId` but ignores it and has no done rendering. Shadow survives only in comments and the kept `SHADOW` const. The `blocks.tsx:303-314` docstring is stale.
7. **Capture**, carried to W16b: `capturable` works on learner text only; `save-word` accepts any string; phrase cards have no DB uniqueness.
8. **The `/talk` conventions** reused by class: the mono eyebrow, the bordered pill, serif for the app and sans for the learner, the inline three-dot indicator, the composer as a block, the `--caution` tokens, and `h-full` inside `main.flex.min-h-0`.
9. **`specs/design/`**: W13b's export is plain; W16's is bundled.
10. **Migrations** run `001–026` contiguous. **027 is free on disk**, and W18 holds it in the table.

**Disagreements carried into W16a:**
- **D2**: `did_well` already exists.
- **D3**: the cap is 3 in the tree against 2 in TASKS.
- **D5**: `dayKind` does not exist.
- **D6**: the collapse contradiction.
- **D7**: the floor stays server-authoritative; the counter is removed.
- **D8**: 1,000 chars would truncate a 300-word entry.
- **D9**: *"Foundgrant"* becomes *"Reading it"*.
- **D10**: there is no non-English frame.
- **D11**: `murphy_units`, `has_errors` and `error_type` are rendered by nothing.
- **D12**: `1s`'s grid.
- **D13**: the fold sum omits the nav, and nothing handles the iOS keyboard.
- **D14**: `1p`'s wayfinding, and home's link.
- **D17**: `/talk` has no wire boolean.
- **D18**: no typo filter.

**Moved to W16b:**
- **D4**: the unit strings as paragraph prompts.
- **D15**: *"Four more below."*
- **D16**: ledger against phrases.

---

## 2. PRODUCT-PRINCIPLES

**§2.** W16a adds **one user-keyed table, `writing_submissions`**. It keys on `users(id) ON DELETE CASCADE` and adds no Telegram-id dependency.

**§3, first bullet — raised, and the resolution is the reason for the table's shape (S2).** A per-day counter would materialise a number the submissions themselves compute. The log stores the submissions and computes the count. It grows by at most five rows per learner per day, which is not a per-lexeme product.

**§3, second bullet.** `WRITING_MAX_SUBMISSIONS_PER_DAY` (default 5) is global configuration that becomes per-user at multi-tenancy. It is filed as **#405**, to be read with #382.

---

## 3. Migration — needed; the number is taken when the file is written

**DDL is needed. One file.** It takes the next free number at the moment of writing. `migrations/` is re-read first rather than trusting "027" (#185). W18 shifts in both halves of TASKS in the same commit.

**`writing_submissions`:**
```
id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE
session_id         BIGINT REFERENCES sessions(id) ON DELETE SET NULL
day_kind           TEXT NOT NULL CHECK (day_kind IN ('journal','paragraph'))
local_date         DATE NOT NULL
is_english         BOOLEAN NOT NULL
llm_input_tokens   INTEGER NOT NULL CHECK (>= 0)
llm_output_tokens  INTEGER NOT NULL CHECK (>= 0)
created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
INDEX (user_id, local_date); INDEX (session_id)
```
- **There is no text column.** A test asserts this from `information_schema` (CLAUDE.md §5).
- `'paragraph'` is admitted by the CHECK now, so W16b needs no CHECK widening. **W16a never writes it**, and a test pins that.
- **A row is written only for a completed model call**, in the same transaction as any `errors` rows. A 503 writes nothing and counts nothing. A too-short 422 never reaches the model.

**`error_types.learner_label TEXT NULL`.** The sixteen written codes are filled and the three spoken codes are NULL. **`label` is not edited**, because `correction.txt`'s type list feeds the live bot.

**The rulings, served from the log:**
- **Ruling 3:** `SELECT count(*) FROM writing_submissions WHERE user_id = %s AND local_date = %s` is compared with the ceiling. `is_english` is **not** filtered here, because a non-English submission spent a call.
- **Ruling 1:** `_derive_done` gains an `output` branch: `done` when `EXISTS (… WHERE session_id = %s AND is_english)`. This is log-derived, #258's shape. **No `sessions.payload` flag is written.**
- The submission's `session_id` is stored **only if** the session is the learner's own `daily` row for their local today. Otherwise the column is NULL: a foreign or stale id is a silent no-op and nothing is leaked.

**Not needed:**
- `errors.session_id`: a clean entry writes a submission row, not an `errors` row.
- `errors.source` widening: `'text'` stays.

---

## 4. The wire — every field traced to a frame

**The bot path stays byte-identical.** `correction.correct`, `apply_result` and `prompts/correction.txt` are untouched, because `apps/bot/handlers/correction.py:17-21` imports them and `texts.py:739,743` renders `👍 {did_well}`.

The web path gets:
- `core/services/writing.py` — `today` and `correct_submission`
- `core/writing/` — `rules`, `gates`, `probe`
- `prompts/writing_correction.txt`

### `GET /write/today` — new, plain `def`, `writing.today(user_id, now)`

| Field | Type | Frame |
|---|---|---|
| `day_kind` | `"journal"` (the only value until W16b) | `1c`, `1d`, `1a` |
| `session_id` | `int \| null`: today's `daily` row if one exists, **never created here** | not rendered; posted back (Ruling 1) |
| `ceiling_reached` | `bool`: never a count, never a reset time | `1q` unavailable |

**Block 4 payload (`_output_block`):**
- **Added:** `day_kind`, for `1c`.
- **Removed:** `task`, `unit_number` and `mode`. `1c` draws no task text, and nothing renders the other two.

### `POST /correct` — request

| Field | Type | Why |
|---|---|---|
| `text` | `str`, 10..**2,000** (Q-B; the floor is unchanged) | `submission.text`, never stored |
| `day_kind` | `"journal"` | The kind the learner was shown. W16b widens the enum |
| `session_id` | `int \| null` | Ruling 1; validated server-side as in §3 |

### `POST /correct` — response (`WritingResult`)

| Field | Type | Frame |
|---|---|---|
| `is_english` | `bool` | D10's state (no frame; human check HW8) |
| `did_well` | `str \| null`: **absent, never blank, never a fallback** | `1k` / `1l` / `1m` opening line |
| `corrections[].you_said` / `correct_form` / `explanation` | `str` | `1k` card anatomy |
| `corrections[].label` | `str \| null`, from `error_types.learner_label` | `1k` eyebrow (absent when null) |

**Removed from the web response:** `has_errors`, `murphy_units` and `error_type` (D11).

**Status codes:**
- `409 cap_reached` → `1q` unavailable. The model is not called and no row is written.
- `503` → `1q` failure.
- `422` below the floor → `1h`. The pinned client mirror normally prevents the round trip.

### Rules and gates (`packages/core`, pure, each tested)

- **Day kind** returns `journal` for every date in W16a, tested on frozen dates (§3 rule 6).
- **Journal cap: 2**, applied after the gates so dropped items do not consume it.
- **G1 (self-produced):** `you_said` must be a verbatim substring of the submitted text, whitespace-normalised. If not, the correction is dropped, not written and not shown.
- **G2 (typo):** the differing learner token must resolve against the reference lexicon (`lemmatize(w, frozenset())`). If not, the correction is dropped. **Stated limit:** a typo that lands on a real word passes.
- **Explanation gate:** a `BANNED_IN_CONTENT` hit drops the correction.
- **Opening-line gate:** `did_well` becomes absent on any of:
  - a `BANNED` term (it is the app addressing the learner);
  - a platitude-list hit;
  - a digit, `score`, `/10`, `%`, `mark` or `rating`;
  - more than one sentence.
- **What the gates can and cannot establish (#271):** they refuse what they catch. **They cannot show** that the opening line is true of the entry, that a correction's rule is right, or that a journal row is a genuine error rather than a model misreading. Those are human checks.

---

## 5. Build order

1. **Record and PRD.**
   - Archive the prompt, this plan's revisions and the send-backs to `prompts/CC-W16-writing-output-PLAN.md`.
   - **Amend PRD §4.2's Mon/Wed/Fri rows only** (S4 as amended by A1). Their **speaking** output lost its surface when W14r retired the Azure path, and it returns at **W15**. Quote the old text in place (#82's shape) and name W15.
   - **Tuesday and Thursday stay exactly as written** (journal; paragraph). **No build state goes into the PRD.** W16a's Thursday journal is reported as **unmet in the slice row** (§7), not written into the spec, because editing the spec until the shipped behaviour meets it would move the bar (§3 rule 7).
   - **Add W16b's row to TASKS** and to the BUILD_PROGRESS slice table, in the same commit (W11b's precedent).
2. **The migration file.** Re-read `migrations/` first. Update TASKS' authoritative table with W16a's row and W18's shift, in both halves. Run `test_record_consistency`. Apply to the **Mac dev database only**.
3. **`packages/core`.**
   - Config: `WRITING_MAX_SUBMISSIONS_PER_DAY`, using the three-place pattern (`config.py:87/349/586`).
   - `core/writing/{rules,gates}.py`.
   - `prompts/writing_correction.txt`, with `{explanation_language_rule}`, the optional `did_well`, and ≤2 corrections.
   - `core/services/writing.py`, calling `chat(json_mode=True, max_tokens=2000, reject_truncation=True, usage_out=…)`.
   - `_derive_done`'s `output` branch. Its docstring and `_output_block`'s are corrected **with the old text quoted** (#82).
   - **`python -m core.writing.probe`.** Dry by default: it prints the rendered system prompt, the request parameters, both fixture texts and **the call count `--live` will make: 2** (one entry with errors, one clean entry, so both `did_well` branches are seen). `--live` makes those two calls against fixture texts and a fixture learner profile, prints raw JSON, `usage` and each gate's verdict, and **writes nothing** — an AST test checks for no `record_errors`, no `INSERT`/`UPDATE`, and no submission write.
4. **`apps/api`.** `GET /write/today`, `POST /correct` rewired to `writing.correct_submission`, and the schemas.
5. **Python tests** (§6). Each is demonstrated red. The full pytest suite is run.
6. **§5c rehearsal.** Run the probe **dry** on the Mac and **read the printed request**, not just the exit code.
7. **🛑 STOP — CLAUDE.md §3 rule 2, on the Mac (S3).** The operator runs, from the repo root on the Mac:
   ```bash
   python -m core.writing.probe
   ```
   ```bash
   python -m core.writing.probe --live
   ```
   - **What the run touches:** `load_dotenv` resolves the repo-root `.env`, which holds `ANTHROPIC_API_KEY` (checked, value not printed). The prompt build reads `error_types` from **the Mac dev database**.
   - **What it does not do:** no backup, no migration, no restart, no deploy. **Production is never contacted.** It makes **exactly 2 billed calls**.
   - **The output is pasted back and I read it before `apps/web` is started.** A shape change goes back through step 3 and the calls are re-run.
8. **`apps/web`.**
   - `lib/api.ts`: typed `getWriteToday` and `requestCorrection(text, {dayKind, sessionId})`.
   - A `WRITE` copy block.
   - `components/write/`:
     - `entry-card` (`1c`)
     - `composer`: TaskHead, WritingField, SubmitBar, ShortRefusal, ReadingIndicator
     - `result`: ResultOpening, WrittenText, CorrectionCard
     - `states`: FailureCard, CeilingCard
   - `write/page.tsx` rewritten.
   - `OutputBlock` → `1c`.
   - The stale docstring corrected.
   - Home: *"write anything"* → *"write"* (Q-C).
   - *Back to today* → `/session` when a `session_id` was posted, otherwise `/`. There is no `1p` card.
9. **Vitest**, rendered from **fixtures Python generates through the real serialiser** and compares against a real ASGI body (the `wire-contract.test.tsx` precedent, #190).
10. **The Playwright harness plus `e2e/write.spec.ts`.** Each assertion class is demonstrated red. The first browser download's size is **measured and recorded**.
11. **Full suites:** pytest, Vitest, `tsc --noEmit`, `next build`, `pnpm test:e2e`. Report the counts.
12. **The `BUILD_PROGRESS.md` update block** (§10). **Stop.**

---

## 6. Test plan — every new test demonstrated red, with the method in its docstring

### Python

**`tests/test_writing_route.py`**, through the ASGI transport against the real DB, reusing `test_correct_route.py`'s fixtures; the model is stubbed at the service seam.

- **Acceptance:** the model returns 3 → **exactly 2 `errors` rows**, counted by an independent `SELECT` (rule 5).
- **Ruling 1:**
  - posted with the learner's own today `daily` id → `GET /session/today` block 4 is `done`;
  - a **clean** entry also counts, because a submission row is written and no `errors` row is;
  - non-English → not done;
  - a foreign id → 200, `session_id` stored NULL, the other user's session untouched;
  - yesterday's id → not done.
- **Ruling 3:**
  - five succeed; the sixth → `409` with **zero stub calls** and no row;
  - `ceiling_reached` goes true;
  - a 503 writes no row and does not count;
  - a 422 does not count;
  - non-English **does** count;
  - **no integer appears in any writing response body except `session_id`** (a banned-key and banned-value scan).
- **Ruling 2 / S6:** each of these makes `did_well` absent, and it is **never `"Nice."`**:
  - empty;
  - a `BANNED` term;
  - a platitude;
  - a digit;
  - two sentences.
- **Labels:** `label` is read from `learner_label` (queried in the test, not hardcoded); a spoken code gives `null`.
- **Guards:**
  - G1: `you_said` absent from the text → not written.
  - G2: a non-word → not written.
  - A real-word typo **is** written; this is the stated limit, pinned.
- **§5:** caplog on a submission holds no submitted text, and the table has no text column.
- **Plain `def`:** the existing `test_llm_and_speech_routes_are_plain_def` is extended.
- **W16a writes no `'paragraph'`.**

**`tests/test_writing_request.py`** mocks **at `anthropic.Anthropic`** (TASKS standing rule 7) and checks:
- the shared rule is in the system prompt;
- `max_tokens=2000` and `reject_truncation=True` are sent;
- the text arrives wrapped in `<user_text>`.

**`tests/test_writing_rules.py`** (pure):
- the day kind on frozen dates across a week boundary;
- the cap;
- each gate against a deliberate-violation fixture.

**`tests/test_writing_probe.py`:**
- dry mode makes no call;
- the AST test finds no write path;
- the printed count equals an independently computed count.

**`tests/test_writing_wiring.py`** (#402's lesson): each gate's **call site** is exercised through `correct_submission`, demonstrated red **by deleting the call site**.

**Extended tests:**
- `test_prompt_rules.py`: `writing_correction` is registered in `PROMPT_BUILDERS`. The pinned set (`:77`) and both parametrize lists (`:86-88`, `:110`) gain it, and the test is renamed by count.
- The migration test covers:
  - the FK to `users(id)` and the CHECKs;
  - the absence of a text column;
  - **every non-null `learner_label` passes `BANNED`**;
  - the three spoken codes being NULL.
- Config: the ceiling is set **through a `.env` file** (§3 rule 3), and a value below 1 is refused.
- `test_sessions_service`: the new `output` branch.
- `test_web_shell.py`:
  - **Kept:** the no-strike and no-red pins; the MIN/MAX mirror pin, repointed to the writing constants.
  - **Numeral scan:** extended to the `WRITE` block and `components/write/*`.
  - **Scan coverage:** a new test that `components/write/` is inside the no-guilt walk.
- **`test_corrections_are_capped_at_three` moves to a service-level test of `correction.correct`**, the bot's path. The route no longer reaches it, and a green test over an unreachable path is decoration (rule 4). The other route tests are repointed.

### Vitest (Python-generated fixtures)

- **Silent branches:**
  - no `did_well` → no opening node;
  - one correction → no *"I've picked the two…"* line;
  - zero corrections → no *Worth a look* heading and no empty card;
  - `label: null` → no eyebrow;
  - a short entry → no length line.
- **States:**
  - `1h` keeps the text and focus, and the button stays enabled;
  - `1i` has no button and the field is read-only;
  - `1q` failure re-sends the same text;
  - `1q` unavailable has no control.
- **Block 4:** the `1c` card renders, and `sessionId` is no longer ignored.
- **In every state:** a DOM text scan finds no numeral and no banned term.

### Playwright (`apps/web/e2e/`)

- **Server:** `webServer` runs `next build && next start -p 3100` with `NEXT_PUBLIC_API_URL=http://api.e2e.test`.
- **Mocking:** every API call is answered by `page.route` from the same Python-generated fixtures, and `/health/auth` returns signed-in. So there is no backend, no DB, no provider, no billed call and no production entrypoint (§5b).
- **Projects, derived from `1j`:**

  | Project | Engine | Viewport | Derivation |
  |---|---|---|---|
  | `phone` | WebKit | 390×768 | 812 − 44 |
  | `phone-keyboard-model` | WebKit | 390×477 | 768 − 291 |
  | `desktop` | Chromium | 1280×800 | — |

  Each project runs in **light and dark** through `colorScheme`. The theme is `system`-driven, so no stored value is needed.
- **The five helpers:**
  - `inViewport`: the element's box is fully inside the viewport.
  - `noHorizontalOverflow`: `scrollWidth <= clientWidth`.
  - `noClipping`: regions that must not scroll don't; the field is exempt.
  - `reachable`: the control is visible and enabled, `elementFromPoint` at its centre hits it, and a trial click follows.
  - The projects and themes above provide the width and theme coverage.
- **Per frame:**

  | Frame | Assertion |
  |---|---|
  | `1c` | Both lines and the whole button are in the viewport |
  | `1d` `1f` `1g` `1h` × `phone-keyboard-model` | **`1j`'s assert:** the submit box is fully in the viewport, **the document does not scroll**, only the field does, and at 300+ words the head has collapsed |
  | `1i` | No button |
  | `1k` / `1l` / `1m` | Opening line and text above the fold; *Back to today* reachable |
  | `1q` | Both states |
  | `1r` | **Contrast ≥ 4.5:1** from `getComputedStyle` on the real tokens |
  | `1s` | The same test ids at `desktop` as at `phone`; no overflow |

  Every control is ≥ 44px tall.
- **Red demonstrations, one per assertion class:**
  - `h-[100dvh]` on the field;
  - `min-h-0` removed;
  - `h-9` on a control;
  - the dark token dropped;
  - a `w-[600px]` child.
- **Who runs it:** there is no CI. Claude Code runs it before the `BUILD_PROGRESS.md` update in every slice that touches a screen, and the operator runs it before any screen-changing Vercel rebuild. Both go into Next action as a standing line.
- **The boundary, in words:** Playwright proves a control is on screen and reachable at a given size and theme. **It cannot judge whether the screen is good, whether a correction teaches, or whether the opening line is true — and it cannot raise a software keyboard.** `phone-keyboard-model` proves the column-of-three contract at the height a keyboard leaves, not how iOS Safari behaves. The human checks in §9 are not retired by a green run.

---

## 7. Acceptance criteria

**From the TASKS row, W16a's half:**
1. **Journal corrections are capped at 2.** Proven by the route test's independent count, **and** on the phone by a `psql` count independent of the app.
2. **Errors are written to the journal**, through the route (ASGI) and on the phone.

**From the rulings:**
3. **Ruling 1:** block 4 reads `done` after a session submission, derived from the log.
4. **Ruling 2:** the opening line is absent when refused, with no fallback anywhere. The no-guilt gate runs on it at runtime.
5. **Ruling 3:** the sixth submission of the day gets a `409` with no model call; `1q` renders; no count or reset time crosses the wire.
6. **S5 (rule 2):** two real calls, run on the Mac, with the output pasted and read.
7. **S6:** every new static string passes the frontend scan, and every generated string passes its gate.
8. **S7 / §3a:** `1j` is a Playwright assertion demonstrated red, and all five assertions run on every drawn W16a state at phone and desktop width, in light and dark.

**Reported UNMET, not approximated (§3 rule 7):**
- **`1s`'s desktop grid**: the shell ruling (D12) takes precedence.
- **"Keyboard up" on a real iOS device** (D13, #407, HW2).
- **`1p`'s wayfinding line**, dropped by Q-C.
- **The truth of the opening line and the correctness of a correction.** No gate can establish either (#271).
- **The paragraph half of the TASKS acceptance** (*"paragraph task returns structure feedback"*): **W16b's**, not met by W16a, and stated on both rows.
- **PRD §4.2's Thursday paragraph (A1).** Thursday serves the journal until W16b ships. The day-kind rule returns `journal` for every date, and the slice row says so rather than the PRD.

---

## 8. What W16a does not claim

- **`sessions.completed` does not become reachable.** Block 4 can reach `done`. But `complete_block` was removed at W11, `minutes` and `completed_at` still have no writer (#349, #361), and block 5 has no `done`. **#259 is unchanged.**
- **#107 and #248 do not close.** This slice writes `source='text'`, not `'item'`, and there is no error→card bridge.
- **#401 stays open.** The harness asserts `/write` and block 4 only.
- **#398 is untouched.** `/talk` stays untyped.
- **#364 is untouched.**
- **There is no paragraph, no structure feedback, no word offers and no deck write.** All of that is W16b's.
- **No raise line, no history, no past entries (Q5).**
- **G1 and G2 narrow wrong journal rows; they do not close them.** A real-word typo passes G2, and G1 cannot show a correction is right.
- **The keyboard is not tested by Playwright**, and **Playwright runs by hand**.
- **PRD §4.2's speaking days are deferred to W15, not abolished.**

---

## 9. Human checks owed

- **HW1: the Mac probe (step 7).** The operator runs it and pastes the output. I read it for three things: is each opening line true of its fixture, is each correction a real error, and does the clean fixture's `did_well` behave as ruled.
- **HW-L: the sixteen `learner_label` strings (S5).** The operator reads all sixteen **before they ship**. A BANNED pass does not show a label names its category in a way a B1 learner understands.
- **HW2: phone, real keyboard.** *Read it over* stays reachable with the keyboard up at every length. This is the `/write` half of #407.
- **HW3: phone, journal end to end.** Read the corrections: do they teach? Then check, with an **independent `psql` count**, that the `errors` rows are ≤2 and that one `writing_submissions` row carries the session id.
- **HW4: back to the session.** Block 4 reads done.
- **HW5: the sixth submission.** `1q` unavailable renders and reads as the same product as `/talk`.
- **HW7: both themes on the phone.**
- **HW8: the non-English state**, which has no design frame.
- **HW9:** `pnpm test:e2e` runs before the Vercel rebuild.

---

## 10. The `BUILD_PROGRESS.md` update block W16a will owe

**Slice row:** `| W16a | Writing output — the journal | 🟡 code-complete | <date> | … |`. **Never ✅.** The row records:
- **Built:** the journal on `/write`; Ruling 1 derived from the log; Ruling 2's contract change; Ruling 3; G1 and G2; `learner_label`; the DDL, named by the number actually taken and worded so `test_record_consistency` reads it correctly; the Playwright harness.
- **Reported unmet:** the `1s` grid, the real keyboard, `1p`, the gates' limits, and the paragraph half of the TASKS acceptance.
- **Suites:** RUN counts for pytest, Vitest, `tsc`, `next build` and `test:e2e`, plus the number of red demonstrations.
- **VERCEL MUST REBUILD, and every server check passes while the old screen is still up.**

**New row, W16b:** `| W16b | Writing output — the paragraph | ⬜ not started — mode PLAN | … |`. It carries:
- `structure`, `word_offers`, `POST /write/keep`, and the Thursday paragraph with the current unit's `output_task_written`;
- **Q-D:** a ceiling of 8, and *"Four more below."* removed;
- **Q-E:** the offer rule, including the recorded refusal of a lemma-level ledger filter on phrases;
- **S6:** the operator reads the first run's offers before Keep is reachable from the screen;
- its own §3 rule 2 call, on the Mac;
- D4, D15, D16 and #406;
- **no PRD amendment** — §4.2's Thursday paragraph is unchanged (A1), and W16b is the slice that meets it.

**Decisions log**, each entry with its reason:
1. Rulings 1–3 and S3–S7: assistant-recommended, operator-accepted 2026-09-14.
2. **The split (S1):** the journal changes an existing contract, while the paragraph adds generated content, one field of which writes cards FSRS drills for months. Those are different risks and need separate approvals. The harness goes in the smaller surface. Thursday stays a journal day until W16b.
3. **A log, not a counter (S2):** PRODUCT-PRINCIPLES §3's first bullet was raised. Ruling 1 becomes log-derived, which is #258's shape, and the payload flag is refused as the shape closest to the deleted manual button. `is_english` was added because non-English counts toward the ceiling but not toward done. A 503 writes no row.
4. **The rule 2 call runs on the Mac (S3):** W5b's precedent. The prompt's *"the key is on the host"* was the operator's error, corrected. Pulling on production without backup, migration or restart would have left unreviewed code one restart from learners.
5. **PRD §4.2: only Mon/Wed/Fri amended (S4, A1)**, old text quoted, speaking returns at W15. Tuesday and Thursday are untouched, and the Thursday gap is reported unmet in the slice row. Putting *"while W16a alone ships"* into the PRD was refused, because it is #82's pattern and it moves the bar.
5a. **Three send-backs applied better than asked (operator, on approval):**
   - `day_kind`'s CHECK admits `'paragraph'` now, with a test pinning that W16a never writes it. This is migration 012's *widen the CHECK once* precedent, so W16b needs no DDL.
   - `is_english` on the log: a non-English submission counts toward the ceiling but not toward `done`. One column serves two rulings, and the asymmetry is argued at the site.
   - The `.env` credential check was read-only, and the value was not printed.
5b. **#409 targeted at W19, not W15 (A2).** A target is a slice that owns the surface; W15 may never open the composer.
6. **The three prompt errors, recorded as errors:**
   - D2: `did_well` is an existing field whose contract changes, and the `"Nice."` fallback survives only on the bot.
   - #402: the prompt's characterisation is the reverse of `/talk`'s code, so the app-text-only rule is new at W16b.
   - D3: the *"max 2 — v2 rule"* attribution is wrong.
7. **Evidenced negative:** block 4 names no retired feature. The prompt predicted a defect and the tree did not have it.
8. **`learner_label` instead of editing `label`:** the bot shares the prompt list.
9. **A new service and prompt:** the bot path stays byte-identical.
10. **"Reading it":** the **second** application of the §1a brand rule, after the close-out import.
11. **`1s`'s grid refused:** the shell ruling takes precedence.
12. **The D6 collapse is layout-triggered.**
13. **Fields nothing renders come off the wire:** `murphy_units`, `has_errors`, `error_type`, `task`, `unit_number` and `mode`.
14. **The harness design:** a production build rather than dev, fixtures generated by Python, projects derived from `1j`, WebKit for the phone, and who runs it and when.
15. **`test_corrections_are_capped_at_three` moved to the service:** the route no longer reaches it.
16. **The bundled design export had to be decoded to be read (S8.2):** a finding the next design slice needs.

**Known issues — new** (severity · target):
- **#404** — `docs/TASKS-v3-web.md` still carries an unstruck W21 row for work that shipped at W1c (*"Off-site backup — pulled forward from W21"*, ✅ verified 2026-08-24, closed #6 with a restore drill, a proven freshness alarm and an unattended cron dump). A reader counting remaining slices counts one that is done, and a planner reaching W21 would rebuild R2 backup. Not corrected here, because striking a row is a scheduling change and the operator owns the schedule. Found by counting the remaining slices against the record rather than against a handover note. · `low` · **W19**
- **#405** — `WRITING_MAX_SUBMISSIONS_PER_DAY` is global configuration that becomes per-user at multi-tenancy. PRODUCT-PRINCIPLES §3; read with #382. · `low` · **W24**
- **#406** — `output_task_written` for units 18, 21, 22 and 23 is unfit as a paragraph prompt: u23 needs audio, and u18 refers to a message that isn't there. · `low` · **W16b** (the body notes that no learner is near those units)
- **#407** — `/write` half. No `apps/web` surface handles the iOS software keyboard (`visualViewport`/`interactive-widget`), and Playwright can only model its height. · `medium` · **W16a, closed or escalated by HW2**
- **#408** — `POST /conversation/save-word` accepts any 1–80 character string; #402's filter guards the offer list, never the write. · `low` · **W15** (the next slice building on `/talk`'s loop)
- **#409** — `/talk` half of #407. The composer on a live daily surface has the same unhandled keyboard exposure, and a W16a phone check does not close it. The body states the exposure: `/talk` is used daily, W15's stated scope may never open the composer, and so no started slice owns the component. · `medium` · **W19** (A2)

**Carried forward:** every still-open issue; none dropped.

**File inventory:**
- the migration `.sql` and its test;
- `packages/core/services/writing.py`;
- `packages/core/writing/{__init__,rules,gates,probe}.py`;
- `packages/core/prompts/writing_correction.txt`;
- the new API router or the additions to `correct.py`;
- `tests/test_writing_{route,request,rules,probe,wiring}.py`;
- `apps/web/components/write/*.tsx` with their tests and Python-generated `*.fixture.json`;
- `apps/web/playwright.config.ts`, `apps/web/e2e/write.spec.ts`, `apps/web/e2e/support/assertions.ts`;
- `prompts/CC-W16-writing-output-PLAN.md`;
- **`specs/design/W16-writing-output.dc.html`**, whose entry records that it is bundled, how it was decoded, and that it was read as DATA and not run.

**Next action**, with this slice's checks at the head:
- HW1, HW-L, HW2–HW5, HW7–HW9.
- **The deploy block**, explicit commands, rehearsed per §5c. Per the Environment table, `bot` runs backup, pull, pip and `core.db`, and root runs `systemctl`.
  1. `sudo -u bot -i`
  2. `cd /home/bot/english-bot`
  3. `scripts/backup.sh`
  4. `git pull`
  5. `.venv/bin/pip install -e packages/core`
  6. `.venv/bin/python -m core.db migrate`
  7. `.venv/bin/python -m core.db status`
  8. `exit`
  9. `systemctl restart english-api` (**`english-worker` not touched, #69**)
  10. `sleep 5`
  11. `curl -s -o /dev/null -w '%{http_code}\n' https://api.foundgrant.com/write/today` → **401**, which proves the route registered
  12. **Vercel rebuild of `main`**, with `pnpm test:e2e` run locally first
- **What could not be rehearsed**, stated in the block: the migrate and the restart against production. Their arguments were checked against the Environment table, and the migrate was run against the dev database.
- **Carried, none dropped:** H3 #299's billed run (journal moved aside first, #309) · H4 #388 · #364 · #401 (narrowed, still open) · #378's interim · W13-i's four phone checks · T1 · T2 · T4 · #352's 33 calls · #306 · #309 · #169 · #387 · #391 (b)(c) · #393 · #396 · #397 · #398 · #376 · #370 · #390 · #307 · #215/#141/#151 · unit 2's generation held on #299/#249 · **W11c and W14 await the operator's ✅** · **§3a met for `/write` and block 4 only.**
