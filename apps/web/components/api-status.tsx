"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";

type State =
  | { kind: "checking" }
  | { kind: "reachable"; schemaVersion: number | null }
  | { kind: "unreachable"; detail: string };

/**
 * A one-line proof that this app can reach its backend from the browser.
 *
 * On purpose it runs client-side: a server-component fetch would talk to the
 * API over the loopback interface and prove nothing about CORS, which is the
 * part that breaks on a phone (W0 risk R4).
 */
export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) {
          setState({ kind: "reachable", schemaVersion: health.schema_version });
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setState({ kind: "unreachable", detail: error.message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dot =
    state.kind === "reachable"
      ? "bg-primary"
      : state.kind === "checking"
        ? "bg-muted-foreground/50"
        : "bg-muted-foreground";

  return (
    <p className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden />
      {state.kind === "checking" && "Checking the API…"}
      {state.kind === "reachable" &&
        `API reachable — schema version ${state.schemaVersion ?? "unknown"}`}
      {state.kind === "unreachable" && state.detail}
    </p>
  );
}
