# Claude Code — W1c closeout · record the live verification

**Run in: AGENT MODE.**
**Scope: `BUILD_PROGRESS.md` and `docs/DEPLOYMENT.md` only. No code changes, no test changes, no new features.**

W1c was deployed to Hetzner on 2026-08-23 and every acceptance criterion was verified against real infrastructure by the human. This slice records what happened. Several results contradict what the W1c report assumed, and the corrections matter more than the confirmations.

**Do not change any `.py`, `.sh`, or test file.** If something below looks like it needs a code fix, name it as a known issue and stop.

---

## 1. What was verified live, on the server

Record these as fact in the decisions log and in `DEPLOYMENT.md`. They are observed output, not expectations.

**The deploy.** `git pull` → `pip install -e packages/core` → `core.db status` reported **`Applied: 001–008, Pending: (none)`**. Migrations 007 and 008 were **already applied on production** — only the S26c *code* had been undeployed. The systemd unit's `ExecStart` still read `python -m app.main` and the service failed with `status=1/FAILURE` until it was changed to `python -m apps.bot.main`; after `daemon-reload` the bot came up `active (running)`, loaded all twelve prompt templates from `core.PROMPTS_DIR`, registered its scheduler jobs and started polling. **The W1 restructure is live on production and works.**

**The backup.** `scripts/backup.sh` produced a local dump and uploaded to R2 with a verified byte count on both sides. Observed run at 16:23 UTC: `size=56176 bytes`, key `english_bot/2026/08/english_bot_2026-08-23_1623.dump`.

**The restore drill — this is what closes #6.** `scripts/restore_from_r2.sh` downloaded a real object from R2, created a scratch database, restored into it, and compared row counts against the live production database:

| table | restored | live | result |
|---|---|---|---|
| `errors` | 27 | 27 | match |
| `chunks` | 29 | 29 | match |
| `users` | 3 | 3 | match |
| `sessions` | 43 | 44 | behind live — the dump predates today's writes |

`DRILL PASSED in 2s`. Scratch database dropped. **Write these exact numbers into `DEPLOYMENT.md`** under the Restoring from R2 section, with the date and the note that `sessions` lagging by one is correct behaviour: a dump *should* trail the live database by exactly the writes that happened after it was taken. An exact match on every table would have suggested the drill was comparing the live database to itself.

**Retention.** Verified across two consecutive backups: after uploading at 16:20 and again at 16:21, `list-objects-v2` returned **both** objects. Retention deletes nothing inside the 14-day window.

**The freshness alarm, both directions.** With the `english_bot/` prefix deleted: `R2Health(status='empty', should_alert=True, …)`. After a fresh backup: `R2Health(status='ok', should_alert=False, detail='Newest object … is 0.0h old (56176 bytes).')`. An alarm that only ever fires is as useless as one that never does; both states are now proven.

---

## 2. Decisions to record, with reasons

- **The R2 endpoint must carry the jurisdiction segment: `https://<account_id>.eu.r2.cloudflarestorage.com`.** The bucket was created under the EU jurisdiction, and a token scoped to an EU bucket signing against the *default* endpoint returns `AccessDenied` on **every** operation — `PutObject`, `ListObjectsV2`, `ListBuckets` alike — with nothing in the error naming jurisdiction as the cause. This cost several debugging cycles and was initially misdiagnosed as a token permission problem. **Update the `R2_ENDPOINT` comment in `.env.example` to say this explicitly**, including that the value must match the bucket's jurisdiction and that a mismatch presents as a permissions error.

- **`ALTER ROLE bot CREATEDB` is required on production** for the restore drill. `bot` owns `english_bot` but could not create the scratch database. `CREATEDB` permits a role to create and drop its own databases; it does not confer superuser and does not widen access to any existing database. The alternative — running the drill as `postgres` — would require superuser for a routine verification, which is strictly worse. Record this in `DEPLOYMENT.md` as a required setup step.

- **AWS CLI v2 is installed from the official installer, not from `apt`.** Ubuntu 24.04 has no `awscli` package in the default repositories, and the version that exists elsewhere is v1. Installed to `/usr/local/bin/aws`, version 2.36.29, confirmed on `bot`'s PATH. Record the install commands in `DEPLOYMENT.md`.

- **The `english-worker` and `english-api` systemd units were deliberately NOT installed.** The worker is blocked by the job-table overlap it correctly detected. The API would install cleanly but serves no routes until W2, and adding an idle service to a shared production host buys nothing today. Both are deployed at W2. `deploy/systemd/*.service` stays in the repo, uninstalled.

