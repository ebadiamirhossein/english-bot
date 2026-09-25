import { PageHeader } from "@/components/page-header";
import { PlacementView } from "@/components/placement/placement-view";
import { PLACEMENT } from "@/components/session/copy";

/**
 * W18 — *Where to start*: the placement check. Reached from the Progress tab's
 * level card, not from the bottom nav (four places, `test_web_shell`). A normal
 * scrolling page, like Progress: nothing here needs a full-height column.
 */
export default function PlacementPage() {
  return (
    <>
      <PageHeader eyebrow={PLACEMENT.eyebrow} title={PLACEMENT.title}>
        {PLACEMENT.subline}
      </PageHeader>
      <PlacementView />
    </>
  );
}
