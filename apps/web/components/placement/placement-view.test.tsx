import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Placement, PlacementResult, PlacementStep } from "@/lib/api";

import fixture from "./placement.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getPlacement: vi.fn(),
    startPlacement: vi.fn(),
    answerPlacement: vi.fn(),
    speakPlacement: vi.fn(),
    finishPlacement: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { PlacementView } = await import("./placement-view");

/**
 * W18's client half, rendered from `placement.fixture.json` — bodies built by
 * `scripts/export_placement_fixture.py` through the routes' own serialisers and
 * held to real ASGI bodies by `tests/test_placement_fixture.py` (#190).
 *
 * **What these cannot see** (CLAUDE.md §3a): whether any of it is on screen, or
 * reachable, on a phone. `e2e/placement.spec.ts` carries that.
 *
 * **RED DEMONSTRATIONS (2026-09-25), each one edit, run, and restored:** the
 * `AudioSource.Provider` removed turned "fetches the clip from the placement
 * route" red (the clip pointed at `/items/303/audio`); `send({ known: true })`
 * swapped to `false` turned "a yes sends known: true" red; the `Up from`
 * line drawn whenever there are two sittings turned "announces nothing on a
 * first result" red; the 409 branch re-reading nothing turned "re-reads the
 * sitting when the server says the item moved on" red.
 * **The rest, by a scripted mutation each:** the not-ready line never drawn; a
 * "1 of 60" beside the part's name; "Correct!" after the grammar prompt; a tap
 * sent as an option; the typed speaking answer sent empty; voice ignored (no
 * Record); `finish` not called on `done`; the next-check line never drawn.
 */

const STEPS = fixture.steps as Record<string, PlacementStep>;
const VERDICT = /correct|wrong|score|%|\bof \d|missed|failed|keep it up/i;

function overview(name: "not_ready" | "ready" | "open" | "waiting"): Placement {
  return fixture[name] as Placement;
}

async function open(body: Placement, phase: string) {
  vi.mocked(api.getPlacement).mockResolvedValue(body);
  const view = render(<PlacementView />);
  await waitFor(() => expect(screen.getByTestId("placement-screen").dataset.phase).toBe(phase));
  return view;
}

async function sitting(step: PlacementStep) {
  return open({ ...overview("open"), step }, "sitting");
}

beforeEach(() => {
  vi.mocked(api.answerPlacement).mockReset();
  vi.mocked(api.startPlacement).mockReset();
  vi.mocked(api.finishPlacement).mockReset();
  vi.mocked(api.getPlacement).mockReset();
});

