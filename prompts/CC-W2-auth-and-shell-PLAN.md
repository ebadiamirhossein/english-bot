# Claude Code — W2 · Auth + shell

**Run in: PLAN MODE. Do not write, move, edit or delete a single file in this slice — including `BUILD_PROGRESS.md`.**
**Scope of the plan: passkey authentication implemented in FastAPI, migration 009, the app shell behind a session, and the first public surface this project has ever had — `app.foundgrant.com` and `api.foundgrant.com`.**

`docs/TASKS-v3-web.md` marks W2 as AGENT. That was written before the domain was chosen. **It is being run as PLAN, deliberately:** this slice runs the first migration against the live error journal, adds DNS records, terminates TLS, and exposes an HTTP surface to the internet. None of that is additive or self-contained. The plan is reviewed before any code is written.

Read `CLAUDE.md` first, then `docs/PRD-v3-web.md`, `docs/ARCHITECTURE-v3-web.md`, `docs/TASKS-v3-web.md`, then `BUILD_PROGRESS.md` for the current state and the known-issues table.

---

## Decisions already made — do not re-open these

These were settled before this prompt was written. Plan against them; do not propose alternatives.

**1. Better Auth is not being used. Auth is implemented in FastAPI, in Python.**

`docs/ARCHITECTURE-v3-web.md` §2 names Better Auth. Better Auth is a TypeScript library: it runs inside Next.js route handlers and needs a **direct Postgres connection**. `apps/web` deploys to Vercel; PostgreSQL binds `127.0.0.1` on Hetzner. The three ways out were all rejected:

- Exposing Postgres to Vercel puts the error journal's database on the public internet to solve a login problem, and Vercel's egress addresses are not static, so the allow-list would be weak.
- Running Better Auth as a Node service on the Hetzner box keeps the database private but adds a third process and a second language, and a process whose only job is auth is close enough to `CLAUDE.md` §2's permanent ban on microservices to be worth avoiding.
- Clerk is ARCHITECTURE's own named fallback, but it reintroduces the vendor the choice existed to avoid.

Implementing it in FastAPI adds no process, no vendor and no exposed port, and keeps `route → service → SQL` as the single spine. **Record this in the plan as a deliberate departure from ARCHITECTURE §2, and say plainly in the update block that §2's auth row is now wrong.** Do not quietly leave the document contradicting the code.

**2. Passkey only. No magic link, no email sender, in this slice.**

No Resend/Postmark/SES account, no DKIM records, no SPF edit. The domain carries imported Namecheap email-forwarding MX records and an SPF TXT record that **must not be broken**, and an SPF merge does not belong inside an auth slice. Magic link gets its own slice later, and the schema you design must accommodate it arriving then without a second migration to `users`.

**Consequence you must plan around honestly: `auth_email` is an unverified identifier, not a verified channel.** There is no way to prove someone owns the address in this slice. That is exactly why the claim step in Part 3 exists.

**3. Account binding.** `users.telegram_user_id` is the primary key and every table's foreign key hangs off it. It is not re-keyed. Migration 009 adds `auth_user_id`, `auth_email` and `l1_pronunciation_seed` to `users`. **The human runs the two `UPDATE` statements** that set `auth_email` on the two existing rows — no email address appears in this repo, in this plan, or in any test fixture. First successful registration with a matching address links `auth_user_id`. An address with no matching row gets no session and no account.

**4. `api.foundgrant.com` is DNS-only on Cloudflare (grey cloud).** Caddy obtains and renews its own certificate over HTTP-01. A proxied record would need Full (strict) and a second TLS hop for no benefit here.

**5. W1c does not block this slice.** Its substance — a restore drill run against the production database — passed, and that is what closed issue #6. What remains unrun is the unattended 04:00 UTC cron, which is a scheduling fact rather than a data-integrity one. **W1c stays 🟡 and only the human marks it ✅.**

---

## Constraints on the plan itself

