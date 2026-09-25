import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import * as Sentry from "@sentry/nextjs";
import { describe, expect, it, vi } from "vitest";
import { createTransport } from "@sentry/nextjs";
import type { ErrorEvent } from "@sentry/nextjs";

import { isEuDsn, scrubEvent, setMonitoringUser, startMonitoring } from "@/lib/monitoring";

/**
 * W23 — the web half of ruling 0.2, in the SDK's own CLIENT build (the one Next
 * bundles for the browser; `vitest.config.ts` aliases it).
 *
 * **THE ROW'S ACCEPTANCE, WEB SIDE:** an uncaught error whose message is a
 * learner's sentence reaches the Sentry transport with the learner's id and
 * without the sentence. The transport keeps the serialised envelope in memory;
 * **no DSN is real and nothing leaves the test.**
 *
 * **RED DEMONSTRATIONS (2026-09-25):**
 * - `scrubEvent` returning `event` unchanged → the acceptance test red (the
 *   sentence reached the envelope in the exception's `value`).
 * - `pick(value, ["type"])` widened to `["type", "value"]` → the acceptance and
 *   allowlist tests red.
 * - `setMonitoringUser`'s `sdk?.setUser(...)` line removed AND the pending-user
 *   line in `startMonitoring` removed → the acceptance test red (no user).
 * - `EU_HOST` loosened to `/sentry\.io$/` → `isEuDsn`'s US cases red.
 * - `import * as Sentry from "@sentry/nextjs"` added to
 *   `components/require-session.tsx` → the one-door test red.
 */

const SENTENCE = "Yesterday I goed to the market with my sister";

describe("isEuDsn — ruling 0.2's region, parsed", () => {
  it.each([
    ["https://k@o1.ingest.de.sentry.io/2", true],
    ["https://k@o4509.ingest.de.sentry.io/4510/", true],
    ["https://k@o1.ingest.sentry.io/2", false],
    ["https://k@o1.ingest.us.sentry.io/2", false],
    ["https://k@o1.ingest.de.sentry.io.example.com/2", false],
    ["https://k@example.com/ingest.de.sentry.io/2", false],
    ["http://k@o1.ingest.de.sentry.io/2", false],
    ["https://o1.ingest.de.sentry.io/2", false],
    ["not a url", false],
  ])("%s → %s", (dsn, eu) => {
    expect(isEuDsn(dsn)).toBe(eu);
  });
});

describe("scrubEvent — an allowlist", () => {
  it("keeps the type, the frames and the id; drops everything that could carry text", () => {
    const raw = {
      event_id: "e1",
      timestamp: 1,
      level: "error",
      platform: "javascript",
      environment: "production",
      sdk: { name: "sentry.javascript.nextjs" },
      message: SENTENCE,
      request: { url: `https://app.foundgrant.com/write?draft=${SENTENCE}`, headers: {} },
      breadcrumbs: [{ message: SENTENCE }],
      extra: { text: SENTENCE },
      contexts: { react: { componentStack: SENTENCE } },
      user: { id: 7, ip_address: "10.0.0.1", username: "x" },
      tags: { component: "web", learner: SENTENCE },
      a_key_from_a_future_sdk: SENTENCE,
      exception: {
        values: [
          {
            type: "TypeError",
            value: SENTENCE,
            mechanism: { type: "onerror", handled: false, data: { text: SENTENCE } },
            stacktrace: {
              frames: [
                {
                  filename: "https://app.foundgrant.com/_next/static/chunks/app/write/page.js",
                  function: "submit",
                  lineno: 1,
                  colno: 2345,
                  in_app: true,
                  abs_path: "x",
                  context_line: SENTENCE,
                  vars: { text: SENTENCE },
                },
              ],
            },
          },
        ],
      },
    } as unknown as ErrorEvent;
    const out = scrubEvent(raw) as unknown as Record<string, unknown>;
    expect(JSON.stringify(out)).not.toContain("goed");
    expect(Object.keys(out).sort()).toEqual(
      ["environment", "event_id", "exception", "level", "platform", "sdk", "tags", "timestamp", "user"].sort(),
    );
    expect(out.user).toEqual({ id: "7" });
    expect(out.tags).toEqual({ component: "web" });
    expect(out.exception).toEqual({
      values: [
        {
          type: "TypeError",
          mechanism: { type: "onerror", handled: false },
          stacktrace: {
            frames: [
              {
                filename: "https://app.foundgrant.com/_next/static/chunks/app/write/page.js",
                function: "submit",
                lineno: 1,
                colno: 2345,
                in_app: true,
              },
            ],
          },
        },
      ],
    });
  });
});

