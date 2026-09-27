# W31e — first live gloss run: fix the token budget and skip names; record the run. AGENT mode.

One Claude Code session on this repo at a time (#417). This work goes on `main`, one commit.

**Standing rules:**
- no billed call, no SSH, no production entrypoint;
- every new test is demonstrated red first;
- pytest runs serially, with the W10c journals read-only;
- Vitest, `tsc` and `next build` are run and counted only if `apps/web` changes;
- **nothing is marked ✅.**

## Evidence (operator's paste, host, 2026-09-27 ~19:24 UTC)

**W31 deploy:**
- `b1df2ee` on the host.
- Backup `english_bot_2026-09-27_1921.dump`, 1,988,066 bytes, R2 SUCCESS.
- `Applying migration 035` / `Applied: 001 … 035` / `Pending: (none)`.
- `Scheduler built jobs=push_poll,assign_video,refresh_videos`.
- `/health` → `{"ok":true,"schema_version":35}`.

**Q2, the three-video `lines --report`.** It was read by the operator, so W31b's gate is met.

| Video | Track | Cues | Overlapping pairs | Lines | Words/line p50 / p90 / max | Seconds/line p50 / p90 / max |
|---|---|---|---|---|---|---|
| 44 | generated | 121 | 104 | 89 | 7 / 12 / 16 | 3.0 / 5.9 / **8.7** |
| 25 | generated | 1528 | 1405 | 1171 | 7 / 12 / 16 | 2.6 / 5.2 / **29.5** |
| 26 | generated | 715 | 655 | 552 | 7 / 12 / 16 | 2.5 / 5.0 / **26.9** |

The samples read correctly: `>>` is gone and `[laughter]` stands on its own line. Some lines still break mid-phrase ("Right down here we have / a large foot.").

**The first `core.video.explain --video 44 --user 3 --limit 20 --apply`:**
- The dry run printed `below_floor=17 planned=17 … l1=fa,lt calls_at_most=17`.
- `wrote 15 gloss(es)`.
- **2 refused, both at `max_tokens=400`:**
  - `shed`: `blocks=['ThinkingBlock']`, `chars=0`. The log says "the whole budget was spent on thinking … raise the caller's max_tokens above core.items.gates.THINKING_HEADROOM_TOKENS".
  - `dinosaur`: `blocks=['ThinkingBlock','TextBlock']`, `chars=259`, and the JSON was cut off inside the `fa` string.
- Per call: `model=claude-sonnet-5`, input 626–642 tokens, output 129–287 tokens on success.
- **`phillips` was planned and glossed.** It is the name in "Thank you, Dr. Phillips.".
- **Stored rows read by the operator.** `mastodon` has `fa` and `lt` present. The `lt` line has a grammar slip: *"su ilgais iltimis"* (`iltis` is feminine; it should be *"su ilgomis iltimis"*).

## Build

1. **Token budget (#473's first live finding).**
   - `explain`'s `max_tokens` must leave room for adaptive thinking **plus** the longest valid reply, which now includes two L1 strings.
   - Derive the value from `THINKING_HEADROOM_TOKENS` plus a reply budget, as the other callers of that constant do. Do not hardcode a new magic number.
   - **Do not change `llm.py`'s request construction.** If it must change, CLAUDE.md §3.2's real-call rule applies. Say so and stop, rather than doing it.
   - **Tests, red first:**
     - the budget is ≥ headroom + reply budget;
     - a stubbed Thinking-only response and a stubbed truncated-JSON response are each refused **without** being stored, as today;
     - a full response inside the new budget is stored.
   - Update the cost table with the measured token counts above. State the new ceiling per call.

2. **No glosses for names.**
   - `explain.plan_for` and `WORD_GLOSS_JOB` must skip a word that is capitalised mid-sentence elsewhere in the same transcript. **Reuse W31b's per-video proper-noun set** (C1), not a second rule.
   - A tap on such a word still opens the sheet. Saving it follows today's path; the job must not spend a call on it.
   - **Red first:** "Dr. Phillips" is not planned; "museum" still is.

3. **Record the three-video report.**
   - Mark W31b's Q2 check read, with the table above.
   - **File (low):** a derived line can exceed the 6 s cap (29.5 s on video 25, 26.9 s on video 26). Find the cause from `lines.py` and state it. Fix it only if it is a one-line rule; otherwise file it with the cause.

4. **Record the first live `explain` run as above.**
   - The 2 refusals.
   - `phillips`.
   - The Lithuanian agreement slip, as a quality note under #473 (low): a person reads L1 output, and the slip shows why.
   - **The operator's Farsi read:** leave it as "on the operator's report" until he states it.

5. **Next action, one block per role (#422):**
   - **Mac:** push.
   - **Host, as `bot`:**
     - backup, pull, `pip install -e packages/core`;
     - re-run `explain --video 44 --user 3 --limit 20 --apply`. It skips what it already holds, so expect at most 2 calls (`shed`, `dinosaur`).
   - **Host, as root:** restart `english-api`, `english-bot` and `english-worker`.
   - **`WORD_GLOSS_JOB`:** if the operator has already turned it on, record the worker's `Scheduler built jobs=` line. Otherwise leave its step as written.
   - **Carry every earlier unrun check.**

Report the commit, the suite counts and anything filed. Then stop.

---

**Operator, with the prompt:** *WORD_GLOSS_JOB=1 is on. Worker at 19:33:28 UTC: Scheduler built jobs=push_poll,assign_video,refresh_videos,fill_word_glosses.*
