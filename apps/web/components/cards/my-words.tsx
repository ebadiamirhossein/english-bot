"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { MY_WORDS } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { getMyWords, type SavedWord } from "@/lib/api";

const MARKER: Record<SavedWord["state"], string> = {
  in_deck: MY_WORDS.inDeck,
  pending: MY_WORDS.pending,
  no_meaning: MY_WORDS.noMeaning,
};

/**
 * The words a learner saved from videos. **W31c.**
 *
 * **NO COUNT ANYWHERE** — not a total, not *N waiting*, not a badge (CLAUDE.md
 * §4, #160). A pending word is marked *meaning coming* while the worker job is
 * on its way to it; the marker is a state of that word, not a number about the
 * list.
 */
/** `back` (W32f): false inside Words, which is where the link goes. */
export function MyWords({ back = true }: { back?: boolean }) {
  const [words, setWords] = useState<SavedWord[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [problem, setProblem] = useState(false);

  const load = useCallback((before: string | null) => {
    getMyWords(before)
      .then((page) => {
        setWords((current) => (before && current ? [...current, ...page.words] : page.words));
        setNext(page.next_before ?? null);
        setProblem(false);
      })
      .catch(() => setProblem(true));
  }, []);

  useEffect(() => load(null), [load]);

  return (
    <div className="space-y-4" data-testid="my-words">
      {problem ? (
        <p className="text-sm text-muted-foreground" data-testid="my-words-unavailable">
          {MY_WORDS.unavailable}
        </p>
      ) : words === null ? null : words.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="my-words-empty">
          {MY_WORDS.empty}
        </p>
      ) : (
        <ul className="divide-y rounded-lg border" data-testid="my-words-list">
          {words.map((word) => (
            <li
              key={`${word.word}-${word.saved_at}`}
              className="space-y-1 px-3 py-3"
              data-testid="my-word"
              data-state={word.state}
            >
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span lang="en" className="text-lg font-medium">
                  {word.word}
                </span>
                <span
                  className={
                    "text-xs " +
                    (word.state === "pending" ? "text-primary" : "text-muted-foreground")
                  }
                  data-testid="my-word-marker"
                >
                  {MARKER[word.state]}
                </span>
              </p>
              {word.sentence ? (
                <p lang="en" className="text-sm italic text-muted-foreground">
                  {word.sentence}
                </p>
              ) : null}
              {word.source_title ? (
                <p className="text-xs text-muted-foreground/80">{word.source_title}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {next ? (
        <Button
          variant="outline"
          className="min-h-11"
          data-testid="my-words-more"
          onClick={() => load(next)}
        >
          {MY_WORDS.more}
        </Button>
      ) : null}
      {back ? (
        <p>
          <Link href="/review" className="text-sm underline underline-offset-4" data-testid="my-words-back">
            {MY_WORDS.back}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
