# S1b · Onboarding rebuild — single-message wizard

**Slice:** S1b (replaces the interaction model from S1 / S1a)
**Phase:** 1 — Foundation
**Depends on:** S1, S1a
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Why this exists

S1a followed its spec correctly and the result still reads badly. The spec was
wrong, not the implementation. Two root causes:

**1. Message accumulation.** Eight questions produce twelve or more bubbles. The
user scrolls through a transcript of their own interview. Duolingo, Tinder and
every well-regarded onboarding show *one screen at a time* that replaces itself.
Telegram's equivalent is editing a single message in place. Echoing answers into
new bubbles (S1a change 1) treated the symptom and made the wall taller.

**2. Forced typing produces worse data, not just friction.** S1 required three
free-text answers. The real answer given for the why-statement was
`social talking` — two words that S10 is meant to quote back as motivation. A
preset option would have produced a better sentence than the user was willing to
type. Buttons here are not only easier; they yield higher-quality input.

`PRD.md` §8 already says *buttons over typing wherever a choice is being made*.
S1 did not follow it.

## Goal

Onboarding completes in **eight taps and zero typing** on the common path, inside
**one message** that never leaves a trail.

## Non-goals

- No change to `services/users.py`, the save transaction, or the schema.
- No change to what is stored — same fields, same types.
- No change to validation rules for the free-text escape hatches.
- No Telegram Mini App (see *Deferred* at the end).
- Interest questions remain S9. `/settings` remains S18.

---

## The interaction model

One message. Sent once at `/start`, then `edit_message_text` on every step.
Never send a second message until the final confirmation.

Each step renders as:

```
●●●○○○○○

What do you work in?
This shapes the examples I'll use.

[ Marketing ]  [ Tech ]
[ Healthcare ] [ Business ]
[ Something else ]
```

- Filled circles = completed steps. Eight total.
- Question in bold, one line.
- At most one line of helper text. Often none.
- Two buttons per row where labels are short.
- Every step except step 1 has a `← Back` button in the last row.

**Back must work.** Answers live in `context.user_data`; stepping back re-renders
the previous question with the previous choice still selected. This is standard
in every onboarding the user named and its absence makes a wizard feel like a
trap.

---

## Steps

### 1 · Name — prefilled, not asked

Telegram already provides it. Use `update.effective_user.first_name`.

```
●○○○○○○○

Hi Amir 👋
I'm your English practice partner.
Should I call you Amir?

[ Yes, that's me ]
[ Call me something else ]
```

"Something else" → free text, then straight to step 2. This is the only place a
name is ever typed.

If `first_name` is empty (rare but possible), fall back to asking directly.

### 2 · Native language

```
●●○○○○○○

What's your first language?

[ Farsi ]  [ Lithuanian ]
[ Russian ] [ Polish ]
[ Other ]
```

"Other" → free text → store lowercased. Store ISO 639-1 for the known four
(`fa`, `lt`, `ru`, `pl`), matching the schema comment.

### 3 · EF SET score

```
●●●○○○○○

Do you know your EF SET score?
It's a free 50-minute test — we can do this later.

[ I know my score ]
[ Not yet — start me at B1 ]
```

"I know my score" → free text, validated 1–100, mapped per the S1 table.
"Not yet" → `efset_baseline` NULL, `cefr_level` `B1`.

### 4 · Work domain

```
●●●●○○○○

What do you work in?
This shapes the examples I'll use.

[ Marketing ]   [ Tech ]
[ Healthcare ]  [ Business ]
[ Education ]   [ Trades ]
[ Something else ]
```

"Something else" → free text, kept verbatim. The free-text path stays because
`work_domain` feeds content generation in S9 and S14 and specificity there is
worth real money; but nobody is *forced* through it.

### 5 · Why — multi-select

```
●●●●●○○○

Why do you want better English?
Pick as many as you like.

[ ✓ Speak with people ]
[   Do better at work ]
[   Feel more confident ]
[ ✓ Travel more easily ]
[   Study or exams ]
[ Done → ]
```

Tapping toggles the checkmark and re-renders. `Done` proceeds. At least one
selection required — `Done` with none selected re-renders with a one-line nudge,
it does not advance.

Store as a single natural sentence built from the selections, because S10 quotes
this back verbatim:

> "I want to speak with people and travel more easily."

Order the clauses as listed above, join with `and` for two, commas plus `and` for
three or more.

