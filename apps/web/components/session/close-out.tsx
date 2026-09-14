"use client";

/**
 * The close-out. **W13b/4 — the design import.**
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **THIS SURFACE DID NOT EXIST AS A SURFACE.** Until this slice it was a branch
 * inside `conversation.tsx` — `if (done)`, four elements, no ordering argument
 * and no test of any kind. The design gives it a shape; the record decides what
 * may fill it.
 *
 * **IT IS A VIEW, NOT A ROUTE, AND THAT IS FORCED RATHER THAN PREFERRED.**
 * `POST /conversation/close` is a one-shot mutation: it deletes the turns and
 * writes `conversations.summary` in one transaction and answers 404 on a second
 * call, so the payload exists exactly once, in that response. Carrying it
 * across a navigation would need browser storage — refused by
 * `test_no_browser_storage_except_the_theme` and CLAUDE.md §5 — or a query
 * string, which would put corrections and the words a learner did not know into
 * a URL. **The design agrees independently:** its own state machine is
 * `step: 'topics' | 'thread' | 'closeout' | 'limit'` inside one screen, and
 * ending is a `setState`, not a navigation.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **PAYOFF FIRST — the design's ordering, and it is ordering that carries the
 * meaning.** Topic, then what went well, then at most two things worth a look,
 * then the words. **Nothing leads with a fix.** `close-out.test.tsx` asserts
 * the ORDER and not merely the presence of each part, because a close-out that
 * opened with the corrections would pass a presence test intact.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **THREE THINGS THE DESIGN DRAWS THAT HAVE NO DATA. REPORTED, NOT
 * APPROXIMATED** (CLAUDE.md §3 rule 7, and the standing rule that an
 * acceptance bar is never quietly lowered):
 *
 * 1. **The summary paragraph** — *"You talked about a colleague's wedding…"*.
 *    `conversations.summary` is written at close and **deliberately kept off
 *    the wire**: `CloseOut`'s docstring rules that putting it there *"would
 *    invite a client to render the app's assessment of the learner back at
 *    them, which is a report card by another name"*. **Operator ruling
 *    2026-09-07: DEFERRED PENDING EVIDENCE, not declined** — all three stored
 *    summaries on production are empty because no conversation has ever been
 *    closed, so nobody has read one. The close-out opens on `did_well` instead.
 *    Read with **#391**, whose option (a) stays open.
 * 2. **The grammar-category chip** — the design's amber card is titled *PAST
 *    TENSE*. `CorrectionOut` carries `you_said`, `correct_form` and
 *    `explanation` and **no category field**. The card keeps the triangle and
 *    the section heading; it invents no label.
 * 3. **A definition under each word, and an *In your deck* state before any
 *    tap.** `unknown_words` is `list[str]`. `save_conversation_word`'s own
 *    docstring settles the first: *"A conversation word has no gloss row and no
 *    video"*, and generating one *"would breach the half of the 2026-08-27
 *    ruling §0's amendment explicitly left standing"*. The second is simply not
 *    on the wire. **So a word row is a word and an offer, and the second line
 *    is absent rather than empty.**
 *
 * **AND ONE THING THE DESIGN OMITS THAT IS KEPT:** `explanation`. It is real
 * data, it has shipped since W13b/2, and dropping it to match a mock would lose
 * something a learner reads for a reason the mock does not know about.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **SERIF IS THE APP, SANS IS THE LEARNER — three signals, none of them
 * colour.** The design proposes Source Serif 4 against Public Sans; **this uses
 * `font-heading` (Fraunces) against the body sans, which the app already
 * loads**, so the distinction costs no new font. `data-speaker` carries it for
 * the tests regardless, because a test that asserts a typeface asserts Tailwind
 * the same way one asserting a colour does.
 *
 * **THE CARD IS AMBER AND THE TRANSCRIPT'S MARKED WORDS STAY TEAL.** Operator
 * ruling 2026-09-07 against the design, on #373: the design paints both amber,
 * which would make one colour mean *new word* and *worth a look* at once. A
 * card carrying a triangle and the words *Worth a look*, on a surface with no
 * per-word marking anywhere, cannot be read as a highlight.
 */

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { CONVERSATION } from "./copy";

export type Correction = {
  you_said: string;
  correct_form: string;
  explanation: string;
};

/** The triangle from the design's icon set. **Not a cross and never red** —
 * CLAUDE.md §4, and `test_no_red_anywhere_in_the_frontend` holds the palette
 * side of it. */
/** The *worth a look* triangle. Exported for `/write`'s correction cards (W16a)
 * so the glyph has one home. */
export function Look() {
  return (
    <svg width="11" height="10" viewBox="0 0 11 10" aria-hidden="true">
      <path d="M5.5 0 11 10H0z" fill="currentColor" />
    </svg>
  );
}

