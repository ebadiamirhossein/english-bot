"use client";

import { readString, readStrings } from "@/lib/items";

import { Cue, Stem, Tile } from "./shared";
import type { PresentationProps } from "./types";

/**
 * A sentence split into tappable tiles, one of which is the mistake.
 *
 * The instruction is `prompt_text` — it comes from the item, not from this
 * file, which is why it does not appear here as a string. That is worth knowing
 * about the whole no-guilt rule: the scan over `.tsx` cannot reach item content
 * at all, and from W10 that content is model-generated (#110).
 *
 * `wrong_index` and `correction` are not in the projection and never will be —
 * finding the wrong tile is the entire task. What travels back is the index
 * tapped; the server resolves it to a word before grading.
 */
export default function ErrorSpot({
  projection,
  draft,
  onDraft,
  disabled,
}: PresentationProps) {
  const tiles = readStrings(projection, "tiles");
  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <div className="flex flex-wrap gap-2" data-testid="error-spot-tiles">
        {tiles.map((tile, index) => (
          <Tile
            key={`${tile}-${index}`}
            label={tile}
            selected={draft.tile_index === index}
            disabled={disabled}
            onSelect={() => onDraft({ tile_index: index })}
          />
        ))}
      </div>
    </div>
  );
}
