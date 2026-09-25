"use client";

/**
 * The conversation. **W13b/3 §B — a real chat surface.**
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **EVERY REQUIREMENT HERE COMES FROM THE OPERATOR USING THE THING AND FINDING
 * IT UNUSABLE.** They are recorded as defects rather than as polish, because
 * the loop underneath them was working the whole time — the surface being
 * unusable was a UI finding, not a model finding (§D).
 *
 * 1. **FULL HEIGHT, AND THE PAGE DOES NOT SCROLL — THE CONVERSATION DOES.**
 *    The message list is its own scroll region and the composer is pinned
 *    below it. `min-h-0` on the flex child is the whole trick: without it the
 *    list grows to its content and the *page* scrolls instead, which is what
 *    happened when this was crammed into a card in block 4.
 * 2. **THE TWO SPEAKERS ARE VISUALLY DISTINCT** in alignment *and* background,
 *    not position alone. Before this, every message was the same colour and
 *    the same alignment and **a learner could not tell who said what.**
 *    `data-speaker` carries it for the tests, because a test that asserts a
 *    colour class asserts Tailwind rather than the thing that matters.
 * 3. **THE COMPOSER HOLDS WHAT IS TYPED.** A textarea that grows to a few
 *    lines and then scrolls internally. The operator's sentence scrolled out
 *    of a single-line input mid-thought; the send control is never pushed off
 *    screen.
 * 4. **ENTER SENDS, SHIFT+ENTER IS A NEWLINE.**
 * 5. **A VISIBLE IN-PROGRESS STATE.** *The wait is the product* still stands,
 *    so there is **no spinner and no progress bar** — nothing implying it
 *    could be faster or claiming to know how long is left. What there is: the
 *    surface says it is working.
 * 6. **THE TOPIC STAYS VISIBLE** at the top while the list scrolls under it.
 * 7. **THE END CONTROL IS ALWAYS REACHABLE AND IS NEVER THE EMPHASIS.**
 *
 * **NO COUNT, NO BADGE, NO DOT, NO *days since your last conversation*.**
 * #160's actual ruling, which forbids a counter rather than a page.
 * ────────────────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  ApiError,
  closeConversation,
  getConversationRungs,
  openConversation,
  saveConversationWord,
  sendConversationTurn,
  sendConversationVoice,
  suggestConversationTopics,
  type ConversationCorrection,
  type ConversationKind,
  type ConversationRungs,
  type ConversationTurn,
} from "@/lib/api";
import { CloseOut } from "./close-out";
import { CONVERSATION } from "./copy";
import { useKeyboardInset } from "./use-keyboard-inset";
import { useRecorder } from "./use-recorder";

type Line = { who: "you" | "app"; text: string };

/*
 * **#398, CLOSED BY W15: THIS FILE NO LONGER CALLS `fetch`.** It held the only
 * untyped network code in the app — a local `CloseResult` type and six raw
 * `fetch` calls reading `await res.json()` — which is how `did_well` was
 * returned for a month and rendered by nothing. Every call now goes through a
 * named function in `lib/api.ts` with a named type (`ConversationClose`,
 * `ConversationTurn`, …), so the compiler notices an unread field. *(The
 * `CloseResult` docstring that stood here recorded the half-fix and filed the
 * rest; the rest is this.)*
 */

