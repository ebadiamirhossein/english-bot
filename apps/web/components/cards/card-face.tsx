"use client";

import { cn } from "@/lib/utils";
import type { CardFace as CardFaceData } from "@/lib/api";

/**
 * One card, front then back. PRD §5 and §8.5.4.
 *
 * **The provenance is not decoration, and it is not unconditional either.**
 * PRD §5: "every card carries the sentence it came from and where it came
 * from." W8c found what that sentence costs when it is printed on the wrong
 * card type. On production, card 38's front read:
 *
 *     extra expenses that are not obvious at first
 *     "I wish someone had warned me to ask about _____ upfront," she said.
 *       ""I wish someone had warned me to ask about hidden costs
 *       upfront," she said." — reading_1
 *
 * The gloss asks for the phrase, the gap marks where it goes, and the line
 * underneath supplies it. `migrate_chunks.py:211` sets `context_sentence` to
 * the **ungapped** sentence — the same string with the answer still in it — and
 * this component used to render it before the reveal for every card type.
 *
 * **A gate that examines one field cannot see a leak from another.** Neither
 * code review nor `probe_cloze` caught this: the probe measured whether the gap
 * was answerable and never asked what else was on the card. A person looked at
 * a phone for ten seconds. #116 is the same shape — the answer arriving before
 * it is asked for.
 *
 * "Carries" is not "prints before the question is answered". See
 * `SOURCE_LINE_ON_FRONT`.
 *
 * **The four §8.5.4 fields need no missing-value branch.** Migration 013's
 * `cards_informal_shows_the_four_things` CHECK refuses to store an
 * `informal`/`slang` card without the source line, the meaning, the neutral
 * equivalent and who-says-this — so if the register says slang, all four are
 * there. The component renders them rather than defending against their
 * absence, which is the point of putting the rule in the schema.
 */

/**
 * Whether the source line belongs on the FRONT, per PRD §5's five card types.
 *
 * **Exhaustive on purpose, and not a default with exceptions.** Every type gets
 * a line and a reason, so a sixth type cannot inherit a decision nobody made
 * for it. An unrecognised `card_type` falls through to withheld — the safe
 * direction — which means a new type has to be ruled on here before its
 * provenance can reach a front.
 *
 * - `recognition` — **stays.** PRD §5's front is "word in its mined sentence".
 *   The sentence *is* the question; withholding it would delete the card. This
 *   is the type the rule was written for, and it is why the rule was right.
 * - `production` — **withheld.** Front is "L1 gloss + context hint"; the
 *   ungapped sentence contains the back. This is the defect W8c exists to fix.
 * - `cloze` — **withheld.** Front is the sentence *gapped*; the source line is
 *   the same sentence *ungapped*. The same leak, one step more obvious. No
 *   cloze card exists today — W8b deleted all fourteen — and W13 creates them
 *   from video lines, so the ruling is written now rather than rediscovered
 *   then.
 * - `audio` — **withheld.** PRD §5's back is the transcript. Printing the
 *   sentence turns a listening card into a reading one.
 * - `collocation` — **withheld.** Back is the correct verb and the source
 *   sentence contains it.
 */
const SOURCE_LINE_ON_FRONT: Record<string, boolean> = {
  recognition: true,
  production: false,
  cloze: false,
  audio: false,
  collocation: false,
};

/**
 * Which L1s need a declared font family and a right-to-left run.
 *
 * **W10 keys this on the learner's language, not on the characters** (#159).
 * The component used to tag a line from the SCRIPT alone: right for Farsi by
 * accident, and **silently wrong for Morkyte** — Lithuanian is Latin script, so
 * her gloss was labelled English, with no tofu, no direction symptom, nothing
 * on screen and nothing in a log. A screen reader and a hyphenation engine were
 * simply told the wrong language.
 *
 * There was never a missing column. `users.native_language TEXT NOT NULL` has
 * existed since `001_init_postgres.sql:19` and reads `fa` / `lt` / `fa` for the
 * three production rows; the value just never reached the card. #143's open half
 * asked for exactly this field, from the rendering side.
 */
