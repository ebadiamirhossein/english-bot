"use client";

import { useEffect, useState } from "react";

import { CardImage } from "@/components/cards/card-image";
import { L1Text } from "@/components/l1-text";
import { VIDEO } from "@/components/session/copy";
import { resolve, type Resolved } from "@/components/video/meanings";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  lookupWord,
  saveWord,
  type MeaningsMap,
  type SaveWordResult,
  type WordLookup,
} from "@/lib/api";

/**
 * What a Save came to. The server's states, plus **the four ways a request can
 * come back refused**, each with its own sentence (W31a, #465). W31c splits
 * `pending` by whether a meaning is actually coming.
 */
export type TapOutcome =
  | Exclude<SaveWordResult["state"], "pending">
  | "pending_soon"
  | "pending_held"
  | "not_assigned"
  | "rate_limited"
  | "offline"
  | "server";

export function refusal(error: unknown): TapOutcome {
  if (!(error instanceof ApiError)) return "server";
  if (error.status === undefined) return "offline";
  if (error.status === 404) return "not_assigned";
  if (error.status === 429) return "rate_limited";
  return "server";
}

export const TAP_COPY: Record<TapOutcome, string> = {
  saved: VIDEO.saveWord.saved,
  already_saved: VIDEO.saveWord.already,
  no_gloss: VIDEO.saveWord.notReady,
  pending_soon: VIDEO.saveWord.pendingSoon,
  pending_held: VIDEO.saveWord.pendingHeld,
  no_line: VIDEO.saveWord.noLine,
  not_assigned: VIDEO.saveWord.notAssigned,
  rate_limited: VIDEO.saveWord.rateLimited,
  offline: VIDEO.saveWord.offline,
  server: VIDEO.saveWord.server,
};

function outcomeOf(result: SaveWordResult): TapOutcome {
  if (result.state === "pending") return result.meaning_soon ? "pending_soon" : "pending_held";
  return result.state;
}

/** Refusals the learner can simply try again: Save stays under the line. */
const RETRYABLE = new Set<TapOutcome>(["offline", "server", "rate_limited"]);

export type SheetTarget = { word: string; line: number | null };

function RegisterChip({ register }: { register: string | null }) {
  if (!register || register === "neutral" || register === "formal") return null;
  return (
    <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
      {register}
    </span>
  );
}

function L1({ text, language }: { text: string | null | undefined; language: string | null | undefined }) {
  if (!text || !language) return null;
  // W32f (B3): lang, dir and — for Farsi — Vazirmatn (`components/l1-text.tsx`).
  return <L1Text testId="word-sheet-l1" text={text} language={language} className="text-base" />;
}

/**
 * The word sheet. **W31c.** The operator's reference is Trancy / Language
 * Reactor: tap any word, see what it is, keep it.
 *
 * **W32b — FROM THE MAP, WITH NO REQUEST.** When the page's meanings map has
 * loaded, the sheet renders straight from it: the video's own meaning first,
 * labelled *here*; the dictionary's senses under it, each with the learner's
 * language; a name said plainly; and Save. **`lookupWord` is now only the
 * fallback** for a map that could not load — today's W31c path, unchanged.
 *
 * **IT READS AND SAVES; IT NEVER GENERATES.** *Nothing* still offers Save,
 * because a learner must be able to keep a word nobody has explained yet (the
 * operator's finding, 2026-09-27). **No definition is invented here and
 * nothing counts.** A bottom sheet on a phone, a panel near the bottom on a
 * desktop; above Focus mode, so a word tapped in Focus opens here too.
 */
