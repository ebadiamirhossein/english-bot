import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockVideo } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * **W32e — the operator's first real use of `/watch` (2026-09-28, desktop and
 * iPhone).** Four findings, each asserted here at phone, phone-landscape
 * (the phone projects turned to 844×390 and 667×375) and desktop, light and
 * dark, with screenshots in `e2e/screenshots/W32e/`:
 *
 * - **B1** — *Focus* was not recognised as full screen. The row's button reads
 *   *Full screen* with an expand icon, and a second, icon-only button sits on
 *   the video's bottom-right corner. Both enter Focus, at every width.
 * - **B2** — on iPhone Safari, sideways: the bottom nav painted over Focus and
 *   over the word sheet, so Save was off the screen. **iPhone has no element
 *   fullscreen, so Focus there is the fixed layout — and W32d's landscape specs
 *   never saw it, because Playwright's WebKit grants real fullscreen.** The
 *   iPhone path is forced below by taking element fullscreen away.
 * - **B3** — YouTube's own captions doubled ours (a viewer's saved preference
 *   beats `cc_load_policy: 0`). The fake player carries the undocumented
 *   captions module.
 * - **B4** — the saved state says where the word will be practised.
 *
 * **WHAT THIS CANNOT SHOW:** a real iPhone turned sideways (its toolbars, its
 * safe areas, the rotation itself), and whether YouTube's real player honours
 * `unloadModule('captions')` — both are the operator's phone checks.
 *
 * **RED BEFORE W32e (2026-09-28), on `f8ce946`:** every test below failed —
 * the buttons read *Focus*, there was no corner button, the nav covered Focus
 * and the sheet's Save, nothing unloaded YouTube's captions, and a Save read
 * *Added to your deck.*
 */

type Yt = {
  time: number;
  state: number;
  unloaded: string[];
  track: Record<string, unknown>;
};

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W32e/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

const desktop = (info: TestInfo) => info.project.name.startsWith("desktop");

/** iPhone Safari: no element fullscreen, so Focus is the fixed layout. */
async function iphone(page: Page) {
  await page.addInitScript(() => {
    for (const key of ["fullscreenEnabled", "webkitFullscreenEnabled"]) {
      Object.defineProperty(Document.prototype, key, { get: () => false, configurable: true });
    }
  });
}

async function openWatch(page: Page, captions: "absent" | "on" | "stuck" = "absent") {
  await fakeYouTube(page, { captions });
  await mockApi(page);
  await mockKeepGoing(page, { watch: fixture.watch_study });
  await mockVideo(page, { meanings: fixture.watch_meanings, save: fixture.save_saved });
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-meanings", "ready");
}

async function at(page: Page, seconds: number, contains: string) {
  await page.evaluate((t) => {
    (window as unknown as { __yt: Yt }).__yt.time = t;
  }, seconds);
  await expect(page.getByTestId("subtitle-now")).toContainText(contains);
}

const nav = (page: Page) => page.locator('nav[aria-label="Main"]');

/** Scroll a control to the middle of the viewport — as a learner would read
 * it, rather than to the edge the fixed nav sits on. */
async function centre(locator: Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
}

/** Save: on the screen with no scrolling, nothing over it, and a tap reaches it. */
async function saveOnScreen(page: Page) {
  const save = page.getByTestId("word-sheet-save");
  await expectInViewport(page, save);
  await expectReachable(save);
  await expectTapTarget(save);
}

// ── B1 — Full screen, twice ──────────────────────────────────────────────────

const WIDTHS = [
  { name: "320", width: 320, height: 568 },
  { name: "390", width: 390, height: 768 },
];

