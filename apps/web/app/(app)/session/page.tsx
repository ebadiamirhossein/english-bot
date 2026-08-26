import { PageHeader } from "@/components/page-header";
import { SessionRunner } from "@/components/session/runner";

/**
 * The daily session. PRD §4.1's five blocks, behind home's one button.
 *
 * **It is thin on day one and that is correct.** The deck is 33 cards, nothing
 * generates items yet, and no lesson exists — so blocks 2 and 3 carry no
 * exercises and say so. A session that looked full on day one would be inventing
 * work, which is the one thing this product is not allowed to do.
 */
export default function SessionPage() {
  return (
    <>
      <PageHeader eyebrow="Today" title="Here’s today.">
        Five short blocks. Stop whenever you need to — it’ll be where you left
        it.
      </PageHeader>

      <SessionRunner />
    </>
  );
}
