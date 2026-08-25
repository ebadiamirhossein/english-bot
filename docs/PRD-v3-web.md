# PRD v3 — English Learning Web App

**Version 3.0 · 23 August 2026 · Supersedes PRD v2.0 (Telegram bot)**
**Codename:** the app formerly known as `english-bot`

---

## 0. What changed and why

v2 built a **reactive error-correction engine**. It works: correction, the error journal, the spacing ladder, calibration, streaks. That engine is the most valuable thing in the project and none of it is being thrown away.

What v2 never had:

| Missing | Consequence you actually felt |
|---|---|
| A syllabus | No answer to "what am I learning this week?" |
| A journey | No map, no stages, no sense of distance travelled |
| Explicit goals | Nothing to complete; nothing to fail; nothing to finish |
| A tracker of *knowledge*, not activity | Streaks measure attendance, not English |
| New material | The system only ever recycled your own mistakes — you cannot learn a word you have never met |
| An item-quality gate | Unanswerable questions shipped to production (§4.3) |
| A real UI | Chat bubbles cannot render a flashcard, a transcript, a waveform, or a progress map |
| In-app flashcards | Anki export was a hand-off, and a hand-off is a place where habits die |

v3 keeps the engine and builds the missing half: **a curriculum, a session structure, a knowledge model, and a real interface.**

**Platform:** installable PWA (mobile-first, works as an app on the phone home screen), served from a real domain. Telegram is demoted from *the product* to *a notification channel*.

---

## 1. The two loops

Everything in the product is one of two loops. Naming them prevents the v2 failure mode where every feature was its own island.

```
LOOP A — SYLLABUS (what you don't know yet)
  CEFR B1→B2 skill map → this week's unit → new grammar + new lexis
  → practice → checkpoint → unit marked mastered → next unit
                                    │
                                    ▼
LOOP B — PERSONAL (what you got wrong / met in the wild)
  Real usage: speaking, writing, video, series, reading
  → errors detected + words mined → journal + card deck
  → FSRS review → mastery → silent re-test (anti-fossilisation)
```

Loop A gives **direction**. Loop B gives **precision**. v2 had only B. Duolingo has only A. Having both is the entire thesis of this product.

**Every screen must be traceable to a loop.** If a feature belongs to neither, it does not ship.

---

## 2. The learner model — what the app actually knows about you

This is the biggest structural addition in v3, and everything else depends on it. Four ledgers:

### 2.1 Known-word ledger (`user_lexemes`)

One row per lemma per user. States: `unknown` → `seen` → `learning` → `known` → `mastered`.

Populated by: placement test, words tapped in a transcript, words you skipped over in a text you rated "easy", card reviews, corrections.

This unlocks everything the good apps do and v2 could not:

- **Automatic content selection.** For any video or text, compute *known-word coverage* = % of tokens whose lemma is in `known`/`mastered`. Comprehensible input means **95–98% coverage** — the "i+1" every single one of those YouTube transcripts talks about. Below 90% the learner drowns; above 99% they learn nothing. The app selects material by coverage, not by a hand-typed CEFR guess.
- **Honest progress.** "You know 4,180 words" is a real number that goes up. Streak days are not.
- **Vocabulary targets.** B1 ≈ 2,500–3,000 lemmas. B2 ≈ 4,000–5,000. The gap is roughly **1,500–2,000 new words in six months ≈ 10–12 new words a day.** That is the vocabulary budget of the whole programme, and it should be visible on the home screen.

Seed lemma difficulty from a merged frequency + CEFR list (SUBTLEX/COCA frequency bands + English Vocabulary Profile / CEFR-J level tags). Ships as a static table, ~15k rows.

### 2.2 Error journal (`errors`) — **unchanged, migrated as-is**

The 19-type taxonomy, the spacing ladder, resolution, the monthly anti-fossilisation sweep. This is the crown jewel of v2. It moves to the new app byte-for-byte. The rule from v2 stands: **a wrong entry is permanent damage, a missing one is recoverable** — only genuine self-produced errors are journaled.

### 2.3 Skill map (`syllabus_units`, `user_unit_state`) — **new**

The CEFR B1→B2 curriculum as an explicit graph (§3). Each unit has a state: `locked` → `available` → `in_progress` → `passed` → `mastered`. Mastery requires a checkpoint pass **plus** retained performance 3+ weeks later.

