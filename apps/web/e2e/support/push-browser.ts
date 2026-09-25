import type { Page } from "@playwright/test";

import { pushFixture } from "./api";

/**
 * W20 — the browser's half of Web Push, stubbed before any page script runs.
 *
 * **Why a stub and not the real thing:** the harness blocks service workers
 * (`playwright.config.ts`) so none can answer a request the routes should, and
 * with no worker there is no `PushManager` subscription to be had. A real
 * subscription would also need a real push service — a network call this
 * harness never makes. So `navigator.serviceWorker`, `PushManager` and
 * `Notification` are replaced with the few members `components/push/
 * reminders.tsx` reads, and the subscription they hand over is the fixture's,
 * which `PushSubscriptionIn` validated (#190).
 *
 * **WHAT THIS CANNOT SHOW:** that a phone's browser grants permission, that iOS
 * delivers a push to a Home Screen app, or that a tap on the notification opens
 * the session. Those are the operator's phone check, and a green run here is
 * not evidence for any of them.
 */
export type PushBrowser = {
  /** `Notification.permission` when the page loads. */
  permission?: "default" | "granted" | "denied";
  /** What the permission prompt answers when asked. */
  answer?: "default" | "granted" | "denied";
  /** A subscription already exists in this browser. */
  subscribed?: boolean;
  /** `PushManager` exists (false: iOS Safari in a tab, or an engine without push). */
  push?: boolean;
  /** Report an iPhone's Safari user agent. */
  iphone?: boolean;
  /** `navigator.standalone`: opened from the Home Screen. */
  standalone?: boolean;
};

export async function stubPushBrowser(page: Page, options: PushBrowser = {}) {
  await page.addInitScript(
    ({ cfg, subscription }) => {
      const sub = {
        endpoint: subscription.endpoint,
        expirationTime: null,
        options: { userVisibleOnly: true, applicationServerKey: null },
        toJSON: () => subscription,
        unsubscribe: async () => {
          current = null;
          return true;
        },
      };
      let current: typeof sub | null = cfg.subscribed ? sub : null;
      const w = window as unknown as Record<string, unknown>;
      w.__pushSubscribeOptions = null;
      const pushManager = {
        getSubscription: async () => current,
        subscribe: async (opts: { userVisibleOnly: boolean; applicationServerKey: unknown }) => {
          w.__pushSubscribeOptions = {
            userVisibleOnly: opts.userVisibleOnly,
            applicationServerKey: opts.applicationServerKey,
          };
          current = sub;
          return sub;
        },
      };
      const noop = () => undefined;
      const registration = {
        scope: `${location.origin}/`,
        active: null,
        installing: null,
        waiting: null,
        pushManager,
        addEventListener: noop,
        removeEventListener: noop,
        update: async () => undefined,
        unregister: async () => true,
      };
      const container = {
        controller: null,
        ready: Promise.resolve(registration),
        register: async () => registration,
        getRegistration: async () => registration,
        getRegistrations: async () => [registration],
        addEventListener: noop,
        removeEventListener: noop,
        startMessages: noop,
      };
      Object.defineProperty(Navigator.prototype, "serviceWorker", {
        configurable: true,
        get: () => container,
      });

      let permission = cfg.permission;
      w.Notification = {
        get permission() {
          return permission;
        },
        requestPermission: async () => {
          permission = cfg.answer;
          return permission;
        },
      };
      if (cfg.push) w.PushManager = function PushManager() {};
      else delete w.PushManager;

      if (cfg.iphone) {
        Object.defineProperty(Navigator.prototype, "userAgent", {
          configurable: true,
          get: () =>
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
        });
      }
      Object.defineProperty(Navigator.prototype, "standalone", {
        configurable: true,
        get: () => cfg.standalone,
      });
    },
    {
      cfg: {
        permission: options.permission ?? "default",
        answer: options.answer ?? "granted",
        subscribed: options.subscribed ?? false,
        push: options.push ?? true,
        iphone: options.iphone ?? false,
        standalone: options.standalone ?? false,
      },
      subscription: pushFixture.subscription,
    },
  );
}
