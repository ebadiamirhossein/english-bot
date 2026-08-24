import Link from "next/link";

import { ApiStatus } from "@/components/api-status";
import { ComingLater } from "@/components/coming-later";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

/**
 * Home. One button, and the button is the product (PRD §4).
 *
 * It is disabled at W1b because W10 builds the session runner. The shape is
 * here from the start on purpose: every screen added between now and then has
 * to justify itself against a home page that asks for one decision a day.
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
          size="lg"
          disabled
          className="h-14 w-full rounded-2xl text-base font-semibold"
        >
          Start today&rsquo;s session
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          The session runner arrives in W10.{" "}
          <Link
            href="/write"
            className="text-primary underline underline-offset-4"
          >
            Write anything
          </Link>{" "}
          in the meantime.
        </p>
      </section>

      <ComingLater
        slice="W10"
        title="What this button will open"
        items={[
          "Five blocks: warm-up, focus, input, production, review.",
          "Built overnight, so it opens in under a second.",
          "Resumable — lock your phone mid-session and pick it up later.",
          "Missed a day? Tomorrow is smaller, not doubled.",
        ]}
      />

      <ApiStatus />
    </>
  );
}
