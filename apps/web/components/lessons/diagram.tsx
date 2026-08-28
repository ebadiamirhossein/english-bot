"use client";

import type { LessonDiagram } from "@/lib/api";

/**
 * The five diagram kinds, as SVG and plain layout. **We own every pixel.**
 *
 * The model emits a typed spec through `core.llm` and this file renders it
 * (ruled 2026-08-26; the image-model option was raised once and declined). The
 * spec has **no colour field, no font field and no coordinate field** — that is
 * asserted in `tests/test_lessons_schema.py`, and it is what makes "no red in
 * the lesson UI" structural rather than a promise. The model cannot choose a
 * colour because it has nowhere to put one.
 *
 * `first`/`second` on a contrast pair are NOT `left`/`right`: on a phone they
 * stack. The schema names them semantically for exactly that reason.
 *
 * **Nothing here checks that the picture READS.** No check in this slice does.
 * That is the operator's eyes, and unlike the English it is a judgement he can
 * actually make — which is the whole reason diagrams earn their cost.
 */

function Frame({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <figure
      className="rounded-xl border border-border bg-muted/40 p-4"
      data-testid="lesson-diagram"
    >
      <div className="overflow-x-auto">{children}</div>
      <figcaption className="sr-only">{label}</figcaption>
    </figure>
  );
}

function Timeline({ points }: { points: { label: string; at: number; now: boolean }[] }) {
  const ordered = [...points].sort((a, b) => a.at - b.at);
  return (
    <ol className="flex min-w-max items-stretch gap-3" data-testid="diagram-timeline">
      {ordered.map((point, i) => (
        <li key={`${point.at}-${point.label}`} className="flex items-center gap-3">
          <div className="flex flex-col items-center gap-2">
            <span
              className={
                point.now
                  ? "h-3 w-3 rounded-full bg-foreground"
                  : "h-3 w-3 rounded-full border-2 border-muted-foreground"
              }
              aria-hidden
            />
            <span className="max-w-36 text-center text-xs leading-snug">
              {point.label}
            </span>
            {point.now ? (
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                now
              </span>
            ) : null}
          </div>
          {i < ordered.length - 1 ? (
            <span className="h-px w-8 self-start bg-border" style={{ marginTop: 6 }} aria-hidden />
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function ContrastPair({
  situation,
  first,
  second,
  whatChanges,
}: {
  situation: string;
  first: { form: string; example: string };
  second: { form: string; example: string };
  whatChanges: string;
}) {
  return (
    <div className="space-y-3" data-testid="diagram-contrast-pair">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {situation}
      </p>
      {/* Stacks on a phone, side by side when there is room. The spec does not
          decide this and cannot. */}
      <div className="grid gap-3 sm:grid-cols-2">
        {[first, second].map((side, i) => (
          <div key={i} className="rounded-lg bg-background p-3">
            <p className="text-sm font-medium">{side.form}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {side.example}
            </p>
          </div>
        ))}
      </div>
      <p className="text-sm leading-relaxed">{whatChanges}</p>
    </div>
  );
}

function FormBuild({ slots, example }: { slots: string[]; example: string }) {
  return (
    <div className="space-y-3" data-testid="diagram-form-build">
      <div className="flex min-w-max flex-wrap items-center gap-2">
        {slots.map((slot, i) => (
          <span key={`${i}-${slot}`} className="flex items-center gap-2">
            <span className="rounded-lg bg-background px-3 py-2 text-sm">
              {slot}
            </span>
            {i < slots.length - 1 ? (
              <span className="text-muted-foreground" aria-hidden>
                +
              </span>
            ) : null}
          </span>
        ))}
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{example}</p>
    </div>
  );
}

function DecisionTree({
  question,
  branches,
}: {
  question: string;
  branches: { answer: string; form: string }[];
}) {
  return (
    <div className="space-y-3" data-testid="diagram-decision-tree">
      <p className="text-sm font-medium">{question}</p>
      <ul className="space-y-2">
        {branches.map((branch) => (
          <li key={branch.answer} className="flex items-baseline gap-2 text-sm">
            <span className="rounded-md bg-background px-2 py-1 text-xs">
              {branch.answer}
            </span>
            <span className="text-muted-foreground" aria-hidden>
              →
            </span>
            <span className="leading-relaxed">{branch.form}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AnnotatedExample({
  sentence,
  callouts,
}: {
  sentence: string;
  callouts: { part: string; note: string }[];
}) {
  return (
    <div className="space-y-3" data-testid="diagram-annotated-example">
      <p className="text-base leading-relaxed">{sentence}</p>
      <ul className="space-y-2">
        {callouts.map((callout) => (
          <li key={callout.part} className="text-sm leading-relaxed">
            <span className="font-medium">{callout.part}</span>
            <span className="text-muted-foreground"> — {callout.note}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Diagram({ spec }: { spec: LessonDiagram }) {
  switch (spec.kind) {
    case "timeline":
      return (
        <Frame label={`Timeline for ${spec.target}`}>
          <Timeline points={spec.points} />
        </Frame>
      );
    case "contrast_pair":
      return (
        <Frame label={`Two forms for ${spec.target}`}>
          <ContrastPair
            situation={spec.situation}
            first={spec.first}
            second={spec.second}
            whatChanges={spec.what_changes}
          />
        </Frame>
      );
    case "form_build":
      return (
        <Frame label={`How to build ${spec.target}`}>
          <FormBuild slots={spec.slots} example={spec.example} />
        </Frame>
      );
    case "decision_tree":
      return (
        <Frame label={`Choosing for ${spec.target}`}>
          <DecisionTree question={spec.question} branches={spec.branches} />
        </Frame>
      );
    case "annotated_example":
      return (
        <Frame label={`An example of ${spec.target}`}>
          <AnnotatedExample sentence={spec.sentence} callouts={spec.callouts} />
        </Frame>
      );
    default:
      // A kind this renderer does not know is not rendered. Never a placeholder
      // and never an error a learner can see.
      return null;
  }
}
