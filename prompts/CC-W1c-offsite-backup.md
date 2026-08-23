# Claude Code — W1c · Off-site backup to Cloudflare R2

**Run in: AGENT MODE.**
**Scope: `pg_dump` → Cloudflare R2, 14-day retention, a freshness alarm that actually fires, one real documented restore, and the two new systemd units written and installed. Closes known issue #6.**

This slice ends the single largest risk in the project. Since 2026-08-11 the only copy of the production error journal has been a nightly local dump sitting on the same disk as the database it came from. That is not a backup; it survives an accidental `DROP` and nothing else. **W2 is the first slice to run a migration against that journal**, and this slice is what makes that safe.

`CLAUDE.md` §5 is the reason this matters more than it looks: *code is replaceable, the journal is not.*

---

## Before anything: read `CLAUDE.md`

Three sections bind this slice.

- **§3 rule 3 — test configuration the way it is really set.** This is the *exact* rule known issue #26 was written from: `backup.sh` read `DATABASE_URL` from `.env` but took `BACKUP_DIR` and `BACKUP_OFFSITE_DIR` from the process environment only. Configured in `.env`, they looked unset, and the script silently skipped. **Eighteen tests passed** because the harness exported them as real environment variables and never exercised the `.env` path. Every new R2 variable in this slice must be read through the same `env_file_get` / `apply_dotenv_*` path, and its regression test must write a temp `.env` — never export a variable.
- **§3 rule 5 — a test must never derive its expected value from the function under test.** The retention test must not ask the pruning function which files it kept.
- **§5b — never run a production entrypoint during a slice.** The new units are *installed* in this slice, but no acceptance check may start a Telegram polling loop against the real token.

---

## Already done by the human — do not redo

- Cloudflare R2 bucket **`english-bot-backups`** exists (Automatic location → Eastern Europe, Standard storage class, not public).
- An **Account** API token scoped to that one bucket, Object Read & Write, no TTL, no IP filter.
- Five keys are already in `/home/bot/english-bot/.env` on the server, mode 600:

```
R2_ACCOUNT_ID
R2_BUCKET
R2_ENDPOINT
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
```

**Use exactly these five names.** They are already set on the server; renaming them means a silent skip on the first real run, which is the failure this slice exists to end. Add all five to `.env.example` with placeholders and a comment.

**Never print, log or echo `R2_SECRET_ACCESS_KEY`.** Not at DEBUG, not in an error path, not in an alert body. Logs carry user ids and route names only (`CLAUDE.md` §5).

---

## Part 1 — the upload path

Extend `scripts/backup.sh` rather than writing a second script. It already dumps correctly, already has the `.env` loading fix from #26, and already runs from the `bot` crontab at 04:00 UTC. A parallel script would mean two retention policies and two things to keep in step.

- Upload the dump produced by the existing local step. **Local dumps continue** — R2 is a second copy, not a replacement. Do not remove the local path.
- Use the **AWS CLI v2** (`aws s3` with `--endpoint-url`) or `boto3`, whichever you can install cleanly on Ubuntu 24.04 with the venv already present. State which you chose and why in the decisions log. Do not add a heavyweight dependency to `requirements.txt` for a shell-level concern if the CLI serves.
- **Object key layout:** `english_bot/<YYYY>/<MM>/english_bot_<YYYY-MM-DD>_<HHMM>.dump` — dated prefixes make a human browsing the bucket able to find a given day without listing everything.
- **Every failure is loud.** A failed upload must exit non-zero, log at ERROR, and leave the local dump in place. A backup that fails quietly is worse than one that never ran, because it is trusted.
- If the five R2 variables are absent, log at INFO that the R2 copy was skipped and **continue** with the local dump. That mirrors the existing `BACKUP_OFFSITE_DIR` behaviour and keeps the Mac working without R2 credentials.

---

## Part 2 — retention, 14 days

- Prune objects under the `english_bot/` prefix older than 14 days, after a successful upload — **never before**, and never if the upload failed. Pruning on a failed run is how you end up with neither an old copy nor a new one.
- **Never prune the newest object**, whatever its age. If uploads have been broken for a month, the one surviving dump must not be deleted by its own retention rule.
- Do not use an R2 lifecycle rule for this. The script owns retention so the logic is visible in the repo, testable, and identical on the Mac.
- **Retention test:** build a fixture list of object keys with known dates, hardcode which ones must survive, and compare. The expected set is written by hand, not produced by calling the pruning function (§3 rule 5).

---

## Part 3 — the freshness alarm

`backup_freshness` already exists and already works — the W1b worker run proved it, correctly reporting a 305-hour-old dump on the Mac. The defect is #31: **it is silent when nothing is configured**, so an unconfigured backup and a healthy one look identical.

