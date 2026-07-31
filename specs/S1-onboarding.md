# S1 · Onboarding

**Slice:** S1
**Phase:** 1 — Foundation
**Depends on:** S0 (verified 2026-07-31)
**Status:** ⬜ not started
**Spec written:** 2026-07-31

---

## Goal

`/start` runs a conversation that collects everything the system needs to
personalise itself, then writes one `users` row and one `streaks` row. After
this slice the bot knows who it is talking to, at what level, in what native
language, on what schedule, and why they are doing this at all.

This is also where access control begins. From here on, the bot ignores anyone
who is not in `users`.

## Non-goals

- `/settings` — editing individual fields after onboarding is **S18**.
- The ~10 interest questions — that is **S9**, which extends this conversation.
- Any correction, quiz, or LLM call. No `llm.py` in this slice.
- Timezone selection (see open decision 5).
- `explanation_language_fallback` as a question — schema default `TRUE` stands.
- Admin tooling to view or edit users. `psql` is the admin panel for now.

---

## Open decisions — review these before implementation

These are product choices, not technical ones. My recommendation is given, but
this is the part of the spec that most deserves your disagreement.

### 1. EF SET → CEFR mapping (spec bug)

`PRD.md` §3 states the month-6 target as "B2 (57–70)". EF's published alignment
is B2 = 51–60 and C1 = 61–70, so that range spans two levels.

**Recommendation:** use EF's official bands in code, and correct `PRD.md` §3 to
"B2 (51–60)".

| EF SET | `cefr_level` |
|---|---|
| 1–30 | A1 |
| 31–40 | A2 |
| 41–50 | B1 |
| 51–60 | B2 |
| 61–70 | C1 |
| 71–100 | C2 |

*Note:* if the 57 in the PRD was deliberate — a stretch target inside B2 rather
than the band floor — say so and I will reword the PRD instead of the target.

### 2. Onboarding when the EF SET has not been taken yet

The test takes 50 minutes. Blocking onboarding on it means nobody starts today.
`PRD.md` §3 says the baseline is measured in week 1, not day 1.

**Recommendation:** offer a "Not yet" button. Then `efset_baseline` stays NULL
and `cefr_level` defaults to `B1`. The user can re-run `/start` after taking the
test to fill it in.

### 3. Track weights: presets, not numbers

Asking someone to type three numbers that sum to 100 in a Telegram chat is bad
UX and invites invalid input. `PRD.md` §8 says buttons over typing.

**Recommendation:** three preset buttons.

| Label | work / life / curiosity |
|---|---|
| Balanced | 40 / 40 / 20 |
| More work English | 60 / 25 / 15 |
| More everyday English | 25 / 60 / 15 |

Fine-grained weights are auto-adjusted by content ratings from S9 anyway.

### 4. What a second `/start` does

`TASKS.md` says "offers to edit, not duplicate". Full per-field editing is
`/settings`, which is S18.

**Recommendation:** a second `/start` shows the current profile as a summary
with two buttons — **Redo onboarding** (re-runs the whole conversation and
overwrites the `users` row) and **Keep as is**. The `streaks` row is never
touched on a redo; streak history survives.

### 5. Timezone is not asked

Both users are in Vilnius and the schema defaults to `Europe/Vilnius`.

**Recommendation:** don't ask in S1. Add it in S20 (Generalize), which is the
slice that removes location and language assumptions. Record this as a known
assumption so S20 doesn't miss it.

---

## Conversation flow

A `ConversationHandler`. One question per message, per `PRD.md` §8.

| # | State | Question | Input | Writes to |
|---|---|---|---|---|
| 1 | `NAME` | What should I call you? | free text | `name` |
| 2 | `NATIVE_LANG` | What's your native language? | buttons: Farsi · Lithuanian · Other | `native_language` |
| 2b | `NATIVE_LANG_OTHER` | Which language? | free text | `native_language` |
| 3 | `EFSET` | Your EF SET score? | free text 1–100, or button "Not yet" | `efset_baseline`, `cefr_level` |
| 4 | `DOMAIN` | What do you work in? | free text | `work_domain` |
| 5 | `WHY` | Why do you want better English? One sentence. | free text | `why_statement` |
| 6 | `WEIGHTS` | What should we focus on? | 3 preset buttons | `track_weights` |
| 7 | `MORNING` | When should the morning task arrive? | buttons 07:00 · 08:00 · 09:00 · Other | `morning_time` |
| 7b | `MORNING_OTHER` | What time? (HH:MM) | free text | `morning_time` |
| 8 | `EVENING` | And the evening task? | buttons 19:00 · 20:00 · 21:00 · Other | `evening_time` |
| 8b | `EVENING_OTHER` | What time? (HH:MM) | free text | `evening_time` |
| 9 | `CONFIRM` | *(summary of all answers)* | buttons: Save · Start over | — |

Language codes: store ISO 639-1 where known (`fa`, `lt`, `es`), matching the
schema comment. For "Other", store what the user typed, lowercased. Do not
reject an unknown language — `PRD.md` §2 requires any native language to work
with zero code changes.

