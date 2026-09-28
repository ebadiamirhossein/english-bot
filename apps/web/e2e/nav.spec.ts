import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockKeepGoing, mockMyWords, mockPractice, mockVideo } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * **W32f (B4) — the menu gains Watch and Words.** Operator ruling 2026-09-28,
 * superseding the four-item nav (*Today · Map · Review · Progress*): five
 * items, **Today · Watch · Words · Map · Progress**, no counter or badge on any.
 * Asserted at every phone width from 320 to 430 (the five labels and icons fit
 * with no truncation, every tap target ≥ 44 px) and at desktop, light and
 * dark; screenshots in `e2e/screenshots/W32f/`.
 *
 * **Watch** opens today's video with a GET that never assigns (the POST is
 * keep going's); with nothing assigned, a calm line. **Words** is one page of
 * three parts — Review, word practice, My words — and `/review` is an alias of
 * it.
 *
 * **RED BEFORE W32f (2026-09-28, on `ca55e40`):** four items, no Words page,
 * and `/watch` asked the POST.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  // The nav's pill fades in 150 ms after a client navigation; a shot taken
  // inside that showed the item just left still lit (the assertion above it
  // had already passed). Wait for every running transition to finish (a
  // cancelled one rejects, which is also finished).
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))));
  await page.screenshot({ path: `e2e/screenshots/W32f/${state}--${info.project.name}.png`, fullPage: false });
}

const desktop = (info: TestInfo) => info.project.name.startsWith("desktop");
const nav = (page: Page) => page.locator('nav[aria-label="Main"]');
const ORDER = ["Today", "Watch", "Words", "Map", "Progress"];

async function reviewQueue(page: Page) {
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
}

/** Every item: on screen, one line, not truncated, ≥ 44 × 44, reachable. */
async function fiveFit(page: Page, info: TestInfo) {
  const links = nav(page).getByRole("link");
  await expect(links).toHaveText(ORDER);
  await expect(nav(page)).not.toContainText(/\d/);
  for (let i = 0; i < ORDER.length; i += 1) {
    const link = links.nth(i);
    await expectInViewport(page, link);
    await expectReachable(link);
    await expectTapTarget(link);
    const box = (await link.boundingBox())!;
    expect(box.width, `${ORDER[i]} is narrower than a thumb`).toBeGreaterThanOrEqual(44);
    // The label: its own width inside the link's, on one line, not clipped.
    const fits = await link.evaluate((el) => {
      const range = document.createRange();
      const text = [...el.childNodes].find((n) => n.nodeType === Node.TEXT_NODE)!;
      range.selectNodeContents(text);
      const rects = range.getClientRects();
      const r = el.getBoundingClientRect();
      const t = range.getBoundingClientRect();
      return { lines: rects.length, inside: t.left >= r.left - 0.5 && t.right <= r.right + 0.5, overflow: el.scrollWidth > el.clientWidth };
    });
    expect(fits.lines, `${ORDER[i]} wraps`).toBe(1);
    expect(fits.inside, `${ORDER[i]} is cut off`).toBe(true);
    expect(fits.overflow, `${ORDER[i]} overflows its item`).toBe(false);
    await expect(link.locator("svg")).toBeVisible();
  }
  await expectNoHorizontalOverflow(page);
  void info;
}

const WIDTHS = [320, 360, 375, 390, 414, 430];

test("five items at every phone width from 320 to 430, none truncated, every target ≥ 44 px", async ({ page }, info) => {
  await mockApi(page);
  await mockKeepGoing(page);
  await page.goto("/");
  if (desktop(info)) {
    await fiveFit(page, info);
    await shot(page, info, "nav");
    return;
  }
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 768 });
    await fiveFit(page, info);
    await shot(page, info, `nav-${width}`);
  }
});

test("Watch opens today's video with a GET — the POST that assigns is never called", async ({ page }, info) => {
  await fakeYouTube(page);
  await mockApi(page);
  const methods = await mockKeepGoing(page, { watch: fixture.watch_study });
  await mockVideo(page, { meanings: fixture.watch_meanings });
  await page.goto("/");
  await nav(page).getByRole("link", { name: "Watch" }).click();
  await expect(page).toHaveURL(/\/watch$/);
  await expect(page.getByTestId("watch-player")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Today’s video.");
  await expect(nav(page).getByRole("link", { name: "Watch" })).toHaveAttribute("aria-current", "page");
  expect(methods).toEqual(["GET"]);
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "watch-today");
});

test("Watch with nothing assigned today: a calm line, no count, and the way home", async ({ page }, info) => {
  await mockApi(page);
  await mockKeepGoing(page, { today: null });
  await page.goto("/watch");
  const none = page.getByTestId("watch-none");
  await expect(none).toContainText("There’s no video for today.");
  await expect(none).not.toContainText(/\d/);
  await expectReachable(page.getByTestId("watch-back"));
  if (!desktop(info)) await expectTapTarget(page.getByTestId("watch-back"));
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "watch-none-today");
});

test("Words: Review, word practice and My words on one page, no count", async ({ page }, info) => {
  await mockApi(page);
  await reviewQueue(page);
  await mockPractice(page);
  await mockMyWords(page);
  await page.goto("/");
  await nav(page).getByRole("link", { name: "Words" }).click();
  await expect(page).toHaveURL(/\/words$/);
  await expect(nav(page).getByRole("link", { name: "Words" })).toHaveAttribute("aria-current", "page");
  const tabs = page.getByRole("tab");
  await expect(tabs).toHaveText(["Review", "Practice", "My words"]);
  for (let i = 0; i < 3; i += 1) {
    await expectReachable(tabs.nth(i));
    await expectTapTarget(tabs.nth(i));
    // One line each — "Practice words" wrapped at 390 px in the first build.
    const lines = await tabs.nth(i).evaluate((el) => {
      const lh = parseFloat(getComputedStyle(el).lineHeight);
      const range = document.createRange();
      range.selectNodeContents(el);
      return Math.round(range.getBoundingClientRect().height / lh);
    });
    expect(lines).toBe(1);
  }
  await expect(page.getByTestId("words-tabs")).not.toContainText(/\d/);
  await expect(page.getByTestId("words-part-review")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "words-review");

  await page.getByRole("tab", { name: "Practice" }).click();
  await expect(page.getByTestId("drill")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "words-practice");

  await page.getByRole("tab", { name: "My words" }).click();
  await expect(page.getByTestId("my-word")).toHaveCount(3);
  await expectInViewport(page, page.getByTestId("my-word").first());
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "words-mine");
});

test("/review still works — an alias of Words, opening on Review", async ({ page }, info) => {
  await mockApi(page);
  await reviewQueue(page);
  await page.goto("/review");
  await expect(page).toHaveURL(/\/review$/);
  await expect(page.getByRole("tab", { name: "Review" })).toHaveAttribute("aria-selected", "true");
  await expect(nav(page).getByRole("link", { name: "Words" })).toHaveAttribute("aria-current", "page");
  await shot(page, info, "review-alias");
});
