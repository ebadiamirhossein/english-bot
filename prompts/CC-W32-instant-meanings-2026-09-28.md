# W32 — Instant meaning for every word on /watch (Trancy-style)

Archived by W32a (2026-09-28) under CLAUDE.md's `prompts/` rule: **intent, not state.** Two messages, in the order given: the PLAN prompt, then the approval with the operator's rulings and changes. The approved plan itself lived in the session's plan file; what was built is `BUILD_PROGRESS.md`'s.

---

## Message 1 — the PLAN prompt (2026-09-28)

W32 — Instant meaning for every word on /watch (Trancy-style). PLAN mode. Plan only; no code until approved.
One Claude Code session on this repo at a time (#417). This work goes on `main`.
Read these first:

* `PRODUCT-PRINCIPLES.md` and `BUILD_PROGRESS.md` (the W31 and W31e records);
* `packages/core/video/explain.py` and `packages/core/services/words.py`;
* `packages/core/services/glosses.py`;
* `apps/web/components/video/word-sheet.tsx` and `player.tsx`;
* `data/lexemes.tsv`;
* #292, #473, #478.

Slice id: take the next free id, expected W32. Confirm it is free. If not, say so and take the next.
Standing rules:

* no billed call, no SSH, no production entrypoint;
* every new test is demonstrated red first;
* pytest runs serially, with the W10c journals read-only;
* Vitest, `tsc`, `next build` and e2e are run and counted (`E2E_PORT=3190`);
* Playwright screenshots of every asserted state, at phone and desktop width, in light and dark;
* migration numbers are taken when the file is written;
* nothing is marked ✅.

1. The operator's finding (2026-09-27, ~23:35 Vilnius, user 3, desktop)
On `/watch`, tapping "moving" or "over" shows "No meaning for this one yet — you can still save it."

* Only the ~17 below-floor words per video have a meaning (`video_glosses`).
* Every other word has none.
* A live `explain` call takes 4.4–8.0 s (host log: `duration_ms` 2662–7991).

The operator's requirement, verbatim in substance:

* like Trancy, hovering (desktop) or tapping (phone) any word shows its meaning in under 1 second;
* the learner then chooses whether to save it.

Evidence, W31e deploy (operator's paste, 20:34 UTC):

* `4aee6f1` was pulled.
* Backup `english_bot_2026-09-27_2034.dump`, 1,995,891 bytes, R2 SUCCESS.
* `explain --video 44` re-run: `below_floor=2 planned=2 already_held=15`, `wrote 2 gloss(es)`, output tokens 451 and 457, `stop_reason=end_turn`. The 3,000 budget fixed `shed` and `dinosaur`.
* All three services were restarted.
* Record this in W32's first `BUILD_PROGRESS.md` update. #473 stays open until the operator gives his Farsi read.

2. The design to plan (recommended; challenge it if the code says otherwise)
Under 1 s cannot come from a model call. It has to come from data that already exists when the page loads.
A. A global word dictionary

* A new table (expected 036), global, with no `user_id`, keyed by lemma, for the reason `videos` and `lexeme_images` are global.
* Each entry holds:
   * the lemma;
   * part(s) of speech;
   * 1–3 short English senses, B1-friendly;
   * register;
   * short `fa` and `lt` translations, for the learners' languages;
   * `model`, `generated_at`, `source`.

B. Fill it ahead of time, in batches (billed, operator-run first)

* A human-run CLI, `python -m core.video.dictionary`, dry by default, with `--apply` and a printed ceiling. It covers:
   * (1) every lemma in `data/lexemes.tsv`;
   * (2) every lemma in every `ok` pool video's transcript.
* Many words per call (e.g. 40–60), each word validated on its own. A bad entry is dropped, never repaired. Fix #478's repair call in this path, or route around it, and show it red.
* Measure before you estimate: count the distinct lemmas (1) + (2) on the Mac from the repo, and give the host a read-only query for (2).
* Then give the cost table for:
   * the one-time backfill;
   * the per-new-video top-up;
   * a comparison of Sonnet 5 vs Haiku 4.5 and the Message Batches API (50% cheaper, asynchronous) for the backfill.
* Recommend one, with the reason. The `fa`/`lt` quality is the deciding factor.
* The ongoing top-up is a worker job behind a flag (`WORD_DICTIONARY_JOB=1`, off by default), with a daily ceiling. It fills lemmas of newly pooled or assigned videos before anyone watches them.
* The model call lives inside the #292 allow-list. Either it goes in `explain.py`, or the new file is added to the set in the same diff, with the reason at the entry.

C. Zero-wait on the page

* When `/watch` loads, one request returns the meaning map for every lemma in that video's lines: dictionary entry plus `video_glosses` context meaning, where one exists. Hover and tap are then client-side, with no network request.
* State the payload size for video 25 (1,171 lines).
* Desktop: hovering a word for about 250 ms shows a small popover with the word, the first sense and the L1. Clicking opens the existing sheet with Save.
* Phone: tapping opens the sheet immediately with the meaning.
* Context beats dictionary: where `video_glosses` has a meaning for this word in this video, show it first, labelled "here", with the dictionary senses under it.
* The ~250 ms hover delay stops the popover flickering while the mouse passes over words. It must not fight W31b's hover-pause on the current line.

D. Save is instant too

* Saving a word that has a dictionary entry writes the cards immediately, using the context sentence and the dictionary sense, with no pending state.
* Pending (W31c) remains only for a word with no entry at all.
* Keep the register rules (receptive-only for informal/slang/taboo) and `lexeme_id` on capture (#469).

E. A miss (a word with no entry)

* Operator ruling, 2026-09-27: for a miss only, the app may call the model while the learner waits.
* The sheet shows "Looking it up…" and fills in. The result is stored in the dictionary, so every later hover is instant.
* Rate-limited per user and counted against a daily ceiling.
* Record this as a scoped exception to the 2026-08-27 standing ruling ("the app never generates while a learner waits"). It is not a repeal, and it applies to dictionary misses only.

F. Subtitles inside the video: fullscreen and landscape (operator request, 2026-09-27)
Most learners watch full screen or with the phone turned sideways. Today (W31b), Focus mode puts our line under the video, and in landscape there is little room for it.
Required:

* In Focus mode, our subtitle line is drawn ON the video, over its bottom area, like YouTube captions.
   * It is an absolutely positioned layer over the iframe, inside the same wrapper that goes fullscreen.
   * The words stay hoverable and tappable, with the popover and sheet working inside fullscreen.
   * Clicks outside the words still reach the video.
   * Readable on bright video: a semi-transparent backing, as YouTube uses.
   * The previous line is optional and dimmed. State your choice.
* Turning a phone to landscape on `/watch` enters Focus automatically. Turning back exits it.
   * This covers iPhone Safari, iPhone PWA and Android.
   * Say per platform what happens, extending W31b's table.
* YouTube's own fullscreen stays disabled (`fs: 0`), because it would hide our layer.
* YouTube's own captions (CC) stay off by default, so two subtitle tracks never show at once.
* e2e:
   * Focus mode at desktop size and phone-landscape size;
   * the line is visible inside the video's box;
   * a word in the overlay opens the popover or sheet;
   * screenshots in light and dark.

G. Where the dictionary comes from: compare before building
The operator asks whether an existing dictionary can be used instead of the model. Compare briefly:

* A: an open dictionary: WordNet (English only), Wiktionary (CC BY-SA, with share-alike obligations on derived data in a commercial product), or FreeDict (for fa/lt coverage);
* B: model-written once, and stored.

Judge them on:

* licence for a commercial product (PRODUCT-PRINCIPLES §3, clauses quoted verbatim);
* B1-friendly English;
* `fa`/`lt` coverage and quality;
* cost;
* effort.

Recommend one. Either way, the model is never called per hover. It is used only to fill words missing at the start of a video (§2B top-up) or on a rare miss (§2E).
3. The plan must answer

1. The measured distinct-lemma counts and the cost table (§2B), with a recommendation.
2. The migration, its rollback, and why the table is global.
3. How a dictionary entry becomes a card, per register, with the tests.
4. The payload shape and size, and the no-network-on-hover assertion (e2e: hover with network blocked still shows the meaning).
5. How the popover and hover-pause interact, and phone behaviour.
6. #478: fix or route around it in the batch path, shown red.
7. The merge risk with `w22-bot-reduction` (`apps/worker/jobs.py`).
8. Numbered questions for the operator, each with your recommendation. Keep them few.

Pre-ruled (do not ask again):

* CLAUDE.md §1a is suspended for this surface, as in W31 (Q4), with screenshots as the review.
* `VIDEO_PREGEN_GLOSSES` stays off.
* W25 follows this slice.

4. After approval (not now)
Build back to back, one commit per sub-slice, each with its `BUILD_PROGRESS.md` update:

* the row at 🟡;
* decisions with their reasons;
* issues with severity and slice;
* the inventory;
* Next action one block per role (#422), carrying every earlier unrun check.

The Next action must include:

* the host's backfill dry run;
* the backfill `--apply`, with the printed ceiling, operator-run;
* the operator reading a sample of 30 `fa` entries;
* only then `WORD_DICTIONARY_JOB=1`.

Then: rebase `w22-bot-reduction` onto `main`, run the full suite on the tip, `push --force-with-lease`, re-verify R-A, and do not merge.

---

## Message 2 — the approval, with rulings and changes (2026-09-28)

# W32 — plan approved, with rulings and changes. AGENT mode, in the same session as the plan.

The plan is approved as written, with the rulings and changes below.
- **Build W32a → W32b → W32c → W32d back to back in this session.**
- **Each sub-slice gets one commit and its own `BUILD_PROGRESS.md` update:**
  - the row at 🟡;
  - decisions with their reasons;
  - issues with severity and slice;
  - the inventory;
  - Next action, one block per role (#422), carrying every earlier unrun check.
- **Do not stop between sub-slices unless one fails.** Stop after W32d and the W22 rebase.

The standing rules hold:
- no billed call, no SSH, no production entrypoint;
- every new test is demonstrated red first;
- pytest runs serially, with the W10c journals read-only;
- Vitest, `tsc`, `next build` and `E2E_PORT=3190 pnpm test:e2e` are run and counted;
- screenshots of every asserted state, at phone and desktop width, in light and dark;
- migration numbers are taken when the file is written;
- **nothing is marked ✅.**

## Operator rulings, 2026-09-28

Record these in the decisions log as operator rulings. They were recommended by the plan or by the assistant and accepted by the operator.

- **Q1: accepted.** A 60-word pilot on Sonnet 5 and Haiku 4.5. The operator reads `fa`/`lt`, chooses the model, and then runs a synchronous backfill with the winner. Batches are filed, not built.
- **Q2: accepted.**
  - The manifest stays `portrait`.
  - On Android, the Focus button locks landscape after native fullscreen, and unlocks on exit.
  - Rotation auto-Focus works in browser tabs and on iPhone.
- **Q3: yes.** Apply the one-parse, no-repair fix to `explain_one` in W32a, red first, and close #478.
- **Q4: accepted.** `WORD_DICTIONARY_JOB`, and retroactively `WORD_GLOSS_JOB`, are recorded as flagged, ceilinged, operator-switched exceptions to the "never while nobody is watching" half of the 2026-08-27 ruling, in the same entry as §E's miss exception. **#196's line is amended in place, with the old text quoted.**

## Changes (numbered)

**C1. Narrow the backfill. Do not buy all 15,300 lexemes.**
- The backfill scope becomes the union of:
  - **(a) every lemma in the `ok` pool videos' lines**, keyed through `gloss_key`;
  - **(b) the most frequent 5,000 lexemes that carry a POS tag**, by the frequency rank the table already holds. State which column that is.
- The 4,564 untagged rows (names and abbreviations) are **excluded** from (b). They are still reachable through (a), or through a miss.
- The dry run prints:
  - (a), (b) and their union;
  - the typical/ceiling cost for the union;
  - the count excluded as untagged.
- The rest of the list is filled only through top-up or a miss.
- **Expected result:** roughly half the ≈ $51. Report the real number from the dry run, not this estimate.
- A `--scope all` flag may exist for later. It is **not** the default.

**C2. One sense by default.**
- The prompt asks for **one** sense, and a second or third only when the word has more than one sense common at B1–B2 (*over*, *run*, *miss*).
- The validator still accepts 1–3 senses.
- Re-derive the per-call word count and `max_tokens` from this, and update the cost table. Keep the non-streaming ceiling reasoning.

**C3. The long backfill must survive a dropped SSH session and the API's own limits.**
- The Next action runs the backfill under `nohup … > "$RUNTIME_DIR/dictionary-backfill.log" 2>&1 &`, with the exact line written out. It gives:
  - a `tail -f` command to watch it;
  - a `pgrep` line to confirm it is running;
  - a count query to see progress.
- **A 429 or overloaded (529) response backs off and retries.** It is **never** counted as a refusal, and never drops words silently.
  - Say whether `chat()` already does this. If it doesn't, handle it in the CLI loop, not in `llm.py`.
  - Test it with a mocked 429, red first.
- The end line prints: written, refused (with reasons counted), skipped, and total output tokens.

**C4. Check the Anthropic spend limit before the backfill.**
- The Next action puts **one operator step before `--apply`**: open the Anthropic Console, compare this month's usage and limit against the dry run's printed ceiling, and raise the limit if needed.
- Reason: the spend limit stopped the app once already, and #458's alarm exists because of it.
- The CLI's dry-run line ends with that ceiling in dollars, so the comparison is direct.

**C5. The sample reads use the operator's languages.**
- The 30-entry read query returns `lemma`, sense 1's English, and **`fa`**. The operator reads Farsi himself.
- Also give a separate 20-entry `lt` query, marked for Morkyte to read. That read is **not** a gate for switching on `WORD_DICTIONARY_JOB`. File the Lithuanian read as a check carried until done.

**C6. Record the plan's unexplained 15,000 vs 15,300 difference** as a low issue if it survives the build-time check. Do not let it change the backfill scope silently.

## Everything else stands
- Migration 036, global, with its rollback.
- All model calls in `explain.py`; the allow-list is unchanged.
- The dictionary → card branch through `capture_from_gloss`, with register rules unchanged.
- `/meanings`, with self-gzip and the shared key contract file.
- The network-blocked hover and tap proof.
- The popover's 250 ms delay plus the skip delay, never touching playback.
- The miss path, with its per-user and global ceilings and its request-path pin.
- `fill_word_dictionary` behind its flag.
- The Focus overlay inside the video box, with no previous line.
- Landscape auto-Focus.
- The `jobs.py` layout for the W22 merge.
- `TOUCHES_HEARTBEAT` filed, not decided.

## At the end

W32d's Next action is **one launch block**, one block per role, in this order:
1. **Mac:** push, and state the expected `rev-parse`.
2. **Host, as `bot`:** backup, pull, `pip install -e packages/core`, migrate (036), status.
3. **Host, as root:** restart all three services; `/health` reports `schema_version` 36.
4. **Vercel:** rebuild.
5. **Host, as `bot`:** the read-only lemma query (§1.1), then the pilot for Sonnet 5, then the pilot for Haiku 4.5, each with its printed ceiling.
6. **The operator** reads both pilot reports and chooses the model.
7. **C4:** the spend-limit check.
8. **Host, as `bot`:** the backfill dry run, then the backfill `--apply` under `nohup` (C3), then the progress checks.
9. **The operator** reads the 30 `fa` entries (C5). `lt` is queued for Morkyte.
10. **Host, as `bot`:** `--payload 25`.
11. **Host, as `bot`:** `WORD_DICTIONARY_JOB=1` via the idempotent append; then **as root**, restart `english-worker` and check the `Scheduler built jobs=` line.
12. **The phone and desktop checks:**
    - hover and tap on any word in under a second;
    - a miss;
    - Save, instant;
    - Focus with subtitles on the video;
    - rotation on iPhone and Android;
    - the Android Focus landscape lock.
13. **Every earlier unrun check, carried forward.** That includes W13d-P1, W18-R2 → W18-P1, the Apify charge after Monday's refresh, #457, #473's Farsi read, W25 next, and W22's gates.

Then rebase `w22-bot-reduction` onto `main`:
- run the full suite on the tip;
- `push --force-with-lease`;
- re-verify R-A;
- **do not merge.**

Report:
- the commit per sub-slice;
- the suite counts;
- the migration number;
- the dry-run scope numbers from C1, if the Mac can compute (b);
- the rebased W22 tip;
- anything filed.

Then stop.
