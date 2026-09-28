W32e — /watch fixes from the operator's first real use, and record the W32 launch. AGENT mode.
One Claude Code session on this repo at a time (#417). This work goes on `main`, one commit, with its `BUILD_PROGRESS.md` update.
Standing rules:

* no billed call, no SSH, no production entrypoint;
* every new test is demonstrated red first;
* pytest runs serially, with the W10c journals read-only;
* Vitest, `tsc`, `next build` and `E2E_PORT=3190 pnpm test:e2e` are run and counted;
* screenshots of every asserted state, at phone, phone-landscape and desktop, in light and dark;
* nothing is marked ✅.

A. Record the W32 launch (2026-09-28): evidenced on the operator's paste
Deploy

* `f8ce946` on the host.
* Backup `english_bot_2026-09-28_0855.dump`, 2,216,379 bytes, R2 SUCCESS.
* `Applying migration 036`, `Applied: 001 … 036`, `Pending: (none)`.
* `/health` → `{"ok":true,"schema_version":36}`.

The lemma scope

* The dry run printed: `scope=c1 (a) pool_videos=85 pool_words=6725 (b) tagged_lexemes=4986 top=5000 union=8055 already_held=3 to_buy=8052 excluded_untagged=4566 excluded_not_a_token=14`, with `typical_usd~16.62 ceiling_usd=62.93`.

Pilot skipped (operator ruling, 2026-09-28)

* The pilot was replaced by a 40-word `--apply --limit 40` test on Sonnet 5: 2 calls, 40 written, 0 refused, 12,903 output tokens.
* The operator read 10 `fa` entries (`accomplish` … `accept`) and approved the Farsi. Model: Sonnet 5.
* The measured cost per word was ~$0.0032, above the plan's typical estimate. Record the gap.

The Anthropic API key was rotated by the operator before the backfill.

* The new key is in `.env` and all services were restarted.
* The old key was deleted. Record that this happened, never the key.

Backfill, under `nohup`

* The run ended with: `done planned=8012 written=8007 already_held=0 refused=5 (no entry=2, no-guilt=1, senses=2) deferred=0 calls=401 input_tokens=314136 output_tokens=2426518`.
* Cost ≈ $24.9 (input × $2 + output × $10 per MTok). The estimate was $16.54 typical and $62.62 ceiling. Record both.

`WORD_DICTIONARY_JOB=1`

* Set via the idempotent append.
* The worker's line at 11:51:30 UTC read `Scheduler built jobs=push_poll,assign_video,refresh_videos,fill_word_glosses,fill_word_dictionary`.

The operator's use, desktop and iPhone, 14:55 local

* The hover popover is instant (`intriguing` → sense plus `fa`).
* The sheet shows two senses with `fa`, and Save works.
* The iPhone portrait sheet is correct.
* #473: the operator has now read `fa` output from both paths and accepts it. Close it with that evidence, or narrow it to the `lt` read (queued for Morkyte), whichever the row's text supports.

B. Four fixes (the operator's findings)
B1. The Focus button is not recognised as fullscreen

* The operator looked for fullscreen and did not see it. Rename the control "Full screen", with an expand icon, and its exit to "Exit full screen" with a collapse icon.
* Also put a small full-screen icon button on the video's bottom-right corner, above the iframe, in our layer, because that is where people look.
* Keep the internal name `Focus` in code if a rename is wide. The copy lives in `copy.ts` under the no-guilt scan.
* e2e: both buttons enter Focus; both are visible and reachable at every width.

B2. iPhone landscape: Save is hidden, and Focus did not engage
Evidence: the operator's iPhone Safari screenshot (a tab, not the PWA), landscape, 14:55.

* The page is not in Focus: the bottom nav is visible and the video is not full-width.
* The word sheet is cut off by the bottom nav, so Save is not visible.

Tasks

1. Find why rotation did not enter Focus on iPhone Safari. The `matchMedia` listener, `change` event support, or a check at mount? Fix it, and state the cause in the record. Test it with a stub that behaves like WebKit's `MediaQueryList`: if older iOS only supports `addListener`, handle both.
2. In Focus, and in any landscape phone viewport, the bottom nav is hidden.
3. The word sheet must fit a short viewport.
   * It gets `max-height` against `100dvh`, with its body scrolling.
   * Save is sticky at the bottom of the sheet, always visible.
   * Safe-area insets are respected.
   * e2e at 844×390 and 667×375: Save is in the viewport and clickable with no scrolling, with a two-sense entry and with a three-sense entry. Red first on today's tree.

B3. YouTube's own captions double ours
Evidence: the operator's iPhone portrait screenshot shows YouTube's caption ("Yes, and people should remember that they can get a free worksheet") inside the video, while ours shows underneath. `cc_load_policy: 0` does not override a viewer's saved YouTube caption preference.
Tasks

1. After `onReady`, turn YouTube's captions off with the IFrame API's captions module: `player.unloadModule('captions')`, or `setOption('captions','track',{})`.
   * These are undocumented. Say so in the code comment and the record, and guard every call so a missing method does nothing and never throws (W31a's rule: no swallow-everything `try/catch`; check that the method exists).
2. If they cannot be turned off, tell the learner.
   * Where the player exposes whether a caption track is active (`getOption('captions','track')`, guarded), show a one-line hint under the player: "YouTube subtitles are on. Tap CC on the video to turn them off — ours are below."
   * Dismissible, no-guilt copy.
   * If detection is impossible, say so and show nothing. Never guess.
3. Tests: Vitest with a fake player, both with and without the module methods, red first. e2e: the fake player records `unloadModule('captions')`.

B4. Saved words: make the loop visible
The operator asked whether a saved word will be practised later. It is: cards go to the FSRS deck (block 1 of the daily session and `/review`) and to the word drill (W31d).

* Make that visible at the moment of saving. The sheet's saved state reads: "Saved. You'll practise it in Review and in word practice." Plain, no count.
* e2e: assert the copy after Save.

C. Next action (one block per role, #422)

* Mac: push, and state the expected `rev-parse`.
* Host, as `bot`: backup, pull, `pip install -e packages/core`. No migration expected; say so.
* Host, as root: restart `english-api`, `english-bot` and `english-worker`; `/health` reports 36.
* Vercel: rebuild.
* Operator checks:
   * iPhone Safari rotate → Focus, with Save visible in landscape;
   * YouTube captions off, or the hint shown;
   * the "Full screen" button and the corner icon;
   * the saved-state copy;
   * Android rotate, if a device is available.
* Carry every earlier unrun check. That includes:
   * `--payload 25`;
   * the 20 `lt` entries for Morkyte;
   * W13d-P1;
   * W18-R2 → W18-P1;
   * Monday's Apify charge;
   * #457;
   * W25 next;
   * W22's gates.

Then rebase `w22-bot-reduction` onto `main`:

* run the full suite on the tip;
* `push --force-with-lease`;
* re-verify R-A;
* do not merge.

Report the commit, the suite counts, the W22 tip and anything filed. Then stop.
