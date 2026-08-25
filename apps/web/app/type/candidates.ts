import { Figtree, Newsreader, Nunito, Vazirmatn } from "next/font/google";

/**
 * W8a — three complete typography candidates and the control, for one unlinked
 * preview page. **Nothing here is a default and nothing here ships.**
 *
 * ## Why the fonts are loaded here and not in `app/layout.tsx`
 *
 * `next/font` calls must sit at module scope, and a call in the root layout
 * loads that face on every screen. These four families exist only for `/type`,
 * so they are declared in this module, which only `/type` imports. Not one byte
 * reaches a learner's normal screens, and the shipped stack is untouched: the
 * "today" candidate below deliberately declares no fonts at all and inherits
 * Geist and Fraunces from the root layout, which is what makes it a control
 * rather than a fourth candidate.
 *
 * ## The brief
 *
 * Amirhossein's words: the reviewer type is *"not good look and not soft"*. He
 * wants it softer and more beautiful — something a learner can stay looking at,
 * not something that reads as scary, stressful or tiring.
 *
 * **What ships today is high-contrast Fraunces on a cream ground** — which is
 * approximately the default an AI reaches for when asked to make something look
 * designed, and it is probably why the screen reads the way it does. So a
 * candidate that only swaps the family will not move the brief: **softness is
 * mostly not the typeface.** Line height, contrast and whitespace do more of the
 * work, which is why each candidate below is a whole token set — ground, ink,
 * scale, leading, weight pairing, radius, spacing — and not a font.
 *
 * ## The Farsi companion, and why every candidate declares one
 *
 * Two learners; one of them is a native Farsi speaker. PRD §5's card table puts
 * an L1 gloss on the production front and on the recognition back, so **W10 and
 * W13 are the slices that put Farsi on a card face** — the type has to be ready
 * before then, not after.
 *
 * Today it is not. Geist, Geist Mono and Fraunces are all loaded
 * `subsets: ["latin"]` and **none of the three even offers an Arabic subset**,
 * so a Farsi string anywhere outside `l1-to-l2-production.tsx` renders in
 * whatever face the operating system picks, differently on each phone, with no
 * way for the app to know. That is filed as a known issue rather than fixed
 * here.
 *
 * **Vazirmatn** is the declared companion in all three candidates. It is a
 * *Persian* face rather than an Arabic one — correct Persian letterforms and
 * digits — its 100–900 range matches every Latin candidate so a weight pairing
 * survives the script switch, and using one companion across all three keeps the
 * comparison about the Latin face.
 *
 * ## Licence gate — run before this file was written, as W4's and W7's were
 *
 * Verified against each family's upstream `OFL.txt` in `google/fonts`, not
 * against a summary page. **All seven faces on this page are SIL Open Font
 * License 1.1**: Figtree, Nunito, Newsreader, Vazirmatn, and the three already
 * shipped (Fraunces, Geist, Geist Mono).
 *
 * The two clauses that decide the commercial question, quoted verbatim:
 *
 * > Permission is hereby granted, free of charge, to any person obtaining a
 * > copy of the Font Software, to use, study, copy, merge, embed, modify,
 * > redistribute, and sell modified and unmodified copies of the Font Software…
 *
 * > 1) Neither the Font Software nor any of its individual components, in
 * > Original or Modified Versions, may be sold by itself.
 * > 2) Original or Modified Versions of the Font Software may be bundled,
 * > redistributed and/or sold with any software…
 *
 * Clause 2 is the permission this project needs and clause 1 is a restriction it
 * cannot breach: we embed faces in an application, we never sell a font. The
 * answer holds for a commercial product, which is what PRODUCT-PRINCIPLES §3
 * requires rather than "holds for a private one".
 *
 * All four are self-hosted by `next/font/google` at build time — no runtime CDN
 * fetch, no new runtime dependency, nothing beyond what Next already provides.
 */

// ── the faces ──────────────────────────────────────────────────────────────

/** Humanist sans, 300–900 variable. Candidate A's whole voice; C's UI chrome. */
const figtree = Figtree({
  variable: "--tp-sans",
  subsets: ["latin"],
  display: "swap",
});

/** The roundest legible option with a real weight range. Candidate B. */
const nunito = Nunito({
  variable: "--tp-rounded",
  subsets: ["latin"],
  display: "swap",
});

