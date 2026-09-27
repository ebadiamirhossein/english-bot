import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockVideo } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W31b — the study screen on `/watch`, in a real browser, in every project
 * (phone, keyboard-height phone, desktop; light and dark).
 *
 * **§1a is suspended for W31 (ruling Q4)**: the reference is Trancy / Language
 * Reactor, named by the operator, and **every state asserted here is
 * screenshotted into `e2e/screenshots/W31b/`** in place of a design review.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the lines read well, that the
 * breaks fall where a listener would put them, or that the screen helps anyone
 * learn. The lines are synthesised; the real ones are the operator's
 * three-video `lines --report` on the host (Q2) and the phone check.
 *
 * **RED BEFORE W31b:** `/watch` rendered one paragraph, no current line, no
 * list, no Focus, and passed no `fs`/`playsinline` — every test below failed.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W31b/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openStudy(page: Page, watch: unknown = fixture.watch_study) {
  await fakeYouTube(page);
  await mockApi(page);
  await mockKeepGoing(page, { watch });
  const saves = await mockVideo(page);
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  return saves;
}

async function at(page: Page, seconds: number) {
  await page.evaluate((t) => {
    (window as unknown as { __yt: { time: number } }).__yt.time = t;
  }, seconds);
}

/** Centre a control, as a learner scrolls to one: an edge-scroll parks it
 * under the fixed bottom nav (the W24e specs' `usable()` does the same). */
async function centre(locator: import("@playwright/test").Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
}

const yt = (page: Page) =>
  page.evaluate(() => (window as unknown as { __yt: Record<string, unknown> }).__yt);

