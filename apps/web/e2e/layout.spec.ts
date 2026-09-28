import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockApi } from "./support/api";
import { expectInViewport, expectNoHorizontalOverflow, expectReachable } from "./support/assertions";

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
 *
 * **UPDATED ONCE, BY W32f (2026-09-28), AND ONLY IN THE NAV BAND.** The bottom
 * nav went from four items to five (operator ruling: Today · Watch · Words ·
 * Map · Progress), so all twelve baselines changed. Each diff image was read
 * before the update (W24d's precedent): every changed pixel lies in the nav's
 * rows (709–751 at 768 px tall, 418–460 at 477), and the page above it is
 * pixel-identical — so "the phone does not move" still holds for every page.
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

/**
 * **RED BEFORE THE CSS (2026-09-27):** the desktop half below failed on the
 * shell's `512px` and the root's `16px` — W1b's phone-width column at every
 * width, which R5 overrules at ≥1024 px only.
 */
test.describe("W24c — the desktop column is wider and the type larger (R5)", () => {
  test("the shell is 42rem wide at a desktop's 18px, and nothing overflows", async ({ page }, info) => {
    test.skip(PHONE.test(info.project.name), "the desktop half");
    await open(page, "/", PAGES[0].ready);
    const [maxWidth, rootFont] = await Promise.all([
      shell(page).evaluate((el) => getComputedStyle(el).maxWidth),
      page.evaluate(() => getComputedStyle(document.documentElement).fontSize),
    ]);
    // 42rem at an 18px root: 42 × 18. Hardcoded, not read from the CSS.
    expect(maxWidth).toBe("756px");
    expect(rootFont).toBe("18px");
    await expectNoHorizontalOverflow(page);
    await expectReachable(PAGES[0].ready(page));
  });

  for (const { name, path, ready } of PAGES) {
    test(`${name}: screenshotted for the operator's read`, async ({ page }, info) => {
      await open(page, path, ready);
      await expectNoHorizontalOverflow(page);
      await expectInViewport(page, page.getByRole("heading", { level: 1 }).first());
      await page.screenshot({
        path: `e2e/screenshots/W24c/${name}--${info.project.name}.png`,
        fullPage: false,
      });
    });
  }
});
