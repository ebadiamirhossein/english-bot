"""User-facing copy that `packages/core` services render themselves.

Only the strings a core service actually formats live here. Everything
else stays in `apps/bot/texts.py`, which re-exports these names, so every
handler call site and every `dir(texts)` no-guilt test is unchanged and
each string still has exactly one definition. A second copy of these
strings would be the drift this codebase has already been bitten by three
times (`spacing_step`, `approved_onboarded_users`,
`CHUNK_PRESENTED_AND_DUE_SQL`).

Deliberately narrow: W19 owns the wider copy refactor.
"""

# --- Access / admin panel (S18d) — core.services.admin_panel -------------------

ADMIN_TITLE = "Operator panel"

ADMIN_PENDING_LINE = "Pending requests: {n}"

ADMIN_PENDING_NONE = "No pending requests."

ADMIN_PENDING_ITEM = "{display} · id {telegram_id}"

ADMIN_EMPTY = "No onboarded users yet."

ADMIN_USER_LINE = (
    "{name} · {level} · streak {streak} · "
    "active {active}/{week} · last {last} · {paused}"
)

ADMIN_LAST_NEVER = "never"

ADMIN_PAUSED_YES = "paused"

ADMIN_PAUSED_NO = "active"

ADMIN_REVOKED_TAG = "revoked"

# --- Operator alerts (S18) — core.services.alerts ------------------------------

SOFT_UNHANDLED = "Something broke on my side — try that again in a moment."

# --- Anki export (S7 / M6) — core.services.anki --------------------------------

ANKI_WEEKLY = (
    "Your Anki pack for the week — {count} new card(s). "
    "Import the TSV into Anki when you're ready."
)

ANKI_MANUAL = (
    "Here's your Anki export — {count} new card(s). "
    "Import the TSV when you're ready."
)

ANKI_EMPTY = "Nothing new to export yet — keep reading and they'll show up here."

ANKI_SEND_FAILED = (
    "Something broke on my side sending the file — try /anki again in a moment."
)

# --- Level raise (S6) — core.services.calibration ------------------------------

LEVEL_RAISE = (
    "Your English is settling at {level} — I'll pitch things a step up from here."
)

# --- Nudges and Sunday report (S10 / M7) — core.services.motivation ------------

NUDGE_FIRST_QUIZ = (
    "Your quiz is still here whenever you have a few minutes."
)

NUDGE_FIRST_READING = (
    "Your reading is still here whenever you have a few minutes."
)

NUDGE_FIRST_DIARY = (
    "Tonight's diary is still open — about a minute whenever you like."
)

NUDGE_SECOND_QUIZ = (
    "No time for the full set? Just do 2 — it still counts."
)

NUDGE_SECOND_READING = (
    "No time for all five? Just do 2 questions — it still counts."
)

NUDGE_SECOND_DIARY = (
    "No time for a full minute? Even half a minute still counts."
)

NUDGE_SHORT_ACK = "Two questions whenever you're free — tap on the task above."

NUDGE_SHORT_DONE = "Nice — those two count. You're done for this one."

BTN_NUDGE_JUST_2 = "Just do 2"

SUNDAY_LEAD_QUIET = "Quiet this week: {labels}."

SUNDAY_LEAD_KEEPING = "You've been showing up — keep the thread going."

SUNDAY_ACTIVE_FULL = "{n} active days — full week."

SUNDAY_ACTIVE_SHORT = "{n} of {target} active days."

SUNDAY_SHORTFALL = "Room for a couple more next week."

SUNDAY_WHY = "{why}"

# --- /prep sheet (S14) — core.services.prep ------------------------------------

PREP_TITLE = "Prep: {topic}"

PREP_SECTION_CHUNKS = "Phrases"

PREP_SECTION_FRAMES = "Reply frames"

# --- Shadowing feedback (S16) — core.services.shadow ---------------------------

SHADOW_TIP_CLEAR = "That came through clearly."

SHADOW_TIP_PART = "Try this part again: {detail}"

SHADOW_TIP_AGAIN = "Try this part again — a few words didn't come through clearly."

# --- /stats (S12) — core.services.stats ----------------------------------------

STATS_HEADER = "Your snapshot"

STATS_LEVEL = "Level: {level}"

STATS_STREAK = "Streak: {streak} day(s) · freeze tokens: {freezes}"

STATS_ACTIVE = "{active_line}"

STATS_DUE = "Due errors: {n}"

STATS_RESOLVED = "Quiet types: {labels}"

STATS_RESOLVED_NONE = "Quiet types: none yet"

STATS_CHUNKS = "Chunks: {total} · due: {due} · unexported: {unexported}"

STATS_BOOKS = "Book units stored: {n}"

STATS_CALIBRATION = "Calibration: {accuracy} · last change: {change}"

STATS_CALIBRATION_NONE = "Calibration: not enough recent evidence yet"

STATS_OPERATOR_SWEEP = "Sweep (ops): pending {pending} · done {done}"

# --- Vocabulary CSV import (S24a) — core.services.vocab_import -----------------

IMPORT_DOC_RESULT = (
    "Import done.\n"
    "Imported: {imported} · already had: {duplicates} · skipped: {invalid}\n"
    "Due for review now: {due}"
)

IMPORT_DOC_VOCAB_SKIPS = (
    "Couldn't use these words:\n{lines}"
)

IMPORT_DOC_VOCAB_SKIPS_MORE = "• and {n} more"

def format_shadow_feedback(
    target: str, attempt: str, tip: str
) -> str:
    """Fixed scannable shape for shadow compare (ASR intelligibility)."""
    return "\n".join(
        [
            f"🎯 {target}",
            f"🎤 {attempt}",
            f"💡 {tip}",
        ]
    )
