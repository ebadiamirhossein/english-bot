import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "@/components/write/write.fixture.json";

let pathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    todayWatch: vi.fn(),
    startWatch: vi.fn(),
    getReviewQueue: vi.fn(),
    startPractice: vi.fn(),
    getMyWords: vi.fn(),
    reportVideoProgress: vi.fn(),
    videoMeanings: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { BottomNav } = await import("@/components/bottom-nav");
const { WordsHub } = await import("@/components/words/words-hub");
const { WatchRunner } = await import("@/components/watch/watch-runner");

/**
 * **W32f (B4) — the menu gains Watch and Words. Operator ruling, 2026-09-28,
 * superseding the four-item nav** (*Today · Map · Review · Progress*): today's
 * video and the saved words were reachable only through *keep going* and
 * Review. **Five items, in this order: Today · Watch · Words · Map · Progress**;
 * Words replaces Review and is one page of three parts — Review (today's due
 * cards), word practice (W31d), My words (W31c). **No counter or badge on any
 * item** (#160, CLAUDE.md §4).
 *
 * Whether the five fit at 320–430 px without truncation, and every tap target
 * is ≥ 44 px, is Playwright's (`e2e/nav.spec.ts`).
 *
 * **RED BEFORE THE CODE (2026-09-28, on `ca55e40`).**
 */

describe("B4 — the bottom nav: five places, no count", () => {
  it("Today · Watch · Words · Map · Progress, in that order, each with its icon", () => {
    render(<BottomNav />);
    const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Today", "/"],
      ["Watch", "/watch"],
      ["Words", "/words"],
      ["Map", "/map"],
      ["Progress", "/progress"],
    ]);
    for (const link of links) expect(link.querySelector("svg")).not.toBeNull();
  });

  it("carries no number and no badge", () => {
    const { container } = render(<BottomNav />);
    expect(container.textContent).not.toMatch(/\d/);
    expect(container.querySelector("[data-badge], [data-count], .badge")).toBeNull();
  });

  it.each([
    ["/watch", "Watch"],
    ["/words", "Words"],
    ["/review", "Words"],
    ["/review/words", "Words"],
    ["/practice/words", "Words"],
    ["/", "Today"],
  ])("at %s the current item is %s", (path, label) => {
    pathname = path;
    render(<BottomNav />);
    const current = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.textContent)).toEqual([label]);
  });
});

describe("B4 — Words: Review, word practice, My words on one page", () => {
  beforeEach(() => {
    vi.mocked(api.getReviewQueue).mockReset();
    vi.mocked(api.getReviewQueue).mockResolvedValue({ cards: [], l1_language: "fa" } as never);
    vi.mocked(api.startPractice).mockReset();
    vi.mocked(api.startPractice).mockResolvedValue(fixture.practice_start as never);
    vi.mocked(api.getMyWords).mockReset();
    vi.mocked(api.getMyWords).mockResolvedValue(fixture.my_words as never);
  });

  it("three parts, Review first and open", () => {
    render(<WordsHub />);
    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Review", "Practice", "My words"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("words-part-review")).toBeInTheDocument();
    expect(api.getReviewQueue).toHaveBeenCalled();
    expect(api.startPractice).not.toHaveBeenCalled();
  });

  it("each part opens its own screen: the drill, then the list", async () => {
    render(<WordsHub />);
    await userEvent.click(screen.getByRole("tab", { name: "Practice" }));
    expect(screen.getByTestId("words-part-practice")).toBeInTheDocument();
    expect(await screen.findByTestId("drill")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "My words" }));
    expect(await screen.findByTestId("my-words-list")).toBeInTheDocument();
    expect(screen.queryByTestId("drill")).toBeNull();
  });

  it("opens on the part it is asked for", async () => {
    render(<WordsHub initial="mine" />);
    expect(screen.getByRole("tab", { name: "My words" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("my-words-list")).toBeInTheDocument();
  });

  it("no count anywhere on the page", async () => {
    const { container } = render(<WordsHub />);
    await screen.findByTestId("words-part-review");
    expect(within(screen.getByRole("tablist")).queryByText(/\d/)).toBeNull();
    expect(container.querySelector("[data-badge], [data-count]")).toBeNull();
  });

  it("inside Words, the drill and My words carry no link back to Review", async () => {
    render(<WordsHub initial="mine" />);
    await screen.findByTestId("my-words-list");
    expect(screen.queryByTestId("my-words-back")).toBeNull();
  });
});

describe("B4 — the nav's Watch: today's video, never a new one", () => {
  beforeEach(() => {
    vi.mocked(api.todayWatch).mockReset();
    vi.mocked(api.startWatch).mockReset();
    vi.mocked(api.videoMeanings).mockResolvedValue({
      l1: "fa", entries: {}, forms: {}, here: {}, names: [], saved: {}, images: {},
    });
  });

  it("asks for today's video with a GET, and never the POST that assigns an extra", async () => {
    vi.mocked(api.todayWatch).mockResolvedValue(fixture.watch_study as never);
    render(<WatchRunner />);
    expect(await screen.findByTestId("watch-player")).toBeInTheDocument();
    expect(api.todayWatch).toHaveBeenCalledTimes(1);
    expect(api.startWatch).not.toHaveBeenCalled();
  });

  it("nothing today: a calm line and the way home, no count and no day promised", async () => {
    vi.mocked(api.todayWatch).mockRejectedValue(new api.ApiError("nothing_today", 404));
    render(<WatchRunner />);
    const none = await screen.findByTestId("watch-none");
    expect(none).toHaveTextContent("There’s no video for today. Anything you enjoy watching in English counts just as much.");
    expect(none.textContent).not.toMatch(/\d|tomorrow|failed|missed/i);
  });

  it("keep going's watch-another still asks the POST", async () => {
    vi.mocked(api.startWatch).mockResolvedValue(fixture.watch_study as never);
    render(<WatchRunner extra />);
    expect(await screen.findByTestId("watch-player")).toBeInTheDocument();
    expect(api.startWatch).toHaveBeenCalledTimes(1);
    expect(api.todayWatch).not.toHaveBeenCalled();
  });
});