const RTL_SCRIPT_LANGUAGES = new Set(["fa", "ar", "he", "ur", "ps"]);

/**
 * The Arabic script block, and **it is deliberately the same range as the
 * production query** — `SELECT ... WHERE front ~ '[؀-ۿ]'`, which returns 9. The
 * rows that query counts are exactly the lines this component styles, so the
 * number in the record and the behaviour on the phone cannot describe different
 * sets.
 *
 * **It survives W10, narrowed to one job, and the reason it is not simply
 * replaced by the L1 field is that a single field is genuinely bilingual:**
 * `migrate_chunks.py:245` builds a production front as `meaning + "\n" + gapped`,
 * which on card 17 is a Farsi gloss above an English sentence. The field says
 * *which language the learner's half is in*; the script still says *which lines
 * are that half*. For a Latin-script L1 the question is not asked at all.
 */
const ARABIC_SCRIPT = /[؀-ۿ]/;

/**
 * One learner-facing field, laid out **one bidi run per line**.
 *
 * A card field is genuinely multi-line and its lines can be in different
 * scripts: `migrate_chunks.py:245` builds a production front as
 * `meaning + "\n" + gapped`, which on card 17 is a Farsi gloss above an English
 * sentence.
 *
 * **Per line, and not per field, because the paragraph-level fix creates a
 * second bug.** `dir="auto"` on the whole `<p>` takes its direction from the
 * first strong character; on card 17 that is Farsi, so the English hint
 * underneath would be laid out right-to-left with its punctuation on the wrong
 * end. The font has the same shape: font fallback resolves per glyph, so a
 * Vazirmatn-first stack over the paragraph would set the English sentence in
 * Vazirmatn's Latin.
 *
 * `font-l1` leads with Vazirmatn (see `globals.css`). Declaring a companion
 * *after* a `next/font` Latin family is inert — `next/font` inserts its own
 * metric-adjusted local fallback immediately after each family and that
 * fallback has Arabic coverage, so the browser never reaches the companion
 * (#142, measured rather than read).
 *
 * Follows `components/items/presentation/l1-to-l2-production.tsx:22`
 * (`<div dir="auto" lang={language}>`) rather than inventing a second pattern.
 */
function BidiText({
  text,
  language,
  className,
}: {
  text: string;
  /** The learner's L1, from `users.native_language` (#159). */
  language: string;
  className?: string;
}) {
  const lines = text.split("\n");
  // Asked once per field, not once per line: a learner has one first language.
  const l1NeedsItsOwnFace = RTL_SCRIPT_LANGUAGES.has(language);
  return (
    <>
      {lines.map((line, index) => {
        // For a Latin-script L1 this is always false and every line is `en`,
        // which is correct rather than a fallback: Lithuanian and English share
        // a script and a direction, so there is nothing to declare and nothing
        // to override. That is the conditional #159 asks for — the field drives
        // the font, instead of the component applying `font-l1` to whatever it
        // decides is L1.
        const l1 = l1NeedsItsOwnFace && ARABIC_SCRIPT.test(line);
        return (
          <span
            // A field's lines have no identity beyond their position, and the
            // field is re-rendered whole when the card changes.
            key={index}
            dir="auto"
            lang={l1 ? language : "en"}
            className={cn(lines.length > 1 && "block", l1 && "font-l1", className)}
          >
            {line}
          </span>
        );
      })}
    </>
  );
}

