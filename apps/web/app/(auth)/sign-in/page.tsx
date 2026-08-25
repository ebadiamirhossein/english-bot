"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { passkeysSupported, signIn, wasCancelled } from "@/lib/webauthn";

type State =
  | { kind: "ready" }
  | { kind: "waiting" }
  | { kind: "unsupported" }
  | { kind: "problem"; message: string; offerEnrol: boolean };

/**
 * Sign in. One button, because there is one thing to do.
 *
 * No email field and no password field: the passkey is discoverable, so the
 * browser offers it and the assertion carries who it belongs to.
 *
 * Every message here is written to the "never guilt" rule (CLAUDE.md §4). A
 * cancelled prompt is not a failure and is not described as one; an
 * unrecognised passkey points at enrolment instead of saying "denied".
 */
export default function SignInPage() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "ready" });

  useEffect(() => {
    if (!passkeysSupported()) setState({ kind: "unsupported" });
  }, []);

  async function attempt() {
    setState({ kind: "waiting" });
    try {
      await signIn();
      router.replace("/");
    } catch (error) {
      if (wasCancelled(error)) {
        setState({
          kind: "problem",
          message: "No passkey was offered. Try again when you’re ready.",
          offerEnrol: false,
        });
        return;
      }
      // A 401 here means the assertion did not match an account on this
      // device — the useful next step is enrolling, not retrying.
      const unknown = error instanceof ApiError && error.status === 401;
      setState({
        kind: "problem",
        message: unknown
          ? "That passkey isn’t set up here yet."
          : error instanceof Error
            ? error.message
            : "That didn’t work. Try again in a moment.",
        offerEnrol: unknown,
      });
    }
  }

  return (
    <>
      <PageHeader eyebrow="Everyday English" title="Welcome back.">
        Ten minutes a day, in the English people actually speak.
      </PageHeader>

      <section className="space-y-3">
        <Button
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-semibold"
          onClick={attempt}
          disabled={state.kind === "waiting" || state.kind === "unsupported"}
        >
          {state.kind === "waiting" ? "Waiting for your device…" : "Sign in"}
        </Button>

        {state.kind === "unsupported" ? (
          <p className="text-center text-sm text-muted-foreground">
            This browser can’t use passkeys yet. Updating it — or opening the
            app in Safari or Chrome — will fix this.
          </p>
        ) : null}

        {state.kind === "problem" ? (
          <p className="text-center text-sm text-muted-foreground">
            {state.message}{" "}
            {state.offerEnrol ? (
              <Link href="/enrol" className="text-primary underline underline-offset-4">
                Set this device up
              </Link>
            ) : null}
          </p>
        ) : null}

        {state.kind === "ready" ? (
          <p className="text-center text-sm text-muted-foreground">
            Your phone will ask for your face, fingerprint or PIN. There is no
            password to remember.
          </p>
        ) : null}
      </section>

      <p className="text-center text-xs text-muted-foreground">
        First time on this device?{" "}
        <Link href="/enrol" className="underline underline-offset-4">
          Set it up
        </Link>
      </p>
    </>
  );
}
