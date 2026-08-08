"""Every user-facing string in the product belongs in this module.

Handlers and services must import constants from here. Never write a
user-visible message inline in a handler or service.
"""

PONG = "pong"

# --- Onboarding (S1b/S1c + S1d personality) --------------------------------

ONBOARD_GREETING = (
    "Hi {name} 👋\n\n"
    "I'm going to learn your mistakes and keep testing you on them until they're "
    "gone. Eight quick questions first.\n\n"
    "Should I call you {name}?"
)

ONBOARD_ASK_NAME = "What should I call you?"

ONBOARD_ASK_NATIVE_LANG = "What's your first language?"

ONBOARD_ASK_NATIVE_LANG_OTHER = "Which language?"

ONBOARD_ASK_EFSET = "Do you know your EF SET score?"

ONBOARD_ASK_EFSET_HELPER = "It's a free 50-minute test — we can do this later."

ONBOARD_ASK_EFSET_SCORE = "What's your EF SET score? (1–100)"

ONBOARD_ASK_LEVEL = "Roughly where are you in English?"

ONBOARD_ASK_DOMAIN = "What do you do all day?"

ONBOARD_ASK_DOMAIN_SPECIFIC = "Which fits best?"

ONBOARD_ASK_DOMAIN_OTHER = "What do you work in? Be as specific as you like."

ONBOARD_ASK_WHY = "Why does this matter to you?"

ONBOARD_ASK_WHY_HELPER = "Pick as many as you like."

ONBOARD_WHY_NUDGE = "Pick at least one, then tap Done."

ONBOARD_ASK_WEIGHTS = "Where should I aim the practice?"

ONBOARD_ASK_MORNING = "When should the morning task arrive?"

ONBOARD_ASK_MORNING_OTHER = "What time? Use 24-hour HH:MM, like 07:30."

ONBOARD_ASK_EVENING = "When should the evening task arrive?"

ONBOARD_ASK_EVENING_OTHER = "What time? Use 24-hour HH:MM, like 20:30."

ONBOARD_CONFIRM_INTRO = "Right — here's the plan."

ONBOARD_SAVED = "You're set, {name}. First task lands tomorrow at {morning_time}."

ONBOARD_SAVED_EFSET_NUDGE = (
    "You're set, {name}.\n"
    "First task lands tomorrow at {morning_time}.\n\n"
    "When you have 50 minutes, take the free EF SET — I'll tune everything to your "
    "real level. Just send me the score."
)

ONBOARD_CANCELLED = "Okay — nothing saved. Say /start whenever you're ready."

ONBOARD_KEEP = "Alright — leaving your profile as it is."

ONBOARD_SAVE_FAILED = (
    "Something broke on my side — try /start again in a moment."
)

ONBOARD_INVALID_NAME = "I need a name I can use — try again?"

ONBOARD_INVALID_EFSET = "Send a number from 1 to 100, or go back and tap Not yet."

ONBOARD_INVALID_TIME = "That doesn't look like HH:MM. Try something like 08:00."

ONBOARD_INVALID_LANG = "Type the language name — any language is fine."

ONBOARD_PROFILE_INTRO = "You're already set up. Here's your profile."

# Button labels (emoji leading; layout helper enforces ≤12 for shared rows)
BTN_NAME_YES = "👍 Yes, that's me"
BTN_NAME_OTHER = "✏️ Call me something else"
BTN_LANG_FARSI = "🇮🇷 Farsi"
BTN_LANG_LITHUANIAN = "🇱🇹 Lithuanian"
BTN_LANG_RUSSIAN = "🇷🇺 Russian"
BTN_LANG_POLISH = "🇵🇱 Polish"
BTN_LANG_OTHER = "🌍 Other"
BTN_EFSET_KNOW = "📊 I know my score"
BTN_EFSET_NOT_YET = "🤷 Not yet"
BTN_LEVEL_A2 = "🌱 I manage simple, everyday things"
BTN_LEVEL_B1 = "🚶 I get by, but I hesitate a lot"
BTN_LEVEL_B2 = "🏃 I'm comfortable — I want precision"
BTN_DOMAIN_OTHER = "✏️ Something else"
BTN_WHY_DONE = "Done →"
BTN_WEIGHTS_BALANCED = "⚖️ A bit of everything"
BTN_WEIGHTS_WORK = "💼 Mostly work English"
BTN_WEIGHTS_LIFE = "🏠 Mostly everyday English"
BTN_TIME_OTHER = "🕐 Another time"
BTN_MORNING_07 = "🌅 07:00"
BTN_MORNING_08 = "☀️ 08:00"
BTN_MORNING_09 = "🌤 09:00"
BTN_EVENING_19 = "🌆 19:00"
BTN_EVENING_20 = "🌙 20:00"
BTN_EVENING_21 = "🌃 21:00"
BTN_BACK = "← Back"
BTN_SAVE = "🚀 Start learning"
BTN_CHANGE = "✏️ Change something"
BTN_KEEP = "Keep as is"

