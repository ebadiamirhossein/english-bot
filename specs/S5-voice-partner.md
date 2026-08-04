# S5 · Voice partner (M3)

**Cursor Plan mode: ON.**
Cross-cutting: this slice changes how open sessions are selected (shared with S3's quiz
delivery) and reuses S2's correction path. Both are places where a careless edit breaks
something already verified live. Plan first, then implement.

**Save to:** `specs/S5-voice-partner.md`
**Depends on:** S2 (correction + `record_errors`), S3 (sessions + payload), S4 (streaks)
**Migration:** none. `sessions.payload` (002) and `errors.source='voice'` (001 CHECK) already exist.

---

## 1. What ships

A user sends a Telegram voice message. The bot:

1. transcribes it (Whisper),
2. replies **as voice**, in character, continuing the conversation,
3. sends a **separate text message** with the correction block in the PRD §8 shape,
4. writes each error to the journal with `source='voice'`.

Conversation context persists across turns for up to 10 exchanges, and survives a bot
restart.

## 2. Non-goals

Do not build, do not stub, do not "prepare for":

- chunk mining from voice (S5 writes **no** `chunks` rows — chunks come from S9/S15)
- shadowing / pronunciation scoring (S16)
- the nightly voice diary (S13)
- group / couple voice (S8, S17)
- voice **answers** to quiz questions — a voice message never answers an open quiz
- any new columns, tables or migrations

## 3. Decisions this slice must honour

Carried from the decisions log; do not relitigate in code:

| Rule | Source |
|---|---|
| Conversation state lives in `sessions.payload`, never `bot_data` | S3 — `bot_data` dies on restart |
| Only `speech.py` may import the STT/TTS provider SDK | ARCHITECTURE §2 principle 2, mirrors `llm.py` |
| Audio is never written to disk, in either direction | PRD §10, ARCHITECTURE §4 |
| Spoken reply never breaks character — corrections are text-only | PRD M3 |
| Spoken register: short sentences, how people actually talk | S3c |
| Never guilt, neutral or warm only | PRD §7 rule 4 |
| User-facing strings live in `texts.py` | ARCHITECTURE §3 |

## 4. New decisions (record these in BUILD_PROGRESS)

1. **Voice sessions are marked `completed=TRUE` as soon as an exchange succeeds**, not when
   the conversation ends. A voice exchange is real usage the moment it happens; an abandoned
   conversation must not leave an incomplete row that S4's rollover reads as a missed day and
   pays a freeze token for. The live conversation is found by recency, not by `completed`.

2. **A voice session must not block quiz delivery, and a quiz must not block voice.** S3's
   selection currently blocks on *any* session for the local day. Scope that check to
   `task_type IN ('quiz','free_practice')`. Without this, recording a voice message at 07:40
   silently cancels that day's quiz.

3. **Voice replies do not increment `bot_message_counts`.** PRD §7 rule 9 caps *bot-initiated*
   messages. These are answers to the user.

4. **Maximum 3 corrections per voice turn.** A spoken turn generates more errors than a typed
   one; a six-item correction wall after every message ends the conversation. Untaken errors
   are not lost — the user says the same things again.

5. **Conversation window: 120 minutes since the last turn, hard cap 10 exchanges.** Past
   either, the next voice message starts a fresh session.

6. **Voice messages longer than 120 seconds are declined before download.** Telegram gives
   `voice.duration` up front. M3 is a conversation, not a monologue; the 60-second monologue
   is S13.

7. **If TTS fails but the LLM succeeded, send the reply as text.** Losing the turn is worse
   than losing the audio.

## 5. Files

