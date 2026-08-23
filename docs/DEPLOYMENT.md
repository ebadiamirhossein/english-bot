# Deployment — Hetzner

Operational runbook for the production host. Deployed 2026-08-11.

## What runs where

| Role | Detail |
|---|---|
| Host | Hetzner CPX32 `fonderis-worker`, `78.46.240.136`, Nuremberg |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3 |
| Bot code | `/home/bot/english-bot` (user `bot`) |
| Bot process | `english-bot.service` (systemd) |
| API process | `english-api.service` — unit written in `deploy/systemd/`, **not installed**; arrives at W2 |
| Worker process | `english-worker.service` — unit written, **not installed**; blocked by a job-table overlap, see [The worker unit is blocked](#the-worker-unit-is-blocked) |
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

# Required for the R2 restore drill (see "Restoring from R2" below).
sudo -u postgres psql -c 'ALTER ROLE bot CREATEDB;'
```

Confirm listen on **5432** (default on this host; Mac uses 5433).

**`ALTER ROLE bot CREATEDB` is not optional.** `bot` owns `english_bot`, but
ownership does not let a role create a *new* database, and
`scripts/restore_from_r2.sh` creates and drops a scratch one every time it
runs. Without it the drill fails at step 2/5. `CREATEDB` lets a role create and
drop its own databases and nothing else: it is not superuser, and it grants no
access to any database that already exists. The alternative — running the drill
as `postgres` — would demand superuser for a routine verification, which is
strictly worse. Added on production 2026-08-23 for exactly this reason.

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
| `R2_ACCOUNT_ID` / `R2_BUCKET` / `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | All five set. Account API token, Object Read & Write, scoped to `english-bot-backups`. `.env` stays mode 600. **`R2_ENDPOINT` must match the bucket's jurisdiction** — this bucket is EU, so `https://<account_id>.eu.r2.cloudflarestorage.com`; a mismatch presents as `AccessDenied` on every call, not as an endpoint error |
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

**Not from `apt`.** Ubuntu 24.04 has no `awscli` package in the default
repositories, and the version available elsewhere is v1. Use the official
installer:

```bash
sudo apt install -y unzip curl
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

aws --version   # observed 2026-08-23: aws-cli/2.36.29
```

It lands at `/usr/local/bin/aws`, which is on `bot`'s PATH — confirmed on this
host 2026-08-23. Both scripts and the freshness check shell out to that one
binary.

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

> **A pre-W1 unit file will not start.** W1 renamed the entrypoint module from
> the old `app` package to `apps.bot`. A unit whose `ExecStart` still names the
> old module fails with `status=1/FAILURE` and restarts in a loop —
> **this is exactly what happened on the W1c deploy, 2026-08-23.** Correct the
> line to `python -m apps.bot.main`, `sudo systemctl daemon-reload`, then
> restart. After that the service came up `active (running)`, loaded all twelve
> prompt templates from `core.PROMPTS_DIR`, registered its scheduler jobs, and
> began polling.

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
Settled at W1, run as written on the W1c deploy of 2026-08-23, not to be
re-argued. The backup comes first because it is the only step that cannot be
redone after the migration has run. The editable
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
# english-api and english-worker are not installed yet — they arrive at W2.
# See "The API and the worker" below.
```

Check `ExecStart` before the first restart after a W1-or-later pull: it must
name `apps.bot.main`, not the old pre-W1 module (see the warning under
**6. systemd unit**).

`core.db status` on this host reported **`Applied: 001–008, Pending: (none)`**
on 2026-08-23 — migrations 007 and 008 were already applied; only the S26c
*code* had been undeployed.

Step 1 now produces two copies: the local dump in `/home/bot/english-bot-backups`
and the R2 object. The local one is on the same disk as the database it came
from, so it survives an accidental `DROP` and nothing else; R2 is the copy that
survives losing the machine.

Verify:

```bash
journalctl -u english-bot -n 50 --no-pager
# journalctl -u english-api … and curl localhost:8000/health apply from W2,
# when the API unit is installed.
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

**Neither unit is installed on this host. Both arrive at W2.** The files are
written and reviewed in `deploy/systemd/`; nothing under
`/etc/systemd/system/` refers to them, and `systemctl status english-api` and
`systemctl status english-worker` both correctly report `not-found` today.

* **`english-api`** would install cleanly, but it serves no domain routes until
  W2 — an idle service on a shared production host buys nothing today, so it
  was deliberately left off at W1c.
* **`english-worker`** is blocked outright by the job-table overlap below
  (known issue #69), which the W1c deploy confirmed live.

Both need the same `.env`, the same venv, and `pip install -e packages/core`.
Neither needs `TELEGRAM_BOT_TOKEN`: `core.config` stopped requiring it at W1
precisely so these two can boot without one.

The unit files live in the repo at `deploy/systemd/`, so the unit that runs is
the unit that was reviewed rather than something retyped out of this document.

### english-api — at W2, not before

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

### The recorded run — 2026-08-23, production

**This is what closes known issue #6.** Run on the Hetzner host against the
real bucket and the real production database. The drill downloaded an actual
object from R2, created a scratch database, restored into it, and compared row
counts against live:

| table | restored | live | result |
|---|---|---|---|
| `errors` | 27 | 27 | match |
| `chunks` | 29 | 29 | match |
| `users` | 3 | 3 | match |
| `sessions` | 43 | 44 | behind live — the dump predates today's writes |

```
DRILL PASSED in 2s
```

Scratch database dropped at the end of the run, as designed.

**`sessions` lagging by one is the correct result, not a defect.** A dump
*should* trail the live database by exactly the writes that happened after it
was taken. An exact match on every table would have been the suspicious
outcome — it would suggest the drill was comparing the live database to itself
rather than to a restored copy.

The backup that produced the object was itself observed the same day:
`scripts/backup.sh` at **16:23 UTC**, `size=56176 bytes`, key
`english_bot/2026/08/english_bot_2026-08-23_1623.dump`, byte count verified on
both the local and the R2 side.

**Retention was verified on the same day**, across two consecutive backups: one
upload at 16:20 and another at 16:21, after which `list-objects-v2` returned
**both** objects. Nothing is deleted inside the 14-day window.

Re-run this drill after any change to `scripts/backup.sh` or
`scripts/restore_from_r2.sh`, and at least once a quarter otherwise. Paste the
new numbers here when you do.

**Earlier, and superseded: what was proved on the Mac, 2026-08-23.** Before the
deploy, the drill was run once against the Mac development database with a stub
standing in for the R2 transport only — the download step copied a local
`pg_dump` file, and `createdb`, `pg_restore`, the row-count comparison and
`dropdb` were all real. It showed the restore machinery worked and **nothing**
about Cloudflare R2; its row counts were a near-empty development database
(`errors` 0, `chunks` 2, `users` 1, `sessions` 1). Kept here only so the
distinction between that run and the production one above stays visible.

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

**Proved in both directions on 2026-08-23**, which is the only way an alarm is
worth anything — one that always fires is as useless as one that never does:

```
# with the english_bot/ prefix deleted
R2Health(status='empty', should_alert=True, …)

# after a fresh backup
R2Health(status='ok', should_alert=False,
         detail='Newest object … is 0.0h old (56176 bytes).')
```

**One caveat, now a known issue: R2 list-after-write lag.** On this same day an
object uploaded at 16:14 was successfully *downloaded* by the restore drill at
16:15, yet did not appear in `list-objects-v2` several minutes later — the
freshness check reported `status='empty'` for a bucket that provably held it,
and a later listing showed the object had been there all along. The object was
never lost, and retention was never at fault (an intermediate diagnosis that
retention was deleting live objects was **wrong**; it is recorded here so it is
not re-derived). The check has no tolerance for listing lag, so **running it
shortly after an upload can raise a false alarm.** Harmless at the 04:00 UTC
cron, which has hours of slack. If you are testing the alarm by hand and it
says `empty` right after a `backup.sh`, list the bucket again before believing
it.

**R2_ENDPOINT must carry the jurisdiction segment.** This bucket is under the
EU jurisdiction, so the endpoint is
`https://<account_id>.eu.r2.cloudflarestorage.com`. A token scoped to an EU
bucket signing against the *default* endpoint returns `AccessDenied` on every
operation — `PutObject`, `ListObjectsV2` and `ListBuckets` alike — and nothing
in the error names jurisdiction as the cause. It looks exactly like a token
permission problem and was misdiagnosed as one for several cycles on
2026-08-23.

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
