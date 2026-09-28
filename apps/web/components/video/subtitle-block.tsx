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
   * **W32f (B2), #487 — the caption STRIP, directly under the video in Focus.**
   * *(W32d drew this line ON the picture, in a layer over the video's box;
   * the operator ruled on 2026-09-28 that it moves below: YouTube's Required
   * Minimum Functionality forbids overlays on the embedded player except
   * playback controls, and on an iPhone held sideways it was two lines of
   * large type over the picture — Finding 2.)*
   *
   * The current line only, on the same dark backing, white, the words
   * hoverable and tappable, **the type sized by the viewport**
   * (`.caption-strip-text`, a `clamp()` in `globals.css`), so a typical line
   * fits on one or two normal lines on a phone held sideways. The whole strip
   * is this Focus's current-line block: hovering it pauses (C5). **No previous
   * line** — it would take height from the video.
   */
  caption?: boolean;
}) {
  const now = active === null ? null : lines[active];
  if (caption) {
    return (
      <div
        data-testid="subtitle-block"
        onMouseEnter={onHoverStart}
        onMouseLeave={onHoverEnd}
        className="rounded-md bg-black/80 px-3 py-1 text-center text-white"
      >
        <p
          data-testid="subtitle-now"
          lang="en"
          aria-live="off"
          className="caption-strip-text font-medium"
        >
          {now ? (
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
          ) : null}
        </p>
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
