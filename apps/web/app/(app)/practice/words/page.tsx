import { Drill } from "@/components/practice/drill";
import { PRACTICE } from "@/components/session/copy";
import { PageHeader } from "@/components/page-header";

/**
 * W31d — word practice (W24f, un-deferred). No score, no count (#160).
 *
 * **At `/practice/words`, not `/practice`**: `/practice` is W6's free item
 * practice and stays as it is — a first draft of this page overwrote it, and it
 * was restored from git before anything was committed.
 */
export default function WordPracticePage() {
  return (
    <>
      <PageHeader eyebrow={PRACTICE.eyebrow} title={PRACTICE.title}>
        {PRACTICE.intro}
      </PageHeader>
      <Drill />
    </>
  );
}
