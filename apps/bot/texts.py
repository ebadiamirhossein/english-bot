"""Every user-facing string the Telegram bot can still send.

Handlers must import constants from here. Never write a user-visible message
inline in a handler or service.

**W22: 411 names became 17** (367 defined here, the rest re-exported). Everything else in this module belonged to a
handler that was deleted with the Telegram teaching path, and the re-exports
from ``core.copy`` went with them — ``core.copy`` is walked by the no-guilt test
directly (``tests/test_no_guilt_all_copy.py``), so nothing loses coverage.
"""

PONG = "pong"

# --- S18b: Telegram command menu descriptions (outcome-first, lowercase start) ---
# W22: `/start` no longer onboards (`/start` and `/help` give the same reply),
# so its description was "set up or change your profile" and is not any more.
CMD_DESC_START = "what this bot does now"
CMD_DESC_HELP = "see what i can do"

# --- W22: the whole `/start` and `/help` reply ---
# Conditional on purpose: the couple challenge has never been set up on
# production (#29 — no shared group, `COUPLE_CHAT_ID` unset), and a reply that
# promised an 18:00 question would be promising one that does not come.
HELP_AFTER_W22 = (
    "Your practice lives in the app now — the daily session, talking, "
    "writing, your cards and your progress are all there.\n\n"
    "Here in Telegram there's the couple challenge: once it's set up in a "
    "group chat you share, a question arrives there each evening and the "
    "week's points come on Sunday."
)

# --- S8: couple challenge ---
COUPLE_QUESTION = "Tonight's challenge\n\n{question}"
COUPLE_TRY_AGAIN = "Not quite — have another go."
COUPLE_ALREADY_CLAIMED = "Already taken — nice try though."
COUPLE_WIN = "Point to {name}!"
COUPLE_HERE_SET = (
    "This chat's id is {chat_id}.\n"
    "Put COUPLE_CHAT_ID={chat_id} in .env and restart the bot."
)
COUPLE_HERE_ALREADY = "This chat is already the couple challenge home."
COUPLE_HERE_PRIVATE = "Run /here in your shared group chat."
COUPLE_LEADERBOARD_HEADER = "This week's challenge"
COUPLE_LEADERBOARD_SCORE = "{name}: {points}"
COUPLE_LEADERBOARD_AHEAD = "{name} is ahead this week."
COUPLE_LEADERBOARD_TIE = "You're level — nice week."
COUPLE_LEADERBOARD_STAKE = "Stake is whatever you two agreed."

# --- the error handler's reply (apps/bot/alerts.py) ---
SOFT_UNHANDLED = "Something broke on my side — try that again in a moment."
