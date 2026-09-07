"use client";

import Link from "next/link";
import { Mic } from "lucide-react";
import { useState } from "react";

import { CardRunner } from "@/components/cards/card-runner";
import { ItemCard } from "@/components/items/item-card";
import { LessonBody } from "@/components/lessons/lesson";
import { BlockShell } from "@/components/session/block-shell";
import { BLOCKS, CONVERSATION, SEEN_BEFORE, NOTHING_DUE } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { VideoPlayer } from "@/components/video/player";
import type {
  CardFace,
  ItemPresentation,
  Lesson,
  SessionBlock,
  VideoBlockPayload,
} from "@/lib/api";

/**
 * The five blocks of PRD §4.1, one component each.
 *
 * **Block 2 stopped being structurally empty at W13-i.** The old note is quoted
 * rather than deleted (#82's shape): *"Block 2 is empty and that is the correct
 * output, not a gap to be filled. It needs the video engine (W12) and the player
 * (W13)."* W12b built the engine and W13-i built the player, so the block is now
 * empty only on the days PRD §7.1 assigns no video.
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

/**
 * Block 2 · Input. **W13-i fills it. It has been empty since W10 (#302).**
 *
 * **The empty state changed meaning rather than going away.** It used to say the
 * video side was not built; it now says there is no video *on this day* — PRD
 * §7.1 assigns video on Monday, Wednesday and Friday, so four days in seven have
 * none and that is the ordinary state. **No backlog and no yesterday**
 * (CLAUDE.md §4): it never says a video was missed.
 *
 * **A purged transcript keeps this block `ready` and not `unavailable` (#335).**
 * The video is still watchable — `youtube_id` survives the purge by design — so
 * nothing failed, and `unavailable` would claim a larger loss than occurred. The
 * player renders that case itself.
 *
 * **This block reaches no model.** Tap-to-define, Add to deck and register
 * detection are W13-ii's and are gated on the operator's §1a ruling.
 */