| Path | Action |
|---|---|
| `app/speech.py` | **new** — `transcribe()`, `synthesize()`, `SpeechError` |
| `app/prompts/voice.txt` | **new** — conversation + correction system prompt |
| `app/handlers/voice.py` | **new** — voice message handler |
| `app/config.py` | add STT/TTS keys |
| `app/main.py` | register `MessageHandler(filters.VOICE, ...)` |
| `app/texts.py` | voice strings **+ fix the freeze copy bug (§10)** |
| `app/services/sessions.py` | voice conversation read/write; scope open-session check |
| `app/handlers/correction.py` | extract the shared formatter only — no behaviour change |
| `.env.example` | new keys with dummy values |
| `requirements.txt` | add `openai` (match existing pinning style) |
| `tests/test_voice.py` | **new** |
| `tests/test_speech.py` | **new** |
| `BUILD_PROGRESS.md` | slice row, decisions, file inventory, next action |

## 6. Config

Add to `Settings` (frozen dataclass, `ConfigError` on missing required keys):

```
STT_PROVIDER=openai
TTS_PROVIDER=openai
OPENAI_API_KEY=sk-...
WHISPER_MODEL=whisper-1
TTS_MODEL=tts-1
TTS_VOICE=alloy
TTS_FORMAT=opus
VOICE_MAX_SECONDS=120
VOICE_CONTEXT_MINUTES=120
VOICE_MAX_TURNS=10
```

`OPENAI_API_KEY` is required only when a voice message actually arrives — importing the app
without it must still work, because the daily quiz does not need it. Follow whatever pattern
`ANTHROPIC_API_KEY` uses; if that one is required at import, keep the same shape and note it
in the handoff so the human knows the key must be present before starting the bot.

Unknown `STT_PROVIDER` / `TTS_PROVIDER` raises `ConfigError` at load.

**Model names are env-driven on purpose** — verify `whisper-1` / `tts-1` against current
OpenAI docs before the first live run and change the `.env` value if they have moved. No code
change should ever be needed for that.

## 7. `app/speech.py`

Exact signatures from ARCHITECTURE §4:

```python
def transcribe(audio: bytes, *, language: str = "en") -> str
def synthesize(text: str, *, voice: str = "alloy") -> bytes
```

Requirements:

- Retry 3× with backoff, raise `SpeechError` on final failure. Mirror `llm.py` structure.
- `transcribe` passes an in-memory file tuple — `("voice.ogg", io.BytesIO(audio))` — because
  the OpenAI SDK infers the container from the filename. Telegram voice is OGG/Opus.
- `synthesize` requests `response_format=settings.TTS_FORMAT`. Opus in an OGG container is
  what Telegram's `send_voice` accepts.
- Nothing touches the filesystem. No `tempfile`, no `download_to_drive`, no `open(...)`.
- This is the only module in the repo allowed to `import openai`.

## 8. `app/prompts/voice.txt`

**Read `app/prompts/correction.txt` first and mirror its error object field names and its
`error_type` code list exactly**, so `services/errors.py::record_errors` and the existing
correction formatter need no changes. Do not invent a second error schema.

The prompt takes the same parameterised variables the correction prompt takes (name,
native language, CEFR level, work domain, explanation-language fallback) plus the
conversation history.

Returns one JSON object per turn:

```json
{
  "reply": "spoken text, 1-2 sentences, max 40 words, ends with a question",
  "errors": [ /* same object shape as correction.txt, max 3 */ ],
  "did_well": "one specific thing, not generic praise"
}
```

Rules to state in the prompt:

- `reply` is **spoken**. It must contain no corrections, no grammar talk, no meta-commentary
  about the user's English. It is one side of a conversation between two people.
- Apply the S3c spoken register test: would a person say this out loud to a friend? No report
  sentences, no "the museum team", no subordinate-clause stacking.
- Pitch vocabulary at the user's `cefr_level`, one small step above.
- End with a question so the user has something to answer — except on the final turn (the
  handler will tell it `final_turn: true`), where it wraps up warmly and asks nothing.
- Explanations max 25 words (PRD §8). Native-language fallback only for abstract grammar and
  only when the flag is on.
