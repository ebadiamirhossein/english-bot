/**
 * W13b/3 §B and §C — the chat surface, and the microphone that was never wired.
 *
 * **EVERY ASSERTION HERE CORRESPONDS TO A DEFECT THE OPERATOR HIT IN A REAL
 * SESSION**, not to a design preference. The turn loop underneath was working
 * the whole time: the surface being unusable was a UI finding (§D).
 *
 * **THE AUDIO MOCK IS `audio-mocks.ts`, IMPORTED AND NOT REWRITTEN.** Its own
 * header records why: when `recorder.test.tsx` added `createAnalyser` and
 * `shadow.test.tsx` kept an older copy, five tests failed for a reason that had
 * nothing to do with what they assert — **#190's shape arriving in the test
 * suite.** A second divergent mock is the thing that row exists to prevent.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Conversation } from "./conversation";
import { CONVERSATION } from "./copy";
import { mockAudio, polyfillBlobArrayBuffer } from "./audio-mocks";

polyfillBlobArrayBuffer();

function jsonOnce(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as unknown as Response;
}

/** Opens a conversation: topics -> pick -> first app turn on screen. */
async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
  await screen.findByTestId("conversation-topics");
  await user.click(screen.getByRole("button", { name: "Weekend plans" }));
  await screen.findByTestId("conversation-log");
}

describe("the chat surface", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics")) {
          return jsonOnce({ topics: ["Weekend plans"], voice: true });
        }
        if (String(url).endsWith("/open")) {
          return jsonOnce({
            conversation_id: 1,
            topic_label: "Weekend plans",
            reply: "Hey — what did you get up to?",
            state: "open",
          });
        }
        if (String(url).endsWith("/turn")) {
          return jsonOnce({
            conversation_id: 1,
            topic_label: "Weekend plans",
            reply: "Nice. Was it busy?",
            state: "open",
          });
        }
        return jsonOnce({});
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("marks who said what with something other than colour", async () => {
    // **THE DEFECT, STATED AS ONE: every message was the same colour and the
    // same alignment and a learner could not tell who said what.**
    //
    // Asserted on `data-speaker` rather than on a class, because a test that
    // pins `bg-muted` asserts Tailwind and would pass on a palette where both
    // speakers happen to look identical — which is exactly what shipped.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);

    await user.type(screen.getByTestId("conversation-composer"), "I went out");
    await user.click(screen.getByRole("button", { name: CONVERSATION.send }));

    await screen.findByText("Nice. Was it busy?");
    const log = screen.getByTestId("conversation-log");
    const speakers = Array.from(
      log.querySelectorAll("[data-speaker]"),
      (n) => n.getAttribute("data-speaker"),
    );
    expect(speakers).toContain("you");
    expect(speakers).toContain("app");
    expect(new Set(speakers).size).toBeGreaterThan(1);
  });

  it("gives the message list its own scroll region, so the page does not scroll", async () => {
    // **`min-h-0` IS THE WHOLE FIX AND IT IS WHY THIS IS ASSERTED.** Without it
    // the list grows to its content and the *page* scrolls underneath — which
    // is what happened when the chat was crammed into a card in block 4.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);
    const log = screen.getByTestId("conversation-log");
    expect(log.className).toContain("overflow-y-auto");
    expect(log.className).toContain("min-h-0");
    expect(log.className).toContain("flex-1");
  });

  it("keeps a long message in the composer instead of scrolling it out", async () => {
    // The operator's sentence scrolled out of a single-line input mid-thought.
    // A textarea that grows and then scrolls INTERNALLY keeps the text and the
    // send control both on screen.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);
    const box = screen.getByTestId("conversation-composer") as HTMLTextAreaElement;
    //
    // **W13b/4 RESIZED IT TO THE DESIGN'S MEASUREMENT: four lines open, about
    // seven before it scrolls.** The previous contract, quoted rather than
    // deleted (#82's shape): `min-h-[2.75rem]` (one row) and `max-h-32`. The
    // reason is the design's and it is about what people write rather than
    // what fits: a one-row box asks for a one-row answer.
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.className).toContain("min-h-24");
    expect(box.className).toContain("max-h-44");
    expect(box.className).toContain("overflow-y-auto");

    const long = "I went to the lake with my friends and we ".repeat(4);
    await user.type(box, long);
    expect(box.value).toBe(long);
  });

  it("sends on Enter and makes a newline on Shift+Enter", async () => {
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);
    const box = screen.getByTestId("conversation-composer") as HTMLTextAreaElement;

    await user.type(box, "one{Shift>}{Enter}{/Shift}two");
    expect(box.value).toBe("one\ntwo");

    await user.type(box, "{Enter}");
    await screen.findByText("Nice. Was it busy?");
    expect(box.value).toBe("");
  });

  it("shows it is working, without a spinner or a progress bar", async () => {
    // **The wait is the product** — so the surface says it is working and
    // never how long is left. `progressbar` is the role a bar would take.
    //
    // **THE RESPONSE IS HELD OPEN DELIBERATELY.** The first draft let the mock
    // resolve immediately, `busy` flipped back before the assertion, and the
    // test failed against a working implementation — an in-progress state is
    // only observable while something is in progress, and a 2–4 second wait is
    // what this surface actually has.
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics")) {
          await held;
          return jsonOnce({ topics: ["Weekend plans"], voice: true });
        }
        return jsonOnce({});
      }),
    );
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
    expect(await screen.findByText(CONVERSATION.working)).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
    release();
  });

  it("keeps the topic and the end control out of the scroll region", async () => {
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);
    const log = screen.getByTestId("conversation-log");
    expect(log.contains(screen.getByTestId("conversation-topic"))).toBe(false);
    expect(log.contains(screen.getByTestId("conversation-end"))).toBe(false);
  });

  it("shows no number anywhere on the surface", async () => {
    // #160's actual rule, and #348's lesson: *"0 of 5 active days."* passed a
    // banned-word scan for a year. The elapsed counter is excluded because it
    // only exists while recording and is a clock, not a tally.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await open(user);
    expect(screen.getByTestId("conversation").textContent ?? "").not.toMatch(/\d/);
  });
});

