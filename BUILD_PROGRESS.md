# BUILD PROGRESS

> **Cursor: you must update this file at the end of every slice, before finishing your turn.**
> **Human: upload this file to a new Claude chat to restore full context.**

**Project:** English Learning System — Telegram bot, 2 users, B1 → B2 in 6 months
**Repo:** `english-bot`
**Last updated:** 2026-07-31
**Current slice:** S0
**Status:** 🟡 code-complete — awaiting human verification

---

## How to resume in a new Claude chat

Upload this file plus `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/TASKS.md`. Say:
*"Continuing the English bot build. Read BUILD_PROGRESS.md. Give me the Cursor prompt for the next slice."*

---

## Slice status

| Slice | Name | Status | Date | Notes |
|---|---|---|---|---|
| S0 | Repo skeleton | 🟡 code-complete | 2026-07-31 | Config, db migrate/status, `/ping` only. Awaiting Telegram + Supabase verification. |
| S1 | Onboarding | ⬜ not started | | |
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

Status key: ⬜ not started · 🟡 in progress · ✅ done & verified · ⚠️ done but has known issues

---

## Environment

| Item | Status | Value / note |
|---|---|---|
| Hetzner server | ⬜ | — |
| Supabase project created | ⬜ | region: eu-central or eu-north — human prerequisite for S0 verify |
| DATABASE_URL (session pooler) | ⬜ | put in `.env` from `.env.example` |
| Telegram bot token | ⬜ | put in `.env` from `.env.example` |
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
| 2026-07-31 | Migration runner uses `psycopg.ClientCursor` for applying `.sql` files | psycopg3's default server-side cursor rejects multi-statement scripts; ClientCursor uses the simple query protocol |
| 2026-07-31 | Replaced undotted `cursorrules` with `.cursorrules` | ARCHITECTURE §3 and S0 require the dotted filename Cursor reads; content rewritten to match S0's required clauses |
| 2026-07-31 | ARCHITECTURE §7 "Database file chmod 600" → credentials in `.env` mode 600 | No local DB file under Postgres/Supabase; keep the security intent |
| 2026-07-31 | ARCHITECTURE §1 "SQLite" → PostgreSQL; §5 backup job → `pg_dump` | Doc fix required by S0; matches §2 and earlier decisions log |
| 2026-07-31 | ARCHITECTURE §3 gains `specs/` | Prevent later slices treating specs as out-of-tree |
| 2026-07-31 | Local verify venv used Python 3.13 (3.12 not installed on this machine) | Runtime target remains 3.12 per ARCHITECTURE; deps install cleanly on 3.13 |
| 2026-07-31 | PostgreSQL on Supabase (+€10/mo), not SQLite, not self-hosted PG | Choosing PG now permanently removes the SQLite→PG migration risk. Supabase→self-hosted stays reversible via pg_dump. Managed backups + PITR + table editor worth €120/yr for an irreplaceable database. |
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
| — | none yet | | | |

---

## File inventory

Cursor: keep this current so a fresh chat knows what exists without reading the repo.

| Path | Purpose | Status |
|---|---|---|
| `.cursorrules` | Project constitution for every slice | ✅ |
| `.env.example` | Dummy env keys + session-pooler comment | ✅ |
| `.gitignore` | Ignores `.env`, venv, pycache, pytest | ✅ |
| `requirements.txt` | ptb, psycopg[binary,pool], python-dotenv | ✅ |
| `BUILD_PROGRESS.md` | Slice progress / resume context | ✅ |
| `docs/PRD.md` | Product requirements | ✅ |
| `docs/ARCHITECTURE.md` | Stack, structure, interfaces (Postgres-corrected) | ✅ |
| `docs/TASKS.md` | Vertical slice list | ✅ |
| `specs/S0-repo-skeleton.md` | S0 spec | ✅ |
| `migrations/001_init_postgres.sql` | Initial schema + 19 error_types | ✅ |
| `app/__init__.py` | Package marker | ✅ |
| `app/config.py` | Env → frozen `Settings`, `ConfigError` | ✅ |
| `app/db.py` | Pool + migrate/status CLI | ✅ |
| `app/texts.py` | User-facing strings (`PONG`) | ✅ |
| `app/main.py` | Bot entrypoint; `/ping` only | ✅ |
| `app/handlers/__init__.py` | Empty handlers package | ✅ |
| `app/services/__init__.py` | Empty services package | ✅ |
| `app/prompts/.gitkeep` | Empty prompts dir | ✅ |
| `tests/.gitkeep` | Empty tests dir | ✅ |
| `scripts/.gitkeep` | Empty scripts dir | ✅ |

---

## Next action

**Human: run the S0 manual verification steps (config fail, migrate, schema check, `/ping` in Telegram). Flip S0 to ✅ when all five acceptance criteria pass. Then run the S1 Cursor prompt — do not start S1 before that.**