- Errors are the 3 that most matter, not the first 3 found. Ignore self-corrections and
  transcription noise — if a word looks like a Whisper artefact rather than something the user
  said, skip it.

Use `json_mode=True` on the `llm.chat()` call and reuse the existing cache-control pattern
if `correction.py` uses one.

## 9. Handler behaviour — `app/handlers/voice.py`

Registered as `MessageHandler(filters.VOICE, handle_voice)`. Not `filters.AUDIO`, not
`VIDEO_NOTE` — those are out of scope this slice.

Flow:

1. **Access control.** Reuse `handlers/access.py`. Unregistered users are silently ignored,
   exactly as everywhere else.
2. **Duration gate.** `update.message.voice.duration > VOICE_MAX_SECONDS` → warm decline from
   `texts.py`, return. Do not download.
3. **Per-user lock.** An in-process `dict[int, asyncio.Lock]` in the handler module. A second
   voice message that arrives mid-processing waits rather than racing the payload write. No
   new dependency.
4. **Download to memory.** `await file.download_as_bytearray()` → `bytes`. Send a chat action
   (`RECORD_VOICE` or `TYPING`) while working, since transcribe + LLM + TTS takes several
   seconds.
5. **Transcribe.** Empty or near-empty transcript → warm "I didn't catch that" from
   `texts.py`, return, no session row, no LLM call.