/**
 * A text serif with an optical-size axis, so 21px is set as 21px rather than as
 * a shrunk display cut. Candidate C reads with it; it never labels a button.
 */
const newsreader = Newsreader({
  variable: "--tp-serif",
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
});

/** The Farsi companion. Declared by all three candidates, never by the control. */
const vazirmatn = Vazirmatn({
  variable: "--tp-farsi",
  subsets: ["arabic", "latin"],
  display: "swap",
});

/** Every candidate font variable, for the page wrapper. */
export const FONT_VARIABLES = [
  figtree.variable,
  nunito.variable,
  newsreader.variable,
  vazirmatn.variable,
].join(" ");

// ── the token sets ─────────────────────────────────────────────────────────

export type Candidate = {
  id: string;
  label: string;
  /** One line under the switcher: what makes it soft. */
  claim: string;
  /** One line under that: what it costs. Stated, never buried. */
  cost: string;
  /** The font stack the card sentence is set in, Farsi fallback included. */
  stack: string;
  /** CSS custom properties scoped to this candidate's wrapper. */
  tokens: Record<string, string>;
};

/**
 * The Farsi companion, and **it has to come first on an L1 line.**
 *
 * The obvious construction — `var(--tp-sans), var(--tp-farsi)` — was written
 * first and measured second, and it does not work. `next/font` generates a
 * metric-adjusted local fallback for each family (`"Figtree Fallback"`, and so
 * on) and inserts it directly after that family; those fallbacks resolve to a
 * broad system face **which has Arabic coverage**, so the browser satisfies the
 * Farsi from it and never reaches Vazirmatn. Measured on the preview at 40px:
 * the declared stack and Figtree alone both rendered the gloss at 201.54px
 * while Vazirmatn renders it at 250.55px — the same three glyphs, a different
 * face, and nothing on screen says so.
 *
 * **That is the exact failure this slice exists to catch**, and it is invisible
 * to a reader: the stack looks correct, the page looks fine, and the one learner
 * whose glosses are Farsi is reading a face nobody chose.
 *
 * So an element marked `lang="fa"` gets `--tp-l1`, which leads with Vazirmatn.
 * Latin characters inside a Farsi line resolve in Vazirmatn too, which is right
 * — it carries a latin subset, and a gloss is one line in one voice.
 */
const FARSI = "var(--tp-farsi), system-ui, sans-serif";

/** An L1 line: the Persian face first, the candidate's own face behind it. */
const l1 = (latin: string) => `var(--tp-farsi), ${latin}, system-ui, sans-serif`;

