import { Writer } from "@/components/write/writer";

/**
 * `/write` — the journal. W3's correction surface, restyled and handed the day's
 * task at W16a (design Q1: this screen, not a new route and not a view inside
 * block 4).
 *
 * **`[contain:size]` ON THIS WRAPPER IS WHAT KEEPS THE BUTTON ON SCREEN, AND IT
 * WAS MEASURED, NOT GUESSED.** The shell is a `min-h-dvh` column: its height
 * follows its content. So any content taller than the viewport grows the shell,
 * scrolls the document, and pushes the pinned button past the fold — however the
 * child is sized. Two attempts failed in the harness before the geometry was
 * read: `/talk`'s `h-full`, then `flex-1 min-h-0`. Measured on the `1k` result
 * at 390×768 (WebKit): as shipped the shell was **940** tall and the result
 * region was not scrolling (653 of 653); `height:0` on this wrapper changed
 * nothing; **`contain: size` held the shell at 768, the region scrolled (481 of
 * 653), and the button's bottom sat at 640.** Size containment stops the content
 * counting toward the wrapper's size, so the wrapper takes only what the column
 * gives it. **No viewport unit anywhere** (#395). See #413 for `/talk`.
 *
 * Everything the screen does is in `components/write/writer.tsx`, so it can be
 * rendered in Vitest and asserted in a browser without this route.
 */
export default function WritePage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden [contain:size]">
      <Writer />
    </div>
  );
}