### 6 · Focus

```
●●●●●●○○

What should we focus on?

[ A bit of everything ]
[ Mostly work English ]
[ Mostly everyday English ]
```

Same three presets and weights as S1 (40/40/20, 60/25/15, 25/60/15).

### 7 · Morning time

```
●●●●●●●○

When should the morning task arrive?

[ 07:00 ] [ 08:00 ] [ 09:00 ]
[ Another time ]
```

### 8 · Evening time

Same shape. `[ 19:00 ] [ 20:00 ] [ 21:00 ] [ Another time ]`

"Another time" → free text `HH:MM`, validated as in S1.

### 9 · Confirm

```
●●●●●●●●

Here's your setup.

Amir · Farsi · B1
Digital marketing
Balanced — work 40 · life 40 · curiosity 20
Morning 07:00 · Evening 20:00

"I want to speak with people and travel more easily."

[ Start learning ]  [ Change something ]
```

`Change something` returns to step 1 with every answer preserved, so the user
taps through and adjusts only what they want. It is not a reset.

### 10 · Done

Only here does a second message get sent — a fresh one, so the completed setup
stays visible above it:

```
You're set, Amir.
First task lands tomorrow at 07:00.
```

---

## Free-text handling inside a single-message wizard

When a step needs typed input, the wizard message stays put and shows the prompt
with a `← Back` button. The user's typed reply appears as their own bubble —
unavoidable, and fine, because it is *their* message, not bot clutter. On
receipt: delete nothing, edit the wizard message to the next step.

Invalid input re-renders the same step with a short correction line above the
question. Never a separate error message.

---

## Rendering rules

- Progress dots on their own first line, always eight characters.
- Question bold via Markdown. Helper text plain, one line maximum.
- No emoji in questions. One in the greeting, none elsewhere — the progress dots
  are the visual language.
- Every message under 400 characters (`PRD.md` §8).
- Button labels under 20 characters so two fit per row on a phone.

## Copy principles

Warm, short, and never explaining itself. Compare:

| Don't | Do |
|---|---|
| "Step 3 of 8 — What's your EF SET score? If you haven't taken it yet, tap Not yet — we can fill it in later." | "Do you know your EF SET score?" + a `Not yet` button |
| "What do you work in? Be specific if you can — it shapes the examples I'll use. e.g. digital marketing, AI engineering, nursing" | "What do you work in?" + six buttons |

The instructions disappear because the buttons *are* the instructions.

---

## Second `/start`

Unchanged from S1 in behaviour: show the profile summary with
`Change something` / `Keep as is`. Render it in the same single-message style so
it matches.

---

## Cursor verifies before handing back

1. `python -m pytest -q` — all 7 tests pass unchanged. `services/users.py` must
   not be modified; include `git diff --stat app/services/users.py` proving it.
2. Add `tests/test_why_sentence.py`: the why-statement builder produces correct
   grammar for one, two, three and five selections.
3. `python -m app.main` starts with no `PTBUserWarning`. Paste the log.
4. No new dependency.
5. Count the bot messages a full run produces. It must be **two** — the wizard
   and the final confirmation. State the number in your reply.

## Human verifies (Telegram)

1. `/start` → complete the whole flow. Confirm **no new bot bubbles appear**
   between the first message and the final one.
2. Reach step 6, tap `← Back` three times, then forward again. Previous answers
   still shown as selected.
3. Multi-select: choose three reasons, confirm the sentence in the summary reads
   as correct English.
4. Complete without typing anything at all. Possible?
5. `Change something` at the summary → answers preserved, not reset.
6. Read it as a whole. Does it feel like an app now?

## Definition of done

- Cursor checks pass, output pasted, message count = 2
- All six human checks pass
- Both users onboarded
- `BUILD_PROGRESS.md`: S1b row, decisions log entry explaining why the S1/S1a
  interaction model was replaced
- Committed and pushed

---

## Deferred: Telegram Mini App

The honest ceiling on the above is that it is still a chat message. Real
Duolingo-grade onboarding — full screens, illustrations, animation — needs a
**Telegram Mini App**: an HTML page opened inside Telegram from a button.

Not now. It requires HTTPS hosting and a web layer that `ARCHITECTURE.md` §2
deliberately excludes, and it would serve exactly two users who onboard once.
Revisit at **S23** (landing + onboarding funnel), where a Mini App and the
landing page share the same design work and the same hosting.
