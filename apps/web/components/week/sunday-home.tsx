"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { KeepGoing } from "@/components/keep-going/keep-going";
import { PageHeader } from "@/components/page-header";
import { WeekReport } from "@/components/week/report";
import { getWeek } from "@/lib/api";
import type { Week } from "@/lib/api";

/**
 * Home, on Sunday. PRD §4.2: *"No tasks. Weekly report. Free extensive input,
 * tracked but never required."* — and *"Sunday being empty is deliberate and
 * non-negotiable"*.
 *
 * **So a Sunday that acquires a task is a defect**, and this component is what
 * stops home from being one. Six days a week it renders its children — the page
 * W10 shipped, byte for byte. On the seventh it renders the report instead, and
 * **the session call-to-action is not on the screen at all.**
 *
 * **THE DAY IS DECIDED BY THE SERVER.** `GET /week` knows the learner's local
 * date through `users.timezone`; a `new Date().getDay()` here would put a
 * learner in Vilnius on the browser's idea of Sunday. That is the reasoning
 * `components/checkpoint/saturday-link.tsx` already records, reused rather than
 * re-argued.
 *
 * **WHILE IT DOES NOT YET KNOW, IT RENDERS NEITHER.** Showing the button and
 * then taking it away is worse than a moment of nothing — the app would be
 * asking for a session and then withdrawing the ask. The app shell already
 * waits on `getAuthHealth` behind `RequireSession`'s splash, so this is one
 * more short wait on a screen that was never instant.
 *
 * **IF `GET /week` CANNOT BE REACHED, THE WEEKDAY SHAPE WINS.** A learner on a
 * Tuesday with a flaky connection must still be able to start their session;
 * the cost is that an unreachable API on a Sunday shows a button it should not.
 * That trade is deliberate and is the smaller harm of the two.
 *
 * **Block 1 is NOT suppressed on Sunday and nothing here touches the session.**
 * Forcing the review block empty would skip a day of the FSRS schedule for
 * every card and shift every interval — a scheduler change made by a calendar
 * rule. #160 already keeps `/review` reachable without a count, and that shape
 * is reused.
 */

type State =
  | { kind: "unknown" }
  | { kind: "sunday"; week: Week }
  | { kind: "weekday" };

export function SundayHome({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "unknown" });

  useEffect(() => {
    let live = true;
    getWeek()
      .then((week) => {
        if (!live) return;
        setState(week.sunday ? { kind: "sunday", week } : { kind: "weekday" });
      })
      .catch(() => {
        // Home must open with or without the report. See the docstring: the
        // weekday shape is the safe default because it is the one a learner can
        // act on, and there is nothing they could do about the failure.
        if (live) setState({ kind: "weekday" });
      });
    return () => {
      live = false;
    };
  }, []);

  if (state.kind === "unknown") return null;
  if (state.kind === "weekday") return <>{children}</>;

  return (
    <>
      <PageHeader eyebrow="Sunday" title="Your week.">
        Nothing is asked of you today.
      </PageHeader>

      <section className="space-y-6" data-testid="sunday-report">
        <WeekReport week={state.week} />

        {/*
          The session stays reachable and is never the primary. PRD §4.2's
          "free extensive input, tracked but never required" — a link, not a
          button, and phrased so the learner is choosing rather than complying.
        */}
        <p className="text-sm text-muted-foreground">
          Or{" "}
          <Link
            href="/session"
            className="text-primary underline underline-offset-4"
            data-testid="sunday-session-link"
          >
            practise anyway
          </Link>
          .
        </p>

        {/* W24e (R1, R3): Sunday's keep going is watch-only — the day's own
            video first. Low emphasis, below the report and the link; nothing
            here is asked of anyone. */}
        <KeepGoing sunday />
      </section>
    </>
  );
}
