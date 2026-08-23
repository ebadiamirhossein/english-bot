# Architecture v3 — Web App

**Version 3.0 · 23 August 2026 · Supersedes ARCHITECTURE v2.0**

---

## 1. The central decision: extend, don't rewrite

**Keep:** PostgreSQL 16 on Hetzner (with every row of the error journal), `app/services/*`, `app/llm.py`, `app/speech.py`, `app/prompts/*`, the migration runner, the 19-type taxonomy, the spacing ladder, streaks/freeze/rescue, calibration.

**Delete:** `app/handlers/*` (Telegram teaching handlers), `app/scheduler.py`'s delivery jobs in their current form, everything shaped by the 4096-character message limit.

**Add:** a FastAPI HTTP layer over the existing services, and a Next.js PWA on top of that.

**Why not a full TypeScript rewrite.** Tempting — one language, `ts-fsrs`, better PWA ergonomics. Rejected because the Python services encode roughly forty bug-fixes that are invisible in the code and unrecoverable from a spec: the spacing-ladder edge cases, the freeze-token consumption order, the calibration approximation, the prefill regression fix in `llm.py`, the `.env` loading bug. Rewriting reintroduces all of them. The Telegram *dispatch* bugs — which is what actually hurt in v2 — live entirely in `handlers/`, and those are being deleted anyway.

**The dispatch bug class dies with this migration.** There is no `ConversationHandler`, no filter ordering, no silent-consume. HTTP routes either match or 404. This alone justifies the move.

---

## 2. Stack

| Concern | Choice | Why |
|---|---|---|
| Frontend | **Next.js 15 (App Router) + TypeScript** | Best PWA story, server components for the heavy dashboard reads |
| UI | **Tailwind + shadcn/ui** | Fast, consistent, accessible defaults |
| State/data | **TanStack Query** | Offline cache for the review queue |
| PWA | `next-pwa` / Workbox, installable, offline review queue | The phone-app requirement |
| Frontend host | **Vercel** | Zero-config, preview deploys, free tier is plenty |
| Backend | **FastAPI + uvicorn (Python 3.12)** | Wraps existing services; async; auto OpenAPI |
| Backend host | **Hetzner CPX32** (existing box), behind **Caddy** | DB is already there; Caddy does TLS with one line |
| DB | **PostgreSQL 16, existing instance** | The journal must not move |
| Driver / migrations | `psycopg[binary,pool]`, numbered `.sql` + `schema_version` | Unchanged from v2. No ORM. |
| Auth | **WebAuthn passkeys in FastAPI** (`py_webauthn`), Postgres-backed — magic link deferred to its own slice | Better Auth is TypeScript and needs a direct Postgres connection; `apps/web` is on Vercel and PostgreSQL binds `127.0.0.1`. The three bridges were all worse: exposing the journal's database to the internet, adding a Node process against CLAUDE.md §2's microservice ban, or taking Clerk — the vendor Better Auth was chosen to avoid. Implementing it in FastAPI adds no process, no vendor and no exposed port. **Changed at W2; see BUILD_PROGRESS.** |
| Scheduling | APScheduler in a **separate worker process** | Never in the API process |
| SRS | **`py-fsrs`** (FSRS-5) | Modern, actively maintained |
| LLM | existing `llm.py` wrapper (Anthropic primary, OpenAI fallback) | Unchanged. **Never call a provider SDK anywhere else.** |
| STT | **ElevenLabs Scribe v2** ($0.22/hr) | Cheaper than Whisper ($0.36/hr), 98%+ accuracy, and **word-level timestamps** — required for shadowing word-colouring. Whisper stays as fallback behind the same `speech.py` wrapper |
| TTS | **ElevenLabs Flash/Turbo** ($0.05/1K chars) for cards and drills; **v2 Multilingual** ($0.10/1K) for listening content; cached to R2 | Card audio is heard hundreds of times. Generated once, stored forever — ~$3/month at 12 new cards/day × 2 users |
| Pronunciation | **Azure Speech pronunciation assessment** | Per-phoneme scoring; nothing else does this. Free tier F0 = 5 audio hrs/month, then €0.879/hr; prosody is a €0.264/hr add-on. Expected spend €0–6/month |
| Object storage | **Cloudflare R2** | Cached TTS + card images; no egress fees |
| Transcripts, topic search, slang sourcing | **Apify** (account already connected) | One vendor for three jobs (PRD §7.2). Never scrape the player directly |
| Video metadata | **YouTube Data API v3** | Free quota is far beyond our need |
| Errors/monitoring | **Sentry** (both apps) + **PostHog** (frontend only) | v2 had no visibility at all |
| Notifications | Web Push (VAPID) + existing Telegram bot | §PRD 10 |

