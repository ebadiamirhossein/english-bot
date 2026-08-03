# S1c · Onboarding content — level, domain, motivation

**Slice:** S1c (amends S1b)
**Phase:** 1 — Foundation
**Depends on:** S1b
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Why this exists

S1b fixed the interaction model. The *content* of three questions is still weak,
and each weakness has a downstream cost.

| Problem | Cost |
|---|---|
| "Not yet" silently sets B1 with no evidence | Every reading text, quiz and voice prompt is mis-pitched until M14 calibration arrives in S12 — a whole phase away |
| Work domain collapsed to 6 broad categories | "Marketing" generates generic content where "digital marketing" generates campaign and client scenarios. `work_domain` drives S9 reading and S14 `/prep` |
| Motivation options are generic and polite | S10 quotes `why_statement` back verbatim during motivation dips. "Speak with people" motivates nobody |

## Non-goals

- No change to the single-message wizard model from S1b.
- No change to `services/users.py`, the save transaction, or the schema.
- No LLM call. Everything here is static buttons.
- No placement *test* — that would need S2's LLM and 5+ minutes of user time.

---

## Change 1 · Self-assessment replaces the silent B1

Step 3 currently ends the EF SET branch by assigning B1. Insert one screen after
"Not yet".

```
●●●○○○○○

Roughly where are you in English?

[ I manage simple, everyday things ]
[ I get by, but I hesitate a lot ]
[ I'm comfortable — I want precision ]
[ ← Back ]
```

| Button | `cefr_level` |
|---|---|
| I manage simple, everyday things | `A2` |
| I get by, but I hesitate a lot | `B1` |
| I'm comfortable — I want precision | `B2` |

`efset_baseline` stays NULL either way. These are CEFR can-do descriptors, which
is how the Council of Europe's own self-assessment grid works — people place
themselves far more accurately against described behaviour than against a label
like "intermediate".

This does **not** add a step to the progress dots. It is a substep of step 3,
same as "I know my score" is.

Users who tap "I know my score" skip this screen entirely — a real EF SET number
beats self-assessment.

### Follow-up nudge

Because self-assessment is a stopgap, the final message gains one line when
`efset_baseline` is NULL:

```
You're set, Amir.
First task lands tomorrow at 08:00.

When you have 50 minutes, take the free EF SET — I'll tune everything to your
real level. Just send me the score.
```

Do **not** build a reminder job for this. That belongs with the nudge ladder in
S10.

---

## Change 2 · Work domain becomes a two-tap drill-down

Step 4 shows a category, then a specific role. Both screens are buttons; typing
stays available but is never required.

### Screen A — category

```
●●●●○○○○

What field do you work in?

[ Marketing & Sales ]    [ Tech & Data ]
[ Business & Finance ]   [ Health & Care ]
[ Education ]            [ Creative & Media ]
[ Trades & Services ]    [ Law & Public ]
[ Studying / Other ]
[ ← Back ]
```

### Screen B — specific

Each category opens 4–6 specifics plus an escape hatch. Store the **specific**
label as `work_domain`, lowercased.

| Category | Specifics |
|---|---|
| Marketing & Sales | Digital marketing · Content & social · Sales · Brand & PR · Market research |
| Tech & Data | Software engineering · Data & AI · IT & infrastructure · Product management · QA & testing · Design (UX/UI) |
| Business & Finance | Finance & accounting · Operations · HR & recruiting · Consulting · Logistics · Entrepreneur |
| Health & Care | Medicine · Nursing · Dentistry · Pharmacy · Therapy & rehab · Care work |
| Education | Teaching · Academic research · Training & coaching · Education admin |
| Creative & Media | Design · Writing & editing · Film & video · Music · Photography |
| Trades & Services | Construction · Automotive · Hospitality · Retail · Beauty · Driving & transport |
| Law & Public | Law · Government · Non-profit · Police & emergency |
| Studying / Other | Student · Between jobs · Parenting full-time · Retired · Something else → free text |

Screen B always ends with `[ Something else ]` (free text) and `[ ← Back ]`,
where Back returns to screen A, not to step 3.

Both screens share step 4's progress dots.

---

## Change 3 · Motivation options that mean something

Replace step 5's five options with eight that describe real situations. Multi-
select as in S1b; the sentence builder is unchanged apart from the new clauses.

| Button | Clause used in the sentence |
|---|---|
| Speak without freezing up | speak without freezing up |
| Do better in meetings | do better in meetings |
| Get a better job | get a better job |
| Make friends here | make friends here |
| Watch films without subtitles | watch films without subtitles |
| Stop feeling embarrassed | stop feeling embarrassed about my English |
| Travel more easily | travel more easily |
| Study or pass an exam | study or pass an exam |

Rationale for the additions: both users are immigrants in Vilnius, and nothing in
the S1b list touched living abroad, local friendships, or the specific work
situations — meetings, interviews — that produce daily practice pressure.
`PRD.md` §5 M10 is built entirely around real work stakes.

Sentence assembly is unchanged: listed order, `and` for two, commas plus `and`
for three or more.

```
"I want to speak without freezing up, do better in meetings, and make friends
here."
```

Nine buttons plus Done plus Back is a long screen. Lay the eight out two per row.

---

## Cursor verifies before handing back

1. `python -m pytest -q` — 12 existing pass. `tests/test_onboarding.py` must be
   untouched; include `git diff --stat` proving it.
2. Extend `tests/test_why_sentence.py` for the new clause set, including a
   six-selection case.
3. Add a test that each self-assessment button maps to the correct
   `cefr_level`, and that `efset_baseline` stays NULL on that path.
4. Add a test that every category in the drill-down table has at least four
   specifics and that no specific label exceeds 20 characters (button width).
5. `python -m app.main` starts clean, no `PTBUserWarning`.
6. Message count on a full button-only run is still **2**. State it.

## Human verifies (Telegram)

1. `/start` → "Not yet" → self-assessment screen appears → pick the middle
   option → summary shows B1.
2. `/start` → "I know my score" → type `55` → summary shows B2 and skips the
   self-assessment screen.
3. Work domain: pick Tech & Data → Data & AI. Summary shows the specific, not
   the category.
4. On screen B, `← Back` returns to the category list, not to the EF SET
   question.
5. Pick three motivations. The sentence is correct English.
6. Complete the whole flow without typing. Still possible.
7. With EF SET skipped, the final message includes the EF SET line.

## Definition of done

- Cursor checks pass, output pasted, message count = 2
- All seven human checks pass
- Both users onboarded
- `BUILD_PROGRESS.md`: S1c row, decisions log entry covering the self-assessment
  fallback, the drill-down, and why the motivation list changed
- Committed and pushed