test("both full-screen buttons are visible, reachable and enter Focus", async ({ page }, info) => {
  await openWatch(page);
  const sizes = desktop(info) ? [null] : WIDTHS;
  for (const size of sizes) {
    if (size) await page.setViewportSize({ width: size.width, height: size.height });
    const root = page.getByTestId("video-player");
    const row = page.getByTestId("focus-enter");
    const corner = page.getByTestId("focus-corner");
    await expect(row).toHaveText("Full screen");
    await expect(row.locator("svg")).toHaveCount(1);
    await expect(corner).toHaveAccessibleName("Full screen");
    // The corner is the video's own bottom-right, drawn above the picture.
    const video = (await page.getByTestId("video-box").boundingBox())!;
    const box = (await corner.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(video.x + video.width + 0.5);
    expect(box.y + box.height).toBeLessThanOrEqual(video.y + video.height + 0.5);
    expect(box.x).toBeGreaterThan(video.x + video.width / 2);
    expect(box.y).toBeGreaterThan(video.y + video.height / 2);
    for (const control of [row, corner]) {
      await centre(control);
      await expectInViewport(page, control);
      await expectReachable(control);
      if (!desktop(info)) await expectTapTarget(control);
    }
    await expectNoHorizontalOverflow(page);
    await centre(row);
    await expectInViewport(page, corner);
    await shot(page, info, `fullscreen-buttons-${size?.name ?? "desktop"}`);

    for (const control of [row, corner]) {
      await centre(control);
      await control.click();
      await expect(root).not.toHaveAttribute("data-focus", "off");
      const exit = page.getByTestId("focus-exit");
      await expect(exit).toHaveText("Exit full screen");
      await expect(exit.locator("svg")).toHaveCount(1);
      await expectReachable(exit);
      await exit.click();
      await expect(root).toHaveAttribute("data-focus", "off");
    }
  }
});

// ── B2 — iPhone sideways ─────────────────────────────────────────────────────

const LANDSCAPES = [
  { name: "844x390", width: 844, height: 390 },
  { name: "667x375", width: 667, height: 375 },
];

for (const size of LANDSCAPES) {
  test(`iPhone ${size.name}: turning sideways enters Focus, the nav is gone, Save stays on screen`, async ({ page }, info) => {
    test.skip(desktop(info), "a phone turned");
    await iphone(page);
    await openWatch(page);
    const root = page.getByTestId("video-player");
    await page.setViewportSize({ width: size.width, height: size.height });
    // The iPhone path: no element fullscreen, so the fixed layout.
    await expect(root).toHaveAttribute("data-focus", "fixed");
    await expect(nav(page)).toBeHidden();
    await expectReachable(page.getByTestId("focus-exit"));
    await expectNoHorizontalOverflow(page);

    // Two senses (*model*) and three (*suit*): Save on screen, no scrolling.
    for (const [time, line, word, senses] of [
      [3.5, "model", "model", 2],
      [21.5, "suits", "suits", 3],
    ] as const) {
      await at(page, time, line);
      await page.getByTestId("subtitle-now").getByRole("button", { name: word, exact: true }).click();
      const sheet = page.getByTestId("word-sheet");
      await expect(sheet).toBeVisible();
      await expect(sheet.getByTestId("word-sheet-sense")).toHaveCount(senses);
      await expectInViewport(page, sheet.getByTestId("word-sheet-word"));
      await saveOnScreen(page);
      await shot(page, info, `landscape-${size.name}-sheet-${senses}-senses`);
      await sheet.getByTestId("word-sheet-close").click();
      await expect(sheet).toBeHidden();
    }
    await shot(page, info, `landscape-${size.name}-focus`);
  });

  test(`${size.name}, Focus left while sideways: the nav stays hidden and Save stays on screen`, async ({ page }, info) => {
    test.skip(desktop(info), "a phone turned");
    await iphone(page);
    await openWatch(page);
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.getByTestId("focus-exit").click();
    await expect(page.getByTestId("video-player")).toHaveAttribute("data-focus", "off");
    await expect(nav(page)).toBeHidden();
    await at(page, 21.5, "suits");
    await page.getByTestId("subtitle-now").getByRole("button", { name: "suits", exact: true }).click();
    await expect(page.getByTestId("word-sheet-sense")).toHaveCount(3);
    await saveOnScreen(page);
    await shot(page, info, `landscape-${size.name}-unfocused-sheet`);
  });
}

test("the nav is hidden in Focus at any size, and back when Focus ends", async ({ page }, info) => {
  await iphone(page);
  await openWatch(page);
  await expect(nav(page)).toBeVisible();
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-focus", "fixed");
  await expect(nav(page)).toBeHidden();
  await expectReachable(page.getByTestId("focus-exit"));
  await shot(page, info, "focus-fixed");
  await page.getByTestId("focus-exit").click();
  await expect(nav(page)).toBeVisible();
});

test("a portrait phone's sheet: Save on screen with three senses", async ({ page }, info) => {
  test.skip(desktop(info), "the bottom sheet is the phone's");
  await openWatch(page);
  await at(page, 21.5, "suits");
  await page.getByTestId("subtitle-now").getByRole("button", { name: "suits", exact: true }).click();
  await expect(page.getByTestId("word-sheet-sense")).toHaveCount(3);
  await saveOnScreen(page);
  await shot(page, info, "portrait-sheet-3-senses");
});

// ── B3 — YouTube's own captions ──────────────────────────────────────────────

const yt = (page: Page) => page.evaluate(() => (window as unknown as { __yt: Yt }).__yt);

test("YouTube's captions are unloaded when the player is ready, and no hint shows", async ({ page }, info) => {
  await openWatch(page, "on");
  await expect.poll(async () => (await yt(page)).unloaded).toContain("captions");
  expect((await yt(page)).track).toEqual({});
  await expect(page.getByTestId("yt-captions-hint")).toHaveCount(0);
  await shot(page, info, "captions-off");
});

test("captions that will not unload: the hint says so, and it can be dismissed", async ({ page }, info) => {
  await openWatch(page, "stuck");
  const hint = page.getByTestId("yt-captions-hint");
  await expect(hint).toHaveText(/YouTube subtitles are on\. Tap CC on the video to turn them off — ours are below\./);
  // Directly under the player: at the keyboard's height that is just below
  // the fold when the page opens, so it is scrolled to, as the video is.
  await centre(hint);
  await expectInViewport(page, hint);
  const dismiss = page.getByTestId("yt-captions-hint-dismiss");
  await expectReachable(dismiss);
  if (!desktop(info)) await expectTapTarget(dismiss);
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "captions-hint");
  await dismiss.click();
  await expect(hint).toHaveCount(0);
});

test("a player with no captions module: nothing is guessed and no hint shows", async ({ page }) => {
  await openWatch(page, "absent");
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-yt-captions", "unknown");
  await expect(page.getByTestId("yt-captions-hint")).toHaveCount(0);
});

// ── B4 — the saved state says where the word goes ────────────────────────────

test("Save says the word will be practised in Review and in word practice", async ({ page }, info) => {
  await openWatch(page);
  await at(page, 3.5, "model");
  const word: Locator = page.getByTestId("subtitle-now").getByRole("button", { name: "model", exact: true });
  await word.click();
  await page.getByTestId("word-sheet-save").click();
  const result = page.getByTestId("save-word-result");
  await expect(result).toHaveText("Saved. You’ll practise it in Review and in word practice.");
  await expectInViewport(page, result);
  await shot(page, info, "sheet-saved");
});