### 2.4 Card deck (`cards`, `card_reviews`) — **new, replaces Anki**

FSRS-5 scheduling, in-app. Details in §5.

---

## 2.5 Two learners, two native languages

The two learners have different native languages — Farsi and Lithuanian. Nothing in the product is hardcoded to either. `native_language` is a free field chosen at signup, every prompt is parameterised, and a Spanish speaker must work on day one with zero code changes.

### What follows from the L1 choice

| Surface | Behaviour |
|---|---|
| Card meaning gloss | rendered in the learner's L1 |
| **Production cards** | L1 → English. This is the highest-value drill in the deck (§5), so it must be genuinely idiomatic in *that* L1, not a word-for-word rendering of an English sentence |
| Grammar explanation fallback | L1, when `explanation_language_fallback` is on |
| Subtitle ladder, step 1 | English + L1 |
| Placement test | the Yes/No vocabulary section is L1-independent by design; only the production items need translating |

Everything else — the 24-week road, the deck mechanics, item types, pronunciation scoring, gamification — is identical for both learners.

### L1 subtitles are generated, not fetched

**YouTube has almost no Lithuanian subtitles, and Farsi coverage is patchy.** Depending on the platform's own translated captions would leave step 1 of the subtitle ladder (§7.5) empty for one learner and unreliable for the other.

So the app generates the L1 subtitle track itself, once per video segment, from the **English transcript we already have**, and caches it. Two benefits beyond availability: the L1 line is a translation of what was genuinely said rather than a machine translation of a machine transcription, and it is produced at the learner's level rather than literally.

### Per-L1 pronunciation seeds

The sounds a Farsi speaker finds hard and the sounds a Lithuanian speaker finds hard overlap only partly. The minimal-pair drill generator (§8) starts from a **per-L1 seed list of likely problem contrasts**, then adapts to the learner's actual Azure phoneme scores within the first two weeks. The seed list is a starting hypothesis, never a fixed diagnosis — the measured data overrides it.

### The error taxonomy is shared; the profile is not

The 19-type taxonomy is language-neutral and both learners write to the same `errors` structure. But which types dominate will differ, and the system discovers that from real errors rather than assuming it. No L1-specific error rules are hardcoded anywhere.

### Progression is independent

Each learner moves along the §3 map at their own speed. **They are not locked to the same unit.** Coupling their progression means one of them is permanently waiting or permanently behind, which is the fastest way to kill a shared habit.

What *is* shared: the Saturday couple challenge, the leaderboard, and watch-together sessions — where the question drawn from one partner's real mistakes is answered by the other. Shared accountability without shared pace.

---

## 3. The journey — 24 weeks, six stages

The thing v2 was missing. This is a visible map on the home screen, with your dot on it.

| Stage | Weeks | Can-do goal (the thing you can do at the end) | Grammar cluster (Murphy refs) | Lexical field |
|---|---|---|---|---|
| **1 · Tell me what happened** | 1–4 | Tell a 2-minute story about something that happened to you, without freezing | past simple/continuous, present perfect vs past simple, `used to`, time linkers (5–20, 25–28) | daily life, work routine, home, food, transport |
| **2 · Describe and compare** | 5–8 | Compare two options and justify a choice out loud | comparatives/superlatives, relative clauses, quantifiers, adjective order, articles (72–79, 92–100) | places, products, people, city life, apartments |
| **3 · Plans and what-ifs** | 9–12 | Run a planning conversation: propose, hedge, commit, change plan | future forms, conditionals 1 & 2, modals of possibility, `going to` vs `will` (19–24, 29–38) | projects, travel, appointments, deadlines |
| **4 · Say what you think** | 13–16 | Hold a position for 2 minutes, disagree politely, concede a point | discourse markers, passive, reported speech, modals of deduction (42–47, 48–52) | opinions, news, arguments, culture |
| **5 · Sound professional** | 17–20 | Run a client call and write a proposal email that doesn't read as translated | 3rd conditional, perfect modals, hedging, phrasal vs Latinate register, formal email conventions (38–41, 137–145) | marketing, pricing, negotiation, feedback, meetings |
| **6 · Range and repair** | 21–24 | Speak for 4 minutes on an unprepared topic; self-correct mid-sentence | collocation depth, idiom, connected speech, self-repair strategies, B2 exam task formats | everything; consolidation |