- **The kernel reboot (#32) was not needed.** The server is already running **6.8.0-138** — newer than the 6.8.0-137 the issue was written against — and `apt` reported *"Running kernel seems to be up-to-date. No services need to be restarted."* The box was rebooted at some point after that issue was filed. No reboot was performed and none is outstanding.

- **`localStorage` ban lifted for theme preference only.** The human wants a light/dark toggle; it arrives at W2, which owns the shell and dark mode. Session state, learner content and progress all stay server-side. The original ban came from a rule about throwaway previews and was never a product decision.

- **Domain: `foundgrant.com`**, already owned, registrar Namecheap, nameservers moved to Cloudflare on 2026-08-23. `app.foundgrant.com` → Vercel, `api.foundgrant.com` → Hetzner behind the existing Caddy. The imported Namecheap email-forwarding MX records and the SPF TXT record **must not be deleted**. DNS records for the two subdomains are added at W2, not before.

---

## 3. Known issues

**Close these:**

- **#6 — production has no off-site backup.** Closed 2026-08-23. Closing evidence is the restore drill above, not the existence of an object in a bucket. Quote the four row counts in the closing note. This was the highest-ranked risk in the project and had been open since the Hetzner deploy on 2026-08-11.
- **#31 — freshness check silent while unset.** Closed 2026-08-23. An empty or unconfigured R2 now alerts; verified live in both directions.
- **#32 — pending kernel upgrade.** Closed 2026-08-23: already on 6.8.0-138, no action needed or taken.

**Add this new issue:**

- **R2 list-after-write consistency lag.** Severity **medium**, slice W1c. An object uploaded at 16:14 and successfully *downloaded* by the restore drill at 16:15 did not appear in `list-objects-v2` several minutes later — the freshness check reported `status='empty'` for a bucket that provably held it, and a subsequent listing showed the object had been there all along. The object was never lost and retention was never at fault; **an intermediate diagnosis that retention was deleting live objects was wrong** and is recorded here so it is not re-derived later. Consequence: the freshness check has no tolerance for listing lag and **can produce a false alarm if it runs shortly after an upload**. Harmless at the 04:00 UTC cron with hours of slack. Fix path: treat "empty" as inconclusive when the newest *local* dump is very recent, or re-list once after a short delay before alerting. Do not fix it in this slice.

**Note against the existing #70:** the recording `aws` stub does not reproduce real R2 listing output — it never exhibited the consistency lag and could not have. That is the concrete instance of #70 that this deployment surfaced; add it to the issue's text as evidence.

**Carry forward every other open issue**, including #64 (dotenv resolution), #65 (no operator alert channel for `apps/api`), #66 (duplicate job registration — now confirmed live and the reason the worker unit is uninstalled), #67 (no JS test runner), #71 (`BACKUP_R2_REQUIRED`), and the whole v2 set. #6, #31, #32, #49, #53 (TASKS half), #61, #63 and #68 are closed — do not reopen them.

---

## 4. Slice rows

- **W1c → 🟡 code-complete**, dated 2026-08-23, note: *"pg_dump → R2 verified live; restore drill passed (errors 27/27, chunks 29/29, users 3/3, sessions 43/44); freshness alarm proven both directions; api + worker units written but deliberately not installed."*

Leave W1c at 🟡. **The human marks it ✅** (`CLAUDE.md` §1). W1b is already ✅ and stays there.

---

## 5. `docs/DEPLOYMENT.md`

- Add the **Restoring from R2** section with the real row counts, the date, and the 2-second runtime.
- Add the AWS CLI v2 install commands.
- Add `ALTER ROLE bot CREATEDB` as a required setup step, with the reason.
- Note that the `english-api` and `english-worker` units are written but not installed, and that they arrive at W2.
- Confirm the deploy sequence reads **backup → pull → `pip install -e packages/core` → migrate → restart**, and that the bot's `ExecStart` is `python -m apps.bot.main`. Add a warning that a pre-W1 unit file will fail with `status=1/FAILURE` until `ExecStart` is corrected — that is exactly what happened on this deploy.

---

## 6. Next action

Rewrite it as:

**W1c's remaining human checks:** confirm a dump lands in R2 unattended after the 04:00 UTC cron (the first unattended run has not happened yet — every run so far was manual); confirm `/ping` and `/stats` answer in Telegram on the restructured bot.

**Carried forward, explicitly:**

- **W1b's PWA home-screen install** — deferred to W2. `next-pwa` disables service workers in dev and a service worker needs a secure context, so a LAN IP over plain http cannot register one. W2 already carries "installed to iPhone home screen" as an acceptance criterion.
- **The v2 deploy backlog, now partly cleared:** S26c code is deployed as of this slice, and migrations 007+008 were already applied. Still outstanding: the **S25 pre-flight counts** filled from production, and **#44** — evening reading confirmed running after `/interests`, which stays open until a real Mon/Wed/Fri delivery lands.
- **The entire v2 desk-check list**, unchanged. W1c is infrastructure; it exercises no learner path.
- **#57** — the §6b work-vocabulary SQL and the quiz-scenario frequency query, to be run on Hetzner before W5 rewrites the prompts.
- **S8** — the shared group, `/here`, `COUPLE_CHAT_ID`, then the seven group checks.

Then stop. Do not begin W2.
