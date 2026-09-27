import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { fixture, mockApi, mockKeepGoing, mockPractice } from "./support/api";
import {
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W31d — word practice (W24f, un-deferred by C6), in every project.
 *
 * **§1a is suspended for W31 (ruling Q4)**; every state asserted here is
 * screenshotted into `e2e/screenshots/W31d/` in place of a design review.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that five minutes of this is worth a
 * learner's time, that the pictures show the word, or that the right words are
 * drawn. The drill here is fixture data; the operator's phone read is the check.
 *
 * **The pictures are a stand-in PNG** served by the mock, so the layout and the
 * credit are real; one test refuses the bytes (as offline) and asserts the drill
 * says so and skips. A first run refused every picture and the screenshots
 * showed *"Which word is this?"* with no picture — which is how the
 * unanswerable-exercise gap was found.
 *
 * **RED BEFORE W31d:** there was no drill, no `/practice/words`, and keep going
 * offered no practice.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W31d/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

const phone = (info: TestInfo) => !info.project.name.startsWith("desktop");

async function centre(locator: import("@playwright/test").Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
}

async function openDrill(page: Page, options: Parameters<typeof mockPractice>[1] = {}) {
  await mockApi(page);
  const answers = await mockPractice(page, options);
  await page.goto("/practice/words");
  await expect(page.getByTestId("drill")).toBeVisible();
  return answers;
}

test.describe("W31d — word practice", () => {
  test("picture → word: four words, each reachable, then the word in its line", async ({ page }, info) => {
    const answers = await openDrill(page);
    await expect(page.getByTestId("drill-prompt")).toHaveText("Which word is this?");
    await expect(page.getByTestId("card-image")).toBeVisible();
    await expect(page.getByTestId("card-image-credit")).toContainText("A. Photographer");
    const options = page.getByTestId("drill-option");
    await expect(options).toHaveCount(4);
    for (let i = 0; i < 4; i += 1) {
      await centre(options.nth(i));
      await expectReachable(options.nth(i));
      if (phone(info)) await expectTapTarget(options.nth(i));
    }
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-picture-to-word");
    await options.nth(1).click();
    await expect(page.getByTestId("drill-outcome")).toContainText("Yes — that's it.");
    await expectInViewport(page, page.getByTestId("drill-full-sentence"));
    expect(answers[0]).toMatchObject({ card_id: 501, kind: "picture_to_word", response: "parrot" });
    await shot(page, info, "2-answered");
  });

  test("meaning → type: the field and Check stay on screen, even over a keyboard", async ({ page }, info) => {
    await openDrill(page, {
      start: { exercises: [fixture.practice_start.exercises[2]] },
      outcome: fixture.practice_wrong_typed,
    });
    await expect(page.getByTestId("drill-definition")).toHaveText(
      "a group of musicians who play together",
    );
    const input = page.getByTestId("drill-input");
    await input.click();
    await input.fill("bend");
    await expectInViewport(page, input);
    await expectInViewport(page, page.getByTestId("drill-check"));
    if (phone(info)) await expectTapTarget(page.getByTestId("drill-check"));
    await shot(page, info, "3-meaning-to-type");
    await page.getByTestId("drill-check").click();
    await expect(page.getByTestId("drill-outcome")).toContainText("It's “band”.");
    await expect(page.getByTestId("drill-outcome")).not.toContainText(/wrong|incorrect|failed/i);
    await shot(page, info, "4-said-plainly");
  });

  test("hear → type: the word from our own API, and the gapped line", async ({ page }, info) => {
    await openDrill(page, { start: { exercises: [fixture.practice_start.exercises[3]] } });
    await expect(page.getByTestId("drill-audio")).toBeVisible();
    await expect(page.getByTestId("drill-sentence")).toHaveText("we found it in the museum's _____.");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-hear-to-type");
  });

  test("word → picture: four pictures to choose from", async ({ page }, info) => {
    await openDrill(page, { start: { exercises: [fixture.practice_start.exercises[1]] } });
    await expect(page.getByTestId("drill-word")).toHaveText("spoon");
    await expect(page.getByTestId("drill-option")).toHaveCount(4);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "6-word-to-picture");
  });

  test("no score anywhere, and the round ends with a way back", async ({ page }, info) => {
    await openDrill(page, { start: { exercises: [fixture.practice_start.exercises[0]] } });
    await page.getByTestId("drill-option").first().click();
    await page.getByTestId("drill-next").click();
    await expect(page.getByTestId("drill-done")).toBeVisible();
    await expect(page.locator("main")).not.toContainText(/\d+\s*(of|\/)\s*\d+|score|points/i);
    await expectReachable(page.getByTestId("drill-again"));
    await shot(page, info, "7-round-done");
  });

  test("a picture that cannot load: said plainly, skipped, nothing sent", async ({ page }, info) => {
    const answers = await openDrill(page, {
      start: { exercises: [fixture.practice_start.exercises[0]] },
      pictures: false,
    });
    await expect(page.getByTestId("drill-picture-gone")).toHaveText(/The picture didn't load/);
    await expect(page.getByTestId("drill-option")).toHaveCount(0);
    await expectReachable(page.getByTestId("drill-next"));
    await shot(page, info, "8-picture-gone");
    await page.getByTestId("drill-next").click();
    await expect(page.getByTestId("drill-done")).toBeVisible();
    expect(answers).toEqual([]);
  });

  test("keep going offers it (not on Sunday), and it opens the drill", async ({ page }) => {
    await mockApi(page, { session: fixture.session_finished });
    await mockKeepGoing(page, { options: fixture.keep_going_with_practice });
    await mockPractice(page);
    await page.goto("/session");
    const offer = page.getByTestId("keep-going-practice");
    await centre(offer);
    await expectReachable(offer);
    await offer.click();
    await expect(page).toHaveURL(/\/practice\/words$/);
    await expect(page.getByTestId("drill")).toBeVisible();
  });
});
