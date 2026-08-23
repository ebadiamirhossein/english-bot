# Claude Code — W0 · Audit and migration plan

**Run in: PLAN MODE. Do not write, move, or delete a single file in this slice.**
**Working directory: the `english-bot` repo.**

---

You are picking up an existing, working project and planning its migration from a Telegram bot to a web app. Read `CLAUDE.md`, then `docs/PRD-v3-web.md`, `docs/ARCHITECTURE-v3-web.md` and `docs/TASKS-v3-web.md` — they are the target state. Then read `BUILD_PROGRESS.md` for what actually happened during the v2 build, including the known-issues table. The v2 docs (`docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`) are superseded historical record: read for context, never build from them.

The decision has already been made and is not open for re-litigation: **the Python services layer, the database, and the prompts are kept; the Telegram handlers are deleted; a FastAPI layer and a Next.js PWA are added.** Your job is to plan the move precisely, not to propose an alternative architecture.

## What to produce

A single plan document. No code. Sections:

### 1. Module inventory

Walk every file under `app/`. For each, one row:

| Path | Lines | Verdict | Reason |
|---|---|---|---|

Verdict is exactly one of:

- **MOVE** — goes to `packages/core` unchanged
- **MOVE+STRIP** — goes to `packages/core` after removing Telegram/PTB coupling (say exactly which imports, parameters or return shapes are coupled)
- **REWRITE** — the logic survives but the interface must change for HTTP (say what the new signature is)
- **DELETE** — Telegram-only, dies with the bot
- **KEEP-IN-BOT** — stays in `apps/bot` for notifications and the couple challenge

Be specific about the coupling. "Uses `Update`" is not enough — name the function and what it needs instead.

### 2. Hidden knowledge inventory

This is the most important section. The v2 codebase encodes fixes that are invisible in the code and unrecoverable from the spec. Find them and list them so the migration cannot silently drop them. Start from these known ones and search for more:

- the spacing-ladder edge cases in `services/errors.py`
- freeze-token consumption order in `services/streaks.py`
- the calibration approximation and why per-question outcomes were never logged (known issue #20)
- the `llm.py` prefill regression fix (known issue #10) and the tolerant JSON parse
- the `.env` loading fix in `backup.sh` (known issue #26)
- the `asyncio.to_thread` requirement around LLM calls (known issue #7)

For each: what it protects against, where it lives, and which new test must cover it after the move.

### 3. Test inventory

The suite is currently 714 tests. For each test file: does it survive the move as-is, does it need rewiring to the new import paths, or does it die with the handlers? Give the expected post-move count. Flag any test that would pass in the new structure while testing nothing — the v2 lesson was that green tests over an unreachable path prove nothing.

### 4. Schema audit

Read `migrations/001`–`008` and the live schema. For each of the 15 existing tables: untouched, extended, or superseded. Then list what migrations 009–014 need to add per ARCHITECTURE §5, and flag any collision with existing column names or constraints.

Pay particular attention to the `chunks` → `cards` migration: propose the exact mapping, including how a chunk's v2 review history (`times_right`, `times_wrong`, `streak_right`, `next_review`) seeds an initial FSRS stability and difficulty. A learner must open the new deck on day one and find it already populated.

### 5. Monorepo layout

The concrete file-move plan: source path → destination path, for every file. Plus the import-rewrite strategy and the boundary rule to enforce (`packages/core` may not import FastAPI, Telegram, or anything HTTP).

### 6. Risks

Ranked. For each: what breaks, how you'd detect it, and what the cheapest guard is. Include at minimum: journal data loss, silent loss of a v2 behaviour fix, the two-process scheduler collision, and CORS/auth on first deploy.

### 6b. Content audit — how much of v2 sounded like work

Sample the generated content that survives in the database: quiz sentences in `sessions.payload`, `chunks` carrier sentences, reading passages. Count what fraction contains work/business vocabulary (client, campaign, deploy, meeting, deadline, Q3, stakeholder, budget, launch, report). Report the number.

This is not a side note. The learner's strongest complaint about v2 is that everything sounded like work, and PRD §4.6 changes the default weights to Life 50 / Curiosity 30 / Work 20 because of it. Say plainly where in the code the work bias was introduced — prompt templates, `work_domain` injection, track weights, or all three — so W5 can remove it at the source rather than filtering it downstream.

### 7. Open questions for the human

Anything you cannot resolve from the repo or the docs. Keep this short and specific — do not pad it with questions the docs already answer.

## Constraints

- **Read-only.** No file is created, edited, moved or deleted in this slice.
- Do not propose a TypeScript rewrite of the services layer. That fork was considered and closed; the reasoning is in ARCHITECTURE §1.
- Do not propose an ORM, Alembic, Redis, Celery, Docker, or a queue.
- Do not redesign the error taxonomy, the spacing ladder, or the streak rules.
- If you find something in the repo that contradicts the v3 docs, say so plainly rather than quietly picking one.

## BUILD_PROGRESS.md update block

At the end of the plan (still without editing the file — output the text to be pasted), produce the exact block to add to `BUILD_PROGRESS.md`:

- **Slice row:** `| W0 | Audit + migration plan | 🟡 plan produced | <today> | Plan output only, no code |`
- **Decisions log:** every decision made during the audit, each with its reason.
- **Known issues:** any new issue found during the audit, with severity and slice. Carry forward every still-open v2 issue that survives the migration — in particular #6 (no off-site backup), #20 (calibration approximation), #27 (CSV column mapping unverified), #28 (couple challenge produces no learning signal), #29 (couple challenge unverified), #32 (pending kernel upgrade).
- **File inventory:** no new files this slice.
- **Next action:** the human checks for W0, plus every earlier unrun check still outstanding from the v2 build.

Then stop. Do not begin W1.
