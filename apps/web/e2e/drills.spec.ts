import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { drillFixture, mockApi } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W17 — a weak-spot drill inside block 3, in a real browser, in every project
 * (phone, keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame to
 * test against. In exchange every state asserted here is screenshotted into
 * `e2e/screenshots/W17/`, which is how the operator reviews the screen at the
 * launch pass.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that a drill teaches, that the label
 * names the pattern in words a B1 learner reads the way it is meant, or that the
 * right pattern was chosen. Those are the launch pass's reading checks.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W17/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openOn(page: Page, key: string) {
  await mockApi(page, { session: drillFixture[key], answer: drillFixture.answer_drill });
  await page.goto("/session");
  const card = page.getByTestId("item-card");
  await card.evaluate((el) => el.scrollIntoView({ block: "center" }));
  return card;
}

test.describe("W17 — block 3 with a weak-spot drill", () => {
  test("the unit's item comes first and carries no drill label", async ({ page }, info) => {
    await openOn(page, "session_unit_first");
    await expect(page.getByText("Practice · 1 of 3")).toBeVisible();
    await expect(page.getByTestId("focus-drill")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-unit-item-first");
  });

  test("a drill names its pattern, and its answer control is on screen and tappable", async ({ page }, info) => {
    await openOn(page, "session_on_drill");
    const drill = page.getByTestId("focus-drill");
    const pill = page.getByTestId("focus-drill-pattern");
    await drill.evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.evaluate(() => window.scrollBy(0, -96));
    await expectInViewport(page, drill);
    await expect(pill).toHaveText("Articles");
    await expect(drill).not.toContainText(/\d/);
    expect(await contrastOf(pill), "the pill's text against what is painted behind it").toBeGreaterThanOrEqual(4.5);

    const field = page.getByTestId("typed-answer-input");
    await field.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, field);
    await expectReachable(field);
    await field.fill("the");
    const check = page.getByRole("button", { name: "Check" });
    await check.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, check);
    await expectReachable(check);
    await expectTapTarget(check);
    await expectNoHorizontalOverflow(page);
    await drill.evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.evaluate(() => window.scrollBy(0, -96));
    await shot(page, info, "2-drill-before-answer");

    await check.click();
    const feedback = page.getByTestId("feedback");
    await feedback.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, feedback);
    await expect(page.getByTestId("focus-drill-pattern")).toHaveText("Articles");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-drill-after-answer");
  });

  test("a drill met before says so and still names its pattern", async ({ page }, info) => {
    await openOn(page, "session_on_seen_drill");
    const drill = page.getByTestId("focus-drill");
    await drill.evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.evaluate(() => window.scrollBy(0, -96));
    await expectInViewport(page, drill);
    await expect(page.getByTestId("focus-drill-pattern")).toHaveText("Subject and verb");
    await expect(page.getByTestId("focus-seen-before")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-seen-drill");
  });
});
