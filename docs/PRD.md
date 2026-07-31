# PRD — English Learning System

**Version 2.0 · 31 July 2026 · Supersedes english-system-spec.md v1.0**

---

## 1. Problem

Two adults in Vilnius at CEFR B1 want to reach B2 in six months. Every existing product fails them for the same reason: it does not remember their specific mistakes. Duolingo teaches a generic curriculum. A tutor remembers imperfectly and costs €15/hour. Sitcoms give input but no correction.

**The insight this product is built on:** the highest-value asset in language learning is a persistent, structured record of *your own* errors, and a system that keeps re-testing you on them until they disappear.

## 2. Users

| | User A | User B |
|---|---|---|
| Native language | Farsi | Lithuanian |
| Domain | Digital marketing | TBD at onboarding |
| Level | Measured via EF SET at onboarding | Measured via EF SET at onboarding |
| Relationship | Partners, living together — shared accountability is a design asset |

**Nothing in the system is hardcoded to these two languages.** `native_language` is a free field; all prompts are parameterised. A Spanish speaker learning English must work on day one with zero code changes.

## 3. Success criteria

| Metric | Baseline | Month 6 target |
|---|---|---|
| EF SET score | measured week 1 | B2 (57–70) |
| Mature Anki cards | 0 | 1,200+ |
| Error types resolved | 0 | 25+ |
| Voice sessions | 0 | 150+ |
| Active days | — | ≥65% |

"Resolved" = 5 consecutive correct answers on that error type across ≥3 weeks.

**Non-goals:** IELTS/TOEFL prep, academic writing, accent elimination, mobile app, web app.

## 4. Core loop

```
Real usage (voice, text, reading, mining)
        ↓
   Errors detected and typed
        ↓
   Written to error journal
        ↓
   Spaced re-testing (1→3→7→21→60 days)
        ↓
   Error type marked resolved
        ↓
   Proof of progress shown weekly  →  motivation  →  more real usage
```

Everything else in this document serves that loop.

## 5. Modules

### Core (Phases 1–3)

**M1 · Daily quiz.** 5 questions from the user's own due errors. Top up from studied book units if fewer than 5 are due. Spacing on failure: 1→3→7→21→60 days.

**M2 · Free correction.** Any text sent outside a task gets corrected and written to the error journal. Highest-value passive feature — turns ordinary usage into training data.

**M3 · Voice partner.** Voice in → transcribe → conversational reply as voice + correction block as text. 5–10 turn conversations. Never breaks character in the spoken part.

**M4 · Reading engine.** 3×/week. 300–400 words at the user's level on a topic from their interest profile. 5 comprehension questions, 5 extracted chunks. User rating adjusts topic weights.

**M5 · Book ingestion.** `/book` → user photographs 10–20 pages of Murphy / Vocabulary in Use / marketing books → vision model extracts unit number, title, target items. Enables "test me on unit 12" and grounds quizzes in the user's actual textbooks. Personal-use only.

**M6 · Anki export.** Weekly TSV posted to Telegram. Format: `sentence_with_gap ⇥ answer ⇥ meaning ⇥ source`.

**M7 · Motivation engine.** Streaks, freeze tokens, rescue mode, nudge ladder, Sunday report. Rules in §7.

**M8 · Couple challenge.** Shared group chat. One daily question, first correct answer wins. Sunday leaderboard, loser owes the agreed real-world stake.

### Added in brainstorming (Phase 3–4)

**M9 · Voice diary.** 60 seconds every night about your day. Lowest-friction speaking practice that exists; highest fluency return per minute. Correction is light-touch — max 2 errors — because the goal is volume, not precision.

**M10 · Load-up mode.** `/prep marketing budget meeting` → bot returns the 10 chunks and 3 sentence frames you'll need, 30 minutes before the real thing. Ties the system to actual work stakes, which is what makes people open it.

**M11 · Real-life capture.** Forward any English you encounter — a client email, a Slack message, a sign, a contract clause — and the bot explains it and mines chunks from it. Learning attached to real life instead of a curriculum.

**M12 · Shadowing.** Bot sends a 10–15 second audio clip from a mined scene. You repeat it. Whisper transcribes your attempt and compares word-for-word against the original. Targets pronunciation and rhythm, which correction alone never fixes.

**M13 · Anti-fossilization sweep.** Monthly, silently re-tests error types marked `resolved`. If one comes back, it un-resolves and re-enters rotation. Prevents the illusion of progress.

**M14 · Difficulty auto-calibration.** Rolling 30-question accuracy targets 75–85%. Above 85% for two weeks → raise level. Below 70% → lower it. Prevents both boredom and demoralisation.

