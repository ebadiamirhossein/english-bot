import { cn } from "@/lib/utils";

/**
 * **W32f (B3) — the learner's-language line, and Farsi in Vazirmatn.**
 *
 * The operator, 2026-09-28: the Farsi on `/watch` rendered in the phone's
 * fallback face and read poorly. **Vazirmatn was already declared** (W8a, #142:
 * `app/layout.tsx` loads it through `next/font/google`, and `--font-l1` in
 * `globals.css` puts it FIRST, which is the whole of that fix) — but only the
 * card face used it. The popover and the word sheet gave their Farsi line
 * `lang` and `dir` and no face, so it fell to Geist, which has no Arabic, and
 * from there to whatever the phone had.
 *
 * **The rule, one place:** an element that renders a Farsi string carries
 * `lang="fa"`, `dir="rtl"` and `font-l1`. Any other language keeps its own
 * `lang`, left-to-right, in the page's face — Lithuanian and English fonts are
 * unchanged. Keyed on the LANGUAGE (#159), never guessed from the characters —
 * except in `scriptLanguage` below, which says why.
 */

/** Right-to-left scripts among the learners' languages. */
export const RTL_L1 = new Set(["fa"]);

/** The languages that need their own face — the Arabic-script one. */
const OWN_FACE = new Set(["fa"]);

export function l1Attributes(language: string) {
  return {
    lang: language,
    dir: RTL_L1.has(language) ? ("rtl" as const) : ("ltr" as const),
    face: OWN_FACE.has(language) ? "font-l1" : undefined,
  };
}

/** One line in the learner's language, as a `<p>`. */
export function L1Text({
  text,
  language,
  className,
  testId,
}: {
  text: string;
  language: string;
  className?: string;
  testId?: string;
}) {
  const { lang, dir, face } = l1Attributes(language);
  return (
    <p data-testid={testId} lang={lang} dir={dir} className={cn(face, className)}>
      {text}
    </p>
  );
}

const ARABIC_SCRIPT = /[\u0600-\u06FF]/;

/**
 * **For a payload that carries no language: word practice.** `/practice/start`
 * sends a card's meaning with no `l1_language` beside it, and a card imported
 * from Trancy fronts a Farsi gloss (#142). **In this product an Arabic-script
 * line can only be Farsi** — the learners' languages are English, Farsi and
 * Lithuanian — so the script decides here, and only here. Threading the
 * learner's language through the drill's payload is filed (#488); until then
 * this is the stated exception to #159's rule.
 */
export function scriptLanguage(text: string): "fa" | "en" {
  return ARABIC_SCRIPT.test(text) ? "fa" : "en";
}
