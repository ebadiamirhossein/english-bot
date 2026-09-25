import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { mockApi, mockReview, reviewFixture } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W13d — a picturable word's card on `/review`, in a real browser, in every
 * project (phone, keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame;
 * every state asserted here is screenshotted into `e2e/screenshots/W13d/` for
 * the launch pass. The API is the fixture's (`support/api.ts`,
 * `review-queue.fixture.json`), and the picture is this project's own drawing
 * (`e2e/fixtures/card-picture.png`) — no third-party image is in this suite.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that any picture the operator
 * approves shows its word as a learner means it, that a credit line reads well
 * under a real photograph, or that a picture helps a word stick. Those are the
 * launch pass's reading and phone checks (CLAUDE.md §3a's boundary).
 *
 * **RED DEMONSTRATIONS (2026-09-25), each one edit, run on `phone-light`, and
 * restored:** the `<img>` given `w-[520px] max-w-none` in place of
 * `w-full max-w-[330px]` turned "picture and credit" red (*"ends below the
 * fold"* — the picture no longer fits the viewport at all); the figure given
 * `fixed inset-0 z-50` over the card turned the same test red at the grade
 * button (*"something covers the control's centre"*); `onError` removed from
 * `CardImage` turned "cannot load" red (`toHaveCount(0)` received 1: the
 * figure stayed drawn around a broken picture).
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W13d/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function onScreen(page: Page, locator: Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectInViewport(page, locator);
}

async function usable(page: Page, control: Locator) {
  await onScreen(page, control);
  await expectReachable(control);
  await expectTapTarget(control);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const cardWith = (id: number) => reviewFixture.cards.find((c: any) => c.id === id);
const only = (id: number) => ({ ...reviewFixture, cards: [cardWith(id)] });

async function open(page: Page, options: Parameters<typeof mockReview>[1] = {}) {
  await mockApi(page);
  const requests = await mockReview(page, options);
  await page.goto("/review");
  await expect(page.getByTestId("card-face")).toBeVisible();
  return requests;
}

/** Reveal the way a learner would: the reveal button, or "skip typing". */
async function reveal(page: Page) {
  const typed = page.getByTestId("card-skip-typing");
  const button = (await typed.count()) > 0 ? typed : page.getByTestId("reveal");
  await usable(page, button);
  await button.click();
  await expect(page.getByTestId("card-back")).toBeVisible();
}

test.describe("W13d — image cards for concrete vocabulary", () => {
  test("before the reveal: no picture, and none is fetched", async ({ page }, info) => {
    const requests = await open(page, { queue: only(51) });
    await expect(page.getByTestId("card-image")).toHaveCount(0);
    expect(requests).toEqual([]);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-before-reveal");
  });

  test("a picturable word: picture and credit with the answer", async ({ page }, info) => {
    const requests = await open(page, { queue: only(51) });
    await reveal(page);

    const img = page.getByTestId("card-image").getByRole("img");
    await onScreen(page, img);
    await expect
      .poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatch(/\/lexeme-images\/7\.png$/);

    // The credit is VISIBLE (CC BY) and readable, not a footnote off-screen.
    const credit = page.getByTestId("card-image-credit");
    await onScreen(page, credit);
    await expect(credit).toContainText("THOR");
    await expect(credit.getByRole("link", { name: "CC BY 2.0" })).toBeVisible();
    await expect(credit.getByRole("link", { name: "Wikimedia Commons" })).toBeVisible();
    expect(await contrastOf(credit)).toBeGreaterThanOrEqual(4.5);
    await expectNoHorizontalOverflow(page);
    await img.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await shot(page, info, "2-picture-revealed");

    // The picture added a face; the card's own controls still work.
    await usable(page, page.getByTestId("grade-good"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-grade-after-picture");
  });

  test("the picture cannot load (offline): the card is whole, with no broken image", async ({ page }, info) => {
    const requests = await open(page, { queue: only(51), picture: "offline" });
    await reveal(page);
    await expect.poll(() => requests.length).toBe(1);
    await expect(page.getByTestId("card-image")).toHaveCount(0);
    await expect(page.getByTestId("card-image-credit")).toHaveCount(0);
    await onScreen(page, page.getByTestId("card-back"));
    await usable(page, page.getByTestId("grade-good"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-picture-unavailable");
  });

  for (const [id, name] of [
    [52, "abstract-word"],
    [53, "phrasal-verb"],
    [54, "collocation"],
  ] as const) {
    test(`${name}: unchanged — no picture, nothing fetched`, async ({ page }, info) => {
      const requests = await open(page, { queue: only(id) });
      await reveal(page);
      await expect(page.getByTestId("card-image")).toHaveCount(0);
      expect(requests).toEqual([]);
      await onScreen(page, page.getByTestId("card-back"));
      await usable(page, page.getByTestId("grade-good"));
      await expectNoHorizontalOverflow(page);
      await shot(page, info, `5-unchanged-${name}`);
    });
  }
});
