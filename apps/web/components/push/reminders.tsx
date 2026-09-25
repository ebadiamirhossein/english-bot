"use client";

/**
 * W20 — the daily-reminder control, inside the settings menu. PRD §10.
 *
 * **What it draws, and when:**
 *
 * - **nothing** while it is still finding out, when the server has no VAPID key
 *   (`public_key: null` — reminders are not set up here), when the key cannot be
 *   read, and when this browser cannot do Web Push at all. A control that can
 *   never work is not drawn, disabled or explained.
 * - **one line** on iOS outside a Home Screen app, where Safari exposes no
 *   `PushManager`: the one step that makes reminders possible there.
 * - **one line** when notifications are blocked in the browser's settings.
 * - **the switch**, off or on, with what the reminder is beneath it.
 *
 * **The state is this browser's, read from the server** (`POST /push/state`),
 * not inferred from `getSubscription()` alone: a subscription the server has
 * forgotten (it answered `410`, or another learner turned reminders on here) is
 * off, and the switch says so.
 *
 * **The endpoint only travels in a JSON body** (`lib/api.ts`), and nothing here
 * logs it.
 *
 * **`applicationServerKey` is passed as the server's base64url string.** Every
 * engine that implements `PushManager.subscribe` accepts a string there, so no
 * byte conversion is written by hand — the rule `lib/webauthn.ts` already keeps
 * (`test_the_frontend_writes_no_base64url_by_hand`).
 *
 * Conventions are ruling 0.3's: the mono eyebrow, a bordered pill for the
 * control at 44px, the serif for the app's own words, the caution tokens for a
 * line the learner has to act on elsewhere.
 */

import { useEffect, useRef, useState } from "react";

import { REMINDERS } from "@/components/session/copy";
import { getPushKey, getPushState, subscribePush, unsubscribePush } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ReminderPhase =
  | "checking"
  | "hidden"
  | "install"
  | "blocked"
  | "unknown"
  | "off"
  | "on";

const EYEBROW =
  "px-2 pt-1 font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground";
const VOICE = "px-2 font-heading text-[0.8125rem] leading-snug";

/** Can this browser subscribe at all? */
export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/**
 * iOS/iPadOS in a browser tab rather than a Home Screen app. iPadOS reports
 * itself as a Mac, so a Mac with a touch screen is counted as one.
 */
export function needsHomeScreen(): boolean {
  if (typeof window === "undefined") return false;
  const ios =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (!ios) return false;
  const standalone =
    (navigator as Navigator & { standalone?: boolean }).standalone === true ||
    (typeof window.matchMedia === "function" &&
      window.matchMedia("(display-mode: standalone)").matches);
  return !standalone;
}

async function firstPhase(): Promise<{ phase: ReminderPhase; key: string | null }> {
  let key: string | null;
  try {
    key = (await getPushKey()).public_key;
  } catch {
    return { phase: "hidden", key: null };
  }
  if (!key) return { phase: "hidden", key: null };
  if (!pushSupported()) return { phase: needsHomeScreen() ? "install" : "hidden", key };
  if (Notification.permission === "denied") return { phase: "blocked", key };
  try {
    // `ready` never settles where no worker registers (development builds):
    // then the control simply never appears, which is the truth there.
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return { phase: "off", key };
    const { on } = await getPushState(subscription.endpoint);
    return { phase: on ? "on" : "off", key };
  } catch {
    return { phase: "unknown", key };
  }
}

type Outcome = "on" | "off" | "blocked" | "closed";

/**
 * **`requestPermission` is the first call, before any `await`.** iOS grants the
 * prompt only from inside the tap; one awaited promise ahead of it and Safari
 * treats the request as unprompted and refuses it.
 */
async function turnOn(key: string): Promise<Outcome> {
  const permission = await Notification.requestPermission();
  if (permission === "denied") return "blocked";
  if (permission !== "granted") return "closed";
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    }));
  const { on } = await subscribePush(subscription.toJSON());
  return on ? "on" : "off";
}

/**
 * The server first: once it has forgotten this browser nothing more is sent,
 * whatever the browser does next. A browser-side unsubscribe that then refuses
 * leaves a subscription nobody sends to, which costs nothing — so it is not
 * reported as trouble.
 */
