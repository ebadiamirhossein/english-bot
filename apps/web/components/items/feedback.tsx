"use client";

import type { ItemAnswerResult } from "@/lib/api";

/**
 * What the learner reads after answering. **The highest-risk copy in the app.**
 *
 * Three rules, all of them CLAUDE.md §4 rather than taste:
 *
 *  - **Nothing is red.** The palette has no red in it by design, so the colour
 *    for failure does not exist to reach for (`apps/web/README.md`). A miss is
 *    information, not an alarm.
 *  - **The emphasis goes on the better version**, never on what was submitted —
 *    the same shape the correction screen uses. What you got wrong is not the
 *    part worth reading twice.
 *  - **No verdict word passes judgement on the person.** "Not quite" and then
 *    the answer. The banned-phrase scan over every `.tsx` would fail this file
 *    for "wrong", "incorrect", "missed" or "failed", which is the point: the
 *    obvious phrasings are the ones to refuse.
 *
 * A self-marked result says so, because an accuracy number that mixes a string
 * match with someone's own judgement is not one number.
 */
export function Feedback({ result }: { result: ItemAnswerResult }) {
  if (result.correct) {
    return (
      <p
        className="flex gap-2.5 rounded-2xl bg-accent/60 p-4 text-sm leading-relaxed text-accent-foreground"
        data-testid="feedback"
        data-correct="true"
      >
        <span aria-hidden>👍</span>
        <span>That&rsquo;s it.</span>
      </p>
    );
  }

  return (
    <div
      className="space-y-1.5 rounded-2xl border border-border bg-card p-5"
      data-testid="feedback"
      data-correct="false"
    >
      <p className="text-sm leading-relaxed text-muted-foreground">
        {result.graded_by === "self"
          ? "Noted — worth another go later."
          : "Not quite. Here it is:"}
      </p>
      {result.canonical ? (
        <p className="font-heading text-lg leading-snug text-primary">
          {result.canonical}
        </p>
      ) : null}
    </div>
  );
}
