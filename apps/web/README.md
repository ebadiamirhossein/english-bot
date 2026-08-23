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

**No `localStorage`, no `sessionStorage`, anywhere.** Enforced by
`tests/test_web_shell.py`. It is also why dark mode follows
`prefers-color-scheme` rather than a toggle: a toggle has to remember its
setting, and the only places to remember it are the two this app will not
use.

**The API client is typed.** `lib/api.ts` is hand-written while there is one
route; from W3 it is generated from the OpenAPI schema `apps/api/schemas`
produces, so a renamed field is a TypeScript error rather than `undefined` on
a phone.

**The health check runs in the browser, not on the server.** A server
component would reach the API over loopback and prove nothing about CORS —
which is the part that breaks on a phone (W0 risk R4).

## PWA

`app/manifest.ts` is served at `/manifest.webmanifest` and linked from every
page. The service worker is generated into `public/` at build time and is
disabled in development, so a cached shell never hides an edit.

Installing to an iPhone home screen: open the site in Safari → Share → Add to
Home Screen. That is a W1b human check.
