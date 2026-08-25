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
 * The box a learner reads to find out how they did. W6 shipped it as a flat
 * tinted rectangle and the human named it as the weakest thing in the slice, so
 * these assert the properties the redesign is *for* — not the styling.
 */
describe("wrong-answer copy", () => {
  it("names no verdict on the person", () => {
    render(<Feedback result={result()} />);
    expect(screen.getByTestId("feedback").textContent ?? "").not.toMatch(
      /\bwrong\b|\bincorrect\b|\bmissed\b|\bfailed\b|should have|try harder/i,
    );
  });

  it("renders the canonical when the answer was wrong", () => {
    // **The assertion the box exists for.** If this stops holding, the learner
    // is told they were not right and never shown what right was — which is the
    // shape #112 took on `match_pairs` in production.
    render(<Feedback result={result({ canonical: "went" })} />);
    expect(screen.getByTestId("feedback-canonical")).toHaveTextContent("went");
  });

  it("sets the canonical larger than the lead-in", () => {
    // The answer is what the learner is here to read, so the box is built
    // around it rather than beside it. jsdom does not lay out, so this pins the
    // relationship; a person on a phone settles whether it reads at a glance.
    render(<Feedback result={result()} />);
    const canonical = screen.getByTestId("feedback-canonical");
    expect(canonical.className).toContain("text-2xl");
    expect(canonical.className).toContain("font-heading");
  });

  it("uses no red and strikes nothing through", () => {
    const { container } = render(<Feedback result={result()} />);
    expect(container.innerHTML).not.toMatch(
      /line-through|text-red|bg-red|border-red|destructive/,
    );
    expect(container.innerHTML).not.toContain("✗");
  });

  it("tells right from wrong without relying on colour", () => {
    // Filled versus outlined, and one line versus two tiers. A treatment that
    // depended on hue alone would fail anyone who cannot separate the two — and
    // the palette has no red in it to depend on anyway.
    const right = render(<Feedback result={result({ correct: true })} />);
    const rightBox = screen.getByTestId("feedback");
    expect(rightBox.className).toContain("bg-accent");
    expect(rightBox.className).not.toContain("border-l-4");
    right.unmount();

    render(<Feedback result={result()} />);
    const wrongBox = screen.getByTestId("feedback");
    expect(wrongBox.className).toContain("border-l-4");
    expect(wrongBox.className).not.toContain("bg-accent");
  });

  it("reserves enough height that Next cannot land under the thumb", () => {
    // The "Check" button is h-14 and vanishes when the verdict arrives; this
    // box takes its place and Next renders below it. A short box would put Next
    // where the finger just was, so an eager second tap skips the feedback.
    for (const r of [result(), result({ correct: true }), result({ graded_by: "self" })]) {
      const view = render(<Feedback result={r} />);
      expect(screen.getByTestId("feedback").className).toContain("min-h-20");
      view.unmount();
    }
  });
});

describe("a self-mark is not a verdict (#113)", () => {
  it("never renders the graded-correct string", () => {
    // W6 replied "👍 That's it." when the learner tapped "Got it" on
    // `speak_answer` — the same confirmation a graded answer gets, for an
    // answer nothing checked. No microphone is opened in W6.
    render(<Feedback result={result({ correct: true, graded_by: "self", canonical: null })} />);
    const box = screen.getByTestId("feedback");
    expect(box.textContent ?? "").not.toContain("That’s it.");
    expect(box.textContent ?? "").not.toContain("That's it.");
    expect(box).toHaveTextContent("Noted.");
  });

  it("shows no thumb, because the thumb is a verdict", () => {
    render(<Feedback result={result({ correct: true, graded_by: "self", canonical: null })} />);
    expect(screen.getByTestId("feedback").textContent ?? "").not.toContain("👍");
  });

  it("keeps the line saying scoring arrives later", () => {
    // It lived on the answer control, which unmounts once answered — so the
    // learner would otherwise lose the only statement that this was not scored.
    render(<Feedback result={result({ correct: true, graded_by: "self", canonical: null })} />);
    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Pronunciation scoring comes later.",
    );
  });

  it("reads the same whichever way the learner marked themselves", () => {
    // "Got it" and "Not yet" are both records, not judgements. `graded_by`
    // keeps them separable in the data; the copy keeps them honest on screen.
    for (const correct of [true, false]) {
      const view = render(
        <Feedback result={result({ correct, graded_by: "self", canonical: null })} />,
      );
      expect(screen.getByTestId("feedback")).toHaveTextContent("Noted.");
      expect(screen.getByTestId("feedback")).toHaveAttribute(
        "data-graded-by",
        "self",
      );
      view.unmount();
    }
  });
});

describe("the box never promises what it cannot show (#112)", () => {
  it("drops the lead-in when there is no canonical to follow it", () => {
    // Reproduced on production 2026-08-25: `match_pairs` graded wrong rendered
    // "Not quite. Here it is:" and then nothing, because its correct answer is
    // a mapping and `items.answer IS NULL` by schema rule. Telling a learner
    // the answer is coming and not showing it is worse than not offering.
    render(<Feedback result={result({ canonical: null })} />);
    const box = screen.getByTestId("feedback");
    expect(box.textContent ?? "").not.toContain("Here it is:");
    expect(box).toHaveTextContent("Not quite.");
    expect(box).toHaveAttribute("data-shows-answer", "false");
    expect(screen.queryByTestId("feedback-canonical")).toBeNull();
  });

  it("keeps the lead-in when there is one", () => {
    render(<Feedback result={result({ canonical: "went" })} />);
    expect(screen.getByTestId("feedback")).toHaveTextContent("Not quite. Here it is:");
    expect(screen.getByTestId("feedback")).toHaveAttribute(
      "data-shows-answer",
      "true",
    );
  });
});
