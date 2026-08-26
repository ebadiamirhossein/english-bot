"use client";

import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ApiError, requestCorrection, type CorrectionResult } from "@/lib/api";
import { CORRECTION_MAX_CHARS, CORRECTION_MIN_CHARS } from "@/lib/limits";

type State =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "done"; result: CorrectionResult }
  | { kind: "problem"; message: string };

/**
 * "Write anything" — the first screen in this app that teaches.
 *
 * Tone is the whole design here (CLAUDE.md §4). This is the one place in the
 * product that tells someone their English was wrong, so:
 *
 *  - **nothing is red.** The palette has no red in it by design; errors are
 *    shown in the same warm teal as everything else. A correction is
 *    information, not an alarm.
 *  - **what you wrote is never struck through or marked.** It is set in muted
 *    text and left alone. The emphasis goes on the better version, which is
 *    the part worth reading twice.
 *  - **the praise is always shown**, including when there are corrections —
 *    that is the v2 shape and it is deliberate.
 *  - **"no errors" is a real result with real content**, not an empty state.
 */
export default function WritePage() {
  const [text, setText] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const trimmed = text.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < CORRECTION_MIN_CHARS;
  const remaining = CORRECTION_MAX_CHARS - trimmed.length;

  async function check() {
    setState({ kind: "checking" });
    try {
      setState({ kind: "done", result: await requestCorrection(trimmed) });
    } catch (error) {
      setState({
        kind: "problem",
        message:
          error instanceof ApiError && error.status === 503
            ? "That didn’t come back. Give it a moment and try again."
            : error instanceof Error
              ? error.message
              : "That didn’t work. Try again in a moment.",
      });
    }
  }

  return (
    <>
      <PageHeader eyebrow="Write anything" title="Say it your way.">
        A sentence, a paragraph, whatever’s on your mind. You’ll get back what a
        fluent speaker would have said — and why.
      </PageHeader>

      <section className="space-y-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          maxLength={CORRECTION_MAX_CHARS}
          placeholder="Yesterday I go to the shop and buy two breads…"
          className="w-full resize-y rounded-2xl border border-border bg-card p-4 text-base leading-relaxed outline-none transition-colors placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {tooShort
              ? `A few more words — ${CORRECTION_MIN_CHARS} characters or so.`
              : " "}
          </span>
          {remaining < 120 ? <span>{remaining} left</span> : null}
        </div>
        <Button
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-semibold"
          disabled={
            state.kind === "checking" ||
            trimmed.length < CORRECTION_MIN_CHARS ||
            trimmed.length > CORRECTION_MAX_CHARS
          }
          onClick={check}
        >
          {state.kind === "checking" ? "Reading it…" : "Check it"}
        </Button>
      </section>

      {state.kind === "problem" ? (
        <p className="text-center text-sm text-muted-foreground">
          {state.message}
        </p>
      ) : null}

      {state.kind === "done" ? <Result result={state.result} /> : null}
    </>
  );
}

function Result({ result }: { result: CorrectionResult }) {
  if (!result.is_english) {
    return (
      <section className="rounded-2xl border border-border bg-card p-5">
        <p className="text-sm leading-relaxed">
          That looks like it’s in another language — write it in English and
          I’ll take a look.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      {result.corrections.map((c, i) => (
        <article
          key={`${c.error_type}-${i}`}
          className="space-y-2.5 rounded-2xl border border-border bg-card p-5"
        >
          {/* What you wrote. Muted and unmarked — never struck through. */}
          <p className="text-sm leading-relaxed text-muted-foreground">
            {c.you_said}
          </p>
          {/* The version worth remembering. This is where the emphasis goes. */}
          <p className="font-heading text-lg leading-snug text-primary">
            {c.correct_form}
          </p>
          {/* The explanation stands alone. The Murphy citation that sat
              here from W3 until 2026-08-26 is gone by operator ruling (#183):
              most learners own no copy and some own a different edition, so a
              unit number was clutter for nearly everyone who read it. The
              column stays as an operator note; nothing renders it. */}
          <p className="text-sm leading-relaxed">{c.explanation}</p>
        </article>
      ))}

      {/* Always shown, corrections or not — the v2 shape, and the point. */}
      {result.did_well ? (
        <p className="flex gap-2.5 rounded-2xl bg-accent/60 p-4 text-sm leading-relaxed text-accent-foreground">
          <span aria-hidden>👍</span>
          <span>{result.did_well}</span>
        </p>
      ) : null}
    </section>
  );
}
