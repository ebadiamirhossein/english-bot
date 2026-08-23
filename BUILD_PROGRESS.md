# BUILD PROGRESS

> **Cursor: you must update this file at the end of every slice, before finishing your turn.**
> **Human: upload this file to a new Claude chat to restore full context.**

**Project:** English Learning System — web app (PWA), 2 users, B1 → B2 in 6 months. Telegram is a notification channel, not the product.
**Repo:** `english-bot`
**Last updated:** 2026-08-23
**Current slice:** W1b
**Status:** **v2 is closed** — the Telegram bot build ended at S26c. The **v3 web rebuild** (`docs/TASKS-v3-web.md`) is at **W1b: code-complete, unverified on a phone and unverified on the server.** W1 restructured Python into `packages/core` + `apps/bot`; W1b adds the three application shells — `apps/api` (FastAPI, `/health` + `/health/auth`, CORS locked to two origins, one exception handler), `apps/worker` (APScheduler behind its own instance lock, five maintenance jobs) and `apps/web` (Next.js 15 PWA shell, four screens, installable). No domain routes, no auth, no migration. **771 tests, all passing, none skipped — zero failures for the first time in this build**: the two long-standing broken tests were repaired (#61 wall-clock dependency, #63 fixture derived from the function under test). Carried forward: production off-site backup (#6) still open and still the highest-ranked risk — **W1c is its fix and blocks W2**. **New and urgent: `.env.example` has carried a real-looking `ANTHROPIC_API_KEY` in git since S2 (#68) — rotate it.** Prod interests empty→reading skip (#44) until `/interests` re-run. S8 blocked on shared group + `COUPLE_CHAT_ID`. #27 open for the Language Reactor half. Hetzner migrations 007+008 and S26c outstanding unless the W1 deploy has landed; S25 pre-flight counts unfilled. Every v2 desk check remains unrun — a scaffolding slice exercises no user path and clears none of them.

---

## How to resume in a new Claude chat

Upload this file plus `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/TASKS.md`. Say:
*"Continuing the English bot build. Read BUILD_PROGRESS.md. Give me the Cursor prompt for the next slice."*

---

## Slice status

| Slice | Name | Status | Date | Notes |
|---|---|---|---|---|
| S0 | Repo skeleton | ✅ done & verified | 2026-07-31 | Config, db migrate/status, `/ping` verified against local PG 16.14. |
| S1 | Onboarding | ✅ done & verified | 2026-07-31 | ConversationHandler `/start`; users+streaks upsert; access control. Verified live. |
| S1a | Onboarding UX polish | ✅ done & verified | 2026-08-01 | Superseded interaction model by S1b; data layer unchanged. Verified live. |
| S1b | Onboarding rebuild | ✅ done & verified | 2026-08-03 | Single-message `edit_message_text` wizard; 8 taps / 0 typing common path; why multi-select → sentence; HTML + escape. Verified live. |
| S1c | Onboarding content | ✅ done & verified | 2026-08-03 | Self-assessment A2/B1/B2; domain category→specific drill-down; situation-based why options; EF SET nudge on save. Verified live. |
| S1d | Onboarding personality | ✅ done & verified | 2026-08-03 | Layout helper (≤12 shared rows); emoji on options; static reactions; warmer copy. Sticker skipped (no stable file_id). Verified live. |
| S2 | LLM wrapper + correction | ✅ done & verified | 2026-08-03 | `llm.py` + free correction. Verified live. |
| S3 | Daily quiz + scheduler | ✅ done & verified | 2026-08-03 | Spacing ladder + quiz + 5-min poll. Core verified live. **2026-08-09:** order/choice body+1–4 button layout verified live; dispatch fix verified live (free text after open non-gap quiz reached correction at 17:59). Gap-path live check still in Verification checklist. |
| S3a | Quiz content + formats | ✅ done & verified | 2026-08-03 | Labels not codes; track mix; gap/choice/reorder/spot. Verified live. |
| S3b | Quiz question layout | ✅ done & verified | 2026-08-03 | Body reads / buttons tap; feedback blank line. Verified live. |
| S3c | Quiz formats + register | ✅ done & verified | 2026-08-03 | Reorder→order; spoken register; one scenario. Verified live. |
| S3d | Quiz feedback + format mix | ✅ done & verified | 2026-08-03 | Full-sentence feedback; 2 typed/3 tapped. Verified live. |
| S4 | Streaks, freeze, rescue | ✅ done & verified | 2026-08-03 | 03:00 local rollover; freeze; rescue 3Q. Verified live. |
| S4b | Database backups | ✅ done & verified | 2026-08-04 | pg_dump/restore scripts; restore verified; off-site deferred to S4c. Verified live. |
| S4c | Off-site backup + freshness | 🟡 code-complete | 2026-08-10 | Mechanism verified on Mac; `.env` load fixed 2026-08-10. **Prod (Hetzner):** `BACKUP_OFFSITE_DIR` deliberately unset — local cron dumps only; known issue #6 restated. |
| — | **PHASE 1 SHIPPED — 14-day usage gate** | ⬜ | | Phase 1 slices verified; 14-day use gate still open |
| S5 | Voice partner | 🟡 code-complete | 2026-08-04 | Whisper+TTS; voice sessions; Active>Missed. Unrun: mid-conversation restart. |
| S5a | Voice processing status | 🟡 code-complete | 2026-08-04 | Repeating chat action + 3-stage status message. Unrun: never tested in Telegram. |
| S6 | Book ingestion | 🟡 code-complete | 2026-08-08 | `/book` → album debounce → vision OCR → `book_units` upsert; Done/Add more ends CH. Live: 10 pages → 5 units. **2026-08-09:** OCR, two-page merge, album debounce, re-ingest dedup, and text-after-Done reaching correction verified live. Suspected “correction collision” was S3 OpenQuizFilter, not the book CH. Light hardening: `collecting` gates late photos; 1h `conversation_timeout` clears abandoned `user_data["book"]`. Remaining human checks in Verification checklist. |
| S6a | `/test` + quiz top-up | 🟡 code-complete | 2026-08-08 | `book_test` session; tap-only `/test unit N`; morning top-up from `book_units` when due < size; selection-time dedup/word-bank; journal on book miss with taxonomy guard. |
| S7 | Anki export | ✅ done & verified | 2026-08-08 | TSV from `chunks` only; poll + `/anki`; mark-after-send. Human imported TSV into Anki; second `/anki` reported nothing new. **2026-08-09:** full Anki path verified live. S11 moved weekly poll to Saturday. |
| S7a | Chunk spaced review in daily quiz | 🟡 code-complete | 2026-08-10 | Migration 004; due chunks between errors and books (capped at typed_gap_count); article-tolerant grading; shared spacing_step; calib_* excludes chunks; Anki independent. |
| S8 | Couple challenge | 🟡 code-complete | 2026-08-10 | Group chat daily Q at 18:00 Vilnius from error journal; atomic first-correct → `couple_scores`; Sunday leaderboard; `COUPLE_CHAT_ID` + `/here`; correction already PRIVATE (unchanged). Second user onboarded; live verify blocked on shared group + `COUPLE_CHAT_ID` via `/here`. |
| S9 | Interests profile | 🟡 code-complete | 2026-08-04 | `/interests` wizard seeds `interests`. Unrun: custom-topic weight/last_used across Change→Done. |
| S9a | Reading delivery + chunks | 🟡 code-complete | 2026-08-06 | Mon/Wed/Fri evening poll; readings+chunks+session; ceiling; LLM off event loop. Unrun: same-day second poll / ceiling / morning quiz unblock. |
| S9b | Video engine (YouTube) | ⬜ not started | | |
| S9c | Reading comprehension + rating | 🟡 code-complete | 2026-08-08 | MCQ taps only; session resolve by message_id; edit-failure resend; rating→additive weight; legacy skip score=NULL. |
| S10 | Motivation engine | 🟡 code-complete | 2026-08-08 | Nudge ladder (quiz/reading/diary, max 2/day; Just do 2 for quiz/reading only) + Sunday report; human Telegram verify pending. |
| S11 | Weekly test + Murphy routing | 🟡 code-complete | 2026-08-08 | Sun 15Q weekly test (replaces morning quiz); Anki→Sat; Murphy rec on complete; weekly excluded from M14 window. | |
| S12 | Calibration + anti-fossilization | 🟡 code-complete | 2026-08-08 | M14 windowed raise/silent drop + M13 monthly fossil_sweep inject; human Telegram verify pending. |
| S18 | Hardening | 🟡 code-complete | 2026-08-08 | Global error handler + file-backed throttle; heartbeat (touch on success); rotating log; flock single-instance; `/pause` + `/stats`. |
| S18a | `/settings` editor | 🟡 code-complete | 2026-08-10 | Tapped-only editor for weights/times/fallback; no MessageHandler; route-outs to `/interests` + `/pause`; cefr read-only. |
| S18b | `/help` + command menu | 🟡 code-complete | 2026-08-10 | `setMyCommands` in post_init; grouped `/help`; `/ping` off menu; `/import` conditional on `WATCH_DIR`; onboarding save points at `/help` (still 2 messages). |
| S18c | `/guide` how-to | 🟡 code-complete | 2026-08-10 | Tapped-only topic wizard from GUIDE-saving-phrases; Anki template + field map exact; `/help` + onboarding point at `/guide`; prose command-drift test. |
| S18d | Access approval + `/admin` | 🟡 code-complete | 2026-08-11 | Migration 005 `access_requests` + `approved_onboarded_users` view; gate at group=-1; operator `/admin` activity-never-content; revoke≠delete; decline cap=2. |
| S24 | Shared content library | 🟡 code-complete | 2026-08-14 | Fan-out slang + operator shared books; migration 006 ledger; opt-in Share; convergent backfill; Trancy/LR sender-only. **Live 2026-08-14:** Share prompt for slang; Share fanned to both users (`users_reached: 2`, 5 slang chunks each); re-import imported 0 / already had 5; unrecognised header rejected with zero rows. |
| S24a | Trancy vocabulary CSV (generated sentences) | 🟡 code-complete | 2026-08-14 | Exact `{Word,Phonetic,Translation,Date}`; batched LLM sentences; sender-only; folder refuses vocab; prose failed-headers alert. **Live 2026-08-14:** 9 words → 8 imported / 1 skipped (`frustrate`); one call 1052 in / 486 out / 6.3s. |
| S24b | Vocabulary sentence quality + skip visibility | 🟡 code-complete | 2026-08-14 | Exact-form prompt; one capped gate retry; named skips in reply not log; register-balance prompt (human-verify). |
| S25 | First touch presents, it does not grade | 🟡 code-complete | 2026-08-14 | Migration 007 `presented_at`; fan-out unpresented; morning quiz ≤2 FIFO cards before graded Qs; shared due predicate; Anki ungated. |
| S26 | Conversation mode (text) | 🟡 code-complete | 2026-08-14 | `/talk`; `OpenConversationFilter` (not CH free-text); 30m/2m filter-time staleness; plain-text turns + close ≤3; migration 008 `errors.source`; gap entrance refuse. Close-out broken live — fixed in S26a. |
| S26a | Conversation close-out fix | 🟡 code-complete | 2026-08-14 | Fix S26 End-chat: trailing user cue; gen-fail completes session; distinct close copy; richer failure logs; never-echo prompt; construction tests at transport. |
| S26b | Conversation worth having | 🟡 code-complete | 2026-08-14 | Close 2000 + turn 500 `reject_truncation`; close truncation→max-2 retry→fallback; End UX; prompt rewrite; real topics + `picking_topic` rotation; #44 reading skip reported. 709 tests. |
| S26c | Readable, alive, English-clean | 🟡 code-complete | 2026-08-14 | Single-language close explanations; paragraph shaping; occasional reactions (not stickers); `/interests` free-text silent-drop fixed; named save confirmation. 714 tests. |
| S15 | Real-life capture (M11) | 🟡 code-complete | 2026-08-09 | Forward/`/capture` → explain + chunks only (`source=capture`); never `errors`; commit-after-send; dispatch spies pin M2. |
| S15a | Watched-folder bridge | 🟡 code-complete | 2026-08-10 | `WATCH_DIR` CSV import (Trancy/LR) + Anki outbox; mtime≥2min; collision-safe moves; due_chunks `id DESC` tie-break; `/import` + settings paths. **Prod:** `WATCH_DIR` unset — folder bridge dormant; CSV via Telegram (S15b) is the only import route. |
| S15b | CSV via Telegram document | 🟡 code-complete | 2026-08-10 | Private-chat `.csv` → shared S15a pipeline in memory; tool from headers; non-CSV warm line; 5 MiB cap; `/help` upload line; independent of `WATCH_DIR`. |
| S13 | Voice diary (M9) | 🟡 code-complete | 2026-08-09 | Tue/Thu prompts + `/diary`; live M3 wins voice routing; max 2 corrections; no TTS; full transcript discarded. |
| S14 | Load-up mode (M10) | 🟡 code-complete | 2026-08-09 | `/prep <topic>` → 10 chunks + 3 frames; persist `prep_<slug>` to Anki pool; no sessions/errors; commit-after-send. |
| S16 | Shadowing (M12) | 🟡 code-complete | 2026-08-09 | `/shadow` TTS from chunks; 30-min voice claim; word diff (ASR intelligibility); retry once; no errors/nudge/calibration. |
| S17, S19 | Phase 4 depth | ⬜ not started | | |
| S20–S23 | Phase 5 commercial | ⬜ not started | | |
| — | **V2 CLOSED — rebuild as web app begins (`docs/TASKS-v3-web.md`)** | ⬜ | | v2 slices above are historical record; v3 slices below |
| W0 | Audit + migration plan | ✅ plan approved | 2026-08-23 | Plan output only, no code |
| W1 | Python restructure | 🟡 code-complete | 2026-08-23 | `git mv` + core package + boundary tests; 721 green (+1 pre-existing failure); nothing deleted |
| W1b | App scaffolds | 🟡 code-complete | 2026-08-23 | api + worker + web shells; suite green with zero failures |

Status key: ⬜ not started · 🟡 in progress / code-complete · ✅ done & verified · ⚠️ done but has known issues

---

## Environment

| Item | Status | Value / note |
|---|---|---|
| Hetzner server | ✅ | CPX32 `fonderis-worker`, 78.46.240.136, Nuremberg, Ubuntu 24.04.4 LTS, Python 3.12.3. **Shared** with Node app `fonderis-worker.service` (port 3011), Redis 6379, Caddy 80/443 — bot must not assume exclusive use. No inbound port (Telegram long-poll outbound). See `docs/DEPLOYMENT.md`. |
| PostgreSQL 16 (local / Mac / development only) | ✅ | 16.14 on port **5433** (5432 taken by Docker). Not production; Mac data was **not** migrated to Hetzner. |
| PostgreSQL 16 (Hetzner / prod) | ✅ | Ubuntu repos, port **5432**. Database `english_bot`, owner `bot`. Migrations 001–006 applied (007+008 on next deploy). Started empty 2026-08-11. |
| DATABASE_URL | ✅ | Prod: local DSN `postgresql://bot:…@127.0.0.1:5432/english_bot` in `/home/bot/english-bot/.env` (mode 600). Mac keeps its own for development. |
| Telegram bot token | ✅ | in `.env` (Mac + server) |
| Shared group created | ⬜ | — |
| LLM provider + key | 🟡 | `LLM_PROVIDER`/`LLM_MODEL`/`ANTHROPIC_API_KEY` in config; real key on server `.env` |
| Whisper/TTS key | 🟡 | `OPENAI_API_KEY` + STT/TTS model env in config; optional at boot, required before first voice message |
| YouTube Data API key (S9b) | ⬜ | — |
| systemd unit | ✅ | `/etc/systemd/system/english-bot.service` — `User=bot`, `Restart=always`, `RestartSec=10`, journal, enabled at boot |
| Service user + code | ✅ | User `bot`, home `/home/bot`, code `/home/bot/english-bot`, venv `.venv` |
| GitHub deploy key | ✅ | Read-only deploy key generated on the server; clone over SSH |
| Backup cron | ✅ | `bot` crontab `0 4 * * *` → `scripts/backup.sh` (**04:00 UTC = 07:00 Vilnius**). Local dumps → `/home/bot/english-bot-backups` |
| Weekly pg_dump to independent storage | ⬜ | Local daily dump on same disk ✅; **`BACKUP_OFFSITE_DIR` unset on server** — no off-site copy (known issue #6) |
| User A onboarded | ✅ | `7222549221` — re-onboarded on empty prod DB via S18d (2026-08-11). Mac still holds prior 5 Murphy units + settings (deliberately left behind). |
| User B onboarded | ✅ | `5013535972` (Morkytė) — Lithuanian native, A2, onboarded 2026-08-12. |
| OPERATOR_TELEGRAM_ID | ✅ | Set on server `.env` |
| RUNTIME_DIR | ✅ | `/home/bot/english-bot-runtime` |
| BACKUP_DIR | ✅ | `/home/bot/english-bot-backups` |
| WATCH_DIR (S15a) | ✅ unset (deliberate) | No Drive client on server; folder bridge dormant in prod. CSV via Telegram (S15b) only. |
| BACKUP_OFFSITE_DIR (S4c) | ✅ unset (deliberate) | Google Drive unreachable from server; freshness check silent while unset (known issue #6 / #31) |

---

## Decisions log

Record every decision that deviates from or resolves ambiguity in the spec. Newest first.

| Date | Decision | Reason |
|---|---|---|
| 2026-08-23 | W1b: **`test_vocabulary_due_and_anki` now reads `CURRENT_DATE + 1` from the database after the insert** and passes that as `now`, instead of a frozen date or a changed `insert_chunks`. | The insert writes `next_review = CURRENT_DATE + 1` **server-side**; any date the test names itself is a second opinion about what day it is. Reading it back asks the same server the same question (CLAUDE.md §3 rule 6). Order matters: read *after* the insert, so a run that crosses midnight compares against the earlier day and stays due. Closes #61. |
| 2026-08-23 | W1b: **the `assert_path_outside_repo` tests derive the repo root from `tests/`** (`Path(__file__).parents[1]`), never from `repo_root()`, and there are now five cases: under `packages/`, under `scripts/`, a direct child of the root, the root itself, and `/tmp` accepted. | The old single test built its "inside" fixture from the function under test, so when W1 left `repo_root()` one directory too shallow the guard was broken and the test stayed green (CLAUDE.md §3 rule 5). `scripts/x.sql` and the direct-child case are the two that a `parents[2]` root accepts — **verified by re-introducing the bug: three of the five fail, then pass again when it is reverted.** Closes #63. |
| 2026-08-23 | W1b: **`core.db.current_schema_version()` was added** rather than putting a query in the route or calling `core.db.status()` from it. | SQL in `apps/api` fails `test_no_sql_outside_services`, deliberately. `status()` opens its own connection *and* runs `CREATE TABLE IF NOT EXISTS schema_version` — a health endpoint a monitor polls every minute must not run DDL. The new function is read-only and uses the shared pool, so `/health` fails exactly when a real request would. `core/db.py` already owns `schema_version` and is already the boundary test's named exemption. |
| 2026-08-23 | W1b: **`GET /health` answers 503, not 500, when the database is unreachable**, and catches that one exception itself. | "The service is up, its dependency is not" is a different fact from "this route crashed", and it is the one an uptime check acts on. The generic 500 handler stays the rule for everything else; this is the one probe that is allowed to know why it failed. No exception text crosses the wire either way. |
| 2026-08-23 | W1b: **`GET /health/auth` has no `response_model`** and returns the resolved session verbatim (`null` today). | A pydantic model for a session that Better Auth has not defined yet would be a guess, and the guess would be copied into `lib/api.ts` and then into every screen. `schemas/__init__.py` says W2 adds `Session` and types this route then. The route already reads `get_current_user`, and a test overrides that dependency to prove it renders what the dependency returns — otherwise the `null` proves nothing. |
| 2026-08-23 | W1b: **`http://localhost:3000` is a constant in `apps/api/main.py`, not configuration**, and `allowed_origins()` drops any origin containing `*` or missing a scheme even though `core.config` already rejects those. | `pnpm dev` always serves on 3000; putting it in `.env` means every developer's file drifts and the deploy has two origins to get right instead of one. The second filter is belt-and-braces: this list is what the middleware trusts, and "the validator upstream catches it" is how a credentialed wildcard ships. `allow_credentials=True` from day one so CORS is exercised in the shape W2's cookie needs. |
| 2026-08-23 | W1b: **the API's operator alert is a logging stub** (`send_operator_alert` → `logger.error`), reusing `format_alert` and `should_send_alert` for the text and the throttle. | The bot's channel is `context.bot`, which lives in the bot process; borrowing it means importing Telegram into `apps/api`, which CLAUDE.md §2 forbids. Sharing the throttle file means a burst of API 500s cannot flood a channel the bot's throttle does not cover. Recorded as #65 so the missing channel is a tracked gap rather than an assumption. |
| 2026-08-23 | W1b: **the worker takes `RUNTIME_DIR/worker.lock`, derived from `INSTANCE_LOCK_FILE`, not a new environment variable** — and writes `RUNTIME_DIR/worker.log`, not the bot's log. | The bot and the worker must be able to run at the same time, so they cannot share a lock; and a second env var is a second thing to forget on a deploy. Separate log files because `configure_logging` installs a `RotatingFileHandler`, and two processes rotating one file lose whichever one's lines are in flight when it rolls. |
| 2026-08-23 | W1b: **the worker reads the heartbeat file and never writes it.** | The file means "a scheduled job succeeded recently", and until W20 every delivery job is still in `apps/bot`. A worker that touched it would keep it fresh while the bot lay dead and the staleness alarm would never fire again. The writing moves here when the deliveries do. |
| 2026-08-23 | W1b: **both `monthly_freeze_reset` and `monthly_reset` are registered**, though the second calls the first. | They are the two units ARCHITECTURE-v3 §7 names, and both are idempotent per user per local day (`freeze_reset_on`; the `fossil_sweep` session guard), so the overlap costs one extra no-op query per 15 minutes. Collapsing them now would mean choosing which name survives while the bot's own scheduler still registers a third variant. Tracked as #66, resolved at W20. |
| 2026-08-23 | W1b: **`build_scheduler()` returns a `BlockingScheduler` with jobs added but not started**, and the job table is a `tuple[Job, ...]` of plain data. | Registration is the thing that broke in v2 (#54): five tests passed while asserting only predicates, so all five would pass against a worker that registers nothing. A table that can be inspected without starting a process is what makes "assert every job by name and trigger" a one-line test. The expected table in `test_worker.py` is written out by hand rather than imported, or it would assert that `JOBS` equals itself. |
| 2026-08-23 | W1b: **the plain-`def` route rule is enforced by AST**, and `await asyncio.to_thread(llm.chat, ...)` is explicitly *not* flagged. | A rule that also flags the sanctioned escape teaches people to hide the call instead of moving it off the loop. Because `apps/api` has no such route yet, the detector would be inert — so `test_the_plain_def_detector_actually_detects` runs it over an offending and a compliant fixture and asserts both results (CLAUDE.md §3 rule 4). |
| 2026-08-23 | W1b: **the new boundary test bans `apscheduler` and `telegram` in `apps/api`, and cross-imports between `apps/api`, `apps/worker` and `apps/bot`** — and deliberately does **not** ban `apps.*` inside `core`. | The API runs several uvicorn workers, each a whole process; a scheduler imported there fires every job once per worker (W0 risk R3). Widening the same test to `core → apps` would close #60, but it would fail on pre-existing code (`access_control.delivery_lister_ids`) and the pressure would be to weaken the test. That inversion gets its own slice. |
| 2026-08-23 | W1b: **`apps/web` uses `@ducanh2912/next-pwa`, not `next-pwa`.** | ARCHITECTURE-v3 §2 says "`next-pwa` / Workbox". The original has had no release since 2022 and declares support only to Next 13; this is the maintained fork of the same Workbox setup, with Next 14/15 in its peer range. Same mechanism, still built. |
| 2026-08-23 | W1b: **dark mode follows `prefers-color-scheme` with no toggle**, and shadcn's `.dark` class variant was rewritten as a media query. | A toggle has to remember its setting, and the two places to remember it in a browser are `localStorage` and a cookie. The slice bans the first outright and the second belongs to W2's session. Following the system is also what a phone user expects at dusk. |
| 2026-08-23 | W1b: the web shell's visual direction — **warm paper / deep teal-slate, one teal accent, Fraunces headings over Geist text, `max-w-lg` at every breakpoint, and no red anywhere in the palette.** | `/mnt/skills/public/frontend-design/SKILL.md` **does not exist in this environment**, so the direction was chosen rather than read, and is written down in `apps/web/README.md` so W6 onwards has something to be consistent with. Phone-width even on a desktop: both learners use a phone, and a second responsive layout is a second design to maintain for a screen nobody opens. No red because "never guilt" (CLAUDE.md §4) is easier to hold to when the colour for failure is not in the theme. |
| 2026-08-23 | W1b: **the `/health` check on the Today screen runs in the browser, not in a server component.** | A server component would call the API over loopback and prove nothing about CORS — which is the half that breaks on a phone (W0 risk R4). It is also the only thing on the shell that can fail, so it is the only thing worth rendering a state for. |
| 2026-08-23 | W1b: **the PWA manifest is `app/manifest.ts` (typed) rather than a hand-kept `public/manifest.json`**, and the four icons are generated by a script into `public/icons/`. | A wrong `display` or a missing icon size becomes a build error instead of a home-screen tile that turns out to be a browser shortcut. The icons are geometric and generated because there is no design asset yet and a placeholder that says "replace me" never gets replaced; `test_web_shell.py` asserts every file the manifest names actually exists. |
| 2026-08-23 | W1b: **the web shell's invariants are tested from the Python suite** (`tests/test_web_shell.py`) — no `localStorage`/`sessionStorage`, four nav items each with a page, one button on Today, manifest icons present, API base URL from the environment. | `pytest -q` is the only suite this repo runs; a second test runner nobody invokes is not coverage. The storage scan strips comments first and proves it does so, because the comment explaining why the app avoids `localStorage` contains the word — the grep-versus-parse trap the boundary tests already avoid. Adding a real JS test runner is #67, and belongs to W6 when components exist to render. |
| 2026-08-23 | W1b: **`WEB_ORIGIN` is validated in `core.config`** (scheme required, no trailing slash) rather than accepted as free text. | CORS compares origins literally: `https://app.example.com/` never matches anything a browser sends, and the failure appears on a phone as a blank screen with a console message nobody is reading. Failing at startup is cheaper. |
| 2026-08-23 | W1b: **`requirements.txt` is now grouped by which application needs each dependency**, and declares `APScheduler` explicitly. | It arrived transitively through `python-telegram-bot[job-queue]`; `apps/worker` imports it directly, and a dependency you rely on but do not declare disappears the day the transitive path changes. `httpx` is declared for the same reason — it is how the API tests reach the app through its real ASGI transport. |
| 2026-08-23 | W1b: **Next.js is pinned at 15.5.23**, not the current 16. | ARCHITECTURE-v3 §2 says Next.js 15, and a shell is the wrong slice to take a major-version bump in — the first thing it would break is the PWA plugin, which is the one piece here that is version-sensitive. |
| 2026-08-23 | W1: **`alerts.py`, `anki.py` and `motivation.py` moved to `packages/core/services/` in the bulk `git mv`**, though the W0 §5.2 move list did not name them. | §5.2's commit-4 edits are written against `core/services/{anki,alerts,motivation}.py`. They had to be in core before that commit could touch them. The omission was in the enumeration, not the intent. |
| 2026-08-23 | W1: **`app/config.py` → `packages/core/config.py`** and **`app/scheduler.py` → `apps/bot/scheduler.py`**, though neither appeared in the W0 §5.2 mv list. | Both are named by later commits in the same plan (`app.config` → `core.config` in the commit-3 rewrite; `apps/bot/scheduler.py` in commit 5). Leaving them behind would have left an `app/` package holding two files nothing could import. |
| 2026-08-23 | W1: **`deliver_weekly`, `handle_anki_command` and `on_error` were lifted to `apps/bot`, not deleted**, despite §5.2 saying "delete". | 14 tests cover them, and W1's own rule is that it deletes nothing. Deleting outright would have put the acceptance bar out of reach and invited quietly lowering it — the mechanism by which #12 and #26 survived v2. They live in `apps/bot/anki_delivery.py` and `apps/bot/alerts.py` and die at W22 with the rest of the bot. |
| 2026-08-23 | W1: **`packages/core/copy.py` holds the single definition** of the 52 strings core services render; `apps/bot/texts.py` imports and re-exports them. | Two copies of the same string is the drift this codebase has already paid for three times (`spacing_step`, `approved_onboarded_users`, `CHUNK_PRESENTED_AND_DUE_SQL`). Re-export keeps every handler call site and every `dir(texts)` no-guilt test working unchanged, with one place to edit. `SOFT_UNHANDLED` and the four `ANKI_*` strings went back to `texts.py` in commit 4, following their renderers to `apps/bot`. |
| 2026-08-23 | W1: the 12 moved prompts are addressed via **`core.PROMPTS_DIR`**, not a path literal per handler. | Each handler used `Path(__file__).parent.parent / "prompts"`, which after the move resolved to `apps/bot/prompts/` — a directory holding only `couple.txt`. One named constant beats twelve literals that must all be corrected again at W3. |
| 2026-08-23 | W1: **`core/services/paths.py::repo_root` changed from `parents[2]` to `parents[3]`** — an edit the W0 plan did not name. | Left alone it returned `packages/` after the move, so `assert_path_outside_repo` would have accepted any path under the repo but outside `packages/` as a `WATCH_DIR` — private learner content one `git add` away from the repo. **The existing test derives its "inside" path from `repo_root()` itself, so it stayed green either way** (#63). This is the CLAUDE.md §3.4 failure shape exactly. |
| 2026-08-23 | W1: **`TELEGRAM_BOT_TOKEN` validation moved from `core.config` to `apps/bot/main.py`**, which prints the same message and exits 1. | §5.2 says the API and worker must boot without a bot token, and that the field stays on `Settings`. Dropping the check entirely would trade one startup failure for a confusing PTB error deep in `ApplicationBuilder`. |
| 2026-08-23 | W1: **`test_no_sql_outside_services` excludes `apps/bot`** (≈20 handlers query directly, #58) and exempts `core/db.py` (migration runner) and `core/scheduling.py` (#59). | The alternative was a 25-file exemption list, which makes the test a rubber stamp. The rule's job is to stop a **W3 route** growing its own query; `apps/bot` is deleted at W22. The exclusions are named in the test's own docstring so nobody has to guess. |
| 2026-08-23 | W1: the five repo-scanning tests (`SPACING_DAYS` single-implementation, provider-SDK-outside-wrappers, two prompt-path constants, the `csv_import` source scans) were **rewired to the new tree**. | Left pointing at `app/` they would have scanned a directory that no longer exists — passing while testing nothing, and taking the `SPACING_DAYS` duplicate-implementation guard with them. |
| 2026-08-23 | W1: `notify_operator`'s new `send` parameter was **shadowed by the existing local** `send, suppressed = should_send_alert(...)`; the local is now `may_send`. | Caught by `test_on_error_soft_user_and_operator_alert`, which failed with `'bool' object is not callable`. Recorded because it is the one class of bug a signature change like this reliably produces, and the only reason it surfaced is that an integration test covers the real path. |
| 2026-08-23 | W1: **`docs/DEPLOYMENT.md` updated** — `python -m core.db`, `python -m apps.bot.main`, and a new `pip install -e packages/core` step in both the first-time and update sequences. | Without the editable install the server cannot import `core` and the deploy fails at the migrate step. The settled backup → pull → migrate → restart sequence is unchanged; the install sits between pull and migrate. |
| 2026-08-23 | W1: **the pre-slice baseline was 713 passing / 1 failing, not 714.** The count was held at that ratio through every commit rather than treated as a regression to fix. | `test_vocabulary_due_and_anki` is wall-clock dependent (#61) and has been failing since 2026-08-14, before W1 opened. Fixing it inside a move-only slice would have widened scope and, worse, mixed a behaviour fix into the commits whose whole purpose is to prove nothing changed. |
| 2026-08-23 | W1: **`apps` is a plain package on the repo root, resolved by `python -m`'s cwd insertion**, exactly as `app` was; only `core` is pip-installed. | Installing `apps` too would make `apps/bot` a dependency of the environment rather than of the process, and W1 changes no deployment shape it does not have to. |
| 2026-08-23 | W0: **`users.telegram_user_id` stays the primary key.** Better Auth links to it via a new `auth_user_id` column; the 12 foreign keys are not remapped. | 12 tables FK to it (verified against the live schema). A UUID remap in week 1 is the riskiest possible change to the journal, for a naming improvement. Cost: the column name stays misleading once sign-in is email/passkey. Confirmed with the human before writing the plan. |
| 2026-08-23 | W0: **restructure this repo in place** (`git mv`), not a new `english-app` repo. Root stays `english-bot/` on disk; ARCHITECTURE §3's name is logical. | ARCHITECTURE §1 says the value of the Python layer is ~40 encoded bug-fixes invisible in the code. `git blame` and `git log --follow` are how those fixes stay traceable; a copy-paste to a new repo destroys exactly the asset the whole extend-don't-rewrite decision is built on. Confirmed with the human. |
| 2026-08-23 | W0: **W1 moves and rewires only — it deletes nothing.** `app/handlers/*` stay alive under `apps/bot` through W21 and are deleted in W22 with their ~209 tests. | This is the only reading under which W1's own acceptance criterion (714 tests green) is meetable. The alternative — delete handlers at W1 — makes the bar unmeetable and invites quietly lowering it, which is how #12 and #26 survived. |
| 2026-08-23 | W0: **W1 makes zero behaviour edits.** Files needing an edit (`config.py` required-keys, `db.py` MIGRATIONS_DIR, `anki.py`/`alerts.py`/`motivation.py` PTB strip) get that edit in a separate commit from their `git mv`. | A slice that moves and refactors at once cannot distinguish a move bug from a refactor bug. The 335 pure-port tests are the migration's only proof of correctness. |
| 2026-08-23 | W0: `packages/core` is installed as the package `core` (`pip install -e`), so imports read `from core.services.errors import …`. | Makes the import boundary a packaging fact rather than a path convention, and keeps `apps/api`/`apps/worker`/`apps/bot` declaring an explicit dependency. |
| 2026-08-23 | W0: **`chunks` is never dropped or mutated by the W7 card migration.** `cards` gains `source_chunk_id` FK; the migration is pure-INSERT and reversible by `DELETE FROM cards`. Anki export keeps reading `chunks.exported_to_anki`. | Re-runnable and auditable against the live journal. Mirroring the export flag onto `cards` would create the drift this codebase has been bitten by three times (`spacing_step`, `approved_onboarded_users`, `CHUNK_PRESENTED_AND_DUE_SQL`). |
| 2026-08-23 | W0: FSRS seeding uses `stability = SPACING_DAYS[min(streak_right,4)]`, `difficulty = clamp(1,10, 5.0 + 1.6·lapses − 0.7·streak_right)`, `due = COALESCE(next_review, CURRENT_DATE)`. | The v2 ladder interval **is** an empirical stability estimate — the interval at which this learner last recalled the item. FSRS re-estimates both parameters from the first real review, so only the region matters; `due` and `stability` are what make the deck correctly spaced on day one. |
| 2026-08-23 | W0: chunks with no gappable `full_sentence` produce a **production card only**, no cloze card; skips are counted and logged, never silently dropped. | `due_chunks` already skips exactly these rows (`chunks.py:171–184`). A cloze card with no gap is an unanswerable item — the §4.3 bug this whole rebuild exists to fix. |
| 2026-08-23 | W0: migrated card `register` is derived from `chunks.source` — `slang` → `slang` **with no production card created**; `prep_*` → `formal`; everything else → `neutral` pending an LLM tagging pass. | PRD §8.5.1 forbids untagged cards and §8.5.2 forbids slang production cards. Tagging everything `neutral` would turn every HIMYM phrase into a speaking drill. The `slang` half is free and is the half that matters. |
| 2026-08-23 | W0: `errors.source` CHECK must be widened **once**, in the W5 migration, for the complete v3 source set (`shadow`, `retell`, `answer`, `item`, `placement`, `video`) rather than per-slice. | S26 already hit this wall and needed migration 008 for a single value. `record_errors` writes all corrections in one transaction, so a CHECK rejection loses the whole correction, not one row. |
| 2026-08-23 | W0: every LLM-calling FastAPI route is a plain `def` (threadpool), never `async def` calling `llm.chat` directly. | Known issue #7 with a worse blast radius: `llm.py` is synchronous by design and a blocking call in an `async def` route stalls the entire uvicorn worker, not one job tick. 19 `to_thread` call sites encode this today. |
| 2026-08-23 | W0: the `packages/core` boundary test is **AST-based**, not grep-based, and is joined by `test_no_provider_sdk_outside_wrapper` and `test_no_sql_outside_routers`. | Grep fails a docstring containing "telegram" and passes `import telegram.ext as x`. The two companion tests encode CLAUDE.md §2 rules that are currently satisfied by convention only. |
| 2026-08-23 | W0: the v2 work bias has **four** sources, not three — schema default (Work 40), a second hardcoded fallback at `handlers/quiz.py:116`, `{work_domain}` in 8 of 13 prompts, and `quiz.txt`'s own topic list naming campaigns first. W5 must fix all four; the schema default alone changes nothing. | PRD §4.6 names the first and third. The duplicated fallback means a NULL `track_weights` still yields Work 40 after the migration. The topic list is content, not weighting — no weight change removes "a work chat about a deadline" from the scenario examples. |
| 2026-08-23 | W0: existing `users.track_weights` rows are **not** rewritten when the default changes to 50/30/20. | The operator has already hand-tuned to `{"life":55,"work":30,"curiosity":15}` via `/settings`. Overwriting a deliberate user setting to enforce a new default is the opposite of the intent. |
| 2026-08-23 | W0: `app/prompts/*.txt` are `git mv`'d with **zero content edits** in W1. Exactly one (`quiz.txt`) is rewritten, deliberately, in W5. | The prompts carry fixes as prose: the no-prefill constraint, the single-language/no-transliteration rule, the capture PII substitution, the S24b exact-form gate. A tidy-up pass deletes a paragraph nobody can trace back to a live failure. |
| 2026-08-23 | W0: recommend **pulling W21 (off-site backup) ahead of W4**, the first slice to migrate the live journal. Raised once; the human decides. | Known issue #6 is the highest-ranked risk in the plan and W4 is the first irreversible action taken against the only copy of the data. Raising it here rather than at W4, per CLAUDE.md §8. |
| 2026-08-14 | S26c: close explanations must be **one language, one script** — no mixing, no Latin transliteration of native words. `{explanation_language_rule}` was already injected when `explanation_language_fallback` is on; the defect was that the rule never forbade half-switching. Live example mixed Persian + English + “zaman”. | Live close-out 2026-08-14. |
| 2026-08-14 | S26c: same language-instruction gap exists in **correction**, **diary**, **voice**, and **capture** prompts/handlers (shared `_FALLBACK_RULE_*` shape). Quiz/reading/book_test do not use this explanation-fallback injection the same way. Listed only — not fixed here. | Cross-prompt audit. |
| 2026-08-14 | S26c: turn replies shaped as short paragraphs + question on its own line (phone readability). Close-out correction blocks already use blank-line separation via `format_correction_reply`. | Six-line unbroken paragraph on phone. |
| 2026-08-14 | S26c: occasional `setMessageReaction` (~1 in 3 successful turns); failure non-fatal. **No sticker packs** — `file_id`s are bot-specific, need upload/maintenance, and date badly. Reactions give the same alive feeling without that. | User asked three times for more fun; stickers rejected deliberately. |
| 2026-08-14 | S26c `/interests` silent drop: WORK/LIFE/CURIOSITY states had **no MessageHandler**. Parent ConversationHandler `check_update` matched (active conversation) with `block=True`, found no text handler, and swallowed the update — nothing reached M2. Fix: same `receive_other` MessageHandler on track screens; reply `INTERESTS_CUSTOM_ADDED` so a reply is always visible. Save confirmation now names all three tracks (`INTERESTS_SAVED_NAMED`). | Live 15:37 Got it / 15:39 “Vibe Coding…” silence. |
| 2026-08-14 | S26b: prod `interests` **empty for both** `7222549221` and `5013535972` (Hetzner SQL, 0 rows). Mac DB still has 12 interests for the operator — not production. Zero `task_type=reading` sessions for either user on prod. S9 `select_topic` → `None` → `skipped_no_interests` with **no fallback** — evening reading silently skipped since empty-DB rebuild (operator 2026-08-11, User B 2026-08-12). Mon/Wed/Fri slots missed at least Wed 2026-08-13 for both; Mon 2026-08-11 also for the operator if onboarded before that evening. **Not fixed in S26b.** Recommend a follow-up slice: operator alert and/or `/stats` line and/or one-off “run `/interests`” prompt — a silent skip of a scheduled feature must not be invisible. | Live investigation during S26b; known issue #44. |
| 2026-08-14 | S26b: `_CLOSE_MAX_TOKENS=2000` (was 800). Live success used 513 output; failure hit 800 exactly then “no text blocks”. 2000 ≈ 4× success / ~2.5× failed ceiling — room for three corrections + Murphy refs. A constant-assertion test would not have caught this; mock transport truncation instead. | Observed 2026-08-14 close logs. |
| 2026-08-14 | S26b: `_TURN_MAX_TOKENS=500` (was 300) + `reject_truncation=True` on turns. Observed turn outs 26–110; Part C lengthens replies — truncated mid-sentence must never be sent. Truncation → existing warm turn-failure path (session open, turn not counted, zero errors). | Same `reject_truncation` flag as close. |
| 2026-08-14 | S26b: close truncation → one retry asking for at most two corrections → S26a `TALK_CLOSE_FAILED` + complete + zero errors. `stop_reason` logged on every `llm call` line. | Diagnosable from one log line; never trap the user. |
| 2026-08-14 | S26b: End chat answers callback first, edits wrap-up + clears keyboard, `payload.closing` idempotency; only one live End keyboard (`end_keyboard_message_id` cleared on prior message). Typing during close-out. | Live taps waited ~10s with a column of stale End buttons. |
| 2026-08-14 | S26b: rewrite `conversation.txt` — recast only on error; never restate whole message; contribute every turn; do not always ask a question; vary length; use chunks sometimes naturally. Original S26 “reuse their sentence” + “end with a question” made every turn an interview. Quality remains human-verified only (#41). | User verdict after two real chats. |
| 2026-08-14 | S26b: topics from interests + English chunk labels (`chunk`/`full_sentence` never `meaning`) + book units; defaults only if all empty. Persist `offered_topics` at picker show via phase `picking_topic` (filter ignores it — free text → M2). Rotate preferring unoffered. | Defaults were the empty-interests path; rotation must not require a tap. |
| 2026-08-14 | S26a root cause: close-out passed the live transcript ending on an **assistant** turn; Anthropic 400 (`invalid_request_error` — conversation must end with a user message) raised in `app/llm.py` `_anthropic_once` → wrapped as `LLMError` **before** any successful response, so no `app.llm: llm call` line. Turn path always appends the new user text first and succeeded. Fix: `build_conversation_close_messages` appends a fixed review cue as the final user turn. | Live evidence 2026-08-14 (three End taps, zero close `llm call` lines, session `completed=f`, zero `errors`). Same provider constraint as known issue #10 / S6 prefill removal. |
| 2026-08-14 | S26a: **generation** failure at close-out → warm `TALK_CLOSE_FAILED`, `completed=TRUE`, zero `errors`. **Send** failure after a successful generate → session stays open, zero `errors`, retry possible. | Being unable to leave trapped the user until the 30-min timeout — worse than losing ≤3 corrections. Send failure is different: the content exists and can still be delivered. Do not “harmonise” these later. |
| 2026-08-14 | S26a: distinct `TALK_CLOSE_FAILED` copy (chat has ended); never reuse `TALK_TURN_FAILED` (“say it again”) on End | Turn-failure copy after an End tap is confusing — there is nothing to say again. |
| 2026-08-14 | S26a: never echo an ungrammatical learner fragment in `conversation.txt` recasts | Live recast repeated “a little resting” verbatim — confirms the error. Instruction-only; #41 stays open for human verify. |
| 2026-08-14 | S26a: mock LLM at the **transport** (`anthropic.Anthropic`) for construction regression tests; do not mock above request construction for that check | `test_failed_close_send_writes_zero_errors` mocked `asyncio.to_thread`, so close request construction never ran — 693 greens, feature broken on first live use. |
| 2026-08-14 | S26: session-backed `OpenConversationFilter` — **not** a ConversationHandler free-text state | Free-text CH states twice killed M2 (S18a/S18c decisions). Same family as gap-only `OpenQuizFilter`; fail-open; never widen OpenQuizFilter. |
| 2026-08-14 | S26: `/talk` refuses on every entry path while a gap quiz awaits (`/talk`, `/talk <topic>`, topic tap, `talk:other`) | Quiz filter is correctly ahead of conversation. Without an entrance guard, a forgotten gap would grade a conversational sentence and advance the ladder. |
| 2026-08-14 | S26: `/talk` works while paused | `/pause` suppresses scheduled sends only; `/talk` is user-initiated (same class as `/diary`/`/shadow`). |
| 2026-08-14 | S26: implicit recasts mid-chat; ≤3 explicit corrections only at close-out, preferring recurring journal types | Conversation is the only sustained-production surface; interrupting to correct turns it into a quiz. Cap 3 (diary caps 2). |
| 2026-08-14 | S26: plain-text turn replies; JSON only for close-out | Errors-key argument applies to close. Turn parse/LLM failure → warm line, session stays open, `last_activity` refreshed, turn not counted, zero `errors`. |
| 2026-08-14 | S26: filter-time staleness — 30 min active, 2 min `awaiting_topic`; no scheduler | Forgotten chat must not permanently swallow M2. Other-topic wait must not turn a later correction sentence into a topic. |
| 2026-08-14 | S26: turn cap 12 + history 20 messages; a priori ~6–12¢/conversation; log `cache_read` | Cost ballpark fine for caps; fifty cents would force redesign. Hard turn cap is primary bound; history truncate from front is belt-and-suspenders. |
| 2026-08-14 | S26: voice during open text conversation unchanged (shadow → M3 → diary → M3) | Out of scope; do not let text conversation claim voice. |
| 2026-08-14 | S26: completed conversation → Active day without editing `streaks.py` | Active = any `completed=TRUE` (type-agnostic). Timeout leaves incomplete → Neutral. |
| 2026-08-14 | S26: migration 008 expands `errors.source` CHECK for `'conversation'` | Close-out inserts otherwise fail the CHECK. Verified constraint accepts `conversation` after apply. |
| 2026-08-14 | S25: nullable `presented_at` — do **not** overload `spacing_step` / `streak_right = 0` as unpresented | `spacing_step` is shared by `errors` and `chunks` (S7a). Errors are always already seen. A chunks-only meaning for step 0 would fork the shared ladder implicitly. |
| 2026-08-14 | S25: fan-out inserts leave `presented_at` NULL; user-sourced inserts set `NOW()` | Content through `shared_content_deliveries` was never studied — including the operator’s Share copy. Capture/prep/vocab/reading/Just-me already met the word outside the bot. |
| 2026-08-14 | S25: backfill uses `source <> 'slang' OR source IS NULL` — **not** a ledger join on `content_key` | Fuzzy SQL-approx `normalize_for_match` can under-match and silently mark fan-out rows presented — reintroducing the bug on the exact rows this slice fixes. Just-me slang gets one extra card (safe direction). **Future shared sources must set NULL at insert** — backfill is a one-off and must never be re-derived. |
| 2026-08-14 | S25: Hetzner pre-flight counts — **OPERATOR TO FILL after applying 007 on the server** | Placeholder (do not invent): total=`___`; stay_null (source=slang)=`___`; become_presented=`___`; non_slang_delivered must be 0. Desk DB numbers are irrelevant. Manual `next_review = CURRENT_DATE + 7` on User B’s five slang rows is irrelevant for unpresented selection — presentation picks them up regardless. |
| 2026-08-14 | S25: presentations ride the morning quiz (same message / one `bot_message_counts` increment) — no new scheduled message | Ceiling is hard (PRD §7). A separate presentation job would compete with quiz/nudges. Cards appear before questions in the same flow. |
| 2026-08-14 | S25: oldest-first (`created_at ASC, id ASC`) for unpresented — not `due_chunks` `id DESC` | Presentation is a drain queue; `id DESC` starves the oldest. Graded due keeps `id DESC` so bulk imports do not starve later captures. |
| 2026-08-14 | S25: presentations excluded from rescue, weekly test, and `/test` | Rescue never presents a backlog (PRD §7). Weekly and `/test` are assessment surfaces — flashcards do not belong. |
| 2026-08-14 | S25: Anki export not gated on `presented_at` | S7 already builds a proper card (word/sentence/meaning). Parallel retention path; withholding export would hide shared slang from Anki for days. |
| 2026-08-14 | S25: `present:ack` is idempotent (double-tap / out-of-order → answer callback, no-op) | Slow edits and impatient taps; S1b already swallows `message is not modified`. No double advance, no skipped card. |
| 2026-08-14 | S25: one shared `CHUNK_PRESENTED_AND_DUE_SQL` for `due_chunks`, `count_due_chunks`, `/stats` + drift test | Same lesson as `spacing_step` (S7a) and `approved_onboarded_users` (S18d). Divergent due counts are a lie. |
| 2026-08-14 | S24b: exact-form instruction in the prompt — do not relax the word-in-sentence gate | Same `normalize_for_match` invariant as S24/S15a/capture/prep; forking it for vocabulary is how invariants die. Base forms work in present simple. |
| 2026-08-14 | S24b: one capped retry for gate failures; retry LLMError does not abort when first pass succeeded | Failed words were invisible before. One retry recovers exact-form misses. First-pass rows are already good — aborting them on a retry blip would discard successful work. Whole-file abort still applies only when the **first** pass fails (S24a). |
| 2026-08-14 | S24b: name skipped words in the Telegram reply; log count + reason category only | Sender owns the content and needs the detail. Logs must not hold vocabulary (PRD §10). Cap + “and N more” avoids a wall of text. |
| 2026-08-14 | S24b: register balance + everyday sense as prompt instructions only | `work_domain` was colouring nearly every sentence. No unit test can judge register — next live import is the real check. Prefer plain sense over idiom (“a notch above”). |
| 2026-08-14 | S24a: generate example sentences rather than reject sentence-less Trancy files | Real Trancy vocabulary export has no sentence column and cannot be configured to add one. Chunks without `full_sentence` cannot feed S7 Anki cloze, S16 shadowing, or S7a gap-fill. Cost: sentences are generated, not mined — the word is no longer tied to the scene where it was met (memorability loss). Slang CSV (real examples) stays the better source. |
| 2026-08-14 | S24a: send Translation glosses into the LLM for sense selection | Multi-sense words (`notch`, `tier`) need the Persian gloss; bare word makes the model pick a sense at random. Prompt: use gloss for sense only, everyday sense when several listed, English output only. |
| 2026-08-14 | S24a: `Translation` column name is the structural never-share marker | Native-language meanings by construction. A column name (not a separate flag) is what the classifier already sees — a flag could drift from the header. Vocabulary never reaches Share / `shared_content` code. |
| 2026-08-14 | S24a: batch up to 40 words per LLM call; sequential batches; whole-file abort on failure | One call per row would stall the handler and inflate cost. Cap keeps long Persian glosses + sentence outputs inside a sane `max_tokens`. Any batch failure → zero rows (never a half-import). |
| 2026-08-14 | S24a: sender-only is structure, not a Share default | Mis-tap must be impossible — no Share keyboard, no ledger rows. Any user (incl. Morkytė) imports to self only. |
| 2026-08-14 | S24a: real header `{word,phonetic,translation,date}` vs S15a guess | S15a inferred Word+Translation plus a sentence-like column. Real export is four columns, no sentence. Trancy-legacy now **requires** a sentence-like column structurally (not order-only vs vocabulary). |
| 2026-08-14 | S24a: folder path refuses vocabulary (WARNING → `failed/`); Telegram is the acceptance path | Calling the LLM inside `watch_poll` is known issue #7. `WATCH_DIR` is unset in prod — do not plant that failure in a dormant path. |
| 2026-08-14 | S24a: generate with no write transaction held; then insert→send→commit | Pool `max=5`; holding a connection across a 40-sentence generation would starve other handlers. |
| 2026-08-14 | S24: fan-out one row per approved user — not nullable `chunks.user_id` + join table | Every consumer (S7a ladder, `due_chunks`, Anki, `/stats`, quiz) assumes `user_id`-scoped rows; a shared catalog would force a review-state join and refactor S7a/S7/quiz for two users. Fan-out also gives each person their own `next_review`. Cost is duplicated rows; storage is not a constraint at this scale. |
| 2026-08-14 | S24: English-only shared content — slang Share opt-in; Trancy/LR never auto-share | Operator Trancy exports carry Persian meanings; User B is Lithuanian — Persian in her queue/Anki is noise. Slang CSV is English-to-English (safe by construction) but still requires explicit Share / Just me. “Share everything the operator imports” rejected. |
| 2026-08-14 | S24: convergent backfill — Save (soft-fail) + both approve/re-approve handlers + reconcile at fan-out top | One-shot hooks lose the library forever if they throw. Soft-fail never breaks onboarding; weekly slang CSV repairs gaps. Call sites are idempotent via `shared_content_deliveries`. |
| 2026-08-14 | S24: skip-owned still writes a delivery (`skipped_owned`) | Without it the ledger permanently disagrees with reality and every backfill re-checks forever. Copy insert + delivery in one transaction. |
| 2026-08-14 | S24: phonetic appended to `meaning` as `… (/ipa/)` — no schema column | No consumer today (S16 TTS uses `full_sentence`). |
| 2026-08-14 | S24: chunk ledger first-write-wins; book ledger refreshes title/items | Same word with a new example must not rewrite everyone’s mid-review card. Books refresh because OCR can improve a unit; never overwrite `studied_at`/`created_at` (S6a/S11). |
| 2026-08-14 | S24: `SHARED_BOOK_SLUGS` env (normalised match) + INFO when operator slug stays personal | Not a hardcoded Python list. Silent non-share is indistinguishable from a broken config. |
| 2026-08-14 | S24: whole-header slang signature (exact five columns) — not token presence | Token matching would let a Trancy file look like slang and fan Persian meanings out. Mutual exclusion with Trancy/LR; unknown → reject. |
| 2026-08-14 | S24: Share is CallbackQuery only (no MessageHandler / ConversationHandler); orphan `share:` warm line | Free-text ConversationHandler states twice killed M2. Restart between file and tap clears `user_data`. |
| 2026-08-14 | S24: backfill called from access_request + admin handlers — not `access_control.approve_access` | Avoids circular import with the delivery-lister registry. Both grant paths must wire backfill. |
| 2026-08-11 | Deployed to Hetzner alongside an existing production service | The bot needs no inbound port (Telegram long-poll outbound), so it cannot conflict with the Node app on 3011 / Redis / Caddy. PostgreSQL 16 was added to the shared host rather than a separate box. |
| 2026-08-11 | Started with an empty database rather than migrating the Mac data | The Mac database had been truncated the previous evening and held only book units and settings; a clean start also exercised the S18d approval flow end to end. Mac data left behind deliberately. |
| 2026-08-11 | `WATCH_DIR` unset on the server | The S15a folder bridge reads a local path that Google Drive syncs; no Drive client exists on the server and neither user's laptop Drive is reachable. CSV upload via Telegram (S15b) is now the only import route — exactly why it was built. **S15a is effectively dormant in production.** |
| 2026-08-11 | `BACKUP_OFFSITE_DIR` unset on the server | Google Drive is unreachable from the host; no off-site destination configured yet. Local dumps land on the same disk as the database (known issue #6). |
| 2026-08-11 | S18d: configured operator always passes the gate | Approve/Decline and `/admin` must work even if the operator id has no `access_requests` row yet (bootstrap). Strangers still blocked. |
| 2026-08-11 | S18d: `access_requests` table (+ `decline_count`) — not `plan`/`tenant_id`/status-on-users | Pending cannot live on `users` (NOT NULL name/language; write-nothing-until-Save). `plan`/`tenant_id` are Phase 5 commercial vocabulary — reusing them muddies S21. |
| 2026-08-11 | S18d: view `approved_onboarded_users` is the single delivery predicate; six call sites + drift test | Same lesson as S7a `spacing_step` — six hand-rolled JOINs drift; a missed site silently keeps delivering to a revoked user. |
| 2026-08-11 | S18d: open `/start` was a live hole on a public server | ARCHITECTURE §7 allowed `/start` for anyone; full onboarding + LLM spend. Closed before Phase 5 tenancy. |
| 2026-08-11 | S18d: revoke ≠ delete | Mis-tap must not destroy journal/chunks/sessions/streaks (ARCHITECTURE principle 3). Re-approve restores access with data intact. |
| 2026-08-11 | S18d: `/admin` shows activity never content | Voice diary and error journal are personal (PRD §10). If the operator can read what someone wrote or said, willingness to put real life into the bot collapses. Future “peek at errors” must argue against this explicitly. |
| 2026-08-11 | S18d: `OPERATOR_TELEGRAM_ID` unset → store pending, loud log, tell requester access closed | Silent drop hides misconfiguration; storing lets the operator catch up when configured. |
| 2026-08-11 | S18d: central gate at group=-1 + `ApplicationHandlerStop`; drop `is_onboarding`/`bot_data` | Old group-1 TypeHandler only logged after handlers ran. Approval precedes wizard so mid-onboarding allowlist is redundant and fragile on restart. Gate is load-bearing — surface regression test mandatory. |
| 2026-08-11 | S18d: decline cap = 2 operator DMs | Re-request after decline stays allowed (mistaken decline lockout is worse); uncapped cycles spam the operator from an unauthenticated stranger. |
| 2026-08-11 | S18d: `on_error` soft-reply-to-strangers closed by the gate | Unapproved updates never reach group-0 handlers. Residual only if the gate itself throws (DB down) — fail-soft under outage, not an access hole. |
| 2026-08-11 | S18d: `/admin` omitted from `setMyCommands`, `/help`, `/guide` | Advertising it teaches strangers the command exists; silent ignore for non-operators is the security UX. |
| 2026-08-11 | S18d: leave `streaks.py` untouched | Rollover for a revoked user sends no Telegram message; constraint forbids editing that file. |
| 2026-08-10 | S18c: tapped-only `/guide` — **no MessageHandler**, nested `per_message=True` under `per_message=False` parent (same as S18a) | Free-text ConversationHandler states twice consumed text ahead of correction and silently killed M2. Guide is read-only navigation; taps cannot steal dispatch. Do not silence the mixed-handler warning. |
| 2026-08-10 | S18c: guide copy lives in `texts.py`, not read from `docs/GUIDE-saving-phrases.md` at request time | Runtime must not depend on a docs path on the host; every user-facing string belongs in `texts.py` (constitution). Markdown stays the human-facing source for editing. |
| 2026-08-10 | S18c: onboarding save confirmation gains `/guide` beside `/help` (still 2 bot messages) | Fits inside the existing confirmation lines without a third reply; second user needs the how-to pointer at the moment they finish setup. |
| 2026-08-10 | S18c: command-drift test extended to **prose** — every `/command` named in guide strings must have a registered handler | Guide names more commands in running text than `/help` lists; nobody re-reads a guide, so a stale `/capture` or `/anki` mention would go unnoticed. |
| 2026-08-10 | S18c: callback prefix `guide:` (distinct from `set:`/`pause:`/`wiz:`/`int:`/`btest:`/`read:`/`nudge:`/`shadow:`) | Orphan stale handler and no collision with other tap surfaces. |
| 2026-08-10 | S15b: Telegram document is the **general** CSV entrance; `WATCH_DIR` folder remains a **single-user convenience** | Folder only works for whoever syncs Drive to the bot host; after Hetzner neither user's laptop Drive is visible. Telegram works from any device/account. Entrances are independent — unset `WATCH_DIR` must not disable uploads. |
| 2026-08-10 | S15b: tool detection from header shape (Trancy: Word+Translation; LR: Phrase+(Definition\|Context\|Video)); else `subtitle_csv_*` | No folder hint on Telegram. Guessing wrong tags Anki/review metadata permanently; `csv` fallback is safer than a confident wrong tool. |
| 2026-08-10 | S15b: non-CSV → one warm line (no LLM); refuse >**5 MiB** before download; IMAGE excluded from non-CSV filter | Silent ignore looks like a broken bot. Phrase exports are small; multi-year cumulatives fit under 5 MiB; larger is almost certainly a wrong file. |
| 2026-08-10 | S15b `/book` collision: book `COLLECT_PAGES` is `PHOTO \| Document.IMAGE` only — CSV never matches; non-CSV filter is `Document.ALL & ~IMAGE & ~csv` | Confirmed: mid-book CSV reaches import; mid-book image document still reaches book; plain text still reaches correction. No OpenQuizFilter widen. |
| 2026-08-10 | S15b: one shared `import_csv_rows` / `map_headers` for folder + Telegram (not two mappers) | Mapping is the least certain part of S15a (#27); duplicated logic would drift. Folder path adds move-to `processed/`/`failed/` only. |
| 2026-08-10 | S8: `correction.py` already had `ChatType.PRIVATE` — **not modified** | Verified before assuming; group text never reached M2. Adding couple filter is additive only. |
| 2026-08-10 | S8: `OpenCoupleChallengeFilter` checks `is_registered` inside the filter | Handler never runs for strangers; “ignored entirely” asserts spy not called. |
| 2026-08-10 | S8: questions from error journal (alternate by `date.toordinal() % 2`, stubborn = highest `times_wrong`); partner fallback; both empty → skip | Product point is *their* mistakes. **Fairness:** half the week each is tested on the partner’s gaps, so the non-author is likelier to win that day — balanced over a week, not a bug. |
| 2026-08-10 | S8: no `mark_result` on challenge answers (no `source_error_id`; no migration) | Cannot map answer → error row. Known issue #28. |
| 2026-08-10 | S8: group posts do **not** increment `bot_message_counts` | Rule 9 is per-user private delivery; group messages are not DMs and do not compete with quiz/reading/nudge. |
| 2026-08-10 | S8: atomic first-correct via `UPDATE … WHERE winner_user_id IS NULL` | Read-then-write races would hand out two points. |
| 2026-08-10 | S8: feature inert until `COUPLE_CHAT_ID` set **and** ≥2 registered users | No solo spam; no errors when unset; starts when second `/start` completes. |
| 2026-08-10 | S8: `/here` in group echoes chat id for `.env` + restart (Settings stays env-only) | Friendlier than scraping getUpdates; no migration / no second config path. |
| 2026-08-10 | S8: Sunday leaderboard marker = `sessions` `couple_leaderboard`, `completed=FALSE`, `date=` Sunday posted | Proven inert by tests (Neutral, morning still due, out of calibration, backfill Neutral). Never flip completed — Active = any completed of any type. |
| 2026-08-10 | S18b: `/help` grouped by intent (Every day / Speaking / Real English / Books / Vocabulary / Settings), not alphabetically | Fourteen flat lines are unscannable on a phone; intent groups match how someone looks something up. |
| 2026-08-10 | S18b: `/ping` stays registered, omitted from `setMyCommands` and `/help` | Developer liveness check — pollutes the learner menu. |
| 2026-08-10 | S18b: `/import` omitted from menu + `/help` when `WATCH_DIR` unset (same one condition, both surfaces) | Command no-ops without the folder; listing it only confuses. No general capability registry. |
| 2026-08-10 | S18b: onboarding save adds one `/help` line inside the existing confirmation (still 2 bot messages) | S1d fixed the count at 2; appending to `ONBOARD_SAVED` / `ONBOARD_SAVED_EFSET_NUDGE` does not add a third reply. |
| 2026-08-10 | S18b: handler-drift test — every `setMyCommands` name must appear in `register_handlers` (walks ConversationHandler entry points); `/ping` asserted present in handlers and absent from menu | A help/menu entry with no handler (or a live command missing from the menu) is worse than no menu. |
| 2026-08-10 | S18b: `/start` and `/help` on the Telegram menu but not repeated as lines inside `/help` body | Menu needs them for discovery; the body is by intent after onboarding, and `/help` is the message itself. |
| 2026-08-10 | S18b: `setMyCommands` failure → WARNING + continue boot | A Telegram blip must not prevent the bot from starting. |
| 2026-08-10 | S15a: tolerant whole-word header map (not hardcoded Trancy/LR columns); fail loud to `failed/` + operator if required fields missing | Both tools change headers between versions; a silent mangled import poisons the review queue looking legitimate. Whole-word so `title` does not match inside `subtitle`. |
| 2026-08-10 | S15a: row-level dedupe via `normalize_for_match(chunk)`, not file-name tracking | Cumulative exports reappear under new filenames; file tracking alone would re-import everything. |
| 2026-08-10 | S15a: stability = mtime ≥ **2 minutes** (single-pass); not two-observation size map | Two-observation with a slow poll lands every automatic import a day late; mtime needs no cross-tick state and gives Drive time to finish writing. |
| 2026-08-10 | S15a: `watch_poll` on shared **5-min** `POLL_SECONDS` (not once-daily) | With the 2-min mtime gate, a settled file imports within ~5–7 minutes. |
| 2026-08-10 | S15a: **no per-import row cap**; confirmation shows imported/duplicate/invalid + due-chunk count | Anki is the overflow valve (S7a); leftover CSVs fight Drive re-sync. Visibility beats a silent multi-year queue. |
| 2026-08-10 | S15a: due_chunks tie-break `ORDER BY next_review ASC NULLS FIRST, id DESC`; **due_errors stay `id ASC`** | Uncapped import would bury later captures for months under oldest-first within the same tomorrow date. Errors: oldest failing must not be starved — different data, different rule. |
| 2026-08-10 | S15a: move to `processed/` / `failed/` with UTC timestamp suffix on name collision — never overwrite | Both tools reuse stable default filenames; silent overwrite would destroy the earlier export the move-not-delete rule exists to keep. |
| 2026-08-10 | S15a: Anki outbox write additive + failure-tolerant (Telegram + `exported_to_anki` always proceed) | Folder is a convenience; its failure must not cost the user their export. |
| 2026-08-10 | S15a: per-user `inbox/<telegram_user_id>/` (+ auto-created `trancy/` / `language_reactor/`); **never** attribute root-level inbox files | Misattribution puts one person's viewing history in the other's Anki/review (PRD §10). |
| 2026-08-10 | S15a: orphan WARN set is module-level (resets on restart → re-warn OK); not `bot_data` | S3: `bot_data` dies on restart and must not hold state; operator throttle still prevents flood. |
| 2026-08-10 | S15a: `/import` + `/settings` surface exact inbox and tool paths; direct inbox drop → `subtitle_csv_*` | Nobody should look up their Telegram id; tool folders are first-class, csv default is intentional not a surprise. |
| 2026-08-10 | S15a: poll confirmation increments `bot_message_counts`; `/import` does not; no pause gate on folder scan | Bot-initiated toast counts toward ceiling of 3; user-initiated scan must stay testable; pause must not strand CSVs. |
| 2026-08-10 | S15a: Hetzner Drive sync via `rclone` + Google service account deferred (document only — first real cloud credential) | This Mac uses a plain Drive-synced path with no credentials; do not add rclone/SDK now. |
| 2026-08-10 | S4c: INFO log when off-site skipped because `BACKUP_OFFSITE_DIR` unset (`off-site copy skipped …`) | Silent skip hid a misconfiguration (`.env` unread) for three runs; one INFO line distinguishes "not configured" from "configured but broken". Still no nag for operators who have not opted in. |
| 2026-08-10 | S4c: **daily** off-site copy after each successful local dump (deviation from TASKS S4b "weekly") | More restore points; no separate weekly schedule to go wrong. TASKS S4b/S4c wording updated to match. |
| 2026-08-10 | S4c: `BACKUP_OFFSITE_KEEP=14` (match local) | Off-site is the set that survives machine death; shorter than local would invert the disaster model and lose slow-corruption headroom. Storage is not the constraint. |
| 2026-08-10 | S4c: iCloud `.english_bot_*.dump.icloud` placeholders count as **present** in freshness + retention | Optimise Mac Storage evicts cold dumps; ignoring placeholders cries wolf (alerts muted) and disables pruning. A placeholder means the file is safely in iCloud. |
| 2026-08-10 | S4c: refuse `BACKUP_OFFSITE_DIR` inside / equal to `BACKUP_DIR` | Same-disk folder tree is not off-site — configuring that way is false confidence. |
| 2026-08-10 | S4c: loud fail if off-site dir missing/unwritable — never `mkdir` | An unmounted drive or unsynced cloud folder must not silently write into a stub nobody mounted. |
| 2026-08-10 | S4c: freshness threshold **48h**; in-process hourly check via `notify_operator` | One missed daily run still ok; two missed → alert. Same honesty as S18 heartbeat: detects stopped backup while the bot is alive; cannot detect anything if the bot is also down. Unset dir → silent no-op. |
| 2026-08-10 | S18a: tapped-only `/settings` — **no MessageHandler**, no free-text states | A ConversationHandler with free-text state is the shape that twice consumed text ahead of correction and silently killed M2 (S3 OpenQuizFilter / book CH history). Tapped-only cannot do that; Agent-mode safe. Later free-text fields (`why_statement`, `work_domain`) take on that dispatch risk deliberately. |
| 2026-08-10 | S18a: no `conversation_timeout` on the settings CH | Known issue #18 — timeout is a no-op under nested conversations (PTB warning on S6 book). Abandoned `/settings` is harmless: no text filter, `set:` cannot collide with `pause:`/`wiz:`/`int:`. Leaving it out is intentional, not an oversight. |
| 2026-08-10 | S18a: fourth weight preset **Mostly everyday** 15/70/15 | S1's three presets (40/40/20, 60/25/15, 25/60/15) did not cover a real ask to lean hard into everyday life — user had to edit production SQL. |
| 2026-08-10 | S18a: `cefr_level` read-only; pointer to `/stats` | S12 calibrates from rolling accuracy. A manual override would fight the calibrator silently (set B2 → pulled to B1 in a fortnight with no explanation). |
| 2026-08-10 | S18a: route-outs to `/interests` and `/pause` (one line each) | Do not reimplement topic or pause UIs inside settings. |
| 2026-08-10 | S18a: morning/evening buttons = S1b presets (07/08/09, 19/20/21); no Other | Sets match onboarding's button list. Times chosen via onboarding "Other" free text are unreachable here — accepted cost of tapped-only, not an oversight. `split(":", 2)` keeps `07:00` intact. |
| 2026-08-10 | S18a: stale `set:` after restart → warm "send /settings again" (orphan handler + in-handler flight check) | `user_data` is in-memory; post-restart taps on an old panel would otherwise KeyError or silently no-op. Same class as S9c stale callbacks. |
| 2026-08-10 | S7a: first migration since 003 (`004_chunk_review.sql`) — additive review columns on `chunks` only | Chunks had no review fields; spaced quiz review cannot work without them. Nullable/`DEFAULT` so existing rows and queries stay valid; standing no-migration rule lifted for this slice only. |
| 2026-08-10 | S7a selection: due errors → due chunks (cap `typed_gap_count`) → book top-up | Errors remain the core asset; chunks are user-collected vocabulary; books are generic filler. Cap at 2 typed/day (S3d) so multi-word chunk gaps do not become the routine mix — excess wait (nothing expires). ~14 slots/week vs ~15 reading chunks/week → backlog grows; Anki stays the volume valve. |
| 2026-08-10 | S7a: article-tolerant `grade_chunk_answer` (drop a/an/the); no length ceiling | Live n=27: median 4 words, zero single-word; exact match would punish phone typing and stall the ladder. Content-word misses still fail. Ceiling at ≤3 would exclude ~⅔ and gut the feature. |
| 2026-08-10 | S7a: extract `spacing_step` in `errors.py`; chunks call it via `mark_chunk_result` | ARCHITECTURE §8 — one ladder implementation. Chunk failures never write `errors` (vocab ≠ grammar). |
| 2026-08-10 | S7a: Anki `exported_to_anki` independent of review state | Export and in-bot review are parallel retention paths; exported chunks still due when `next_review` says so. |
| 2026-08-10 | S7a: `sessions.score` full-quiz honest; calibration uses `calib_correct`/`calib_answered` (non-chunk) | Phrase recall ≠ difficulty fit (same spirit as excluding `/test` and weekly). Silent M14 drops must not be driven by multi-word typed misses. |
| 2026-08-10 | S7a: chunks excluded from weekly test; no M13 interaction | Weekly measures error-type coverage; M13 sweeps resolved error types only. |
| 2026-08-10 | S7a: NULL `next_review` = never reviewed = due; new inserts get tomorrow | Picks up existing chunks without a backfill; matches S2 new-error contract. |
| 2026-08-09 | S16 audio source = `speech.synthesize` over `chunks.full_sentence` (not mined scene clips) | No mining pipeline / scene audio exists. Pedagogical loop unchanged. **Cost:** TTS is cleaner/slower than real dialogue — trains rhythm and word stress, not casual reductions ("gonna", elisions). Mined sitcom clips remain the better source (known issue follow-up). |
| 2026-08-09 | S16 voice routing: claimable shadow → live M3 → open diary → M3 | `/shadow` is the most recent explicit "repeat this" instruction. Lookups disjoint by `task_type` + completion; only one branch runs. When shadow is not claimable, S13 preserved (live M3 beats diary). |
| 2026-08-09 | S16 shadow voice **claim window = 30 min** after `payload.clip_sent_at` (Try again re-arms) | Open-until-03:00 claim would strand M3 after an abandoned `/shadow`. Session stays open (rule 2); only the microphone claim is time-bounded. |
| 2026-08-09 | S16 sentence select: exclude last **K=10** shadowed `chunk_id`s from payloads, then `created_at DESC` | Skip-previous-only alternates two newest forever. K-exclusion is deterministic, uses existing payload data, no migration; weighted-random would flake tests. |
| 2026-08-09 | S16 deterministic `SequenceMatcher` word diff; no LLM | Free, reproducible; Whisper is ASR not a pronunciation scorer — feedback measures intelligibility to ASR; copy says "didn't come through clearly" / "try this part again", never "pronunciation was wrong". |
| 2026-08-09 | S16 never writes `errors` | Transcription mismatch ≠ grammar error; would poison spacing / weekly test / calibration / Sunday report. |
| 2026-08-09 | S16 retry once then complete regardless of score; not nudgeable; no schedule; no `bot_message_counts` | Two attempts enough; evenings fully allocated; user-initiated like `book_test`. |
| 2026-08-09 | S16 attempt transcript not persisted (score only on `sessions.score`) | PRD §10 — transcript is the user's voice in text form. |
| 2026-08-09 | S16 `sessions.score` deliberately outside calibration (`CALIBRATION_TASK_TYPES` stays quiz/reading + comment + test) | Shadow score is ASR intelligibility, not comprehension accuracy; conflating would move CEFR from how well Whisper heard them. |
| 2026-08-09 | S14 prep chunks **persist** to `chunks` (Anki pool) | Highest-intent vocabulary in the product — user asked for them for a real situation with real stakes; S7 TSV is the retention path. |
| 2026-08-09 | S14 `chunks.source = prep_<slug>` (slug = lowercase topic, non-alnum → `_`, max 48) | Distinguishable in TSV from `capture`, `reading_17`, `book_unit_12`. Topic may name a client — logged never; source column is user-facing Anki metadata. |
| 2026-08-09 | S14 **no `sessions` row** | `/prep` is a lookup, not a task: must not claim quiz/reading slots, affect streaks, or make the day Active. “Any completed session = Active” makes inventing a session type the wrong easy choice. |
| 2026-08-09 | S14 never writes `errors` | User has not produced English; nothing to correct. Same reasoning as S15. |
| 2026-08-09 | S14 partial-result-over-failure: fewer than 10 valid chunks after validation → send survivors + WARNING with count | Nine useful phrases beat an error message; S7 gap needs chunk inside sentence so broken pairs are dropped, not padded. |
| 2026-08-09 | S14 reply may exceed 400 characters | PRD §8’s 400-char limit is for scheduled messages; `/prep` is a user-requested reference list meant for a phone 30 minutes before a meeting. |
| 2026-08-09 | S14 frames are reply-only (never DB) | Reusable skeletons with `___` slots for the moment; Anki cloze contract is chunk/full_sentence/meaning — frames are not cards. |
| 2026-08-09 | S14 `track` NULL when omitted/invalid — never invent `'work'` | Same as S15; CHECK permits NULL; inventing work would bias tags. |
| 2026-08-09 | S13 voice routing (ordered): live M3 (`get_continuable_voice_session`) wins → else open incomplete `diary` for local today → else M3 | A Tue/Thu diary prompt routinely lands inside the 120-min M3 window; claiming that turn as diary breaks mid-conversation with no explanation. Diary stays open until 03:00. Lookups are disjoint by `task_type` + completion semantics; only one branch runs. |
| 2026-08-09 | S13 bot diary prompts **Tue/Thu** only (`DIARY_WEEKDAYS={1,3}`); separate `diary_poll`; never same day as reading/Anki/report | Ceiling + existing evening owners. ARCHITECTURE “rotating M3/M4/M9” refined: evening = M4 Mon/Wed/Fri + M9 Tue/Thu; M3 stays user-initiated. |
| 2026-08-09 | S13 `/diary` is user-initiated any night — no `bot_message_counts`, no ceiling; reuses open session; warm already-done after complete | Restores PRD “every night” without spending rule-9 slots. Tue/Thu prompts are the reminder; `/diary` is the habit. |
| 2026-08-09 | S13 diary is nudgeable (`NUDGEABLE_TASK_TYPES`); text-only ladder; **no** Just do 2 | Open until 03:00 needs a recovery path. Just do 2 is quiz/reading `early_limit`. Tue/Thu quiz+diary = 2/3 ceiling → ≤1 nudge; oldest session wins. |
| 2026-08-09 | S13 no TTS reply | Diary is a monologue; spoken reply would double cost and turn it into a conversation. |
| 2026-08-09 | S13 `DIARY_MAX_SECONDS=90` (separate from M3’s 120) | ~60s ask with headroom; caps Whisper at 1.5 min without lowering partner turns. |
| 2026-08-09 | S13 hard cap 2 corrections in code (`[:2]`) before `record_errors`/`render` | Volume over precision; model returning 6 must yield 2 rows. |
| 2026-08-09 | S13 full transcript discarded (never in `sessions.payload` / logs); quoted fragments in `errors.you_said` retained like every other source | PRD §10: audio deleted after STT; error journal *is* the product — not a diary archive. |
| 2026-08-09 | S13 never mines chunks from diary | Chunks → S7 TSV → Anki → may sync AnkiWeb; diary is the last material for that path. |
| 2026-08-09 | S15 routes on `filters.FORWARDED` (PTB 22.8: `forward_origin`; no `forward_date`) + `/capture <text>` at registration — never a broad TEXT filter that decides internally | Plain-text capture would swallow M2 (S3 OpenQuizFilter outage shape). A forward is unambiguous third-party text. |
| 2026-08-09 | S15 capture registers after quiz choice / before gap `quiz_text` and correction; interests/book CHs stay later | Forwards must not be graded as gap answers. Ordinary typed CH answers lack `forward_origin` so they cannot match; a mid-flow forward is intentional capture, not “Other” free text. |
| 2026-08-09 | S15 lives in `handlers/capture.py`, not `correction.py` (ARCHITECTURE §3 tree comment overridden) | Constraint: do not modify `correction.py`; M2 must stay a clean text owner. |
| 2026-08-09 | S15 never writes `errors` despite schema CHECK allowing `source='capture'` | Forwarded English is someone else’s production; journaling it would poison spacing, weekly test, calibration, Sunday report (ARCHITECTURE principle 3). Chunks only. |
| 2026-08-09 | S15 `chunks.source = 'capture'` (literal); adaptive 1–5 chunks (~1 per 40 words, never pad) | Distinct from `reading_17` / `book_unit_12` in Anki. Reading’s fixed 5 assumes 300–400 words — wrong for a Slack line. |
| 2026-08-09 | S15 does not persist the full forward body; stores only mined `chunk` / `full_sentence` / `meaning` | Feature needs patterns, not a third-party email archive (PRD §10). |
| 2026-08-09 | S15 accepts that `full_sentence` still leaves the box: DB → S7 TSV → Telegram → Anki → may sync to AnkiWeb; prompt prefers generic carriers (no names/amounts/companies when a neutral sentence teaches the same pattern); no code redaction | Deliberate export path, not an emergent leak. User controls Anki sync. Prompt + test document the mitigation. |
| 2026-08-09 | S15 `chunks.track` defaults to NULL when omitted/invalid — never invent `'work'` | CHECK permits NULL; inventing work would systematically bias a marketing user’s tags. No consumer requires track on chunks. |
| 2026-08-09 | S15 length gates: under 20 warm short, over 4000 warm long, no LLM; empty forward silent / bare `/capture` usage hint | Capture is intentional and longer than M2’s 1000; 4000 ≈ one dense page, cost bounded. |
| 2026-08-09 | S15 text-only; forwarded photos/captions out of scope | Vision path has its own failure modes (S6); follow-up candidate. |
| 2026-08-09 | S15 no `sessions` row, no `bot_message_counts`, `has_session_on` untouched | User-initiated; must not claim quiz/reading slots or affect streaks. |
| 2026-08-08 | S18 alert channel = Telegram DM to `OPERATOR_TELEGRAM_ID`; second channel (email/PagerDuty) deferred until Hetzner | Same bot token already reaches the operator; no new infra while the process runs on a laptop. |
| 2026-08-08 | S18 alert throttle = **15 minutes**, keyed by `(exc_type, handler)`, persisted in `{RUNTIME_DIR}/alert_throttle.json` | A 5‑min poll or per-user tick would flood; in-memory alone resets on every diagnostic restart — exactly when mute risk is highest. |
| 2026-08-08 | S18 operator alerts do **not** increment `bot_message_counts` | PRD §7 rule 9 caps learning messages. Operator and learner currently share one chat — **throttling** protects that chat, not the ceiling of 3. |
| 2026-08-08 | S18 heartbeat touches `last_job_fire` only after **successful job completion**; hourly checker never touches | Start-touch hides hangs; at 26h no legitimate job runs long enough for completion-only to false-alarm. Silent APScheduler drops and hung jobs both go stale. |
| 2026-08-08 | S18 heartbeat is in-process (+ `scripts/heartbeat.py` CLI for future cron) | Catches “process up, jobs not firing.” Cannot detect total process death — needs external checker; out of scope on laptop. |
| 2026-08-08 | S18 runtime artifacts under `RUNTIME_DIR` default `$HOME/english-bot-runtime` (last_job_fire, throttle JSON, bot.log, bot.lock) | Same reason as S4b: private data / PID / logs must not live inside the git tree. |
| 2026-08-08 | S18 single-instance guard = `fcntl.flock` on `bot.lock` | Kernel drops the lock when the holder dies — stale PID files cannot block forever. Works on macOS and Linux. |
| 2026-08-08 | S18 logs/alerts: `user_id` + handler + exception only — never message bodies, transcripts, or image bytes | PRD §10; error journal is private writing. Existing LLM `raw=` truncate (300) stays. |
| 2026-08-08 | S18 `/stats` omits M13 fossil-sweep from learner view; optional ops line only when `user_id == OPERATOR_TELEGRAM_ID`; calibration kept | Sweep must stay indistinguishable from ordinary questions — leaking pending retests changes answers and destroys the measurement. Level/accuracy are actable and not designed to be hidden. |
| 2026-08-08 | S18 pause-day Missed: pre-pause incomplete quiz still rolls over as Missed (`streaks.py` untouched); pure pause days are Neutral and do not feed rescue | Quiz was delivered before pause — pause stops future sends, not history. Feels harsh vs rule 4; pin with a test. Forgiveness would be a separate slice. Neutral no-session pause days break consecutive-Missed for rescue. |
| 2026-08-08 | S11 weekly test **replaces** Sunday morning quiz (`task_type='quiz'`, 15Q) — does not add a fourth bot-initiated message | Sunday was already at the hard ceiling of 3 (quiz + Anki + report). Yielding would silently suppress the test; a weekly test that skips itself is not a weekly test. |
| 2026-08-08 | S11 Anki export moved from Sunday to **Saturday** evening | Nothing about the export needs Sunday; frees Sunday to weekly test + report = 2, leaving a nudge slot. Supersedes S10 “report beats Anki on last Sunday slot.” |
| 2026-08-08 | S11 `mark_result` applies to weekly-test error answers (including not-yet-due) | Genuine evidence either way; the alternative (test without recording) would make the weekly test the only place answers don’t count. Book-sourced answers still journal (S6a fork). |
| 2026-08-08 | S11 rescue skips the weekly test — Sunday in rescue stays a normal 3Q day | PRD §7 rule 7: no backlog. A 15Q Sunday is the opposite of re-engagement. |
| 2026-08-08 | S11 Murphy range match: expand `'69-81'` / `'5-6,11-14'` to unit-number strings; overlap with `book_units` where `book='murphy'` → “already studied”, else “new”; skip NULL `murphy_units` | `unit_number` is TEXT; ranges must expand. Uses S10 `top_error_types` for order — no second aggregation. |
| 2026-08-08 | S11 quiz gen `max_tokens=7500` when ≥10 questions; else 2500 | 15Q is ~3× the 5Q JSON payload; 2500 truncates. |
| 2026-08-08 | S11 `plan_formats` generic path places gaps at evenly spaced indices; `typed_gap_count` gate is `n==5` only (n=3/5 pinned unchanged) | Old `gaps_left >= slots_left - taps_left` front-loaded all gaps (six in a row for n=15). Rescue/daily mixes stay byte-identical. |
| 2026-08-08 | S11 calibration window **excludes** `payload.weekly_test` | Coverage set draws not-yet-due (easier) errors and is half the 30Q window — would ratchet `cefr_level` on non-representative material. Same spirit as excluding `book_test`. |
| 2026-08-08 | S11 with weekly excluded, Sunday contributes **no** calibration evidence: if Sunday is the only completed session, no `calibration_log` row and that day does not count toward ≥8-of-14 raise | A non-representative session should neither raise nor block. A user who only ever does Sundays can never be calibrated — intended, not a bug. |
| 2026-08-08 | S12 rolling “30-question” accuracy = session-aggregate walk over completed `quiz`+`reading` (`correct_count`/`answered` or `score×n`), newest-first until ≥30 answers (may slightly overshoot). Not a true per-question event stream — `mark_result` has no timestamps and quiz payloads lack per-question outcomes. | No migration; honesty over false precision. Known issue #20. |
| 2026-08-08 | S12 calibration window excludes `book_test` | `/test` is user-chosen material; easy self-selected units would inflate accuracy and raise `cefr_level` on choice rather than ability. Book answers still journal / feed the ladder. Hook gates on `task_type=='quiz'` despite shared `_advance_after_answer`. |
| 2026-08-08 | S12 daily `calibration_log` upsert (SELECT then INSERT/UPDATE) when sample ≥30; same-day second completion refreshes `accuracy_30` | First-write-wins would discard the day’s full evidence; a change row already written today is preserved when only accuracy refreshes. |
| 2026-08-08 | S12 raise = last 14 local days, **≥8 logged days**, every log (and today) `>85%`, current window `>85%`. Skipped days are not failures. Min 8 ≈ rule-6 5/7 over a fortnight (exact pace ≈10). | Consecutive 14 active days contradicts PRD §7 rule 6 and would make raise dead code. |
| 2026-08-08 | S12 drop when current window `<70%` (no multi-day sustain); cooldown 14 days after any level change; bounds A2–C1; min sample 30 before any change | PRD states two weeks only for raises; hysteresis prevents day-after oscillation; A2/C1 match onboarding/EF bands without inventing C2 pitch. |
| 2026-08-08 | S12 **raise announced** (warm, ceiling-aware; skip message + WARNING if at 3, level still changes); **drop silent** (log + apply, never message) | Raise is earned progress; announcing a drop is guilt (PRD §7 rule 4) and punishes a bad fortnight. |
| 2026-08-08 | S12 M13: monthly poll (with freeze) queues ≤2 aged resolved rows (`resolved_at` ≤ today−30) into `fossil_sweep` session `{pending,done}`; inject 1/quiz; **skip entirely in rescue**; correct → `done` only (**never mutate `resolved_at`**); wrong → existing `mark_result` un-resolve | `resolved_at` bump would fake “newly quiet” on Sunday (S10). Rescue must not spend 1/3 of a 3Q re-engagement ask on sweep material. No migration for last_retested_at. |
| 2026-08-08 | S12 un-resolving one row drops that type from S10 `resolved_types` (all-clear) — intended | M13 exists to prevent the illusion of progress the Sunday lead would otherwise keep showing. |
| 2026-08-08 | **Contract from S6 onward:** Cursor prompt + PRD is the slice contract; no `specs/S10-*.md` (same as S6/S6a/S7/S9c). Decisions log is the source of truth. **`.cursorrules` still says stop if specs/ is missing — amend it separately; S10 does not edit `.cursorrules`.** | A parallel spec file drifts; Amirhossein amends the constitution deliberately. |
| 2026-08-08 | S10 nudges only `quiz` and `reading` | `book_test` is user-initiated (nagging); voice has no scheduled delivery; `free_practice` is a soft empty-journal day. |
| 2026-08-08 | S10 “Just do 2” sets `payload.early_limit=2`; completes at 2 answers with `score = correct_count / 2.0`; remainder ungraded (stay due) | A button that promised less work and still delivered 5 would be worse than no button (PRD §7 rule 3). |
| 2026-08-08 | S10 rescue second nudge still offers “just do 2” | Rescue is already 3Q; 2 of 3 is a real cut. Offering “just 1” invents a third ladder step PRD does not define. |
| 2026-08-08 | S10 `resolved_types` = all-clear (every row of that type resolved; ≥1 row) — not “any instance resolved” | One resolved + nine unresolved must not lead the Sunday report; that is the illusion of progress M13 exists to prevent. |
| 2026-08-08 | S10 Sunday active-days copy: `N < 5` → “N of 5”; `N >= 5` → “{n} active days — full week” (no denominator) | Rule 6 forbids judging against 7; `7/5` is nonsense above target. |
| 2026-08-08 | S10 Sunday report poll `first` before Anki; report wins last ceiling slot; Anki yields (`/anki` escape hatch) | Report has no manual equivalent; weekly Anki is recoverable. Nudges are not specially disabled on Sunday — full quiz+Anki+report leaves zero room by rule 9 (expected, not a bug). Mon/Wed/Fri quiz+reading spend 2 of 3 ceiling slots, so the 2-nudge daily budget is only reachable on non-reading days. |
| 2026-08-08 | S10 Sunday report assembled without an LLM | Deterministic DB facts cannot hallucinate progress; free; warmth is templates only (`why_statement` only if under 400 chars). |
| 2026-08-08 | S10 daily nudge cap = `SUM(nudges_sent)` on session delivery date (max 2/day ever); per-session ladder still +3h/+6h via `nudges_sent` | PRD §7 rule 3 wins over “per unfinished task” wording in the prompt intro. |
| 2026-08-08 | S6a: `/test` uses `task_type='book_test'`, never `'quiz'` | Fake quiz rows corrupt completion rate, streak Missed-detection, and the 14-day gate (2026-08-03). `has_session_on` stays scoped to `('quiz','free_practice')` so `/test` cannot cancel the next morning quiz. |
| 2026-08-08 | S6a: `/test` answers are **taps only** — no text MessageHandler; callbacks use `btest:` | Widening `OpenQuizFilter` or owning free text would re-swallow M2 (S3 live outage). Dispatch-tested: open mid-set `book_test` → plain text reaches correction. |
| 2026-08-08 | S6a: top-up walks `book_units` by `studied_at DESC`, exhausting each unit before the next | User photographed units because they are studying them now; recency is the signal. |
| 2026-08-08 | S6a: selection-time near-dedup (casefold + whitespace + strip parentheticals; substring if shorter ≥8) — do not rewrite stored rows | Known issue #14: exact-string union leaves “Present continuous” beside “present continuous (I am doing)”. Fixing at selection avoids a migration and keeps OCR history intact. |
| 2026-08-08 | S6a: word-bank heuristic = `^(verbs?\|nouns?\|…)\s*:` **or** ≥4 short comma tokens **after stripping parentheticals** | Live dry-run on 41 Murphy items: excludes only `verbs: cross, hide, scratch, take, tie, wave`; keeps stative-verbs-with-exemplars and irregular-verbs lists. Comma arm on the full string falsely excluded unit 5 irregular verbs. |
| 2026-08-08 | S6a: zero due + usable book items → morning `quiz` (not `free_practice`). **On a zero-due-error day where book items exist, an ignored morning quiz now costs a freeze where it previously stayed Neutral.** | PRD M1 top-up; a real task was delivered. Zero due and no book items still → `free_practice` / Neutral. `streaks.py` untouched; behaviour pinned by tests. |
| 2026-08-08 | S6a: wrong book-sourced answers → `record_errors(source='quiz')`; never `mark_result`. Unknown `error_type` → WARNING + skip | Book questions have no prior `errors` row. Taxonomy guard matches correction — a bad type poisons the journal permanently. Fork lives in `_advance_after_answer` so typed gap and tapped paths both hit it. |
| 2026-08-08 | S6a: new `/test` marks prior incomplete `book_test` completed-as-abandoned (`score=NULL`) | Abandoned mid-sets would accumulate forever; reuse is error-prone with message_id. NULL = not assessed (same signal as S9c legacy skip). |
| 2026-08-08 | S9c: all comprehension answers are **taps only** — no reading branch in `correction.py` | Typed answers would fall through to M2 and poison the error journal with comprehension guesses. Free text during an open reading still reaches correction (dispatch-tested). |
| 2026-08-08 | S9c: `reading.txt` questions are MCQ `{q, options[4], answer_index, why}` (why ≤25 words) | PRD §8 explanations; grading is deterministic index compare — no second LLM call. Generation validator enforces the shape; delivery uses soft `parse_stored_questions`. |
| 2026-08-08 | S9c: resume state in session `payload` with required `phase` (`questions`\|`rating`) | `bot_data` dies on restart (S3). Skip-to-rating never enters `questions`, so `phase` cannot be inferred from `q_index == 5`. |
| 2026-08-08 | S9c: resolve session by `payload.message_id` + `chat_id` from the callback message | “Any open reading” would let orphan session 803 (reading 17, no message_id) steal Monday’s Questions tap and rate the wrong topic. |
| 2026-08-08 | S9c: on edit BadRequest other than “not modified”, resend as a new message and update `message_id` | Next-day / deleted-message edits are expected (PRD §7 rule 2); a silent dead button is worse than a new message. No `bot_message_counts` — reply to a tap. |
| 2026-08-08 | S9c: rating→weight is **additive** (`1→−0.30 … 5→+0.30`) clamped `[0.25, 3.00]` | Multiplicative decay would bury a topic after one bad evening; S9a selection still resurfaces floor-weight topics. Removal stays the user’s job via `/interests`. |
| 2026-08-08 | S9c: legacy/malformed questions → WARNING + skip to rating with **`score = NULL`** | Reading 17 still has `question`/`answer`/`distractors`. Zero would mean “0/5” and poison S12 rolling accuracy — NULL means not assessed; later consumers must not treat NULL as 0. |
| 2026-08-08 | S7: export reads **`chunks` only** — do not export `book_units.target_items` | Book items are grammar concepts ("am/is/are + -ing"), not sentences; no carrier sentence → poor cloze cards. A later slice can generate sentences for book items if wanted. |
| 2026-08-08 | S7: sanitise **all four** TSV fields (tab→space, CR/LF→space, collapse whitespace, strip) before write | A literal tab is a field break and a newline is a row break in Anki; one dirty subtitle/reading chunk silently shifts every field after it. |
| 2026-08-08 | S7: mark `exported_to_anki` + insert `anki_export` session inside a txn held across `send_document` (commit only after send) | Same as S9a: a failed send that already marked rows loses those cards permanently — they are never re-offered. |
| 2026-08-08 | S7: weekly idempotency via `sessions` row `task_type='anki_export'` + `has_anki_session_on` (poll pattern, not per-user job) | Second Sunday poll tick must send nothing; polls survive restarts and pick up new users (S3 decision). |
| 2026-08-08 | S7: `/anki` is user-initiated — no `bot_message_counts` increment; weekly document is bot-initiated and respects the ceiling of 3 | PRD §7 rule 9 caps bot-initiated messages; manual export must stay testable even when the day is full. |
| 2026-08-08 | S3: `OpenQuizFilter` matches only when the open quiz’s **current** question `format == "gap"` | Root cause of live “free text after /book Done does nothing”: incomplete quiz at `choice` (session 1133) — `on_quiz_text` returned silently on non-gap while `block=True` stopped correction. Survives restart (DB). Not the book ConversationHandler: `COLLECT_PAGES` has no TEXT handler; nested Done `map_to_parent END→END` does end the parent (verified). Present since non-gap formats landed — intermittent dark M2 and unrecorded journal gaps. |
| 2026-08-08 | S3: rejected soft-nudge on non-gap typed text; accept that typing during choice/order/spot yields a **correction**, not a grade | A nudge still consumes the update and blocks M2 — same outage with better manners. Buttons remain the answer path (PRD §8). Do not “restore” the broad filter later. |
| 2026-08-08 | S3: leave incomplete quizzes incomplete (do not forge `completed` to unblock M2) | Forging completion marks the day Active and corrupts completion rate / 14-day usage (2026-08-03 — same reason zero-due days use `free_practice`). After filter narrowing, non-gap open quizzes are harmless. |
| 2026-08-08 | S6: do **not** poke `ConversationHandler._conversations` from JobQueue; do **not** move Done/Add more to parent entry points | Private PTB internals are upgrade-fragile; CallbackQuery entry points on `per_message=False` reintroduce the S1a `PTBUserWarning`. Open book CH does not block correction; `collecting=False` already gates late photos. Abandoned flows: 1h `conversation_timeout` + TIMEOUT clears `user_data["book"]` (PTB nested-timeout caveat noted; never silence the warning). |
| 2026-08-08 | **Standing rule:** any change to `llm.py` request construction requires **one real API call** before it ships | Mocked tests cannot express the provider contract. Prefill shipped green under mocks and broke every live `json_mode` caller (`action=skipped_llm` on morning quiz). |
| 2026-08-08 | S6 fix: assistant `{` prefill **removed** entirely (initial + repair); every request must end on a user message | Hard provider constraint: `claude-sonnet-5` returns 400 `invalid_request_error` — "This model does not support assistant message prefill. The conversation must end with a user message." Do not reintroduce trailing-assistant prefill. |
| 2026-08-08 | Why the earlier "repair already uses prefill" claim was wrong | The repair path never prefaced the API call with a trailing assistant `{`. It appended `assistant=<bad text>` then `user=<repair instruction>`, so the request **ended on a user turn**. Mid-conversation assistant messages are fine; ending on assistant is not. The 2026-08-07 decision conflated those two shapes. |
| 2026-08-08 | S6 fix: tolerant JSON extraction in `_parse_json` (strip ``` fences; first `{`…last `}` span) instead of request-shape constraints | Original OCR failure was prose-around/instead-of-JSON (~96 tok). Prefill was the wrong lever and broke the API. On total failure (no `{` / span won't parse): WARNING + truncated `raw=` + `LLMError` — never fabricate `{}` or empty `target_items`. |
| 2026-08-08 | S6 summary: >4 failed pages collapse to `All N pages`; CTA singular/plural (`that page` / `those pages`) | Long enumerated lists are unreadable; singular CTA contradicted plural page lists. |
| 2026-08-07 | ~~S6 fix: `json_mode` appends assistant `{` prefill on **every** call~~ — **REVERTED 2026-08-08** | Claimed Anthropic already accepts trailing assistant via repair; that was false (see above). Live blast radius: correction, quiz, reading, voice, book OCR. |
| 2026-08-07 | S6 fix: JSON parse failures log/raise with first ~300 chars of raw response text (permanent) | Parser message alone (`Expecting value: line 1 column 1`) is unfixable without a live repro; next `/book` must show whether the model wrote a legibility complaint or a **copyright/textbook refusal** (two ~96-token calls are consistent with either — if refusal, stop and report; do not tune toward silent empty `target_items`). Never log image bytes. |
| 2026-08-07 | S6 fix: `book_ocr.txt` forces structural `readable: false` (never prose); handwriting excluded from `target_items`; rotation alone ≠ unreadable; personal-use scope stated | Model explained instead of returning the failure object; filled-in Murphy pages will recur; PRD §5 M5 is personal-use study extraction. |
| 2026-08-07 | S6 fix: summary uses `Page`/`Pages` agreement; unreadable vs snag kept; both CTAs unify to “re-shoot that page, one page per photo” | User cannot act differently on either failure path; singular “Pages 1 …” was wrong. |
| 2026-08-07 | S6: album debounce cancels prior jobs via `get_jobs_by_name` + `schedule_removal` before `run_once` (~2.5s); `process_pages` pops `pages` and bails if empty or `processing` | PTB `name=` does not replace jobs — ten album updates would schedule ten runs and race on `user_data`. Mid-fire removal is not guaranteed, so the pop/`processing` guard is required. |
| 2026-08-07 | S6: after batch, summary with Done / Add more pages; Done callback returns `ConversationHandler.END`; `collecting` cleared by the job | JobQueue cannot return `END`; leaving CH in `COLLECT_PAGES` would swallow later photos / risk free-text not reaching correction. |
| 2026-08-07 | S6: pages past 20 set `over_cap` and drop silently; one summary line, no per-photo refusal | A 25-photo album would otherwise spam five refusal messages. |
| 2026-08-07 | S6: book identity is the user's button/slug (`murphy` / `vocabulary_in_use` / `marketing` / slugified Other), never the LLM | OCR guesses the book from a page; the user knows. Slug makes S6a `/test unit N` match reliable. |
| 2026-08-07 | S6: `target_items` is a flat `list[str]` of short grammar/vocab items | Contract for S6a / quiz top-up; nested shapes are expensive to change once rows exist. |
| 2026-08-07 | S6: re-ingest upserts in app code (SELECT then UPDATE union / INSERT); no unique constraint / no migration | Schema forbids 004 in this slice; second `/book` on the same chapter must not double rows or double S6a weight. |
| 2026-08-07 | S6: continuation pages (`unit_number` null) merge into the latest non-null unit in-batch; orphan before any unit → WARNING + skip + named in summary | Guessing a unit for an orphan invents journal noise. |
| 2026-08-07 | S6: failure summary names batch-position page indexes, never OCR-read page numbers | User can identify and re-shoot; a bare count hides systematic OCR failure. |
| 2026-08-07 | S6: `llm.py` embeds images into messages before the first call so json_mode repair re-sends image blocks | A repair that drops the image silently degrades to a text-only guess. |
| 2026-08-07 | S6: batch INFO logs page count / units written / pages failed only; per-call tokens stay in `llm.py`; `chat()` return type unchanged | Provider usage is already logged per call; inventing image-token estimates would be fiction. |
| 2026-08-07 | S6 ends at `book_units` rows; `/test unit N` and quiz top-up are S6a | TASKS S6 bundled both; splitting matches S3→S3d vertical-slice pattern and keeps this slice shippable. |
| 2026-08-07 | S6 `/book` replies do not increment `bot_message_counts` | User-initiated; PRD §7 rule 9 caps bot-initiated messages (same as S5 voice). |
| 2026-08-07 | Standing rule — every slice ends with a `BUILD_PROGRESS.md` update (slice row, decisions with reasons, known issues, file inventory, Next action carrying forward every unrun check) | This file is the only memory between sessions; a stale file causes settled work to be re-litigated. |
| 2026-08-07 | S9c split from S9a — comprehension delivery, grading and the 1–5 rating are their own slice | Chunks unblock S7 before the Q&A UX lands. |
| 2026-08-07 | Quiz `order`/`choice`: options as numbered list in the message body; buttons are `1`–`4` only. Permanent ≤20-char button-label rule in `.cursorrules` | Live: Telegram truncates full-sentence button labels ("I went to Vilnius l...for a conference") — question unanswerable. Restates S3b (body reads / buttons tap). Spot tiles stay single words (audit: gap has no buttons; spot under contract stays ≤20). |
| 2026-08-06 | S9a: scheduled LLM via `asyncio.to_thread`; evening job `first=EVENING_FIRST_SECONDS` (mid-interval) | Live 2026-08-06: morning quiz LLM blocked the event loop ~17s; APScheduler skipped the evening poll (jobs were only 5s apart). Soft to the user looked like "reading never fires." |
| 2026-08-04 | Split TASKS S9 into **S9a** (delivery + chunks) and **S9c** (comprehension + rating) | Chunks unblock S7 Anki before Q&A UX lands; same vertical-slice pattern as S3→S3d. S9 itself stayed interests-only. |
| 2026-08-04 | S9a: commit readings/chunks/session only after Telegram send succeeds (txn held across send) | A send failure after persist would poison the chunk pool with text the user never read; Anki (S7) would export untraceable cards. Day stays unclaimed → next 5-min tick retries. |
| 2026-08-04 | S9a: chunk-in-body check normalises casefold / whitespace / apostrophes+quotes; store model text as-is | Strict `in` rejects valid capitalised / curly-apostrophe chunks; retry then silent-skip wasted the day. |
| 2026-08-04 | S9a: NULL `last_used` scores as 30 days; exact score ties → alphabetically first topic | Huge NULL constant drowned weight/track_weights; argmax over ties was DB-order-dependent. |
| 2026-08-04 | S9a: every skip path logs WARNING with user_id + reason (ceiling, no interests, LLM, validation) | Soft to the user, loud to the operator (ARCHITECTURE principle 4) — a quiet no-op is indistinguishable from a working engine. |
| 2026-08-04 | S9: `/interests` is a standalone ConversationHandler, not an onboarding extension | Partner not yet onboarded; the S1 wizard is verified and must not be re-opened. TASKS "onboarding extension" wording overridden for this reason. |
| 2026-08-04 | S9: callback_data carries option indexes (`int:tw:3`), never topic text; option lists live in `user_data` | Telegram 64-byte limit; free-text topics can contain `:` (S1b colon-split bug) or be arbitrarily long. |
| 2026-08-04 | S9: Change preload rebuilds option lists as presets + stored non-presets so customs stay toggleable | Without that, a no-op Change→Done silently deletes "Something else" topics because save writes `user_data` only. |
| 2026-08-04 | S5a: honest stage names (listening / thinking / recording) over a percentage or ▓▓▓░░░ progress bar | Stage durations are unpredictable (Whisper on 60s ≫ 10s); a bar that stalls at 80% reads as a crash. |
| 2026-08-04 | S5: day-state precedence Active > Missed > Neutral over **all** sessions for the local day (not latest row) | After voice no longer blocks quiz delivery, voice-then-ignored-quiz left an incomplete quiz as latest and burned a freeze on a day of real usage — inverts PRD §4 and can push engaged users into rescue. |
| 2026-08-04 | S5: freeze notice keeps remaining count when tokens > 0; omits inventory clause when zero | "One left" is informational; "None left this month" scores scarcity and violates PRD §7 rule 4. |
| 2026-08-04 | S5: voice sessions marked `completed=TRUE` as soon as an exchange succeeds | Abandoned mid-conversation must not leave an incomplete row that rollover could misread; live conversation is found by recency + turn count, not `completed`. |
| 2026-08-04 | S5: morning `has_session_on` scoped to `task_type IN ('quiz','free_practice')` | A 07:40 voice message must not silently cancel that day's quiz. |
| 2026-08-04 | S5: voice replies do not increment `bot_message_counts` | PRD §7 rule 9 caps bot-initiated messages; voice answers are replies to the user. |
| 2026-08-04 | S5: max 3 corrections per voice turn | Spoken turns generate more errors; a six-item wall ends the conversation. Untaken errors recur naturally. |
| 2026-08-04 | S5: conversation window 120 min since last turn, hard cap 10 exchanges | Past either, next voice starts a fresh session. |
| 2026-08-04 | S5: voice >120s declined before download; TTS failure falls back to text reply | M3 is conversation not monologue (S13); losing the turn is worse than losing audio. |
| 2026-08-04 | S4b: refuse `BACKUP_DIR` inside the git repo | Dumps contain the user's private writing (PRD §10); a path under the repo is one `git add` away from a leak. |
| 2026-08-04 | S4b: 10 KB sanity floor before counting a dump as success | A 0-byte / tiny file that silently replaces a good backup is worse than no backup; never prune on failure. |
| 2026-08-04 | S4b: restore defaults to `english_bot_restore_test`; live `english_bot` needs `--force` | An untested backup is not a backup — and a careless restore must not destroy production. |
| 2026-08-04 | S4b: off-site copy left as a documented stub (`offsite_copy_stub`) | TASKS requires independent storage; this slice must not add cloud credentials. Options: rsync / rclone / manual weekly copy. |
| 2026-08-03 | S4: 03:00 **local** rollover (15-min poll), never UTC midnight | PRD §7 rule 1 — Monday's quiz stays open until 03:00 Tuesday. UTC midnight would close Vilnius days mid-evening and break streaks for completions that were still on time. |
| 2026-08-03 | S4: no `roll_over_day` on quiz complete; show `current_streak+1` optimistically | Early evaluation advances `last_evaluated_date` and can close the next day before its quiz is delivered. Real evaluation is only the 03:00 job. |
| 2026-08-03 | S4: idempotency via `streaks.last_evaluated_date` | Freeze-covered misses do not move `last_active_date`; without a separate marker a second rollover would consume another freeze. |
| 2026-08-03 | S4: backfill capped at 30 days; ≤50 users per streak poll tick | A two-month absence must not run 60 sequential rollovers inside one tick or starve other users. |
| 2026-08-03 | S4: freeze-covered missed days still count toward rescue | A freeze protects the streak number; it does not mean the person engaged. Rescue exists to re-engage. |
| 2026-08-03 | S4: no-session days are Neutral | Do not break the streak for a day the bot never asked about (paused / not yet onboarded). |
| 2026-08-03 | S4: incomplete `free_practice` = Neutral; completed (via correction) = Active | Empty journal is success, not a miss — burning a freeze is backwards. But using M2 that day *is* activity; correction marks the open free_practice session completed so rollover needs no special branch. Only permitted change to `correction.py`. |
| 2026-08-03 | S4: monthly freeze reset is per-user local 1st via `freeze_reset_on` | Users in Tokyo and Vilnius reach the 1st at different UTC moments; a global sweep would reset some early and some late. Unused tokens do not carry over. |
| 2026-08-03 | S4: rescue window is fixed 7 days from entry; further misses do not extend it | "Runs its 7 days" — completing early does not clear it; extending on every extra miss would never end. |
| 2026-08-03 | S3d: hard 2 typed (gap) / 3 tapped per 5-question quiz | Production practice matters (4-option guess is 25% right by chance), but daily completion matters more — PRD §7 is built around not abandoning; an easier quiz done every day beats a harder one abandoned. |
| 2026-08-03 | S3c: one everyday scenario per quiz (shared people/places); avoid past scenarios from session payload | Five unrelated sentences felt like a worksheet; a thread makes the quiz feel like a conversation. |
| 2026-08-03 | S3c: spoken-register rule (≤12 words, text-message test, conversations about work not documents) | Live sentences read like reports ("the museum team…"); people don't talk that way. |
| 2026-08-03 | S3c: remove reorder tile format; replace with `order` (4 full-sentence word-order choices) | Failed twice in live testing — a 3-column button grid gives no visual signal that tiles form one sentence. Chat grids can't express a sentence; full options on their own rows can. |
| 2026-08-03 | S3b: spot sentences capped at 8 words in the generation prompt | Nine tiles = three button rows; too much to scan on a phone. |
| 2026-08-03 | S3b: message body is for reading; buttons are only for tapping | Live bug: spot/reorder existed only as a tile grid — the sentence was unreadable. |
| 2026-08-03 | S3a: past prompts read from prior quiz `sessions.payload` (last 3 per error_id) — no new column | Payload already stores every question; a column would duplicate data and need a migration for no gain. |
| 2026-08-03 | S3a: four formats (gap/choice/reorder/spot), not more multiple-choice | Reorder and spot keep tapping without collapsing to 25%-guess recognition; gap still forces production. |
| 2026-08-03 | S3a: quiz sentences distributed by `track_weights` (interleaved) | PRD §6 — all-work quizzes ignore the weight the user set at onboarding. |
| 2026-08-03 | S3a: user-facing copy uses `error_types.label`, never the code | Live bug: "quantifier_modifier is getting steadier" — database codes are not language. |
| 2026-08-03 | S3: morning eligibility uses the user's **local** date/time (minute precision); every eligibility fn takes explicit `now` | Server UTC midnight ≠ Vilnius local; without local today a user can get two quizzes around UTC midnight. Tests must not touch the wall clock. |
| 2026-08-03 | S3: `bot_message_counts(user_id, local_date, count)` table — not session-row counting | PRD §7 rule 9 caps **messages**. S10 nudges are not sessions; counting sessions would under-count. Increment on every bot-initiated send. |
| 2026-08-03 | S3: quiz-active state from incomplete `sessions` (`task_type='quiz'`) + `payload` JSONB — never `bot_data` | `bot_data` dies on restart; a typed answer would fall through to correction and poison the journal. |
| 2026-08-03 | S3: zero due errors → `task_type='free_practice'` session (not `'quiz'`); selection blocks on **any** session that local day | Fake quiz rows corrupt completion-rate / streak / 14-day gate. Distinct type claims the slot, stops the 5-min loop, counts toward the message ceiling. |
| 2026-08-03 | S3: one 5-minute JobQueue poll (APScheduler via PTB), not per-user jobs | Survives restarts, picks up new users, implements PRD §7 rule 1 (delivery times, not deadlines). |
| 2026-08-03 | S3: gap-fill default question format | Production beats recognition. |
| 2026-08-03 | S3: grading by normalised string match against `accept`, no second LLM call | Deterministic, free, and the accept-list is the contract. |
| 2026-08-03 | S2: `claude-sonnet-5` (~$3.40/mo at ~900 corrections) over Haiku (~$1.20) | Wrong `error_type` poisons the journal permanently; ARCHITECTURE principle 3 treats the journal as the product itself. Two euros/month is not worth weaker taxonomy accuracy. |
| 2026-08-03 | S2: keep schema row-level `resolved`/`streak_right`; compute type-level "resolved" by aggregation in S10/S11 | PRD §3 defines resolved per error *type*; schema stores it per error *row*. Spacing (S3) needs per-instance rows; reporting aggregates later. No schema change. |
| 2026-08-03 | S2: length gates — under 10 chars silent, over 1000 → TEXT_TOO_LONG | Short ack messages (`ok`, `thanks`) must not spend API money; essay-length input is outside M2's "ordinary usage" frame and is where cost runs away. |
| 2026-08-03 | S2: keep `cache_control`; confirmed working after prompt grew | First system prompt was ~611 tokens (under Sonnet’s ~1024 floor). Two extra worked examples pushed it over; live calls show call1 `cache_creation=1641` / call2 `cache_read=1641`. |
| 2026-08-03 | S2: `did_well` prefixed with blank line + 👍 | Without a marker it read as part of the last correction block. |
| 2026-08-03 | S2: additive `explanation_language_fallback` on `User`/`get_user()`; `save_onboarding` untouched | Correction prompt needs the flag; read-path layering belongs in `users.py`. Onboarding write path and its tests stay unchanged. |
| 2026-08-03 | S1d: shared `layout_buttons` (≤12 chars to share a row); emoji on options; static reaction line after each choice; celebration sticker skipped | Truncation made step 5 unreadable; reactions make the bot feel like a partner. No stable public sticker `file_id` without bundling a file or adding a dependency — message count stays **2**. Further onboarding polish → S18 backlog. |
| 2026-08-03 | S1c: EF SET "Not yet" → CEFR can-do self-assessment (A2/B1/B2), not silent B1; domain is category→specific drill-down (store specific, lowercased); why options describe real situations (meetings, friends here, freezing up) | Silent B1 mis-pitches all content until S12. Broad domains ("Marketing") starve S9/S14. Generic why clauses motivate nobody when S10 quotes them back. Immigrants in Vilnius need local/work stakes in the list. |
| 2026-08-03 | S1b: replace S1/S1a multi-bubble onboarding with a single-message `edit_message_text` wizard | Message accumulation made onboarding read as a transcript wall; echoing answers (S1a) made it taller. Forced free-text for why produced weak data (`social talking`) that S10 must quote — presets yield better sentences. PRD §8 already required buttons over typing. |
| 2026-08-03 | S1b: ParseMode.HTML + `html.escape` on user-supplied values; ignore BadRequest "message is not modified"; time callbacks via `split(":", 2)` | Markdown breaks on `_` / `&` mid-flow; double-taps crash edits; naive colon split truncates `07:00` to `07`. |
| 2026-08-03 | S1b: native language presets add Russian + Polish; why is multi-select joined into one natural sentence | Matches local language mix; S10 quotes why verbatim so grammar must be correct. |
| 2026-08-01 | S1a: keep `work_domain` as free text with examples in the question, not preset buttons | Superseded for the common path by S1b presets + "Something else" escape hatch; specificity still available via free text. |
| 2026-08-01 | S1a: fix `PTBUserWarning` by nesting callback-only ConversationHandlers with `per_message=True` under a parent with `per_message=False` (MessageHandlers only + nested CHs) | Mixed MessageHandler + CallbackQueryHandler in one CH always warns; nesting matches how each update type is tracked. Do not `filterwarnings`. Kept in S1b. |
| 2026-07-31 | S1 open decision 5: do not ask timezone in onboarding; keep schema default `Europe/Vilnius` | Both users are in Vilnius; S20 (Generalize) must add timezone selection when assumptions are removed |
| 2026-07-31 | S1 open decision 4: second `/start` shows profile summary with Redo onboarding / Keep as is; redo overwrites `users`, never resets `streaks` | Full per-field edit is `/settings` (S18); streak history must survive redo. S1b renames buttons to Change something / Keep as is. |
| 2026-07-31 | S1 open decision 3: track weights via three preset buttons only (Balanced 40/40/20, More work 60/25/15, More everyday 25/60/15) | PRD §8 buttons over typing; fine-grained weights come from S9 ratings |
| 2026-07-31 | S1 open decision 2: EF SET step offers "Not yet"; `efset_baseline` stays NULL, `cefr_level` defaults to B1 | Test takes 50 minutes; PRD baseline is week 1, not day 1 |
| 2026-07-31 | S1 open decision 1: EF SET → CEFR uses official EF bands; PRD §3 target corrected to B2 (51–60) | PRD's "B2 (57–70)" spanned B2+C1; official B2 is 51–60 |
| 2026-07-31 | Added `app/services/users.py` to ARCHITECTURE §3 | User reads/writes needed by S2+; DB access must not live in handlers |
| 2026-07-31 | Onboarding writes nothing until Save; answers held in `context.user_data` | Abandonment leaves no partial rows; duplicate prevention stays trivial |
| 2026-07-31 | Mid-onboarding telegram ids tracked in `bot_data` for access control | Rows exist only after Save; without this, every answer would look unregistered |
| 2026-07-31 | **REVERSAL:** self-hosted PostgreSQL 16 on the Hetzner box, not Supabase | Supabase Pro is $25/mo (~€276/yr), not the €10/mo assumed in the original entry. Managed backups duplicate the `pg_dump` backup already planned (now S4b). Self-hosted costs nothing extra; application code unchanged. |
| 2026-07-31 | Migration runner uses `psycopg.ClientCursor` for applying `.sql` files | psycopg3's default server-side cursor rejects multi-statement scripts; ClientCursor uses the simple query protocol |
| 2026-07-31 | Replaced undotted `cursorrules` with `.cursorrules` | ARCHITECTURE §3 and S0 require the dotted filename Cursor reads; content rewritten to match S0's required clauses |
| 2026-07-31 | ARCHITECTURE §7 "Database file chmod 600" → credentials in `.env` mode 600 | No local DB file under Postgres/Supabase; keep the security intent |
| 2026-07-31 | ARCHITECTURE §1 "SQLite" → PostgreSQL; §5 backup job → `pg_dump` | Doc fix required by S0; matches §2 and earlier decisions log |
| 2026-07-31 | ARCHITECTURE §3 gains `specs/` | Prevent later slices treating specs as out-of-tree |
| 2026-07-31 | Local verify venv used Python 3.13 (3.12 not installed on this machine) | Runtime target remains 3.12 per ARCHITECTURE; deps install cleanly on 3.13 |
| 2026-07-31 | ~~PostgreSQL on Supabase (+€10/mo), not SQLite, not self-hosted PG~~ — **SUPERSEDED** by self-hosted PG 16 reversal above | Choosing PG now permanently removes the SQLite→PG migration risk. Supabase→self-hosted stays reversible via pg_dump. Managed backups + PITR + table editor worth €120/yr for an irreplaceable database. (Price assumption was wrong: Pro is $25/mo.) |
| 2026-07-31 | Session-mode pooler, psycopg3, no supabase-py | Direct connections are IPv6-only; transaction pooling breaks prepared statements |
| 2026-07-31 | Own weekly pg_dump in addition to Supabase backups (S18) | Never rely on a single backup system |
| 2026-07-31 | Added M16 video engine — YouTube Tue/Thu alongside sitcoms Mon/Wed/Fri | Sitcoms give only casual American English; user needs domain register and accent variety for work in Vilnius |
| 2026-07-31 | Agent runtimes (Hermes/OpenClaw) rejected as runtime; Cursor used to build | Product is a deterministic pipeline, not an open-ended task. Reliability, testability, cost, and prompt-injection surface from untrusted input |
| 2026-07-31 | HIMYM primary (Disney+/Trancy), The Office secondary (Netflix/Language Reactor) | Motivation outweighs marginal pedagogical edge |
| 2026-07-31 | Multi-tenancy architected but not built | Product unproven until users reach B2 |
| 2026-07-31 | No Telegram Premium | Irrelevant to bot capabilities |

---

## Known issues

| # | Issue | Severity | Slice | Status |
|---|---|---|---|---|
| 1 | S0 not yet executed | — | S0 | ✅ closed — verified 2026-07-31 |
| 2 | `.cursorrules` needs human review against the required clauses in `specs/S0-repo-skeleton.md` | low | S0 | ⬜ open |
| 3 | Timezone not collected in S1; all users get schema default `Europe/Vilnius`. S20 (Generalize) must add timezone selection when location assumptions are removed. | medium | S1 → S20 | ⬜ open — assumption recorded |
| 4 | System prompt was under Anthropic Sonnet cache minimum (~1024). Fixed by adding two worked examples; live verify: call2 `cache_read=1641`. | low | S2 | ✅ closed — 2026-08-03 |
| 5 | Chat-message UI has reached its design ceiling; a Telegram Mini App is the real answer for quiz UX — revisit after the 14-day usage gate, sharing design work with S23. | medium | S3d → post-gate / S23 | ⬜ open |
| 6 | **Production has no off-site backup.** Daily local dumps (`bot` crontab 04:00 UTC) land in `/home/bot/english-bot-backups` on the **same disk as the database** — not a backup against disk or host failure. `BACKUP_OFFSITE_DIR` is deliberately unset (Google Drive unreachable from the server). Open options (none chosen): (1) Hetzner snapshot backups in the panel (~20% of server cost; whole machine including the other service); (2) `rclone` to Drive or object storage (first real cloud credential on the box); (3) `rsync` down to the Mac (unreliable — Mac not always on). Mac-era note: mechanism + `.env` load were verified before deploy; iCloud placeholders still matter for any Mac-side off-site path. | high | S4c | ⬜ open — restated 2026-08-11 after Hetzner deploy |
| 7 | Morning quiz LLM blocked the event loop (~17s); APScheduler skipped that tick's evening reading poll (jobs first=10/15). | high | S9a | ✅ closed — 2026-08-06 (`asyncio.to_thread` + mid-interval evening offset) |
| 8 | S6 per-batch vision cost unmeasured — record observed cost from the first real 10–20 page run | medium | S6 | ⬜ open |
| 9 | S6 OCR accuracy on real Murphy pages unverified until a clean single-page batch succeeds (first live run failed on JSON shape before accuracy could be judged) | medium | S6 | ✅ closed — 2026-08-09 (clean 10-page OCR batch with valid `target_items`) |
| 10 | 2026-08-07 `{` assistant prefill broke all live `json_mode` callers (`claude-sonnet-5` 400). Morning quiz `action=skipped_llm`. | critical | S6 | ✅ closed — 2026-08-08 (prefill removed; tolerant parse; live json_mode + vision + quiz builder OK) |
| 11 | Original S6 prose-instead-of-JSON (~96 tok ×2) still undiagnosed — next live `/book` must read WARNING `raw=` for refusal vs legibility before further prompt tuning | medium | S6 | ✅ closed — 2026-08-09 (prose failure was the rotated two-page spread; clean batches return JSON) |
| 12 | S3 silent-consume: `OpenQuizFilter` + non-gap `on_quiz_text` return blocked M2 whenever an open quiz sat on choice/order/spot. **Journal gaps** on those days — do not read low error volume as “wrote well.” Fixed by gap-only filter (2026-08-08); Telegram verify pending. | high | S3 | ✅ closed — 2026-08-09 (dispatch fix verified live at 17:59 — free text after open non-gap quiz reached correction) |
| 24 | S16 uses TTS over chunk sentences, not mined sitcom clips — trains rhythm/stress but not casual reductions; restore mined-clip source when a mining pipeline exists | medium | S16 → later | ⬜ open — deliberate deviation |
| 13 | Quiz callback: stale session / format mismatch after `query.answer()` can leave the button inert (no edit). Note only — does not block correction. | low | S3 | ⬜ open — note only |
| 14 | S6 `target_items`: near-duplicates survive two-page union (`"Present continuous"` vs `"present continuous (I am doing)"`) because only exact string matches are dropped. | medium | S6 | ⬜ open — later pass |
| 15 | S6 `target_items`: exercise word banks captured as items (e.g. `"verbs: cross, hide, scratch, take, tie, wave"`). | medium | S6 | ⬜ open — later pass |
| 16 | S7 Anki import itself unverified until a human imports a real TSV and confirms four fields land in the right order with no mangled rows. | medium | S7 | ✅ closed — 2026-08-08 (human imported TSV; second `/anki` empty) |
| 17 | Reading 17 ("Finding a Place to Call Home"): legacy question shape + session 803 has no `message_id` / no Questions keyboard — cannot complete in Telegram; orphan stays incomplete forever. Manual Q&A verify on a **fresh** reading after S9c. Covered by legacy-skip unit test. | medium | S9c | ⬜ open — note only |
| 18 | S6 `conversation_timeout` is a documented no-op under nested ConversationHandlers (PTB warning). Abandoned book `user_data` still cleared on TIMEOUT when the outer job fires; do not silence the warning. | low | S6 | ⬜ open — note only |
| 19 | S10 nudge timing (+3h / +6h) cannot be validated until the bot runs unattended — process currently only lives while the laptop is open, so a +3h nudge requires the process still alive 3 hours after delivery. | medium | S10 | ⬜ open — needs unattended host |
| 20 | S12 rolling accuracy is an **approximation** from completed quiz/reading session aggregates (no per-question outcome log / timestamps). Level changes act on this estimate. | medium | S12 | ⬜ open — by design without migration |
| 21 | S18 in-process heartbeat cannot detect total process death — only silent job drops / hung jobs while the process lives. External cron on Hetzner can run `scripts/heartbeat.py` later. | high | S18 | ⬜ open — by design on laptop |
| 22 | S15 text-only: forwarded photos / captions (PRD “a sign”) out of scope — needs a vision path; candidate follow-up. | medium | S15 | ⬜ open — deliberate exclusion |
| 23 | S15 self-forward → capture, not M2. `forward_origin` cannot reliably detect self (`MessageOriginHiddenUser`). Workaround: paste own English as plain text (reply hint). Guessing wrong would journal someone else’s sentences. | medium | S15 | ⬜ open — by design |
| 25 | S18a: `why_statement` and `work_domain` remain uneditable from Telegram. Deliberate omission — free-text ConversationHandler states are the dispatch shape that killed M2; tapped-only editor excludes them until a later slice accepts that risk. | low | S18a | ⬜ open — deliberate omission |
| 26 | S4c: `backup.sh` never read `BACKUP_OFFSITE_DIR` / `BACKUP_DIR` from `.env` — only `DATABASE_URL` was grepped; backup keys came solely from the process environment. Configured-in-`.env` → silent skip (looked unset). Tests missed it: all 18 passed `BACKUP_OFFSITE_DIR` as a real env var to the subprocess, never exercising the `.env` path (same shape as the prefill regression). Fixed 2026-08-10: `env_file_get` + `apply_dotenv_backup_vars` (real env wins; quoted/unquoted; spaces); INFO when skip; regression tests write a temp `.env` with a space in the path. **Standing lesson: shell configuration must be tested through `.env`, not only through environment variables passed by the test harness.** | high | S4c | ✅ closed — 2026-08-10 |
| 27 | S15a inferred Trancy mapping (Word+Translation plus a sentence-like column) was wrong. A real Trancy vocabulary export (`VOCABULARY_LIST_2026-08-14.csv`) is `Word,Phonetic,Translation,Date` — four columns, no sentence. Trancy files have therefore never been importable since S15a shipped. **S24a is the fix** (exact four-column vocabulary + LLM-generated sentences). Language Reactor half remains untested against a real export. | medium | S15a → S24a | ⬜ open — LR half still unverified |
| 28 | S8 couple challenge produces **no learning signal**: question is generated from a specific error journal row, but a correct group answer does not call `mark_result` (no `source_error_id` column; no migration). Same answer in the morning quiz would advance the spacing ladder. Only product surface where getting something right teaches the system nothing. Fix path: migration adding `source_error_id` → winner’s claim calls `mark_result(..., True)`. | medium | S8 → later | ⬜ open — deliberate omission |
| 29 | S8 cannot be verified live until a shared Telegram group exists and `COUPLE_CHAT_ID` is set via `/here`. Second user is onboarded; remaining blocker is the group + env. | high | S8 | ⬜ open — blocked on shared group + `COUPLE_CHAT_ID` |
| 30 | S18c: `docs/GUIDE-saving-phrases.md` and the in-bot `/guide` strings in `texts.py` are two copies of the same content and can diverge. Markdown is the human-facing source for editing; `texts.py` is what ships to Telegram. | low | S18c | ⬜ open — dual copy by design |
| 31 | `backup_freshness` (S4c) is silent while `BACKUP_OFFSITE_DIR` is unset — by design (do not nag someone who has not opted in). Combined with #6, the absence of off-site copies is invisible until someone looks. | high | S4c | ⬜ open — by design while unset |
| 32 | Pending kernel upgrade on Hetzner host (running 6.8.0-124, available 6.8.0-137). Reboot also restarts the other production service (`fonderis-worker`) — needs a chosen window. | low | ops | ⬜ open — do not forget |
| 33 | S24 fan-out duplicates `chunks`/`book_units` per approved user. A third user multiplies storage. Acceptable at this scale; revisit if the product ever has real tenants. | low | S24 | ⬜ open — acceptable at 2 users |
| 34 | S24 two-user fan-out cannot be verified live until User B is onboarded (only one approved user in production). | high | S24 | ✅ closed — 2026-08-14 (slang CSV Share `users_reached: 2`; `SELECT user_id, count(*) FROM chunks WHERE source='slang' GROUP BY user_id` → 5 each) |
| 35 | S24: a new user’s backfill inserts the whole library with `next_review` = tomorrow; at 2 chunk items/quiz a hundred-item library is ~50 quiz days before anything else competes. Ladder unchanged (constraint 4); bulk-starve `id DESC` still holds for later captures. **S25 softens fan-out flood:** unpresented rows no longer enter `due_chunks`; they drain at 2 presentations/day instead. | medium | S24 → S25 | ⬜ open — by design; softened for fan-out |
| 36 | S24 shared content ignores the recipient’s CEFR level. B2-level slang now enters an A2 user’s ladder unchanged. **S25 softens but does not fix** — a presented B2 phrase is still B2 for an A2 learner. | medium | S24 → S25 | ⬜ open — softened not fixed |
| 37 | S24a generated vocabulary sentences are not mined scene context — memorability loss vs slang CSV / real subtitle examples. Register balance and sense selection are prompt-tuned (S24b) and **not verifiable by unit test** — next live import is the check. First live run also produced an idiomatic `notch` (“a notch above”) against a groove/cut gloss. | medium | S24a → S24b | ⬜ open — human verify next import |
| 38 | S24a makes the CSV import path’s per-import LLM cost non-zero (was free). | medium | S24a | ✅ closed — 2026-08-14 live: one call, 1052 input / 486 output tokens, 6.3s ≈ 1.1¢ at claude-sonnet-5 (~6¢/mo at 1 file/week). 6.3s is why `asyncio.to_thread` mattered. |
| 39 | S25: users with many unpresented chunks meet them at 2 presentations/day (FIFO). A large shared library takes days of morning quizzes to clear before graded review starts for the oldest items. | medium | S25 | ⬜ open — by design |
| 40 | S26/S26a/S26b: first live chat (2026-08-14, user 7222549221) turn inputs ≈913→991→1063→1134→1177 tokens, outputs 110/87/92/38/26; every call `cache_read=0, cache_creation=0`. After S26a deploy: successful close used **513** output tokens; next close hit **800** exactly (`max_tokens` ceiling) → “no text blocks” / LLMError. S26b raises close budget to 2000 + truncation retry. Full $ cost still unmeasured — fill after a fixed close post-S26b deploy. | medium | S26b | ⬜ open — close path $ after S26b deploy |
| 41 | S26/S26b/S26c: **conversation quality is not covered by any test.** Suite asserts prompt instructions; whether the model actually behaves is verified only by a human having a real conversation. Keep open. | medium | S26c | ⬜ open — human verify |
| 42 | S26: incomplete abandoned/timeout `conversation` sessions linger as Neutral orphans (filter fails open). Acceptable at this scale; not completed on timeout (would falsely mark Active). **Prod note 2026-08-14:** session **id 9** (`task_type=conversation`, `completed=f`) is the failed live close-out orphan — leave as Neutral, or operator may `UPDATE sessions SET completed = TRUE WHERE id = 9` if they want that day Active; nothing automated required. | low | S26 | ⬜ open — note only |
| 43 | S26 conversation system prompts are below Anthropic Sonnet’s ephemeral cache floor (~1024 tokens). Caching still cannot engage (do not pad just for cache hits). | low | S26c | ⬜ open — by design; do not chase |
| 44 | **Evening reading silently skipped for both users since empty-DB rebuild.** Prod `interests` count = 0 for both (queried 2026-08-14). Keep open until evening reading is confirmed running after `/interests`. Follow-up: make skip visible (alert / `/stats` / prompt). | high | S9 / S26b | ⬜ open — confirm reading resumes |
| 45 | **Explanation language-mixing / transliteration** may also affect `correction`, `diary`, `voice`, and `capture` (same incomplete `_FALLBACK_RULE_*` without single-language / no-transliteration). S26c fixed conversation close only. **W3 ports `correction.txt` — that is the moment to fix or freeze it.** | medium | S26c → W3 | ⬜ open — own slice |
| 46 | **The no-guilt banned-phrase test does not cover every user-facing string**, contrary to CLAUDE.md §4 and PRD §9. There are eight per-slice tests over hand-maintained lists (`s10/s12/s18/s18b/s18c_user_facing_strings()`) or name-prefix filters over `dir(texts)` (`COUPLE_*`, `BTN_CAPTURE*`, `BTN_COUPLE*`). `texts.py` holds 403 constants; any string matching no prefix and named in no list is unchecked. The ban regex is copy-pasted into five test files. Post-migration the coverage *shrinks*, because the slice-scoped providers live in files being deleted. | medium | W0 → W19 | ⬜ open — widen to one test over all copy, expect existing violations |
| 47 | **`errors.source` CHECK will reject every new v3 write path** (`shadow`, `retell`, `answer`, `item`, `placement`, `video`). `record_errors` writes one transaction per message, so a rejection loses the whole correction, not one row. | high | W0 → W5 | ⬜ open — widen once in the W5 migration |
| 48 | **`approved_onboarded_users` is `SELECT u.*`** and freezes its column list at creation. Any `ALTER TABLE users ADD COLUMN` must be paired with a view recreate in the same migration file, or six delivery call sites silently miss the new column. | high | W0 → W2 | ⬜ open — pair every users ALTER with CREATE OR REPLACE VIEW |
| 49 | **Migration `013a` (W13a) collides with `013`.** `db.py::_discover_migrations` parses a leading integer, so both resolve to version 13 in `schema_version`. | medium | W0 → W13a | ⬜ open — renumber to a plain integer |
| 50 | **Duplicated track-weight defaults.** `migrations/001` sets Work 40 as the column default; `handlers/quiz.py:116` hardcodes the same fallback independently; `handlers/settings.py:56–59` and `handlers/onboarding.py:57–59` each hold a third and fourth copy of the preset table. No preset matches PRD §4.6's new 50/30/20. Changing the schema default alone leaves the bias live for any NULL row. | medium | W0 → W5 | ⬜ open — collapse to one constant in `packages/core` |
| 51 | **ARCHITECTURE §5 says "15 existing tables"; the live schema has 17 plus a view.** The two missing from the doc's list are `shared_content` and `shared_content_deliveries` (S24, shipped after the list was drafted). Harmless until someone "reconciles" the schema by dropping them. | low | W0 | ⬜ open — correct the doc |
| 52 | **ARCHITECTURE §2 says the LLM wrapper is "Anthropic primary, OpenAI fallback"; `llm.py` has no fallback** — any non-`anthropic` provider raises `LLMError` immediately (`llm.py:70`). A provider outage is a total outage today. | medium | W0 | ⬜ open — either build the fallback or correct the doc |
| 53 | **`speech_attempts` (W14) and the `sessions` extension (W10) appear in ARCHITECTURE §5 with no migration number in TASKS.** | low | W0 | ⬜ open — assign numbers |
| 54 | **`test_scheduler.py` (5 tests) asserts job predicates, never job registration.** After the API/worker split all 5 pass against a worker that registers zero jobs. | medium | W0 → W1 | ✅ closed — W1 adds four tests: every job by name, IntervalTrigger + interval, `start_scheduler` idempotent, `stop_scheduler` clears all twelve. Verified by deleting a `run_repeating` call and watching them fail. |
| 55 | **The daily 3-message ceiling is a single DB counter (`bot_message_counts`).** W20 adds Web Push; if push and Telegram keep separate counters the combined ceiling silently becomes 6, violating PRD §12 rule 4. | medium | W0 → W20 | ⬜ open — one shared counter, tested |
| 56 | **The v2 work bias has a fourth source not named in PRD §4.6:** `quiz.txt` lines 17–21 list work topics first (`campaigns, client email, negotiation, standups, interviews, pricing`) and the scenario examples include *"a work chat about a deadline"*. This is content in a prompt; no track-weight change removes it. | medium | W0 → W5 | ⬜ open — rewrite at the source |
| 57 | **The W0 §6b work-vocabulary fraction could not be measured.** The only reachable DB is the truncated Mac dev instance (2 chunks, 0 quiz sessions, 0 readings); the production corpus is on Hetzner. Read-only SQL is supplied in the W0 plan §6b — the number must be filled in from production before W5 rewrites the prompts. | medium | W0 → W5 | ⬜ open — run the supplied SQL on Hetzner and record the number |
| 58 | **≈20 `apps/bot` handlers hold SQL directly**, contrary to CLAUDE.md §2 ("SQL lives only in service functions"). Pre-existing, surfaced by W1's `test_no_sql_outside_services`, which excludes `apps/bot` for exactly this reason. | medium | W1 → W22 | ⬜ open — dies with the handlers at W22; **no new SQL may be added to them** |
| 59 | **`core/scheduling.py::list_candidate_users` carries raw SQL outside `core/services/`.** Lifted with its query from the bot scheduler at W1 per the plan; exempted by name in the boundary test. **Retargeted W1b → W20:** the query serves only the delivery jobs (morning, evening, nudge, Sunday, Anki), and those stay in `apps/bot` until W20. W1b's worker registers `streak_rollover`, `monthly_freeze_reset`, `monthly_reset`, `heartbeat` and `backup_freshness` — none of which touch it. Moving a query for a caller that has not arrived is churn. | low | W1 → W20 | ⬜ open — moves with the delivery jobs at W20 |
| 60 | **`core.services.access_control.delivery_lister_ids` imports from `apps.bot`** (`scheduler.list_candidate_users`, `services.couple.registered_user_ids`), inverting the dependency direction. It is a function-local import, so nothing cycles at import time. The W1 boundary test bans web frameworks, not `apps.*`, so it does not catch this. | medium | W1 | ⬜ open — invert to a registration hook, then widen the boundary test to ban `apps.*` from core |
| 61 | **`tests/test_vocab_import.py::test_vocabulary_due_and_anki` was wall-clock dependent and had failed since 2026-08-14** — before W1. `insert_chunks` writes `next_review = CURRENT_DATE + 1`, but the test asked `due_chunks(..., now=date(2026, 8, 15))`. It passed only while the real date was on or before 2026-08-14. | medium | pre-W1 | ✅ closed — W1b: the test reads `SELECT CURRENT_DATE + 1` from the database after the insert and queries with that. `insert_chunks` unchanged. |
| 62 | **`_user_timezone` is copy-pasted into 10 modules** (8 handlers, `core/services/stats.py`, `apps/bot/anki_delivery.py`) — each its own `SELECT timezone FROM users` with its own `Europe/Vilnius` fallback. Pre-existing; W1 carried it across the move unchanged rather than widen scope. | low | pre-W1 | ⬜ open — one service function |
| 63 | **`test_assert_path_outside_repo_refuses_inside` could not detect a wrong `repo_root()`** — it built its "inside" path from the same function it was testing, so both moved together. W1's move broke `repo_root` and this test stayed green. | medium | W1 | ✅ closed — W1b: five cases against a repo root derived from `tests/`, including `<repo>/scripts/x.sql` and a direct child of the root. Verified by re-introducing `parents[2]`: three fail, then pass again on revert. |
| 64 | **`load_settings()` resolves `.env` relative to `packages/core/config.py`, not the working directory.** `load_dotenv()` walks up from the calling module, so it finds the repo-root `.env` no matter where a process is started. Running a process from another directory with its own `.env` silently gets the repo's instead — which is how a W1b acceptance run picked up the real `.env` (see Next action). Benign under systemd (`WorkingDirectory` is the repo anyway) and arguably desirable there; a trap for anyone trying to run against an alternative environment. | medium | W1b | ⬜ open — either document it as intended or take an explicit path |
| 65 | **`apps/api` has no operator alert channel.** An unhandled 500 is formatted and throttled through `core.services.alerts` and then written to the log at ERROR instead of delivered. On the server that means `journalctl -u english-api`, which nobody is watching. The bot's channel cannot be borrowed without importing Telegram into the API (CLAUDE.md §2). | medium | W1b | ⬜ open — a real sink (Sentry at W1c/W2, or an HTTP call to the bot) |
| 66 | **The worker registers `monthly_freeze_reset` and `monthly_reset`, and the second calls the first.** Both are idempotent per user per local day, so the cost is one extra no-op query per 15 minutes — but there are now three names for two units of work across two processes (`apps/bot/scheduler.py` registers a third variant). | low | W1b → W20 | ⬜ open — collapse when the bot's scheduler retires |
| 67 | **`apps/web` has no JavaScript test runner.** The shell's invariants are asserted from `tests/test_web_shell.py` by reading source files — real coverage of the rules that matter (no browser storage, four nav items, manifest icons exist), but nothing renders a component or clicks anything. `pnpm build` and `pnpm lint` are the only checks that execute the code. | medium | W1b → W6 | ⬜ open — add Vitest + Testing Library when there are item components to render |
| 68 | **`.env.example` contains what appears to be a real Anthropic API key**, committed in S2 (`c04dcda`) and still present on `main`. Anyone with repo access — and anyone who ever had it — has the key, and it is in the history, so deleting the line now does not revoke it. … Not touched in W1b: redacting the file would look like a fix without being one. | **high** | S2 → now | ✅ closed — 2026-08-23: human confirmed the value in `.env.example` is a placeholder, not a live key. No rotation required. |

**Carried forward into the v3 migration, unchanged:** #6 (no off-site backup — highest open risk; W4 is the first slice to migrate the live journal) · #20 (calibration approximation — migration 010's `item_attempts` closes it, but the aggregate path must be retained for historical sessions) · #27 (Language Reactor CSV half still unverified — W13's series-import path depends on it) · #28 (couple challenge produces no learning signal — travels with the handler to `apps/bot`) · #29 (couple challenge unverified — blocked on shared group) · #31 (freshness check silent while unset) · #32 (pending kernel upgrade — **should happen before the API and worker units are added**, not after) · #44 (silent skip of a scheduled feature — the shape recurs in v3: empty `lexemes` → no video, empty `syllabus_units` → no focus block; W10's `assign_daily` must alert on every `skipped_*`) · #45 (explanation language-mixing — W3 is the moment). #14/#15 (duplicate and word-bank `target_items`) become **W8-blocking**: `book_units` is the authoring source for `syllabus_units` and the noise would propagate. #30 (dual `/guide` copy) **closes at W22** when the handler is deleted and the markdown becomes the only source.

**Still open after W1b, carried forward in full:** #6 (**the top risk — W1c is its fix and blocks W2**) · #20 · #27 · #28 · #29 · #31 · #32 (**do the kernel reboot before the API and worker units are installed at W1c, not after**) · #44 (stays open until a real Mon/Wed/Fri evening reading lands — no deploy alone can prove it) · #45 · #46 · #47 · #48 · #50 · #51 · #52 · #53 · #55 · #56 · #57 · #58 · #59 (retargeted to W20 above) · #60 (untouched by design: closing it means editing a file under `packages/core/services/` and widening the boundary test onto pre-existing code) · #62 · and the five new ones, #64–#68. **#49 is already closed** by the separate `docs/TASKS-v3-web.md` numbering reconciliation and is not reopened here.

---

## File inventory

Cursor: keep this current so a fresh chat knows what exists without reading the repo.

| Path | Purpose | Status |
|---|---|---|
| `.cursorrules` | Project constitution for every slice | ✅ |
| `.env.example` | Dummy env keys + session-pooler + LLM + Whisper/TTS + S18 operator/runtime + S4c `BACKUP_OFFSITE_DIR` + S15a `WATCH_DIR` + S24 `SHARED_BOOK_SLUGS` + S8 `COUPLE_CHAT_ID` | ✅ |
| `.gitignore` | Ignores `.env`, venv, pycache, pytest | ✅ |
| `requirements.txt` | ptb[job-queue], psycopg, dotenv, pytest, anthropic, openai | ✅ |
| `BUILD_PROGRESS.md` | Slice progress / resume context | ✅ |
| `docs/PRD.md` | Product requirements (B2 band 51–60) | ✅ |
| `docs/ARCHITECTURE.md` | Stack, structure, interfaces; §5 jobs; §7 approved access + `/start`/`/ping`/`access:` (S18d) | ✅ |
| `docs/TASKS.md` | Vertical slice list (+ … + S26 + S26a + S26b + S26c) | ✅ |
| `docs/DEPLOYMENT.md` | Hetzner runbook: shared host, first-time setup, deploy/update, logs, lockout SQL, restore, two-instance warning | ✅ |
| `specs/S0-repo-skeleton.md` | S0 spec | ✅ |
| `specs/S1-onboarding.md` | S1 spec | ✅ |
| `specs/S1a-onboarding-ux.md` | S1a onboarding UX polish spec | ✅ |
| `specs/S1b-onboarding-rebuild.md` | S1b single-message wizard spec | ✅ |
| `specs/S1c-onboarding-content.md` | S1c level / domain / motivation content | ✅ |
| `specs/S1d-onboarding-personality.md` | S1d layout / emoji / reactions | ✅ |
| `specs/S2-llm-correction.md` | S2 LLM wrapper + free correction | ✅ |
| `specs/S3-daily-quiz.md` | S3 daily quiz + scheduler | ✅ |
| `specs/S3a-quiz-content.md` | S3a quiz content + four formats | ✅ |
| `specs/S3b-quiz-layout.md` | S3b readable layout + feedback | ✅ |
| `specs/S3c-quiz-formats.md` | S3c order format + spoken register | ✅ |
| `specs/S3d-quiz-feedback.md` | S3d feedback + typed/tapped mix | ✅ |
| `specs/S4-streaks.md` | S4 streaks / freeze / rescue | ✅ |
| `specs/S4b-backups.md` | S4b pg_dump / restore | ✅ |
| `specs/S5-voice-partner.md` | S5 voice partner (M3) | ✅ |
| `migrations/001_init_postgres.sql` | Initial schema + 19 error_types | ✅ |
| `migrations/002_quiz_scheduler.sql` | sessions.payload + bot_message_counts | ✅ |
| `migrations/003_streaks.sql` | last_evaluated_date, freeze_reset_on, pending_freeze_notice | ✅ |
| `migrations/004_chunk_review.sql` | chunks next_review / times_right / times_wrong / streak_right + due index (S7a) | ✅ |
| `migrations/005_access_requests.sql` | `access_requests` + `approved_onboarded_users` view; backfill existing users approved (S18d) | ✅ |
| `migrations/006_shared_content.sql` | `shared_content` + `shared_content_deliveries` ledger (S24) | ✅ |
| `migrations/007_chunk_presented.sql` | `chunks.presented_at` + source-based backfill (S25) | ✅ |
| `app/__init__.py` | Package marker | ✅ |
| `app/config.py` | Env → frozen `Settings` (+ LLM/STT/TTS + `DIARY_MAX_SECONDS` + S18 runtime + S4c `BACKUP_OFFSITE_DIR` + S15a `WATCH_DIR` + S24 `SHARED_BOOK_SLUGS` + S8 `COUPLE_CHAT_ID`) | ✅ |
| `app/services/couple.py` | Couple challenge DB: pick error, insert, atomic claim, scores, Sunday marker | ✅ |
| `app/handlers/couple.py` | `/here` + group answer filter/handler + 18:00 / Sunday delivery | ✅ |
| `app/prompts/couple.txt` | Journal row → `{question, answer}` JSON | ✅ |
| `app/db.py` | Pool + migrate/status CLI | ✅ |
| `app/llm.py` | Anthropic chat + vision (`images=`); `json_mode` tolerant parse; `reject_truncation` + `stop_reason` log (S26b); no assistant prefill; only LLM provider SDK import | ✅ |
| `app/speech.py` | OpenAI STT/TTS wrapper; only speech provider SDK import | ✅ |
| `app/scheduler.py` | Morning/evening/diary/Sunday report/Anki/nudge/couple/streak/freeze + M13 + heartbeat + backup_freshness + watch_poll | ✅ |
| `app/texts.py` | User-facing strings + … + S26/S26a/S26b/S26c talk + interests named save / custom-added | ✅ |
| `app/main.py` | Entrypoint; flock; rotating log; error handler; `register_handlers` (gate group=-1 + access/admin + guide + CSV + couple); `setMyCommands`; prompts; scheduler | ✅ |
| `app/services/commands.py` | BotCommand list + `register_bot_commands` (S18b/S18c); `/guide` after `/help`; `/ping` hidden; `/import` conditional | ✅ |
| `app/handlers/help.py` | `/help` grouped intent map (S18b); `/guide` pointer (S18c); CSV upload line (S15b); no ceiling bump | ✅ |
| `app/handlers/access.py` | S18d pre-handler gate (group=-1, `ApplicationHandlerStop`); allow `/start` `/ping` `access:` | ✅ |
| `app/handlers/access_request.py` | Request/Approve/Decline callbacks; S24 soft backfill on approve | ✅ |
| `app/handlers/admin.py` | Operator-only tapped `/admin` panel; pause/resume/revoke; orphan `admin:`; S24 backfill on approve/re-approve | ✅ |
| `app/services/access_control.py` | approve/decline/revoke/request; `is_approved`; delivery lister drift registry (+ S24 `list_recipients`) | ✅ |
| `app/services/shared_content.py` | S24 ledger fan-out, convergent backfill, book refresh | ✅ |
| `app/services/vocab_import.py` | S24a/S24b batched sentences + gate retry + named skips + persist_and_send | ✅ |
| `app/prompts/vocab_sentences.txt` | S24a/S24b CEFR + gloss→sense + exact form + register balance | ✅ |
| `tests/test_shared_content.py` | S24 slang/books/backfill/idempotency/labels | ✅ |
| `tests/test_vocab_import.py` | S24a classifier/dedupe/folder + S24b retry/skips/prompt | ✅ |
| `app/services/admin_panel.py` | Activity-only admin list/format (never journal/chunk/diary text) | ✅ |
| `tests/test_access_approval.py` | S18d approval/gate/delivery drift/admin content/surface regression | ✅ |
| `app/handlers/guide.py` | `/guide` tapped-only topic wizard (S18c); orphan `guide:` stale degrade; no MessageHandler | ✅ |
| `tests/test_help.py` | setMyCommands / failure WARNING / help content / import gate / CSV upload line / unregistered / handler drift / no-guilt (S18b/S15b) | ✅ |
| `tests/test_guide.py` | S18c menu/sections/back/4096/stale/double-tap/unregistered/menu+prose drift/labels/no-guilt | ✅ |
| `app/handlers/shadow.py` | `/shadow` + retry callback + voice processing (S16); never errors; transcript discarded | ✅ |
| `app/services/shadow.py` | Chunk select (K=10), word diff, feedback format; abandon open shadow (S16) | ✅ |
| `tests/test_shadow.py` | Diff, select variety, claim window, retry, streaks, calibration exclusion, privacy, labels (S16) | ✅ |
| `app/handlers/prep.py` | `/prep <topic>` load-up mode (S14); CommandHandler only; never errors/sessions | ✅ |
| `app/services/prep.py` | Prep validate + persist-after-send; source=`prep_<slug>`; track NULL default (S14) | ✅ |
| `app/prompts/prep.txt` | Prep JSON prompt — 10 chunks + 3 frames; pitch cefr + work_domain (S14) | ✅ |
| `tests/test_prep.py` | Prep validation, persist/rollback, Anki source, privacy, partial, labels (S14) | ✅ |
| `app/instance_lock.py` | `fcntl.flock` single-instance guard (S18) | ✅ |
| `app/services/alerts.py` | File-backed throttle + `notify_operator` + `on_error` (S18) | ✅ |
| `app/services/heartbeat.py` | last_job_fire touch/check helpers (S18) | ✅ |
| `app/services/backup_freshness.py` | Off-site newest dump / iCloud placeholder freshness (S4c) | ✅ |
| `app/services/stats.py` | Read-only `/stats` assembly; due-chunk count (S18/S7a); learner omits sweep | ✅ |
| `app/handlers/settings.py` | `/settings` tapped-only editor (S18a) + `/pause` + `/stats` (S18); orphan `set:` stale degrade; S15a watch path line | ✅ |
| `app/handlers/import_cmd.py` | `/import` — scan caller inbox (S15a); no ceiling bump | ✅ |
| `app/handlers/csv_import.py` | Private-chat CSV (S15b) + slang Share (S24) + vocabulary LLM path (S24a); no disk write | ✅ |
| `tests/test_csv_import.py` | S15b bytes import, attribution, headers alert, non-CSV, size, unregistered, cross-entrance dedupe, privacy, shared mapper | ✅ |
| `scripts/heartbeat.py` | CLI stale check for future external cron (S18) | ✅ |
| `tests/test_hardening.py` | Alerts/throttle/heartbeat/lock/log privacy/pause/stats/Missed pin (S18) | ✅ |
| `tests/test_backup_offsite.py` | Off-site copy verify/refuse/retention/placeholders + freshness throttle + `.env` load (S4c) | ✅ |
| `tests/test_settings_editor.py` | S18a weight/time/fallback writes, stale degrade, labels, no MessageHandler, scoped writes | ✅ |
| `app/services/calibration.py` | M14 window; prefers payload calib_* (excludes chunk answers); excludes book_test + weekly_test + shadow | ✅ |
| `app/handlers/nudge.py` | Tap-only `nudge:short:` early-limit callbacks; Murphy append on weekly early-complete (S10/S11) | ✅ |
| `app/services/motivation.py` | Nudge ladder (incl. diary text-only) + Sunday report assembly (no LLM) (S10/S13) | ✅ |
| `app/handlers/__init__.py` | Handlers package | ✅ |
| `app/handlers/onboarding.py` | `/start` wizard + access gate branch + `layout_buttons` + reactions (S1d/S18d); soft backfill after Save (S24) | ✅ |
| `app/handlers/correction.py` | Free-text correction (S2) + shared `render_correction_message` | ✅ |
| `app/handlers/capture.py` | Forward + `/capture` real-life capture (S15); never writes errors | ✅ |
| `app/services/capture.py` | Capture validate + persist-after-send; source=`capture`; track NULL default (S15) | ✅ |
| `app/prompts/capture.txt` | Capture JSON prompt — adaptive chunks, generic carriers (S15) | ✅ |
| `tests/test_capture.py` | Capture validation, persist/rollback, PII fixture, handler, anki source, labels (S15) | ✅ |
| `migrations/007_chunk_presented.sql` | S25 `chunks.presented_at` + slang-null backfill | ✅ |
| `migrations/008_conversation_source.sql` | S26 expand `errors.source` CHECK for `'conversation'` | ✅ |
| `app/handlers/conversation.py` | S26–S26c `/talk` + filter + close-out + truncation/End UX/`picking_topic` + reactions | ✅ |
| `app/prompts/conversation.txt` | S26c paragraph shape + S26b partner prompt | ✅ |
| `app/prompts/conversation_close.txt` | S26c single-language explanations; S26 ≤3 prefer recurring | ✅ |
| `app/handlers/interests.py` | S9 wizard; S26c track-screen free text + named save confirmation | ✅ |
| `tests/test_conversation.py` | S26–S26c turn/close/topics/reactions | ✅ |
| `tests/test_interests.py` | S9 + S26c silent-drop / named confirmation | ✅ |
| `app/handlers/quiz.py` | Daily/weekly quiz + chunk middle source + article-tolerant grade; calib_* counters; book fork; OpenQuizFilter gap-only; S25 presentations + `present:` handlers | ✅ |
| `app/handlers/voice.py` | Voice partner (S5) + S16/S13 router (claimable shadow → live M3 → diary → M3); S5a status helpers | ✅ |
| `app/handlers/diary.py` | Voice diary deliver + `/diary` + voice processing (S13); no TTS; cap 2 | ✅ |
| `app/prompts/diary.txt` | Diary JSON prompt — max 2 errors + specific did_well (S13) | ✅ |
| `tests/test_diary.py` | Schedule, ceiling, pause, `/diary`, routing, cap 2, privacy, streaks, labels (S13) | ✅ |
| `app/handlers/interests.py` | `/interests` multi-select wizard (S9); index callbacks; custom-topic preload | ✅ |
| `app/handlers/reading.py` | Evening reading + S9c Q&A/rating; `early_limit`; M14 calibrate on scored complete | ✅ |
| `app/handlers/book.py` | `/book` ConversationHandler; album debounce; vision OCR; Done/Add more; 1h conversation_timeout (S6); operator shared-slug fan-out (S24) | ✅ |
| `app/handlers/book_test.py` | `/test unit N`; tap-only `btest:` callbacks; abandon prior open book_test (S6a) | ✅ |
| `app/prompts/book_quiz.txt` | Unit practice JSON — choice/order/spot only; taxonomy-bound error_type (S6a) | ✅ |
| `app/services/__init__.py` | Services package | ✅ |
| `app/services/users.py` | get/save user, EF SET → CEFR, `update_cefr_level`, `get/set_paused_until`, S18a field updates (weights/times/fallback) | ✅ |
| `app/services/errors.py` | record_errors + due_errors + weekly + Murphy + spacing_step + mark_result + resolved_types + M13 (S3/S10/S11/S12/S7a) | ✅ |
| `app/services/sessions.py` | sessions + ceiling + diary/shadow claim helpers + nudgeable quiz/reading/diary + fossil_sweep + sunday_report (S3–S16) | ✅ |
| `app/services/anki.py` | Chunk→TSV gap/escape/export; weekly deliver + `/anki`; mark-after-send (S7); S15a outbox write (failure-tolerant) | ✅ |
| `app/services/watch_import.py` | Shared CSV map/dedupe/insert (S15a/S15b) + S24 slang + S24a vocabulary signature / structural mutual exclusion; folder refuses vocabulary | ✅ |
| `app/services/paths.py` | `assert_path_outside_repo` + collision-safe move (PRD §10) | ✅ |
| `app/services/streaks.py` | Streak rollover, freeze, rescue; Active>Missed precedence (S4/S5) | ✅ |
| `app/services/interests.py` | list/replace/select_topic/mark_last_used + adjust_weight_for_rating (S9/S9a/S9c) | ✅ |
| `app/services/chunks.py` | Chunk inserts (`presented_at`); due_chunks / count_due / unpresented_chunks / mark_presented; shared `CHUNK_PRESENTED_AND_DUE_SQL` (S7a/S15a/S25) | ✅ |
| `tests/test_chunk_review.py` | S7a selection cap, ladder, grading, calib exclusion, migration, stats, Anki independence; S15a id DESC / bulk-starve | ✅ |
| `tests/test_presentations.py` | S25 presented_at gate, FIFO present queue, ack idempotency, drift predicate, Anki ungated | ✅ |
| `tests/test_watch_import.py` | S15a headers, dedupe, mtime, collision, orphan, outbox, privacy logs, path refuse; tool detect (S15b); slang/vocab mutual exclusion (S24/S24a) | ✅ |
| `app/services/reading.py` | MCQ validate + parse_stored_questions + persist_and_send + complete_reading (S9a/S9c) | ✅ |
| `app/services/books.py` | OCR parse/merge, upsert, summary; list/find/top-up; `upsert_unit_shared` content-only refresh (S6/S6a/S11/S24) | ✅ |
| `app/prompts/correction.txt` | Correction system prompt template | ✅ |
| `app/prompts/quiz.txt` | Quiz generation + optional book_items top-up; taxonomy list for book Qs (S3/S6a) | ✅ |
| `app/prompts/voice.txt` | Voice conversation + correction JSON prompt | ✅ |
| `app/prompts/reading.txt` | Reading passage + MCQ questions + chunks JSON prompt (S9a/S9c) | ✅ |
| `app/prompts/book_ocr.txt` | Vision OCR JSON prompt — structural unreadable, handwriting, personal-use (S6) | ✅ |
| `tests/conftest.py` | Dummy `ANTHROPIC_API_KEY` for test settings load | ✅ |
| `tests/test_onboarding.py` | S1 persistence + CEFR mapping tests | ✅ |
| `tests/test_onboarding_validation.py` | S1b validation re-ask via wizard edit | ✅ |
| `tests/test_why_sentence.py` | Why multi-select → sentence grammar (S1c clauses) | ✅ |
| `tests/test_s1c_content.py` | Self-assessment CEFR map + domain drill-down table | ✅ |
| `tests/test_s1d_personality.py` | Layout helper + full reaction coverage | ✅ |
| `tests/test_llm.py` | LLM retry / ends-on-user guard / tolerant parse / raw truncate / vision repair keeps images | ✅ |
| `tests/test_correction.py` | record_errors + handler + prompt fallback assertions | ✅ |
| `tests/test_spacing.py` | Spacing ladder (ARCHITECTURE §8) | ✅ |
| `tests/test_quiz.py` | Grading, mark_result once, abandon, free_practice | ✅ |
| `tests/test_scheduler.py` | Local-time eligibility + 24h dual-TZ poll | ✅ |
| `tests/test_quiz_s3a.py` | Tracks, reorder/spot, labels, past prompts | ✅ |
| `tests/test_quiz_s3b.py` | Readable body, blank-line sep, no-guilt copy | ✅ |
| `tests/test_quiz_s3c.py` | No reorder; order rows; scenarios; no divider | ✅ |
| `tests/test_quiz_s3d.py` | Full-sentence feedback; 2/3 mix; dots last | ✅ |
| `tests/test_streaks.py` | Freeze / rescue / Active>Missed / monthly reset (S4/S5) | ✅ |
| `tests/test_rescue_quiz.py` | Rescue 3Q vs 5Q; no backlog | ✅ |
| `tests/test_speech.py` | STT/TTS in-memory + retry (mocked OpenAI) | ✅ |
| `tests/test_voice.py` | Voice session gate, conversation, errors, TTS fallback + S5a status | ✅ |
| `tests/test_interests.py` | S9 save/replace/preserve/custom-survive/min-2/free-text/layout | ✅ |
| `tests/test_reading.py` | S9a eligibility, ceiling, topic pick, MCQ validate, rollback, persist + message_id | ✅ |
| `tests/test_reading_s9c.py` | S9c grading, resume, message_id resolve, rating clamps, legacy NULL score, edit resend, labels | ✅ |
| `tests/test_book.py` | S6 debounce, merge, upsert, failures, Page/Pages / All-N collapse, CTA agreement, prose soft-skip, over-cap, labels, SDK/disk greps | ✅ |
| `tests/test_dispatch_m2.py` | Application dispatch + capture + voice/diary/shadow + settings + S8 couple + S15b CSV vs /book | ✅ |
| `tests/test_couple.py` | S8 scoring, poll, marker inertness, no-guilt, dispatch-adjacent | ✅ |
| `tests/test_s6a.py` | Top-up counts, word-bank/dedup fixtures, journal fork (typed+tap), streak Missed vs Neutral, `/test` parse/disambiguate/abandon, labels (S6a) | ✅ |
| `tests/test_anki.py` | S7 gap/escape/order/mark-after-send/ceiling/idempotency/empty `/anki` | ✅ |
| `tests/test_motivation.py` | S10 nudge ladder, ceiling, dual-TZ, resolved_types all-clear, active-days bands, Sunday report, Just do 2 score, no-guilt/labels | ✅ |
| `tests/test_calibration.py` | S12 M14 windowed raise, drop silent, cooldown, bounds, book_test excluded, upsert, pause, no-guilt | ✅ |
| `tests/test_fossilization.py` | S12 M13 sweep queue, un-resolve, resolved_at untouched, rescue skip, no marker leak, resolved_types | ✅ |
| `tests/test_weekly.py` | S11 Sun 15 / Mon 5 / rescue 3; spread select; top-up; free_practice; mark_result; early_limit; Anki Sat; ceiling 2; Murphy; labels | ✅ |
| `specs/S5a-voice-status.md` | S5a voice processing status | ✅ |
| `scripts/backup.sh` | Daily pg_dump (−Fc), 14-day local retain, verified off-site copy (S4c); loads `BACKUP_*` from `.env` | ✅ |
| `scripts/restore.sh` | Restore into scratch DB; `--force` for live | ✅ |

### W1 tree — `app/` is gone. Every row below marked **moved** kept its `git log --follow` history.

| Path | Purpose | Status |
|---|---|---|
| `packages/core/pyproject.toml` | Declares the distribution `core`; `pip install -e packages/core` is a required deploy step | 🆕 |
| `packages/core/__init__.py` | Package docstring + `PROMPTS_DIR` | 🆕 |
| `packages/core/copy.py` | The 52 strings + `format_shadow_feedback` that core services render; `apps/bot/texts.py` re-exports them | 🆕 |
| `packages/core/logging.py` | `configure_logging` — console + rotating file handler, httpx/apscheduler silenced | 🆕 lift from `main.py` |
| `packages/core/scheduling.py` | `EligibleUser`, `list_candidate_users`, `is_user_due_for_morning/evening/diary/anki`, `_time_reached`, `run_streak_rollover`, `run_monthly_freeze_reset`, `run_monthly_reset`, weekday constants | 🆕 lift from `scheduler.py` |
| `packages/core/{db,llm,speech,config,instance_lock}.py` | Pool + migration runner (repo-root `migrations/`), LLM wrapper, STT/TTS wrapper, Settings (no `TELEGRAM_BOT_TOKEN` requirement), single-instance lock | moved |
| `packages/core/services/*.py` | 24 services: errors, streaks, sessions, chunks, users, calibration, interests, books, reading, capture, prep, shadow, access_control, admin_panel, stats, heartbeat, paths, backup_freshness, shared_content, watch_import, vocab_import, alerts, anki, motivation | moved |
| `packages/core/prompts/*.txt` | 12 prompts, zero content edits (`quiz.txt` is rewritten deliberately at W5) | moved |
| `apps/__init__.py` | Deployable applications; each depends on `core` | 🆕 |
| `apps/bot/main.py` | Bot entrypoint; requires `TELEGRAM_BOT_TOKEN` itself, calls `core.logging.configure_logging` | moved |
| `apps/bot/scheduler.py` | APScheduler wiring + job bodies; re-exports the core predicates | moved |
| `apps/bot/texts.py` | Bot copy; re-exports `core.copy` | moved |
| `apps/bot/commands.py` | Telegram command menu (was `services/commands.py`) | moved |
| `apps/bot/handlers/*.py` | 24 handlers, **moved not deleted** — they and their ~209 tests die at W22 | moved |
| `apps/bot/services/couple.py`, `apps/bot/handlers/couple.py`, `apps/bot/prompts/couple.txt` | Couple challenge — stays with the bot | moved |
| `apps/bot/alerts.py` | `on_error` (PTB error handler) + `operator_send`, the adapter for `core.services.alerts.notify_operator` | 🆕 lift |
| `apps/bot/anki_delivery.py` | `deliver_weekly`, `handle_anki_command`, `_user_timezone` | 🆕 lift |
| `apps/bot/motivation_delivery.py` | `send_nudge`, `deliver_nudges_for_user`, `run_nudge_pass`, `deliver_sunday_report`, `run_sunday_report_pass`, `nudge_keyboard` — the worker takes these at W20 | 🆕 lift |
| `tests/test_core_boundary.py` | AST boundary tests: no web framework in core, no provider SDK outside the wrappers, no SQL outside services, MIGRATIONS_DIR at the repo root, **and (W1b) no scheduler in `apps/api` + no cross-app imports** | 🆕 |

### W1b tree — the three application shells. No domain routes, no auth, no migration.

| Path | Purpose | Status |
|---|---|---|
| `apps/api/main.py` | App factory: CORS locked to `[WEB_ORIGIN, localhost:3000]`, the single exception handler (logs route + user, throttled operator alert, generic body), `init_monitoring` Sentry stub | 🆕 |
| `apps/api/deps.py` | `get_db` (pooled connection, plain `def` generator) and `get_current_user` (returns `None` until W2) | 🆕 |
| `apps/api/routers/health.py` | `GET /health` → `{ok, schema_version}` via `core.db`, 503 when the DB is unreachable; `GET /health/auth` → the resolved session or `null` | 🆕 |
| `apps/api/schemas/__init__.py` | `Health`. Source of truth for the OpenAPI client; W2 adds `Session` | 🆕 |
| `apps/api/README.md` | The plain-`def` convention and why, CORS, error handling, the ASGI-transport testing rule | 🆕 |
| `apps/worker/main.py` | Instance lock (`worker.lock`) **before** the scheduler, `build_scheduler()`, own log file, exits 1 on a second start | 🆕 |
| `apps/worker/jobs.py` | The job table: `streak_rollover`, `monthly_freeze_reset`, `monthly_reset` (15 min); `heartbeat`, `backup_freshness` (hourly). `run_job` swallows and logs | 🆕 |
| `apps/web/app/layout.tsx` | Fonts on `<html>`, PWA metadata, theme colour, `viewport-fit=cover` | 🆕 |
| `apps/web/app/globals.css` | The palette (light + `prefers-color-scheme: dark`), no red anywhere, safe-area utility | 🆕 |
| `apps/web/app/manifest.ts` | Typed manifest served at `/manifest.webmanifest` | 🆕 |
| `apps/web/app/(app)/layout.tsx` | The shell: one phone-width column plus the fixed bottom nav | 🆕 |
| `apps/web/app/(app)/page.tsx` | Today — one disabled "Start today's session" button, what W10 opens, the API status line | 🆕 |
| `apps/web/app/(app)/{map,review,progress}/page.tsx` | Placeholders naming what arrives and in which slice (W9 / W7 / W12) | 🆕 |
| `apps/web/components/bottom-nav.tsx` | Today · Map · Review · Progress; active state from `usePathname`; 64px targets | 🆕 |
| `apps/web/components/api-status.tsx` | Client-side `/health` call — the CORS proof | 🆕 |
| `apps/web/components/{page-header,coming-later}.tsx` | The two layout primitives the placeholders share | 🆕 |
| `apps/web/components/ui/{button,card}.tsx` | shadcn/ui, radix-nova preset, neutral base | 🆕 |
| `apps/web/lib/api.ts` | Typed client: `getHealth`, `getAuthHealth`, `ApiError`, base URL from `NEXT_PUBLIC_API_URL` | 🆕 |
| `apps/web/public/icons/*.png` | 192, 512, maskable 512, apple-touch 180 — generated, geometric | 🆕 |
| `apps/web/{next.config.ts,components.json,eslint.config.mjs,tsconfig.json,package.json}` | Next 15.5 + Tailwind v4 + shadcn + `@ducanh2912/next-pwa` (SW disabled in dev) | 🆕 |
| `apps/web/README.md` | How to run it, and the visual direction this shell sets — the record that stands in for the missing design skill file | 🆕 |
| `apps/web/.env.example` | `NEXT_PUBLIC_API_URL` | 🆕 |
| `tests/test_api.py` | 19 tests through `httpx.ASGITransport`: `current_schema_version` directly (independent expected value) + a no-DDL guard on it, health, 503 path, `null` auth + dependency override, CORS allow/refuse/preflight/no-wildcard, generic 500 + no stack trace + throttled alert + alerting-failure, the `WEB_ORIGIN` validation, and the plain-`def` AST rule with its own detector test | 🆕 |
| `tests/test_worker.py` | 15 tests: every job by name and interval, no delivery jobs, `max_instances`/`coalesce`, lock and log separate from the bot's, second start exits 1 without building a scheduler, each job body, `run_job` swallows | 🆕 |
| `tests/test_web_shell.py` | 8 source-level tests: no browser storage (comments stripped, proven), manifest installable, every icon file exists, four nav items each with a page, one button on Today, API base URL from the environment | 🆕 |
| `packages/core/db.py` | **+ `current_schema_version()`** — pooled, read-only, no DDL | edited |
| `packages/core/config.py` | **+ `WEB_ORIGIN`** with scheme / trailing-slash validation | edited |
| `.env.example` | **+ `WEB_ORIGIN`** (empty until the domain is chosen) | edited |
| `requirements.txt` | Grouped by app; **+ fastapi, uvicorn\[standard], APScheduler, httpx** | edited |
| `docs/DEPLOYMENT.md` | Explicit backup → pull → install → migrate → restart; new section for the `english-api` and `english-worker` units (**documented, installed at W1c**), runtime-file table, `WEB_ORIGIN` | edited |
| `.claude/launch.json` | Local dev-server config for `pnpm --dir apps/web dev` (tooling only) | 🆕 |

### S4c off-site destination options

Set in `.env` (directory must already exist and be writable — the script never creates it):

```
BACKUP_OFFSITE_DIR=/absolute/path/to/existing/folder
```

1. **Cloud-synced folder** (zero-credential on this Mac) — iCloud Drive / Dropbox / Google Drive desktop. Script writes a file; the sync client moves it off-machine.
   - **iCloud:** turn off "Optimise Mac Storage" for that folder/machine, or expect `.english_bot_*.dump.icloud` placeholders. Freshness and retention treat placeholders as present (healthy). Dropbox / Google Drive have equivalent selective-sync / online-only behaviour.
2. **`rsync`** to a second host (Hetzner-era): e.g. `rsync -av ~/english-bot-backups/ user@offsite:/path/`.
3. **`rclone`** to object storage (Hetzner-era): e.g. `rclone copy ~/english-bot-backups remote:bucket/`.

No cloud SDK or credentials live in this repo.

### S15a watched-folder layout

Set in `.env` (directory must already exist outside the repo — bot never invents a Drive mount):

```
WATCH_DIR=/absolute/path/to/existing/folder
```

Auto-created under `WATCH_DIR` for each registered user:

```
inbox/<telegram_user_id>/
  trancy/
  language_reactor/
outbox/<telegram_user_id>/
processed/<telegram_user_id>/
failed/<telegram_user_id>/
```

On this Mac: point at a Google Drive–synced folder (no credentials). **On Hetzner prod: `WATCH_DIR` deliberately unset** — no Drive client; S15a dormant; CSV via Telegram (S15b) only. `rclone` + Google service account remains an open option if the folder bridge is ever needed on the server.

**Operator logs (S18 / prod):** `journalctl -u english-bot -f` (preferred on Hetzner); also `tail -f /home/bot/english-bot-runtime/bot.log`. Message content never appears in either.

---

## Verification checklist

Do not start S9b until these are cleared or explicitly deferred.

### How to verify

1. Start the bot: `.venv/bin/python -m app.main`
2. Watch the terminal alongside Telegram.
3. Tail the rotating log: `tail -f ~/english-bot-runtime/bot.log`

### Needs a shared group (S8) — second user is onboarded

- [ ] **S8** — create a shared group; add the bot; registered user runs `/here` → replies with chat id; set `COUPLE_CHAT_ID` in `.env` and restart
- [ ] **S8** — with both users onboarded and journal errors present, after 18:00 Vilnius → one question in the group (under 400 chars)
- [ ] **S8** — first correct answer gets the point + warm win line; wrong answer → warm try-again, challenge stays open
- [ ] **S8** — second correct after a winner → “already claimed”, no second point
- [ ] **S8** — unregistered group member’s text ignored (no reply)
- [ ] **S8** — ordinary group chat with no open challenge → bot silent; private free text still reaches correction
- [ ] **S8** — Sunday ≥18:00 → one leaderboard (both scores, ahead/tie, stake line); second poll tick same Sunday → nothing new
- [ ] **S8** — with only one registered user or `COUPLE_CHAT_ID` unset → no group posts, no errors
- [ ] **S24** — both approved users receive shared slang phrases; each on their own ladder (`next_review` independent)
- [ ] **S24** — newly approved user is backfilled with the shared library at onboarding Save
- [ ] **S24** — operator `/book` on a `SHARED_BOOK_SLUGS` book appears for both users; non-operator `/book` stays personal

### 1. Can run any time at the desk

Commands and taps needing only a running bot.

- [ ] **S26c** — End chat corrections are one language only (no Persian/English mix, no Latin transliteration)
- [ ] **S26c** — turn replies readable as short paragraphs; question on its own line when present
- [ ] **S26c** — a reaction emoji appears on some (not all) user messages during `/talk`
- [ ] **S26c** — mid-`/interests` free text (without tapping Other) always gets a reply and is saved
- [ ] **S26c** — finish `/interests` confirmation lists Work / Life / Curiosity topics saved
- [ ] **S26b** — have a real conversation: bot contributes (opinion/fact/joke), does not only mirror; sometimes uses your slang; varies length / sometimes no question
- [ ] **S26b** — two `/talk` topic pickers in a row without tapping: offered set differs (rotation)
- [ ] **S26b** — End chat responds instantly (wrap-up edit); only one live End button; long chat closes with corrections
- [ ] **S26b** — free text while topic picker is on screen still reaches correction (`picking_topic` not claimed)
- [ ] **S26b** — both users run `/interests` so evening reading resumes (mitigates #44 until a visibility slice)
- [ ] **S26a** — `/talk` → real multi-turn chat → tap End chat → corrections (or clean close) arrive; session `completed=TRUE`
- [ ] **S26a** — if close generation fails (force via bad key / offline briefly): warm close-failure line saying chat has ended; session completed; user can `/talk` again (not trapped)
- [ ] **S26a** — confirm recasts do not echo ungrammatical fragments (human — #41); note never-echo instruction is in prompt
- [ ] **S26** — `/talk` → pick or type a topic → chat; confirm the bot **recasts** rather than interrupts (human — not covered by suite; known issue #41)
- [ ] **S26** — free text before the conversation and after End chat still reaches correction
- [ ] **S26** — forgotten conversation (>30 min) → next text reaches correction (does not swallow M2)
- [ ] **S26** — tap Other, wait >2 min, type a sentence → correction (not turned into a topic)
- [ ] **S26** — open gap quiz → `/talk` / `/talk topic` / topic tap / Other all refuse; quiz untouched
- [ ] **S26** — End chat → at most three warm corrections; journal rows only after that send
- [ ] **S26** — voice note mid-text-chat → still S5/S13/S16 routing (not captured by `/talk`)
- [ ] **S26** — `/pause` then `/talk` still works; no `bot_message_counts` bump
- [ ] **S26** — after deploy: apply migration 008 on Hetzner; confirm `errors.source` accepts `conversation`
- [ ] **S26** — first live full chat with working close: record observed cost + `cache_read` into known issue #40 (expect cache still 0 — #43)
- [ ] **S25** — after deploy + migrate 007 on Hetzner: fill pre-flight counts in decisions log (total / stay_null slang / become_presented; confirm non_slang_delivered = 0)
- [ ] **S25** — a fan-out slang chunk appears as a presentation card before it is ever graded
- [ ] **S25** — tap “Got it” → `presented_at` set; `next_review` = tomorrow; ladder counters unchanged
- [ ] **S25** — the same chunk is graded the following day (gap in morning quiz)
- [ ] **S25** — an unpresented chunk still appears in the next Anki export
- [ ] **S25** — presentations-only morning (no due errors/chunks/books) → free_practice; cards wait
- [ ] **S24b** — send a Trancy vocabulary CSV → skipped words (if any) are named in the reply with a short reason; not only a count
- [ ] **S24b** — read the generated sentences: not all domain-flavoured (AI/work); ordinary everyday English dominates
- [ ] **S24b** — a previously-skipped exact-form miss like `frustrate` imports when the model uses the base form
- [ ] **S24a** — send the real Trancy file (`VOCABULARY_LIST_*.csv`, Word/Phonetic/Translation/Date) → import result with no Share prompt
- [ ] **S24a** — confirm only the sender receives the chunks (second user has zero new `source=vocabulary` rows)
- [ ] **S24a** — confirm generated sentences read naturally and contain their words
- [ ] **S24a** — send a nonsense-header CSV → warm user line; operator alert is readable prose (filename, sender id, header list)
- [ ] **S24a** — re-send the same Trancy file → imported 0 / already had N; no long wait (no LLM)
- [ ] **S24** — send the sample slang CSV (Word,Phonetic,Meaning,Example,Date) → Share with all → sender sees imported/already had/skipped + users reached
- [ ] **S24** — re-send the same slang CSV → Share → imported 0 for sender
- [ ] **S24** — shared slang chunk appears in the next morning quiz (≤2 chunk gaps) and the next Anki export
- [ ] **S24** — send a Trancy vocabulary or Language Reactor CSV → still imports sender-only (no Share prompt)
- [ ] **S24** — set `SHARED_BOOK_SLUGS=murphy,vocabulary_in_use` on deploy; operator `/book` Murphy fans out; marketing (if not listed) stays personal (INFO log)
- [ ] **S18d** — from a **second Telegram account**: `/start` → private-bot message + Request access (no onboarding wizard); tap Request → your operator account gets Approve/Decline with id + username
- [ ] **S18d** — Approve → second account can `/start` and complete onboarding; Decline → warm line, still cannot onboard
- [ ] **S18d** — second Request while pending → no second operator DM
- [ ] **S18d** — after two Declines, third Request → no operator DM; row still visible under `/admin` → Pending
- [ ] **S18d** — `/admin` from your operator account → pending count + user activity (level, streak, active days, last active, paused); no error/chunk/diary text
- [ ] **S18d** — admin Pause → scheduled quiz/reading skipped; Resume restores; Revoke → that user ignored; data still in DB; Re-approve restores
- [ ] **S18d** — `/admin` from a non-operator account → silent (no reply); `/help` and `/guide` unchanged (no `/admin` advertised)
- [ ] **S18c** — open `/guide`; read every section on a phone; confirm Anki setup + weekly field mapping are followable without help
- [ ] **S18c** — Back from every section returns to the menu; Done closes; restart bot and tap an old section → warm stale line
- [ ] **S18c** — `/` menu lists `/guide`; `/help` points at it; after Save on `/start`, confirmation mentions `/guide`
- [ ] **S18b** — restart bot → Telegram `/` menu shows public commands (no `/ping`); descriptions read as outcomes
- [ ] **S18b** — `/help` is scannable on a phone; groups match intent; names type-English and forward-English with no command
- [ ] **S18b** — with `WATCH_DIR` unset, `/help` and the `/` menu omit `/import`; with it set, both include it
- [ ] **S18b** — after Save on `/start`, confirmation mentions `/help` (still one confirmation message, not a third bubble)
- [ ] **S4c** — set `BACKUP_OFFSITE_DIR` in `.env` (quoted path with spaces ok) to an existing writable folder outside the repo and outside `BACKUP_DIR`; run `bash scripts/backup.sh` **without** exporting the var; confirm a matching-size `english_bot_*.dump` lands in the off-site dir
- [ ] **S4c** — with the bot running and `BACKUP_OFFSITE_DIR` set to a deliberately empty or aged directory → one operator alert; repeat within 15 min → throttled (no flood)
- [ ] **S4c** — unset / empty `BACKUP_OFFSITE_DIR` → backup still succeeds locally; log shows `off-site copy skipped (BACKUP_OFFSITE_DIR not set)`; no freshness alert
- [ ] **S15b** — send a Trancy or Language Reactor `.csv` to the bot in private chat → imported / already had / skipped + due count
- [ ] **S15b** — send a non-CSV document (e.g. `.xlsx`) → warm “only CSV” line; no crash
- [ ] **S15b** — `/help` Vocabulary section mentions sending a CSV export (even when `WATCH_DIR` unset)
- [ ] **S15a** — set `WATCH_DIR` to an existing folder outside the repo; `/import` replies with inbox + `trancy/` + `language_reactor/` paths; `/settings` shows the same
- [ ] **S15a** — drop a CSV into `inbox/<your_id>/trancy/` (or `language_reactor/`); wait ≥2 min or age the file; `/import` → imported counts + due count; file lands in `processed/`
- [ ] **S15a** — re-drop the same cumulative export → imported 0, duplicates = prior count
- [ ] **S15a** — `/anki` → TSV in Telegram **and** `outbox/<id>/`; second `/anki` empty
- [ ] **S15a** — CSV with nonsense headers → `failed/`, operator alert, zero new chunks
- [ ] **S15a** — CSV in `inbox/` root (not under user id) → left in place; operator warned; not imported
- [ ] **S15a** — unset `WATCH_DIR` → `/import` silent no-op
- [ ] **S18a** — `/settings` shows current mix, times, fallback, read-only level + `/stats`, and `/interests` + `/pause` lines
- [ ] **S18a** — Mix → Mostly everyday → confirmation says applies from next quiz/reading; next quiz track mix leans life
- [ ] **S18a** — Morning → 07:00 and Evening → 19:00 round-trip; restart bot and tap Mix on old panel → warm stale line, no crash
- [ ] **S18a** — Explanations toggle flips; plain text while `/settings` is open still gets a correction (M2)
- [ ] **S7a** — migrate to 004; morning quiz with >2 due chunks → at most 2 chunk gaps; mix still 2 typed / 3 tapped on a 5Q day
- [ ] **S7a** — type a chunk with extra/missing `the` → marked correct; ladder advances (`next_review` moves)
- [ ] **S7a** — wrong chunk answer → no new `errors` row; chunk `times_wrong` increments
- [ ] **S7a** — exported chunk (`exported_to_anki=TRUE`) still appears when due
- [ ] **S7a** — `/stats` shows due-chunk count alongside total / unexported
- [ ] **S7a** — `/anki` still exports and marks independently of review state
- [ ] **S16** — with chunks present, `/shadow` → intro + voice clip; reply with voice → feedback (🎯/🎤/💡); Try again once → second attempt completes
- [ ] **S16** — empty chunk pool → warm explanation (readings / capture / prep); no audio
- [ ] **S16** — `/shadow` then immediate voice while an M3 window might exist → shadow feedback, not partner reply
- [ ] **S16** — abandon after clip (no reply) then later voice → M3/diary as usual; Try again re-sends clip and re-arms claim
- [ ] **S16** — complete shadow → day can count Active; next morning quiz still delivers
- [ ] **S16** — logs show `user_id`/handler only (no attempt transcript)
- [ ] **S14** — `/prep marketing budget meeting` → Phrases (numbered) + Reply frames (`▸`); scannable; may exceed 400 chars
- [ ] **S14** — bare `/prep` → usage hint with example; no LLM
- [ ] **S14** — over-long topic (~200+) → warm refusal; no LLM
- [ ] **S14** — after success: 10 `chunks` with `source` like `prep_marketing_budget_meeting`; zero new `errors`; zero new `sessions`
- [ ] **S14** — `/anki` TSV includes a `prep_` source marker
- [ ] **S14** — logs show `user_id`/handler only (topic/company name absent)
- [ ] **S13** — `/diary` opens a warm prompt; send ≤60s voice → ≤2 corrections + specific praise; no spoken reply
- [ ] **S13** — second `/diary` same day reuses open session; after complete → warm already-done
- [ ] **S13** — with no open diary, voice still reaches M3 with TTS
- [ ] **S13** — mid-M3 conversation after a diary prompt → next voice continues M3; diary stays open for later
- [ ] **S13** — logs show `user_id`/handler only (no full transcript)
- [ ] **S15** — ordinary typed English gets a correction reply; journal grows; capture does not run
- [ ] **S15** — forwarded English Slack/email yields explanation + chunks; no new `errors` row; `chunks.source='capture'`
- [ ] **S15** — `/capture` with ≥20 chars of paste matches forward behaviour; bare `/capture` shows usage hint
- [ ] **S15** — forwarded non-English or tiny snippet gets a warm fail; no crash
- [ ] **S15** — `/anki` TSV includes `capture` in the source column
- [ ] **S15** — logs show `user_id`/handler only (no message body)
- [ ] **S15** — (optional) self-forward goes to capture; pasting the same text goes to M2
- [ ] **S18** — unhandled exception → soft user line + operator alert (`OPERATOR_TELEGRAM_ID` set); no traceback in chat
- [ ] **S18** — repeat/restart mid-outage → file throttle holds; suppressed count, not a flood
- [ ] **S18** — second `python -m app.main` refuses with lock message; after killing the first, start succeeds
- [ ] **S18** — `/pause` → pick duration → scheduled sends skip; `/pause` again → resume only; after resume, delivery returns
- [ ] **S18** — `/stats` as learner returns level, streak, active days "of 5", due errors, resolved labels, chunk totals + due, book units; calibration visible; no guilt; no fossil-sweep fields
- [ ] **S18** — `~/english-bot-runtime/bot.log` shows traffic without message bodies
- [ ] **S6a** — with Murphy units 1–5 stored, `/test` shows unit buttons; `/test unit 3` opens a tap-only set that finishes cleanly; morning quiz remains eligible that day (or still delivers next morning)
- [ ] **S6a** — `/test unit 99` shows a warm list of real units; same unit number in two books → which-book buttons
- [ ] **S6a** — abandon mid-`/test` then start a new `/test` → prior session abandoned; new set works
- [ ] **S6a** — free English typed mid-`/test` reaches correction (M2), not a grade
- [ ] **S12** — `/test` completions do not write `calibration_log` / do not change level
- [ ] **S6** — text after a summary without tapping Done reaches correction; Done clears the keyboard; Add more → photos → summary; second `/book` starts a clean session
- [ ] **S6** — blurry page / non-book document / 25-page over-cap behave as specified; scheduler stays responsive during a multi-page batch
- [ ] **S6** — after a real batch, known issue #8 records observed vision cost
- [ ] **S3** — parked on a gap question, typed answer grades the quiz, not correction
- [ ] **S9** — custom topic keeps its weight and `last_used` after Change → Done changing nothing
- [ ] **S5** — after Ctrl-C + restart mid-conversation, the bot still remembers the topic
- [ ] **S5a** — status message shows 🎧 → 💭 → 🔊 then disappears; header "recording" persists the whole wait; over-length voice is declined with no status message first
- [ ] **S10** — tapping `Just do 2` completes after 2 answers; DB `score = correct/2`; day can count Active
- [ ] **S10** — free text mid-nudge reaches correction, not swallowed

### 2. Needs a reading evening (Mon/Wed/Fri at `evening_time` — **runs against the Hetzner server**, not the laptop)

- [ ] **S13** — Mon/Wed/Fri evening is still reading only (no diary prompt that night); `/diary` still works
- [ ] **S9c** — fresh evening reading message has `Questions`
- [ ] **S9c** — five MCQs show options in the body with buttons 1–4; wrong answers show `why`; after Q5 a 1–5 rating appears
- [ ] **S9c** — `readings.completed` / `score` / `rating` and session completed; topic weight moved by the rating map
- [ ] **S9c** — free text mid-set reaches correction (not journal poison); abandon without Questions → Neutral at rollover
- [ ] **S9a** — second evening poll same day delivers no second reading
- [ ] **S9a** — next morning's quiz still delivers (reading session does not block it)

### 2b. Needs a diary evening (Tue/Thu at `evening_time` — **runs against the Hetzner server**, not the laptop)

- [ ] **S13** — Tue or Thu at `evening_time` → one diary prompt; second poll same day → nothing; reading does not also fire
- [ ] **S13** — paused user → no diary prompt
- [ ] **S13** — with `bot_message_counts = 3` → diary prompt skipped (WARNING), no session row

### 3. Needs a Sunday (**checks run against the Hetzner server**, not the laptop)

- [ ] **S11** — Sunday morning delivers a 15-question weekly test with preface; finish → Murphy recommendation matches top error types (labels, studied vs new); no codes; under 400 chars
- [ ] **S11** — Sunday in rescue → 3Q, not 15
- [ ] **S11** — mid-weekly-test on a choice question → free text reaches correction
- [ ] **S11** — `Just do 2` on an open weekly test completes at 2; `score = correct/2`
- [ ] **S11** — Sunday evening → report only, no `anki_export` session; Sunday bot-initiated count = weekly test + report ≤ 2
- [ ] **S11** — a completed weekly alone does not write `calibration_log` / does not raise level
- [ ] **S10** — Sunday after `evening_time` → one progress-first report (`N of 5` or "N active days — full week"); second poll same Sunday → nothing

### 4. Needs the process alive 6+ hours

- [ ] **S10** — unfinished morning quiz with process alive ≥3h → first warm nudge; at +6h second with `Just do 2`; third never (known issue #19)
- [ ] **S13** — unfinished diary with process alive ≥3h → warm diary nudge (no Just do 2); second at +6h text-only

### 5. DB-seeded or hard to trigger deliberately

- [ ] **S7a** — 2 due errors + 3 due chunks + book items → quiz has 2 errors, 2 chunks, 1 book; third chunk still due next day
- [ ] **S7a** — 0 due errors + 0 due chunks + books → unchanged S6a book top-up
- [ ] **S11** — Mon–Sat morning quiz is still 5Q (rescue → 3Q)
- [ ] **S11** — Saturday evening → Anki document when unexported chunks exist
- [ ] **S6a** — light journal day (<5 due) → morning quiz length 5 with book-flavored items; wrong book item → `errors` row with valid type
- [ ] **S6** — gap-format book question in a morning quiz: typed wrong answer journals with no crash
- [ ] **S10** — with `bot_message_counts = 3`, no nudge; `nudges_sent` unchanged
- [ ] **S9a** — with `bot_message_counts = 3`, no reading and no new rows
- [ ] **S12** — after `calibration_log` accrues ≥8 days >85% in a fortnight → warm level-raise once; `users.cefr_level` and log `old≠new`
- [ ] **S12** — low-accuracy window → level drops in DB, no user message
- [ ] **S12** — with `bot_message_counts = 3` on raise day → level still rises, notice skipped (WARNING in logs)
- [ ] **S12** — on local 1st (or forced `now`): `fossil_sweep` session with ≤2 pending; next non-rescue morning quiz includes one ordinary-looking retest; wrong → `resolved=FALSE` / `unresolved_count++`; correct → `resolved_at` unchanged, id in `done`
- [ ] **S12** — in rescue: morning 3Q has no retest; pending stays queued

---

## Next action

**Human — urgent, and not a W1b check: rotate the Anthropic API key (#68).** `.env.example` has carried what looks like a live `sk-ant-api03-…` key since commit `c04dcda` (S2). It is in the git history, so deleting the line does not revoke it. Rotate at console.anthropic.com, update the server `.env`, then replace the line in `.env.example` with a placeholder. W1b deliberately did not edit the file — a redaction that does not revoke reads as a fix and is not one.

**Human — W1b, new checks:**

1. **Open the web shell on your phone and install it to the home screen.** `cd apps/web && pnpm install && pnpm dev`, then reach it from the phone (same Wi-Fi, `http://<mac-ip>:3000`). Safari → Share → Add to Home Screen. Check: it opens without browser chrome, the four nav items work, the icon on the home screen is the teal mark and not a screenshot of the page, and dark mode follows the phone's appearance setting. Note that iOS only offers "Add to Home Screen" in Safari, not in Chrome.
2. **`curl` both health routes.** With `uvicorn apps.api.main:app` running: `curl localhost:8000/health` → `{"ok": true, "schema_version": 8}`, and `curl localhost:8000/health/auth` → `null`. Both verified here on the Mac dev DB; the number will be different on Hetzner if 007+008 have not been applied.
3. **Confirm the worker refuses a second start.** With a dummy token — never the live one (CLAUDE.md §5b). Verified here: the first process wrote its pid into `RUNTIME_DIR/worker.lock` and logged `Scheduler built jobs=streak_rollover,monthly_freeze_reset,monthly_reset,heartbeat,backup_freshness`; the second printed the lock message and exited **1**.
4. **Read `apps/web/README.md` and say whether the visual direction is right** — palette, fonts, phone-width-only, placeholders that name their slice. This shell is what every screen from W6 onwards will be consistent with, and it is much cheaper to redirect now than after eleven screens exist. The design skill file the prompt pointed at (`/mnt/skills/public/frontend-design/SKILL.md`) **does not exist in this environment**, so the direction is a choice, not a house style that was followed.

**Human — a disclosure about the W1b acceptance run.** While setting up the worker check, one worker process ran for roughly thirteen minutes against the **Mac development database** with the repo's real `.env`, because `load_dotenv()` resolves relative to `packages/core/config.py` and ignored the temp `.env` I had written in a scratch directory (now known issue #64). In that window it ran one `streak_rollover` poll for one user and one heartbeat read. Nothing was sent anywhere — the worker has no Telegram, no email and no push — and production was never touched. The re-run that produced the acceptance evidence above forced the dummy environment explicitly and fired no jobs at all.

**Human — W1, deploy checks. Carried forward in full; mark off whatever the W1 deploy already cleared:**

1. **The bot still starts on Hetzner** with `ExecStart=… python -m apps.bot.main` and the new `pip install -e packages/core` step.
2. **The instance lock still refuses a second start on the server.**
3. **`python -m core.db status` reports version 8** on Hetzner (it reports `001–008 applied, none pending` on the Mac dev DB).
4. **One message and one `/stats`**, then `~/english-bot-runtime/bot.log` for import errors.

**Human — W0 decisions still unanswered, carried forward:** migration numbering (does W2 take `009` and everything shift?), the domain name — **now needed twice over: `WEB_ORIGIN` in the API `.env` and the auth cookie domain, both W2 acceptance criteria** — and whether the four prompts missing the single-language rule (#45) are fixed during the W3 port or in their own slice. The `013a` renumber (#49) is closed by the TASKS reconciliation. The W21-ahead-of-W4 recommendation was taken: it is W1c, it is next, and it blocks W2.

**Human — run on Hetzner before W5 (#57):** the §6b work-vocabulary SQL, and the quiz-scenario frequency query. W5 rewrites the prompts against that number.

**Human — deploy backlog, carried forward exactly as it stood; delete a line only when you have seen it land:** prefer verifying against the running server — stop any laptop instance first. Deploy **S26c** (includes S26–S26b); run migrations **007 + 008** on **Hetzner** if not yet applied; fill the **S25 pre-flight counts** in the decisions log from production (total / stay_null slang / become_presented; confirm non_slang_delivered = 0). The W1 deploy carries S26c and 007+008, so if it landed those come off this list and the S25 counts become fillable — but W1b assumes nothing about it either way. **Urgent (#44):** confirm evening reading resumes after `/interests`. **#44 stays open until a real Mon/Wed/Fri delivery lands** — no deploy, and no scaffolding slice, can prove that.

**Human — desk checks, every one still unrun and carried forward. W1b clears none of these: three empty application shells exercise no user path.**

- **S26c:** one-language close corrections; short paragraphs with the question on its own line; occasional reaction emoji; mid-`/interests` free text always replies and saves; finish confirmation lists all three tracks.
- **S26b:** bot contributes rather than mirrors; uses your slang sometimes; topic rotation without tapping; End chat responds instantly with one live button; free text during the topic picker still reaches correction; both users run `/interests`.
- **S26a / S26:** gen-fail close leaves you untrapped; recasts never echo an ungrammatical fragment (#41); forgotten chat / Other-timeout / gap-quiz refusal / voice routing / `/pause`; fill the close-path cost into #40.
- **S25:** fan-out slang appears as a presentation before grading; "Got it" sets `presented_at` with `next_review` tomorrow and unchanged counters; same chunk graded the following day; unpresented chunk still exports to Anki; presentations-only morning yields `free_practice`.
- **S24 / S24a / S24b:** slang CSV Share round-trip; Trancy vocabulary sender-only with no Share prompt; generated sentences read naturally and are not domain-flavoured; named skips in the reply; nonsense-header CSV produces a readable operator alert; `SHARED_BOOK_SLUGS` fan-out.
- **S18d:** second-account request → approve → decline → double-decline cap; `/admin` activity-never-content; pause/resume/revoke/re-approve; `/admin` silent for non-operators.
- **S18c / S18b / S18a:** `/guide` readable on a phone with working Back/Done and stale handling; `/` menu and `/help` correct with and without `WATCH_DIR`; `/settings` mix and time round-trips with plain text still reaching correction.
- **S15a / S15b / S16 / S14 / S13 / S15 / S12 / S11 / S10 / S9a / S9c / S7a / S6 / S6a / S5 / S5a / S3 / S18 / S4c:** the full carried-forward list in the Verification checklist above, unchanged.
- **S8:** create the shared group, add the bot, run `/here`, set `COUPLE_CHAT_ID`, restart; then the seven S8 group checks.

**Known issue #6 (no off-site backup in production) remains the highest open risk. W1c is its fix, it is the next slice, and it blocks W2.** Do not start W1c until W1b is approved.
