import { PageHeader } from "@/components/page-header";
import { WATCH } from "@/components/session/copy";
import { WatchRunner } from "@/components/watch/watch-runner";

/**
 * W24e — keep going's *watch something*. **Assigned, never browsed (R2):** the
 * page asks the server for today's open video or one extra chosen by the same
 * selection score block 2 uses, and plays it in block 2's own player. There is
 * no list, no search and no second choice on this page.
 */
export default function WatchPage() {
  return (
    <>
      <PageHeader eyebrow={WATCH.eyebrow} title={WATCH.title}>
        {WATCH.body}
      </PageHeader>

      <WatchRunner />
    </>
  );
}
