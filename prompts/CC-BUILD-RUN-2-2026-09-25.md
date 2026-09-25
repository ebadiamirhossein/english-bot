BUILD RUN 2 — the last four slices, back to back. AGENT mode.
Paste this same prompt into a fresh Claude Code session each time. Each run builds the next unfinished slice in the queue (§3), commits it, updates the record and stops. The queue lives in `BUILD_PROGRESS.md` under `## Build run 2 — queue`, so a new session knows where to resume.
One Claude Code session at a time on this repository (#417).
Build run 1's rules carry over unchanged. They are recorded in the decisions log, 2026-09-25, rulings 0.1–0.5:

* Human checks are batched into one launch pass at the end, and none is dropped.
* Nothing is deployed until the launch pass.
* §1a design-first stays suspended. Reuse the shipped conventions, and Playwright takes a screenshot of every state it asserts.
* Billed calls go into the probes list, and Claude Code makes none.

Build run 1's per-slice procedure (its §1) applies to every slice, including:

* reconcile against the tree first;
* every new test demonstrated red;
* pytest serial, with the W10c journals read-only;
* Vitest, `tsc`, `next build` and `pnpm test:e2e`, all run and counted, ending at zero failures;
* the bot path byte-identical, except in W22;
* the record updated, then commit, push and stop.

0. Operator rulings for this run (2026-09-25)
Write these into the decisions log in the first run. All are assistant-recommended and operator-accepted. The operator's instruction was to finish the remaining slices fast, using the recommendations.

1. W18's bank is GENERATED, not sourced.
   * The generator is our own existing item pipeline, `core.items.generate` plus every gate. Our own generated content raises no third-party licence question.
   * The TASKS row says "calibrated", and that is REPORTED UNMET rather than claimed. Calibration needs real learners' results. The bank is labelled `uncalibrated` in the data and in the record.
   * A placement result seeds `users.known_word_floor`, and W13c made that a number that can be corrected. So a wrong placement is recoverable through `core.lexicon.floor`.
2. W23 is Sentry only.
   * EU data region.
   * `send_default_pii=False`, and a `before_send` hook that removes request bodies, message text and any learner text. It keeps the user id and the stack trace only.
   * Disabled when the DSN is unset, and the DSN is unset until the operator adds it at the launch pass.
   * PostHog is dropped and reported unmet. Product analytics on two learners adds a data processor and buys nothing.
   * Record the processor question as #364's family: Sentry receives stack traces and user ids, never content. A line in `data/LICENCES.md` or its equivalent names Sentry and what it receives.
3. W13d runs its licence gate FIRST, and the gate can refuse the slice. Clauses are quoted verbatim, and the answer must hold for a commercial product. If no image source passes, stop, report the refusal as the finding, commit the record, and do not build (#224's lesson).
4. W22 is built and committed but NOT deployed.
   * It deletes the Telegram teaching handlers, which cannot be undone on the host.
   * The deploy waits on #423 (the second learner on the web session) and the operator's explicit go, written into the launch pass as a gate.
   * `git` keeps every deleted file, so the build is reversible; only the deploy is not.
5. Two small fixes, folded into the first slice that runs:
   * #440: tighten `DRILL_TARGETS["article_missing"]` so the a/an choice is excluded, with a test demonstrated red.
   * #441: the reminder switch's off state in dark mode must reach at least 3:1 contrast against its track, with a Playwright contrast assertion demonstrated red.
6. Close #422, citing the evidence recorded in `ca836be`.

1. First run only

* Write rulings 0.1–0.6.
* Create `## Build run 2 — queue`.
* Close #422.
* Keep appending to the existing `## Launch pass — human checks` and `## Launch pass — probes` sections, so the launch pass stays one list.

2. What does not change

* The error journal is the product. Only genuine, self-produced errors are written to it.
* No production entrypoint, and no billed call by Claude Code.
* No SSH.
* No text or audio is stored, and logs carry ids, never bodies.
* No count, score or backlog is shown to a learner.
* Take migration numbers when the file is written.
   * W18 holds 032 in the authoritative table. Verify it by reading `migrations/`.
   * Any other slice needing DDL takes the next free number, and shifts W18 in both halves of TASKS if it lands first.

3. The queue — in this order
3.1 W18 — placement test
The spec is the TASKS row, plus ruling 0.1.

* The bank: 60 yes/no vocabulary items, 25 adaptive grammar items, 6 listening items and 1 speaking item. Each carries a CEFR tag and an error taxonomy tag.
   * Grammar and listening items are generated through the existing gates: `probe_target`, uniqueness and naturalness, and for listening, the `synthesize → transcribe` round-trip.
   * Vocabulary items are drawn from `lexemes` by `freq_rank` and CEFR tag. No generation is needed for them.
   * The yes/no vocabulary format includes pseudo-words, which is the standard control against guessing. They are generated as pronounceable non-words and checked absent from `lexemes`.
   * The speaking item goes through the existing STT path. It is gated by `VOICE_ALLOWED_USER_IDS` (#364), and has a typed fallback.
* Bank generation is human-run and dry by default (#196). Its command goes into the probes list with its billed-call count.
* The adaptive ladder:
   * start at B1;
   * step up after 2 consecutive correct answers, and down after 2 wrong;
   * stop when the band is stable.
* The result:
   * CEFR, a vocabulary-size estimate, and the per-skill radar that W19 reported unmet;
   * it writes `users.known_word_floor` through the same service W13c's CLI uses, never directly.
   * A placement is never shown as a score on the learner. It is shown as where to start, with the band and no percentage.
* Monthly re-run with non-overlapping subsets. Two sittings draw disjoint items, asserted.
* W19's radar and placement history turn on here. Close their "reported unmet" lines in W19's row, with the old text quoted.

3.2 W23 — observability (Sentry only)
The spec is the TASKS row, narrowed by ruling 0.2.

* `sentry-sdk` for `apps/api` and `apps/worker`, and `@sentry/nextjs` for `apps/web`. Both go through one config seam each.
   * The licence gate runs first and is quoted into `data/LICENCES.md`. `sentry-sdk` is MIT; verify it rather than assume it.
* The acceptance test: an intentional exception reaches the Sentry transport with a user id and no message body. Assert this against a captured event with the transport mocked. No real DSN is used in tests.
* `/admin` is ported as the row says: activity, never content.
* #65 closes when the DSN is set (the operator alert channel). #438's heartbeat is wired to Sentry's cron monitor if it is simple; otherwise it is carried with a reason.

3.3 W13d — image cards for concrete vocabulary
The spec is PRD §2.6.3 and the TASKS row, plus ruling 0.3.

* The licence gate first. For each candidate source, quote the clauses into `data/LICENCES.md` and answer one question: commercial use, allowed, and under what attribution? A scrape is not a source. Candidates include Openverse/Wikimedia (per-image licences), Pixabay and Unsplash — the terms are read, not recalled.
* If it passes:
   * images are global, not keyed to a user (019's reasoning);
   * they apply only to picturable, concrete lexemes;
   * the image adds a face to the existing card and replaces nothing;
   * attribution is stored and rendered wherever the licence requires it.
* If it refuses: stop, record the refusal with the quoted clauses, commit, and move the queue on.

3.4 W22 — bot reduction (built, NOT deployed)
The spec is the TASKS row, plus ruling 0.4.

* Strip the v2 bot to notifications and the couple challenge. Delete the teaching handlers and their dispatch tests.
* The inheritance W22 owns:
   * move the four jobs the bot runs into the worker (#69's remainder);
   * the heartbeat (#438);
   * the ceiling residual, which closes by construction (#436);
   * `texts.py`'s frozen banned-phrase baseline, which shrinks to what remains.
* "Nothing in the web app regresses": the full suites stay green.
* The deploy block for W22 is written separately in the launch pass, headed GATED: #423 and the operator's explicit go. It is not merged into the main deploy block.

After W22 — the queue is finished
Update `## Launch pass` at the head of Next action, replacing it rather than appending a second one. It covers:

* this run's probes (the W18 bank generation), with exact billed-call counts;
* one deploy block per role (#422), carrying migrations from 032 on;
* the Sentry DSN step, with the DSN pasted into `.env`, never committed;
* the Vercel rebuild;
* the screenshot folders;
* the human checks grouped by sitting;
* W22's gated block, kept separate;
* what stays open.

Do not mark anything ✅.
