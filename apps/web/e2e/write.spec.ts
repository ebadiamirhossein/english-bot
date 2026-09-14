import { expect, test } from "@playwright/test";

import { ENTRY, fixture, LONG, mockApi, PARAGRAPH } from "./support/api";
import {
  contrastOf,
  expectDocumentDoesNotScroll,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
} from "./support/assertions";

/**
 * W16a — every state the design draws for the journal, in a real browser, at
 * phone, keyboard-height phone and desktop width, in light and dark (the six
 * projects in `playwright.config.ts`).
 *
 * Each test is written from its frame's own notes: *above the fold*, *primary*,
 * *absent*, and `1j`'s and `1r`'s explicit *assert* lines.
 *
 * **WHAT A GREEN RUN HERE DOES NOT MEAN:** that a correction teaches, that an
 * opening line is true, or that iOS Safari keeps the button above a real
 * keyboard. Those are the operator's phone checks and stay so.
 */

test.describe("1c — block four's card", () => {
  test("both lines and the whole button are on screen once the card is reached", async ({ page }) => {
    await mockApi(page);
    await page.goto("/session");
    const card = page.locator('[data-block-kind="output"]');
    const start = card.getByRole("link", { name: "Start writing" });
    // **Scrolled to the CENTRE, and the reason is recorded.** The first run used
    // `scrollIntoViewIfNeeded`, which stops with the card at the very bottom edge
    // — under the shell's fixed bottom nav — and the reachability check failed
    // at desktop width because the nav covered the button. A learner scrolls a
    // card up into view; `1c`'s note is "when block 4 is scrolled to".
    await start.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, page.getByTestId("output-subline"));
    await expectInViewport(page, start);
    await expectReachable(start);
    await expectTapTarget(start);
    await expectNoHorizontalOverflow(page);
  });
});

test.describe("1d · 1f · 1g · 1h — composing", () => {
  test("1d empty: the task, the field and the whole button, and the page does not scroll", async ({ page }) => {
    await mockApi(page);
    await page.goto("/write");
    await expectInViewport(page, page.getByText("What happened today?"));
    await expectInViewport(page, page.getByTestId("write-length-line"));
    const submit = page.getByTestId("write-submit");
    await expectInViewport(page, submit);
    await expectReachable(submit);
    await expectTapTarget(submit);
    const leave = page.getByTestId("write-leave");
    await expectReachable(leave);
    await expectTapTarget(leave);
    await expectDocumentDoesNotScroll(page);
    await expectNoHorizontalOverflow(page);
  });

  test("1f short text: the button never moves off screen", async ({ page }) => {
    await mockApi(page);
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await expectInViewport(page, page.getByTestId("write-submit"));
    await expectDocumentDoesNotScroll(page);
    await expect(page.locator("body")).not.toContainText(/\d/);
  });

  test("1g long text: the head collapses, only the field scrolls, the button stays (1j)", async ({ page }) => {
    await mockApi(page);
    await page.goto("/write");
    const field = page.getByTestId("write-field");
    await field.fill(LONG);
    await expect(page.getByTestId("write-task-strip")).toBeVisible();
    await expect(page.getByTestId("write-task-head")).toHaveCount(0);
    const submit = page.getByTestId("write-submit");
    await expectInViewport(page, submit);
    await expectReachable(submit);
    await expectDocumentDoesNotScroll(page);
    const scrolls = await field.evaluate((el) => el.scrollHeight > el.clientHeight);
    expect(scrolls, "the field's own content should scroll, not the page").toBe(true);
    await expectNoHorizontalOverflow(page);
  });

  test("1h too short: the refusal, the text and the button, all at once", async ({ page }) => {
    await mockApi(page);
    await page.goto("/write");
    await page.getByTestId("write-field").fill("Tired");
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByTestId("write-notice"));
    await expectInViewport(page, page.getByTestId("write-submit"));
    await expect(page.getByTestId("write-field")).toHaveValue("Tired");
    await expect(page.getByTestId("write-length-line")).toHaveCount(0);
    await expectDocumentDoesNotScroll(page);
  });
});