describe("§C — the microphone", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("records and posts the turn — the control that used to do nothing", async () => {
    // **#386 / #353's shape: a control that renders and silently does nothing,
    // shipped twice.** This asserts the request actually leaves.
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(String(url));
        if (String(url).endsWith("/topics"))
          return jsonOnce({ topics: ["Weekend plans"], voice: true });
        if (String(url).endsWith("/open"))
          return jsonOnce({
            conversation_id: 1,
            topic_label: "Weekend plans",
            reply: "Hey.",
            state: "open",
          });
        return jsonOnce({
          conversation_id: 1,
          topic_label: "Weekend plans",
          reply: "Got it.",
          state: "open",
        });
      }),
    );
    const user = userEvent.setup();
    render(<Conversation />);
    await open(user);

    await user.click(screen.getByTestId("conversation-speak"));
    await screen.findByTestId("conversation-recording");
    await user.click(screen.getByRole("button", { name: CONVERSATION.micStop }));

    await waitFor(() =>
      expect(calls.some((c) => c.endsWith("/conversation/turn/voice"))).toBe(true),
    );
    expect(await screen.findByText("Got it.")).toBeTruthy();
  });

  it("renders no voice control at all for a learner who is not on the allowlist", async () => {
    // **ABSENT, NOT DISABLED (#364).** A greyed-out button announces a feature
    // she is excluded from; the route answers 404 for the same reason.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics"))
          return jsonOnce({ topics: ["Weekend plans"], voice: false });
        return jsonOnce({
          conversation_id: 1,
          topic_label: "Weekend plans",
          reply: "Hey.",
          state: "open",
        });
      }),
    );
    const user = userEvent.setup();
    render(<Conversation />);
    await open(user);
    expect(screen.queryByTestId("conversation-speak")).toBeNull();
  });
});

