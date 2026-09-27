import { expect, test, type Page, type TestInfo } from "@playwright/test";

import {
  fakeYouTube,
  fixture,
  mockApi,
  mockKeepGoing,
  mockMyWords,
  mockVideo,
} from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W31c — tap and save any word, and My words, in a real browser, in every
 * project (phone, keyboard-height phone, desktop; light and dark).
 *
 * **§1a is suspended for W31 (ruling Q4)**; every state asserted here is
 * screenshotted into `e2e/screenshots/W31c/` in place of a design review.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that a meaning is right, that the
 * Farsi or Lithuanian reads naturally, or that saving words helps anyone
 * learn. The meanings here are fixture text; the real ones are the operator's
 * reading of the first `explain --apply` (Next action, C4).
 *
 * **RED BEFORE W31c:** a tap saved at once and showed one line; there was no
 * sheet, no lookup, no pending save and no `/review/words`.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W31c/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function centre(locator: import("@playwright/test").Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
}

const phone = (info: TestInfo) => !info.project.name.startsWith("desktop");

async function openWatch(page: Page, options: Parameters<typeof mockVideo>[1] = {}) {
  await fakeYouTube(page);
  await mockApi(page);
  await mockKeepGoing(page, { watch: fixture.watch_study });
  const saves = await mockVideo(page, options);
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  return saves;
}

async function tapInList(page: Page, word: string) {
  const button = page.getByTestId("line-list").getByRole("button", { name: word }).first();
  await centre(button);
  await button.click();
  await expect(page.getByTestId("word-sheet")).toBeVisible();
}

test.describe("W31c — the word sheet", () => {
  test("a tapped word: its line, its meaning, the learner's own language, and Save", async ({ page }, info) => {
    await openWatch(page);
    await tapInList(page, "mastodon");
    const sheet = page.getByTestId("word-sheet");
    await expect(page.getByTestId("word-sheet-meaning")).toContainText(
      "a huge animal like an elephant",
    );
    const l1 = page.getByTestId("word-sheet-l1");
    await expect(l1).toHaveText("ماموت");
    await expect(l1).toHaveAttribute("dir", "rtl");
    const save = page.getByTestId("word-sheet-save");
    await expectInViewport(page, save);
    await expectReachable(save);
    if (phone(info)) await expectTapTarget(save);
    await expectInViewport(page, sheet.getByTestId("word-sheet-close"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-sheet-meaning");
  });

  test("a word nobody has explained: still saved, and said plainly", async ({ page }, info) => {
    const saves = await openWatch(page, { lookup: fixture.word_lookup_none });
    await tapInList(page, "basement");
    await expect(page.getByTestId("word-sheet-no-meaning")).toHaveText(
      "No meaning for this one yet — you can still save it.",
    );
    await page.getByTestId("word-sheet-save").click();
    await expect(page.getByTestId("save-word-result")).toHaveText(
      "Saved. The meaning will be ready soon.",
    );
    expect(saves[0].body).toEqual({ word: "basement", line: 1 });
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "2-sheet-saved-pending");
  });

  test("with the job off, the sheet promises nothing (C4)", async ({ page }) => {
    await openWatch(page, { lookup: fixture.word_lookup_none, save: fixture.save_pending_held });
    await tapInList(page, "basement");
    await page.getByTestId("word-sheet-save").click();
    await expect(page.getByTestId("save-word-result")).toHaveText(
      "Saved to your words. Its meaning isn’t ready yet.",
    );
  });

  test("in Focus, a word in the line opens the sheet over the video", async ({ page }, info) => {
    await openWatch(page);
    await page.evaluate(() => {
      (window as unknown as { __yt: { time: number } }).__yt.time = 0.5;
    });
    await centre(page.getByTestId("focus-enter"));
    await page.getByTestId("focus-enter").click();
    const word = page.getByTestId("subtitle-now").getByRole("button", { name: "mastodon" });
    await expect(word).toBeVisible();
    await word.click();
    const save = page.getByTestId("word-sheet-save");
    await expectInViewport(page, save);
    await expectReachable(save);
    await shot(page, info, "3-sheet-in-focus");
    await page.getByTestId("word-sheet-close").click();
    await expect(page.getByTestId("word-sheet")).toHaveCount(0);
  });
});

test.describe("W31c — My words", () => {
  test("reached from Review; each word with its line and a plain state; no count", async ({ page }, info) => {
    await mockApi(page);
    await page.route("**/review/queue*", (route) =>
      route.request().method() === "OPTIONS"
        ? route.fulfill({ status: 204 })
        : route.fulfill({
            status: 200,
            contentType: "application/json",
            headers: {
              "access-control-allow-origin": route.request().headers()["origin"] ?? "*",
              "access-control-allow-credentials": "true",
            },
            body: JSON.stringify({ cards: [], counts: { due: 0, new_today: 0 }, l1_language: "fa" }),
          }),
    );
    await mockMyWords(page);
    await page.goto("/review");
    const link = page.getByTestId("review-my-words");
    await expectReachable(link);
    if (phone(info)) await expectTapTarget(link);
    await link.click();
    await expect(page).toHaveURL(/\/review\/words$/);
    const rows = page.getByTestId("my-word");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText("meaning coming");
    await expect(page.getByTestId("my-words")).not.toContainText(/\d+\s*(words?|left|waiting|saved)/i);
    await expectInViewport(page, rows.nth(0));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-my-words");
  });

  test("none yet: one line saying where they will appear", async ({ page }, info) => {
    await mockApi(page);
    await mockMyWords(page, fixture.my_words_empty);
    await page.goto("/review/words");
    await expect(page.getByTestId("my-words-empty")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-my-words-empty");
  });
});
