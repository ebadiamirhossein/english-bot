# Claude Code — W1 · Python restructure

**Run in: AGENT MODE.**
**Scope: move files and rewire imports. Nothing else.**

The W0 plan is approved. This slice executes its §5 move plan and nothing beyond it.

---

## The one rule for this slice

**W1 changes no behaviour.** Every file that needs an edit gets that edit in a **separate commit** from its `git mv`. A slice that moves and refactors at once cannot tell a move bug from a refactor bug, and the 335 pure-port tests are this migration's only proof that the ~40 encoded fixes survived.

**W1 deletes nothing.** `app/handlers/*` stay alive under `apps/bot` through W21 and are deleted in W22 with their ~209 tests. This is the only reading under which the acceptance bar below is meetable.

Use `git mv` for every move. `git log --follow` on the moved files is a hard acceptance criterion — copy-paste destroys the blame trail on exactly the fixes the extend-don't-rewrite decision was built on.

---

## Commit sequence — follow this order exactly

### Commit 1 — package skeleton

Create `packages/core/pyproject.toml` declaring the package name **`core`**, so imports read `from core.services.errors import mark_result`. Add `packages/core/__init__.py` and `packages/core/services/__init__.py`. Do not move anything yet.

### Commit 2 — bulk `git mv`, no edits

Per W0 §5.2:

- `app/services/{errors,streaks,sessions,chunks,users,calibration,interests,books,reading,capture,prep,shadow,access_control,admin_panel,stats,heartbeat,paths,backup_freshness,shared_content,watch_import,vocab_import}.py` → `packages/core/services/`
- `app/{db,llm,speech,instance_lock}.py` → `packages/core/`
- `app/prompts/{book_ocr,book_quiz,capture,conversation,conversation_close,correction,diary,prep,quiz,reading,vocab_sentences,voice}.txt` → `packages/core/prompts/` — **zero content edits, not one character**
- `app/services/couple.py` → `apps/bot/services/couple.py`
- `app/handlers/couple.py` → `apps/bot/handlers/couple.py`
- `app/prompts/couple.txt` → `apps/bot/prompts/couple.txt`
- `app/services/commands.py` → `apps/bot/commands.py`
- every remaining `app/handlers/*.py` → `apps/bot/handlers/` **(moved, not deleted)**
- `app/texts.py` → `apps/bot/texts.py`
- `app/main.py` → `apps/bot/main.py`

### Commit 3 — mechanical import rewrite

`app.services.X` → `core.services.X`; `app.{db,llm,speech,config,instance_lock}` → `core.{…}`; `app.texts` → `apps.bot.texts` inside the bot.

Ten services currently import `app.texts` for a handful of strings (`calibration.LEVEL_RAISE`, plus labels in `prep`, `stats`, `shadow`, `admin_panel`, `vocab_import`). Create `packages/core/copy.py` holding **only those strings**, and point those services at it. Do not attempt a wider copy refactor — that is W19's job.

Rewire `tests/` the same way. `tests/conftest.py` keeps its `ANTHROPIC_API_KEY` default and gains a `TELEGRAM_BOT_TOKEN` default.

`pip install -e packages/core`, then run the suite. **Stop here and report if it is not 714.**

### Commit 4 — the five behaviour edits, one commit, listed explicitly

Each is minimal and named in W0 §5.2. Nothing else in these files changes.

1. `core/config.py` — drop `TELEGRAM_BOT_TOKEN` from `_REQUIRED_KEYS`. Keep the field on `Settings`; make it required only where `apps/bot` reads it. The API and worker must boot without a bot token.
2. `core/db.py` — repoint `MIGRATIONS_DIR` to the repo-root `migrations/`.
3. `core/services/anki.py` — delete `deliver_weekly` and `handle_anki_command`; remove the `telegram` imports. `make_sentence_with_gap`, `build_tsv`, `row_fields`, `sanitize_tsv_field`, `fetch_unexported_chunks`, `export_and_send` stay exactly as they are.
4. `core/services/alerts.py` — delete `on_error`; change `notify_operator` to take `send: Callable[[str], Awaitable[None]]` instead of reading `app.bot`. `should_send_alert` and `format_alert` are untouched.
5. `core/services/motivation.py` — remove the `telegram` imports. `nudge_keyboard` and the second element of `format_nudge_message`'s tuple become a channel-neutral action descriptor (`{"action": "short_session", "session_id": n}`); `apps/bot` renders it as a keyboard. `send_nudge`, `deliver_nudges_for_user`, `run_nudge_pass`, `deliver_sunday_report`, `run_sunday_report_pass` move to `apps/bot` for now — the worker takes them at W20. **The pure functions do not change**: `task_still_open`, `next_nudge_due_at`, `list_motivation_users`, `is_user_paused`, `sessions_due_for_nudge`, `format_active_days_line`, `assemble_sunday_report`, `is_user_due_for_sunday_report`.