/**
 * W13b/3b — **THE COMPOSER SHIPPED BELOW THE FOLD AND NINE GREEN TESTS DID NOT
 * SEE IT. THIS BLOCK IS WHAT THEY WERE MISSING, AND ONE OF THE TWO IS HONEST
 * ABOUT NOT CATCHING IT.**
 *
 * **WHAT THE NINE ABOVE ASSERT INSTEAD, STATED PLAINLY:**
 *
 * * **Every one of them mounts `<Conversation …/>` directly and none mounts the
 *   PAGE.** So nothing exercised how `/talk` actually assembles the surface.
 * * **None of them passes `fullHeight`** — the prop `/talk` always passes. The
 *   `shell` branch the app runs had **zero coverage**, and the branch every
 *   test ran is the block-4 one, which **no longer exists in the app at all**
 *   since block 4 stopped rendering the chat. **That is #345's family at the
 *   component level: a test constructing a state the app cannot reach**, and it
 *   is the second time in this slice a green suite sat over a dead surface
 *   (#389 was the first — 21 tests, all on one side of the service).
 * * The *own scroll region* test asserts **class substrings on the log**
 *   (`overflow-y-auto`, `min-h-0`, `flex-1`). All three were true. It is a
 *   claim about the log and says nothing about the box the log sits in.
 * * **jsdom HAS NO LAYOUT ENGINE.** `getBoundingClientRect` is zeros; nothing
 *   is ever off-screen. **"Below the fold" is structurally invisible here.**
 *
 * **SO THE PRESENCE TEST BELOW WOULD NOT HAVE FAILED ON THIS BUG, AND SAYING SO
 * IS THE POINT.** The composer was in the DOM the whole time — in the tests and
 * in production. It closes a real class of defect (a composer gated on state
 * the page never sets, which was the first hypothesis and was false) and it is
 * not the one that shipped.
 *
 * **THE SECOND TEST IS THE ONE THAT WOULD HAVE FAILED.** The defect is a height
 * contract, so it is asserted as a height contract.
 */

describe("what /talk actually mounts", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics"))
          return jsonOnce({ topics: ["Weekend plans"], voice: true });
        if (String(url).endsWith("/open"))
          return jsonOnce({
            conversation_id: 1,
            topic_label: "Weekend plans",
            reply: "Hey — what did you get up to?",
            state: "open",
          });
        return jsonOnce({});
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders an enabled composer with the props the page really passes", async () => {
    // **`voice fullHeight` — WHAT `/talk` PASSES.** Every earlier test passed
    // `voice={false}` or nothing and none passed `fullHeight`, so the shell
    // branch the app runs was never rendered by the suite.
    //
    // **THIS WOULD NOT HAVE CAUGHT THE BUG THAT SHIPPED** — the composer was
    // present then too. It catches the composer being conditional on state the
    // page never sets, which is a different defect and a real one.
    const user = userEvent.setup();
    render(<Conversation voice fullHeight />);
    await open(user);

    const box = screen.getByTestId("conversation-composer") as HTMLTextAreaElement;
    expect(box).toBeTruthy();
    expect(box.disabled).toBe(false);
    expect(screen.getByRole("button", { name: CONVERSATION.send })).toBeTruthy();
    expect(screen.getByTestId("conversation-speak")).toBeTruthy();
  });

  it("does not size /talk to the viewport, because it does not start at the top of one", async () => {
    // **THIS IS THE ASSERTION THAT WOULD HAVE FAILED.**
    //
    // `/talk` is nested in `AppLayout`: an `AppMenu` row above it, `main`'s
    // `pt-4` above that, and `pb-32` below to clear the fixed `BottomNav`. **A
    // `100dvh` box starting ~4rem down ends ~4rem below the fold**, and the
    // composer is its last flex child — which is precisely what shipped.
    //
    // **ASSERTED ON THE SOURCE RATHER THAN ON GEOMETRY, AND THAT IS FORCED
    // RATHER THAN CHOSEN:** jsdom has no layout engine, so no rendering test in
    // this suite can see an element pushed off-screen. The height contract is
    // the thing that can be checked, so the height contract is what is checked.
    const source = await import("node:fs").then((fs) =>
      fs.readFileSync("app/(app)/talk/page.tsx", "utf8"),
    );
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/^\s*\/\/.*$/gm, " ");
    for (const unit of ["100dvh", "100vh", "h-screen", "min-h-screen"]) {
      expect(code).not.toContain(unit);
    }
    expect(code).toContain("h-full");
  });
});

/**
 * W13b/4 — the composer split.
 *
 * **THE CLOSE-OUT'S OWN TESTS MOVED TO `close-out.test.tsx`** when it became a
 * component. They are not deleted and not duplicated: the surface has one home
 * and one test file, which is the arrangement that stopped `did_well` being
 * invisible.
 */
