# S5a · Voice processing status

**Cursor Plan mode: OFF.**
One handler, one strings file, additive tests. No cross-cutting logic, no schema, no new
decisions about state. Straightforward slice — implement directly.

**Save to:** `specs/S5a-voice-status.md`
**Depends on:** S5
**Migration:** none.

---

## 1. Problem

A voice turn takes 8–20 seconds: download → Whisper → Sonnet → TTS. During that window the
user gets nothing back. The bot looks broken, and the natural reaction is to record the
message again, which spends a second turn and confuses the conversation history.

S5 §9 already called for a chat action. Telegram chat actions **expire after ~5 seconds** —
sent once, it vanishes well before the reply arrives. Assume it is currently fired once and
verify.

## 2. What ships

Two things, together:

1. A **repeating** chat action for the whole processing window.
2. A **status message** that edits in place through the three real stages, then disappears
   when the voice reply lands.

## 3. Explicitly not building

- **No percentage bar, no `▓▓▓░░░`, no ETA.** The stages are unequal and unpredictable —
  Whisper on a 60-second message is far slower than on a 10-second one. A bar that fills to
  80% and then hangs reads as a crash. Honest stage names are better than dishonest precision.
- **No showing the transcript in the status message.** The correction block already quotes
  what the user said back to them; a transcript would duplicate it, and a Whisper mishearing
  displayed mid-flow invites a "no, I said—" reply that the conversation history then has to
  absorb.
- No progress for the quiz, correction, or any other handler. Voice only.

## 4. Behaviour

After the access check and the duration gate pass — never before, so a declined 3-minute
message still costs nothing — and before the download:

| Stage | Status text | Set when |
|---|---|---|
| 1 | 🎧 Got it, listening… | immediately, before download |
| 2 | 💭 Thinking… | transcription returned a usable transcript |
| 3 | 🔊 Recording my reply… | the LLM call returned |

Then: **delete** the status message immediately before sending the voice reply, so the user
is left with a clean conversation — voice, then correction block, nothing else.

Rules:

- Stage transitions use `edit_message_text` on the same message id. One message for the whole
  turn, never a new one per stage. This is the S1b wizard pattern.
- The empty-transcript path (`I didn't catch that`) **edits the status message into that text**
  rather than deleting it and sending a new one.
- Every failure path does the same: the status message becomes `LLM_RETRY` / `LLM_FAILED` /
  the over-length decline. **The status message must never be left sitting at "💭 Thinking…".**
  Use `try/finally` so an unexpected exception still clears it.
- Ignore `BadRequest: message is not modified` on edits, per the S1b decision.
- Deleting the status message may fail (user deleted it, message too old). Catch and continue —
  a failed delete must not lose the turn.

**Chat action:** run `ChatAction.RECORD_VOICE` on a repeating `asyncio` task that re-sends
every 4 seconds, started with stage 1 and cancelled in the same `finally` that clears the
status message. Not a single call.

**Message ceiling:** the status message is not counted. It is part of a user-initiated
exchange, per S5 decision 3, and it is deleted before the turn ends.

## 5. Files

| Path | Action |
|---|---|
| `app/handlers/voice.py` | status message lifecycle + repeating chat action |
| `app/texts.py` | three stage strings |
| `tests/test_voice.py` | additive cases |
| `BUILD_PROGRESS.md` | S5a row, decisions, next action |

Do not touch `speech.py`, `sessions.py`, `streaks.py`, `correction.py`, `voice.txt`, or any
other handler.

## 6. Tests

Additive to `tests/test_voice.py`. Existing S5 cases must not be modified.

- happy path: status message created once, edited twice, deleted before the voice send —
  assert on call order, not just counts
- empty transcript: status message is **edited** into the "didn't catch that" text, and no
  separate message is sent
- LLM failure: status message ends as the failure text, not "💭 Thinking…"
- an exception raised mid-turn still results in the status message being cleared and the chat
  action task cancelled
- over-length voice: **no** status message and no chat action — the decline happens before
  either starts
- the status message does not increment `bot_message_counts`
- a failed `delete_message` does not prevent the voice reply from being sent

Full suite green — currently 98.

## 7. Acceptance

**Cursor verifies:**

- `pytest` green, count reported
- `git diff --stat` — should be 4 files, no others
- confirm in the diff that the chat action is a repeating task, not a single call

**Human verifies in Telegram:**

- send a voice message → "🎧 Got it, listening…" appears within a second, moves through
  💭 and 🔊, then vanishes as the voice reply arrives
- the "recording audio…" indicator stays visible in the header for the whole wait, not just
  the first few seconds
- a 3-minute message is still declined with no status message beforehand
- a one-second grunt turns the status message into "I didn't catch that", with no leftover
- after a completed turn the chat shows only: your voice, the bot's voice, the correction block

---
---

# CURSOR PROMPT — paste below this line

**Plan mode: OFF.** Implement directly.

Implement slice S5a exactly as specified in `specs/S5a-voice-status.md`. Read that file and
`app/handlers/voice.py` first.

Problem: a voice turn takes 8–20 seconds and the user gets no feedback during it, so the bot
looks broken and they re-record. The chat action added in S5 expires after ~5 seconds — check
how it is currently sent and fix it to repeat.

Build two things in `app/handlers/voice.py`:

1. A repeating `ChatAction.RECORD_VOICE` on an `asyncio` task re-sending every 4 seconds,
   started after the duration gate passes and cancelled in a `finally`.
2. A single status message, created before the download and edited in place through three
   stages — "🎧 Got it, listening…" → "💭 Thinking…" (after transcription) → "🔊 Recording my
   reply…" (after the LLM returns) — then deleted immediately before the voice reply is sent.

Hard requirements:

- One message id for the whole turn. Use `edit_message_text`, never send a new message per
  stage. Ignore `BadRequest: message is not modified`, per the S1b decision.
- The status message must never be left showing a stage. Use `try/finally`. Every terminal
  path — empty transcript, LLM retry, LLM failure, unexpected exception — **edits the status
  message into that text** instead of deleting it and sending a new one.
- The over-length decline happens *before* any status message or chat action exists.
- A failed `delete_message` is caught and ignored; the voice reply still sends.
- Do not increment `bot_message_counts`.
- All three stage strings go in `app/texts.py`.

Do not build a percentage bar, a filling `▓▓▓░░░` bar, or an ETA — the stage durations are
unpredictable and a bar that stalls at 80% reads as a crash. Do not display the transcript in
the status message. Do not add progress indicators to any other handler.

Do not touch `speech.py`, `sessions.py`, `streaks.py`, `correction.py`, `prompts/voice.txt`,
or any handler other than `voice.py`. The diff should be 4 files.

Write the tests in §6 of the spec, additive to `tests/test_voice.py`, without modifying the
existing S5 cases. Assert on call *order* for the happy path, not just call counts.

When done, run `pytest`, paste the output and `git diff --stat`, and update
`BUILD_PROGRESS.md` with the S5a row and the decision that stage names were chosen over a
progress bar because stage durations are unpredictable. S5a stays 🟡 until human Telegram
verification.
