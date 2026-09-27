"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { getAuthHealth } from "@/lib/api";
import { setMonitoringUser } from "@/lib/monitoring";
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
  | { kind: "out" }
  | { kind: "unreachable"; message: string };

export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<State>({ kind: "checking" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // getAuthHealth never rejects: it returns which of the three outcomes
    // happened, so "nobody is signed in" cannot arrive here as an error.
    getAuthHealth().then((result) => {
      if (cancelled) return;
      if (result.kind === "signed-in") {
        // W23: the id an error report carries — `users.id`, never the name.
        setMonitoringUser(result.session.user_id);
        setState({ kind: "in", user: result.session as unknown as SessionUser });
      } else if (result.kind === "anonymous") {
        setMonitoringUser(null);
        setState({ kind: "out" });
      } else {
        // Deliberately NOT a redirect. Sending someone to /sign-in because the
        // API is down tells them to fix the wrong problem — and signing in is
        // the one thing that cannot work while it is down.
        setState({ kind: "unreachable", message: result.message });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [pathname, attempt]);

  useEffect(() => {
    if (state.kind === "out") router.replace("/sign-in");
  }, [state.kind, router]);

  if (state.kind === "unreachable") {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col items-center lg:max-w-2xl justify-center gap-4 px-5 text-center">
        <p className="font-heading text-lg">We can’t reach the app right now.</p>
        <p className="max-w-prose text-sm text-muted-foreground">
          Nothing is lost — this is a connection problem, not your account.
        </p>
        <button
          onClick={() => {
            setState({ kind: "checking" });
            setAttempt((n) => n + 1);
          }}
          className="h-12 rounded-2xl bg-primary px-6 text-sm font-semibold text-primary-foreground"
        >
          Try again
        </button>
      </div>
    );
  }

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