Each stage = 4 weekly units. Each **unit** ships with:

- one **can-do statement** ("I can describe a change I made and why"),
- 3–5 **grammar targets** with Murphy references. **Corrected at W8, 2026-08-25:**
  this line read *"already in `book_units` from v2's OCR"* and that was wrong.
  `book_units` is a **per-learner OCR study log** (`user_id NOT NULL`,
  `unit_number` free TEXT) recording which pages a learner photographed —
  roughly five units for one learner, deliberately left behind at the S18d
  re-onboard. It is a different namespace from `items.unit_number`
  (SMALLINT 1–24) despite the shared column name, and a *shared* syllabus
  row could not key to a per-learner one in any case. The references are
  **authored from the stage table above**, stored as TEXT ranges with no
  foreign key — the convention `error_types.murphy_units` already uses.
  **Stage 6 gives no range, so 20 of the 24 units carry one** and
  `murphy_units` is nullable per target, exactly as it is for the six
  `error_types` rows covering collocation, register and pronunciation,
- ~40 **target lexemes** chosen by frequency band ∩ topic ∩ *not already in your known-word ledger*,
- 3 **video/audio items** at 95–98% coverage,
- 1 **output task** (spoken and written variant),
- 1 **checkpoint** (12 items, 80% to pass).

**Personalisation, not deviation:** the unit sequence is fixed; the *content inside it* is generated against your error profile, your interests, and your known-word ledger. Two learners on Unit 7 see different sentences about the same grammar.

**If you fail a checkpoint:** the unit stays `in_progress`, the missed targets are injected into the next week's review queue, and you retake in 4 days. Never a blocked path, never a punishment screen. (v2 rule: drops are silent, raises are announced — carried forward.)

---

## 4. The daily session — the unit of use

The app opens on **one button: Start today's session.** Not a menu. The single biggest UX failure of a self-directed learning app is making the learner decide what to do.

### 4.1 Session anatomy (target 45 min, hard floor 12 min)

| Block | Min | What | Loop |
|---|---|---|---|
| **1 · Review** | 6–10 | FSRS due cards: vocab, phrases, error cards. Capped. | B |
| **2 · Input** | 15 | Video or audio at your coverage, interactive transcript, tap-to-save | A+B |
| **3 · Focus** | 8 | This week's grammar target: 90-second explanation + 8 generated items | A |
| **4 · Output** | 10–15 | Speak or write. Corrected. Errors → journal. | B |
| **5 · Close** | 2 | What you learned today, 3 lines. Tomorrow's preview. XP. | — |

### 4.2 Weekly rhythm

| Day | Session shape |
|---|---|
| Mon | Full · **video** (BBC Learning English / FluentU) · output: **speaking** |
| Tue | Light · **series episode** (HIMYM etc., mined via Trancy) · output: **writing** (journal, 5–10 sentences) |
| Wed | Full · **video** (Learn English With TV Series) · output: **speaking** |
| Thu | Light · **series** · output: **writing** (paragraph on a prompt, graded on structure) |
| Fri | Full · **video** (topic from your interest weights) · output: **speaking, unprepared** |
| Sat | **Checkpoint** (12 items) + couple challenge + watch-together |
| Sun | No tasks. Weekly report. Free extensive input, tracked but never required. |

Sunday being empty is deliberate and non-negotiable: input you enjoy without a task attached is a requirement of the method, not a reward.

### 4.3 The item quality gate — **fixes the bug you reported**

Your example:

> ⌨️ Type the missing word
> `Bahar texted: 'Head home if you want — ___ stay and push the deploy.'`

The intended answer is presumably `I'll`. But `I'd`, `I'm gonna`, `let me`, `I can`, and `I might` are all grammatical and idiomatic there. **The item has no unique recoverable answer, so it cannot be marked.** Any answer you type is a coin flip. This is not a prompt-tuning problem; it is a missing validation layer, and it is why the quizzes felt arbitrary.

**Rule: no item reaches a learner unless it passes three gates.**

1. **Uniqueness (blind-solver gate).** After generation, a second model call sees *only what the learner will see* — prompt text, cue, options — and must answer. If its answer ≠ the canonical answer (or an accepted variant), the item is ambiguous. Reject or repair.
2. **Recoverability.** The gapped token must be derivable from the visible sentence plus the cue. Never gap a proper noun, an unstated referent, or a free choice.
3. **Target alignment.** The gap tests the unit's target (grammar point or target lexeme), not an arbitrary function word.

