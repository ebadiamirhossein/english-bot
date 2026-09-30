import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { API } from "../playwright.config";
import { mockApi, mockTalk, talkFixture } from "./support/api";
import {
  expectDocumentDoesNotScroll,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W33 (D) — retell is a short conversation (#491 → R2, the operator's ruling of
 * 2026-09-30), in a real browser at every project's size and theme, with a
 * screenshot of each turn and of the close in `e2e/screenshots/W33/`.
 *
 * **THE NETWORK IS THE RULING'S ASSERTION: no `POST /conversation/close` goes out
 * before the learner acts.** Every request to the close route is counted from the
 * page's first load; three turns with three follow-up questions must add none,
 * and *That's enough for now* adds exactly one.
 *
 * **NOT MEANT BY A GREEN RUN:** that a question is about the video, that it is
 * worth answering, or that the close's points are true — W33-P1's reading, on a
 * real video, with a real model.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `e2e/screenshots/W33/${state}--${info.project.name}.png`, fullPage: false });
}

function countCloses(page: Page): () => number {
  let n = 0;
  page.on("request", (request) => {
    if (request.url() === `${API}/conversation/close` && request.method() === "POST") n += 1;
  });
  return () => n;
}

async function openRetell(page: Page, close?: unknown) {
  await mockApi(page);
  await mockTalk(page, { kind: "retell", close });
  const closes = countCloses(page);
  await page.goto("/talk");
  await page.getByTestId("rung-retell").click();
  await expect(page.getByTestId("conversation-log")).toContainText(talkFixture.open_retell.reply);
  return closes;
}

const TURNS = [
  "People waits in a line at the bus stop, even when nobody tell them.",
  "I think because they think it is fair, and jumping is very rude.",
  "It start in the war, when food was not enough for everybody.",
];
const QUESTIONS = [talkFixture.turn_retell_1, talkFixture.turn_retell_2, talkFixture.turn_retell_3];

test.describe("W33 (D) — the retell conversation", () => {
  test("three turns, three follow-up questions, no close until the learner acts", async ({ page }, info) => {
    const closes = await openRetell(page);
    await shot(page, info, "6-retell-open");
    for (const [i, text] of TURNS.entries()) {
      const composer = page.getByTestId("conversation-composer");
      await composer.fill(text);
      await page.getByTestId("conversation-send").click();
      const question = page.getByText(QUESTIONS[i].reply, { exact: true });
      await expect(question).toBeVisible();
      await expectInViewport(page, question);
      await expect(page.getByTestId("conversation-closed")).toHaveCount(0);
      await expectInViewport(page, composer);
      const send = page.getByTestId("conversation-send");
      await composer.fill("…");
      await expectInViewport(page, send);
      await expectReachable(send);
      await composer.fill("");
      const end = page.getByTestId("conversation-end");
      await expectInViewport(page, end);
      await expectReachable(end);
      await expectTapTarget(end);
      await expectNoHorizontalOverflow(page);
      await expectDocumentDoesNotScroll(page);
      expect(closes(), `a close was sent after turn ${i + 1}`).toBe(0);
      await shot(page, info, `${7 + i}-retell-turn-${i + 1}`);
    }
    await page.getByTestId("conversation-end").click();
    await expect(page.getByTestId("close-covered")).toContainText("What you got across");
    await expect(page.getByTestId("conversation-closed")).not.toContainText(/%|score|out of/i);
    expect(closes(), "That's enough for now sends exactly one close").toBe(1);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "10-retell-close");
  });

  test("#493: a close that could not check says so, and never praises", async ({ page }, info) => {
    const closes = await openRetell(page, talkFixture.close_retell_unchecked);
    await page.getByTestId("conversation-composer").fill(TURNS[0]);
    await page.getByTestId("conversation-send").click();
    await expect(page.getByText(QUESTIONS[0].reply, { exact: true })).toBeVisible();
    await page.getByTestId("conversation-end").click();
    const line = page.getByTestId("close-unchecked");
    await expect(line).toHaveText("Couldn’t check that one just now. Your retelling still counts.");
    await expectInViewport(page, line);
    const closed = page.getByTestId("conversation-closed");
    await expect(closed).not.toContainText(/came across well/i);
    await expect(closed).not.toContainText("Here’s what I noticed.");
    expect(closes()).toBe(1);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "11-retell-close-unchecked");
  });
});
