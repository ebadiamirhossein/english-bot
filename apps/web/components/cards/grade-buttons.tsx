"use client";

import { RATINGS, type CardFace, type Rating } from "@/lib/api";

/**
 * The four FSRS grades. **The intervals come from the server.**
 *
 * `card.intervals` carries what each button would schedule, in days, computed
 * by `core/cards/fsrs.py`. There is no arithmetic here and nothing to compute
 * it from — the same rule W6 established for grading, and for the same reason:
 * a second implementation of the schedule would drift from the one that
 * actually writes the due date, and the learner would be shown a number the
 * database disagrees with.
 *
 * **Showing the intervals is the point of showing four buttons.** A learner
 * choosing between Hard and Good is choosing between two intervals; hiding them
 * makes the choice arbitrary and the grades stop meaning anything, which
 * degrades every future schedule.
 *
 * **No colour carries the meaning.** The palette has no red in it by design,
 * and Again is not a failure — it is the learner telling the scheduler the
 * truth, which is the single most useful thing they can do. So the four are one
 * row of equals, distinguished by their labels and their intervals.
 */
const LABELS: Record<Rating, string> = {
  again: "Again",
  hard: "Hard",
  good: "Good",
  easy: "Easy",
};

/**
 * Days as something readable at a glance on a phone.
 *
 * The switch to months is at 60 days and not at 30, deliberately: rounding 41
 * days to "1 month" understates it by nearly a third, and the interval is the
 * information the learner is choosing between. Below two months the exact day
 * count is both short enough to read and honest.
 */
function humanInterval(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day";
  if (days < 60) return `${days} days`;
  const months = Math.round(days / 30);
  return months === 1 ? "1 month" : `${months} months`;
}

export function GradeButtons({
  card,
  disabled,
  onGrade,
}: {
  card: CardFace;
  disabled: boolean;
  onGrade: (rating: Rating) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-2" data-testid="grade-buttons">
      {RATINGS.map((rating) => (
        <button
          key={rating}
          type="button"
          disabled={disabled}
          onClick={() => onGrade(rating)}
          data-testid={`grade-${rating}`}
          data-interval-days={card.intervals[rating]}
          // h-16 and a full-width column each: this is the control a learner
          // taps eighty times in a sitting, on a phone, often one-handed.
          className="flex h-16 flex-col items-center justify-center gap-0.5 rounded-xl border border-border bg-background px-1 transition-colors hover:bg-muted disabled:opacity-50"
        >
          <span className="text-sm font-medium">{LABELS[rating]}</span>
          <span className="text-[0.7rem] leading-none text-muted-foreground">
            {humanInterval(card.intervals[rating])}
          </span>
        </button>
      ))}
    </div>
  );
}
