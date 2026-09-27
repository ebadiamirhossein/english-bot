"use client";

import Link from "next/link";
import { Layers, MessageCircle, PenLine, Play } from "lucide-react";
import { useEffect, useState } from "react";

import { KEEP_GOING } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { getKeepGoing, type KeepGoingOption } from "@/lib/api";

const HREF: Record<KeepGoingOption, string> = {
  watch: "/watch",
  talk: "/talk",
  cards: "/review",
  write: "/write",
};

const ICON = { watch: Play, talk: MessageCircle, cards: Layers, write: PenLine } as const;

/**
 * **W24e — keep going.** An optional next thing, drawn only from what is
 * actually available now (`GET /keep-going`): the server leaves out an option
 * whose cap is reached or whose surface would open onto nothing, so this
 * component never says *why* something is missing and never counts anything.
 *
 * **Low emphasis by construction** (R4: the close block's row shape, outlined
 * rather than filled): the session's own actions and the close block's
 * *Talk with the app* stay the primary buttons. **A failed or empty answer
 * renders nothing** — this is an offer, not a state the learner must resolve,
 * so there is no retry and no error line.
 *
 * Shown by the runner only once the session is `finished` (R2) and by the
 * Sunday home, where the server's answer is watch-only (R1).
 */
export function KeepGoing({ sunday = false }: { sunday?: boolean }) {
  const [options, setOptions] = useState<KeepGoingOption[] | null>(null);

  useEffect(() => {
    let live = true;
    getKeepGoing()
      .then((r) => live && setOptions(r.options))
      .catch(() => live && setOptions([]));
    return () => {
      live = false;
    };
  }, []);

  if (!options || options.length === 0) return null;

  return (
    <section className="space-y-3 border-t border-border pt-5" data-testid="keep-going">
      <p className="text-sm text-muted-foreground">
        {sunday ? KEEP_GOING.sundayLead : KEEP_GOING.lead}
      </p>
      <ul className="space-y-2">
        {options.map((option) => {
          const Icon = ICON[option];
          return (
            <li key={option}>
              <Button
                asChild
                variant="outline"
                size="lg"
                className="h-12 w-full justify-start gap-3 rounded-2xl text-base font-medium"
              >
                <Link href={HREF[option]} data-testid={`keep-going-${option}`}>
                  <Icon className="size-5" aria-hidden="true" />
                  {KEEP_GOING[option]}
                </Link>
              </Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