# Self-assessment after EF SET "Not yet" → cefr_level (efset_baseline stays NULL)
SELF_ASSESS_OPTIONS: list[tuple[str, str, str]] = [
    ("a2", BTN_LEVEL_A2, "A2"),
    ("b1", BTN_LEVEL_B1, "B1"),
    ("b2", BTN_LEVEL_B2, "B2"),
]

# Domain categories — short labels so two fit per row; specifics carry detail.
DOMAIN_CATEGORIES: list[tuple[str, str]] = [
    ("marketing", "📣 Marketing"),
    ("tech", "💻 Tech"),
    ("business", "📊 Business"),
    ("health", "🩺 Health"),
    ("education", "🎓 Education"),
    ("creative", "🎨 Creative"),
    ("trades", "🔧 Trades"),
    ("law", "⚖️ Law"),
    ("other", "🧭 Other"),
]

# Stored work_domain is the specific label, lowercased (unchanged from S1c).
DOMAIN_SPECIFICS: dict[str, list[tuple[str, str]]] = {
    "marketing": [
        ("digital_marketing", "Digital marketing"),
        ("content_social", "Content & social"),
        ("sales", "Sales"),
        ("brand_pr", "Brand & PR"),
        ("market_research", "Market research"),
    ],
    "tech": [
        ("software_eng", "Software engineering"),
        ("data_ai", "Data & AI"),
        ("it_infra", "IT & infrastructure"),
        ("product_mgmt", "Product management"),
        ("qa_testing", "QA & testing"),
        ("design_ux", "Design (UX/UI)"),
    ],
    "business": [
        ("finance_acct", "Finance & accounting"),
        ("operations", "Operations"),
        ("hr_recruiting", "HR & recruiting"),
        ("consulting", "Consulting"),
        ("logistics", "Logistics"),
        ("entrepreneur", "Entrepreneur"),
    ],
    "health": [
        ("medicine", "Medicine"),
        ("nursing", "Nursing"),
        ("dentistry", "Dentistry"),
        ("pharmacy", "Pharmacy"),
        ("therapy", "Therapy & rehab"),
        ("care_work", "Care work"),
    ],
    "education": [
        ("teaching", "Teaching"),
        ("academic", "Academic research"),
        ("training", "Training & coaching"),
        ("edu_admin", "Education admin"),
    ],
    "creative": [
        ("design", "Design"),
        ("writing", "Writing & editing"),
        ("film_video", "Film & video"),
        ("music", "Music"),
        ("photography", "Photography"),
    ],
    "trades": [
        ("construction", "Construction"),
        ("automotive", "Automotive"),
        ("hospitality", "Hospitality"),
        ("retail", "Retail"),
        ("beauty", "Beauty"),
        ("driving", "Driving & transport"),
    ],
    "law": [
        ("law", "Law"),
        ("government", "Government"),
        ("nonprofit", "Non-profit"),
        ("police", "Police & emergency"),
    ],
    "other": [
        ("student", "Student"),
        ("between_jobs", "Between jobs"),
        ("parenting", "Parenting full-time"),
        ("retired", "Retired"),
    ],
}

