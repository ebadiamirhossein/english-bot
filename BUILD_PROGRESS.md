# BUILD PROGRESS

> **Cursor: you must update this file at the end of every slice, before finishing your turn.**
> **Human: upload this file to a new Claude chat to restore full context.**

**Project:** English Learning System — Telegram bot, 2 users, B1 → B2 in 6 months
**Repo:** `english-bot`
**Last updated:** 2026-08-08
**Current slice:** S11
**Status:** S11 weekly test + Murphy routing code-complete — verify in Telegram; unrun checks remain on S11 / S12 / S10 / S6a / S9c / S9a / S9 / S6 / S5 / S5a / S3

---

## How to resume in a new Claude chat

Upload this file plus `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/TASKS.md`. Say:
*"Continuing the English bot build. Read BUILD_PROGRESS.md. Give me the Cursor prompt for the next slice."*

---

## Slice status

| Slice | Name | Status | Date | Notes |
|---|---|---|---|---|
| S0 | Repo skeleton | ✅ done & verified | 2026-07-31 | Config, db migrate/status, `/ping` verified against local PG 16.14. |
| S1 | Onboarding | ✅ done & verified | 2026-07-31 | ConversationHandler `/start`; users+streaks upsert; access control. Verified live. |
| S1a | Onboarding UX polish | ✅ done & verified | 2026-08-01 | Superseded interaction model by S1b; data layer unchanged. Verified live. |
| S1b | Onboarding rebuild | ✅ done & verified | 2026-08-03 | Single-message `edit_message_text` wizard; 8 taps / 0 typing common path; why multi-select → sentence; HTML + escape. Verified live. |
| S1c | Onboarding content | ✅ done & verified | 2026-08-03 | Self-assessment A2/B1/B2; domain category→specific drill-down; situation-based why options; EF SET nudge on save. Verified live. |
| S1d | Onboarding personality | ✅ done & verified | 2026-08-03 | Layout helper (≤12 shared rows); emoji on options; static reactions; warmer copy. Sticker skipped (no stable file_id). Verified live. |
| S2 | LLM wrapper + correction | ✅ done & verified | 2026-08-03 | `llm.py` + free correction. Verified live. |
| S3 | Daily quiz + scheduler | ✅ done & verified | 2026-08-03 | Spacing ladder + quiz + 5-min poll. Core verified live; order/choice body+1–4 buttons check still open (2026-08-07 truncation fix). **2026-08-08:** `OpenQuizFilter` narrowed to current format `gap` only — non-gap open quizzes were silently swallowing free text and killing M2 (dispatch fix; Telegram re-verify pending). |
| S3a | Quiz content + formats | ✅ done & verified | 2026-08-03 | Labels not codes; track mix; gap/choice/reorder/spot. Verified live. |
| S3b | Quiz question layout | ✅ done & verified | 2026-08-03 | Body reads / buttons tap; feedback blank line. Verified live. |
| S3c | Quiz formats + register | ✅ done & verified | 2026-08-03 | Reorder→order; spoken register; one scenario. Verified live. |
| S3d | Quiz feedback + format mix | ✅ done & verified | 2026-08-03 | Full-sentence feedback; 2 typed/3 tapped. Verified live. |
| S4 | Streaks, freeze, rescue | ✅ done & verified | 2026-08-03 | 03:00 local rollover; freeze; rescue 3Q. Verified live. |
| S4b | Database backups | ✅ done & verified | 2026-08-04 | pg_dump/restore scripts; restore verified; off-site stub. Verified live. |
| — | **PHASE 1 SHIPPED — 14-day usage gate** | ⬜ | | Phase 1 slices verified; 14-day use gate still open |
| S5 | Voice partner | 🟡 code-complete | 2026-08-04 | Whisper+TTS; voice sessions; Active>Missed. Unrun: mid-conversation restart. |
| S5a | Voice processing status | 🟡 code-complete | 2026-08-04 | Repeating chat action + 3-stage status message. Unrun: never tested in Telegram. |
| S6 | Book ingestion | 🟡 code-complete | 2026-08-08 | `/book` → album debounce → vision OCR → `book_units` upsert; Done/Add more ends CH. Live: 10 pages → 5 units, clean merge/dedup path. Suspected “correction collision” was S3 OpenQuizFilter, not the book CH. Light hardening: `collecting` gates late photos; 1h `conversation_timeout` clears abandoned `user_data["book"]`. Human checks still pending. |
| S6a | `/test` + quiz top-up | 🟡 code-complete | 2026-08-08 | `book_test` session; tap-only `/test unit N`; morning top-up from `book_units` when due < size; selection-time dedup/word-bank; journal on book miss with taxonomy guard. |
| S7 | Anki export | ✅ done & verified | 2026-08-08 | TSV from `chunks` only; poll + `/anki`; mark-after-send. Human imported TSV into Anki; second `/anki` reported nothing new. S11 moved weekly poll to Saturday. |
| S8 | Couple challenge | ⬜ not started | | |
| S9 | Interests profile | 🟡 code-complete | 2026-08-04 | `/interests` wizard seeds `interests`. Unrun: custom-topic weight/last_used across Change→Done. |
| S9a | Reading delivery + chunks | 🟡 code-complete | 2026-08-06 | Mon/Wed/Fri evening poll; readings+chunks+session; ceiling; LLM off event loop. Unrun: same-day second poll / ceiling / morning quiz unblock. |
| S9b | Video engine (YouTube) | ⬜ not started | | |
| S9c | Reading comprehension + rating | 🟡 code-complete | 2026-08-08 | MCQ taps only; session resolve by message_id; edit-failure resend; rating→additive weight; legacy skip score=NULL. |
| S10 | Motivation engine | 🟡 code-complete | 2026-08-08 | Nudge ladder (quiz/reading, max 2/day, Just do 2) + Sunday report (all-clear resolved_types, no LLM); human Telegram verify pending. |
| S11 | Weekly test + Murphy routing | 🟡 code-complete | 2026-08-08 | Sun 15Q weekly test (replaces morning quiz); Anki→Sat; Murphy rec on complete; weekly excluded from M14 window. | |
| S12 | Calibration + anti-fossilization | 🟡 code-complete | 2026-08-08 | M14 windowed raise/silent drop + M13 monthly fossil_sweep inject; human Telegram verify pending. |
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
| 2026-08-08 | S11 weekly test **replaces** Sunday morning quiz (`task_type='quiz'`, 15Q) — does not add a fourth bot-initiated message | Sunday was already at the hard ceiling of 3 (quiz + Anki + report). Yielding would silently suppress the test; a weekly test that skips itself is not a weekly test. |
| 2026-08-08 | S11 Anki export moved from Sunday to **Saturday** evening | Nothing about the export needs Sunday; frees Sunday to weekly test + report = 2, leaving a nudge slot. Supersedes S10 “report beats Anki on last Sunday slot.” |
| 2026-08-08 | S11 `mark_result` applies to weekly-test error answers (including not-yet-due) | Genuine evidence either way; the alternative (test without recording) would make the weekly test the only place answers don’t count. Book-sourced answers still journal (S6a fork). |
| 2026-08-08 | S11 rescue skips the weekly test — Sunday in rescue stays a normal 3Q day | PRD §7 rule 7: no backlog. A 15Q Sunday is the opposite of re-engagement. |
| 2026-08-08 | S11 Murphy range match: expand `'69-81'` / `'5-6,11-14'` to unit-number strings; overlap with `book_units` where `book='murphy'` → “already studied”, else “new”; skip NULL `murphy_units` | `unit_number` is TEXT; ranges must expand. Uses S10 `top_error_types` for order — no second aggregation. |
| 2026-08-08 | S11 quiz gen `max_tokens=7500` when ≥10 questions; else 2500 | 15Q is ~3× the 5Q JSON payload; 2500 truncates. |
| 2026-08-08 | S11 `plan_formats` generic path places gaps at evenly spaced indices; `typed_gap_count` gate is `n==5` only (n=3/5 pinned unchanged) | Old `gaps_left >= slots_left - taps_left` front-loaded all gaps (six in a row for n=15). Rescue/daily mixes stay byte-identical. |
| 2026-08-08 | S11 calibration window **excludes** `payload.weekly_test` | Coverage set draws not-yet-due (easier) errors and is half the 30Q window — would ratchet `cefr_level` on non-representative material. Same spirit as excluding `book_test`. |
| 2026-08-08 | S11 with weekly excluded, Sunday contributes **no** calibration evidence: if Sunday is the only completed session, no `calibration_log` row and that day does not count toward ≥8-of-14 raise | A non-representative session should neither raise nor block. A user who only ever does Sundays can never be calibrated — intended, not a bug. |
| 2026-08-08 | S12 rolling “30-question” accuracy = session-aggregate walk over completed `quiz`+`reading` (`correct_count`/`answered` or `score×n`), newest-first until ≥30 answers (may slightly overshoot). Not a true per-question event stream — `mark_result` has no timestamps and quiz payloads lack per-question outcomes. | No migration; honesty over false precision. Known issue #20. |
| 2026-08-08 | S12 calibration window excludes `book_test` | `/test` is user-chosen material; easy self-selected units would inflate accuracy and raise `cefr_level` on choice rather than ability. Book answers still journal / feed the ladder. Hook gates on `task_type=='quiz'` despite shared `_advance_after_answer`. |
| 2026-08-08 | S12 daily `calibration_log` upsert (SELECT then INSERT/UPDATE) when sample ≥30; same-day second completion refreshes `accuracy_30` | First-write-wins would discard the day’s full evidence; a change row already written today is preserved when only accuracy refreshes. |
| 2026-08-08 | S12 raise = last 14 local days, **≥8 logged days**, every log (and today) `>85%`, current window `>85%`. Skipped days are not failures. Min 8 ≈ rule-6 5/7 over a fortnight (exact pace ≈10). | Consecutive 14 active days contradicts PRD §7 rule 6 and would make raise dead code. |
| 2026-08-08 | S12 drop when current window `<70%` (no multi-day sustain); cooldown 14 days after any level change; bounds A2–C1; min sample 30 before any change | PRD states two weeks only for raises; hysteresis prevents day-after oscillation; A2/C1 match onboarding/EF bands without inventing C2 pitch. |
| 2026-08-08 | S12 **raise announced** (warm, ceiling-aware; skip message + WARNING if at 3, level still changes); **drop silent** (log + apply, never message) | Raise is earned progress; announcing a drop is guilt (PRD §7 rule 4) and punishes a bad fortnight. |
| 2026-08-08 | S12 M13: monthly poll (with freeze) queues ≤2 aged resolved rows (`resolved_at` ≤ today−30) into `fossil_sweep` session `{pending,done}`; inject 1/quiz; **skip entirely in rescue**; correct → `done` only (**never mutate `resolved_at`**); wrong → existing `mark_result` un-resolve | `resolved_at` bump would fake “newly quiet” on Sunday (S10). Rescue must not spend 1/3 of a 3Q re-engagement ask on sweep material. No migration for last_retested_at. |
| 2026-08-08 | S12 un-resolving one row drops that type from S10 `resolved_types` (all-clear) — intended | M13 exists to prevent the illusion of progress the Sunday lead would otherwise keep showing. |
| 2026-08-08 | **Contract from S6 onward:** Cursor prompt + PRD is the slice contract; no `specs/S10-*.md` (same as S6/S6a/S7/S9c). Decisions log is the source of truth. **`.cursorrules` still says stop if specs/ is missing — amend it separately; S10 does not edit `.cursorrules`.** | A parallel spec file drifts; Amirhossein amends the constitution deliberately. |
| 2026-08-08 | S10 nudges only `quiz` and `reading` | `book_test` is user-initiated (nagging); voice has no scheduled delivery; `free_practice` is a soft empty-journal day. |
| 2026-08-08 | S10 “Just do 2” sets `payload.early_limit=2`; completes at 2 answers with `score = correct_count / 2.0`; remainder ungraded (stay due) | A button that promised less work and still delivered 5 would be worse than no button (PRD §7 rule 3). |
| 2026-08-08 | S10 rescue second nudge still offers “just do 2” | Rescue is already 3Q; 2 of 3 is a real cut. Offering “just 1” invents a third ladder step PRD does not define. |
| 2026-08-08 | S10 `resolved_types` = all-clear (every row of that type resolved; ≥1 row) — not “any instance resolved” | One resolved + nine unresolved must not lead the Sunday report; that is the illusion of progress M13 exists to prevent. |
| 2026-08-08 | S10 Sunday active-days copy: `N < 5` → “N of 5”; `N >= 5` → “{n} active days — full week” (no denominator) | Rule 6 forbids judging against 7; `7/5` is nonsense above target. |
| 2026-08-08 | S10 Sunday report poll `first` before Anki; report wins last ceiling slot; Anki yields (`/anki` escape hatch) | Report has no manual equivalent; weekly Anki is recoverable. Nudges are not specially disabled on Sunday — full quiz+Anki+report leaves zero room by rule 9 (expected, not a bug). Mon/Wed/Fri quiz+reading spend 2 of 3 ceiling slots, so the 2-nudge daily budget is only reachable on non-reading days. |
| 2026-08-08 | S10 Sunday report assembled without an LLM | Deterministic DB facts cannot hallucinate progress; free; warmth is templates only (`why_statement` only if under 400 chars). |
| 2026-08-08 | S10 daily nudge cap = `SUM(nudges_sent)` on session delivery date (max 2/day ever); per-session ladder still +3h/+6h via `nudges_sent` | PRD §7 rule 3 wins over “per unfinished task” wording in the prompt intro. |
| 2026-08-08 | S6a: `/test` uses `task_type='book_test'`, never `'quiz'` | Fake quiz rows corrupt completion rate, streak Missed-detection, and the 14-day gate (2026-08-03). `has_session_on` stays scoped to `('quiz','free_practice')` so `/test` cannot cancel the next morning quiz. |
| 2026-08-08 | S6a: `/test` answers are **taps only** — no text MessageHandler; callbacks use `btest:` | Widening `OpenQuizFilter` or owning free text would re-swallow M2 (S3 live outage). Dispatch-tested: open mid-set `book_test` → plain text reaches correction. |
| 2026-08-08 | S6a: top-up walks `book_units` by `studied_at DESC`, exhausting each unit before the next | User photographed units because they are studying them now; recency is the signal. |
| 2026-08-08 | S6a: selection-time near-dedup (casefold + whitespace + strip parentheticals; substring if shorter ≥8) — do not rewrite stored rows | Known issue #14: exact-string union leaves “Present continuous” beside “present continuous (I am doing)”. Fixing at selection avoids a migration and keeps OCR history intact. |
| 2026-08-08 | S6a: word-bank heuristic = `^(verbs?\|nouns?\|…)\s*:` **or** ≥4 short comma tokens **after stripping parentheticals** | Live dry-run on 41 Murphy items: excludes only `verbs: cross, hide, scratch, take, tie, wave`; keeps stative-verbs-with-exemplars and irregular-verbs lists. Comma arm on the full string falsely excluded unit 5 irregular verbs. |
| 2026-08-08 | S6a: zero due + usable book items → morning `quiz` (not `free_practice`). **On a zero-due-error day where book items exist, an ignored morning quiz now costs a freeze where it previously stayed Neutral.** | PRD M1 top-up; a real task was delivered. Zero due and no book items still → `free_practice` / Neutral. `streaks.py` untouched; behaviour pinned by tests. |
| 2026-08-08 | S6a: wrong book-sourced answers → `record_errors(source='quiz')`; never `mark_result`. Unknown `error_type` → WARNING + skip | Book questions have no prior `errors` row. Taxonomy guard matches correction — a bad type poisons the journal permanently. Fork lives in `_advance_after_answer` so typed gap and tapped paths both hit it. |
| 2026-08-08 | S6a: new `/test` marks prior incomplete `book_test` completed-as-abandoned (`score=NULL`) | Abandoned mid-sets would accumulate forever; reuse is error-prone with message_id. NULL = not assessed (same signal as S9c legacy skip). |
| 2026-08-08 | S9c: all comprehension answers are **taps only** — no reading branch in `correction.py` | Typed answers would fall through to M2 and poison the error journal with comprehension guesses. Free text during an open reading still reaches correction (dispatch-tested). |
| 2026-08-08 | S9c: `reading.txt` questions are MCQ `{q, options[4], answer_index, why}` (why ≤25 words) | PRD §8 explanations; grading is deterministic index compare — no second LLM call. Generation validator enforces the shape; delivery uses soft `parse_stored_questions`. |
| 2026-08-08 | S9c: resume state in session `payload` with required `phase` (`questions`\|`rating`) | `bot_data` dies on restart (S3). Skip-to-rating never enters `questions`, so `phase` cannot be inferred from `q_index == 5`. |
| 2026-08-08 | S9c: resolve session by `payload.message_id` + `chat_id` from the callback message | “Any open reading” would let orphan session 803 (reading 17, no message_id) steal Monday’s Questions tap and rate the wrong topic. |
| 2026-08-08 | S9c: on edit BadRequest other than “not modified”, resend as a new message and update `message_id` | Next-day / deleted-message edits are expected (PRD §7 rule 2); a silent dead button is worse than a new message. No `bot_message_counts` — reply to a tap. |
| 2026-08-08 | S9c: rating→weight is **additive** (`1→−0.30 … 5→+0.30`) clamped `[0.25, 3.00]` | Multiplicative decay would bury a topic after one bad evening; S9a selection still resurfaces floor-weight topics. Removal stays the user’s job via `/interests`. |
| 2026-08-08 | S9c: legacy/malformed questions → WARNING + skip to rating with **`score = NULL`** | Reading 17 still has `question`/`answer`/`distractors`. Zero would mean “0/5” and poison S12 rolling accuracy — NULL means not assessed; later consumers must not treat NULL as 0. |
| 2026-08-08 | S7: export reads **`chunks` only** — do not export `book_units.target_items` | Book items are grammar concepts ("am/is/are + -ing"), not sentences; no carrier sentence → poor cloze cards. A later slice can generate sentences for book items if wanted. |
| 2026-08-08 | S7: sanitise **all four** TSV fields (tab→space, CR/LF→space, collapse whitespace, strip) before write | A literal tab is a field break and a newline is a row break in Anki; one dirty subtitle/reading chunk silently shifts every field after it. |
| 2026-08-08 | S7: mark `exported_to_anki` + insert `anki_export` session inside a txn held across `send_document` (commit only after send) | Same as S9a: a failed send that already marked rows loses those cards permanently — they are never re-offered. |
| 2026-08-08 | S7: weekly idempotency via `sessions` row `task_type='anki_export'` + `has_anki_session_on` (poll pattern, not per-user job) | Second Sunday poll tick must send nothing; polls survive restarts and pick up new users (S3 decision). |
| 2026-08-08 | S7: `/anki` is user-initiated — no `bot_message_counts` increment; weekly document is bot-initiated and respects the ceiling of 3 | PRD §7 rule 9 caps bot-initiated messages; manual export must stay testable even when the day is full. |
| 2026-08-08 | S3: `OpenQuizFilter` matches only when the open quiz’s **current** question `format == "gap"` | Root cause of live “free text after /book Done does nothing”: incomplete quiz at `choice` (session 1133) — `on_quiz_text` returned silently on non-gap while `block=True` stopped correction. Survives restart (DB). Not the book ConversationHandler: `COLLECT_PAGES` has no TEXT handler; nested Done `map_to_parent END→END` does end the parent (verified). Present since non-gap formats landed — intermittent dark M2 and unrecorded journal gaps. |
| 2026-08-08 | S3: rejected soft-nudge on non-gap typed text; accept that typing during choice/order/spot yields a **correction**, not a grade | A nudge still consumes the update and blocks M2 — same outage with better manners. Buttons remain the answer path (PRD §8). Do not “restore” the broad filter later. |
| 2026-08-08 | S3: leave incomplete quizzes incomplete (do not forge `completed` to unblock M2) | Forging completion marks the day Active and corrupts completion rate / 14-day usage (2026-08-03 — same reason zero-due days use `free_practice`). After filter narrowing, non-gap open quizzes are harmless. |
| 2026-08-08 | S6: do **not** poke `ConversationHandler._conversations` from JobQueue; do **not** move Done/Add more to parent entry points | Private PTB internals are upgrade-fragile; CallbackQuery entry points on `per_message=False` reintroduce the S1a `PTBUserWarning`. Open book CH does not block correction; `collecting=False` already gates late photos. Abandoned flows: 1h `conversation_timeout` + TIMEOUT clears `user_data["book"]` (PTB nested-timeout caveat noted; never silence the warning). |
| 2026-08-08 | **Standing rule:** any change to `llm.py` request construction requires **one real API call** before it ships | Mocked tests cannot express the provider contract. Prefill shipped green under mocks and broke every live `json_mode` caller (`action=skipped_llm` on morning quiz). |
| 2026-08-08 | S6 fix: assistant `{` prefill **removed** entirely (initial + repair); every request must end on a user message | Hard provider constraint: `claude-sonnet-5` returns 400 `invalid_request_error` — "This model does not support assistant message prefill. The conversation must end with a user message." Do not reintroduce trailing-assistant prefill. |
| 2026-08-08 | Why the earlier "repair already uses prefill" claim was wrong | The repair path never prefaced the API call with a trailing assistant `{`. It appended `assistant=<bad text>` then `user=<repair instruction>`, so the request **ended on a user turn**. Mid-conversation assistant messages are fine; ending on assistant is not. The 2026-08-07 decision conflated those two shapes. |
| 2026-08-08 | S6 fix: tolerant JSON extraction in `_parse_json` (strip ``` fences; first `{`…last `}` span) instead of request-shape constraints | Original OCR failure was prose-around/instead-of-JSON (~96 tok). Prefill was the wrong lever and broke the API. On total failure (no `{` / span won't parse): WARNING + truncated `raw=` + `LLMError` — never fabricate `{}` or empty `target_items`. |
| 2026-08-08 | S6 summary: >4 failed pages collapse to `All N pages`; CTA singular/plural (`that page` / `those pages`) | Long enumerated lists are unreadable; singular CTA contradicted plural page lists. |
| 2026-08-07 | ~~S6 fix: `json_mode` appends assistant `{` prefill on **every** call~~ — **REVERTED 2026-08-08** | Claimed Anthropic already accepts trailing assistant via repair; that was false (see above). Live blast radius: correction, quiz, reading, voice, book OCR. |
| 2026-08-07 | S6 fix: JSON parse failures log/raise with first ~300 chars of raw response text (permanent) | Parser message alone (`Expecting value: line 1 column 1`) is unfixable without a live repro; next `/book` must show whether the model wrote a legibility complaint or a **copyright/textbook refusal** (two ~96-token calls are consistent with either — if refusal, stop and report; do not tune toward silent empty `target_items`). Never log image bytes. |
| 2026-08-07 | S6 fix: `book_ocr.txt` forces structural `readable: false` (never prose); handwriting excluded from `target_items`; rotation alone ≠ unreadable; personal-use scope stated | Model explained instead of returning the failure object; filled-in Murphy pages will recur; PRD §5 M5 is personal-use study extraction. |
| 2026-08-07 | S6 fix: summary uses `Page`/`Pages` agreement; unreadable vs snag kept; both CTAs unify to “re-shoot that page, one page per photo” | User cannot act differently on either failure path; singular “Pages 1 …” was wrong. |
| 2026-08-07 | S6: album debounce cancels prior jobs via `get_jobs_by_name` + `schedule_removal` before `run_once` (~2.5s); `process_pages` pops `pages` and bails if empty or `processing` | PTB `name=` does not replace jobs — ten album updates would schedule ten runs and race on `user_data`. Mid-fire removal is not guaranteed, so the pop/`processing` guard is required. |
| 2026-08-07 | S6: after batch, summary with Done / Add more pages; Done callback returns `ConversationHandler.END`; `collecting` cleared by the job | JobQueue cannot return `END`; leaving CH in `COLLECT_PAGES` would swallow later photos / risk free-text not reaching correction. |
| 2026-08-07 | S6: pages past 20 set `over_cap` and drop silently; one summary line, no per-photo refusal | A 25-photo album would otherwise spam five refusal messages. |
| 2026-08-07 | S6: book identity is the user's button/slug (`murphy` / `vocabulary_in_use` / `marketing` / slugified Other), never the LLM | OCR guesses the book from a page; the user knows. Slug makes S6a `/test unit N` match reliable. |
| 2026-08-07 | S6: `target_items` is a flat `list[str]` of short grammar/vocab items | Contract for S6a / quiz top-up; nested shapes are expensive to change once rows exist. |
| 2026-08-07 | S6: re-ingest upserts in app code (SELECT then UPDATE union / INSERT); no unique constraint / no migration | Schema forbids 004 in this slice; second `/book` on the same chapter must not double rows or double S6a weight. |
| 2026-08-07 | S6: continuation pages (`unit_number` null) merge into the latest non-null unit in-batch; orphan before any unit → WARNING + skip + named in summary | Guessing a unit for an orphan invents journal noise. |
| 2026-08-07 | S6: failure summary names batch-position page indexes, never OCR-read page numbers | User can identify and re-shoot; a bare count hides systematic OCR failure. |
| 2026-08-07 | S6: `llm.py` embeds images into messages before the first call so json_mode repair re-sends image blocks | A repair that drops the image silently degrades to a text-only guess. |
| 2026-08-07 | S6: batch INFO logs page count / units written / pages failed only; per-call tokens stay in `llm.py`; `chat()` return type unchanged | Provider usage is already logged per call; inventing image-token estimates would be fiction. |
| 2026-08-07 | S6 ends at `book_units` rows; `/test unit N` and quiz top-up are S6a | TASKS S6 bundled both; splitting matches S3→S3d vertical-slice pattern and keeps this slice shippable. |
| 2026-08-07 | S6 `/book` replies do not increment `bot_message_counts` | User-initiated; PRD §7 rule 9 caps bot-initiated messages (same as S5 voice). |
| 2026-08-07 | Standing rule — every slice ends with a `BUILD_PROGRESS.md` update (slice row, decisions with reasons, known issues, file inventory, Next action carrying forward every unrun check) | This file is the only memory between sessions; a stale file causes settled work to be re-litigated. |
| 2026-08-07 | S9c split from S9a — comprehension delivery, grading and the 1–5 rating are their own slice | Chunks unblock S7 before the Q&A UX lands. |
| 2026-08-07 | Quiz `order`/`choice`: options as numbered list in the message body; buttons are `1`–`4` only. Permanent ≤20-char button-label rule in `.cursorrules` | Live: Telegram truncates full-sentence button labels ("I went to Vilnius l...for a conference") — question unanswerable. Restates S3b (body reads / buttons tap). Spot tiles stay single words (audit: gap has no buttons; spot under contract stays ≤20). |
| 2026-08-06 | S9a: scheduled LLM via `asyncio.to_thread`; evening job `first=EVENING_FIRST_SECONDS` (mid-interval) | Live 2026-08-06: morning quiz LLM blocked the event loop ~17s; APScheduler skipped the evening poll (jobs were only 5s apart). Soft to the user looked like "reading never fires." |
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
| 7 | Morning quiz LLM blocked the event loop (~17s); APScheduler skipped that tick's evening reading poll (jobs first=10/15). | high | S9a | ✅ closed — 2026-08-06 (`asyncio.to_thread` + mid-interval evening offset) |
| 8 | S6 per-batch vision cost unmeasured — record observed cost from the first real 10–20 page run | medium | S6 | ⬜ open |
| 9 | S6 OCR accuracy on real Murphy pages unverified until a clean single-page batch succeeds (first live run failed on JSON shape before accuracy could be judged) | medium | S6 | ⬜ open |
| 10 | 2026-08-07 `{` assistant prefill broke all live `json_mode` callers (`claude-sonnet-5` 400). Morning quiz `action=skipped_llm`. | critical | S6 | ✅ closed — 2026-08-08 (prefill removed; tolerant parse; live json_mode + vision + quiz builder OK) |
| 11 | Original S6 prose-instead-of-JSON (~96 tok ×2) still undiagnosed — next live `/book` must read WARNING `raw=` for refusal vs legibility before further prompt tuning | medium | S6 | ⬜ open |
| 12 | S3 silent-consume: `OpenQuizFilter` + non-gap `on_quiz_text` return blocked M2 whenever an open quiz sat on choice/order/spot. **Journal gaps** on those days — do not read low error volume as “wrote well.” Fixed by gap-only filter (2026-08-08); Telegram verify pending. | high | S3 | 🟡 code-fixed — verify live |
| 13 | Quiz callback: stale session / format mismatch after `query.answer()` can leave the button inert (no edit). Note only — does not block correction. | low | S3 | ⬜ open — note only |
| 14 | S6 `target_items`: near-duplicates survive two-page union (`"Present continuous"` vs `"present continuous (I am doing)"`) because only exact string matches are dropped. | medium | S6 | ⬜ open — later pass |
| 15 | S6 `target_items`: exercise word banks captured as items (e.g. `"verbs: cross, hide, scratch, take, tie, wave"`). | medium | S6 | ⬜ open — later pass |
| 16 | S7 Anki import itself unverified until a human imports a real TSV and confirms four fields land in the right order with no mangled rows. | medium | S7 | ✅ closed — 2026-08-08 (human imported TSV; second `/anki` empty) |
| 17 | Reading 17 ("Finding a Place to Call Home"): legacy question shape + session 803 has no `message_id` / no Questions keyboard — cannot complete in Telegram; orphan stays incomplete forever. Manual Q&A verify on a **fresh** reading after S9c. Covered by legacy-skip unit test. | medium | S9c | ⬜ open — note only |
| 18 | S6 `conversation_timeout` is a documented no-op under nested ConversationHandlers (PTB warning). Abandoned book `user_data` still cleared on TIMEOUT when the outer job fires; do not silence the warning. | low | S6 | ⬜ open — note only |
| 19 | S10 nudge timing (+3h / +6h) cannot be validated until the bot runs unattended — process currently only lives while the laptop is open, so a +3h nudge requires the process still alive 3 hours after delivery. | medium | S10 | ⬜ open — needs unattended host |
| 20 | S12 rolling accuracy is an **approximation** from completed quiz/reading session aggregates (no per-question outcome log / timestamps). Level changes act on this estimate. | medium | S12 | ⬜ open — by design without migration |

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
| `docs/ARCHITECTURE.md` | Stack, structure, interfaces; §5 jobs split Anki Sat / Sunday report (S11) | ✅ |
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
| `app/llm.py` | Anthropic chat + vision (`images=`); `json_mode` tolerant parse + raw truncate on fail; no assistant prefill; only LLM provider SDK import | ✅ |
| `app/speech.py` | OpenAI STT/TTS wrapper; only speech provider SDK import | ✅ |
| `app/scheduler.py` | Morning + evening + Sunday report + Saturday Anki + nudge polls + streak/freeze + M13 fossil sweep | ✅ |
| `app/texts.py` | User-facing strings + S1d–S12 (incl. LEVEL_RAISE, QUIZ_WEEKLY, Murphy rec) | ✅ |
| `app/main.py` | Bot entrypoint; `/ping`, `/anki`, `/test`, `/start`, correction, quiz, reading, nudge, book_test, voice, `/interests`, `/book`, scheduler | ✅ |
| `app/services/calibration.py` | M14 rolling accuracy (excludes book_test + weekly_test), daily calibration_log upsert, raise/lower, raise notice | ✅ |
| `app/handlers/nudge.py` | Tap-only `nudge:short:` early-limit callbacks; Murphy append on weekly early-complete (S10/S11) | ✅ |
| `app/services/motivation.py` | Nudge ladder + Sunday report assembly (no LLM) (S10) | ✅ |
| `app/handlers/__init__.py` | Handlers package | ✅ |
| `app/handlers/access.py` | Shared unregistered-user ignore + onboarding allowlist | ✅ |
| `app/handlers/onboarding.py` | `/start` wizard + `layout_buttons` + reactions (S1d) | ✅ |
| `app/handlers/correction.py` | Free-text correction (S2) + shared `render_correction_message` | ✅ |
| `app/handlers/quiz.py` | Daily/weekly quiz + top-up; evenly spaced `plan_formats`; book grading fork; `early_limit`; Murphy append on weekly complete; M13/M14; `OpenQuizFilter` gap-only | ✅ |
| `app/handlers/voice.py` | Voice partner handler (S5) + status stages / repeating chat action (S5a) | ✅ |
| `app/handlers/interests.py` | `/interests` multi-select wizard (S9); index callbacks; custom-topic preload | ✅ |
| `app/handlers/reading.py` | Evening reading + S9c Q&A/rating; `early_limit`; M14 calibrate on scored complete | ✅ |
| `app/handlers/book.py` | `/book` ConversationHandler; album debounce; vision OCR; Done/Add more; 1h conversation_timeout (S6) | ✅ |
| `app/handlers/book_test.py` | `/test unit N`; tap-only `btest:` callbacks; abandon prior open book_test (S6a) | ✅ |
| `app/prompts/book_quiz.txt` | Unit practice JSON — choice/order/spot only; taxonomy-bound error_type (S6a) | ✅ |
| `app/services/__init__.py` | Services package | ✅ |
| `app/services/users.py` | get/save user, EF SET → CEFR, `update_cefr_level` (S12) | ✅ |
| `app/services/errors.py` | record_errors + due_errors + weekly select + Murphy expand/lookup + mark_result + resolved_types + M13 (S3/S10/S11/S12) | ✅ |
| `app/services/sessions.py` | sessions + ceiling + fossil_sweep helpers + sunday_report + active_days (S3–S12) | ✅ |
| `app/services/anki.py` | Chunk→TSV gap/escape/export; weekly deliver + `/anki`; mark-after-send (S7) | ✅ |
| `app/services/streaks.py` | Streak rollover, freeze, rescue; Active>Missed precedence (S4/S5) | ✅ |
| `app/services/interests.py` | list/replace/select_topic/mark_last_used + adjust_weight_for_rating (S9/S9a/S9c) | ✅ |
| `app/services/chunks.py` | Chunk inserts for reading (S9a) | ✅ |
| `app/services/reading.py` | MCQ validate + parse_stored_questions + persist_and_send + complete_reading (S9a/S9c) | ✅ |
| `app/services/books.py` | OCR parse/merge, upsert, summary; list/find/top-up + word-bank/dedup; studied Murphy units (S6/S6a/S11) | ✅ |
| `app/prompts/correction.txt` | Correction system prompt template | ✅ |
| `app/prompts/quiz.txt` | Quiz generation + optional book_items top-up; taxonomy list for book Qs (S3/S6a) | ✅ |
| `app/prompts/voice.txt` | Voice conversation + correction JSON prompt | ✅ |
| `app/prompts/reading.txt` | Reading passage + MCQ questions + chunks JSON prompt (S9a/S9c) | ✅ |
| `app/prompts/book_ocr.txt` | Vision OCR JSON prompt — structural unreadable, handwriting, personal-use (S6) | ✅ |
| `tests/conftest.py` | Dummy `ANTHROPIC_API_KEY` for test settings load | ✅ |
| `tests/test_onboarding.py` | S1 persistence + CEFR mapping tests | ✅ |
| `tests/test_onboarding_validation.py` | S1b validation re-ask via wizard edit | ✅ |
| `tests/test_why_sentence.py` | Why multi-select → sentence grammar (S1c clauses) | ✅ |
| `tests/test_s1c_content.py` | Self-assessment CEFR map + domain drill-down table | ✅ |
| `tests/test_s1d_personality.py` | Layout helper + full reaction coverage | ✅ |
| `tests/test_llm.py` | LLM retry / ends-on-user guard / tolerant parse / raw truncate / vision repair keeps images | ✅ |
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
| `tests/test_reading.py` | S9a eligibility, ceiling, topic pick, MCQ validate, rollback, persist + message_id | ✅ |
| `tests/test_reading_s9c.py` | S9c grading, resume, message_id resolve, rating clamps, legacy NULL score, edit resend, labels | ✅ |
| `tests/test_book.py` | S6 debounce, merge, upsert, failures, Page/Pages / All-N collapse, CTA agreement, prose soft-skip, over-cap, labels, SDK/disk greps | ✅ |
| `tests/test_dispatch_m2.py` | Application dispatch: quiz gap/non-gap vs correction; nudged open quiz → correction; book_test/reading/book (S3+S6+S6a+S9c+S10) | ✅ |
| `tests/test_s6a.py` | Top-up counts, word-bank/dedup fixtures, journal fork (typed+tap), streak Missed vs Neutral, `/test` parse/disambiguate/abandon, labels (S6a) | ✅ |
| `tests/test_anki.py` | S7 gap/escape/order/mark-after-send/ceiling/idempotency/empty `/anki` | ✅ |
| `tests/test_motivation.py` | S10 nudge ladder, ceiling, dual-TZ, resolved_types all-clear, active-days bands, Sunday report, Just do 2 score, no-guilt/labels | ✅ |
| `tests/test_calibration.py` | S12 M14 windowed raise, drop silent, cooldown, bounds, book_test excluded, upsert, pause, no-guilt | ✅ |
| `tests/test_fossilization.py` | S12 M13 sweep queue, un-resolve, resolved_at untouched, rescue skip, no marker leak, resolved_types | ✅ |
| `tests/test_weekly.py` | S11 Sun 15 / Mon 5 / rescue 3; spread select; top-up; free_practice; mark_result; early_limit; Anki Sat; ceiling 2; Murphy; labels | ✅ |
| `specs/S5a-voice-status.md` | S5a voice processing status | ✅ |
| `scripts/backup.sh` | Daily pg_dump (−Fc), 14-day retain, off-site stub | ✅ |
| `scripts/restore.sh` | Restore into scratch DB; `--force` for live | ✅ |

---

## Next action

Unrun human Telegram checks (do not start S8 / S9b until these are cleared or explicitly deferred):

**S11 (weekly test + Murphy routing — this slice)**
- Local Sunday morning → 15-question weekly test (preface line); finish → completion includes Murphy recommendation matching top error types (labels, studied vs new); no codes; under 400
- Local Monday–Saturday morning → still 5Q (rescue → 3Q); Sunday in rescue → 3Q, not 15
- Mid-weekly-test on a choice question → free text reaches correction
- Tap `Just do 2` on an open weekly test → completes at 2; `score = correct/2`
- Saturday evening → Anki document (if unexported chunks); Sunday evening → report only, no `anki_export` session; Sunday bot-initiated count = weekly test + report ≤ 2
- Confirm a completed weekly alone does not write `calibration_log` / does not raise level

**S12 (calibration + anti-fossilization)**
- Seed / complete enough scored quizzes that `calibration_log` accrues ≥8 days >85% in a fortnight → warm level-raise message once; `users.cefr_level` and log `old≠new`
- Force a low-accuracy window → level drops in DB, **no** user message
- With `bot_message_counts = 3` on raise day → level still rises, notice skipped (WARNING in logs)
- On local 1st (or forced `now`): `fossil_sweep` session with ≤2 pending; next non-rescue morning quiz includes one ordinary-looking item; wrong answer → `resolved=FALSE` / `unresolved_count++`; correct → `resolved_at` unchanged, id in `done`
- In rescue: morning 3Q has no retest; pending stays queued
- `/test` completions do not write `calibration_log` / do not change level

**S10 (motivation)**
- Leave morning quiz unfinished with bot process alive ≥3h → first warm nudge; at +6h second with `Just do 2`; third never
- Tap `Just do 2` → completes after 2 answers; DB `score = correct/2`; day can count Active
- With `bot_message_counts = 3`, no nudge; `nudges_sent` unchanged
- Sunday after `evening_time` → one progress-first report (`N of 5` or “N active days — full week”); second poll same Sunday → nothing
- Mid-nudge free text → correction, not swallowed
- Note: +3h/+6h timing needs unattended process (known issue #19)

**S6a (`/test` + quiz top-up)**
- With Murphy units 1–5 stored: `/test` → unit buttons; `/test unit 3` → tap-only set; finish; confirm morning quiz still eligible that day (or next morning still delivers)
- `/test unit 99` → warm list of real units; two books same number → which-book buttons
- Abandon mid-`/test`, start a new `/test` → prior session abandoned; new set works
- Mid-`/test`, type free English → correction (M2), not graded
- Light journal day (<5 due) → morning quiz length 5 with book-flavored items; wrong book item → `errors` row with valid type
- Gap-format book question in morning quiz: typed wrong answer → journal, no crash

**S9c (reading Q&A + rating)**
- Wait for (or trigger) a **fresh** evening reading → message has `Questions`
- Tap through 5 MCQs (options in body, buttons 1–4); wrong answers show `why`; after Q5 rate 1–5
- Confirm `readings.completed/score/rating`, session completed, topic weight moved by the map
- Mid-set free text → correction (not journal poison); abandon without Questions → Neutral at rollover
- Reading 17 is test-fixture-only for legacy skip (no Telegram button / no message_id)

**S3 (M2 dispatch)**
- With an open quiz still on a **choice** (or other non-gap) question — e.g. leave sessions 1133/802 incomplete — send free text → correction reply + `llm call` log
- Park on a **gap** question → typed answer grades the quiz, not correction
- Order/choice layout — all four options readable in the message body, buttons are 1–4 (2026-08-07 truncation fix; status stays until human marks ✅)

**S6** (re-verify; OCR/merge/dedup/album debounce already exercised live on 10 pages → 5 units)
- Text after summary **without** Done → correction; Done still clears keyboard; Add more → photos → summary; second `/book` clean session
- Re-send a stored page → still 5 rows not 6; richer `target_items`, fresh `studied_at`
- Single-page portrait / 2-page merge / blurry page / document / 25-page over-cap / scheduler responsive during multi-page — as still needed
- After cost is known: fill known issue #8 (S6 vision cost still unmeasured)
- Gap-question grading path still needs live confirm where not already covered
- `conversation_timeout` nested-CH no-op remains known issue #18

**S5**
- Mid-conversation restart — bot still remembers the topic after Ctrl-C + restart

**S5a**
- Status message shows 🎧 → 💭 → 🔊 then disappears; header "recording" persists the whole wait; over-length declined with no status message first

**S9**
- Set a non-default weight on one interest row, then `/interests` → Change → Done changing nothing → weight and `last_used` survive

**S9a**
- Second evening poll same day delivers no second reading
- With `bot_message_counts = 3`, no reading and no new rows
- Next morning's quiz still delivers (reading session does not block it)
