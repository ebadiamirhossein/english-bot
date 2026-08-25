"use client";

import type { CardFace as CardFaceData } from "@/lib/api";

/**
 * One card, front then back. PRD §5 and §8.5.4.
 *
 * **The provenance is not decoration.** PRD §5: "every card carries the
 * sentence it came from and where it came from. Context is what makes a card
 * stick; bare word↔translation cards are why people quit Anki." So the source
 * line is on the card at every stage, not tucked behind a disclosure.
 *
 * **The four §8.5.4 fields need no missing-value branch.** Migration 013's
 * `cards_informal_shows_the_four_things` CHECK refuses to store an
 * `informal`/`slang` card without the source line, the meaning, the neutral
 * equivalent and who-says-this — so if the register says slang, all four are
 * there. The component renders them rather than defending against their
 * absence, which is the point of putting the rule in the schema.
 */
export function CardFace({
  card,
  revealed,
}: {
  card: CardFaceData;
  revealed: boolean;
}) {
  const isReceptiveRegister =
    card.register === "slang" || card.register === "informal";

  return (
    <article
      className="rounded-2xl border border-border bg-card p-5 space-y-4"
      data-testid="card-face"
      data-card-id={card.id}
      data-card-type={card.card_type}
      data-register={card.register}
      data-revealed={String(revealed)}
    >
      <p className="font-heading text-2xl leading-snug whitespace-pre-line">
        {card.front}
      </p>

      {/* The cue appears only on a card the leech rule has rewritten. It is a
          first letter and a length, never an apology for the card being hard —
          "raises announced, drops silent" (CLAUDE.md §4) means the learner is
          given the help and not told why they are getting it. */}
      {card.cue && !revealed ? (
        <p
          className="font-mono text-base tracking-widest text-muted-foreground"
          data-testid="card-cue"
        >
          {card.cue}
        </p>
      ) : null}

      {revealed ? (
        <div className="space-y-3 border-t border-border pt-4" data-testid="card-back">
          <p className="font-heading text-2xl leading-snug text-primary">
            {card.back}
          </p>
          {card.meaning ? (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {card.meaning}
            </p>
          ) : null}
        </div>
      ) : null}

      {card.context_sentence ? (
        <p
          className="text-sm leading-relaxed text-muted-foreground italic"
          data-testid="card-context"
        >
          &ldquo;{card.context_sentence}&rdquo;
          {card.source_ref ? (
            <span className="not-italic"> — {card.source_ref}</span>
          ) : null}
        </p>
      ) : null}

      {isReceptiveRegister ? (
        // §8.5.4's whole reason for existing: a bare "hard pass = refusal" card
        // is "useless and slightly dangerous". The safe alternative and the
        // situation are the content, not a footnote, so they get their own
        // block rather than a line of small print.
        <div
          className="rounded-xl bg-muted p-4 space-y-2 text-sm leading-relaxed"
          data-testid="card-register-panel"
        >
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {card.register}
          </p>
          {card.neutral_equivalent ? (
            <p data-testid="card-neutral">
              Safe anywhere:{" "}
              <span className="font-medium">{card.neutral_equivalent}</span>
            </p>
          ) : null}
          {card.who_says_this ? (
            <p className="text-muted-foreground" data-testid="card-who-says">
              {card.who_says_this}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
