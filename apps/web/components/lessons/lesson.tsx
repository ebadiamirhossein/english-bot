"use client";

import { useState } from "react";

import { Diagram } from "@/components/lessons/diagram";
import type { Lesson, LessonSection } from "@/lib/api";

/**
 * A grammar lesson. One section per grammar target, each behind its own label.
 *
 * **The four labels a learner already sees are ANNOTATED, not replaced.** Each
 * `<li>` in block 3 becomes the header of its own section, and the label text is
 * untouched — it still arrives through `core.sessions.blocks.visible_target`, so
 * #171's guarantee that no Murphy citation reaches a surface is unchanged.
 *
 * **The first section is open and the rest are closed.** Opening the section the
 * block's items are actually on is not possible: `grammar_target` sits in
 * `projection.NEVER_VISIBLE` precisely so the blind gates cannot read it, and
 * putting it on the wire to drive a UI default would undo that. Filed against
 * #169's family rather than absorbed.
 *
 * **No red anywhere, and it is structural.** The diagram spec has no colour
 * field, so the model cannot ask for one. The mistake is visually subordinate to
 * its correction — smaller, muted, and second — never the headline.
 *
 * **`Mistake`/`said`, not `Wrong`/`wrong`.** `test_web_shell.py`'s no-guilt scan
 * reads raw `.tsx` source, so the identifier tripped it ten times even though the
 * only string rendered is `"Not: "`. That scan's crudeness is what makes it hard
 * to evade, so this file was renamed rather than the guard given an exemption.
 */

function Mistake({
  said,
  corrected,
  why,
}: {
  said: string;
  corrected: string;
  why: string;
}) {
  return (
    <div className="rounded-xl bg-muted/40 p-3" data-testid="lesson-mistake">
      {/* The CORRECTION is the headline. The mistake is the small print under
          it — a learner should leave with the right sentence in their head, and
          nothing here marks the other one with a cross or a colour. */}
      <p className="text-sm font-medium leading-relaxed" data-testid="lesson-corrected">
        {corrected}
      </p>
      <p
        className="mt-1 text-xs leading-relaxed text-muted-foreground"
        data-testid="lesson-mistake-said"
      >
        Not: {said}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{why}</p>
    </div>
  );
}

export function Section({
  section,
  diagram,
  open,
  onToggle,
}: {
  section: LessonSection;
  diagram?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <li className="overflow-hidden rounded-xl bg-muted">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left text-sm leading-relaxed"
        data-testid="lesson-section-toggle"
      >
        <span>{section.target}</span>
        <span className="text-muted-foreground" aria-hidden>
          {open ? "–" : "+"}
        </span>
      </button>
      {open ? (
        <div className="space-y-3 px-4 pb-4" data-testid="lesson-section-body">
          <p className="text-sm leading-relaxed">{section.explanation}</p>
          <dl className="space-y-2 text-sm leading-relaxed">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Use it
              </dt>
              <dd>{section.when_to_use}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Not for
              </dt>
              <dd>{section.when_not_to}</dd>
            </div>
          </dl>
          <ul className="space-y-1" data-testid="lesson-examples">
            {section.examples.map((example) => (
              <li key={example} className="text-sm leading-relaxed">
                {example}
              </li>
            ))}
          </ul>
          {diagram}
          <Mistake
            said={section.mistake.said}
            corrected={section.mistake.corrected}
            why={section.mistake.why}
          />
        </div>
      ) : null}
    </li>
  );
}

export function LessonBody({
  lesson,
  section,
  teachingComplete = false,
}: {
  lesson: Lesson;
  /**
   * Which section to open, 0-based. `null` opens none.
   *
   * **Operator ruling, 2026-08-29 (#245): a section advances per COMPLETED
   * SESSION, not per calendar day** — so a learner who skips a day loses
   * nothing and sees the next section when they next open a session. The index
   * is computed server-side from the session log
   * (`core.services.syllabus.unit_section_index`); this component only renders
   * what it is given.
   *
   * `undefined` means "no pacing information" — the `/lessons/{unit}` operator
   * route, and the pre-W11 shape — and opens the first section, unchanged.
   */
  section?: number | null;
  /**
   * The learner has been through every section of this unit's teaching.
   *
   * **Distinct from "this unit has no lesson", which is a different screen
   * entirely.** When the sections run out before Saturday, block 3 shows
   * PRACTICE ONLY: no new teaching and no repeated section. The labels stay
   * reachable; nothing is opened.
   */
  teachingComplete?: boolean;
}) {
  // Deterministic and cheap. Pre-W11 this read `useState(0)` unconditionally
  // and every learner saw section 1 on every day of the unit — which is what
  // #245 was filed about.
  const initial =
    teachingComplete ? -1 : section === undefined || section === null ? 0 : section;
  const [open, setOpen] = useState(initial);
  const diagramFor = new Map(lesson.diagrams.map((d) => [d.target, d]));

  return (
    <ul className="space-y-2" data-testid="lesson">
      {lesson.sections.map((section, i) => {
        const spec = diagramFor.get(section.target);
        return (
          <Section
            key={section.target}
            section={section}
            open={open === i}
            onToggle={() => setOpen(open === i ? -1 : i)}
            // A section with no diagram renders without a hole. "Fewer rather
            // than false": a target that suits none of the five kinds gets none.
            diagram={spec ? <Diagram spec={spec} /> : undefined}
          />
        );
      })}
    </ul>
  );
}
