# Claude Code — docs only: shared-server context

**Run in: AGENT MODE. Documentation only. No code, no tests, no deploy.**

Three record updates so this context survives into future chats instead of being re-explained.
Nothing here changes behaviour.

---

## 1. `BUILD_PROGRESS.md` § Environment — add these rows

The production host is **shared with a separate production service that is not this project's**.
That fact currently lives only in a chat, and every future slice needs it before it writes a
server step.

| Item | Status | Value / note |
|---|---|---|
| SSH access | ✅ | `root@78.46.240.136`. The `bot` service account has **no inbound SSH key and no password** — reach it with `sudo -u bot -i` from root. |
| Privilege split | ✅ | `systemctl`, Caddy and anything under `/etc` need **root**. `scripts/backup.sh`, `scripts/restore_from_r2.sh`, `git pull`, `pip`, `core.db` and anything reading `.env` run as **`bot`**. A step that mixes the two must say where to `exit` back to root. |
| Shared host — hard constraints | ⚠️ | `fonderis-worker` (Node, port 3011) is a **separate production service on the same box**, and Caddy already owns 80/443 for it. PostgreSQL 16 on 5432 serves **both** projects. Therefore: never `apt upgrade` broadly, never reboot, never restart a system-wide service — each of those restarts `fonderis-worker` as a side effect. Never bind anything to 80, 443 or 3011; the API binds `127.0.0.1:8000` only, behind Caddy. Caddy changes are **additive site blocks named explicitly**, never a config rewrite, and always `reload`, never `restart`. Never run a destructive PostgreSQL command without naming the exact database — `english_bot` is this project's; other databases on that instance are not. |
| Server access for tooling | ⚠️ | **Claude Code has no SSH access to this server and is not to be given any.** Every server step is written as an explicit command for the human to run. A server step is never an acceptance criterion Claude Code can satisfy itself. |
| Vercel project | ✅ | Team `Zyndix` (Pro), project `english-bot`, root directory `apps/web`, deploys from `main`. Production URL `english-bot-omega.vercel.app` until `app.foundgrant.com` is attached. `NEXT_PUBLIC_API_URL` is the only environment variable this project needs — **the 47 keys Vercel offered to import from `.env.example` were declined deliberately**; a frontend project has no business holding `TELEGRAM_BOT_TOKEN`, `R2_SECRET_ACCESS_KEY` or `AUTH_RATE_LIMIT_SALT`, even as placeholders. |

---

## 2. `CLAUDE.md` §5 — add a shared-server line beside the deployment sequence

Directly after *"Deployment sequence, settled, not to be re-argued: backup → pull →
`pip install -e packages/core` → migrate → restart"*, add:

> **The production host is shared and is not ours alone.** A separate production Node service
> (`fonderis-worker`, port 3011) runs on it, Caddy owns 80/443 for that service, and PostgreSQL
> serves both projects. No slice may `apt upgrade` broadly, reboot, restart a system-wide
> service, bind to 80/443/3011, rewrite the Caddy config, or run a destructive PostgreSQL
> command without naming the exact database. Caddy changes are additive site blocks, applied
> with `reload` and never `restart`. **Every server step is written as an explicit command for
> the human to run** — Claude Code has no SSH access to this host and is not to be given any,
> so a server action is never an acceptance criterion a slice can satisfy on its own.

---

## 3. `prompts/` — resolve a contradiction the W2 commit introduced

`prompts/CC-W2-auth-and-shell-PLAN.md` was committed in `eecd38d`. `CLAUDE.md`'s preamble says
`BUILD_PROGRESS.md` is the only progress record and that per-slice spec markdown files do not
live in the repo. As written, the repo and the constitution now disagree.

The ban exists so that no second document competes with `BUILD_PROGRESS.md` as the record of
what is done. **An archive of the prompts that were sent to Claude Code is a different artifact**
— it records what was *asked for*, not what state the build is in — and keeping it is useful:
the reasoning behind a slice is otherwise only in a chat. So amend `CLAUDE.md`'s preamble to
distinguish the two:

> **Progress record:** `BUILD_PROGRESS.md` — the only one. Do not create per-slice spec markdown
> files in the repo: nothing may compete with it as the record of what is built and what is
> verified. `prompts/` is the exception and is not a competing record — it archives the prompt
> each slice was given, which documents intent rather than state. It is written to only when a
> slice's prompt is first committed, and is never consulted for build status.

Record the decision and its reason in the decisions log.

**If the human would rather not keep the archive**, delete `prompts/` and add it to
`.gitignore` instead, and leave the preamble alone. Do not do both.

---

## Then stop

No test run is needed — nothing executable changed — but run `pytest -q` once anyway to confirm
the doc edits broke no assertion (`tests/test_backup_r2.py` asserts against `docs/DEPLOYMENT.md`,
so doc-only edits have broken this suite before). Report and stop. **Do not deploy.**
