import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "@/components/write/write.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, startPractice: vi.fn(), answerPractice: vi.fn() };
});

const api = await import("@/lib/api");
const { Drill } = await import("./drill");

/**
 * W31d — the word drill. Bodies from `write.fixture.json` (the real models,
 * held to the wire by `tests/test_practice.py`, #190).
 *
 * **RED BEFORE W31d:** the component did not exist.
 */
describe("the word drill", () => {
  beforeEach(() => {
    vi.mocked(api.startPractice).mockReset();
    vi.mocked(api.answerPractice).mockReset();
    vi.mocked(api.startPractice).mockResolvedValue(fixture.practice_start as never);
  });

  it("starts with a picture and four words to choose from, the credit visible", async () => {
    render(<Drill />);
    expect(await screen.findByTestId("drill-prompt")).toHaveTextContent("Which word is this?");
    expect(screen.getAllByTestId("drill-option")).toHaveLength(4);
    expect(screen.getByTestId("card-image")).toHaveTextContent("A. Photographer");
    // The line is there, with the word gapped.
    expect(screen.getByTestId("drill-sentence")).toHaveTextContent("there's a _____ on the balcony.");
  });

  it("answers with the word and its whole line, and never a score", async () => {
    vi.mocked(api.answerPractice).mockResolvedValue(fixture.practice_right as never);
    const { container } = render(<Drill />);
    await userEvent.click((await screen.findAllByTestId("drill-option"))[1]);
    expect(vi.mocked(api.answerPractice)).toHaveBeenCalledWith(
      expect.objectContaining({ card_id: 501, kind: "picture_to_word", response: "parrot" }),
    );
    expect(await screen.findByTestId("drill-outcome")).toHaveTextContent("Yes — that's it.");
    expect(screen.getByTestId("drill-full-sentence")).toHaveTextContent(
      "there's a parrot on the balcony.",
    );
    expect(container.textContent).not.toMatch(/\d+\s*(of|\/)\s*\d+|score|points|streak/i);
  });

  it("says the word plainly when the answer was another one — no verdict about the learner", async () => {
    vi.mocked(api.answerPractice).mockResolvedValue(fixture.practice_wrong_typed as never);
    render(<Drill />);
    await userEvent.click((await screen.findAllByTestId("drill-option"))[0]);
    const outcome = await screen.findByTestId("drill-outcome");
    expect(outcome).toHaveTextContent("It's “band”.");
    expect(outcome.textContent).not.toMatch(/wrong|incorrect|failed|missed/i);
  });

  it("walks through all four kinds, then ends the round with a way back", async () => {
    vi.mocked(api.answerPractice).mockResolvedValue(fixture.practice_right as never);
    render(<Drill />);
    const kinds: string[] = [];
    for (let i = 0; i < 4; i += 1) {
      const drill = await screen.findByTestId("drill");
      kinds.push(drill.dataset.kind!);
      if (drill.dataset.kind === "hear_type" || drill.dataset.kind === "meaning_type") {
        await userEvent.type(screen.getByTestId("drill-input"), "band");
        await userEvent.click(screen.getByTestId("drill-check"));
      } else {
        await userEvent.click(screen.getAllByTestId("drill-option")[0]);
      }
      await userEvent.click(await screen.findByTestId("drill-next"));
    }
    expect(kinds).toEqual(["picture_to_word", "word_to_picture", "meaning_type", "hear_type"]);
    expect(await screen.findByTestId("drill-done")).toHaveTextContent("That's the round.");
    expect(screen.getByTestId("drill-back")).toHaveAttribute("href", "/review");
  });

  it("offers the word to hear, from our own API, with credentials", async () => {
    vi.mocked(api.startPractice).mockResolvedValue({
      exercises: [fixture.practice_start.exercises[3]],
    } as never);
    render(<Drill />);
    const audio = await screen.findByTestId("drill-audio");
    expect(audio.getAttribute("src")).toMatch(/\/practice\/504\/audio$/);
    expect(audio.getAttribute("crossorigin")).toBe("use-credentials");
  });

  it("says where words come from when there are none yet", async () => {
    vi.mocked(api.startPractice).mockResolvedValue(fixture.practice_start_empty as never);
    render(<Drill />);
    expect(await screen.findByTestId("drill-none")).toHaveTextContent(
      "Save a few words while watching and they'll turn up here.",
    );
  });
});
