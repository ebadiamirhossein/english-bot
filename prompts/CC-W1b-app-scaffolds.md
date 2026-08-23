# Claude Code — W1b · App scaffolds

**Run in: AGENT MODE.**
**Scope: create four empty-but-running application shells, and repair two tests. No business logic, no routes with behaviour, no migration.**

W1 is done: `packages/core` is the installed package `core`, 721 passing / 1 pre-existing failure, `app/` is gone. This slice gives the API, the worker and the web app a place to exist. It is deliberately boring.

---

## Before anything: read the updated `CLAUDE.md`

Two sections changed after W1 and both bind this slice:

- **§5b — never run a production entrypoint during a slice.** No acceptance check in W1b may start a Telegram polling loop against the real token. Use a dummy token in a temp `.env`, or stub the polling call. Verify the lock, the config load and the handler registration — never the network loop.
- **§3 rules 5–7** — a test may not derive its expected value from the function under test, may not depend on wall-clock date, and the acceptance bar is never quietly lowered.

---

## Part 1 — two test repairs (do these first)

The suite should be green with **zero failures** for the first time when this slice ends.

1. **`tests/test_vocab_import.py::test_vocabulary_due_and_anki`** — failing since 2026-08-14 because `insert_chunks` writes `next_review = CURRENT_DATE + 1` while the test asks for due items at a hardcoded `2026-08-15`. Fix by computing both sides the same way (query at `CURRENT_DATE + 1`, or freeze the date for the whole test). Do not change `insert_chunks`.

