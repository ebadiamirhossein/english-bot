# S1a · Onboarding UX polish

**Slice:** S1a (amends S1)
**Phase:** 1 — Foundation
**Depends on:** S1 (code-complete 2026-07-31)
**Status:** ⬜ not started
**Spec written:** 2026-07-31

---

## Goal

S1 works correctly but reads as a form. Make the onboarding conversation feel
like a conversation. This is the product's first impression, and it sets the
tone for six months of daily messages.

No change to what is collected, validated, or stored. Copy and interaction only.

## Root cause

When the user taps an inline button, the answer disappears. Four of the eight
answers — native language, focus, morning time, evening time — leave no visible
trace. The chat becomes a one-sided list of questions with silence between them.

Fixing that one thing does most of the work.

## Non-goals

- No new questions, no removed questions.
- No change to `services/users.py`, the transaction, or any DB write.
- No change to validation rules.
- Interest questions remain S9. `/settings` remains S18.

---

## Changes

### 1. Echo every button answer (highest impact)

On any button press, edit the original message so the question and the chosen
answer stay on screen together, keyboard removed:

```
Native language
→ Farsi
```

Apply to: native language, EF SET "Not yet", focus preset, morning time,
evening time, and the confirm step.

### 2. Show progress

Each question carries a step marker on its own line, so the user knows how much
is left:

```
Step 3 of 8
```

Eight steps total. The "Other" follow-ups (custom language, custom time) do not
increment the counter — they are part of their parent step.

### 3. Keep work domain as free text, but make it easier

Do **not** convert this to buttons. `work_domain` feeds content generation in S9
and S14; "AI Engineering" is far better signal than a generic preset would be.
Instead, give examples in the question:

> What do you work in?
> Be specific if you can — it shapes the examples I'll use.
> e.g. digital marketing, AI engineering, nursing

### 4. Reshape the summary

The current summary is a flat list. Make it scannable, and quote the
why-statement back so the user sees it was heard. Emoji are already part of the
design language in `PRD.md` §8's correction format, so light use is on-brand:

```
Does this look right?

👤 Amir · Farsi
📊 B1 — EF SET not taken yet
💼 AI Engineering
🎯 work 40 · life 40 · curiosity 20
🌅 09:00    🌙 19:00

"i want to improve talking with people"
```

Buttons stay: **Save** · **Start over**.

### 5. End on something concrete

"You're set. I'll message you at the times you chose." is flat and generic.
`PRD.md` §8 requires naming one specific thing. Name the next real event:

> You're set, Amir. First task lands tomorrow at 09:00.

Use the actual name and the actual time from their answers.

### 6. Soften the EF SET question

Currently it front-loads the escape hatch. Lead with the question, offer the way
out second:

> Step 3 of 8
> What's your EF SET score?
> No score yet? Tap Not yet — we'll start you at B1 and update it later.

---

## Bug to fix in the same pass

`app/handlers/onboarding.py:531` emits:

```
PTBUserWarning: If 'per_message=False', 'CallbackQueryHandler' will not be
tracked for every message.
```

With change 1 editing messages in place, button routing must be correct.
Resolve the warning properly — either set the `per_*` flags to match how the
handler is actually structured, or restructure so the default is correct. Do
not silence the warning. Explain the fix in the decisions log.

---

## Copy rules (unchanged, from `PRD.md` §8)

- Under 400 characters per message
- One idea per message
- Warm or neutral. Never guilt, never pressure
- Buttons over typing wherever a choice is being made
- Name one specific thing, never generic praise

---

## Cursor verifies before handing back

1. `python -m pytest -q` — all 7 existing tests still pass. If any onboarding
   test needed changing, say which and why; the persistence behaviour must not
   have changed.
2. `python -m app.main` starts with **no** `PTBUserWarning` in the output. Paste
   the startup log.
3. Confirm no new dependency was added.
4. Confirm `services/users.py` is unchanged — `git diff --stat` in your reply.

## Human verifies (Telegram)

1. `/start` from a fresh account → complete the flow. Every button answer stays
   visible on screen afterwards.
2. Step counter is present and correct on all 8 steps.
3. Summary matches the new shape and quotes the why-statement.
4. Final message names the user and the real first-task time.
5. Read the whole thing top to bottom. Does it feel like a conversation now?

## Definition of done

- Cursor checks pass, output pasted
- Human checks pass
- `BUILD_PROGRESS.md`: S1a row, decisions log entry for the `per_message` fix
  and for keeping work domain as free text
- Committed and pushed
