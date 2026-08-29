"use client";

import { useEffect, useState } from "react";

import { ItemCard } from "@/components/items/item-card";
import { Button } from "@/components/ui/button";
import {
  completeCheckpoint,
  getCheckpointToday,
  type Checkpoint,
} from "@/lib/api";
import { CHECKPOINT } from "@/components/checkpoint/copy";

/**
 * The Saturday sitting. PRD §3.
 *
 * **Answering goes through `POST /items/{id}/answer`, the same route block 3
 * uses**, carrying `session_id` so the attempt lands on this sitting. A second
 * grader would drift from `core.items.response`, and the score is counted from
 * the attempt log rather than from anything this component tracks — #108's
 * standing lesson is that the one number W6 took from the browser is the one
 * that turned out to be meaningless.
 *
 * **There is no timer and no running score.** A number climbing while a learner
 * works is a mark being applied in public, and the twelfth question would be
 * answered against a verdict that has already arrived.
 */
export function CheckpointRunner() {
  const [sitting, setSitting] = useState<Checkpoint | null>(null);
  const [index, setIndex] = useState(0);
  const [answered, setAnswered] = useState(0);
  const [problem, setProblem] = useState(false);

  useEffect(() => {
    let live = true;
    getCheckpointToday()
      .then((next) => live && setSitting(next))
      .catch(() => live && setProblem(true));
    return () => {
      live = false;
    };
  }, []);

  if (problem) {
    return (
      <p className="text-sm leading-relaxed text-muted-foreground">
        That didn’t load. Pull down to try again.
      </p>
    );
  }
  if (!sitting) return null;

  if (sitting.state === "not_ready") {
    return (
      <section className="space-y-2" data-testid="checkpoint-not-ready">
        <h2 className="text-lg font-medium">{CHECKPOINT.notReady.title}</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {CHECKPOINT.notReady.body}
        </p>
      </section>
    );
  }

  if (sitting.state === "done") {
    // **The verdict, and the two halves are not symmetrical.** A pass names its
    // score; a miss names none. `score_pct` is null from the API when the unit
    // was not passed, so this cannot render one even if it tried.
    if (sitting.passed === true) {
      const correct = Math.round(
        ((sitting.score_pct ?? 0) / 100) * sitting.item_count,
      );
      return (
        <section className="space-y-2" data-testid="checkpoint-passed">
          <h2 className="text-lg font-medium">{CHECKPOINT.passed.title}</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {CHECKPOINT.passed.body
              .replace("{correct}", String(correct))
              .replace("{total}", String(sitting.item_count))}
          </p>
        </section>
      );
    }
    if (sitting.passed === false) {
      return (
        <section className="space-y-2" data-testid="checkpoint-not-yet">
          <h2 className="text-lg font-medium">{CHECKPOINT.notYet.title}</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {sitting.retake_due_on
              ? CHECKPOINT.notYet.body.replace("{date}", sitting.retake_due_on)
              : CHECKPOINT.notYet.bodyNoDate}
          </p>
        </section>
      );
    }
    return (
      <section className="space-y-2" data-testid="checkpoint-done">
        <h2 className="text-lg font-medium">{CHECKPOINT.done.title}</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {CHECKPOINT.done.body}
        </p>
      </section>
    );
  }

  const item = sitting.items[index];
  const last = index + 1 >= sitting.items.length;

  return (
    <section className="space-y-4" data-testid="checkpoint-runner">
      <p className="text-sm leading-relaxed text-muted-foreground">
        {CHECKPOINT.progress
          .replace("{n}", String(index + 1))
          .replace("{total}", String(sitting.items.length))}
      </p>
      {item ? (
        <ItemCard
          key={item.id}
          item={item}
          sessionId={sitting.session_id}
          onAnswered={() => setAnswered((n) => n + 1)}
          onNext={last ? undefined : () => setIndex(index + 1)}
        />
      ) : null}
      {last && answered >= sitting.items.length ? (
        <Button
          onClick={() =>
            completeCheckpoint(sitting.session_id)
              .then(setSitting)
              .catch(() => setProblem(true))
          }
        >
          {CHECKPOINT.finish}
        </Button>
      ) : null}
    </section>
  );
}
