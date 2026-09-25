/**
 * W17 — a weak-spot drill inside block 3, rendered from the Python-generated
 * fixture (`scripts/export_drill_fixture.py`, held to the real wire by
 * `tests/test_drill_fixture.py` — #190).
 *
 * Red method, run before trusting it: remove the `item.pattern` branch in
 * `FocusBlock` — the drill tests fail (no `focus-drill`); render the count
 * instead of the label — the no-digit test fails.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SessionBlock, SessionToday } from "@/lib/api";

import { FocusBlock } from "./blocks";
import { DRILL_EYEBROW, SEEN_BEFORE } from "./copy";
import fixture from "./drill.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, answerItem: vi.fn() };
});

function focusOf(key: keyof typeof fixture): SessionBlock {
  const body = fixture[key] as unknown as SessionToday;
  return body.blocks.find((one) => one.kind === "focus")!;
}

describe("block 3 with a weak-spot drill (W17)", () => {
  it("serves the unit's item first, with no drill label on it", () => {
    render(<FocusBlock block={focusOf("session_unit_first")} sessionId={91} />);
    expect(screen.getByText("Practice · 1 of 3")).toBeInTheDocument();
    expect(screen.queryByTestId("focus-drill")).not.toBeInTheDocument();
  });

  it("names the drill's pattern in plain words, beside the eyebrow", () => {
    render(<FocusBlock block={focusOf("session_on_drill")} sessionId={91} />);
    const drill = screen.getByTestId("focus-drill");
    expect(drill).toHaveTextContent(DRILL_EYEBROW);
    expect(screen.getByTestId("focus-drill-pattern")).toHaveTextContent("Articles");
    expect(screen.getByText("Practice · 2 of 3")).toBeInTheDocument();
  });

  it("carries no count, no score and no reproach", () => {
    render(<FocusBlock block={focusOf("session_on_drill")} sessionId={91} />);
    const text = screen.getByTestId("focus-drill").textContent ?? "";
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/wrong|mistake|again|failed|missed|score|times/i);
  });

  it("says a drill met before was met before, and still names its pattern", () => {
    render(<FocusBlock block={focusOf("session_on_seen_drill")} sessionId={91} />);
    expect(screen.getByTestId("focus-drill-pattern")).toHaveTextContent("Subject and verb");
    expect(screen.getByText(SEEN_BEFORE)).toBeInTheDocument();
  });
});
