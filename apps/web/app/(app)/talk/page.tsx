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
  // **FULL HEIGHT, AND THE PAGE ITSELF DOES NOT SCROLL.** `min-h-0` is what
  // lets the child's own scroll region actually bound itself inside a flex
  // column — without it the list grows and the page scrolls instead, which is
  // the defect this route exists to fix.
  return (
    <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden">
      <Conversation voice fullHeight />
    </div>
  );
}
