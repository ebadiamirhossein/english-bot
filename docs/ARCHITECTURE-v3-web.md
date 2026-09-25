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
| `syllabus_units` | the 24-unit map: stage, can-do, grammar targets + murphy refs, **both output-task variants**, and the **checkpoint blueprint**. **Corrected at W8:** this row said "target lexemes", and they are not on it — they live in **`syllabus_unit_lexemes`**, a third table 014 ships, because the per-learner target list is `candidates − known_lemmas(user)` **computed at read time** and a column here could carry no foreign key to `lexemes`. The blueprint and the output tasks were missing from this row entirely |
| `syllabus_unit_lexemes` | unit × lexeme, **shared, no `user_id`** — the candidate pool the per-learner diff runs against (added W8, migration 014) |
| `user_unit_state` | user × unit: state, attempts, checkpoint scores, mastered_at |
| `cards` | user card: type, front/back, source_ref, sentence, register — **and its current FSRS state** (stability, difficulty, due, state, lapses, last_review) |
| `card_reviews` | **the append-only review log** — one row per grade, with the state before and after (corrected at W7; see below) |
| `items` | validated exercise items + their validation record (§PRD 4.3) |
| `item_attempts` | per-question outcome log — **closes v2 known-issue #20** (calibration was an approximation because per-question outcomes were never logged) |
| `videos` | youtube_id, channel_id, **accent, track**, title, duration_s, published_at, transcript, **`captions_kind`**, transcript_status/attempts, metadata_refreshed_at — ~~captions_type~~, ~~transcript_ref~~, ~~coverage cache~~ |
| `video_coverage` | **user × video**: coverage, counted/excluded tokens, `proper_nouns_detected`, `casing`, `lexicon_digest` — **added W12b; see the correction below** |
| `video_assignments` | user × video × date, **resume position**, completion, score_breakdown — ~~segment start/end~~ |
| `placement_bank` | fixed calibrated placement items |
| `placement_runs` | each sitting: per-skill scores, CEFR band, vocab estimate |
| `speech_attempts` | scores only — never audio, never transcripts of the diary |
| `subtitle_ladder` | user × source_type (`youtube_curated` / `native_series`): current step, check history, reveal counts |
| `sessions` | **extended**, not replaced: block breakdown, minutes, XP |

**W12b corrected this section on 2026-08-31, in three places, and the
corrections are named rather than quietly reconciled** — the same way W7 and W6
corrected it before.

**1. `coverage cache` was on the wrong row, and it could not have been right.**
Coverage is `% of tokens whose lemma this LEARNER knows`, so it is a fact about
a learner *and* a video. A column on the global `videos` row can only hold one
of the two learners' numbers, and nothing says which. Migration 019 adds
**`video_coverage`**, keyed `(user_id, video_id)` — the same shape and the same
reason `syllabus_unit_lexemes` has no `user_id` while the per-learner diff is
computed against it.

It is an **audit record and not a cache**, which is the second half of the
correction. `core.video.assign` recomputes coverage on every run and never reads
the stored value back, so the table has **no invalidation rule** — and saying so
is the honest statement, where a rule nothing consults would be a guarantee
nobody checks. `lexicon_digest` is therefore **provenance**: W12a moved one real
transcript from 88.24% to 75.76%, so a figure written before it means something
measurably different from one written after, and the digest is what tells them
apart.

**2. `captions_type` was the wrong name for what the column holds.** It holds a
*kind* — `manual` or `generated` — and it exists only because the ruled actor
genuinely reports that distinction. A column wearing a kind's name while holding
a presence flag is #257's defect exactly: a scanner enforces the form of a claim
and not its truth. It is `captions_kind`, and had no actor reported a kind the
column would not exist and PRD §7.2's human-captions preference would have been
filed unmet rather than worked around.

**3. `segment start/end` is gone, by the operator's ruling of 2026-08-30** — the
full video is shown, not a three-minute segment. `video_assignments` carries a
**resume position** instead: where the learner stopped, not where a chooser cut.
The ruling and the operator's reason for it are quoted in `docs/PRD-v3-web.md`
§7.2, which is corrected in the same commit.

