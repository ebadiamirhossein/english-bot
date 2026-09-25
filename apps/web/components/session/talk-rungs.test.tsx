/**
 * W15 — the two rungs on `/talk`: answer and retell.
 *
 * **Rendered from `talk.fixture.json`**, which `scripts/export_talk_fixture.py`
 * builds through the routes' own response models and `tests/test_talk_fixture.py`
 * holds to real ASGI bodies (#190). No body here is hand-written.
 *
 * **What these prove and what they cannot:** the rungs are offered from the free
 * read, open on the task verbatim, take one turn, and close onto what the
 * learner got across — never a count. jsdom has no layout engine, so *on
 * screen* and *above the keyboard* are `e2e/talk.spec.ts`'s. **Whether a
 * correction teaches, or a retell's points are true of the video, is a human
 * check** at the launch pass.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Conversation } from "./conversation";
import { CONVERSATION } from "./copy";
import { mockAudio, polyfillBlobArrayBuffer } from "./audio-mocks";
import fixture from "./talk.fixture.json";

polyfillBlobArrayBuffer();

type Call = { url: string; method: string; body: unknown };

function jsonOnce(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body } as unknown as Response;
}

/**
 * The API, from the fixture. `rungs` picks the `GET /conversation/rungs` body;
 * `kind` picks which open/turn/close bodies a rung answers with.
 */
type ServeOptions = {
  rungs?: unknown;
  kind?: "answer" | "retell";
  close?: unknown;
  voiceTurn?: boolean;
};

function serve(calls: Call[], options: ServeOptions = {}) {
  const kind = options.kind ?? "answer";
  const rungs = options.rungs ?? fixture.rungs_both;
  const close = options.close ?? (kind === "answer" ? fixture.close_answer : fixture.close_retell);
  const voiceTurn = options.voiceTurn ?? false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).replace(/^.*?\/conversation/, "/conversation");
      const body =
        typeof init?.body === "string" ? JSON.parse(init.body as string) : init?.body ?? null;
      calls.push({ url: path, method: init?.method ?? "GET", body });
      if (path === "/conversation/rungs") return jsonOnce(rungs);
      if (path === "/conversation/open")
        return jsonOnce(kind === "answer" ? fixture.open_answer : fixture.open_retell);
      if (path === "/conversation/turn") return jsonOnce(fixture.turn_rung);
      if (path === "/conversation/turn/voice")
        return jsonOnce(voiceTurn ? fixture.turn_rung_voice : fixture.turn_rung);
      if (path === "/conversation/close") return jsonOnce(close);
      if (path === "/conversation/save-word") return jsonOnce({ state: "saved" });
      return jsonOnce({ detail: "not_found" }, 404);
    }),
  );
}

async function answer(user: ReturnType<typeof userEvent.setup>, text = "I wake up at seven.") {
  await user.click(await screen.findByTestId("rung-answer"));
  await screen.findByTestId("conversation-log");
  await user.type(screen.getByTestId("conversation-composer"), text);
  await user.click(screen.getByRole("button", { name: CONVERSATION.send }));
  return screen.findByTestId("conversation-closed");
}