**Repair before rejection** — add a cue rather than discard:

| Cue type | Example for the item above |
|---|---|
| First letter + length | `I'_ _ _` (4) |
| L1 gloss | (من می‌مونم) |
| Definition / function | *(future decision made now)* |
| Word bank | `I'll · I'd · I'm` |
| Convert to MCQ | 3 options, one clearly correct in context |

If a repaired item still fails the blind-solver gate, it is discarded and regenerated. Items are **cached with their validation record** — generation is expensive, validation is cheap to store, and a validated item bank grows over time.

**Item types (canonical set — no free-form LLM prose questions ever again):**

`mcq` · `cloze_cued` · `word_bank_order` · `error_spot` · `l1_to_l2_production` · `dictation` · `listening_gap` · `speak_repeat` · `speak_answer` · `match_pairs` · `collocation_pick`

`l1_to_l2_production` ("say this in English: …") is the highest-value drill in the set and v2 did not have it. Farsi → English forces *production* rather than recognition, which is exactly the input/output gap every one of those transcripts identifies as the reason people understand but can't speak.

---

## 4.6 Content balance — everyday English first

**This fixes the loudest complaint about v2: everything sounded like work.**

v2 defaulted to **Work 40%** and injected `work_domain` into nearly every prompt. The result was a system that talked constantly about campaigns, clients, Q3 results and deploys. The broken quiz item that triggered this whole rebuild was, not coincidentally, about *pushing a deploy*.

That is not how a person learns to live in a language. Living in English is your landlord, your neighbour, being tired, a bad haircut, arguing about a film, ordering the wrong thing, apologising for being late.

### New default weights

| Track | v2 | **v3** | Contains |
|---|---|---|---|
| **Everyday life & social** | 40% | **50%** | apartments, doctors, food, transport, weather, small talk, arguments, humour, plans with friends, complaints, apologies |
| **Curiosity & culture** | 20% | **30%** | film, music, science, history, sport, psychology, news, travel, things you find interesting |
| **Work** | 40% | **20%** | marketing, clients, meetings, email, negotiation |

Adjustable in settings, but **20% is the ceiling for Work unless the user explicitly raises it.**

### The naturalness gate

Alongside the item quality gate (§4.3), every generated sentence must pass a second check before it reaches a learner:

1. **Would a real person say this to a friend?** Not to a client, not in a report. If it reads like a Slack message or a textbook, it is rejected and regenerated.
2. **No domain jargon unless the item's track is Work.** No "deploy", "Q3", "stakeholder", "campaign performance", "onboarding flow" in a Life or Curiosity item.
3. **No textbook English.** A ban list: *"Indeed, it is quite interesting"*, *"I am very fond of"*, *"Let us discuss the matter"*. These are grammatically correct and nobody says them.
4. **Contractions by default.** *I'll, don't, we're, gonna* (marked informal). v2 produced written-register English and then tested it as if it were speech.

Work English appears in exactly three places: the 20% Work track, `/prep` before a real meeting, and Stage 5 of the journey. Nowhere else.

---

## 5. Flashcards — in-app, FSRS, Anki retired

Anki failed here for the obvious reason: it is a second app with its own sync, its own UI, and no knowledge of the rest of the system.

**Scheduler:** FSRS-6 (`py-fsrs` server-side, pinned `fsrs>=6.3.2,<7`). Not SM-2, not the v2 fixed ladder. FSRS models per-card difficulty/stability/retrievability and hits a target retention rate (set 0.90) with materially fewer reviews.

*This line read **FSRS-5** until W7 and is corrected there rather than quietly reconciled.* `py-fsrs` 6.x implements FSRS-6, which carries 21 parameters where FSRS-5 had 19; the 5.x line is still installable but is no longer maintained upstream. Pinning the deck's first day to an unmaintained line would have bought a document match and cost its own upgrade slice later, with a re-seed question attached. The wrapper is `core/cards/fsrs.py` — the only module in the repository permitted to `import fsrs` — and it runs with `enable_fuzzing=False`, because fuzz exists to spread thousand-card decks and here it would only make every due date irreproducible.

**The v2 fixed ladder (1→3→7→21→60) is retained for `errors` only** — error types are not cards and their spacing is tied to the resolution rule. Do not merge these two systems.

