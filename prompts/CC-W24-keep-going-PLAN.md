# W24 — keep going. The plan prompt, the approved plan, and the approval with rulings (2026-09-27)

Archived by W24a (CLAUDE.md: `prompts/` records intent, never build status — `BUILD_PROGRESS.md` is the record). Three parts — the wording as given, with some bullet lists and one table condensed to single lines: **(1)** the plan prompt, **(2)** the plan Claude Code returned, **(3)** the operator's approval with rulings R1–R12.

## (1) The plan prompt

# W24 — "Keep going": something to do every time, a daily video, pictures. PLAN mode.

**Reconcile against the tree and the record first.** Read `PRODUCT-PRINCIPLES.md`, `docs/PRD-v3-web.md`, `docs/TASKS-v3-web.md` and `BUILD_PROGRESS.md`.

**Return a plan only.** No code is written until the operator's approval arrives in writing. One Claude Code session on this repo at a time (#417).

**The standing rules hold:**
- no billed call by Claude Code, no SSH, and no production entrypoint;
- every new test demonstrated red;
- Playwright screenshots of every asserted state;
- migration numbers are taken when the file is written;
- **nothing is marked ✅.**

## 0. Operator decisions of 2026-09-27

Write these into the decisions log when this slice is approved, not before.

1. **The app should always offer something to do.**
   - When today's session is finished, and on the Sunday rest screen, the learner sees a short, optional "keep going" choice instead of a dead end.
   - The model is Duolingo's "there's always a next thing".
   - **It keeps our copy rules:** no counts, no scores, no backlog and no guilt. It is optional and never nagging.
2. **A video every day**, replacing Monday / Wednesday / Friday. This amends PRD §4.2's cadence.
3. **Pictures for concrete vocabulary should actually appear.** W13d built them, but no word is approved yet.
4. **The operator has asked for more input and more speaking.** The assistant's advice was that input volume and speaking drive fluency more than exercises do.

**If any of these conflicts with `PRODUCT-PRINCIPLES.md` or the PRD:** quote the clause; state the conflict; propose the smallest change that honours both; **ask the operator.** Do not silently override a principle.

## 1. First, record 2026-09-27 (the plan lists it; it is written only on approval)

**Evidenced on the operator's paste:**
- **The first `bank --apply` stopped** on `anthropic.BadRequestError 400: You have reached your specified API usage limits. You will regain access on 2026-10-01 at 00:00 UTC.`
  - The operator then raised the limit.
  - **Finding:** the live app shares this key, so every learner LLM call was failing until the limit was raised.
  - **File it:** a spend-limit breach is invisible to the operator. Should Sentry receive it as its own alarm? Propose an answer.
- **The second `--apply`:** `generated rows written: 41`, with calls `generation 12, naturalness 11, probe 48, target 47`; **listening C1 6 of 6 discarded** as `schema_error … item_type_note Extra inputs are not permitted [input_value=None]`.
- **The counts:** grammar A2 27 · B1 26 · B2 26 · C1 27 | listening A2 6 · B1 12 · B2 10 · C1 0 | speaking B1 3 · B2 3 | vocabulary A1 26 · A2 46 · B1 89 · B2 79 · pseudo 120.
  - The dry run afterwards printed `cohorts: 10`, `at most: 148`, and "NO — short listening C1 by 1". **The operator did not run it.**
- **Deploy:** host `0f1ef32`; `prune` deleted ids `[141, 205]`; `english-api` and `english-bot` restarted; `/health` returned `{"ok":true,"schema_version":33}`; Vercel was redeployed.
- **Operator's observation:** on desktop, `/session` renders as a narrow phone-width column with very small text.

## 2. What the plan must cover

### 2.1 The C1 listening fix (small, do it first)
- The generator's strict schema refuses a whole item for an **extra key whose value is null or empty**. Seen twice: `item_type_note: None`, and earlier `tiles: []` on a cloze.
- **Drop extra keys whose value is `None`, `""`, `[]` or `{}` before validation, and log their names. A non-empty extra key is still refused.**
- **Red tests:** both observed shapes, plus a non-empty extra that must still fail.
- **Add `core.placement.bank --only listening:C1`** (or equivalent), so the operator can fill one cell for about 20 calls instead of 148. Dry by default, with the ceiling printed.

### 2.2 "Keep going"
**First, read what exists:** what Today shows after the session is complete; the Sunday "Your week" screen; "practise anyway"; `/practise`, `/write`, the conversation surface, the video library and Review.

