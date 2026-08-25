import { Reviewer } from "@/components/cards/reviewer";
import { PageHeader } from "@/components/page-header";

/**
 * The deck. Replaces W2's `ComingLater` placeholder, whose four bullets were
 * this slice's brief: a deck seeded from what the bot already taught, four
 * grades with a daily cap, provenance on every card face, and the Anki export
 * kept so the existing deck is not orphaned.
 */
export default function ReviewPage() {
  return (
    <>
      <PageHeader eyebrow="Review" title="The things you nearly know.">
        Your cards, scheduled so they come back just before you would forget
        them.
      </PageHeader>

      <Reviewer />
    </>
  );
}
