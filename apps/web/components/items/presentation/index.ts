/**
 * **The one file in this app allowed to enumerate the eleven item types.**
 *
 * The W6 task row asks for one React component per item type; the W5 contract
 * says render from `RESPONSE_MODE` and not from the type. Both are kept, and
 * the resolution is worth stating because it is the rule a reviewer applies:
 *
 *   > Presentation is per type. Answering is per response mode.
 *   > Eleven presentation components over three answer components.
 *
 * So this map and the eleven files it points at may name a type. Nothing else
 * may: not `item-card.tsx`, not anything under `answer/`, not `feedback.tsx`,
 * not `explanation.tsx`, not `lib/items.ts`.
 * `tests/test_web_shell.py::test_only_the_presentation_map_branches_on_item_type`
 * reads `core.items.ITEM_TYPES` out of Python and fails the commit that breaks
 * it — the expected values come from the other side of the boundary, never from
 * the file under test.
 *
 * A twelfth type added in Python with no component here renders the fallback
 * below and fails `test_every_item_type_has_a_render_test`, rather than
 * throwing on a learner's phone.
 */

import type { ComponentType } from "react";

import ClozeCued from "./cloze-cued";
import CollocationPick from "./collocation-pick";
import Dictation from "./dictation";
import ErrorSpot from "./error-spot";
import L1ToL2Production from "./l1-to-l2-production";
import ListeningGap from "./listening-gap";
import MatchPairs from "./match-pairs";
import MCQ from "./mcq";
import SpeakAnswer from "./speak-answer";
import SpeakRepeat from "./speak-repeat";
import WordBankOrder from "./word-bank-order";
import type { PresentationProps } from "./types";

export type { PresentationProps };

const PRESENTATIONS: Record<string, ComponentType<PresentationProps>> = {
  mcq: MCQ,
  cloze_cued: ClozeCued,
  word_bank_order: WordBankOrder,
  error_spot: ErrorSpot,
  l1_to_l2_production: L1ToL2Production,
  dictation: Dictation,
  listening_gap: ListeningGap,
  speak_repeat: SpeakRepeat,
  speak_answer: SpeakAnswer,
  match_pairs: MatchPairs,
  collocation_pick: CollocationPick,
};

export function presentationFor(
  itemType: unknown,
): ComponentType<PresentationProps> | null {
  if (typeof itemType !== "string") return null;
  return PRESENTATIONS[itemType] ?? null;
}

export const PRESENTED_TYPES = Object.keys(PRESENTATIONS);
