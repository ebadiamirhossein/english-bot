import { expect, type Locator, type Page } from "@playwright/test";

/**
 * The five assertion classes CLAUDE.md §3a owes every drawn state.
 *
 * **Each was demonstrated red against a deliberate mutation** before it was
 * accepted (decisions log, W16a): `[contain:size]` removed from the `/write`
 * page wrapper (in-viewport: *"ends below the fold"*); `pointer-events-none` on
 * *Back to today* (reachable: *"something covers the control's centre"*);
 * `min-h-11` removed from the leave pill (tap target); the caution eyebrow's
 * colour at 40% (contrast); and an absolutely positioned 600px element on the
 * page (horizontal overflow: *"the page scrolls horizontally"*).
 *
 * **Two corrections to the first draft of this note, recorded rather than
 * hidden.** It claimed a `min-h-0` "clipping" check that was never built, and
 * its first overflow mutation wrote invalid JSX, so the build failed and nothing
 * was demonstrated; the second widened the page wrapper and was caught by the
 * in-viewport check before the overflow check ran. **Inside `/write` no child
 * can overflow horizontally at all** — the `[contain:size]` wrapper clips — so
 * this assertion guards the page and the shell, not the writer's children.
 */

/** The element's box lies wholly inside the viewport — not merely in the DOM. */
export async function expectInViewport(page: Page, locator: Locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  const vp = page.viewportSize();
  expect(box, "the element has no layout box").not.toBeNull();
  expect(vp).not.toBeNull();
  const slack = 0.5;
  expect(box!.x, "starts left of the viewport").toBeGreaterThanOrEqual(-slack);
  expect(box!.y, "starts above the viewport").toBeGreaterThanOrEqual(-slack);
  expect(box!.x + box!.width, "ends right of the viewport").toBeLessThanOrEqual(vp!.width + slack);
  expect(box!.y + box!.height, "ends below the fold").toBeLessThanOrEqual(vp!.height + slack);
}

/** The page never scrolls sideways. */
export async function expectNoHorizontalOverflow(page: Page) {
  const [scroll, client] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scroll, "the page scrolls horizontally").toBeLessThanOrEqual(client);
}

/** `1g`: the page itself never scrolls; only a region's own content does. */
export async function expectDocumentDoesNotScroll(page: Page) {
  const [scroll, client] = await page.evaluate(() => [
    document.documentElement.scrollHeight,
    document.documentElement.clientHeight,
  ]);
  expect(scroll, "the document scrolls — something outgrew the column").toBeLessThanOrEqual(client + 1);
}

/** Visible, enabled, not covered by anything, and a tap reaches it. */
export async function expectReachable(locator: Locator) {
  await expect(locator).toBeVisible();
  await expect(locator).toBeEnabled();
  const hit = await locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!top && (top === el || el.contains(top));
  });
  expect(hit, "something covers the control's centre").toBe(true);
  await locator.click({ trial: true });
}

/** Design `1v`: every control at least 44 tall. */
export async function expectTapTarget(locator: Locator, min = 44) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height, "the control is shorter than a thumb").toBeGreaterThanOrEqual(min);
}

/**
 * `1r`'s assert: text against what is actually painted behind it, ≥ 4.5:1.
 *
 * Colours are read through a 1×1 canvas so `oklch()` tokens resolve to sRGB the
 * way the browser paints them; translucent backgrounds are composited up the
 * ancestor chain rather than assumed opaque.
 */
export async function contrastOf(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    const rgba = (color: string) => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "rgba(0,0,0,0)";
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0], d[1], d[2], d[3] / 255];
    };
    const over = (top: number[], under: number[]) => {
      const a = top[3] + under[3] * (1 - top[3]);
      if (a === 0) return [0, 0, 0, 0];
      return [0, 1, 2].map((i) => (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a).concat(a);
    };
    const layers: number[][] = [];
    for (let node: Element | null = el; node; node = node.parentElement) {
      const bg = rgba(getComputedStyle(node).backgroundColor);
      if (bg[3] > 0) layers.push(bg);
      if (bg[3] >= 0.999) break;
    }
    let bg = rgba(getComputedStyle(document.documentElement).backgroundColor);
    if (bg[3] < 0.999) bg = over(bg, [255, 255, 255, 1]);
    for (const layer of layers.reverse()) bg = over(layer, bg);
    let fg = rgba(getComputedStyle(el).color);
    const opacity = Number(getComputedStyle(el).opacity);
    fg = over([fg[0], fg[1], fg[2], fg[3] * opacity], bg);
    const lum = (c: number[]) => {
      const [r, g, b] = c.slice(0, 3).map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
    return (hi + 0.05) / (lo + 0.05);
  });
}

/**
 * **#441's assert: one painted surface against another, ≥ 3:1 for a control's
 * state (WCAG 1.4.11, non-text contrast).** `contrastOf` measures TEXT against
 * what is behind it; a switch's state is carried by its thumb against its track,
 * and no text is involved, so the text check could never see the OFF state go
 * dark-on-dark. Each element's background is composited up its own ancestor
 * chain through the same 1×1 canvas, so `oklch()` tokens resolve as painted.
 */
export async function surfaceContrast(a: Locator, b: Locator): Promise<number> {
  const other = await b.elementHandle();
  return a.evaluate((el, otherEl) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    const rgba = (color: string) => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "rgba(0,0,0,0)";
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0], d[1], d[2], d[3] / 255];
    };
    const over = (top: number[], under: number[]) => {
      const a = top[3] + under[3] * (1 - top[3]);
      if (a === 0) return [0, 0, 0, 0];
      return [0, 1, 2].map((i) => (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a).concat(a);
    };
    const painted = (start: Element) => {
      const layers: number[][] = [];
      for (let node: Element | null = start; node; node = node.parentElement) {
        const bg = rgba(getComputedStyle(node).backgroundColor);
        if (bg[3] > 0) layers.push(bg);
        if (bg[3] >= 0.999) break;
      }
      let bg = rgba(getComputedStyle(document.documentElement).backgroundColor);
      if (bg[3] < 0.999) bg = over(bg, [255, 255, 255, 1]);
      for (const layer of layers.reverse()) bg = over(layer, bg);
      return bg;
    };
    const lum = (c: number[]) => {
      const [r, g, b] = c.slice(0, 3).map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const [hi, lo] = [lum(painted(el)), lum(painted(otherEl as Element))].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }, other);
}
