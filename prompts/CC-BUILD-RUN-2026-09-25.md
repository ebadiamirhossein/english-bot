# BUILD RUN — the remaining slices, back to back. AGENT mode.

*Archived by the first session of the run (W17, 2026-09-25) per CLAUDE.md: `prompts/` records intent, never state. The run's state is `BUILD_PROGRESS.md`'s `## Build run — queue`. The same prompt is pasted into a fresh session for each slice; it is archived once.*

Paste this same prompt into a fresh Claude Code session each time. Each run does the next unfinished slice in the queue (§3), commits it, updates the record, and stops. The queue's state lives in `BUILD_PROGRESS.md` under `## Build run — queue`, so a new session knows where to resume without being told.

One session at a time on this repository (#417). If another Claude Code session is open on this tree, stop and say so.

## 0. Operator rulings for this run (2026-09-25), recorded before anything else

Write these into the decisions log in the first run, then build to them. Rulings 1–3 are the operator's. The rest are assistant-recommended and operator-accepted. The operator's instruction was to go fast and build on the recommendations.

1. **Speed ruling (operator's).** Human checks are batched into one launch pass at the end of the run. Until then, Playwright and agent review carry the checks. No human check is dropped. Each one goes into `## Launch pass — human checks` (§6), named, with the slice that owes it.
2. **Nothing built in this run is deployed until the launch pass (operator's).** Every slice is committed and pushed to `main`, and none is deployed to the host. The reason: W15 and W17 write to the error journal, and a wrong row is permanent damage. The first learner to see this work sees it after the human pass. There is one deploy block, at the end of the run.
3. **§1a design-first is suspended for this run (operator's, reversible).** New screens take the conventions shipped in `/talk` and `/write`: the mono eyebrow; the bordered pill; serif for the app's voice and sans for the learner's; the three-dot working indicator; the composer as a block; the `--caution` tokens; `h-full` inside `main.flex.min-h-0`; `contain: size` on any full-height route (W16a's measured fix). In exchange, every Playwright spec takes a screenshot of every state it asserts, in both themes and at phone and desktop width, into `apps/web/e2e/screenshots/<slice>/`. That folder is how the operator reviews the screens at the launch pass. Commit the screenshots.
4. **W21 is struck** from `docs/TASKS-v3-web.md`, with the old row quoted (#82's shape): it duplicates W1c, which shipped and was verified on 2026-08-24. #404 closes.
5. **Billed calls are batched.** A slice whose request construction is new (CLAUDE.md §3 rule 2) builds a probe that is dry by default, prints exactly what `--live` would send, and adds its commands to `## Launch pass — probes` (§6). Build against the documented response shape. The operator runs every probe in one sitting before the deploy, and a shape mismatch found then is a fix, not a rebuild. Record this risk in each slice's row. No billed call is made by Claude Code at any time.

## 1. Every slice, every time — the procedure

1. Read first: `CLAUDE.md`, `docs/PRODUCT-PRINCIPLES.md`, `BUILD_PROGRESS.md` (the queue section, the slice's row, the known issues it inherits), `docs/TASKS-v3-web.md` (the slice's row and the authoritative migration table), and the PRD sections the row cites.
2. Reconcile against the tree before building. Report every disagreement between this prompt, the record and the tree in the slice's decisions entry. The tree wins over this prompt.
3. Use subagents for independent reads and independent test files. Never let two agents write the same file.
4. Build: business logic goes in `packages/core`. Routes are plain `def` with one service call. `apps/web` calls go through typed `lib/api.ts` functions — never a bare `fetch` (#398).
5. Migrations: re-read `migrations/` and take the next free number when the file is written (#185). Shift every unwritten row below it in both halves of TASKS in the same commit. Apply it to the Mac dev database only.
6. Tests. Every new test is demonstrated red, with the red method in its docstring. Python: request construction is mocked at the provider SDK, never at the service function (TASKS standing rule 7). A deck, journal or route write goes through the ASGI transport against the real dev database. Vitest: rendered from Python-generated fixtures compared against a real ASGI body (#190). Playwright: CLAUDE.md §3a's five assertions on every drawn state, all six projects, plus the screenshots (ruling 3).
7. Run the full suites and report their counts: pytest (serial, with the W10c journal read-only for the run, #416/#420), Vitest, `tsc --noEmit`, `next build` with `NEXT_PUBLIC_API_URL` set, and `pnpm test:e2e`. End at zero failures.
8. The bot path stays byte-identical unless the slice is W22. Prove it with `git diff --name-only` over `apps/bot` and the v2 correction files, and paste the result.
9. Record. Update `BUILD_PROGRESS.md`: the slice row at 🟡, never ✅; decisions, each with its reason; new issues, each with a severity and a slice target — never prose; the file inventory; the queue section, with this slice marked built, not deployed; its human checks appended to the launch pass (§6); its probes appended.
10. Commit and push (`git add -A`, then a message naming the slice), then stop. Print which slice is next and tell the operator to paste this prompt again in a new session.

The hard rules still apply in full: the error journal is the product — only genuine, self-produced errors are written; no production entrypoint and no billed call; no SSH; no text or audio is stored, and logs carry user ids, never bodies; nothing new is built for Telegram; no count, score or backlog reaches a learner (CLAUDE.md §4).

## 2. First run only — before the queue

- Write rulings 0.1–0.5 into the decisions log.
- Strike W21 (ruling 4) and close #404.
- Create `## Build run — queue`, `## Launch pass — human checks` and `## Launch pass — probes` in `BUILD_PROGRESS.md`.
- Move every unrun human check already in Next action into the launch pass list. Nothing is dropped. That includes W16a's HW-L, HW2–HW5 and HW7–HW9, and W16b's HP1–HP3 and HP5.
- File #422 — a host paste ran its second half as root. On the 2026-09-25 deploy, the Part B block was pasted as one block. After `exit`, the remaining lines ran again as root: `git pull` refused on dubious ownership, which was harmless; `scripts/backup.sh` ran a second time as root and wrote a root-owned dump, `english_bot_2026-09-25_0906.dump`, 594,609 bytes, over the bot's. The family is #215/#151. The fix is that every host block in this record separates the `bot` half and the root half into two pasteable blocks, with the switch between them stated. `medium`, target: the launch-pass deploy block.
- Record W16's deploy on 2026-09-25, from the operator's paste: backup 590,235 bytes to R2; pull `62ccb3e..b7b2d53`; `Applying migration 027` → `Applied: 001 … 027`, `Pending: (none)`; `schema_version` 27; the sixteen labels as returned (HW-L done); `user_unit_state` holds one row — user 3, unit 1, `in_progress`; `english-api` restarted; `/write/today` returned 401. The Vercel rebuild and `pnpm test:e2e` are the operator's and are not evidenced yet.
- Record, as a launch-readiness finding with a target: only one learner has a `user_unit_state` row. The second learner has never started the web session. W22 cannot run while that is true.

Then start the queue.

## 3. The queue — in this order

### 3.1 W17 — weak spots from the error journal
The spec is the TASKS row, as re-scoped by W14r. Build to its rulings, plus these:
- A pattern is drillable only with evidence: at least 3 journal rows of one `error_type` for this learner, inside the retention window. A pattern with no evidence is never drilled and never reported as mastered. Silence is not mastery (#412: the journal undersamples by design).
- Drills are generated items and go through the existing item gates (`core.items.gates`, `probe_target` and the rest). Generation is human-run and dry by default (#196). Add its command to the probes list.
- The surface serves drills inside the daily session, never as a separate queue and never with a count (#160). The plan names which block and why. Each drill carries the pattern's plain label (`error_types.learner_label`) and never a tally of how often the learner got it wrong.
- Fix #421 here: G2 tokenises before it straightens curly apostrophes. Its pinned test was written to fail once the fix lands.
- The two learners receive different drills for their different journals. Assert this in a route test with two seeded learners.

### 3.2 W15 — retell and answer
The spec is the TASKS row as corrected by W14r: two rungs on top of W13b's turn loop; Converse is struck.
- Answer: the unit's `output_task_spoken` string, verbatim, tied to the week's can-do.
- Retell: a retelling of that day's video, scored on content coverage against the transcript.
- Voice goes through `speech.transcribe` (OpenAI), gated by `VOICE_ALLOWED_USER_IDS`, which still holds only the operator (#364). Everyone gets a typed path.
- Corrections go to the journal with `source='answer'` and `source='retell'`, which the CHECK already admits. G1 and G2 apply.
- No turn counter, no score on the screen. A coverage result is shown as what was covered, never as a percentage.
- New request construction: build the probe and add it to the probes list.
- #387 (`stt_seconds` 0.0) — fix it here if the retell path measures duration; otherwise carry it.
- #408 and #409 — `/talk` keyboard and save-word. Fix them here, because this slice owns the surface.

### 3.3 W19 — progress + gamification
The spec is the TASKS row, with these rulings:
- Every number traces to a real ledger. The known-words counter uses `evidenced_known_count`, which excludes assumptions. The 6-month line is drawn from that same count's history, or it is reported unmet if no history exists. It is never fabricated.
- The radar needs placement (W18). Report it unmet, and do not approximate it.
- The couple leaderboard is dropped and reported unmet. A ranking between the two learners is a score on one of them. CLAUDE.md §4 and the guilt ban outrank the TASKS row. Record this as a scope ruling.
- XP is by effort weight. A spoken sentence earns more than a tapped MCQ, as the row's acceptance requires. XP never goes down on screen.
- The streak shows freezes. A broken streak is silent: no "you lost your streak".
- The guilt-ban scan is extended to all frontend copy.
- Fix #259 and #349 here if the progress screen reads `sessions.completed`, `minutes` or `completed_at`: they have no writer. Otherwise record that it does not read them and why.

### 3.4 W13c — per-user known-word floor
The spec is the TASKS row. The initial-floor question is ruled here as options (c) and (d) together:
- Store the floor as a number per user (default 2000). Compute the covered set at read time from `freq_rank <= floor`.
- Stop materialising `source='assumption'` rows for new users.
- Existing assumption rows are kept, not deleted. Reads switch to the computed set only after a before/after coverage table for every figure the record carries shows parity, or explains the difference.
- No learner-visible count moves down. Check it against the guilt ban.
- The correction path: an operator CLI, dry by default, now. The learner path arrives with W18.

This unblocks #304 and #159's third consumer. Record both.

### 3.5 W20 — notifications
Web Push (VAPID) only. The Telegram fallback is refused under PRODUCT-PRINCIPLES §1. Quote the row and strike the fallback.
- The combined ceiling is 3 per day. The 4th message of a day is never sent.
- The nudge ladder is ported with #259's defect fixed or explicitly carried. A learner who practised today is never nudged to practise today.
- Scheduling is the hard part: nothing scheduled runs on production (#69 — `english-worker` is not installed because of the job-table overlap). Start this slice by reconciling #69. If the overlap can be resolved inside this slice, install the worker unit as a launch-pass deploy step. If it cannot, stop and report, with the two options costed: resolve #69, or a `bot` crontab entry invoking a dry-by-default CLI. Do not pick silently.
- VAPID keys are generated by the operator at the launch pass. Add the command to the deploy block. The key is never committed.

### After W20 — the queue is finished
Write the launch pass (§5) and stop.

## 4. Not in this run — each needs something only the operator can give
Record each in the queue section as blocked, with exactly what unblocks it:
- W18 placement: a calibrated item bank — 60 vocabulary, 25 grammar, 6 listening, 1 speaking — authored or sourced, with its licence checked for commercial use (PRODUCT-PRINCIPLES §3). The operator provides the bank or rules that it is generated.
- W13d image cards: the licence gate, which can refuse the slice.
- W22 bot reduction: it deletes the Telegram teaching handlers and cannot be undone. It needs both learners using the web session first (§2's finding), and the operator's explicit go.
- W23 observability: Sentry and PostHog accounts and keys, plus the data-processing question those services raise (#364's family).

## 5. The end of the run — the launch pass
When W20 is built, write `## Launch pass` at the head of Next action, in this order:
1. **Probes.** Every probe from the run, as one block of Mac commands, with the exact billed call count. They run before anything is deployed. A shape mismatch is fixed and re-probed before the deploy.
2. **The deploy block.** One block per role, never mixed (#422): Mac: `git status`, then `git log`. Host, `bot`: `rev-parse`, backup, pull (it must end on the named hash), pip, migrate, status, and the read-only `psql` checks for every new table. Host, root: restart `english-api` only; `sleep 5`; one `curl` 401 per new route. Mac: `pnpm test:e2e`, then the Vercel rebuild. Rehearse every rehearsable line (§5c) and name the ones that could not be rehearsed.
3. **The screenshot review:** the path to every `e2e/screenshots/<slice>/` folder, and what to look at in each.
4. **The human checks, grouped by sitting:** one phone sitting: everything that needs a device; one reading sitting: everything that needs judgement about content — drills, corrections, structure prose, the labels; one `psql` sitting: every independent count. None dropped. Each is named with its slice and the issue it closes.
5. **What stays open after launch:** the blocked slices (§4) and every open `high` issue.

Do not mark anything ✅. That column is the operator's.
