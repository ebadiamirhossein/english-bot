import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { mockApi, mockProgress, progressFixture } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W19 — the Progress tab, in a real browser, in every project (phone,
 * keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame
 * to test against. Every state asserted here is screenshotted into
 * `e2e/screenshots/W19/`, which is how the operator reviews the screen at the
 * launch pass.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the numbers are honest (the
 * Python suite owns that), or that the screen reads as encouragement rather
 * than a ledger of what was not done. That is the launch pass's reading check.
 *
 * **RED DEMONSTRATIONS (2026-09-25):** the line test went red with the SVG's
 * `w-full` changed to `w-[480px]` (the document scrolled sideways on the phone
 * projects: *"the page scrolls horizontally"*); the problem-state test went red
 * with the retry `Button` given `className="pointer-events-none min-h-11"`
 * (*"something covers the control's centre"*). **W18 (2026-09-25):** the level
 * card's two links without `min-h-11` turned both W18 tests red (*"the control
 * is shorter than a thumb"*).
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W19/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openWith(page: Page, key: string | null) {
  await mockApi(page);
  if (key === null) await mockProgress(page, { status: 500 });
  else await mockProgress(page, { body: progressFixture[key] });
  await page.goto("/progress");
  await expect(page.getByTestId("progress-screen")).toHaveAttribute(
    "data-phase",
    key === null ? "problem" : "ready",
  );
}

/** Bring a card into view clear of the fixed bottom nav, and assert it is there. */
async function showCard(page: Page, card: Locator) {
  await card.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectInViewport(page, card);
}

async function theTabIsReachable(page: Page) {
  const tab = page.getByRole("link", { name: "Progress" });
  await expectInViewport(page, tab);
  await expectReachable(tab);
  await expectTapTarget(tab);
}

test.describe("W19 — the progress screen", () => {
  test("week one: one line, no number, and the tab is reachable", async ({ page }, info) => {
    await openWith(page, "empty");
    const empty = page.getByTestId("progress-empty");
    await expectInViewport(page, empty);
    await expect(page.getByTestId("progress-screen")).not.toContainText(/\d/);
    expect(await contrastOf(empty)).toBeGreaterThanOrEqual(4.5);
    await theTabIsReachable(page);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-week-one");
  });

  test("the first day: the count above the fold, no line yet", async ({ page }, info) => {
    await openWith(page, "first_day");
    const number = page.getByTestId("progress-words-number");
    await expectInViewport(page, number);
    await expect(number).toHaveText("12");
    expect(await contrastOf(number)).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByTestId("progress-words-line")).toHaveCount(0);
    await theTabIsReachable(page);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "2-first-day");
  });

  test("weeks in: the line, XP, streak with freezes and units, each on screen", async ({ page }, info) => {
    await openWith(page, "weeks_in");
    await expectInViewport(page, page.getByTestId("progress-words-number"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-weeks-in-top");

    const line = page.getByTestId("progress-words-line");
    await showCard(page, line);
    const box = await line.locator("svg").boundingBox();
    expect(box && box.width, "the line has a real width").toBeGreaterThan(200);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-weeks-in-line");

    for (const id of ["progress-xp", "progress-streak", "progress-units"]) {
      await showCard(page, page.getByTestId(id));
    }
    const freezes = page.getByTestId("progress-freezes");
    await showCard(page, freezes);
    expect(await contrastOf(freezes)).toBeGreaterThanOrEqual(4.5);
    // W18: the `progress-later` line this test checked is gone — its sentence
    // ("…arrive with the placement test") became untrue when W18 turned the
    // radar and history on. The level card is checked in its own test below.
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-weeks-in-streak-units");
    await theTabIsReachable(page);
  });

  test("W18 — the level card: the band, the radar in bands, the history and the link", async ({ page }, info) => {
    await openWith(page, "weeks_in");
    const band = page.getByTestId("progress-level-band");
    await showCard(page, band);
    await expect(band).toHaveText("B2");
    expect(await contrastOf(band)).toBeGreaterThanOrEqual(4.5);
    const radar = page.getByTestId("placement-radar");
    await showCard(page, radar);
    const svg = await radar.locator("svg").boundingBox();
    expect(svg && svg.width, "the radar has a real width").toBeGreaterThan(240);
    await showCard(page, page.getByTestId("progress-level-history"));
    const link = page.getByTestId("progress-level-link");
    await showCard(page, link);
    await expectReachable(link);
    await expectTapTarget(link);
    expect(await contrastOf(link)).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByTestId("progress-level")).not.toContainText(/%|score/i);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "8-level-radar");
  });

  test("W18 — before a first check, the level card is an offer and a link", async ({ page }, info) => {
    await openWith(page, "empty");
    const offer = page.getByTestId("progress-level-offer");
    await showCard(page, offer);
    expect(await contrastOf(offer)).toBeGreaterThanOrEqual(4.5);
    const link = page.getByTestId("progress-level-link");
    await showCard(page, link);
    await expectReachable(link);
    await expectTapTarget(link);
    await expect(page.getByTestId("placement-radar")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "9-level-offer");
  });

  test("no freezes held: the streak card draws no freezes line", async ({ page }, info) => {
    await openWith(page, "no_freezes");
    const streak = page.getByTestId("progress-streak");
    await showCard(page, streak);
    await expect(page.getByTestId("progress-freezes")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "6-no-freezes");
  });

  test("a failed load offers a way back, and it works", async ({ page }, info) => {
    await openWith(page, null);
    const retry = page.getByRole("button", { name: "Try again" });
    await showCard(page, retry);
    await expectReachable(retry);
    await expectTapTarget(retry);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "7-problem");

    await mockProgress(page, { body: progressFixture.weeks_in });
    await retry.click();
    await expect(page.getByTestId("progress-screen")).toHaveAttribute("data-phase", "ready");
  });
});
