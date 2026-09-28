import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockVideo } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * **W32f — /watch polish, from the operator's W32e device checks (2026-09-28).**
 * Asserted at phone, phone-landscape (the phone projects turned to 844×390 and
 * 667×375) and desktop, light and dark; screenshots in `e2e/screenshots/W32f/`.
 *
 * - **B2, #487 (operator ruling):** in full screen the caption is a strip
 *   BELOW the video — never on the picture (YouTube's Required Minimum
 *   Functionality). The video as large as fits at 16:9; on a phone held
 *   sideways the strip's type is a normal size and a line takes ≤ 2 lines.
 *   **Nothing of ours on the picture** — a grid of points over the video all
 *   land on the player, in Focus and out of it; the full-screen icon moved to
 *   the right end of the line under the video (#486).
 * - **B1:** YouTube's CC turned on mid-play → the hint within one poll; off →
 *   gone. Where the player cannot say, a tip on the first full screen only.
 * - **B3:** the Farsi line of the popover and the sheet is set in Vazirmatn —
 *   the declared stack starts with it AND the face is loaded.
 *
 * **WHAT THIS CANNOT SHOW:** YouTube's real control bar (the fake has none),
 * whether the real player's `getOption` answers (W32f-P1), and a real iPhone
 * turned. **Nor whether the screen is good** — that is the operator's (§3a).
 *
 * **RED BEFORE W32f (2026-09-28, on `ca55e40`).**
 */

type Yt = { time: number; state: number; track: Record<string, unknown>; setState: (s: number) => void };

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({ path: `e2e/screenshots/W32f/${state}--${info.project.name}.png`, fullPage: false });
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

type Box = { x: number; y: number; width: number; height: number };
const boxOf = async (l: Locator): Promise<Box> => (await l.boundingBox())!;

/** A 7×5 grid over the video: every point is the player's, none is ours. */
async function nothingOnThePicture(page: Page) {
  const video = await boxOf(page.getByTestId("video-box"));
  const hits = await page.evaluate((v) => {
    const out: (string | null)[] = [];
    for (let i = 1; i <= 7; i += 1) {
      for (let j = 1; j <= 5; j += 1) {
        const el = document.elementFromPoint(v.x + (v.width * i) / 8, v.y + (v.height * j) / 6);
        out.push(el?.closest("[data-testid]")?.getAttribute("data-testid") ?? null);
      }
    }
    return out;
  }, video);
  expect(new Set(hits), "something of ours is drawn on the picture").toEqual(new Set(["fake-yt"]));
  return video;
}

/** The strip is wholly below the video, and the video's bottom is its top. */
async function stripBelowVideo(page: Page) {
  const video = await boxOf(page.getByTestId("video-box"));
  const strip = await boxOf(page.getByTestId("caption-strip"));
  const caption = await boxOf(page.getByTestId("subtitle-now"));
  expect(strip.y, "the strip starts on the picture").toBeGreaterThanOrEqual(video.y + video.height - 0.5);
  expect(caption.y).toBeGreaterThanOrEqual(video.y + video.height - 0.5);
  // Directly under it: the flex gap (0.5rem) and no more.
  expect(strip.y - (video.y + video.height)).toBeLessThanOrEqual(12);
  return { video, strip };
}

/** How many lines the caption takes, from its own line-height. */
const lineCount = (page: Page) =>
  page.getByTestId("subtitle-now").evaluate((el) => {
    const lh = parseFloat(getComputedStyle(el).lineHeight);
    return Math.round(el.getBoundingClientRect().height / lh);
  });

const fontPx = (page: Page) =>
  page.getByTestId("subtitle-now").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));