# Why multi-select: key → (button label without checkmark, sentence clause)
WHY_OPTIONS: list[tuple[str, str, str]] = [
    ("freeze", "😰 Speak without freezing up", "speak without freezing up"),
    ("meetings", "💼 Do better in meetings", "do better in meetings"),
    ("job", "🚀 Get a better job", "get a better job"),
    ("friends", "🫂 Make friends here", "make friends here"),
    ("films", "🎬 Watch films without subtitles", "watch films without subtitles"),
    (
        "embarrassed",
        "😳 Stop feeling embarrassed",
        "stop feeling embarrassed about my English",
    ),
    ("travel", "✈️ Travel more easily", "travel more easily"),
    ("study", "🎓 Study or pass an exam", "study or pass an exam"),
]

# Language display names for summaries (no emoji)
LANG_LABELS = {
    "fa": "Farsi",
    "lt": "Lithuanian",
    "ru": "Russian",
    "pl": "Polish",
}

WEIGHT_SUMMARY_LABELS = {
    "balanced": "Balanced",
    "work": "More work",
    "life": "More everyday",
}

# --- Reactions (one line, <60 chars, every option keyed) -------------------
# Keys must cover every choice; tests fail if any option key is missing.

REACTIONS: dict[str, str] = {
    # Step 1
    "name:yes": "Good — we'll stick with that.",
    "name:other": "Got it — tell me what to call you.",
    "name:typed": "Nice to meet you.",
    # Step 2
    "lang:fa": "Farsi — articles and word order are our battleground.",
    "lang:lt": "Lithuanian — so articles will be the fun part.",
    "lang:ru": "Russian base — English articles will keep us busy.",
    "lang:pl": "Polish — you know cases; articles are the new puzzle.",
    "lang:other": "Any language works — I'll adapt explanations when needed.",
    "lang:typed": "Noted — I'll keep that in mind for explanations.",
    # Step 3
    "efset:know": "Paste the number when you have it.",
    "efset:skip": "No problem. Rough guess is fine for now.",
    "efset_score:A1": "A1 start. We'll build steadily from the ground.",
    "efset_score:A2": "A2 — everyday basics are there; next is fluency.",
    "efset_score:B1": "Solid B1. That's exactly the jump this is built for.",
    "efset_score:B2": "B2 already. Then we're sharpening, not building.",
    "efset_score:C1": "C1 territory — precision and polish from here.",
    "efset_score:C2": "C2 — rare. We'll chase the last stubborn habits.",
    # Step 3b
    "level:a2": "Everyday basics — we'll grow from there.",
    "level:b1": "Hesitation is normal at B1. We'll chip away at it.",
    "level:b2": "Comfortable base — now we hunt precision.",
    # Step 4 categories
    "domain:cat:marketing": "Marketing world — campaigns and clients ahead.",
    "domain:cat:tech": "Tech it is — standups and specs incoming.",
    "domain:cat:business": "Business side — meetings and numbers.",
    "domain:cat:health": "Care work — high-stakes talk every day.",
    "domain:cat:education": "Education — clear explanations matter here.",
    "domain:cat:creative": "Creative field — voice and style count.",
    "domain:cat:trades": "Hands-on work — practical English first.",
    "domain:cat:law": "Law & public — precision is non-negotiable.",
    "domain:cat:other": "Outside a single field — we'll keep it flexible.",
    # Step 4b named specifics (required) + rest
    "domain:pick:digital_marketing": "Campaigns, clients, pitches. I'll pull examples from there.",
    "domain:pick:content_social": "Content and social — hooks and captions.",
    "domain:pick:sales": "Sales talk — persuasion under pressure.",
    "domain:pick:brand_pr": "Brand and PR — careful wording.",
    "domain:pick:market_research": "Research — clear findings, clear English.",
    "domain:pick:software_eng": "Standups, code review, specs. Noted.",
    "domain:pick:data_ai": "Data and AI — precise terms matter.",
    "domain:pick:it_infra": "Infra — tickets, outages, clear status.",
    "domain:pick:product_mgmt": "Product — roadmaps and stakeholder talk.",
    "domain:pick:qa_testing": "QA — bugs need clear reports.",
    "domain:pick:design_ux": "UX/UI — critique without friction.",
    "domain:pick:finance_acct": "Finance — numbers with clean English.",
    "domain:pick:operations": "Ops — processes said simply.",
    "domain:pick:hr_recruiting": "HR — interviews and sensitive talk.",
    "domain:pick:consulting": "Consulting — slides and client rooms.",
    "domain:pick:logistics": "Logistics — status updates that land.",
    "domain:pick:entrepreneur": "Building something — pitches and hustle.",
    "domain:pick:medicine": "Medicine — clarity under pressure.",
    "domain:pick:nursing": "Handovers and patient talk. That's a demanding register.",
    "domain:pick:dentistry": "Dentistry — calm chairside talk.",
    "domain:pick:pharmacy": "Pharmacy — instructions people follow.",
    "domain:pick:therapy": "Therapy — careful, human language.",
    "domain:pick:care_work": "Care work — warmth plus clarity.",
    "domain:pick:teaching": "Teaching — explain, then check understanding.",
    "domain:pick:academic": "Research — abstracts and argument.",
    "domain:pick:training": "Training — instructions that stick.",
    "domain:pick:edu_admin": "Edu admin — email that doesn't spiral.",
    "domain:pick:design": "Design — feedback that's useful.",
    "domain:pick:writing": "Writing — edit until it breathes.",
    "domain:pick:film_video": "Film and video — scripts and notes.",
    "domain:pick:music": "Music — gigs, briefs, collaboration.",
    "domain:pick:photography": "Photography — clients and shoots.",
    "domain:pick:construction": "Construction — site talk that works.",
    "domain:pick:automotive": "Automotive — diagnosis said clearly.",
    "domain:pick:hospitality": "Hospitality — guests and rush hour.",
    "domain:pick:retail": "Retail — customers, returns, calm.",
    "domain:pick:beauty": "Beauty — consults and aftercare.",
    "domain:pick:driving": "Transport — routes and radio English.",
    "domain:pick:law": "Law — every word earns its place.",
    "domain:pick:government": "Government — formal and careful.",
    "domain:pick:nonprofit": "Non-profit — mission without fluff.",
    "domain:pick:police": "Emergency work — short and clear.",
    "domain:pick:student": "Student life — essays and seminars.",
    "domain:pick:between_jobs": "Between roles — interviews upcoming.",
    "domain:pick:parenting": "Full-time parenting — real-life English.",
    "domain:pick:retired": "Retired — keep the mind sharp.",
    "domain:other": "Specific is better — I'll use what you type.",
    "domain:typed": "Specific beats generic — thanks.",
    # Step 5
    "why:freeze": "That's the one that changes everything.",
    "why:meetings": "Meetings are where B1 becomes B2.",
    "why:job": "Then we'll spend real time on interviews.",
    "why:friends": "Small talk is harder than any grammar. We'll work on it.",
    "why:films": "Good one — HIMYM's already on the plan.",
    "why:embarrassed": "That feeling fades with reps. We'll get you there.",
    "why:travel": "Travel English — practical and forgiving.",
    "why:study": "Exams reward precision — we'll train for that.",
    "why:done": "Those reasons stay on the wall. Let's aim practice.",
    # Step 6
    "weights:balanced": "Balanced mix — work, life, curiosity.",
    "weights:work": "Work-heavy it is.",
    "weights:life": "Everyday English front and centre.",
    # Steps 7–8
    "morning:07:00": "Early start. Respect.",
    "morning:08:00": "Classic morning slot.",
    "morning:09:00": "Gentle morning — still on time.",
    "morning:other": "Your clock — tell me the time.",
    "morning:typed": "Morning slot locked.",
    "evening:19:00": "Early evening — good for a short task.",
    "evening:20:00": "Evening practice — solid habit time.",
    "evening:21:00": "Night owl. Noted.",
    "evening:other": "Your evening — name the time.",
    "evening:typed": "Evening slot locked.",
}

