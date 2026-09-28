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

/**
 * **W32f (#487): REPLACED.** Until W32f this was `captionInsideVideo` — the
 * caption's box inside the video's, in its bottom half — and
 * `clickReachesTheVideo` proved a click beside the caption still reached the
 * picture. **The operator ruled on 2026-09-28 that the caption moves to a strip
 * BELOW the video** (YouTube's Required Minimum Functionality forbids overlays
 * on the embedded player), so both are inverted: the caption is wholly below
 * the video, and nothing of ours is on the picture at all.
 */
async function captionBelowVideo(page: Page) {
  const video = (await page.getByTestId("video-box").boundingBox())!;
  const caption = (await page.getByTestId("subtitle-now").boundingBox())!;
  expect(caption.y).toBeGreaterThanOrEqual(video.y + video.height - 0.5);
  return { video, caption };
}

type Box = { x: number; y: number; width: number; height: number };

/** A 7×5 grid over the video: every point is YouTube's, none is ours. */
async function nothingOnThePicture(page: Page, video: Box) {
  const hits = await page.evaluate((v) => {
    const out: (string | null)[] = [];
    for (let i = 1; i <= 7; i += 1) {
      for (let j = 1; j <= 5; j += 1) {
        const el = document.elementFromPoint(v.x + (v.width * i) / 8, v.y + (v.height * j) / 6) as HTMLElement | null;
        out.push(el?.closest("[data-testid]")?.getAttribute("data-testid") ?? null);
      }
    }
    return out;
  }, video);
  expect(new Set(hits)).toEqual(new Set(["fake-yt"]));
}

test("desktop Focus: the line is under the video (W32f), readable, and a word in it shows its meaning", async ({ page }, info) => {
  test.skip(!desktop(info), "the phone projects are turned sideways below");
  await openStudy(page);
  await page.getByTestId("focus-enter").click();
  await expect(page.getByTestId("video-player")).not.toHaveAttribute("data-focus", "off");
  const { video } = await captionBelowVideo(page);
  await expectInViewport(page, page.getByTestId("subtitle-now"));
  expect(await contrastOf(page.getByTestId("subtitle-now"))).toBeGreaterThanOrEqual(4.5);
  await nothingOnThePicture(page, video);
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

test("a phone turned sideways enters Focus, the line is under the video (W32f), and turning back exits", async ({ page }, info) => {
  test.skip(desktop(info), "a desktop window made wide is not a phone turned");
  await openStudy(page);
  const root = page.getByTestId("video-player");
  await expect(root).toHaveAttribute("data-focus", "off");
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(root).not.toHaveAttribute("data-focus", "off");
  const { video } = await captionBelowVideo(page);
  await expectInViewport(page, page.getByTestId("subtitle-now"));
  await expectInViewport(page, page.getByTestId("focus-exit"));
  await nothingOnThePicture(page, video);
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
