import { ComingLater } from "@/components/coming-later";
import { PageHeader } from "@/components/page-header";

export default function ProgressPage() {
  return (
    <>
      <PageHeader eyebrow="Progress" title="What has actually changed.">
        Words you know, mistakes you have stopped making, and how far the level
        has moved.
      </PageHeader>

      <ComingLater
        slice="W12"
        title="What will live here"
        items={[
          "The known-word ledger, and how much of real speech it covers.",
          "Errors you have retired, from the journal the bot has kept since day one.",
          "Placement history — where B2 sits from here.",
          "Streaks and freezes, shown without ever counting a day against you.",
        ]}
      />
    </>
  );
}