- **Read-only.** No file is created, edited, moved or deleted, including `BUILD_PROGRESS.md`. Produce the update block as *text inside the plan*; the approval prompt will instruct you to apply it.
- **`CLAUDE.md` §5b binds.** No acceptance step in the resulting slice may start a Telegram polling loop against the real token, or run any entrypoint that talks to a live service on a learner's behalf.
- **No ORM, no Alembic, no Redis, no queue.** Migrations are numbered `.sql` files plus a `schema_version` row.
- **`packages/core` may not import FastAPI.** If auth logic needs to live in a service function, it lives in `packages/core/services/` and takes no HTTP types. Say which parts go where.
- If any part of this plan turns out to need something outside W2, **name it and stop** rather than widening. `CLAUDE.md` §8.

---

## What to produce

A single plan document with the sections below. No code files — illustrative SQL and function signatures inside the plan are expected and wanted.

### 1. The auth design, end to end

Name the library (`webauthn` / py_webauthn is the obvious candidate — say if you disagree and why) and pin the parameters that are easy to get subtly wrong:

- **Relying Party ID must be `foundgrant.com`, not `app.foundgrant.com`**, so a credential registered today still works if a second subdomain ever needs it. The expected **origin** on assertion is `https://app.foundgrant.com`. State both explicitly; an RP ID scoped to the subdomain is a decision that cannot be reversed without every learner re-enrolling.
- **Discoverable credentials (resident keys) required**, so sign-in needs no typed identifier — the browser offers the passkey and the assertion carries the user handle. The user handle must be a stable opaque value, **not** `telegram_user_id` and not the email.
- **Multiple passkeys per user.** Two learners, each with a phone and a laptop. A one-credential-per-user schema is wrong on day one.
- **Sign-count regression** must be checked and must be a hard failure, not a warning.
- Registration and authentication challenges: where they are stored, their lifetime, and how they are invalidated after one use.

Walk both ceremonies as a numbered sequence — begin-registration, finish-registration, begin-authentication, finish-authentication — naming what crosses the wire and what is written to which table at each step.

### 2. Migration 009 — and a scope conflict you must resolve in the plan, not in the code

`docs/TASKS-v3-web.md` §Migration numbering says 009 is `users` auth columns plus the view recreate. **That table was written when the auth backend was Better Auth, which would have created its own tables.** Passkeys in FastAPI need at least a credentials table and a session table, and probably a claim-token table. The authoritative numbering table and the actual requirement now disagree.