describe("W15 — the rungs on /talk", () => {
  beforeEach(() => {
    mockAudio();
    globalThis.Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("offers the unit's spoken task verbatim and today's video, with nothing that counts", async () => {
    // RED against a card that renders `label` (the can-do) where the task goes.
    const calls: Call[] = [];
    serve(calls);
    render(<Conversation voice={false} />);
    const rungs = await screen.findByTestId("conversation-rungs");
    expect(screen.getByTestId("rung-answer")).toHaveTextContent(
      fixture.rungs_both.answer.prompt as string,
    );
    expect(screen.getByTestId("rung-retell")).toHaveTextContent(fixture.rungs_both.retell.label);
    expect(rungs.textContent).not.toMatch(/\d/);
    // The conversation stays the page's first action: the press precedes the rungs.
    const press = screen.getByRole("button", { name: CONVERSATION.start });
    expect(press.compareDocumentPosition(rungs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Showing the rungs billed nothing: the only call is the free read.
    expect(calls.map((c) => c.url)).toEqual(["/conversation/rungs"]);
  });

  it("leaves a rung that is not on offer absent, never greyed out", async () => {
    // RED against rendering the retell card `disabled` when `retell` is null.
    serve([], { rungs: fixture.rungs_answer_only });
    render(<Conversation voice={false} />);
    await screen.findByTestId("rung-answer");
    expect(screen.queryByTestId("rung-retell")).toBeNull();
  });

  it("opens an answer on the task, takes one turn, and closes on it", async () => {
    // RED against dropping `if (out.state === "closing") await end()` from
    // `landed` — the rung never closes and the close-out never arrives.
    const calls: Call[] = [];
    serve(calls);
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await user.click(await screen.findByTestId("rung-answer"));
    const log = await screen.findByTestId("conversation-log");
    expect(log).toHaveTextContent(fixture.open_answer.reply);
    expect(screen.getByText(CONVERSATION.answerTitle)).toBeInTheDocument();
    expect(screen.getByTestId("conversation-composer")).toHaveAttribute(
      "placeholder",
      CONVERSATION.answerPlaceholder,
    );
    await user.type(screen.getByTestId("conversation-composer"), "I wake up at seven.");
    await user.click(screen.getByRole("button", { name: CONVERSATION.send }));
    await screen.findByTestId("conversation-closed");
    expect(calls.find((c) => c.url === "/conversation/open")?.body).toEqual({ kind: "answer" });
    expect(calls.map((c) => c.url)).toEqual([
      "/conversation/rungs",
      "/conversation/open",
      "/conversation/turn",
      "/conversation/close",
    ]);
  });

  it("closes an answer onto its own eyebrow, the raise first, and each correction's label", async () => {
    // RED against dropping `label` from the correction card.
    serve([]);
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    const closed = await answer(user);
    expect(closed).toHaveTextContent(CONVERSATION.answerCloseEyebrow);
    expect(closed).toHaveTextContent(CONVERSATION.rungClosing);
    const labels = screen.getAllByTestId("correction-label").map((n) => n.textContent);
    expect(labels).toEqual(["Past tense", "Past tense"]);
    const text = closed.textContent ?? "";
    expect(text.indexOf(fixture.close_answer.did_well)).toBeLessThan(
      text.indexOf(CONVERSATION.correctionsHeading),
    );
  });

  it("closes a retell onto what was got across, then the video's other points, never a count", async () => {
    // RED against rendering every point in one list — the video's other points
    // then sit under *What you got across* and the first `not` fails.
    serve([], { kind: "retell" });
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await user.click(await screen.findByTestId("rung-retell"));
    await screen.findByText(fixture.open_retell.reply);
    expect(screen.getByText(CONVERSATION.retellTitle)).toBeInTheDocument();
    await user.type(screen.getByTestId("conversation-composer"), "People waits in a line.");
    await user.click(screen.getByRole("button", { name: CONVERSATION.send }));
    const closed = await screen.findByTestId("conversation-closed");

    const covered = screen.getByTestId("close-covered");
    const also = screen.getByTestId("close-also");
    expect(covered).toHaveTextContent(CONVERSATION.coveredHeading);
    expect(also).toHaveTextContent(CONVERSATION.alsoHeading);
    for (const point of fixture.close_retell.covered) expect(covered).toHaveTextContent(point);
    for (const point of fixture.close_retell.also) {
      expect(also).toHaveTextContent(point);
      expect(covered).not.toHaveTextContent(point);
    }
    const text = closed.textContent ?? "";
    expect(text).not.toMatch(/%|\bout of\b|\bscore/i);
    expect(covered.textContent).not.toMatch(/\d/);
    // Payoff first: the raise, what was got across, the video's other points,
    // and only then anything worth a look.
    const at = (s: string) => text.indexOf(s);
    expect(at(fixture.close_retell.did_well)).toBeLessThan(at(CONVERSATION.coveredHeading));
    expect(at(CONVERSATION.coveredHeading)).toBeLessThan(at(CONVERSATION.alsoHeading));
    expect(at(CONVERSATION.alsoHeading)).toBeLessThan(at(CONVERSATION.correctionsHeading));
  });

  it("says a rung in another language was not in English, and corrects nothing", async () => {
    // RED against ignoring `is_english` — the *nothing to add* line shows instead.
    serve([], { close: fixture.close_not_english });
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await answer(user, "Vakar atsikėliau septintą.");
    expect(screen.getByTestId("close-not-english")).toHaveTextContent(CONVERSATION.notEnglish);
    expect(screen.queryByText(CONVERSATION.rungNothing)).toBeNull();
    expect(screen.queryAllByTestId("conversation-correction")).toHaveLength(0);
  });

  it("sends a kept word back with the token its offer was signed with (#408)", async () => {
    // RED against posting `{ word }` alone — the body lacks the token.
    const calls: Call[] = [];
    serve(calls);
    const user = userEvent.setup();
    render(<Conversation voice={false} />);
    await answer(user);
    const row = screen.getAllByTestId("conversation-word")[0];
    await user.click(row.querySelector("button") as HTMLButtonElement);
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/conversation/save-word")?.body).toEqual({
        word: "pasta",
        token: "fixture-talk-0",
      }),
    );
  });

  it("shows what was heard on a spoken turn as the learner's own line (#427)", async () => {
    // RED against dropping the `heard` line in `landed` — the transcript never
    // reaches the log, which is what shipped on /talk until W15 (demonstrated).
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = String(url).replace(/^.*?\/conversation/, "/conversation");
        if (path === "/conversation/rungs") return jsonOnce(fixture.rungs_both_voice);
        if (path === "/conversation/topics") return jsonOnce({ ...fixture.topics, voice: true });
        if (path === "/conversation/open") return jsonOnce(fixture.open_talk);
        if (path === "/conversation/turn/voice") return jsonOnce(fixture.turn_talk_voice);
        return jsonOnce({ detail: "not_found" }, 404);
      }),
    );
    const user = userEvent.setup();
    render(<Conversation />);
    await user.click(screen.getByRole("button", { name: CONVERSATION.start }));
    await user.click(await screen.findByRole("button", { name: fixture.topics.topics[0] }));
    await screen.findByTestId("conversation-log");
    await user.click(screen.getByTestId("conversation-speak"));
    await screen.findByTestId("conversation-recording");
    await user.click(screen.getByRole("button", { name: CONVERSATION.micStop }));

    const heard = await screen.findByText(fixture.turn_talk_voice.heard as string);
    expect(heard.closest("[data-speaker]")?.getAttribute("data-speaker")).toBe("you");
    const reply = await screen.findByText(fixture.turn_talk_voice.reply);
    expect(
      heard.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
