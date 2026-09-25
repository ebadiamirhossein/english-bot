import { PageHeader } from "@/components/page-header";
import { ProgressView } from "@/components/progress/progress-view";
import { PROGRESS } from "@/components/session/copy";

/**
 * W19 — the Progress tab (it has been the fourth tab since W2; the placeholder
 * it replaces named W12). A normal scrolling page: `main`'s `space-y-7` spaces
 * the header and the view, and nothing here needs a full-height column.
 */
export default function ProgressPage() {
  return (
    <>
      <PageHeader eyebrow={PROGRESS.eyebrow} title={PROGRESS.title}>
        {PROGRESS.subline}
      </PageHeader>
      <ProgressView />
    </>
  );
}
