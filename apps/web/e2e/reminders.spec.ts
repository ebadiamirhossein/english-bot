import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import { mockApi, mockProgress, mockPush, pushFixture, type CorrectReply } from "./support/api";
import {
  contrastOf,
  expectInViewport,
  expectNoHorizontalOverflow,
  expectReachable,
  expectTapTarget,
  surfaceContrast,
} from "./support/assertions";
import { stubPushBrowser, type PushBrowser } from "./support/push-browser";

/**
 * W20 — the daily-reminder control in the settings menu, in a real browser, in
 * every project (phone, keyboard-height phone and desktop; light and dark).
 *
 * **§1a is suspended for this run (ruling 0.3)**, so there is no design frame
 * to test against. Every state asserted here is screenshotted into
 * `e2e/screenshots/W20/`, which is how the operator reviews it at the launch
 * pass.
 *
 * **The browser's push machinery is a stub** (`support/push-browser.ts`) and the
 * API is the fixture's (`support/api.ts`). **WHAT A GREEN RUN HERE DOES NOT
 * MEAN:** that a phone grants permission, that a push arrives at the learner's
 * practice time, that a tap on it opens the session, or that the words read as
 * an offer rather than a demand. Those are the operator's phone check and the
 * launch pass's reading check.
 *
 * **The endpoint's route is asserted, not assumed:** every `/push/*` call the
 * page made is recorded, and none carries the endpoint in its URL.
 *
 * **RED DEMONSTRATIONS (2026-09-25), each one edit, run on `phone-light`, and
 * restored:** the switch's `min-h-11` removed (*"the control is shorter than a
 * thumb"*); the switch given `pointer-events-none` (*"something covers the
 * control's centre"*); the section given `w-[420px]` (caught by the in-viewport
 * check first — *"ends right of the viewport"* — before the overflow check ran,
 * W16a's pattern); `if (!key)` in `reminders.tsx` made to invent a key (the
 * no-key test found the section drawn). **`expectUncovered` went red against a
 * real defect, not a mutation:** on its first run both keyboard-height projects
 * reported the trouble and closed-prompt lines under the bottom nav (*"(258,
 * 420) is under SPAN"*), because the menu and the nav were both `z-50` and the
 * nav comes later in the document. `app-menu.tsx`'s menu is now `z-[60]`. Its
 * own first draft checked corners and reported every caution line as covered by
 * its own section — hit testing honours `border-radius` — so it checks edge
 * midpoints.
 *
 * **#441 (build run 2, 2026-09-25): `theStateIsLegible` went red BEFORE the
 * fix, on the code as shipped** — the OFF thumb against its track read
 * **1.27:1 in every dark project**, and the light OFF state failed too; the ON
 * state passed. The thumb is now `bg-muted-foreground` when off, and all 42
 * pass. Text contrast (`contrastOf`) could never see this: the switch carries
 * its state in two painted surfaces and no text.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W20/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

async function openMenu(
  page: Page,
  browser: PushBrowser,
  push: Parameters<typeof mockPush>[1] = {},
) {
  await stubPushBrowser(page, browser);
  await mockApi(page);
  await mockProgress(page);
  const calls = await mockPush(page, push);
  await page.goto("/progress");
  await expect(page.getByTestId("progress-screen")).toHaveAttribute("data-phase", "ready");
  const settings = page.getByRole("button", { name: "Settings" });
  await settings.click();
  await expect(page.getByRole("menu")).toBeVisible();
  return calls;
}

async function section(page: Page, phase: string) {
  const reminders = page.getByTestId("reminders");
  await expect(reminders).toHaveAttribute("data-phase", phase);
  await expectInViewport(page, reminders);
  await expectUncovered(reminders);
  await expectNoHorizontalOverflow(page);
  return reminders;
}

/** The switch: in view, reachable, tall enough for a thumb. */
async function theSwitchIsUsable(page: Page, toggle: Locator) {
  await expectInViewport(page, toggle);
  await expectReachable(toggle);
  await expectTapTarget(toggle);
  await theStateIsLegible(page);
}

/**
 * **#441: the thumb against its track, ≥ 3:1, in every state and theme.** The
 * switch says ON or OFF with no text, so the only thing that tells a learner
 * which it is is the thumb against the track (WCAG 1.4.11). Filed from the dark
 * OFF screenshot, where the thumb was darker than the track at about 1.3:1.
 */
async function theStateIsLegible(page: Page) {
  const ratio = await surfaceContrast(
    page.getByTestId("reminders-thumb"),
    page.getByTestId("reminders-switch"),
  );
  expect(ratio, "the switch's thumb against its track").toBeGreaterThanOrEqual(3);
}

/**
 * **Not covered by anything painted above it** — the fixed bottom nav, most
 * likely. `expectInViewport` reads the box and cannot see a sibling on top of
 * it; `expectReachable` checks one point and is for controls. This checks the
 * centre and the middle of each edge, three pixels in.
 *
 * **Edges, not corners, and the first draft is why:** hit testing honours
 * `border-radius`, so a point in the rounded corner of a caution line lands on
 * the section behind it. The corner version reported both caution lines as
 * covered — by their own section — in every project, desktop included.
 */
