import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockVideo } from "./support/api";
import { contrastOf, expectInViewport, expectNoHorizontalOverflow } from "./support/assertions";

/**
 * **W32d — the subtitle line ON the video in Focus, and a phone turned
 * sideways enters Focus.** The operator, 2026-09-27: most learners watch full
 * screen or with the phone turned, and W31b's line under the video had little
 * room in landscape.
 *
 * Asserted at desktop size and at phone-landscape size (844×390, the phone
 * projects turned), light and dark, with screenshots in
 * `e2e/screenshots/W32d/`: **the caption is inside the video's own box**; a
 * word in it opens the popover (desktop) or the sheet (a tap); a click on the
 * picture outside the caption still reaches the video; YouTube's fullscreen and
 * captions stay off.
 *
 * **WHAT THIS CANNOT SHOW:** how it feels on a real iPhone or Android held
 * sideways — the rotation here is a viewport change in a desktop browser, and
 * the installed app's behaviour (the manifest, the Android lock) is the
 * operator's phone check.
 *
 * **RED BEFORE W32d:** Focus put the line under the video, and a landscape
 * viewport did nothing.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W32d/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

const desktop = (info: TestInfo) => info.project.name.startsWith("desktop");

async function openStudy(page: Page) {
  await fakeYouTube(page);
  await mockApi(page);
  await mockKeepGoing(page, { watch: fixture.watch_study });
  await mockVideo(page, { meanings: fixture.watch_meanings });
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-meanings", "ready");
  // A line with a word the map holds: "it's a model of one. we found…"
  await page.evaluate(() => {
    (window as unknown as { __yt: { time: number } }).__yt.time = 3.5;
  });
  await expect(page.getByTestId("subtitle-now")).toContainText("model");
}

async function captionInsideVideo(page: Page) {
  const video = (await page.getByTestId("video-box").boundingBox())!;
  const caption = (await page.getByTestId("subtitle-now").boundingBox())!;
  expect(caption.x).toBeGreaterThanOrEqual(video.x - 1);
  expect(caption.y).toBeGreaterThanOrEqual(video.y - 1);
  expect(caption.x + caption.width).toBeLessThanOrEqual(video.x + video.width + 1);
  expect(caption.y + caption.height).toBeLessThanOrEqual(video.y + video.height + 1);
  // In the bottom half, as captions are.
  expect(caption.y).toBeGreaterThan(video.y + video.height / 2);
  return { video, caption };
}

type Box = { x: number; y: number; width: number; height: number };

async function clickReachesTheVideo(page: Page, video: Box, caption: Box) {
  // Two points on the picture: well above the caption, and BESIDE it on the
  // caption's own row — the layer spans the video's width there, so this is
  // the point a layer that caught the pointer would steal (the first version
  // tested only the first point, and a mutation that made the layer catch the
  // pointer passed it).
  const at = async (x: number, y: number) =>
    page.evaluate(
      ({ x, y }) => (document.elementFromPoint(x, y) as HTMLElement | null)?.dataset.testid ?? null,
      { x, y },
    );
  expect(await at(video.x + video.width / 2, video.y + video.height * 0.3)).toBe("fake-yt");
  const beside = Math.max(video.x + 4, caption.x - 12);
  expect(beside).toBeLessThan(caption.x);
  expect(await at(beside, caption.y + caption.height / 2)).toBe("fake-yt");
}

test("desktop Focus: the line is on the video, readable, and a word in it shows its meaning", async ({ page }, info) => {
  test.skip(!desktop(info), "the phone projects are turned sideways below");
  await openStudy(page);
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).not.toHaveAttribute("data-focus", "off");
  const { video, caption } = await captionInsideVideo(page);
  await expectInViewport(page, page.getByTestId("subtitle-now"));
  expect(await contrastOf(page.getByTestId("subtitle-now"))).toBeGreaterThanOrEqual(4.5);
  await clickReachesTheVideo(page, video, caption);
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "focus-caption");
  // Playing, then the pointer onto the caption: it pauses, as W31b's block
  // does (C5) — the caption is this Focus's current-line block.
  await page.evaluate(() => {
    const yt = (window as unknown as { __yt: { state: number; pauses: number } }).__yt;
    yt.state = 1;
    yt.pauses = 0;
  });
  const word = page.getByTestId("subtitle-now").getByRole("button", { name: "model", exact: true });
  await word.hover();
  expect(
    await page.evaluate(() => (window as unknown as { __yt: { pauses: number } }).__yt.pauses),
  ).toBe(1);
  const popover = page.getByTestId("word-popover");
  await expect(popover).toContainText("a small copy of something bigger");
  await expectInViewport(page, popover);
  await shot(page, info, "focus-popover");
  await word.click();
  await expect(page.getByTestId("word-sheet")).toBeVisible();
  await expectInViewport(page, page.getByTestId("word-sheet-save"));
  await shot(page, info, "focus-sheet");
  // YouTube's own fullscreen and captions stay off, so two tracks never show.
  const vars = await page.evaluate(
    () => (window as unknown as { __yt: { options: { playerVars: Record<string, unknown> } } }).__yt.options.playerVars,
  );
  expect([vars.fs, vars.cc_load_policy]).toEqual([0, 0]);
});

test("a phone turned sideways enters Focus, the line is on the video, and turning back exits", async ({ page }, info) => {
  test.skip(desktop(info), "a desktop window made wide is not a phone turned");
  await openStudy(page);
  const root = page.getByTestId("video-player");
  await expect(root).toHaveAttribute("data-focus", "off");
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(root).not.toHaveAttribute("data-focus", "off");
  const { video, caption } = await captionInsideVideo(page);
  await expectInViewport(page, page.getByTestId("subtitle-now"));
  await expectInViewport(page, page.getByTestId("focus-exit"));
  await clickReachesTheVideo(page, video, caption);
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "landscape-caption");
  await page.getByTestId("subtitle-now").getByRole("button", { name: "model", exact: true }).click();
  const sheet = page.getByTestId("word-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByTestId("word-sheet-sense").first()).toContainText("a small copy of something bigger");
  await shot(page, info, "landscape-sheet");
  await sheet.getByTestId("word-sheet-close").click();
  await page.setViewportSize({ width: 390, height: 768 });
  await expect(root).toHaveAttribute("data-focus", "off");
});

test("a Focus the learner chose stays when the phone turns back", async ({ page }, info) => {
  test.skip(desktop(info), "rotation is a phone's");
  await openStudy(page);
  const root = page.getByTestId("video-player");
  await page.getByTestId("focus-enter").click();
  await expect(root).not.toHaveAttribute("data-focus", "off");
  await page.setViewportSize({ width: 844, height: 390 });
  await page.setViewportSize({ width: 390, height: 768 });
  await expect(root).not.toHaveAttribute("data-focus", "off");
});
