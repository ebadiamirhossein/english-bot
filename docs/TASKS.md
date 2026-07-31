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

### S2 · LLM wrapper + free correction (M2)
**Build:** `llm.py` per ARCHITECTURE §4 with retry/backoff and `LLMError`. `prompts/correction.txt`. Handler: any non-command text → correction → reply in the fixed visual format from PRD §8 → write rows to `errors` with `next_review = tomorrow`.
**Accept:** send "her english is not so much good" → correct reply in the right shape → row exists in `errors` with `error_type='quantifier_modifier'`.

### S3 · Daily quiz + scheduler (M1)
**Build:** `services/errors.py` (`due_errors`, `mark_result`, spacing ladder 1→3→7→21→60). `prompts/quiz.txt`. `scheduler.py` with `send_daily_quiz` at each user's `morning_time`. Inline-button answers where the format allows. Writes `sessions`.
**Accept:** an error recorded today appears in tomorrow's quiz; answering correctly pushes `next_review` to +3 days; answering wrong resets to +1 day and increments `times_wrong`.
**Tests required:** unit tests for the spacing ladder.

### S4 · Streaks, freeze, rescue mode
**Build:** `services/streaks.py` implementing PRD §7 rules 5–7 exactly. Monthly freeze reset job. Rescue mode shrinks the daily task to 3 questions for 7 days after 3 consecutive missed days.
**Accept:** simulate 1 missed day → freeze token consumed, streak intact. Simulate 3 missed days → `rescue_mode_until` set, next quiz has 3 questions, no backlog delivered.
**Tests required:** unit tests for freeze and rescue transitions.

**→ Ship Phase 1. Use it for 14 days. Do not start Phase 2 unless it was used on at least 8 of those days.**

---

## Phase 2 — Voice and books

### S5 · Voice partner (M3)
**Build:** `speech.py` (`transcribe`, `synthesize`; audio never touches disk). `prompts/voice.txt`. Voice message in → transcript → conversational voice reply + separate text correction block → errors written with `source='voice'`. Conversation state held for 5–10 turns.
**Accept:** send a voice message with 2 mistakes → receive a spoken reply that continues the conversation plus a text correction block → both errors in the journal.

### S6 · Book ingestion (M5)
**Build:** `/book` conversation → accepts a photo album → vision call via `llm.py` → `prompts/book_ocr.txt` extracts book, unit number, title, target items → writes `book_units`. `/test unit 12` pulls questions from a stored unit.
**Accept:** photograph 10 pages of Murphy → correct units appear in `book_units` with sensible `target_items`; `/test unit N` produces questions grounded in that unit.

### S7 · Anki export (M6)
**Build:** `services/anki.py` → weekly TSV of unexported chunks, posted as a Telegram document, marks rows exported.
**Accept:** file imports cleanly into Anki with fields in the right order.

### S8 · Couple challenge (M8)
**Build:** group-chat handler. Daily question at 18:00, first correct answer scores. `couple_scores` per week. Sunday leaderboard message.
**Accept:** both answer in the group; first correct gets the point; leaderboard is right on Sunday.

---

## Phase 3 — Intelligence

### S9 · Interests + reading engine (M4)
**Build:** onboarding extension asking ~10 interest questions → `interests`. `prompts/reading.txt`. 3×/week text at the user's level, 5 comprehension questions, chunk extraction, 1–5 rating that adjusts weights.
**Accept:** texts match stated interests; a 1-star rating measurably lowers that topic's weight.

### S9b · Video engine (M16)
**Build:** YouTube Data API integration. 2×/week (Tue/Thu) selection on interest weights + track rotation + `cefr_level`. Filter to videos with human-written captions. Return one 3-minute segment with start timestamp, not a whole video. Track accent exposure per user and bias selection toward unfamiliar accents.
**Accept:** suggestions match stated interests and level; auto-caption-only videos are excluded; the same accent is never suggested three times running; the message names a specific segment, not just a link.

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

### S16 · Shadowing (M12)
Bot sends a 10–15s clip → user repeats → Whisper compares word-for-word → scored feedback on rhythm and stress.

### S17 · Watch-together (M15)
Both mine the same episode; bot cross-quizzes each on the other's chunks.

### S18 · Hardening
`scripts/backup.sh` daily + weekly off-server copy. `scripts/heartbeat.py` alerting if no job fired in 26h. Global exception handler messaging the operator. `/pause` and `/stats` commands.

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
