import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { mockApi, mockTalk, talkFixture } from "./support/api";
import {
  expectDocumentDoesNotScroll,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W15 — `/talk` and its two rungs, in a real browser, in every project (phone,
 * keyboard-height phone and desktop; light and dark). CLAUDE.md §3a's five
 * assertions on every drawn state: in the viewport, no horizontal overflow,
 * reachable and enabled, both themes, both widths.
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame
 * to test against. Every state asserted here is screenshotted into
 * `e2e/screenshots/W15/` — how the operator reviews these screens at the launch
 * pass.
 *
 * **ALSO CARRIES TWO `/talk` LAYOUT ROWS THIS SLICE OWNS:** #413 (a long thread
 * must not grow the page — first ever browser check of `/talk`, #401) and #409
 * (the composer above the keyboard, with `visualViewport` stubbed at a
 * keyboard's height: **Playwright raises no real keyboard**, so iOS's own
 * panning stays the phone check's).
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that a correction teaches, that a
 * retell's points are true of the video, or that the task is a good one. Those
 * are the launch pass's reading checks.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W15/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openTalk(page: Page, options: Parameters<typeof mockTalk>[1] = {}) {
  await mockApi(page);
  await mockTalk(page, options);
  await page.goto("/talk");
}

async function answerRung(page: Page) {
  await page.getByTestId("rung-answer").click();
  await expect(page.getByTestId("conversation-log")).toContainText(talkFixture.open_answer.reply);
}

test.describe("W15 — /talk's rungs", () => {
  test("the opening screen offers the talk first, then the two rungs", async ({ page }, info) => {
    await openTalk(page);
    const start = page.getByRole("button", { name: "Start talking" });
    const answer = page.getByTestId("rung-answer");
    const retell = page.getByTestId("rung-retell");
    await expectInViewport(page, start);
    await expectReachable(start);
    await expect(answer).toContainText(talkFixture.rungs_both.answer.prompt);
    await expect(retell).toContainText(talkFixture.rungs_both.retell.label);
    for (const card of [answer, retell]) {
      await card.scrollIntoViewIfNeeded();
      await expectInViewport(page, card);
      await expectReachable(card);
      await expectTapTarget(card);
    }
    await expect(page.getByTestId("conversation-rungs")).not.toContainText(/\d/);
    await expectNoHorizontalOverflow(page);
    await page.getByTestId("conversation-idle").evaluate((el) => el.scrollTo(0, 0));
    await shot(page, info, "1-opening-with-rungs");
  });

  test("an answer opens on the task, with the composer and Send on screen", async ({ page }, info) => {
    await openTalk(page);
    await answerRung(page);
    await expect(page.getByText("Answer", { exact: true })).toBeVisible();
    const composer = page.getByTestId("conversation-composer");
    const send = page.getByTestId("conversation-send");
    await expectInViewport(page, composer);
    await composer.fill("Yesterday I wake up at seven and I go to work by bus.");
    await expectInViewport(page, send);
    await expectReachable(send);
    await expectTapTarget(send);
    const leave = page.getByTestId("conversation-end");
    await expectInViewport(page, leave);
    await expectReachable(leave);
    await expectNoHorizontalOverflow(page);
    await expectDocumentDoesNotScroll(page);
    await shot(page, info, "2-answer-open");
  });

  test("an answer's close-out: the raise, the labelled corrections, the words, the way back", async ({ page }, info) => {
    await openTalk(page);
    await answerRung(page);
    await page.getByTestId("conversation-composer").fill("Yesterday I wake up at seven.");
    await page.getByTestId("conversation-send").click();
    const closed = page.getByTestId("conversation-closed");
    await expect(closed).toContainText("Your answer");
    await expect(page.getByTestId("conversation-did-well")).toBeVisible();
    await expect(page.getByTestId("correction-label").first()).toHaveText("Past tense");
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-answer-closeout");

    const keep = page.getByTestId("conversation-word").first().getByRole("button");
    await keep.scrollIntoViewIfNeeded();
    await expectInViewport(page, keep);
    await expectReachable(keep);
    const back = page.getByTestId("close-back");
    await back.scrollIntoViewIfNeeded();
    await expectInViewport(page, back);
    await expectReachable(back);
    await expectTapTarget(back);
    await expectDocumentDoesNotScroll(page);
    await shot(page, info, "4-answer-closeout-foot");
  });

  test("a retell's close-out: what was got across, the video's other points, never a count", async ({ page }, info) => {
    await openTalk(page, { kind: "retell" });
    await page.getByTestId("rung-retell").click();
    await expect(page.getByTestId("conversation-log")).toContainText(talkFixture.open_retell.reply);
    await expect(page.getByText("Retell", { exact: true })).toBeVisible();
    await page.getByTestId("conversation-composer").fill("People waits in a line at the bus stop.");
    await page.getByTestId("conversation-send").click();
    // W33 (D), #491 → R2: the retell asks its follow-up and stays open; the
    // learner ends it (read: straight to the close-out, until W33).
    await expect(page.getByTestId("conversation-log")).toContainText(talkFixture.turn_retell_1.reply);
    await page.getByTestId("conversation-end").click();
    const covered = page.getByTestId("close-covered");
    const also = page.getByTestId("close-also");
    await expect(covered).toContainText("What you got across");
    await expect(also).toContainText("Also in the video");
    await expect(page.getByTestId("conversation-closed")).not.toContainText(/%|score|out of/i);
    await covered.scrollIntoViewIfNeeded();
    await expectInViewport(page, covered.locator("li").first());
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-retell-closeout");
    await also.scrollIntoViewIfNeeded();
    await expectInViewport(page, also.locator("li").last());
    await shot(page, info, "6-retell-closeout-points");
  });

  test("a rung answered in another language says so and corrects nothing", async ({ page }, info) => {
    await openTalk(page, { close: talkFixture.close_not_english });
    await answerRung(page);
    await page.getByTestId("conversation-composer").fill("Vakar atsikėliau septintą.");
    await page.getByTestId("conversation-send").click();
    const notice = page.getByTestId("close-not-english");
    await expectInViewport(page, notice);
    await expect(page.getByTestId("conversation-correction")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "7-not-english");
  });
});

test.describe("W15 — /talk's two layout rows (#413, #409)", () => {
  test("#413: a long thread scrolls inside the log and never grows the page", async ({ page }, info) => {
    await openTalk(page, { kind: "talk" });
    await page.getByRole("button", { name: "Start talking" }).click();
    await page.getByTestId("topic-card").first().click();
    const composer = page.getByTestId("conversation-composer");
    for (let n = 0; n < 8; n += 1) {
      await composer.fill(
        `We ate by the lake for hours and nobody wanted to leave, turn ${"one two three four five six seven eight".split(" ")[n]}.`,
      );
      await page.getByTestId("conversation-send").click();
      await expect(page.getByTestId("conversation-working")).toHaveCount(0);
    }
    await expect(page.locator('[data-speaker="you"]')).toHaveCount(8);
    await expectDocumentDoesNotScroll(page);
    await expectInViewport(page, composer);
    await composer.fill("And then?");
    await expectInViewport(page, page.getByTestId("conversation-send"));
    await expectReachable(page.getByTestId("conversation-send"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "8-long-thread");
  });

  test("#409: with a keyboard's height taken, the composer sits above it", async ({ page }, info) => {
    test.skip(
      !info.project.name.startsWith("phone-") || info.project.name.startsWith("phone-keyboard"),
      "a software keyboard is a phone's; phone-keyboard already draws the height one leaves",
    );
    const viewport = page.viewportSize()!;
    const keyboard = 291; // design `1j`'s keyboard, as `playwright.config.ts` uses it
    // A stand-in `visualViewport` the page reads on load: a real EventTarget whose
    // height the test sets, so the hook's listener is the one that runs.
    await page.addInitScript(
      ({ height }) => {
        const vv = new EventTarget() as EventTarget & Record<string, number>;
        Object.assign(vv, { width: window.innerWidth, height, offsetTop: 0, offsetLeft: 0, pageTop: 0, pageLeft: 0, scale: 1 });
        Object.defineProperty(window, "visualViewport", { configurable: true, get: () => vv });
        (window as unknown as { __vv: typeof vv }).__vv = vv;
      },
      { height: viewport.height },
    );
    await openTalk(page);
    await answerRung(page);
    const composer = page.getByTestId("conversation-composer");
    await composer.focus();
    await page.evaluate((h) => {
      const vv = (window as unknown as { __vv: EventTarget & { height: number } }).__vv;
      vv.height = h;
      vv.dispatchEvent(new Event("resize"));
    }, viewport.height - keyboard);

    const visibleBottom = viewport.height - keyboard;
    const send = page.getByTestId("conversation-send");
    await expect
      .poll(async () => (await send.boundingBox())!.y + (await send.boundingBox())!.height)
      .toBeLessThanOrEqual(visibleBottom + 0.5);
    const box = (await composer.boundingBox())!;
    expect(box.y, "the composer starts above the top of the screen").toBeGreaterThanOrEqual(0);
    expect(box.y + box.height, "the composer is under the keyboard").toBeLessThanOrEqual(visibleBottom);
    await composer.fill("I go to work by bus.");
    await expectReachable(send);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "9-keyboard-up");
  });
});
