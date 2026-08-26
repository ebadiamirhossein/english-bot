"use client";

import { Button } from "@/components/ui/button";
import { BLOCK_UNAVAILABLE } from "@/components/session/copy";

/**
 * The frame every block renders inside, and the two states it renders itself.
 *
 * **`empty` and `unavailable` are drawn differently because they mean different
 * things.** An empty block has been asked and has nothing: the copy belongs to
 * that block and says what is true of it. An unavailable block could not be
 * built, says so, and offers the way back. A learner told *nothing's due, go
 * watch something* because a query fell over has been lied to, and on the screen
 * the lie is indistinguishable from the truth.
 *
 * **No red, in either.** The palette has no red in it by design and a block that
 * failed to load is not an alarm.
 */
export function BlockShell({
  n,
  kind,
  state,
  eyebrow,
  title,
  onRetry,
  children,
}: {
  n: number;
  kind: string;
  state: string;
  eyebrow: string;
  title: string;
  onRetry?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <section
      className="space-y-4 rounded-2xl border border-border bg-card p-5"
      data-testid="session-block"
      data-block-n={n}
      data-block-kind={kind}
      data-block-state={state}
    >
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {eyebrow}
        </p>
        <h2 className="font-heading text-xl leading-snug">{title}</h2>
      </header>

      {state === "unavailable" ? (
        <div className="space-y-3" data-testid="block-unavailable">
          <p className="text-sm leading-relaxed">{BLOCK_UNAVAILABLE.title}</p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {BLOCK_UNAVAILABLE.body}
          </p>
          {onRetry ? (
            <Button type="button" variant="outline" onClick={onRetry}>
              {BLOCK_UNAVAILABLE.action}
            </Button>
          ) : null}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
