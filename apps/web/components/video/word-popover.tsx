"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { L1Text } from "@/components/l1-text";
import { VIDEO } from "@/components/session/copy";
import { firstMeaning, type Resolved } from "@/components/video/meanings";

/**
 * Where the word is, measured from the player's own box. **`floor` (W32f):**
 * nothing of the popover may sit above this line — the video's bottom edge,
 * when the word is below the video — so it is never drawn on the picture
 * (#487). `height`: the player box's, so a popover below the word stays inside.
 */
export type Anchor = {
  x: number;
  top: number;
  bottom: number;
  width: number;
  floor?: number;
  height?: number;
  /** W32f: the word's own left and right edges, for placing beside it. */
  left?: number;
  right?: number;
};

/**
 * **W32b — the hover popover.** Desktop only (the player decides): after
 * 250 ms on a word, the word, its first meaning — the video's own, labelled
 * *here*, when there is one — and the learner's language. A click opens the
 * sheet with Save.
 *
 * **Rendered inside the player's root, never portalled to `body`:** in native
 * Focus the root IS the fullscreen element, and anything outside it is not on
 * the screen (the sheet lives there for the same reason). **`pointer-events:
 * none`**, so it never catches the pointer and never fights the word it
 * describes or the video under it. **It reads the map and nothing else** — no
 * request, no playback.
 */
export function WordPopover({
  anchor,
  found,
  l1Language,
}: {
  anchor: Anchor;
  found: Resolved;
  l1Language: string | null;
}) {
  const meaning = firstMeaning(found);
  // **Measured, then placed** (W32f). In order: ABOVE the word — when it is
  // not near the top and would not reach up onto the video; else BELOW it —
  // when that fits inside the player's box; else BESIDE it, level with it,
  // on whichever side has room. **Never on the picture (#487), never over the
  // word it describes** (Focus on a desktop: the video above, the screen's
  // edge below — the first build clamped it up over the word, found in the
  // W32f screenshots). Hidden for the one frame before it is measured.
  const box = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useLayoutEffect(() => {
    setSize({ w: box.current?.offsetWidth ?? 0, h: box.current?.offsetHeight ?? 0 });
  }, [anchor.top, anchor.bottom, anchor.x, found]);
  const gap = 8;
  const { w, h } = size ?? { w: 0, h: 0 };
  const floor = anchor.floor ?? 0;
  const aboveTop = anchor.top - gap - h;
  const belowTop = anchor.bottom + gap;
  const fitsAbove = anchor.top >= 96 && aboveTop >= floor;
  const fitsBelow = anchor.height === undefined || belowTop + h <= anchor.height - 4;
  // Centred on the word, and kept inside the player's box: the popover is at
  // most 18rem (288px) wide, so its centre stays 144px + a gutter from each
  // edge — no horizontal overflow at a phone's width (§3a).
  const half = 144 + 8;
  const centred =
    anchor.width <= 2 * half
      ? anchor.width / 2
      : Math.min(Math.max(anchor.x, half), anchor.width - half);
  let top: number;
  let left: number;
  let transform = "translateX(-50%)";
  if (fitsAbove || fitsBelow || anchor.left === undefined || anchor.right === undefined) {
    top = fitsAbove ? aboveTop : belowTop;
    left = centred;
  } else {
    const middle = (anchor.top + anchor.bottom) / 2 - h / 2;
    top = Math.max(floor, Math.min(middle, (anchor.height ?? middle + h + 4) - h - 4));
    const roomRight = anchor.width - anchor.right - gap >= w + 4;
    left = roomRight ? anchor.right + gap : Math.max(4, anchor.left - gap - w);
    transform = "none";
  }
  return (
    <div
      ref={box}
      role="tooltip"
      data-testid="word-popover"
      className="pointer-events-none absolute z-[55] w-max max-w-[min(18rem,calc(100%-1rem))] rounded-lg border bg-popover px-3 py-2 text-popover-foreground shadow-lg"
      style={{
        left,
        top,
        transform,
        visibility: size === null ? "hidden" : undefined,
      }}
    >
      <p className="flex items-baseline gap-2">
        <span lang="en" className="font-semibold">
          {found.word}
        </span>
        {meaning?.here ? (
          <span
            data-testid="word-popover-here"
            className="rounded bg-muted px-1.5 text-xs text-muted-foreground"
          >
            {VIDEO.sheet.here}
          </span>
        ) : null}
      </p>
      {found.kind === "name" ? (
        <p className="text-sm text-muted-foreground">{VIDEO.popover.name}</p>
      ) : meaning ? (
        <>
          <p lang="en" className="text-sm leading-snug" data-testid="word-popover-meaning">
            {meaning.definition}
          </p>
          {meaning.l1 && l1Language ? (
            <L1Text testId="word-popover-l1" text={meaning.l1} language={l1Language} className="text-sm" />
          ) : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="word-popover-miss">
          {VIDEO.popover.miss}
        </p>
      )}
    </div>
  );
}
