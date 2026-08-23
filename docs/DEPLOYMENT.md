# Deployment — Hetzner

Operational runbook for the production host. Deployed 2026-08-11.

## What runs where

| Role | Detail |
|---|---|
| Host | Hetzner CPX32 `fonderis-worker`, `78.46.240.136`, Nuremberg |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3 |
| Bot code | `/home/bot/english-bot` (user `bot`) |
| Bot process | `english-bot.service` (systemd) |
| Database | PostgreSQL 16 on `127.0.0.1:5432`, DB `english_bot`, owner `bot` |
| Backups (local) | `/home/bot/english-bot-backups` via `bot` crontab |
| Runtime files | `/home/bot/english-bot-runtime` |

**Shared machine.** Also running:

| Service | Ports / notes |
|---|---|
| `fonderis-worker.service` (Node) | 3011 |
| Redis | 6379 |
| Caddy | 80 / 443 |

The bot **must not** assume exclusive use of the host. It needs **no inbound port** — it long-polls Telegram outbound. Nothing was opened in the firewall for the bot; nothing conflicts with the Node app.

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
| `BACKUP_OFFSITE_DIR` | **Leave unset** until an off-site path exists (see Known issue #6 in `BUILD_PROGRESS.md`) |
| `TELEGRAM_BOT_TOKEN` | Same bot token as development (only one process may poll — see below) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / LLM-STT-TTS keys | Same providers; real keys required for live use |
| `COUPLE_CHAT_ID` | Unset until `/here` in the shared group |

Then migrate:

```bash
cd /home/bot/english-bot
.venv/bin/pip install -e packages/core   # W1: makes `core` importable
.venv/bin/python -m core.db migrate
# Expect migrations 001–005 applied
```

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

With `BACKUP_OFFSITE_DIR` unset, the script still dumps locally and logs `off-site copy skipped (BACKUP_OFFSITE_DIR not set)`.

---

## Deploying an update

Stop any laptop/`python -m apps.bot.main` instance first (see **Two instances** below).

```bash
sudo -u bot -i
cd /home/bot/english-bot
git pull
.venv/bin/pip install -r requirements.txt   # when requirements.txt changed
.venv/bin/pip install -e packages/core      # W1: required once, and after any
                                            # packages/core/pyproject.toml change
.venv/bin/python -m core.db migrate
sudo systemctl restart english-bot
```

Verify:

```bash
journalctl -u english-bot -n 50 --no-pager
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

## Two instances is the classic failure

Telegram delivers each update to **one** long-poller. A laptop instance left running will silently steal roughly half the updates; the server looks intermittently dead.

Before starting or restarting production:

1. Stop the other process (`Ctrl-C`, kill the local `python -m apps.bot.main`, or disable any other host’s unit).
2. Confirm only one poller: `/ping` succeeds consistently; `journalctl -u english-bot -f` shows traffic for your taps.
3. The in-process flock only protects two processes on the **same** machine — it does not stop a second host.
