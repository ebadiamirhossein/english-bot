import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import fixtures from "@/lib/items/projections.fixture.json";
import type { MeaningsMap } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, lookupWord: vi.fn(), startPractice: vi.fn(), answerPractice: vi.fn() };
});

const api = await import("@/lib/api");
const { WordPopover } = await import("@/components/video/word-popover");
const { WordSheet } = await import("@/components/video/word-sheet");
const { Drill } = await import("@/components/practice/drill");
const { presentationFor } = await import("@/components/items/presentation");
const { resolve } = await import("@/components/video/meanings");

/**
 * **W32f (B3) — Farsi in Vazirmatn, and only Farsi.** The operator, 2026-09-28:
 * the Farsi on `/watch` rendered in the phone's fallback face and read poorly.
 * **The face was already declared** (`app/layout.tsx`, `--font-l1` in
 * `globals.css`, W8a/#142) — the popover's and the sheet's Farsi lines simply
 * never used it: they had `lang` and `dir`, and no `font-l1`.
 *
 * **The rule, per element:** every element that renders a Farsi string carries
 * `lang="fa"`, `dir="rtl"` and the `font-l1` class (Vazirmatn first). A
 * Lithuanian line gets its `lang` and no Farsi face. Checked by scanning the DOM
 * for Arabic-script text, so a Farsi string that turns up somewhere new is
 * caught rather than listed.
 *
 * **RED BEFORE THE CODE (2026-09-28, on `ca55e40`).**
 */

const ARABIC = /[\u0600-\u06FF]/;

/** Every element with Farsi text of its own must sit in `lang="fa"`,
 * `dir="rtl"` and a `font-l1` element — the same element or one inside it. */
function expectEveryFarsiLineMarked(container: HTMLElement) {
  const holders = Array.from(container.querySelectorAll("*")).filter((el) =>
    Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && ARABIC.test(n.textContent ?? "")),
  );
  expect(holders.length, "no Farsi rendered — the test would pass vacuously").toBeGreaterThan(0);
  for (const el of holders) {
    const marked = el.closest("[lang]");
    expect(marked?.getAttribute("lang"), el.outerHTML).toBe("fa");
    expect(el.closest("[dir]")?.getAttribute("dir"), el.outerHTML).toBe("rtl");
    // The NEAREST face wins: a `font-heading` on the element itself beats a
    // `font-l1` on its wrapper (found on the Farsi→English prompt).
    const face = el.closest(".font-l1, .font-heading, .font-sans, .font-mono");
    expect(face?.classList.contains("font-l1"), `${el.outerHTML} is not set in font-l1`).toBe(true);
  }
}

const MAP: MeaningsMap = {
  l1: "fa",
  entries: {
    model: {
      k: "w", r: "neutral",
      s: [
        ["noun", "a small copy of something bigger", "ماکت"],
        ["noun", "a person whose job is to wear clothes for photos", "مدل"],
      ],
    },
  },
  forms: {},
  here: { mastodon: { d: "a big old animal like an elephant", r: "neutral", l1: "ماستودون" } },
  names: [], saved: {}, images: {},
};

describe("B3 — every Farsi string: lang=fa, dir=rtl, Vazirmatn", () => {
  it("the popover's Farsi line", () => {
    const { container } = render(
      <WordPopover anchor={{ x: 100, top: 200, bottom: 220, width: 400 }} found={resolve(MAP, "model")} l1Language="fa" />,
    );
    expect(screen.getByTestId("word-popover-l1")).toHaveClass("font-l1");
    expectEveryFarsiLineMarked(container);
  });

  it("the sheet from the map: every sense and the video's own meaning", () => {
    render(<WordSheet videoId={1} target={{ word: "model", line: 0 }} onClose={() => {}} map={MAP} lineText="a model" />);
    expect(screen.getAllByTestId("word-sheet-l1")).toHaveLength(2);
    expectEveryFarsiLineMarked(screen.getByTestId("word-sheet"));
  });

  it("the sheet's *here* meaning", () => {
    render(<WordSheet videoId={1} target={{ word: "mastodon", line: 0 }} onClose={() => {}} map={MAP} lineText="a mastodon" />);
    expectEveryFarsiLineMarked(screen.getByTestId("word-sheet-here"));
  });

  it("the sheet's fallback (the map could not load)", async () => {
    vi.mocked(api.lookupWord).mockResolvedValue({
      word: "model", lemma: "model", line: "a model",
      meaning: { definition: "a small copy", register: "neutral", l1: "ماکت", l1_language: "fa" },
      saved: "none",
    });
    render(<WordSheet videoId={1} target={{ word: "model", line: 0 }} onClose={() => {}} map={null} />);
    await screen.findByTestId("word-sheet-l1");
    expectEveryFarsiLineMarked(screen.getByTestId("word-sheet"));
  });

  it("Farsi in → English out: the drill's Farsi prompt", () => {
    const envelope = (fixtures as { projection: Record<string, unknown> }[]).find(
      (f) => f.projection.item_type === "l1_to_l2_production" && ARABIC.test(String(f.projection.prompt_text)),
    )!;
    const Presentation = presentationFor("l1_to_l2_production")!;
    const { container } = render(
      <Presentation
        itemId={1}
        projection={envelope.projection as never}
        draft={null as never}
        onDraft={() => {}}
        disabled={false}
        result={null}
      />,
    );
    expectEveryFarsiLineMarked(container);
  });

  it("word practice: a card whose meaning is Farsi (the Trancy import, #142)", async () => {
    vi.mocked(api.startPractice).mockResolvedValue({
      exercises: [{ card_id: 9, kind: "meaning_type", definition: "بسیار خسته", options: [], graded: false }],
    });
    vi.mocked(api.answerPractice).mockResolvedValue({
      correct: true, answer: "exhausted", meaning: "بسیار خسته", graded: false,
    });
    const { container } = render(<Drill />);
    await screen.findByTestId("drill-definition");
    expectEveryFarsiLineMarked(container);
  });

  it("a Lithuanian meaning keeps its own lang and no Farsi face", () => {
    const lt: MeaningsMap = { ...MAP, l1: "lt", entries: { model: { k: "w", r: "neutral", s: [["noun", "a copy", "maketas"]] } } };
    render(<WordSheet videoId={1} target={{ word: "model", line: 0 }} onClose={() => {}} map={lt} lineText="a model" />);
    const line = screen.getByTestId("word-sheet-l1");
    expect(line).toHaveAttribute("lang", "lt");
    expect(line).toHaveAttribute("dir", "ltr");
    expect(line).not.toHaveClass("font-l1");
  });
});