export function CloseOut({
  topic,
  summary,
  didWell,
  corrections,
  words,
  kept,
  capped,
  busy,
  onKeep,
}: {
  topic: string | null;
  summary: string;
  didWell: string;
  corrections: Correction[];
  words: string[];
  kept: Record<string, boolean>;
  capped: boolean;
  busy: boolean;
  onKeep: (word: string) => void;
}) {
  // **WHITESPACE IS ABSENCE, AND THE RULE LIVES HERE AND NOWHERE ELSE.**
  // `did_well` is `str` and not `str | None` on the wire, so an empty note
  // arrives as `""` — and a model that returns `" "` is returning nothing.
  // The first draft trimmed at the fetch boundary in `conversation.tsx` AND
  // tested truthiness here, which is two homes for one rule and the reason the
  // whitespace case failed: the component was handed `"   "` directly and
  // rendered an empty paragraph. The caller now passes the field through raw.
  const well = didWell.trim();
  const hasCorrections = corrections.length > 0;
  const hasWords = words.length > 0;
  // **The empty close-out says so, rather than rendering three empty
  // headings.** A surface with a heading and nothing under it reads as a thing
  // that failed to load (`BLOCK_UNAVAILABLE`'s whole distinction).
  const bare = !well && !summary.trim() && !hasCorrections && !hasWords;

  return (
    <div
      className="flex h-full min-h-0 flex-col gap-5 overflow-y-auto px-5 py-6"
      data-testid="conversation-closed"
    >
      <div>
        <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
          {CONVERSATION.closeEyebrow}
        </p>
        {topic ? (
          <h2
            className="mt-2 font-heading text-2xl leading-tight"
            data-testid="close-topic"
          >
            {topic}
          </h2>
        ) : null}
        <p className="mt-2 text-base">
          {capped ? CONVERSATION.capReached : CONVERSATION.closing}
        </p>
      </div>

      {/* **THE RECAP. ON THE WIRE SINCE 2026-09-08, AND IT IS THE DESIGN'S
          OPENING LINE** — `1i` leads the close-out with what was talked about,
          before anything that could read as a fix.

          **`CloseOut` REFUSED TO CARRY THIS FIELD UNTIL THE FIRST ONE WAS
          READ.** The refusal called it *"the app's assessment of the learner
          rendered back at them"*; the first real summary was a recap of a
          wedding in Trakai, and the operator overturned it on that evidence.
          **The rule it was protecting has not gone away — it moved to the
          prompt**, where `conversation_close_v3.txt` forbids a score and
          forbids quoting the learner, asserted by a test. **Absent, never
          blank**, like every other field on this surface. */}
      {summary.trim() ? (
        <p className="text-base leading-relaxed" data-testid="close-summary-text">
          {summary.trim()}
        </p>
      ) : null}

      {/* The raise, announced. Serif and brand-coloured: the app's own voice,
          and the only sentence on this screen that is about the learner going
          up. **Absent, never blank** — an empty note renders nothing at all. */}
      {well ? (
        <p
          className="font-heading text-lg leading-relaxed text-brand"
          data-speaker="app"
          data-testid="conversation-did-well"
        >
          {well}
        </p>
      ) : null}

      {bare ? <p className="text-base">{CONVERSATION.closeNothing}</p> : null}

      {hasCorrections ? (
        <section>
          <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
            {CONVERSATION.correctionsHeading}
          </p>
          <div className="mt-3 flex flex-col gap-3">
            {corrections.map((c, i) => (
              <div
                key={i}
                className="rounded-2xl border border-caution-border bg-caution p-4"
                data-testid="conversation-correction"
              >
                <span className="text-caution-foreground" aria-hidden="true">
                  <Look />
                </span>
                {/* What the learner said, and what the app would say. The pair
                    is the whole card, so the two voices are marked here the
                    same way they are in the chat log. */}
                <p
                  className="mt-2 text-[0.95rem] leading-normal text-muted-foreground underline decoration-dotted underline-offset-4"
                  data-speaker="you"
                  data-testid="correction-said"
                >
                  {c.you_said}
                </p>
                <p
                  className="mt-1.5 font-heading text-base leading-normal"
                  data-speaker="app"
                  data-testid="correction-better"
                >
                  {c.correct_form}
                </p>
                {c.explanation ? (
                  <p className="mt-2 text-sm leading-normal text-muted-foreground">
                    {c.explanation}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {hasWords ? (
        <section data-testid="conversation-words">
          <p className="font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
            {CONVERSATION.wordsHeading}
          </p>
          <div className="mt-1 flex flex-col">
            {words.map((w) => (
              <div
                key={w}
                className="flex items-center justify-between gap-3 border-b border-border py-3 last:border-b-0"
                data-testid="conversation-word"
              >
                {/* **The word, and nothing under it.** The design draws a gloss
                    here; a conversation word has none and cannot be given one
                    without generating study material behind a gate that is
                    still standing. Absent, not an empty line. */}
                <p className="font-heading text-base font-semibold leading-tight">
                  {w}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  disabled={busy || Boolean(kept[w])}
                  onClick={() => onKeep(w)}
                >
                  {kept[w] ? CONVERSATION.saved : CONVERSATION.save}
                </Button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Link
        href="/"
        className="mt-1 flex w-full items-center justify-center rounded-xl bg-primary px-4 py-4 text-base font-medium text-primary-foreground"
        data-testid="close-back"
      >
        {CONVERSATION.backToToday}
      </Link>
    </div>
  );
}
