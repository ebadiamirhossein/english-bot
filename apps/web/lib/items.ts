/**
 * Reading a projection, and the draft a learner builds before submitting.
 *
 * **Nothing here mentions an item type, and that is the rule this file is held
 * to.** The eleven types are enumerated in exactly one place —
 * `components/items/presentation/index.ts` — because presentation is per type
 * while answering is per response mode. A reviewer applies it as: only
 * `presentation/index.ts` and the eleven files it maps to may name a type.
 * `tests/test_web_shell.py::test_only_the_presentation_map_branches_on_item_type`
 * reads `core.items.ITEM_TYPES` from Python and fails the commit that breaks it.
 *
 * **Nothing here compares an answer either.** There is no fold, no casefold, no
 * punctuation stripping and nothing to compare against: the projection carries
 * no answer. All grading is `core.items.grading.grade_text`, server-side, and a
 * second implementation in TypeScript would be a fourth fold — one that could
 * accept a string the uniqueness gate rejected, or reject one it accepted, with
 * the learner seeing a coin flip.
 */

/** The projection, as it arrives. Readers below narrow it; nothing else does. */
export type Projection = Record<string, unknown>;

export function readString(p: Projection, key: string): string | null {
  const value = p[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function readStrings(p: Projection, key: string): string[] {
  const value = p[key];
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

/**
 * What the learner has built so far. One shape for all three response modes;
 * which field carries the answer is decided on the server, from the item's own
 * type, so this never has to know.
 */
export type Draft = {
  text?: string;
  option?: string;
  tile_index?: number;
  order?: string[];
  pairs?: Record<string, string>;
  self_marked?: boolean;
};

/**
 * Is there anything to submit? Generic on purpose — a per-type readiness rule
 * would be a twelfth place the eleven types are enumerated.
 */
export function isAnswered(draft: Draft): boolean {
  return (
    (draft.text ?? "").trim().length > 0 ||
    (draft.option ?? "").length > 0 ||
    draft.tile_index !== undefined ||
    (draft.order?.length ?? 0) > 0 ||
    Object.keys(draft.pairs ?? {}).length > 0
  );
}

/**
 * The feedback state machine. **There is no path from `idle` to `graded`** —
 * a verdict exists only once the server has answered, which is what makes
 * optimistic grading unwritable rather than merely discouraged.
 */
export type AnswerState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "graded"; result: import("@/lib/api").ItemAnswerResult }
  | { kind: "problem"; message: string };
