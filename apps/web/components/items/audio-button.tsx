"use client";

import { useRef, useState } from "react";

import { itemAudioUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";

/**
 * Play the item's audio. **Fetched on tap, never on load.**
 *
 * That is the whole reason a session still opens in under a second with three
 * audio types in it: nothing is synthesised until someone asks for it. The
 * `<audio>` element rather than a `fetch` lets the platform handle buffering
 * and the lock-screen controls, and `crossOrigin="use-credentials"` is what
 * carries the session cookie to the API on its own origin — without it the
 * element requests anonymously and the route answers 401.
 *
 * A failure says the audio did not arrive and offers another tap. It does not
 * say why: a provider message would be a free map of the backend, and to the
 * learner "it did not play, try again" is the whole of the useful information.
 */
export function AudioButton({ itemId }: { itemId: number }) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "played" | "problem">(
    "idle",
  );

  async function play() {
    setState("loading");
    try {
      const element = ref.current;
      if (!element) return;
      element.currentTime = 0;
      await element.play();
      setState("played");
    } catch {
      setState("problem");
    }
  }

  return (
    <div className="space-y-2">
      <audio
        ref={ref}
        src={itemAudioUrl(itemId)}
        crossOrigin="use-credentials"
        preload="none"
        data-testid="item-audio"
      />
      <Button
        type="button"
        size="lg"
        variant="outline"
        onClick={play}
        className="h-14 w-full rounded-2xl text-base font-semibold"
      >
        {state === "loading"
          ? "Loading…"
          : state === "played"
            ? "Play again"
            : "Play"}
      </Button>
      {state === "problem" ? (
        <p className="text-center text-sm text-muted-foreground">
          That didn&rsquo;t play. Give it another tap.
        </p>
      ) : null}
    </div>
  );
}