# Every choosable option key that must have a reaction (for coverage tests).
REACTION_OPTION_KEYS: frozenset[str] = frozenset(REACTIONS.keys())

# --- Free correction (S2) ---------------------------------------------------

TEXT_TOO_LONG = (
    "That's a bit long for one pass — send something under 1000 characters?"
)

NOT_ENGLISH = (
    "I can only correct English for now. Send me a sentence in English?"
)

LLM_RETRY = "Give me a second, trying again…"

LLM_FAILED = "Something broke on my side — try that message again in a moment."

# --- Daily quiz (S3–S3d) ----------------------------------------------------

QUIZ_FREE_PRACTICE = (
    "Nothing due from your journal today — send me any English you're using "
    "and I'll correct it. That builds tomorrow's quiz."
)

QUIZ_HINT_GAP = "⌨️ Type the missing word"
QUIZ_HINT_CHOICE = "👆 Tap the one that sounds right"
QUIZ_HINT_ORDER = "👆 Tap the one that sounds right"
QUIZ_HINT_SPOT = "👆 Tap the word that's wrong"

QUIZ_SPOT_PROMPT = "One word is wrong. Which one?"

QUIZ_YOU_SAID = '❌ You said: "{said}"'
QUIZ_CORRECT_SENTENCE = '✅ "{sentence}"'
QUIZ_WRONG_EXPLAIN = "💡 {explanation}"

