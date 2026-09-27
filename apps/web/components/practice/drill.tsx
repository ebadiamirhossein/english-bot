"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { CardImage } from "@/components/cards/card-image";
import { PRACTICE } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import {
  answerPractice,
  practiceAudioUrl,
  startPractice,
  type PracticeExercise,
  type PracticeOutcome,
} from "@/lib/api";

const PROMPT: Record<PracticeExercise["kind"], string> = {
  picture_to_word: PRACTICE.pictureToWord,
  word_to_picture: PRACTICE.wordToPicture,
  hear_type: PRACTICE.hearType,
  meaning_type: PRACTICE.meaningType,
};

/**
 * The word drill. **W31d** — W24f, un-deferred by C6.
 *
 * One exercise at a time, from the learner's own cards, due first. **No score,
 * no count, no running tally of how many are left** (CLAUDE.md §4, #160). An answer is followed by the
 * word and its whole line — the sentence is where the word lives (PRD §2.6.3)
 * — and a wrong one by *"It's “…”."*, never a verdict about the learner.
 *
 * **Grading is the server's**: a due card is graded through FSRS, a top-up
 * card is practice only (Q8). The client never decides which.
 */
export function Drill() {
  const [exercises, setExercises] = useState<PracticeExercise[] | "loading" | "unavailable">(
    "loading",
  );
  const [index, setIndex] = useState(0);
  const [outcome, setOutcome] = useState<PracticeOutcome | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  /** A picture in a picture exercise failed to load: the exercise cannot be
   * answered, so it is skipped — nothing sent, nothing graded. */
  const [pictureGone, setPictureGone] = useState(false);
  const onGone = useCallback(() => setPictureGone(true), []);
  const shownAt = useRef(Date.now());

  const load = useCallback(() => {
    setExercises("loading");
    setIndex(0);
    setOutcome(null);
    startPractice()
      .then((r) => setExercises(r.exercises))
      .catch(() => setExercises("unavailable"));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    shownAt.current = Date.now();
    setTyped("");
    setPictureGone(false);
  }, [index]);

  if (exercises === "loading") {
    return <p className="text-sm text-muted-foreground" data-testid="drill-loading">{PRACTICE.loading}</p>;
  }
  if (exercises === "unavailable") {
    return <p className="text-sm text-muted-foreground" data-testid="drill-unavailable">{PRACTICE.unavailable}</p>;
  }
  if (exercises.length === 0) {
    return (
      <div className="space-y-4" data-testid="drill-none">
        <p className="text-sm text-muted-foreground">{PRACTICE.none}</p>
        <BackLink />
      </div>
    );
  }
  if (index >= exercises.length) {
    return (
      <div className="space-y-4" data-testid="drill-done">
        <p className="text-base">{PRACTICE.done}</p>
        <div className="flex flex-wrap gap-3">
          <Button className="min-h-11" data-testid="drill-again" onClick={load}>
            {PRACTICE.again}
          </Button>
          <BackLink />
        </div>
      </div>
    );
  }

  const ex = exercises[index];
  const submit = (response: string) => {
    if (busy || outcome || !response.trim()) return;
    setBusy(true);
    answerPractice({
      card_id: ex.card_id,
      kind: ex.kind,
      response: response.trim(),
      duration_ms: Date.now() - shownAt.current,
    })
      .then(setOutcome)
      .catch(() => setOutcome(null))
      .finally(() => setBusy(false));
  };

  return (
    <section className="space-y-4" data-testid="drill" data-kind={ex.kind}>
      <p className="text-sm font-medium text-muted-foreground" data-testid="drill-prompt">
        {PROMPT[ex.kind]}
      </p>

      {ex.kind === "picture_to_word" && ex.image ? <CardImage image={ex.image} onGone={onGone} /> : null}
      {ex.kind === "word_to_picture" ? (
        <p lang="en" className="text-3xl font-semibold" data-testid="drill-word">{ex.word}</p>
      ) : null}
      {ex.kind === "meaning_type" ? (
        <p lang="en" className="text-lg leading-relaxed" data-testid="drill-definition">{ex.definition}</p>
      ) : null}
      {ex.kind === "hear_type" ? (
        <audio
          controls
          preload="none"
          crossOrigin="use-credentials"
          src={practiceAudioUrl(ex.card_id)}
          data-testid="drill-audio"
          aria-label={PRACTICE.play}
          className="w-full"
        />
      ) : null}
      {ex.sentence && !outcome ? (
        <p lang="en" className="text-sm italic text-muted-foreground" data-testid="drill-sentence">
          {ex.sentence}
        </p>
      ) : null}

      {ex.kind === "picture_to_word" && !pictureGone ? (
        <div className="grid grid-cols-2 gap-2" data-testid="drill-options">
          {ex.options.map((o) => (
            <Button
              key={o.value}
              variant="outline"
              className="min-h-11 text-base"
              data-testid="drill-option"
              disabled={Boolean(outcome) || busy}
              onClick={() => submit(o.value)}
            >
              {o.label}
            </Button>
          ))}
        </div>
      ) : null}
      {ex.kind === "word_to_picture" && !pictureGone ? (
        <div className="grid grid-cols-2 gap-3" data-testid="drill-options">
          {ex.options.map((o) => (
            <button
              key={o.value}
              type="button"
              data-testid="drill-option"
              disabled={Boolean(outcome) || busy}
              onClick={() => submit(o.value)}
              className="rounded-lg border p-1 text-left transition-colors hover:bg-muted disabled:opacity-100"
            >
              {o.image ? <CardImage image={o.image} onGone={onGone} /> : null}
            </button>
          ))}
        </div>
      ) : null}
      {ex.kind === "hear_type" || ex.kind === "meaning_type" ? (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            submit(typed);
          }}
        >
          <input
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            disabled={Boolean(outcome) || busy}
            aria-label={PRACTICE.typeHere}
            placeholder={PRACTICE.typeHere}
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="off"
            spellCheck={false}
            lang="en"
            data-testid="drill-input"
            className="min-h-11 flex-1 rounded-md border bg-background px-3 text-base"
          />
          <Button type="submit" className="min-h-11" data-testid="drill-check" disabled={Boolean(outcome) || busy}>
            {PRACTICE.check}
          </Button>
        </form>
      ) : null}

      {pictureGone && !outcome ? (
        <div className="space-y-2 rounded-lg bg-muted/50 p-3" data-testid="drill-picture-gone">
          <p className="text-sm">{PRACTICE.pictureGone}</p>
          <Button className="min-h-11" data-testid="drill-next" onClick={() => setIndex((i) => i + 1)}>
            {PRACTICE.next}
          </Button>
        </div>
      ) : null}

      {outcome ? (
        <div className="space-y-2 rounded-lg bg-muted/50 p-3" data-testid="drill-outcome" data-correct={String(outcome.correct)}>
          <p className="font-medium">
            {outcome.correct ? PRACTICE.yes : PRACTICE.itIs.replace("{word}", outcome.answer)}
          </p>
          {outcome.sentence ? (
            <p lang="en" className="text-sm italic text-muted-foreground" data-testid="drill-full-sentence">
              {outcome.sentence}
            </p>
          ) : null}
          {outcome.meaning && ex.kind !== "meaning_type" ? (
            <p lang="en" className="text-sm text-muted-foreground">{outcome.meaning}</p>
          ) : null}
          <Button className="min-h-11" data-testid="drill-next" onClick={() => { setOutcome(null); setIndex((i) => i + 1); }}>
            {PRACTICE.next}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function BackLink() {
  return (
    <Link href="/review" className="inline-flex min-h-11 items-center text-sm underline underline-offset-4" data-testid="drill-back">
      {PRACTICE.back}
    </Link>
  );
}
