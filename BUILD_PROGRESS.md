# BUILD PROGRESS

> **Cursor: you must update this file at the end of every slice, before finishing your turn.**
> **Human: upload this file to a new Claude chat to restore full context.**

**Project:** English Learning System — Telegram bot, 2 users, B1 → B2 in 6 months
**Repo:** `english-bot`
**Last updated:** 2026-08-03
**Current slice:** S1d
**Status:** S1d code-complete — awaiting Telegram verification

---

## How to resume in a new Claude chat

Upload this file plus `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/TASKS.md`. Say:
*"Continuing the English bot build. Read BUILD_PROGRESS.md. Give me the Cursor prompt for the next slice."*

---

## Slice status

| Slice | Name | Status | Date | Notes |
|---|---|---|---|---|
| S0 | Repo skeleton | ✅ done & verified | 2026-07-31 | Config, db migrate/status, `/ping` verified against local PG 16.14. |
| S1 | Onboarding | 🟡 code-complete | 2026-07-31 | ConversationHandler `/start`; users+streaks upsert; access control; pytest green on :5433. |
| S1a | Onboarding UX polish | 🟡 code-complete | 2026-08-01 | Superseded interaction model by S1b; data layer unchanged. |
| S1b | Onboarding rebuild | 🟡 code-complete | 2026-08-03 | Single-message `edit_message_text` wizard; 8 taps / 0 typing common path; why multi-select → sentence; HTML + escape. |
| S1c | Onboarding content | 🟡 code-complete | 2026-08-03 | Self-assessment A2/B1/B2; domain category→specific drill-down; situation-based why options; EF SET nudge on save. |
| S1d | Onboarding personality | 🟡 code-complete | 2026-08-03 | Layout helper (≤12 shared rows); emoji on options; static reactions; warmer copy. Sticker skipped (no stable file_id). |
| S2 | LLM wrapper + correction | ⬜ not started | | |
| S3 | Daily quiz + scheduler | ⬜ not started | | |
| S4 | Streaks, freeze, rescue | ⬜ not started | | |
| — | **PHASE 1 SHIPPED — 14-day usage gate** | ⬜ | | |
| S5 | Voice partner | ⬜ not started | | |
| S6 | Book ingestion | ⬜ not started | | |
| S7 | Anki export | ⬜ not started | | |
| S8 | Couple challenge | ⬜ not started | | |
| S9 | Interests + reading | ⬜ not started | | |
| S9b | Video engine (YouTube) | ⬜ not started | | |
| S10 | Motivation engine | ⬜ not started | | |
| S11 | Weekly test + Murphy routing | ⬜ not started | | |
| S12 | Calibration + anti-fossilization | ⬜ not started | | |
| S13–S19 | Phase 4 depth | ⬜ not started | | |
| S20–S23 | Phase 5 commercial | ⬜ not started | | |

Status key: ⬜ not started · 🟡 in progress / code-complete · ✅ done & verified · ⚠️ done but has known issues

---

## Environment

| Item | Status | Value / note |
|---|---|---|
| Hetzner server | ⬜ | — |
| PostgreSQL 16 (local / dev) | ✅ | 16.14 on port 5433 (5432 taken by a Docker container from another project) |
| PostgreSQL 16 (Hetzner / prod) | ⬜ | pending; will use 5432 |
| DATABASE_URL (session pooler) | ⬜ | put in `.env` from `.env.example` |
| Telegram bot token | ✅ | in `.env` |
| Shared group created | ⬜ | — |
| LLM provider + key | ⬜ | — |
| Whisper/TTS key | ⬜ | — |
| YouTube Data API key (S9b) | ⬜ | — |
| systemd unit | ⬜ | — |
| Weekly pg_dump to independent storage | ⬜ | — |
| User A onboarded | ⬜ | EF SET: — |
| User B onboarded | ⬜ | EF SET: — |

---

## Decisions log

Record every decision that deviates from or resolves ambiguity in the spec. Newest first.

| Date | Decision | Reason |
|---|---|---|
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

---

## File inventory

Cursor: keep this current so a fresh chat knows what exists without reading the repo.

| Path | Purpose | Status |
|---|---|---|
| `.cursorrules` | Project constitution for every slice | ✅ |
| `.env.example` | Dummy env keys + session-pooler comment | ✅ |
| `.gitignore` | Ignores `.env`, venv, pycache, pytest | ✅ |
| `requirements.txt` | ptb, psycopg[binary,pool], python-dotenv, pytest | ✅ |
| `BUILD_PROGRESS.md` | Slice progress / resume context | ✅ |
| `docs/PRD.md` | Product requirements (B2 band 51–60) | ✅ |
| `docs/ARCHITECTURE.md` | Stack, structure, interfaces (+ `services/users.py`) | ✅ |
| `docs/TASKS.md` | Vertical slice list | ✅ |
| `specs/S0-repo-skeleton.md` | S0 spec | ✅ |
| `specs/S1-onboarding.md` | S1 spec | ✅ |
| `specs/S1a-onboarding-ux.md` | S1a onboarding UX polish spec | ✅ |
| `specs/S1b-onboarding-rebuild.md` | S1b single-message wizard spec | ✅ |
| `specs/S1c-onboarding-content.md` | S1c level / domain / motivation content | ✅ |
| `specs/S1d-onboarding-personality.md` | S1d layout / emoji / reactions | ✅ |
| `migrations/001_init_postgres.sql` | Initial schema + 19 error_types | ✅ |
| `app/__init__.py` | Package marker | ✅ |
| `app/config.py` | Env → frozen `Settings`, `ConfigError` | ✅ |
| `app/db.py` | Pool + migrate/status CLI | ✅ |
| `app/texts.py` | User-facing strings + S1d reactions/emoji | ✅ |
| `app/main.py` | Bot entrypoint; `/ping`, `/start`, access control | ✅ |
| `app/handlers/__init__.py` | Handlers package | ✅ |
| `app/handlers/access.py` | Shared unregistered-user ignore + onboarding allowlist | ✅ |
| `app/handlers/onboarding.py` | `/start` wizard + `layout_buttons` + reactions (S1d) | ✅ |
| `app/services/__init__.py` | Services package | ✅ |
| `app/services/users.py` | get/save user, EF SET → CEFR | ✅ |
| `app/prompts/.gitkeep` | Empty prompts dir | ✅ |
| `tests/test_onboarding.py` | S1 persistence + CEFR mapping tests (untouched by S1b/S1c) | ✅ |
| `tests/test_onboarding_validation.py` | S1b validation re-ask via wizard edit | ✅ |
| `tests/test_why_sentence.py` | Why multi-select → sentence grammar (S1c clauses) | ✅ |
| `tests/test_s1c_content.py` | Self-assessment CEFR map + domain drill-down table | ✅ |
| `tests/test_s1d_personality.py` | Layout helper + full reaction coverage | ✅ |
| `scripts/.gitkeep` | Empty scripts dir | ✅ |

---

## Next action

**Human:** run the six Telegram verification steps in `specs/S1d-onboarding-personality.md`. Mark S1d (and S1) ✅ when it feels like a partner. Onboarding is then closed — further polish goes to the S18 backlog. Do not start S2 until both users are onboarded.
