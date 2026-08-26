"use client";

import Link from "next/link";

import { CardRunner } from "@/components/cards/card-runner";
import { BlockShell } from "@/components/session/block-shell";
import { BLOCKS, NOTHING_DUE } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import type { CardFace, SessionBlock } from "@/lib/api";

/**
 * The five blocks of PRD §4.1, one component each.
 *
 * **Two of them are empty in this slice and that is the correct output, not a
 * gap to be filled.** Block 2 needs the video engine (W12) and the player
 * (W13); block 3's eight items need a generator, and building one inside a
 * surface slice would put a billed content pipeline in it. A session that looked
 * full on day one would be inventing work, which is the thing the rules forbid.
 */

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-sm leading-relaxed text-muted-foreground"
      data-testid="block-empty"
    >
      {children}
    </p>
  );
}

/**
 * Block 1 · Review. The due deck, **inside the session** (#160).
 *
 * The empty state is the ruling made 2026-08-26: **when nothing is due the app
 * offers watching and never invents work.** No filler item, no "practise
 * anyway", no streak language, and nothing at all about what was not shown.
 *
 * It links nowhere on purpose — the video side is W12 and W13, so there is no
 * video to point at, and a link to a screen that does not exist would be worse
 * than a sentence that stands on its own.
 */
export function ReviewBlock({
  block,
  l1Language,
  sessionId,
  onGraded,
}: {
  block: SessionBlock;
  l1Language: string;
  sessionId: number;
  onGraded: () => Promise<void> | void;
}) {
  const cards = (block.payload.cards as CardFace[] | undefined) ?? [];
  const card = cards[0];

  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.review.eyebrow}
      title={BLOCKS.review.title}
    >
      {block.state === "empty" || !card ? (
        <div className="space-y-2" data-testid="nothing-due">
          <p className="font-heading text-lg leading-snug">
            {NOTHING_DUE.title}
          </p>
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            {NOTHING_DUE.body}
          </p>
        </div>
      ) : (
        <CardRunner
          key={card.id}
          card={card}
          l1Language={l1Language}
          sessionId={sessionId}
          onGraded={onGraded}
        />
      )}
    </BlockShell>
  );
}

/** Block 2 · Input. Empty until the video engine exists. */
export function InputBlock({ block }: { block: SessionBlock }) {
  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.input.eyebrow}
      title={BLOCKS.input.title}
    >
      <Empty>{BLOCKS.input.empty}</Empty>
    </BlockShell>
  );
}

/**
 * Block 3 · Focus. The unit's can-do and its grammar targets.
 *
 * **Labels over nothing, and that is #182 on a screen** — *the 82 grammar
 * targets are labels for teaching that exists nowhere.* The written explanation
 * is the next slice; the eight items need a generator. W10 does not paper over
 * the gap with filler, and this is the first place a person can see it rather
 * than read about it in the record.
 *
 * **No citation reaches here and none can.** The server hands over
 * `{target}` and nothing else — `core.sessions.blocks.visible_target` builds the
 * dict by naming the one field that may travel, so `murphy_units` was never in
 * the payload to render (#171, #183).
 */
export function FocusBlock({ block }: { block: SessionBlock }) {
  const canDo = block.payload.can_do as string | undefined;
  const targets =
    (block.payload.grammar_targets as { target: string }[] | undefined) ?? [];

  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.focus.eyebrow}
      title={BLOCKS.focus.title}
    >
      {block.state === "empty" || !canDo ? (
        <Empty>{BLOCKS.focus.empty}</Empty>
      ) : (
        <div className="space-y-4">
          <p className="text-base leading-relaxed" data-testid="focus-can-do">
            {canDo}
          </p>
          <ul className="space-y-2" data-testid="focus-targets">
            {targets.map((one) => (
              <li
                key={one.target}
                className="rounded-xl bg-muted px-4 py-3 text-sm leading-relaxed"
              >
                {one.target}
              </li>
            ))}
          </ul>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {BLOCKS.focus.noLesson}
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {BLOCKS.focus.noItems}
          </p>
        </div>
      )}
    </BlockShell>
  );
}

/**
 * Block 4 · Output. The unit's written task, corrected through `/write`.
 *
 * The written half only: speaking is scored at W14 and offering a task nothing
 * can score would be worse than not offering it.
 *
 * **This task repeats every day until W11**, because `user_unit_state` has no
 * writer and the unit cannot advance — see
 * `core.services.syllabus.current_unit`. It ships repeating rather than empty
 * because the task is real and doing it twice is not harmful; the failure would
 * be presenting it as working content without saying it repeats.
 */
export function OutputBlock({ block }: { block: SessionBlock }) {
  const task = block.payload.task as string | undefined;

  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.output.eyebrow}
      title={BLOCKS.output.title}
    >
      {block.state === "empty" || !task ? (
        <Empty>{BLOCKS.output.empty}</Empty>
      ) : (
        <div className="space-y-4">
          <p className="text-base leading-relaxed" data-testid="output-task">
            {task}
          </p>
          {/* `/write` is W3's correction surface, ✅ verified, and the only path
              in this app that writes the error journal. The session hands the
              learner to it rather than adding a second writer. */}
          <Button asChild size="lg" className="h-14 w-full rounded-2xl text-base font-semibold">
            <Link href="/write">{BLOCKS.output.action}</Link>
          </Button>
        </div>
      )}
    </BlockShell>
  );
}

/**
 * Block 5 · Close. What you actually did.
 *
 * **No XP number.** W19 owns the effort weighting — a spoken sentence must
 * outscore a tapped MCQ — and inventing one now would make the first weeks of
 * history incomparable with every week after them. `sessions.xp` ships as a
 * column and W10 writes NULL into it.
 *
 * The three lines on what you learned need a model call, and nothing may be
 * generated while a learner waits.
 */
export function CloseBlock({ block }: { block: SessionBlock }) {
  const reviewed = (block.payload.cards_reviewed as number | undefined) ?? 0;

  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.close.eyebrow}
      title={BLOCKS.close.title}
    >
      <p className="text-sm leading-relaxed" data-testid="close-summary">
        {reviewed === 1
          ? "One card reviewed today."
          : `${reviewed} cards reviewed today.`}
      </p>
    </BlockShell>
  );
}
