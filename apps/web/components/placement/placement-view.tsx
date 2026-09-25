"use client";

/**
 * W18 — the placement check. PRD §6.
 *
 * **Four parts, then *where to start*.** Words (yes/no), grammar (adaptive),
 * listening (gap-fill, the clip fetched on tap), speaking (spoken if voice is on
 * for this learner, #364; typed otherwise, and always skippable). The server
 * decides every next step; this screen renders whatever `step` it is handed and
 * sends one answer back. **No grading happens here**: the projection carries no
 * answer, and no verdict is shown after an item — a placement item is a
 * measurement, and a running verdict would turn it into a tally.
 *
 * **No position and no count.** The part's name is the only progress shown.
 *
 * **The grammar and listening items reuse the app's own presentation and answer
 * components** (`components/items/presentation`, `…/answer`), chosen by
 * `projection.item_type` and `response_mode` exactly as `ItemCard` chooses
 * them; only the submit goes elsewhere. The listening clip's URL comes through
 * `AudioSource`, so `AudioButton` fetches `/placement/items/{id}/audio`.
 *
 * Conventions are `/talk` and `/write`'s (ruling 0.3): the mono eyebrow, cards
 * on `bg-card`, the serif for the app's voice.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AudioSource } from "@/components/items/audio-button";
import { answerFor } from "@/components/items/answer";
import { presentationFor } from "@/components/items/presentation";
import { useRecorder } from "@/components/session/use-recorder";
import { PLACEMENT } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  answerPlacement,
  finishPlacement,
  getPlacement,
  placementAudioUrl,
  speakPlacement,
  startPlacement,
  type Placement,
  type PlacementAnswer,
  type PlacementItem,
  type PlacementResult,
  type PlacementStep,
} from "@/lib/api";
import type { Draft } from "@/lib/items";

import { Radar } from "./radar";

type Phase =
  | { kind: "loading" }
  | { kind: "problem" }
  | { kind: "intro"; placement: Placement }
  | { kind: "sitting"; step: PlacementStep }
  | { kind: "finishing" }
  | { kind: "result"; result: PlacementResult };

const EYEBROW =
  "font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground";
const CARD = "rounded-2xl border border-border bg-card p-4";
const VOICE = "font-heading text-[0.9375rem] leading-relaxed";
const BIG = "h-14 w-full rounded-2xl text-base font-semibold";

function longDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

export function PlacementView() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });

  const load = useCallback(() => {
    setPhase({ kind: "loading" });
    getPlacement()
      .then((placement) =>
        setPhase(
          placement.state === "open" && placement.step
            ? { kind: "sitting", step: placement.step }
            : { kind: "intro", placement },
        ),
      )
      .catch(() => setPhase({ kind: "problem" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const finish = useCallback(() => {
    setPhase({ kind: "finishing" });
    finishPlacement()
      .then((result) => setPhase({ kind: "result", result }))
      .catch(() => setPhase({ kind: "problem" }));
  }, []);

  /** Every move forward goes through here. A 409 means the screen and the
   * server disagree about which item is being asked: re-read, never guess. */
  const advance = useCallback(
    (next: Promise<PlacementStep>) =>
      next
        .then((step) => {
          if (step.section === "done") finish();
          else setPhase({ kind: "sitting", step });
        })
        .catch((error) => {
          if (error instanceof ApiError && error.status === 409) load();
          else setPhase({ kind: "problem" });
        }),
    [finish, load],
  );

  // A sitting reopened after its last answer lands on `done`: finish it.
  useEffect(() => {
    if (phase.kind === "sitting" && phase.step.section === "done") finish();
  }, [phase, finish]);

  return (
    <div className="space-y-4" data-testid="placement-screen" data-phase={phase.kind}>
      {phase.kind === "problem" ? (
        <div className="space-y-3" data-testid="placement-problem">
          <p className="text-base leading-relaxed">{PLACEMENT.trouble}</p>
          <Button type="button" className="min-h-11" onClick={load}>
            {PLACEMENT.retry}
          </Button>
        </div>
      ) : null}
      {phase.kind === "intro" ? (
        <Intro placement={phase.placement} onStart={() => advance(startPlacement())} />
      ) : null}
      {phase.kind === "sitting" && phase.step.item ? (
        <Sitting step={phase.step} item={phase.step.item} advance={advance} />
      ) : null}
      {phase.kind === "finishing" ? (
        <p className={`${VOICE} text-muted-foreground`} role="status" data-testid="placement-finishing">
          {PLACEMENT.finishing}
        </p>
      ) : null}
      {phase.kind === "result" ? <Result result={phase.result} /> : null}
    </div>
  );
}

