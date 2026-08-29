import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Checkpoint } from "@/lib/api";

import { CHECKPOINT } from "./copy";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getCheckpointToday: vi.fn(), completeCheckpoint: vi.fn() };
});

const api = await import("@/lib/api");
const { CheckpointRunner } = await import("./runner");
const { SaturdayLink } = await import("./saturday-link");

function sitting(over: Partial<Checkpoint> = {}): Checkpoint {
  return {
    session_id: 11,
    unit_number: 1,
    can_do: "I can tell a friend what I did yesterday.",
    item_count: 12,
    state: "ready",
    items: [],
    passed: null,
    score_pct: null,
    retake_due_on: null,
    ...over,
  };
}

/**
 * **The assertions this file exists for are the two on the not-passed path.**
 * *Drops are silent, raises are announced* — so a pass may say what it scored
 * and a miss may not, and neither a fraction nor a bar may appear anywhere on
 * the screen when a unit was not passed.
 */
describe("the checkpoint's verdict", () => {
  it("announces a pass and says what it scored", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "done", passed: true, score_pct: 100 }),
    );
    render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-passed")).toBeTruthy(),
    );
    expect(screen.getByText(CHECKPOINT.passed.title)).toBeTruthy();
    expect(document.body.textContent).toContain("12 of 12");
  });

  it("shows NO score and NO fraction when the unit was not passed", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({
        state: "done",
        passed: false,
        score_pct: null,
        retake_due_on: "2026-09-09",
      }),
    );
    render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-not-yet")).toBeTruthy(),
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+\s*(of|\/)\s*12/);
    expect(text).not.toContain("%");
    expect(text).not.toContain("80");
  });

  it("renders no progress bar or meter on either path", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "done", passed: false, retake_due_on: "2026-09-09" }),
    );
    const { container } = render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-not-yet")).toBeTruthy(),
    );
    expect(container.querySelector("progress")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("survives a missing retake date rather than printing undefined", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "done", passed: false, retake_due_on: null }),
    );
    render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-not-yet")).toBeTruthy(),
    );
    expect(document.body.textContent).not.toContain("undefined");
    expect(document.body.textContent).toContain("a few days");
  });
});

describe("a checkpoint the bank could not fill", () => {
  it("says so, and offers no short sitting in its place", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "not_ready", items: [] }),
    );
    render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-not-ready")).toBeTruthy(),
    );
    expect(screen.getByText(CHECKPOINT.notReady.title)).toBeTruthy();
  });

  it("names no count of what is missing", async () => {
    // #160: no surface presents a backlog. "4 of 12 ready" would be one.
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "not_ready" }),
    );
    render(<CheckpointRunner />);
    await waitFor(() =>
      expect(screen.getByTestId("checkpoint-not-ready")).toBeTruthy(),
    );
    expect(document.body.textContent).not.toMatch(/\d/);
  });
});

describe("Saturday's link on home", () => {
  it("renders nothing when there is no sitting to go to", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "not_ready" }),
    );
    const { container } = render(<SaturdayLink />);
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("renders nothing when the sitting is already done", async () => {
    // Re-offering a finished checkpoint reads as unfinished work.
    vi.mocked(api.getCheckpointToday).mockResolvedValue(
      sitting({ state: "done", passed: true, score_pct: 100 }),
    );
    const { container } = render(<SaturdayLink />);
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("links to the checkpoint when one is ready", async () => {
    vi.mocked(api.getCheckpointToday).mockResolvedValue(sitting());
    render(<SaturdayLink />);
    await waitFor(() =>
      expect(screen.getByTestId("saturday-checkpoint-link")).toBeTruthy(),
    );
    expect(
      screen.getByTestId("saturday-checkpoint-link").getAttribute("href"),
    ).toBe("/checkpoint");
  });

  it("stays silent when the call fails — home must still open", async () => {
    vi.mocked(api.getCheckpointToday).mockRejectedValue(new Error("offline"));
    const { container } = render(<SaturdayLink />);
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
