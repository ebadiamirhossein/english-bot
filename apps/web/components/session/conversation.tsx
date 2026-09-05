"use client";

/**
 * W13b — block 4's conversation half, and the home entry point's target.
 *
 * **THE WAIT IS THE PRODUCT (§0, cost 3).** A turn takes 2–4 seconds and there
 * is deliberately no spinner, no progress bar and no "thinking…" that implies
 * it could be faster. What is rendered is a quiet ellipsis in the place the
 * reply will appear, which is what a person waiting for an answer sees anyway.
 *
 * **NO COUNT IS EVER SHOWN.** Not turns used, not turns left, not days since
 * the last conversation. #160 forbids a counter that accumulates while the
 * learner is away, and a remaining-turns figure is that counter running
 * backwards; PRD §8.6.4 calls a tally a score. The server sends `state`, which
 * is `open` or `closing`, and never a number.
 *
 * **THE VOICE CONTROL IS ABSENT, NOT DISABLED, WHEN THE LEARNER IS NOT ON THE
 * ALLOWLIST (#364).** The route answers 404 for the same reason: a blocked
 * learner must not be able to tell a consent gate from a feature that does not
 * exist, because a greyed-out button announces something she is excluded from.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CONVERSATION } from "./copy";

type Line = { who: "you" | "app"; text: string };
type Correction = {
  you_said: string;
  correct_form: string;
  explanation: string;
};

export function Conversation({ voice }: { voice: boolean }) {
  const [lines, setLines] = useState<Line[]>([]);
  const [topic, setTopic] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [capped, setCapped] = useState(false);
  const [trouble, setTrouble] = useState(false);
  const [corrections, setCorrections] = useState<Correction[] | null>(null);
  const [swapped, setSwapped] = useState(false);

  const api = process.env.NEXT_PUBLIC_API_URL ?? "";

  async function call(path: string, body?: unknown) {
    setTrouble(false);
    setBusy(true);
    try {
      const res = await fetch(`${api}/conversation/${path}`, {
        method: "POST",
        credentials: "include",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.status === 409) {
        // **The cap, or the spent alternative.** Both are stated conditions,
        // not errors, and neither reports a number.
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
  }

  async function start() {
    const out = await call("open");
    if (!out) return;
    setTopic(out.topic_label);
    setLines([{ who: "app", text: out.reply }]);
  }

  async function another() {
    const out = await call("alternative");
    if (!out) return;
    setSwapped(true);
    setTopic(out.topic_label);
    setLines([{ who: "app", text: out.reply }]);
  }

  async function send() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setLines((l) => [...l, { who: "you", text }]);
    const out = await call("turn", { text });
    if (!out) return;
    setLines((l) => [...l, { who: "app", text: out.reply }]);
    // **`closing` is the cap arriving AFTER this turn was answered.** The
    // learner's last message always gets a reply; the surface then ends itself.
    if (out.state === "closing") await end();
  }

  async function end() {
    const out = await call("close");
    setDone(true);
    if (out) setCorrections(out.corrections ?? []);
  }

  if (lines.length === 0 && !done) {
    return (
      <div data-testid="conversation-idle">
        <Button onClick={start} disabled={busy}>
          {CONVERSATION.start}
        </Button>
        {trouble ? <p className="mt-2 text-sm">{CONVERSATION.trouble}</p> : null}
      </div>
    );
  }

  if (done) {
    return (
      <div data-testid="conversation-closed">
        <p className="text-base">
          {capped ? CONVERSATION.capReached : CONVERSATION.closing}
        </p>
        {/* **SHOWN, NOT NECESSARILY WRITTEN (§2a.1).** Whether a correction
            reached the journal is decided server-side and is not on the wire:
            rendering *this one didn't count* would be a tally about the
            learner's own speech. A voice-only conversation shows these and
            wrote none of them. */}
        {corrections?.map((c, i) => (
          <div key={i} className="mt-3" data-testid="conversation-correction">
            <p className="text-sm opacity-70">{c.you_said}</p>
            <p className="text-base">{c.correct_form}</p>
            {c.explanation ? (
              <p className="text-sm opacity-70">{c.explanation}</p>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div data-testid="conversation">
      {topic ? (
        <p className="text-sm opacity-70" data-testid="conversation-topic">
          {topic}
        </p>
      ) : null}
      <div className="mt-3 space-y-3">
        {lines.map((l, i) => (
          <p key={i} className="text-base leading-relaxed" data-line={l.who}>
            {l.text}
          </p>
        ))}
        {busy ? <p className="opacity-50">{CONVERSATION.thinking}</p> : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <input
          className="flex-1 rounded-md border px-3 py-2 text-base"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
          aria-label={CONVERSATION.send}
        />
        <Button onClick={send} disabled={busy || !draft.trim()}>
          {CONVERSATION.send}
        </Button>
        {/* Absent, not disabled, when the learner is not on the allowlist. */}
        {voice ? (
          <Button variant="outline" disabled={busy} data-testid="conversation-speak">
            {CONVERSATION.speak}
          </Button>
        ) : null}
        {/* One swap, and only before the learner has spoken. */}
        {!swapped && lines.length === 1 ? (
          <Button variant="ghost" onClick={another} disabled={busy}>
            {CONVERSATION.another}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={end} disabled={busy}>
          {CONVERSATION.end}
        </Button>
      </div>
      {trouble ? <p className="mt-2 text-sm">{CONVERSATION.trouble}</p> : null}
    </div>
  );
}