describe("the composer while a reply is coming", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics"))
          return jsonOnce({ topics: ["Weekend plans"], voice: false });
        if (String(url).endsWith("/open"))
          return jsonOnce({
            conversation_id: 1,
            topic_label: "Weekend plans",
            reply: "Hey — what did you get up to?",
            state: "open",
          });
        // **Never resolves.** The turn is left in flight on purpose: that is
        // the state both assertions below are about, and a resolved promise
        // would test the surface after the wait rather than during it.
        if (String(url).endsWith("/turn")) return new Promise<Response>(() => {});
        return jsonOnce({});
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the textarea live so a learner can write during the wait", async () => {
    // **THE DEFECT THIS CHANGES: both controls went dead for 2–4 seconds**, so
    // the sentence someone was forming had nowhere to go. The design's ruling
    // is that the wait is the learner's thinking time.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
    await screen.findByTestId("conversation-topics");
    await user.click(screen.getByRole("button", { name: "Weekend plans" }));
    await screen.findByTestId("conversation-log");

    const composer = screen.getByTestId("conversation-composer");
    await user.type(composer, "I went out");
    await user.click(screen.getByRole("button", { name: CONVERSATION.send }));

    await screen.findByTestId("conversation-working");
    expect(composer).not.toBeDisabled();
    await user.type(composer, "and then");
    expect(composer).toHaveValue("and then");
  });

  it("holds Send, and holds Enter with it, so no second turn goes out in flight", async () => {
    // **ONE RULE, TWO PATHS.** A disabled button with a live Enter key puts the
    // in-flight turn one keystroke away, and the JSX would not show it.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
    await screen.findByTestId("conversation-topics");
    await user.click(screen.getByRole("button", { name: "Weekend plans" }));
    await screen.findByTestId("conversation-log");

    const composer = screen.getByTestId("conversation-composer");
    await user.type(composer, "I went out");
    await user.click(screen.getByRole("button", { name: CONVERSATION.send }));
    await screen.findByTestId("conversation-working");

    expect(screen.getByRole("button", { name: CONVERSATION.send })).toBeDisabled();

    // The learner's own turn, plus the app's opener. Enter must not add a third.
    const before = screen.getByTestId("conversation-log").querySelectorAll(
      "[data-speaker]",
    ).length;
    await user.type(composer, "second try{Enter}");
    expect(
      screen.getByTestId("conversation-log").querySelectorAll("[data-speaker]")
        .length,
    ).toBe(before);
  });
});

/**
 * W13b/5 — `/talk` brought to the design.
 *
 * **EVERY ASSERTION HERE CORRESPONDS TO A DIFFERENCE THE OPERATOR FOUND BY
 * COMPARING THE DEPLOYED SCREEN WITH THE DESIGN, AND NOT ONE OF THEM WAS
 * VISIBLE TO THIS SUITE BEFOREHAND.** W13b/5's changes are large enough to
 * rewrite the header, the turns, the composer and the chooser, and the 223
 * tests that existed passed over all of it unchanged. **A suite that cannot see
 * a screen being wrong is the condition these tests exist to end**, and it is
 * the same finding as `did_well` one slice earlier: nobody looked.
 */
