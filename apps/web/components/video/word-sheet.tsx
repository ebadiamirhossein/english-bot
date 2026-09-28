"use client";

import { useEffect, useState } from "react";

import { CardImage } from "@/components/cards/card-image";
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

/** Right-to-left scripts among the learners' languages (#159: keyed on the
 * language, never guessed from the characters). */
const RTL = new Set(["fa"]);

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
  return (
    <p
      data-testid="word-sheet-l1"
      lang={language}
      dir={RTL.has(language) ? "rtl" : "ltr"}
      className="text-base"
    >
      {text}
    </p>
  );
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
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="word-sheet-word"
        data-testid="word-sheet"
        className="absolute inset-x-0 bottom-0 max-h-[75dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-lg lg:inset-x-auto lg:bottom-6 lg:left-1/2 lg:w-[32rem] lg:-translate-x-1/2 lg:rounded-2xl lg:border"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
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
              <FromMap found={resolved} language={map?.l1 ?? null} />
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
function FromMap({ found, language }: { found: Resolved; language: string | null }) {
  if (found.kind === "name") {
    return (
      <p className="text-sm text-muted-foreground" data-testid="word-sheet-name">
        {VIDEO.sheet.aName}
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
