import { PageHeader } from "@/components/page-header";
import { WATCH } from "@/components/session/copy";
import { WatchRunner } from "@/components/watch/watch-runner";

/**
 * **Two doors to one player, never a library (R2, PRD §7.4).**
 *
 * - **`/watch` — the bottom nav's Watch (W32f, operator ruling 2026-09-28):**
 *   today's assigned video, any day, Sunday's included (R3). A read: it never
 *   assigns anything, and with nothing assigned it says so calmly.
 * - **`/watch?extra=1` — keep going's *watch something* (W24e):** today's open
 *   video or one extra chosen by the same selection score block 2 uses.
 *
 * There is no list, no search and no second choice on this page.
 */
export default async function WatchPage({
  searchParams,
}: {
  searchParams: Promise<{ extra?: string }>;
}) {
  const extra = (await searchParams).extra === "1";
  return (
    <>
      {extra ? (
        <PageHeader eyebrow={WATCH.eyebrow} title={WATCH.title}>
          {WATCH.body}
        </PageHeader>
      ) : (
        <PageHeader eyebrow={WATCH.todayEyebrow} title={WATCH.todayTitle}>
          {WATCH.todayBody}
        </PageHeader>
      )}

      <WatchRunner extra={extra} />
    </>
  );
}