function Intro({ placement, onStart }: { placement: Placement; onStart: () => void }) {
  return (
    <section className="space-y-4" data-testid="placement-intro">
      {placement.shown ? <Level shown={placement.shown} next={null} /> : null}
      {placement.available ? (
        <Button type="button" size="lg" className={BIG} onClick={onStart} data-testid="placement-start">
          {PLACEMENT.start}
        </Button>
      ) : !placement.ready ? (
        <p className={`${VOICE} text-muted-foreground`} data-testid="placement-not-ready">
          {PLACEMENT.notReady}
        </p>
      ) : placement.next_from ? (
        <p className={`${VOICE} text-muted-foreground`} data-testid="placement-next">
          {PLACEMENT.nextFrom(longDate(placement.next_from))}
        </p>
      ) : null}
    </section>
  );
}

function Sitting({
  step,
  item,
  advance,
}: {
  step: PlacementStep;
  item: PlacementItem;
  advance: (next: Promise<PlacementStep>) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  useEffect(() => setBusy(false), [item.id]);

  const send = useCallback(
    (answer: PlacementAnswer) => {
      setBusy(true);
      void advance(answerPlacement(item.id, answer)).finally(() => setBusy(false));
    },
    [advance, item.id],
  );

  const section = step.section as keyof typeof PLACEMENT.parts;
  return (
    <section className="space-y-5" data-testid="placement-sitting" data-section={step.section}>
      <h2 className={EYEBROW} data-testid="placement-part">
        {PLACEMENT.parts[section]}
      </h2>
      {step.section === "vocabulary" ? <Word item={item} busy={busy} send={send} /> : null}
      {step.section === "grammar" || step.section === "listening" ? (
        <AudioSource.Provider value={placementAudioUrl}>
          <Question item={item} busy={busy} send={send} about={PLACEMENT[step.section].about} />
        </AudioSource.Provider>
      ) : null}
      {step.section === "speaking" ? (
        <Speaking item={item} busy={busy} send={send} advance={advance} setBusy={setBusy} />
      ) : null}
    </section>
  );
}

function Word({ item, busy, send }: { item: PlacementItem; busy: boolean; send: (a: PlacementAnswer) => void }) {
  return (
    <div className="space-y-5">
      <p className={`${VOICE} text-muted-foreground`}>{PLACEMENT.vocabulary.about}</p>
      <div className={`${CARD} text-center`}>
        <p className={EYEBROW}>{PLACEMENT.vocabulary.ask}</p>
        <p className="mt-4 mb-2 break-words font-heading text-[2.25rem] leading-tight" data-testid="placement-word">
          {item.word}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Button type="button" size="lg" className={BIG} disabled={busy} onClick={() => send({ known: true })} data-testid="placement-yes">
          {PLACEMENT.vocabulary.yes}
        </Button>
        <Button type="button" size="lg" variant="outline" className={BIG} disabled={busy} onClick={() => send({ known: false })} data-testid="placement-no">
          {PLACEMENT.vocabulary.no}
        </Button>
      </div>
    </div>
  );
}

function Question({
  item,
  busy,
  send,
  about,
}: {
  item: PlacementItem;
  busy: boolean;
  send: (a: PlacementAnswer) => void;
  about: string;
}) {
  const [draft, setDraft] = useState<Draft>({});
  useEffect(() => setDraft({}), [item.id]);
  const projection = useMemo(() => item.projection ?? {}, [item.projection]);
  const Presentation = useMemo(
    () => presentationFor(projection["item_type"]),
    [projection],
  );
  const Answer = answerFor(item.response_mode ?? "");
  if (!Presentation || !Answer) return null;
  return (
    <div className="space-y-5" data-testid="placement-question">
      <p className={`${VOICE} text-muted-foreground`}>{about}</p>
      <Presentation
        itemId={item.id}
        projection={projection}
        draft={draft}
        onDraft={setDraft}
        disabled={busy}
        result={null}
      />
      <Answer
        draft={draft}
        onDraft={setDraft}
        onSubmit={(submitted) => {
          // `self_marked` is the spoken items' own mark; no placement item is
          // spoken, and the placement answer has no field for it.
          const answer: PlacementAnswer = { ...submitted };
          delete (answer as Draft).self_marked;
          send(answer);
        }}
        submitting={busy}
        answered={false}
      />
    </div>
  );
}

function Speaking({
  item,
  busy,
  send,
  advance,
  setBusy,
}: {
  item: PlacementItem;
  busy: boolean;
  send: (a: PlacementAnswer) => void;
  advance: (next: Promise<PlacementStep>) => Promise<void>;
  setBusy: (b: boolean) => void;
}) {
  const [typing, setTyping] = useState(!item.voice);
  const [text, setText] = useState("");
  const [unheard, setUnheard] = useState(false);
  const recorder = useRecorder((blob) => {
    setBusy(true);
    setUnheard(false);
    speakPlacement(item.id, blob)
      .then((step) => advance(Promise.resolve(step)))
      .catch((error) => {
        setBusy(false);
        if (error instanceof ApiError && error.status === 422) setUnheard(true);
        else void advance(Promise.reject(error));
      });
  });

  return (
    <div className="space-y-4" data-testid="placement-speaking">
      <p className={`${VOICE} text-muted-foreground`}>
        {typing ? PLACEMENT.speaking.typedAbout : PLACEMENT.speaking.about}
      </p>
      <p className={`${CARD} font-heading text-lg leading-snug`} data-testid="placement-prompt">
        {item.prompt_text}
      </p>
      {unheard ? (
        <p role="status" className="text-sm text-muted-foreground" data-testid="placement-unheard">
          {PLACEMENT.speaking.unheard}
        </p>
      ) : null}
      {typing ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim() && !busy) send({ text });
          }}
        >
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={5}
            maxLength={4000}
            aria-label={PLACEMENT.speaking.placeholder}
            placeholder={PLACEMENT.speaking.placeholder}
            data-testid="placement-typed"
            className="w-full rounded-2xl border border-border bg-card px-4 py-3 text-base outline-none placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <Button type="submit" size="lg" className={BIG} disabled={!text.trim() || busy} data-testid="placement-send">
            {PLACEMENT.speaking.send}
          </Button>
        </form>
      ) : (
        <div className="space-y-3">
          {recorder.recording ? (
            <Button type="button" size="lg" className={BIG} onClick={recorder.stop} data-testid="placement-stop">
              {PLACEMENT.speaking.stop}
            </Button>
          ) : (
            <Button
              type="button"
              size="lg"
              className={BIG}
              disabled={busy}
              onClick={() => void recorder.start()}
              data-testid="placement-record"
            >
              {busy ? PLACEMENT.speaking.listening : PLACEMENT.speaking.record}
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="lg"
            className={BIG}
            disabled={recorder.recording || busy}
            onClick={() => setTyping(true)}
            data-testid="placement-type-instead"
          >
            {PLACEMENT.speaking.typeInstead}
          </Button>
        </div>
      )}
      <Button
        type="button"
        variant="ghost"
        className="min-h-11 w-full"
        disabled={busy || recorder.recording}
        onClick={() => send({ skip: true })}
        data-testid="placement-skip"
      >
        {PLACEMENT.speaking.skip}
      </Button>
    </div>
  );
}

