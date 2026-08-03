# S1d · Onboarding personality — layout, emoji, reactions

**Slice:** S1d (final amendment to onboarding)
**Phase:** 1 — Foundation
**Depends on:** S1b, S1c
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Why this exists

Two problems, one structural and one tonal.

**1. Button labels truncate.** Two buttons per row leaves roughly 14 characters
each on a phone. "Speak without freezing up" renders as `Speak...zing up`. The
step-5 screen is currently unreadable.

**2. It reads like a form.** Every screen is a question and a list. Nothing
responds to what the user chose, so the bot feels like a survey rather than a
partner they'll talk to daily for six months.

## Scope note

This is the fourth onboarding pass. It is the last one. Anything that surfaces
after this goes into a backlog item for S18, not a new slice — onboarding is a
screen two people see twice, and S2 is the slice that makes the product work.

## Non-goals

- No change to the single-message wizard model, the questions asked, or the data
  stored.
- No change to `services/users.py`, the save transaction, or the schema.
- No LLM call. Every reaction is a static string chosen by lookup.
- No animated stickers mid-flow — they would break the single-message model.

---

## Change 1 · Layout rules that prevent truncation

**Rule:** two buttons per row only when *both* labels are ≤ 12 characters
including the emoji. Otherwise one per row.

| Step | Layout |
|---|---|
| 1 Name | one per row (2 buttons) |
| 2 Language | two per row — labels are short |
| 3 EF SET | one per row |
| 3b Self-assessment | one per row — descriptors are sentences |
| 4 Category | two per row |
| 4b Specifics | two per row where both fit, else one |
| 5 Why | **one per row** |
| 6 Focus | one per row |
| 7–8 Times | three per row for the presets, `Another time` on its own row |
| Confirm | two per row |

Add a helper that takes a list of `(label, callback)` pairs and lays them out by
this rule automatically, rather than hardcoding rows per screen. Any future
screen then gets correct layout for free.

Cursor must assert in a test that no button label exceeds 12 characters when it
shares a row.

---

## Change 2 · An emoji on every option

One emoji, leading, then a space. Never two. Never an emoji in the question text
itself — the buttons carry the colour.

### Step 2 · Language
`🇮🇷 Farsi` · `🇱🇹 Lithuanian` · `🇷🇺 Russian` · `🇵🇱 Polish` · `🌍 Other`

### Step 3 · EF SET
`📊 I know my score` · `🤷 Not yet`

### Step 3b · Self-assessment
- `🌱 I manage simple, everyday things`
- `🚶 I get by, but I hesitate a lot`
- `🏃 I'm comfortable — I want precision`

### Step 4 · Category
`📣 Marketing` · `💻 Tech` · `📊 Business` · `🩺 Health` · `🎓 Education` ·
`🎨 Creative` · `🔧 Trades` · `⚖️ Law & Public` · `🧭 Other`

Category labels shorten to fit two per row; the specifics screen carries the
detail, so nothing is lost.

### Step 5 · Why — one per row, full labels
- `😰 Speak without freezing up`
- `💼 Do better in meetings`
- `🚀 Get a better job`
- `🫂 Make friends here`
- `🎬 Watch films without subtitles`
- `😳 Stop feeling embarrassed`
- `✈️ Travel more easily`
- `🎓 Study or pass an exam`

Selected state prefixes a checkmark: `✅ 😰 Speak without freezing up`.

### Step 6 · Focus
`⚖️ A bit of everything` · `💼 Mostly work English` · `🏠 Mostly everyday English`

### Step 7–8 · Times
`🌅 07:00` `☀️ 08:00` `🌤 09:00` / `🕐 Another time`
`🌆 19:00` `🌙 20:00` `🌃 21:00` / `🕐 Another time`

### Confirm
`🚀 Start learning` · `✏️ Change something`

---

## Change 3 · The bot reacts to choices

After each answer, the next screen opens with **one short reaction line** based
on what was just picked, then a blank line, then the next question. This is the
change that makes it feel alive.

Reactions are static strings in `texts.py`, selected by lookup. No LLM.

