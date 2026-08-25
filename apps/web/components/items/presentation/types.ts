import type { ItemAnswerResult } from "@/lib/api";
import type { Draft, Projection } from "@/lib/items";

/**
 * What every one of the eleven presentation components receives.
 *
 * Controlled, not self-contained: for a `tap` item the thing you look at *is*
 * the thing you touch, so the presentation owns the selection UI and hands the
 * draft up. Committing that draft belongs to the answer component, which is
 * chosen by response mode and never by type.
 */
export type PresentationProps = {
  itemId: number;
  projection: Projection;
  draft: Draft;
  onDraft: (draft: Draft) => void;
  /** True once the response has been submitted — the item stops accepting taps. */
  disabled: boolean;
  /**
   * The graded result, or `null` before the server has answered.
   *
   * **This is not a pre-grading leak and cannot become one.** `ItemCard` holds
   * no result until the round trip lands, so there is nothing to pass down
   * until there is a verdict — the same reason the feedback box cannot render
   * early. It exists for the two types whose correct answer is a *structure*
   * rather than a string, which the verdict box cannot set as one line of text
   * (#112).
   */
  result?: ItemAnswerResult | null;
};
