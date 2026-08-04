# S4b · Database backups

**Slice:** S4b
**Phase:** 1 — Foundation (post Phase-1 ship; before Phase 2)
**Depends on:** S0 (Postgres reachable via `DATABASE_URL`)
**Status:** ⬜ not started
**Spec written:** 2026-08-04

---

## Goal

Daily `pg_dump` of the self-hosted Postgres database is the only protection for
the error journal. No managed backups. Scripts must run from cron without the
Python venv.

---

## Non-goals

- No cloud SDK, rclone credentials, or off-site automation in this slice —
  leave a clearly marked stub.
- Do not install crontab (document only).
- Do not start Phase 2 / S5.
- Do not modify application Python code, migrations, or tests.

---

## Locked decisions

1. **Bash, not Python** — cron must not depend on the venv.
2. **Custom format (`-Fc`), compressed** via `pg_dump`.
3. **Parse `DATABASE_URL` from `.env`** — never hardcode host/port/db. Mac uses
   5433; Hetzner will use 5432; both come from the URL.
4. **Default dump dir `~/english-bot-backups`**, override with `BACKUP_DIR`.
   Filename `english_bot_YYYY-MM-DD_HHMM.dump`.
5. **Sanity floor 10 KB** — a dump below that is failure; never count as success.
6. **Keep 14 local days** — delete older dumps only after a successful new dump.
7. **Refuse if dump dir is inside the git repo** — dumps contain private writing
   (PRD §10) and must never be committable.
8. **Log to `$BACKUP_DIR/backup.log`** — timestamped success and failure lines.
9. **Restore defaults to scratch DB** `english_bot_restore_test`; targeting
   `english_bot` requires `--force`.
10. **Off-site copy is a stub** — documented function naming rsync / rclone /
    manual weekly copy. Known-issue until automated.

---

## Scripts

### `scripts/backup.sh`

- Load `.env` from repo root (script lives in `scripts/`).
- Dump, verify size ≥ 10 KB, retain 14 days, call off-site stub.
- Exit non-zero with a clear message on any failure.

### `scripts/restore.sh`

```
scripts/restore.sh <dump-file> [target-db] [--force]
```

- Default target-db: `english_bot_restore_test`.
- `--force` required when target is `english_bot`.

---

## Scheduling (document only)

```
0 4 * * * /path/to/english-bot/scripts/backup.sh >> /path/to/backup.log 2>&1
```

---

## Acceptance

1. `backup.sh` produces a non-trivial dump outside the repo.
2. `restore.sh` into scratch DB; `errors` and `error_types` counts match live.
3. Scratch DB dropped afterwards.
4. Bad `DATABASE_URL` → non-zero exit, failure logged, no retention deletes.
5. Backup dir outside repo; nothing dump-related in `git status`.
