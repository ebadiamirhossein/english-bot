"""Every user-facing string in the product belongs in this module.

Handlers and services must import constants from here. Never write a
user-visible message inline in a handler or service.
"""

PONG = "pong"

# --- Onboarding -----------------------------------------------------------

ONBOARD_WELCOME = (
    "Hey — I'm your English practice partner. "
    "A few quick questions so I can set things up for you."
)

ONBOARD_ASK_NAME = "What should I call you?"

ONBOARD_ASK_NATIVE_LANG = "What's your native language?"

ONBOARD_ASK_NATIVE_LANG_OTHER = "Which language?"

ONBOARD_ASK_EFSET = (
    "What's your EF SET score? "
    "If you haven't taken it yet, tap Not yet — we can fill it in later."
)

ONBOARD_ASK_DOMAIN = "What do you work in?"

ONBOARD_ASK_WHY = (
    "Why do you want better English? "
    "One honest sentence — I'll bring it back when motivation dips."
)

ONBOARD_ASK_WEIGHTS = "What should we focus on?"

ONBOARD_ASK_MORNING = "When should the morning task arrive?"

ONBOARD_ASK_MORNING_OTHER = "What time? Use 24-hour HH:MM, like 07:30."

ONBOARD_ASK_EVENING = "And the evening task?"

ONBOARD_ASK_EVENING_OTHER = "What time? Use 24-hour HH:MM, like 20:30."

ONBOARD_CONFIRM_INTRO = "Does this look right?"

ONBOARD_SAVED = "You're set. I'll message you at the times you chose."

ONBOARD_CANCELLED = "Okay — nothing saved. Say /start whenever you're ready."

ONBOARD_KEEP = "Alright — leaving your profile as it is."

ONBOARD_REDO = "Okay, let's start over."

ONBOARD_SAVE_FAILED = (
    "Something broke on my side — try /start again in a moment."
)

ONBOARD_INVALID_NAME = "I need a name I can use — try again?"

ONBOARD_INVALID_EFSET = "Send a number from 1 to 100, or tap Not yet."

ONBOARD_INVALID_TIME = "That doesn't look like HH:MM. Try something like 08:00."

ONBOARD_INVALID_LANG = "Type the language name — any language is fine."

ONBOARD_PROFILE_INTRO = "You're already set up. Here's your profile:"

# Button labels
BTN_LANG_FARSI = "Farsi"
BTN_LANG_LITHUANIAN = "Lithuanian"
BTN_LANG_OTHER = "Other"
BTN_EFSET_NOT_YET = "Not yet"
BTN_WEIGHTS_BALANCED = "Balanced"
BTN_WEIGHTS_WORK = "More work English"
BTN_WEIGHTS_LIFE = "More everyday English"
BTN_TIME_OTHER = "Other"
BTN_SAVE = "Save"
BTN_START_OVER = "Start over"
BTN_REDO = "Redo onboarding"
BTN_KEEP = "Keep as is"

# Language display names for summaries
LANG_LABELS = {
    "fa": "Farsi",
    "lt": "Lithuanian",
}
