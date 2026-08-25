"use client";

import { useEffect, useState } from "react";

import { ItemCard } from "@/components/items/item-card";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ApiError, getItems, type ItemPresentation } from "@/lib/api";

/**
 * Free practice — the eleven item types, one at a time.
 *
 * **Not a stop-gap for W10.** Migration 012 made `item_attempts.session_id`
 * nullable precisely because an attempt can happen outside a session: rescue
 * quiz, free practice. W10's session runner becomes the primary path and home
 * keeps its one button; this stays as the place you come to practise on
 * purpose.
 *
 * State lives in React and nowhere else. No `localStorage`, no
 * `sessionStorage` — the only permitted browser storage in this app is the
 * theme, under one key, in one file (CLAUDE.md §5).
 *
 * The empty state is the ordinary state today: `items` is empty by design until
 * W10's `assign_daily` fills it, and if a learner sees anything else before
 * then, something is wrong.
 */
type Loading =
  | { kind: "loading" }
  | { kind: "ready"; items: ItemPresentation[] }
  | { kind: "problem"; message: string };

export default function PracticePage() {
  const [state, setState] = useState<Loading>({ kind: "loading" });
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let live = true;
    getItems(20)
      .then((items) => live && setState({ kind: "ready", items }))
      .catch((error) => {
        if (!live) return;
        setState({
          kind: "problem",
          message:
            error instanceof ApiError
              ? error.message
              : "That didn’t work. Try again in a moment.",
        });
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <>
      <PageHeader eyebrow="Practice" title="One at a time.">
        Items built for you and checked before you ever see them. Answer, read
        the feedback, move on.
      </PageHeader>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}

      {state.kind === "problem" ? (
        <p className="text-sm text-muted-foreground">{state.message}</p>
      ) : null}

      {state.kind === "ready" && state.items.length === 0 ? (
        <section className="rounded-2xl border border-border bg-card p-5">
          <p className="text-sm leading-relaxed">
            Nothing here yet. Items arrive with your daily session.
          </p>
        </section>
      ) : null}

      {state.kind === "ready" && state.items.length > 0 ? (
        <>
          <p className="text-xs text-muted-foreground" data-testid="practice-position">
            {index + 1} of {state.items.length}
          </p>
          <ItemCard
            key={state.items[index].id}
            item={state.items[index]}
            onNext={
              index + 1 < state.items.length
                ? () => setIndex(index + 1)
                : undefined
            }
          />
          {index + 1 >= state.items.length ? (
            <Button
              type="button"
              size="lg"
              variant="outline"
              onClick={() => setIndex(0)}
              className="h-14 w-full rounded-2xl text-base font-semibold"
            >
              Start again
            </Button>
          ) : null}
        </>
      ) : null}
    </>
  );
}
