import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "@/components/write/write.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getMyWords: vi.fn() };
});

const api = await import("@/lib/api");
const { MyWords } = await import("./my-words");

/**
 * W31c — My words. The bodies are `write.fixture.json`'s, built through the
 * real `MyWordsOut` and held to the wire by `tests/test_word_saves.py` (#190).
 *
 * **RED BEFORE W31c:** the component did not exist.
 */
describe("My words", () => {
  beforeEach(() => {
    vi.mocked(api.getMyWords).mockReset();
  });

  it("lists each saved word with its sentence and a plain state", async () => {
    vi.mocked(api.getMyWords).mockResolvedValue(fixture.my_words as never);
    render(<MyWords />);
    const rows = await screen.findAllByTestId("my-word");
    expect(rows.map((r) => r.dataset.state)).toEqual(["pending", "in_deck", "no_meaning"]);
    expect(rows[0]).toHaveTextContent("basement");
    expect(rows[0]).toHaveTextContent("meaning coming");
    expect(rows[1]).toHaveTextContent("in your cards");
    expect(rows[2]).toHaveTextContent("no meaning found");
    expect(rows[0]).toHaveTextContent("we found it in the museum's basement.");
  });

  it("never shows a count, a total or a backlog (#160)", async () => {
    vi.mocked(api.getMyWords).mockResolvedValue(fixture.my_words as never);
    const { container } = render(<MyWords />);
    await screen.findAllByTestId("my-word");
    expect(container.textContent).not.toMatch(/\d+\s*(words?|left|to go|waiting|saved)/i);
    expect(container.textContent).not.toMatch(/total|remaining|backlog/i);
  });

  it("says where saved words will appear when there are none", async () => {
    vi.mocked(api.getMyWords).mockResolvedValue(fixture.my_words_empty as never);
    render(<MyWords />);
    expect(await screen.findByTestId("my-words-empty")).toHaveTextContent(
      "Words you save from videos will appear here.",
    );
  });

  it("asks for the next page by time, and adds it below", async () => {
    vi.mocked(api.getMyWords)
      .mockResolvedValueOnce({ ...(fixture.my_words as object), next_before: "2026-09-26T20:40:00Z" } as never)
      .mockResolvedValueOnce({
        words: [{ word: "nickname", state: "in_deck", saved_at: "2026-09-25T10:00:00Z" }],
      });
    render(<MyWords />);
    await userEvent.click(await screen.findByTestId("my-words-more"));
    expect(vi.mocked(api.getMyWords)).toHaveBeenLastCalledWith("2026-09-26T20:40:00Z");
    expect((await screen.findAllByTestId("my-word")).at(-1)).toHaveTextContent("nickname");
    expect(screen.queryByTestId("my-words-more")).toBeNull();
  });
});
