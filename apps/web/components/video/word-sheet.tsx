"use client";

import { useEffect, useState } from "react";

import { CardImage } from "@/components/cards/card-image";
import { VIDEO } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  lookupWord,
  saveWord,
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

/**
 * The word sheet. **W31c.** The operator's reference is Trancy / Language
 * Reactor: tap any word, see what it is, keep it.
 *
 * **IT READS AND SAVES; IT NEVER GENERATES.** The meaning is a stored gloss or
 * nothing — and *nothing* still offers Save, because a learner must be able to
 * keep a word nobody has explained yet (the operator's finding, 2026-09-27).
 * The worker explains it later; the card enters the deck only then.
 *
 * **No definition is invented here and nothing counts.** A bottom sheet on a
 * phone, a panel near the bottom on a desktop; above Focus mode, so a word
 * tapped in Focus opens here too.
 */
export function WordSheet({
  videoId,
  target,
  onClose,
}: {
  videoId: number;
  target: SheetTarget | null;
  onClose: () => void;
}) {
  const [found, setFound] = useState<WordLookup | "loading" | "unavailable">("loading");
  const [outcome, setOutcome] = useState<TapOutcome | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!target) return;
    let live = true;
    setFound("loading");
    setOutcome(null);
    lookupWord(videoId, target.word, target.line)
      .then((result) => live && setFound(result))
      .catch(() => live && setFound("unavailable"));
    return () => {
      live = false;
    };
  }, [videoId, target]);

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
      .then((result) => setOutcome(outcomeOf(result)))
      .catch((error: unknown) => setOutcome(refusal(error)))
      .finally(() => setSaving(false));
  };

  const lookup = typeof found === "object" ? found : null;
  const kept = lookup && lookup.saved !== "none";

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
            {lookup && lookup.lemma !== lookup.word ? (
              <p className="text-sm text-muted-foreground" data-testid="word-sheet-lemma">
                {VIDEO.sheet.fromLemma.replace("{lemma}", lookup.lemma)}
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

        {found === "loading" ? (
          <p className="mt-3 text-sm text-muted-foreground" data-testid="word-sheet-loading">
            {VIDEO.sheet.loading}
          </p>
        ) : found === "unavailable" ? (
          <p className="mt-3 text-sm text-muted-foreground" data-testid="word-sheet-unavailable">
            {VIDEO.sheet.unavailable}
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {lookup?.line ? (
              <p lang="en" className="text-sm italic leading-relaxed text-muted-foreground" data-testid="word-sheet-line">
                {lookup.line}
              </p>
            ) : null}

            {lookup?.meaning ? (
              <div className="space-y-1" data-testid="word-sheet-meaning">
                <p lang="en" className="text-base leading-relaxed">
                  {lookup.meaning.definition}
                  {lookup.meaning.register !== "neutral" && lookup.meaning.register !== "formal" ? (
                    <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                      {lookup.meaning.register}
                    </span>
                  ) : null}
                </p>
                {lookup.meaning.neutral_equivalent ? (
                  <p className="text-sm text-muted-foreground">
                    {VIDEO.sheet.safer} <span lang="en">{lookup.meaning.neutral_equivalent}</span>
                  </p>
                ) : null}
                {lookup.meaning.l1 ? (
                  <p
                    data-testid="word-sheet-l1"
                    lang={lookup.meaning.l1_language}
                    dir={RTL.has(lookup.meaning.l1_language ?? "") ? "rtl" : "ltr"}
                    className="text-base"
                  >
                    {lookup.meaning.l1}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="word-sheet-no-meaning">
                {lookup?.saved === "no_meaning" ? VIDEO.sheet.noMeaningFound : VIDEO.sheet.noMeaning}
              </p>
            )}

            {lookup?.image ? <CardImage image={lookup.image} /> : null}

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
                {lookup?.saved === "pending"
                  ? VIDEO.sheet.pending
                  : lookup?.saved === "no_meaning"
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
