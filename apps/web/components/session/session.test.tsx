import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CardFace as CardFaceData, SessionBlock, SessionToday } from "@/lib/api";

import { CloseBlock, FocusBlock, InputBlock, OutputBlock, ReviewBlock } from "./blocks";
import { NOTHING_DUE } from "./copy";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getSessionToday: vi.fn(),
    attemptCard: vi.fn(),
    gradeCard: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { SessionRunner } = await import("./runner");

function block(over: Partial<SessionBlock> & { n: number; kind: SessionBlock["kind"] }): SessionBlock {
  return { state: "ready", payload: {}, ...over };
}

function session(over: Partial<SessionToday> = {}): SessionToday {
  return {
    session_id: 7,
    date: "2026-08-26",
    l1_language: "fa",
    current_block: 1,
    completed: false,
    blocks: [
      block({ n: 1, kind: "review", state: "empty" }),
      block({ n: 2, kind: "input", state: "empty" }),
      block({ n: 3, kind: "focus", state: "empty" }),
      block({ n: 4, kind: "output", state: "empty" }),
      block({ n: 5, kind: "close", payload: { cards_reviewed: 0 } }),
    ],
    ...over,
  };
}

function card(over: Partial<CardFaceData> = {}): CardFaceData {
  return {
    id: 44,
    card_type: "production",
    front: "to eat something quickly and eagerly",
    back: "devour",
    cue: null,
    context_sentence: null,
    source_ref: "language_reactor",
    meaning: "to eat something quickly and eagerly",
    register: "neutral",
    neutral_equivalent: null,
    who_says_this: null,
    typed: true,
    intervals: { again: 0, hard: 3, good: 7, easy: 15 },
    ...over,
  };
}

beforeEach(() => {
  vi.mocked(api.getSessionToday).mockReset();
  vi.mocked(api.attemptCard).mockReset();
  vi.mocked(api.gradeCard).mockReset();
});

/**
 * **The distinction this whole slice is built around.**
 *
 * `empty` is a fact the server computed after a successful read. `unavailable`
 * is a block that could not be built. A request that never came back is
 * NEITHER — it is unknown, and the only honest thing to show is a retry.
 *
 * A learner told *nothing's due, go watch something* because a fetch failed has
 * been lied to, and on the screen the lie is indistinguishable from the truth.
 */
describe("empty is never a failure, and a failure is never empty", () => {
  it("shows the watching invitation when nothing is due", () => {
    render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", state: "empty" })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );
    expect(screen.getByTestId("nothing-due").textContent).toContain(
      NOTHING_DUE.title,
    );
  });

  it("says something different when the block could not be built", () => {
    render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", state: "unavailable" })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );
    expect(screen.getByTestId("block-unavailable")).not.toBeNull();
    expect(screen.queryByTestId("nothing-due")).toBeNull();
  });

  it("renders no block at all when the whole request fails", async () => {
    vi.mocked(api.getSessionToday).mockRejectedValue(new Error("boom"));
    render(<SessionRunner />);

    await waitFor(() =>
      expect(screen.getByTestId("session-problem")).not.toBeNull(),
    );
    // The three things a learner must NOT see when the request failed.
    expect(screen.queryByTestId("nothing-due")).toBeNull();
    expect(screen.queryByTestId("block-empty")).toBeNull();
    expect(screen.queryByTestId("session-block")).toBeNull();
  });
});

/**
 * CLAUDE.md §4: *"Never present a backlog. Missed days shrink the task; they
 * never pile up."* Nothing on this surface may accumulate while a learner is
 * away.
 */
describe("nothing accumulates", () => {
  it("counts position within today and never a remainder", async () => {
    vi.mocked(api.getSessionToday).mockResolvedValue(session());
    render(<SessionRunner />);

    await waitFor(() =>
      expect(screen.getByTestId("session-position")).not.toBeNull(),
    );
    const text = screen.getByTestId("session-position").textContent ?? "";
    expect(text).toContain("Block 1 of 5");
    expect(text).not.toContain("left");
    expect(text).not.toContain("overdue");
  });

  it("says nothing about yesterday", async () => {
    vi.mocked(api.getSessionToday).mockResolvedValue(session());
    const { container } = render(<SessionRunner />);

    await waitFor(() =>
      expect(screen.getByTestId("session-runner")).not.toBeNull(),
    );
    const copy = (container.textContent ?? "").toLowerCase();
    for (const word of ["yesterday", "since", "behind", "catch up", "streak"]) {
      expect(copy).not.toContain(word);
    }
  });
});

