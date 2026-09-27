"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { WATCH } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { VideoPlayer } from "@/components/video/player";
import { startWatch, type VideoBlockPayload } from "@/lib/api";

type State =
  | { kind: "finding" }
  | { kind: "ready"; video: VideoBlockPayload; l1: string }
  | { kind: "none" };

/**
 * W24e. One request, one video, block 2's player — **the SAME payload shape
 * from the same producer** (`sessions.video_payload`), so progress, completion
 * and tap-to-save behave here exactly as they do in the session.
 *
 * **Nothing to watch is not a failure** — the pool had nothing in band and
 * unseen, or today's extra is watched — so both a 404 and an unreachable server
 * land on the same quiet line and a way back. No retry: this was an offer.
 */
export function WatchRunner() {
  const [state, setState] = useState<State>({ kind: "finding" });

  useEffect(() => {
    let live = true;
    startWatch()
      .then((r) => live && setState({ kind: "ready", video: r.video, l1: r.l1_language }))
      .catch(() => live && setState({ kind: "none" }));
    return () => {
      live = false;
    };
  }, []);

  if (state.kind === "finding") {
    return <p className="text-sm text-muted-foreground">{WATCH.finding}</p>;
  }

  if (state.kind === "none") {
    return (
      <div className="space-y-4" data-testid="watch-none">
        <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">{WATCH.none}</p>
        <Button asChild variant="outline" size="lg" className="min-h-11 rounded-2xl">
          <Link href="/" data-testid="watch-back">
            {WATCH.back}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div data-testid="watch-player">
      <VideoPlayer payload={state.video} l1Language={state.l1} />
    </div>
  );
}
