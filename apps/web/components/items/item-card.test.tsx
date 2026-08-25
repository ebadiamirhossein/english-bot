import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ItemAnswerResult } from "@/lib/api";
import fixtures from "@/lib/items/projections.fixture.json";

import { ItemCard } from "./item-card";

const answerItem = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  answerItem,
}));

type Envelope = {
  id: number;
  response_mode: string;
  projection: Record<string, unknown>;
};

const BY_TYPE = new Map(
  (fixtures as Envelope[]).map((e) => [e.projection["item_type"] as string, e]),
);

function graded(over: Partial<ItemAnswerResult> = {}): ItemAnswerResult {
  return {
    correct: true,
    graded_by: "deterministic",
    canonical: "went",
    explanation: null,
    murphy_units: null,
    ...over,
  };
}

beforeEach(() => answerItem.mockReset());

describe("the feedback state machine", () => {
  it("shows no verdict at all until the server answers", async () => {
    // User action: tapping an answer and waiting.
    //
    // **The anti-optimistic-grading test, and the reason Vitest is here.** A
    // source scan can ban `toLowerCase`; it cannot prove that nothing renders a
    // verdict before the round trip lands. The promise below is held open
    // deliberately so "in flight" is a state the test can look at.
    let settle: (result: ItemAnswerResult) => void = () => {};
    answerItem.mockReturnValue(
      new Promise<ItemAnswerResult>((resolve) => {
        settle = resolve;
      }),
    );

    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
    expect(screen.queryByTestId("feedback")).toBeNull();

    settle(graded());
    await waitFor(() =>
      expect(screen.getByTestId("feedback")).toHaveAttribute(
        "data-correct",
        "true",
      ),
    );
  });

  it("sends exactly one request, carrying the tapped option and a latency", async () => {
    // User action: tapping an answer once.
    answerItem.mockResolvedValue(graded());
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);

    await userEvent.click(screen.getByRole("button", { name: "goed" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByTestId("feedback");

    expect(answerItem).toHaveBeenCalledTimes(1);
    const [itemId, body] = answerItem.mock.calls[0];
    expect(itemId).toBe(BY_TYPE.get("mcq")!.id);
    expect(body.option).toBe("goed");
    expect(typeof body.latency_ms).toBe("number");
    expect(body.latency_ms).toBeGreaterThanOrEqual(0);
  });

  it("a wrong answer shows the canonical and no failure state", async () => {
    // User action: getting one wrong.
    //
    // CLAUDE.md §4: nothing red, nothing struck through, and the emphasis on
    // the better version rather than on the mistake.
    answerItem.mockResolvedValue(graded({ correct: false, canonical: "went" }));
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);

    await userEvent.click(screen.getByRole("button", { name: "goed" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    const feedback = await screen.findByTestId("feedback");
    expect(feedback).toHaveAttribute("data-correct", "false");
    expect(feedback).toHaveTextContent("went");
    expect(feedback.className).not.toMatch(/red|destructive/);
    expect(feedback.innerHTML).not.toContain("line-through");
  });

  it("the explanation panel renders nothing when the item carries neither half", async () => {
    // Today's ordinary case, and worth pinning rather than discovering on a
    // phone: the generator never asks for an explanation (#103) and an item
    // need not declare an error type (#104). An empty "Why" box would be a
    // promise the item cannot keep.
    answerItem.mockResolvedValue(graded());
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByTestId("feedback");
    expect(screen.queryByTestId("explanation")).toBeNull();
  });

  it("shows the explanation and the Murphy reference when they exist", async () => {
    answerItem.mockResolvedValue(
      graded({ explanation: "Past simple for a finished action.", murphy_units: "5-6" }),
    );
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    const panel = await screen.findByTestId("explanation");
    expect(panel).toHaveTextContent("Past simple for a finished action.");
    expect(panel).toHaveTextContent("Murphy 5-6");
  });

  it("cannot be answered twice — the check disappears once graded", async () => {
    // W6 allows no retry: the feedback reveals the canonical answer, so a
    // second attempt at the same encounter measures reading, not retrieval.
    // `item_attempts.attempt_no` is therefore always 1.
    answerItem.mockResolvedValue(graded());
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByTestId("feedback");
    expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
  });

  it("a failed request says so and offers another go, without a verdict", async () => {
    // User action: answering with the API down.
    answerItem.mockRejectedValue(new Error("boom"));
    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(screen.queryByTestId("feedback")).toBeNull());
    expect(screen.getByRole("button", { name: "Check" })).toBeInTheDocument();
  });
});

describe("choosing an input by response mode, never by type", () => {
  it("gives a typed item a text field and a tap item none", () => {
    const { unmount } = render(<ItemCard item={BY_TYPE.get("cloze_cued")!} />);
    expect(screen.getByTestId("typed-answer-input")).toBeInTheDocument();
    unmount();

    render(<ItemCard item={BY_TYPE.get("mcq")!} />);
    expect(screen.queryByTestId("typed-answer-input")).toBeNull();
  });

  it("gives a spoken item two self-mark buttons and no microphone", async () => {
    // User action: saying the sentence and marking yourself.
    //
    // Nothing is recorded in W6 — `navigator.mediaDevices` is never touched,
    // so there is no audio to discard and `audio_seconds` stays NULL.
    answerItem.mockResolvedValue(graded({ graded_by: "self", canonical: null }));
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia },
      configurable: true,
    });

    render(<ItemCard item={BY_TYPE.get("speak_repeat")!} />);
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    await screen.findByTestId("feedback");

    expect(answerItem.mock.calls[0][1].self_marked).toBe(true);
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("marking yourself short is recorded and reads without blame", async () => {
    answerItem.mockResolvedValue(
      graded({ correct: false, graded_by: "self", canonical: null }),
    );
    render(<ItemCard item={BY_TYPE.get("speak_answer")!} />);
    await userEvent.click(screen.getByRole("button", { name: "Not yet" }));
    const feedback = await screen.findByTestId("feedback");
    expect(answerItem.mock.calls[0][1].self_marked).toBe(false);
    expect(feedback.textContent ?? "").not.toMatch(
      /wrong|incorrect|missed|failed/i,
    );
  });
});
