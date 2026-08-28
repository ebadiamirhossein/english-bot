"use client";

import { use, useEffect, useState } from "react";

import { LessonBody } from "@/components/lessons/lesson";
import { PageHeader } from "@/components/page-header";
import { getLesson, type Lesson } from "@/lib/api";

/**
 * One unit's lesson, rendered on its own page.
 *
 * **Why this exists.** Under #188 `current_unit` returns 1 for every learner and
 * cannot advance, so a lesson for unit 9 or 20 is unreachable inside the daily
 * session. This page is how those lessons are read at all — and reading them as
 * raw JSON would not do, because what the operator's reading establishes
 * includes **whether the diagram reads on a phone**, which is a property of the
 * render and not of the spec. Accepting two of three lessons as JSON would have
 * claimed three read lessons while two were read in a form that cannot support
 * the claim.
 *
 * **#160: reachable, never owed.** No bottom-nav entry, no badge, no count, and
 * nothing links here yet — the map is still W9's placeholder. When W9 builds it,
 * it links here rather than inventing a second surface.
 */
export default function LessonPage({
  params,
}: {
  params: Promise<{ unit: string }>;
}) {
  const { unit } = use(params);
  const unitNumber = Number(unit);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing">("loading");

  useEffect(() => {
    let live = true;
    getLesson(unitNumber)
      .then((found) => {
        if (!live) return;
        setLesson(found);
        setState("ready");
      })
      .catch(() => {
        if (live) setState("missing");
      });
    return () => {
      live = false;
    };
  }, [unitNumber]);

  return (
    <>
      <PageHeader eyebrow={`Unit ${unitNumber}`} title="This week’s grammar.">
        One section for each thing this unit teaches.
      </PageHeader>

      {state === "loading" ? (
        <p className="text-sm leading-relaxed text-muted-foreground">Loading…</p>
      ) : null}

      {state === "missing" ? (
        // A unit nobody has generated for has no lesson, and that is the
        // correct behaviour rather than a bug: generation is human-run (#196).
        // No apology, no counter, nothing about what is missing elsewhere.
        <p
          className="text-sm leading-relaxed text-muted-foreground"
          data-testid="lesson-missing"
        >
          The written explanation for this unit is on its way.
        </p>
      ) : null}

      {state === "ready" && lesson ? <LessonBody lesson={lesson} /> : null}
    </>
  );
}
