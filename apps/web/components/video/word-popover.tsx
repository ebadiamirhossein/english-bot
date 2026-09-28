"use client";

import { VIDEO } from "@/components/session/copy";
import { firstMeaning, type Resolved } from "@/components/video/meanings";

/** Right-to-left scripts among the learners' languages (#159: keyed on the
 * language, never guessed from the characters). */
const RTL = new Set(["fa"]);

/** Where the word is, measured from the player's own box. */
export type Anchor = { x: number; top: number; bottom: number; width: number };

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
  // Above the word when there is room, below it when the word is near the top.
  const below = anchor.top < 96;
  // Centred on the word, and kept inside the player's box: the popover is at
  // most 18rem (288px) wide, so its centre stays 144px + a gutter from each
  // edge — no horizontal overflow at a phone's width (§3a).
  const half = 144 + 8;
  const x =
    anchor.width <= 2 * half
      ? anchor.width / 2
      : Math.min(Math.max(anchor.x, half), anchor.width - half);
  return (
    <div
      role="tooltip"
      data-testid="word-popover"
      className="pointer-events-none absolute z-[55] w-max max-w-[min(18rem,calc(100%-1rem))] rounded-lg border bg-popover px-3 py-2 text-popover-foreground shadow-lg"
      style={{
        left: x,
        top: below ? anchor.bottom + 8 : anchor.top - 8,
        transform: below ? "translateX(-50%)" : "translate(-50%, -100%)",
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
            <p
              data-testid="word-popover-l1"
              lang={l1Language}
              dir={RTL.has(l1Language) ? "rtl" : "ltr"}
              className="text-sm"
            >
              {meaning.l1}
            </p>
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