test.describe("W31b — study mode", () => {
  test("YouTube's own fullscreen is off and the video plays inline", async ({ page }) => {
    await openStudy(page);
    const options = (await yt(page)).options as { playerVars: Record<string, unknown> };
    expect(options.playerVars.fs).toBe(0);
    expect(options.playerVars.playsinline).toBe(1);
  });

  test("the line being spoken sits under the player, on screen, cleaned", async ({ page }, info) => {
    await openStudy(page);
    await at(page, 0.5);
    const now = page.getByTestId("subtitle-now");
    // C1: the shouted line is sentence case and the name keeps its capital.
    await expect(now).toHaveText("Hey, Ross! Is that a mastodon? [laughter]");
    await page.getByTestId("fake-yt").evaluate((el) => el.scrollIntoView({ block: "start" }));
    await expectInViewport(page, now);
    await expect(page.locator("body")).not.toContainText(">>");
    // The sound tag is dimmed text, never a button.
    const tag = page.getByTestId("subtitle-block").getByTestId("sound-tag");
    await expect(tag).toHaveText("[laughter]");
    expect(await tag.evaluate((el) => el.tagName)).toBe("SPAN");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-current-line");
  });

  test("the list follows the video and highlights the active line", async ({ page }, info) => {
    await openStudy(page);
    const list = page.getByTestId("line-list");
    // The page first, the clock second: scrolling the page while the list is
    // smooth-scrolling interrupts the list's animation half-way.
    await centre(list);
    await at(page, 41.5);
    const active = list.locator('[data-testid="line"][data-active="true"]');
    await expect(active).toHaveText(/you don’t look relaxed at all|you don't look relaxed at all/);
    // Inside the list's own box, not just somewhere in the DOM.
    // The list scrolls smoothly, so the position is polled rather than read once.
    await expect
      .poll(async () => {
        const [row, box] = await Promise.all([active.boundingBox(), list.boundingBox()]);
        return row!.y >= box!.y - 1 && row!.y + row!.height <= box!.y + box!.height + 1;
      })
      .toBe(true);
    // Real styling on the active line (#467): a painted background.
    const bg = await active.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).not.toBe("rgba(0, 0, 0, 0)");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "2-list-follows");
  });

  test("tapping a line's time seeks to it", async ({ page }) => {
    await openStudy(page);
    const seek = page.getByTestId("line-seek").nth(9);
    await centre(seek);
    await expectReachable(seek);
    if (!info_isDesktop(page)) await expectTapTarget(seek);
    await seek.click();
    expect(((await yt(page)).seeks as number[]).at(-1)).toBe(26);
  });

  test("loop line: past its end, back to its start", async ({ page }, info) => {
    await openStudy(page);
    await at(page, 12);
    await expect(page.getByTestId("subtitle-now")).toHaveText("so what’s its nickname?".replace("’", "'"));
    const loop = page.getByTestId("loop-line");
    await centre(loop);
    await expectReachable(loop);
    if (!info.project.name.startsWith("desktop")) await expectTapTarget(loop);
    await loop.click();
    await expect(loop).toHaveAttribute("aria-pressed", "true");
    await at(page, 13.6); // past the line's end (13.4)
    await expect.poll(async () => ((await yt(page)).seeks as number[]).at(-1)).toBe(11.6);
    await shot(page, info, "3-looping");
  });

  test("Focus fills the screen with the player and the line", async ({ page }, info) => {
    await openStudy(page);
    await at(page, 8);
    const enter = page.getByTestId("focus-enter");
    await centre(enter);
    await expectReachable(enter);
    await enter.click();
    const root = page.getByTestId("video-player");
    await expect(root).not.toHaveAttribute("data-focus", "off");
    const vp = page.viewportSize()!;
    const box = (await root.boundingBox())!;
    expect(Math.abs(box.width - vp.width)).toBeLessThanOrEqual(2);
    expect(Math.abs(box.height - vp.height)).toBeLessThanOrEqual(2);
    await expectInViewport(page, page.getByTestId("fake-yt"));
    await expectInViewport(page, page.getByTestId("subtitle-now"));
    await expect(page.getByTestId("subtitle-now")).toHaveText(
      "I told Ross it would never fit through the front door.",
    );
    await expectInViewport(page, page.getByTestId("focus-exit"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-focus");
    await page.getByTestId("focus-exit").click();
    await expect(root).toHaveAttribute("data-focus", "off");
  });

  test("desktop: hovering the current line pauses; the list never does (C5)", async ({ page }, info) => {
    test.skip(!info.project.name.startsWith("desktop"), "a hovering pointer is a desktop's");
    await openStudy(page);
    await at(page, 3.5);
    await page.evaluate(() => {
      (window as unknown as { __yt: { state: number } }).__yt.state = 1; // playing
    });
    await page.getByTestId("subtitle-block").hover();
    await expect.poll(async () => (await yt(page)).pauses).toBe(1);
    await shot(page, info, "5-hover-paused");
    // Leaving resumes what the hover paused …
    await page.getByTestId("line-list").hover();
    await expect.poll(async () => (await yt(page)).plays).toBe(1);
    // … and moving over the list, line by line, pauses nothing.
    for (const n of [2, 5, 8]) await page.getByTestId("line").nth(n).hover();
    expect((await yt(page)).pauses).toBe(1);
  });

  test("a word tap pauses the video; Save posts the word as JSON (#465)", async ({ page }) => {
    const saves = await openStudy(page);
    await at(page, 0.5);
    await page.evaluate(() => {
      (window as unknown as { __yt: { state: number } }).__yt.state = 1;
    });
    const word = page.getByTestId("line-list").getByRole("button", { name: "mastodon" }).first();
    await centre(word);
    await word.click();
    expect((await yt(page)).pauses).toBe(1);
    // W31c: the tap opens the word sheet; Save is in it.
    await page.getByTestId("word-sheet-save").click();
    await expect(page.getByTestId("save-word-result")).toHaveText(
      "Saved. The meaning will be ready soon.",
    );
    expect(saves).toHaveLength(1);
    expect(saves[0].contentType).toContain("application/json");
    // The line's INDEX travels, never its text.
    expect(saves[0].body).toEqual({ word: "mastodon", line: 0 });
  });

  test("no cues: the transcript as untimed lines, no current line, no loop", async ({ page }, info) => {
    await openStudy(page, fixture.watch_untimed);
    await expect(page.getByTestId("line").first()).toHaveText("Hey, Ross!");
    await expect(page.getByTestId("subtitle-block")).toHaveCount(0);
    await expect(page.getByTestId("line-seek")).toHaveCount(0);
    await expect(page.getByTestId("loop-line")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "7-untimed");
    await centre(page.getByTestId("focus-enter"));
    await page.getByTestId("focus-enter").click();
    await expectInViewport(page, page.getByTestId("no-timed"));
    await shot(page, info, "8-untimed-focus");
  });
});

function info_isDesktop(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) >= 1024;
}
