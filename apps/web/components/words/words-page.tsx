import { PageHeader } from "@/components/page-header";
import { WORDS } from "@/components/session/copy";
import { WordsHub, type WordsPart } from "@/components/words/words-hub";

/** The Words page (W32f), shared by `/words` and its alias `/review`. */
export function WordsPage({ initial = "review" }: { initial?: WordsPart }) {
  return (
    <>
      <PageHeader eyebrow={WORDS.eyebrow} title={WORDS.title}>
        {WORDS.intro}
      </PageHeader>
      <WordsHub initial={initial} />
    </>
  );
}

const PARTS = new Set<string>(["review", "practice", "mine"]);

/** `?part=` → a part; anything else opens Review. */
export function partOf(asked: string | undefined): WordsPart {
  return asked && PARTS.has(asked) ? (asked as WordsPart) : "review";
}