QUIZ_DONE = "Done — {correct}/{total} {stars}"

QUIZ_STREAK = "🔥 {n}-day streak"

QUIZ_IMPROVED = "Getting steadier: {label}."

QUIZ_CAME_BACK = "📌 {label} came back — I'll ask again tomorrow."

QUIZ_RESCUE = "Shorter one today — three questions."

QUIZ_WEEKLY = "Sunday check-in — fifteen questions across your journal."

# Murphy routing (S11) — appended to weekly-test completion (reply, not a
# new bot-initiated message). Labels only; under 400 chars; no guilt.
MURPHY_REC_STUDIED = (
    "Worth revisiting: Murphy {units} ({label}) — you already have some "
    "of those stored."
)
MURPHY_REC_NEW = (
    "New from your patterns: Murphy {units} ({label})."
)

# Freeze notice (S5 choice b): keep remaining count when tokens remain;
# omit the inventory clause when zero — "None left" is guilt (PRD §7 rule 4).
QUIZ_FREEZE_USED = (
    "Yesterday got away from you — I used a freeze, your streak's intact. "
    "{remaining} left this month."
)

QUIZ_FREEZE_USED_NO_REMAINING = (
    "Yesterday got away from you — I used a freeze, your streak's intact."
)


def format_freeze_notice(remaining_tokens: int) -> str:
    """Freeze-used line. Count only when tokens remain."""
    if remaining_tokens <= 0:
        return QUIZ_FREEZE_USED_NO_REMAINING
    if remaining_tokens == 1:
        remaining = "One"
    else:
        remaining = str(remaining_tokens)
    return QUIZ_FREEZE_USED.format(remaining=remaining)


def format_correction_block(
    you_said: str,
    correct_form: str,
    explanation: str,
    murphy_units: str | None,
) -> str:
    """One PRD §8 correction block. Omits the Murphy line when units is None."""
    lines = [
        f'✏️ "{you_said}"',
        f"→ {correct_form}",
        f"💡 {explanation}",
    ]
    if murphy_units:
        lines.append(f"📗 Murphy {murphy_units}")
    return "\n".join(lines)


def format_correction_reply(
    corrections: list[dict],
    did_well: str,
    murphy_by_code: dict[str, str | None],
) -> str:
    """Full correction reply: blocks separated by blank lines, then did_well."""
    blocks = [
        format_correction_block(
            you_said=c["you_said"],
            correct_form=c["correct_form"],
            explanation=c["explanation"],
            murphy_units=murphy_by_code.get(c["error_type"]),
        )
        for c in corrections
    ]
    return "\n\n".join(blocks) + f"\n\n👍 {did_well}"


def format_praise(did_well: str) -> str:
    return f"👍 {did_well}"


# --- Voice partner (S5) ------------------------------------------------------

VOICE_TOO_LONG = (
    "That one's a bit long for a chat — send something under two minutes?"
)

VOICE_DIDNT_CATCH = (
    "I didn't catch that — try again when you're ready?"
)

# Processing stages (S5a) — honest names, not a progress bar.
VOICE_STATUS_LISTENING = "🎧 Got it, listening…"
VOICE_STATUS_THINKING = "💭 Thinking…"
VOICE_STATUS_RECORDING = "🔊 Recording my reply…"


# --- Voice diary (S13 / M9) ---------------------------------------------------

