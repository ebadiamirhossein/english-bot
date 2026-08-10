# Architecture

**Version 2.0 · 31 July 2026**

---

## 1. Principles

1. **Boring technology.** PostgreSQL, Python, cron-like scheduling. No Docker orchestration, no message queues, no microservices. Two users.
2. **Provider-agnostic AI.** Every LLM, STT and TTS call goes through a wrapper. Swapping providers is one environment variable.
3. **The database is the product.** Code is replaceable; the error journal is not. Back it up obsessively.
4. **Fail loud to the operator, soft to the user.** A user never sees a stack trace; you get an alert.
5. **Vertical slices.** Every task ships something usable end-to-end, not a layer.

## 2. Stack

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.12 | Best SDK support |
| Bot | python-telegram-bot v21+ | Mature, async, well-documented |
| Scheduling | APScheduler in-process | No separate cron; survives with the app |
| Database | Self-hosted PostgreSQL 16 on the Hetzner box | No managed-DB fee; application code unchanged; backups are our job |
| DB driver | `psycopg[binary,pool]` | Plain SQL + own pool. Never `supabase-py` |
| Migrations | Plain numbered `.sql` files + `schema_version` | No ORM, no Alembic |
| LLM | Wrapper over Anthropic / OpenAI | Switchable |
| STT | OpenAI Whisper API | Most mature |
| TTS | OpenAI TTS | Most mature |
| Vision (M5) | Same LLM wrapper, vision-capable model | Reuse |
| Host | Hetzner CX22, Ubuntu 24.04 | ~€4–6/mo, EU, GDPR |
| Process | systemd, `Restart=always` | Simplest supervision |

Deliberately excluded: ORM, Redis, Celery, Docker, web framework, `supabase-py`.

### Database connection notes

- Connect with `psycopg[binary,pool]` over a normal `postgresql://` DSN (typically `127.0.0.1` on the same box).
- Connection pool: min 1, max 5. Two users generate trivial load.
- The Hetzner box holds the database. If the disk dies or the box is wiped without a recent off-box copy, the error journal is gone. Off-box `pg_dump` backups (slice S4b) are the only protection — not optional.

## 3. Project structure

```
english-bot/
├── app/
│   ├── main.py               # entrypoint: build app, register handlers, start
│   ├── config.py             # env → typed Settings object
│   ├── db.py                 # connection, migration runner, helpers
│   ├── llm.py                # provider-agnostic chat + vision
│   ├── speech.py             # transcribe(), synthesize()
│   ├── scheduler.py          # all recurring jobs
│   ├── texts.py              # every user-facing string, one place
│   ├── handlers/
│   │   ├── onboarding.py     # /start conversation
│   │   ├── help.py           # /help (S18b)
│   │   ├── quiz.py           # M1
│   │   ├── correction.py     # M2, M11
│   │   ├── voice.py          # M3, M9, M12
│   │   ├── reading.py        # M4
│   │   ├── book.py           # M5
│   │   ├── prep.py           # M10
│   │   ├── couple.py         # M8, M15
│   │   └── settings.py       # /settings, /pause, /stats
│   ├── services/
│   │   ├── users.py          # get/save user, onboarding, EF SET → CEFR
│   │   ├── errors.py         # journal writes, spacing, resolution, M13
│   │   ├── chunks.py
│   │   ├── streaks.py        # streak, freeze, rescue mode
│   │   ├── motivation.py     # nudge ladder, Sunday report
│   │   ├── interests.py      # profile, weights
│   │   ├── calibration.py    # M14
│   │   ├── anki.py           # M6 export
│   │   ├── commands.py       # setMyCommands list (S18b)
│   │   ├── watch_import.py   # S15a CSV import + Anki outbox
│   │   └── paths.py          # path-outside-repo (PRD §10)
│   └── prompts/
│       ├── correction.txt
│       ├── quiz.txt
│       ├── voice.txt
│       ├── reading.txt
│       └── book_ocr.txt
├── migrations/
│   └── 001_init_postgres.sql
├── tests/
├── scripts/
│   ├── backup.sh
│   └── heartbeat.py
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── TASKS.md
├── specs/
│   ├── S0-repo-skeleton.md
│   └── ...
├── .env.example
├── .cursorrules
├── BUILD_PROGRESS.md
└── requirements.txt
```

