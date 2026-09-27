import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockApi } from "./support/api";

/**
 * W24c — the shell's width and type scale, **and the proof that a phone does
 * not move.**
 *
 * **The baselines below are COMMITTED BEFORE W24c's CSS change, in a commit of
 * their own**, so "the phone layout is unchanged" is provable from history
 * rather than asserted by the slice that changed it. Until W24c, every
 * screenshot in `e2e/screenshots/` was a review artefact written by
 * `page.screenshot` — **nothing compared one against another**, so no
 * committed image could say a phone had not moved. `toHaveScreenshot` does.
 *
 * Phone projects only: the desktop is the half W24c changes on purpose (R5,
 * ≥1024 px only), and its screenshots are review artefacts like every other
 * slice's, under `e2e/screenshots/W24c/`.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the desktop reads well. That is
 * the operator's check (CLAUDE.md §3a's boundary).
 */

const PHONE = /^phone-/;

const PAGES: { name: string; path: string; ready: (page: Page) => Locator }[] = [
  { name: "home", path: "/", ready: (page) => page.getByRole("link", { name: /Start today/ }) },
  { name: "session", path: "/session", ready: (page) => page.locator('[data-block-kind="output"]') },
  { name: "write", path: "/write", ready: (page) => page.getByTestId("write-field") },
];

/** The shell's column: `main`'s parent in `app/(app)/layout.tsx`. */
const shell = (page: Page) => page.locator("main").locator("..");

async function open(page: Page, path: string, ready: (page: Page) => Locator) {
  await mockApi(page);
  await page.goto(path);
  await expect(ready(page)).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe("W24c — the phone does not move", () => {
  for (const { name, path, ready } of PAGES) {
    test(`${name}: pixel-identical to the baseline committed before W24c`, async ({ page }, info) => {
      test.skip(!PHONE.test(info.project.name), "the phone half; the desktop changes on purpose");
      await open(page, path, ready);
      await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true });
    });
  }

  test("the shell is 32rem wide and the type is 16px", async ({ page }, info) => {
    test.skip(!PHONE.test(info.project.name), "the phone half");
    await open(page, "/", PAGES[0].ready);
    const [maxWidth, rootFont] = await Promise.all([
      shell(page).evaluate((el) => getComputedStyle(el).maxWidth),
      page.evaluate(() => getComputedStyle(document.documentElement).fontSize),
    ]);
    expect(maxWidth).toBe("512px");
    expect(rootFont).toBe("16px");
  });
});