export function WordSheet({
  videoId,
  target,
  onClose,
  map = null,
  lineText = null,
  onKept,
  onMiss,
  lookingUp = false,
}: {
  videoId: number;
  target: SheetTarget | null;
  onClose: () => void;
  /** W32b: the page's meanings; `null` while loading or when it could not load. */
  map?: MeaningsMap | null;
  /** W32b: the tapped line's text, which the page already shows. */
  lineText?: string | null;
  /** W32b: a Save landed — the page's map learns the word is kept. */
  onKept?: (word: string, state: "in_deck" | "pending") => void;
  /** W32c: the sheet opened on a word the map has no entry for. The page
   * looks it up once; the answer arrives through `map`. */
  onMiss?: (word: string, line: number | null) => void;
  /** W32c: that lookup is in flight. */
  lookingUp?: boolean;
}) {
  const [found, setFound] = useState<WordLookup | "loading" | "unavailable">("loading");
  const [outcome, setOutcome] = useState<TapOutcome | null>(null);
  const [saving, setSaving] = useState(false);
  const fromMap = map !== null;

  useEffect(() => {
    setOutcome(null);
  }, [target]);

  useEffect(() => {
    // **The fallback only.** With the map, the sheet already has everything.
    if (!target || fromMap) return;
    let live = true;
    setFound("loading");
    lookupWord(videoId, target.word, target.line)
      .then((result) => live && setFound(result))
      .catch(() => live && setFound("unavailable"));
    return () => {
      live = false;
    };
  }, [videoId, target, fromMap]);

  // **W32c: a miss is looked up as the sheet opens** — never on a hover, and
  // once per word per page (the page keeps the list). A word already known to
  // have no meaning (`no_meaning`) is not asked about again.
  const missing =
    target !== null &&
    map !== null &&
    resolve(map, target.word).kind === "miss" &&
    resolve(map, target.word).saved !== "no_meaning";
  useEffect(() => {
    if (target && missing) onMiss?.(target.word, target.line);
    // Once per opening; `onMiss` itself refuses a word already asked about.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => {
    if (!target) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, onClose]);

  if (!target) return null;

  const save = () => {
    setSaving(true);
    // **Optimistic nothing** (W13-ii): the line appears when the server answers.
    saveWord(videoId, target.word, target.line)
      .then((result) => {
        setOutcome(outcomeOf(result));
        if (result.state === "saved" || result.state === "already_saved") onKept?.(target.word, "in_deck");
        if (result.state === "pending") onKept?.(target.word, "pending");
      })
      .catch((error: unknown) => setOutcome(refusal(error)))
      .finally(() => setSaving(false));
  };

  const resolved = map ? resolve(map, target.word) : null;
  const lookup = !map && typeof found === "object" ? found : null;
  const lemma = resolved ? resolved.key : lookup?.lemma;
  const line = resolved ? lineText : lookup?.line;
  const saved = resolved ? resolved.saved : lookup?.saved;
  const image = resolved ? resolved.image : lookup?.image;
  const kept = saved !== undefined && saved !== "none";
  const ready = resolved !== null || lookup !== null;

  return (
    <div className="fixed inset-0 z-[60]" data-testid="word-sheet-layer">
      <button
        type="button"
        aria-label={VIDEO.sheet.close}
        className="absolute inset-0 bg-black/30"
        data-testid="word-sheet-backdrop"
        onClick={onClose}
      />
      {/*
        **W32e (B2) — the sheet fits a short screen.** The operator's iPhone,
        sideways: the sheet ran under the bottom nav and Save was off the
        screen. Now three parts in a column held to the viewport — the word,
        a body that scrolls, and **Save in a footer that never scrolls away**.
        75% of the height on a tall screen, so the video stays in sight; on a
        short one (a phone turned, a keyboard up) all of it but the top inset.
        Every safe-area inset is respected (a notch sits at the side when the
        phone is turned).
      */}
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="word-sheet-word"
        data-testid="word-sheet"
        className="absolute inset-x-0 bottom-0 flex max-h-[75dvh] flex-col overflow-hidden rounded-t-2xl border-t bg-background pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] shadow-lg [@media(max-height:32rem)]:max-h-[calc(100dvh-max(0.5rem,env(safe-area-inset-top)))] lg:inset-x-auto lg:bottom-6 lg:left-1/2 lg:w-[32rem] lg:-translate-x-1/2 lg:rounded-2xl lg:border"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 pt-4">
          <div className="min-w-0">
            <h2 id="word-sheet-word" lang="en" className="text-2xl font-semibold" data-testid="word-sheet-word">
              {target.word}
            </h2>
            {ready && lemma && lemma !== target.word.toLowerCase() ? (
              <p className="text-sm text-muted-foreground" data-testid="word-sheet-lemma">
                {VIDEO.sheet.fromLemma.replace("{lemma}", lemma)}
              </p>
            ) : null}
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="min-h-11 min-w-11"
            data-testid="word-sheet-close"
            onClick={onClose}
          >
            {VIDEO.sheet.close}
          </Button>
        </div>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-3"
          data-testid="word-sheet-body"
        >
          {!ready && found === "unavailable" ? (
            <p className="mt-3 text-sm text-muted-foreground" data-testid="word-sheet-unavailable">
              {VIDEO.sheet.unavailable}
            </p>
          ) : !ready ? (
            <p className="mt-3 text-sm text-muted-foreground" data-testid="word-sheet-loading">
              {VIDEO.sheet.loading}
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {line ? (
                <p lang="en" className="text-sm italic leading-relaxed text-muted-foreground" data-testid="word-sheet-line">
                  {line}
                </p>
              ) : null}

              {resolved ? (
                <FromMap found={resolved} language={map?.l1 ?? null} lookingUp={lookingUp} />
              ) : lookup?.meaning ? (
                <div className="space-y-1" data-testid="word-sheet-meaning">
                  <p lang="en" className="text-base leading-relaxed">
                    {lookup.meaning.definition}
                    <RegisterChip register={lookup.meaning.register} />
                  </p>
                  {lookup.meaning.neutral_equivalent ? (
                    <p className="text-sm text-muted-foreground">
                      {VIDEO.sheet.safer} <span lang="en">{lookup.meaning.neutral_equivalent}</span>
                    </p>
                  ) : null}
                  <L1 text={lookup.meaning.l1} language={lookup.meaning.l1_language} />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground" data-testid="word-sheet-no-meaning">
                  {lookup?.saved === "no_meaning" ? VIDEO.sheet.noMeaningFound : VIDEO.sheet.noMeaning}
                </p>
              )}

              {image ? <CardImage image={image} /> : null}
            </div>
          )}
        </div>

        {ready ? (
          <div
            className="shrink-0 space-y-2 border-t pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]"
            data-testid="word-sheet-footer"
          >
            {outcome ? (
              <p
                className="text-sm text-muted-foreground"
                data-testid="save-word-result"
                data-outcome={outcome}
                aria-live="polite"
              >
                {TAP_COPY[outcome]}
              </p>
            ) : null}
            {outcome && !RETRYABLE.has(outcome) ? null : kept ? (
              <p className="text-sm text-muted-foreground" data-testid="word-sheet-kept">
                {saved === "pending"
                  ? VIDEO.sheet.pending
                  : saved === "no_meaning"
                    ? VIDEO.sheet.noMeaningFound
                    : VIDEO.sheet.inDeck}
              </p>
            ) : (
              <Button
                className="min-h-11 w-full"
                data-testid="word-sheet-save"
                disabled={saving}
                onClick={save}
              >
                {saving ? VIDEO.sheet.saving : VIDEO.sheet.save}
              </Button>
            )}
          </div>
        ) : (
          <div className="shrink-0 pb-[max(1rem,env(safe-area-inset-bottom))]" />
        )}
      </section>
    </div>
  );
}

