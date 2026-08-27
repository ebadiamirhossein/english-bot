import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CardFace as CardFaceData, Rating } from "@/lib/api";

import faces from "./session-today.fixture.json";

/**
 * **#190. The regression for the bug both suites were green through.**
 *
 * W10 shipped a daily session that crashed on the first card a learner graded:
 * `GradeButtons` maps over the four ratings and reads `card.intervals[rating]`,
 * and block 1 served `Card.face()`, which has no `intervals`. The client's
 * `CardFace` type declares the field as non-optional, so TypeScript was
 * satisfied and the runtime was not.
 *
 * **Why nothing caught it, which is the finding rather than the fix.** Every
 * card in `session.test.tsx` is HAND-WRITTEN, and a hand-written fixture is a
 * statement of what the author believed the server sends. It happened to include
 * `intervals` because the author copied it from the `/review` shape. So the
 * client's expectation and the server's output were two independent inventions
 * that were never compared — and the one place that could have compared them,
 * `BlockOut.payload`, is `dict[str, Any]`.
 *
 * **So these render against `session-today.fixture.json`, which Python
 * generates through the real `core.services.cards.card_face`** and which
 * `tests/test_session_route.py` compares against a real ASGI response body. A
 * field the server stops sending disappears from this file, and these tests go
 * red on the next run.
 *
 * **The premise the crash was reported under was wrong, and the correction is
 * why both cards below are exercised.** It looked like a typed-path bug because
 * card 41 is a production card. It is not: `GradeButtons` renders on both
 * paths, so a `recognition` card reached by *Show me* crashed identically. The
 * split was never typed-versus-reveal — it was **session-versus-`/review`**,
 * because `/review` had the only complete producer.
 */
const REAL: CardFaceData[] = faces as unknown as CardFaceData[];

const typedCard = REAL.find((c) => c.typed)!;
const revealCard = REAL.find((c) => !c.typed)!;

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    attemptCard: vi.fn(),
    gradeCard: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { CardRunner } = await import("@/components/cards/card-runner");

beforeEach(() => {
  vi.mocked(api.attemptCard).mockReset();
  vi.mocked(api.gradeCard).mockReset();
});

function runner(card: CardFaceData) {
  return render(
    <CardRunner card={card} l1Language="fa" sessionId={7} onGraded={() => {}} />,
  );
}

const RATINGS: Rating[] = ["again", "hard", "good", "easy"];

describe("the card the session actually serves", () => {
  it("carries an interval for each of the four grades", () => {
    // The fixture is the server's own output. If this fails, the wire changed.
    for (const card of REAL) {
      for (const rating of RATINGS) {
        expect(typeof card.intervals[rating]).toBe("number");
      }
    }
  });

  it("survives the TYPED path through to the grade buttons", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: true });
    runner(typedCard);

    await userEvent.type(screen.getByTestId("card-typed-input"), "feel trapped");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    await waitFor(() => expect(screen.getByTestId("grade-buttons")).not.toBeNull());
  });

  it("survives the REVEAL path through to the grade buttons", async () => {
    runner(revealCard);
    await userEvent.click(screen.getByTestId("reveal"));
    expect(screen.getByTestId("grade-buttons")).not.toBeNull();
  });

  /**
   * The second defect named in the report: a guard would have stopped the crash
   * and left four buttons with no interval on them. **A missing preview is
   * missing data.** Showing the intervals is the point of showing four buttons —
   * a learner choosing between Hard and Good is choosing between two intervals,
   * and hiding them makes the choice arbitrary, which degrades every schedule
   * that follows.
   */
  it("prints a real interval on every button, not a blank", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: false });
    runner(typedCard);

    await userEvent.type(screen.getByTestId("card-typed-input"), "stuck");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(screen.getByTestId("grade-buttons")).not.toBeNull());

    for (const rating of RATINGS) {
      const button = screen.getByTestId(`grade-${rating}`);
      expect(button.getAttribute("data-interval-days")).toBe(
        String(typedCard.intervals[rating]),
      );
      // "today", "1 day", "10 days" — never an empty span or "undefined".
      expect(button.textContent).not.toContain("undefined");
      expect(button.textContent).toMatch(/today|day|days|month|months/);
    }
  });

  it("grades from inside the session and carries what the server needs", async () => {
    vi.mocked(api.attemptCard).mockResolvedValue({ matched: true });
    vi.mocked(api.gradeCard).mockResolvedValue({
      due: "2026-08-27T00:00:00Z",
      interval_days: 1,
      counts: { new_remaining: 0, review_remaining: 0, total_remaining: 0 },
    });
    runner(typedCard);

    await userEvent.type(screen.getByTestId("card-typed-input"), "feel trapped");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(screen.getByTestId("grade-buttons")).not.toBeNull());
    await userEvent.click(screen.getByTestId("grade-good"));

    const [id, rating, , extra] = vi.mocked(api.gradeCard).mock.calls[0];
    expect(id).toBe(typedCard.id);
    expect(rating).toBe("good");
    expect(extra).toMatchObject({ sessionId: 7, typedResponse: "feel trapped" });
  });
});