export function Conversation({
  voice,
  fullHeight = false,
}: {
  voice?: boolean;
  fullHeight?: boolean;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [topic, setTopic] = useState<string | null>(null);
  const [topics, setTopics] = useState<string[] | null>(null);
  const [micAllowed, setMicAllowed] = useState<boolean>(Boolean(voice));
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [capped, setCapped] = useState(false);
  const [trouble, setTrouble] = useState(false);
  const [corrections, setCorrections] = useState<ConversationCorrection[] | null>(null);
  const [didWell, setDidWell] = useState<string>("");
  const [summary, setSummary] = useState<string>("");
  const [words, setWords] = useState<string[]>([]);
  const [kept, setKept] = useState<Record<string, boolean>>({});
  // W15. Which exchange is open, what the page can offer besides a talk, and
  // what a rung's close-out carries.
  const [kind, setKind] = useState<ConversationKind>("talk");
  const [rungs, setRungs] = useState<ConversationRungs | null>(null);
  const [covered, setCovered] = useState<string[]>([]);
  const [also, setAlso] = useState<string[]>([]);
  const [isEnglish, setIsEnglish] = useState(true);
  // #408: each offered word's token, held here and never rendered.
  const tokens = useRef<Record<string, string>>({});

  const listEnd = useRef<HTMLDivElement | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  // #409: the keyboard's overlap with this column's foot, on a full-height page.
  const keyboard = useKeyboardInset(root);

  // New messages scroll into view. `block: "end"` rather than centring, so a
  // long reply lands with its first line readable.
  useEffect(() => {
    listEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [lines.length, busy]);

  // **W15: THE RUNGS ARE A FREE READ ON LOAD.** `POST /conversation/topics` is
  // billed and stays behind the *Start talking* press (#399); what else the page
  // offers is a database read, so it is fetched once, here. A failure costs the
  // two cards and nothing else — the talk still works.
  useEffect(() => {
    let live = true;
    getConversationRungs()
      .then((out) => {
        if (!live) return;
        setRungs(out);
        if (typeof out?.voice === "boolean") setMicAllowed(out.voice);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  /**
   * One network call, with the page's three outcomes: a value, the day's cap
   * (`409` — **a stated condition, not an error, and it reports no number**),
   * or trouble. `busy` brackets it either way.
   */
  const call = useCallback(async <T,>(run: () => Promise<T>): Promise<T | null> => {
    setTrouble(false);
    setBusy(true);
    try {
      return await run();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setCapped(true);
      else setTrouble(true);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  async function suggest() {
    const out = await call(suggestConversationTopics);
    if (!out) return;
    setTopics(out.topics ?? []);
    // **THE GATE COMES FROM THE SERVER, NOT FROM A PROP** (#364). `/talk` has
    // no session payload to read it from, so this call carries it.
    if (typeof out.voice === "boolean") setMicAllowed(out.voice);
  }

  async function start(opening: ConversationKind, chosen?: string) {
    const out = await call(() => openConversation(opening, chosen));
    if (!out) return;
    setKind(opening);
    setTopic(out.topic_label);
    setLines([{ who: "app", text: out.reply }]);
  }

  const end = useCallback(async () => {
    const out = await call(closeConversation);
    setDone(true);
    if (out) {
      setCorrections(out.corrections ?? []);
      // **Passed through RAW.** Whitespace-is-absence is `CloseOut`'s rule and
      // lives there alone; trimming here as well put one rule in two homes, and
      // that is what let a `"   "` reach the component untrimmed by the other
      // path and render an empty paragraph.
      setDidWell(out.did_well ?? "");
      setSummary(out.summary ?? "");
      const offers = out.word_offers ?? [];
      tokens.current = Object.fromEntries(offers.map((o) => [o.word, o.token]));
      setWords(offers.map((o) => o.word));
      setCovered(out.covered ?? []);
      setAlso(out.also ?? []);
      setIsEnglish(out.is_english !== false);
    }
  }, [call]);

  /** A turn came back: what was heard (voice), the reply (a talk), and `closing`. */
  const landed = useCallback(
    async (out: ConversationTurn) => {
      // #427: a voice turn shows what Whisper heard as the learner's own line —
      // G3's bound on #381 assumed this and nothing did it.
      if (out.heard) setLines((l) => [...l, { who: "you", text: out.heard! }]);
      // A rung answers with an EMPTY reply: nothing to show until the close.
      if (out.reply) setLines((l) => [...l, { who: "app", text: out.reply }]);
      // `closing` is the cap arriving after this turn, or a rung's one turn.
      if (out.state === "closing") await end();
    },
    [end],
  );

  async function send() {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    setLines((l) => [...l, { who: "you", text }]);
    const out = await call(() => sendConversationTurn(text));
    if (out) await landed(out);
  }

  // §C — the microphone. **One recorder, shared with the shadow surface**
  // (`use-recorder.ts`, #190): MediaRecorder, a level meter on the real signal,
  // an elapsed counter, and teardown on every exit path including unmount.
  // 404 is the consent gate or an absent conversation, deliberately
  // indistinguishable (#364); 422 is *heard nothing*.
  const onRecorded = useCallback(
    async (blob: Blob) => {
      const out = await call(() => sendConversationVoice(blob));
      if (out) await landed(out);
    },
    [call, landed],
  );
  const rec = useRecorder(onRecorded);

  /**
   * **THE COMPOSER SPLITS FROM THE SEND CONTROL. W13b/4, operator ruling
   * 2026-09-07, and it is ONE condition rather than two.**
   *
   * **The textarea stays live while the reply is coming.** The design's note is
   * *"the composer stays live while it writes — you can keep typing"*, and the
   * wait is 2–4 seconds of the learner's thinking time: a box that goes dead
   * for it throws away the sentence they were forming. Shipped behaviour
   * disabled both.
   *
   * **Send stays held until the reply lands**, so a second turn cannot go out
   * in flight — that would interleave two turns on one conversation and the
   * server has no notion of which came first.
   *
   * **ENTER IS THE SAME CONTROL AS SEND, AND THE GUARD IS IN `send` ALONE.**
   * The first draft added `if (busy) return` here as well — and the red
   * demonstration proved it did nothing: removing it left the suite green,
   * because `send` already opens with `if (!text || busy) return`. **A guard
   * whose removal changes no behaviour is a second home for one rule**, and
   * the enforcement then lives in two places that can disagree. It is gone.
   * The button's `disabled` is presentation; `send` is the rule.
   */
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  // **W15: `flex-1` ON THE FULL-HEIGHT COLUMN, MEASURED IN THE FIRST BROWSER
  // RUN `/talk` EVER HAD (#401).** `h-full` alone did not resolve under the
  // `[contain:size]` wrapper, so the column was CONTENT-sized: the composer
  // floated under a short thread instead of sitting at the foot, and #409's
  // keyboard padding GREW the column rather than lifting the composer.
  // Measured at 390×768 (WebKit): wrapper 576 tall, column 486. `flex-1` makes
  // it the wrapper's height, so the padding shrinks the log and nothing else.
  const shell = fullHeight
    ? "flex h-full min-h-0 flex-1 flex-col"
    : "flex min-h-0 flex-col";

  // ── before the conversation starts ────────────────────────────────────────
  if (lines.length === 0 && !done) {
    return (
      <div
        className={`${shell} gap-4 overflow-y-auto px-5 py-6`}
        data-testid="conversation-idle"
      >
        {topics === null ? (
          <>
            {/* **THE PRESS STAYS AND IS NOW A REAL PRIMARY BUTTON (#399).** The
                design opens straight onto three cards; `suggest_topics` is a
                PROVIDER CALL, so that would spend money on every page load —
                including loads nobody uses. **Operator ruling 2026-09-07: the
                direct open is declined and the gate is kept.** What changes is
                that the gate stops looking incidental. */}
            <Button
              size="lg"
              className="h-14 w-full rounded-2xl text-base font-semibold"
              onClick={suggest}
              disabled={busy}
            >
              {CONVERSATION.start}
            </Button>
            {/* **W15 — THE TWO RUNGS, UNDER THE PRESS AND NEVER ABOVE IT.** The
                conversation stays this page's first action (W13b/3 §A); a rung
                is an offer beside it. **§1a is suspended for this run (ruling
                0.3)**, so these take `/talk`'s own conventions: the mono
                eyebrow, the serif card for the app's words, the bordered card.
                **A rung not on offer today is ABSENT, never greyed** — and
                there is no count, no *done today* and no dot (#160). */}
            {rungs?.answer || rungs?.retell ? (
              <section className="mt-2 flex flex-col gap-2.5" data-testid="conversation-rungs">
                <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
                  {CONVERSATION.rungsHeading}
                </p>
                {rungs.answer ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => start("answer")}
                    data-testid="rung-answer"
                    className="w-full rounded-2xl border border-border bg-card px-5 py-4 text-left shadow-sm transition-colors hover:border-primary disabled:opacity-60"
                  >
                    <span className="block font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
                      {CONVERSATION.answerEyebrow}
                    </span>
                    <span className="mt-2 block font-heading text-lg leading-snug">
                      {rungs.answer.prompt}
                    </span>
                  </button>
                ) : null}
                {rungs.retell ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => start("retell")}
                    data-testid="rung-retell"
                    className="w-full rounded-2xl border border-border bg-card px-5 py-4 text-left shadow-sm transition-colors hover:border-primary disabled:opacity-60"
                  >
                    <span className="block font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
                      {CONVERSATION.retellEyebrow}
                    </span>
                    <span className="mt-2 block font-heading text-lg leading-snug">
                      {CONVERSATION.retellCard}
                    </span>
                    {/* The title is the VIDEO's words, so it is set in the
                        body sans and muted — never the app's serif voice. */}
                    <span className="mt-1 block text-sm leading-snug text-muted-foreground">
                      {rungs.retell.label}
                    </span>
                  </button>
                ) : null}
              </section>
            ) : null}
          </>
        ) : (
          <div data-testid="conversation-topics">
            <h2 className="font-heading text-2xl leading-tight">
              {CONVERSATION.pick}
            </h2>
            <div className="mt-5 flex flex-col gap-2.5">
              {/* The design's serif cards. **A card and not a list row**: three
                  choices that each look like the beginning of something, which
                  is the whole difference between choosing and picking off a
                  menu. */}
              {topics.map((t) => (
                <button
                  key={t}
                  type="button"
                  disabled={busy}
                  onClick={() => start("talk", t)}
                  data-testid="topic-card"
                  className="w-full rounded-2xl border border-border bg-card px-5 py-4 text-left font-heading text-lg leading-snug shadow-sm transition-colors hover:border-primary disabled:opacity-60"
                >
                  {t}
                </button>
              ))}
              {/* The fourth action is TEXT and not a card, so it never competes
                  with the three. The design's own note. */}
              <button
                type="button"
                onClick={suggest}
                disabled={busy}
                className="mt-2 self-start py-3 text-sm font-medium text-primary"
              >
                {CONVERSATION.reshuffle}
              </button>
            </div>
          </div>
        )}
        {busy ? (
          <p className="text-sm text-muted-foreground">{CONVERSATION.working}</p>
        ) : null}
        {trouble ? <p className="text-sm">{CONVERSATION.trouble}</p> : null}
      </div>
    );
  }

  // ── after it ends ─────────────────────────────────────────────────────────
  // **W13b/4: the close-out is a surface of its own now** (`close-out.tsx`),
  // and this component keeps the one thing it owns — the single call to
  // `POST /conversation/close`, whose payload exists exactly once.
  if (done) {
    return (
      <CloseOut
        topic={topic}
        summary={summary}
        didWell={didWell}
        corrections={corrections ?? []}
        words={words}
        kept={kept}
        capped={capped}
        busy={busy}
        kind={kind}
        covered={covered}
        also={also}
        isEnglish={isEnglish}
        onKeep={async (w) => {
          // #408: the word goes back with the token its offer was signed with.
          const token = tokens.current[w] ?? "";
          const out = await call(() => saveConversationWord({ word: w, token }));
          if (out) setKept((k) => ({ ...k, [w]: true }));
        }}
      />
    );
  }

  // ── the conversation ──────────────────────────────────────────────────────
  const rung = kind !== "talk";
  return (
    <div
      ref={root}
      className={`${shell} h-full`}
      // #409: on a full-height page the column pads its own foot by the
      // keyboard's overlap, so the composer rises onto the keyboard and the
      // log above it shrinks. `0` when no keyboard is up.
      style={fullHeight && keyboard > 0 ? { paddingBottom: keyboard } : undefined}
      data-testid="conversation"
      data-kind={kind}
    >
      {/* **W13b/5 — THE SCREEN TITLE THE APP NEVER HAD, AND THE END CONTROL
          MOVED INTO IT.** The design puts a mono eyebrow at the top of every
          `/talk` state and the end control as a bordered pill at its right.
          Before this the screen opened on a muted topic line and nothing said
          where you were.

          **7 — the end control is now visibly a control.** It was a ghost
          button below the composer and read as bare text. It keeps its wording:
          the design labels it *End the conversation*, and **"That's enough for
          now" is deliberately kept** — the design's phrase describes the
          mechanism, ours declines to make stopping sound like abandoning
          something. The FORM is the design's; the words are the record's.

          **6 — the topic still stays put while the list scrolls under it**,
          which the design's thread does not show but which is a requirement
          taken from the operator using it. A design is evidence about intent,
          not about what was already learned. */}
      <header className="shrink-0 border-b bg-background px-5 pb-3 pt-4">
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
            {kind === "answer"
              ? CONVERSATION.answerTitle
              : kind === "retell"
                ? CONVERSATION.retellTitle
                : CONVERSATION.eyebrow}
          </span>
          <button
            type="button"
            onClick={end}
            disabled={busy}
            data-testid="conversation-end"
            className="shrink-0 rounded-full border border-border px-4 py-2.5 text-xs text-muted-foreground transition-colors hover:border-foreground hover:text-foreground disabled:opacity-50"
          >
            {CONVERSATION.end}
          </button>
        </div>
        {topic ? (
          <p
            // W15: ONE line, truncated. A rung's label is the unit's whole
            // can-do sentence, and at the height a keyboard leaves (477) three
            // wrapped lines pushed Send under the nav — measured, not guessed.
            className="mt-2 truncate text-sm text-muted-foreground"
            title={topic}
            data-testid="conversation-topic"
          >
            {topic}
          </p>
        ) : null}
      </header>

      {/* 1 — THE scroll region. `min-h-0` is what bounds it inside the flex
          column; without it this grows and the page scrolls instead. */}
      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4"
        data-testid="conversation-log"
      >
        {/* **W13b/5 — THE TURNS READ AS A THREAD. FOUR SIGNALS, NONE OF THEM
            COLOUR.** Before this both speakers were tinted bubbles with the
            speaker's name in an `sr-only` span — **invisible**, so on a phone
            the two sides were told apart by a background tint and an alignment
            and nothing else, which is what the operator saw and could not read.

            The design's answer, taken whole: **a VISIBLE mono label above each
            turn; the app unboxed and full width; the learner in a bordered card
            indented from the left; and the typeface split** already shipped in
            W13b/4. `data-speaker` still carries it for the tests, because a
            test asserting a class asserts Tailwind. */}
        {lines.map((l, i) => (
          <div
            key={i}
            data-speaker={l.who}
            className={l.who === "you" ? "flex flex-col items-end pl-10" : "pr-6"}
          >
            <span className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
              {l.who === "you" ? CONVERSATION.you : CONVERSATION.app}
            </span>
            <p
              className={
                l.who === "you"
                  ? "mt-1.5 whitespace-pre-wrap rounded-2xl rounded-br-sm border border-border bg-card px-4 py-2.5 text-base leading-relaxed"
                  : "mt-1.5 whitespace-pre-wrap font-heading text-lg leading-relaxed"
              }
            >
              {l.text}
            </p>
          </div>
        ))}

        {/* 5 — it is working. **No spinner, no bar, no estimate.** */}
        {busy ? (
          <div className="pr-6" data-speaker="app" data-testid="conversation-working">
            <span className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
              {rung ? CONVERSATION.reading : CONVERSATION.working}
            </span>
            {/* **Three dots, and they are NOT a spinner or a bar.** *The wait
                is the product*: nothing here implies it could be faster, claims
                to know how long is left, or apologises. They say the app is
                doing something, which is all the surface knows. */}
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
        ) : null}
        <div ref={listEnd} />
      </div>

      {trouble ? (
        <p className="shrink-0 px-4 text-sm">{CONVERSATION.trouble}</p>
      ) : null}
      {rec.unavailable ? (
        <p className="shrink-0 px-4 text-sm">{CONVERSATION.micTrouble}</p>
      ) : null}

      {/* 3 · 7 — pinned composer, and the end control lives beside it so it is
          always reachable without scrolling. */}
      {/* **W13b/5 — THE COMPOSER IS A BLOCK, NOT A BOX WITH BUTTONS BESIDE
          IT.** It was a `flex-1` field sharing one row with two controls, so on
          a phone it read as a small box floating at the left with the actions
          crowding it. The design gives the field the full width and puts the
          controls in a row beneath — which is also what lets both of them be
          thumb-sized rather than squeezed.

          **3 — four lines open, about seven before it scrolls**, kept from
          W13b/4. The send control still cannot be pushed off screen, because
          the footer is pinned and the textarea is what is bounded.

          **7 — the end control is NOT here any more.** It moved into the header
          as a bordered pill; below the composer, as a ghost button, it read as
          bare text. */}
      <footer className="shrink-0 border-t bg-background px-5 pb-5 pt-3">
        {rec.recording ? (
          <div className="flex items-center gap-3" data-testid="conversation-recording">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-[width] duration-75"
                style={{ width: `${Math.round(rec.level * 100)}%` }}
                data-testid="conversation-level"
              />
            </div>
            <span className="font-mono text-sm tabular-nums text-muted-foreground">
              {rec.elapsed}s
            </span>
            <Button onClick={rec.stop}>{CONVERSATION.micStop}</Button>
          </div>
        ) : (
          <>
            <textarea
              ref={composer}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={4}
              aria-label={CONVERSATION.composerLabel}
              placeholder={
                kind === "answer"
                  ? CONVERSATION.answerPlaceholder
                  : kind === "retell"
                    ? CONVERSATION.retellPlaceholder
                    : CONVERSATION.placeholder
              }
              data-testid="conversation-composer"
              // W15: on a SHORT screen (the height a keyboard leaves) the box
              // opens at two lines, not four, so Send stays above the nav. It
              // still scrolls internally, so nothing typed is lost.
              className="block max-h-44 min-h-24 w-full resize-none overflow-y-auto rounded-2xl border bg-background px-4 py-3 text-base [@media(max-height:560px)]:max-h-20 [@media(max-height:560px)]:min-h-0"
            />
            {/* **ICON AND WORD, NEVER ICON ALONE AND NEVER A BARE WORD.** The
                design's own note is that Speak and Send became a microphone and
                a send glyph *"with the words kept as labels, so neither reads
                as a bare link"*. The icons come from `lucide-react`, which the
                app ALREADY depends on and already uses in `bottom-nav` and
                `app-menu` — **no new dependency for this slice**. Each glyph is
                `aria-hidden`; the word is the accessible name, so nothing here
                is an icon a learner has to decode. */}
            <div className="mt-2.5 flex items-center gap-2.5">
              {/* Absent, not disabled, when the learner is not on the allowlist. */}
              {micAllowed ? (
                <button
                  type="button"
                  onClick={rec.start}
                  disabled={busy}
                  data-testid="conversation-speak"
                  className="flex shrink-0 items-center gap-2 rounded-full border border-border px-4 py-3 text-sm font-medium transition-colors hover:border-foreground disabled:opacity-50"
                >
                  <Mic className="size-4" aria-hidden="true" />
                  {CONVERSATION.micStart}
                </button>
              ) : null}
              <button
                type="button"
                onClick={send}
                disabled={busy || !draft.trim()}
                data-testid="conversation-send"
                className="flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-50"
              >
                <Send className="size-4" aria-hidden="true" />
                {CONVERSATION.send}
              </button>
            </div>
          </>
        )}
      </footer>
    </div>
  );
}
