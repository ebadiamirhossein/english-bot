"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { CardFace as CardFaceView } from "@/components/cards/card-face";
import { GradeButtons } from "@/components/cards/grade-buttons";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  getReviewQueue,
  gradeCard,
  type CardFace,
  type DeckCounts,
  type Rating,
} from "@/lib/api";

/**
 * The deck reviewer: one card, reveal, four grades.
 *
 * **State lives in React and nowhere else.** No `localStorage`, no
 * `sessionStorage` — the only permitted browser storage in this app is the
 * theme, under one key, in one file (CLAUDE.md §5). A session that survives a
 * phone lock is W10's resumable runner; a card graded is a card written to the
 * server, so there is nothing here worth persisting on the device.
 *
 * **The empty state is an ending, never a limit.** When the deck runs out —
 * because it was finished or because the daily cap stopped it — the copy says
 * the same thing either way and never mentions what was not shown. Missed days
 * shrink the task; they never pile up, and a backlog is never presented
 * (CLAUDE.md §4). A learner with two hundred overdue cards sees eighty and is
 * told nothing about the other hundred and twenty.
 *
 * **The queue is refetched after each grade rather than advanced locally.** A
 * graded card's next due date is the server's answer, and a card rated *Again*
 * can legitimately come back inside the same session — an index into a stale
 * array cannot express that, and reconstructing the scheduler on the client to
 * decide is precisely what this codebase refuses to do.
 */
type Loading =
  | { kind: "loading" }
  | { kind: "ready"; cards: CardFace[]; counts: DeckCounts }
  | { kind: "problem"; message: string };

export function Reviewer() {
  const [state, setState] = useState<Loading>({ kind: "loading" });
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  // Reveal → grade. Reported to the server, clamped there, and read by nothing
  // that schedules: FSRS's inputs are state, stability, difficulty, elapsed days
  // and the rating. It is stored for W19's effort weighting (#108).
  const revealedAt = useRef<number | null>(null);

  const load = useCallback(() => {
    return getReviewQueue(20)
      .then((queue) => {
        setState({ kind: "ready", cards: queue.cards, counts: queue.counts });
        setRevealed(false);
        revealedAt.current = null;
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
        setState({ kind: "ready", cards: queue.cards, counts: queue.counts });
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

  const reveal = useCallback(() => {
    revealedAt.current = Date.now();
    setRevealed(true);
  }, []);

  const grade = useCallback(
    async (card: CardFace, rating: Rating) => {
      setBusy(true);
      const started = revealedAt.current;
      try {
        await gradeCard(
          card.id,
          rating,
          started === null ? undefined : Date.now() - started,
        );
        await load();
      } catch (error) {
        setState({
          kind: "problem",
          message:
            error instanceof ApiError
              ? error.message
              : "That didn’t save. Try again in a moment.",
        });
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

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
    <div className="space-y-5">
      <p
        className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground"
        data-testid="deck-counts"
      >
        {state.counts.total_remaining} left today
      </p>

      <CardFaceView card={card} revealed={revealed} />

      {revealed ? (
        <GradeButtons card={card} disabled={busy} onGrade={(r) => void grade(card, r)} />
      ) : (
        <Button
          type="button"
          onClick={reveal}
          data-testid="reveal"
          className="h-14 w-full text-base"
        >
          Show me
        </Button>
      )}
    </div>
  );
}