Resolve it in the plan: propose the full contents of 009, and propose the exact edit to `docs/TASKS-v3-web.md` that brings the numbering table back into agreement. **Do not silently ship a wider migration than the table describes** — that table exists because a slice reading only its own row once wrote the wrong number (issue #49).

Specify:

- The three `users` columns, with types, nullability and uniqueness. `auth_user_id` and `auth_email` are both `UNIQUE` and both nullable — a row with neither is a Telegram-era user who has not enrolled. `l1_pronunciation_seed` is added now and unused until W14; say what shape you expect it to hold and why it is being added early rather than in 017.
- **The `approved_onboarded_users` view recreated in the same file.** This is the standing rule from issue #48: every `ALTER TABLE users` is paired with a view recreate in the same `.sql`. State how the acceptance test proves the view's column set equals the table's, rather than asserting a hand-written list that drifts.
- The new tables. **Namespace them.** A table called `sessions` already exists and holds *learning* sessions; an auth table called `session` next to it is a trap. Propose names and say so.
- Whether anything in 009 is destructive or irreversible, and what the rollback is.

### 3. The claim problem — the part most likely to be got wrong

With no email channel, a pre-seeded `auth_email` alone is not an authentication factor. If registration only requires typing an address that exists, **whoever types it first owns the account**, including the error journal behind it.

Design the first-enrolment gate and justify it:

- A one-time claim token, generated by the operator through a CLI in `packages/core` or a script, handed over out of band, single-use, short-lived, stored hashed.
- Registration requires a matching `auth_email` **and** a valid unused claim token **and** `auth_user_id IS NULL`.
- Adding a *second* passkey to an already-enrolled account is a different path — it should require an existing authenticated session, not a claim token.

Then design **recovery**, and put it in `docs/DEPLOYMENT.md`: passkey-only means a lost device is a lockout, and there is no email reset in this slice. The operator-side path — clear `auth_user_id`, issue a fresh claim token, re-enrol — must be written down as a runbook procedure with the exact SQL, because the moment it is needed is the moment nobody wants to be reasoning it out from first principles.

### 4. Session, cookie and CORS across two origins

`app.foundgrant.com` and `api.foundgrant.com` are different **origins** but the same **site**. Get the consequences right and state them:

- Cookie attributes in full — domain, `Secure`, `HttpOnly`, `SameSite`, path, max-age. 30-day persistence is the acceptance criterion; say whether the cookie is sliding or absolute and why.
- The session token is stored **hashed** server-side; the raw value exists only in the cookie. Say which hash.
- The browser must send credentials, so the fetch client needs `credentials: 'include'` and CORS needs `allow_credentials=True` with the two explicit origins. **`allow_credentials` with a wildcard origin is rejected by browsers outright** — W1b already locked CORS to a list and there is a test asserting no wildcard; confirm it still holds.
- Logout, and session invalidation on the server rather than only clearing the cookie.
- Rate limiting on the auth routes. Two users, one public surface, no email verification — say what the limit is and where it is enforced.

### 5. API surface

The routes W2 adds, with request and response shapes. `GET /health/auth` already exists as a stub returning `null`; W2 makes it real. Every route that resolves a session goes through one dependency in `apps/api/deps.py` — `get_current_user`, currently stubbed — and **no route re-implements session lookup**.

State which routes are plain `def` and which are `async def`, and why. The standing rule is that any route touching `llm.py` or `speech.py` is a plain `def` (issue #7 with a wider blast radius); none of W2's routes should touch either, so say what the rule implies here.

### 6. `apps/web` — sign-in, protection, and the shell

- The sign-in screen and the enrolment screen. Read `/mnt/skills/public/frontend-design/SKILL.md` before proposing any component; W1b set a visual direction and `apps/web/README.md` records it — this must not look like a second, unrelated app.
- **How unauthenticated routes redirect.** Say whether this is middleware, a server component check, or a client guard, and what the flash-of-protected-content behaviour is in each case.
- **PWA home-screen install on iPhone — this was deferred from W1b to here explicitly** and is a W2 acceptance criterion. `next-pwa` disables service workers in dev and a service worker needs a secure context, which is why a LAN IP over plain `http` could not register one. `app.foundgrant.com` gives it HTTPS. Say what has to be true for the install to work, and what to check when it does not.
- **Dark mode, and a light/dark toggle.** The `localStorage` ban is lifted **for theme preference only** — that was decided at W1c and this is the slice that lands it. Everything else — session state, learner content, progress — stays server-side. There is an existing test asserting no browser storage anywhere in `apps/web`; say exactly how it is narrowed so it still catches a real violation instead of being deleted.
- Session behaviour inside an installed PWA: iOS treats a home-screen app as a separate storage context. If a 30-day session in the browser does not mean a 30-day session in the installed app, say so now rather than discovering it after install.

### 7. Infrastructure — DNS, Caddy, Vercel, systemd

- The two Cloudflare records, with `api.` grey-cloud and the reason. **The imported Namecheap email-forwarding MX records and the SPF TXT record must not be deleted or modified.**
- The Caddy site block for `api.foundgrant.com` reverse-proxying to `127.0.0.1:8000`. Caddy is shared with `fonderis-worker` and already holds 80/443 — say how the config is added without disturbing the existing service, and how it is rolled back.
- **Installing `english-api.service`.** It is already written at `deploy/systemd/english-api.service` and was deliberately left uninstalled at W1c because it served no routes. It serves routes now.
- **`english-worker` stays uninstalled.** Issue **#69** — its job table overlaps the bot's on `streak_rollover`, `monthly_freeze_reset`, `heartbeat` and `backup_freshness`, and two processes through `streak_rollover` against one database is a data-integrity problem. Do not install it, do not fix the overlap here. (Note for accuracy: **#66** is the smaller, separate issue that `monthly_reset` and `monthly_freeze_reset` are two names for overlapping work.)
- Whether uvicorn runs multiple workers, and what that implies for anything held in process memory — challenges in particular.

### 8. The deploy sequence, with the pre-migration backup made explicit

The settled sequence is **backup → pull → `pip install -e packages/core` → migrate → restart** (`CLAUDE.md` §5, not to be re-argued).

**W2 is the first slice to run a migration against the live error journal.** The backup step is therefore not a formality and must not rely on the 04:00 cron having fired — that cron has never yet run unattended. Write the sequence so the operator, immediately before `migrate`:

1. runs `scripts/backup.sh` by hand,
2. confirms the resulting object exists in R2 by listing the bucket,
3. and only then migrates.

**Note the trap from issue #73:** R2 has a list-after-write consistency lag. An object uploaded moments ago may not appear in `list-objects-v2` immediately. The confirmation step must tolerate that — list again after a short wait rather than treating a first empty listing as a failed upload — and the runbook must say so, because the alternative is an operator concluding the backup failed and either re-running it or, worse, migrating anyway.

### 9. Test plan

Every route that resolves a session or writes to `users` needs an **integration test through the ASGI transport**, not a direct service call. That is the direct descendant of v2's most expensive failure: 161 tests passed while the main feature was dead because every test called handlers directly.

State how you test:

- A full registration and a full authentication ceremony without a real authenticator. Name the approach — a software authenticator, or fixture attestation and assertion blobs.
- Rejection paths, each individually: unknown email, matching email with no claim token, used claim token, expired claim token, already-enrolled account, sign-count regression, tampered assertion, expired session, session for a revoked user.
- **The view's column set equals the table's**, computed from `information_schema` rather than a hand-written list.
- The cookie's attributes as actually set on the response.
- CORS: allowed origin, refused origin, preflight, credentials, and still no wildcard.

Three `CLAUDE.md` §3 rules bite here and should be addressed by name in the plan: **rule 5** — no test derives its expected value from the function under test (a session test that asks the session module what the expiry should be proves nothing); **rule 6** — no test depends on wall-clock date, and expiry tests are exactly where that creeps in; **rule 4** — if you cannot state which user action a test exercises, it is decoration.

Give the expected test count delta against the current 828.

### 10. Risks

Ranked. For each: what breaks, how it is detected, and the cheapest guard. Include at minimum:

- Migration 009 against the live journal.
- Account takeover during the enrolment window, before both learners have claimed.
- Lockout with no recovery path.
- The cookie failing across the two origins — the failure mode that is invisible on `localhost` and only appears on a phone.
- Caddy misconfiguration taking down `fonderis-worker`, which is a **separate production service on the same host**.
- Certificate issuance failing, and what the DNS-only choice means if it does.

### 11. Open questions for the human

Short and specific. Do not pad it with anything the docs or this prompt already answer.

---

## Out of scope

- **No `/correct` route, no correction port** — that is W3.
- No lexicon, no items, no cards, no FSRS, no session runner.
- No magic link, no email provider, no DKIM, no SPF edit.
- **No changes to any file under `packages/core/services/`** except what auth genuinely requires, and if it requires any, say which and why before touching them.
- No prompt edits. **Known issue #45** — the single-language rule missing from five prompt templates — belongs to W3, which closes it with one shared constant.
- **Do not install `english-worker`** and do not fix issue #69.
- **Do not fix issue #60** (`core.services.access_control` importing from `apps.bot`, inverting the dependency direction). Still open, still belongs to the slice that deliberately widens the boundary test.
- **Do not fix issue #73** (R2 list-after-write lag). The runbook works around it; the code fix is a later slice.
- No deletion of anything under `apps/bot`. The bot is still the only thing the learners have.

---

## BUILD_PROGRESS.md update block

Produce this as **text inside the plan**. Do not edit the file — this slice is read-only, and the approval prompt will instruct you to apply it.

- **Slice row:** `| W2 | Auth + shell | 🟡 plan produced | <date> | PLAN mode; passkey auth in FastAPI, migration 009; no code written |`

- **Decisions log — one row each, with the reason, not just the decision:**
  - Better Auth rejected; auth implemented in FastAPI. Reason: Better Auth is TypeScript and Postgres-backed, `apps/web` is on Vercel, and PostgreSQL binds `127.0.0.1` — the three ways to bridge that were exposing the journal's database to the internet, adding a Node process against `CLAUDE.md` §2, or taking the vendor ARCHITECTURE chose Better Auth to avoid. **Record that `docs/ARCHITECTURE-v3-web.md` §2's auth row is now wrong and name the edit that fixes it.**
  - Passkey-only for W2; magic link deferred to its own slice. Reason: no email sender exists, and an SPF merge that risks the domain's existing Namecheap forwarding does not belong inside an auth slice.
  - `auth_email` is an unverified identifier, not a verified channel — and the claim-token gate is what stands in for verification.
  - RP ID `foundgrant.com` rather than `app.foundgrant.com`, with the re-enrolment cost of getting it wrong.
  - Account binding by operator-set `auth_email`; no self-serve claim flow; no email address in the repo.
  - `api.` grey-cloud on Cloudflare so Caddy owns its own certificate.
  - W2 run as PLAN against `docs/TASKS-v3-web.md`'s AGENT marking, with the reason: first migration against live data, first public surface, DNS and TLS.
  - The `localStorage` ban narrowed to permit theme preference only, and how the test was narrowed rather than deleted.
  - Whatever the plan resolves about migration 009's contents versus the numbering table.

- **Known issues:** anything new, with severity and slice. Carry forward every still-open issue — the current set is listed under *Still open after W1c* in `BUILD_PROGRESS.md` and includes **#69** (worker job-table overlap, still blocking the worker install), **#65** (`apps/api` has no operator alert channel — W2 is the slice that makes this bite, because the API is about to serve real traffic), **#73** (R2 list-after-write lag), **#64**, **#67** (no JS test runner in `apps/web` — W2 adds a sign-in screen with real logic and no way to render-test it; say whether that changes the recommendation to wait for W6), **#44**, **#45**, **#48**. Do not reopen anything in the *Closed and not to be reopened* list.

- **File inventory:** no new files this slice — it is a plan. List the files the *implementation* slice will create or change, so the review has something concrete to argue with.

- **Next action.** Rewrite it as W2's human checks **plus every earlier check still unrun**, carried forward explicitly and never silently:
  - **W2's own checks** (for the implementation slice, not the plan): installed to the iPhone home screen over HTTPS; a passkey enrolled and a sign-in completed on the phone; the session surviving 30 days, or at least surviving an app restart and a device reboot; an unauthenticated route redirecting; the view's column set matching; **CORS verified from the phone, not from `localhost`**.
  - **W1c's two remaining checks:** the first *unattended* 04:00 UTC cron dump landing in R2, and `/ping` + `/stats` answering in Telegram on the restructured bot. Carry the #73 caveat with them — do not trust an `empty` verdict within minutes of an upload.
  - **The v2 deploy backlog:** the S25 pre-flight counts to be filled into the decisions log from production (total / stay_null slang / become_presented; confirm `non_slang_delivered = 0`), and **#44**, which stays open until a real Mon/Wed/Fri evening reading lands — no deploy and no infrastructure slice can prove it.
  - **#57:** the §6b work-vocabulary SQL and the quiz-scenario frequency query, to run on Hetzner before W5 rewrites the prompts.
  - **S8:** create the shared group, add the bot, run `/here`, set `COUPLE_CHAT_ID`, restart, then the seven S8 group checks.
  - **The entire v2 desk-check list, unchanged** — S26c, S26b, S26a/S26, S25, S24/S24a/S24b, S18d, S18c/S18b/S18a, and the full carried-forward set in the Verification checklist. W2 is auth and infrastructure; it exercises no learner path and clears none of them.
  - **The W0 decision still unanswered:** whether the four prompts missing the single-language rule (#45) are fixed during the W3 port or in their own slice. The migration-numbering question is now answered — 009 is W2's, and this plan proposes its contents.

---

Produce the plan, then **stop**. Write no code, edit no files, and do not begin implementing W2.
