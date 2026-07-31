# S0 · Repo skeleton

**Slice:** S0
**Phase:** 1 — Foundation
**Depends on:** nothing
**Status:** ⬜ not started
**Spec written:** 2026-07-31

---

## Goal

Produce a repository that starts, connects to Supabase, applies its schema, and
answers one Telegram command. Nothing more. Every later slice adds handlers and
services to this frame; none of them should have to change it.

This slice exists to make the two riskiest pieces of infrastructure — the
database connection and the Telegram loop — provably working before any product
logic depends on them.

## Non-goals

Explicitly out of scope. Do not build these, even partially:

- Any handler other than `/ping`. No `/start`, no message handler.
- Any service module. `app/services/` stays empty.
- Any prompt file. `app/prompts/` stays empty.
- `llm.py`, `speech.py`, `scheduler.py` — later slices.
- Automated tests. The first required tests land in S3 (spacing ladder).
- Access control. Restricting the bot to known `telegram_user_id` values is S1's
  job. In S0 anyone who finds the bot gets `pong`, and that is acceptable.
- Any dependency beyond the three listed below.

## Prerequisites (human, before running this slice)

- Supabase project created, region `eu-central` or `eu-north`
- Telegram bot created via @BotFather, token in hand
- Python 3.12 available

---

## Deliverables

Directory structure exactly as `docs/ARCHITECTURE.md` §3, plus a `specs/`
directory (see *Doc fixes* below). Empty packages get `__init__.py`; empty
directories get `.gitkeep`. Nothing else in them.

### `.cursorrules`

Does not currently exist, despite being referenced by `BUILD_PROGRESS.md` and
listed in `ARCHITECTURE.md` §3. Create it. It is this project's constitution and
every later slice reads it first.

Must state:

**Scope**
- One slice per prompt. Implement the slice's spec file in `specs/` and nothing
  else. If that spec file does not exist, stop and ask — do not improvise.
- Never begin a slice before the previous one meets its acceptance criteria.
- No dependency added unless the current slice needs it; add it to
  `requirements.txt` in the same change.
- No handler, service or prompt file created ahead of the slice that implements
  it.

**Architecture (non-negotiable)**
- Plain SQL only. No ORM, no Alembic. Migrations are numbered `.sql` files in
  `migrations/`, tracked in `schema_version`.
- PostgreSQL via `psycopg[binary,pool]` against the Supabase **session-mode**
  pooler. Never `supabase-py`.
- Every LLM, STT and TTS call goes through `app/llm.py` or `app/speech.py`.
  A provider SDK is imported nowhere else.
- Every user-facing string lives in `app/texts.py`.
- Every environment variable is read in `app/config.py` and nowhere else.
- Excluded by decision: ORM, Redis, Celery, Docker, web framework.

**Behaviour**
- Fail loud to the operator, soft to the user. A user never sees a stack trace
  or an exception message.
- Copy follows `docs/PRD.md` §8: under 400 characters for scheduled messages,
  one idea per message, never guilt, buttons over typing.
- Audio is never written to disk.

**Every slice ends by**
- Updating `BUILD_PROGRESS.md`: slice row, header fields, file inventory,
  decisions log, known issues, next action.
- Marking the slice 🟡 code-complete. Only the human marks ✅, after verifying
  in Telegram.

### `requirements.txt`

Three lines only:

```
python-telegram-bot>=21.6,<23
psycopg[binary,pool]>=3.2
python-dotenv>=1.0
```

The upper bound on python-telegram-bot makes a v23 upgrade a deliberate act
rather than an accident. The API used here (`ApplicationBuilder`,
`CommandHandler`, `run_polling`) is unchanged across v21 and v22.

### `app/config.py`

`.env` into a frozen, typed `Settings` dataclass.

| Key | Required | Default |
|---|---|---|
| `DATABASE_URL` | yes | — |
| `TELEGRAM_BOT_TOKEN` | yes | — |
| `DB_POOL_MIN` | no | 1 |
| `DB_POOL_MAX` | no | 5 |
| `LOG_LEVEL` | no | `INFO` |

Requirements:

- Missing required keys raise a fatal `ConfigError` naming **all** missing keys
  at once, not just the first one found.
- Real environment variables win over `.env`, so systemd and CI can override.
- Reject a `DATABASE_URL` that is not a `postgresql://` or `postgres://` DSN.
- Reject `DB_POOL_MIN < 1` or `DB_POOL_MAX < DB_POOL_MIN`.
- Provide a helper returning the DSN with the password stripped, for logging.
  The password must never reach a log line.
- Log a WARNING — do not fail — if the DSN port is `6543`. That is Supabase's
  transaction-mode pooler, which breaks psycopg3 prepared statements;
  `ARCHITECTURE.md` §2 requires session mode. The port is a heuristic, not a
  guarantee, so a wrong guess must not stop the operator from starting the bot.

