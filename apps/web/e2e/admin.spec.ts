import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { adminFixture, mockAdmin, mockApi } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W23 — the operator's panel (`/admin`), in a real browser, in every project
 * (phone, keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (build run 1's ruling 0.3, carried by build
 * run 2)**, so there is no design frame to test against. Every state asserted
 * here is screenshotted into `e2e/screenshots/W23/`, which is how the operator
 * reviews the screen at the launch pass.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the panel shows only activity
 * (the Python suite holds the wire's key set), or that it is useful to the one
 * person who reads it. That is the launch pass's check.
 *
 * **RED DEMONSTRATIONS (2026-09-25):** the long-name test went red on
 * `phone-light` with the name's `break-words min-w-0` replaced by
 * `whitespace-nowrap` (*"ends right of the viewport"*); the problem
 * test went red with the retry `Button` given `className="pointer-events-none
 * min-h-11"` (*"something covers the control's centre"*).
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W23/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openWith(page: Page, options: Parameters<typeof mockAdmin>[1], phase: string) {
  await mockApi(page);
  await mockAdmin(page, options);
  await page.goto("/admin");
  await expect(page.getByTestId("admin-screen")).toHaveAttribute("data-phase", phase);
}

test.describe("W23 — the operator's panel", () => {
  test("two learners: each card on screen, legible, nothing clipped", async ({ page }, info) => {
    await openWith(page, { body: adminFixture.two }, "ready");
    const requests = page.getByTestId("admin-requests");
    await expectInViewport(page, requests);
    expect(await contrastOf(requests)).toBeGreaterThanOrEqual(4.5);
    const cards = page.getByTestId("admin-user");
    await expect(cards).toHaveCount(2);
    const first = cards.first();
    await first.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, first);
    expect(await contrastOf(first.getByRole("heading"))).toBeGreaterThanOrEqual(4.5);
    await expectNoHorizontalOverflow(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, info, "1-two-learners");
  });

  test("a long name, a revoked learner and a waiting request stay inside the screen", async ({ page }, info) => {
    await openWith(page, { body: adminFixture.mixed }, "ready");
    await expect(page.getByTestId("admin-requests")).toContainText("Access request waiting: 1.");
    const long = page.getByRole("heading", { name: /Konstantinas/ });
    await long.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, long);
    const revoked = page.getByText("Access revoked");
    await revoked.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, revoked);
    expect(await contrastOf(revoked)).toBeGreaterThanOrEqual(4.5);
    await expectNoHorizontalOverflow(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, info, "2-mixed");
  });

  test("nobody yet: one line", async ({ page }, info) => {
    await openWith(page, { body: adminFixture.none }, "ready");
    await expectInViewport(page, page.getByTestId("admin-empty"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-nobody");
  });

  test("a learner who is not the operator reads one neutral line and no header", async ({ page }, info) => {
    await openWith(page, { status: 404 }, "not-found");
    const line = page.getByTestId("admin-not-found");
    await expectInViewport(page, line);
    expect(await contrastOf(line)).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByText("Operator")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-not-the-operator");
  });

  test("a failed load: the retry is on screen, reachable and thumb-sized", async ({ page }, info) => {
    await openWith(page, { status: 500 }, "problem");
    const retry = page.getByRole("button", { name: "Try again" });
    await expectInViewport(page, retry);
    await expectReachable(retry);
    await expectTapTarget(retry);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-problem");
  });
});
