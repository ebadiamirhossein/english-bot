"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { enrol, passkeysSupported, wasCancelled } from "@/lib/webauthn";

type State =
  | { kind: "ready" }
  | { kind: "working" }
  | { kind: "unsupported" }
  | { kind: "problem"; message: string };

const FIELD =
  "h-12 w-full rounded-xl border border-border bg-card px-4 text-base " +
  "outline-none transition-colors placeholder:text-muted-foreground/70 " +
  "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/**
 * First enrolment: claim an account and put a passkey on this device.
 *
 * Two fields, because there are two facts: the address the operator set on the
 * account, and the one-time code they handed over in person. The code is what
 * stands in for email verification — there is no email sender in this slice,
 * so without it, typing an address that exists would be enough to take over
 * the account behind it.
 *
 * The failure message deliberately does not say which of the two was wrong.
 * The server answers the same way for an unknown address, an unapproved
 * learner, an already-claimed account and a bad code; saying more here would
 * undo that on the client.
 */
export default function EnrolPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [state, setState] = useState<State>({ kind: "ready" });

  useEffect(() => {
    if (!passkeysSupported()) setState({ kind: "unsupported" });
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState({ kind: "working" });
    try {
      await enrol(email.trim(), code.trim());
      router.replace("/");
    } catch (error) {
      setState({
        kind: "problem",
        message: wasCancelled(error)
          ? "Nothing was set up. Try again when you’re ready."
          : "That email and code don’t open an account here.",
      });
    }
  }

  const busy = state.kind === "working" || state.kind === "unsupported";

  return (
    <>
      <PageHeader eyebrow="Set up this device" title="One code, once.">
        Use the address your account was set up with, and the code you were
        given. The code works a single time and then it’s spent.
      </PageHeader>

      <form onSubmit={submit} className="space-y-3">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Email</span>
          <input
            type="email"
            className={FIELD}
            autoComplete="username webauthn"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Setup code</span>
          <input
            type="text"
            className={`${FIELD} font-mono tracking-tight`}
            autoComplete="one-time-code"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste the code you were given"
          />
        </label>

        <Button
          type="submit"
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-semibold"
          disabled={busy || !email.trim() || !code.trim()}
        >
          {state.kind === "working" ? "Waiting for your device…" : "Set up"}
        </Button>
      </form>

      {state.kind === "unsupported" ? (
        <p className="text-center text-sm text-muted-foreground">
          This browser can’t use passkeys yet. Updating it — or opening the app
          in Safari or Chrome — will fix this.
        </p>
      ) : null}

      {state.kind === "problem" ? (
        <p className="text-center text-sm text-muted-foreground">
          {state.message}
        </p>
      ) : null}

      <p className="text-center text-xs text-muted-foreground">
        Already set up on this device?{" "}
        <Link href="/sign-in" className="underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </>
  );
}