### Examples

| Choice | Reaction line |
|---|---|
| Farsi | `Farsi speaker — articles and word order will be our battleground.` |
| Lithuanian | `Lithuanian — so articles will be the fun part.` |
| Not yet (EF SET) | `No problem. Rough guess is fine for now.` |
| Score 51–60 | `B2 already. Then we're sharpening, not building.` |
| Score 41–50 | `Solid B1. That's exactly the jump this is built for.` |
| Digital marketing | `Campaigns, clients, pitches. I'll pull examples from there.` |
| Software engineering | `Standups, code review, specs. Noted.` |
| Nursing | `Handovers and patient talk. That's a demanding register.` |
| Watch films without subtitles | `Good one — HIMYM's already on the plan.` |
| Speak without freezing up | `That's the one that changes everything.` |
| Get a better job | `Then we'll spend real time on interviews.` |
| Make friends here | `Small talk is harder than any grammar. We'll work on it.` |
| Mostly work English | `Work-heavy it is.` |
| 07:00 morning | `Early start. Respect.` |
| 21:00 evening | `Night owl. Noted.` |

Write a reaction for **every** option in every step. Where a category has many
specifics, one reaction per category is acceptable if a specific one would be
forced — but the named specifics above must have their own.

Rules:
- One line, under 60 characters.
- Never praise generically ("Great choice!"). `PRD.md` §8 forbids it.
- Never guilt, never pressure.
- The reaction replaces any previous error line; both never show at once.

Step 1 has no reaction — there is no prior answer.

---

## Change 4 · Warmer copy

Current questions are correct but clipped. Loosen them slightly, keeping one
line each.

| Now | Becomes |
|---|---|
| `What's your first language?` | `What's your first language?` *(unchanged — it's fine)* |
| `Do you know your EF SET score?` | `Do you know your EF SET score?` *(unchanged)* |
| `What field do you work in?` | `What do you do all day?` |
| `Why do you want better English?` | `Why does this matter to you?` |
| `What should we focus on?` | `Where should I aim the practice?` |
| `Here's your setup.` | `Right — here's the plan.` |

The greeting gains one line of intent:

```
Hi Amir 👋

I'm going to learn your mistakes and keep testing you on them until they're
gone. Eight quick questions first.

Should I call you Amir?
```

---

## Change 5 · One celebration sticker at the end

After the final message, send a single Telegram sticker. This is the only place
a third message is allowed, and it is a reward moment, not clutter.

Use a stock Telegram sticker via `send_sticker` with a file_id from a public
pack (e.g. the animated `🎉` from Telegram's own set). If no stable file_id can
be sourced, **skip this change entirely** and note it in the decisions log —
do not add a dependency or bundle a file to make it work.

Message count becomes **3** on the happy path: wizard, confirmation, sticker.

---

## Cursor verifies before handing back

1. `python -m pytest -q` — all 14 existing pass. `tests/test_onboarding.py`
   untouched; include `git diff --stat`.
2. New test: the layout helper never places two buttons on a row when either
   label exceeds 12 characters.
3. New test: every option in every step has a reaction string, and none exceeds
   60 characters. Fail if any option is missing one.
4. `python -m app.main` starts clean, no `PTBUserWarning`.
5. State the message count on a full run — 3 with the sticker, 2 without.

## Human verifies (Telegram)

1. Step 5 — every label reads in full. Nothing truncated anywhere in the flow.
2. Each screen after step 1 opens with a reaction to what you just picked.
3. Selected motivations show a checkmark and stay checked when you go back.
4. Emoji present on every button, one each.
5. Complete without typing. Still possible.
6. Does it feel like a partner now, rather than a form?

## Definition of done

- Cursor checks pass, output pasted
- All six human checks pass
- Both users onboarded — S1 finally closed
- `BUILD_PROGRESS.md`: S1d row, decisions log entry on the layout rule and the
  reaction system, sticker outcome noted either way
- Committed and pushed
- **Onboarding is closed.** Further polish goes to the S18 backlog.
