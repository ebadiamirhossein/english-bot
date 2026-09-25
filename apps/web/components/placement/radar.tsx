"use client";

/**
 * W18 — the per-skill radar, **in bands, never numbers.** PRD §6 asks for *"a
 * per-skill radar (listening / reading / grammar / production /
 * pronunciation)"*. The instrument measures four skills and they are drawn under
 * their own names; **reading and pronunciation are not drawn** — the bank has no
 * reading section and pronunciation needed the retired Azure assessment
 * (reported unmet in the record, not approximated here).
 *
 * Four rings, A2 innermost and C1 outermost. A skill never measured has **no
 * point at all** — a point at the centre would draw a measurement of nothing,
 * and the label says *not measured* instead. The shape is drawn only when three
 * or more skills have a point.
 *
 * The rings carry no numbers. Each axis is labelled with its skill, and the
 * bands are written out underneath as text, so the picture is readable without
 * the picture — and a long *not measured* never has to fit beside an axis.
 */

import type { Band, PlacementShown } from "@/lib/api";
import { PLACEMENT } from "@/components/session/copy";

const RINGS: Band[] = ["A2", "B1", "B2", "C1"];
const W = 360;
const H = 250;
const CX = W / 2;
const CY = H / 2;
const R = 88;

/** Up, right, down, left — the order the wire sends the skills in. */
const ANGLES = [-90, 0, 90, 180].map((d) => (d * Math.PI) / 180);

function radius(band: Band): number {
  return (R * (RINGS.indexOf(band) + 1)) / RINGS.length;
}

export function Radar({ radar }: { radar: PlacementShown["radar"] }) {
  const points = radar.map((axis, i) =>
    axis.band === null
      ? null
      : {
          x: CX + radius(axis.band) * Math.cos(ANGLES[i]),
          y: CY + radius(axis.band) * Math.sin(ANGLES[i]),
        },
  );
  const drawn = points.filter((p): p is { x: number; y: number } => p !== null);
  const label = radar
    .map((axis) => `${PLACEMENT.skills[axis.skill]}: ${axis.band ?? PLACEMENT.unmeasured}`)
    .join(", ");

  return (
    <figure className="mt-3" data-testid="placement-radar">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full max-w-[22rem] text-primary"
        role="img"
        aria-label={`${PLACEMENT.result.radar}. ${label}`}
      >
        {RINGS.map((band) => (
          <circle
            key={band}
            cx={CX}
            cy={CY}
            r={radius(band)}
            fill="none"
            className="stroke-border"
            strokeWidth={1}
          />
        ))}
        {ANGLES.map((a, i) => (
          <line
            key={i}
            x1={CX}
            y1={CY}
            x2={CX + R * Math.cos(a)}
            y2={CY + R * Math.sin(a)}
            className="stroke-border"
            strokeWidth={1}
          />
        ))}
        {drawn.length >= 3 ? (
          <polygon
            points={drawn.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="currentColor"
            fillOpacity={0.18}
            stroke="currentColor"
            strokeWidth={2}
            strokeLinejoin="round"
          />
        ) : null}
        {drawn.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={4} fill="currentColor" />
        ))}
        {radar.map((axis, i) => {
          const a = ANGLES[i];
          const x = CX + (R + 16) * Math.cos(a);
          const y = CY + (R + 16) * Math.sin(a);
          const anchor = Math.abs(Math.cos(a)) < 0.01 ? "middle" : Math.cos(a) > 0 ? "start" : "end";
          const dy = Math.sin(a) < -0.5 ? -6 : Math.sin(a) > 0.5 ? 14 : 4;
          return (
            <text
              key={axis.skill}
              x={x}
              y={y + dy}
              textAnchor={anchor}
              className="fill-foreground font-mono text-[11px] uppercase tracking-[0.08em]"
            >
              {PLACEMENT.skills[axis.skill]}
            </text>
          );
        })}
      </svg>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {radar.map((axis) => (
          <div key={axis.skill} className="flex items-baseline justify-between gap-2" data-testid={`placement-radar-${axis.skill}`}>
            <dt className="text-muted-foreground">{PLACEMENT.skills[axis.skill]}</dt>
            <dd className={axis.band ? "font-heading text-base" : "text-muted-foreground"}>
              {axis.band ?? PLACEMENT.unmeasured}
            </dd>
          </div>
        ))}
      </dl>
    </figure>
  );
}
