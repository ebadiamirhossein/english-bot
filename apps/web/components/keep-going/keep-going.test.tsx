import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getKeepGoing: vi.fn() };
});

const api = await import("@/lib/api");
const { KeepGoing } = await import("./keep-going");

/**
 * W24e — the panel on its own. **RED BEFORE W24e:** the component did not exist.
 * What it may NOT do is the point: explain an absent option, show a number, or
 * turn a failed request into something the learner has to deal with.
 */
describe("KeepGoing", () => {
  beforeEach(() => vi.mocked(api.getKeepGoing).mockReset());

  it("renders only the options the server offers, in its order", async () => {
    vi.mocked(api.getKeepGoing).mockResolvedValue({ options: ["talk", "write"] });
    render(<KeepGoing />);
    await screen.findByTestId("keep-going");
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("data-testid"));
    expect(links).toEqual(["keep-going-talk", "keep-going-write"]);
  });

  it("renders nothing at all when nothing is on offer", async () => {
    vi.mocked(api.getKeepGoing).mockResolvedValue({ options: [] });
    const { container } = render(<KeepGoing />);
    await waitFor(() => expect(api.getKeepGoing).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the request fails — an offer is never an error", async () => {
    vi.mocked(api.getKeepGoing).mockRejectedValue(new Error("down"));
    const { container } = render(<KeepGoing />);
    await waitFor(() => expect(api.getKeepGoing).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("uses Sunday's own lead on Sunday (R1)", async () => {
    vi.mocked(api.getKeepGoing).mockResolvedValue({ options: ["watch"] });
    render(<KeepGoing sunday />);
    expect(await screen.findByText("If you feel like watching something:")).toBeInTheDocument();
    // W32f: `?extra=1` — keep going's watch-another; the nav's plain `/watch`
    // only opens today's video and never assigns (was `"/watch"` until W32f).
    expect(screen.getByTestId("keep-going-watch")).toHaveAttribute("href", "/watch?extra=1");
  });
});