- Point the check at **R2**, not only at a local directory: list the newest object under the prefix and compare its age.
- **Alert when the newest R2 object is older than 26 hours** (a 24-hour cycle plus slack for a late cron).
- **Alert when R2 is not configured at all on the server.** Silence must no longer be a valid state in production. On the Mac, unconfigured stays quiet — a dev machine is not expected to hold backups. Decide this by whether the five variables are present, not by hostname.
- Route it through `core.services.alerts` with the existing throttle, so a broken backup produces one alert a day and not one every fifteen minutes.
- **Known issue #65 is the honest limitation here:** `apps/api` has no real alert sink and the worker's alerts land in the log. Say plainly in the decisions log where this alarm is actually delivered today, and whether the operator will see it without running `journalctl`. If the answer is "no", say so — do not describe a log line as an alert.

---

## Part 4 — the restore drill, performed for real

**This is the acceptance criterion that matters.** An untested backup is a hypothesis. #6 does not close because a file appears in a bucket; it closes because a database was rebuilt from that file.

Write `scripts/restore_from_r2.sh` and then **run it**:

1. Download the newest dump from R2 to a temp path
2. `createdb english_bot_restore_test`
3. `pg_restore` into it
4. Verify with row counts on the tables that matter — `errors`, `chunks`, `users`, `sessions` — compared against the live database
5. `dropdb english_bot_restore_test`

Document the real run in `docs/DEPLOYMENT.md` under a new **Restoring from R2** section: the actual commands, the actual row counts observed, the date, and how long it took. Not a template — the real numbers from the real run.

**If the restore fails, stop and report it.** Do not fix forward into a passing test. A failed restore drill is the most valuable output this slice could produce, and burying it would waste it.

---

## Part 5 — the two systemd units

W1b documented `english-api` and `english-worker` but did not install them. Install them now.

- `english-worker.service` — `ExecStart=/home/bot/english-bot/.venv/bin/python -m apps.worker.main`, `User=bot`, `WorkingDirectory=/home/bot/english-bot`, `Restart=always`, `RestartSec=10`, journal logging.
- `english-api.service` — uvicorn against `apps.api.main:app`, bound to **`127.0.0.1`** only. The API must not be exposed directly; Caddy already holds 80/443 on this shared host and will terminate TLS for `api.foundgrant.com` at W2. **Do not touch the Caddy config in this slice** — no route exists to serve yet.
- **`english-worker` and `english-bot` must not both run the same jobs.** The worker owns `streak_rollover`, `monthly_freeze_reset`, `monthly_reset`, `heartbeat`, `backup_freshness`; the bot still owns the delivery jobs until W20. Check `apps/bot/scheduler.py` and confirm the two job tables are disjoint. **If they overlap, do not install the worker unit — stop and report it.** Two processes running `streak_rollover` against one database is a data-integrity problem, not a tidiness one.
- Confirm the worker's instance lock file does not collide with the bot's.

Document both units in `DEPLOYMENT.md`, including how to check status and read logs.

---

## Part 6 — the deploy sequence

`DEPLOYMENT.md` still shows the pre-W1 sequence in places (`python -m app.db migrate`, `ExecStart=... -m app.main`). Bring the whole document to the current truth:

- **backup → pull → `pip install -e packages/core` → migrate → restart** (`CLAUDE.md` §5, settled, not to be re-argued)
- `python -m core.db migrate` and `python -m core.db status`, not `app.db`
- `ExecStart` for the bot is `python -m apps.bot.main`
- Add restart lines for the two new units

---

## Acceptance

```bash
pytest -q                                    # green, zero failures
scripts/backup.sh                            # on the server: local dump + R2 object
aws s3 ls s3://english-bot-backups/english_bot/ --endpoint-url <R2_ENDPOINT>
scripts/restore_from_r2.sh                   # real restore into a scratch DB, real row counts
systemctl status english-worker english-api  # both active
```

Then, to prove the alarm is real rather than asserted: **delete the newest object in the bucket, run the freshness check, and confirm it alerts.** Put the newest object back afterwards, or run a fresh backup. An alarm that has never fired on real data is an assumption.

---

## Out of scope

- No auth, no Better Auth, no `users` columns, no migration — that is W2
- No DNS records, no Caddy config, no TLS certificate — W2 owns `api.foundgrant.com`
- No domain routes: no `/correct`, no `/session`
- No changes to any file under `packages/core/services/` except the freshness check itself
- No prompt edits
- **Do not fix known issue #60** (`core.services.access_control` importing from `apps.bot`). Still open, still belongs to the slice that deliberately widens the boundary test.
- **Do not perform the kernel reboot.** The human runs it before this deploy — see below.

If something here needs a migration or a wider core change, stop and say so.

---

## The kernel reboot — the human runs this, not you

