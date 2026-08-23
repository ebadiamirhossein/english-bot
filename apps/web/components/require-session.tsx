"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { getAuthHealth } from "@/lib/api";
import type { SessionUser } from "@/lib/webauthn";

/**
 * The route guard for everything behind a session.
 *
 * **Why this is a client guard and not Next middleware.** The session cookie is
 * host-only on `api.foundgrant.com` — it has no Domain attribute, deliberately,
 * so the Vercel edge never receives it. Middleware and server components run on
 * that edge and therefore cannot see it. A server-side gate would mean either
 * handing the session cookie to Vercel or proxying the API through it, and both
 * are worse than a splash. (Known issue #74.)
 *
 * **This guard is UX, not security.** Every route that returns learner data
 * requires the session server-side through `require_current_user`; someone who
 * skips this component sees an empty shell and no data. What it buys is that a
 * signed-out learner lands on sign-in instead of on a page that renders nothing.
 *
 * The flash-of-protected-content answer: while the check is in flight this
 * renders a neutral splash and **not** the page. At W2 the screens hold no
 * learner data so the difference is cosmetic; from W3 it is real, which is why
 * the splash is here from the start rather than added when it starts to matter.
 */

const SessionContext = createContext<SessionUser | null>(null);

/** The signed-in learner. Only valid inside RequireSession. */
export function useSession(): SessionUser | null {
  return useContext(SessionContext);
}

type State =
  | { kind: "checking" }
  | { kind: "in"; user: SessionUser }
  | { kind: "out" };

export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    getAuthHealth()
      .then((session) => {
        if (cancelled) return;
        setState(
          session
            ? { kind: "in", user: session as unknown as SessionUser }
            : { kind: "out" },
        );
      })
      .catch(() => {
        // A dead API and a refused origin look identical from here. Either way
        // there is no session, so the sign-in screen is the honest destination.
        if (!cancelled) setState({ kind: "out" });
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    if (state.kind === "out") router.replace("/sign-in");
  }, [state.kind, router]);

  if (state.kind !== "in") {
    return (
      <div
        className="flex min-h-dvh items-center justify-center px-5"
        aria-busy="true"
      >
        {/* The wordmark and nothing else. No nav, no skeleton of the page
            behind it — a skeleton is still a shape of protected content. */}
        <p className="font-heading text-lg text-muted-foreground">
          Everyday English
        </p>
        <span className="sr-only">Checking your session…</span>
      </div>
    );
  }

  return (
    <SessionContext.Provider value={state.user}>
      {children}
    </SessionContext.Provider>
  );
}