**W7 corrected this section on 2026-08-25, and the correction is named rather
than quietly reconciled** — the same way W6 corrected §6.

This table gave `card_reviews` the FSRS state ("difficulty, stability, due,
lapses, last_review"), which describes **one mutable row per card** and leaves
nowhere for the individual reviews to live. Migration 013 puts the state on
`cards`, where it belongs — it is one row per card and it is rewritten on every
grade — and makes `card_reviews` the append-only log.

The reason is `item_attempts`' reason one table later. The state is derivable and
rewritable; the individual grades are not. Without the log, `py-fsrs`' optimiser
can never be fitted to these two learners' own data (a review log is its only
input), W19 has no review history to show, and a mis-seeded stability can never
be re-derived from what actually happened.

**Migration of `chunks` → `cards`:** every existing chunk becomes a cloze card + a production card, seeded into FSRS with an initial stability derived from its v2 review history. Nothing is lost; the deck is populated on day one rather than empty.

**What "v2 review history" actually is, established at W7:** four aggregate
columns on `chunks` — `next_review`, `times_right`, `times_wrong`,
`streak_right` (migration 004) — and nothing else. **No table logs an individual
chunk review.** So the seeding is a stated mapping from four numbers, versioned
in `core.cards.seeding`, and a chunk with no graded review at all produces a
genuinely new FSRS card with a NULL stability rather than an invented one. The
migration never modifies `chunks` and every seeded card carries its inputs in
`cards.seed_basis`, so a wrong mapping is an UPDATE with a formula rather than a
reconstruction.

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
GET  /review/queue?limit=          → FSRS due cards, capped by the daily budgets
POST /review/{card_id}/grade       → {again|hard|good|easy} → next due
GET  /items?limit=&item_type=      → the validated bank, learner-visible halves only
GET  /items/{id}                   → one item, learner-visible half only (404 if not yours)
POST /items/{id}/answer            → correctness + the canonical + explanation. **No journal write**
GET  /items/{id}/audio             → audio/mpeg for the three types whose content is sound
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

**W6 corrected three things in this section on 2026-08-25 and W8a a fourth on
the same day. All four are named rather than quietly reconciled.**