# Rotating prompts — under 400 chars; concrete, warm, one idea each.
DIARY_PROMPTS: tuple[str, ...] = (
    "Sixty seconds about your day — what was the main thing that happened?",
    "Voice note time: what went well today, even something small?",
    "Tell me about one conversation you had today — who, and what about?",
    "What took most of your energy today? About a minute is perfect.",
    "Anything you figured out or decided today? Talk it through for ~60s.",
    "How did the afternoon feel compared to the morning? Send a short voice note.",
    "What are you glad is done for the day? About a minute of talking.",
)

DIARY_TOO_LONG = (
    "That one's a bit long for the diary — try under a minute and a half?"
)

DIARY_ALREADY_OPEN = (
    "Tonight's diary is already open — just send a voice note when you're ready."
)

DIARY_ALREADY_DONE = (
    "You've already done today's diary — nice. Tomorrow's another one."
)

DIARY_DIDNT_CATCH = (
    "I didn't catch that — send another voice note when you're ready?"
)

NUDGE_FIRST_DIARY = (
    "Tonight's diary is still open — about a minute whenever you like."
)

NUDGE_SECOND_DIARY = (
    "No time for a full minute? Even half a minute still counts."
)


# --- Interests profile (S9) ---------------------------------------------------

INTERESTS_INTRO = (
    "What do you actually want to read and watch about?\n"
    "I'll use this for the reading and video picks."
)

INTERESTS_ASK_WORK = "Work — pick topics you care about."
INTERESTS_ASK_LIFE = "Life & Social — what comes up in your day?"
INTERESTS_ASK_CURIOSITY = "Curiosity — what do you dig into for fun?"

INTERESTS_ASK_OTHER = "What topic? One short phrase is enough."

INTERESTS_INVALID_OTHER = "I need a short topic — try again?"

INTERESTS_PROFILE_INTRO = "Here's what I'm aiming at for reading and video."

INTERESTS_SAVED = "Got it — I'll lean on these for reading and video."

INTERESTS_KEEP = "Alright — leaving your interests as they are."

INTERESTS_CANCELLED = "Okay — nothing changed. Say /interests whenever you're ready."

INTERESTS_SAVE_FAILED = (
    "Something broke on my side — try /interests again in a moment."
)

# Toast when Done is tapped with fewer than 2 selections (callback query answer).
INTERESTS_DONE_TOAST = "Pick at least two first."

# --- Reading delivery (S9a) + comprehension (S9c) -----------------------------

# Title + body; PRD §8 exempts reading from the 400-character scheduled limit.
READING_DELIVERY = "{title}\n\n{body}"

BTN_READING_QUESTIONS = "Questions"

READING_Q_PROGRESS = "Question {n} of {total}"

READING_CORRECT = "✅ That's right."

READING_WRONG = "❌ Not quite.\n💡 {why}"

READING_SCORE = "You got {correct} of {total}."

READING_RATE_PROMPT = "How useful was this topic for you?"

READING_CLOSE = "Thanks — I'll lean on that for the next picks."

# --- Anki export (S7 / M6) ----------------------------------------------------

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

INTERESTS_TRACK_LABELS: dict[str, str] = {
    "work": "Work",
    "life": "Life & Social",
    "curiosity": "Curiosity",
}

# Every preset gets a leading emoji; customs use the topic text with none.
INTEREST_TOPIC_LABELS: dict[str, str] = {
    "campaigns": "📣 Campaigns",
    "client email": "📧 Client email",
    "negotiation": "🤝 Negotiation",
    "standups": "🗣️ Standups",
    "interviews": "💼 Interviews",
    "pricing": "💰 Pricing",
    "positioning": "🎯 Positioning",
    "apartments": "🏠 Apartments",
    "doctors": "🩺 Doctors",
    "arguments": "💢 Arguments",
    "cooking": "🍳 Cooking",
    "travel": "✈️ Travel",
    "humour": "😄 Humour",
    "opinions": "💭 Opinions",
    "small talk": "💬 Small talk",
    "space": "🚀 Space",
    "psychology": "🧠 Psychology",
    "history": "📜 History",
    "mysteries": "🕵️ Mysteries",
    "technology": "💻 Technology",
    "sport": "⚽ Sport",
    "nature": "🌿 Nature",
}