**Validation.** Reject and re-ask, never crash:
- EF SET outside 1–100, or not a number
- A time that isn't `HH:MM` in 24-hour form
- Empty or whitespace-only name

**Cancel.** `/cancel` at any point ends the conversation and writes nothing.

---

## Persistence

> **Design rule: write nothing until the conversation completes.**
>
> Hold every answer in `context.user_data`. On **Save**, write both rows in a
> single transaction. This makes abandonment free — no partial rows, no cleanup
> job, and duplicate prevention becomes trivial because a half-finished
> onboarding leaves no trace.

On Save, in one transaction:

1. `INSERT INTO users (...) VALUES (...) ON CONFLICT (telegram_user_id) DO
   UPDATE SET ...` — every collected field, plus `onboarded = TRUE`.
   Do **not** overwrite `created_at` on conflict.
2. `INSERT INTO streaks (user_id) VALUES (...) ON CONFLICT DO NOTHING` — schema
   defaults give `current_streak 0`, `freeze_tokens 2`. A redo must not reset an
   existing streak.

Leave `tenant_id`, `plan`, `target_language`, `explanation_language_fallback`,
`timezone` and `paused_until` at their schema defaults. Do not set them in
application code — `PRD.md` §9 wants these present but unused.

### New module: `app/services/users.py`

`ARCHITECTURE.md` §3 does not list this file, but user reads are needed by S2
(native language for prompts), S3 (quiz scheduling) and everything after. DB
access does not belong in a handler.

```python
def get_user(telegram_user_id: int) -> User | None
def is_registered(telegram_user_id: int) -> bool
def save_onboarding(telegram_user_id: int, data: dict) -> None   # the transaction above
def efset_to_cefr(score: int) -> str
```

Add `services/users.py` to `ARCHITECTURE.md` §3 as part of this slice, and log
the addition in the decisions log.

---

## Access control

`ARCHITECTURE.md` §7: the bot responds only to `telegram_user_id` values present
in `users`, plus `/start`. This is the entire access-control model for Phases
1–4, and it must land **before S2**, because S2 sends arbitrary user text to a
paid LLM.

- `/start` — always allowed, from anyone.
- `/ping` — keep allowed for anyone. It is a liveness check and leaks nothing.
- Everything else — if `is_registered()` is false, **ignore silently**. No
  reply, no error, no "you are not authorised". Log at INFO with the user id.

Implement as a shared check in `app/handlers/`, not copy-pasted per handler.

---

## Texts

Every string goes in `app/texts.py`. Copy rules from `PRD.md` §8:

- Under 400 characters per message
- One idea per message — do not stack the question and an explanation
- Warm and neutral. Never guilt, never pressure
- The why-statement question matters most: it is quoted back by the motivation
  engine in S10, so ask it in a way that gets a real answer, not one word

---

## Cursor verifies before handing back

Do not report this slice complete until you have run these yourself and pasted
the output.

1. **Migrations current** — `python -m app.db status` shows nothing pending.
2. **Automated persistence test.** Write `tests/test_onboarding.py` and run it
   against the local database on port 5433:
   - `efset_to_cefr` returns the correct level at every band boundary —
     1, 30, 31, 40, 41, 50, 51, 60, 61, 70, 71, 100
   - `save_onboarding` with a fake `telegram_user_id` creates exactly one
     `users` row with every field set as given, and `onboarded = TRUE`
   - it also creates exactly one `streaks` row with `freeze_tokens = 2`
   - calling `save_onboarding` **twice** leaves exactly one `users` row and one
     `streaks` row — this is the duplicate-prevention criterion
   - a redo does not reset `current_streak`: set it to 5, save again, assert
     it is still 5
   - the test cleans up its own rows afterwards
   This adds `pytest` to `requirements.txt`. S3 requires it anyway.
3. **Row inspection** — after the test, run
   `psql -p 5433 english_bot -c "SELECT count(*) FROM users;"` and confirm the
   test left nothing behind.
4. **No secrets in logs** — confirm no token or DSN password appears in output.

## Human verifies (Telegram only)

Everything above is Cursor's job. What is left needs a person:

1. `/start` → complete the conversation → **Save**. Check the summary matches
   what you entered.
2. `psql -p 5433 english_bot -c "SELECT name, native_language, cefr_level,
   efset_baseline, track_weights, morning_time FROM users;"` — values correct.
3. `/start` again → shows your profile with Redo / Keep as is → choose **Keep
   as is** → still exactly one row.
4. Send any other text (e.g. `hello`) from an account **not** in `users` → no
   reply at all.
5. Read the conversation as copy. Does it sound like something you would want to
   receive at 8am? This is the only criterion Cursor cannot judge.

## Definition of done

- All Cursor checks pass, output pasted
- All five human checks pass
- Both real users onboarded, two rows in `users`, two in `streaks`
- `ARCHITECTURE.md` §3 lists `services/users.py`
- `PRD.md` §3 EF SET target corrected (pending decision 1)
- `BUILD_PROGRESS.md` updated: slice row 🟡, file inventory, decisions log
  entries for all five open decisions as resolved, known issues, next action
- Committed and pushed
