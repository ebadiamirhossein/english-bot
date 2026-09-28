import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CardFace as CardFaceData, SessionBlock, SessionToday } from "@/lib/api";

import { CloseBlock, FocusBlock, InputBlock, OutputBlock, ReviewBlock } from "./blocks";
import { CONVERSATION } from "./copy";
import { NOTHING_DUE } from "./copy";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getSessionToday: vi.fn(),
    getKeepGoing: vi.fn(),
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
    finished: false,
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
    // W13d: most cards carry no picture, and a hand-built face says so.
    image: null,
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
    render(<FocusBlock block={focus} sessionId={90} />);
    expect(screen.getByTestId("focus-can-do").textContent).toContain("most days");
    expect(screen.getByTestId("focus-targets").textContent).toContain(
      "present simple",
    );
  });

  it("renders no Murphy citation, because none arrives", () => {
    const { container } = render(<FocusBlock block={focus} sessionId={90} />);
    expect(container.textContent).not.toContain("Murphy");
  });

  it("renders no practice section at all when no items were generated", () => {
    render(<FocusBlock block={focus} sessionId={90} />);
    expect(screen.queryByTestId("focus-items")).toBeNull();
  });

  it("no longer apologises for the generator that now exists", () => {
    const { container } = render(<FocusBlock block={focus} sessionId={90} />);
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
    const { container } = render(<FocusBlock block={focus} sessionId={90} />);
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
    render(<FocusBlock block={withItems} sessionId={90} />);
    expect(screen.getByTestId("focus-items")).not.toBeNull();
    expect(screen.getByText(/there twice last year/)).not.toBeNull();
    expect(screen.queryByText(/to the shops yesterday/)).toBeNull();
  });

  it("shows a position and never a count of what is left", () => {
    const { container } = render(<FocusBlock block={withItems} sessionId={90} />);
    // CLAUDE.md §4: never present a backlog. "1 of 2" is where you are;
    // "1 remaining" would be a debt.
    expect(container.textContent).toContain("1 of 2");
    expect(container.textContent).not.toMatch(/remaining|left|still to do/i);
  });

  it("keeps rendering the unit's targets above the practice", () => {
    render(<FocusBlock block={withItems} sessionId={90} />);
    expect(screen.getByTestId("focus-targets").textContent).toContain(
      "past simple",
    );
  });

  it("carries no guilt language into the block", () => {
    const { container } = render(<FocusBlock block={withItems} sessionId={90} />);
    expect(container.textContent).not.toMatch(
      /wrong|incorrect|failed|missed|try harder/i,
    );
  });
});

