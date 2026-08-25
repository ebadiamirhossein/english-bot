import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TypedAnswer from "./typed-answer";

/**
 * **The phone keyboard is a second grader**, and these four attributes are what
 * stop it grading. Autocorrect turning `dont` into `don't` before the server
 * sees it is a teaching bug: the acceptance criterion "typed items never
 * require punctuation or capitalisation to match" is about `fold_answer` being
 * permissive, not about iOS repairing the answer first.
 *
 * jsdom has no autocorrect and no viewport zoom, so this pins the attributes
 * and the human check on a real phone settles whether iOS honours them.
 */
function mount(over: Partial<Parameters<typeof TypedAnswer>[0]> = {}) {
  const onSubmit = vi.fn();
  const onDraft = vi.fn();
  render(
    <TypedAnswer
      draft={{}}
      onDraft={onDraft}
      onSubmit={onSubmit}
      submitting={false}
      answered={false}
      {...over}
    />,
  );
  return { onSubmit, onDraft };
}

describe("the typed answer input", () => {
  it("refuses every form of keyboard help", () => {
    mount();
    const input = screen.getByTestId("typed-answer-input");
    expect(input).toHaveAttribute("autocapitalize", "off");
    expect(input).toHaveAttribute("autocorrect", "off");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAttribute("spellcheck", "false");
  });

  it("is set at 16px or larger, so focusing it does not zoom the page", () => {
    // Below 16px iOS Safari zooms the viewport on focus. That is a layout shift
    // in the middle of typing a sentence, which is the third human check.
    mount();
    expect(screen.getByTestId("typed-answer-input").className).toContain(
      "text-base",
    );
  });

  it("cannot be submitted empty", async () => {
    // User action: tapping Check having typed nothing.
    mount();
    expect(screen.getByRole("button", { name: "Check" })).toBeDisabled();
  });

  it("sends what was typed, verbatim — no trimming, folding or casing", async () => {
    // User action: typing an answer with a capital and a full stop.
    //
    // The server folds; this side must not, or there would be two definitions
    // of "the answer" and `item_attempts.response_text` would stop recording
    // what the learner actually typed.
    const { onSubmit } = mount({ draft: { text: "  Went.  " } });
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(onSubmit).toHaveBeenCalledWith({ text: "  Went.  " });
  });

  it("submits on the keyboard's done key", async () => {
    // User action: pressing return instead of reaching for the button.
    const { onSubmit } = mount({ draft: { text: "went" } });
    await userEvent.type(screen.getByTestId("typed-answer-input"), "{enter}");
    expect(onSubmit).toHaveBeenCalledWith({ text: "went" });
  });

  it("locks once graded, so the same encounter cannot be answered twice", () => {
    mount({ draft: { text: "went" }, answered: true });
    expect(screen.getByTestId("typed-answer-input")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
  });
});
