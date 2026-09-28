"use client";

import { LineText } from "@/components/video/line-text";
import type { VideoLine } from "@/components/video/lines";

/**
 * The line being spoken, large, directly under the player — with the one
 * before and the one after dimmed. W31b; the operator's reference is Trancy /
 * Language Reactor (the subtitle stays visible while watching).
 *
 * **THIS BLOCK AND ONLY THIS BLOCK PAUSES ON HOVER (C5).** Hovering or
 * scrolling the full line list below never pauses: a learner reading ahead in
 * the list has not asked the video to stop.
 */
export function SubtitleBlock({
  lines,
  active,
  unknown,
  onWordTap,
  onHoverStart,
  onHoverEnd,
  onWordHover,
  onWordHoverEnd,
  large = false,
  caption = false,
}: {
  lines: VideoLine[];
  active: number | null;
  unknown: Set<string>;
  /** W31c: the word and the INDEX of the line it was tapped in. */
  onWordTap?: (word: string, line: number | null) => void;
  onHoverStart?: () => void;
  onHoverEnd?: () => void;
  /** W32b: the popover's hover, per word. The BLOCK's hover above is what
   * pauses; a word's hover never touches playback. */
  onWordHover?: (word: string, line: number | null, el: HTMLElement, immediate: boolean) => void;
  onWordHoverEnd?: () => void;
  /** Focus mode: bigger type, same structure. */
  large?: boolean;
  /**
   * **W32d — the line ON the video, as YouTube draws captions.** Focus draws it
   * in a layer over the bottom of the video's own box (inside the element that
   * goes fullscreen), on a dark translucent backing that reads on a bright
   * frame in either theme. **The layer passes the pointer through; only the
   * caption box takes it**, so a click on the picture still reaches the video,
   * and the caption is this Focus's current-line block — hovering it pauses,
   * as W31b's block does (C5). **No previous line**: it would cover more of the
   * picture, and a phone held sideways leaves the video ~300 px tall; loop-line
   * and seeking cover "what was that?" (the plan's choice, stated).
   */
  caption?: boolean;
}) {
  const now = active === null ? null : lines[active];
  if (caption) {
    return (
      <div
        data-testid="caption-layer"
        className="pointer-events-none absolute inset-x-0 bottom-[6%] z-10 flex justify-center px-[4%]"
      >
        {now ? (
          <p
            data-testid="subtitle-block"
            onMouseEnter={onHoverStart}
            onMouseLeave={onHoverEnd}
            // **Only the visible caption takes the pointer, not its line box.**
            // A wrapped caption makes this flex item as wide as the video, and
            // it caught clicks beside the text (found by Playwright at phone-
            // landscape size, where the line wraps). The hover-pause still
            // fires: `mouseenter` reaches an ancestor through its descendant.
            className="pointer-events-none max-w-full text-center"
          >
            <span
              data-testid="subtitle-now"
              lang="en"
              aria-live="off"
              className="pointer-events-auto rounded-md bg-black/75 px-2 py-0.5 text-lg font-medium leading-relaxed text-white [box-decoration-break:clone] [-webkit-box-decoration-break:clone] sm:text-2xl"
            >
              <LineText
                text={now.text}
                unknown={unknown}
                onWordTap={onWordTap ? (word) => onWordTap(word, active) : undefined}
                onWordHover={
                  onWordHover ? (word, el, at) => onWordHover(word, active, el, at) : undefined
                }
                onWordHoverEnd={onWordHoverEnd}
                wordTestId={false}
                onVideo
              />
            </span>
          </p>
        ) : null}
      </div>
    );
  }
  const prev = active === null || active === 0 ? null : lines[active - 1];
  const next = active === null ? lines[0] ?? null : lines[active + 1] ?? null;
  return (
    <div
      data-testid="subtitle-block"
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      className="space-y-1 rounded-lg bg-muted/40 px-3 py-2 text-center"
    >
      <p
        data-testid="subtitle-prev"
        className="min-h-[1.25rem] truncate text-sm text-muted-foreground/70"
        aria-hidden="true"
      >
        {prev ? prev.text : ""}
      </p>
      <p
        data-testid="subtitle-now"
        lang="en"
        aria-live="off"
        className={
          "min-h-[2.5rem] font-medium leading-snug " +
          (large ? "text-2xl sm:text-3xl" : "text-lg sm:text-xl")
        }
      >
        {now ? (
          <LineText
            text={now.text}
            unknown={unknown}
            onWordTap={onWordTap ? (word) => onWordTap(word, active) : undefined}
            onWordHover={
              onWordHover ? (word, el, now) => onWordHover(word, active, el, now) : undefined
            }
            onWordHoverEnd={onWordHoverEnd}
            wordTestId={false}
          />
        ) : null}
      </p>
      <p
        data-testid="subtitle-next"
        className="min-h-[1.25rem] truncate text-sm text-muted-foreground/70"
        aria-hidden="true"
      >
        {next ? next.text : ""}
      </p>
    </div>
  );
}
