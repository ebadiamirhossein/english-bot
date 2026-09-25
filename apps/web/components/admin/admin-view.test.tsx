import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AdminActivity } from "@/lib/api";

import fixture from "./admin.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getAdminActivity: vi.fn() };
});

const api = await import("@/lib/api");
const { AdminView } = await import("./admin-view");

/**
 * W23's client half of the `/admin` port, rendered from `admin.fixture.json` —
 * bodies built by `scripts/export_admin_fixture.py` through the route's own
 * serialiser and held to a real ASGI body by `tests/test_admin_fixture.py` (#190).
 *
 * **RED DEMONSTRATIONS (2026-09-25):** "draws each learner's activity" went red
 * with the `Streak` fact passed `user.active_days`; "marks a paused and a revoked
 * learner" went red with the `user.revoked` tag removed; "a learner who is not
 * the operator reads one neutral line" went red with the not-found branch
 * rendering `<Header />` too (the word *Operator* reached the screen); "offers
 * a way back after a failed load" went red with the retry `onClick` removed.
 */

const TWO = fixture.two as AdminActivity;
const MIXED = fixture.mixed as AdminActivity;
const NONE = fixture.none as AdminActivity;

async function open(body: AdminActivity) {
  vi.mocked(api.getAdminActivity).mockResolvedValue(body);
  const view = render(<AdminView />);
  await waitFor(() => expect(screen.getByTestId("admin-screen").dataset.phase).toBe("ready"));
  return view;
}

function card(name: string): HTMLElement {
  return screen.getByRole("heading", { name }).closest("li") as HTMLElement;
}

describe("the operator's panel", () => {
  it("draws each learner's activity from the wire", async () => {
    await open(TWO);
    const darius = within(card("Darius"));
    expect(darius.getByText("B2")).toBeInTheDocument();
    expect(darius.getByText("23")).toBeInTheDocument();
    expect(darius.getByText("6")).toBeInTheDocument();
    expect(darius.getByText("14 Oct")).toBeInTheDocument();
    expect(darius.getByText("Active, last 7 days")).toBeInTheDocument();
    expect(screen.getByTestId("admin-requests")).toHaveTextContent("No access requests waiting.");
  });

  it("marks a paused and a revoked learner, and one who has not practised", async () => {
    const mixed = await open(MIXED);
    expect(within(card("Tomas")).getByText("Access revoked")).toBeInTheDocument();
    expect(within(card("Mehrnoosh")).getByText("Not yet")).toBeInTheDocument();
    mixed.unmount();
    await open(TWO);
    expect(within(card("Rasa")).getByText("Paused")).toBeInTheDocument();
  });

  it("says where the waiting requests are handled", async () => {
    await open(MIXED);
    expect(screen.getByTestId("admin-requests")).toHaveTextContent(
      "Access request waiting: 1. This panel only reads — approve or decline it where you always have.",
    );
  });

  it("says so when nobody has joined", async () => {
    await open(NONE);
    expect(screen.getByTestId("admin-empty")).toHaveTextContent("Nobody has joined yet.");
  });

  it("a learner who is not the operator reads one neutral line", async () => {
    vi.mocked(api.getAdminActivity).mockRejectedValue(new api.ApiError("/admin/activity returned 404", 404));
    render(<AdminView />);
    await waitFor(() => expect(screen.getByTestId("admin-screen").dataset.phase).toBe("not-found"));
    expect(screen.getByTestId("admin-screen").textContent).toBe("There’s nothing here.");
  });

  it("offers a way back after a failed load", async () => {
    vi.mocked(api.getAdminActivity).mockRejectedValueOnce(new api.ApiError("x", 500));
    vi.mocked(api.getAdminActivity).mockResolvedValueOnce(TWO);
    render(<AdminView />);
    await waitFor(() => expect(screen.getByTestId("admin-screen").dataset.phase).toBe("problem"));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("admin-screen").dataset.phase).toBe("ready"));
  });
});