**Card types, auto-generated when a word or phrase is captured:**

| Type | Front | Back | Made for |
|---|---|---|---|
| Recognition | word in its mined sentence | meaning (English) + L1 gloss | reading/listening |
| **Production** | L1 gloss + context hint | the English word | speaking — the one that matters |
| Cloze-in-context | mined sentence, word gapped, cued | word | retrieval in context |
| Audio | TTS of the sentence | transcript | listening |
| Collocation | "make / do ___ a decision" | correct verb | naturalness |

Every card carries **the sentence it came from and where it came from** (video title + timestamp, episode, your own email). Context is what makes a card stick; bare word↔translation cards are why people quit Anki.

**Rules:** daily new-card cap (default 12, from the vocabulary budget in §2.1) · daily review cap (default 80) · leech at 6 lapses → card is rewritten with an easier cue, not suspended.

*This Rules line carried a fourth clause — **"Anki export stays as a one-click backup, because the learner should never be locked in"** — until 2026-08-25, and it is struck at W8a rather than quietly reconciled.*

**The clause was not stale and W7 did not misread it.** W7 built `GET /cards/export.tsv` *because this line specified it*, `ARCHITECTURE-v3-web.md` §6 listed the route as "PRD §5's backup", and the W7 row in `docs/TASKS-v3-web.md` carried it in both its Build and its Accept column. All three documents agreed with each other and with the code. **This is a product change across three consistent documents, not the correction of one drifted row**, and it is written down that way because the handover note that ordered it gave the opposite reason — that the W7 row contradicted the PRD — and the next reader will otherwise re-derive that false premise from the same three files.

**What changed is the judgement, not the facts.** §2.4 and the §0 failure table say the in-app deck *replaces* Anki, and the reason given there is that "a hand-off is a place where habits die". A one-click backup is still a hand-off: it is a second app with its own sync and its own scheduler, and a card exported into it stops being a card this system knows anything about. Keeping the door open cost a route, a module and a link on the one screen whose job is to be the deck. **The in-app reviewer is the flashcard system and there is no export from the web app.** `tests/test_web_shell.py` bans the path from `apps/api` and `apps/web` so it cannot return by someone reading a cached copy of this section.

**The v2 Telegram chunk exporter (`core/services/anki.py`) is a different surface** — a ✅-verified live path both learners use weekly — and it is untouched. It dies at W22 with the rest of the bot.

---

## 6. Placement test — signup, and repeated monthly

Yes, this is possible, and doing it properly is what makes progress measurable.

**Design: fixed calibrated item bank, adaptive delivery, ~12 minutes.**

1. **Vocabulary size (3 min).** Yes/No lexical decision test: 60 items, 40 real words sampled across frequency bands + 20 pseudowords. Score corrected for false alarms. Outputs an estimated vocabulary size ±300 words. Cheap, fast, validated in the literature, and it seeds the known-word ledger immediately.
2. **Grammar + usage (5 min).** 25 items adaptive over an A2–C1 bank tagged by CEFR and by the 19-type error taxonomy. Ladder: start at B1, step up on 2 consecutive correct, down on 2 wrong, stop when the band stabilises. Output: CEFR band **plus a per-error-type profile** that pre-seeds the journal with weak areas.
3. **Listening (2 min).** 6 short clips, increasing speed and accent variety, gap-fill.
4. **Speaking (90 s).** One prompt, free response, recorded. Scored by (a) Azure pronunciation assessment for accuracy/fluency/completeness and (b) an LLM rubric against CEFR descriptors for range, coherence, and accuracy.

**Critical design constraint: the bank is authored and fixed, not generated at runtime.** Comparable scores over time are only possible if the instrument doesn't change. Re-run monthly with non-overlapping item subsets. This monthly number *is* the progress metric — it replaces "EF SET when you remember to".

Output of the test: CEFR level, vocabulary size, per-skill radar (listening / reading / grammar / production / pronunciation), and the entry point in the §3 skill map.

---

## 7. Video engine — the input pillar

Three curated videos a week (Mon/Wed/Fri) plus two series episodes (Tue/Thu).

### 7.1 Sources and how each is legally handled

