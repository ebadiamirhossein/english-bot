import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { fixture, mockApi, mockKeepGoing } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W24e — keep going, in a real browser, in every project (phone,
 * keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this work (R4)**: keep going is ruled an extension of
 * the session's done state and the Sunday home, built from the close block's row
 * shape, and **every state asserted here is screenshotted into
 * `e2e/screenshots/W24e/` in place of a design review.**
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the choice feels inviting
 * rather than naggy, that four options are the right number to see after a
 * session, or that a learner finds *watch something* worth a tap. Those are
 * the operator's phone check (CLAUDE.md §3a's boundary).
 *
 * **RED BEFORE W24e (2026-09-27):** `/session` never rendered its done state
 * (the runner read `completed`, which no daily session carries), `/watch` did
 * not exist, and the Sunday home had no offer — every test below failed.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W24e/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function usable(page: Page, control: Locator) {
  await control.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectInViewport(page, control);
  await expectReachable(control);
  await expectTapTarget(control);
}

async function finishedSession(page: Page, options: unknown = fixture.keep_going_weekday) {
  await mockApi(page, { session: fixture.session_finished });
  await mockKeepGoing(page, { options });
  await page.goto("/session");
  await expect(page.getByTestId("session-finished")).toBeAttached();
}

test.describe("W24e — keep going", () => {
  test("a finished session: the done line, then four optional choices", async ({ page }, info) => {
    await finishedSession(page);
    await expect(page.getByText("Done for today.")).toBeVisible();
    for (const kind of ["watch", "talk", "cards", "write"]) {
      await usable(page, page.getByTestId(`keep-going-${kind}`));
    }
    await expect(page.getByTestId("keep-going")).not.toContainText(/[0-9]/);
    await expectNoHorizontalOverflow(page);
    await page.getByTestId("keep-going").evaluate((el) => el.scrollIntoView({ block: "end" }));
    await shot(page, info, "1-finished-four-choices");
  });

  test("nothing on offer: the done line alone, and no empty panel", async ({ page }, info) => {
    await finishedSession(page, fixture.keep_going_none);
    await expect(page.getByText("Done for today.")).toBeVisible();
    await expect(page.getByTestId("keep-going")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await page.getByTestId("session-finished").evaluate((el) => el.scrollIntoView({ block: "end" }));
    await shot(page, info, "2-finished-nothing-offered");
  });

  test("an open session shows no choice at all (R2)", async ({ page }) => {
    await mockApi(page);
    await mockKeepGoing(page);
    await page.goto("/session");
    await expect(page.getByTestId("session-runner")).toBeVisible();
    await expect(page.getByTestId("session-finished")).toHaveCount(0);
    await expect(page.getByTestId("keep-going")).toHaveCount(0);
  });

  test("watch something opens one assigned video, not a list", async ({ page }, info) => {
    await finishedSession(page);
    const watch = page.getByTestId("keep-going-watch");
    await usable(page, watch);
    await watch.click();
    await expect(page).toHaveURL(/\/watch$/);
    await expect(page.getByTestId("watch-player")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Something to watch.");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-watch-one-video");
  });

  test("nothing to watch: a quiet line and a way back", async ({ page }, info) => {
    await mockApi(page);
    await mockKeepGoing(page, { watch: null });
    await page.goto("/watch");
    await expect(page.getByTestId("watch-none")).toBeVisible();
    await expect(page.getByTestId("watch-none")).not.toContainText(/[0-9]/);
    await usable(page, page.getByTestId("watch-back"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-watch-nothing");
  });

  test("Sunday: the report, practise anyway, and only something to watch (R1)", async ({ page }, info) => {
    await mockApi(page);
    await mockKeepGoing(page, { options: fixture.keep_going_sunday, week: fixture.week_sunday });
    await page.goto("/");
    await expect(page.getByTestId("sunday-report")).toBeVisible();
    await expect(page.getByTestId("sunday-session-link")).toBeVisible();
    await expect(page.getByText("If you feel like watching something:")).toBeVisible();
    await usable(page, page.getByTestId("keep-going-watch"));
    for (const kind of ["talk", "cards", "write"]) {
      await expect(page.getByTestId(`keep-going-${kind}`)).toHaveCount(0);
    }
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-sunday-watch-only");
  });
});