async function turnOff(): Promise<Outcome> {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    const { on } = await unsubscribePush(subscription.endpoint);
    await subscription.unsubscribe().catch(() => undefined);
    return on ? "on" : "off";
  }
  return "off";
}

export function Reminders() {
  const [phase, setPhase] = useState<ReminderPhase>("checking");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<"closed" | "trouble" | null>(null);
  const key = useRef<string | null>(null);

  useEffect(() => {
    let live = true;
    firstPhase()
      .then((first) => {
        if (!live) return;
        key.current = first.key;
        setPhase(first.phase);
      })
      // Anything unforeseen is "not drawn", never a half-drawn control.
      .catch(() => live && setPhase("hidden"));
    return () => {
      live = false;
    };
  }, []);

  function toggle() {
    if (busy || (phase !== "on" && phase !== "off") || !key.current) return;
    setNote(null);
    setBusy(true);
    // Called synchronously from the tap — see `turnOn`.
    const work = phase === "on" ? turnOff() : turnOn(key.current);
    work
      .then((outcome) => {
        if (outcome === "closed") setNote("closed");
        else setPhase(outcome);
      })
      .catch(() => setNote("trouble"))
      .finally(() => setBusy(false));
  }

  if (phase === "checking" || phase === "hidden") return null;

  return (
    <>
      <div className="space-y-1.5" data-testid="reminders" data-phase={phase} data-busy={busy}>
        <p className={EYEBROW}>{REMINDERS.eyebrow}</p>

        {phase === "install" ? (
          <p className={cn(VOICE, "pb-1 text-muted-foreground")} data-testid="reminders-install">
            {REMINDERS.install}
          </p>
        ) : null}

        {phase === "blocked" ? (
          <p
            className="rounded-2xl border border-caution-border bg-caution px-3 py-2.5 font-heading text-[0.8125rem] leading-snug text-caution-foreground"
            data-testid="reminders-blocked"
          >
            {REMINDERS.blocked}
          </p>
        ) : null}

        {phase === "on" || phase === "off" ? (
          <>
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={phase === "on"}
              aria-busy={busy}
              disabled={busy}
              onClick={toggle}
              data-testid="reminders-toggle"
              className="flex min-h-11 w-full items-center gap-3 rounded-full border border-border bg-background px-3.5 text-sm transition-colors hover:bg-muted disabled:cursor-default"
            >
              <span className="flex-1 text-left">{REMINDERS.toggle}</span>
              {busy ? <Working /> : <Switch on={phase === "on"} />}
            </button>
            <p className={cn(VOICE, "text-muted-foreground")} data-testid="reminders-about">
              {REMINDERS.about}
            </p>
          </>
        ) : null}

        {phase === "unknown" || note === "trouble" ? (
          <p
            role="status"
            className="rounded-2xl border border-caution-border bg-caution px-3 py-2.5 font-heading text-[0.8125rem] leading-snug text-caution-foreground"
            data-testid="reminders-trouble"
          >
            {REMINDERS.trouble}
          </p>
        ) : null}
        {note === "closed" ? (
          <p role="status" className={cn(VOICE, "text-muted-foreground")} data-testid="reminders-closed">
            {REMINDERS.closed}
          </p>
        ) : null}
      </div>
      {/* The divider below is the section's own, so a menu without the section
          draws no empty pair of lines. */}
      <div className="my-1 h-px bg-border" />
    </>
  );
}

/** Drawn, not a checkbox: the whole pill is the control and says its state. */
function Switch({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden="true"
      data-testid="reminders-switch"
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors",
        on ? "border-primary bg-primary" : "border-border bg-muted",
      )}
    >
      <span
        className={cn(
          "absolute h-4 w-4 rounded-full shadow-sm transition-transform",
          on ? "translate-x-[1.125rem] bg-primary-foreground" : "translate-x-1 bg-background",
        )}
      />
    </span>
  );
}

/** `/talk`'s three dots: it is doing something, and nothing says how long. */
function Working() {
  return (
    <span className="flex h-6 w-10 shrink-0 items-center justify-center gap-1.5" data-testid="reminders-working">
      <span className="sr-only">{REMINDERS.working}</span>
      {[0, 1, 2].map((n) => (
        <span
          key={n}
          aria-hidden="true"
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary"
          style={{ animationDelay: `${n * 180}ms` }}
        />
      ))}
    </span>
  );
}
