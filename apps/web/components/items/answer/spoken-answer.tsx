"use client";

import { Button } from "@/components/ui/button";

import type { AnswerProps } from "./types";

/**
 * `speak_repeat` and `speak_answer`, self-marked. Ruled 2026-08-25.
 *
 * **No microphone is opened and no audio exists.** Pronunciation scoring is
 * W14 (migration 018) and is outside this slice's fence, so the honest
 * instrument here is the learner's own judgement — recorded as
 * `item_attempts.graded_by = 'self'`, which is the value migration 012 already
 * ships. That column exists precisely so an accuracy number never silently
 * mixes a string match, a rubric and a self-mark, and so W19's progress line
 * stays comparable over time.
 *
 * "Not yet" rather than any of the obvious alternatives: raises are announced
 * and drops are silent (CLAUDE.md §4), and every natural phrasing of the second
 * button — "Wrong", "I got it wrong", "Missed it" — is a small verdict on the
 * person rather than on the attempt.
 */
export default function SpokenAnswer({
  onSubmit,
  submitting,
  answered,
}: AnswerProps) {
  if (answered) return null;
  return (
    <div className="space-y-3">
      <p className="text-sm leading-relaxed text-muted-foreground">
        Pronunciation scoring comes later — for now, mark yourself.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Button
          type="button"
          size="lg"
          disabled={submitting}
          onClick={() => onSubmit({ self_marked: true })}
          className="h-14 rounded-2xl text-base font-semibold"
        >
          {submitting ? "Saving…" : "Got it"}
        </Button>
        <Button
          type="button"
          size="lg"
          variant="outline"
          disabled={submitting}
          onClick={() => onSubmit({ self_marked: false })}
          className="h-14 rounded-2xl text-base font-semibold"
        >
          Not yet
        </Button>
      </div>
    </div>
  );
}