### `app/db.py`

Connection pool and migration runner.

**Pool:** `psycopg_pool.ConnectionPool` against `DATABASE_URL`, `min_size=1`,
`max_size=5` from settings. Opened lazily on first use, not at import. Expose
`connection()` and `cursor()` context managers so no later slice constructs its
own connection.

**Migration runner:** reads `NNN_name.sql` files from `migrations/`, applies
pending ones in version order, records applied versions in `schema_version`.

> **Trap — read this before writing the runner.**
> `migrations/001_init_postgres.sql` both creates the `schema_version` table
> *and* inserts its own version row. So:
> 1. The runner must `CREATE TABLE IF NOT EXISTS schema_version` **itself**
>    before it can read applied versions — it cannot assume 001 ran.
> 2. The runner must record versions with
>    `INSERT ... ON CONFLICT DO NOTHING`, so 001's own insert does not collide
>    with the runner's bookkeeping.
>
> This keeps the runner authoritative whether or not a migration file records
> itself. A naive implementation crashes on the first `migrate`.

Further requirements:

- One transaction per migration file. A failure leaves earlier files committed
  and the failing one fully rolled back. Never a half-applied schema.
- Hold a `pg_advisory_lock` for the duration of the run so two deploys cannot
  race. Release it in a `finally`.
- Use a dedicated `psycopg.connect` for migrations, not the pool — migrations
  run before the application starts.
- Reject duplicate version numbers and filenames not matching `NNN_name.sql`,
  with a clear error naming the offending files.
- Running `migrate` twice must be a clean no-op.

**CLI:** `python -m app.db migrate` and `python -m app.db status`. `status` is
read-only and reports applied vs pending versions. Both exit non-zero with a
readable message on config or database error — never a bare traceback.

### `app/texts.py`

Docstring stating that every user-facing string in the product belongs in this
module and must never be written inline in a handler or service, plus the single
constant `/ping` needs. Nothing else.

### `app/main.py`

- Build the Telegram application from `Settings`.
- Register exactly one handler: `CommandHandler("ping", ...)` replying with the
  constant from `texts.py`.
- Start polling.
- Do **not** connect to the database at startup. Keeping the two acceptance
  criteria independently verifiable is worth more here than an early health
  check; a real startup check belongs with the heartbeat work in S18.
- Set the `httpx` logger to WARNING or the poll loop floods the log at INFO.
- A `ConfigError` prints a readable message and exits non-zero.

### `.env.example`

Dummy values for every key `config.py` reads. Include a comment on
`DATABASE_URL` explaining the three Supabase connection options and why session
pooler is the required one: direct connections are IPv6-only, the transaction
pooler on 6543 breaks prepared statements.

### `.gitignore`

`.env`, `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`

---

## Doc fixes (part of this slice)

1. **`ARCHITECTURE.md` contradicts itself on the database.** §1 principle 1 says
   "SQLite"; §5's backup job says `sqlite3 .backup`; §7 says "Database file
   `chmod 600`". All three contradict the PostgreSQL/Supabase decision in §2 and
   in the `BUILD_PROGRESS.md` decisions log. Correct those three lines to match
   Postgres. Change nothing else in the document — this is a correction, not a
   rewrite.

2. **`ARCHITECTURE.md` §3 has no `specs/` directory.** Add it, or a later slice
   may delete the folder as "not in the structure":
   ```
   ├── specs/
   │   ├── S0-repo-skeleton.md
   │   └── ...
   ```

---

## Acceptance criteria

Each is verified manually by the human. The slice is not ✅ until all pass.

1. **Config fails loudly.** With `.env` absent, `python -m app.db status` exits
   non-zero and prints a message naming both `DATABASE_URL` and
   `TELEGRAM_BOT_TOKEN`.
2. **Migration applies.** `python -m app.db status` reports version 1 pending;
   `python -m app.db migrate` applies it; a second `migrate` reports no work.
3. **Schema is correct.** The Supabase database contains 13 tables
   (`schema_version`, `users`, `error_types`, `errors`, `chunks`, `book_units`,
   `sessions`, `streaks`, `interests`, `readings`, `couple_challenges`,
   `couple_scores`, `calibration_log`) and `error_types` holds 19 rows.
4. **Bot answers.** `python -m app.main` starts; `/ping` in Telegram returns
   `pong`.
5. **Secrets stay out of logs.** No log line at `LOG_LEVEL=INFO` contains the
   database password or the bot token.

## Definition of done

- All five acceptance criteria pass.
- `BUILD_PROGRESS.md` updated: S0 row 🟡 with date, header fields, full file
  inventory, decisions log entries for every ambiguity resolved, known issues,
  next action.
- The human has run the verification steps and flipped S0 to ✅.