describe("/talk, brought to the design", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/topics"))
          return jsonOnce({
            topics: [
              "A wedding you went to recently",
              "Something you cooked this week",
              "A place you keep meaning to visit",
            ],
            voice: true,
          });
        if (String(url).endsWith("/open"))
          return jsonOnce({
            conversation_id: 1,
            topic_label: "A wedding you went to recently",
            reply: "Hey — have you been to any weddings lately?",
            state: "open",
          });
        if (String(url).endsWith("/turn"))
          return jsonOnce({
            conversation_id: 1,
            topic_label: "A wedding you went to recently",
            reply: "A garden wedding sounds lovely.",
            state: "open",
          });
        return jsonOnce({});
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  async function toThread(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
    await screen.findByTestId("conversation-topics");
    await user.click(
      screen.getByRole("button", { name: "A wedding you went to recently" }),
    );
    await screen.findByTestId("conversation-log");
  }

  it("spends no provider call until the learner asks for topics (#399)", async () => {
    // **THE COST GATE, ASSERTED AS BEHAVIOUR RATHER THAN TRUSTED AS A HABIT.**
    // `suggest_topics` is a model call. The design opens straight onto three
    // cards, which would spend it on every page load — including loads nobody
    // uses. **Operator ruling 2026-09-07: the direct open is declined.**
    //
    // RED against a `useEffect(() => void suggest(), [])`.
    render(<Conversation voice={false} />);
    const calls = () =>
      (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    expect(calls().length).toBe(0);

    await userEvent.setup().click(
      screen.getByRole("button", { name: CONVERSATION.start }),
    );
    await screen.findByTestId("conversation-topics");
    expect(calls().length).toBe(1);
  });

  it("names the screen, which it never did", async () => {
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await toThread(user);
    expect(screen.getByText(CONVERSATION.eyebrow)).toBeInTheDocument();
  });

  it("makes ending the conversation a control, and keeps it out of the scroll region", async () => {
    // **THE DEFECT: it was a ghost button below the composer and read as bare
    // text.** It is now a bordered pill in the header. Asserted as *is a
    // button* and *is not inside the log*, which is the structural claim; the
    // border is not asserted, because that would be pinning Tailwind.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await toThread(user);
    const endControl = screen.getByTestId("conversation-end");
    expect(endControl.tagName).toBe("BUTTON");
    expect(screen.getByTestId("conversation-log").contains(endControl)).toBe(false);
  });

  it("shows each speaker's name on screen, not only to a screen reader", async () => {
    // **THE DEFECT THE OPERATOR SAW: *no visible speaker sides*.** The label
    // existed and was `sr-only`, so on a phone the two turns were told apart by
    // a background tint and an alignment and nothing else.
    //
    // **THIS NAMES A CLASS, AND THAT IS DELIBERATE AND NOT THE THING THE
    // COLOUR RULE FORBIDS:** `sr-only` IS the mechanism of invisibility, not a
    // palette choice, and jsdom's `toBeVisible` cannot see it — the class
    // clips the element rather than hiding it.
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await toThread(user);
    await user.type(screen.getByTestId("conversation-composer"), "it was lovely");
    await user.click(screen.getByTestId("conversation-send"));
    await screen.findByText("A garden wedding sounds lovely.");

    for (const name of [CONVERSATION.you, CONVERSATION.app]) {
      const label = screen.getAllByText(name)[0];
      expect(label).toBeInTheDocument();
      expect(label.className).not.toContain("sr-only");
    }
  });

  it("gives the composer the full width, with its controls in a row beneath", async () => {
    // **THE DEFECT: a small box floating at the left with two buttons beside
    // it.** The field and the controls shared one flex row, so the field got
    // whatever was left. Asserted structurally — the send control is no longer
    // a sibling of the textarea — rather than by measuring, which jsdom cannot
    // do (it has no layout engine).
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await toThread(user);
    const box = screen.getByTestId("conversation-composer");
    const sendControl = screen.getByTestId("conversation-send");
    expect(box.className).toContain("w-full");
    expect(box.parentElement).not.toBe(sendControl.parentElement);
  });

  it("gives Speak and Send a glyph each, and keeps the word as the label", async () => {
    // The design's own note: a microphone and a send glyph **"with the words
    // kept as labels, so neither reads as a bare link"**. Both halves are
    // asserted, because either alone is a different defect — an icon with no
    // word is a puzzle, a word with no icon is what shipped.
    const user = userEvent.setup();
    render(<Conversation voice />);
    await toThread(user);
    for (const [id, word] of [
      ["conversation-send", CONVERSATION.send],
      ["conversation-speak", CONVERSATION.micStart],
    ] as const) {
      const control = screen.getByTestId(id);
      expect(control.querySelector("svg")).not.toBeNull();
      expect(control).toHaveTextContent(word);
    }
  });

  it("offers the topics as cards, behind a full-width primary control", async () => {
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    const startControl = screen.getByRole("button", { name: CONVERSATION.start });
    expect(startControl.className).toContain("w-full");

    await user.click(startControl);
    await screen.findByTestId("conversation-topics");
    expect(screen.getAllByTestId("topic-card")).toHaveLength(3);
  });
});
