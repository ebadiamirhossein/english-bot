# CC — W24 follow-up, 2026-09-27

The prompt this session was given, archived verbatim as intent (CLAUDE.md: `prompts/` documents intent, never build status — `BUILD_PROGRESS.md` is the record).

---

W24 follow-up: record the W24 launch, #462, drop C1 listening, the video pool, pictures. AGENT mode.
One Claude Code session on this repo at a time (#417). This work goes on `main`.
Standing rules:

* no billed call, no SSH, no production entrypoint;
* every new test demonstrated red;
* pytest serial with the W10c journals read-only; Vitest, `tsc`, `next build` and e2e counted (use `E2E_PORT=3190`);
* Playwright screenshots of every asserted state;
* migration numbers taken when the file is written;
* nothing marked ✅.

Commit each part separately, with its own `BUILD_PROGRESS.md` update. Then rebase `w22-bot-reduction` onto the new `main`, run the full suite on the tip, `push --force-with-lease`, re-verify R-A, and do not merge.

A. Record the W24 launch (2026-09-27): evidenced on the operator's paste

Host deploy

* The first `rev-parse` printed `0f1ef32`.
* Backup: `english_bot_2026-09-27_1024.dump`, 673,217 bytes, uploaded to R2.
* Pull reached `eed40b3`.
* `Applying migration 034 (034_video_assignment_kind.sql)`. Status: `Applied: 001 … 034`, `Pending: (none)`.

Listening C1 fill

* `--only listening:C1` dry run: `cohorts: 1`, `at most: 20`.
* `--apply`: `calls spent: {'generation': 1}`, `generated rows written: 0`.
* All 6 slots were discarded with `['answer_not_in_transcript', 'stem_transcript_mismatch']`.
* The journal shows the cause: the explanations say the transcript renders the reduced form ("'might have' often sounds like 'mighta'", "'Could have' is often pronounced 'coulda'"), while `answer` is `might have` / `could have`. The target "hearing could have or might have in fast speech" invites phonetic spellings that no transcript check can match.
* The counts are unchanged from before, and listening C1 is still 0.

Video pool (Q-V1)

* The first read: 12 `ok` videos, all refreshed 2026-09-01.
* Dry assign for user 3: `Candidates: 12 selectable: 3`.
* `core.video.refresh --live` listed 180 videos; the projected floor was `$0.0009`.
* `@ModernFamily` returned 404 on playlistItems.
* `--live --apply`:
   * wrote 180 pool rows;
   * 40 candidates (caption kinds: 6 manual, 32 generated, 2 unknown);
   * 2 `unavailable` (`hvESODUTFeE`, `sZUprwBnpiw`);
   * 38 transcripts stored; coverage recomputed as 50 × 3;
   * Purge: 0;
   * Pool: 185 videos (`ok 50`, `pending 133`, `failed 0`, `unavailable 2`);
   * 3 coverage rows computed with the proper-noun rule OFF.
* Dry assign after the refresh:
   * user 3: `Candidates: 50 selectable: 8`;
   * user 2: `selectable: 11`;
   * both excluded 38 of 50 as outside the 93–98% band (the tool's own "FINDING" banner);
   * both would get `kZhTprPs7PA` today.
* Learners (`approved_onboarded_users`): 1 Navid, 2 Morkyte, 3 Amirhossein, all Europe/Vilnius.

Restart

* `english-api`, `english-bot` and `english-worker` restarted.
* The worker logged `Monitoring on component=worker region=eu` and `Scheduler built jobs=push_poll,assign_video`.
* `/health` returned `{"ok":true,"schema_version":34}`.
* Vercel was redeployed, on the operator's report.

Sentry

* The issues feed shows only ENGLISH-WEB-1 and ENGLISH-API-1 (the two probes).
* The `LLMSpendLimit` alert rule is not yet created. Keep #458 open until it is.

W24b candidate list

* The picture candidate query returned ~140 nouns. Nearly all are `in_placement=t`, `in_cards=f`; only `notch` and `psychosis` came from the learners' cards.
* Finding: pictures on card faces will rarely show, because the learners' cards hold almost no concrete nouns. That is why W24f (the picture drill) would be the surface that actually shows them.

B. #462: a conversation counts as block 4 (operator ruling, 2026-09-27)

A day on which the learner sent at least 3 learner turns on `/talk` (typed or voice) counts as block 4 done for that day, exactly as a writing submission does.

* Derive it from the existing evidence (`conversation_usage.turns_learner` for the local date, or the equivalent the tree uses). Do not add a journal write.
* Tests, red first:
   * 2 turns: not done;
   * 3 turns: done;
   * `finished` becomes true;
   * keep-going appears;
   * Sunday is unaffected.
* Screenshots only if a screen changes. Close #462.

C. Drop listening C1 from the placement check (operator ruling)

* Remove the C1 listening target and cohort from the bank plan.
* Listening's highest band is B2. The readiness minimum for listening C1 goes away.
* Scoring already caps listening at the highest band served. State that it now reports at most B2, and assert it.
* Tests, red first:
   * the bank's dry run on today's counts prints "a first sitting can be offered now: yes" (reproduce the host counts in a fixture);
   * no C1 listening cohort is planned.
* Record the reason: the phonetic-spelling finding in A.
* Operator step: after the deploy, the host's `core.placement.bank` dry run reads yes. W18-R2 and then W18-P1 are unchanged, and still nobody sits the placement check before W18-R2.

D. The video pool

1. `@ModernFamily`: confirm the handle is gone or changed. Remove it or correct it in `data/video_channels.json`, with the evidence.
2. A weekly automatic refresh. This is an operator request; the operator wants no manual weekly step.
   * Add a worker job `refresh_videos`: weekly, Monday about 04:00 Europe/Vilnius.
   * It calls the same code as `core.video.refresh --live --apply`, with a hard ceiling of 40 transcripts per run and the same purge.
   * It is off unless `VIDEO_AUTO_REFRESH=1` is set in `.env`.
   * It logs a one-line summary (ok / pending / unavailable counts; no titles) and captures failures to Sentry.
   * This is a billed call made by the system on a schedule. It needs the operator's explicit ruling, which is given here: cost measured at under $1 per run.
   * Record the ruling as an exception to #196's "billed runs are operator-run", scoped to this job only.
   * Tests: the job is registered only when the flag is set; the ceiling is enforced; it runs over a fixed `now`.
3. File the band finding (38 of 50 outside 93–98%) under #289/#329, with the numbers. Do not change the band.

E. W24b: propose the pictures (Mac, 0 billed)

Choose 60–100 concrete, picturable nouns from this list, which is the operator's candidate paste. No abstract nouns, no people-as-roles where the picture would be generic, and nothing a learner could misread.

```
man friend throw report burn till class pain area enemy flower difference engine dig chase energy interview coach commander princess century customer lab sugar winner traffic row cab flag sheet outfit navy passport jungle beef actress compromise trunk motor steak weed relief encounter cheek soda medal cinema rib celebrity strain economy acid rhythm clerk circuit democracy sympathy platform bicycle fork hike shrimp publicity fountain flu bartender fabric balcony swan gown runner wheelchair globe tutor interior caption racket sparkle parrot spaceship battlefield mustache wheat prospect masterpiece lemonade batch relay comparison cafeteria keyboard distribution convenience researcher cone frustration mist belongings seminar tendency notch defender withdrawal bravery cocoa listener wildlife mango canteen superstition examiner shortage chemist cucumber heater enquiry refund distinction bookstore handshake interruption implication goodwill workplace similarity attendance interpreter mortar publication partisan drugstore concession carton teamwork psychosis
```

Then run:

```
python -m core.images.bank --propose --live --lemmas <chosen> --limit 100 --contact "https://app.foundgrant.com" --out <scratch>
```

Report:

* the absolute path of `sheet.html` for the operator to open;
* `refused.tsv`'s count;
* your chosen list and the excluded list, in the decisions log.

Do not write to `data/lexeme_images.tsv`. Approval is the operator's.

F. Next action

Rewrite `## Next action`, one block per role (#422):

1. Mac: push; state the expected `rev-parse`.
2. Host, as `bot`:
   * backup, pull, `pip install -e packages/core`, `migrate`, `status`;
   * add `VIDEO_AUTO_REFRESH=1` to `.env`;
   * the bank dry run, expecting yes.
3. Host, as root: restart all three services; check that `Scheduler built jobs=push_poll,assign_video,refresh_videos`; `/health`.
4. Sentry: the `LLMSpendLimit` alert (carried).
5. Vercel: rebuild, only if `apps/web` changed.
6. The picture approval:
   * the operator opens `sheet.html`;
   * appends the approved lines to `data/lexeme_images.tsv`, commits and pushes;
   * on the host, as `bot`: `git pull`, then `core.images.bank --load` (dry run), then `--load --apply --contact "https://app.foundgrant.com"`.
7. W18-R2, then W18-P1.
8. Every earlier unrun check, carried.

Report the commits, the suite counts, the W22 branch tip and the `sheet.html` path. Then stop.