/**
 * Block 3. The unit's labels, no citation, and — since W10c — its items.
 *
 * **And no citation can reach it**: the server sends `{target}` alone.
 */
describe("block 3 shows labels and no citation", () => {
  const focus = block({
    n: 3,
    kind: "focus",
    payload: {
      unit_number: 1,
      can_do: "I can talk about what I do most days.",
      grammar_targets: [{ target: "present simple for habits" }],
      lesson: null,
      items: [],
    },
  });

  it("renders the can-do and the targets", () => {
    render(<FocusBlock block={focus} />);
    expect(screen.getByTestId("focus-can-do").textContent).toContain("most days");
    expect(screen.getByTestId("focus-targets").textContent).toContain(
      "present simple",
    );
  });

  it("renders no Murphy citation, because none arrives", () => {
    const { container } = render(<FocusBlock block={focus} />);
    expect(container.textContent).not.toContain("Murphy");
  });

  it("renders no practice section at all when no items were generated", () => {
    render(<FocusBlock block={focus} />);
    expect(screen.queryByTestId("focus-items")).toBeNull();
  });

  it("no longer apologises for the generator that now exists", () => {
    const { container } = render(<FocusBlock block={focus} />);
    expect(container.textContent).not.toContain("exercise generator");
  });

  /**
   * **This assertion's MEANING inverted at W10b, and the old one is quoted here
   * rather than deleted.** It previously read, unconditionally:
   *
   *     it("still says the written explanation is on its way (#182, W10b's half)")
   *     expect(container.textContent).toContain("written explanation");
   *
   * The line was rendered on every block 3, because there were no lessons. It is
   * now rendered ONLY when `payload.lesson` is null — which is still most units,
   * since generation is human-run (#196) — so the same expectation now tests the
   * null branch specifically. A test whose meaning inverted reads as a deletion
   * six weeks later, so the change is recorded, not just made.
   */
  it("says the written explanation is on its way WHEN there is no lesson", () => {
    const { container } = render(<FocusBlock block={focus} />);
    expect(container.textContent).toContain("written explanation");
    expect(screen.queryByTestId("lesson")).toBeNull();
  });
});

/**
 * Block 3 with items — the half W10 shipped empty.
 *
 * **The user action:** reaching block 3 of the daily session and answering the
 * eight items generated against this unit's own grammar targets.
 */
describe("block 3 serves its generated items", () => {
  const withItems = block({
    n: 3,
    kind: "focus",
    payload: {
      unit_number: 1,
      can_do: "I can tell a friend what I did yesterday.",
      grammar_targets: [{ target: "past simple: regular and irregular verbs" }],
      lesson: null,
      items: [
        {
          id: 41,
          response_mode: "typed",
          projection: {
            item_type: "cloze_cued",
            prompt_text: "I ___ there twice last year.",
          },
        },
        {
          id: 42,
          response_mode: "tap",
          projection: {
            item_type: "mcq",
            prompt_text: "I ___ to the shops yesterday.",
            options: ["went", "goed", "gone", "going"],
          },
        },
      ],
    },
  });

  it("renders the first item, not all of them at once", () => {
    render(<FocusBlock block={withItems} />);
    expect(screen.getByTestId("focus-items")).not.toBeNull();
    expect(screen.getByText(/there twice last year/)).not.toBeNull();
    expect(screen.queryByText(/to the shops yesterday/)).toBeNull();
  });

  it("shows a position and never a count of what is left", () => {
    const { container } = render(<FocusBlock block={withItems} />);
    // CLAUDE.md §4: never present a backlog. "1 of 2" is where you are;
    // "1 remaining" would be a debt.
    expect(container.textContent).toContain("1 of 2");
    expect(container.textContent).not.toMatch(/remaining|left|still to do/i);
  });

  it("keeps rendering the unit's targets above the practice", () => {
    render(<FocusBlock block={withItems} />);
    expect(screen.getByTestId("focus-targets").textContent).toContain(
      "past simple",
    );
  });

  it("carries no guilt language into the block", () => {
    const { container } = render(<FocusBlock block={withItems} />);
    expect(container.textContent).not.toMatch(
      /wrong|incorrect|failed|missed|try harder/i,
    );
  });
});

