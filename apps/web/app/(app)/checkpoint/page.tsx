import { CheckpointRunner } from "@/components/checkpoint/runner";
import { PageHeader } from "@/components/page-header";
import { CHECKPOINT } from "@/components/checkpoint/copy";

/**
 * Saturday's checkpoint. PRD §3, §4.2.
 *
 * **Saturday only builds the checkpoint.** §4.2's Saturday row holds three
 * things and W11 ships one: the couple challenge lives in the Telegram bot
 * until W22 (PRODUCT-PRINCIPLES §1 forbids designing new work for it), and
 * watch-together is W27.
 */
export default function CheckpointPage() {
  return (
    <>
      <PageHeader eyebrow={CHECKPOINT.eyebrow} title={CHECKPOINT.title}>
        {CHECKPOINT.intro}
      </PageHeader>
      <CheckpointRunner />
    </>
  );
}