/** Blocks 2 and 4, and the close line that carries no XP. */
describe("the remaining blocks", () => {
  /**
   * **AMENDED AT W13-i, AND THE OLD NAME IS QUOTED (#82's shape):** *"says the
   * video side is not built rather than hiding the block."* The block is built;
   * what it now reports is that **this day** has no video, which is the ordinary
   * state on four days in seven (PRD §7.1 is Mon/Wed/Fri) — until W24d, which
   * made video daily when the pool has one; the empty day is now the pool's.
   *
   * **The assertion that mattered survives unchanged**: the block is RENDERED
   * rather than hidden. A four-block session would say the product has four.
   */
  it("renders the block on a day with no video rather than hiding it", () => {
    render(
      <InputBlock
        block={block({ n: 2, kind: "input", state: "empty" })}
        l1Language="fa"
      />,
    );
    expect(screen.getByTestId("session-block")).not.toBeNull();
    expect(screen.getByTestId("block-empty")).not.toBeNull();
  });

  it("never presents a backlog or names another day as missed", () => {
    const { container } = render(
      <InputBlock
        block={block({ n: 2, kind: "input", state: "empty" })}
        l1Language="fa"
      />,
    );
    // CLAUDE.md §4: missed days shrink the task, they never pile up.
    expect(container.textContent).not.toMatch(
      /missed|yesterday|catch up|behind|overdue/i,
    );
  });

  // **W16a replaced "offers the unit's written task and hands over to /write".**
  // It rendered `payload.task`; W16a removed `task` from block 4's payload
  // because design `1c` draws no task text, so the old test asserted a field
  // that no longer exists. Red demonstration for the two below: keying the copy
  // on nothing (always the journal card) turned the second red; restoring the
  // old `output-task` paragraph turned the first red.
  it("draws design 1c's journal card and hands over to /write", () => {
    render(
      <OutputBlock
        block={block({ n: 4, kind: "output", payload: { day_kind: "journal" } })}
      />,
    );
    expect(screen.getByText("Today · your turn to write")).not.toBeNull();
    expect(screen.getByText("Write a few lines about your day.")).not.toBeNull();
    expect(screen.getByTestId("output-subline").textContent).toContain("one or two things");
    expect(
      screen.getByRole("link", { name: /start writing/i }).getAttribute("href"),
    ).toBe("/write");
    expect(screen.queryByTestId("output-task")).toBeNull();
  });

  it("draws design 1c's Thursday paragraph card (W16b)", () => {
    render(
      <OutputBlock
        block={block({ n: 4, kind: "output", payload: { day_kind: "paragraph" } })}
      />,
    );
    expect(screen.getByText("Today · this week’s paragraph")).not.toBeNull();
    expect(screen.getByText("One paragraph, on this week’s task.")).not.toBeNull();
    expect(
      screen.getByRole("link", { name: /start writing/i }).getAttribute("href"),
    ).toBe("/write");
  });

  // **W16b finding (b), from the session that stood down.** The card promised
  // "I'll go through all of it afterwards" while Q-D caps the paragraph at eight
  // corrections — `WRITE.paragraph.subline` had already dropped "all of it" and the
  // card had not. Red demonstration: the shipped string turned this red.
  it("promises no correction of all of it on the Thursday card (Q-D caps at eight)", () => {
    render(
      <OutputBlock
        block={block({ n: 4, kind: "output", payload: { day_kind: "paragraph" } })}
      />,
    );
    const subline = screen.getByTestId("output-subline").textContent ?? "";
    expect(subline).toBe("A bit longer than usual. I’ll go through it afterwards.");
    expect(subline).not.toMatch(/all of it/i);
  });

  // **W16b moved this from `paragraph` to a kind that does not exist**, because
  // the paragraph now has a card. Red demonstration: keying the copy on nothing.
  it("draws no card for a day kind this build has no copy for", () => {
    render(
      <OutputBlock
        block={block({ n: 4, kind: "output", payload: { day_kind: "essay" } })}
      />,
    );
    expect(screen.getByTestId("block-empty")).not.toBeNull();
    expect(screen.queryByRole("link", { name: /start writing/i })).toBeNull();
  });

  it("closes with what happened and no XP number", () => {
    const { container } = render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 3 } })} />,
    );
    expect(screen.getByTestId("close-summary").textContent).toContain("3 cards");
    expect(container.textContent).not.toContain("XP");
  });

  it("says nothing about cards on a day none were reviewed (#400)", () => {
    // **#348's EXACT SHAPE, FOUND LIVE ON THE CLOSING BLOCK.** `cards_reviewed`
    // defaults to 0 and every value but 1 went through the same template, so a
    // learner who reviewed nothing read **"0 cards reviewed today."** — a
    // numeric zero on a report, which is a score, on a day nobody promised
    // anything about.
    //
    // **THE BLOCK CANNOT TELL WHY THE COUNT IS ZERO.** `cards_reviewed` counts
    // rows in `card_reviews` for this session, so nothing was due and block 1
    // was skipped are the same number. **Any sentence it writes about cards
    // risks being false in one of those two worlds**, which is why the fix is
    // silence rather than a friendlier count.
    //
    // **RAISES ANNOUNCED, DROPS SILENT** (CLAUDE.md §4): twenty cards is
    // acknowledged, zero is not remarked on.
    //
    // RED against the shipped `${reviewed} cards reviewed today.`
    const { container } = render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 0 } })} />,
    );
    expect(screen.queryByTestId("close-summary")).toBeNull();
    expect(container.textContent ?? "").not.toMatch(/[0-9]/);
    // #345: a sibling proving the block rendered at all, so "absent" cannot be
    // satisfied by "nothing rendered".
    expect(screen.getByTestId("conversation-link")).toBeInTheDocument();
  });

  it("carries the design's own closing-card copy", () => {
    // **EXPECTED VALUES ARE THE DESIGN'S LITERAL STRINGS, NOT `BLOCKS.close`**
    // — CLAUDE.md §3 rule 5: a test must never derive its expected value from
    // the thing under test. Reading the constant back would pass whatever it
    // said.
    const { container } = render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 3 } })} />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Today \u00b7 to close");
    expect(text).toContain(
      "That\u2019s the session. The rest of the English is up to you.",
    );
    expect(text).toContain("Ten minutes, in English, about anything.");
  });

  it("puts the conversation entry point on the closing block, as a control", () => {
    // **W13b/5, design `1i`.** It was an underlined phrase inside block 4,
    // styled to lose against that block's own action; the design makes it a
    // filled button at the foot of the session.
    //
    // **THE #160 CLAUSE IS ASSERTED, NOT ASSUMED.** What that ruling forbids is
    // a COUNTER, and the emphasis clause from W13b/3 §A is honoured by
    // PLACEMENT — so the test checks the link is here, is a real control, and
    // carries nothing that accumulates.
    render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 3 } })} />,
    );
    const entry = screen.getByTestId("conversation-link");
    expect(entry).toHaveAttribute("href", "/talk");
    expect(entry).toHaveTextContent(CONVERSATION.entryAction);
    expect(entry.querySelector("svg")).not.toBeNull();
    expect(entry.className).not.toContain("underline");
  });

  it("puts nothing on the entry point that accumulates while the learner is away", () => {
    // #160, asserted on the words rather than trusted to the styling. A count
    // of conversations, a days-since, or a badge would each be a backlog
    // presented — and the entry point is exactly where one would be added.
    const { container } = render(
      <CloseBlock block={block({ n: 5, kind: "close", payload: { cards_reviewed: 3 } })} />,
    );
    const text = (container.textContent ?? "").toLowerCase();
    expect(text).toContain(CONVERSATION.entryAction.toLowerCase());
    for (const banned of ["days since", "last conversation", "streak", "you haven"]) {
      expect(text).not.toContain(banned);
    }
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


describe("#274 — block 3 must tell the server which session it is", () => {
  /**
   * **RED BEFORE THE FIX.** `FocusBlock` took only `block` and rendered
   * `<ItemCard item={...} />` with **no `sessionId`**, so `answerItem` sent no
   * `session_id` and every daily block-3 attempt stored NULL. The checkpoint's
   * runner passed it and the daily runner did not — **#254 was fixed on one
   * route and the other was never checked.**
   *
   * Without it `block_breakdown.focus` can never reach `done`, so #258's
   * automatic completion is inert and the pacing clock reads 0 forever.
   *
   * Asserted on the PROP reaching `ItemCard`, because that is the seam that was
   * missing; the wire itself is asserted server-side, on the stored row.
   */
  it("hands the session id to the item card", () => {
    const focus = block({
      n: 3,
      kind: "focus",
      payload: {
        unit_number: 1,
        can_do: "I can talk about what I do most days.",
        grammar_targets: [{ target: "present simple for habits" }],
        lesson: null,
        items: [
          {
            id: 501,
            response_mode: "typed",
            projection: { item_type: "cloze_cued", prompt_text: "I ___ home." },
          },
        ],
      },
    });
    const { container } = render(<FocusBlock block={focus} sessionId={90} />);
    expect(container.querySelector("[data-session-id='90']")).not.toBeNull();
  });
});



/**
 * W24e — the done state and keep going. **RED BEFORE W24e:** the runner read
 * `completed`, which no daily session ever carries, so "Done for today." never
 * rendered and there was no keep going to show.
 */
describe("keep going appears only once the session is finished (R2)", () => {
  beforeEach(() => {
    vi.mocked(api.getKeepGoing).mockResolvedValue({ options: ["watch", "talk", "cards", "write"] });
  });

  it("shows neither the done line nor keep going while a block is open", async () => {
    vi.mocked(api.getSessionToday).mockResolvedValue(session());
    render(<SessionRunner />);
    await screen.findByTestId("session-runner");
    expect(screen.queryByTestId("session-finished")).toBeNull();
    expect(api.getKeepGoing).not.toHaveBeenCalled();
  });

  it("shows the done line and every offered option, as links and without a number", async () => {
    vi.mocked(api.getSessionToday).mockResolvedValue(session({ finished: true }));
    render(<SessionRunner />);
    expect(await screen.findByText("Done for today.")).toBeInTheDocument();
    const panel = await screen.findByTestId("keep-going");
    // W32f: `?extra=1` — keep going's watch-another; the nav's plain `/watch`
    // only opens today's video and never assigns (was `"/watch"` until W32f).
    expect(screen.getByTestId("keep-going-watch")).toHaveAttribute("href", "/watch?extra=1");
    expect(screen.getByTestId("keep-going-talk")).toHaveAttribute("href", "/talk");
    expect(screen.getByTestId("keep-going-cards")).toHaveAttribute("href", "/review");
    expect(screen.getByTestId("keep-going-write")).toHaveAttribute("href", "/write");
    expect(panel.textContent).not.toMatch(/[0-9]/);
    expect(panel.textContent?.toLowerCase()).not.toMatch(/should|must|left|remaining/);
  });
});