/** Blocks 2 and 4, and the close line that carries no XP. */
describe("the remaining blocks", () => {
  it("says the video side is not built rather than hiding the block", () => {
    render(<InputBlock block={block({ n: 2, kind: "input", state: "empty" })} />);
    expect(screen.getByTestId("session-block")).not.toBeNull();
    expect(screen.getByTestId("block-empty")).not.toBeNull();
  });

  it("offers the unit's written task and hands over to /write", () => {
    render(
      <OutputBlock
        block={block({
          n: 4,
          kind: "output",
          payload: { unit_number: 1, mode: "write", task: "Tell me about your week." },
        })}
      />,
    );
    expect(screen.getByTestId("output-task").textContent).toContain("your week");
    expect(screen.getByRole("link", { name: /write/i }).getAttribute("href")).toBe(
      "/write",
    );
  });

  it("closes with what happened and no XP number", () => {
    const { container } = render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 3 } })} />,
    );
    expect(screen.getByTestId("close-summary").textContent).toContain("3 cards");
    expect(container.textContent).not.toContain("XP");
  });
});

/**
 * #157. The learner commits to a string before the back appears, and the four
 * grade buttons still decide the schedule.
 */
describe("the typed answer comes before the reveal", () => {
  it("asks for a typed answer on a production card and hides the back", () => {
    render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", payload: { cards: [card()] } })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );
    expect(screen.getByTestId("card-typed-input")).not.toBeNull();
    expect(screen.queryByTestId("card-back")).toBeNull();
  });

  it("asks for no typed answer on a recognition card", () => {
    render(
      <ReviewBlock
        block={block({
          n: 1,
          kind: "review",
          payload: { cards: [card({ card_type: "recognition", typed: false })] },
        })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );
    expect(screen.queryByTestId("card-typed-input")).toBeNull();
    expect(screen.getByTestId("reveal")).not.toBeNull();
  });

  it("sends the typed string to the server and keeps the four grades", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: true });
    render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", payload: { cards: [card()] } })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );

    await userEvent.type(screen.getByTestId("card-typed-input"), "devour");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(api.attemptCard).toHaveBeenCalledWith(44, "devour");
    await waitFor(() =>
      expect(screen.getByTestId("card-typed-verdict")).not.toBeNull(),
    );
    // The verdict informs the self-grade; it does not replace it.
    expect(screen.getByTestId("grade-buttons")).not.toBeNull();
    expect(screen.getByTestId("card-back")).not.toBeNull();
  });

  it("carries the session id and the typed string into the grade", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: false });
    vi.mocked(api.gradeCard).mockResolvedValue({
      due: "2026-08-27T00:00:00Z",
      interval_days: 1,
      counts: { new_remaining: 0, review_remaining: 0, total_remaining: 0 },
    });
    render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", payload: { cards: [card()] } })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );

    await userEvent.type(screen.getByTestId("card-typed-input"), "devoured");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() =>
      expect(screen.getByTestId("card-typed-verdict")).not.toBeNull(),
    );
    await userEvent.click(screen.getByRole("button", { name: /again/i }));

    const [, , , extra] = vi.mocked(api.gradeCard).mock.calls[0];
    expect(extra).toMatchObject({ sessionId: 7, typedResponse: "devoured" });
  });

  it("never says the learner was wrong", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: false });
    const { container } = render(
      <ReviewBlock
        block={block({ n: 1, kind: "review", payload: { cards: [card()] } })}
        l1Language="fa"
        sessionId={7}
        onGraded={() => {}}
      />,
    );

    await userEvent.type(screen.getByTestId("card-typed-input"), "eat");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() =>
      expect(screen.getByTestId("card-typed-verdict")).not.toBeNull(),
    );

    const copy = (container.textContent ?? "").toLowerCase();
    for (const banned of ["wrong", "incorrect", "not quite", "missed", "failed"]) {
      expect(copy).not.toContain(banned);
    }
  });
});
