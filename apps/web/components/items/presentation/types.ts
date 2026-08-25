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
};