## 4. Key interfaces

### `llm.py`

```python
def chat(
    messages: list[dict],
    *,
    system: str | None = None,
    json_mode: bool = False,
    max_tokens: int = 1000,
    images: list[bytes] | None = None,
) -> str | dict:
    """Provider chosen by settings.LLM_PROVIDER. Retries 3x with backoff.
    Raises LLMError on final failure — callers must handle."""
```

Never call a provider SDK anywhere else in the codebase.

### `speech.py`

```python
def transcribe(audio: bytes, *, language: str = "en") -> str
def synthesize(text: str, *, voice: str = "alloy") -> bytes
```

Audio is deleted immediately after transcription. Never written to disk.

### `services/errors.py`

```python
def record_errors(user_id: int, source: str, errors: list[dict]) -> None
def due_errors(user_id: int, limit: int = 5) -> list[Error]
def mark_result(error_id: int, correct: bool) -> None   # applies spacing ladder
def resolved_types(user_id: int, since_days: int = 21) -> list[str]
def top_error_types(user_id: int, n: int = 5) -> list[str]
```

Spacing ladder on correct answers: 1 → 3 → 7 → 21 → 60 days. Any wrong answer resets to 1 day and increments `times_wrong`.

## 5. Scheduled jobs

All registered in `scheduler.py`, all timezone-aware per user.

| Job | Schedule | Action |
|---|---|---|
| `send_daily_quiz` | user's `morning_time` | M1 (Sun: 15Q weekly test; else 5Q / rescue 3Q) |
| `send_evening_task` | user's `evening_time` | M3 / M4 / M9, rotating |
| `nudge_check` | every 30 min | nudge ladder, respects the 3-message ceiling |
| `couple_challenge` | 18:00 | M8 |
| `anki_export` | Sat evening (`evening_time`) | M6 Anki TSV |
| `sunday_report` | Sun evening (`evening_time`) | M7 progress report |
| `monthly_reset` | 1st, 00:05 | freeze tokens → 2; M13 sweep |
| `heartbeat` | hourly | alert operator if no job fired in 26h |
| `backup_freshness` | hourly | alert operator if newest off-site dump older than 48h (or missing); no-op if `BACKUP_OFFSITE_DIR` unset |
| `watch_poll` | every 5 min | S15a CSV import from `WATCH_DIR` inboxes; no-op if unset |
| `backup` | daily 04:00 (cron) | `pg_dump` to local + off-site copy, keep 14 days each |

## 6. Error handling

- Any LLM failure inside a user-facing flow → user sees "give me a second, trying again"; on second failure, "something broke on my side, I'll retry this later" and the task is re-queued for the next slot.
- Never surface exceptions to the user.
- All exceptions logged with `user_id` and handler name; operator alerted via a private Telegram message for anything unhandled.

## 7. Security

- SSH key auth only, password auth disabled, `ufw` allowing 22 only.
- Secrets in `.env`, never committed. `.env.example` documents keys with dummy values.
- Bot responds only to `telegram_user_id` values present in `users`, plus `/start`. Everything else is silently ignored — this is the whole access-control model for Phases 1–4.
- Database credentials in `.env` with mode `600`; no database files on the host.

## 8. Testing

Every slice must be manually verifiable in Telegram against its acceptance criteria in `TASKS.md`. Automated tests are required only for `services/errors.py` (the spacing ladder) and `services/streaks.py` (freeze and rescue logic), because those are the two places where a silent bug destroys the product's value without being visible.

## 9. Deployment

```bash
# one-time
sudo apt update && sudo apt install -y postgresql-16
sudo -u postgres createuser --pwprompt bot
sudo -u postgres createdb -O bot english_bot
# DATABASE_URL=postgresql://bot:PASSWORD@127.0.0.1:5432/english_bot

adduser bot && su bot
git clone <repo> && cd english-bot
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in
.venv/bin/python -m app.db migrate

# systemd unit at /etc/systemd/system/english-bot.service
# Restart=always, RestartSec=10, User=bot

# deploy loop
git pull && .venv/bin/pip install -r requirements.txt \
  && .venv/bin/python -m app.db migrate \
  && systemctl restart english-bot
```
