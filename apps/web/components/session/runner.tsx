"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import {
  CloseBlock,
  FocusBlock,
  InputBlock,
  OutputBlock,
  ReviewBlock,
} from "@/components/session/blocks";
import { SESSION_DONE } from "@/components/session/copy";
import {
  ApiError,
  getSessionToday,
  type SessionToday,
} from "@/lib/api";

/**
 * The daily session: five blocks, one screen, resumable.
 *
 * **A failed request is a `problem`, never five empty blocks.** This is the
 * distinction the whole slice is built around: an empty block is a fact the
 * server computed after a successful read, and a request that did not come back
 * is neither empty nor unavailable — it is unknown, and the only honest thing to
 * show is a retry. A learner told *nothing's due, go watch something* because a
 * fetch failed has been lied to, and on the screen the lie is indistinguishable
 * from the truth.
 *
 * **The session opens each day and yesterday leaves nothing behind.** No badge,
 * no carried count, no mention of a session that was not finished. Missed days
 * shrink the task; they never pile up (CLAUDE.md §4).
 *
 * **Resume comes from the server, not from this device.** `block_breakdown`
 * holds which blocks are done, so locking a phone mid-session and reopening it —
 * or opening it on the other phone — lands in the same place. No `localStorage`,
 * no `sessionStorage`: the only permitted browser storage in this app is the
 * theme, under one key, in one file (CLAUDE.md §5).
 */
type Loading =
  | { kind: "loading" }
  | { kind: "ready"; session: SessionToday }
  | { kind: "problem"; message: string };

function message(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "That didn’t work. Try again in a moment.";
}

export function SessionRunner() {
  const [state, setState] = useState<Loading>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const session = await getSessionToday();
      setState({ kind: "ready", session });
    } catch (error) {
      setState({ kind: "problem", message: message(error) });
    }
  }, []);

  useEffect(() => {
    let live = true;
    getSessionToday()
      .then((session) => live && setState({ kind: "ready", session }))
      .catch((error) => live && setState({ kind: "problem", message: message(error) }));
    return () => {
      live = false;
    };
  }, []);


  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Opening today’s session…</p>;
  }

  if (state.kind === "problem") {
    return (
      <div className="space-y-3" data-testid="session-problem">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {state.message}
        </p>
        <Button type="button" onClick={() => void load()}>
          Try again
        </Button>
      </div>
    );
  }

  const { session } = state;
  const current = session.blocks.find((b) => b.n === session.current_block);

  return (
    <div className="space-y-5" data-testid="session-runner" data-session-id={session.session_id}>
      {/* Position within TODAY, which is not a backlog: it counts what this
          session contains, and it is the same five every day whatever happened
          yesterday. Nothing here accumulates. */}
      <p
        className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground"
        data-testid="session-position"
      >
        Block {session.current_block} of {session.blocks.length}
      </p>

      {session.blocks.map((block) => {
        if (block.kind === "review") {
          return (
            <ReviewBlock
              key={block.n}
              block={block}
              l1Language={session.l1_language}
              sessionId={session.session_id}
              onGraded={load}
            />
          );
        }
        if (block.kind === "input")
          return (
            <InputBlock
              key={block.n}
              block={block}
              l1Language={session.l1_language}
            />
          );
        if (block.kind === "focus")
          return (
            <FocusBlock
              key={block.n}
              block={block}
              sessionId={session.session_id}
            />
          );
        if (block.kind === "output")
          return (
            <OutputBlock
              key={block.n}
              block={block}
              sessionId={session.session_id}
            />
          );
        return <CloseBlock key={block.n} block={block} />;
      })}


      {session.completed ? (
        <div className="space-y-2" data-testid="session-finished">
          <p className="font-heading text-2xl leading-snug">{SESSION_DONE.title}</p>
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            {SESSION_DONE.body}
          </p>
        </div>
      ) : null}
    </div>
  );
}
