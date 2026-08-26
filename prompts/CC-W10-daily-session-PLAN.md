# W10 — The daily session

**Archived plan. Intent, not state — `BUILD_PROGRESS.md` is the record of what is
built.**

**Mode: PLAN. APPROVED 2026-08-26 and IMPLEMENTED in the same session.** Two
changes were made to the plan at review, before approval, and both are in the
text below: **§3a** (blocks 3 and 4 frozen on unit 1, and block 4's daily repeat
stated as a cost rather than discovered — filed #188) and **§3b** (whose clock
defines `sessions.date`; the reviewer's premise that no column recorded a
timezone did not hold — `users.timezone` has existed since
`001_init_postgres.sql:27`).

Where this plan and the shipped slice differ, the slice row and the decisions log
in `BUILD_PROGRESS.md` are the record. One difference is worth naming here
because it changed the work: the plan proposed fixing **#158** if W8f check 5 had
been run by then. It has not, so #158 is carried.

---


**Mode: PLAN.** Nothing below is built. Slice row goes to 🟡 at the end; the human owns ✅.

---

## Context

`apps/web/app/(app)/page.tsx` has carried one disabled button since W1b, captioned *"The session runner arrives in W10."* This is that slice. It builds the surface PRD §4.1 specifies — five blocks, one button, resumable — and it is where six standing rulings land at once.

**It generates nothing.** Block 3's "8 generated items" has no generator; building one here would put a billed content pipeline inside a surface slice. The session will look thin on day one: 33 cards, no generated items, no lessons. That is the correct output, and the slice's job is to render an empty block honestly rather than reach for something to fill it.

---

## Verification of the prompt's claims against the tree

Every number and file the prompt asserts, checked:

