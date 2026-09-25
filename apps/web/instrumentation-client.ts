/**
 * W23 — Next.js runs this file in the browser before the app hydrates
 * (Next 15.3+'s client instrumentation hook). It does one thing: hand over to
 * `lib/monitoring.ts`, the only file that knows Sentry exists.
 *
 * **No server-side init** (`instrumentation.ts`) and that is deliberate: every
 * page here is a static shell and every learner request goes browser → API,
 * because the session cookie never reaches Vercel (#74). The API's errors are
 * reported by the API; a server init would ship `@sentry/node` and
 * OpenTelemetry into Vercel's functions to watch code that handles no learner
 * data.
 */
import { startMonitoring } from "@/lib/monitoring";

void startMonitoring();
