"use client";

/**
 * `/talk` — the conversation, on a page of its own. **W13b/3 §A.**
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **THIS REVERSES W13b's §3.2, AND THE REVERSAL IS AN ASSISTANT ERROR
 * CORRECTED, NOT A CHANGE OF MIND.**
 *
 * §3.2 argued the conversation into block 4 citing #160 and PRD §4's *one
 * button, not a menu*. **#160 forbids a COUNTER, not a page.** Its ruling is
 * that `/review` *"stays reachable for someone who wants extra work, never as a
 * daily obligation with a count"*, on CLAUDE.md §4's *never present a backlog*.
 * **A conversation page has nothing that accumulates.**
 *
 * **WHAT THE MISAPPLICATION PRODUCED, FROM THE OPERATOR'S OWN SESSION:** a chat
 * crammed into a card between a grammar exercise and a *Write it* button, with
 * no room, no scroll region of its own, and the whole page scrolling underneath
 * it.
 *
 * **WHAT #160 STILL IMPOSES AND WHAT THIS PAGE HONOURS:** no count, no badge,
 * no dot, no *days since your last conversation*, and **never the primary
 * call-to-action on home.** Block 4 keeps a low-emphasis link and renders no
 * chat — W11b's Sunday link is the shipped shape for exactly this.
 * ────────────────────────────────────────────────────────────────────────────
 */

import { Conversation } from "@/components/session/conversation";

export default function TalkPage() {
  // ────────────────────────────────────────────────────────────────────────
  // **`h-full`, NOT `h-[100dvh]` — AND THE FIRST VERSION SHIPPED WITH THE
  // COMPOSER BELOW THE FOLD BECAUSE OF EXACTLY THAT.**
  //
  // **THE DEFECT: a viewport-height box does not start at the top of the
  // viewport.** `AppLayout` puts the `AppMenu` row above this and `main` adds
  // `pt-4`, so this container's top edge sits ~4rem down. **A `100dvh` box
  // beginning 4rem down ends 4rem BELOW the fold**, and the composer is its
  // last flex child — so the learner saw the topic, the opening message, the
  // log's `flex-1` region stretching to fill an oversized box, and no input at
  // all. `main`'s `pb-32` (8rem, clearing the fixed `BottomNav`) put a further
  // 8rem of page underneath it.
  //
  // **`h-full` SIZES THIS TO THE SPACE THE SHELL ACTUALLY LEAVES**, which
  // already excludes the menu row (flex) and the nav (`pb-32`). The composer
  // then lands 8rem above the viewport bottom, clear of the fixed nav.
  //
  // **AND IF THE PERCENTAGE EVER FAILS TO RESOLVE, IT DEGRADES TO CONTENT
  // HEIGHT** — the composer sits directly under the messages and the page
  // scrolls. That is a worse layout and a working surface, which is the right
  // way round for a fallback; `100dvh` failed to a surface with no input.
  // ────────────────────────────────────────────────────────────────────────
  // ────────────────────────────────────────────────────────────────────────
  // **W15 — `[contain:size]`, AND #413 IS WHY.** `/write` measured it (W16a):
  // the shell is a `min-h-dvh` column whose height FOLLOWS ITS CONTENT, so a
  // long conversation grew the shell, scrolled the document and could push the
  // composer back past the fold — `h-full` alone held only while the log was
  // short. Size containment stops the content counting toward this wrapper's
  // size, so it takes exactly what the column gives it. `e2e/talk.spec.ts`
  // asserts the document does not scroll with a long thread on every project.
  // *(The wrapper was `flex h-full min-h-0 flex-col overflow-hidden` — quoted,
  // #82's shape; the paragraph above about `h-full` stays true of WHY the
  // viewport unit was refused.)*
  // ────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden [contain:size]">
      <Conversation voice fullHeight />
    </div>
  );
}
