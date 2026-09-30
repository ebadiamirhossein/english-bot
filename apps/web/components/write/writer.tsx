"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Look } from "@/components/session/close-out";
import { WRITE } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  getWriteToday,
  keepPhrase,
  requestCorrection,
  type CorrectionResult,
  type MoreNote,
  type NaturalSegment,
  type WordOffer,
  type WriteToday,
} from "@/lib/api";
import { WRITING_MAX_CHARS, WRITING_MIN_CHARS } from "@/lib/limits";

/**
 * The writing screen — design `W16-writing-output.dc.html`, frames `1d`–`1q`. W16a.
 *
 * **A COLUMN OF THREE: fixed head, flexible field, fixed button (`1j`).** Only
 * the field flexes, and nothing here is given a viewport height — #395 put
 * `/talk`'s composer below the fold with `h-[100dvh]` on a box that did not
 * start at the top of the viewport.
 *
 * **THE HEIGHT COMES FROM `app/(app)/write/page.tsx`'s `[contain:size]`, AND
 * THE HARNESS IS WHAT FOUND THAT IT WAS NEEDED.** `e2e/write.spec.ts` failed on
 * its first two runs — with `/talk`'s `h-full`, then with `flex-1 min-h-0` —
 * because the shell is a `min-h-dvh` column whose height follows its content:
 * the result grew the shell, the document scrolled and the button went below
 * the fold. **jsdom could not have seen any of it.** The measured geometry and
 * the fix are in the page's docstring; this root only has to be `flex-1 min-h-0`
 * inside a wrapper that has a real height.
 *
 * **What this screen never does, each a rule rather than a preference:**
 *  - **marks the learner's own text.** It is shown whole and unmarked; marks
 *    live in the cards (`1k`). No strike-through, no red, no squiggle, and no
 *    as-you-type feedback of any kind (`1f`).
 *  - **counts.** No sentence counter, no word count, no ring, no bar, no
 *    remaining characters (`1d`). The head collapses on LAYOUT — when the
 *    field's content overflows its box — and not on a count, because the design
 *    contradicted itself here (`1g` vs `1u`, D6) and a count computed to hide a
 *    line is still a count.
 *  - **shows a fallback opening line.** `did_well` is absent or it is rendered;
 *    there is no third option (Ruling 2).
 *  - **says how many of today's submissions are left.** The ceiling is a
 *    boolean from the server (Ruling 3).
 */

type Notice = null | "short" | "trouble" | "not_english";

type Phase =
  | { kind: "loading" }
  | { kind: "problem" }
  | { kind: "ceiling" }
  | { kind: "composing"; notice: Notice }
  | { kind: "reading" }
  | { kind: "result"; sent: string; result: CorrectionResult };

