import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ItemAnswerResult } from "@/lib/api";

import { Feedback } from "./feedback";

function result(over: Partial<ItemAnswerResult> = {}): ItemAnswerResult {
  return {
    correct: false,
    graded_by: "deterministic",
    canonical: "went",
    explanation: null,
    murphy_units: null,
    ...over,
  };
}

/**
 * The copy a learner reads after getting one wrong is the highest-risk string
 * in the app, and the source scan over `.tsx` is a blunt instrument. This looks
 * at what actually renders.
 */
describe("wrong-answer copy", () => {
  it("names no verdict on the person", () => {
    render(<Feedback result={result()} />);
    expect(screen.getByTestId("feedback").textContent ?? "").not.toMatch(
      /\bwrong\b|\bincorrect\b|\bmissed\b|\bfailed\b|should have|try harder/i,
    );
  });

  it("puts the emphasis on the better version", () => {
    render(<Feedback result={result()} />);
    expect(screen.getByTestId("feedback")).toHaveTextContent("went");
  });

  it("uses no red and strikes nothing through", () => {
    const { container } = render(<Feedback result={result()} />);
    expect(container.innerHTML).not.toMatch(
      /line-through|text-red|bg-red|border-red|destructive/,
    );
  });

  it("says something different for a self-marked attempt", () => {
    // `graded_by` exists so an accuracy number never silently mixes a string
    // match with someone's own judgement. The learner should see the
    // difference too.
    render(<Feedback result={result({ graded_by: "self", canonical: null })} />);
    expect(screen.getByTestId("feedback").textContent ?? "").not.toContain(
      "Not quite",
    );
  });
});