test.describe("1i — reading", () => {
  test("the label and the start of the text, and no control at all", async ({ page }) => {
    let release!: () => void;
    const hold = new Promise<void>((resolve) => (release = resolve));
    await mockApi(page, { correct: { hold, body: fixture.two } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByTestId("write-reading"));
    await expect(page.getByTestId("write-submit")).toHaveCount(0);
    await expect(page.getByTestId("write-leave")).toHaveCount(0);
    await expect(page.getByTestId("write-field")).toHaveAttribute("readonly", "");
    release();
  });
});

test.describe("1k · 1l · 1m · 1r · 1s — the result", () => {
  test("1k: the opening line and the text lead; Back to today is reachable without scrolling to the end", async ({ page }) => {
    await mockApi(page, { correct: { body: fixture.two } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByTestId("write-opening"));
    const written = await page.getByTestId("write-written").boundingBox();
    expect(written!.y, "the learner's text starts below the fold").toBeLessThan(page.viewportSize()!.height);
    const back = page.getByTestId("write-back");
    await expectInViewport(page, back);
    await expectReachable(back);
    await expectTapTarget(back);
    await expect(page.getByTestId("write-correction")).toHaveCount(2);
    await expectDocumentDoesNotScroll(page);
    await expectNoHorizontalOverflow(page);
  });

  test("1l: one correction and no picked-two line", async ({ page }) => {
    await mockApi(page, { correct: { body: fixture.one } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expect(page.getByTestId("write-correction")).toHaveCount(1);
    await expect(page.getByTestId("write-picked")).toHaveCount(0);
    await expectInViewport(page, page.getByTestId("write-back"));
  });

  test("1m: nothing to fix and nothing to say — no heading, no empty card, no opening line", async ({ page }) => {
    await mockApi(page, { correct: { body: fixture.clean_no_line } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByTestId("write-written"));
    await expect(page.getByTestId("write-corrections")).toHaveCount(0);
    await expect(page.getByTestId("write-opening")).toHaveCount(0);
    await expectReachable(page.getByTestId("write-back"));
  });

  test("1r: every text pair on the result holds 4.5:1 in this theme", async ({ page }) => {
    await mockApi(page, { correct: { body: fixture.two } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expect(page.getByTestId("write-correction")).toHaveCount(2);
    // **The RESTING pair is `1r`'s subject.** On desktop the mouse is still where
    // *Read it over* was clicked, and *Back to today* renders under it — the first
    // W16b run measured its HOVER state (3.96:1 in light) and failed. Hover
    // contrast is filed on its own (#414), not hidden by this move.
    await page.mouse.move(0, 0);
    const pairs: Record<string, import("@playwright/test").Locator> = {
      opening: page.getByTestId("write-opening"),
      written: page.getByTestId("write-written"),
      label: page.getByTestId("write-correction-label").first(),
      said: page.getByTestId("write-correction-said").first(),
      better: page.getByTestId("write-correction-better").first(),
      why: page.getByTestId("write-correction-why").first(),
      back: page.getByTestId("write-back"),
    };
    const failing: string[] = [];
    for (const [name, locator] of Object.entries(pairs)) {
      const ratio = await contrastOf(locator);
      if (ratio < 4.5) failing.push(`${name} ${ratio.toFixed(2)}:1`);
    }
    expect(failing, "text pairs under 4.5:1").toEqual([]);
  });
});

test.describe("1q — failure and the day's ceiling", () => {
  test("failure: the line, the text still editable, and Try again", async ({ page }) => {
    await mockApi(page, { correct: { status: 503 } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(ENTRY);
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByTestId("write-notice"));
    const retry = page.getByRole("button", { name: "Try again" });
    await expectInViewport(page, retry);
    await expectReachable(retry);
    await expect(page.getByTestId("write-field")).toHaveValue(ENTRY);
    await expect(page.getByTestId("write-notice")).not.toContainText(/503|error|sorry/i);
  });

  test("unavailable: the single line, no field and no control", async ({ page }) => {
    await mockApi(page, { today: fixture.today_ceiling });
    await page.goto("/write");
    await expectInViewport(page, page.getByTestId("write-ceiling"));
    await expect(page.getByTestId("write-field")).toHaveCount(0);
    await expect(page.getByTestId("write-screen").getByRole("button")).toHaveCount(0);
    await expect(page.getByTestId("write-screen").getByRole("link")).toHaveCount(0);
    await expect(page.getByTestId("write-ceiling")).not.toContainText(/\d/);
  });
});


/**
 * W16b — the paragraph: `1c`'s Thursday card, `1e`, `1g`'s prompt-card collapse,
 * `1n` and `1o`, across all six projects.
 *
 * **RED DEMONSTRATIONS** (decisions log), each a mutation of `writer.tsx`: the
 * structure block moved below the learner's text (`1n` — **first run STILL GREEN**:
 * the test checked only the fold, so it now also asserts the prose starts above the
 * learner's text, and the same mutation was re-run); `min-h-11` removed from Keep
 * (`1o` tap target); the strip's `setCollapsed(false)` removed (`1g` reopen); the
 * keep sentence colour at 40% (`1r` paragraph contrast); and the head's
 * `min-h-0 shrink … overflow-y-auto` reverted to `shrink-0` (`1e` at keyboard
 * height — the defect this harness found).
 *
 * **NOT MEANT BY A GREEN RUN:** that the structure prose describes this paragraph,
 * or that an offered phrase is worth keeping (HP1, HP2).
 */
test.describe("W16b — the paragraph", () => {
  test("1c: Thursday's card and its button are on screen once reached", async ({ page }) => {
    await mockApi(page, { session: fixture.session_paragraph });
    await page.goto("/session");
    const card = page.locator('[data-block-kind="output"]');
    const start = card.getByRole("link", { name: "Start writing" });
    await start.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect(card).toContainText("this week’s paragraph");
    await expectInViewport(page, start);
    await expectReachable(start);
    await expectTapTarget(start);
    await expectNoHorizontalOverflow(page);
  });

  test("1e: the prompt card, the field and the whole button; the page does not scroll", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph });
    await page.goto("/write");
    await expectInViewport(page, page.getByTestId("write-prompt"));
    const submit = page.getByTestId("write-submit");
    await expectInViewport(page, submit);
    await expectReachable(submit);
    await expectTapTarget(submit);
    await expectTapTarget(page.getByTestId("write-leave"));
    await expectDocumentDoesNotScroll(page);
    await expectNoHorizontalOverflow(page);
    await expect(page.getByTestId("write-screen")).not.toContainText(/\d/);
  });

  test("1g: a long paragraph collapses the prompt card to a strip that taps to reopen", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(LONG);
    const strip = page.getByTestId("write-task-strip");
    await expect(strip).toBeVisible();
    await expect(page.getByTestId("write-prompt-card")).toHaveCount(0);
    await expectReachable(strip);
    await expectTapTarget(strip);
    await expectInViewport(page, page.getByTestId("write-submit"));
    await expectDocumentDoesNotScroll(page);
    await strip.click();
    await expect(page.getByTestId("write-prompt-card")).toBeVisible();
    await expectInViewport(page, page.getByTestId("write-submit"));
    await expectReachable(page.getByTestId("write-submit"));
    await expectDocumentDoesNotScroll(page);
  });

  test("1n: structure leads — its heading and first sentence above the fold; Back reachable", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph, correct: { body: fixture.paragraph } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(PARAGRAPH);
    await page.getByTestId("write-submit").click();
    await expectInViewport(page, page.getByText("How it’s put together"));
    const first = await page.getByTestId("write-structure-paragraph").first().boundingBox();
    expect(first!.y, "the structure prose starts below the fold").toBeLessThan(page.viewportSize()!.height);
    // **Leads, on screen — not merely above the fold.** The first version checked
    // only the fold, and moving the whole block below the learner's text left it
    // green on a 768-tall phone (red demonstration PB1, found by running it).
    const written = await page.getByTestId("write-written").boundingBox();
    expect(first!.y, "the structure prose does not lead the learner's text").toBeLessThan(written!.y);
    const back = page.getByTestId("write-back");
    await expectInViewport(page, back);
    await expectReachable(back);
    await expectTapTarget(back);
    await expect(page.getByTestId("write-result")).not.toContainText(/more below|\d/i);
    await expectDocumentDoesNotScroll(page);
    await expectNoHorizontalOverflow(page);
  });

  test("1o: a Keep row is reachable once scrolled to, 44 tall, and flips to In your deck", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph, correct: { body: fixture.paragraph } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(PARAGRAPH);
    await page.getByTestId("write-submit").click();
    const keep = page.getByTestId("write-keep-button");
    await expect(keep).toHaveCount(1);
    await keep.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expectInViewport(page, keep);
    await expectReachable(keep);
    await expectTapTarget(keep);
    await keep.click();
    await expect(page.getByTestId("write-keep-in-deck")).toHaveCount(2);
    await expect(page.getByTestId("write-keep-button")).toHaveCount(0);
    await expectDocumentDoesNotScroll(page);
    await expectNoHorizontalOverflow(page);
  });

  test("1o absent: nothing to keep and no structure — no heading, no empty row", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph, correct: { body: fixture.paragraph_bare } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(PARAGRAPH);
    await page.getByTestId("write-submit").click();
    await expect(page.getByTestId("write-correction").first()).toBeVisible();
    await expect(page.getByTestId("write-keep")).toHaveCount(0);
    await expect(page.getByTestId("write-structure")).toHaveCount(0);
    await expectReachable(page.getByTestId("write-back"));
  });

  test("1r: the paragraph's text pairs hold 4.5:1 in this theme", async ({ page }) => {
    await mockApi(page, { today: fixture.today_paragraph, correct: { body: fixture.paragraph } });
    await page.goto("/write");
    await page.getByTestId("write-field").fill(PARAGRAPH);
    await page.getByTestId("write-submit").click();
    await expect(page.getByTestId("write-keep-row")).toHaveCount(2);
    await page.mouse.move(0, 0);
    const pairs: Record<string, import("@playwright/test").Locator> = {
      structure: page.getByTestId("write-structure-paragraph").first(),
      quote: page.getByTestId("write-structure-quote").first(),
      phrase: page.getByTestId("write-keep-phrase").first(),
      sentence: page.getByTestId("write-keep-sentence").first(),
      keep: page.getByTestId("write-keep-button"),
      inDeck: page.getByTestId("write-keep-in-deck").first(),
    };
    const failing: string[] = [];
    for (const [name, locator] of Object.entries(pairs)) {
      const ratio = await contrastOf(locator);
      if (ratio < 4.5) failing.push(`${name} ${ratio.toFixed(2)}:1`);
    }
    expect(failing, "text pairs under 4.5:1").toEqual([]);
  });
});