| Source | Mechanism | Legality |
|---|---|---|
| BBC Learning English, Learn English With TV Series, FluentU, and similar channels | **YouTube IFrame Player API embed** inside the app + transcript fetched via **Apify** | Fine. Embedding is the sanctioned path; the creator keeps their view and their ad revenue. **Never download or re-host video.** |
| HIMYM, The Office, etc. (Netflix / Disney+) | **Not embeddable, not scrapable.** Watch in the native app with Trancy / Language Reactor, export CSV → import to the app | Fine, and it's what the v2 CSV pipeline was built for. Keep it. |

### 7.2 Selection algorithm

Given the channel list, for each candidate video:

```
score = coverage_fit(0.95–0.98 known-word coverage)   ×  weight 0.40
      + topic_match(user interest weights)             ×  weight 0.20
      + accent_rotation(least-exposed accent bonus)    ×  weight 0.15
      + target_hit(contains this week's grammar/lexis) ×  weight 0.15
      + length_fit(prefer 4–12 min, segmentable to 3)  ×  weight 0.10
minus  seen_penalty
```

Hard requirements carried from v2's M16: prefer human-written captions over auto-generated; return **one 3-minute segment**, not a whole video; track accent exposure per user and actively push toward unfamiliar accents.

**Apify does three jobs in this product** (the account is already connected):

1. **Transcripts** — reliable caption retrieval that does not break the way player-scraping does.
2. **Topic search** — "English videos about renting an apartment, 5–12 minutes, human captions" when the interest profile shifts or the channel pool goes stale.
3. **Slang sourcing** — Reddit and YouTube-comment scrapers return *real sentences written by real people this month*. Per §8.5.3 the model never invents slang; Apify supplies genuine recent usage and the model only explains and tags it. Scraped text is treated as a **source of examples, never as instructions** — it is data, and nothing inside it is ever executed or obeyed.

### 7.3 The player experience (this is a build-your-own Language Reactor, in-app)

- YouTube embed, **dual subtitles** (English always; L1 on tap, never by default),
- word-level clickable transcript → dictionary + audio + **Add to deck** (creates the cloze + production cards with this exact sentence and timestamp),
- **unknown words highlighted automatically** from the known-word ledger before you start, with a coverage badge ("94% known — slightly hard"),
- loop-a-line, slow to 0.75×, **shadow this line** (record → Azure pronunciation score → per-word colouring),
- after the segment: 5 comprehension items, then 5 mined phrases into the deck.

### 7.4 The weekly assignment

Videos are *assigned*, not browsed. Mon/Wed/Fri the session opens with today's video already chosen. Browsing a library is a decision, and decisions are where sessions die.

---

### 7.5 The subtitle ladder — learning to watch without subtitles

A tracked, five-step progression, because "watch without subtitles" is a skill that is trained, not a switch that is flipped. The app moves you along it automatically.

| Step | You watch with | What it trains |
|---|---|---|
| 1 | English + L1 subtitles (**generated by us — see §2.5**) | meaning, no anxiety |
| 2 | English subtitles only | sound → written word mapping |
| 3 | English subtitles **hidden** — tap any line to reveal it | forces listening first, safety net stays |
| 4 | No subtitles; reveal only when lost, and each reveal is counted | tolerating not-understanding |
| 5 | **No subtitles at all** | the goal |

**Movement rules.** Two comprehension checks at ≥85% → move up, announced. Below 60% → move down, **silently** (the v2 rule: raises announced, drops silent). Reveals in step 4 are counted and shown as a number that goes down over weeks — that number is the honest measure of listening progress.

**Tracked separately per source type.** You will reach step 5 on BBC Learning English long before you reach it on *How I Met Your Mother*, because scripted sitcom speech is faster, overlapping, and full of idiom. Treating them as one skill would stall you. Two ladders: `youtube_curated` and `native_series`.

**Connected speech drills.** When a comprehension check fails on a line, the app checks *why*. If the failure is a reduction — *"what are you going to do"* heard as *"whatcha gonna do"*, *"did you eat"* as *"dja eat"* — it generates a listening drill for that exact reduction. This is the single most common reason a learner with good grammar cannot follow a film, and no amount of vocabulary study fixes it.

---

## 8. Speaking and pronunciation — the actual bottleneck

Every transcript in the project folder says the same thing: input is easy to get, output is where people are stuck. v2's voice partner was good but invisible and unstructured.

**Four speaking surfaces, in increasing difficulty (progressive/"easy-to-hard imitation"):**

