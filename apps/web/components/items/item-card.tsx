"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, answerItem, type ItemPresentation } from "@/lib/api";
import type { AnswerState, Draft } from "@/lib/items";

import { answerFor } from "./answer";
import { Explanation } from "./explanation";
import { Feedback } from "./feedback";
import { presentationFor } from "./presentation";

/**
 * One item, start to finish. **This file branches on `response_mode` and never
 * on item type** — the eleven are enumerated in `presentation/index.ts` alone.
 *
 * **All grading is server-side, and "instant feedback" is one round trip.**
 * There is no optimistic path here and none is writable: `AnswerState` has no
 * edge from `idle` to `graded`, and the projection carries no answer to compare
 * against even if someone wanted to. An optimistic check would be a second
 * definition of "the answer" — and `core/items/grading.py`'s fold is shared
 * with the uniqueness gate, so a copy of it here could accept a string the gate
 * rejected, or reject one it accepted, and the learner would see a coin flip.
 * That is the exact bug the v3 rebuild exists to end.
 *
 * `latency_ms` is measured from first render to submit. The server clamps it
 * and stores NULL for anything implausible, because this is the one value W6
 * writes that the browser chose (#108).
 */
export function ItemCard({
  item,
  onAnswered,
  onNext,
}: {
  item: ItemPresentation;
  onAnswered?: () => void;
  onNext?: () => void;
}) {
  const [draft, setDraft] = useState<Draft>({});
  const [state, setState] = useState<AnswerState>({ kind: "idle" });
  const shownAt = useRef<number>(Date.now());

  // A new item is a new encounter: the draft, the verdict and the clock all
  // reset together. Without this, moving to the next item would carry the
  // previous one's feedback and a latency measured from the wrong moment.
  useEffect(() => {
    setDraft({});
    setState({ kind: "idle" });
    shownAt.current = Date.now();
  }, [item.id]);

  const Presentation = useMemo(
    () => presentationFor(item.projection["item_type"]),
    [item.projection],
  );
  const Answer = answerFor(item.response_mode);

  async function submit(submitted: Draft) {
    setState({ kind: "submitting" });
    try {
      const result = await answerItem(item.id, {
        ...submitted,
        latency_ms: Date.now() - shownAt.current,
      });
      setState({ kind: "graded", result });
      onAnswered?.();
    } catch (error) {
      setState({
        kind: "problem",
        message:
          error instanceof ApiError && error.status === 503
            ? "That didn’t come back. Give it a moment and try again."
            : error instanceof Error
              ? error.message
              : "That didn’t work. Try again in a moment.",
      });
    }
  }

  // A type Python knows about and this app has no component for. Rendering a
  // quiet line beats throwing on a phone; the suite is where it should fail,
  // and `test_every_item_type_has_a_render_test` is what makes it.
  if (!Presentation || !Answer) {
    return (
      <section className="rounded-2xl border border-border bg-card p-5">
        <p className="text-sm leading-relaxed text-muted-foreground">
          This one isn&rsquo;t ready to show yet. Skip on to the next.
        </p>
      </section>
    );
  }

  const answered = state.kind === "graded";

  return (
    <section className="space-y-5" data-testid="item-card">
      <Presentation
        itemId={item.id}
        projection={item.projection}
        draft={draft}
        onDraft={setDraft}
        disabled={answered || state.kind === "submitting"}
        // Null until the server answers. The two types whose correct answer is
        // a structure rather than a string show it themselves (#112); every
        // other component ignores this.
        result={state.kind === "graded" ? state.result : null}
      />

      <Answer
        draft={draft}
        onDraft={setDraft}
        onSubmit={submit}
        submitting={state.kind === "submitting"}
        answered={answered}
      />

      {state.kind === "problem" ? (
        <p className="text-center text-sm text-muted-foreground">
          {state.message}
        </p>
      ) : null}

      {state.kind === "graded" ? (
        <>
          <Feedback result={state.result} />
          <Explanation result={state.result} />
          {onNext ? (
            <Button
              type="button"
              size="lg"
              variant="outline"
              onClick={onNext}
              className="h-14 w-full rounded-2xl text-base font-semibold"
            >
              Next
            </Button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
