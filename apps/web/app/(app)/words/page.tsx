import { WordsPage, partOf } from "@/components/words/words-page";

/**
 * **W32f (B4) — Words**, in the nav where Review was: Review, word practice
 * and My words on one page (operator ruling, 2026-09-28). `?part=practice` or
 * `?part=mine` opens on that part. `/review` is kept as a working route — an
 * ALIAS that renders this same page (`app/(app)/review/page.tsx`), not a
 * redirect.
 */
export default async function Words({
  searchParams,
}: {
  searchParams: Promise<{ part?: string }>;
}) {
  return <WordsPage initial={partOf((await searchParams).part)} />;
}