INTEREST_PRESETS: dict[str, list[str]] = {
    "work": [
        "campaigns",
        "client email",
        "negotiation",
        "standups",
        "interviews",
        "pricing",
        "positioning",
    ],
    "life": [
        "apartments",
        "doctors",
        "arguments",
        "cooking",
        "travel",
        "humour",
        "opinions",
        "small talk",
    ],
    "curiosity": [
        "space",
        "psychology",
        "history",
        "mysteries",
        "technology",
        "sport",
        "nature",
    ],
}

BTN_INTERESTS_OTHER = BTN_DOMAIN_OTHER
BTN_INTERESTS_DONE_NEED_2 = "Pick 2 to continue"
BTN_INTERESTS_DONE_NEED_1 = "Pick 1 more"
BTN_INTERESTS_DONE_READY = "Done →"


# --- Book ingestion (S6) ------------------------------------------------------

BOOK_ASK_WHICH = (
    "Which book are these pages from?\n"
    "Pick one — I'll remember it for this batch."
)

BOOK_ASK_OTHER = "What's the book called? A short name is enough."

BOOK_INVALID_OTHER = "I need a short book name — try again?"

BOOK_ASK_PAGES = (
    "Send photos of the pages (or uncompressed image files).\n"
    "I'll wait a moment after the last one, then read them."
)

BOOK_CANCELLED = "Okay — cancelled. Say /book whenever you're ready."

BOOK_NUDGE_AWAITING = "Tap Done or Add more pages below when you're ready."

BOOK_STATUS_READING = "📖 Reading your pages…"
BOOK_STATUS_SAVING = "💾 Saving units…"

BOOK_SUMMARY_UNITS = "Saved {count} unit(s) from {book}: {units}."
BOOK_SUMMARY_NO_UNITS = "I couldn't pull out any units from those pages."
BOOK_SUMMARY_UNREADABLE = "{pages} couldn't be read — {cta}"
BOOK_SUMMARY_LLM_FAIL = "{pages} hit a snag on my side — {cta}"
BOOK_SUMMARY_RESHOOT_ONE = "re-shoot that page, one page per photo?"
BOOK_SUMMARY_RESHOOT_MANY = "re-shoot those pages, one page per photo?"
BOOK_SUMMARY_ORPHAN = (
    "{pages} looked like a continuation with no unit before them, "
    "so I skipped those."
)
BOOK_SUMMARY_OVER_CAP = (
    "I only took the first 20 pages; send the rest with another /book."
)
BOOK_SUMMARY_FOOTER = "Done closes this; Add more pages keeps going."

BOOK_PROCESS_FAILED = (
    "Something broke on my side while reading those pages — "
    "try /book again in a moment."
)

BTN_BOOK_MURPHY = "Murphy"
BTN_BOOK_VOCAB = "Vocabulary in Use"
BTN_BOOK_MARKETING = "Marketing"
BTN_BOOK_OTHER = "Other"
BTN_BOOK_DONE = "Done"
BTN_BOOK_ADD_MORE = "Add more pages"


# --- Book unit test /test (S6a) -----------------------------------------------

TEST_EMPTY = (
    "No book units saved yet — photograph some pages with /book first, "
    "then try /test."
)

TEST_LIST = "Which unit should we practise?"

TEST_UNKNOWN = (
    "I don't have unit {unit} saved yet.\n"
    "You do have: {available}."
)

TEST_UNKNOWN_NONE = (
    "I don't have unit {unit} saved yet — and no other units either. "
    "Try /book first?"
)

TEST_WHICH_BOOK = "Unit {unit} is in more than one book — which one?"

TEST_NO_ITEMS = (
    "Unit {unit} is saved, but I couldn't pull teachable points from it yet. "
    "Try re-shooting that unit with /book?"
)

TEST_FAILED = (
    "Something snagged while building that set — try /test again in a moment."
)

TEST_DONE = "Done — {correct}/{total} {stars}"

BTN_TEST_UNIT_PREFIX = "Unit {unit}"


# --- Motivation / nudges + Sunday report (S10) --------------------------------

NUDGE_FIRST_QUIZ = (
    "Your quiz is still here whenever you have a few minutes."
)

NUDGE_FIRST_READING = (
    "Your reading is still here whenever you have a few minutes."
)