2. **The `assert_path_outside_repo` test (#63)** — it computes its "inside the repo" fixture from `repo_root()`, the same function that was silently broken by the W1 move, so it stayed green against a broken guard. Rewrite it to assert against a **hardcoded relative path** (e.g. `<repo>/scripts/x.sql` must be rejected, `/tmp/x.sql` must be accepted) with no call to `repo_root()` in the test body. Add one case that would have caught the `parents[2]` bug specifically: a path directly under the repo root but outside `packages/`.

---

## Part 2 — `apps/api`

FastAPI application, no domain routes.

```
apps/api/
├── main.py          # app factory, CORS, exception handler, Sentry hook (stubbed)
├── deps.py          # get_db, get_current_user (stub returning None for now)
├── routers/
│   └── health.py
└── schemas/
    └── __init__.py
```

**Routes, exactly two:**

- `GET /health` → `{"ok": true, "schema_version": <int>}` — reads the version through `core.db`, so a broken DB connection shows up here rather than in a user-facing route.
- `GET /health/auth` → the resolved session, or explicit `null`. It exists so a W2 auth failure is one `curl` away instead of a browser-console hunt (W0 risk R4).

**CORS** — locked to exactly `[settings.WEB_ORIGIN, "http://localhost:3000"]`. No `*`, no regex, no wildcard subdomain. `WEB_ORIGIN` comes from config; add the key to `.env.example` with a placeholder, since the domain is not chosen yet.

**Document the plain-`def` convention** in `apps/api/README.md` and enforce it with a test now, while there is nothing to break: any route function whose body references `llm.chat`, `speech.transcribe` or `speech.synthesize` must be a plain `def`, never `async def`. `llm.py` and `speech.py` are synchronous by design; a blocking call inside an `async def` route stalls the whole uvicorn worker (known issue #7, wider blast radius).

**Exception handling** — one handler that logs with the route name and the user id, returns a generic body to the client, and never leaks a stack trace. Reuse `core.services.alerts.format_alert` and `should_send_alert`; the `send` callable is a no-op stub in this slice.

---

## Part 3 — `apps/worker`

APScheduler process, no jobs with behaviour yet.

```
apps/worker/
├── main.py     # acquire instance lock, build scheduler, register jobs, start
└── jobs.py     # job table
```

- **Acquire `core.instance_lock` at boot**, before the scheduler starts. A second start must refuse and exit non-zero. This is the W0 risk R3 guard: the API may run multiple uvicorn workers, the scheduler must not.
- Register the jobs that already exist as pure predicates in `core.scheduling` — `streak_rollover`, `monthly_freeze_reset`, `monthly_reset`, `heartbeat`, `backup_freshness`. Leave the delivery jobs (morning, evening, nudge, Sunday, Anki) in `apps/bot` for now; they move at W20.
- **Keep the job-registration test from W1** and extend it to the worker: assert the worker's job table **by name and trigger**. Five v2 scheduler tests passed while asserting only predicates — they would pass against a worker that registers nothing.

**Boundary test to add:** `apps/api` must not import `apscheduler`, nor `core.scheduling`'s job-registration entrypoint. If the API imports the scheduler, every uvicorn worker runs every job.

---

## Part 4 — `apps/web`

Next.js 15, App Router, TypeScript, Tailwind, shadcn/ui. Installable PWA. **No real screens** — a shell only.

- App shell with bottom navigation: **Today · Map · Review · Progress**. Each is a placeholder page saying what will live there. Today's page shows a single disabled **Start today's session** button, because that is the shape the whole product resolves to (PRD §4).
- PWA: manifest, icons, service worker via `next-pwa`, installable to an iPhone home screen.
- Dark mode.
- `lib/api.ts` — a typed client hitting `/health`, generated or hand-written from the OpenAPI schema. It exists to prove the frontend can reach the backend.
- **No `localStorage`, no `sessionStorage`** anywhere.

**Design:** read `/mnt/skills/public/frontend-design/SKILL.md` before writing any component. This shell sets the visual direction for everything after it, so it should not look like a bootstrapped default.

---

## Part 5 — deployment notes

W1 changed the deploy sequence and the systemd unit. Update `docs/DEPLOYMENT.md`:

- New sequence: **backup → pull → `pip install -e packages/core` → migrate → restart**
- `ExecStart` for the bot unit becomes `python -m apps.bot.main`
- Add the two new units, `english-api` and `english-worker`, as **documented but not yet installed** — they are deployed at W1c, not now

Do not deploy anything in this slice.

---

## Acceptance

```bash
pytest -q                        # green, ZERO failures — first time
pytest tests/test_core_boundary.py
uvicorn apps.api.main:app &
curl localhost:8000/health       # {"ok": true, "schema_version": 8}
curl localhost:8000/health/auth  # null
cd apps/web && pnpm dev          # shell serves, 4 nav items, PWA manifest resolves
```

Worker: start it, confirm it holds the lock and registers its jobs; start a second instance, confirm it refuses. **Use a dummy token in a temp `.env`.**

---

## Out of scope

- No auth, no Better Auth, no `users` columns, no migration — that is W2
- No domain routes: no `/correct`, no `/session`, no `/review`
- No deletion of anything under `apps/bot`
- No prompt edits
- No changes to any file under `packages/core/services/`
- No production deploy

If something here looks like it needs a migration or a core service change, stop and say so.

---

## BUILD_PROGRESS.md update block

- **Slice row:** `| W1b | App scaffolds | 🟡 code-complete | <date> | api + worker + web shells; suite green with zero failures |`
- **Decisions log:** every decision with its reason, especially anything the prompt left open and any place the frontend design direction was chosen.
- **Known issues:** new ones with severity and slice. **Close #63** if the `assert_path_outside_repo` test repair lands. Carry forward every other open issue — #6 (still the top risk, and W1c is its fix), #20, #27, #28, #29, #31, #32, #44, #45, #46–#62.
- **File inventory:** every new file under `apps/api`, `apps/worker`, `apps/web`, plus the changed `docs/DEPLOYMENT.md`.
- **Next action:** W1b's human checks — open the web shell on a phone and install it to the home screen; `curl` both health routes; confirm the worker refuses a second start — **plus every earlier unrun check carried forward**, including the whole v2 desk-check list and the outstanding deploy backlog (S26c, migrations 007+008, S25 pre-flight counts, #44 evening-reading confirmation).

Then stop. Do not begin W1c.
