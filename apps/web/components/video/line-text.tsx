"use client";

import { useMemo } from "react";

import { pieces } from "@/components/video/lines";

/**
 * One line's words, tappable. W31b.
 *
 * **Unknown words are marked from the server's `unknown_lemmas`, and only by
 * lowercase surface** — no lemmatising here (a second instrument on one
 * screen; W13-i's reasoning, kept). Sound tags are dimmed spans, never buttons.
 */
export function LineText({
  text,
  unknown,
  onWordTap,
  onWordHover,
  onWordHoverEnd,
  wordTestId = true,
  onVideo = false,
}: {
  text: string;
  unknown: Set<string>;
  onWordTap?: (word: string) => void;
  /** W32b: the pointer (or keyboard focus) arrived on a word. The player owns
   * the delay and the popover; this only reports where. */
  onWordHover?: (word: string, el: HTMLElement, immediate: boolean) => void;
  onWordHoverEnd?: () => void;
  /** The list and the current line both render words; only one set carries
   * the test ids the component tests count. */
  wordTestId?: boolean;
  /** W32d: the words sit on the video's caption backing (white on a dark
   * box), so the unknown mark is an underline only and the hover a light wash —
   * the page's accent fill would sink white text into a pale green. */
  onVideo?: boolean;
}) {
  const parts = useMemo(() => pieces(text), [text]);
  return (
    <>
      {parts.map((part, index) => {
        if (part.kind === "text") return <span key={index}>{part.text}</span>;
        if (part.kind === "tag") {
          return (
            <span
              key={index}
              data-testid="sound-tag"
              className="text-muted-foreground/70 italic"
            >
              {part.text}
            </span>
          );
        }
        const isUnknown = unknown.has(part.text.toLowerCase());
        return (
          <button
            key={index}
            type="button"
            data-unknown={isUnknown ? "true" : undefined}
            data-testid={wordTestId ? (isUnknown ? "unknown-word" : "known-word") : undefined}
            onMouseEnter={
              onWordHover ? (event) => onWordHover(part.text, event.currentTarget, false) : undefined
            }
            onMouseLeave={onWordHoverEnd}
            onFocus={
              onWordHover ? (event) => onWordHover(part.text, event.currentTarget, true) : undefined
            }
            onBlur={onWordHoverEnd}
            onClick={
              onWordTap
                ? (event) => {
                    // A word inside a seekable row must not also seek.
                    event.stopPropagation();
                    onWordTap(part.text);
                  }
                : undefined
            }
            className={
              "rounded-sm px-px transition-colors " +
              (onVideo
                ? isUnknown
                  ? "underline decoration-dotted underline-offset-4 hover:bg-white/20"
                  : "hover:bg-white/20"
                : isUnknown
                  ? "bg-accent/60 underline decoration-dotted underline-offset-4"
                  : "hover:bg-muted")
            }
          >
            {part.text}
          </button>
        );
      })}
    </>
  );
}
