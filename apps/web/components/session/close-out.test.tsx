/**
 * W13b/4 — the close-out.
 *
 * **THIS SURFACE HAD NO TEST OF ANY KIND UNTIL THE PREVIOUS COMMIT**, having
 * rendered since W13b/2 with nothing in the suite opening it. That is the same
 * condition that let `did_well` be generated, billed and discarded for a month:
 * nobody looked, and nothing made looking mandatory.
 *
 * **#345 GOVERNS EVERY ASSERTION HERE.** No accepted-value set contains the
 * assertion's own failure mode — no `toBeNull()` standing in for "the feature
 * is off", no `x || fallback` inside an `expect`. Where a thing must be absent,
 * a sibling assertion proves the surface rendered at all, so "absent" cannot be
 * satisfied by "nothing rendered".
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CloseOut } from "./close-out";
import { CONVERSATION } from "./copy";

const CORRECTIONS = [
  {
    you_said: "she marry last month",
    correct_form: "she got married last month",
    explanation: "Past simple, and the verb is reflexive here.",
  },
  {
    you_said: "we sit outside for the dinner",
    correct_form: "we sat outside for dinner",
    explanation: "Past simple, and no article before the meal.",
  },
];

function mount(props: Partial<React.ComponentProps<typeof CloseOut>> = {}) {
  const merged = {
    topic: "A wedding you went to recently",
    summary:
      "You talked about a colleague's wedding in a garden last month — the weather, dinner outside, and the dancing afterwards.",
    didWell: "Your past tense held up across the whole story.",
    corrections: CORRECTIONS,
    words: ["reception", "to toast"],
    kept: {},
    capped: false,
    busy: false,
    onKeep: vi.fn(),
    ...props,
  } as React.ComponentProps<typeof CloseOut>;
  render(<CloseOut {...merged} />);
  return merged;
}

afterEach(() => vi.clearAllMocks());

describe("the close-out", () => {
  it("leads with what was talked about and what went well, before any fix", () => {
    // **PAYOFF FIRST IS THE DESIGN'S ORDERING AND IT IS ASSERTED AS ORDER**,
    // not as presence — a close-out that opened with the corrections would
    // still pass a presence test while leading with a fix.
    mount();
    const surface = screen.getByTestId("conversation-closed");
    const text = surface.textContent ?? "";

    const topicAt = text.indexOf("A wedding you went to recently");
    const wellAt = text.indexOf("Your past tense held up");
    const lookAt = text.indexOf(CONVERSATION.correctionsHeading);
    const wordsAt = text.indexOf(CONVERSATION.wordsHeading);

    // Each index is asserted found on its own, so a missing section cannot
    // satisfy the ordering by returning -1 (#345).
    expect(topicAt).toBeGreaterThan(-1);
    expect(wellAt).toBeGreaterThan(-1);
    expect(lookAt).toBeGreaterThan(-1);
    expect(wordsAt).toBeGreaterThan(-1);

    expect(topicAt).toBeLessThan(wellAt);
    expect(wellAt).toBeLessThan(lookAt);
    expect(lookAt).toBeLessThan(wordsAt);
  });

  it("shows what the learner did well, which the surface used to discard", () => {
    mount();
    expect(screen.getByTestId("conversation-did-well")).toHaveTextContent(
      "Your past tense held up across the whole story.",
    );
  });

  it("renders no did-well element at all when there is nothing to say", () => {
    // **ABSENT, NOT BLANK.** `did_well` is `str` on the wire, so an empty note
    // arrives as `""`; `"   "` is what that looks like before trimming.
    //
    // **THE SIBLING ASSERTION IS #345's REQUIREMENT:** without it this test
    // passes when the whole component renders nothing.
    mount({ didWell: "   " });
    expect(screen.getByTestId("conversation-closed")).toBeInTheDocument();
    expect(screen.queryByTestId("conversation-did-well")).toBeNull();
  });

  it("marks the app's voice and the learner's by attribute, never by colour", () => {
    // The correction pairs the learner's sentence against the app's. **A test
    // that pinned a class would assert Tailwind**, and would pass on a palette
    // where the two look identical — which is exactly what shipped in the chat.
    mount();
    const first = screen.getAllByTestId("conversation-correction")[0];
    const said = within(first).getByTestId("correction-said");
    const better = within(first).getByTestId("correction-better");
    expect(said).toHaveAttribute("data-speaker", "you");
    expect(better).toHaveAttribute("data-speaker", "app");
    expect(said).toHaveTextContent("she marry last month");
    expect(better).toHaveTextContent("she got married last month");
  });

  it("shows the words bare, with no definition line, because there is none", () => {
    // **UNMET, REPORTED, NOT APPROXIMATED.** `unknown_words` is `list[str]`.
    // `save_conversation_word`'s own docstring rules out generating a gloss:
    // *a conversation word has no gloss row and no video*, and generating one
    // would breach the half of the 2026-08-27 ruling still standing.
    //
    // Asserted as "the row holds the word and nothing else" rather than as the
    // absence of an element that was never named — an absence test over an
    // element with no name passes whatever happens (#345).
    mount({ words: ["reception"] });
    const row = screen.getByTestId("conversation-word");
    expect(row).toHaveTextContent("reception");
    expect(within(row).getByRole("button")).toHaveTextContent(CONVERSATION.save);
    expect(row.textContent?.replace("reception", "").trim()).toBe(
      CONVERSATION.save,
    );
  });

  it("offers each word to the deck, and says so once it is kept", async () => {
    const user = userEvent.setup();
    const props = mount({ words: ["reception"] });
    await user.click(screen.getByRole("button", { name: CONVERSATION.save }));
    expect(props.onKeep).toHaveBeenCalledWith("reception");
  });

  it("shows a kept word as kept, and stops offering it", () => {
    mount({ words: ["reception"], kept: { reception: true } });
    const row = screen.getByTestId("conversation-word");
    expect(row).toHaveTextContent(CONVERSATION.saved);
    expect(within(row).getByRole("button")).toBeDisabled();
  });

  it("opens on the cap line when the cap is what ended it", () => {
    mount({ capped: true });
    expect(screen.getByTestId("conversation-closed")).toHaveTextContent(
      CONVERSATION.capReached,
    );
  });

  it("says so plainly when there is nothing to show, rather than empty headings", () => {
    mount({ didWell: "", summary: "", corrections: [], words: [] });
    const surface = screen.getByTestId("conversation-closed");
    expect(surface).toHaveTextContent(CONVERSATION.closeNothing);
    expect(surface).not.toHaveTextContent(CONVERSATION.correctionsHeading);
    expect(surface).not.toHaveTextContent(CONVERSATION.wordsHeading);
  });

  it("puts no numeral on the screen, whatever the close returns", () => {
    // #348 on the rendered surface rather than in `copy.ts`. The payload has
    // two corrections and two words — things a tally would count.
    mount();
    const text = screen.getByTestId("conversation-closed").textContent ?? "";
    expect(text.length).toBeGreaterThan(0);
    expect(text).not.toMatch(/[0-9]/);
  });

  it("carries no count, no duration and no score", () => {
    // The words #160 and CLAUDE.md §4 forbid on a surface that has just ended
    // something. Asserted on the rendered text, in one place, so a later
    // section cannot reintroduce one unnoticed.
    mount();
    const text = (screen.getByTestId("conversation-closed").textContent ?? "")
      .toLowerCase();
    expect(text.length).toBeGreaterThan(0);
    for (const banned of ["minute", "turn", "score", "streak", "total", "out of"]) {
      expect(text).not.toContain(banned);
    }
  });
});


/**
 * W13b/6 — the recap, and the heading that was wrong about the learner.
 */