1. **Shadow** — repeat a line from today's video. Scored per phoneme by Azure. Colour-coded playback of your own attempt.
2. **Retell** — listen to a 30-second segment, then say it in your own words. LLM scores content coverage + flags errors. (This is the imitation technique from the transcripts, and it is far more effective than parroting.)
3. **Answer** — respond to a prompt tied to the week's can-do statement. 60–90 s.
4. **Converse** — the v2 voice partner, ported, now with a visible turn counter and a transcript you can read afterwards.

**Pronunciation gets its own tracked skill.** Azure Speech pronunciation assessment returns accuracy / fluency / completeness / prosody plus per-phoneme scores. Persist per-phoneme accuracy per user → surfaces "your /θ/ and /w/ are the two costing you most" and generates targeted minimal-pair drills (ship/sheep, very/wary). No other feature in the app can do this, and no LLM can fake it.

**Privacy rule carried from v2, unchanged:** audio is transcribed/scored and discarded. Never written to disk, never stored. Only scores and corrections survive.

---

## 8.5 Register, slang and idiom

A B2 speaker is not someone who knows more words. It is someone who knows **which** word to use with **whom**. v2 had no concept of this at all: a phrase mined from HIMYM and a phrase mined from a client email entered the same deck with the same weight, and could come back in the same quiz.

### 8.5.1 Every card and item carries a register tag

Five values, on `cards`, `items`, and `user_lexemes`:

| Tag | Example | Where it's safe |
|---|---|---|
| `formal` | *I would be grateful if you could…* | client email, proposal |
| `neutral` | *Could you send me…* | anywhere — the default |
| `informal` | *Can you shoot me…* | colleagues, friends |
| `slang` | *That's a hard pass* | friends, and only when you're sure |
| `taboo` | swearing, insults | **receptive only — never taught for production** |

The tag is set at capture time by the same LLM call that writes the card, and it is visible on the card face. Nothing enters the deck untagged.

### 8.5.2 The receptive-first rule

**You learn slang to understand it. You learn neutral English to speak it.**

This is the rule that protects you. Slang used slightly wrong sounds worse than plain English used correctly — especially in a marketing job, in a second language, with a client. So:

- `slang` and `informal` cards are created as **recognition and listening cards only**.
- A slang item is *promoted* to a production card only after you have already mastered the neutral equivalent of the same idea.
- `/prep` and any work-context generation **filters out `slang` and `taboo` entirely**. A client-call prep sheet must never suggest *"that's a hard pass"*.
- The Tue/Thu series sessions (HIMYM etc.) are where slang mostly arrives, and that is correct — those sessions are tagged as informal input by design.

### 8.5.3 Slang must come from real input, not from a list

Two hard reasons:

1. **Slang lists go stale fast.** A "100 English slang words" list is mostly 2015 English. Teaching it makes you sound dated, which is worse than sounding formal.
2. **The model's knowledge has a cutoff.** An LLM asked "what's new slang in 2026" will confidently invent things or give you 2023. It cannot be trusted as a *source* of current slang.

So the pipeline is inverted: slang is **detected**, never **generated**. It arrives from the video transcript, the series subtitle export, the Reddit comment, the Slack message you forward. The LLM's job is only to *explain and tag* something that was actually said by a real person, recently, in real context. That it can do reliably.

### 8.5.4 What each slang card must show

A bare "hard pass = refusal" card is useless and slightly dangerous. Every `informal`/`slang` card shows four things:

- **the line it came from**, with source and timestamp,
- **the meaning**, in plain English,
- **the neutral equivalent** — the safe thing to say instead,
- **who says this and to whom** — one line. *"Friends and casual colleagues. Fine in Slack. Not in a client email."*

Idioms and phrasal verbs use the same card shape, because they fail for the same reason: learners know the meaning and misjudge the situation.

### 8.5.5 Phrasal verbs get explicit curriculum space

Phrasal verbs are the single biggest reason B1 speakers sound non-native, and they cannot be learned from context alone at any reasonable speed. Stage 5 of the journey (§3) makes the **phrasal vs Latinate register pair** an explicit target: *put off / postpone*, *find out / discover*, *bring up / raise*, *cut down on / reduce*. You learn both sides of the pair and which situation each belongs to.

### 8.5.6 "What does this mean?" — the ad-hoc surface