NUDGE_SECOND_QUIZ = (
    "No time for the full set? Just do 2 — it still counts."
)

NUDGE_SECOND_READING = (
    "No time for all five? Just do 2 questions — it still counts."
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


# --- Calibration (S12 / M14) --------------------------------------------------

LEVEL_RAISE = (
    "Your English is settling at {level} — I'll pitch things a step up from here."
)


# --- Settings / pause / stats (S18) -------------------------------------------

SOFT_UNHANDLED = "Something broke on my side — try that again in a moment."

PAUSE_PICK = "How long should I hold scheduled messages?"

PAUSE_ACTIVE = (
    "You're paused until {until}. Scheduled quizzes and readings stay quiet."
)

PAUSE_SET = "Paused until {until}. Tap /pause anytime to resume."

PAUSE_RESUMED = "You're back — scheduled messages will return at your usual times."

BTN_PAUSE_1D = "1 day"
BTN_PAUSE_3D = "3 days"
BTN_PAUSE_7D = "1 week"
BTN_PAUSE_RESUME = "Resume"

STATS_HEADER = "Your snapshot"

STATS_LEVEL = "Level: {level}"
STATS_STREAK = "Streak: {streak} day(s) · freeze tokens: {freezes}"
STATS_ACTIVE = "{active_line}"
STATS_DUE = "Due errors: {n}"
STATS_RESOLVED = "Quiet types: {labels}"
STATS_RESOLVED_NONE = "Quiet types: none yet"
STATS_CHUNKS = "Chunks: {total} · unexported: {unexported}"
STATS_BOOKS = "Book units stored: {n}"
STATS_CALIBRATION = "Calibration: {accuracy} · last change: {change}"
STATS_CALIBRATION_NONE = "Calibration: not enough recent evidence yet"
STATS_OPERATOR_SWEEP = "Sweep (ops): pending {pending} · done {done}"


# --- Real-life capture (S15 / M11) --------------------------------------------

CAPTURE_USAGE = (
    "Paste the English after the command, like:\n"
    "/capture Could you circle back on this by Friday?"
)

CAPTURE_TOO_SHORT = (
    "That snippet is too short to mine — send a bit more English?"
)

CAPTURE_TOO_LONG = (
    "That's a bit long for one pass — send something under 4000 characters?"
)

CAPTURE_NOTHING_USEFUL = (
    "I couldn't pull useful phrases from that — try another bit of English?"
)

CAPTURE_FAILED = (
    "Something broke on my side — try that capture again in a moment."
)

# Shown under a successful capture when the whole reply stays ≤400 chars.
CAPTURE_SELF_HINT = (
    "Want your own writing corrected? Type it — don't forward it."
)


# --- Load-up mode (S14 / M10) -------------------------------------------------

PREP_USAGE = (
    "Tell me what you're walking into, like:\n"
    "/prep marketing budget meeting"
)

PREP_TOO_LONG = (
    "That's a bit long for a topic — keep it to a short phrase "
    "(under 200 characters)?"
)

PREP_FAILED = (
    "Something broke on my side — try that prep again in a moment."
)

PREP_TITLE = "Prep: {topic}"

PREP_SECTION_CHUNKS = "Phrases"

PREP_SECTION_FRAMES = "Reply frames"


# --- Shadowing (S16 / M12) ----------------------------------------------------

SHADOW_EMPTY_POOL = (
    "I don't have a sentence for you yet. Send me a reading evening, "
    "forward some English with /capture, or try /prep for a real meeting — "
    "then come back to /shadow."
)

SHADOW_INTRO = (
    "Listen, then send a voice note repeating it. "
    "I'll show which words came through clearly."
)

SHADOW_FAILED_TTS = (
    "I couldn't play that clip just now — try /shadow again in a moment."
)

SHADOW_FAILED_STT = (
    "I couldn't catch that recording — try the voice note once more?"
)

SHADOW_TIP_CLEAR = "That came through clearly."

SHADOW_TIP_AGAIN = "Try this part again — a few words didn't come through clearly."

SHADOW_TIP_PART = "Try this part again: {detail}"

SHADOW_DONE = "Nice — that's enough for this one."

BTN_SHADOW_AGAIN = "Try again"


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