describe("startMonitoring", () => {
  it("stays off, and loads nothing, while the DSN is unset", async () => {
    const load = vi.fn();
    expect(await startMonitoring({ dsn: "", load })).toBe(false);
    expect(load).not.toHaveBeenCalled();
  });

  it("refuses a DSN outside the EU region, and loads nothing", async () => {
    const load = vi.fn();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await startMonitoring({ dsn: "https://k@o1.ingest.sentry.io/2", load })).toBe(false);
    expect(load).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith(expect.stringContaining("not an EU-region DSN"));
    error.mockRestore();
  });

  it("an uncaught error reaches the transport with the learner's id and no sentence", async () => {
    const sent: string[] = [];
    const decoder = new TextDecoder();
    const transport = (options: Parameters<typeof createTransport>[0]) =>
      createTransport(options, async (request) => {
        sent.push(typeof request.body === "string" ? request.body : decoder.decode(request.body));
        return { statusCode: 200 };
      });

    // RequireSession learns the id before or after the SDK loads; both orders
    // must end with the id on the event. This is the "before" order.
    setMonitoringUser(42);
    const started = await startMonitoring({
      dsn: "https://publickey@o0.ingest.de.sentry.io/0",
      transport,
      load: async () => Sentry,
    });
    expect(started).toBe(true);

    // What the browser does with an error nothing caught: it calls the global
    // `onerror` hook, which the SDK's global-handlers integration installed.
    // Called directly because jsdom does not route a synthetic ErrorEvent to it,
    // and Vitest would report a dispatched one as the test's own uncaught error.
    const error = new TypeError(`cannot read the draft: ${SENTENCE}`);
    const onerror = globalThis.onerror as OnErrorEventHandlerNonNull;
    expect(typeof onerror).toBe("function");
    onerror(error.message, "https://app.foundgrant.com/_next/static/chunks/page.js", 1, 1, error);
    await Sentry.flush(2000);

    const wire = sent.join("\n");
    expect(sent.length).toBeGreaterThan(0);
    expect(wire).not.toContain("goed");
    expect(wire).not.toContain("draft");
    const event = JSON.parse(wire.split("\n").find((line) => line.includes('"exception"'))!);
    expect(event.user).toEqual({ id: "42" });
    expect(event.tags).toEqual({ component: "web" });
    expect(event.exception.values[0].type).toBe("TypeError");
    expect(event.exception.values[0].value).toBeUndefined();
    for (const key of ["request", "breadcrumbs", "extra", "contexts", "message"]) {
      expect(event[key]).toBeUndefined();
    }
  });
});

describe("the one door", () => {
  it("nothing but lib/monitoring.ts imports @sentry/*", () => {
    const root = path.resolve(__dirname, "..");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        if (["node_modules", ".next", "e2e", "public", "test-results"].includes(name)) continue;
        const full = path.join(dir, name);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.(ts|tsx|mjs)$/.test(name) && !/\.test\.tsx?$/.test(name)) {
          const rel = path.relative(root, full);
          if (rel === path.join("lib", "monitoring.ts")) continue;
          if (/from\s+["']@sentry\/|import\(\s*["']@sentry\//.test(readFileSync(full, "utf-8"))) offenders.push(rel);
        }
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});
