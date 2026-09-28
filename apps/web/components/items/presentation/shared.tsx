"use client";

/**
 * The pieces the eleven presentation components share.
 *
 * Tap targets are 48px minimum and full-width where the content allows: both
 * learners use a phone one-handed, and a row of small inline chips is a layout
 * that only works with two thumbs. `text-base` everywhere — 16px is the
 * threshold below which iOS Safari zooms the viewport, which is the layout
 * shift the human check looks for.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The item's prompt, in the display face. **`face` (W32f, B3)** replaces that
 * face for a Farsi prompt: Fraunces has no Arabic, and a face set ON this
 * element beats one inherited from the wrapper — so `font-l1` on the wrapper
 * alone left the Farsi prompt in the phone's fallback.
 */
export function Stem({ children, face = "font-heading" }: { children: ReactNode; face?: string }) {
  return (
    <p className={`${face} text-xl leading-snug`}>{children}</p>
  );
}

export function Instruction({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
  );
}

/** One tappable choice. Selected is the accent, never a colour that judges. */
export function Choice({
  label,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "min-h-12 w-full rounded-2xl border px-4 py-3 text-left text-base",
        "transition-colors disabled:opacity-60",
        selected
          ? "border-primary bg-accent/60 text-accent-foreground"
          : "border-border bg-card",
      )}
    >
      {label}
    </button>
  );
}

/** A word-sized tappable tile. Wraps; never scrolls sideways. */
export function Tile({
  label,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "min-h-12 rounded-xl border px-3.5 py-2.5 text-base transition-colors",
        "disabled:opacity-60",
        selected
          ? "border-primary bg-accent/60 text-accent-foreground"
          : "border-border bg-card",
      )}
    >
      {label}
    </button>
  );
}

/** The applied repair cue, when there is one. Never its category name. */
export function Cue({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <p className="text-sm text-muted-foreground" data-testid="item-cue">
      {text}
    </p>
  );
}