export function InputBlock({
  block,
  l1Language,
}: {
  block: SessionBlock;
  l1Language: string;
}) {
  const payload = block.payload as unknown as VideoBlockPayload | undefined;

  return (
    <BlockShell
      n={block.n}
      kind={block.kind}
      state={block.state}
      eyebrow={BLOCKS.input.eyebrow}
      title={BLOCKS.input.title}
    >
      {block.state === "empty" || !payload?.youtube_id ? (
        <Empty>{BLOCKS.input.empty}</Empty>
      ) : (
        <VideoPlayer payload={payload} l1Language={l1Language} />
      )}
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
  // **Seeded from the server, not from zero (#275).** Refreshing `/session`
  // restarted practice at 1 of 8 while `item_attempts` held the answers: the
  // position was React state and the server was never asked. `answered` is the
  // count of THIS session's eight that carry an attempt, so a resumed session
  // opens on the first one the learner has not done.
  const answered = Number(
    (block.payload as { answered?: number } | undefined)?.answered ?? 0,
  );
  const [index, setIndex] = useState(answered);
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
              {(item as { seen?: boolean }).seen ? (
                <p
                  className="text-sm leading-relaxed text-muted-foreground"
                  data-testid="focus-seen-before"
                >
                  {SEEN_BEFORE}
                </p>
              ) : null}
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
export function OutputBlock({
  block,
  sessionId,
}: {
  block: SessionBlock;
  sessionId?: number;
}) {
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
          {/* **W14: the speak half is ADDITIVE and never replaces the written
              task.** PRD §4.1's block 4 is *Speak or write*, and until W14 it
              only wrote. A deck with no usable sentence yields no `shadow` key
              at all — absent, never an empty face (§1e). */}
          {/* **THE SHADOW CONTROL IS RETIRED FROM BLOCK 4 (operator ruling,
              2026-09-05).** #376: assessment catches a word said as a different
              word and misses an inflectional ending, so the surface tells a
              learner they said it right when they did not. **The code stays --
              W17's weak-spot surface is the consumer that keeps it alive.**
              #348's disable-don't-delete precedent. */}
          {/* **W13b/5 MOVED THE CONVERSATION ENTRY POINT OFF BLOCK 4 AND ONTO
              THE CLOSING BLOCK.** The old link is quoted rather than deleted
              (#82's shape): an underlined `text-sm text-muted-foreground`
              reading *"Or have a conversation"*, sitting above the written task
              with `data-testid="conversation-link"`.

              **WHY IT LEFT: it was competing with block 4's own action while
              being styled to lose.** W13b/3 §A put it here to keep it away from
              the primary emphasis, and the effect was a phrase a learner reads
              past — the design's note names it as an underlined phrase that
              should be a button. **The closing block is where the design puts
              it (`Today · to close`) and where it competes with nothing**,
              because every block's own action is behind the learner by then.

              **#160 IS UNTOUCHED BY THE MOVE: no count, no badge, no dot, no
              days-since**, and block 4's primary action is still *Write it*. */}
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
      {/* **#400 — THE ZERO CASE SAID *"0 cards reviewed today."* AND THAT
          SHIPPED.** #348's exact shape: a numeric zero on a report is a score,
          and a score of zero on a day nobody promised anything about is guilt
          with no banned word in it. The banned-phrase scan passed over it
          because the numeral is interpolated and the literal reads
          *" cards reviewed today."*.

          **THE FIX IS SILENCE, NOT A KINDER COUNT, AND THE REASON IS THAT THE
          BLOCK DOES NOT KNOW WHY THE NUMBER IS ZERO.** `cards_reviewed` counts
          rows in `card_reviews` for this session, so *nothing was due* and
          *block 1 was skipped* arrive as the same integer. **Any sentence about
          cards would be false in one of those two worlds** — and the one where
          it is false is the one where the learner already feels it.

          **CLAUDE.md §4: raises announced, drops silent.** Twenty cards is
          worth saying; zero is not a thing to remark on. **Absent, not an empty
          element** — the surrounding card still closes the session. */}
      {reviewed > 0 ? (
        <p className="text-sm leading-relaxed" data-testid="close-summary">
          {reviewed === 1
            ? "One card reviewed today."
            : `${reviewed} cards reviewed today.`}
        </p>
      ) : null}

      {/* **W13b/5 — THE CONVERSATION ENTRY POINT, design `1i`.** A filled button
          at the foot of the session, replacing the underlined phrase inside
          block 4.

          **THIS IS THE ONE PLACE THE SLICE RAISES EMPHASIS, AND THE RULE IT HAS
          TO CLEAR IS STATED RATHER THAN STEPPED AROUND.** W13b/3 §A wrote
          *never the primary call-to-action*, on #160. **#160's actual ruling
          forbids a COUNTER** — *"a tab whose counter accumulates while the
          learner is away is a backlog presented"* — **and there is still no
          counter here**: no count, no badge, no dot, nothing about days since
          the last conversation, and a learner who never presses it is told
          nothing about not having pressed it. **The emphasis clause is honoured
          by PLACEMENT: this is the closing block, after every block's own
          action, so it competes with none of them.** Block 4's primary action is
          still *Write it*. **Operator ruling 2026-09-07.** */}
      <div className="mt-5 border-t border-border pt-5">
        <Button
          asChild
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-semibold"
        >
          <Link href="/talk" data-testid="conversation-link">
            <Mic className="size-5" aria-hidden="true" />
            {CONVERSATION.entryAction}
          </Link>
        </Button>
        {/* Sets the expectation before the tap. **Nothing measures it and
            nothing reports on it afterwards** — it is not a target. */}
        <p className="mt-3 text-center text-sm text-muted-foreground">
          {CONVERSATION.entryCaption}
        </p>
      </div>
    </BlockShell>
  );
}
