import { WordsPage } from "@/components/words/words-page";

/**
 * **`/review` — kept as a working route: an ALIAS of Words (W32f).**
 *
 * The nav's Review became Words on 2026-09-28 (operator ruling): one page of
 * Review, word practice and My words. **An alias rather than a redirect**:
 * keep going's *a few more cards*, the drill's and My words' way back, and any
 * installed app's cached shell already point here, and a redirect is one more
 * response for the service worker to cache under the wrong URL. It opens on
 * Review, and the nav lights Words for it.
 *
 * *(Until W32f this page was the deck alone — PageHeader "Review / The things
 * you nearly know.", with the two links W31c and W31d added under it; W2's
 * `ComingLater` before that. The deck itself is unchanged: `Reviewer`.)*
 */
export default function ReviewPage() {
  return <WordsPage initial="review" />;
}