Update `apps/bot` call sites to match. Run the suite again — still 714.

### Commit 5 — extractions that are pure lifts

Two only. Both are copy-out-unchanged, not rewrites:

- `apps/bot/main.py::_configure_logging` → `packages/core/logging.py` (rotating file handler, httpx/apscheduler silencing). The bot calls it from its new home.
- The scheduling **predicates** from `apps/bot/scheduler.py` → `packages/core/scheduling.py`: `list_candidate_users`, `is_user_due_for_morning/evening/diary/anki`, `_time_reached`, `run_streak_rollover`, `run_monthly_freeze_reset`, `run_monthly_reset`. The APScheduler wiring and the handler-calling job bodies **stay in `apps/bot/scheduler.py`** for this slice; the worker takes them at W1b.

### Commit 6 — the three boundary tests

`tests/test_core_boundary.py`, all AST-based, not grep:

1. **`test_core_imports_no_web_framework`** — no module under `packages/core` imports `fastapi`, `starlette`, `telegram`, `uvicorn`, `httpx`, `requests`, or `aiohttp`. AST-based so a docstring containing "telegram" passes and `import telegram.ext as x` fails.
2. **`test_no_provider_sdk_outside_wrapper`** — `anthropic`, `openai`, `elevenlabs` and any `azure*` module may be imported by `core/llm.py` and `core/speech.py` only.
3. **`test_no_sql_outside_services`** — no `SELECT`/`INSERT`/`UPDATE`/`DELETE` string literal outside `core/services/` and `migrations/`. This one will have no violations yet; it exists so W3 onward cannot introduce one.

Also add, per W0 §3.5 item 2: one test asserting `apps/bot`'s scheduler registers its jobs **by name and trigger**, not just that the predicates work. Today five scheduler tests pass without any job being registered at all.

---

## Acceptance

```
pip install -e packages/core
pytest -q                       # 714 passing
pytest tests/test_core_boundary.py
python -m core.db status        # migrations found at repo root
python -m apps.bot.main         # starts, holds the instance lock
                                # second start refuses
git log --follow packages/core/services/errors.py   # full v2 history
```

`git log --follow` on `errors.py`, `streaks.py`, `llm.py` and `chunks.py` must show pre-migration commits. If it shows one commit, the move was a copy and this slice must be redone.

---

## Out of scope — do not do any of this in W1

- No FastAPI app, no routes, no `apps/api` beyond an empty directory
- No Next.js, no `apps/web`
- No worker process
- No migration, no schema change, no SQL
- **No prompt content edits.** `quiz.txt` keeps its work-first topic list and its `{work_domain}` injection until W5 rewrites it deliberately
- No deletions of handlers, tests, or `texts.py` strings
- No copy/`texts.py` refactor beyond the narrow `core/copy.py` extraction in commit 3
- No fixes to any open known issue, including #45, #46, #50 and #52 — each has an assigned slice

If something in this list looks necessary to make the slice work, stop and say so rather than widening scope.

---

## BUILD_PROGRESS.md update block

At the end of the slice, update `BUILD_PROGRESS.md`:

- **Slice row:** `| W1 | Python restructure | 🟡 code-complete | <date> | git mv + core package + boundary tests; 714 green; nothing deleted |`
- **Decisions log:** every decision taken during the move with its reason — in particular anything you had to resolve that the W0 plan did not specify, and any file where the mechanical import rewrite was not mechanical.
- **Known issues:** any new issue found during the move. Carry forward every open issue unchanged, including the W0 additions #46–#57 and the still-open v2 set (#6, #20, #27, #28, #29, #31, #32, #44, #45).
- **File inventory:** the new tree — `packages/core/*`, `packages/core/pyproject.toml`, `packages/core/copy.py`, `packages/core/logging.py`, `packages/core/scheduling.py`, `apps/bot/*`, `tests/test_core_boundary.py`. Mark moved files as moved, not new.
- **Next action:** W1's human checks — the bot still starts on Hetzner and answers, the instance lock still refuses a second start, `python -m core.db status` reports version 8 — **plus every earlier unrun check carried forward from the v2 verification list**, unchanged. A restructure clears none of them.

Then stop. Do not begin W1b.