async function expectUncovered(locator: Locator) {
  const covered = await locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const points: [number, number][] = [
      [cx, cy],
      [cx, r.top + 3],
      [cx, r.bottom - 3],
      [r.left + 3, cy],
      [r.right - 3, cy],
    ];
    return points
      .filter(([x, y]) => {
        const top = document.elementFromPoint(x, y);
        return !top || !(top === el || el.contains(top));
      })
      .map(([x, y]) => `(${Math.round(x)}, ${Math.round(y)}) is under ${document.elementFromPoint(x, y)?.tagName ?? "nothing"}`);
  });
  expect(covered, "something is painted over part of this").toEqual([]);
}

async function readable(locator: Locator) {
  await expectUncovered(locator);
  expect(await contrastOf(locator), "text against what is painted behind it").toBeGreaterThanOrEqual(4.5);
}

const toggleOf = (page: Page) => page.getByRole("menuitemcheckbox", { name: /^Daily reminder/ });

test.describe("W20 — the reminder control", () => {
  test("off: the switch is on screen, and a tap turns reminders on", async ({ page }, info) => {
    let release!: () => void;
    const hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    const calls = await openMenu(page, {}, { subscribe: { hold, body: pushFixture.on } as CorrectReply });
    await section(page, "off");
    const toggle = toggleOf(page);
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await theSwitchIsUsable(page, toggle);
    await readable(page.getByTestId("reminders-about"));
    await expect(page.getByTestId("reminders")).not.toContainText(/\d/);
    await shot(page, info, "1-off");

    await toggle.click();
    await expect(page.getByTestId("reminders-working")).toBeVisible();
    await expect(toggle).toBeDisabled();
    await expectInViewport(page, toggle);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "2-working");

    release();
    await section(page, "on");
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await theSwitchIsUsable(page, toggle);
    await shot(page, info, "3-turned-on");

    // The subscription went up as the browser handed it over, in the body only.
    const options = await page.evaluate(() => (window as unknown as Record<string, unknown>).__pushSubscribeOptions);
    expect(options).toEqual({ userVisibleOnly: true, applicationServerKey: pushFixture.key_set.public_key });
    const up = calls.filter((c) => c.url.endsWith("/push/subscribe"));
    expect(up).toHaveLength(1);
    expect(up[0].body).toEqual(pushFixture.subscription);
    for (const call of calls) expect(call.url).not.toContain("example.invalid");
  });

  test("on: the switch says so, and a tap turns reminders off", async ({ page }, info) => {
    const calls = await openMenu(page, { permission: "granted", subscribed: true }, { on: true });
    await section(page, "on");
    const toggle = toggleOf(page);
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await theSwitchIsUsable(page, toggle);
    await readable(page.getByTestId("reminders-about"));
    await shot(page, info, "4-on");

    await toggle.click();
    await section(page, "off");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await shot(page, info, "5-turned-off");
    const down = calls.filter((c) => c.url.endsWith("/push/unsubscribe"));
    expect(down).toHaveLength(1);
    expect(down[0].body).toEqual({ endpoint: pushFixture.subscription.endpoint });
    for (const call of calls) expect(call.url).not.toContain("example.invalid");
  });

  test("blocked in the browser: one calm line, and no switch", async ({ page }, info) => {
    await openMenu(page, { permission: "denied" });
    await section(page, "blocked");
    const line = page.getByTestId("reminders-blocked");
    await expectInViewport(page, line);
    await readable(line);
    await expect(toggleOf(page)).toHaveCount(0);
    await shot(page, info, "6-blocked");
  });

  test("iPhone Safari in a tab: says to add the app to the Home Screen", async ({ page }, info) => {
    await openMenu(page, { push: false, iphone: true });
    await section(page, "install");
    const line = page.getByTestId("reminders-install");
    await expectInViewport(page, line);
    await readable(line);
    await expect(toggleOf(page)).toHaveCount(0);
    await shot(page, info, "7-install");
  });

  test("trouble on the way: says so, and the switch still works", async ({ page }, info) => {
    await openMenu(page, {}, { subscribe: { status: 500 } });
    await section(page, "off");
    const toggle = toggleOf(page);
    await toggle.click();
    const line = page.getByTestId("reminders-trouble");
    await expectInViewport(page, line);
    await readable(line);
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await theSwitchIsUsable(page, toggle);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "8-trouble");
  });

  test("a closed prompt: nothing changes, and it says so", async ({ page }, info) => {
    await openMenu(page, { answer: "default" });
    await section(page, "off");
    const toggle = toggleOf(page);
    await toggle.click();
    const line = page.getByTestId("reminders-closed");
    await expectInViewport(page, line);
    await readable(line);
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await theSwitchIsUsable(page, toggle);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "9-prompt-closed");
  });

  test("no key on the server: the menu draws no reminders at all", async ({ page }, info) => {
    const calls = await openMenu(page, {}, { key: pushFixture.key_unset });
    // Positive control: the menu itself is drawn, around where the section would be.
    const menu = page.getByRole("menu");
    await expect(menu.getByText("Appearance")).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Add this device" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("reminders")).toHaveCount(0);
    await expect(menu).not.toContainText("Reminders");
    expect(calls.filter((c) => !c.url.endsWith("/push/key"))).toEqual([]);
    await expectNoHorizontalOverflow(page);
    await shot(page, info, "10-not-drawn");
  });
});