Anywhere in the app: paste or tap anything you didn't understand and get back meaning, register tag, neutral equivalent, and an **Add to deck** button. This is the v2 real-life capture feature (M11), kept, with register added. It stays barred from writing to the error journal — that is someone else's English, and journaling it corrupts the record of your own mistakes.

---

## 9. Gamification — the honest kind

The brief was explicit: *really learn English, not play.* So:

**Ship:**
- **XP weighted by cognitive effort.** Production > recognition. Speaking a sentence: 10. Typing an L1→L2 production item: 6. Tapping an MCQ: 2. This makes the score mean something, and it makes gaming it identical to studying properly.
- **The skill map** (§3) as the primary progress surface — stages, units, mastery bars. This is the "journey" screen.
- **Words you know**, a real number from the known-word ledger, with the 6-month target line.
- **Weekly goal in minutes**, not days. 5 active days out of 7 (v2 rule, unchanged).
- **Streak with 2 freeze tokens/month**, auto-consumed (v2, unchanged).
- **Checkpoint = the boss fight.** Saturday, 12 items, pass at 80%, a real ceremony on passing.
- **Monthly placement re-test** as the level-up event. Levels change on measurement, never on vibes.
- **Couple leaderboard** with your partner only. Never strangers.

**Do not ship:** hearts/lives, gems, purchasable streak repair, global leaderboards, daily-loss anxiety mechanics, "you're 3 XP behind Sarah". These increase engagement and decrease learning, which is the exact trade this project exists to refuse.

**Guilt ban (v2 §7.4) applies to every string in the new UI**, and the banned-phrase test moves over with it.

---

## 10. Notifications

Telegram stays — as a **notification channel with deep links**, not an interface. It is already built, already reliable, already on both phones, and it dodges the entire iOS web-push mess.

- Web Push for installed PWA (works on iOS 16.4+ once added to home screen) as the primary channel.
- Telegram as fallback and as the couple-challenge surface.
- **Ceiling of 3 pushes/day/user across both channels combined** (v2 rule, unchanged).
- The v2 bot's teaching handlers are retired once the web equivalents are verified — no double maintenance.

---

## 11. Success criteria

| Metric | Baseline | Month 6 target |
|---|---|---|
| Placement test CEFR band | measured week 1 | B2 |
| Known-word ledger size | measured week 1 | +1,800 lemmas |
| Units mastered | 0 | 20 / 24 |
| Error types resolved | carried from v2 | 25+ |
| Speaking minutes produced | 0 | 900+ (≈5 min/active day) |
| Pronunciation accuracy (Azure, rolling) | measured week 1 | +12 points |
| Subtitle ladder — curated YouTube | step 1 | **step 5 (no subtitles)** |
| Subtitle ladder — native series | step 1 | step 3–4 |
| Active days | — | ≥65% |
| Cards mature (interval ≥21d) | 0 | 1,200+ |

**Non-goals for v3:** native iOS/Android apps, multi-tenancy, payments, public launch, IELTS/TOEFL prep, accent elimination. All Phase 5, all after B2.

---

## 12. Rules carried forward from v2 — non-negotiable

Unchanged, and the tests that enforce them move to the new repo:

1. Scheduled times are delivery times, not deadlines. Nothing expires.
2. Never guilt. No "you failed", no broken-streak message, no disappointed emoji.
3. A week is 5 active days out of 7. Never judged against 7.
4. Max 3 system-initiated messages per user per day, all channels combined.
5. Rescue mode after 3 missed days: session shrinks to 3 items for 7 days. **No backlog is ever presented.**
6. Level raises announced, drops silent.
7. The error journal is the product. Only genuine self-produced errors are written to it — never captured text, never typos, never ASR mishearings.
8. Privacy: audio transcribed and discarded; diary transcripts never stored; logs never contain message bodies; the operator panel shows activity, never content.

---

## 13. Open decisions for the human

1. **Domain name** — needed before deploy.
2. **Does the partner want the same syllabus stage, or independent progression?** (Recommendation: independent progression, shared Saturday challenge.)
3. **Series choice for Tue/Thu, weeks 1–8.** HIMYM is a good B1→B2 fit; The Office is harder (overlapping speech, mumbling).
4. **Retire the bot at which point** — recommendation: after web parity on correction + quiz + review is verified live, keep notifications only.
