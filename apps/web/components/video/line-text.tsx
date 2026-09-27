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
  wordTestId = true,
}: {
  text: string;
  unknown: Set<string>;
  onWordTap?: (word: string) => void;
  /** The list and the current line both render words; only one set carries
   * the test ids the component tests count. */
  wordTestId?: boolean;
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
              (isUnknown
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
