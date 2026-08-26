"use client";

import { useCallback, useEffect, useState } from "react";

import { CardRunner } from "@/components/cards/card-runner";
import { Button } from "@/components/ui/button";
import { ApiError, getReviewQueue, type CardFace } from "@/lib/api";

/**
 * `/review` — the deck, on its own, for someone who wants extra.
 *
 * **It is no longer a daily duty, and the count is gone** (#160, ruled
 * 2026-08-26). This header used to read *"N left today"*, and a number that sits
 * on a tab and grows while a learner is away is a backlog presented — which
 * CLAUDE.md §4 forbids outright: *"Never present a backlog. Missed days shrink
 * the task; they never pile up."* It had been one since W7.
 *
 * **The ruling is a RETURN to PRD §4.1, not a revision of it.** §4.1 has
 * specified "Block 1 · Review — FSRS due cards, capped" inside the daily session
 * all along; the standalone screen is what diverged. So the due deck now lives
 * in the session and this screen keeps its route and loses its obligation.
 *
 * Nothing about the deck, the scheduler or the card face changed with it. Only
 * where cards are encountered.
 *
 * **The queue is refetched after each grade rather than advanced locally.** A
 * graded card's next due date is the server's answer, and a card rated *Again*
 * can legitimately come back inside the same session — an index into a stale
 * array cannot express that, and reconstructing the scheduler on the client to
 * decide is precisely what this codebase refuses to do.
 *
 * **The empty state is an ending, never a limit.** When the deck runs out —
 * because it was finished or because the daily cap stopped it — the copy says
 * the same thing either way and never mentions what was not shown.
 */
type Loading =
  | { kind: "loading" }
  | { kind: "ready"; cards: CardFace[]; l1Language: string }
  | { kind: "problem"; message: string };

export function Reviewer() {
  const [state, setState] = useState<Loading>({ kind: "loading" });

  const load = useCallback(() => {
    return getReviewQueue(20)
      .then((queue) => {
        setState({
          kind: "ready",
          cards: queue.cards,
          // #159: one per response, from `users.native_language`. The card face
          // used to guess it from the script, which is silently wrong for a
          // Latin-script L1.
          l1Language: queue.l1_language,
        });
      })
      .catch((error) => {
        setState({
          kind: "problem",
          message:
            error instanceof ApiError
              ? error.message
              : "That didn’t work. Try again in a moment.",
        });
      });
  }, []);

  useEffect(() => {
    let live = true;
    getReviewQueue(20)
      .then((queue) => {
        if (!live) return;
        setState({
          kind: "ready",
          cards: queue.cards,
          l1Language: queue.l1_language,
        });
      })
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

  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Getting your deck…</p>;
  }

  if (state.kind === "problem") {
    return (
      <div className="space-y-3" data-testid="reviewer-problem">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {state.message}
        </p>
        <Button type="button" onClick={() => void load()}>
          Try again
        </Button>
      </div>
    );
  }

  const card = state.cards[0];

  if (!card) {
    return (
      <div className="space-y-4" data-testid="deck-finished">
        <p className="font-heading text-2xl leading-snug">
          That&rsquo;s today&rsquo;s deck.
        </p>
        <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
          Your cards will come back on their own, spaced so they land just
          before you would forget them.
        </p>
      </div>
    );
  }

  return (
    <CardRunner
      card={card}
      l1Language={state.l1Language}
      // No `sessionId`: this screen is deliberately outside the daily session,
      // so its reviews carry a NULL `card_reviews.session_id` — the same reason
      // `item_attempts.session_id` is nullable for free practice.
      onGraded={load}
    />
  );
}
