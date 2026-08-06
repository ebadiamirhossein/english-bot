# BUILD PROGRESS

> **Cursor: you must update this file at the end of every slice, before finishing your turn.**
> **Human: upload this file to a new Claude chat to restore full context.**

**Project:** English Learning System — Telegram bot, 2 users, B1 → B2 in 6 months
**Repo:** `english-bot`
**Last updated:** 2026-08-04
**Current slice:** S9a
**Status:** S9a code-complete — awaiting human Telegram verify

---

## How to resume in a new Claude chat

Upload this file plus `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/TASKS.md`. Say:
*"Continuing the English bot build. Read BUILD_PROGRESS.md. Give me the Cursor prompt for the next slice."*

---

## Slice status

| Slice | Name | Status | Date | Notes |
|---|---|---|---|---|
| S0 | Repo skeleton | ✅ done & verified | 2026-07-31 | Config, db migrate/status, `/ping` verified against local PG 16.14. |
| S1 | Onboarding | 🟡 code-complete | 2026-07-31 | ConversationHandler `/start`; users+streaks upsert; access control; pytest green on :5433. |
| S1a | Onboarding UX polish | 🟡 code-complete | 2026-08-01 | Superseded interaction model by S1b; data layer unchanged. |
| S1b | Onboarding rebuild | 🟡 code-complete | 2026-08-03 | Single-message `edit_message_text` wizard; 8 taps / 0 typing common path; why multi-select → sentence; HTML + escape. |
| S1c | Onboarding content | 🟡 code-complete | 2026-08-03 | Self-assessment A2/B1/B2; domain category→specific drill-down; situation-based why options; EF SET nudge on save. |
| S1d | Onboarding personality | 🟡 code-complete | 2026-08-03 | Layout helper (≤12 shared rows); emoji on options; static reactions; warmer copy. Sticker skipped (no stable file_id). |
| S2 | LLM wrapper + correction | 🟡 code-complete | 2026-08-03 | `llm.py` + free correction; pytest green; await Telegram verify. |
| S3 | Daily quiz + scheduler | 🟡 code-complete | 2026-08-03 | Spacing ladder + quiz + 5-min poll; await Telegram verify. |
| S3a | Quiz content + formats | 🟡 code-complete | 2026-08-03 | Labels not codes; track mix; gap/choice/reorder/spot. |
| S3b | Quiz question layout | 🟡 code-complete | 2026-08-03 | Body reads / buttons tap; feedback blank line. |
| S3c | Quiz formats + register | 🟡 code-complete | 2026-08-03 | Reorder→order; spoken register; one scenario. |
| S3d | Quiz feedback + format mix | 🟡 code-complete | 2026-08-03 | Full-sentence feedback; 2 typed/3 tapped; 63 pytest green. |
| S4 | Streaks, freeze, rescue | 🟡 code-complete | 2026-08-03 | 03:00 local rollover; freeze; rescue 3Q; 83 pytest green. |
| S4b | Database backups | 🟡 code-complete | 2026-08-04 | pg_dump/restore scripts; restore verified; off-site stub. |
| — | **PHASE 1 SHIPPED — 14-day usage gate** | ⬜ | | await S4 verify + 14-day use |
| S5 | Voice partner | 🟡 code-complete | 2026-08-04 | Whisper+TTS; voice sessions; Active>Missed; 98 pytest green. |
| S5a | Voice processing status | 🟡 code-complete | 2026-08-04 | Repeating chat action + 3-stage status message; await Telegram verify. |
| S6 | Book ingestion | ⬜ not started | | |
| S7 | Anki export | ⬜ not started | | |
| S8 | Couple challenge | ⬜ not started | | |
| S9 | Interests profile | 🟡 code-complete | 2026-08-04 | `/interests` wizard seeds `interests`; 112 pytest green; reading engine is S9a. |
| S9a | Reading delivery + chunks | 🟡 code-complete | 2026-08-04 | Mon/Wed/Fri evening poll; readings+chunks+session; ceiling; 134 pytest green. |
| S9b | Video engine (YouTube) | ⬜ not started | | |
| S9c | Reading comprehension + rating | ⬜ not started | | Questions delivery, grading, 1–5 rating → weight adjust. |
| S10 | Motivation engine | ⬜ not started | | |
| S11 | Weekly test + Murphy routing | ⬜ not started | | |
| S12 | Calibration + anti-fossilization | ⬜ not started | | |
| S13–S19 | Phase 4 depth | ⬜ not started | | |
| S20–S23 | Phase 5 commercial | ⬜ not started | | |

