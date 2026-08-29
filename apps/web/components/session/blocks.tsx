"use client";

import Link from "next/link";
import { useState } from "react";

import { CardRunner } from "@/components/cards/card-runner";
import { ItemCard } from "@/components/items/item-card";
import { LessonBody } from "@/components/lessons/lesson";
import { BlockShell } from "@/components/session/block-shell";
import { BLOCKS, NOTHING_DUE } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import type { CardFace, ItemPresentation, Lesson, SessionBlock } from "@/lib/api";

/**
 * The five blocks of PRD §4.1, one component each.
 *
 * **Block 2 is empty and that is the correct output, not a gap to be filled.**
 * It needs the video engine (W12) and the player (W13). A session that looked
 * full on day one would be inventing work, which is the thing the rules forbid.
 *
 * **Block 3 stopped being empty at W10c**, which built the generator its eight
 * items were waiting for, and **W10b filled the explanation half** — so PRD
 * §4.1's block 3 is whole for the first time. A unit with no generated lesson
 * still renders bare labels and says so in one line.
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
 * Block 3 · Focus. The unit's can-do, its grammar targets, and its items.
 *
 * **#182 is half-answered here and the half that remains is named on screen.**
 * The 82 grammar targets were labels for teaching that existed nowhere; W10c
 * gives each unit eight items generated against its own targets and checked by
 * `probe_target` before anybody sees them. The *written explanation* is still
 * W10b's, so the "on its way" line stays and the "practice arrives with the
 * generator" line is gone — it has arrived.
 *
 * **A unit with no items renders the targets and no practice section at all**,
 * rather than an empty heading. Only the units someone has run the generator for
 * have items, and only for the learner it was run for (#159).
 *
 * **This block deliberately does NOT reload the session when an item is
 * answered**, where `ReviewBlock` passes `onGraded={load}` and does. The reason
 * is `core.services.items.bank_for_session`, which orders by least-recently-
 * attempted first: a reload after each answer would re-sort the eight items
 * under the learner's fingers and move the one they just did to the end. The
 * position is held here, in React, and the block is completed by the session's
 * own done button like every other block.
 *
 * **No citation reaches here and none can.** The server hands over
 * `{target}` and nothing else — `core.sessions.blocks.visible_target` builds the
 * dict by naming the one field that may travel, so `murphy_units` was never in
 * the payload to render (#171, #183).
 */
/**
 * **`sessionId` is required, not optional, and #274 is why.** This component
 * took only `block` and rendered `ItemCard` without it, so every daily block-3
 * attempt stored `item_attempts.session_id = NULL` — while the checkpoint's
 * runner, which does pass it, produced rows that carry it. **#254 was fixed on
 * one route and the other was never checked.**
 *
 * The cost was not cosmetic: `block_breakdown.focus` is derived from attempts
 * belonging to the session, so it could never reach `done`, #258's automatic
 * completion was inert, and the pacing clock read 0 whatever a learner did.
 */
export function FocusBlock({
  block,
  sessionId,
}: {
  block: SessionBlock;
  sessionId: number;
}) {
  const canDo = block.payload.can_do as string | undefined;
  const targets =
    (block.payload.grammar_targets as { target: string }[] | undefined) ?? [];
  const lesson = (block.payload.lesson as Lesson | null | undefined) ?? null;
  const items = (block.payload.items as ItemPresentation[] | undefined) ?? [];
  // **W11: the lesson is paced.** Operator ruling 2026-08-29 (#245) — a section
  // advances per COMPLETED SESSION, not per calendar day, so a skipped day
  // loses nothing. The index is computed server-side; this reads it.
  const lessonSection =
    (block.payload.lesson_section as number | null | undefined) ?? null;
  const teachingComplete = Boolean(block.payload.teaching_complete);
  const [index, setIndex] = useState(0);
  const item = items[index];

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
          {/* **The labels are ANNOTATED, not replaced.** With a lesson each one
              becomes the header of its own section; without one they stay
              exactly as W10 shipped them. The label text is identical either
              way — it is the same string from `visible_target`, so #171 holds
              in both branches. */}
          {lesson ? (
            <>
              <LessonBody
                lesson={lesson}
                section={lessonSection}
                teachingComplete={teachingComplete}
              />
              {/* **Running out of teaching and having none are different facts,
                  and the learner may only see one of them.** Without this line
                  a learner who has finished the unit's four sections sees four
                  closed labels and nothing saying why — which reads as the
                  lesson having failed to load. It is not congratulation either:
                  the checkpoint has not happened, so there is nothing to
                  congratulate. */}
              {teachingComplete ? (
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {BLOCKS.focus.teachingComplete}
                </p>
              ) : null}
            </>
          ) : (
            <>
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
            </>
          )}
          {item ? (
            <div className="space-y-3" data-testid="focus-items">
              <p className="text-sm leading-relaxed text-muted-foreground">
                {BLOCKS.focus.progress
                  .replace("{n}", String(index + 1))
                  .replace("{total}", String(items.length))}
              </p>
              <ItemCard
                key={item.id}
                item={item}
                sessionId={sessionId}
                onNext={
                  index + 1 < items.length
                    ? () => setIndex(index + 1)
                    : undefined
                }
              />
            </div>
          ) : null}
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
