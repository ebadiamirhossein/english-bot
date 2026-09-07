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

import { Button } from "@/components/ui/button";
import { CloseOut, type Correction } from "./close-out";
import { CONVERSATION } from "./copy";
import { useRecorder } from "./use-recorder";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type Line = { who: "you" | "app"; text: string };

/**
 * `POST /conversation/close`'s response. **W13b/4.**
 *
 * **THIS TYPE IS HERE AND NOT IN `lib/api.ts` BECAUSE `lib/api.ts` HAS NO
 * CONVERSATION LAYER AT ALL** — the conversation surface is the one surface in
 * this app that calls `fetch` directly and reads `await res.json()` untyped,
 * which is exactly how a field can be returned for a week and never noticed.
 * Every other surface goes through a named function and a named type there.
 *
 * **Typing it locally is the small half of the fix and it is deliberately not
 * the whole one.** Migrating the six conversation endpoints into `lib/api.ts`
 * is a refactor of a shipped surface, not a line in a slice about the close-out
 * page, so it is FILED rather than improvised here.
 *
 * `conversation_id` is carried on the wire and read by nothing. That is not the
 * same finding as `did_well`: an id costs no generated tokens and says nothing
 * to a learner, so it is recorded and left alone.
 */
type CloseResult = {
  conversation_id: number;
  corrections: Correction[];
  /**
   * **The model's note on what the learner did well — generated on every close,
   * billed on every close, and rendered by nothing until W13b/4.**
   *
   * CLAUDE.md §4: *raises announced, drops silent*. The app was paying for the
   * raise and then swallowing it. `/write` has rendered the same field from
   * `POST /correct` since W9 (`app/(app)/write/page.tsx`), so this is the
   * shipped shape rather than a new idea.
   */
  did_well: string;
  unknown_words: string[];
};

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
  const [corrections, setCorrections] = useState<Correction[] | null>(null);
  const [didWell, setDidWell] = useState<string>("");
  const [words, setWords] = useState<string[]>([]);
  const [kept, setKept] = useState<Record<string, boolean>>({});

  const listEnd = useRef<HTMLDivElement | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);

  // New messages scroll into view. `block: "end"` rather than centring, so a
  // long reply lands with its first line readable.
  useEffect(() => {
    listEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [lines.length, busy]);

  const call = useCallback(async (path: string, body?: unknown) => {
    setTrouble(false);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/conversation/${path}`, {
        method: "POST",
        credentials: "include",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.status === 409) {
        // The cap, or the spent alternative. **Stated conditions, not errors,
        // and neither reports a number.**
        setCapped(true);
        return null;
      }
      if (!res.ok) {
        setTrouble(true);
        return null;
      }
      return await res.json();
    } catch {
      setTrouble(true);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  async function suggest() {
    const out = await call("topics");
    if (!out) return;
    setTopics(out.topics ?? []);
    // **THE GATE COMES FROM THE SERVER, NOT FROM A PROP** (#364). `/talk` has
    // no session payload to read it from, so this call carries it.
    if (typeof out.voice === "boolean") setMicAllowed(out.voice);
  }

  async function start(chosen?: string) {
    const out = await call("open", chosen ? { topic_label: chosen } : undefined);
    if (!out) return;
    setTopic(out.topic_label);
    setLines([{ who: "app", text: out.reply }]);
  }

  const end = useCallback(async () => {
    const out = (await call("close")) as CloseResult | null;
    setDone(true);
    if (out) {
      setCorrections(out.corrections ?? []);
      // **Passed through RAW.** Whitespace-is-absence is `CloseOut`'s rule and
      // lives there alone; trimming here as well put one rule in two homes, and
      // that is what let a `"   "` reach the component untrimmed by the other
      // path and render an empty paragraph.
      setDidWell(out.did_well ?? "");
      setWords(out.unknown_words ?? []);
    }
  }, [call]);

  async function send() {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    setLines((l) => [...l, { who: "you", text }]);
    const out = await call("turn", { text });
    if (!out) return;
    setLines((l) => [...l, { who: "app", text: out.reply }]);
    // `closing` is the cap arriving **after** this turn was answered.
    if (out.state === "closing") await end();
  }

  // §C — the microphone. **One recorder, shared with the shadow surface**
  // (`use-recorder.ts`, #190): MediaRecorder, a level meter on the real signal,
  // an elapsed counter, and teardown on every exit path including unmount.
  const onRecorded = useCallback(
    async (blob: Blob) => {
      setBusy(true);
      setTrouble(false);
      try {
        const res = await fetch(`${API_BASE_URL}/conversation/turn/voice`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": blob.type || "audio/webm" },
          body: blob,
        });
        if (res.status === 409) {
          setCapped(true);
          return;
        }
        if (!res.ok) {
          // 404 is the consent gate or an absent conversation, and they are
          // deliberately indistinguishable (#364). 422 is *heard nothing*.
          setTrouble(true);
          return;
        }
        const out = await res.json();
        setLines((l) => [...l, { who: "app", text: out.reply }]);
        if (out.state === "closing") await end();
      } catch {
        setTrouble(true);
      } finally {
        setBusy(false);
      }
    },
    [end],
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

  const shell = fullHeight
    ? "flex h-full min-h-0 flex-col"
    : "flex min-h-0 flex-col";

  // ── before the conversation starts ────────────────────────────────────────
  if (lines.length === 0 && !done) {
    return (
      <div className={`${shell} gap-3 p-4`} data-testid="conversation-idle">
        {topics === null ? (
          <Button onClick={suggest} disabled={busy}>
            {CONVERSATION.start}
          </Button>
        ) : (
          <div data-testid="conversation-topics">
            <p className="text-sm text-muted-foreground">{CONVERSATION.pick}</p>
            <div className="mt-3 flex flex-col gap-2">
              {topics.map((t) => (
                <Button
                  key={t}
                  variant="outline"
                  className="h-auto whitespace-normal py-3 text-left"
                  disabled={busy}
                  onClick={() => start(t)}
                >
                  {t}
                </Button>
              ))}
              <Button variant="ghost" onClick={suggest} disabled={busy}>
                {CONVERSATION.reshuffle}
              </Button>
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
        didWell={didWell}
        corrections={corrections ?? []}
        words={words}
        kept={kept}
        capped={capped}
        busy={busy}
        onKeep={async (w) => {
          const out = await call("save-word", { word: w });
          if (out) setKept((k) => ({ ...k, [w]: true }));
        }}
      />
    );
  }

  // ── the conversation ──────────────────────────────────────────────────────
  return (
    <div className={`${shell} h-full`} data-testid="conversation">
      {/* 6 — the topic stays put while the list scrolls under it. */}
      {topic ? (
        <header
          className="shrink-0 border-b bg-background px-4 py-3"
          data-testid="conversation-topic"
        >
          <p className="text-sm text-muted-foreground">{topic}</p>
        </header>
      ) : null}

      {/* 1 — THE scroll region. `min-h-0` is what bounds it inside the flex
          column; without it this grows and the page scrolls instead. */}
      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4"
        data-testid="conversation-log"
      >
        {lines.map((l, i) => (
          <div
            key={i}
            data-speaker={l.who}
            className={
              l.who === "you"
                ? "ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary/10 px-4 py-2"
                : "mr-auto max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2"
            }
          >
            {/* 2 — alignment AND background differ, and the label is there for
                anyone who cannot rely on either. */}
            <span className="sr-only">
              {l.who === "you" ? CONVERSATION.you : CONVERSATION.app}:{" "}
            </span>
            {/* **THREE SIGNALS, NONE OF THEM COLOUR** — the design's answer to
                the constraint and the strongest available. Alignment,
                container AND typeface differ: the app speaks in the display
                serif the app already loads, the learner in the body sans.
                `data-speaker` still carries it for the tests, because a test
                asserting a typeface asserts Tailwind exactly as one asserting
                a colour does. */}
            <p
              className={
                "whitespace-pre-wrap text-base leading-relaxed " +
                (l.who === "app" ? "font-heading" : "")
              }
            >
              {l.text}
            </p>
          </div>
        ))}

        {/* 5 — it is working. **No spinner, no bar, no estimate.** */}
        {busy ? (
          <div
            className="mr-auto max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2"
            data-speaker="app"
            data-testid="conversation-working"
          >
            <p className="text-base text-muted-foreground">
              {CONVERSATION.working}
            </p>
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
      <footer className="shrink-0 border-t bg-background px-4 py-3">
        {rec.recording ? (
          <div className="flex items-center gap-3" data-testid="conversation-recording">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-[width] duration-75"
                style={{ width: `${Math.round(rec.level * 100)}%` }}
                data-testid="conversation-level"
              />
            </div>
            <span className="tabular-nums text-sm text-muted-foreground">
              {rec.elapsed}s
            </span>
            <Button onClick={rec.stop}>{CONVERSATION.micStop}</Button>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <textarea
              ref={composer}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={4}
              aria-label={CONVERSATION.composerLabel}
              placeholder={CONVERSATION.placeholder}
              data-testid="conversation-composer"
              // 3 — **opens at four lines and grows to about seven, then
              // scrolls inside itself.** The design's measurement, and its
              // reason is that four lines is what people actually write; the
              // shipped single row meant the operator's sentence scrolled out
              // of view mid-thought. The send control cannot be pushed off
              // screen because the footer is pinned and this is what is
              // bounded.
              className="max-h-44 min-h-24 flex-1 resize-none overflow-y-auto rounded-md border bg-background px-3 py-2 text-base"
            />
            {/* Absent, not disabled, when the learner is not on the allowlist. */}
            {micAllowed ? (
              <Button
                variant="outline"
                onClick={rec.start}
                disabled={busy}
                data-testid="conversation-speak"
              >
                {CONVERSATION.micStart}
              </Button>
            ) : null}
            <Button onClick={send} disabled={busy || !draft.trim()}>
              {CONVERSATION.send}
            </Button>
          </div>
        )}
        <div className="mt-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={end}
            disabled={busy}
            data-testid="conversation-end"
          >
            {CONVERSATION.end}
          </Button>
        </div>
      </footer>
    </div>
  );
}
