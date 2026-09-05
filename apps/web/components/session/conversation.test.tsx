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
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.className).toContain("max-h-32");
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
