import { render, screen, within } from "@testing-library/react";
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
    correct: false,
    graded_by: "deterministic",
    canonical: null,
    explanation: null,
    murphy_units: null,
    pairs: null,
    ...over,
  };
}

beforeEach(() => answerItem.mockReset());

/**
 * **#112 — the two types whose correct answer is a structure, not a string.**
 *
 * The verdict box prints `canonical` as one line, which is right for a typed
 * item and cannot express an ordering or a bijection. So these two show their
 * own answer, in the shape the exercise is in — or, where they genuinely
 * cannot, say so rather than promising it.
 */
describe("word_bank_order shows the correct order on the wrong path", () => {
  it("renders the answer as ordered tokens, not only as a sentence", async () => {
    // User action: building the sentence in the wrong order and tapping Check.
    //
    // The task was *ordering*; a sentence in the verdict box does not show
    // which token went where. `canonical` is a real string for this type, so
    // this costs nothing and introduces no second source of truth.
    answerItem.mockResolvedValue(graded({ canonical: "I went to the shops" }));
    render(<ItemCard item={BY_TYPE.get("word_bank_order")!} />);

    const pool = screen.getByTestId("word-bank-pool");
    await userEvent.click(within(pool).getByRole("button", { name: "shops" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    const answer = await screen.findByTestId("word-bank-answer");
    expect(answer).toHaveTextContent("In this order:");
    for (const token of ["I", "went", "to", "the", "shops"]) {
      expect(within(answer).getByText(token)).toBeInTheDocument();
    }
  });

  it("shows nothing extra when the order was right", async () => {
    answerItem.mockResolvedValue(
      graded({ correct: true, canonical: "I went to the shops" }),
    );
    render(<ItemCard item={BY_TYPE.get("word_bank_order")!} />);
    const pool = screen.getByTestId("word-bank-pool");
    await userEvent.click(within(pool).getByRole("button", { name: "I" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByTestId("feedback");
    expect(screen.queryByTestId("word-bank-answer")).toBeNull();
  });
});

describe("match_pairs on the wrong path", () => {
  it("never claims an answer it cannot produce", async () => {
    // User action: pairing all three wrong and tapping Check — the exact
    // sequence reproduced on production 2026-08-25.
    //
    // Its correct answer is a bijection in `items.payload.pairs`, which the
    // projection withholds because it *is* the answer, and `AnswerOutcome`
    // carries no field for it. Nothing on the client has it. So the box drops
    // the lead-in and the component says what a learner can do instead. The
    // real fix — the answer route returning the pairing after grading — is
    // #118, and needs an API change this closeout is barred from making.
    answerItem.mockResolvedValue(graded({ canonical: null }));
    render(<ItemCard item={BY_TYPE.get("match_pairs")!} />);

    const left = screen.getByTestId("match-left");
    const right = screen.getByTestId("match-right");
    await userEvent.click(within(left).getByRole("button", { name: "skint" }));
    await userEvent.click(
      within(right).getByRole("button", { name: "very tired" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    const box = await screen.findByTestId("feedback");
    expect(box.textContent ?? "").not.toContain("Here it is:");
    expect(box).toHaveAttribute("data-shows-answer", "false");
    const note = screen.getByTestId("match-pairs-no-answer");
    expect(note).toBeInTheDocument();
    // And the note promises nothing either — re-delivery under spacing is W7's,
    // so "you'll see it next time" would be a second cheque the app cannot cash.
    expect(note.textContent ?? "").not.toMatch(/next (round|time)|will be shown/i);
  });

  it("says nothing extra when the pairing was right", async () => {
    answerItem.mockResolvedValue(graded({ correct: true, canonical: null }));
    render(<ItemCard item={BY_TYPE.get("match_pairs")!} />);
    const left = screen.getByTestId("match-left");
    const right = screen.getByTestId("match-right");
    await userEvent.click(within(left).getByRole("button", { name: "skint" }));
    await userEvent.click(
      within(right).getByRole("button", { name: "having no money" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByTestId("feedback");
    expect(screen.queryByTestId("match-pairs-no-answer")).toBeNull();
  });
});

describe("nothing about the answer reaches a component before grading", () => {
  it("passes no result while the request is still in flight", async () => {
    // The `result` prop exists so the two structural types can show their own
    // answer — and it must not become a way for one to arrive early. There is
    // nothing to pass until the round trip lands, which is the same reason the
    // verdict box cannot render early.
    let settle: (r: ItemAnswerResult) => void = () => {};
    answerItem.mockReturnValue(
      new Promise<ItemAnswerResult>((resolve) => {
        settle = resolve;
      }),
    );
    render(<ItemCard item={BY_TYPE.get("word_bank_order")!} />);
    const pool = screen.getByTestId("word-bank-pool");
    await userEvent.click(within(pool).getByRole("button", { name: "shops" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(screen.queryByTestId("word-bank-answer")).toBeNull();
    expect(screen.queryByTestId("feedback")).toBeNull();

    settle(graded({ canonical: "I went to the shops" }));
    await screen.findByTestId("word-bank-answer");
  });
});
