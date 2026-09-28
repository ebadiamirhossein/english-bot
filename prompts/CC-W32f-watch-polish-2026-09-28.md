W32f — /watch polish, Farsi font, Watch and Words in the menu; record the W32e launch. AGENT mode.
One Claude Code session on this repo at a time (#417). This work goes on `main`, one commit, with its `BUILD_PROGRESS.md` update.
Standing rules:

* no billed call, no SSH, no production entrypoint;
* every new test is demonstrated red first;
* pytest runs serially, with the W10c journals read-only;
* Vitest, `tsc`, `next build` and `E2E_PORT=3190 pnpm test:e2e` are run and counted;
* screenshots of every asserted state, at phone, phone-landscape (844×390, 667×375) and desktop, in light and dark;
* nothing is marked ✅.
* CLAUDE.md §1a stays suspended for this surface, as in W31/W32 (Q4); screenshots are the review.

A. Record the W32e launch (2026-09-28): evidenced on the operator's paste
Deploy

* `ca55e40` pulled.
* Backup `english_bot_2026-09-28_1320.dump`, 2,790,135 bytes, R2 SUCCESS.
* `core.db status`: `Applied: 001 … 036`, `Pending: (none)`, with no migration.
* All three services restarted.
* `/health` → `{"ok":true,"schema_version":36}`.

The operator's device checks, 16:24–16:27 local (desktop Chrome and iPhone Safari), on his report and screenshots

* The "Full screen" button and the corner icon work, on desktop and iPhone.
* iPhone landscape, sheet: Save is visible (`service`, two senses), and the bottom nav is hidden. #485's fix is confirmed on the device. W32e-P1 passes for this part.
* iPhone portrait: the sheet has 2–3 senses with `fa`, and Save is visible.
* The popover and the sheet are instant.
* Finding 1 (B3 did not hold on the device). On desktop, the operator turned YouTube's CC on during playback: the player showed "Subtitles/CC turned on", and YouTube's captions and ours both showed, with no hint. On the iPhone, YouTube's caption also shows under ours in full screen.
* Finding 2. In iPhone landscape full screen, our caption is too large: two lines of large type over the picture.
* Finding 3. The Farsi text renders in the system fallback font and reads poorly. The operator asks for Vazir (Vazirmatn).
* Finding 4. The menu has no Watch and no Words entry. Today's video and saved words are only reachable through "keep going" and Review.

B. Changes
B1. YouTube captions: detect a mid-play toggle, or tell the learner once

* W32e turns captions off once, on `onReady`. A learner can turn CC back on at any time, and the IFrame API has no event for it.
* While playing, poll the guarded `getOption('captions','track')` every 2 s. When it reports a non-empty track, show the hint: "YouTube subtitles are on. Tap CC on the video to turn them off — ours are below." Hide it again when the track clears.
* If the method is missing or always returns nothing (not detectable), fall back to a one-time tip shown the first time the learner enters full screen: "Seeing two subtitles? Turn off CC on the video." It is dismissible and remembered in memory for the session only (no browser storage, CLAUDE.md §5).
* State in the record which path real YouTube takes. That is the operator's device check (W32f-P1). Do not claim it from the fake.
* Tests, red first:
   * Vitest with the fake player: the track appears mid-play → hint; the track clears → no hint; the method is absent → tip on first full screen only;
   * the polling stops when paused, hidden or unmounted.

B2. #487: in full screen, the caption goes in a strip below the video, not on the picture (operator ruling, 2026-09-28)

* Reason: YouTube's Required Minimum Functionality forbids overlays on the embedded player except playback controls. This also fixes Finding 2.
* The layout in Focus:
   * the video is as large as fits, 16:9;
   * directly under it, a caption strip: our current line, hoverable and tappable as today, on the same dark backing;
   * then the control row.
* In landscape phone viewports, the video shrinks just enough for a one-line strip. The caption font scales with the viewport (`clamp()`), so a typical line fits on one or two lines of normal size at 844×390 and 667×375.
* Nothing of ours is drawn over the iframe except the corner full-screen icon (the allowed control). Check #486 again: the icon must not cover YouTube's CC or settings buttons at any tested size. Move it to the caption strip's right end if it can't be placed safely.
* Close #487, with this ruling and the RMF clause quoted.
* e2e, red first:
   * the caption box's bounding rect is outside (below) the video box at desktop and both landscape sizes;
   * there is no horizontal overflow;
   * at 844×390 and 667×375, the caption's rendered line count is ≤ 2 for the fixture's longest line;
   * words in the strip open the popover (desktop) and the sheet (phone).
   * W32d's "caption inside the video box" assertions are replaced, with the reason recorded.

B3. Farsi font: Vazirmatn

* Licence gate first (PRODUCT-PRINCIPLES §3): Vazirmatn is under the SIL Open Font License 1.1. Quote the clause that allows commercial use and bundling into `data/LICENCES.md`, verbatim, with the source URL and the date read.
* Load it through `next/font/google` (`Vazirmatn`, subsets `arabic` and `latin`, `display: swap`), or self-host the OFL files if Google Fonts doesn't serve it. No new CDN origin.
* Apply it only to Persian text: every element rendering an `fa` string gets `lang="fa"`, `dir="rtl"` and the Vazirmatn class. That covers the popover, the sheet, My words, the drill, and anywhere else an `l1.fa` string renders.
* Grep for every place an `fa` string renders, and list them in the record. Lithuanian and English fonts are unchanged.
* Tests:
   * a Vitest check that `fa` elements carry `lang="fa"` and the font class;
   * e2e: the computed `font-family` of the popover's and the sheet's Farsi line starts with Vazirmatn;
   * screenshots.

B4. The menu: add Watch and Words

* Bottom nav, 5 items, in this order: Today · Watch · Words · Map · Progress.
* Watch opens `/watch`, today's assigned video, reachable any day including Sunday (R3). If no video is assigned yet, it shows a calm empty state. It is not a library to browse (PRD §7.4 and R2 are unchanged).
* Words replaces the `Review` item. It opens one page with three parts:
   * Review (today's due cards, with no count; #160 unchanged);
   * Practice words (the W31d drill);
   * My words (the W31c list).
   * Keep `/review` as a working route (redirect or alias). Say which.
* No counters or badges on any nav item (#160, CLAUDE.md §4).
* Phone widths 320–430: the five labels and icons fit with no truncation. Tap targets are ≥ 44 px.
* Update every e2e baseline that shows the nav: read each diff image before updating it (W24d precedent), and list the updated baselines in the record.
* Record this nav change as an operator ruling (2026-09-28) that supersedes the four-item nav. Quote the old order.

C. Next action (one block per role, #422)

* Mac: push, and state the expected `rev-parse`.
* Host, as `bot`: backup, pull, `pip install -e packages/core`. No migration expected; say so.
* Host, as root: restart `english-api`, `english-bot` and `english-worker`; `/health` reports 36.
* Vercel: rebuild.
* Operator checks (W32f-P1):
   * turn YouTube CC on mid-play, and say whether the hint shows or the one-time tip appears;
   * iPhone landscape full screen: the caption sits below the video on 1–2 normal lines;
   * Farsi in Vazirmatn;
   * Watch and Words in the menu;
   * the corner icon does not cover YouTube's buttons.
* Carry every earlier unrun check. That includes:
   * `--payload 25`;
   * Morkyte's 20 `lt` entries (#473);
   * the first `fill_word_dictionary ok` line;
   * W13d-P1;
   * W18-R2 → W18-P1;
   * Monday's Apify charge;
   * #457;
   * #423 (Morkyte onto the web app);
   * W25 next;
   * W22's gates.

Then rebase `w22-bot-reduction` onto `main`:

* run the full suite on the tip;
* `push --force-with-lease`;
* re-verify R-A;
* do not merge.

Report the commit, the suite counts, the W22 tip and anything filed. Then stop.