export function CardFace({
  card,
  revealed,
  l1Language = "en",
}: {
  card: CardFaceData;
  revealed: boolean;
  /**
   * The learner's first language, from the queue or session envelope (#159).
   *
   * Defaulted to `en` so a caller not yet threaded renders English-only rather
   * than throwing — and `en` is the value that makes this component do nothing
   * special, which is the harmless direction to fail in.
   */
  l1Language?: string;
}) {
  const isReceptiveRegister =
    card.register === "slang" || card.register === "informal";

  const sourceLineOnFront = SOURCE_LINE_ON_FRONT[card.card_type] === true;
  const showSourceLine = sourceLineOnFront || revealed;

  // A slang chunk becomes a recognition card whose front IS its mined sentence:
  // `migrate_chunks._slang_plan` sets `front = sentence` and
  // `context_sentence = sentence`. Rendering both prints the same string twice,
  // which it did on all fifteen live slang cards. When they match, only the
  // provenance is left to say.
  const sentenceIsAlreadyTheFront =
    card.context_sentence !== null &&
    card.context_sentence.trim() === card.front.trim();

  const sourceSentence = sentenceIsAlreadyTheFront ? null : card.context_sentence;
  const hasSourceLine =
    showSourceLine && (sourceSentence !== null || card.source_ref !== null);

  return (
    <article
      className="rounded-2xl border border-border bg-card p-5 space-y-4"
      data-testid="card-face"
      data-card-id={card.id}
      data-card-type={card.card_type}
      data-register={card.register}
      data-revealed={String(revealed)}
    >
      <p className="font-heading text-2xl leading-snug">
        <BidiText language={l1Language} text={card.front} />
      </p>

      {/* The cue appears only on a card the leech rule has rewritten. It is a
          first letter and a length, never an apology for the card being hard —
          "raises announced, drops silent" (CLAUDE.md §4) means the learner is
          given the help and not told why they are getting it. */}
      {card.cue && !revealed ? (
        <p
          className="font-mono text-base tracking-widest text-muted-foreground"
          data-testid="card-cue"
        >
          <BidiText language={l1Language} text={card.cue} />
        </p>
      ) : null}

      {revealed ? (
        <div className="space-y-3 border-t border-border pt-4" data-testid="card-back">
          <p className="font-heading text-2xl leading-snug text-primary">
            <BidiText language={l1Language} text={card.back} />
          </p>
          {card.meaning ? (
            <p className="text-sm leading-relaxed text-muted-foreground">
              <BidiText language={l1Language} text={card.meaning} />
            </p>
          ) : null}
        </div>
      ) : null}

      {hasSourceLine ? (
        <p
          className="text-sm leading-relaxed text-muted-foreground italic"
          data-testid="card-context"
        >
          {sourceSentence ? (
            <>
              &ldquo;
              <BidiText language={l1Language} text={sourceSentence} />
              &rdquo;
            </>
          ) : null}
          {card.source_ref ? (
            // `dir="ltr"`, not `dir="auto"`: a source_ref is a provenance slug
            // ('reading_1', 'himym_s2e4'), not learner text, and an RTL
            // sentence beside it must not drag it into its run.
            <span className="not-italic" dir="ltr">
              {sourceSentence ? " " : ""}— {card.source_ref}
            </span>
          ) : null}
        </p>
      ) : null}

      {isReceptiveRegister && revealed ? (
        // §8.5.4's whole reason for existing: a bare "hard pass = refusal" card
        // is "useless and slightly dangerous". The safe alternative and the
        // situation are the content, not a footnote, so they get their own
        // block rather than a line of small print.
        //
        // **Behind the reveal since W8c**, and that is the same finding as the
        // source line. §8.5.4 constrains what the CARD shows, not what the
        // FRONT shows: on a recognition card the answer is the back *and the
        // meaning*, and `neutral_equivalent` paraphrases the meaning — "Safe
        // anywhere: I'd rather not, thanks" on the front of a card whose answer
        // is "a firm refusal" is the answer in different words. `meaning`, one
        // of the same four things, was already behind the reveal; the panel
        // joins the field it duplicates.
        <div
          className="rounded-xl bg-muted p-4 space-y-2 text-sm leading-relaxed"
          data-testid="card-register-panel"
        >
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {card.register}
          </p>
          {card.neutral_equivalent ? (
            <p data-testid="card-neutral">
              Safe anywhere:{" "}
              <span className="font-medium">
                <BidiText language={l1Language} text={card.neutral_equivalent} />
              </span>
            </p>
          ) : null}
          {card.who_says_this ? (
            <p className="text-muted-foreground" data-testid="card-who-says">
              <BidiText language={l1Language} text={card.who_says_this} />
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
