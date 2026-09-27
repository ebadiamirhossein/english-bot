import Link from "next/link";

import { Reviewer } from "@/components/cards/reviewer";
import { PageHeader } from "@/components/page-header";
import { MY_WORDS } from "@/components/session/copy";

/**
 * The deck. Replaces W2's `ComingLater` placeholder, whose bullets were this
 * slice's brief: a deck seeded from what the bot already taught, four grades
 * with a daily cap, and provenance on every card face.
 *
 * The fourth bullet was a one-click backup out of the app. It shipped at W7 and
 * was removed at W8a: this deck *is* the flashcard system, and a hand-off is a
 * place where habits die.
 */
export default function ReviewPage() {
  return (
    <>
      <PageHeader eyebrow="Review" title="The things you nearly know.">
        Your cards, scheduled so they come back just before you would forget
        them.
      </PageHeader>

      {/* W31c: the saved words, reachable from the deck. A quiet link, no
          count beside it (#160). */}
      <nav className="-mt-2 mb-4 flex flex-wrap gap-4 text-sm" data-testid="review-links">
        <Link
          href="/review/words"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
          data-testid="review-my-words"
        >
          {MY_WORDS.link}
        </Link>
      </nav>

      <Reviewer />
    </>
  );
}