**Then propose the smallest addition** that gives a learner who has finished, or who is on Sunday, a choice of **two to four optional next things**, drawn from what already exists:
- **Watch another video** from the library. State how many videos exist per learner level and whether saved phrases work from them.
- **Talk.** The conversation surface, voice where `VOICE_ALLOWED_USER_IDS` allows it (#364), typed otherwise.
- **A few more cards**, only if any are genuinely due or near-due. Never invent a backlog.
- **Write a few lines.**

**Say, for each:** what it costs in billed calls per use; whether it writes to the error journal (only genuine, self-produced errors may be written); how it respects the daily ceiling on LLM use, if one exists.

**One rule: nothing shows a count, a score or a backlog, and nothing says the learner "should".**

### 2.3 A daily video
- What decides Monday / Wednesday / Friday today?
- What does a daily cadence need? Library size per level; the pipeline's cost per new video, if any; what happens when the library runs out. **Never a repeat presented as new.**
- If the library cannot sustain daily, **say so with numbers** and propose the fallback.
- Amend PRD §4.2's cadence rows on approval.

### 2.4 Pictures (W13d-A1)
- **On the Mac only**, run `core.images.bank --propose --live` (network to Wikidata and Commons; **0 billed**) for the concrete, picturable lemmas that actually sit in the two learners' cards and the placement bank. **Aim for 60–100 words.**
- Produce the contact sheet for the operator to read.
- **Do not approve anything:** a line in `data/lexeme_images.tsv` is the operator's approval.
- **In the plan, state the host commands** to load the approved set (`--load`, then `--load --apply`).
- **Also answer #451:** may the credit link to the Commons page instead of printing the title? Recommend one answer.

### 2.5 A picture-based vocabulary exercise (option, operator decides)
- Propose, but **do not build without approval**, one item type that uses the approved pictures.
- **Shape rules:** it only uses words with an approved picture; the distractors are other approved pictures; no picture of an abstract word; licence credit stays visible.
- State where it would live: Review, "keep going", or both.

### 2.6 Desktop layout
Is the narrow `/session` column on desktop intended? If it is not, propose the smallest fix: width and type scale on wide screens only, with **phone layout unchanged, asserted by the existing screenshots**.

### 2.7 The web settings screen (#454): scope only, do not build here
Settings is still missing: reminder time, pause, interests and explanation language, plus operator approve / decline / revoke (#97). W22 cannot deploy without it. **State its size. Recommend** whether it is its own slice (W25) before W22.

## 3. The plan's shape
1. **The reconcile:** what exists, quoted from the tree.
2. **Conflicts with `PRODUCT-PRINCIPLES.md` or the PRD**, each quoted, with a question for the operator.
3. **The split into sub-slices,** in order, each with: files; migration (if any); tests; screenshots; billed-call impact; operator steps (probes and host commands, **one block per role, #422**).
4. **What stays open.**

Stop after the plan.

---

## (2) The approved plan, as returned

### W24 — "Keep going": something to do every time, a daily video, pictures — PLAN

**Context.** The operator (2026-09-27) wants four things:
- the app should never dead-end after the session or on Sunday;
- a video every day;
- the W13d pictures should actually appear;
- more input and more speaking.

Two things from the launch also have to be recorded and fixed:
- listening C1 was discarded 6 of 6 on an empty extra key;
- the API spend limit was hit invisibly.

This is a plan only. No code, no record edit and no network call until the operator approves in writing. The standing rules hold: no billed call by Claude Code, no SSH, no production entrypoint, every new test demonstrated red, Playwright screenshots of every asserted state, migration numbers taken when the file is written, and nothing marked ✅.

---

## 1. The reconcile: what exists, from the tree

### 1.1 Placement bank (`packages/core/placement/bank.py`)

**Flags.** Only `--free`, `--live`, `--sample`, `--apply` and `--journal` exist (`:442-449`).
- It is dry by default (`:464-466`).
- A billed run makes the operator type back the printed ceiling (`:479`).
- **There is no `--only`.**

**The ceiling.** `calls_for` (`:243-259`) computes it. A listening cohort of 6 slots costs **20 calls** (`tests/test_placement_bank.py:136-150`).

**Targets.** `LISTENING_PER_BAND = {"A2":6,"B1":12,"B2":12,"C1":6}` (`targets.py:42`). The readiness minimum for C1 is **1** (`readiness.py:53-74`). That is why the dry run prints "short listening C1 by 1".

**Where the schema refuses.**
- `schema.py:13-15` says: *"`extra="forbid"` everywhere is load-bearing. A generator that invents a field … must fail loudly … rather than have the field dropped on the floor and the item shipped without whatever it was for."*
- The refusal happens in `generate.py:948-956`, where `_draft_to_item` → `parse` raises `ValidationError` and the draft is discarded as `schema_error`.
- `_draft_to_item` (`generate.py:761-811`) is shared by the bank and the focus/checkpoint generator.

**Evidence of the defect.**
- `tiles: []` on a cloze: `w18-placement-journal.jsonl` line 4. `ClozeCuedItem` has no `tiles` field; only `ErrorSpotItem` does.
- `item_type_note: None`: the operator's paste. The string appears nowhere in the repo, so the model invented it.
- `l1_gloss_note` (non-empty, #264) is already refused, and `tests/test_checkpoint_supply.py:578` asserts that.

### 1.2 The "done" state, Sunday, and "practise anyway"

**Home (`app/(app)/page.tsx:40-73`) has no done state.** It always shows "Start today's session" and the link "Or practise or write."

**`/session`'s done block is unreachable.**
- The block is at `runner.tsx:148-155` and its copy at `copy.ts:171-174`: *"Done for today." / "Same time tomorrow…"*.
- It reads `sessions.completed`, which has had **no writer since W11** (#361, #349, #259).

**Per-block `done` is derived and does work.** `_derive_done` (`sessions.py:1769`) marks each block done from its own evidence:
- review: `card_reviews`
- input: `video_assignments.completed_at`
- focus: `item_attempts`
- output: `writing_submissions`

It writes the result to `block_breakdown` on every hydration.

**The close block always offers "Talk with the app" → `/talk`** (`blocks.tsx:446-461`).

**Sunday** (`components/week/sunday-home.tsx`):
- It shows "Your week." / "Nothing is asked of you today." and the report.
- It has no session button (`:13-20`).
- There is one low-emphasis link, **"Or practise anyway."** → `/session` (`:89-99`).
- `copy.ts:18` bans "practise anyway" as filler inside the session. Both uses are ruled and they do not contradict each other.

### 1.3 The surfaces "keep going" would draw on

Cost is billed calls per use. Journal means writes to `errors`.

| Surface | Cost per use | Journal | Daily ceiling |
|---|---|---|---|
| **Video** (block 2 only, `routers/video.py`) | 0 | none | — |
| **Talk** (`/talk`) | topics 1 + open 1 + 1 per turn + close 1 LLM; +1 STT per voice turn | close writes `journalable` corrections from typed turns only; voice turns never (`guards.py:64`) | `CONVERSATION_MAX_TURNS_PER_DAY`, default 30, global (#382); 409 `cap_reached`. Topics are not under the cap. |
| **Review** (`/review`) | 0 (no `llm`/`speech` import) | none | review cap 80 |
| **Write** (`/write`) | 1 LLM per submission (+1 JSON repair possible) | yes, `record_errors(…,"text")` for English entries with corrections, integration-tested | `WRITING_MAX_SUBMISSIONS_PER_DAY`, default 5, global (#405); 409 `cap_reached` |
| **Practise** (`/practice`) | 0 (TTS per tap on audio items) | none | — |

**Video details that matter:**
- **There is no video library screen.**
- Save-a-word from a video always answers **"No definition for that one yet."** `video_glosses` is empty because `core.video.explain --apply` has never run.

**Voice.** `VOICE_ALLOWED_USER_IDS` is enforced in `conversations.voice_allowed_for` (`:152-183`). Typed talk is never gated.

**There is no overall per-learner LLM ceiling.** There are only the two caps above plus per-hour rate limits (`apps/api/deps.py:162-193`).

### 1.4 Video cadence

**What decides Monday/Wednesday/Friday:** `WEEKDAYS = (0, 2, 4)` in `packages/core/video/assign.py:28-36`. On other days `today_for` returns `None` and block 2 is `empty` (`services/video.py:678-686`).

**Assignment is a manual weekly CLI.**
- The command is `core.video.assign --user N --week-of D [--apply]`.
- It refuses fewer than 3 videos (`:228-230`).
- **Nothing schedules it.**
- **The only assignment ever recorded is user 3, week of 2026-09-07.**

**Schema.** `video_assignments` has `UNIQUE (user_id, assigned_for)` (`migrations/019`), so a second video on the same day is impossible today.

**Repeats.** `seen_penalty = 1.0` exceeds the sum of every weight, so a repeat is never selected.

**Pool and cost.**
- 13 channels (`data/video_channels.json`).
- Refresh is `core.video.refresh --apply`. It is operator-run and billed on Apify, measured at **$0.58 per invocation of up to 40 transcripts** (#321).
- Transcripts are purged after 30 days (`services/video.py:52`), so a pool that is not refreshed empties itself.
- The last measured refresh (2026-09-01, #329) added **six clips, all six in band** (Friends / The Office). Teaching and lecture channels sit below the 93% floor.
- **The Mac's dev database holds 0 videos** (rehearsed). Current depth per learner is a production read (Q-V1 below).

### 1.5 Pictures (W13d)

**Commands:** `core.images.bank --propose [--live --contact C --out DIR] [--lemmas …] [--limit N]` and `--load [--apply --contact C]`.

**What `--propose --live` does:**
- It sends 4 requests per lemma, serially, with a 1 s pause.
- It writes `proposals.tsv`, `refused.tsv` and `sheet.html` to a directory outside the repo.
- It writes no database row.

**What the default lemma query takes** (`lexeme_images.proposal_lemmas`): nouns from **cards and the syllabus, not the placement bank**. It was measured as *"mostly abstract nouns"* (`bank.py:372-375`), so `--lemmas` with a curated list is the working path.

**`data/lexeme_images.tsv` is header-only (#449).**

**The card credit** (`card-image.tsx:56-84`) reads "Picture: author · licence (linked) · Wikimedia Commons (linked to the file page)". **The title is not printed.** That is #451.

**The Mac holds no production cards** (dev `cards` = 11, `placement_bank` = 0). The candidate list therefore needs a host read.

### 1.6 The desktop column is intentional

- The shell is `max-w-lg` (512 px) at every width (`app/(app)/layout.tsx:8-11,22`). The comment says *"Max width is a phone's width even on a laptop … a second design to maintain for a screen nobody uses."*
- W1b's decision (`BUILD_PROGRESS.md:1649`) and D12 (`:680`, which refused the design's two-column `1s` grid) record it.
- There are no `md:`/`lg:` breakpoints in the shell.
- **Screenshots are review artefacts, not baselines.** No spec calls `toHaveScreenshot`, so "phone unchanged, asserted by the existing screenshots" is not true today. W24c adds real baselines.
- There is no e2e coverage of home, the Sunday home, `/week`, `/practice` or the session done state.

### 1.7 Sentry and the spend limit

- `llm.py` never calls monitoring. A 400 becomes `LLMError` with no retry (`llm.py:332-351`).
- `/correct`, `/write`, the conversation close and the placement rubric **swallow** `LLMError` into 503s or warnings, so they never reach Sentry.
- `scrub_event` drops the message, so even a captured one arrives as a bare `LLMError`.
- **A spend-limit breach is therefore invisible**, which is what happened.

### 1.8 Settings (#454)

- The web has an app menu only: theme, a reminder on/off switch, add-a-device, sign out. **No route writes a `users` setting.**
- The setters exist with no web caller (#453): `update_morning_time`, `set_paused_until`, `replace_interests`, `update_track_weights`, `update_explanation_language_fallback`, and `approve_access`/`decline_access`/`revoke_access`.

---

## 2. Conflicts: each quoted, each with a question

Each conflict gives my proposal and the question for the operator. Decisions 1–4 are written into the decisions log only on approval.

**C1 — Sunday "keep going" against PRD §4.2 and W11b.**
- §4.2 Sun: *"No tasks. Weekly report. Free extensive input, tracked but never required."* and *"Sunday being empty is deliberate and non-negotiable."*
- W11b: *"a Sunday that acquires a task is a defect."*
- **Proposal:** on Sunday, "keep going" offers only **"Watch something"**, which is §4.2's own *free extensive input*. The existing "Or practise anyway." link stays. Cards, write and talk are not offered on Sunday. §4.2 is unchanged.
- **Q1:** Is Sunday watch-only, or all four options?

**C2 — A choice against PRD §4 / §7.4.**
- §4: *"one button … making the learner decide what to do"* is the biggest failure.
- §7.4: *"Videos are assigned, not browsed … decisions are where sessions die."*
- **Proposal:** the choice appears **only after the session is finished**, so the session itself stays one button. "Watch another" is **assigned by the same selection score, never a library to browse**. No PRD change is needed; it is recorded as a decision.
- **Q2:** Accept?

**C3 — Cadence against PRD §4.2 Mon/Wed/Fri rows, §7 line 350 ("Three curated videos a week (Mon/Wed/Fri)") and §7.4 ("Mon/Wed/Fri the session opens with today's video").**
- Operator decision 2 amends all three sites on approval, with the old text quoted (#82).
- The Tue/Thu "series" rows describe W27, which is unbuilt. I propose they read "video (series when W27 exists)".
- **Q3:** Is a video assigned on **Sunday** too, reachable only through "keep going" / "practise anyway"? I recommend yes: it is the same free input and needs no weekday special case.

**C4 — Design first against CLAUDE.md §1a.**
- §1a: *"Every new surface is designed in Claude Design before it is implemented. The export is committed to `specs/design/`."*
- The keep-going panel and the picture drill are new surfaces.
- **Proposal:** W24e (keep going) and W24f (picture drill) **do not start until an export is committed**. W24a–d do not need one: W24c is a width and type-scale change to an existing shell, and W24d is block 2 on more days.
- **Q4:** Will you design both panels, or rule keep-going an extension of the close block's existing "Talk with the app" row (no new surface)?

**C5 — Desktop against W1b's recorded decision and D12.** W1b says *"Phone-width even on a desktop: both learners use a phone."*
- The premise ("a screen nobody opens") is now false, because the operator uses desktop.
- **Proposal:** a wider single column plus a type scale at ≥1024 px only. No two-column layout, so D12's refusal of `1s` stands.
- **Q5:** Overrule W1b for widths of 1024 px and up?

**C6 — Picture drill against PRD §4.3's canonical 11 item types** (*"no free-form LLM prose questions ever again"*).
- **Proposal:** the drill is a **card-face drill over approved pictures, not an `items` row**. It has no model and no validator path, so §4.3 is unchanged.

**C7 — Slice IDs against `docs/TASKS-v3-web.md` Phase F.** Phase F reads *"**W24** Multi-tenancy · **W25** Payments."* This slice is W24 and the settings slice would be W25.
- **Proposal:** this slice keeps **W24**, settings takes **W25**, and Phase F shifts to W30… with the old text quoted.
- **Q7:** Accept that renumbering, or pick other IDs?

**C8 — "near-due" cards against PRD §5 / FSRS.** Reviewing a card before it is due changes its FSRS stability, which is a scheduler change.
- **Proposal:** offer cards **only when `review_queue` is non-empty now (genuinely due)**. There is no near-due. That matches "never invent a backlog".

**C9 — Wikimedia User-Agent.** `--contact` puts a contact string in every request to Wikidata and Commons.
- **Q9:** What contact string may I send? I will not use your account email unless you say so.

---

## 3. The sub-slices, in order

Migration numbers are taken when the file is written. 034 is expected free today.

### W24a — the bank fix, `--only`, the 2026-09-27 record, and the spend-limit alarm (do first)

**Records (on approval):**
- **Slice/record rows:** 2026-09-27 as evidenced in the operator's paste:
  - first `--apply` stopped on the 400 usage limit, and the limit was then raised;
  - second `--apply` wrote 41 rows (calls: generation 12, naturalness 11, probe 48, target 47);
  - listening C1 6/6 `schema_error item_type_note`;
  - the counts table;
  - the dry re-read (cohorts 10, at most 148, "NO — short listening C1 by 1", not run);
  - the deploy (host `0f1ef32`, prune ids `[141, 205]`, api and bot restarted, `/health` `{"ok":true,"schema_version":33}`, Vercel redeployed).
- **Launch 2's Next-action block** goes from "NOT RUN" to RUN, with old text quoted. The desktop observation is recorded too.
- **Decisions 1–4.**

**Known issues (next free is #458):**
- **#458** — the spend-limit breach is invisible, and the live app shares the key. High severity, W24a.
- **#459** — an empty extra key discards a whole item (`item_type_note: None`, `tiles: []`). Medium, closed by W24a.
- The Phase F ID collision, if C7 is ruled.
- **Video assignment has no scheduler.** Checked against the record at write time; filed if not already filed.

**Code:**
- `packages/core/items/generate.py` `_draft_to_item`:
  - before `parse`, drop keys absent from `MODEL_FOR_TYPE[item_type].model_fields` (aliases included) **whose value is `None`, `""`, `[]` or `{}`**;
  - `logger.info` the key **names only**, and add `dropped_empty_extras` to the journal line when it is non-empty;
  - **a non-empty extra is still refused.**
- `packages/core/items/schema.py`: amend the docstring with the reason. An empty extra carries nothing, so dropping it loses nothing, and the invariant ("never ship without whatever it was for") holds.
- `packages/core/placement/bank.py`: add `--only SECTION:BAND` (repeatable).
  - It filters `p.cohorts` after `plan()`.
  - `dry_print` prints the filtered cohorts and the filtered ceiling. The readiness line still covers the whole bank.
  - It is refused for an unknown section or band, and it prints "nothing short" when the cell is full.
  - It stays dry by default, with the ceiling typed back on `--apply`.
- **Spend-limit alarm** (my proposal for #458; built only if approved):
  - In `llm.py`'s `_anthropic_once`, a 400 whose body names the usage limit raises **`LLMSpendLimit(LLMError)`**, so every existing `except LLMError` still works.
  - Before it raises, it calls `core.monitoring.capture_exception` once, tagged `route=llm:spend_limit`.
  - `scrub_event` keeps the exception type, so Sentry opens it as **its own issue** even on paths that swallow `LLMError`.
  - The operator adds a Sentry alert rule: new issue of type `LLMSpendLimit` → email.
  - Only response classification changes. Request construction is untouched, so CLAUDE.md §3.2's real-call rule does not fire, and a real spend-limit 400 cannot be produced on demand anyway. That is stated in the record.

**Tests** (all demonstrated red first):
- `tests/test_items_generate.py`:
  - `item_type_note: None` on a `listening_gap` draft parses;
  - `tiles: []` on a cloze parses;
  - `tiles: ["a"]` on a cloze and `hint: "x"` are still `schema_error`.
  - The existing `l1_gloss_note` test is kept unchanged.
- `tests/test_placement_bank.py`:
  - `--only listening:C1` prints `cohorts: 1` and a ceiling of 20 (hardcoded, not derived);
  - a bad cell is refused;
  - a full cell prints nothing short.
- `tests/test_llm.py`: at the transport (`anthropic.Anthropic` raising `BadRequestError` with the observed text) → `LLMSpendLimit` plus one capture; a different 400 → plain `LLMError`, no capture.

**Screens:** none. **Migration:** none. **Billed:** 0 by Claude Code.

**Operator — Mac:** `git log --oneline -1`, then push.

**Operator — host, as `bot`:**
- `set +H`, `cd`, `rev-parse`, `scripts/backup.sh`, `git pull`, `rev-parse`, `pip install -e packages/core`, `core.db status` (033, nothing pending).
- `core.placement.bank --only listening:C1` (dry): read the ceiling (≈20).
- `… --only listening:C1 --apply`: **billed ≤ the printed ceiling**; type it back.
- `psql english_bot -c "SELECT section, cefr, count(*) FROM placement_bank GROUP BY 1,2 ORDER BY 1,2;"`.
- `core.placement.bank` (dry): expect *"a first sitting can be offered now: yes"*.

**Operator — host, as root:** restart `english-api`, `english-bot` and `english-worker` (core changed, #433), then `curl …/health`.

**Operator — Sentry:** the alert rule (if the alarm is approved).

Every line is rehearsed on the Mac dev database before it is handed over (§5c).

### W24b — pictures: propose, read, load (no code)

1. **Operator — host, as `bot`, read-only:** the candidate query (rehearsed on dev: it parses and runs, 0 rows).
   - It takes nouns from the learners' non-collocation cards ∪ the real words of the placement vocabulary section, with no picture yet, ordered by `freq_rank`.
   - Written as `psql english_bot -At -c "…" > /tmp/w24b-candidates.txt`. Paste back.
2. **Claude Code — Mac, 0 billed:**
   - From that list I choose **60–100 concrete, picturable lemmas**, and exclude abstract nouns, phrasal verbs and collocations (PRD §2.6.3). The list and its exclusions go in the decisions log as my judgement.
   - I run `python -m core.images.bank --propose --live --lemmas <list> --limit 100 --contact <Q9> --out <scratchpad>` (about 400 requests, about 7 minutes).
   - I deliver `sheet.html` for reading, plus `refused.tsv`.
3. **Operator — Mac:** read the sheet. Append the kept `proposals.tsv` lines to `data/lexeme_images.tsv`; that line is the approval. Commit.
4. **Operator — host, as `bot`:** `git pull`, `core.images.bank --load` (dry, read the add lines), `core.images.bank --load --apply --contact <C>` (re-checks each file on Commons; type the confirmation).
5. **Operator — phone:** a reviewed card of an approved word shows its picture after the reveal, and the credit is visible.

**#451 recommendation: accept the link and do not print the title.**
- CC BY 2.0–3.0 §4(b) permits credit *"in any reasonable manner"* appropriate to the medium.
- Commons' own minimum online credit is author / licence / a link to the file page, and the file page carries the title one tap away.
- A filename-as-title on a small card caption adds noise and no attribution value.
- Reversible with one line in `card-image.tsx` if you rule otherwise.

**Migration:** none. **Screens:** none new; the W13d e2e already covers the picture states.

### W24c — desktop width and type, phone unchanged

**Files:**
- `app/(app)/layout.tsx` and `components/bottom-nav.tsx`: add `lg:max-w-2xl`.
- `app/globals.css`: `@media (min-width:1024px) { html { font-size: 112.5% } }`, so every rem-based size scales.
- `app/(auth)/layout.tsx`: same, for consistency.

**Tests:**
- New `e2e/layout.spec.ts`. **Before** the change, capture `toHaveScreenshot` baselines at `phone-*` and `phone-keyboard-*` for home, `/session` and `/write`, and commit them.
- They must pass unchanged **after** the change: that is the "phone unchanged" assertion the prompt asked for, which does not exist today.
- Plus computed-style asserts:
  - at 390 px: shell `max-width` 512 px and root font 16 px;
  - at 1280 px: 672 px and 18 px.
- Red demonstration: apply the scale without the media query, and the phone baselines fail.
- **The whole e2e suite reruns at desktop** (`/talk` full-height and `/write` `[contain:size]` are the risks).

**Screenshots:** `e2e/screenshots/W24c/` for every state at all six projects. **Migration:** none. **Billed:** 0.

**Operator:** a Vercel rebuild; open `/session` on desktop and phone. Whether it reads well is a human check.

### W24d — a daily video

**Change:**
- `assign.py`: `WEEKDAYS` becomes every day (Sunday per Q3), and there is a per-day entry `--user N --date D`.
- A per-day assign **refuses rather than repeats or goes below band**. No row means block 2 is `empty` with the existing copy.
- A worker job `assign_video` runs nightly per onboarded learner for the local day. It is free (local coverage over stored text) and makes no model call.

**Migration 034 (taken when written):** `video_assignments.kind TEXT NOT NULL DEFAULT 'daily' CHECK (kind IN ('daily','extra'))`. `UNIQUE (user_id, assigned_for)` is replaced by `UNIQUE (user_id, assigned_for, kind)`, so W24e can add one extra video a day. It is keyed on `users(id)` (PRODUCT-PRINCIPLES §2). **Merge risk:** the unmerged `w22-bot-reduction` branch also edits `apps/worker/jobs.py`.

**Numbers owed before cadence is promised (Q-V1, host as `bot`, read-only; rehearsed on dev: parses, 0 rows).** Per learner:
- videos with `transcript_status='ok'`, a transcript present, coverage in [0.93, 0.98] and never assigned;
- plus the purge horizon (the oldest `metadata_refreshed_at`).

**What daily needs:**
- 7 new in-band videos a week per learner, or up to 14 with a daily "watch another".
- The pool is shared and `seen` is per learner, so one in-band clip can serve both learners.
- At the measured $0.58 per refresh invocation, **a weekly refresh costs about $2.50 a month**. Refresh stays an operator-run billed command.
- Tap-to-save on a new video needs `core.video.explain --apply` (billed; it prints its own ceiling) or it keeps answering "No definition for that one yet."

**If Q-V1 shows fewer than 7 a week:** the fallback is **"daily when available"**. A video is assigned on days with an in-band unseen candidate and block 2 is `empty` otherwise, **never a repeat and never below band**. The shortfall is reported, with the number, in the record and in the worker's log line, and the fix is content (more conversational channels, #329/#314), not a wider band (§3 rule 7).

**Tests (red first):**
- a per-day assign on a Tuesday;
- refusing when no candidate exists (no row, no repeat);
- seen videos are never chosen (hardcoded ids);
- migration 034's two-kinds-per-day constraint;
- the worker job over a fixed `now` (§3 rule 6).

**Screens:** block 2 on a Tuesday, Playwright at six projects. **PRD amendments:** C3's three sites.

**Operator steps:**
- **Host as `bot`:** backup, pull, `pip install`, `core.db migrate`, `core.db status` (034), `core.video.refresh --live` (free quota read), then `--apply` if Q-V1 is short (billed, ceiling typed back), and `core.video.assign --user N --date today` (dry, then `--apply`).
- **Host as root:** restart `english-api` and `english-worker`; a `journalctl` read of the `assign_video` line the next morning.
- **Phone:** a Tuesday session shows a video.

### W24e — "keep going" (after C4's design is committed)

**Finished is derived, not stored.** `sessions.today` exposes `finished = every block among review/input/focus/output is done or empty, and at least one is done`, from `block_breakdown`.
- It does **not** write `sessions.completed`. That would change the nudge ladder (#259) and widen scope.
- If `/talk` output does not mark block 4 done, that is reported rather than papered over.

**Route and service.** `GET /keep-going` → `core.services.keep_going.options(user_id, now)`. It is one route and one service function, and it returns only the **kinds** available, never counts:

| Kind | Shown when |
|---|---|
| `watch` | an in-band unseen video exists (W24d); `POST /keep-going/watch` assigns today's `extra` and returns it; it plays on `/watch` with the existing `VideoPlayer` |
| `talk` | the turn cap is not reached; voice per `VOICE_ALLOWED_USER_IDS`, typed otherwise |
| `cards` | `review_queue` is non-empty now (C8) |
| `write` | the write cap is not reached |

Sunday shows the Q1 subset.

**Where it renders:** in `/session`'s done state, replacing the unreachable block, and on the Sunday home below the report.

**Copy:** no count, score or backlog, and no "should" (for example *"If you'd like a bit more:"*). The banned-phrase test and the banned-key scan (`test_no_surface_presents_a_backlog_count`) are extended to it.

**Cost per use:**
- watch 0;
- talk as §1.3 (≈3 + turns LLM, +1 STT per voice turn, under the existing cap);
- cards 0;
- write 1 LLM (under the existing cap).

**Journal:** only talk's typed close and write, both existing and integration-tested. Keep going adds no new journal writer.

**Tests (red first):**
- an ASGI integration test per kind and precondition (cap reached → kind absent; empty queue → no `cards`);
- the Sunday subset;
- no numeric field in the payload.
- **Playwright:** the panel visible, reachable and without overflow, in light/dark at phone/desktop. Screenshots in `e2e/screenshots/W24e/`.

**Operator:** a Vercel rebuild; restart `english-api`; a phone check that finishing a session shows the choices and that each one opens. Whether the choice feels inviting or naggy is a human check.

### W24f — picture drill (OPTION — propose only; built only on your approval and after its design)

**Shape:**
- **"Hear or see the word → pick the picture"**: 4 approved pictures, 1 correct, and the distractors are other approved pictures.
- Optional follow-up: **"picture → type the word"**, graded with the existing `fold`.
- It uses only lemmas with an approved picture that sit in the learner's deck. It is never shown for an abstract word, because only approved lemmas exist and approval excludes them.
- The credit stays under each picture.

**Where:** a `pictures` kind in "keep going", shown only when ≥4 approved pictures intersect the learner's cards. **Not in Review**: writing FSRS grades from a drill would change scheduling.

**Cost and data:** 0 billed, no journal (a tapped choice is a selection and a typed miss is a typo, CLAUDE.md §5), no migration, no write.

**Tests:** grading, the ≥4 precondition, credit presence, and Playwright states.

---

## 4. The web settings screen (#454): scope only

**Size: medium, and no migration expected** (every column and setter exists). It needs:
- one `settings` router (`GET` plus `PATCH`, plain `def`, one service call each);
- a `/settings` page or sheet from the app menu:
  - reminder time (`update_morning_time`; the W20 push already reads it);
  - pause (`set_paused_until`);
  - interests and track weights (`replace_interests`, `update_track_weights`, with Work capped at 20 unless raised);
  - explanation language (`update_explanation_language_fallback`);
- operator actions on `/admin`: approve / decline / revoke (#97), admin-guarded `POST`s over `approve_access`/`decline_access`/`revoke_access`;
- about 25 tests, including ASGI integration per route and Playwright states;
- a Claude Design export (§1a).

(f) is a **ruling, not code**: what drives `users.cefr_level` after the bot?

**Recommendation:** make it its own slice (**W25**, subject to C7) and run it **before W22's deploy**. It can run right after W24a–c if you want the bot retired sooner. W22 is also gated on #423.

---

## 5. What stays open after W24

- #314: the pool still has no unscripted speech.
- Video glosses are unfilled until `core.video.explain` runs.
- #259/#361: `sessions.completed` is still never written.
- #382/#405: the caps are global.
- #253: free input is tracked only through video progress, and only if W24d/e ship.
- #454/W25, #452 (M13 sweep), W22's gate, #449/#450 (per-sense pictures).
- Every earlier unrun check, carried forward in Next action and not dropped.

## 6. Verification, per sub-slice

- `pytest -q` (full) and `pnpm test` (Vitest) green.
- `pnpm test:e2e` for every screen slice, with screenshots committed.
- Each new test shown red before its fix.
- Host blocks rehearsed on the Mac dev database, with output read and not just exit codes.
- `BUILD_PROGRESS.md` updated per §7 at the end of each sub-slice, rows at 🟡.
- One sub-slice per approval; I stop after each.

---

## (3) The approval, with rulings

# W24 — plan approved, with rulings. AGENT mode, in the same session as the plan.

The plan is approved as written, with the rulings below. **Build W24a, W24c, W24d and W24e back to back in this session**, in that order.
- **Each sub-slice gets its own commit and its own `BUILD_PROGRESS.md` update** (row at 🟡, decisions, issues, inventory, Next action).
- **Do not stop between them unless one fails.** Stop after W24e.
- **W24b is operator-driven.** Write its steps into Next action; do not run `--propose` until the operator has pasted the candidate list.
- **W24f is deferred** (see R8).

The standing rules hold: no billed call, no SSH, no production entrypoint; every new test is demonstrated red first; pytest runs serially, with the W10c journals read-only; Vitest, `tsc`, `next build` and `pnpm test:e2e` are run and counted; Playwright screenshots of every asserted state; migration numbers are taken when the file is written; **nothing is marked ✅.**

## Operator rulings, 2026-09-27

Write these into the decisions log as operator rulings. They were recommended by the assistant and accepted by the operator.

- **R1 (Q1): Sunday is watch-only.** On Sunday, "keep going" offers only `watch`, alongside the existing "Or practise anyway." link. PRD §4.2's Sunday is unchanged.
- **R2 (Q2): accepted.** The choice appears only after the session is finished. `watch` is assigned by the selection score and is never a library to browse.
- **R3 (Q3): yes.** A video is also assigned on Sunday. It is reachable only through "keep going" and "practise anyway".
- **R4 (Q4): no Claude Design pass for W24e.** §1a stays suspended for this work, as in build run 1's ruling 0.1. "Keep going" is ruled an **extension of existing surfaces**: the session's done state and the Sunday home. It is built from the shipped conventions (the close block's row style), and Playwright screenshots stand in for the design review.
- **R5 (Q5): overrule W1b at ≥1024 px only**, as proposed. Single column, no two-column layout, and D12 stands.
- **R6 (Q7): accept the renumbering.** This slice is W24, settings is W25, and Phase F shifts, with the old text quoted.
- **R7 (C8): accepted.** Offer `cards` only when `review_queue` is non-empty now. No near-due cards.
- **R8: W24f (picture drill) is deferred.** It is filed as a slice with its plan text quoted. It is reconsidered after pictures are loaded and used for a week.
- **R9 (Q9): the Wikimedia contact string is `https://app.foundgrant.com`.** Never send the operator's email.
- **R10: #451.** Accept the recommendation: credit is author, licence and a link to the Commons file page, with no printed title.
- **R11: the spend-limit alarm (#458) is approved as proposed.** `LLMSpendLimit(LLMError)`; one capture per occurrence, tagged `route=llm:spend_limit`; the Sentry alert rule goes into Next action as an operator step.
- **R12: W25 (settings)** is its own slice, run **after W24 and before W22's deploy**. Do not start it.

## Per sub-slice

- **W24a:** exactly as planned. Also record 2026-09-27 in full, as the plan lists it.
- **W24c:** exactly as planned. **The phone baselines are captured and committed before the CSS change**, in a separate commit, so the "phone unchanged" claim is provable from history.
- **W24d:** as planned, with migration 034. It ships **"daily when available"** regardless of the Q-V1 numbers. Q-V1 goes into Next action as the operator's read. **Never a repeat and never below band.** **Merge risk with `w22-bot-reduction` (`apps/worker/jobs.py`):** after W24d is pushed, rebase the branch onto `main` and resolve the conflict so both job sets survive; run the full suite on the rebased tip; `push --force-with-lease`; re-verify R-A; **do not merge.**
- **W24e:** as planned, with R1, R4 and R7. The finished state is **derived from `block_breakdown`**. Do not write `sessions.completed`. **If `/talk` output does not mark block 4 done, report it and file it. Do not paper over it.**

## At the end (after W24e)

Rewrite `## Next action` as **one launch block for all of W24**, one block per role (#422): 1. Mac; 2. Host, as `bot` (backup, pull, `rev-parse`, `pip install -e packages/core`; `core.db migrate`, then `status` (034 applied); `core.placement.bank --only listening:C1`, the dry run, then `--apply`, typing back the ceiling it prints; the counts query; `core.placement.bank`, the dry run, expecting *"a first sitting can be offered now: yes"*; the **Q-V1** read; the **W24b candidate** query; the video assign or refresh steps, if Q-V1 is short — billed steps state their ceiling); 3. Host, as root (restart `english-api`, `english-bot` and `english-worker`; `/health`, expecting `schema_version` 34; the new routes' `401`s); 4. Sentry (the `LLMSpendLimit` alert rule); 5. Vercel (rebuild); 6. the phone and desktop checks for W24c, W24d and W24e; 7. W24b's steps, in order; 8. every earlier unrun check, carried forward — nothing drops off.

Report at the end: the commit per sub-slice; the suite counts; the rebased W22 branch tip; anything filed. Then stop.
