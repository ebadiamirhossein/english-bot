"use client";

import type { ItemAnswerResult } from "@/lib/api";

/**
 * The "why" half, shown only after grading — never before, because it would
 * give the answer away, and never generated on demand, because a billed model
 * call in the request path is the opposite of the whole pre-validation design.
 *
 * **What this will actually show today is the Murphy reference or nothing**,
 * and that is worth knowing before anyone records "the explanation panel was
 * verified". `items.payload.explanation` exists as a field, but
 * `core/prompts/item_generate.txt` never asks the generator for one, so it is
 * absent on every generated item (#103, W10). `murphy_units` comes from
 * `error_types` and is present only when the item declares an `error_type` —
 * which the `items_declares_a_target` CHECK does not require (#104, W8).
 *
 * When both are absent this renders nothing at all rather than an empty
 * heading. The feedback above it already carries the answer, which is real
 * content; an empty "Why" box would be a promise the item cannot keep.
 */
export function Explanation({ result }: { result: ItemAnswerResult }) {
  if (!result.explanation && !result.murphy_units) return null;
  return (
    <section
      className="space-y-2 rounded-2xl border border-border bg-card p-5"
      data-testid="explanation"
    >
      <h2 className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        Why
      </h2>
      {result.explanation ? (
        <p className="text-sm leading-relaxed">{result.explanation}</p>
      ) : null}
      {result.murphy_units ? (
        <p className="text-xs text-muted-foreground">
          Murphy {result.murphy_units}
        </p>
      ) : null}
    </section>
  );
}
