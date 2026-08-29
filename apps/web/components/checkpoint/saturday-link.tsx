"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getCheckpointToday } from "@/lib/api";

/**
 * Saturday's way in to the checkpoint. **Renders nothing on the other six days.**
 *
 * **A link, never a second button.** Home asks for one decision a day and that
 * is the whole design of the page; a second full-width button is the menu it
 * exists to refuse.
 *
 * **It shows only when there is a sitting to go to** — `state: "ready"`. A
 * checkpoint the bank could not fill (`not_ready`) offers nothing, so pointing
 * at it would be sending a learner to a dead end on the one day it matters. One
 * already sat (`done`) is finished, and re-offering it would read as unfinished
 * work — a backlog, in a place CLAUDE.md §4 forbids one.
 *
 * **The day is decided by the SERVER, not by this component.** `GET
 * /checkpoint/today` is what knows the learner's local date (`users.timezone`),
 * and a `new Date().getDay()` here would put a learner in Vilnius on the
 * browser's idea of Saturday. The route simply returns `not_ready` on a
 * Wednesday, because no cohort is waiting.
 */
export function SaturdayLink() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    getCheckpointToday()
      .then((sitting) => live && setReady(sitting.state === "ready"))
      // Silent: home must open with or without this. A failure here is one
      // missing link, not a broken page, and there is nothing a learner could
      // do about it.
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  if (!ready) return null;

  return (
    <p className="text-center text-sm text-muted-foreground">
      <Link
        href="/checkpoint"
        className="text-primary underline underline-offset-4"
        data-testid="saturday-checkpoint-link"
      >
        This week&rsquo;s checkpoint
      </Link>{" "}
      is ready.
    </p>
  );
}