export const CANDIDATES: Candidate[] = [
  {
    id: "today",
    label: "Today",
    claim:
      "The control. What is on the phone right now, so the three below are compared against it rather than against a memory.",
    cost:
      "High-contrast display serif on cream. Declares no Farsi companion at all, which is the known issue the three below each answer.",
    stack: "var(--font-fraunces), Georgia, serif",
    tokens: {
      "--tp-ground": "oklch(0.985 0.006 95)",
      "--tp-ink": "oklch(0.24 0.02 205)",
      "--tp-quiet": "oklch(0.48 0.02 205)",
      "--tp-edge": "oklch(0.9 0.008 95)",
      "--tp-panel": "oklch(1 0 0)",
      "--tp-accent": "oklch(0.42 0.06 195)",
      "--tp-accent-soft": "oklch(0.93 0.03 190)",
      "--tp-display": "var(--font-fraunces), Georgia, serif",
      "--tp-body": "var(--font-geist-sans), system-ui, sans-serif",
      "--tp-ui": "var(--font-geist-sans), system-ui, sans-serif",
      // No companion, on purpose: this is what ships, and the Farsi sample
      // below renders in whatever the phone reaches for. That IS the control.
      "--tp-l1": "var(--font-fraunces), Georgia, serif",
      "--tp-card-size": "1.5rem",
      "--tp-card-leading": "1.375",
      "--tp-card-weight": "400",
      "--tp-body-size": "0.875rem",
      "--tp-body-leading": "1.625",
      "--tp-radius": "1rem",
      "--tp-gap": "1rem",
      "--tp-pad": "1.25rem",
    },
  },
  {
    id: "soft-sans",
    label: "A · Soft sans",
    claim:
      "Figtree alone, no display face. Warmer paper, lighter ink, and a card sentence set at 20px on 1.65 instead of 24px on 1.375 — the page stops shouting before you read a word.",
    cost:
      "It gives up the character Fraunces had. Calm and forgettable are neighbours, and this is the candidate most likely to read as any other app.",
    stack: "var(--tp-sans), " + FARSI,
    tokens: {
      "--tp-ground": "oklch(0.975 0.008 85)",
      "--tp-ink": "oklch(0.32 0.018 200)",
      "--tp-quiet": "oklch(0.52 0.015 200)",
      "--tp-edge": "oklch(0.91 0.012 85)",
      "--tp-panel": "oklch(0.995 0.004 85)",
      "--tp-accent": "oklch(0.44 0.055 195)",
      "--tp-accent-soft": "oklch(0.94 0.025 190)",
      "--tp-display": "var(--tp-sans), " + FARSI,
      "--tp-body": "var(--tp-sans), " + FARSI,
      "--tp-ui": "var(--tp-sans), " + FARSI,
      "--tp-l1": l1("var(--tp-sans)"),
      "--tp-card-size": "1.25rem",
      "--tp-card-leading": "1.65",
      "--tp-card-weight": "500",
      "--tp-body-size": "0.9375rem",
      "--tp-body-leading": "1.7",
      "--tp-radius": "1.25rem",
      "--tp-gap": "1.75rem",
      "--tp-pad": "1.5rem",
    },
  },
  {
    id: "rounded",
    label: "B · Rounded",
    claim:
      "Nunito, the warmest ground of the three, borders reduced to a tint rather than a line, and everything at 1.7. The furthest any of these goes toward not being frightening.",
    cost:
      "Rounded reads as childish, and this is two adults working toward B2. Nunito's l, I and 1 are also less separated than Figtree's — check the gap and the digits at phone width before deciding.",
    stack: "var(--tp-rounded), " + FARSI,
    tokens: {
      "--tp-ground": "oklch(0.98 0.012 80)",
      "--tp-ink": "oklch(0.33 0.02 195)",
      "--tp-quiet": "oklch(0.54 0.016 195)",
      "--tp-edge": "oklch(0.94 0.016 80)",
      "--tp-panel": "oklch(0.997 0.005 80)",
      "--tp-accent": "oklch(0.46 0.05 190)",
      "--tp-accent-soft": "oklch(0.945 0.028 185)",
      "--tp-display": "var(--tp-rounded), " + FARSI,
      "--tp-body": "var(--tp-rounded), " + FARSI,
      "--tp-ui": "var(--tp-rounded), " + FARSI,
      "--tp-l1": l1("var(--tp-rounded)"),
      "--tp-card-size": "1.3125rem",
      "--tp-card-leading": "1.7",
      "--tp-card-weight": "600",
      "--tp-body-size": "0.9375rem",
      "--tp-body-leading": "1.7",
      "--tp-radius": "1.75rem",
      "--tp-gap": "1.75rem",
      "--tp-pad": "1.5rem",
    },
  },
  {
    id: "reading-serif",
    label: "C · Reading serif",
    claim:
      "Newsreader for the sentence and the answer; Figtree for every button, count and label. The serif is only ever the thing you read, never the thing you tap — which is what makes it restful rather than decorative.",
    cost:
      "A second family. And a text serif at 21px thins out on a lower-DPI Android, which is one of the two phones this has to work on.",
    stack: "var(--tp-serif), " + FARSI,
    tokens: {
      "--tp-ground": "oklch(0.982 0.006 92)",
      "--tp-ink": "oklch(0.3 0.018 205)",
      "--tp-quiet": "oklch(0.5 0.015 205)",
      "--tp-edge": "oklch(0.915 0.01 92)",
      "--tp-panel": "oklch(0.998 0.003 92)",
      "--tp-accent": "oklch(0.4 0.06 200)",
      "--tp-accent-soft": "oklch(0.935 0.026 192)",
      "--tp-display": "var(--tp-serif), " + FARSI,
      "--tp-body": "var(--tp-serif), " + FARSI,
      "--tp-ui": "var(--tp-sans), " + FARSI,
      "--tp-l1": l1("var(--tp-serif)"),
      "--tp-card-size": "1.3125rem",
      "--tp-card-leading": "1.6",
      "--tp-card-weight": "400",
      "--tp-body-size": "0.9375rem",
      "--tp-body-leading": "1.65",
      "--tp-radius": "1.125rem",
      "--tp-gap": "1.625rem",
      "--tp-pad": "1.5rem",
    },
  },
];
