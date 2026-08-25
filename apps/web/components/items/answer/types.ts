import type { Draft } from "@/lib/items";

/**
 * What every answer component receives. **Nothing type-specific is in here**,
 * and nothing may be added: these three files are chosen by `response_mode`,
 * and a prop that only one item type needs would be an eleven-way branch
 * arriving through the back door.
 */
export type AnswerProps = {
  draft: Draft;
  onDraft: (draft: Draft) => void;
  onSubmit: (draft: Draft) => void;
  /** True while the request is in flight. There is no verdict until it lands. */
  submitting: boolean;
  /** True once graded — the item stops accepting input. */
  answered: boolean;
};