**Deliberately excluded:** ORM, Redis, Celery, Kubernetes, microservices, GraphQL, React Native.

---

## 3. Repository layout — monorepo

```
english-app/
├── apps/
│   ├── web/                     # Next.js PWA
│   │   ├── app/
│   │   │   ├── (auth)/          # sign-in, placement test
│   │   │   ├── (app)/
│   │   │   │   ├── page.tsx             # HOME: "Start today's session"
│   │   │   │   ├── session/             # the session runner (5 blocks)
│   │   │   │   ├── review/              # FSRS card reviewer
│   │   │   │   ├── watch/[videoId]/     # player + interactive transcript
│   │   │   │   ├── map/                 # the journey / skill map
│   │   │   │   ├── progress/            # ledgers, radar, placement history
│   │   │   │   └── settings/
│   │   ├── components/
│   │   │   ├── items/           # ONE component per item type (§PRD 4.3)
│   │   │   ├── cards/
│   │   │   └── player/
│   │   └── lib/api.ts           # typed client generated from OpenAPI
│   └── api/                     # FastAPI
│       ├── main.py
│       ├── routers/             # session, review, items, video, speech, progress, placement, admin
│       ├── deps.py              # auth, db session, rate limits
│       └── schemas/             # pydantic, source of truth for the OpenAPI client
├── packages/
│   └── core/                    # ← the MIGRATED v2 python package
│       ├── services/            #   errors, chunks, streaks, calibration, motivation, interests
│       ├── llm.py  speech.py  db.py  config.py
│       ├── prompts/
│       ├── srs/                 #   NEW: fsrs.py (cards) — separate from errors ladder
│       ├── items/               #   NEW: generator.py, validator.py, schema.py
│       └── lexicon/             #   NEW: known-word ledger, coverage, frequency table
├── apps/worker/                 # APScheduler: assignments, digests, sweeps, video picks
├── apps/bot/                    # v2 bot, reduced to notifications + couple challenge
├── migrations/                  # 001–008 existing, 009+ new
├── data/                        # static: frequency+CEFR lexicon, placement item bank
├── docs/                        # PRD-v3, ARCHITECTURE-v3, TASKS-v3, DEPLOYMENT
├── tests/
└── BUILD_PROGRESS.md
```

`packages/core` is importable by `apps/api`, `apps/worker` and `apps/bot`. Nothing in `core` may import FastAPI, Telegram, or HTTP.

---

## 4. Layering rule — the one that prevents v2's worst bug class

```
HTTP route  →  service function  →  SQL
```

- A route contains **no business logic**: parse, authorise, call one service function, serialise.
- A service function **never** knows about HTTP, Telegram, or the UI.
- A service function is the **only** place SQL is written.
- Every route is covered by an **integration test that hits the real app through the ASGI transport**, not by calling the service directly.

That last line is the direct descendant of v2's most expensive lesson: 161 unit tests passed while free correction was dead, because every test called handlers directly and none exercised dispatch.

---

## 5. Schema additions (migrations 009+)

Existing 15 tables are untouched. New:

| Table | Holds |
|---|---|
| `lexemes` | static: lemma, frequency band, CEFR tag, POS (~15k rows, seeded from `data/`) |
| `user_lexemes` | user × lemma: state, strength, first_seen, source |
| `syllabus_units` | the 24-unit map: stage, can-do, grammar targets, murphy refs, target lexemes |
| `user_unit_state` | user × unit: state, attempts, checkpoint scores, mastered_at |
| `cards` | user card: type, front/back, source_ref, sentence, audio_key |
| `card_reviews` | FSRS state: difficulty, stability, due, lapses, last_review |
| `items` | validated exercise items + their validation record (§PRD 4.3) |
| `item_attempts` | per-question outcome log — **closes v2 known-issue #20** (calibration was an approximation because per-question outcomes were never logged) |
| `videos` | youtube_id, channel, captions_type, duration, transcript_ref, coverage cache |
| `video_assignments` | user × video × date, segment start/end, completion |
| `placement_bank` | fixed calibrated placement items |
| `placement_runs` | each sitting: per-skill scores, CEFR band, vocab estimate |
| `speech_attempts` | scores only — never audio, never transcripts of the diary |
| `subtitle_ladder` | user × source_type (`youtube_curated` / `native_series`): current step, check history, reveal counts |
| `sessions` | **extended**, not replaced: block breakdown, minutes, XP |

**Migration of `chunks` → `cards`:** every existing chunk becomes a cloze card + a production card, seeded into FSRS with an initial stability derived from its v2 review history. Nothing is lost; the deck is populated on day one rather than empty.

---

## 6. API surface (first cut)

