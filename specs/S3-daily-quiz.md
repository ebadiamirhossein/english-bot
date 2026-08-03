# S3 · Daily quiz + scheduler (M1)

**Slice:** S3
**Phase:** 1 — Foundation
**Depends on:** S2 (code-complete; Telegram verify may still be pending)
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Goal

Deliver a morning quiz built from the user's due error journal rows, apply the
spacing ladder on each answer, and schedule delivery with one timezone-aware
poll job. This is the slice `ARCHITECTURE.md` §8 singles out: a silent bug in
the spacing ladder destroys the product's value without ever being visible.
Tests are mandatory.

---

## Non-goals

- No nudges, streak updates, freeze tokens, or rescue mode — S4.
- No evening task rotation.
- No book-unit top-up (S6). If fewer than 5 errors are due, send fewer questions.
- Do not modify `services/users.py`, `handlers/correction.py`, or any existing
  test file.

---

## Locked decisions

1. **One 5-minute poll job**, not one APScheduler job per user. Survives
   restarts, picks up newly onboarded users, implements PRD §7 rule 1
   (scheduled times are delivery times, not deadlines).
2. **Gap-fill is the default** question format — production beats recognition.
3. **Grading is a normalised string match** against `accept` — no second LLM
   call.
4. **Zero due errors** → short free-practice invite + `sessions` row with
   `task_type='free_practice'` (not `'quiz'`). Fake quiz rows would corrupt
   completion-rate / streak / 14-day usage signals.
5. **Morning selection** checks for **any** `sessions` row on the user's
   **local** today — otherwise a free-practice day still lets a quiz fire.
6. **Quiz-active state is derived from the database**, not `bot_data`: any
   incomplete `sessions` row with `task_type='quiz'` (progress in
   `sessions.payload` JSONB). Morning *selection* still keys on local today;
   answer routing deliberately ignores date so a restart or local-midnight
   crossover cannot send a typed answer into the correction handler.
7. **Bot-initiated message ceiling** uses table `bot_message_counts`
   `(user_id, local_date, count)`, incremented on every bot-initiated send.
   Counting sessions would under-count once S10 nudges exist (nudges are not
   sessions). Cap is 3 per PRD §7 rule 9.
8. **All date/time eligibility uses the user's local calendar** and minute
   precision for `morning_time`. Every eligibility function takes an explicit
   `now: datetime` (timezone-aware UTC) so tests never touch the wall clock.

---

## Migration `002_quiz_scheduler.sql`

```sql
ALTER TABLE sessions ADD COLUMN payload JSONB;

CREATE TABLE bot_message_counts (
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    local_date  DATE NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
    PRIMARY KEY (user_id, local_date)
);
```

---

## `app/services/errors.py` — extend, do not rewrite `record_errors`

```python
SPACING_DAYS: dict[int, int]  # 0→1, 1→3, 2→7, 3→21, 4→60

def due_errors(user_id: int, limit: int = 5) -> list[Error]
def mark_result(error_id: int, correct: bool) -> None
```

### `due_errors`

Rows where `resolved = FALSE` and `next_review <= CURRENT_DATE`, oldest
`next_review` first (then `id`), limit applied, scoped by `user_id`.

### `mark_result(correct=True)`

- `streak_right += 1`, `times_right += 1`
- If `streak_right >= 5` **and** `CURRENT_DATE - created_at::date >= 21`:
  `resolved = TRUE`, `resolved_at = CURRENT_DATE`
- Else: `next_review = CURRENT_DATE + SPACING_DAYS[min(streak_right, 4)]`
  (streak ≥5 but under 21 days old stays at +60)

### `mark_result(correct=False)`

- `streak_right = 0`, `times_wrong += 1`, `next_review = CURRENT_DATE + 1`
- If the row was resolved: `resolved = FALSE`, `resolved_at = NULL`,
  `unresolved_count += 1`

---

## `app/prompts/quiz.txt`

One LLM call per quiz, `json_mode=True`. Input: due error rows plus
`cefr_level`, `native_language`, `work_domain`.

Output contract:

```json
{
  "questions": [
    {
      "error_id": 12,
      "format": "gap",
      "prompt": "Her English ___ very good.",
      "accept": ["isn't", "is not", "isnt"],
      "answer": "isn't"
    },
    {
      "error_id": 15,
      "format": "choice",
      "prompt": "Which is correct?",
      "options": ["I agree with you", "I am agree with you"],
      "answer": "I agree with you"
    }
  ]
}
```

Rules in the prompt:

