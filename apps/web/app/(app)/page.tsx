import Link from "next/link";

import { ApiStatus } from "@/components/api-status";
import { SaturdayLink } from "@/components/checkpoint/saturday-link";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

/**
 * Home. One button, and the button is the product (PRD §4).
 *
 * **W10 turns it on.** It was disabled from W1b, and the shape was here from the
 * start on purpose: every screen added between then and now had to justify
 * itself against a home page that asks for one decision a day.
 *
 * **There is nothing else on this page and there is deliberately no number on
 * it.** No due count, no streak, no "you missed yesterday" — a badge that grows
 * while a learner is away is a backlog presented, which CLAUDE.md §4 forbids
 * (*"Missed days shrink the task; they never pile up"*) and PRD §12 rule 5
 * repeats. The session opens each day; yesterday leaves nothing behind.
 * `tests/test_web_shell.py::test_no_surface_presents_a_backlog_count` holds it.
 *
 * The two links below the button are links, not a second decision: `/practice`
 * and `/write` are places you go on purpose, and neither is ever asked for.
 *
 * **W11 adds a third, on Saturdays only, and it is still not a second
 * decision.** The checkpoint is Saturday's shape (PRD §4.2) and it is a LINK
 * rather than a second button: two full-width buttons on one screen is the menu
 * this page exists to refuse. It renders only when there is a sitting to go to,
 * so six days a week this page is byte-for-byte what W10 shipped.
 */
export default function TodayPage() {
  return (
    <>
      <PageHeader eyebrow="Today" title="Ready when you are.">
        One session a day, twelve minutes at the least, in the English people
        actually speak.
      </PageHeader>

      <section className="space-y-3">
        <Button
          asChild
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-semibold"
        >
          <Link href="/session">Start today&rsquo;s session</Link>
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          Or{" "}
          <Link
            href="/practice"
            className="text-primary underline underline-offset-4"
          >
            practise
          </Link>{" "}
          or{" "}
          <Link
            href="/write"
            className="text-primary underline underline-offset-4"
          >
            write anything
          </Link>
          .
        </p>
        <SaturdayLink />
      </section>

      <ApiStatus />
    </>
  );
}