/** The band shown: the letters, the name under them, a raise if there was one. */
function Level({ shown, next }: { shown: NonNullable<Placement["shown"]>; next: string | null }) {
  return (
    <section className={CARD} data-testid="placement-level" aria-labelledby="placement-level-h">
      <h2 id="placement-level-h" className={EYEBROW}>
        {PLACEMENT.result.eyebrow}
      </h2>
      <p className="mt-3 font-heading text-[2.75rem] leading-none" data-testid="placement-band">
        {shown.where_to_start}
      </p>
      <p className="mt-1 font-heading text-lg">{PLACEMENT.bandName[shown.where_to_start]}</p>
      {shown.raised_from ? (
        <p className="mt-2 text-sm font-medium text-primary" data-testid="placement-raised">
          {PLACEMENT.result.raised(shown.raised_from)}
        </p>
      ) : null}
      <Radar radar={shown.radar} />
      {shown.vocab_estimate ? (
        <p className="mt-3 max-w-prose text-sm leading-relaxed text-muted-foreground" data-testid="placement-vocab">
          {PLACEMENT.result.vocab(shown.vocab_estimate)}
        </p>
      ) : null}
      {next ? (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {PLACEMENT.nextFrom(longDate(next))}
        </p>
      ) : null}
    </section>
  );
}

function Result({ result }: { result: PlacementResult }) {
  return (
    <section className="space-y-4" data-testid="placement-result">
      <Level shown={result.shown} next={result.next_from} />
      <Button asChild size="lg" variant="outline" className={BIG}>
        <Link href="/progress" data-testid="placement-back">
          {PLACEMENT.result.back}
        </Link>
      </Button>
    </section>
  );
}
