/**
 * W20 — the service worker's own code: show a reminder, and open the session
 * when it is tapped.
 *
 * **How it gets into the service worker.** `@ducanh2912/next-pwa` looks for
 * `worker/index.{ts,js}` (its `customWorkerSrc` default), builds it to
 * `public/worker-<hash>.js`, and puts that name first in the generated `sw.js`'s
 * `importScripts`. Nothing in `next.config.ts` names this file; its location is
 * the configuration.
 *
 * **What a push carries** is `core.services.push`'s message:
 * `{"title", "body", "url": "/session"}`. The copy is the server's
 * (`core/copy.py`, under the no-guilt scan); this file adds none of its own
 * beyond the app's name as a title of last resort.
 *
 * **Types are declared locally, and narrowly.** The app's `tsconfig` is DOM-only;
 * adding the `webworker` lib to it would redeclare half of the DOM for every
 * component. This file uses five members of the worker scope and says so.
 */

export {};

type ExtendableEventLike = Event & { waitUntil(promise: Promise<unknown>): void };
type PushEventLike = ExtendableEventLike & { data: { json(): unknown } | null };
type NotificationClickLike = ExtendableEventLike & { notification: Notification };
type WindowClientLike = {
  url: string;
  focus(): Promise<unknown>;
  navigate(url: string): Promise<unknown>;
};
type WorkerScope = {
  location: Location;
  registration: ServiceWorkerRegistration;
  clients: {
    matchAll(options: { type: "window"; includeUncontrolled: boolean }): Promise<WindowClientLike[]>;
    openWindow(url: string): Promise<unknown>;
  };
  addEventListener(type: "push", listener: (event: PushEventLike) => void): void;
  addEventListener(type: "notificationclick", listener: (event: NotificationClickLike) => void): void;
};

const sw = self as unknown as WorkerScope;

/** Where a tap lands when the message names nowhere usable. */
const SESSION = "/session";

/**
 * **Only a path on this origin is ever opened.** A payload is encrypted to this
 * browser and signed by our server, but a tap that could be steered to another
 * site is not a door worth leaving ajar: `//evil.example` and `/\evil.example`
 * both parse as another host, so the check is on the parsed origin, not on the
 * string's first character alone.
 */
function samePath(raw: unknown): string {
  if (typeof raw !== "string" || !raw.startsWith("/")) return SESSION;
  try {
    const url = new URL(raw, sw.location.origin);
    return url.origin === sw.location.origin ? url.pathname + url.search + url.hash : SESSION;
  } catch {
    return SESSION;
  }
}

sw.addEventListener("push", (event) => {
  let message: { title?: unknown; body?: unknown; url?: unknown } = {};
  try {
    message = (event.data?.json() ?? {}) as typeof message;
  } catch {
    // Not JSON. `userVisibleOnly` still obliges a notification, so one is shown.
  }
  const title = typeof message.title === "string" && message.title ? message.title : "English";
  const options: NotificationOptions & { renotify?: boolean } = {
    body: typeof message.body === "string" ? message.body : "",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url: samePath(message.url) },
    // **One notification at a time, never a pile** (CLAUDE.md §4): a nudge
    // REPLACES the morning's reminder on the lock screen rather than stacking
    // under it, and `renotify` lets the replacement still be noticed.
    tag: "daily-reminder",
    renotify: true,
  };
  event.waitUntil(sw.registration.showNotification(title, options));
});

sw.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data as { url?: unknown } | null;
  const target = new URL(samePath(data?.url), sw.location.origin).href;
  event.waitUntil(
    (async () => {
      // An app window already open is brought forward and moved to the
      // session; a second copy of the app is opened only when there is none.
      const windows = await sw.clients.matchAll({ type: "window", includeUncontrolled: true });
      const open = windows.find((client) => new URL(client.url).origin === sw.location.origin);
      if (open) {
        await open.focus();
        try {
          await open.navigate(target);
          return;
        } catch {
          // `navigate` refuses a window this worker does not control.
        }
      }
      await sw.clients.openWindow(target);
    })(),
  );
});
