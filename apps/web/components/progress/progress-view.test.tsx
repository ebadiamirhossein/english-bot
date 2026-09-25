import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Progress } from "@/lib/api";

import fixture from "./progress.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getProgress: vi.fn() };
});

const api = await import("@/lib/api");
const { ProgressView } = await import("./progress-view");

/**
 * W19's client half, rendered from `progress.fixture.json` — bodies built by
 * `scripts/export_progress_fixture.py` through the route's own serialiser and
 * held to a real ASGI body by `tests/test_progress_fixture.py` (#190).
 *
 * **Every "no zero" assertion is paired with a positive control** (#345): a
 * scan over a component that rendered nothing passes whether the rule holds or
 * the component is broken.
 *
 * **RED DEMONSTRATIONS (2026-09-25):** "draws no number at all for a learner in
 * week one" went red with the `xp > 0` guard removed (`0` on screen); "does not
 * draw a line from one point" went red with the `known_history.length >= 2`
 * test changed to `>= 1`; "draws the line from the count's history" went red
 * with `KnownLine` returning null; "draws no freezes line when none are held"
 * went red with the `freezes > 0` guard removed (the `no_freezes` body then
 * drew a freezes line for zero); "offers a way back after a failed load" went red
 * with the retry button's `onClick` removed.
 */

const EMPTY = fixture.empty as Progress;
const FIRST = fixture.first_day as Progress;
const WEEKS = fixture.weeks_in as Progress;
const NO_FREEZES = fixture.no_freezes as Progress;

/** Words that would turn a progress screen into a verdict. */
const VERDICT = /missed|behind|\bleft\b|\blost\b|remaining|score|rank|partner|failed|wrong|keep it up/i;

async function open(body: Progress) {
  vi.mocked(api.getProgress).mockResolvedValue(body);
  const view = render(<ProgressView />);
  await waitFor(() =>
    expect(screen.getByTestId("progress-screen").dataset.phase).toBe("ready"),
  );
  return view;
}

function digits(container: HTMLElement): string[] {
  return (container.textContent ?? "").match(/\d+/g) ?? [];
}

describe("the progress screen", () => {
  it("draws no number at all for a learner in week one", async () => {
    const { container } = await open(EMPTY);
    // Positive control: the empty state really rendered.
    expect(screen.getByTestId("progress-empty")).toHaveTextContent(
      "Nothing to show yet. This fills in as you practise.",
    );
    expect(digits(container)).toEqual([]);
    expect(screen.queryByTestId("progress-words")).toBeNull();
    expect(screen.queryByTestId("progress-streak")).toBeNull();
  });

  it("draws each number that is above zero, with what it counts", async () => {
    await open(WEEKS);
    expect(screen.getByTestId("progress-words-number")).toHaveTextContent("164");
    expect(screen.getByTestId("progress-xp")).toHaveTextContent("1,246");
    expect(screen.getByTestId("progress-xp")).toHaveTextContent(
      "Speaking earns the most, then writing, then typing, then tapping.",
    );
    expect(screen.getByTestId("progress-streak")).toHaveTextContent("23days of practice");
    expect(screen.getByTestId("progress-streak")).toHaveTextContent(
      "A day off doesn’t break it.",
    );
    expect(screen.getByTestId("progress-units")).toHaveTextContent("2units passed");
  });

  it("does not draw a line from one point", async () => {
    await open(FIRST);
    expect(screen.getByTestId("progress-words-number")).toHaveTextContent("12");
    expect(screen.queryByTestId("progress-words-line")).toBeNull();
    expect(screen.getByTestId("progress-words-first")).toHaveTextContent(
      "Each visit here adds a point, and the line starts from the second.",
    );
  });

  it("draws the line from the count's history, one vertex per point", async () => {
    await open(WEEKS);
    const line = screen.getByTestId("progress-words-line");
    const polyline = line.querySelector("polyline");
    expect(polyline).not.toBeNull();
    expect(polyline!.getAttribute("points")!.trim().split(/\s+/)).toHaveLength(
      WEEKS.known_history.length,
    );
    expect(line.querySelector("svg")).toHaveAttribute("aria-label", "Words you know over time");
    // The two ends are labelled with their dates.
    expect(line).toHaveTextContent("9 Sept");
    expect(line).toHaveTextContent("14 Oct");
  });

  it("shows freezes only when there are some", async () => {
    await open(WEEKS);
    expect(screen.getByTestId("progress-freezes")).toHaveTextContent(
      "One freeze this month covers a day you can’t make it.",
    );
  });

  it("draws no freezes line when none are held", async () => {
    await open(NO_FREEZES);
    // Positive control: the streak card is there.
    expect(screen.getByTestId("progress-streak")).toBeInTheDocument();
    expect(screen.queryByTestId("progress-freezes")).toBeNull();
  });

  it("says the radar and level history arrive with placement, and draws neither", async () => {
    await open(WEEKS);
    expect(screen.getByTestId("progress-later")).toHaveTextContent(
      "Your skill profile and level history arrive with the placement test.",
    );
  });

  it.each([
    ["empty", EMPTY],
    ["first_day", FIRST],
    ["weeks_in", WEEKS],
    ["no_freezes", NO_FREEZES],
  ])("carries no word that reads as a verdict (%s)", async (_name, body) => {
    const { container } = await open(body as Progress);
    expect(container.textContent).not.toBe("");
    expect(container.textContent ?? "").not.toMatch(VERDICT);
  });

  it("offers a way back after a failed load", async () => {
    vi.mocked(api.getProgress).mockRejectedValueOnce(new Error("down"));
    render(<ProgressView />);
    await waitFor(() =>
      expect(screen.getByTestId("progress-screen").dataset.phase).toBe("problem"),
    );
    expect(screen.getByTestId("progress-problem")).toHaveTextContent(
      "That didn’t load. Nothing’s lost.",
    );
    vi.mocked(api.getProgress).mockResolvedValueOnce(WEEKS);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(screen.getByTestId("progress-screen").dataset.phase).toBe("ready"),
    );
  });
});
