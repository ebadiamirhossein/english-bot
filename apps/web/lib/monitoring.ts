/**
 * W23 — the web app's one door to Sentry (build run 2, ruling 0.2).
 *
 * `instrumentation-client.ts` calls `startMonitoring()` once; `RequireSession`
 * calls `setMonitoringUser()` when it learns who is signed in. **Nothing else in
 * the app imports `@sentry/nextjs`**, and `lib/monitoring.test.ts` holds that by
 * reading the source tree — the Python side's `core/monitoring.py` rule, here.
 *
 * **OFF WHEN `NEXT_PUBLIC_SENTRY_DSN` IS UNSET, AND IT IS UNSET UNTIL THE LAUNCH
 * PASS.** The SDK is then never even downloaded: it is a dynamic `import()`,
 * so the bundle a learner loads today does not carry it.
 *
 * **WHAT SENTRY RECEIVES — THE WHOLE LIST, BECAUSE `scrubEvent` IS AN ALLOWLIST.**
 * An exception's type, the stack frames' file, function, line and column, the
 * learner's `users.id`, the tag `component=web`, the environment and the SDK's
 * name. **Not the exception's message** (`new Error(\`… ${text}\`)` would carry
 * a sentence), not the page URL or request, not breadcrumbs (console lines and
 * clicks), not a source line, not a replay — nothing a key the SDK adds tomorrow
 * could carry, because it is not on the list.
 *
 * **The automatic integrations are off.** Three are put back by name: global
 * handlers (uncaught errors and rejections — the reason to have this at all),
 * linked errors (an error's `cause`), and dedupe. No tracing, no replay, no
 * sessions, no HTTP context.
 *
 * **Why the DSN is public and that is fine:** a browser DSN is visible to anyone
 * who opens the bundle by design — it can only SEND events to the project. What
 * this file controls is what those events contain.
 */

import type { ErrorEvent } from "@sentry/nextjs";

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || "";

/** Sentry's docs: an EU organisation "must use `o<number>.ingest.de.sentry.io`". */
const EU_HOST = /^o\d+\.ingest\.de\.sentry\.io$/;

/** Parsed, never substring-matched — `core/config.py`'s `_is_eu_sentry_dsn`, in TS. */
export function isEuDsn(dsn: string): boolean {
  try {
    const url = new URL(dsn);
    return (
      url.protocol === "https:" &&
      url.username !== "" &&
      EU_HOST.test(url.hostname) &&
      /^\/\d+\/?$/.test(url.pathname)
    );
  } catch {
    return false;
  }
}

const EVENT_KEYS = ["event_id", "timestamp", "level", "platform", "environment", "sdk"] as const;
const FRAME_KEYS = ["filename", "function", "lineno", "colno", "in_app"] as const;
const KEPT_TAGS = ["component"] as const;

type Loose = Record<string, unknown>;

function pick(source: Loose, keys: readonly string[]): Loose {
  const out: Loose = {};
  for (const key of keys) if (key in source) out[key] = source[key];
  return out;
}

/**
 * `beforeSend`: rebuild the event from an allowlist. Built fresh, so nothing
 * survives by being forgotten. **Never the exception's `value`.**
 */
// The SDK passes a hint as the second argument; nothing here reads it.
export function scrubEvent(event: ErrorEvent): ErrorEvent {
  const source = event as unknown as Loose;
  const out = pick(source, EVENT_KEYS);

  const user = (source.user ?? {}) as Loose;
  if (user.id !== undefined && user.id !== null) out.user = { id: String(user.id) };

  const tags = pick((source.tags ?? {}) as Loose, KEPT_TAGS);
  if (Object.keys(tags).length) out.tags = tags;

  const values = (((source.exception ?? {}) as Loose).values ?? []) as Loose[];
  if (values.length) {
    out.exception = {
      values: values.map((value) => {
        const kept = pick(value, ["type"]);
        const mechanism = value.mechanism as Loose | undefined;
        if (mechanism) kept.mechanism = pick(mechanism, ["type", "handled"]);
        const frames = (((value.stacktrace ?? {}) as Loose).frames ?? []) as Loose[];
        if (frames.length) kept.stacktrace = { frames: frames.map((f) => pick(f, FRAME_KEYS)) };
        return kept;
      }),
    };
  }
  return out as unknown as ErrorEvent;
}

/**
 * The six things this file uses, destructured AT the `import()` so the bundler
 * can drop the rest of the SDK — session replay included — from the lazy
 * chunk. A namespace import kept all of it: measured 2026-09-25, the chunk
 * carried rrweb, which nothing here turns on.
 */
async function loadSdk() {
  const {
    init,
    setTag,
    setUser,
    globalHandlersIntegration,
    linkedErrorsIntegration,
    dedupeIntegration,
  } = await import("@sentry/nextjs");
  return { init, setTag, setUser, globalHandlersIntegration, linkedErrorsIntegration, dedupeIntegration };
}

type Sdk = Awaited<ReturnType<typeof loadSdk>>;

let sdk: Sdk | null = null;
let pendingUser: number | null = null;

export type StartOptions = {
  dsn?: string;
  /** Tests only: a transport that keeps envelopes in memory. */
  transport?: NonNullable<Parameters<Sdk["init"]>[0]>["transport"];
  /** Tests only: where the SDK comes from. */
  load?: () => Promise<Sdk>;
};

/** Start Sentry in this browser, or stay off. Resolves to whether it started. */
export async function startMonitoring({
  dsn = SENTRY_DSN,
  transport,
  load = loadSdk,
}: StartOptions = {}): Promise<boolean> {
  if (!dsn) return false;
  if (!isEuDsn(dsn)) {
    // `scripts/check-env.mjs` refuses this at build; this is the second line.
    console.error("NEXT_PUBLIC_SENTRY_DSN is not an EU-region DSN — monitoring stays off (ruling 0.2)");
    return false;
  }
  const Sentry = await load();
  Sentry.init({
    dsn,
    environment: "production",
    // Ruling 0.2, and the default — stated so no one has to know that.
    sendDefaultPii: false,
    defaultIntegrations: false,
    integrations: [
      Sentry.globalHandlersIntegration(),
      Sentry.linkedErrorsIntegration(),
      Sentry.dedupeIntegration(),
    ],
    beforeSend: scrubEvent,
    beforeBreadcrumb: () => null,
    maxBreadcrumbs: 0,
    sendClientReports: false,
    ...(transport ? { transport } : {}),
  });
  Sentry.setTag("component", "web");
  sdk = Sentry;
  if (pendingUser !== null) Sentry.setUser({ id: String(pendingUser) });
  return true;
}

/** Who is signed in — the internal `users.id`, never a name. `null` on sign-out. */
export function setMonitoringUser(id: number | null): void {
  pendingUser = id;
  sdk?.setUser(id === null ? null : { id: String(id) });
}
