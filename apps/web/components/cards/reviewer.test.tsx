import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CardFace as CardFaceData } from "@/lib/api";

import { CardFace } from "./card-face";
import { GradeButtons } from "./grade-buttons";

function card(over: Partial<CardFaceData> = {}): CardFaceData {
  return {
    id: 1,
    card_type: "cloze",
    front: "I _____ to the shops yesterday.",
    back: "went",
    cue: null,
    context_sentence: "I went to the shops yesterday and it was shut.",
    source_ref: "himym_s2e4",
    meaning: "past of go",
    register: "neutral",
    neutral_equivalent: null,
    who_says_this: null,
    intervals: { again: 0, hard: 3, good: 7, easy: 15 },
    ...over,
  };
}

/**
 * The card face. PRD §5's provenance rule and §8.5.4's four things.
 *
 * These assert the properties the schema is *for* — not the styling. Migration
 * 013 refuses to store an informal/slang card without all four fields, so the
 * component's job is to show them, and a component that quietly dropped one
 * would make the CHECK pointless.
 */
describe("card face", () => {
  it("keeps the back hidden until it is revealed", () => {
    render(<CardFace card={card()} revealed={false} />);
    expect(screen.queryByTestId("card-back")).toBeNull();
  });

  it("shows the back once revealed", () => {
    render(<CardFace card={card()} revealed />);
    expect(screen.getByTestId("card-back").textContent).toContain("went");
  });

  it("carries the sentence it came from and where it came from", () => {
    render(<CardFace card={card()} revealed={false} />);
    const context = screen.getByTestId("card-context").textContent ?? "";
    expect(context).toContain("I went to the shops yesterday");
    expect(context).toContain("himym_s2e4");
  });

  it("shows all of PRD §8.5.4's four things on a slang card", () => {
    render(
      <CardFace
        card={card({
          register: "slang",
          front: "That's a hard pass.",
          back: "hard pass",
          meaning: "a firm refusal",
          neutral_equivalent: "I'd rather not, thanks",
          who_says_this: "Friends and casual colleagues. Not in a client email.",
        })}
        revealed
      />,
    );
    // the line it came from, the meaning, the neutral equivalent, who says it
    expect(screen.getByTestId("card-context")).toBeTruthy();
    expect(screen.getByTestId("card-back").textContent).toContain(
      "a firm refusal",
    );
    expect(screen.getByTestId("card-neutral").textContent).toContain(
      "I'd rather not, thanks",
    );
    expect(screen.getByTestId("card-who-says").textContent).toContain(
      "client email",
    );
  });

  it("shows no register panel on a neutral card", () => {
    render(<CardFace card={card()} revealed />);
    expect(screen.queryByTestId("card-register-panel")).toBeNull();
  });

  it("hides the leech cue once the answer is on screen", () => {
    const leeched = card({ cue: "w___ (4)" });
    const { rerender } = render(<CardFace card={leeched} revealed={false} />);
    expect(screen.getByTestId("card-cue").textContent).toContain("w___");
    rerender(<CardFace card={leeched} revealed />);
    expect(screen.queryByTestId("card-cue")).toBeNull();
  });
});

/**
 * The four grades.
 *
 * The interval assertions are the load-bearing ones: they prove the numbers
 * come from the payload and are not recomputed here. A component that did its
 * own arithmetic would pass a "four buttons render" test and still show a
 * learner a schedule the database disagrees with.
 */
describe("grade buttons", () => {
  it("renders exactly the four FSRS grades, in order", () => {
    render(<GradeButtons card={card()} disabled={false} onGrade={() => {}} />);
    const labels = Array.from(
      screen.getByTestId("grade-buttons").querySelectorAll("button"),
    ).map((b) => b.textContent);
    expect(labels).toHaveLength(4);
    expect(labels[0]).toContain("Again");
    expect(labels[1]).toContain("Hard");
    expect(labels[2]).toContain("Good");
    expect(labels[3]).toContain("Easy");
  });

  it("renders the server's interval for each button and computes none itself", () => {
    // Deliberately not FSRS-shaped numbers. If the component derived them, it
    // could not reproduce these.
    render(
      <GradeButtons
        card={card({ intervals: { again: 0, hard: 2, good: 41, easy: 400 } })}
        disabled={false}
        onGrade={() => {}}
      />,
    );
    expect(screen.getByTestId("grade-again").textContent).toContain("today");
    expect(screen.getByTestId("grade-hard").textContent).toContain("2 days");
    expect(screen.getByTestId("grade-good").textContent).toContain("41 days");
    expect(screen.getByTestId("grade-easy").textContent).toContain("13 months");
    expect(
      screen.getByTestId("grade-easy").getAttribute("data-interval-days"),
    ).toBe("400");
  });

  it("reports the rating by name, never as a number", async () => {
    const onGrade = vi.fn();
    render(<GradeButtons card={card()} disabled={false} onGrade={onGrade} />);
    await userEvent.click(screen.getByTestId("grade-good"));
    expect(onGrade).toHaveBeenCalledWith("good");
  });

  it("refuses a second tap while a grade is in flight", async () => {
    const onGrade = vi.fn();
    render(<GradeButtons card={card()} disabled onGrade={onGrade} />);
    await userEvent.click(screen.getByTestId("grade-good"));
    expect(onGrade).not.toHaveBeenCalled();
  });
});
