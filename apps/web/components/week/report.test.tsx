import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Week } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getWeek: vi.fn() };
});

const api = await import("@/lib/api");
const { WeekReport } = await import("./report");
const { SundayHome } = await import("./sunday-home");

/**
 * W11b's client half.
 *
 * **What these assert that the Python suite cannot:** that no numeric zero is
 * on the screen, that Sunday's home carries no session call-to-action, and that
 * the other six days are unchanged.
 *
 * **The no-zero assertions are paired with a positive control, always.** A scan
 * for "0" over a component that rendered nothing passes whether the rule holds
 * or the component is broken — an assertion whose accepted outcome contains its
 * own failure mode (#345). So every "there is no zero" test also names a number
 * that IS on the screen, or the specific empty-state line.
 */

function week(over: Partial<Week> = {}): Week {
  return {
    week_ending: "2026-08-30",
    sunday: true,
    days_with_a_session: 0,
    items_answered: 0,
    items_right: 0,
    cards_reviewed: 0,
    words_now_known: 0,
    units_passed: 0,
    empty: true,
    ...over,
  };
}

/** Every digit on the screen, so a zero cannot hide inside a longer number. */
function digits(container: HTMLElement): string[] {
  return (container.textContent ?? "").match(/\d+/g) ?? [];
}

describe("the report", () => {
  it("renders one line and no number at all on an empty week", () => {
    const { container } = render(<WeekReport week={week()} />);
    // The positive control: the empty state really did render.
    expect(screen.getByTestId("week-empty")).toHaveTextContent(
      "Nothing to report yet.",
    );
    expect(digits(container)).toEqual([]);
  });

  it("never renders a zero beside a real number", () => {
    // Five items answered and none of them right; nothing else happened. The
    // natural report — "5 answered, 0 right, 0 cards, 0 words" — is four scores
    // on a screen, three of them zero.
    const { container } = render(
      <WeekReport
        week={week({ items_answered: 5, items_right: 0, empty: false })}
      />,
    );
    expect(digits(container)).toEqual(["5"]);
    expect(container.textContent).toContain("5 practice items answered.");
  });

  it("names the right-count when there is one", () => {
    const { container } = render(
      <WeekReport
        week={week({ items_answered: 5, items_right: 4, empty: false })}
      />,
    );
    expect(container.textContent).toContain("5 practice items answered, 4 of them right.");
  });

  it("counts days from what happened and never what did not", () => {
    const { container } = render(
      <WeekReport week={week({ days_with_a_session: 3, empty: false })} />,
    );
    expect(container.textContent).toContain("You opened a session on 3 days.");
    // Seven minus three is the number this screen must never learn to compute.
    expect(digits(container)).toEqual(["3"]);
  });

  it("says one day rather than 1 days", () => {
    const { container } = render(
      <WeekReport week={week({ days_with_a_session: 1, empty: false })} />,
    );
    expect(container.textContent).toContain("1 day.");
  });

  it("announces a passed unit, which is the one raise it has", () => {
    const { container } = render(
      <WeekReport week={week({ units_passed: 1, empty: false })} />,
    );
    expect(container.textContent).toContain("You passed a unit.");
  });
});

describe("home on Sunday", () => {
  beforeEach(() => {
    vi.mocked(api.getWeek).mockReset();
  });

  it("shows the report and no session call-to-action", async () => {
    vi.mocked(api.getWeek).mockResolvedValue(
      week({ sunday: true, cards_reviewed: 9, empty: false }),
    );
    render(
      <SundayHome>
        <button>Start today&rsquo;s session</button>
      </SundayHome>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("sunday-report")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/9 cards reviewed/)).toBeInTheDocument();
    // Reachable, and never the primary.
    expect(screen.getByTestId("sunday-session-link")).toHaveTextContent(
      "practise anyway",
    );
  });

  it("shows the ordinary home on the other six days", async () => {
    vi.mocked(api.getWeek).mockResolvedValue(week({ sunday: false }));
    render(
      <SundayHome>
        <button>Start today&rsquo;s session</button>
      </SundayHome>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("sunday-report")).toBeNull();
  });

  it("falls back to the ordinary home when the report cannot be reached", async () => {
    vi.mocked(api.getWeek).mockRejectedValue(new Error("offline"));
    render(
      <SundayHome>
        <button>Start today&rsquo;s session</button>
      </SundayHome>,
    );
    // A learner on a Tuesday with a flaky connection must still be able to
    // start. The cost — a Sunday that shows the button when the API is down —
    // is the smaller of the two harms and is stated rather than discovered.
    await waitFor(() =>
      expect(screen.getByRole("button")).toBeInTheDocument(),
    );
  });

  it("asks for neither until the server has said what day it is", () => {
    // A promise that never settles: the browser must not guess the day, so
    // there is nothing to render yet — not the button, not the report.
    vi.mocked(api.getWeek).mockReturnValue(new Promise(() => {}));
    render(
      <SundayHome>
        <button>Start today&rsquo;s session</button>
      </SundayHome>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByTestId("sunday-report")).toBeNull();
  });
});
