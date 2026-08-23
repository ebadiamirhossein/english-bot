# `apps/web` — the PWA shell

Next.js 15 (App Router) · TypeScript · Tailwind v4 · shadcn/ui ·
`@ducanh2912/next-pwa`.

At W1b this is a shell: four screens, none of which do anything yet, and one
status line proving the browser can reach the API.

```bash
pnpm install
pnpm dev            # http://localhost:3000
```

The API has to be running for the status line on Today to turn green:

```bash
uvicorn apps.api.main:app --port 8000
```

Copy `.env.example` to `.env.local` if the API is not on
`http://localhost:8000`.

## The direction this shell sets

**One screen matters.** Home is a single button. Everything else in the
product — the map, the deck, the ledgers — is somewhere you go to *look at*
what that button produced (PRD §4). Any screen added later has to earn its
place against that.

**A phone, held in one hand.** `max-w-lg` even on a desktop: both learners
use a phone, and a layout that reflows into three columns is a second design
to maintain for a screen nobody opens. Nav targets are 64px tall.

**Warm, not corporate.** Paper-white and ink in daylight, deep teal-slate
after dark, with one teal accent doing all the signalling. Headings are set
in Fraunces, body in Geist: a language app that looks like an admin dashboard
reads like homework.

**Nothing in the palette is red.** "Never guilt" (CLAUDE.md §4) is easier to
hold to when the colour for failure does not exist in the theme.

**Placeholders name their slice.** Every empty screen says what will live
there and which slice brings it, so the shell is readable next to
`docs/TASKS-v3-web.md` instead of saying "coming soon" four times.

## Rules this app is held to

**No browser storage, with exactly one exception.** `sessionStorage` is banned
outright, everywhere. `localStorage` may be used in **`lib/theme.ts` only**, and
only under the key `"theme"` — the colour scheme is a property of the device
rather than of the learner. Session, progress and learner content stay
server-side (CLAUDE.md §5).

`tests/test_web_shell.py` enforces the narrowing as an allow-list of one path
and one key, with a meta-test that feeds it deliberate violations and requires
them to fail. That is also why the theme provider is ~35 hand-written lines
rather than `next-themes`: a dependency would put the one permitted write inside
`node_modules`, where the check cannot see it, and the exception would be
unbounded in practice.

Dark mode is therefore driven by a `dark` class on `<html>`, not by
`prefers-color-scheme` directly. The blocking inline script in `app/layout.tsx`
maps the three states (`light` / `dark` / `system`) onto that class before first
paint. Leaving the media query in as well is what produces a toggle that
visibly does nothing.

**The API client is typed.** `lib/api.ts` is hand-written while there is one
route; from W3 it is generated from the OpenAPI schema `apps/api/schemas`
produces, so a renamed field is a TypeScript error rather than `undefined` on
a phone.

**The health check runs in the browser, not on the server.** A server
component would reach the API over loopback and prove nothing about CORS —
which is the part that breaks on a phone (W0 risk R4).

## Auth (W2)

Passkeys, verified by `apps/api`. Two screens under `app/(auth)/`: `/sign-in`
(one button — the credential is discoverable, so no identifier is typed) and
`/enrol` (address + one-time code, the code standing in for the email
verification this slice has no sender for).

**`lib/webauthn.ts` contains no base64url encoder, deliberately.** It uses the
native `PublicKeyCredential.parseCreationOptionsFromJSON()` /
`parseRequestOptionsFromJSON()` / `credential.toJSON()` bridge, which speaks
exactly the JSON `py_webauthn` emits. Hand-rolled binary conversion is the one
piece of frontend logic here whose failure is silent: a mangled challenge
surfaces as `NotAllowedError`, which is also what the browser throws when the
learner cancels, so a bug looks exactly like someone changing their mind. A test
fails the commit that reintroduces `atob`/`Uint8Array` in that file.

**Route protection is a client guard, not middleware.** The session cookie is
host-only on `api.foundgrant.com`, so the Vercel edge never receives it and
middleware cannot read it. `components/require-session.tsx` renders a neutral
splash while it asks `/health/auth`, then either renders the page or redirects
to `/sign-in`. The guard is UX; the API is the enforcement point — every data
route requires the session server-side.

**Preview deployments cannot sign in, and that is expected.** A `*.vercel.app`
origin is cross-*site* to `api.foundgrant.com`, so the `SameSite=Lax` session
cookie is not sent, and the origin is not in `WEB_ORIGIN` either. Previews render
the shell and stop at the sign-in screen. Do not "fix" this by loosening
`SameSite` or widening CORS.

## PWA

`app/manifest.ts` is served at `/manifest.webmanifest` and linked from every
page. The service worker is generated into `public/` at build time and is
disabled in development, so a cached shell never hides an edit.

**The two learners are on different platforms, and installing differs.**

| | iPhone (Safari) | Android (Chrome) |
|---|---|---|
| Install | Share → Add to Home Screen | the install prompt, or ⋮ → Add to Home screen |
| Service worker | not required to install | **required** for a real installed app (a WebAPK) rather than a bookmark shortcut |
| Cookie store | **separate from the browser** | shared with Chrome |
| Passkey lives in | iCloud Keychain | Google Password Manager |

Two consequences worth knowing before anyone tests this:

* **On iPhone, signing in in Safari does not sign you in inside the installed
  app** — an installed web app has its own cookie store. The learner signs in
  once more inside it, which is one Face ID prompt because the passkey itself is
  shared through iCloud Keychain. Install first, then sign in. **On Android the
  installed app shares Chrome's cookies, so it is already signed in.**
* The service worker is load-bearing on Android in a way it is not on iOS. It is
  generated by `@ducanh2912/next-pwa` in production builds only, which is why the
  install check has to be done against a deployed build and never `pnpm dev`.

The session cookie is `HttpOnly` and server-set from a first-party same-site
context, so it is **not** subject to WebKit's seven-day cap on script-writable
storage — 30 days in the installed app is a real 30 days. The theme preference
*is* script-writable and can be evicted on iOS after seven days without a visit;
it falls back to following the system, which is harmless. Android Chrome has no
equivalent eviction.
