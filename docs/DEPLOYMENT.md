# Deployment — Hetzner

Operational runbook for the production host. Deployed 2026-08-11.

## What runs where

| Role | Detail |
|---|---|
| Host | Hetzner CPX32 `fonderis-worker`, `78.46.240.136`, Nuremberg |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3 |
| Bot code | `/home/bot/english-bot` (user `bot`) |
| Bot process | `english-bot.service` (systemd) |
| API process | `english-api.service` — unit in `deploy/systemd/`, installed at W1c |
| Worker process | `english-worker.service` — unit written, **deliberately not installed**; see [The worker unit is blocked](#the-worker-unit-is-blocked) |
| Web app | Vercel, not this host (ARCHITECTURE-v3 §9) |
| Database | PostgreSQL 16 on `127.0.0.1:5432`, DB `english_bot`, owner `bot` |
| Backups (local) | `/home/bot/english-bot-backups` via `bot` crontab |
| Backups (off-site) | Cloudflare R2 bucket `english-bot-backups`, prefix `english_bot/`, 14-day retention |
| Runtime files | `/home/bot/english-bot-runtime` |

**Shared machine.** Also running:

| Service | Ports / notes |
|---|---|
| `fonderis-worker.service` (Node) | 3011 |
| Redis | 6379 |
| Caddy | 80 / 443 |

The bot **must not** assume exclusive use of the host. It needs **no inbound port** — it long-polls Telegram outbound. Nothing was opened in the firewall for the bot; nothing conflicts with the Node app. The API binds `127.0.0.1:8000` behind Caddy — still nothing new open at the firewall.

Mac PostgreSQL (port 5433) is **development only**. Its data was not migrated; production started empty.

---

## First-time setup

Order matters. Run as root/`sudo` where noted, then as `bot`.

### 1. PostgreSQL

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql

sudo -u postgres createuser --pwprompt bot
sudo -u postgres createdb -O bot english_bot
```

Confirm listen on **5432** (default on this host; Mac uses 5433).

### 2. Service user

```bash
sudo adduser --disabled-password --gecos "" bot
sudo mkdir -p /home/bot/english-bot-backups /home/bot/english-bot-runtime
sudo chown bot:bot /home/bot/english-bot-backups /home/bot/english-bot-runtime
```

### 3. Deploy key and clone

As `bot`:

```bash
sudo -u bot -i
ssh-keygen -t ed25519 -C "english-bot-deploy" -f ~/.ssh/english-bot_deploy -N ""
cat ~/.ssh/english-bot_deploy.pub
# Add the public key to the GitHub repo as a read-only deploy key.

# ~/.ssh/config (or GIT_SSH_COMMAND) so git uses that key for github.com
git clone git@github.com:<org-or-user>/english-bot.git /home/bot/english-bot
cd /home/bot/english-bot
```

### 4. Venv and dependencies

```bash
cd /home/bot/english-bot
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 5. `.env`

```bash
cp .env.example .env
chmod 600 .env
# edit .env
```

Every key from `.env.example` applies. Values that **differ from development**:

| Key | Production value / rule |
|---|---|
| `DATABASE_URL` | `postgresql://bot:PASSWORD@127.0.0.1:5432/english_bot` (local PG, port **5432**) |
| `BACKUP_DIR` | `/home/bot/english-bot-backups` |
| `RUNTIME_DIR` | `/home/bot/english-bot-runtime` |
| `OPERATOR_TELEGRAM_ID` | Set (required for alerts + S18d operator bootstrap) |
| `WATCH_DIR` | **Leave unset** — no Drive client on the server; S15a dormant; CSV via Telegram (S15b) only |
| `BACKUP_OFFSITE_DIR` | **Leave unset** — R2 is the off-site copy now; this key is the older synced-folder path and there is no Drive client on the server |
| `R2_ACCOUNT_ID` / `R2_BUCKET` / `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | All five set. Account API token, Object Read & Write, scoped to `english-bot-backups`. `.env` stays mode 600 |
| `BACKUP_R2_REQUIRED` | **Leave unset** (= required). Only a machine that is not meant to hold backups sets `0` |
| `BACKUP_R2_MAX_AGE_HOURS` | Leave at the default `26` |
| `TELEGRAM_BOT_TOKEN` | Same bot token as development (only one process may poll — see below) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / LLM-STT-TTS keys | Same providers; real keys required for live use |
| `COUPLE_CHAT_ID` | Unset until `/here` in the shared group |

Then migrate:

```bash
cd /home/bot/english-bot
.venv/bin/pip install -e packages/core   # W1: makes `core` importable
.venv/bin/python -m core.db migrate
.venv/bin/python -m core.db status       # confirm the applied schema_version
# Expect migrations 001–008 applied
```

### 5b. AWS CLI v2 (for the off-site backup)

`scripts/backup.sh` and `scripts/restore_from_r2.sh` talk to R2 through the AWS
CLI. It is a shell tool for a shell concern — the backup runs from cron without
the venv, so a Python client would have meant giving it one.

```bash
sudo apt install -y awscli   # Ubuntu 24.04 ships v2
aws --version                # expect aws-cli/2.x
```

No `aws configure`: the scripts pass the R2 credentials in the child process's
environment, so there is no `~/.aws/credentials` on this host to leak or to
drift out of step with `.env`.

### 6. systemd unit

Create `/etc/systemd/system/english-bot.service`:

```ini
[Unit]
Description=English Learning Telegram bot
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=bot
Group=bot
WorkingDirectory=/home/bot/english-bot
ExecStart=/home/bot/english-bot/.venv/bin/python -m apps.bot.main
Restart=always
RestartSec=10
# Logs go to the journal (no disk message bodies — by design)
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now english-bot
sudo systemctl status english-bot
```

### 7. Backup crontab

As `bot` (`crontab -e`):

```cron
0 4 * * * /home/bot/english-bot/scripts/backup.sh >> /home/bot/english-bot-backups/backup.log 2>&1
```

**04:00 UTC = 07:00 Vilnius.** Scheduler job times stay per-user local; only the backup wall-clock is UTC.

With `BACKUP_OFFSITE_DIR` unset, the script still dumps locally and logs
`off-site copy skipped (BACKUP_OFFSITE_DIR not set)`.

With the five `R2_*` keys set it then uploads to
`english_bot/<YYYY>/<MM>/english_bot_<date>_<HHMM>.dump`, reads the object back
to check its size, and prunes objects older than 14 days — never the newest
one, whatever its age. With none of them set it logs
`R2 copy skipped (R2_* not configured)` and carries on. With *some* of them set
it exits non-zero, because a half-configured backup that quietly skips is the
failure this whole arrangement exists to prevent (known issue #26).

Confirm from the bucket side:

```bash
aws s3 ls s3://english-bot-backups/english_bot/ --recursive \
  --endpoint-url "$R2_ENDPOINT"
```

---

## Deploying an update

**The sequence is: backup → pull → `pip install -e packages/core` → migrate → restart.**
Settled at W1; not to be re-argued. The backup comes first because it is the
only step that cannot be redone after the migration has run. The editable
install comes before `migrate` because `core.db` cannot be imported without
it.

Stop any laptop/`python -m apps.bot.main` instance first (see **Two instances** below).

```bash
sudo -u bot -i
cd /home/bot/english-bot
./scripts/backup.sh                         # 1. backup — before anything else
git pull                                    # 2. pull
.venv/bin/pip install -r requirements.txt   #    when requirements.txt changed
.venv/bin/pip install -e packages/core      # 3. required once, and after any
                                            #    packages/core/pyproject.toml change
.venv/bin/python -m core.db migrate         # 4. migrate
.venv/bin/python -m core.db status          #    confirm the new schema_version
sudo systemctl restart english-bot          # 5. restart
sudo systemctl restart english-api          #    …and the API
# english-worker is not installed — see "The worker unit is blocked" below.
```

Step 1 now produces two copies: the local dump in `/home/bot/english-bot-backups`
and the R2 object. The local one is on the same disk as the database it came
from, so it survives an accidental `DROP` and nothing else; R2 is the copy that
survives losing the machine.

Verify:

```bash
journalctl -u english-bot -n 50 --no-pager
journalctl -u english-api -n 50 --no-pager
curl -s localhost:8000/health               # {"ok": true, "schema_version": N}
# In Telegram: /ping  → pong
# /ping is on the S18d access allowlist — it proves process liveness, not approval.
# Use /help (or any gated command) to confirm access.
```

---

## Reading logs

```bash
journalctl -u english-bot -f
# optional file log:
tail -f /home/bot/english-bot-runtime/bot.log
```

Message content never appears in logs by design — `user_id` / handler / errors only.

---

## Recovering from a lockout

If the S18d gate or a migration leaves the operator unable to use the bot, approve via SQL (escape hatch). Connect as the DB owner:

```bash
sudo -u postgres psql english_bot
```

```sql
INSERT INTO access_requests (
    telegram_user_id, display_name, status, requested_at, resolved_at
) VALUES (
    <OPERATOR_TELEGRAM_ID>,  -- bigint, same as OPERATOR_TELEGRAM_ID in .env
    'operator',
    'approved',
    NOW(),
    NOW()
)
ON CONFLICT (telegram_user_id) DO UPDATE SET
    status = 'approved',
    resolved_at = NOW();
```

Then `/start` or `/help` from that Telegram account. Configured `OPERATOR_TELEGRAM_ID` also always passes the gate when set — this upsert covers a missing/revoked row or a mis-set env id.

---

## Restoring a backup

```bash
cd /home/bot/english-bot
./scripts/restore.sh /home/bot/english-bot-backups/english_bot_YYYY-MM-DD.dump
# Default target: english_bot_restore_test (scratch)
```

Restores into a **scratch** database unless you pass the live name **and** `--force`:

```bash
./scripts/restore.sh /path/to/dump.dump english_bot --force
```

`--force` is required for `english_bot`. Prefer scratch + inspect before touching production.

---

## The API and the worker

Both need the same `.env`, the same venv, and `pip install -e packages/core`.
Neither needs `TELEGRAM_BOT_TOKEN`: `core.config` stopped requiring it at W1
precisely so these two can boot without one.

The unit files live in the repo at `deploy/systemd/`, so the unit that runs is
the unit that was reviewed rather than something retyped out of this document.

### english-api

```bash
sudo cp /home/bot/english-bot/deploy/systemd/english-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now english-api
sudo systemctl status english-api
curl -s localhost:8000/health     # {"ok": true, "schema_version": N}
```

It binds `127.0.0.1:8000`, never `0.0.0.0`. Caddy already terminates TLS on
this box and is the only thing that should face the internet; W2 gives it the
`api.foundgrant.com` route. Nothing new opens at the firewall.

`--workers 2` is safe here precisely because the API holds no schedule.

`.env` gains one key for the API at W2, when the domain exists:

```bash
# The browser origin the API trusts, alongside http://localhost:3000.
# Scheme included, no trailing slash, no wildcard.
WEB_ORIGIN=https://app.foundgrant.com
```

Until then leave it empty and the API allows localhost only.

### The worker unit is blocked

`english-worker.service` is written (`deploy/systemd/english-worker.service`)
and **must not be enabled yet.**

`apps/bot/scheduler.py` and `apps/worker/jobs.py` currently register the same
four job names:

```
streak_rollover   monthly_freeze_reset   heartbeat   backup_freshness
```

Enabling the worker would put two processes through `streak_rollover` against
one database. That is a data-integrity problem, not an untidiness one, so the
unit stays off the server until one side gives those jobs up — W20 is where
the bot's own scheduler retires.

`tests/test_backup_r2.py::test_bot_and_worker_job_tables_still_overlap` records
the overlap and fails the moment it changes, so the fix and the decision to
install arrive in the same change.

When it is disjoint:

```bash
sudo cp /home/bot/english-bot/deploy/systemd/english-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now english-worker
journalctl -u english-worker -n 50 --no-pager   # expect "Scheduler built jobs=…"
```

**One worker, always.** It takes `RUNTIME_DIR/worker.lock` at boot — its own
file, not the bot's `bot.lock` — and a second start exits non-zero. That guard,
like the bot's, only covers two processes on the *same* machine.

### Status and logs for both

```bash
systemctl status english-api english-worker
journalctl -u english-api -f
journalctl -u english-worker -n 100 --no-pager
```

Runtime files, all under `RUNTIME_DIR`:

| File | Written by |
|---|---|
| `bot.lock`, `bot.log` | `english-bot` |
| `worker.lock`, `worker.log` | `english-worker` |
| `last_job_fire` | `english-bot` only — the worker reads it and never writes it, so a dead bot still goes stale |

The API logs to the journal rather than to a file; `journalctl -u english-api`
is where its errors are, and an unhandled exception there is logged with the
route name and the user id and answered with a generic body.

`apps/web` does not deploy to this box at all — it is a Next.js app on Vercel
(ARCHITECTURE-v3 §9), and `WEB_ORIGIN` is what lets it call this API.

---

## Restoring from R2

An untested backup is a hypothesis. This is the drill; run it after any change
to `scripts/backup.sh`, and at least once a quarter otherwise.

```bash
sudo -u bot -i
cd /home/bot/english-bot
./scripts/restore_from_r2.sh
```

It downloads the newest object under `english_bot/`, creates
`english_bot_restore_test`, runs `pg_restore`, prints restored-vs-live row
counts for `errors`, `chunks`, `users` and `sessions`, and drops the scratch
database. `--keep` leaves it in place; `--key <object-key>` restores a specific
day instead of the newest. There is no `--force` and no way to name the live
database — this is meant to be run casually.

A restored count *lower* than live is expected: the dump is from 04:00 UTC and
the learners have written since. A restored count *higher* than live is not
explainable that way, and the script exits non-zero on it.

### The recorded run

**Not yet performed.** This section is where the real numbers go — the actual
commands, the actual row counts, the date, and how long it took — and it stays
empty rather than carrying a plausible-looking template, because a template
here would read exactly like evidence.

The drill could not run inside the W1c slice: it needs the R2 credentials and a
production database, both of which live on the server, and the slice was built
on the Mac with no access to either. Known issue #6 therefore **stays open**
until this section has real numbers in it.

To fill it in, run the drill on the server and paste the output here verbatim,
with the date and the elapsed seconds the script prints.

**What *was* proved, on the Mac, 2026-08-23.** The drill was run once against
the Mac development database with a stub standing in for the R2 transport only
— the download step copied a local `pg_dump` file, and every step after it was
real: `createdb`, `pg_restore`, the row-count comparison and `dropdb`.

```
1/5 downloading…
    340251 bytes
2/5 createdb english_bot_restore_test…
3/5 pg_restore…
4/5 row counts (restored vs live)…
    table            restored         live
    errors                  0            0   match
    chunks                  2            2   match
    users                   1            1   match
    sessions                1            1   match
5/5 cleanup…
    dropped english_bot_restore_test

DRILL PASSED in 2s
```

Read that for exactly what it is. It shows the restore machinery works — a
custom-format dump goes in, a usable database comes out, and the comparison
reports honestly. It shows **nothing** about whether an object can be written
to or read from Cloudflare R2, and the row counts are a near-empty development
database, not the production error journal. Known issue #6 closes on the
server, with real numbers, or not at all.

### Freshness alarm

`backup_freshness` runs hourly in the bot's scheduler. It alerts the operator
on Telegram when:

* the newest object under `english_bot/` is older than 26 hours (a 24-hour
  cycle plus slack for a late cron);
* the bucket holds no object at all;
* the listing call fails;
* R2 is **not configured** — silence is no longer a valid state (known issue
  #31). A machine that is not meant to hold backups sets `BACKUP_R2_REQUIRED=0`;
* some but not all five `R2_*` keys are set, on any machine.

One alert per day per problem, not one per hourly tick.

To prove the alarm rather than assume it, delete the newest object and wait for
the next tick:

```bash
aws s3 ls s3://english-bot-backups/english_bot/ --recursive --endpoint-url "$R2_ENDPOINT"
aws s3 rm s3://english-bot-backups/<newest-key> --endpoint-url "$R2_ENDPOINT"
# …expect a Telegram alert within the hour, then put a copy back:
./scripts/backup.sh
```

The same check also runs in `english-worker`, where it only reaches the journal
— that process has no operator channel (known issue #65). While the worker unit
is uninstalled, the bot's copy is the one that actually alerts.

---

## Two instances is the classic failure

Telegram delivers each update to **one** long-poller. A laptop instance left running will silently steal roughly half the updates; the server looks intermittently dead.

Before starting or restarting production:

1. Stop the other process (`Ctrl-C`, kill the local `python -m apps.bot.main`, or disable any other host’s unit).
2. Confirm only one poller: `/ping` succeeds consistently; `journalctl -u english-bot -f` shows traffic for your taps.
3. The in-process flock only protects two processes on the **same** machine — it does not stop a second host.