/** The declared family starts with Vazirmatn, and the face actually loaded. */
async function inVazirmatn(page: Page, line: Locator) {
  const family = await line.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(family).toMatch(/^["']?Vazirmatn["']?,/);
  await expect
    .poll(() =>
      page.evaluate(async () => {
        await document.fonts.ready;
        return [...document.fonts].some(
          (f) => f.family.replace(/["']/g, "") === "Vazirmatn" && f.status === "loaded",
        );
      }),
    )
    .toBe(true);
}

const LINES = (fixture.watch_study.video.lines as { start: number; end: number; text: string }[]).filter(
  (l) => !/^\[[^\]]+\]$/.test(l.text),
);

// ── B2 — the strip, at desktop size ─────────────────────────────────────────

test("desktop Focus: the strip under the video, the popover off the picture, Farsi in Vazirmatn", async ({ page }, info) => {
  test.skip(!desktop(info), "the phone projects are turned sideways below");
  await openWatch(page, "on");
  await at(page, 3.5, "model");
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).not.toHaveAttribute("data-focus", "off");
  const { video } = await stripBelowVideo(page);
  await nothingOnThePicture(page);
  // As large as fits: the height it can have, or the full width.
  const vp = page.viewportSize()!;
  expect(video.width >= vp.width - 26 || video.height >= vp.height * 0.7).toBe(true);
  await expectInViewport(page, page.getByTestId("subtitle-now"));
  expect(await contrastOf(page.getByTestId("subtitle-now"))).toBeGreaterThanOrEqual(4.5);
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "focus-strip");

  const word = page.getByTestId("caption-strip").getByRole("button", { name: "model", exact: true });
  await word.hover();
  const popover = page.getByTestId("word-popover");
  await expect(popover).toContainText("a small copy of something bigger");
  await expectInViewport(page, popover);
  const pop = await boxOf(popover);
  expect(pop.y, "the popover reaches onto the picture").toBeGreaterThanOrEqual(video.y + video.height - 0.5);
  // Never over the word it describes (the first build clamped it up onto it).
  const hovered = await boxOf(word);
  const overlaps =
    pop.x < hovered.x + hovered.width && hovered.x < pop.x + pop.width &&
    pop.y < hovered.y + hovered.height && hovered.y < pop.y + pop.height;
  expect(overlaps, "the popover covers the word it describes").toBe(false);
  await inVazirmatn(page, page.getByTestId("word-popover-l1"));
  await shot(page, info, "focus-strip-popover");

  await word.click();
  const sheet = page.getByTestId("word-sheet");
  await expect(sheet).toBeVisible();
  await expectInViewport(page, page.getByTestId("word-sheet-save"));
  await inVazirmatn(page, sheet.getByTestId("word-sheet-l1").first());
  await shot(page, info, "focus-strip-sheet");
});

// ── B2 — a phone held sideways (the iPhone path: the fixed layout) ─────────

const LANDSCAPES = [
  { name: "844x390", width: 844, height: 390 },
  { name: "667x375", width: 667, height: 375 },
];

for (const size of LANDSCAPES) {
  test(`iPhone ${size.name}: the strip under the video, normal type, every line on ≤ 2 lines`, async ({ page }, info) => {
    test.skip(desktop(info), "a phone turned");
    await iphone(page);
    // A player that can say whether YouTube's captions are on — so no
    // one-time tip takes a row here (the tip's own test is below).
    await openWatch(page, "on");
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(page.getByTestId("video-player")).toHaveAttribute("data-focus", "fixed");
    await at(page, 3.5, "model");
    const { video } = await stripBelowVideo(page);
    await nothingOnThePicture(page);
    // The video shrinks only for the strip and the row: most of the height.
    expect(video.height / size.height).toBeGreaterThanOrEqual(0.6);
    // Normal type — Finding 2 was 24px here.
    const px = await fontPx(page);
    expect(px).toBeGreaterThanOrEqual(14);
    expect(px).toBeLessThanOrEqual(17.5);
    await expectInViewport(page, page.getByTestId("subtitle-now"));
    await expectReachable(page.getByTestId("focus-exit"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, `landscape-${size.name}-strip`);

    // Every spoken line of the fixture, the longest included: ≤ 2 lines.
    let most = 0;
    for (const line of LINES) {
      await at(page, line.start + 0.1, line.text.split(" ")[0].replace(/[^\w']/g, ""));
      const n = await lineCount(page);
      most = Math.max(most, n);
      expect(n, `"${line.text}" takes ${n} lines`).toBeLessThanOrEqual(2);
      await stripBelowVideo(page);
    }
    expect(most).toBeGreaterThanOrEqual(1);

    await at(page, 3.5, "model");
    await page.getByTestId("caption-strip").getByRole("button", { name: "model", exact: true }).click();
    const sheet = page.getByTestId("word-sheet");
    await expect(sheet).toBeVisible();
    await expectInViewport(page, page.getByTestId("word-sheet-save"));
    await expectReachable(page.getByTestId("word-sheet-save"));
    await inVazirmatn(page, sheet.getByTestId("word-sheet-l1").first());
    await shot(page, info, `landscape-${size.name}-sheet`);
  });
}

test("a phone upright, Focus from the button: the strip under the video", async ({ page }, info) => {
  test.skip(desktop(info), "desktop is above");
  await iphone(page);
  await openWatch(page, "on");
  await at(page, 3.5, "model");
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-focus", "fixed");
  await stripBelowVideo(page);
  await nothingOnThePicture(page);
  await expectReachable(page.getByTestId("caption-strip").getByRole("button", { name: "model", exact: true }));
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "portrait-focus-strip");
});

// ── #486 — outside Focus: nothing on the picture; the icon under its corner ─

for (const width of [320, null]) {
  test(`outside Focus${width ? ` at ${width}px` : ""}: the full-screen icon under the video's right edge, nothing on the picture`, async ({ page }, info) => {
    test.skip(width !== null && desktop(info), "a phone width");
    await openWatch(page);
    if (width) await page.setViewportSize({ width, height: 568 });
    await at(page, 3.5, "model");
    const video = await nothingOnThePicture(page);
    const corner = page.getByTestId("focus-corner");
    const icon = await boxOf(corner);
    expect(icon.y).toBeGreaterThanOrEqual(video.y + video.height - 0.5);
    expect(Math.abs(icon.x + icon.width - (video.x + video.width))).toBeLessThanOrEqual(1);
    await corner.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, corner);
    await expectReachable(corner);
    if (!desktop(info)) await expectTapTarget(corner);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, `outside-focus-icon${width ? `-${width}` : ""}`);
    await corner.click();
    await expect(page.getByTestId("video-player")).not.toHaveAttribute("data-focus", "off");
  });
}

// ── B1 — YouTube's CC, mid-play ─────────────────────────────────────────────

test("CC turned on mid-play: the hint within one poll; turned off: gone", async ({ page }, info) => {
  await openWatch(page, "on"); // a saved preference, switched off at ready (W32e)
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-yt-captions", "off");
  await page.evaluate(() => (window as unknown as { __yt: Yt }).__yt.setState(1));
  await page.evaluate(() => {
    (window as unknown as { __yt: Yt }).__yt.track = { languageCode: "en" };
  });
  const hint = page.getByTestId("yt-captions-hint");
  await expect(hint).toBeVisible({ timeout: 3_000 });
  await hint.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectInViewport(page, hint);
  await expectReachable(page.getByTestId("yt-captions-hint-dismiss"));
  if (!desktop(info)) await expectTapTarget(page.getByTestId("yt-captions-hint-dismiss"));
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "captions-on-mid-play");
  await page.evaluate(() => {
    (window as unknown as { __yt: Yt }).__yt.track = {};
  });
  await expect(hint).toHaveCount(0, { timeout: 3_000 });
});

test("CC on in Focus: the hint is under the strip, on screen", async ({ page }, info) => {
  await iphone(page);
  await openWatch(page, "stuck");
  await page.getByTestId("focus-enter").click();
  const hint = page.getByTestId("yt-captions-hint");
  await expect(hint).toBeVisible();
  await expectInViewport(page, hint);
  await expectReachable(page.getByTestId("yt-captions-hint-dismiss"));
  await nothingOnThePicture(page);
  await shot(page, info, "captions-hint-in-focus");
});

test("a player that cannot say: the tip on the first full screen only", async ({ page }, info) => {
  await iphone(page);
  await openWatch(page, "absent");
  await expect(page.getByTestId("yt-captions-tip")).toHaveCount(0);
  await page.getByTestId("focus-enter").click();
  const tip = page.getByTestId("yt-captions-tip");
  await expect(tip).toHaveText(/Seeing two subtitles\? Turn off CC on the video\./);
  await expectInViewport(page, tip);
  const dismiss = page.getByTestId("yt-captions-tip-dismiss");
  await expectReachable(dismiss);
  if (!desktop(info)) await expectTapTarget(dismiss);
  await nothingOnThePicture(page);
  await shot(page, info, "captions-tip");
  await dismiss.click();
  await expect(tip).toHaveCount(0);
  await page.getByTestId("focus-exit").click();
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).not.toHaveAttribute("data-focus", "off");
  await expect(tip).toHaveCount(0);
});

// ── B3 — the Farsi line, upright on a phone ─────────────────────────────────

test("the sheet's Farsi, in Vazirmatn, right to left", async ({ page }, info) => {
  await openWatch(page);
  await at(page, 3.5, "model");
  await page.getByTestId("subtitle-block").getByRole("button", { name: "model", exact: true }).click();
  const l1 = page.getByTestId("word-sheet-l1").first();
  await expect(l1).toHaveAttribute("lang", "fa");
  await expect(l1).toHaveAttribute("dir", "rtl");
  await inVazirmatn(page, l1);
  await shot(page, info, "sheet-farsi");
});
