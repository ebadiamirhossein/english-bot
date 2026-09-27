"use client";

import { useEffect, useRef } from "react";

import { LineText } from "@/components/video/line-text";
import { clock, type VideoLine } from "@/components/video/lines";

/** After the learner scrolls the list themselves, auto-scroll waits this long
 * before following the video again — reading ahead is not interrupted. */
const HANDS_OFF_MS = 4000;

/**
 * The whole transcript as a list of lines. W31b — **lines, not a paragraph**
 * (the operator's ruling on #397). The active line is highlighted with real
 * CSS — W13-i's highlight set `data-lit` and nothing styled it (#467) — and
 * scrolls into view inside the list, never the page. Tapping a line's time
 * seeks to it. Untimed lines (no cues) show without times and never scroll.
 */
export function LineList({
  lines,
  active,
  unknown,
  onWordTap,
  onSeek,
}: {
  lines: VideoLine[];
  active: number | null;
  unknown: Set<string>;
  /** W31c: the word and the INDEX of the line it was tapped in. */
  onWordTap?: (word: string, line: number | null) => void;
  onSeek?: (seconds: number) => void;
}) {
  const box = useRef<HTMLOListElement | null>(null);
  const touchedAt = useRef(0);

  useEffect(() => {
    const list = box.current;
    if (active === null || !list) return;
    if (Date.now() - touchedAt.current < HANDS_OFF_MS) return;
    const row = list.children[active] as HTMLElement | undefined;
    if (!row) return;
    // Inside the list only: scrolling the page would move the player away.
    // The list is `relative`, so a row's `offsetTop` is already measured from
    // it (a first draft subtracted the list's own offset too, and the target
    // went below zero — the list never moved; found by Playwright).
    const target = row.offsetTop - list.clientHeight / 3;
    if (typeof list.scrollTo === "function") {
      list.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    } else {
      list.scrollTop = Math.max(0, target);
    }
  }, [active]);

  const handsOn = () => {
    touchedAt.current = Date.now();
  };

  return (
    <ol
      ref={box}
      lang="en"
      data-testid="line-list"
      onWheel={handsOn}
      onTouchMove={handsOn}
      className="relative max-h-[45vh] space-y-1 overflow-y-auto overscroll-contain rounded-lg border p-2 text-base leading-relaxed"
    >
      {lines.map((line, index) => {
        const isActive = index === active;
        return (
          <li
            key={index}
            data-testid="line"
            data-active={isActive ? "true" : undefined}
            aria-current={isActive ? "true" : undefined}
            className={
              "flex gap-2 rounded-md px-2 py-1 transition-colors " +
              (isActive ? "bg-primary/10 ring-1 ring-primary/40" : "")
            }
          >
            {line.start !== null && onSeek ? (
              <button
                type="button"
                data-testid="line-seek"
                onClick={() => onSeek(line.start as number)}
                className="-my-1 flex min-h-11 min-w-11 shrink-0 items-start justify-center pt-1.5 font-mono text-xs text-muted-foreground tabular-nums hover:text-foreground lg:min-h-0 lg:min-w-0 lg:pt-0.5"
                aria-label={`Play from ${clock(line.start)}`}
              >
                {clock(line.start)}
              </button>
            ) : null}
            <span className="min-w-0">
              <LineText
                text={line.text}
                unknown={unknown}
                onWordTap={onWordTap ? (word) => onWordTap(word, index) : undefined}
              />
            </span>
          </li>
        );
      })}
    </ol>
  );
}