6. **Load conversation.** Most recent `sessions` row for this user with `task_type='voice'`
   whose last turn is within `VOICE_CONTEXT_MINUTES` and whose turn count is under
   `VOICE_MAX_TURNS`. Otherwise start a new row (`date` = user's **local** date, per S3).
7. **LLM call** with the history from `payload` plus this turn. Pass `final_turn: true` when
   this exchange hits `VOICE_MAX_TURNS`.
8. **Synthesize and send.** Voice message first, then the text correction block as a separate
   message. If `TTS_FORMAT` is `opus`, send with `send_voice`; any other format goes via
   `send_audio`. If `synthesize` raises, send `reply` as text and continue — the turn is not
   lost.
9. **Persist.** Append `{role, content}` for both sides to `payload`, set `completed=TRUE`,
   `completed_at=NOW()`. `record_errors(user_id, source='voice', errors=...)`.
10. **Do not** touch `bot_message_counts`.

Text correction block: reuse the formatter that `correction.py` already produces for M2.
If it is currently inline in the handler, extract it into a shared function — a pure move,
no behaviour change, and `tests/test_correction.py` must stay green untouched. If `errors`
is empty, still send the `did_well` line (blank line + 👍, per the S2 decision) so the user
gets something back.

Failure handling per ARCHITECTURE §6: first failure → "give me a second, trying again";
second → the soft message; never a stack trace, never a silent drop.

## 10. Copy bug to fix in this slice

`texts.py` currently tells the user **"None left this month"** after a freeze token is spent.
That is guilt, and PRD §7 rule 4 forbids it. Rewrite it neutrally — state that yesterday is
covered and the streak stands, without scoring the user on what they have run out of. Update
any `tests/test_streaks.py` assertion that pins the old string.

## 11. Tests required

`tests/test_speech.py` (provider mocked, no network):

- `transcribe` passes a named in-memory file, never a path
- neither function opens, writes or creates a file — assert on a patched `builtins.open` and
  `tempfile`
- retry fires 3× then raises `SpeechError`

`tests/test_voice.py`:

- a voice session for today does **not** block quiz delivery for that day (this is the
  regression that matters most — write it before the code)
- a completed quiz session does not block a voice conversation
- a voice exchange does not increment `bot_message_counts`
- conversation continues inside the window, starts fresh outside it
- turn 10 sends `final_turn` and the next message opens a new session
- errors are written with `source='voice'`, capped at 3
- over-length voice is declined without calling `transcribe`
- TTS failure still delivers the reply as text and still records errors

Full suite must stay green — 83 existing tests, none modified except the freeze-copy
assertion in §10.

## 12. Acceptance

**Cursor verifies and pastes output:**

- `pytest` green, count reported
- `grep -rn "import openai" app/` returns only `app/speech.py`
- `grep -rn "open(\|tempfile\|download_to_drive" app/speech.py app/handlers/voice.py` returns nothing
- `grep -rn "bot_message_count" app/handlers/voice.py` returns nothing
- `git diff --stat` for the slice
- the diff of the open-session selection change, shown explicitly

**Human verifies in Telegram (do not mark ✅ before this):**

- send a voice message with 2 deliberate mistakes → a spoken reply arrives that continues the
  conversation, plus a separate text correction block in the PRD §8 shape
- both errors appear in `errors` with `source='voice'`
- reply to the reply → the bot remembers the topic
- restart the bot mid-conversation → it still remembers
- next morning's quiz still arrives
- a 3-minute voice message is declined warmly

## 13. Cost

Roughly $3–5/month added for two users at ~10 turns/day: Whisper ~$0.006/min, TTS `tts-1`
$15 per 1M characters, plus one extra Sonnet call per turn. Under the noise floor of the
Hetzner box.

---
---

# CURSOR PROMPT — paste below this line

**Plan mode: ON.** Produce the plan, wait for approval, then implement.

Implement slice S5 (voice partner, M3) exactly as specified in
`specs/S5-voice-partner.md`. Read that file first, then read `.cursorrules`,
`BUILD_PROGRESS.md`, `docs/ARCHITECTURE.md` §4/§6/§8, `docs/PRD.md` §7/§8/§10 and
`docs/TASKS.md` §S5 before writing anything.

Before you plan, read these three existing files and plan around what is actually there
rather than what you assume:

1. `app/llm.py` — mirror its retry, error class and provider-dispatch structure in the new
   `app/speech.py`.
2. `app/prompts/correction.txt` and `app/handlers/correction.py` — the new voice prompt must
   emit the **same error object shape and the same `error_type` code list**, so
   `record_errors` needs no change, and the voice handler must **reuse** the existing
   correction formatter rather than duplicating it.
3. `app/services/sessions.py` and `app/scheduler.py` — find the query that decides whether a
   session already exists for the local day. It currently blocks on any session. Scope it to
   `task_type IN ('quiz','free_practice')` so a voice conversation cannot cancel that day's
   quiz. Show me this diff separately; it is the highest-risk change in the slice.

Constraints:

- No migration. No new tables or columns. `sessions.payload` and `source='voice'` already exist.
- No new dependency other than `openai`.
- `import openai` may appear only in `app/speech.py`.
- Audio never touches the filesystem in either direction — no `tempfile`, no
  `download_to_drive`, no `open()`. Use `download_as_bytearray()` and `io.BytesIO`.
- Conversation state lives in `sessions.payload`. Never `bot_data`.
- Every user-facing string goes in `app/texts.py`.
- Do not build chunk mining, shadowing, the voice diary, group voice, or voice answers to
  quiz questions. S5 writes zero rows to `chunks`.
- Do not change onboarding, quiz generation, grading, the spacing ladder, or streak logic.
  The only permitted edit to `correction.py` is extracting the correction formatter into a
  shared function with no behaviour change.

Also fix, in the same slice: `app/texts.py` tells the user "None left this month" after a
freeze token is consumed. That is guilt and violates PRD §7 rule 4. Rewrite it neutrally —
yesterday is covered, the streak stands — and update the one test assertion that pins the
old string.

Write the tests listed in §11 of the spec. Write the "a voice session does not block quiz
delivery" test first, before the handler.

When done, run `pytest` and the four greps in §12, paste the output plus `git diff --stat`,
and update `BUILD_PROGRESS.md`: the S5 row, the six new decisions from §4 with their reasons,
the file inventory, the environment table (`Whisper/TTS key`), and the Next action block.
Do not mark S5 ✅ — it stays 🟡 until the human verifies it in Telegram.