```
POST /auth/register/begin          passkey creation options (claim-token gated)
POST /auth/register/finish         first enrolment; sets the session cookie
POST /auth/login/begin             request options (discoverable, no identifier)
POST /auth/login/finish            assertion → session cookie
POST /auth/logout                  revokes the session server-side, clears cookie
GET  /auth/passkeys                the caller's credentials (no secrets)
POST /auth/passkeys/begin          add a passkey to an authenticated account
POST /auth/passkeys/finish
DELETE /auth/passkeys/{id}         409 on the last credential, 404 if not yours
GET  /health/auth                  the resolved session, or literal null
GET  /session/today                → the 5 blocks, fully hydrated
POST /session/{id}/block/{n}/complete
GET  /review/queue?limit=          → FSRS due cards
POST /review/{card_id}/grade       → {again|hard|good|easy} → next due
POST /items/{id}/answer            → correctness, explanation, journal write
POST /correct                      → free text → correction + journal (v2 M2, ported)
GET  /video/today                  → assigned video + segment + transcript + coverage
POST /video/{id}/save-word         → creates cards
POST /speech/shadow                → audio → Azure scores + word colouring
POST /speech/answer                → audio → transcript + correction + journal
GET  /map                          → skill map + unit states
GET  /progress                     → ledgers, radar, placement history
POST /placement/start | /answer | /finish
```

Audio is uploaded, processed in memory, scored, and **discarded within the request**. It never touches disk and never reaches R2.

---

## 7. Scheduled jobs (`apps/worker`)

| Job | Schedule | Action |
|---|---|---|
| `assign_daily` | 03:30 local | build tomorrow's session; pick + pre-validate items; choose the video |
| `pick_videos` | Sun 04:00 | refresh candidate pool from the channel list, compute coverage, cache transcripts |
| `nudge_check` | every 30 min | push ladder, respects the 3/day ceiling |
| `checkpoint_prep` | Fri 04:00 | build Saturday's 12-item checkpoint |
| `weekly_report` | Sun evening | progress-first report |
| `monthly_sweep` | 1st, 00:05 | freeze tokens → 2; anti-fossilisation re-test; placement re-test invite |
| `backup` | daily 04:00 | `pg_dump` local **+ off-site to R2** — closes v2 known-issue #6 |
| `heartbeat` | hourly | external cron pings; alerts if no job fired in 26h |

**Pre-validation matters:** items are generated and gated (§PRD 4.3) *the night before*, not while the learner waits. A session must open in under a second.

---

## 8. Cost model at two users

| Item | Monthly |
|---|---|
| Hetzner CPX32 (existing) | ~€15 |
| Vercel | €0 (hobby) |
| Anthropic + OpenAI | €25–50 |
| ElevenLabs (pay-as-you-go: TTS ~$3 + Scribe STT ~$1) | ~€4 |
| Azure Speech (5 free hrs, then €0.879/hr) | €0–6 |
| Apify (transcripts + search + slang) | €0–35 |
| Forvo API (Non-Profit tier) | ~€2 |
| Cloudflare R2 | ~€1 |
| Sentry + PostHog | €0–26 |
| **Total** | **≈ €50–120/month** |

Comparable to three hours of tutoring, and it runs 30 days a month.

---

## 9. Deployment

- **Frontend:** Vercel, `main` auto-deploys, preview per PR.
- **API + worker:** Hetzner, two systemd units (`english-api`, `english-worker`), Caddy reverse proxy with automatic TLS on `api.<domain>`.
- **Deploy sequence unchanged from v2 and not to be re-argued:** backup → pull → migrate → restart.
- **Two processes, one lock each.** The v2 `flock` guard moves to the worker. The API may run multiple workers; the scheduler must not.
- **CORS** locked to the production frontend origin plus `localhost:3000`.

---

## 10. Testing requirements

Mandatory automated coverage — everything else is discretionary:

1. **Spacing ladder** (`errors`) — ported from v2 unchanged.
2. **Streaks / freeze / rescue** — ported from v2 unchanged.
3. **FSRS wrapper** — grade → next-due, leech detection, caps.
4. **Item validator** — a fixture set of deliberately ambiguous items (including *your* `___ stay and push the deploy` example) must all be rejected or repaired. This is the regression test for the bug that started this rebuild.
4b. **Naturalness gate** (PRD §4.6) — a fixture set of work-jargon and textbook-English sentences must all be rejected when the item's track is Life or Curiosity. Generated Life-track items must contain contractions at a plausible rate.
5. **Route integration tests through the ASGI transport** for every route that writes to the journal or the deck.
6. **Coverage calculation** — known-word ledger → % coverage, on fixture transcripts.
7. **No-guilt string test** — ported, extended to all frontend copy.

**Standing rule from v2, unchanged:** any change to `llm.py` request construction requires one real API call before shipping. Mocked tests cannot verify a provider contract.
