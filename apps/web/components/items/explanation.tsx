"use client";

import type { ItemAnswerResult } from "@/lib/api";

/**
 * The "why" half, shown only after grading — never before, because it would
 * give the answer away, and never generated on demand, because a billed model
 * call in the request path is the opposite of the whole pre-validation design.
 *
 * **This panel now shows `items.payload.explanation` or nothing at all**, and
 * the second half of that sentence is the part worth knowing before anyone
 * records "the explanation panel was verified".
 *
 * Until 2026-08-26 it also showed a Murphy reference from `error_types`, and
 * that reference was in practice the ONLY thing it ever showed: this file's own
 * docstring used to say so. The operator ruling on #183 removed it — most
 * learners own no copy and some own a different edition, so a unit number was
 * clutter for nearly everyone who read it — and removing it makes a
 * pre-existing gap visible rather than creating one. `core/prompts/item_generate.txt`
 * never asks the generator for an `explanation`, so the field is absent on every
 * generated item (#103), which means **from W10 this panel renders nothing on a
 * generated item until #103 is fixed.** That is #182 at item granularity, and it
 * is filed rather than papered over here.
 *
 * When the explanation is absent this renders nothing at all rather than an
 * empty heading. The feedback above it already carries the answer, which is real
 * content; an empty "Why" box would be a promise the item cannot keep.
 */
export function Explanation({ result }: { result: ItemAnswerResult }) {
  if (!result.explanation) return null;
  return (
    <section
      className="space-y-2 rounded-2xl border border-border bg-card p-5"
      data-testid="explanation"
    >
      <h2 className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        Why
      </h2>
      <p className="text-sm leading-relaxed">{result.explanation}</p>
    </section>
  );
}