Status key: ⬜ not started · 🟡 in progress / code-complete · ✅ done & verified · ⚠️ done but has known issues

---

## Environment

| Item | Status | Value / note |
|---|---|---|
| Hetzner server | ⬜ | — |
| PostgreSQL 16 (local / dev) | ✅ | 16.14 on port 5433 (5432 taken by a Docker container from another project) |
| PostgreSQL 16 (Hetzner / prod) | ⬜ | pending; will use 5432 |
| DATABASE_URL (session pooler) | ⬜ | put in `.env` from `.env.example` |
| Telegram bot token | ✅ | in `.env` |
| Shared group created | ⬜ | — |
| LLM provider + key | 🟡 | `LLM_PROVIDER`/`LLM_MODEL`/`ANTHROPIC_API_KEY` in config; add real key to `.env` before Telegram verify |
| Whisper/TTS key | 🟡 | `OPENAI_API_KEY` + STT/TTS model env in config; optional at boot, required before first voice message |
| YouTube Data API key (S9b) | ⬜ | — |
| systemd unit | ⬜ | — |
| Weekly pg_dump to independent storage | 🟡 | Daily local dump ✅ (`~/english-bot-backups`); weekly off-site copy still a stub (known issue #6) |
| User A onboarded | ⬜ | EF SET: — |
| User B onboarded | ⬜ | EF SET: — |

---

## Decisions log

Record every decision that deviates from or resolves ambiguity in the spec. Newest first.

| Date | Decision | Reason |
|---|---|---|
| 2026-08-04 | Split TASKS S9 into **S9a** (delivery + chunks) and **S9c** (comprehension + rating) | Chunks unblock S7 Anki before Q&A UX lands; same vertical-slice pattern as S3→S3d. S9 itself stayed interests-only. |
| 2026-08-04 | S9a: commit readings/chunks/session only after Telegram send succeeds (txn held across send) | A send failure after persist would poison the chunk pool with text the user never read; Anki (S7) would export untraceable cards. Day stays unclaimed → next 5-min tick retries. |
| 2026-08-04 | S9a: chunk-in-body check normalises casefold / whitespace / apostrophes+quotes; store model text as-is | Strict `in` rejects valid capitalised / curly-apostrophe chunks; retry then silent-skip wasted the day. |
| 2026-08-04 | S9a: NULL `last_used` scores as 30 days; exact score ties → alphabetically first topic | Huge NULL constant drowned weight/track_weights; argmax over ties was DB-order-dependent. |
| 2026-08-04 | S9a: every skip path logs WARNING with user_id + reason (ceiling, no interests, LLM, validation) | Soft to the user, loud to the operator (ARCHITECTURE principle 4) — a quiet no-op is indistinguishable from a working engine. |
| 2026-08-04 | S9: `/interests` is a standalone ConversationHandler, not an onboarding extension | Partner not yet onboarded; the S1 wizard is verified and must not be re-opened. TASKS "onboarding extension" wording overridden for this reason. |
| 2026-08-04 | S9: callback_data carries option indexes (`int:tw:3`), never topic text; option lists live in `user_data` | Telegram 64-byte limit; free-text topics can contain `:` (S1b colon-split bug) or be arbitrarily long. |
| 2026-08-04 | S9: Change preload rebuilds option lists as presets + stored non-presets so customs stay toggleable | Without that, a no-op Change→Done silently deletes "Something else" topics because save writes `user_data` only. |
| 2026-08-04 | S5a: honest stage names (listening / thinking / recording) over a percentage or ▓▓▓░░░ progress bar | Stage durations are unpredictable (Whisper on 60s ≫ 10s); a bar that stalls at 80% reads as a crash. |
| 2026-08-04 | S5: day-state precedence Active > Missed > Neutral over **all** sessions for the local day (not latest row) | After voice no longer blocks quiz delivery, voice-then-ignored-quiz left an incomplete quiz as latest and burned a freeze on a day of real usage — inverts PRD §4 and can push engaged users into rescue. |
| 2026-08-04 | S5: freeze notice keeps remaining count when tokens > 0; omits inventory clause when zero | "One left" is informational; "None left this month" scores scarcity and violates PRD §7 rule 4. |
| 2026-08-04 | S5: voice sessions marked `completed=TRUE` as soon as an exchange succeeds | Abandoned mid-conversation must not leave an incomplete row that rollover could misread; live conversation is found by recency + turn count, not `completed`. |
| 2026-08-04 | S5: morning `has_session_on` scoped to `task_type IN ('quiz','free_practice')` | A 07:40 voice message must not silently cancel that day's quiz. |
| 2026-08-04 | S5: voice replies do not increment `bot_message_counts` | PRD §7 rule 9 caps bot-initiated messages; voice answers are replies to the user. |
| 2026-08-04 | S5: max 3 corrections per voice turn | Spoken turns generate more errors; a six-item wall ends the conversation. Untaken errors recur naturally. |
| 2026-08-04 | S5: conversation window 120 min since last turn, hard cap 10 exchanges | Past either, next voice starts a fresh session. |
| 2026-08-04 | S5: voice >120s declined before download; TTS failure falls back to text reply | M3 is conversation not monologue (S13); losing the turn is worse than losing audio. |
| 2026-08-04 | S4b: refuse `BACKUP_DIR` inside the git repo | Dumps contain the user's private writing (PRD §10); a path under the repo is one `git add` away from a leak. |
| 2026-08-04 | S4b: 10 KB sanity floor before counting a dump as success | A 0-byte / tiny file that silently replaces a good backup is worse than no backup; never prune on failure. |
| 2026-08-04 | S4b: restore defaults to `english_bot_restore_test`; live `english_bot` needs `--force` | An untested backup is not a backup — and a careless restore must not destroy production. |
| 2026-08-04 | S4b: off-site copy left as a documented stub (`offsite_copy_stub`) | TASKS requires independent storage; this slice must not add cloud credentials. Options: rsync / rclone / manual weekly copy. |
| 2026-08-03 | S4: 03:00 **local** rollover (15-min poll), never UTC midnight | PRD §7 rule 1 — Monday's quiz stays open until 03:00 Tuesday. UTC midnight would close Vilnius days mid-evening and break streaks for completions that were still on time. |
| 2026-08-03 | S4: no `roll_over_day` on quiz complete; show `current_streak+1` optimistically | Early evaluation advances `last_evaluated_date` and can close the next day before its quiz is delivered. Real evaluation is only the 03:00 job. |
| 2026-08-03 | S4: idempotency via `streaks.last_evaluated_date` | Freeze-covered misses do not move `last_active_date`; without a separate marker a second rollover would consume another freeze. |
| 2026-08-03 | S4: backfill capped at 30 days; ≤50 users per streak poll tick | A two-month absence must not run 60 sequential rollovers inside one tick or starve other users. |
| 2026-08-03 | S4: freeze-covered missed days still count toward rescue | A freeze protects the streak number; it does not mean the person engaged. Rescue exists to re-engage. |
| 2026-08-03 | S4: no-session days are Neutral | Do not break the streak for a day the bot never asked about (paused / not yet onboarded). |
| 2026-08-03 | S4: incomplete `free_practice` = Neutral; completed (via correction) = Active | Empty journal is success, not a miss — burning a freeze is backwards. But using M2 that day *is* activity; correction marks the open free_practice session completed so rollover needs no special branch. Only permitted change to `correction.py`. |
| 2026-08-03 | S4: monthly freeze reset is per-user local 1st via `freeze_reset_on` | Users in Tokyo and Vilnius reach the 1st at different UTC moments; a global sweep would reset some early and some late. Unused tokens do not carry over. |
| 2026-08-03 | S4: rescue window is fixed 7 days from entry; further misses do not extend it | "Runs its 7 days" — completing early does not clear it; extending on every extra miss would never end. |
| 2026-08-03 | S3d: hard 2 typed (gap) / 3 tapped per 5-question quiz | Production practice matters (4-option guess is 25% right by chance), but daily completion matters more — PRD §7 is built around not abandoning; an easier quiz done every day beats a harder one abandoned. |
| 2026-08-03 | S3c: one everyday scenario per quiz (shared people/places); avoid past scenarios from session payload | Five unrelated sentences felt like a worksheet; a thread makes the quiz feel like a conversation. |
| 2026-08-03 | S3c: spoken-register rule (≤12 words, text-message test, conversations about work not documents) | Live sentences read like reports ("the museum team…"); people don't talk that way. |
| 2026-08-03 | S3c: remove reorder tile format; replace with `order` (4 full-sentence word-order choices) | Failed twice in live testing — a 3-column button grid gives no visual signal that tiles form one sentence. Chat grids can't express a sentence; full options on their own rows can. |
| 2026-08-03 | S3b: spot sentences capped at 8 words in the generation prompt | Nine tiles = three button rows; too much to scan on a phone. |
| 2026-08-03 | S3b: message body is for reading; buttons are only for tapping | Live bug: spot/reorder existed only as a tile grid — the sentence was unreadable. |
| 2026-08-03 | S3a: past prompts read from prior quiz `sessions.payload` (last 3 per error_id) — no new column | Payload already stores every question; a column would duplicate data and need a migration for no gain. |
| 2026-08-03 | S3a: four formats (gap/choice/reorder/spot), not more multiple-choice | Reorder and spot keep tapping without collapsing to 25%-guess recognition; gap still forces production. |
| 2026-08-03 | S3a: quiz sentences distributed by `track_weights` (interleaved) | PRD §6 — all-work quizzes ignore the weight the user set at onboarding. |
| 2026-08-03 | S3a: user-facing copy uses `error_types.label`, never the code | Live bug: "quantifier_modifier is getting steadier" — database codes are not language. |
| 2026-08-03 | S3: morning eligibility uses the user's **local** date/time (minute precision); every eligibility fn takes explicit `now` | Server UTC midnight ≠ Vilnius local; without local today a user can get two quizzes around UTC midnight. Tests must not touch the wall clock. |
| 2026-08-03 | S3: `bot_message_counts(user_id, local_date, count)` table — not session-row counting | PRD §7 rule 9 caps **messages**. S10 nudges are not sessions; counting sessions would under-count. Increment on every bot-initiated send. |
| 2026-08-03 | S3: quiz-active state from incomplete `sessions` (`task_type='quiz'`) + `payload` JSONB — never `bot_data` | `bot_data` dies on restart; a typed answer would fall through to correction and poison the journal. |
| 2026-08-03 | S3: zero due errors → `task_type='free_practice'` session (not `'quiz'`); selection blocks on **any** session that local day | Fake quiz rows corrupt completion-rate / streak / 14-day gate. Distinct type claims the slot, stops the 5-min loop, counts toward the message ceiling. |
| 2026-08-03 | S3: one 5-minute JobQueue poll (APScheduler via PTB), not per-user jobs | Survives restarts, picks up new users, implements PRD §7 rule 1 (delivery times, not deadlines). |
| 2026-08-03 | S3: gap-fill default question format | Production beats recognition. |
| 2026-08-03 | S3: grading by normalised string match against `accept`, no second LLM call | Deterministic, free, and the accept-list is the contract. |
| 2026-08-03 | S2: `claude-sonnet-5` (~$3.40/mo at ~900 corrections) over Haiku (~$1.20) | Wrong `error_type` poisons the journal permanently; ARCHITECTURE principle 3 treats the journal as the product itself. Two euros/month is not worth weaker taxonomy accuracy. |
| 2026-08-03 | S2: keep schema row-level `resolved`/`streak_right`; compute type-level "resolved" by aggregation in S10/S11 | PRD §3 defines resolved per error *type*; schema stores it per error *row*. Spacing (S3) needs per-instance rows; reporting aggregates later. No schema change. |
| 2026-08-03 | S2: length gates — under 10 chars silent, over 1000 → TEXT_TOO_LONG | Short ack messages (`ok`, `thanks`) must not spend API money; essay-length input is outside M2's "ordinary usage" frame and is where cost runs away. |
| 2026-08-03 | S2: keep `cache_control`; confirmed working after prompt grew | First system prompt was ~611 tokens (under Sonnet’s ~1024 floor). Two extra worked examples pushed it over; live calls show call1 `cache_creation=1641` / call2 `cache_read=1641`. |
| 2026-08-03 | S2: `did_well` prefixed with blank line + 👍 | Without a marker it read as part of the last correction block. |
| 2026-08-03 | S2: additive `explanation_language_fallback` on `User`/`get_user()`; `save_onboarding` untouched | Correction prompt needs the flag; read-path layering belongs in `users.py`. Onboarding write path and its tests stay unchanged. |
| 2026-08-03 | S1d: shared `layout_buttons` (≤12 chars to share a row); emoji on options; static reaction line after each choice; celebration sticker skipped | Truncation made step 5 unreadable; reactions make the bot feel like a partner. No stable public sticker `file_id` without bundling a file or adding a dependency — message count stays **2**. Further onboarding polish → S18 backlog. |
| 2026-08-03 | S1c: EF SET "Not yet" → CEFR can-do self-assessment (A2/B1/B2), not silent B1; domain is category→specific drill-down (store specific, lowercased); why options describe real situations (meetings, friends here, freezing up) | Silent B1 mis-pitches all content until S12. Broad domains ("Marketing") starve S9/S14. Generic why clauses motivate nobody when S10 quotes them back. Immigrants in Vilnius need local/work stakes in the list. |
| 2026-08-03 | S1b: replace S1/S1a multi-bubble onboarding with a single-message `edit_message_text` wizard | Message accumulation made onboarding read as a transcript wall; echoing answers (S1a) made it taller. Forced free-text for why produced weak data (`social talking`) that S10 must quote — presets yield better sentences. PRD §8 already required buttons over typing. |
| 2026-08-03 | S1b: ParseMode.HTML + `html.escape` on user-supplied values; ignore BadRequest "message is not modified"; time callbacks via `split(":", 2)` | Markdown breaks on `_` / `&` mid-flow; double-taps crash edits; naive colon split truncates `07:00` to `07`. |
| 2026-08-03 | S1b: native language presets add Russian + Polish; why is multi-select joined into one natural sentence | Matches local language mix; S10 quotes why verbatim so grammar must be correct. |
| 2026-08-01 | S1a: keep `work_domain` as free text with examples in the question, not preset buttons | Superseded for the common path by S1b presets + "Something else" escape hatch; specificity still available via free text. |
| 2026-08-01 | S1a: fix `PTBUserWarning` by nesting callback-only ConversationHandlers with `per_message=True` under a parent with `per_message=False` (MessageHandlers only + nested CHs) | Mixed MessageHandler + CallbackQueryHandler in one CH always warns; nesting matches how each update type is tracked. Do not `filterwarnings`. Kept in S1b. |
| 2026-07-31 | S1 open decision 5: do not ask timezone in onboarding; keep schema default `Europe/Vilnius` | Both users are in Vilnius; S20 (Generalize) must add timezone selection when assumptions are removed |
| 2026-07-31 | S1 open decision 4: second `/start` shows profile summary with Redo onboarding / Keep as is; redo overwrites `users`, never resets `streaks` | Full per-field edit is `/settings` (S18); streak history must survive redo. S1b renames buttons to Change something / Keep as is. |
| 2026-07-31 | S1 open decision 3: track weights via three preset buttons only (Balanced 40/40/20, More work 60/25/15, More everyday 25/60/15) | PRD §8 buttons over typing; fine-grained weights come from S9 ratings |
| 2026-07-31 | S1 open decision 2: EF SET step offers "Not yet"; `efset_baseline` stays NULL, `cefr_level` defaults to B1 | Test takes 50 minutes; PRD baseline is week 1, not day 1 |
| 2026-07-31 | S1 open decision 1: EF SET → CEFR uses official EF bands; PRD §3 target corrected to B2 (51–60) | PRD's "B2 (57–70)" spanned B2+C1; official B2 is 51–60 |
| 2026-07-31 | Added `app/services/users.py` to ARCHITECTURE §3 | User reads/writes needed by S2+; DB access must not live in handlers |
| 2026-07-31 | Onboarding writes nothing until Save; answers held in `context.user_data` | Abandonment leaves no partial rows; duplicate prevention stays trivial |
| 2026-07-31 | Mid-onboarding telegram ids tracked in `bot_data` for access control | Rows exist only after Save; without this, every answer would look unregistered |
| 2026-07-31 | **REVERSAL:** self-hosted PostgreSQL 16 on the Hetzner box, not Supabase | Supabase Pro is $25/mo (~€276/yr), not the €10/mo assumed in the original entry. Managed backups duplicate the `pg_dump` backup already planned (now S4b). Self-hosted costs nothing extra; application code unchanged. |
| 2026-07-31 | Migration runner uses `psycopg.ClientCursor` for applying `.sql` files | psycopg3's default server-side cursor rejects multi-statement scripts; ClientCursor uses the simple query protocol |
| 2026-07-31 | Replaced undotted `cursorrules` with `.cursorrules` | ARCHITECTURE §3 and S0 require the dotted filename Cursor reads; content rewritten to match S0's required clauses |
| 2026-07-31 | ARCHITECTURE §7 "Database file chmod 600" → credentials in `.env` mode 600 | No local DB file under Postgres/Supabase; keep the security intent |
| 2026-07-31 | ARCHITECTURE §1 "SQLite" → PostgreSQL; §5 backup job → `pg_dump` | Doc fix required by S0; matches §2 and earlier decisions log |
| 2026-07-31 | ARCHITECTURE §3 gains `specs/` | Prevent later slices treating specs as out-of-tree |
| 2026-07-31 | Local verify venv used Python 3.13 (3.12 not installed on this machine) | Runtime target remains 3.12 per ARCHITECTURE; deps install cleanly on 3.13 |
| 2026-07-31 | ~~PostgreSQL on Supabase (+€10/mo), not SQLite, not self-hosted PG~~ — **SUPERSEDED** by self-hosted PG 16 reversal above | Choosing PG now permanently removes the SQLite→PG migration risk. Supabase→self-hosted stays reversible via pg_dump. Managed backups + PITR + table editor worth €120/yr for an irreplaceable database. (Price assumption was wrong: Pro is $25/mo.) |
| 2026-07-31 | Session-mode pooler, psycopg3, no supabase-py | Direct connections are IPv6-only; transaction pooling breaks prepared statements |
| 2026-07-31 | Own weekly pg_dump in addition to Supabase backups (S18) | Never rely on a single backup system |
| 2026-07-31 | Added M16 video engine — YouTube Tue/Thu alongside sitcoms Mon/Wed/Fri | Sitcoms give only casual American English; user needs domain register and accent variety for work in Vilnius |
| 2026-07-31 | Agent runtimes (Hermes/OpenClaw) rejected as runtime; Cursor used to build | Product is a deterministic pipeline, not an open-ended task. Reliability, testability, cost, and prompt-injection surface from untrusted input |
| 2026-07-31 | HIMYM primary (Disney+/Trancy), The Office secondary (Netflix/Language Reactor) | Motivation outweighs marginal pedagogical edge |
| 2026-07-31 | Multi-tenancy architected but not built | Product unproven until users reach B2 |
| 2026-07-31 | No Telegram Premium | Irrelevant to bot capabilities |

---

## Known issues

| # | Issue | Severity | Slice | Status |
|---|---|---|---|---|
| 1 | S0 not yet executed | — | S0 | ✅ closed — verified 2026-07-31 |
| 2 | `.cursorrules` needs human review against the required clauses in `specs/S0-repo-skeleton.md` | low | S0 | ⬜ open |
| 3 | Timezone not collected in S1; all users get schema default `Europe/Vilnius`. S20 (Generalize) must add timezone selection when location assumptions are removed. | medium | S1 → S20 | ⬜ open — assumption recorded |
| 4 | System prompt was under Anthropic Sonnet cache minimum (~1024). Fixed by adding two worked examples; live verify: call2 `cache_read=1641`. | low | S2 | ✅ closed — 2026-08-03 |
| 5 | Chat-message UI has reached its design ceiling; a Telegram Mini App is the real answer for quiz UX — revisit after the 14-day usage gate, sharing design work with S23. | medium | S3d → post-gate / S23 | ⬜ open |
| 6 | S4b off-site weekly copy is a stub (`offsite_copy_stub` in `scripts/backup.sh`). Local 14-day dumps exist; independent storage (rsync / rclone / manual) is not automated yet. Wire before relying on the Hetzner box alone. | high | S4b | ⬜ open |

---

## File inventory

Cursor: keep this current so a fresh chat knows what exists without reading the repo.

| Path | Purpose | Status |
|---|---|---|
| `.cursorrules` | Project constitution for every slice | ✅ |
| `.env.example` | Dummy env keys + session-pooler comment + LLM + Whisper/TTS keys | ✅ |
| `.gitignore` | Ignores `.env`, venv, pycache, pytest | ✅ |
| `requirements.txt` | ptb[job-queue], psycopg, dotenv, pytest, anthropic, openai | ✅ |
| `BUILD_PROGRESS.md` | Slice progress / resume context | ✅ |
| `docs/PRD.md` | Product requirements (B2 band 51–60) | ✅ |
| `docs/ARCHITECTURE.md` | Stack, structure, interfaces (+ `services/users.py`) | ✅ |
| `docs/TASKS.md` | Vertical slice list | ✅ |
| `specs/S0-repo-skeleton.md` | S0 spec | ✅ |
| `specs/S1-onboarding.md` | S1 spec | ✅ |
| `specs/S1a-onboarding-ux.md` | S1a onboarding UX polish spec | ✅ |
| `specs/S1b-onboarding-rebuild.md` | S1b single-message wizard spec | ✅ |
| `specs/S1c-onboarding-content.md` | S1c level / domain / motivation content | ✅ |
| `specs/S1d-onboarding-personality.md` | S1d layout / emoji / reactions | ✅ |
| `specs/S2-llm-correction.md` | S2 LLM wrapper + free correction | ✅ |
| `specs/S3-daily-quiz.md` | S3 daily quiz + scheduler | ✅ |
| `specs/S3a-quiz-content.md` | S3a quiz content + four formats | ✅ |
| `specs/S3b-quiz-layout.md` | S3b readable layout + feedback | ✅ |
| `specs/S3c-quiz-formats.md` | S3c order format + spoken register | ✅ |
| `specs/S3d-quiz-feedback.md` | S3d feedback + typed/tapped mix | ✅ |
| `specs/S4-streaks.md` | S4 streaks / freeze / rescue | ✅ |
| `specs/S4b-backups.md` | S4b pg_dump / restore | ✅ |
| `specs/S5-voice-partner.md` | S5 voice partner (M3) | ✅ |
| `migrations/001_init_postgres.sql` | Initial schema + 19 error_types | ✅ |
| `migrations/002_quiz_scheduler.sql` | sessions.payload + bot_message_counts | ✅ |
| `migrations/003_streaks.sql` | last_evaluated_date, freeze_reset_on, pending_freeze_notice | ✅ |
| `app/__init__.py` | Package marker | ✅ |
| `app/config.py` | Env → frozen `Settings`, `ConfigError` (+ LLM + STT/TTS keys) | ✅ |
| `app/db.py` | Pool + migrate/status CLI | ✅ |
| `app/llm.py` | Anthropic chat wrapper; only LLM provider SDK import | ✅ |
| `app/speech.py` | OpenAI STT/TTS wrapper; only speech provider SDK import | ✅ |
| `app/scheduler.py` | Morning + evening reading poll + streak rollover + monthly freeze reset | ✅ |
| `app/texts.py` | User-facing strings + S1d–S9a quiz/streak/freeze/voice/status/interests/reading | ✅ |
| `app/main.py` | Bot entrypoint; `/ping`, `/start`, correction, quiz, voice, `/interests`, reading prompt init, scheduler | ✅ |
| `app/handlers/__init__.py` | Handlers package | ✅ |
| `app/handlers/access.py` | Shared unregistered-user ignore + onboarding allowlist | ✅ |
| `app/handlers/onboarding.py` | `/start` wizard + `layout_buttons` + reactions (S1d) | ✅ |
| `app/handlers/correction.py` | Free-text correction (S2) + shared `render_correction_message` | ✅ |
| `app/handlers/quiz.py` | Daily quiz delivery + grading UI (S3–S4 rescue/streak) | ✅ |
| `app/handlers/voice.py` | Voice partner handler (S5) + status stages / repeating chat action (S5a) | ✅ |
| `app/handlers/interests.py` | `/interests` multi-select wizard (S9); index callbacks; custom-topic preload | ✅ |
| `app/handlers/reading.py` | Evening reading delivery (S9a); title+body only; commit-after-send | ✅ |
| `app/services/__init__.py` | Services package | ✅ |
| `app/services/users.py` | get/save user, EF SET → CEFR (+ explanation_language_fallback read) | ✅ |
| `app/services/errors.py` | record_errors + due_errors + mark_result spacing (S3) | ✅ |
| `app/services/sessions.py` | sessions + bot_message_counts + voice + has_reading_session_on (S3/S5/S9a) | ✅ |
| `app/services/streaks.py` | Streak rollover, freeze, rescue; Active>Missed precedence (S4/S5) | ✅ |
| `app/services/interests.py` | list/replace/select_topic/mark_last_used (S9/S9a) | ✅ |
| `app/services/chunks.py` | Chunk inserts for reading (S9a) | ✅ |
| `app/services/reading.py` | Validate + persist_and_send under open txn (S9a) | ✅ |
| `app/prompts/correction.txt` | Correction system prompt template | ✅ |
| `app/prompts/quiz.txt` | Quiz generation (tracks, 4 formats, freshness) | ✅ |
| `app/prompts/voice.txt` | Voice conversation + correction JSON prompt | ✅ |
| `app/prompts/reading.txt` | Reading passage + questions + chunks JSON prompt (S9a) | ✅ |
| `tests/conftest.py` | Dummy `ANTHROPIC_API_KEY` for test settings load | ✅ |
| `tests/test_onboarding.py` | S1 persistence + CEFR mapping tests | ✅ |
| `tests/test_onboarding_validation.py` | S1b validation re-ask via wizard edit | ✅ |
| `tests/test_why_sentence.py` | Why multi-select → sentence grammar (S1c clauses) | ✅ |
| `tests/test_s1c_content.py` | Self-assessment CEFR map + domain drill-down table | ✅ |
| `tests/test_s1d_personality.py` | Layout helper + full reaction coverage | ✅ |
| `tests/test_llm.py` | LLM retry / json_mode / images (mocked provider) | ✅ |
| `tests/test_correction.py` | record_errors + handler + prompt fallback assertions | ✅ |
| `tests/test_spacing.py` | Spacing ladder (ARCHITECTURE §8) | ✅ |
| `tests/test_quiz.py` | Grading, mark_result once, abandon, free_practice | ✅ |
| `tests/test_scheduler.py` | Local-time eligibility + 24h dual-TZ poll | ✅ |
| `tests/test_quiz_s3a.py` | Tracks, reorder/spot, labels, past prompts | ✅ |
| `tests/test_quiz_s3b.py` | Readable body, blank-line sep, no-guilt copy | ✅ |
| `tests/test_quiz_s3c.py` | No reorder; order rows; scenarios; no divider | ✅ |
| `tests/test_quiz_s3d.py` | Full-sentence feedback; 2/3 mix; dots last | ✅ |
| `tests/test_streaks.py` | Freeze / rescue / Active>Missed / monthly reset (S4/S5) | ✅ |
| `tests/test_rescue_quiz.py` | Rescue 3Q vs 5Q; no backlog | ✅ |
| `tests/test_speech.py` | STT/TTS in-memory + retry (mocked OpenAI) | ✅ |
| `tests/test_voice.py` | Voice session gate, conversation, errors, TTS fallback + S5a status | ✅ |
| `tests/test_interests.py` | S9 save/replace/preserve/custom-survive/min-2/free-text/layout | ✅ |
| `tests/test_reading.py` | S9a eligibility, ceiling, topic pick, validate, rollback, persist | ✅ |
| `specs/S5a-voice-status.md` | S5a voice processing status | ✅ |
| `scripts/backup.sh` | Daily pg_dump (−Fc), 14-day retain, off-site stub | ✅ |
| `scripts/restore.sh` | Restore into scratch DB; `--force` for live | ✅ |

---

## Next action

**Human:** verify S9a in Telegram (user must already be onboarded with `/interests` seeded):

1. On a Mon/Wed/Fri after `evening_time`, with message ceiling free: receive one message = title + body (~300–400 words on an interest topic). No questions yet.
2. DB: 1 `readings` row (`completed=FALSE`, questions JSONB present), 5 `chunks` (`source=reading_<id>`, `exported_to_anki=FALSE`), 1 `sessions` row (`task_type=reading`, `payload.reading_id`, `completed=FALSE`); chosen interest `last_used` = local today; `bot_message_counts` +1.
3. Second poll same evening: no second reading.
4. With ceiling already at 3: no reading, no new rows.
5. Next morning: quiz still delivers (reading session does not block).

Mark S9a ✅ only after that. Next slice after verify: S9c (comprehension + rating) or S7 (Anki — chunks now exist).