- One question per due error, in order. Never invent an `error_id`.
- Default format `gap`. Use `choice` only when a whole clause would make a gap
  ambiguous (~one in five).
- `accept`: every reasonable spelling/contraction, lowercase.
- NEW sentences in work domain or daily life — never repeat `you_said`.
- Each `prompt` under 100 characters.

---

## Grading

No LLM. Normalise both sides: lowercase, strip whitespace, strip trailing
punctuation, collapse internal spaces, normalise apostrophes (`'` and `'` →
`'`). Match against `accept`.

---

## `app/services/sessions.py`

```python
def local_today(timezone: str, now: datetime) -> date
def has_session_on(user_id: int, local_date: date) -> bool
def insert_session(...) -> int
def complete_session(session_id: int, score: float) -> None
def update_session_payload(session_id: int, payload: dict) -> None
def get_open_quiz_session(user_id: int, local_date: date) -> ... | None
def bot_initiated_count(user_id: int, local_date: date) -> int
def increment_bot_messages(user_id: int, local_date: date) -> int
```

---

## `app/handlers/quiz.py`

Single message, edited in place (reuse `layout_buttons` and BadRequest
"message is not modified" handling from onboarding).

Per question:

```
●○○○○

Her English ___ very good.
```

Gap → typed answer; choice → option buttons. After each answer, brief result
then next question. End: score + one line naming an improved error type.

Wrong feedback: "Not quite — it's X" + original explanation. Never guilt.

`mark_result` exactly once per answered question. Abandoned quiz leaves
remaining errors untouched.

**Active-quiz detection for the text filter:** incomplete `sessions` row with
`task_type='quiz'` for the user's local today (and load `payload` from that
row). Never `bot_data`.

Call `increment_bot_messages` on every bot-initiated send (quiz open message,
free-practice invite). In-quiz edits of the same message do not increment.

---

## `app/scheduler.py`

APScheduler in-process via PTB `JobQueue` (`python-telegram-bot[job-queue]`),
registered from `main.py` `post_init`. One shared queue — do not create a second
`AsyncIOScheduler`.

ONE job every 5 minutes:

1. Read onboarded users where `paused_until` is null or past (relative to
   the user's local date at `now`).
2. For each, compute local datetime in `users.timezone`.
3. If local time (hour:minute) `>= morning_time` **and** no sessions row for
   that user's local today **and** `bot_initiated_count < 3` → deliver.

On quiz delivery: insert `sessions` (`task_type='quiz'`, `delivered_at`,
`payload` with questions + message ids). On completion: `completed=TRUE`,
`completed_at`, `score`.

On zero due errors: free-practice invite + `task_type='free_practice'`,
`delivered_at` set, `completed=FALSE`. No `quiz` row.

Eligibility helpers take explicit `now: datetime` (aware UTC).

---

## Tests required

### `tests/test_spacing.py`

- Full correct ladder: four correct answers → next_review +3, +7, +21, +60
- Wrong at any rung → next_review +1, streak_right 0, times_wrong++
- streak_right 5 on row younger than 21 days does NOT resolve
- streak_right 5 on row 21+ days old DOES resolve + resolved_at
- Wrong on resolved row un-resolves + unresolved_count++
- due_errors: unresolved, next_review ≤ today, oldest first, limit, never
  another user's rows

### `tests/test_quiz.py`

- Grading normalisation matches accept variants
- Answer calls mark_result exactly once
- Abandon after Q2 leaves Q3–5 next_review unchanged
- Zero due errors → exactly one free_practice row, no quiz row, no second
  message on the next poll

### `tests/test_scheduler.py`

- Local time before morning_time → not selected
- Past morning_time, no session today → selected
- Same user not selected twice same local day
- Two users, different timezones, each at own local time
- Asia/Tokyo and Europe/Vilnius both morning_time 07:00: selected at their
  own local 07:00; neither selected twice across a simulated 24 hours of
  5-minute polls

---

## Acceptance (Telegram)

1. Record an error via free correction; force `next_review` to local today if
   needed.
2. Force morning delivery (see verification steps in BUILD_PROGRESS / handoff).
3. Quiz arrives as one editable message; gap/choice behave correctly.
4. Correct answer pushes spacing; wrong resets to +1.
5. Restart bot mid-quiz; typed answer still grades (does not become a
   correction).
6. With zero due errors, receive free-practice invite once; no quiz session
   row.

## Verify before handoff

1. `python -m pytest -q`
2. `python -m app.main` starts clean
3. `git diff --stat app/services/users.py app/handlers/correction.py` empty
