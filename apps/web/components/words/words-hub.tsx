"use client";

import { useState } from "react";

import { MyWords } from "@/components/cards/my-words";
import { Reviewer } from "@/components/cards/reviewer";
import { Drill } from "@/components/practice/drill";
import { WORDS } from "@/components/session/copy";
import { cn } from "@/lib/utils";

export type WordsPart = "review" | "practice" | "mine";

const PARTS: { part: WordsPart; label: string }[] = [
  { part: "review", label: WORDS.review },
  { part: "practice", label: WORDS.practice },
  { part: "mine", label: WORDS.mine },
];

/**
 * **W32f (B4) — Words: one page, three parts.** Operator ruling 2026-09-28:
 * the nav's Words replaces Review, and holds **Review** (the due cards — no
 * count, #160 unchanged), **word practice** (W31d's drill) and **My words**
 * (W31c's list). Three tabs rather than one long column: each part is a whole
 * screen on a phone (a card with its grades, a drill, a list), and only the
 * open part is mounted — so opening Words starts no drill and fetches no list
 * until the learner asks for it.
 *
 * **No number anywhere** — not on a tab, not beside a part (CLAUDE.md §4).
 */
export function WordsHub({ initial = "review" }: { initial?: WordsPart }) {
  const [part, setPart] = useState<WordsPart>(initial);
  return (
    <div className="space-y-5">
      <div
        role="tablist"
        aria-label={WORDS.tablist}
        className="grid grid-cols-3 gap-1 rounded-2xl bg-muted/60 p-1"
        data-testid="words-tabs"
      >
        {PARTS.map(({ part: p, label }) => (
          <button
            key={p}
            type="button"
            role="tab"
            id={`words-tab-${p}`}
            aria-selected={part === p}
            aria-controls={`words-part-${p}`}
            data-testid={`words-tab-${p}`}
            onClick={() => setPart(p)}
            className={cn(
              "min-h-11 whitespace-nowrap rounded-xl px-2 text-sm font-medium transition-colors",
              part === p
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <section
        role="tabpanel"
        id={`words-part-${part}`}
        aria-labelledby={`words-tab-${part}`}
        data-testid={`words-part-${part}`}
      >
        {part === "review" ? <Reviewer /> : part === "practice" ? <Drill back={false} /> : <MyWords back={false} />}
      </section>
    </div>
  );
}
