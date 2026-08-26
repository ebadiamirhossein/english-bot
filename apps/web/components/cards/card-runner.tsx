"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { CardFace as CardFaceView } from "@/components/cards/card-face";
import { GradeButtons } from "@/components/cards/grade-buttons";
import { TYPED } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { ApiError, attemptCard, gradeCard, type CardFace, type Rating } from "@/lib/api";

/**
 * One card at a time: type (or reveal), see the back, choose a grade.
 *
 * **Extracted at W10 so `/review` and the session's block 1 are the same
 * reviewer.** #160 moved the due deck into the daily session and left `/review`
 * reachable for someone who wants extra work; two components would have been two
 * card experiences, and the one nobody opened would have been the one that
 * rotted.
 *
 * **State lives in React and nowhere else.** No `localStorage`, no
 * `sessionStorage` — the only permitted browser storage in this app is the
 * theme, under one key, in one file (CLAUDE.md §5). A session that survives a
 * phone lock is resumed from the SERVER (`sessions.block_breakdown`), and a
 * graded card is a card written to the server, so there is nothing here worth
 * persisting on the device.
 *
 * **The typed answer is #157, and it comes BEFORE the reveal.** The operator's
 * reason, recorded as the operator's: *a card that shows the answer on a tap and
 * then asks the learner to grade themselves cannot distinguish recall from
 * recognition, and that distinction is the whole difference between knowing a
 * word and thinking you know it.* Committing to a string first is what makes the
 * self-grade honest.
 *
 * **The four grade buttons still decide the schedule.** The typed verdict
 * informs them; it does not replace them. A card has no `accepted_variants`
 * column, so the fold runs against `back` alone — and card 17's malformed
 * `_____s` hint (#147) plus a one-word back would otherwise mark correct English
 * as a miss, which CLAUDE.md §4 forbids.
 *
 * **Nothing is compared here.** `attemptCard` is a round trip even though this
 * component holds `back`, because `test_no_answer_comparison_in_typescript`
 * forbids a fold in TypeScript: a second definition of "the answer" is how a
 * learner ends up seeing a coin flip.
 */
export function CardRunner({
  card,
  l1Language,
  sessionId,
  onGraded,
}: {
  card: CardFace;
  l1Language: string;
  /** Set inside the daily session, absent on `/review` (#160). */
  sessionId?: number;
  /** Refetch, never advance an index — see the note below. */
  onGraded: () => Promise<void> | void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [typed, setTyped] = useState("");
  const [verdict, setVerdict] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Reveal → grade. Reported to the server, clamped there, and read by nothing
  // that schedules: FSRS's inputs are state, stability, difficulty, elapsed days
  // and the rating. It is stored for W19's effort weighting (#108).
  const revealedAt = useRef<number | null>(null);

  // A new card is a new encounter: the draft, the verdict and the clock all
  // reset together.
  useEffect(() => {
    setRevealed(false);
    setTyped("");
    setVerdict(null);
    setProblem(null);
    revealedAt.current = null;
  }, [card.id]);

  const reveal = useCallback(() => {
    revealedAt.current = Date.now();
    setRevealed(true);
  }, []);

  const check = useCallback(async () => {
    if (!typed.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      const result = await attemptCard(card.id, typed);
      setVerdict(result.matched);
      revealedAt.current = Date.now();
      setRevealed(true);
    } catch (error) {
      setProblem(
        error instanceof ApiError
          ? error.message
          : "That didn’t come back. Give it a moment and try again.",
      );
    } finally {
      setBusy(false);
    }
  }, [card.id, typed]);

  const grade = useCallback(
    async (rating: Rating) => {
      setBusy(true);
      const started = revealedAt.current;
      try {
        await gradeCard(
          card.id,
          rating,
          started === null ? undefined : Date.now() - started,
          {
            sessionId,
            // Only when there was one. An empty string is not an attempt, and
            // migration 016's CHECK pairs the verdict with its answer.
            typedResponse: verdict === null ? undefined : typed,
          },
        );
        await onGraded();
      } catch (error) {
        setProblem(
          error instanceof ApiError
            ? error.message
            : "That didn’t save. Try again in a moment.",
        );
      } finally {
        setBusy(false);
      }
    },
    [card.id, onGraded, sessionId, typed, verdict],
  );

  const asksForTyping = card.typed && !revealed;

  return (
    <div className="space-y-5" data-testid="card-runner">
      <CardFaceView card={card} revealed={revealed} l1Language={l1Language} />

      {asksForTyping ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void check();
          }}
        >
          <input
            type="text"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={TYPED.label}
            aria-label={TYPED.label}
            // The phone keyboard is a second grader. Autocorrect repairing a
            // learner's spelling before it is folded would measure the keyboard
            // rather than the learner — the same four attributes, and the same
            // reason, as `components/items/answer/typed-answer.tsx`.
            // `text-base` is 16px on purpose: below that Safari zooms on focus.
            autoCapitalize="off"
            autoCorrect="off"
            autoComplete="off"
            spellCheck={false}
            inputMode="text"
            enterKeyHint="done"
            data-testid="card-typed-input"
            className="h-14 w-full rounded-2xl border border-border bg-card px-4 text-base outline-none transition-colors placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <Button
            type="submit"
            size="lg"
            disabled={busy || !typed.trim()}
            className="h-14 w-full rounded-2xl text-base font-semibold"
          >
            {TYPED.submit}
          </Button>
          {/* Always available. A learner who cannot retrieve it must not be
              stuck behind a text field — that would turn "I don't know" into a
              dead end, and the honest answer to a card you cannot recall is
              Again, not silence. */}
          <Button
            type="button"
            variant="outline"
            onClick={reveal}
            data-testid="card-skip-typing"
            className="h-12 w-full rounded-2xl text-sm"
          >
            {TYPED.skip}
          </Button>
        </form>
      ) : null}

      {revealed && verdict !== null ? (
        <p
          className="text-sm leading-relaxed text-muted-foreground"
          data-testid="card-typed-verdict"
          data-matched={String(verdict)}
        >
          {verdict ? TYPED.matched : TYPED.unmatched}
        </p>
      ) : null}

      {problem ? (
        <p className="text-sm text-muted-foreground" data-testid="card-problem">
          {problem}
        </p>
      ) : null}

      {revealed ? (
        <GradeButtons card={card} disabled={busy} onGrade={(r) => void grade(r)} />
      ) : card.typed ? null : (
        <Button
          type="button"
          onClick={reveal}
          data-testid="reveal"
          className="h-14 w-full text-base"
        >
          {TYPED.skip}
        </Button>
      )}
    </div>
  );
}
