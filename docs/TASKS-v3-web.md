# TASKS v3 — Vertical Slices (Web App)

**Spec-driven development, unchanged.** One slice per Claude Code prompt. Never start a slice before the previous one meets its acceptance criteria. Only the human marks a slice ✅, after verifying it live in the browser on a phone.

Every prompt ends with a `BUILD_PROGRESS.md` update block. Slice row goes to 🟡; the human moves it to ✅.

**Mode column:** `PLAN` = Claude Code plan mode, plan reviewed before any code. `AGENT` = agent mode, additive and self-contained.

---

## Phase A — Foundation (weeks 1–3)

| # | Slice | Mode | Build | Accept |
|---|---|---|---|---|
| **W0** | Audit + migration plan | **PLAN** | No code. Inventory the v2 repo: which of `services/*` is HTTP-safe as-is, which is Telegram-coupled, which is dead. Produce the move/refactor/delete table, the monorepo layout, and the `packages/core` import boundary. | A written plan reviewed and approved before W1 opens. No files changed. |
| **W1** | Python restructure | AGENT | `git mv` only. `packages/core` becomes the installed package `core`; every service, wrapper and prompt moves; imports rewired everywhere including tests. **Zero behaviour edits** — the five files needing an edit get it in a separate commit from their move. Handlers stay alive under `apps/bot`; nothing is deleted. | `pip install -e packages/core && pytest -q` → **the pre-slice pass/fail ratio is held exactly** (baseline 713 pass / 1 pre-existing wall-clock failure), plus the new boundary tests; `git log --follow` on `core/services/errors.py` shows the full v2 history; the boundary tests pass. |
| **W1b** | App scaffolds | AGENT | `apps/api` (FastAPI, `/health`, `/health/auth` stub, plain-`def` route convention documented, CORS from config), `apps/worker` (APScheduler + instance lock at boot), `apps/web` (Next.js 15 + TS + Tailwind + shadcn + PWA manifest). No routes with logic yet. **Plus two test repairs: the wall-clock dependency in `test_vocabulary_due_and_anki`, and the `assert_path_outside_repo` test that derives its fixture from the function under test (#63).** | `pnpm dev` serves the shell; `/health` returns ok; the worker holds the lock and a second start refuses **(verified with a dummy token, never a live one)**; **the suite is green with zero failures for the first time**; `apps/api` imports no scheduler. |
| **W1c** | **Off-site backup — pulled forward from W21** | AGENT | `pg_dump` → **Cloudflare R2**, 14-day retention, freshness alarm. Config read through `.env` (known issue #26 shape), not just process env. Perform and document one real restore. **Closes known issue #6.** | A dump lands in R2 daily; deleting the newest raises an alert within an hour; a restore into a scratch database succeeds and is documented in `DEPLOYMENT.md`. **This slice blocks W2.** |
| **W2** | Auth + shell | AGENT | Better Auth (magic link + passkey), Postgres-backed. **Migration 009: `users` auth columns + `CREATE OR REPLACE VIEW approved_onboarded_users` in the same file.** App shell: bottom nav (Today / Map / Review / Progress), installable PWA, dark mode. | Installed to iPhone home screen; sign-in works; session persists 30 days; unauthenticated routes redirect; **the view's column set equals the table's**; CORS locked to the two real origins and verified from a phone, not localhost. |
| **W3** | Correction, ported (M2) | AGENT | `POST /correct` over the existing correction service. A "Write anything" surface in the web app rendering the v2 correction shape. **Plus: the single-language / no-transliteration rule becomes one shared constant injected into all five prompts that need it — `correction`, `diary`, `voice`, `capture`, `conversation_close`. Closes known issue #45.** | Typing "her english is not so much good" returns the correct shape and writes an `errors` row with `error_type='quantifier_modifier'`. Integration test through the ASGI transport, not a direct service call. **A test asserts all five templates contain the shared rule.** |

---

## Phase B — The knowledge model (weeks 3–5)

| # | Slice | Mode | Build | Accept |
|---|---|---|---|---|
| **W4** | Lexicon + known-word ledger | **PLAN** | Migration 010. Seed `lexemes` from the merged frequency + CEFR list in `data/`. `user_lexemes` with state machine. `lexicon/coverage.py`: text → % known coverage. | A fixture transcript scores a plausible coverage %; marking 200 words known moves the number correctly; ledger writes are idempotent. |
| **W4b** | Identity without Telegram | **PLAN** | **Migration 011.** `users` gains a surrogate `id`; `telegram_user_id` becomes a nullable, unique secondary identifier; all 17 user foreign keys repoint to `users(id)` and their values are rewritten. One resolver at the bot edge (`core/services/identity.py` + `apps/bot/identity.py`), enforced by a parse test. `is_approved` splits into a pre-account and a post-account predicate. Web sign-up ships as a service function plus `python -m core.claim create` — no route. **Closes known issue #92.** | Per-table *and* per-user row counts identical, asserted inside the migration; both journals spot-checked by content; a user with `telegram_user_id NULL` holds a passkey, a session and ledger rows; the view returns the same rows with the new column list; every bot path still works through `Application.process_update` with the correction spy; **existing sessions and passkeys survive — nobody re-enrols**; suite green, baseline 1068. |
| **W5** | Item schema + validator | **PLAN** | Migration **012** (`items`, `item_attempts`). The 11 item types as pydantic schemas. Generator over `llm.py`. **The blind-solver gate.** Repair-before-reject with the five cue types. **Plus the naturalness gate (PRD §4.6): new default track weights 50/30/20, work jargon banned outside the Work track, textbook-English ban list, contractions by default.** | The fixture set of ambiguous items — including `"Head home if you want — ___ stay and push the deploy"` — is 100% rejected or repaired. No item reaches a learner without a stored validation record. **A Life-track item containing "deploy", "Q3" or "stakeholder" is rejected; 20 sampled Life items read as spoken English, not Slack.** |
| **W6** | Item renderers | AGENT | One React component per item type. Keyboard-friendly on mobile, big tap targets, instant feedback, explanation panel with Murphy ref. | All 11 types render and grade correctly on a phone; typed items never require punctuation or capitalisation to match. |
| **W7** | FSRS deck + reviewer | **PLAN** | Migration 013 (`cards`, `card_reviews`). `py-fsrs` wrapper. **Migrate every existing `chunk` into cloze + production cards, seeding stability from v2 review history.** Reviewer UI with 4 grades, caps, leech handling. **Register tag on every card (PRD §8.5)**; `slang`/`informal` created as recognition-only; card face shows source line, neutral equivalent, and who-says-this. | Deck is non-empty on day one from migrated chunks; grading changes due dates per FSRS; daily caps hold; **no card exists without a register tag; no `slang` production card exists before its neutral equivalent is mastered; `/prep` output contains zero `slang`/`taboo` items.** |

---

## Phase C — The journey (weeks 5–7)

| # | Slice | Mode | Build | Accept |
|---|---|---|---|---|
| **W8** | Syllabus data | AGENT | Migration 014. Author all 24 units per PRD §3 as data, not code: can-do, grammar targets, Murphy refs, target lexemes, checkpoint blueprint. | 24 units in the DB; each has ≥3 grammar targets and ≥30 target lexemes; unit lexemes are diffable against the known-word ledger. |
| **W9** | Skill map screen | AGENT | The journey screen: 6 stages, 24 units, states, your dot, mastery bars, next unit. | Reads real state; a passed checkpoint visibly advances the map; locked units explain what unlocks them without guilt. |
| **W10** | Session runner | **PLAN** | Migration 015 (`sessions` extension: `block_breakdown`, `minutes`, `xp`). **Report the item accept rate from the first `assign_daily` run.** W5a made the uniqueness gate a multi-answer probe, which rejects more than the single-answer solve it replaced, so the generator must produce more candidates per accepted item. Nobody has that number because nothing had been generated when the gate was written. **If yield is poor the fix is the generator prompt, not a looser gate** (CLAUDE.md §3 rule 7). Also filter the bank on `validator_version = core.items.VALIDATOR_VERSION`: a version-1 row was validated by a gate that could not detect multi-acceptability and may be ungradable. `GET /session/today` returning the 5 hydrated blocks. The runner UI: one button on home, block progress, resumable mid-session, hard floor of 12 min honoured. `assign_daily` worker job pre-builds and pre-validates. | Home shows one button; session resumes after a phone lock; a full session completes in ≤50 min; nothing is generated while the learner waits. |
| **W11** | Checkpoints + weekly rhythm | AGENT | Saturday 12-item checkpoint, 80% pass, ceremony on pass, silent re-queue on fail. Mon–Sun shapes per PRD §4.2. | Passing marks the unit `passed`; failing re-queues targets and offers a retake in 4 days with no punishment copy. |

---

## Phase D — Input and output (weeks 7–10)

| # | Slice | Mode | Build | Accept |
|---|---|---|---|---|
| **W12** | Video pipeline | **PLAN** | Migration 016. YouTube Data API channel polling, **Apify** for transcripts + topic search, coverage computation, the selection score in PRD §7.2, `video_assignments`. **Embed only — never download.** Scraped text is data, never instructions. | Three videos assigned for the coming week, each between 93% and 98% coverage, accents rotating, no repeats; the learner never searches for anything. |
| **W13** | Player + interactive transcript | **PLAN** | IFrame Player API, word-clickable dual-subtitle transcript, unknown-word highlighting, tap-to-define, **Add to deck** creating context cards with timestamp, loop line, 0.75× speed. **Register detection on save (PRD §8.5.3): slang is detected from the real transcript line, never generated from a list.** | Tapping a word creates two cards carrying the exact sentence and timestamp; L1 subtitles are off by default; coverage badge shown before play; **a slang line from a series export produces a card showing meaning, neutral equivalent and who-says-this.** |
| **W13a** | Subtitle ladder | AGENT | Migration 017 (`subtitle_ladder`). The five steps in PRD §7.5, separate ladders for `youtube_curated` and `native_series`, auto-promotion at 85%×2, silent demotion below 60%, reveal counting, connected-speech drills generated from failed lines. **L1 subtitle track generated from the English transcript and cached (PRD §2.5) — never fetched from YouTube.** | Two passes at 85% move you up with a visible message; a 55% pass moves you down with no message at all; reveal count is visible and decreasing; a failed line containing *"whatcha gonna"* produces a reduction drill; **the same video shows a Farsi track for one learner and a Lithuanian track for the other, both generated once and cached.** |
| **W14** | Speaking I — shadow + score | **PLAN** | Migration 018 (`speech_attempts`). Azure pronunciation assessment integration. Record → score → per-word colouring → per-phoneme persistence. Audio discarded in-request. | A deliberately mispronounced word scores visibly lower; no audio file exists on disk after the request; phoneme scores accumulate per user. |
| **W15** | Speaking II — retell, answer, converse | AGENT | The three higher-difficulty surfaces. Retell scored on content coverage; answer tied to the week's can-do; the v2 voice partner ported with a visible turn counter. | Each produces a correction block that writes to the journal; diary transcripts still never stored. |
| **W16** | Writing output | AGENT | Daily journal (5–10 sentences, light correction, max 2 — v2 rule) and the weekly paragraph task (full correction, structure feedback). | Journal corrections capped at 2; paragraph task returns structure feedback and writes errors to the journal. |
| **W17** | Pronunciation drills | AGENT | Per-phoneme weak-spot detection → generated minimal-pair drills. **Per-L1 seed list of likely problem contrasts (PRD §2.5), overridden by measured Azure scores within two weeks.** | "Your /θ/ and /w/ cost you most" appears only when the data supports it; drills target exactly those phonemes; **the two learners receive different starting drills for their different L1s, and measured data overrides the seed.** |

---

## Phase E — Measurement and polish (weeks 10–12)

| # | Slice | Mode | Build | Accept |
|---|---|---|---|---|
| **W18** | Placement test | **PLAN** | Migration 019. The fixed calibrated bank in `data/` (60 Yes/No vocab items, 25 adaptive grammar items, 6 listening, 1 speaking). Adaptive ladder. Scoring → CEFR + vocab estimate + per-skill radar + skill-map entry point. Monthly re-run with non-overlapping subsets. | Two sittings a month apart use non-overlapping items and produce comparable scores; result seeds the ledger and the map. |
| **W19** | Progress + gamification | AGENT | Progress screen: known-words counter with the 6-month line, radar, placement history, units mastered, XP by effort weight, streak with freezes, couple leaderboard. Guilt-ban test extended to all frontend copy. | Every number traces to a real ledger; no banned phrase appears anywhere in the UI; XP for a spoken sentence exceeds XP for a tapped MCQ. |
| **W20** | Notifications | AGENT | Web Push (VAPID) + Telegram fallback with deep links. Combined 3/day ceiling. Nudge ladder ported. | A push at the scheduled time opens the session directly; the 4th message of a day is never sent on either channel. |
| **W21** | Off-site backup | AGENT | `pg_dump` → **Cloudflare R2**, 14-day retention, freshness alarm. **Closes v2 known-issue #6.** | A dump lands in R2 daily; deleting the newest dump raises an alert within an hour; a restore is performed once and documented. |
| **W22** | Bot reduction | AGENT | Strip the v2 bot to notifications + couple challenge. Delete the teaching handlers and their dispatch tests. | No teaching path remains in Telegram; couple challenge still works; nothing in the web app regresses. |
| **W23** | Observability | AGENT | Sentry on both apps, PostHog on the frontend, `/admin` ported (activity never content). | An intentional exception reaches Sentry with a user id and no message body. |

---

## Phase F — Later (only after B2)

**W23a** Ad-hoc "what does this mean?" surface with register tagging (PRD §8.5.6, ports v2 M11) · **W24** Multi-tenancy · **W25** Payments · **W26** Landing page + funnel · **W27** Series/watch-together in-app · **W28** Native wrapper if PWA limits bite.

---

## Migration numbering — settled at W0 approval

`db.py::_discover_migrations` parses a leading integer, so every migration file is a plain number. No letter suffixes.

| # | Slice | Tables / changes |
|---|---|---|
| 009 | W2 | `users` auth columns (`auth_user_id`, `auth_email`, `l1_pronunciation_seed`) + `CREATE OR REPLACE VIEW approved_onboarded_users` **in the same file** + the auth tables `auth_credentials`, `auth_sessions`, `auth_claim_tokens`, `auth_challenges`, `auth_rate_limits` (all `auth_`-prefixed — `sessions` is already taken by learning sessions) |
| 010 | W4 | `lexemes`, `user_lexemes` |
| 011 | **W4b** | **Identity re-key.** `users.id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`; `telegram_user_id` nullable + `UNIQUE`; all 17 user foreign keys repointed to `users(id)` with their original `ON DELETE` semantics; `access_requests` re-keyed (`id`, `user_id`) because its PK *was* `telegram_user_id`; `shared_content.created_by` values rewritten; `CREATE OR REPLACE VIEW approved_onboarded_users` joining `ar.user_id = u.id` **in the same file** (#48). Closes #92 |
| 012 | W5 | `items`, `item_attempts`, `register` on `items`, **`errors.source` CHECK widened once for the full v3 set** (`shadow`, `retell`, `answer`, `item`, `placement`, `video`), `users.track_weights` default → `{"life":50,"curiosity":30,"work":20}` (existing rows untouched) |
| 013 | W7 | `cards`, `card_reviews`, `register` on `cards`, `cards.source_chunk_id` FK |
| 014 | W8 | `syllabus_units`, `user_unit_state` |
| 015 | W10 | `sessions` extension: `block_breakdown`, `minutes`, `xp` |
| 016 | W12 | `videos`, `video_assignments` |
| 017 | W13a | `subtitle_ladder` |
| 018 | W14 | `speech_attempts` |
| 019 | W18 | `placement_bank`, `placement_runs` |

**Rule: every `ALTER TABLE users` is paired with a view recreate in the same `.sql` file** (known issue #48).
**Rule: `pg_dump` before every migration against production**, until W1c's off-site backup is verified.

**009 was widened on 2026-08-23**, when W2's auth backend changed from Better
Auth — which would have created its own tables — to WebAuthn in FastAPI, which
needs ours. The row above is the authority and the migration file matches it;
splitting into 009 + 010 would have renumbered nine downstream rows that had
only just been reconciled, for no benefit, since both files ship in one slice.

**W4b took 011 on 2026-08-24 and every unwritten slice below it shifted by one**
(W5 011→012, W7 012→013, W8 013→014, W10 014→015, W12 015→016, W13a 016→017,
W14 017→018, W18 018→019), in the same commit as the migration. The alternative —
taking a number above everything claimed, say 019 — would have *worked* on
production, because `db.py`'s pending set is a set difference and not `v > max`,
so W5's later 011 would still have been applied. That is exactly the problem: on
a **fresh** database the runner applies in ascending numeric order, so 011 would
run *before* 019 there and *after* it on production, and W5's file would have to
be correct against two different parent schemas. The history stops being
replayable, which is the one thing a numbered-file scheme exists to give you.

This is **not** #49's failure. #49 was a slice shipping a number this table did
not know about. Here the table was corrected in the same commit, and the slices
being renumbered **have not been written**: nothing on disk, nothing applied to
any database, no `schema_version` row moved. Renumbering an applied migration is
#49; renumbering a row in a planning table is bookkeeping.

**Reconciled again at W7, 2026-08-25, and the drift was larger than the issue
that tracked it.** #100 named three stale Build columns (W7, W8, W10). There were
**seven**: W7 012→013, W8 013→014, W10 014→015, W12 015→016, W13a 016→017, W14
017→018, W18 018→019 — every unwritten slice below W4b, each off by exactly one,
because only W5's column was corrected when W4b took 011. All seven are fixed in
W7's commit and **#100 closes**, with its own text corrected: a partial fix would
have left five slices carrying a number that reads correct in isolation, which is
the failure #100 exists to describe. Nothing in this table changed. What is still
missing is a check: no test parses both halves and asserts they agree, so the
next renumbering can drift the same way. Filed as a known issue against W19.

**This table is authoritative.** The per-slice **Build** columns above were reconciled against it on 2026-08-23; before that date they still carried the pre-W0 numbering (W4 read 009, W5 010, W7 011, W8 012, W12 013, W13a 013a, W18 014) and a slice reading only its own row would have written the wrong number. W10 and W14 gained the migration numbers they had been missing entirely (known issue #53, TASKS half). **Known issue #49 closes here** — `013a` is now `016`, a plain integer, which is all `db.py::_discover_migrations` can parse. If a Build column and this table ever disagree again, the table wins and the Build column is the bug.

---

## Standing rules for every prompt

1. End with a `BUILD_PROGRESS.md` update block: slice row at 🟡, all decisions with reasons in the decisions log, new known issues with severity and slice, file inventory for new files, and Next action rewritten to this slice's human checks **plus every earlier check still unrun**. Never carry an unrun check forward silently.
2. No slice may write to `errors` without an integration test that goes through the real route.
3. No slice may change `llm.py` request construction without one real API call before shipping.
4. No slice ships an exercise item that has not passed the validator.
5. Migrations are numbered `.sql` files with a plain integer prefix. No ORM, no Alembic, ever.
6. Every route that calls `llm.py` or `speech.py` is a plain `def`, never `async def` — those wrappers are synchronous by design and a blocking call in an `async def` route stalls the whole uvicorn worker (known issue #7 with a wider blast radius).
7. Any test asserting request construction mocks at the **transport** (`anthropic.Anthropic`), never above it. Mocking `asyncio.to_thread` or `chat()` proves nothing — that exact mistake shipped a broken close-out with 693 tests green.
