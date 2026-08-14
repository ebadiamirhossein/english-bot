# TASKS — Vertical Slices

**Spec-driven development.** Each slice is independently shippable and manually verifiable in Telegram. Do **one slice per Cursor prompt**. Never start a slice before the previous one meets its acceptance criteria.

After every slice, Cursor must update `BUILD_PROGRESS.md`.

---

## Phase 1 — Foundation

### S0 · Repo skeleton
**Build:** directory structure per ARCHITECTURE §3, `requirements.txt`, `config.py` loading `.env` into a typed `Settings`, `db.py` with a psycopg3 connection pool + migration runner, `main.py` that starts the bot and responds to `/ping` with `pong`.
**Accept:** `python -m app.main` runs locally; `/ping` returns `pong` in Telegram; `python -m app.db migrate` applies `001_init_postgres.sql` to the Supabase database with the error taxonomy seeded.

### S1 · Onboarding
**Build:** `/start` conversation collecting name, native language, EF SET score → mapped to `cefr_level`, work domain, why-statement, track weights, morning/evening times. Writes `users` + `streaks` rows. Idempotent — running `/start` again offers to edit, not duplicate.
**Accept:** both users complete onboarding; rows correct in DB; second `/start` does not create a duplicate.

### S1a · Onboarding UX polish
**Build:** Early UX polish on the S1 flow (later superseded by S1b's interaction model; data layer unchanged).
**Accept:** onboarding remains completable; no duplicate user rows.

### S1b · Onboarding rebuild
**Build:** Replace multi-bubble onboarding with a single-message `edit_message_text` wizard; common path ~8 taps / 0 typing; why multi-select joined into one sentence; HTML + escape.
**Accept:** wizard stays one editable message; Save writes `users` + `streaks` once; second `/start` offers Change / Keep as is.

### S1c · Onboarding content
**Build:** EF SET "Not yet" → CEFR can-do self-assessment (A2/B1/B2); work domain category→specific drill-down; situation-based why options; EF SET nudge on save.
**Accept:** skipping EF SET stores a chosen A2/B1/B2 (not silent B1); domain and why are specific enough for later motivation/content.

### S1d · Onboarding personality
**Build:** Shared `layout_buttons` (≤12 chars to share a row); emoji on options; static reaction line after each choice; warmer copy. Celebration sticker skipped (no stable `file_id`).
**Accept:** long labels stay readable; reactions appear without adding extra bot messages beyond the wizard contract.

### S2 · LLM wrapper + free correction (M2)
**Build:** `llm.py` per ARCHITECTURE §4 with retry/backoff and `LLMError`. `prompts/correction.txt`. Handler: any non-command text → correction → reply in the fixed visual format from PRD §8 → write rows to `errors` with `next_review = tomorrow`.
**Accept:** send "her english is not so much good" → correct reply in the right shape → row exists in `errors` with `error_type='quantifier_modifier'`.

### S3 · Daily quiz + scheduler (M1)
**Build:** `services/errors.py` (`due_errors`, `mark_result`, spacing ladder 1→3→7→21→60). `prompts/quiz.txt`. `scheduler.py` with `send_daily_quiz` at each user's `morning_time`. Inline-button answers where the format allows. Writes `sessions`.
**Accept:** an error recorded today appears in tomorrow's quiz; answering correctly pushes `next_review` to +3 days; answering wrong resets to +1 day and increments `times_wrong`.
**Tests required:** unit tests for the spacing ladder.

### S3a · Quiz content + formats
**Build:** User-facing `error_types.label` (never codes); quiz sentences distributed by `track_weights`; four formats gap/choice/reorder/spot; past prompts from prior quiz session payload.
**Accept:** a quiz mixes tracks per weights; labels read as language, not `quantifier_modifier`.

### S3b · Quiz question layout
**Build:** Message body is for reading; buttons are only for tapping. Spot body shows the full sentence; feedback separated by a blank line (no divider wall).
**Accept:** spot/order questions are readable without relying on truncated button text alone.

### S3c · Quiz formats + spoken register
**Build:** Remove reorder tile grid; replace with `order` (4 full-sentence word-order choices). Spoken-register prompt rules; one shared everyday scenario per quiz.
**Accept:** order options are full sentences; quiz feels like one situation, not five unrelated worksheets.

### S3d · Quiz feedback + format mix
**Build:** Full-sentence feedback; hard mix 2 typed (gap) / 3 tapped per 5-question quiz; progress dots last.
**Accept:** feedback quotes a full sentence; production stays present without making daily completion brittle.

### S4 · Streaks, freeze, rescue mode
**Build:** `services/streaks.py` implementing PRD §7 rules 5–7 exactly. Monthly freeze reset job. Rescue mode shrinks the daily task to 3 questions for 7 days after 3 consecutive missed days.
**Accept:** simulate 1 missed day → freeze token consumed, streak intact. Simulate 3 missed days → `rescue_mode_until` set, next quiz has 3 questions, no backlog delivered.
**Tests required:** unit tests for freeze and rescue transitions.

**→ Ship Phase 1. Use it for 14 days. Do not start Phase 2 unless it was used on at least 8 of those days.**

### S4b · Database backups
**Build:** `scripts/backup.sh` — daily `pg_dump`, keep 14 local days. Off-site copy to independent storage is S4c (daily after each successful dump). The database is self-hosted on the Hetzner box with **no managed safety net**; this slice is the only protection for the error journal.
**Accept:** a scheduled dump restores cleanly into an empty Postgres 16 database.
**When:** immediately after Phase 1 ships — before Phase 2.

### S4c · Off-site backup + freshness alerting
**Build:** After each successful local dump, copy to `BACKUP_OFFSITE_DIR` (verified size + checksum; keep 14; refuse repo / inside `BACKUP_DIR`; never mkdir the destination). iCloud eviction placeholders (`.english_bot_*.dump.icloud`) count as present for retention and freshness. In-process daily/hourly freshness check: newest off-site dump older than 48h (or missing/empty) → throttled operator alert via `notify_operator`. Unset `BACKUP_OFFSITE_DIR` → INFO skip in `backup.sh` (`off-site copy skipped …`); no freshness alert.
**Accept:** configured off-site path receives a verified copy after a successful dump; a deliberately stale/empty directory produces one throttled operator alert; unset path never alerts.
**When:** immediately after S4b — before relying on a single machine.

---

## Phase 2 — Voice and books

### S5 · Voice partner (M3)
**Build:** `speech.py` (`transcribe`, `synthesize`; audio never touches disk). `prompts/voice.txt`. Voice message in → transcript → conversational voice reply + separate text correction block → errors written with `source='voice'`. Conversation state held for 5–10 turns.
**Accept:** send a voice message with 2 mistakes → receive a spoken reply that continues the conversation plus a text correction block → both errors in the journal.

### S5a · Voice processing status
**Build:** Repeating chat action while processing; editable 3-stage status message (listening → thinking → recording) instead of a fake progress bar.
**Accept:** user sees honest stage names during a voice turn; over-length voice is declined before download with no status flash.

### S6 · Book ingestion (M5)
**Build:** `/book` conversation → accepts a photo album → vision call via `llm.py` → `prompts/book_ocr.txt` extracts book, unit number, title, target items → writes `book_units`. `/test unit 12` pulls questions from a stored unit.
**Accept:** photograph 10 pages of Murphy → correct units appear in `book_units` with sensible `target_items`; `/test unit N` produces questions grounded in that unit.

### S7 · Anki export (M6)
**Build:** `services/anki.py` → weekly TSV of unexported chunks, posted as a Telegram document, marks rows exported.
**Accept:** file imports cleanly into Anki with fields in the right order.

### S7a · Chunk spaced review in the daily quiz
**Build:** Migration `004` adds review columns on `chunks` (`next_review` nullable = due, `times_right`/`times_wrong`/`streak_right`). Daily quiz selects due errors → due chunks (capped at `typed_gap_count`) → book top-up. Chunk questions are deterministic gaps via S7 `make_sentence_with_gap`; article-tolerant grading; shared `spacing_step` with errors (no duplicate ladder). Wrong chunk answers never write `errors`. `sessions.score` includes chunks; calibration uses `calib_*` (non-chunk only). Anki export unchanged and independent of review state. `/stats` shows due-chunk count.
**Accept:** 2 due errors + 3 due chunks → 2 errors + 2 chunks + 1 book; NULL `next_review` selected as due; correct advances ladder / wrong resets to 1 day; article slip still grades correct; all-chunk-wrong quiz does not drop the calibration window; exported chunk still comes up for review; `/stats` shows due count.

### S8 · Couple challenge (M8)
**Build:** group-chat handler. Daily question at 18:00, first correct answer scores. `couple_scores` per week. Sunday leaderboard message.
**Accept:** both answer in the group; first correct gets the point; leaderboard is right on Sunday.

---

## Phase 3 — Intelligence

### S9 · Interests profile
**Build:** Standalone `/interests` ConversationHandler (not an onboarding extension). Multi-select per track → seeds `interests`; Change/Keep on re-entry; preserves `weight`/`last_used` across replace.
**Accept:** ≥2 topics per track saved; custom topics survive a no-op Change→Done; unregistered users ignored.

### S9a · Reading delivery + chunks (M4 delivery)
**Build:** Mon/Wed/Fri evening poll at `evening_time`; LLM reading on a weighted interest topic; validates body/chunks; persists `readings` + 5 `chunks` + incomplete `reading` session; sends title+body only; respects 3-message ceiling; commit-after-send.
**Accept:** reading arrives on a reading evening; DB has 1 reading / 5 chunks / 1 session; questions stored unsent; ceiling skip writes nothing; reading session does not block next morning's quiz.

### S9b · Video engine (M16)
**Build:** YouTube Data API integration. 2×/week (Tue/Thu) selection on interest weights + track rotation + `cefr_level`. Filter to videos with human-written captions. Return one 3-minute segment with start timestamp, not a whole video. Track accent exposure per user and bias selection toward unfamiliar accents.
**Accept:** suggestions match stated interests and level; auto-caption-only videos are excluded; the same accent is never suggested three times running; the message names a specific segment, not just a link.

### S9c · Reading comprehension + rating (M4 Q&A)
**Build:** Deliver the five stored comprehension questions; grade answers; 1–5 topic rating that adjusts `interests.weight`; mark reading/session complete.
**Accept:** answering the questions completes the reading; a 1-star rating measurably lowers that topic's weight.

### S10 · Motivation engine (M7)
**Build:** nudge ladder per PRD §7 rules 1–4 and 9 (max 2 nudges, second offers a smaller task, 3-message daily ceiling, never guilt). Sunday report leading with resolved error types.
**Accept:** ignore a task → exactly 2 nudges, correctly worded and spaced; a third never arrives. Sunday report opens with progress.

### S11 · Weekly test + Murphy routing
**Build:** Sunday 15-question test drawing across all error types. Error-type frequency maps to recommended Murphy units via `error_types.murphy_units`, overriding the default week-by-week sequence.
**Accept:** test covers a spread of types; recommendation matches the actual top error types.

### S12 · Difficulty calibration (M14) + anti-fossilization (M13)
**Build:** rolling 30-question accuracy; >85% for 14 days raises `cefr_level`, <70% lowers it; logged to `calibration_log`. Monthly sweep silently re-tests resolved types and un-resolves failures.
**Accept:** simulated high accuracy triggers a level change with a log row; a failed resolved-type retest sets `resolved=0` and increments `unresolved_count`.

---

## Phase 4 — Depth

### S13 · Voice diary (M9)
60-second nightly recording. Max 2 corrections — volume over precision.

### S14 · Load-up mode (M10)
`/prep <topic>` → 10 chunks and 3 sentence frames for a real upcoming situation.

### S15 · Real-life capture (M11)
Forward any English → explanation + chunks mined, `source='capture'`.

### S15a · Watched-folder bridge (subtitle import + Anki drop)
**Build:** `WATCH_DIR` bidirectional folder — CSV imports from Trancy / Language Reactor into `chunks` (tolerant whole-word header map; row-level dedupe; mtime ≥ 2 min stability; collision-safe `processed/` / `failed/`); weekly Anki TSV also written to per-user `outbox/` (additive, failure-tolerant). Per-user `inbox/<telegram_user_id>/{trancy,language_reactor}/`; never attribute root-level files. `watch_poll` (5 min) + `/import`. Due-chunk tie-break `id DESC` within same `next_review` (errors stay oldest-first). No migration, no new dependency.
**Accept:** real Trancy + Language Reactor CSV import once each; `/import` shows paths; Anki TSV lands in outbox; bulk import does not starve later captures in the quiz.

### S15b · CSV import via Telegram document
**Build:** Accept a `.csv` document in a private chat; download to memory; run through the shared S15a pipeline (`import_csv_rows` / `map_headers`). Attribution = sender. Tool from header shape (else `subtitle_csv_*`). Non-CSV → warm line (IMAGE excluded so `/book` keeps pages); refuse >5 MiB before download. Unrecognisable headers → warm reply + `notify_operator` (no move). Independent of `WATCH_DIR`. No migration, no new dependency, no `bot_message_counts`.
**Accept:** send a Trancy or Language Reactor CSV to the bot → imported/duplicate/invalid + due count; second user uploads under their own `user_id`; re-send after folder import → zero new rows.

### S24 · Shared content library (slang CSV + operator book uploads)
**Build:** Fan-out shared library — one `chunks`/`book_units` row per approved user. Migration `006` `shared_content` + `shared_content_deliveries` (outcomes `delivered`|`skipped_owned`). Exact five-column slang header signature (mutually exclusive with Trancy/LR); opt-in Share confirmation (CallbackQuery only); Trancy/LR stay sender-only. Convergent backfill after onboarding Save (soft-fail) + both approve/re-approve handlers + reconcile at fan-out top. `SHARED_BOOK_SLUGS` config; operator-only fan-out; refresh title/items never `studied_at`. Recipients = `approved_onboarded_users` only (drift registry). No `correction.py`/`streaks.py`/`OpenQuizFilter`/`tenant_id` changes; never writes `errors`; no receiver Telegram / ceiling bump.
**Accept:** slang CSV Share fans out; re-import zero; per-user dedupe; revoked excluded; backfill at Save; Trancy/LR sender-only; operator shared books fan out; button labels ≤20.

### S24a · Trancy vocabulary CSV (generated sentences)
**Build:** Exact four-column Trancy vocabulary signature `{Word,Phonetic,Translation,Date}` as a fourth mutually exclusive CSV shape. Trancy-legacy requires a sentence-like column structurally. One batched LLM call (cap 40, sequential batches) generates English example sentences pitched at the sender’s CEFR/domain; Translation glosses sent for sense selection; exact-string response match; in-file + DB dedupe before LLM; word-in-sentence validation unchanged. Sender-only — no Share keyboard, no `shared_content`. Folder path refuses vocabulary (WARNING; no LLM in `watch_poll`). Generate off-loop via `asyncio.to_thread` with no write transaction held; then insert→send→commit. Prose operator alert for failed headers. No migration; never writes `errors`; no `bot_message_counts`.
**Accept:** real Trancy file imports with natural sentences containing each word; no Share prompt; only sender receives chunks; re-import zero new rows and zero LLM calls; unrecognised headers get a readable operator alert; folder refuse vocabulary without calling the LLM.

### S24b · Vocabulary sentence quality + skip visibility
**Build:** Prompt exact-form + register balance (≤~⅓ domain) + everyday sense over idiom. One capped retry for gate failures (exact form); retry LLM failure keeps first-pass rows. Named skips in Telegram reply (capped + “and N more”); log count/reason category only (PRD §10). No gate relaxation, no migration, no Share path changes.
**Accept:** skipped words named with reasons; clean import = one LLM call; previously-skipped forms like `frustrate` import when the model cooperates; sentences not all domain-flavoured (human check).

### S25 · First touch presents, it does not grade
**Build:** Migration `007` adds nullable `chunks.presented_at`. Backfill: `presented_at = created_at` where `source <> 'slang' OR source IS NULL` (slang stays NULL). User-sourced inserts set `presented_at = NOW()`; fan-out via `shared_content_deliveries` leaves NULL. `due_chunks` / `count_due_chunks` / `/stats` share one presented-and-due predicate. Morning quiz (not rescue/weekly/`/test`) rides up to 2 oldest-first presentation cards before graded questions; tap sets `presented_at` + `next_review` tomorrow without advancing the ladder. Presentations are not answers (no `errors`, score, calibration, or early_limit). Anki export ungated. Tap-only `present:` + orphan warm line; free text reaches M2.
**Accept:** unpresented chunks never graded; still export to Anki; cap 2 FIFO; no presentation-only quiz; rescue/weekly/`/test` have zero presentations; tap schedules tomorrow; untapped reappears; repeated/out-of-order ack no-ops; free text during presentation → correction; orphan → stale line; labels ≤20.

### S26 · Conversation mode (text)
**Build:** `/talk` text conversation (M3 sibling). Session-backed `OpenConversationFilter` (not a ConversationHandler free-text state); 30-min active / 2-min `awaiting_topic` staleness at filter time (fail-open). Implicit recasts mid-chat; ≤3 explicit corrections only at close-out (prefer recurring journal types); commit-after-send; migration `008` expands `errors.source` for `'conversation'`. Entrance refuses while a gap quiz awaits (every path). Plain-text turns; Sonnet + prompt caching; history cap 20; turn cap 12 with one-turn warning. No `bot_message_counts`; works while paused; voice/diary/shadow routing untouched; `streaks.py` / `correction.py` / `OpenQuizFilter` untouched.
**Accept:** open conversation captures private text; stale/none/group fall through to M2; mutual exclusivity with correction; commands mid-chat work; End / turn-cap close with ≤3 corrections; failed send / abandon / mid-turn LLM failure write zero `errors`; `/talk` refused on every entry path while gap quiz open; eligibility helpers unchanged with open conversation; labels ≤20.

### S16 · Shadowing (M12)
Bot sends a 10–15s clip → user repeats → Whisper compares word-for-word → scored feedback on rhythm and stress.

### S17 · Watch-together (M15)
Both mine the same episode; bot cross-quizzes each on the other's chunks.

### S18 · Hardening
`scripts/heartbeat.py` alerting if no job fired in 26h. Global exception handler messaging the operator. `/pause` and `/stats` commands. (Backups live in S4b/S4c.)

### S18a · `/settings` editor
Tapped-only editor for weights / times / explanation fallback; route-outs to `/interests` and `/pause`; `cefr_level` read-only.

### S18b · `/help` + Telegram command menu
**Build:** `setMyCommands` once in `post_init` (network failure → WARNING, boot continues). `/help` grouped by intent; omit `/import` when `WATCH_DIR` unset; `/ping` stays working but off the public menu. Point onboarding save confirmation at `/help` without adding a third bot message. No migration, no LLM, no `bot_message_counts`, no dispatch changes.
**Accept:** Telegram `/` menu lists the public commands; `/help` is scannable on a phone and names the two no-command behaviours (type English → journal; forward English → explain+mine); unregistered `/help` is ignored.

### S18c · `/guide` — how to use the bot, in the bot
**Build:** Tapped-only single-message wizard (`edit_message_text`, S1b/`/settings` pattern) with topic buttons derived from `docs/GUIDE-saving-phrases.md`. Sections: how this works, saving phrases, Trancy export, Language Reactor export, Anki first-time, Anki weekly, Anki on phone. Nested callback ConversationHandler `per_message=True` under `per_message=False` parent; no `MessageHandler`; stale-callback guard; strings in `texts.py` (not reading the markdown at runtime). `/help` points at `/guide`; register in `setMyCommands`. No migration, no LLM, no `bot_message_counts`.
**Accept:** `/guide` opens a menu; every section + Back works; every section under 4096 chars; Anki field mapping and back template are exact; unregistered ignored; command names in guide prose have handlers; button labels ≤20; no guilt.

### S18d · Access approval + operator admin panel
**Build:** Migration `005` — `access_requests` (+ `decline_count`) and view `approved_onboarded_users`; backfill existing `users` as approved. Unknown `/start` → request access (no `users` row); operator Approve/Decline via DM; pending dedupe; after two declines further requests update/log but no operator DM. Central gate at handler `group=-1` with `ApplicationHandlerStop` (allow `/start`, `/ping`, `access:`). Drop mid-onboarding `bot_data` allowlist. `is_registered` requires approved. All six delivery lists read the view only. Operator-only tapped `/admin` (activity never content): pause/resume/revoke (revoke ≠ delete). No `tenant_id`/`plan`, no `MessageHandler`, no `bot_message_counts`, no `/admin` in menu/`/help`/`/guide`. Do not modify `correction.py` or `streaks.py`.
**Accept:** Unknown cannot onboard until approved; second pending request does not re-ping operator; decline cap=2; existing users remain approved after migrate; `/admin` silent for non-operator; admin strings contain no journal/chunk/diary text; revoke blocks access and deletes nothing; re-approve restores; operator unset stores request and tells requester access is closed; gate surface regression (text/quiz/voice/document/settings) for approved users; delivery call-site drift test; button labels ≤20.

### S19 · Notion dashboard
Weekly read-only sync: level, streak, chunks, resolved types, EF SET history.

---

## Phase 5 — Commercial (month 6+, only after B2 is reached)

### S20 · Generalize
Remove every remaining assumption about Farsi/Lithuanian. Onboarding accepts any native language. Verify with a third test language end-to-end.

### S21 · Tenancy
Activate `tenant_id` and `plan`. Per-tenant config. Usage limits by plan.

### S22 · Payments
Telegram Stars integration. Requires a Lithuanian legal entity and VAT handling. Evaluate Paddle as merchant-of-record alternative.

### S23 · Landing + onboarding funnel
Design in Claude Design first. Do not write code before the wireframe exists.
