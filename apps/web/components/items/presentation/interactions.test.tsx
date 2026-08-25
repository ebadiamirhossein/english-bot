import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Draft } from "@/lib/items";
import fixtures from "@/lib/items/projections.fixture.json";

import { presentationFor } from "./index";

type Envelope = {
  id: number;
  response_mode: string;
  projection: Record<string, unknown>;
};

const BY_TYPE = new Map(
  (fixtures as Envelope[]).map((e) => [e.projection["item_type"] as string, e]),
);

/** Render a presentation with a live draft, the way `ItemCard` does. */
function mount(itemType: string, draft: Draft = {}) {
  const envelope = BY_TYPE.get(itemType)!;
  const onDraft = vi.fn();
  const Presentation = presentationFor(itemType)!;
  const view = render(
    <Presentation
      itemId={envelope.id}
      projection={envelope.projection}
      draft={draft}
      onDraft={onDraft}
      disabled={false}
    />,
  );
  return { onDraft, view, envelope };
}

describe("what a tap actually sends", () => {
  it("mcq: tapping an option drafts that option", async () => {
    // User action: tapping one of the four answers.
    const { onDraft } = mount("mcq");
    await userEvent.click(screen.getByRole("button", { name: "went" }));
    expect(onDraft).toHaveBeenCalledWith({ option: "went" });
  });

  it("error_spot: tapping a tile drafts its INDEX, never its word", async () => {
    // User action: tapping the word that is the mistake.
    //
    // The index rather than the word is load-bearing: duplicate tokens are
    // legitimate in a sentence, and the server resolves the index against the
    // stored tiles — so a client cannot invent a tile that was never shown.
    const { onDraft } = mount("error_spot");
    const tiles = screen.getByTestId("error-spot-tiles");
    await userEvent.click(
      within(tiles).getByRole("button", { name: "goed" }),
    );
    expect(onDraft).toHaveBeenCalledWith({ tile_index: 1 });
  });

  it("word_bank_order: tapping builds an ordering, and tapping back removes", async () => {
    // User action: building the sentence, then changing your mind.
    const first = mount("word_bank_order");
    await userEvent.click(
      within(screen.getByTestId("word-bank-pool")).getByRole("button", {
        name: "I",
      }),
    );
    expect(first.onDraft).toHaveBeenCalledWith({ order: ["I"] });

    first.view.unmount();
    const second = mount("word_bank_order", { order: ["I", "went"] });
    await userEvent.click(
      within(screen.getByTestId("word-bank-line")).getByRole("button", {
        name: "I",
      }),
    );
    expect(second.onDraft).toHaveBeenCalledWith({ order: ["went"] });
  });

  it("match_pairs: two taps make one pair", async () => {
    // User action: tapping a word, then tapping its meaning.
    const pending = mount("match_pairs");
    await userEvent.click(
      within(screen.getByTestId("match-left")).getByRole("button", {
        name: "skint",
      }),
    );
    expect(pending.onDraft).toHaveBeenCalledWith({
      pairs: {},
      option: "skint",
    });

    pending.view.unmount();
    const joined = mount("match_pairs", { pairs: {}, option: "skint" });
    await userEvent.click(
      within(screen.getByTestId("match-right")).getByRole("button", {
        name: "having no money",
      }),
    );
    expect(joined.onDraft).toHaveBeenCalledWith({
      pairs: { skint: "having no money" },
      option: "",
    });
  });

  it("the right-hand column is inert until a word is chosen", () => {
    // Without this the first tap on a meaning silently does nothing and reads
    // as the app ignoring you.
    mount("match_pairs");
    const right = within(screen.getByTestId("match-right")).getAllByRole(
      "button",
    );
    for (const button of right) expect(button).toBeDisabled();
  });
});