export function Writer() {
  const [today, setToday] = useState<WriteToday | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [text, setText] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  // `1g`, paragraph only: the collapsed prompt card taps to reopen, and a card the
  // learner reopened is not collapsed again under them while they type.
  const [reopened, setReopened] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(() => {
    setPhase({ kind: "loading" });
    getWriteToday()
      .then((t) => {
        setToday(t);
        setPhase(t.ceiling_reached ? { kind: "ceiling" } : { kind: "composing", notice: null });
      })
      .catch(() => setPhase({ kind: "problem" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // D6. Collapse once the text no longer fits its box, and stay collapsed while
  // there is text: expanding the head would shrink the field and overflow it
  // again, so re-expanding on every keystroke would flicker.
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    if (!text.trim()) {
      setCollapsed(false);
      return;
    }
    if (!reopened && el.scrollHeight > el.clientHeight + 1) setCollapsed(true);
  }, [text, phase.kind, reopened]);

  const back = today?.session_id != null ? "/session" : "/";
  // W16b: the paragraph needs its prompt; a paragraph day with none is not drawn.
  const kind = today?.day_kind;
  const prompt = kind === "paragraph" ? today?.prompt ?? null : null;
  const task =
    kind === "journal"
      ? { ...WRITE.journal, subline: WRITE.journal.length }
      : kind === "paragraph" && prompt
        ? { ...WRITE.paragraph, title: null, subline: WRITE.paragraph.subline }
        : null;
  const eyebrow = kind === "paragraph" && prompt ? WRITE.paragraph.eyebrow : WRITE.eyebrow;

  async function submit() {
    const trimmed = text.trim();
    if (trimmed.length < WRITING_MIN_CHARS) {
      // `1h`: the refusal, the text left in place, focus kept, no request.
      setPhase({ kind: "composing", notice: "short" });
      setReopened(false);
      field.current?.focus();
      return;
    }
    // `1i`: the keyboard goes away and the text goes read-only for the call,
    // because the correction is written against exactly what was sent.
    field.current?.blur();
    setPhase({ kind: "reading" });
    try {
      const result = await requestCorrection(trimmed, {
        dayKind: today?.day_kind ?? "journal",
        sessionId: today?.session_id ?? null,
      });
      setPhase(
        result.is_english
          ? { kind: "result", sent: trimmed, result }
          : { kind: "composing", notice: "not_english" },
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        // Finding (c): the server refused the kind this screen was shown — a
        // Thursday paragraph left open into Friday (or a Thursday with no unit
        // task). Ask for today's task again; `text` is state, so it survives.
        // No notice: nothing went wrong that the learner did.
        load();
        return;
      }
      setPhase(
        error instanceof ApiError && error.status === 409
          ? { kind: "ceiling" }
          : { kind: "composing", notice: "trouble" },
      );
    }
  }

  const showLeave = phase.kind === "composing" || phase.kind === "loading" || phase.kind === "problem";

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="write-screen" data-phase={phase.kind}>
      <header className="flex shrink-0 items-center justify-between gap-3 pb-3">
        <span className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
          {eyebrow}
        </span>
        {showLeave ? (
          <Link
            href={back}
            data-testid="write-leave"
            className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-border px-4 text-xs text-muted-foreground transition-colors hover:border-foreground hover:text-foreground"
          >
            {WRITE.leave}
          </Link>
        ) : null}
      </header>

      {phase.kind === "problem" || (phase.kind !== "loading" && phase.kind !== "ceiling" && !task) ? (
        <div className="space-y-3" data-testid="write-problem">
          <p className="text-base leading-relaxed">{WRITE.trouble}</p>
          <Button type="button" className="min-h-11" onClick={load}>
            {WRITE.retry}
          </Button>
        </div>
      ) : null}

      {phase.kind === "ceiling" ? (
        <p className="text-base leading-relaxed" data-testid="write-ceiling">
          {WRITE.ceiling}
        </p>
      ) : null}

      {task && (phase.kind === "composing" || phase.kind === "reading") ? (
        <>
          {phase.kind === "reading" ? (
            <div className="shrink-0 pb-3" data-testid="write-reading">
              <span className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
                {WRITE.reading}
              </span>
              <div className="mt-2 flex h-4 items-center gap-1.5" aria-hidden="true">
                {[0, 1, 2].map((n) => (
                  <span
                    key={n}
                    className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary"
                    style={{ animationDelay: `${n * 180}ms` }}
                  />
                ))}
              </div>
            </div>
          ) : collapsed && prompt ? (
            <button
              type="button"
              onClick={() => {
                setCollapsed(false);
                setReopened(true);
              }}
              className="flex min-h-11 w-full shrink-0 items-center truncate pb-2 text-left font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground"
              data-testid="write-task-strip"
            >
              {task.strip}
            </button>
          ) : collapsed ? (
            <p
              className="shrink-0 truncate pb-2 font-heading text-base text-muted-foreground"
              data-testid="write-task-strip"
            >
              {task.strip}
            </p>
          ) : prompt ? (
            // **W16b: the head SHRINKS and scrolls, the field keeps two lines.** The
            // harness found that at keyboard height the prompt card plus its line
            // pushed *Read it over* under the shell's bottom nav (1e, 1g reopened).
            // A shrinkable head means the prompt scrolls inside its own region
            // before the button is ever covered — no viewport unit anywhere.
            <div className="min-h-0 shrink space-y-2 overflow-y-auto pb-3" data-testid="write-task-head">
              <section className="rounded-2xl border border-border bg-card p-4" data-testid="write-prompt-card">
                <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
                  {WRITE.paragraph.promptLabel}
                </p>
                <p className="mt-1.5 font-heading text-[1.0625rem] leading-snug" data-testid="write-prompt">
                  {prompt}
                </p>
              </section>
              {phase.kind === "composing" && phase.notice === "short" ? null : (
                <p className="text-sm text-muted-foreground" data-testid="write-length-line">
                  {task.subline}
                </p>
              )}
            </div>
          ) : (
            <div className="shrink-0 space-y-1 pb-3" data-testid="write-task-head">
              <h1 className="font-heading text-[1.5625rem] leading-tight">{task.title}</h1>
              {phase.kind === "composing" && phase.notice === "short" ? null : (
                <p className="text-sm text-muted-foreground" data-testid="write-length-line">
                  {task.subline}
                </p>
              )}
            </div>
          )}

          <textarea
            ref={field}
            value={text}
            onChange={(e) => setText(e.target.value)}
            readOnly={phase.kind === "reading"}
            maxLength={WRITING_MAX_CHARS}
            aria-label={WRITE.fieldLabel}
            placeholder={task.placeholder}
            data-testid="write-field"
            className={`block min-h-16 w-full flex-1 resize-none overflow-y-auto rounded-2xl border border-border bg-card px-4 py-3 text-[1.03rem] leading-[1.6] outline-none transition-opacity focus-visible:border-ring ${
              phase.kind === "reading" ? "opacity-60" : ""
            }`}
          />

          {phase.kind === "composing" ? (
            <div className="shrink-0 space-y-2 pt-3">
              {phase.notice ? (
                <p className="text-sm leading-relaxed" data-testid="write-notice" data-notice={phase.notice}>
                  {phase.notice === "short"
                    ? WRITE.short
                    : phase.notice === "trouble"
                      ? WRITE.trouble
                      : WRITE.notEnglish}
                </p>
              ) : null}
              <Button
                type="button"
                size="lg"
                data-testid="write-submit"
                className="h-14 w-full rounded-2xl text-base font-semibold"
                onClick={() => void submit()}
              >
                {phase.notice === "trouble" ? WRITE.retry : WRITE.submit}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}

      {phase.kind === "result" ? (
        <Result sent={phase.sent} result={phase.result} back={back} paragraph={kind === "paragraph"} />
      ) : null}
    </div>
  );
}

/** The *in your deck* diamond. The design says it is "already used at /talk"; it
 * is not — only the triangle exists — so it is drawn once, here (W16b). */
function Diamond() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M5 0 10 5 5 10 0 5z" fill="currentColor" />
    </svg>
  );
}

function Result({
  sent,
  result,
  back,
  paragraph,
}: {
  sent: string;
  result: CorrectionResult;
  back: string;
  paragraph: boolean;
}) {
  const corrections = result.corrections;
  const structure = result.structure ?? [];
  const offers = result.word_offers ?? [];
  // W33 (B): both come in the ONE response already in hand — a button press
  // only shows what is here, and never asks the server for anything.
  const more = paragraph ? [] : result.more ?? [];
  const natural = paragraph ? [] : result.natural ?? [];
  const [showAll, setShowAll] = useState(false);
  const [showNatural, setShowNatural] = useState(false);
  const moreRef = useRef<HTMLElement>(null);
  const naturalRef = useRef<HTMLElement>(null);
  // What was just opened is brought into view inside the result's own scroll
  // region: on a phone the buttons sit near the bottom, and a section that opens
  // below the fold looks like a button that did nothing.
  useEffect(() => {
    if (showAll) moreRef.current?.scrollIntoView?.({ block: "start" });
  }, [showAll]);
  useEffect(() => {
    if (showNatural) naturalRef.current?.scrollIntoView?.({ block: "start" });
  }, [showNatural]);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pb-4" data-testid="write-result">
        {/* `1n`: on the paragraph the structure prose LEADS — it is about the
            whole piece. Prose that quotes the learner, never named dimensions
            (Q3). Absent when the gate refused it. */}
        {structure.length > 0 ? (
          <section className="space-y-3" data-testid="write-structure">
            <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
              {WRITE.structureHeading}
            </p>
            {structure.map((para, i) => (
              <p
                key={i}
                className="font-heading text-[1.125rem] leading-[1.55]"
                data-speaker="app"
                data-testid="write-structure-paragraph"
              >
                {para.segments.map((segment, j) =>
                  segment.quote ? (
                    <em key={j} data-testid="write-structure-quote">
                      {segment.text}
                    </em>
                  ) : (
                    <span key={j}>{segment.text}</span>
                  ),
                )}
              </p>
            ))}
          </section>
        ) : null}
        {/* Ruling 2: absent, never blank, never a fallback. */}
        {result.did_well ? (
          <p className="font-heading text-[1.3125rem] leading-snug" data-speaker="app" data-testid="write-opening">
            {result.did_well}
          </p>
        ) : null}

        <section className="space-y-2">
          <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
            {WRITE.whatYouWrote}
          </p>
          {/* Whole and unmarked. The first thing on the screen is what they
              wrote, not what was wrong with it (`1k`). */}
          <p className="whitespace-pre-wrap text-[1.03rem] leading-[1.6]" data-speaker="you" data-testid="write-written">
            {sent}
          </p>
        </section>

        {/* `1m`: no corrections removes the whole block, heading included. */}
        {corrections.length > 0 ? (
          <section className="space-y-3" data-testid="write-corrections">
            <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
              {WRITE.worthALook}
            </p>
            {!paragraph && corrections.length === 2 ? (
              <p className="text-sm text-muted-foreground" data-testid="write-picked">
                {WRITE.pickedTwo}
              </p>
            ) : null}
            {corrections.map((c, i) => (
              <article
                key={i}
                className="rounded-2xl border border-caution-border bg-caution p-4"
                data-testid="write-correction"
              >
                {c.label ? (
                  <p
                    className="flex items-center gap-2 font-mono text-[0.625rem] uppercase tracking-[0.11em] text-caution-foreground"
                    data-testid="write-correction-label"
                  >
                    <Look />
                    {c.label}
                  </p>
                ) : null}
                <p
                  className="mt-2 text-[0.97rem] leading-normal text-muted-foreground underline decoration-dotted underline-offset-4"
                  data-speaker="you"
                  data-testid="write-correction-said"
                >
                  {c.you_said}
                </p>
                <p
                  className="mt-1.5 font-heading text-[1.0625rem] leading-normal"
                  data-speaker="app"
                  data-testid="write-correction-better"
                >
                  {c.correct_form}
                </p>
                <p className="mt-2 text-sm leading-normal text-muted-foreground" data-testid="write-correction-why">
                  {c.explanation}
                </p>
              </article>
            ))}
          </section>
        ) : null}

        {/* W33 (B) — the operator's request of 2026-09-30. The two above stay the
            default; these two quiet buttons open the rest and the rewrite. Each
            is drawn only when there is something behind it, and neither says how
            many (#160). */}
        {more.length > 0 || natural.length > 0 ? (
          <div className="flex flex-wrap gap-2" data-testid="write-more-controls">
            {more.length > 0 ? (
              <button
                type="button"
                data-testid="write-show-all"
                aria-expanded={showAll}
                aria-controls="write-more"
                onClick={() => setShowAll((open) => !open)}
                className={QUIET}
              >
                {showAll ? WRITE.showFewer : WRITE.showAll}
              </button>
            ) : null}
            {natural.length > 0 ? (
              <button
                type="button"
                data-testid="write-show-natural"
                aria-expanded={showNatural}
                aria-controls="write-natural"
                onClick={() => setShowNatural((open) => !open)}
                className={QUIET}
              >
                {showNatural ? WRITE.hideNatural : WRITE.showNatural}
              </button>
            ) : null}
          </div>
        ) : null}

        {showAll && more.length > 0 ? <MoreNotes notes={more} anchor={moreRef} /> : null}
        {showNatural && natural.length > 0 ? <Natural segments={natural} anchor={naturalRef} /> : null}

        {/* `1o`: last on the screen, and absent — heading and all — when nothing
            survived the offer rule. No gloss: nothing is generated while the
            learner waits, so the row carries the sentence the deck stores. */}
        {offers.length > 0 ? (
          <section className="space-y-2" data-testid="write-keep">
            <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
              {WRITE.keepHeading}
            </p>
            <p className="text-sm text-muted-foreground" data-testid="write-keep-intro">
              {offers.length === 2 ? WRITE.keepIntroTwo : WRITE.keepIntroOne}
            </p>
            <div>
              {offers.map((offer) => (
                <KeepRow key={offer.phrase} offer={offer} />
              ))}
            </div>
          </section>
        ) : null}
      </div>

      <div className="shrink-0 pt-3">
        <Button asChild size="lg" className="h-14 w-full rounded-2xl text-base font-semibold" data-testid="write-back">
          <Link href={back}>{WRITE.back}</Link>
        </Button>
      </div>
    </>
  );
}


/** W33 (B). The quiet button: `KeepRow`'s outline pill, 44 tall. */
const QUIET =
  "inline-flex min-h-11 items-center rounded-full border border-border px-4 text-sm font-medium transition-colors hover:border-foreground";

/** W33 (B). The other notes — a correction card's anatomy, smaller. Shown, never journaled. */
function MoreNotes({ notes, anchor }: { notes: MoreNote[]; anchor: React.RefObject<HTMLElement | null> }) {
  return (
    <section id="write-more" ref={anchor} className="space-y-2" data-testid="write-more">
      <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
        {WRITE.moreHeading}
      </p>
      {notes.map((n, i) => (
        <article
          key={i}
          className="rounded-xl border border-caution-border bg-caution px-3.5 py-3"
          data-testid="write-more-note"
        >
          <p
            className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-caution-foreground"
            data-testid="write-more-label"
          >
            {WRITE.moreKinds[n.kind] ?? WRITE.moreKinds.grammar}
          </p>
          <p
            className="mt-1.5 text-sm leading-normal text-muted-foreground underline decoration-dotted underline-offset-4"
            data-speaker="you"
            data-testid="write-more-said"
          >
            {n.you_said}
          </p>
          <p className="mt-1 font-heading text-[0.97rem] leading-normal" data-speaker="app" data-testid="write-more-better">
            {n.correct_form}
          </p>
          <p className="mt-1.5 text-[0.8125rem] leading-normal text-muted-foreground" data-testid="write-more-why">
            {n.explanation}
          </p>
        </article>
      ))}
    </section>
  );
}

/** W33 (B). The whole entry as a friend might say it; the changed words marked.
 * The learner's own text above stays whole and unmarked (`1k`) — the marks are
 * on the rewrite only, and they are a highlight, never a red or a strike. */
function Natural({ segments, anchor }: { segments: NaturalSegment[]; anchor: React.RefObject<HTMLElement | null> }) {
  return (
    <section id="write-natural" ref={anchor} className="space-y-2" data-testid="write-natural">
      <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
        {WRITE.naturalHeading}
      </p>
      <p
        className="whitespace-pre-wrap font-heading text-[1.0625rem] leading-[1.6]"
        data-speaker="app"
        data-testid="write-natural-text"
      >
        {segments.map((s, i) =>
          s.changed ? (
            <mark
              key={i}
              className="rounded-sm bg-accent px-0.5 text-accent-foreground"
              data-testid="write-natural-changed"
            >
              {s.text}
            </mark>
          ) : (
            <span key={i}>{s.text}</span>
          ),
        )}
      </p>
      <p className="text-sm text-muted-foreground" data-testid="write-natural-note">
        {WRITE.naturalNote}
      </p>
    </section>
  );
}

/** `1o`'s row: offer → *In your deck*, or *In your deck* as it arrives. */
function KeepRow({ offer }: { offer: WordOffer }) {
  const [kept, setKept] = useState(offer.in_deck);
  const [busy, setBusy] = useState(false);

  async function keep() {
    setBusy(true);
    try {
      await keepPhrase(offer);
      setKept(true);
    } catch {
      // No toast and no error copy (`1o`): the row simply stays offerable.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="flex items-center justify-between gap-3 border-b border-border py-3 last:border-b-0"
      data-testid="write-keep-row"
      data-state={kept ? "in_deck" : "offer"}
    >
      <div className="min-w-0">
        <p className="font-heading text-base font-semibold leading-tight" data-testid="write-keep-phrase">
          {offer.phrase}
        </p>
        <p className="mt-1 text-sm leading-snug text-muted-foreground" data-testid="write-keep-sentence">
          {offer.sentence}
        </p>
      </div>
      {kept ? (
        <span
          className="inline-flex min-h-11 shrink-0 items-center gap-1.5 text-sm text-muted-foreground"
          data-testid="write-keep-in-deck"
        >
          <Diamond />
          {WRITE.inDeck}
        </span>
      ) : (
        <button
          type="button"
          onClick={() => void keep()}
          disabled={busy}
          data-testid="write-keep-button"
          className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-border px-4 text-sm font-medium transition-colors hover:border-foreground disabled:opacity-50"
        >
          {WRITE.keep}
        </button>
      )}
    </div>
  );
}
