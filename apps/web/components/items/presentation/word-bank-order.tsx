"use client";

import { readString, readStrings } from "@/lib/items";

import { Cue, Instruction, Stem, Tile } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Shuffled tokens to be rearranged. Tap to add, tap the sentence to take back.
 *
 * Tap-to-build rather than drag-and-drop, deliberately: a drag on a phone
 * fights the page scroll, and a mis-drag reads as the app ignoring you. The
 * order is the answer, and the server joins it with spaces before grading —
 * this file never joins anything for comparison.
 *
 * Duplicate tokens are legitimate ("to the shops to the park"), so the bank is
 * indexed by position and not by word; keying on the string would make the
 * second `to` untappable.
 */
export default function WordBankOrder({
  projection,
  draft,
  onDraft,
  disabled,
}: PresentationProps) {
  const bank = readStrings(projection, "bank");
  const chosen = draft.order ?? [];
  const used = new Set<number>();
  const chosenIndexes = chosen.map((token) => {
    const index = bank.findIndex((b, i) => b === token && !used.has(i));
    used.add(index);
    return index;
  });

  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />

      <div
        className="min-h-14 rounded-2xl border border-dashed border-border bg-card p-3"
        data-testid="word-bank-line"
      >
        {chosen.length === 0 ? (
          <Instruction>Tap the words below to build the sentence.</Instruction>
        ) : (
          <div className="flex flex-wrap gap-2">
            {chosen.map((token, position) => (
              <Tile
                key={`${token}-${position}`}
                label={token}
                selected
                disabled={disabled}
                onSelect={() =>
                  onDraft({
                    order: chosen.filter((_, i) => i !== position),
                  })
                }
              />
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2" data-testid="word-bank-pool">
        {bank.map((token, index) =>
          chosenIndexes.includes(index) ? null : (
            <Tile
              key={`${token}-${index}`}
              label={token}
              selected={false}
              disabled={disabled}
              onSelect={() => onDraft({ order: [...chosen, token] })}
            />
          ),
        )}
      </div>
    </div>
  );
}
