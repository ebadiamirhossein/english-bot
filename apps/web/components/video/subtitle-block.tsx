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
}) {
  const now = active === null ? null : lines[active];
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
