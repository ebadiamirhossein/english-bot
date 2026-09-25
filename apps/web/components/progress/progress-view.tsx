"use client";

/**
 * W19 — the progress screen. PRD §9, *gamification — the honest kind*.
 *
 * **NO NUMERIC ZERO REACHES THE SCREEN** (W11b's rule, `week/report.tsx`): a
 * section whose number is zero is not drawn, and a learner with nothing yet
 * reads one line. A zero on a progress screen is a score of nothing.
 *
 * **Every number carries one line saying what it counts**, so none of them
 * reads as a verdict. **Nothing counts what was not done** — the wire has no
 * field for it (`lib/api.ts`'s `Progress`).
 *
 * **The line is drawn from the count's own history, from its second point
 * on.** With one point there is nothing to connect and the screen says so in a
 * sentence; nothing is interpolated or reconstructed (run ruling, W19).
 *
 * Conventions are `/talk` and `/write`'s (ruling 0.3): the mono eyebrow, cards
 * on `bg-card`, the serif for the app's own words and numbers.
 */

import { useCallback, useEffect, useState } from "react";

import { PROGRESS } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { getProgress, type KnownPoint, type Progress } from "@/lib/api";

type Phase =
  | { kind: "loading" }
  | { kind: "problem" }
  | { kind: "ready"; progress: Progress };

const EYEBROW =
  "font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground";
const CARD = "rounded-2xl border border-border bg-card p-4";
const NUMBER = "font-heading text-[2.25rem] leading-none";

function formatted(n: number): string {
  return n.toLocaleString("en-GB");
}

export function ProgressView() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });

  const load = useCallback(() => {
    setPhase({ kind: "loading" });
    getProgress()
      .then((progress) => setPhase({ kind: "ready", progress }))
      .catch(() => setPhase({ kind: "problem" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4" data-testid="progress-screen" data-phase={phase.kind}>
      {phase.kind === "problem" ? (
        <div className="space-y-3" data-testid="progress-problem">
          <p className="text-base leading-relaxed">{PROGRESS.trouble}</p>
          <Button type="button" className="min-h-11" onClick={load}>
            {PROGRESS.retry}
          </Button>
        </div>
      ) : null}
      {phase.kind === "ready" ? <Sections progress={phase.progress} /> : null}
    </div>
  );
}

function Sections({ progress }: { progress: Progress }) {
  const { known_words, known_history, xp, streak_days, freezes, units_passed } = progress;
  const empty = !known_words && !xp && !streak_days && !units_passed;

  return (
    <>
      {empty ? (
        <p className="max-w-prose text-base leading-relaxed" data-testid="progress-empty">
          {PROGRESS.empty}
        </p>
      ) : null}

      {known_words > 0 ? (
        <section className={CARD} data-testid="progress-words" aria-labelledby="progress-words-h">
          <h2 id="progress-words-h" className={EYEBROW}>
            {PROGRESS.words.eyebrow}
          </h2>
          <p className={`${NUMBER} mt-3`} data-testid="progress-words-number">
            {formatted(known_words)}
          </p>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted-foreground">
            {PROGRESS.words.about}
          </p>
          {known_history.length >= 2 ? (
            <KnownLine points={known_history} />
          ) : (
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground" data-testid="progress-words-first">
              {PROGRESS.words.firstPoint}
            </p>
          )}
        </section>
      ) : null}

      {xp > 0 ? (
        <section className={CARD} data-testid="progress-xp" aria-labelledby="progress-xp-h">
          <h2 id="progress-xp-h" className={EYEBROW}>
            {PROGRESS.xp.eyebrow}
          </h2>
          <p className={`${NUMBER} mt-3`}>{formatted(xp)}</p>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted-foreground">
            {PROGRESS.xp.about}
          </p>
        </section>
      ) : null}

      {streak_days > 0 ? (
        <section className={CARD} data-testid="progress-streak" aria-labelledby="progress-streak-h">
          <h2 id="progress-streak-h" className={EYEBROW}>
            {PROGRESS.streak.eyebrow}
          </h2>
          <p className="mt-3 flex items-baseline gap-2">
            <span className={NUMBER}>{formatted(streak_days)}</span>
            <span className="font-heading text-lg">{PROGRESS.streak.days(streak_days)}</span>
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {PROGRESS.streak.about}
          </p>
          {freezes > 0 ? (
            <p className="mt-3 flex items-center gap-2 text-sm" data-testid="progress-freezes">
              <span className="flex gap-1" aria-hidden="true">
                {Array.from({ length: freezes }, (_, i) => (
                  <span key={i} className="h-2 w-2 rounded-full bg-primary" />
                ))}
              </span>
              {PROGRESS.streak.freezes(freezes)}
            </p>
          ) : null}
        </section>
      ) : null}

      {units_passed > 0 ? (
        <section className={CARD} data-testid="progress-units" aria-labelledby="progress-units-h">
          <h2 id="progress-units-h" className={EYEBROW}>
            {PROGRESS.units.eyebrow}
          </h2>
          <p className="mt-3 flex items-baseline gap-2">
            <span className={NUMBER}>{formatted(units_passed)}</span>
            <span className="font-heading text-lg">{PROGRESS.units.passed(units_passed)}</span>
          </p>
        </section>
      ) : null}

      <p className="max-w-prose text-sm leading-relaxed text-muted-foreground" data-testid="progress-later">
        {PROGRESS.later}
      </p>
    </>
  );
}

const W = 300;
const H = 88;
const PAD = 6;

/**
 * The count's own history as a line. Dates are placed by time, not by index,
 * so a gap of two weeks between visits looks like two weeks. The vertical axis
 * starts at zero: a line that started at its own minimum would turn a rise of
 * three words into a cliff.
 */
function KnownLine({ points }: { points: KnownPoint[] }) {
  const times = points.map((p) => Date.parse(`${p.local_date}T12:00:00Z`));
  const t0 = times[0];
  const span = Math.max(times[times.length - 1] - t0, 1);
  const top = Math.max(...points.map((p) => p.known_words), 1);
  const xy = points.map((p, i) => ({
    x: PAD + ((times[i] - t0) / span) * (W - 2 * PAD),
    y: H - PAD - (p.known_words / top) * (H - 2 * PAD),
  }));
  const first = points[0].local_date;
  const last = points[points.length - 1].local_date;

  return (
    <figure className="mt-4" data-testid="progress-words-line">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-24 w-full text-primary"
        role="img"
        aria-label={PROGRESS.words.chartLabel}
        preserveAspectRatio="none"
      >
        <line x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} className="stroke-border" strokeWidth={1} />
        <polyline
          points={xy.map((p) => `${p.x},${p.y}`).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <figcaption className="mt-1 flex justify-between font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
        <span>{shortDate(first)}</span>
        <span>{shortDate(last)}</span>
      </figcaption>
    </figure>
  );
}

function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}
