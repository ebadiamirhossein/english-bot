# S4 · Streaks, freeze tokens, rescue mode

**Slice:** S4
**Phase:** 1 — Foundation (last slice)
**Depends on:** S3d
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Goal

Implement PRD §7 rules 5–7 exactly: freeze tokens, streak rollover at 03:00
local, and rescue mode (3-question quiz, no backlog). ARCHITECTURE §8 names
`services/streaks.py` as one of two places where a silent bug destroys the
product without being visible. Tests are mandatory.

---

## Non-goals

- No nudges, Sunday report, or weekly-success calculation — S10.
- No evening task rotation.
- Do not modify `services/errors.py` or `services/users.py`.
- Do not change any existing test.
- The only permitted change to `handlers/correction.py` is completing an open
  `free_practice` session when a correction is processed.
- Do not start S4b.

---

## Locked decisions

1. **03:00 local rollover, never UTC midnight.** PRD §7 rule 1: scheduled times
   are delivery times; Monday's quiz stays open until 03:00 Tuesday. Evaluating
   too early breaks streaks for days the user actually completed.
2. **No early `roll_over_day` on quiz complete.** Completion must not advance
   `last_evaluated_date`. Show `current_streak + 1` optimistically in the
   completion message; the 03:00 job is the only real evaluation.
3. **Idempotency via `last_evaluated_date`.** Running `roll_over_day` twice for
   the same day changes nothing the second time.
4. **Backfill cap 30 days.** If `last_evaluated_date` is null or older than
   30 days before the closed-through day, start from `closed_through - 29` and
   set `last_evaluated_date` accordingly; log a warning when the cap is hit.
   Cap users processed per poll tick so one backfill cannot starve others.
5. **Freeze-covered missed days still count toward rescue.** A freeze protects
   the streak number; it does not mean the person engaged.
6. **No-session days are Neutral** — do not break the streak for a day the bot
   never asked about.
7. **free_practice:** Active only if the user sent at least one message the
   correction handler processed that day (marks the open free_practice session
   `completed = TRUE`). Otherwise Neutral. Never consumes a freeze.
   Rollover needs no free_practice special case beyond task_type on incomplete
   rows.
8. **Monthly freeze reset is per-user local date.** Iterate users; reset only
   when that user's local date is the 1st and `freeze_reset_on` is not already
   that date. Unused tokens do not carry over.
9. **Rescue runs its full 7 days.** Completing a day during rescue does not
   clear `rescue_mode_until` early.
10. **Copy:** warm/neutral, never guilt. Never explain rescue as a consequence.

---

## Rollover outcomes for day D

| Session state | Outcome |
|---|---|
| `completed = TRUE` (any `task_type`) | **Active** |
| `completed = FALSE` and `task_type = 'quiz'` | **Missed** |
| `completed = FALSE` and `task_type = 'free_practice'` | **Neutral** |
| No session | **Neutral** |

- **Active:** `current_streak += 1`, `total_active_days += 1`,
  `last_active_date = D`, `longest_streak = max(longest_streak, current_streak)`.
- **Missed:** if `freeze_tokens > 0`: decrement token, streak unchanged,
  `last_active_date` unchanged, set `pending_freeze_notice`. If tokens = 0:
  `current_streak = 0`. Count toward consecutive miss / rescue.
- **Neutral:** change nothing (except advance `last_evaluated_date`).

At 3+ consecutive missed days ending at D: `rescue_mode_until = D + 7 days`.

---

## Migration `003_streaks.sql`

```sql
ALTER TABLE streaks
    ADD COLUMN last_evaluated_date DATE,
    ADD COLUMN freeze_reset_on DATE,
    ADD COLUMN pending_freeze_notice BOOLEAN NOT NULL DEFAULT FALSE;
```

---

## `app/services/streaks.py`

```python
def roll_over_day(user_id: int, day: date) -> StreakResult
def is_in_rescue(user_id: int, day: date) -> bool
def reset_monthly_freezes(*, now: datetime) -> int  # rows updated
def get_streak(user_id: int) -> Streak
def evaluate_pending(user_id: int, *, timezone: str, now: datetime) -> list[StreakResult]
def consume_freeze_notice(user_id: int) -> str | None
```

Every time-sensitive function takes an explicit timezone-aware `now`.

---

## Scheduler

Same JobQueue as S3. Add two jobs (do not create a second scheduler):

1. `streak_rollover` — every 15 minutes; call `evaluate_pending` per user
   (user cap per tick).
2. `monthly_freeze_reset` — every 15 minutes; `reset_monthly_freezes(now=...)`.

Reuse `local_today` / `local_time_hhmm` from S3.

---

## Quiz / copy

- Rescue: `due_errors(..., limit=3)`; quiz opens with
  "Shorter one today — three questions."
- Completion: optimistic streak line `🔥 {n}-day streak` with `current_streak+1`
  when today's session is completed but not yet evaluated.
- Freeze notice on next quiz open (not at miss time):
  "Yesterday got away from you — I used a freeze, your streak's intact.
  One left this month." (parameterize remaining tokens).
- All copy in `app/texts.py`.

---

## Correction hook (only change to correction.py)

When `_handle_model_result` runs successfully, if an open `free_practice`
session exists for the user's local today, mark it `completed = TRUE`.

---

## Acceptance

1. Simulate 1 missed day → freeze consumed, streak intact.
2. Simulate 3 missed days → `rescue_mode_until` set, next quiz has 3 questions,
   no backlog.
3. `python -m pytest -q` — existing 63 + new tests green.
4. Startup log lists morning poll + both new jobs.
5. `git diff --stat` on `errors.py` / `users.py` empty; `correction.py` only
   the free_practice complete call.

---

## Tests required

### `tests/test_streaks.py`

- completed day increments streak, total_active_days, last_active_date
- longest_streak updates only when current exceeds it
- missed with tokens: token consumed, streak unchanged
- missed without tokens: streak resets to 0
- no session: Neutral
- `roll_over_day` idempotent
- 3 consecutive misses → rescue_mode_until = D + 7
- freeze-covered miss still counts toward rescue
- completing during rescue does not clear rescue_mode_until
- offline 7 days: all 7 evaluated in order with correct final streak/tokens
- monthly reset sets tokens to 2 and is idempotent
- unused tokens do not carry over
- Tokyo vs Vilnius each reset on their own local 1st, neither twice
- free_practice + correction → Active; + no messages → Neutral; never freezes
- completing a quiz does **not** change `last_evaluated_date`

### `tests/test_rescue_quiz.py`

- rescue → 3-question quiz; non-rescue → 5
- rescue never returns more than 3 due errors
