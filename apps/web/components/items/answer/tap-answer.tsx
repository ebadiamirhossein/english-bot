"use client";

import { Button } from "@/components/ui/button";
import { isAnswered } from "@/lib/items";

import type { AnswerProps } from "./types";

/**
 * Committing a tapped answer. The *selecting* happens inside the presentation
 * component, because for a tap item the thing you look at is the thing you
 * touch; what belongs to the response mode is the commit.
 *
 * Readiness is `isAnswered`, which is deliberately generic — a per-type rule
 * ("an option is chosen" / "every pair is joined") would be a twelfth place the
 * eleven types are enumerated. An incomplete draft submits and grades as wrong,
 * which is the honest outcome for a response that answers only half.
 */
export default function TapAnswer({
  draft,
  onSubmit,
  submitting,
  answered,
}: AnswerProps) {
  if (answered) return null;
  return (
    <Button
      type="button"
      size="lg"
      disabled={!isAnswered(draft) || submitting}
      onClick={() => onSubmit(draft)}
      className="h-14 w-full rounded-2xl text-base font-semibold"
    >
      {submitting ? "Checking…" : "Check"}
    </Button>
  );
}
