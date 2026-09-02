"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { WeekReport } from "@/components/week/report";
import { getWeek } from "@/lib/api";
import type { Week } from "@/lib/api";

/**
 * The report, at a permanent address. W11b.
 *
 * **Home is where a learner meets it** — on Sunday, as the primary — and this
 * page is the same report where it can be looked at on purpose, on any day.
 * Both mount the one `WeekReport`; there is no second renderer and no second
 * place the numbers are assembled.
 *
 * **It is deliberately NOT in the bottom nav.** The nav has four places and a
 * fifth tab is a fifth thing to keep up with; a report you can visit is not the
 * same object as a tab that waits for you.
 */
export default function WeekPage() {
  const [week, setWeek] = useState<Week | null>(null);

  useEffect(() => {
    let live = true;
    getWeek()
      .then((got) => live && setWeek(got))
      // Silent, as on home: a report that failed to load is one missing screen,
      // not a broken app, and there is nothing a learner could do about it.
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  return (
    <>
      <PageHeader eyebrow="Your week" title="What happened.">
        Sunday&rsquo;s report, for the week that runs Monday to Sunday.
      </PageHeader>

      {week ? <WeekReport week={week} /> : null}
    </>
  );
}
