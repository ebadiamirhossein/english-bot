import { MyWords } from "@/components/cards/my-words";
import { MY_WORDS } from "@/components/session/copy";
import { PageHeader } from "@/components/page-header";

/** W31c — My words, reached from Review. No count, no backlog (#160). */
export default function MyWordsPage() {
  return (
    <>
      <PageHeader eyebrow={MY_WORDS.eyebrow} title={MY_WORDS.title}>
        {MY_WORDS.intro}
      </PageHeader>
      <MyWords />
    </>
  );
}