/**
 * W32b: the meaning, from the map. **The video's own meaning first, labelled
 * *here*; the dictionary's senses under it** (context beats dictionary), each
 * with the learner's language. A name is said plainly; a word with nothing
 * stored says so and still offers Save.
 */
function FromMap({
  found,
  language,
  lookingUp,
}: {
  found: Resolved;
  language: string | null;
  lookingUp: boolean;
}) {
  if (found.kind === "name") {
    return (
      <p className="text-sm text-muted-foreground" data-testid="word-sheet-name">
        {VIDEO.sheet.aName}
      </p>
    );
  }
  if (found.kind === "miss" && lookingUp) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="word-sheet-looking" aria-live="polite">
        {VIDEO.sheet.loading}
      </p>
    );
  }
  if (found.kind === "miss") {
    return (
      <p className="text-sm text-muted-foreground" data-testid="word-sheet-no-meaning">
        {found.saved === "no_meaning" ? VIDEO.sheet.noMeaningFound : VIDEO.sheet.noMeaning}
      </p>
    );
  }
  return (
    <div className="space-y-3" data-testid="word-sheet-meaning">
      {found.here ? (
        <div className="space-y-1 rounded-lg bg-muted/40 p-2" data-testid="word-sheet-here">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{VIDEO.sheet.here}</p>
          <p lang="en" className="text-base leading-relaxed">
            {found.here.d}
            <RegisterChip register={found.here.r} />
          </p>
          <L1 text={found.here.l1} language={language} />
        </div>
      ) : null}
      {found.senses.length ? (
        <ol className="space-y-2">
          {found.senses.map((sense, index) => (
            <li key={index} className="space-y-0.5" data-testid="word-sheet-sense">
              <p lang="en" className="text-base leading-relaxed">
                <span className="mr-1.5 text-sm text-muted-foreground">{sense.pos}</span>
                {sense.definition}
                {index === 0 && !found.here ? <RegisterChip register={found.register} /> : null}
              </p>
              <L1 text={sense.l1} language={language} />
            </li>
          ))}
        </ol>
      ) : null}
      {found.neutral ? (
        <p className="text-sm text-muted-foreground">
          {VIDEO.sheet.safer} <span lang="en">{found.neutral}</span>
        </p>
      ) : null}
    </div>
  );
}
