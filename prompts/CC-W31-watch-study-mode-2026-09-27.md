# CC — W31 (asked as "W26"), watch study mode, save any word, word practice, 2026-09-27

The prompts this session was given, archived verbatim as intent (CLAUDE.md: `prompts/` documents intent, never build status — `BUILD_PROGRESS.md` is the record). Three parts, in the order received: the planning prompt, the operator's server evidence pasted beneath it, and the approval with rulings. **The slice was asked for as W26; W26–W30 are reserved in `docs/TASKS-v3-web.md` Phase F, so it is W31 (ruling Q1).**

---

## 1. The planning prompt

W26 — Watch study mode, save any word, word practice. PLAN mode. Plan only; write no code until approved.
One Claude Code session on this repo at a time (#417). This work goes on `main`.
Read these first:

* `PRODUCT-PRINCIPLES.md` and `BUILD_PROGRESS.md`;
* `docs/TASKS-v3-web.md`, and PRD §7.3 and §7.5;
* the W13-i / W13-ii / W13a / W13d / W24d records;
* #396, #397 and the W24f filing.

Slice id: take the next free id after W25 and confirm it isn't already used. If W26 is taken, say so and use the next one.
Operator ruling, 2026-09-27: this slice runs before W25. W22 stays on its branch and its gates are unchanged.
Standing rules:

* no billed call, no SSH, no production entrypoint;
* every new test is demonstrated red first;
* pytest runs serially, with the W10c journals read-only;
* Vitest, `tsc`, `next build` and e2e are run and counted (use `E2E_PORT=3190`);
* Playwright screenshots of every asserted state, at phone width and desktop;
* migration numbers are taken when the file is written;
* nothing is marked ✅.

1. What the operator found using the app (2026-09-27, ~19:40 Vilnius, user 3, desktop Chrome). Evidence: the operator's screenshots.

1. `/watch` is not usable for learning:
   * the transcript is one wall of text under the player;
   * it is not synced to playback, so nothing shows which line is being spoken;
   * in YouTube fullscreen the transcript disappears completely;
   * the display shows raw `>>` speaker markers, `[laughter]` tags and ALL-CAPS runs.
2. Tapping a highlighted word (`mastodon`, `epoch`, `nickname`…) shows "Could not add that just now." That is not #178's `no_gloss` copy ("No definition for that one yet."), so it is a failure path. Find the cause. Do not assume it is the empty `video_glosses` table.
3. Sentry `ENGLISH-WEB-2`: `TypeError`, unhandled, `(No error message)`, user `id:3`, `/_next/static/chunks/883-…js`. The frame is the `setInterval(() => { … e.getCurrentTime() … }, 250)` in the player's `useEffect`. It is probably a call on a player that isn't ready or has been destroyed. Find it, fix it, and assert it.
4. A word that isn't highlighted, or that has no gloss, cannot be saved at all. The learner has no way to keep a word they didn't know.
5. "I didn't find vocabulary flashcards."
   * The `Review` tab exists, but it holds only due cards, and the learners' cards contain almost no concrete nouns (W24b finding).
   * The 18 pictures loaded today (`data/lexeme_images.tsv`, 18 rows written on production) therefore reach nobody.
   * W24f (the picture drill) is un-deferred by this ruling.

The reference the operator named is Trancy / Language Reactor on YouTube:

* hovering the subtitle pauses the video;
* any word can be clicked, looked up and saved;
* the subtitle stays visible while watching.

PRD §7.3 already says "this is a build-your-own Language Reactor, in-app". This slice closes that gap.
2. What to build (sub-slices, in this order, one commit each)
W26a — Fix the two failures (small, first)

* The "Could not add" path:
   * reproduce it against the dev database;
   * state the actual response (status and body);
   * fix the cause, and make every non-`saved` outcome show its own honest copy.
* The `ENGLISH-WEB-2` TypeError:
   * guard on player readiness;
   * clear the interval on unmount and on video change;
   * add no swallow-everything `try/catch`.
* Tests, red first, for both.
* Close or file the issues.

W26b — Study mode on `/watch`

1. Synced lines.
   * Show the current subtitle line large, directly under the player, with previous and next lines dimmed.
   * Below that, the full transcript as a list of lines (not a paragraph): the active line is highlighted and auto-scrolls; tapping a line seeks to it.
   * This answers #397 (timed paragraph vs lines): lines. Record it as the operator's ruling.
   * Generated caption tracks overlap (R12: ~92% of consecutive pairs overlap). Plan how clean, non-duplicated lines are derived from `transcript_cues`. Show the measured result on three real assigned videos, and state what happens for a video with no cues.
2. No lost subtitles.
   * Disable YouTube's own fullscreen (`fs=0`).
   * Provide an in-app Focus mode: the player plus the subtitle line filling the viewport. Use the Fullscreen API on our wrapper where supported, and a fixed full-viewport layout where it isn't (iPhone Safari).
   * State per platform what the learner gets.
3. Pause to read.
   * Desktop: hovering the subtitle line pauses; leaving resumes, unless a word sheet is open.
   * Phone: tapping a word pauses.
   * Loop-line and 0.75× stay.
4. Clean display, stored text unchanged.
   * Strip `>>` from the display.
   * Render sound tags (`[laughter]`) dimmed and not tappable.
   * Show ALL-CAPS runs as sentence case for display only.
   * The stored transcript, coverage and the purge are untouched.

W26c — Tap and save any word

1. Tapping any word opens a sheet containing:
   * the word as spoken, plus its lemma;
   * the sentence;
   * the meaning (English, plus the learner's L1 from `users.native_language`) when a gloss exists;
   * Save.
2. With a gloss: today's W13-ii path. Two cards, the register-dependent pair, and the exact sentence plus timestamp.
3. Without a gloss: the word is saved as pending. The standing ruling holds: the app never generates while a learner waits.
   * A worker job fills the meaning after the tap. The card enters the deck only once it has a meaning; a gloss-less row in `cards` is refused, for the reason recorded at W13-ii/2.
   * The sheet says so plainly (e.g. "Saved. The meaning will be ready soon.").
   * Plan:
      * where pending saves live (a user-keyed table referencing `users(id)` is expected — justify it or refute it);
      * the job;
      * its ceiling per run;
      * the flag that gates it (`WORD_GLOSS_JOB=1`, off by default, same shape as `VIDEO_AUTO_REFRESH`).
4. Pre-generation for the assigned video.
   * Plan an option where `assign_video` (or a follow-on job) runs `core.video.explain` for today's assigned video only, so most taps already have a gloss.
   * Estimate the per-video and per-week cost from token counts; make no billed call.
   * This is billed and scheduled, so it needs an explicit operator ruling at plan review, as `refresh_videos` did. Present it as a choice with numbers.
5. "My words". Somewhere reachable (inside `Review` is expected), a list of saved words, with pending ones marked.
   * No count, no backlog framing (CLAUDE.md §4, #160).

W26d — Word practice (W24f, un-deferred)

1. A short drill of about 5 minutes, drawn from the learner's own cards, due first:
   * picture → choose the word;
   * word → choose the picture;
   * hear it → type it;
   * meaning → type the word.
   * Picture exercises appear only for lemmas in `lexeme_images`. Everything else uses the text and audio forms, and no card loses its sentence context (PRD §2.6.3).
2. Grading goes through the existing FSRS path and `equivalence_key`. No second scheduler.
3. It is offered by "keep going" and reachable from `Review`.
4. The finding to resolve in the plan, not to paper over: the 18 pictured words are almost never in any learner's deck.
   * Propose options, e.g. a one-tap "add to my words" on picture words shown in the drill, or choosing future picture candidates from the learners' saved words.
   * The operator rules.

3. The plan must answer

* The migration(s), if any, their numbers taken when written, and the rollback.
* The cost table for W26c's job and option (4), with the gating flags.
* The per-platform Focus-mode behaviour.
* The cue-to-line method, with the measured result on three real videos.
* Which existing tests and issues are touched (#178, #292's allow-list — any new model caller amends it in the diff, with the reason at it — #356, #396, #397, #160, #170).
* The merge risk with `w22-bot-reduction` (`apps/worker/jobs.py`).
* Questions for the operator, numbered, each with your recommendation.

4. After approval (not now)
Build W26a → W26d back to back, one commit and one `BUILD_PROGRESS.md` update each.

* Each update includes:
   * the row at 🟡;
   * decisions with their reasons;
   * issues with severity and slice;
   * the file inventory;
   * Next action rewritten one block per role (#422), with every earlier unrun check carried.
* Then rebase `w22-bot-reduction` onto `main`: run the full suite on the tip, `push --force-with-lease`, re-verify R-A, and do not merge.

Also record, in W26a's `BUILD_PROGRESS.md` update:

* W24b's load on 2026-09-27, evidenced on the operator's paste:
   * `ae14357` was pulled on the host;
   * the dry run printed `add: 18 replace: 0 unchanged: 0 withdraw: 0`;
   * `--apply` printed `done: 18 written, 0 refused, 36 requests`;
   * skipped: keyboard, cheek, parrot, cafeteria, carton, drugstore and lemonade.
* The operator findings in §1 of this prompt.

Operator's server evidence (pasted below this line by the operator):

## 2. The operator's server evidence

journalctl save-word grep (since 19:00 server time): no lines
video_glosses count: 0

Server clock is UTC (19:38 Vilnius = 16:38 UTC).
journalctl -u english-api --since "-1h":
- 16 × "POST /video/44/save-word HTTP/1.1" 422 Unprocessable Entity, 16:38:38–16:39:31 UTC, from the operator's taps.
- No save-word request returned 200. POST /video/44/progress returned 200 throughout.
- The first grep "since 19:00" was empty only because the clock is UTC.
video_glosses: count = 0 on production.
So the "Could not add" copy is a 422 request-shape mismatch between apps/web and the API, before any gloss lookup. W26a must find the field mismatch, add a contract test covering the web request and the API model, and demonstrate it red.

## 3. The approval, with rulings

# W31 — plan approved, with rulings. AGENT mode, in the same session as the plan.

The plan is approved as written, with the rulings and changes below.
- **Build W31a → W31b → W31c → W31d back to back in this session**, in that order.
- **Each sub-slice gets its own commit and its own `BUILD_PROGRESS.md` update:**
  - the row at 🟡;
  - decisions with their reasons;
  - issues with severity and slice;
  - the file inventory;
  - Next action rewritten one block per role (#422), with every earlier unrun check carried.
- **Do not stop between sub-slices unless one fails.** Stop after W31d.

The standing rules hold:
- no billed call, no SSH, no production entrypoint;
- every new test is demonstrated red first;
- pytest runs serially, with the W10c journals read-only;
- Vitest, `tsc`, `next build` and `E2E_PORT=3190 pnpm test:e2e` are run and counted;
- Playwright screenshots of every asserted state, at phone and desktop width, in light and dark;
- migration numbers are taken when the file is written;
- **nothing is marked ✅.**

## Operator rulings, 2026-09-27

Record these in the decisions log as operator rulings. They were recommended by the plan or by the assistant and accepted by the operator.

- **Q1: W31**, with sub-slices W31a–d. W26–W30 stay reserved as the plan found them.
- **Q2: do not block on the three-video measurement.**
  - Build W31b with the plan's thresholds.
  - Ship `python -m core.video.lines --report --video N`, and put the three-video report in Next action as a host step.
  - **W31b stays 🟡 and is not reported done until the operator's report has been read.** If the report shows the thresholds are wrong, the tuning is a follow-up commit, not a redesign.
- **Q3: yes.** Build loop-line in W31b on the derived lines. 0.75× stays whole-player.
- **Q4: CLAUDE.md §1a is suspended for W31**, as R4 did for W24.
  - The reference is Trancy / Language Reactor, named by the operator.
  - The phone and desktop screenshots of every state are the design review.
- **Q5: option (b).** `VIDEO_PREGEN_GLOSSES` covers today's daily video only, at most 20 lemmas per learner. It is **built off by default**. It is switched on only after the operator has read the first manual `explain --apply`.
- **Q6: accepted**, with change C2 below: every 15 min, 20 per run, 3 attempts before "no meaning found".
- **Q7: yes.** Farsi and Lithuanian go in the same `explain` call, shown in the sheet only. Card backs stay English. The first `--apply` output is read by a person before either flag is turned on.
- **Q8: accepted.**
  - Due cards are graded through FSRS (Good / Again).
  - Not-due top-up is practice only, with no FSRS write.
- **Q9: (C) + (B).** (A) is not built.

## Changes to the plan (numbered)

**C1. Sentence-casing must not lowercase names.**
- *"HEY, PETER! IT'S ME, ROSS"* must render as *"Hey, Peter! It's me, Ross"*, not *"Hey, peter! It's me, ross"*.
- **The rule:**
  - lowercase the run;
  - capitalise sentence starts and *I*;
  - **restore the original capitalisation of any word that appears capitalised in mixed-case text elsewhere in the same transcript** (a per-video proper-noun set);
  - leave a lone acronym (*TV*) untouched.
- **A pytest case with Friends-shaped text, red first.** Display only, as planned.

**C2. The two gloss jobs get separate daily ceilings, so pre-generation can never starve a learner's own taps.**
- `WORD_GLOSS_JOB`: **60 per UTC day**.
- `VIDEO_PREGEN_GLOSSES`: **40 per UTC day**.
- Both are counted from `video_glosses.generated_at` by a source marker, and both are enforced with `min()` inside the function.
- If distinguishing the source needs a column, it goes in migration 035 and is stated.
- Update the cost table:
  - worst case ≈ **$1.0/day with both on**;
  - typical is still under $1/week at real use.

**C3. Pricing honesty.**
- The cost table states which model `explain` actually calls, read from the code.
- It marks the per-token price as **"list price, not re-verified in this session"**, unless it is read from a file in the repo that states it.
- Keep the numbers as estimates. Do not present them as measured.

**C4. Pending words must not wait silently forever while the flags are off.**
- With `WORD_GLOSS_JOB` off, "My words" shows the pending marker. That is fine.
- **Next action must make the order explicit:**
  1. deploy;
  2. the first manual `explain --apply` on one video, read by a person;
  3. only then `WORD_GLOSS_JOB=1`;
  4. then `VIDEO_PREGEN_GLOSSES=1`.
- Each step states its ceiling and its exact command. No placeholders: use the real video id from a query the operator runs first, and say so.

**C5. Hover-pause scope.**
- On desktop, hovering pauses only when the pointer enters the **current-line block under the player**. Scrolling or hovering the full line list below does not pause.
- Assert it in Playwright.

**C6. Record W24f's un-deferral in the decisions log.** R8 (W24, 2026-09-27) deferred W24f "until pictures are loaded and used for a week".
- It is un-deferred on the operator's finding the same day: no vocabulary practice was findable, and the 18 pictures reach nobody.
- **W31d is where it lands.** Quote R8's text; do not delete it.

## Everything else in the plan stands
- W31a's contract fixture and the red demonstration.
- The honest copy per outcome.
- The `onReady` lifecycle and its three fake-timer tests.
- `lines.py`, with its no-cue fallback.
- `fs: 0`, `playsinline: 1` and the Focus mode table.
- `word_saves_pending` and why it is a new table.
- The F5 lemma lookup and F6 `lexeme_id` on capture, with the collision → `already_saved`.
- My words, with no count.
- The drill, with context on every exercise.
- The #292 allow-list unchanged.
- The `jobs.py` layout for the W22 merge.
- #396 / #397 closed on the operator's ruling.
- #178 closed as stale.

## At the end (after W31d)

Rewrite `## Next action` as **one launch block for all of W31**, one block per role (#422):
1. **Mac:** push, and state the expected `rev-parse`.
2. **Host, as `bot`:**
   - backup, pull, `rev-parse`;
   - `pip install -e packages/core`;
   - `core.db migrate`, then `status` (035 applied);
   - the three-video `lines --report` (the Q2 check);
   - the query that names one assigned video for the first `explain` run;
   - `explain` dry run, then `--apply` on that one video, stating its ceiling;
   - **stop: the operator reads the glosses (English + L1) before any flag.**
3. **Host, as `bot` (after the read):** add `WORD_GLOSS_JOB=1` to `.env`. Then, separately and later, `VIDEO_PREGEN_GLOSSES=1`.
4. **Host, as root:**
   - restart `english-api`, `english-bot` (core changed, #433) and `english-worker`;
   - check that the `Scheduler built jobs=` line lists the flagged jobs only when their flags are set;
   - `/health` returns `schema_version` 35.
5. **Vercel:** rebuild (`apps/web` changed).
6. **Sentry:** resolve `ENGLISH-WEB-2` and watch for recurrence.
7. **Operator phone and desktop checks:**
   - a word tap saves (no 422);
   - the line syncs and highlights;
   - Focus mode on the iPhone;
   - hover-pause on desktop;
   - the word sheet with its L1 and picture;
   - My words;
   - the drill, all four exercise types.
8. **Every earlier unrun check, carried forward.** Nothing drops off. That includes W13d-P1, W18-R2 → W18-P1, the Apify charge after Monday's refresh, #457, W25 and W22's gates.

Then rebase `w22-bot-reduction` onto `main`:
- resolve `jobs_for` so both job sets survive;
- run the full suite on the tip;
- `push --force-with-lease`;
- re-verify R-A;
- **do not merge.**

Report at the end:
- the commit per sub-slice;
- the suite counts;
- the migration number taken;
- the rebased W22 branch tip;
- anything filed.

Then stop.
