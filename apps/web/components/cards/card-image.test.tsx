import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CardFace as CardFaceData, ReviewQueue } from "@/lib/api";

import { CardFace } from "./card-face";
import queueFixture from "./review-queue.fixture.json";

/**
 * W13d — the picture on a card, rendered from the Python-generated
 * `review-queue.fixture.json` (`scripts/export_review_fixture.py`, held to the
 * real `GET /review/queue` body by `tests/test_lexeme_images.py`, #190).
 *
 * The four cards are TASKS' acceptance, one each: `spoon` (pictured), `trust`
 * (an abstract word), `give up` (a phrasal verb — a phrase card) and
 * `hold a spoon` (a collocation naming the pictured lemma).
 *
 * **RED, demonstrated 2026-09-25 and restored:** the picture moved above the
 * reveal (the "never before the reveal" test fails); `onError` removed (the
 * offline test finds the figure still drawn); the caption's author dropped (the
 * credit test fails). Which cards carry a picture is decided on the server
 * (`core.images.shows_picture`), and its red demonstrations are in
 * `tests/test_lexeme_images.py`; here the collocation arrives with `null`.
 */

const queue = queueFixture as unknown as ReviewQueue;
const byId = (id: number) => queue.cards.find((c) => c.id === id) as CardFaceData;
const spoon = byId(51);
const unpictured = [byId(52), byId(53), byId(54)];

describe("W13d — a picturable word's card", () => {
  it("shows the picture with the answer, with its visible credit", () => {
    render(<CardFace card={spoon} revealed l1Language="fa" />);
    const figure = screen.getByTestId("card-image");
    const img = within(figure).getByRole("img");
    expect(img).toHaveAttribute("src", "http://api.test/lexeme-images/7.png");
    expect(img).toHaveAttribute("alt", "spoon");
    expect(img).toHaveAttribute("width", "330");
    expect(img).toHaveAttribute("height", "215");
    expect(img).toHaveAttribute("crossorigin", "use-credentials");

    const credit = screen.getByTestId("card-image-credit");
    expect(credit).toHaveTextContent("Picture: THOR · CC BY 2.0 · Wikimedia Commons");
    expect(within(credit).getByRole("link", { name: "CC BY 2.0" })).toHaveAttribute(
      "href",
      "https://creativecommons.org/licenses/by/2.0",
    );
    expect(within(credit).getByRole("link", { name: "Wikimedia Commons" })).toHaveAttribute(
      "href",
      "https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
    );
  });

  it("keeps the sentence context — the picture replaces nothing", () => {
    render(<CardFace card={spoon} revealed l1Language="fa" />);
    // A recognition front IS its mined sentence, and the provenance stays below.
    expect(screen.getByTestId("card-face")).toHaveTextContent("Could you pass me a spoon?");
    expect(screen.getByTestId("card-context")).toHaveTextContent("— vocabulary");
    expect(screen.getByTestId("card-back")).toHaveTextContent("spoon");
  });

  it("never shows the picture before the reveal, where it would answer the card", () => {
    render(<CardFace card={spoon} revealed={false} l1Language="fa" />);
    expect(screen.queryByTestId("card-image")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("offline or on any error, removes picture and credit together", () => {
    render(<CardFace card={spoon} revealed l1Language="fa" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByTestId("card-image")).toBeNull();
    expect(screen.queryByTestId("card-image-credit")).toBeNull();
    // …and the card is still whole.
    expect(screen.getByTestId("card-back")).toHaveTextContent("spoon");
    expect(screen.getByTestId("card-face")).toHaveTextContent("Could you pass me a spoon?");
  });
});

describe("W13d — an abstract word, a phrasal verb and a collocation are unchanged", () => {
  it.each(unpictured.map((c) => [c.back, c] as const))("%s: no picture, no credit", (_, card) => {
    expect(card.image).toBeNull();
    render(<CardFace card={card} revealed l1Language="fa" />);
    expect(screen.queryByTestId("card-image")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("renders exactly what a face without the field rendered before W13d", () => {
    for (const card of unpictured) {
      const { container: now, unmount } = render(
        <CardFace card={card} revealed l1Language="fa" />,
      );
      const withField = now.innerHTML;
      unmount();
      // The face as W13d found it: no `image` key at all.
      const before: Partial<CardFaceData> = { ...card };
      delete before.image;
      const { container: then, unmount: unmount2 } = render(
        <CardFace card={before as CardFaceData} revealed l1Language="fa" />,
      );
      expect(withField).toBe(then.innerHTML);
      unmount2();
    }
  });
});