describe("the placement check", () => {
  it("says plainly when the check is not ready, and offers no start", async () => {
    await open(overview("not_ready"), "intro");
    expect(screen.getByTestId("placement-not-ready")).toHaveTextContent("The check isn’t ready yet.");
    expect(screen.queryByTestId("placement-start")).toBeNull();
  });

  it("starts, and shows a word with nothing that counts the items", async () => {
    vi.mocked(api.startPlacement).mockResolvedValue(STEPS.vocabulary);
    await open(overview("ready"), "intro");
    fireEvent.click(screen.getByTestId("placement-start"));
    await waitFor(() => expect(screen.getByTestId("placement-word")).toHaveTextContent("cupboard"));
    expect(screen.getByTestId("placement-part")).toHaveTextContent("Words");
    // No position, no count: the only digits on screen would be one.
    expect(screen.getByTestId("placement-screen").textContent ?? "").not.toMatch(/\d/);
  });

  it("a yes sends known: true, and a no sends known: false", async () => {
    vi.mocked(api.answerPlacement).mockResolvedValue(STEPS.vocabulary);
    await sitting(STEPS.vocabulary);
    fireEvent.click(screen.getByTestId("placement-yes"));
    await waitFor(() => expect(api.answerPlacement).toHaveBeenCalledWith(101, { known: true }));
    await waitFor(() => expect(screen.getByTestId("placement-no")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("placement-no"));
    await waitFor(() => expect(api.answerPlacement).toHaveBeenLastCalledWith(101, { known: false }));
  });

  it("renders a grammar item with the app's own components and shows no verdict", async () => {
    vi.mocked(api.answerPlacement).mockResolvedValue(STEPS.listening);
    const { container } = await sitting(STEPS.grammar);
    expect(screen.getByText(/the film ___ already started/)).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("typed-answer-input"), { target: { value: "had" } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(api.answerPlacement).toHaveBeenCalledWith(202, { text: "had" }));
    // Straight on to the next item: no feedback box, no explanation.
    await waitFor(() => expect(screen.getByTestId("placement-part")).toHaveTextContent("Listening"));
    expect(container.textContent).not.toMatch(VERDICT);
  });

  it("renders a tap item the same way, and sends the tile tapped", async () => {
    vi.mocked(api.answerPlacement).mockResolvedValue(STEPS.listening);
    await sitting(STEPS.grammar_tap);
    fireEvent.click(screen.getByText("don't"));
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(api.answerPlacement).toHaveBeenCalledWith(203, { tile_index: 1 }));
  });

  it("fetches the clip from the placement route", async () => {
    await sitting(STEPS.listening);
    const audio = screen.getByTestId("item-audio");
    expect(audio.getAttribute("src")).toMatch(/\/placement\/items\/303\/audio$/);
    expect(screen.getByTestId("placement-part")).toHaveTextContent("Listening");
  });

  it("takes a typed speaking answer when voice is off, and lets it be skipped", async () => {
    vi.mocked(api.answerPlacement).mockResolvedValue(STEPS.speaking);
    await sitting(STEPS.speaking);
    expect(screen.queryByTestId("placement-record")).toBeNull();
    fireEvent.change(screen.getByTestId("placement-typed"), {
      target: { value: "We had dinner by the sea." },
    });
    fireEvent.click(screen.getByTestId("placement-send"));
    await waitFor(() =>
      expect(api.answerPlacement).toHaveBeenCalledWith(404, { text: "We had dinner by the sea." }),
    );
    await waitFor(() => expect(screen.getByTestId("placement-skip")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("placement-skip"));
    await waitFor(() => expect(api.answerPlacement).toHaveBeenLastCalledWith(404, { skip: true }));
  });

  it("offers a recording when voice is on, and typing instead", async () => {
    await sitting(STEPS.speaking_voice);
    expect(screen.getByTestId("placement-record")).toHaveTextContent("Record");
    fireEvent.click(screen.getByTestId("placement-type-instead"));
    expect(screen.getByTestId("placement-typed")).toBeInTheDocument();
  });

  it("finishes after the last answer and shows where to start, in bands", async () => {
    vi.mocked(api.answerPlacement).mockResolvedValue(STEPS.done);
    vi.mocked(api.finishPlacement).mockResolvedValue(fixture.result_first as PlacementResult);
    const { container } = await sitting(STEPS.speaking);
    fireEvent.click(screen.getByTestId("placement-skip"));
    await waitFor(() => expect(screen.getByTestId("placement-screen").dataset.phase).toBe("result"));
    expect(screen.getByTestId("placement-band")).toHaveTextContent("B1");
    expect(screen.getByText("Intermediate")).toBeInTheDocument();
    expect(screen.getByTestId("placement-radar-vocabulary")).toHaveTextContent("B2");
    expect(screen.getByTestId("placement-vocab")).toHaveTextContent("about 3,300");
    expect(screen.getByTestId("placement-back")).toHaveAttribute("href", "/progress");
    expect(container.textContent).not.toMatch(VERDICT);
  });

  it("announces nothing on a first result, and announces a raise", async () => {
    vi.mocked(api.finishPlacement).mockResolvedValueOnce(fixture.result_first as PlacementResult);
    const first = await sitting(STEPS.done);
    await waitFor(() => expect(screen.getByTestId("placement-screen").dataset.phase).toBe("result"));
    expect(screen.queryByTestId("placement-raised")).toBeNull();
    first.unmount();

    vi.mocked(api.finishPlacement).mockResolvedValueOnce(fixture.result_raised as PlacementResult);
    await sitting(STEPS.done);
    await waitFor(() => expect(screen.getByTestId("placement-screen").dataset.phase).toBe("result"));
    expect(screen.getByTestId("placement-raised")).toHaveTextContent("Up from B1.");
    expect(screen.getByTestId("placement-band")).toHaveTextContent("B2");
  });

  it("shows the level and when the next check opens, with no start", async () => {
    await open(overview("waiting"), "intro");
    expect(screen.getByTestId("placement-band")).toHaveTextContent("B1");
    expect(screen.getByTestId("placement-next")).toHaveTextContent("The next check opens on 11 November.");
    expect(screen.queryByTestId("placement-start")).toBeNull();
  });

  it("re-reads the sitting when the server says the item moved on", async () => {
    vi.mocked(api.answerPlacement).mockRejectedValue(new api.ApiError("stale", 409));
    await sitting(STEPS.vocabulary);
    vi.mocked(api.getPlacement).mockResolvedValue({ ...overview("open"), step: STEPS.grammar });
    fireEvent.click(screen.getByTestId("placement-yes"));
    await waitFor(() => expect(screen.getByTestId("placement-part")).toHaveTextContent("Grammar"));
    expect(api.getPlacement).toHaveBeenCalledTimes(2);
  });
});
