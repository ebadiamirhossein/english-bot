import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { fakeYouTube, fixture, mockApi, mockDefine, mockKeepGoing, mockVideo } from "./support/api";
import { expectInViewport, expectNoHorizontalOverflow, expectReachable } from "./support/assertions";

/**
 * **W32c — a word with no entry, looked up while the learner waits**, in a
 * real browser in every project. The one scoped exception to the 2026-08-27
 * ruling (operator ruling Q4): the sheet says *Looking it up…* and fills in; a
 * refusal says *no meaning yet* and still offers Save.
 *
 * The answer here is a fixture body built through the real response model
 * (`DefineWordOut`, `wire_entry`); **no model is reached** — the route is
 * mocked. Screenshots in `e2e/screenshots/W32c/`.
 *
 * **RED BEFORE W32c:** the sheet said *no meaning yet* and asked nothing.
 */

async function shot(page: Page, info: TestInfo, state: string) {
  await page.screenshot({
    path: `e2e/screenshots/W32c/${state}--${info.project.name}.png`,
    fullPage: false,
  });
}

const desktop = (info: TestInfo) => info.project.name.startsWith("desktop");

async function openWatch(page: Page, define: unknown, delayMs = 0) {
  await fakeYouTube(page);
  await mockApi(page);
  await mockKeepGoing(page, { watch: fixture.watch_study });
  await mockVideo(page, { meanings: fixture.watch_meanings });
  const asked = await mockDefine(page, define, delayMs);
  await page.goto("/watch");
  await expect(page.getByTestId("player-mount")).toHaveAttribute("data-player-ready", "true");
  await expect(page.getByTestId("video-player")).toHaveAttribute("data-meanings", "ready");
  return asked;
}

function listWord(page: Page, word: string) {
  return page.getByTestId("line-list").getByRole("button", { name: word, exact: true }).first();
}

test("a miss: Looking it up…, then the meaning, and the next hover is instant", async ({ page }, info) => {
  const asked = await openWatch(page, fixture.word_define_defined, 900);
  const van = listWord(page, "van");
  await van.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await van.click();
  const looking = page.getByTestId("word-sheet-looking");
  await expect(looking).toHaveText("Looking it up…");
  await expectInViewport(page, looking);
  await shot(page, info, "sheet-miss-looking");
  const sense = page.getByTestId("word-sheet-sense");
  await expect(sense).toContainText("a big vehicle for carrying things or people");
  await expect(sense.getByTestId("word-sheet-l1")).toHaveText("ون");
  await expectReachable(page.getByTestId("word-sheet-save"));
  await expectNoHorizontalOverflow(page);
  await shot(page, info, "sheet-miss-filled");
  expect(asked).toEqual([{ word: "van", line: 11 }]);
  await page.getByTestId("word-sheet-close").click();
  if (desktop(info)) {
    await van.hover();
    await expect(page.getByTestId("word-popover")).toContainText("a big vehicle");
    await shot(page, info, "popover-after-miss");
  }
  expect(asked).toHaveLength(1);
});

test("a refused lookup: no meaning yet, and Save is still there", async ({ page }, info) => {
  await openWatch(page, fixture.word_define_refused);
  const van = listWord(page, "van");
  await van.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await van.click();
  await expect(page.getByTestId("word-sheet-no-meaning")).toHaveText(
    "No meaning for this one yet — you can still save it.",
  );
  const save = page.getByTestId("word-sheet-save");
  await expectInViewport(page, save);
  await expectReachable(save);
  await shot(page, info, "sheet-miss-refused");
});