**M15 · Watch-together.** Both users mine the same episode independently, then the bot cross-quizzes them on each other's chunks. Turns TV night into a shared session.

**M16 · Video engine.** Curated YouTube segments, 2×/week, complementing sitcoms. Selects on interest weights, track rotation and current level. Hard requirements: prefers videos with human-written captions over auto-generated ones (auto-captions are too inaccurate to mine from), returns one specific 3-minute segment rather than a whole video, and rotates accents deliberately — tracking exposure per accent and pushing toward unfamiliar ones. Uses the YouTube Data API (free quota is far more than sufficient).

**Media strategy.** The two sources do different jobs and neither is optional:

| | Sitcoms (Mon/Wed/Fri) | YouTube (Tue/Thu) |
|---|---|---|
| Teaches | idioms, fast casual speech, humour, social register | domain vocabulary, formal register, accent variety, long-form listening |
| Sources | HIMYM (Disney+/Trancy), The Office (Netflix/Language Reactor) | curated by M16, mined with Language Reactor |

Weekends are deliberately unstructured — extensive watching with no task attached. Input you enjoy without effort is a requirement, not a reward.

## 6. Content tracks

Three tracks. **Weights are per-user and dynamic** — set at onboarding, changeable via `/settings`, auto-adjusted by content ratings.

| Track | Default weight | Topics |
|---|---|---|
| Work | 40% | campaigns, client email, negotiation, standups, interviews, pricing, positioning |
| Life & Social | 40% | apartments, doctors, arguments, cooking, travel, humour, opinions, small talk |
| Curiosity | 20% | space, psychology, history, mysteries, technology, sport, nature |

Voice prompts, reading texts and quiz sentences all draw from the active track for that day.

## 7. Behaviour rules — non-negotiable

These separate a working system from a dead one. Implement exactly.

1. **Scheduled times are delivery times, not deadlines.** Tasks stay open until 03:00 the following night.
2. **Nothing expires.** Unanswered questions return to the queue. No content is ever lost.
3. **Maximum 2 nudges per day.** First at +3h, second at +6h and it must offer a *smaller* version ("no time? just do 2"). Never a third.
4. **Never guilt.** No "you failed", no "you broke your streak", no disappointed emoji. Neutral or warm only.
5. **Freeze tokens:** 2 per user per month, reset on the 1st, consumed automatically before a streak breaks.
6. **Weekly success = 5 active days out of 7.** Never judge against 7.
7. **Rescue mode:** 3+ consecutive missed days → daily task shrinks to 3 questions (~3 min) for 7 days. **No backlog is ever presented.** Backlog dumping is the primary cause of abandonment.
8. **Sunday report leads with progress**, specifically error types that have gone quiet. Shortfall comes second, briefly, or not at all.
9. **Hard ceiling: 3 bot-initiated messages per user per day.** Including nudges.

## 8. Bot message UX

The bot's interface *is* its copy. Rules:

- Under 400 characters for any scheduled message. Voice and reading are the only exceptions.
- One idea per message. Never stack a quiz, a tip and a reminder together.
- Corrections use a fixed visual shape so they're scannable:
  ```
  ✏️ "her english is not so much good"
  → her English isn't very good
  💡 "so much" doesn't go before adjectives. Use "very".
  📗 Murphy 101–102
  ```
- Explanations max 25 words, in English. Drop to the user's native language only for abstract grammar concepts, and only when `explanation_language_fallback` is enabled.
- Always name one specific thing done well. Generic praise is noise.
- Buttons over typing wherever a choice is being made.

## 9. Multi-tenancy and commercial path

**Build now (near-zero cost):**
- `tenant_id` and `plan` columns present but unused
- No language hardcoded anywhere; all prompts parameterised
- All queries scoped by `user_id`
- Config-driven bot identity (name, timezone, schedule)

**Do not build now:** payments, admin panel, landing page, ToS/privacy, onboarding funnel, analytics.

**Rationale:** the product is unproven until these two users reach B2. That result is the asset that makes commercialisation possible. Building billing in month 1 guarantees shipping nothing.

**Phase 5 path (month 6+):** Telegram Stars for in-bot payment — native to the platform, handles digital-goods flow. As an EU seller, VAT must be handled: Stars or a merchant-of-record such as Paddle does this; raw Stripe does not. Requires a legal entity in Lithuania.

## 10. Privacy

Voice recordings are transcribed and then deleted — never stored. The error journal contains personal writing and speech, so the database is treated as private data: encrypted disk, SSH-key-only access, no third-party analytics. If this ever becomes multi-tenant, GDPR obligations attach and must be handled before the first external user.