Known issue #32: the server runs 6.8.0-124 with 6.8.0-137 available, and the reboot also restarts `fonderis-worker`, a separate production service. The human has said any time is acceptable and will run it **before deploying this slice**:

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
# wait ~60s, then reconnect
uname -r                                  # expect 6.8.0-137
systemctl status english-bot fonderis-worker postgresql
```

Do not run these. Do not add them to an acceptance script. They are here so the sequence is recorded in one place.

---

## BUILD_PROGRESS.md update block

Make **all** of the following edits. The human no longer hand-edits this file — everything goes through this block.

- **Slice row:** `| W1c | Off-site backup — Cloudflare R2 | 🟡 code-complete | <date> | pg_dump → R2, 14-day retention, freshness alarm, restore drill performed; api + worker units installed |`

- **W1b row → ✅.** The human has run all three W1b checks and accepted the result: the worker refused a second start with exit code 1, the web shell renders correctly on an iPhone across all four nav items, and the visual direction is approved. `curl` output for both health routes was verified in the W1b report. Set W1b to `✅ done & verified`, dated 2026-08-23. **This is the human's instruction relayed — you are still never to mark a slice ✅ on your own judgement** (`CLAUDE.md` §1).

- **Decisions log — record each of these with its reason:**
  - Cloudflare R2 chosen over a Hetzner Storage Box: R2 is already required from W7 for generated audio, and putting backups behind a different vendor from the server means one compromised or suspended account cannot take the database and its backups together.
  - Bucket location Automatic → Eastern Europe, Standard storage class: close to Nuremberg, inside the EU, and the freshness check reads the newest object daily, so Infrequent Access would cost more.
  - Account API token rather than User token, scoped to the single bucket: a User token dies with the user who created it, and a backup that stops silently is the failure mode this slice exists to close.
  - No client-IP restriction on the token: if Hetzner ever reassigns the address the backup breaks silently — bucket scoping is the safer boundary.
  - `localStorage` ban lifted **for theme preference only**: the human wants a light/dark toggle. It arrives at W2, which owns the shell and dark mode. Everything else — session state, learner content, progress — stays server-side. The original ban came from a rule about throwaway previews and was never a product decision.
  - The **domain is `foundgrant.com`** (already owned, registrar Namecheap, nameservers moved to Cloudflare 2026-08-23). `app.foundgrant.com` → Vercel, `api.foundgrant.com` → Hetzner behind Caddy. Existing Namecheap email-forwarding MX records and the SPF TXT record were imported intact and **must not be deleted**.
  - Whichever upload tool you chose (AWS CLI v2 or boto3) and why.
  - Where the freshness alert is actually delivered today, honestly stated (see #65).

- **Known issues:**
  - **Close #6** — but only if the restore drill actually succeeded. If it did not, #6 stays open, and that is the correct outcome to report.
  - **Close #31** (freshness check silent while unset) if the unconfigured-in-production case now alerts.
  - Update **#32** to closed if the human confirms the reboot ran, otherwise leave it open.
  - Carry forward everything still open: #2, #3, #5, #8, #13, #14, #15, #17, #18, #19, #20, #21, #22, #23, #24, #25, #27, #28, #29, #30, #33, #35, #36, #37, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #50–#60, #62, #64, #65, #66, #67. #49, #53 (TASKS half), #61, #63 and #68 are already closed — do not reopen them.
  - Add any new issue this slice surfaces, with severity and slice.

- **File inventory:** every new file — `scripts/restore_from_r2.sh`, the two unit files, new tests — plus the changed `scripts/backup.sh`, `.env.example` and `docs/DEPLOYMENT.md`.

- **Next action.** Rewrite it as this slice's human checks plus every earlier check still unrun:
  - **W1c's own checks:** confirm a dump lands in R2 the morning after deploy (04:00 UTC = 07:00 Vilnius); confirm the freshness alarm fires when the newest object is deleted; read the restore drill's recorded row counts and confirm they match production.
  - **Deferred from W1b, explicitly and not silently:** the **PWA home-screen install on iPhone** could not be verified — `next-pwa` disables service workers in dev, and a service worker needs a secure context, so a LAN IP over plain http cannot register one. **This check moves to W2**, where `app.foundgrant.com` gives it HTTPS. W2 already carries "installed to iPhone home screen" as an acceptance criterion.
  - **The v2 deploy backlog**, unchanged unless the human reports otherwise: S26c deployed, migrations 007+008 applied on Hetzner, the S25 pre-flight counts filled from production, and **#44** — evening reading confirmed running after `/interests`, which stays open until a real Mon/Wed/Fri delivery lands.
  - **The entire v2 desk-check list**, unchanged. W1c is infrastructure; it exercises no learner path and clears none of them.
  - **#57:** the §6b work-vocabulary SQL and the quiz-scenario frequency query, to be run on Hetzner before W5 rewrites the prompts.
  - **S8:** the shared group, `/here`, `COUPLE_CHAT_ID`, then the seven group checks.

Then stop. Do not begin W2.