| Claim | Verdict |
|---|---|
| `users.native_language` reads `fa`/`lt`/`fa` | Column exists since `001_init_postgres.sql:19`; the three values are the record's 2026-08-26 production read (#159). Not re-read here — no production access. |
| `grading.equivalence_key` / `distinct_answers` exist | `packages/core/items/grading.py:100`, `:127`. ✅ |
| `/review` reviewer to absorb | `apps/web/components/cards/reviewer.tsx`, reveal → 4 grades, header reads `counts.total_remaining`. ✅ |
| Deck is 33 cards | W8f slice row: 29 → 33, production 16 / recognition 17. Record, not re-queried. |
| 015 is taken | On disk: `001`…`015`. **016 is free.** ✅ |
| `sessions` has no `task_type` CHECK | Confirmed — `task_type TEXT NOT NULL`, no constraint. `task_type='daily'` needs no widening (unlike #47's `errors.source`). ✅ |
| `#171`'s test exists | `tests/test_no_murphy_reaches_a_learner.py`, and it already scans **every** `.tsx` under `apps/web/{app,components}`. ✅ |
| baseline pytest 1765 / 6 skipped, Vitest 74 | W8h slice row. Not re-run (plan mode). |

**Two claims do not resolve, and both are recorded rather than worked around:**

1. **`PRD §11.5` does not exist.** PRD §11 is *Success criteria*, a table with no subsections. The sentence *"No backlog is ever presented"* is at **PRD §12 rule 5**. #160's row cites §11.5 and the W10 prompt repeats it. → file `low`, correct #160 in place with the old wording quoted (#82's shape).
2. **`user_unit_state` has no service reader and zero rows.** Nothing in the repository resolves "which unit is this learner on", and **W11 owns every write to it** — so the unit never advances during W10's lifetime. Blocks 3 and 4 both depend on it. See §3 for the read and **§3a for what it costs**.

---

## 1. Design question 1 — do PRD §4.1's five blocks still fit?

**Finding: yes. No PRD amendment is owed, and this is a return to §4.1 rather than a revision of it.** Named explicitly because the opposite finding was plausible and a later reader will otherwise re-derive it.

| Block | §4.1 says | What exists today | W10 ships |
|---|---|---|---|
| 1 · Review | FSRS due cards, capped | `cards.due_queue` + caps + 33 cards | **Real content.** #160 moves it here from `/review`. |
| 2 · Input | video, transcript, tap-to-save | nothing — W12/W13 | **Empty, honestly.** |
| 3 · Focus | 90-second explanation + 8 generated items | the unit's `can_do` and `grammar_targets` labels; **no lesson (W10b), no generator** | **Labels only, items empty.** |
| 4 · Output | speak or write, corrected, errors → journal | `POST /correct` (W3, ✅ verified) + `output_task_written` on all 24 units | **Real content, written half only — and it repeats daily.** See §3a. Spoken is W14/W15. |
| 5 · Close | 3 lines, tomorrow's preview, XP | nothing generates the 3 lines; XP weighting is W19 | **What you did, plainly. No XP number.** |

Three cells have moved and each is named rather than quietly reconciled:

- **Block 1's parenthetical is unchanged.** #160 is a *return* to §4.1; the standalone `/review` screen is what diverged. No document change.
- **Block 3 renders labels over nothing.** That is **#182 made visible**, exactly as filed — the 82 grammar targets are labels for teaching that exists nowhere. W10 does not paper over it; W10b fills it.
- **Block 5's XP is deferred to W19.** Migration 016 ships the `xp` column (the authoritative table says so) and W10 writes NULL. Inventing an effort weighting here would make W19's numbers incomparable with the first weeks of history — the same reasoning `item_attempts.grade` was left NULL at W6.

**§4.2's weekly rhythm is NOT this slice.** W10 ships one session shape every day; Mon–Sun shapes and the Saturday checkpoint are W11's row. Sunday's "no tasks" is a shape, not a suppression, so a daily session that opens on Sunday contradicts nothing today — named so W11 does not find it silently pre-decided.

---

## 2. Design question 2 — what `GET /session/today` returns, and how a block says "I am empty"

```
SessionToday {
  session_id, date, l1_language,          # per-user, once, not per card (#159)
  current_block: 1..5,
  blocks: [Block, Block, Block, Block, Block],
}

Block {
  n, kind: "review"|"input"|"focus"|"output"|"close",
  state: "ready" | "empty" | "done" | "unavailable",
  payload: {…} | null,
}
```

**The two states the prompt asks to keep apart are kept apart by construction, at three levels:**

1. **A whole-route failure is an HTTP error**, never five empty blocks. The client's `problem` branch — the shape `reviewer.tsx` already uses — renders a retry, never the empty copy.
2. **`empty` is only ever written after a successful read.** The service computes it from a query that returned zero rows, or from a dependency that does not exist yet (block 2, block 3's items). It is a fact.
3. **`unavailable` is only ever written from a caught exception** while building that one block. One block's dependency failing must not take the session down, and must not read as "nothing to do". Its copy is a quiet *"That part didn't load. It'll be here next time you open this."* with a retry — no apology, no blame.

A test asserts all three: `empty` and `unavailable` never collapse, and a route-level failure produces neither.

**When nothing is due, the app offers watching.** The copy lives in exactly one place — block 1's empty payload — and is reachable today: 33 cards against a 12-new/80-review cap means a learner finishes the deck and sees it. It reads, plainly:

> Nothing's due today. Go watch something you actually enjoy — that counts.

No filler item, no "practise anyway", no streak language. **It does not link anywhere**, because the video side is W12/W13. **A session-level variant is deliberately NOT built**: block 4 always has an output task, so an all-blocks-empty session is unreachable today, and a green test over an unreachable path proves nothing (CLAUDE.md §3 rule 4). Filed against **W13**, where the message becomes a real suggestion with an actual video.

**Route shape.** `GET /session/today` is a plain `def` that parses, authorises, calls **one** service function (`core.services.sessions.today(user_id, now=…)`), and serialises. All five blocks are hydrated inside that one call. `POST /session/{id}/block/{n}/complete` is the second route (ARCHITECTURE §6).

**`presentations_for` is inherited, not rewritten.** `core/services/items.py:389` carries the cross-slice contract in a comment: W10 calls `presentations_for` and writes no serialiser. Block 3's items list is `[]` today and goes through that function anyway, so the seam is exercised from day one rather than at W10a.

---

## 3. Design question 3 — where session state lives, and the migration number

**Migration `016`, and it forces no renumber.** `docs/TASKS-v3-web.md`'s authoritative table already reserves 016 for W10 (`sessions` extension). On disk the highest is 015. **`docs/TASKS-v3-web.md` is not edited by this slice.** #185 (the reservation scheme keeps producing renumbers) is untouched and stays open with no owner — W10b's owed 017 renumber is W10b's, at its implementation time.

`migrations/016_session.sql`, following 015's header conventions:

```sql
ALTER TABLE sessions ADD COLUMN block_breakdown JSONB;
ALTER TABLE sessions ADD COLUMN minutes INTEGER;   -- CHECK 0..600 or NULL
ALTER TABLE sessions ADD COLUMN xp INTEGER;        -- CHECK >= 0 or NULL; W10 writes NULL

CREATE UNIQUE INDEX sessions_one_daily_per_user_per_date
    ON sessions (user_id, date) WHERE task_type = 'daily';

ALTER TABLE card_reviews ADD COLUMN session_id BIGINT
    REFERENCES sessions(id) ON DELETE SET NULL;
ALTER TABLE card_reviews ADD COLUMN typed_response TEXT;
ALTER TABLE card_reviews ADD COLUMN typed_matched BOOLEAN;
    -- CHECK (typed_matched IS NULL OR typed_response IS NOT NULL)
```

- **`block_breakdown` is the resume state**, not a report. It holds per-block `state` and what was served. `sessions.payload` already exists and is not reused: it is v2's per-task-type grab bag and overloading it would make one column mean six things.
- **The partial UNIQUE is what makes "the session opens each day" idempotent** — two tabs, or a worker pre-build racing a lazy create, cannot make two daily rows. Same instrument as 015's `cards_one_card_per_lemma`, and for the same reason: a NULL-tolerant plain UNIQUE cannot express it. **It enforces one row per date and cannot tell you the date was computed wrongly — which is why §3b is settled explicitly and in the file's own comment.**
- **`card_reviews` gains three columns and this is a departure from the authoritative table's one-line description, named rather than absorbed.** The table says "`sessions` extension"; #157's typed answer has nowhere else to live, and `card_reviews` is the append-only log W7 built precisely so the individual grades survive. `session_id` ships now for W7's stated reason about `item_attempts`: adding a column later is one line, but the months of blank history in between are exactly where W19 needs it.
- **No `ALTER TABLE users`, so #48 does not fire.** Stated rather than omitted — #48 has recurred because each case looked like the one where the rule did not apply.
- **PRODUCT-PRINCIPLES §2 position, post-011 form:** `sessions.user_id` and `card_reviews.user_id` already reference `users(id)`. **This slice adds no user-keyed table and enlarges nothing.**
- **`schema_version` 15 → 16.** Every server step is written out as an explicit command for the human; no acceptance criterion here can be satisfied by a server action.

**Resolving "this week's unit" — read-only, and W11 keeps its table.** New `core/services/syllabus.py::current_unit(conn, user_id) -> int`: the lowest `unit_number` with no `passed_at` row in `user_unit_state`, defaulting to **1**. It never writes. W11 owns the writes; `locked` staying "the absence of a row" (`core/syllabus/states.py:11`) is untouched.

---

## 3a. Blocks 3 and 4 are frozen on unit 1 until W11, and block 4 repeats every day

**This is a stated cost, not a discovery, and it is the one thing in this slice that is invisible until tomorrow.**

`user_unit_state` is empty and **W11 owns every write to it**. `current_unit` therefore returns 1 for both learners and keeps returning 1 no matter what they do. Both blocks that depend on it are static until W11 ships:

- **Block 3** renders unit 1's can-do and grammar labels, unchanged, every day. Already named — #182 made visible.
- **Block 4** renders **unit 1's single `output_task_written`, verbatim, every morning.** Day two is the same task. Day thirty is the same task. Unit 1 has one written task and there is no rotation to draw on.

**Why that is worse than an empty block, and why it still ships.** An empty block says *nothing here yet* and is honest. A block showing an identical prompt every day reads as the app being broken or not paying attention — and it is the one block this plan counts as working content. But the task is real, doing it twice is not harmful, and shipping block 4 empty would remove the only production surface in the session. **So it ships repeating; the failure would be presenting it as working content without saying it repeats.**

**No workaround is built.** Rotating tasks, drawing from adjacent units, or advancing the unit are all unit progression, and pulling progression into a surface slice is exactly the widening CLAUDE.md §8 forbids. **Do not build unit advancement here.**

**Filed against W11 at `medium`** — a daily-visible repeat on the session's only output surface, seen by both learners every morning until W11 lands. W11's row already owns unit advancement; the filing makes the dependency explicit rather than leaving W11 to find out that W10 shipped depending on it.

---

## 3b. Which clock defines `sessions.date`

**The learner's local date, from `users.timezone`. Stated here, in the migration comment, and at `today(user_id, *, now)`'s signature.**

**The premise that nothing on `users` records an offset does not hold, and the correction makes this cheaper rather than larger.** `users.timezone TEXT DEFAULT 'Europe/Vilnius'` has existed since `migrations/001_init_postgres.sql:27`. It is read by `core.scheduling.list_candidate_users()` (`EligibleUser.timezone`) and converted by `core.services.sessions.local_today(timezone, now)` — **which is already how every other `sessions.date` in that table is computed**, across eleven task types. **No new column, no missing-column filing, and nothing inferred from a request header.**

Choosing UTC was the live alternative and is rejected for a concrete reason: `sessions.date` would then mean the learner's day for `quiz`, `reading`, `diary` and eight others, and the server's day for `daily`, **in the same column**. A learner opening the session at 00:30 Vilnius would get a row dated yesterday, sitting beside a `reading` row dated today.

- `today(user_id, *, now)` reads the learner's timezone and derives `local_today(tz, now)`. `now` is injected, as it already is throughout `apps/api/routers/cards.py` — this names a convention rather than adding machinery, and it keeps the date assertable in a test without freezing the clock (§3 rule 6).
- **`assign_daily` uses the same function.** The job computes each learner's *local* tomorrow from `list_candidate_users()`, which already carries the timezone, so the pre-create and the lazy create cannot disagree at the boundary. Under UTC they would have disagreed exactly once per day, and the partial UNIQUE would have accepted both rows — it enforces one row per date and **cannot tell you the date was computed wrongly.**
- **What a learner studying at 00:30 Vilnius sees: a fresh session for the new day**, and yesterday's leaves nothing behind.

**A boundary test pins it**, and pins it in the direction that would otherwise be silent: two `GET /session/today` calls either side of local midnight — one at 23:50 and one at 00:10 Vilnius, both with an injected `now` — produce **two** rows with consecutive dates; two calls either side of *UTC* midnight in the middle of a Vilnius evening produce **one**.

**One divergence is named rather than reconciled.** `core.services.cards._day_start` (`cards.py:359`) counts the daily card caps against a **UTC** day, deliberately and with its reason recorded at W7. The session's date is local. **These answer different questions** — "is this a new session" versus "has this learner used up today's review budget" — and W10 does not quietly align them. Recorded in the decisions log so a later reader finds the asymmetry explained rather than re-derives it as a bug.

---

## 4. Design question 4 — the checkpoint

**Out of scope, and out of scope by the same rule the generator is.** The checkpoint is 12 items at 80% with no generator, and `docs/TASKS-v3-web.md` gives it to **W11**. W10 builds the daily session and does not special-case Saturday.

**#170 is executed by not doing the thing**: no checkpoint re-sources vocabulary from the learner's due cards in W10. W8d's redistribution stands as shipped, `lexeme_items` stays 0 in all 24 rows, and the trigger for #170 remains deck size at W13.

**#168 cannot get its evidence here, and that must be recorded rather than left as a stale target.** #168 waits for "the first slice with evidence about which item types actually serve a grammar target" — that is the generation slice, not this one. Same for **#102** (meaning-equivalence call), **#103** (the generator prompt never asks for an explanation), **#110** (the no-guilt scan cannot reach generated content), **#120** (`JUDGE_BATCH` declared and never called), **#105** (the "show me a cue" affordance needs generated items to be worth building). All six are targeted `→ W10` today and W10 as scoped ships no generator. **They are re-targeted to a named successor — proposed `W10a — item generation` — with the reason stated once**, not left pointing at a slice that shipped without them.

---

## 5. The six rulings — where each one lands

### #160 · review lives inside the session
- Block 1 hydrates `cards.due_queue` into the session and grades through the existing `POST /review/{card_id}/grade`.
- **`/review` stays reachable and loses its counter.** `reviewer.tsx:163` renders `{state.counts.total_remaining} left today` — that is the duty. The nav tab stays: `test_bottom_nav_has_the_four_places_the_app_has` pins four items and removing one is a nav redesign W19 would have to re-decide. **The count is the substantive half of the ruling; the tab is not.**
- The API keeps returning `DeckCountsOut` (the session sizes block 1 from it). The ban is on *rendering*, the same standing `murphy_units` has under #187.
- **CLAUDE.md §4's "never present a backlog" is the binding rule**, not §5 and not a preference. #160's PRD citation is corrected to §12 rule 5 (see §Context).

### #157 · typed answers, split by card type
- `production` and `cloze` take a typed answer. `recognition` keeps W6's self-mark — its answer is a meaning, and `equivalence_key` folds variants of a known answer, it cannot judge a paraphrase. Grading wording would fail a learner for being right in different words (§4, no guilt).
- **Graded through `grading.equivalence_key` / `distinct_answers` and nothing else.** No second normaliser, no comparison in TypeScript — `test_no_answer_comparison_in_typescript` already forbids it and the client physically cannot do this.
- **Two calls, because the client must not hold the verdict.** `POST /review/{card_id}/attempt {text}` → `{matched}`, read-only. Then the existing grade call carries `typed_response`; **the service recomputes `typed_matched` server-side** rather than trusting a client-supplied boolean (#108's lesson).
- **The four grade buttons stay, and the typed attempt precedes them.** This is the whole of #157's stated reason: *a card that shows the answer on a tap and then asks the learner to grade themselves cannot distinguish recall from recognition*. Committing before the reveal fixes that. **Machine-marking a card outright is deliberately not done**: `cards` has no `accepted_variants` column, so a typed production card grades against `back` alone, and card 17's `_____s` hint (#147) plus a one-word back would produce wrong-answer marks for correct English. The verdict informs the self-grade; it does not replace it.

### #159 · the L1 language reaches the card
- `l1_language` travels on the **envelope**, once, from `users.native_language` via `cards.user_id` — not on every `CardFace`. It is a per-user fact and eighty copies of it is eighty chances to disagree.
- `apps/web/components/cards/card-face.tsx`'s `ARABIC_SCRIPT` sniff (`:87`, `:119`) is replaced: the `lang` tag comes from the field, and `font-l1` is applied **only** for Arabic-script L1. Today the component is right for the wrong reason and silently wrong for Morkyte.
- **Consumer 3 — the generator prompt — is not in this slice**, because this slice generates no glosses. Recorded against W10a/W13 so #159 closes on evidence rather than on plumbing alone.
- Small §2 improvement carried with it: `review_queue` currently calls two service functions from one route. It becomes one — `cards_service.review_queue(...) -> ReviewQueue(cards, counts, l1_language)`.

### #170 · checkpoints stay pure grammar
See §4. Executed by not doing it, recorded so the absence is a decision.

### #171 · no surface renders a Murphy citation
- **The existing test is extended, not copied.** `tests/test_no_murphy_reaches_a_learner.py` already scans every `.tsx`, so W10's new components are covered the moment they exist.
- What is genuinely new is the **payload**: block 3 serialises a unit's `grammar_targets`, and `GrammarTarget` carries `murphy_units`. A third check joins `murphy_offenders()`, asserted **at the serialisation seam** — the learner-visible projection of a grammar target has no `murphy_units` key — not by grep. Both fields, one file, one rule.

### #182 · the teaching that exists nowhere
Not fixed here (W10b, approved). W10's obligation is to ship the **block-3 contract W10b reconciles against**, and to state it in the record so W10b's first implementation step has something to read: `{unit_number, can_do, grammar_targets: [{target}], lesson: null, items: []}`.

---

## 6. Files

**New**
- `migrations/016_session.sql`
- `packages/core/sessions/__init__.py`, `blocks.py` — pure block assembly, no SQL, no HTTP.
- `packages/core/services/sessions.py` — **extended**, not replaced. `today()`, `complete_block()`, `current_unit` reads. Every query for the daily session.
- `apps/api/routers/session.py` — two plain `def` routes.
- `apps/web/app/(app)/session/page.tsx`, `apps/web/components/session/*.tsx` — runner, block shells, empty/unavailable states.
- `tests/test_migration_016.py`, `tests/test_session_route.py`, `tests/test_sessions_service.py`
- Vitest: `session-runner.test.tsx`, `blocks.test.tsx`, `typed-card.test.tsx`

**Changed**
- `apps/web/app/(app)/page.tsx` — the button is enabled and points at `/session`. `ComingLater` goes.
- `apps/web/components/cards/reviewer.tsx` — counter removed; typed attempt for `production`/`cloze`.
- `apps/web/components/cards/card-face.tsx` — `l1_language` prop replaces the script sniff.
- `apps/api/routers/cards.py`, `apps/api/schemas/__init__.py`, `apps/web/lib/api.ts`
- `packages/core/services/cards.py`, `packages/core/services/syllabus.py`
- `apps/worker/jobs.py` — `assign_daily`.
- `packages/core/services/items.py` — `validator_version = VALIDATOR_VERSION` filter on `list_bank` / `bank_for_session` (TASKS W10, and cheap now: `items` is empty on production).
- `tests/test_web_shell.py`, `tests/test_no_murphy_reaches_a_learner.py`

**`assign_daily`, honestly.** Registered in `apps/worker/jobs.py` over `core.scheduling.list_candidate_users()` — which already carries each learner's `timezone`, so it pre-creates **each learner's local tomorrow** (§3b) and nothing else, **because there is nothing to generate**. `GET /session/today` creates the row idempotently if the job has not run — safe under the partial UNIQUE. The job ships with one step rather than being invented later under time pressure, and its empty generation half is recorded.

**TASKS' criterion *"Report the item accept rate from the first `assign_daily` run"* cannot be met by this slice, and the number is reported as unmeasurable rather than the bar being moved (CLAUDE.md §3 rule 7).** Nothing is generated, so there is no accept rate. It belongs to W10a and is carried there verbatim.

**Also unmeasurable and said so: the 12-minute hard floor.** With blocks 2 and 3 carrying no content, a real session is block 1 + block 4 + close. W10 records `minutes` (computed server-side from `delivered_at` to `completed_at`, clamped — never client-supplied, per #108) and cannot enforce a floor against two empty blocks. Checkable at W12.

**#158, named because W10 is its filed target and this slice edits that exact component:** the L1 gloss renders twice on a production card after reveal. The fix is dropping the reveal-side `meaning` when it equals the front's first line, with the value-level assertion #154 has. **It waits on W8f check 5's `split_part` read**, which is unrun — so it is planned as *do it if the query has been run by then, otherwise carry it*. Not silently absorbed either way.

---

## 7. Constraints held

- **Nothing is generated while a learner waits.** `GET /session/today` makes zero model calls, asserted by an ASGI integration test with `tests/support/netguard.py` armed.
- **No red anywhere**, and the banned-phrase scan in `tests/test_web_shell.py` already covers every `.tsx`, so the new components are in scope automatically. A `test_no_red_reaches_the_session_screen` joins the two that guard `/write`.
- **The new ruling's test**, in `test_today_still_offers_one_button`'s shape: `test_no_surface_presents_a_backlog_count` — no learner surface reads `total_remaining` / `due_now` / `review_remaining` / `new_remaining`, and home renders no badge. Demonstrated red first.
- `test_today_offers_exactly_one_action` asserts `"disabled" in source` and **is inverted, not deleted** — the button is now enabled and the assertion becomes that it links to `/session`.
- Every route is a plain `def` that parses, authorises, calls one service function, serialises.
- **#186 is live in the bot and this slice does not fix it.** Named so it is not absorbed by proximity.
- **Not this slice:** item generation · lesson content (W10b) · the video suggestion's link (W13) · #186 · #165's `syllabus_unit_lexemes` removal · the other 21 lessons · anything Telegram.

---

## 8. Verification

**Automated** — report the split, hold the baseline exactly:

```bash
pytest -q
```
```bash
cd apps/web && pnpm vitest run
```

Baseline to hold: **pytest 1765 passed / 6 skipped / 0 failing · Vitest 74 across 7 files.**

Specific tests that must be **demonstrated red before they are accepted** (§3 rule 4): the backlog-count scan, the Murphy payload assertion, the empty-vs-unavailable separation, and the netguard assertion on `/session/today`.

**Local, against the Mac dev database:**
```bash
python -m core.db migrate && python -m core.db status
```
Expect `Applied: 001–016, Pending: (none)`.

**Production — every step an explicit command for the human, in `Next action`:** backup → pull → `pip install -e packages/core` → migrate → restart, with `core.db status` pasted back **verbatim** (the reporting discipline W8c established for #141).

**On a phone, and these are the ones the suite cannot find:**
1. Open the session, grade a card in block 1, **lock the phone**, reopen — the session resumes at the same block.
2. Finish the deck and read block 1's empty copy. **It must offer watching and mention nothing that was not shown.**
3. Read block 3. It renders a can-do and three or four grammar labels and **nothing that teaches them** — confirm that is what #182 looks like on a screen, and say whether it is tolerable until W10b.
4. **DAY TWO — the only check on this list that cannot be run in the same sitting, and the defect it looks for is invisible today.** Open the session on a second calendar day and read block 4. It is **the same writing task as yesterday**, and it will be the same one until W11 (§3a). Say whether that is tolerable, or whether block 4 should ship empty instead. Confirm at the same time that nothing accumulated overnight: no badge, no count, no mention of yesterday.
5. Type an answer on a `production` card. Confirm the verdict appears **before** the four buttons make sense to press, and that a near-miss does not read as a rebuke.
6. `/review` opened directly — no count anywhere on it.

---

## 9. BUILD_PROGRESS.md update block (written at the end of implementation)

Slice row **🟡**, never ✅. Decisions log carries: where each of the six rulings landed with its issue number; the five-block finding and that **no PRD correction is owed**; the two unresolved citations (§11.5, and `user_unit_state` having no reader); **that blocks 3 and 4 are frozen on unit 1 until W11 and block 4 therefore repeats one writing task every day, with the reason and the rejected alternatives (§3a)**; **that `sessions.date` is the learner's local date from `users.timezone`, why UTC was rejected, and the deliberate divergence from `cards._day_start`'s UTC cap day (§3b)**; the empty-state copy and why it offers watching rather than practice; the migration number taken and that it forced **no** renumber; the `card_reviews` departure from the authoritative table's one-line description; and the six issues re-targeted off W10 onto the generation slice.

New known issues to file: the §11.5 citation (`low`), **the frozen unit and block 4's daily repeat (`medium`, W10 → W11)**, and anything else the build surfaces. File inventory. **Next action reproducing every carried check in full, none silently** — W8f's checks 4 and 5, W8c's slang card, W8b's two phone checks, the typography pick at `/type` (#146), and the twenty-one still-unrun items, plus W10's own six above — **with check 4 marked as day-two so it is not run and reported from the same sitting as the rest.**

Stop when the update block is written. **Do not start W10b.**
