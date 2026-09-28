import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { API } from "../playwright.config";
import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockVideo } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * **W32b — instant meaning for every word on `/watch`**, in a real browser, in
 * every project (phone, keyboard-height phone, desktop; light and dark).
 *
 * The operator, 2026-09-27: hover (desktop) or tap (phone) ANY word and see
 * its meaning in under a second. **The proof that no request is involved is
 * made with the network BLOCKED after the page has loaded**: every request is
 * refused and counted, and the popover and the sheet still show the meaning.
 *
 * **§1a is suspended for this surface (as W31, Q4)**; every asserted state is
 * screenshotted into `e2e/screenshots/W32b/` in place of a design review.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that a meaning is right, or that the
 * Farsi or Lithuanian reads naturally — the map here is fixture text (built by
 * the server's own `assemble_meanings`). The real entries are the operator's
 * `fa` read and Morkyte's `lt` read (Next action).
 *
 * **RED BEFORE W32b:** there was no map, no popover, and the sheet asked the
 * server for every word.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W32b/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

const desktop = (info: TestInfo) => info.project.name.startsWith("desktop");

async function openWatch(page: Page, options: Parameters<typeof mockVideo>[1] = {}) {
  await fakeYouTube(page);
  await mockApi(page);
  await mockKeepGoing(page, { watch: fixture.watch_study });
  await mockVideo(page, { meanings: fixture.watch_meanings, save: fixture.save_saved, ...options });
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-meanings", "ready");
}

/**
 * From here on, every request the page makes is refused — and recorded.
 * **What is asserted is that no request goes to the API** — where every meaning
 * lives — except the progress ping, a 15 s timer that is block 2's log and is
 * named so a count cannot hide it. **Requests to the app's own origin are Next.js
 * prefetching the nav tabs** (`/_next/static/…` code and `?_rsc=` payloads for
 * `/`, `/map`, `/review` — found by the first runs, intermittently, on the
 * phone projects whose bottom nav is on screen); they carry no meaning and are
 * refused all the same.
 */
async function offline(page: Page): Promise<string[]> {
  const seen: string[] = [];
  page.on("request", (request) => seen.push(request.url()));
  await page.route("**/*", (route) => route.abort());
  return seen;
}

function meaningRequests(seen: string[]): string[] {
  return seen.filter((url) => url.startsWith(API) && !url.includes("/progress"));
}

function listWord(page: Page, word: string) {
  return page.getByTestId("line-list").getByRole("button", { name: word, exact: true }).first();
}

async function centre(locator: import("@playwright/test").Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
}

test.describe("W32b — hover, on a desktop pointer", () => {
  test("a word shows its meaning and the learner's own language, with the network blocked", async ({ page }, info) => {
    test.skip(!desktop(info), "hover is a desktop pointer's; a phone taps (below)");
    await openWatch(page);
    const seen = await offline(page);
    const word = listWord(page, "basement");
    await centre(word);
    await word.hover();
    const popover = page.getByTestId("word-popover");
    await expect(popover).toBeVisible();
    await expect(popover).toContainText("a room or floor under a building");
    const l1 = popover.getByTestId("word-popover-l1");
    await expect(l1).toHaveText("زیرزمین");
    await expect(l1).toHaveAttribute("dir", "rtl");
    await expectInViewport(page, popover);
    await expectNoHorizontalOverflow(page);
    // The popover never catches the pointer: the word under it stays clickable.
    await expect(popover).toHaveCSS("pointer-events", "none");
    expect(meaningRequests(seen)).toEqual([]);
    await shot(page, info, "popover-offline");
  });

  test("an inflected word finds its entry, and the video's own meaning comes first, labelled here", async ({ page }, info) => {
    test.skip(!desktop(info), "hover is a desktop pointer's");
    await openWatch(page);
    const relaxed = listWord(page, "relaxed");
    await centre(relaxed);
    await relaxed.hover();
    await expect(page.getByTestId("word-popover")).toContainText("to stop worrying and feel calm");
    await shot(page, info, "popover-inflected");
    const mastodon = listWord(page, "mastodon");
    await centre(mastodon);
    await mastodon.hover();
    const popover = page.getByTestId("word-popover");
    await expect(popover.getByTestId("word-popover-here")).toHaveText("here");
    await expect(popover).toContainText("a big model of an ancient elephant-like animal");
    await shot(page, info, "popover-here");
  });

  test("a word with nothing stored says so, and a click opens the sheet with Save", async ({ page }, info) => {
    test.skip(!desktop(info), "hover is a desktop pointer's");
    await openWatch(page);
    const van = listWord(page, "van");
    await centre(van);
    await van.hover();
    await expect(page.getByTestId("word-popover-miss")).toBeVisible();
    await shot(page, info, "popover-miss");
    await van.click();
    await expect(page.getByTestId("word-popover")).toHaveCount(0);
    await expect(page.getByTestId("word-sheet-no-meaning")).toBeVisible();
    await expectReachable(page.getByTestId("word-sheet-save"));
  });

  test("hovering the current line still pauses, and the popover changes nothing about it (C5)", async ({ page }, info) => {
    test.skip(!desktop(info), "hover-pause is a desktop pointer's");
    await openWatch(page);
    await page.evaluate(() => {
      const yt = (window as unknown as { __yt: { time: number; state: number } }).__yt;
      yt.time = 1.0;
      yt.state = 1;
    });
    const now = page.getByTestId("subtitle-now");
    await expect(now).toContainText("mastodon", { ignoreCase: true });
    const word = now.getByRole("button").first();
    await word.hover();
    await expect(page.getByTestId("word-popover")).toBeVisible();
    const yt = await page.evaluate(() => (window as unknown as { __yt: { pauses: number; plays: number } }).__yt);
    expect(yt.pauses).toBe(1); // the block's pause (W31b), and only that
    expect(yt.plays).toBe(0);
    await shot(page, info, "popover-current-line");
  });
});

test.describe("W32b — the sheet, from the map", () => {
  test("a tap opens the meaning at once, with the network blocked", async ({ page }, info) => {
    await openWatch(page);
    const seen = await offline(page);
    const word = listWord(page, "model");
    await centre(word);
    await word.click();
    const sheet = page.getByTestId("word-sheet");
    await expect(sheet).toBeVisible();
    const senses = sheet.getByTestId("word-sheet-sense");
    await expect(senses).toHaveCount(2);
    await expect(senses.first()).toContainText("a small copy of something bigger");
    await expect(senses.first().getByTestId("word-sheet-l1")).toHaveText("ماکت");
    const save = sheet.getByTestId("word-sheet-save");
    await expectInViewport(page, save);
    await expectReachable(save);
    if (!desktop(info)) await expectTapTarget(save);
    await expectNoHorizontalOverflow(page);
    expect(meaningRequests(seen)).toEqual([]);
    await shot(page, info, "sheet-offline");
  });

  test("here first, the dictionary under it; an informal word carries its safer word", async ({ page }, info) => {
    await openWatch(page);
    const mastodon = listWord(page, "mastodon");
    await centre(mastodon);
    await mastodon.click();
    const sheet = page.getByTestId("word-sheet");
    await expect(sheet.getByTestId("word-sheet-here")).toContainText("a big model of an ancient");
    await expect(sheet.getByTestId("word-sheet-sense")).toContainText("a huge hairy animal");
    await shot(page, info, "sheet-here");
    await sheet.getByTestId("word-sheet-close").click();
    const okay = listWord(page, "okay");
    await centre(okay);
    await okay.click();
    await expect(page.getByTestId("word-sheet")).toContainText("informal");
    await expect(page.getByTestId("word-sheet")).toContainText("all right");
    await shot(page, info, "sheet-informal");
  });

  test("a name is a name", async ({ page }, info) => {
    await openWatch(page);
    const ross = listWord(page, "Ross");
    await centre(ross);
    await ross.click();
    await expect(page.getByTestId("word-sheet-name")).toHaveText("A name.");
    await shot(page, info, "sheet-name");
  });

  test("Save is instant, and the word then reads as kept", async ({ page }, info) => {
    await openWatch(page);
    const word = listWord(page, "nickname");
    await centre(word);
    await word.click();
    await page.getByTestId("word-sheet-save").click();
    await expect(page.getByTestId("save-word-result")).toHaveText("Saved. You’ll practise it in Review and in word practice.");
    await shot(page, info, "sheet-saved");
    await page.getByTestId("word-sheet-close").click();
    await word.click();
    await expect(page.getByTestId("word-sheet-kept")).toHaveText("In your words.");
  });
});
