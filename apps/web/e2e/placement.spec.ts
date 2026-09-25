import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { mockApi, mockPlacement, placementFixture } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W18 — the placement check, `/placement`, in a real browser, in every project
 * (phone, keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame
 * to test against. Every state asserted here is screenshotted into
 * `e2e/screenshots/W18/`, which is how the operator reviews it at the launch
 * pass.
 *
 * **The API is the fixture's** (`support/api.ts`, `placement.fixture.json`).
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that the bank's items are good
 * English at the band they claim, that the pseudo-words are not real words,
 * that twelve minutes feels like twelve minutes, or that the result reads as
 * *where to start* and not as a mark. Those are the launch pass's reading and
 * phone checks (CLAUDE.md §3a's boundary).
 *
 * **RED DEMONSTRATIONS (2026-09-25), each one edit, run on `phone-light`, and
 * restored:** the Yes/No grid given `w-[520px]` turned "a word" red (*"the
 * page scrolls horizontally"*); the Send button given `pointer-events-none`
 * turned "speaking, typed" red (*"something covers the control's centre"*); the
 * radar SVG's `w-full max-w-[22rem]` changed to `min-w-[480px]` turned "the
 * result" and "waiting" red (the page scrolled sideways).
 * **The rest, in two batched builds whose mutations each touch one test:** the
 * not-ready line given `w-[520px]` (*"ends right of the viewport"*); the Record
 * button given `pointer-events-none` (*"something covers the control's
 * centre"*); the clip's `AudioSource` pointed elsewhere (the listening test's
 * `src` assert); the question block given `w-[520px]` (both grammar tests). In
 * `progress.spec.ts`, the level card's links without `min-h-11` turned both W18
 * tests red (*"the control is shorter than a thumb"*).
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W18/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openWith(page: Page, options: Parameters<typeof mockPlacement>[1], phase: string) {
  await mockApi(page);
  const calls = await mockPlacement(page, options);
  await page.goto("/placement");
  await expect(page.getByTestId("placement-screen")).toHaveAttribute("data-phase", phase);
  return calls;
}

/** In view, clear of the bottom nav, and readable. */
async function onScreen(page: Page, locator: Locator) {
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectInViewport(page, locator);
}

async function usable(page: Page, control: Locator) {
  await onScreen(page, control);
  await expectReachable(control);
  await expectTapTarget(control);
}

const openStep = (step: unknown) => ({ ...placementFixture.open, step });

test.describe("W18 — the placement check", () => {
  test("not ready: one plain line, and nothing to start", async ({ page }, info) => {
    await openWith(page, { overview: placementFixture.not_ready }, "intro");
    const line = page.getByTestId("placement-not-ready");
    await onScreen(page, line);
    expect(await contrastOf(line)).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByTestId("placement-start")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "1-not-ready");
  });

  test("a word: Start, then the word and both answers on screen, with no count", async ({ page }, info) => {
    const calls = await openWith(page, {}, "intro");
    const start = page.getByTestId("placement-start");
    await usable(page, start);
    await shot(page, info, "2-intro");
    await start.click();

    const word = page.getByTestId("placement-word");
    await expect(word).toHaveText("cupboard");
    await onScreen(page, word);
    expect(await contrastOf(word)).toBeGreaterThanOrEqual(4.5);
    for (const id of ["placement-yes", "placement-no"]) await usable(page, page.getByTestId(id));
    await expect(page.getByTestId("placement-sitting")).not.toContainText(/\d/);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "3-word");

    await page.getByTestId("placement-yes").click();
    await expect.poll(() => calls.filter((c) => c.url.endsWith("/placement/answer")).length).toBe(1);
    expect(calls.find((c) => c.url.endsWith("/placement/answer"))?.body).toEqual({ item_id: 101, known: true });
  });

  test("grammar, typed: the gap, the input and Check on screen", async ({ page }, info) => {
    await openWith(page, { overview: openStep(placementFixture.steps.grammar) }, "sitting");
    await onScreen(page, page.getByText(/the film ___ already started/));
    const input = page.getByTestId("typed-answer-input");
    await usable(page, input);
    await input.fill("had");
    await usable(page, page.getByRole("button", { name: "Check" }));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "4-grammar-typed");
  });

  test("grammar, tap: every tile reachable", async ({ page }, info) => {
    await openWith(page, { overview: openStep(placementFixture.steps.grammar_tap) }, "sitting");
    for (const tile of ["She", "don't", "evening"]) {
      await usable(page, page.getByRole("button", { name: tile, exact: true }));
    }
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "5-grammar-tap");
  });

  test("listening: the play button and the input on screen", async ({ page }, info) => {
    await openWith(page, { overview: openStep(placementFixture.steps.listening) }, "sitting");
    await expect(page.getByTestId("placement-part")).toHaveText("Listening");
    await usable(page, page.getByRole("button", { name: /Play/ }));
    await usable(page, page.getByTestId("typed-answer-input"));
    const src = await page.getByTestId("item-audio").getAttribute("src");
    expect(src).toMatch(/\/placement\/items\/303\/audio$/);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "6-listening");
  });

  test("speaking, typed: the prompt, the box, Send and Skip", async ({ page }, info) => {
    await openWith(page, {
      overview: openStep(placementFixture.steps.speaking),
      answers: [placementFixture.steps.done],
    }, "sitting");
    const prompt = page.getByTestId("placement-prompt");
    await onScreen(page, prompt);
    expect(await contrastOf(prompt)).toBeGreaterThanOrEqual(4.5);
    const box = page.getByTestId("placement-typed");
    await usable(page, box);
    await box.fill("We had dinner by the sea, with my sister.");
    await usable(page, page.getByTestId("placement-send"));
    await usable(page, page.getByTestId("placement-skip"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "7-speaking-typed");
  });

  test("speaking, voice on: Record and Type it instead", async ({ page }, info) => {
    await openWith(page, { overview: openStep(placementFixture.steps.speaking_voice) }, "sitting");
    await usable(page, page.getByTestId("placement-record"));
    await usable(page, page.getByTestId("placement-type-instead"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "8-speaking-voice");
  });

  test("the result: the band raised, the radar in bands, and the way back", async ({ page }, info) => {
    await openWith(page, {
      overview: openStep(placementFixture.steps.speaking),
      answers: [placementFixture.steps.done],
      finish: placementFixture.result_raised,
    }, "sitting");
    await page.getByTestId("placement-skip").click();
    await expect(page.getByTestId("placement-screen")).toHaveAttribute("data-phase", "result");

    const band = page.getByTestId("placement-band");
    await onScreen(page, band);
    await expect(band).toHaveText("B2");
    const raised = page.getByTestId("placement-raised");
    await expect(raised).toHaveText("Up from B1.");
    expect(await contrastOf(raised)).toBeGreaterThanOrEqual(4.5);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "9-result-top");

    const radar = page.getByTestId("placement-radar");
    await onScreen(page, radar);
    const svg = await radar.locator("svg").boundingBox();
    expect(svg && svg.width, "the radar has a real width").toBeGreaterThan(240);
    for (const skill of ["vocabulary", "grammar", "listening", "speaking"]) {
      const row = page.getByTestId(`placement-radar-${skill}`);
      await expectInViewport(page, row);
      expect(await contrastOf(row.locator("dd"))).toBeGreaterThanOrEqual(4.5);
    }
    await expect(page.getByTestId("placement-screen")).not.toContainText(/%|score|correct/i);
    await usable(page, page.getByTestId("placement-back"));
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "10-result-radar");
  });

  test("waiting: the level, and when the next check opens", async ({ page }, info) => {
    await openWith(page, { overview: placementFixture.waiting }, "intro");
    await onScreen(page, page.getByTestId("placement-band"));
    const next = page.getByTestId("placement-next");
    await onScreen(page, next);
    await expect(next).toHaveText("The next check opens on 11 November.");
    expect(await contrastOf(next)).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByTestId("placement-start")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "11-waiting");
  });
});