1. **`POST /items/{id}/answer` does not write to the journal.** This row said it
   did. `errors.source` was widened at migration 012 to include `item`, and
   after W6 that value still has **no writer**. A tapped wrong option is a
   *selection*, not self-produced English; a spoken response is not captured at
   all; and a typed miss is not necessarily a grammar error — a missed
   `dictation` is a listening failure, and an `l1_to_l2_production` canonical is
   trusted rather than verified (known issue #102), so a `correct_form` written
   from it could itself be wrong. A wrong journal row is permanent damage; a
   missing one is recoverable. The evidence lives in `item_attempts` instead.
   **W11 is the slice that will write the first `source = 'item'` row** (#107).
2. **The two read routes and the audio route were missing.** This section
   assumed hydration would arrive with W10's `GET /session/today`. It does — and
   `/session/today` is built from the same `core.services.items.presentations_for`
   that `GET /items` uses, so W10 adds a resource rather than replacing one.
   `item_attempts.session_id` is nullable precisely because migration 012 named
   free practice as a first-class path.
3. **`GET /items/{id}/audio` synthesises inside the service, not in the route.**
   For `listening_gap` the text being spoken *is* the answer. A route that
   called `core.speech.synthesize` itself would hold that string inside
   `apps/api`, where one exception handler echoing context puts it on the wire —
   so the service returns bytes and `tests/test_core_boundary.py::test_the_api_never_reaches_the_hidden_half_of_an_item`
   keeps `core.speech` out of `apps/api` entirely.
4. **`GET /cards/export.tsv` is gone, removed by W8a.** This row read *"the whole
   deck as an Anki TSV (PRD §5's backup)"* and it was accurate: PRD §5's Rules
   line specified the export, the W7 row in `docs/TASKS-v3-web.md` carried it in
   both columns, and W7 built it. **The three documents agreed with each other
   and with the code, so this is a product change and not a drifted row** — a
   distinction worth the sentence, because the handover note that ordered the
   removal gave the opposite reason and a reader reaching the same three files
   will otherwise re-derive it. The judgement changed: a one-click backup is
   still a hand-off, and §2.4's "replaces Anki" is only true if the deck is the
   whole system. PRD §5 carries the full reasoning. **The route's absence is now
   a test, not a convention** —
   `tests/test_web_shell.py::test_no_anki_export_path_in_the_web_app` scans
   `apps/api` and `apps/web` and fails the commit that puts it back.
   `core/services/anki.py`, the **v2 Telegram** chunk exporter, is a different
   surface, is untouched, and dies at W22.

---

## 7. Scheduled jobs (`apps/worker`)

| Job | Schedule | Action |
|---|---|---|
| `assign_daily` | 03:30 local | build tomorrow's session; pick + pre-validate items; ~~choose the video~~ **CHOOSING THE VIDEO IS HUMAN-RUN and is not this job's** (operator ruling, 2026-08-30) — it is `python -m core.video.assign`, dry by default. It refuses rather than assigning fewer than three videos, and a job cannot refuse to anybody |
| `pick_videos` | ~~Sun 04:00~~ **NOT SCHEDULED — human-run** | ~~refresh candidate pool from the channel list, compute coverage, cache transcripts~~ **HUMAN-RUN, NEVER UNATTENDED (operator ruling, 2026-08-30).** Two reasons, and **neither is #69**: **Apify bills per run**, so an unattended job is an unattended invoice; and the **30-day retention purge runs inside the same command**, so a scheduled refresh would silently re-stamp the retention clock on every video every week. It is `python -m core.video.refresh`, dry by default, with `--live` making only quota-costing YouTube calls and **`--apply` the only mode that spends money**. **This ruling is INDEPENDENT of #69 and does not lapse when #69 closes** — the same standing `checkpoint_prep`'s ruling has, and recorded the same way so it is not reversed the day the worker is installed |
| ~~`nudge_check`~~ **`push_poll`** (W20) | ~~every 30 min~~ **every 5 min** | push ladder, respects the 3/day ceiling. **BUILT BY W20 as `apps/worker/jobs.py::push_poll`** — the reminder at `users.morning_time` and v2's two nudges (+3h, +6h), each step decided once per learner per local day into `push_deliveries` (031). Five minutes, not thirty, because the reminder should land near the learner's own time and the bot's poll is five. **It is the worker's ONLY registered job (#69)**: the four jobs this table's other rows share with the bot stay the bot's until W22, and `assign_daily` / `monthly_sweep` are held pending an operator ruling (#437) |
| `checkpoint_prep` | ~~Fri 04:00~~ **NOT SCHEDULED — human-run** | ~~build Saturday's 12-item checkpoint~~ **HUMAN-RUN, NEVER UNATTENDED (operator ruling, 2026-08-27). The reason is that NO GATE CERTIFIES AN ITEM (#196) — NOT that the worker is uninstalled.** **This ruling is INDEPENDENT of #69 and does not lapse when #69 closes.** See the note below the table |
| `weekly_report` | Sun evening | progress-first report |
| `monthly_sweep` | 1st, 00:05 | freeze tokens → 2; anti-fossilisation re-test; placement re-test invite |
| `backup` | daily 04:00 | `pg_dump` local **+ off-site to R2** — closes v2 known-issue #6 |
| `heartbeat` | hourly | external cron pings; alerts if no job fired in 26h |

**`checkpoint_prep` is annotated, not deleted (2026-08-27, W10r).** **Operator
ruling: checkpoint generation is human-run and never unattended.** The reason, in
the operator's terms: known issue #196 refused a scheduled billed pipeline on the
grounds that **no gate certifies an item**, and nothing has changed that. The
operator runs a command; the app never generates while a learner waits, and never
while nobody is watching. **The ruling is independent of #69** — it would hold
unchanged if the `english-worker` unit were installed tomorrow, and reading it as
a consequence of the worker being blocked is how it gets reversed the day #69
closes. **The row is kept because a later slice will look here.** Note that this
table's **`assign_daily` row is already known to overstate what that job does**
(#196): it builds a session row and neither generates items nor picks a video.
**And as of 2026-08-27 no job in this table has ever fired on production** — the
worker unit is uninstalled (#69); the backup runs from cron, not from here.

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
