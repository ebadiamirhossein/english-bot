import { ComingLater } from "@/components/coming-later";
import { PageHeader } from "@/components/page-header";

export default function ReviewPage() {
  return (
    <>
      <PageHeader eyebrow="Review" title="The things you nearly know.">
        Your cards, scheduled so they come back just before you would forget
        them.
      </PageHeader>

      <ComingLater
        slice="W7"
        title="What will live here"
        items={[
          "An FSRS deck seeded from every phrase the bot has already taught you.",
          "Four grades per card, and a daily cap so it never becomes a chore.",
          "Each card shows where the phrase came from and who says it to whom.",
          "Anki export stays — the deck you already have is not orphaned.",
        ]}
      />
    </>
  );
}
