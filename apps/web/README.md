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

## Items (W6)

The eleven item types, under `components/items/`.

**Presentation is per type. Answering is per response mode.** The W6 task row
asks for one component per item type; the W5 contract says render from
`core.items.RESPONSE_MODE` and never from an eleven-way switch. Both hold —
eleven presentation components over three answer components:

```
components/items/
  item-card.tsx              shell — branches on response_mode ONLY
  presentation/index.ts      THE type → component map (the only enumeration)
  presentation/*.tsx         eleven, one per type
  answer/index.ts            THE response_mode → component map (three entries)
  answer/{tap,typed,spoken}-answer.tsx
  feedback.tsx  explanation.tsx  audio-button.tsx
```

**The rule a reviewer applies:** only `presentation/index.ts` and the eleven
files it points at may name an item type. Nothing under `answer/`, and not
`item-card.tsx`, `feedback.tsx`, `explanation.tsx` or `lib/items.ts`.
`tests/test_web_shell.py::test_only_the_presentation_map_branches_on_item_type`
reads `core.items.ITEM_TYPES` out of Python and fails the commit that breaks it.

`response_mode` arrives on the wire, so this app holds **no copy** of
`RESPONSE_MODE`. A mirrored table is a table that drifts.

**All grading is server-side, and nothing here compares an answer.** There is no
fold, no casefold, no punctuation stripping, and nothing to compare against —
the projection carries no answer. "Instant feedback" is one network round trip.
An optimistic client-side check would be a second definition of "the answer",
and `core/items/grading.py`'s fold is shared with the item uniqueness gate, so a
copy of it here could accept a string the gate rejected or reject one it
accepted, and the learner would see a coin flip. That is the bug the v3 rebuild
exists to end.

**The phone keyboard is a second grader.** Every typed input carries
`autoCapitalize="off"`, `autoCorrect="off"`, `autoComplete="off"`,
`spellCheck={false}` and a ≥16px font. Autocorrect repairing a learner's
spelling before the server sees it is a teaching bug, not a cosmetic one — the
criterion "typed items never require punctuation or capitalisation to match" is
about the server's fold being permissive, not about iOS fixing the answer first.
The 16px is separate: below it, Safari zooms the viewport on focus.

**The eleven render from a committed fixture.**
`lib/items/projections.fixture.json` is generated by Python through the real
`visible_projection`, so the seam fails in both directions: a renderer reading a
field the projection does not carry fails in Vitest, and a projection change
that is not re-exported fails in `tests/test_items_web_contract.py`. A third
test compares the fixture against a real ASGI response body, so it describes the
wire rather than a function. Regenerate with:

```bash
python scripts/export_item_projections.py
```

**Two types are answered by an instrument that is not scoring.** `speak_repeat`
and `speak_answer` are self-marked, writing `item_attempts.graded_by = 'self'`.
No microphone is opened and no audio exists. Pronunciation scoring is W14
(migration 018). `dictation`, `listening_gap` and `speak_repeat` fetch audio
from `GET /items/{id}/audio` **on tap, never on load**.

## Tests

Two suites, and both have to be run:

```bash
pytest -q
```

```bash
cd apps/web && pnpm test
```

Vitest (`vitest.config.ts`, jsdom) covers what a source scan cannot: rendering
each of the eleven, tapping, the typed-input path, and the feedback state
machine — in particular that **no verdict appears while the request is in
flight**. The Python suite keeps the structural checks: no browser storage, no
answer comparison in TypeScript, no type branching outside the one map, the
no-guilt scan over every `.tsx`, and no red anywhere.

`tests/test_web_shell.py::test_every_item_type_has_a_render_test` requires a
Vitest test naming each of `core.items.ITEM_TYPES`, so a twelfth type fails the
Python suite until somebody renders it. A file count would not do that.

## Environment

`NEXT_PUBLIC_API_URL` is **required for a production build**, and the build
fails without it (`prebuild` → `scripts/check-env.mjs`). That closes known issue
#80: an *unset* variable took the localhost fallback but an **empty** one did
not, so every request went to a relative path the deployment does not serve and
the error read "Could not reach the API at ." — indistinguishable from the API
being down. Vercel lets you save an empty string, so it was reachable.

`lib/env.ts` stays a pure read with no throw, deliberately: a module-load throw
fails the build only if that module is evaluated during prerender, and evaluated
first in the browser it white-screens a phone instead — a worse failure than the
one being fixed.

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