describe("the close-out's recap", () => {
  it("opens on what was talked about, before anything that reads as a fix", () => {
    // **DESIGN `1i`'s ORDERING, AND IT IS NOW COMPLETE.** W13b/4 built the
    // card without this line because `CloseOut` refused to carry the field;
    // the refusal was overturned on 2026-09-08 once a real summary could be
    // read. Asserted as ORDER, like `did_well` — a recap printed below the
    // corrections would still pass a presence test.
    mount();
    const text = screen.getByTestId("conversation-closed").textContent ?? "";
    const summaryAt = text.indexOf("You talked about a colleague");
    const wellAt = text.indexOf("Your past tense held up");
    const lookAt = text.indexOf(CONVERSATION.correctionsHeading);
    expect(summaryAt).toBeGreaterThan(-1);
    expect(wellAt).toBeGreaterThan(-1);
    expect(lookAt).toBeGreaterThan(-1);
    expect(summaryAt).toBeLessThan(wellAt);
    expect(wellAt).toBeLessThan(lookAt);
  });

  it("renders no recap element at all when the summary is empty", () => {
    // Absent, never blank — the same rule as `did_well`, and the #345 sibling
    // proving the surface rendered so "absent" cannot be met by "nothing".
    mount({ summary: "   " });
    expect(screen.getByTestId("conversation-closed")).toBeInTheDocument();
    expect(screen.queryByTestId("close-summary-text")).toBeNull();
  });

  it("does not tell the learner he asked for the words, because he did not", () => {
    // **#403.** The heading read *"Words you asked about"* — the design's
    // phrase for an interaction this app does not have. The words are DETECTED
    // from his own typed turns against his ledger; nothing was requested.
    //
    // Expected values are literal, never read back from `CONVERSATION`
    // (CLAUDE.md §3 rule 5) — reading the constant would pass whatever it said.
    mount({ words: ["reception"] });
    const text = screen.getByTestId("conversation-closed").textContent ?? "";
    expect(text).toContain("Worth keeping");
    expect(text).not.toContain("you asked about");
    expect(text.toLowerCase()).not.toContain("didn\u2019t know");
  });
});
