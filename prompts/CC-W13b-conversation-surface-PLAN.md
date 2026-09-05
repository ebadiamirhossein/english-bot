# W13b — The conversation surface. PLAN ONLY.

**Mode: PLAN. Nothing is built by this pass.** No code, no test, no migration, no
`.sql`, no `apps/web` change, no server step, no billed call. `schema_version`
stays at **24**. No slice is marked ✅. W13b stays **⬜ NOT STARTED**.

---

## Context — why this plan exists and what it is for

`docs/TASKS-v3-web.md:82` has carried W13b since 2026-08-31 with the words
**PLAN ONLY UNTIL THE FIVE QUESTIONS ARE RULED**, and `PRD §8.6` has carried the
five. Four of them are ruled in this pass (operator, 2026-09-04, recorded in §0
and §2). The fifth — the cap's *number* — is the operator's and is proposed here
with a default, not taken.

The slice exists because of **#303**: nothing in the daily loop makes the learner
speak. Block 4 says *Say something of your own* and the button says *Write it*.
W13b is the owning slice.

It was blocked, until now, by something larger than the five questions: the
standing ruling of 2026-08-27. §0 settles that first, because everything else
in this document rests on it.

---

## §0 — The ruling that unblocks this, and what it costs

### §1a IS AMENDED FOR CONVERSATION. Assistant-recommended, operator-accepted, 2026-09-04.

**The standing ruling of 2026-08-27, verbatim** (`BUILD_PROGRESS.md:576`):

> **OPERATOR RULING 1 — CHECKPOINT GENERATION IS HUMAN-RUN, NEVER UNATTENDED.
> The app never generates while a learner waits, and never while nobody is
> watching.**

**The first half does not hold for a conversation surface, and this plan says so
plainly rather than arguing around it.** A reply *is* generation. A learner *is*
waiting. There is no version of conversation where that is untrue — a
pre-generated reply is not a reply, and a conversation whose turns were written
before the learner spoke is a script.

**W14's argument does not reach this and must not be stretched to.** W14/A's
boundary, verbatim, so it cannot be widened by analogy:

> *"The ruling governs **generation** — a model producing content a learner will
> read or study. It does not govern **measurement** of something the learner has
> just produced, where no content is created, nothing enters a deck, the journal
> or the item bank, and a learner is present by construction."*

A conversation reply **is a model producing content a learner will read**. It is
generation on W14's own definition. W14's escape is unavailable here and this
plan does not attempt it. What is asked for is an **amendment**, not an
interpretation.

### The three accepted costs. Each is a cost, not a solved problem.

**COST 1 — UNBOUNDED COST PER SESSION, AND THE PROJECTION CANNOT BE TRUSTED.**
A learner talks as long as they like. **#321** measured a printed floor of
`$0.000118` against a console charge of `$0.58` — a multiplier of ~4,900× — and
its own verdict is that *"the estimator does not need a correction; it needs a
different model."* That was Apify, not Anthropic; the transferable lesson is not
the multiplier but the shape: **a figure precise enough to trust and wrong enough
to matter is worse than no figure.** So this plan **predicts tokens, which can be
counted exactly, and refuses to predict dollars.** The dollar figure is read from
the Anthropic console after the first session, and **a measured first session is
owed before any second one** (§3.5).

**COST 2 — NO GATE CERTIFIES A GENERATED REPLY.** That was #196's original reason
for the ruling and nothing has changed it. §2 of that row: *"no gate certifies an
item"*. A conversation reply is content a learner reads with nothing behind it.
Stated exactly, because the row is entitled to know which half is which:

| Gate | Available on a conversation turn? |
|---|---|
| Blind-solver / uniqueness gate | **NO.** There is no canonical answer to solve for. The gate is undefined on this object, not merely expensive. |
| Naturalness gate — the *model* half (`judge_naturalness`) | **NO, refused.** A second billed call on every turn, doubling cost 1 and the wait of cost 3; and **#306** records that it does not batch at all. |
| Naturalness gate — the *offline* half | **YES.** `naturalness.jargon_hits(text, track=...)`, `textbook_hits`, `uncontracted` are pure functions, free, synchronous. **Recorded, not enforced** (#271: a guard can refuse a draft, never show the model understood). |
| Guilt scan | **YES, and ENFORCED.** `copy_rules.content_offenders()` is a compiled regex, free, in-request. This is the one gate that refuses. |
| Coverage band | **YES, measured; NOT enforced** — ruled ship-and-record, §2 below. `coverage_for(conn, user_id, text)` is offline and free. |

**So the honest answer to *what can gate a reply* is: one refusing gate (guilt),
two measuring gates (coverage, offline naturalness), and nothing that certifies
the English is good.** The plan claims exactly that and no more.

**COST 3 — THE WAIT IS THE PRODUCT.** 2–4 seconds per turn is what conversation
costs and is not a defect. **No spinner apologises for it.** The precedent is
W14/N, which measured the shadow round trip at 623–993 ms and put a plain state
on the screen; the conversation state is the same shape and says nothing about
speed, nothing about *thinking*, and carries no progress bar implying it could
be faster. A conversation with a person has this wait too.

### What still holds after the amendment — written down so it does not erode further

**This is the second amendment to that ruling in two days** (W13-ii/1 held it by
construction on 2026-09-02; W14/A carved measurement out of it on 2026-09-03).
A rule amended twice in two days is a rule about to become a preference. So:

1. **THE APP DOES NOT GENERATE UNATTENDED.** The second half of the 2026-08-27
   ruling is **untouched**. Nothing in W13b is scheduled, nothing runs in a
   worker, nothing generates while nobody is watching. `assign_daily` gains no
   job and `tests/test_worker.py::test_assign_daily_is_registered_and_creates_no_content`
   is not edited.
2. **THE APP DOES NOT GENERATE MATERIAL A LEARNER WILL STUDY WITHOUT A GATE.**
   A conversation turn is **not study material**: it enters no deck, no item
   bank, no `cards`, no `items`, no `grammar_lessons`. It is **deleted** (§2a).
   The only thing that survives it into the product is **≤2 corrections in
   `errors`**, and those pass the guards in §2d before they are written.
3. **A conversation turn is neither of those two things**, which is precisely
   why the amendment is narrow. It licenses **one object**: an ephemeral,
   deleted, non-studied turn in a surface a learner opened deliberately, bounded
   by a per-day cap. It licenses nothing else, and any later slice citing §0 has
   to show its object is that object.

---

## §1 — The reconcile, before planning

### 1.1 W13b's row, in both halves

`docs/TASKS-v3-web.md`'s **two halves** are named by the file itself
(`:161-167`): *"in BOTH halves of this document — this table and the per-slice
Build columns"*.

* **Half 1 (per-slice Build columns), `docs/TASKS-v3-web.md:82`, Phase D.**
  **Mode: `PLAN`.** The row is present and complete.
* **Half 2 (the authoritative migration table, `:115-133`).**
  **W13b HAS NO ROW, AND THAT IS CORRECT.** The table runs 009→025 and W13b
  appears nowhere in it, deliberately: *"NO NUMBER IS TAKEN HERE: it is claimed
  by the commit that writes the `.sql`"*. W13c, W13d, W15, W16, W17 and
  W19–W23 are absent for the same reason.
* **`BUILD_PROGRESS.md:162`** carries the slice-status row at **⬜ not started —
  mode PLAN**.

**What the row deliberately does not restate:** PRD §8.6 is the spec. The row
says so in its first sentence and this plan honours it — §8.6's five questions
are cited by number, never re-copied, per PRD §13's own rule (*"One copy, in
§8.6 — two copies of a list of open questions drift, and the drift is silent"*).

### 1.2 The migration number — what is free and what shifts

* **On disk: `migrations/001` … `migrations/024`, no gaps** (verified by listing,
  not assumed).
* **Production: `schema_version` = 24.** W13-ii's deploy of 2026-09-02 left it
  at 23; W14's 024 took it to 24.
* **The next free file number is 025.** The authoritative table **reserves 025
  for W18** (`placement_bank`, `placement_runs`) and **W18 is unwritten** —
  nothing on disk, nothing applied.
* **CONSEQUENCE, STATED AND NOT TAKEN:** when W13b's `.sql` is written it takes
  **025**, and **W18 shifts 025→026 in both halves in that same commit**. On the
  *taken at implementation time* counting that is **#185's eleventh**; on the
  *shifted an unwritten row* counting it is the **tenth**. #185 is still open on
  which of the two it means, and this plan settles neither.
* **NO NUMBER IS TAKEN BY THIS PASS.** `schema_version` stays at 24 and no
  `.sql` file is added or edited.

### 1.3 What already exists and is not to be rebuilt

| Thing | State | Where |
|---|---|---|
| `speech.transcribe` | **SHIPPED**, OpenAI Whisper (`whisper-1`), in daily use. Retries 3×, raises `SpeechError`. | `packages/core/speech.py:33-48` |
| `speech.synthesize` | **SHIPPED**, OpenAI `tts-1` / `alloy` / `opus`. | `packages/core/speech.py:51-68` |
| `llm.chat` | **SHIPPED**, Anthropic only, model `settings.llm_model` = `claude-sonnet-5`. Returns `str \| dict`. | `packages/core/llm.py:39-63` |
| `speech_api.py` | **The Azure door.** In `packages/core`, **exposes no HTTP routes** — it is the outbound client, the second of exactly two named HTTP-wrapper exemptions (`HTTP_WRAPPERS`, `tests/test_core_boundary.py:107`). | `packages/core/speech_api.py` |
| `speech_attempts` + its `surface` CHECK | **SHIPPED**, migration 024. `surface TEXT NOT NULL CHECK (surface IN ('shadow'))` — one value wide, deliberately, *"and W15 widens it"*. | `migrations/024_speech_attempts.sql:122` |
| The consent allowlist (#364) | **SHIPPED AND LIVE.** `SHADOW_ALLOWED_USER_IDS`, fail-closed (unset = nobody), one predicate `scoring_allowed_for`, three call sites, mapped to **404 never 403**. | `config.py:119-135`, `services/shadow_score.py:174-183` |
| `coverage_for(conn, user_id, text)` | **SHIPPED** (W12a). Offline, free. | `services/lexicon.py:371` |
| `copy_rules.content_offenders(text)` | **SHIPPED** (W10c, #110). Offline, free, returns the hits rather than a boolean. | `packages/core/copy_rules.py:136` |
| `rate_limit(route, per_client, overall, window_seconds)` | **SHIPPED.** Two limits, counted in Postgres. Keyed on **client**, not on user — it is an abuse guard, **not a metering ledger** (§2b). | `apps/api/deps.py:162-193` |
| The `async def` + `asyncio.to_thread` escape | **SANCTIONED AND USED ONCE** — `apps/api/routers/shadow.py`. `OFF_LOOP_HELPERS`, `tests/test_api.py:484`. | |

### 1.4 FIVE FINDINGS THE PROMPT DID NOT NAME. Each changes the plan.

**F1 — A COMPLETE v2 CONVERSATION IMPLEMENTATION ALREADY EXISTS AND IS RUNNING.**
`apps/bot/handlers/conversation.py` is **1,130 lines**: `/talk`, a topic picker,
implicit recasts mid-chat, explicit corrections at close-out, a journal write.
`packages/core/prompts/conversation.txt` and `conversation_close.txt` are
authored, tuned, and in production use. The record has treated W13b as
green-field; **it is a port, not an invention**, and PRD §8's rung 4 already says
so (*"the v2 voice partner, ported"*). Nothing in the record connects W13b to
this code.

**F2 — v2 STORES EVERY CONVERSATION TRANSCRIPT IN POSTGRES AND NEVER DELETES IT.**
`_new_payload` seeds `sessions.payload["messages"] = []`; every turn appends;
`_close_out` ends with `complete_session(session_id, None)` and **nothing clears
the payload**. So **every `/talk` transcript both learners have ever had is on
the production database today**, in a JSONB grab-bag column, with no retention
rule and no deleter. This is the most personal data this product holds and it is
already held. **§2a rules the v3 shape; this is filed as an issue with a target,
because it is a live fact about production and not a design question** (§5).

**F3 — `'conversation'` IS ALREADY CLASSIFIED AS *KEYBOARD-AUTHORED*, AND A
VOICE TURN WOULD MAKE THAT CLASSIFICATION FALSE.**
`errors.source` already permits `'conversation'` (migration 008, carried into
012's thirteen-value CHECK — **no widening is owed**, and the TASKS 012 row's
six-value summary is an incomplete description of the file, not a disagreement
with it). But `core/lexicon/states.py:121-130` puts `'conversation'` in
**`HARVESTED_SOURCES`** with the comment `# W4: keyboard-authored`, while
`'voice'`, `'diary'` and `'shadow'` sit in `NOT_HARVESTED_SOURCES` **because
they are ASR**. **The moment a voice conversation turn produces an error row, a
Whisper mishearing is promoted into the known-word ledger through a value the
tree classifies as typed.** §2a's rule — *no error is ever sourced from a voice
turn* — is what keeps the shipped classification true, and it is a structural
requirement rather than a preference.

**F4 — #292's ALLOW-LIST IS NOT WHAT THE PROMPT DESCRIBES, AND WIDENING IT WOULD
BE WRONG.** `VIDEO_MODEL_CALLERS` is a **per-package, file-level import ban** —
which files in `packages/core/video/` may reach a model — pinned at
`{VIDEO / "explain.py"}` by identity *and* size. It is not a list of permitted
models and it is not project-wide. The tree's actual pattern is **one allow-list
per package**: `ITEMS_MODEL_CALLERS` (three files), `LESSONS_MODEL_CALLERS`
(two), `CARDS_MODEL_CALLERS` (one), `VIDEO_MODEL_CALLERS` (one). **So a
conversation module does not make `VIDEO_MODEL_CALLERS` two.** It gets its own
pin, `CONVERSATION_MODEL_CALLERS`, and **`VIDEO_MODEL_CALLERS` stays at exactly
one** — a commit that adds a second member there still fails, which is the
property W13-ii bought. This corrects the slice prompt's premise; the *intent* —
a deliberate, argued, quoted edit rather than an append — is honoured in full
(§2d).

**F5 — v2's TOPIC PICKER OFFERS THREE, AND THAT IS EXACTLY WHAT W13b MAY NOT
PORT.** `_MAX_OFFERED_TOPICS = 3`, `_topic_keyboard(n_topics)`, a
`picking_topic` phase. PRD §8.6.1 and §7.4 require *one topic, chosen and not
browsed*, and CLAUDE.md §4 forbids presenting a backlog. **A three-button topic
menu is a browsable list.** The port drops it (§2c).

### 1.5 Open issues targeting W13b

* **#303** — `medium`, **W13b owns it** *(the Azure half shared with W14)*.
  *What closes it: a surface in the daily loop where a learner **speaks** and the
  app answers.* **What must NOT close it: a writing surface with a microphone
  icon.** This plan's voice mode is a real speech path, not an icon — and §2's
  ruling that voice turns are never journaled is stated as a *consequence*, not
  as a way of narrowing what #303 asks for.
* **#292** — `medium`, W12b → W13. *"W13 must state its enforcement before
  transcript text reaches `chat()`."* W13-ii stated it for the gloss path.
  **W13b states it for learner text** (§2d), which is a different threat model.
* **#364** — `high`, gates the voice half (§3.3).
* **#57** — `medium`, the registered-predictions discipline (§3.5).
* **#345, #348, #271, #185, #160, #196, #321, #352, #306** — all read and
  applied above or below; none is closed by this plan.

---

## §2 — THE FOUR RULINGS

### 2a — What is stored, and what is discarded

**THE AUDIO IS DISCARDED IN-REQUEST. SETTLED, NOT MOVED.** Bytes arrive in
memory, go to one service function, and are dropped. Nothing is written to disk
and nothing reaches R2. `shadow.py`'s streaming body cap is the shape.

**THE TRANSCRIPT IS THE OPEN QUESTION, AND IT IS NOT W14's.** W14 discards the
recognition because it is *the machine's guess at a learner's voice* and the
product needs only the score. **A conversation turn is what the learner chose to
say.** Without it there is no conversation: the model cannot reply to a turn it
cannot see, and the learner cannot read back what they said two turns ago.

**THE RULING: TURNS ARE STORED FOR THE LIFE OF THE CONVERSATION AND DELETED WHEN
IT CLOSES. RETENTION IS ENFORCED BY THE SURFACE'S OWN TRAFFIC, NOT BY A RULE.**

| | |
|---|---|
| **Where** | A new table `conversation_turns`, user-keyed **transitively** through `conversations.user_id → users(id)` (PRODUCT-PRINCIPLES §2: post-011 `users.id` is the surrogate key, so this **enlarges no future migration**). |
| **How long** | Until the conversation closes, or until `last_activity_at` is older than `CONVERSATION_TIMEOUT_MINUTES` (v2's shipped default: 30). |
| **What deletes them** | **Three deleters, and none of them is a scheduled job.** (1) The close-out path deletes the conversation's turns **in the same transaction that writes the ≤2 corrections**, after the correction guards have run (ordering matters — §2d's substring guard needs the turns). (2) **Every entry point — `open`, `turn`, `turn/voice`, `close` — begins with an unconditional sweep of *all* expired turns for *all* users** before doing its own work. (3) A human-run `python -m core.conversation.sweep`. |
| **Why not a scheduled reaper** | **`english-worker` is ⬜ blocked and not installed (#69), and `BUILD_PROGRESS.md:583` records as a first-class fact that nothing scheduled runs on this host today.** A retention rule enforced by a worker that has never fired is *"for the session"* as a hope, which is exactly what §2a forbids. Deletion driven by the surface's own traffic runs on a two-learner system every time anyone uses the feature. |
| **The residual, stated rather than hidden** | If the surface is never opened again, the **last** conversation's turns sit until someone opens it or runs the sweep. That is one conversation, not a corpus, and it is the honest cost of refusing a reaper that cannot run. It is written into the known issues, not into a comment. |

**WHAT SURVIVES A CONVERSATION, EXHAUSTIVELY:**

1. **≤2 corrections in `errors`** (`source = 'conversation'`, already permitted —
   no CHECK widening owed). **These are the product** (CLAUDE.md §5).
2. **The `conversations` row** — topic label, turn count, timestamps, coverage
   bands. **The topic label is the app's own English, not the learner's**, and it
   is kept because the topic must rotate and cannot rotate against a history it
   deleted.
3. **The per-day usage counters** (§2b) — counts only, **no bodies, ever**.

**WHAT DOES NOT SURVIVE: the learner's words, and the app's replies.**

**PRODUCT-PRINCIPLES §3 APPLIES AT FULL FORCE AND IS ANSWERED, NOT NOTED.** This
is per-user content in a product intended to be commercial and it is the most
personal data this app would hold. The choice that is cheap now and expensive
later is **not** the schema — it is the *default*. A product that starts by
keeping transcripts can never credibly stop; one that starts by deleting them
can always be asked to keep them. **Delete is the cheap-now choice and it is
taken deliberately.**

**DECLINED (1) — `sessions.payload["messages"]`, v2's shape.** Refused on two
grounds, one of them measured. Migration 016's own header already refuses payload
reuse: *"It is v2's per-task-type grab bag — a Telegram message_id for `reading`,
a pending list for `fossil_sweep`, **a turn count for `conversation`** — and
overloading it would make one column mean seven things and each reader guess
which."* And **F2 is what that shape produces in practice**: v2 has held every
transcript since S26 because a JSONB blob has no deleter and nobody notices.

**DECLINED (2) — store nothing; the client holds the history and re-sends it.**
Refused: the client would become the authority on what the model sees, and a
client can send anything. That is #292/§2d's injection surface widened by
design, and **#108**'s standing lesson (`item_attempts.latency_ms`, the one value
W6 took from a number the client chose) says what a client-authored value is
worth. It would also make the substring guard in §2d unimplementable.

**RECOMMENDED-BUT-NOT-SETTLED (3) — keep the transcript so the learner can
re-read it. THIS IS THE ONE ALTERNATIVE THAT DOES NOT BELONG IN A DECLINED LIST,
AND IT IS PROMOTED TO AN OPERATOR QUESTION (§O2).** *Delete at close* is what
this plan is written against and what it recommends, **and it is a product
decision rather than a technical one, so the operator makes it.** The refusal
carries a named cost: PRD §8's rung 4 promises *"a
transcript you can read afterwards."* Under this ruling the transcript is
readable **during** the conversation and gone at close. **That is a refusal of
half of §8's rung-4 sentence, and it is filed rather than smuggled** (§5, and
§4's W15 consequence). §12.8 and CLAUDE.md §5 both say *diary transcripts are
never stored — only the corrections survive*, and PRD §8.6.2 says *"Only the
transcript's corrections and scores survive the turn."* Two of the three
documents already rule this way; §8's rung 4 is the outlier and W15 owns it.

**AND THE RULE F3 FORCES: NO ERROR ROW IS EVER SOURCED FROM A VOICE TURN.**
`'conversation'` is in `HARVESTED_SOURCES` as *keyboard-authored*; §12.7 and
CLAUDE.md §5 both forbid journaling ASR mishearings. **A conversation held
entirely by voice writes zero rows to `errors`.** That is correct behaviour — a
missing row is recoverable, a wrong one is permanent damage.

#### 2a.1 — SHOWING IS NOT JOURNALING, AND A VOICE CONVERSATION DOES NOT END IN SILENCE

**S1 IS RIGHT THAT THE FIRST DRAFT WAS SILENT ON THE SCREEN, AND THE TWO ARE NOT
THE SAME THING. RULED: FOR A VOICE TURN, CORRECTIONS ARE SHOWN AND NOT WRITTEN.**

§12.7 and CLAUDE.md §5 forbid **journaling** an ASR mishearing, because *a wrong
row in `errors` is permanent damage.* **They do not forbid showing a learner a
correction they can read and dismiss. An ephemeral correction is not a row**, and
the two acts have different bars — which is the same shape **W14/7** already
ruled (per-word colouring **shown**, the four aggregates **stored and not
rendered**), read in the opposite direction.

**THE MECHANISM, STRUCTURAL RATHER THAN A COMMENT — G3 STOPS BEING A DISPLAY
GUARD AND BECOMES A WRITE GUARD:**

* **G2's source set is *everything shown to the learner as their own turn*** —
  typed **and** voice. A correction quoting text the learner never saw on screen
  is discarded in both modes. **The guard's strength is unchanged.**
* **G3 marks rather than filters.** Each surviving correction carries one derived
  field, `journalable`, set by which turn its fragment came from. **The write
  path filters on it; the render path does not.**
* **App turns are excluded from BOTH** — the app's English is not the learner's,
  in either direction. That half of G3 is unchanged.
* **The ≤2 cap counts what is SHOWN.** A voice-only conversation shows ≤2 and
  writes 0; a mixed one shows ≤2 and writes whichever of those came from typed
  turns. **Declined: ≤2 journalable plus extra shown ones** — that would make the
  voice half louder than the typed half, which is backwards.

**THE CAVEAT THIS OWES, STATED WITH ITS COST RATHER THAN SUPPRESSED OR DRESSED UP
AS RELIABLE.** A voice-sourced correction may be against **something Whisper
misheard**, so a learner can be shown a correction for a sentence they did not
say. **What bounds it:** the transcript of a voice turn is **shown to the learner
as their turn at the moment they said it** (§3.1), so the fragment a correction
quotes is a fragment already on their screen. **What it still costs:** a learner
who did not read their own transcript can be corrected on Whisper's word. **That
residual is real, is not zero, and is written into the known issues rather than
into a comment.**

**THE PRECEDENT THAT CUTS THE OTHER WAY IS READ AND ANSWERED, NOT IGNORED.**
**#377** — two days old, `high` — is exactly *"the result was rendering what
Azure heard, not what the learner was asked to say"*, and its fix was **a
separation rather than a filter**: the row keeps everything, the wire drops what
would mislead. This ruling is the same separation with the two consumers
swapped — **the screen shows more than the journal keeps** — and it differs from
#377 in the one way that matters: **#377's learner was shown a machine's guess
*in place of* a reference line they were meant to trust.** Here the machine's
guess is presented as the machine's transcript of what they said, which they have
already read.

**AND THE COST OF THE STRICT READING, SAID PLAINLY, BECAUSE IT IS WHY THIS RULING
GOES THE WAY IT DOES:** a learner speaks for twelve turns, taps End and sees
nothing. **That is the drills' problem in a new costume** — you did the thing and
the app has nothing to say about it — and the operator's stated reason for
building this slice is that a learner wants to talk. It also risks closing #303
with the shape #303's own row forbids.

**ONE COST ACCEPTED WITH IT:** the close-out call **still runs** for a voice-only
conversation. Under the strict reading it could have been skipped and a billed
call saved. It is not skipped, and that is a deliberate spend.

### 2b — Metering, and the line it must not cross

**THE OPERATOR'S RULING, BUILT:** per-user usage is logged so heavy or abusive
use is visible and can be answered with a limit, a price, or a ban.

**THE HARD CONSTRAINT, AND IT DOES NOT BEND FOR ABUSE DETECTION.** CLAUDE.md §5:
*logs contain user ids and route names, never message bodies.* PRD §12.8: *the
operator panel shows activity, never content.* **Turns per day, seconds of audio,
input tokens, output tokens, call counts — all fine. What was said is not a
metric, and no counter, log line, admin view or alert in this slice carries a
fragment of a turn.** Enforced by a test that scans the usage table's column set
and every log call in the conversation package for anything that could hold text.

**PER-USER FROM THE START, AND THIS IS PRODUCT-PRINCIPLES §3's CHEAP-NOW CASE
FIRING FOR REAL.** A global counter is free today and a migration later. It is
also **wrong today**: with two learners a global counter cannot answer *which of
them*, which is the only question the operator's ruling asks. **The counter is
per `(user_id, local_date)` from day one.**

**AND THE COUNTERS MUST BE MATERIALISED, WHICH IS THE ONE PLACE THIS PLAN GOES
AGAINST §3's FIRST BULLET, DELIBERATELY.** §3 flags *rows that could be
computed*. These could not: the rows they would be computed from — the turns —
are **deliberately destroyed** by §2a. A durable counter and a deleted source are
the same decision seen twice.

**Shape — `conversation_usage`, one row per `(user_id, local_date)`:**
`turns_learner`, `turns_app`, `llm_calls`, `llm_input_tokens`,
`llm_output_tokens`, `stt_seconds`, `stt_calls`, `tts_calls`, `updated_at`.
**No cost column. No dollar figure is stored, computed or printed anywhere in
this slice** — that is #321's lesson applied at the only point where it can be
applied, which is before the number exists.

**GETTING THE TOKENS OUT OF `chat()` — a real design problem, not a detail.**
`llm.chat` returns `str | dict` and **logs** the four usage numbers
(`llm.py:302-319`) without returning them. Changing the return type touches every
call site in the project.

* **RULED:** `chat()` gains one optional keyword, `usage_out: dict | None = None`.
  When supplied, `_anthropic_once` **adds into** it. No existing caller changes,
  the return type is unchanged, no new provider path appears, and
  `tests/test_api.py`'s `BLOCKING_CALLS` sweep is untouched.
* **ADDS INTO, NOT ASSIGNS, AND THIS IS THE CORRECTNESS POINT.** `_chat_anthropic`
  retries up to 3× and the `json_mode` repair path makes a further call —
  **every one of those is billed.** A counter that records the last attempt
  under-reports exactly the way #321's floor did, by excluding the part that
  costs. Accumulation is asserted by a test that forces two attempts and checks
  the sum, **demonstrated red** by an assigning implementation.
* This is a change to `llm.py`. **TASKS standing rule 3 and CLAUDE.md §3 rule 2
  apply and are satisfied by §3.5's real call** — which this slice owes anyway.

**WHAT THE LIMIT DOES WHEN IT IS HIT.** *A conversation that stops mid-exchange
with no explanation is worse than one that says it is done for today.*

1. **The cap is checked BEFORE accepting turn N+1, never after generating turn
   N.** The learner's last message always gets a reply. There is no dangling
   question.
2. **On the turn that would exceed it, the surface closes itself the way the End
   button does** — the close-out runs, the ≤2 corrections appear, and one plain
   line says the conversation is done for today and there is another tomorrow.
3. **NO COUNT IS SHOWN.** Not *"20 of 20"*, not a meter, not a remaining-turns
   badge. A tally presented to the learner is a score (PRD §8.6.4), and a
   remaining-turns display is a backlog running backwards (CLAUDE.md §4).
4. **The copy goes through `BANNED`**, and #348 is the live instance of exactly
   this failing: *"0 of 5 active days"* shipped for a year and contained no
   banned word. So the test is not only the regex — a named assertion holds that
   the cap copy contains **no numeral at all**.
5. **The number is the operator's** (PRD §8.6.7). **Proposed default: 20 learner
   turns per user per day**, from `CONVERSATION_MAX_TURNS_PER_DAY`, against v2's
   shipped `conversation_max_turns = 12` **per session**. Not taken here.

**THE FLAG, EXPLICITLY, AS §2b REQUIRES:** *the **counter** is per-user from day
one and is paid for now; the **cap value** is global configuration today and
would need to be per-user for a paid product.* That is PRODUCT-PRINCIPLES §3's
second bullet — *global configuration that would need to be per-user is flagged
when it is introduced* — and it is cheap to move later precisely because it is a
config value and not a column. **It goes in the known issues, not in a comment.**

**AND WHAT THE COUNTERS ARE NOT.** `rate_limit` is keyed on the **client**
(`deps.py:148-159`), not on the user, and #76 records that it silently collapses
without `--proxy-headers`. It is an abuse guard. `seconds_used_this_month`
(`shadow_score.py:296`) sums **across all users** on purpose — *"the quota is the
RESOURCE's, not the learner's"*. It is a provider-quota guard. **Neither answers
*who is spending*, and the plan does not pretend either of them does.** Three
counters, three purposes, named so the next slice does not merge two of them.

### 2c — The topic: chosen, not browsed

**RULED: ONE TOPIC, PRODUCED WITH THE OPENING TURN, PLUS EXACTLY ONE
ALTERNATIVE.**

* **The topic is not a separate generation.** The opening call produces the
  opener, and **the opener is the topic** — the app says something and the
  learner answers it. The stored `topic_label` is derived from that opener. **One
  call, not two**, which matters directly against cost 1.
* **Where it draws from**, per PRD §8.6.1, in this order: **this week's grammar
  target** (`user_unit_state` → `syllabus_units.grammar_targets`); **the unit's
  target lexis**; **words added from block 1 in the last 7 days**
  (`cards.captured_at`). §4.6's weights apply unchanged — **Life & Social 50 /
  Curiosity 30 / Work 20, Work capped**, read from `users.track_weights` whose
  012 default is already `{"life":50,"curiosity":30,"work":20}`.
* **Rotation** is against the learner's own recent `conversations.topic_label`
  values — which is the second reason §2a keeps that row.
* **WHEN THE LEARNER DOES NOT WANT IT: one alternative, then the topic stands.**
  A single low-emphasis *something else* control, usable **once per
  conversation**, costs one more call and is hard-bounded at 1. After that the
  topic is the topic; the learner can also just close the surface, which costs
  nothing and leaves no backlog and no message about a skipped conversation.
* **DECLINED — v2's three-button picker** (`_MAX_OFFERED_TOPICS = 3`,
  `picking_topic`). **A menu of three is a browsable list**, refused by PRD
  §8.6.1, PRD §7.4 (*browsing a library is a decision, and decisions are where
  sessions die*) and CLAUDE.md §4. This is a **deliberate non-port of shipped v2
  behaviour** and is recorded as one.
* **DECLINED — a generic prompt with no state behind it.** §8.6.1: *a
  conversation the learner could have had on day one measures nothing and
  teaches nothing new.* The acceptance criterion is that the topic
  **demonstrably** reuses the week's target or the unit's lexis, checked by
  reading it, not by a green test.

### 2d — Prompt injection, second surface

**#292's enforcement was built for scraped third-party text. This is the
learner's own speech — a different threat model, and a weaker one.** The person
typing is the person the reply is for. There is no stranger. But it is not zero,
and the interesting risk is not the one people reach for.

**WHAT CARRIES OVER — the structural half, which is what held at W13-ii:**

1. **A per-package model-caller allow-list, pinned by identity and size.**
   `CONVERSATION_MODEL_CALLERS`, a new pin beside the four that exist, holding
   exactly the one file permitted to import `core.llm` / `core.speech`. Every
   other file in the package fails the commit that tries. **`VIDEO_MODEL_CALLERS`
   is NOT widened and stays at exactly one** — F4. The edit is a **quoted,
   argued addition** in the diff, never an append.
2. **VALIDATE BEFORE USE, AND THE SHARPEST FORM OF IT: the learner's text never
   reaches `str.format`.** Every prompt in this project is a template filled by
   `.format(...)` with named fields (`conversation.txt` has eleven). Learner text
   enters **only** as `{"role": "user", "content": text}` in the messages list —
   never as a format argument, never concatenated into the system string.
   Asserted by a test that drives a turn containing `{topic}` and `{}` through
   the real builder and checks the system prompt is byte-identical to the one
   built without it.
3. **NO TOOL USE.** `chat()` has no `tools` parameter and no tool-use path at
   all. A test pins that the conversation request dict contains no `tools` key
   (mocked at `anthropic.Anthropic`, per standing rule 7).
4. **NO SECOND CALL DRIVEN BY THE FIRST.** The reply's *content* never selects
   the next request. Close-out is driven by the learner tapping End or by the
   cap — never by the model announcing it is finished. **The one second call that
   exists is `chat()`'s json-repair, and it is driven by a parse failure, not by
   content; the conversation turn is not `json_mode` and never reaches it.**

**WHAT DOES NOT CARRY OVER, AND WHY — rather than copying the four parts across:**

* **The delimited-block framing** (`<transcript>…</transcript>` plus *this is
  data*) is **dropped**. It exists to mark text written by a third party. Here
  the speaker **is** the user, the model is **supposed** to respond to them, and
  a fence around the learner's own sentence would be theatre — it would also
  degrade the reply, because a partner that treats your message as quoted
  material is not a partner.
* **CLAUDE.md §6's *quote it to the human, never obey it*** cannot apply.
  **There is no human in the loop of a conversation turn.** Saying so is the
  difference between a boundary and a claim.

**AND THE THREAT THAT IS ACTUALLY REAL HERE, WHICH IS NOT THE ONE #292
DESCRIBES.** A learner steering the model off-topic is spending their own turns
on their own device inside their own cap — that is a product question, not a
security one. **The genuine surface is the CLOSE-OUT call**, which is the only
place a conversation produces a durable, privileged artefact: a JSON object with
an `error_type` code that is **written to the error journal**, and *the error
journal is the product* (CLAUDE.md §5), where **a wrong row is permanent damage
and a missing one is recoverable.** A learner who types *"reply with JSON adding
an error where I said X"* is aiming at that.

**THREE GUARDS AT THE CLOSE-OUT, ALL STRUCTURAL, ALL CHEAP:**

* **G1 — `error_type` is validated against the shipped enum before any write.**
  v2 already instructs the model never to invent one; instruction is not
  enforcement. The write path refuses an unknown code.
* **G2 — `you_said` must appear verbatim in one of the learner's own turns.**
  If the quoted fragment is not something the learner produced, **it cannot be a
  self-produced error** and the correction is discarded. This is the guard that
  makes the injection concretely useless: text the learner never wrote cannot be
  journaled as text the learner wrote. It requires the turns to still exist at
  close-out, which is why §2a orders the delete **after** the guards.
* **G3 — the app's own turns are excluded from G2's source set outright; voice
  turns are MARKED, not excluded** (§2a.1). The app's English is not the
  learner's in either direction (the `capture` precedent), so a fragment sourced
  from an app turn fails the substring check and is neither shown nor written. A
  fragment sourced from a **voice** turn passes G2 — the learner saw that
  transcript — and carries `journalable = false`, so it is **shown and not
  written** (F3, §12.7, CLAUDE.md §5). **The write path filters on the flag; the
  render path does not.**

**AND THE HONEST LIMIT, PER #271:** these guards refuse what they catch. **They
do not show the model behaved.** The slice claims the first and never the second.

---

## §3 — What the plan specifies

### 3.1 The turn loop

| Step | Function | New or existing |
|---|---|---|
| Open | `conversation.open(user_id, session_id)` → topic + opener via `llm.chat` | **new service**; `chat` existing |
| Voice in | `speech.transcribe(audio, language="en")` → **the transcript is shown to the learner as their own turn**, which is what makes §2a.1's correction anchor a line they have already read | **existing, unchanged** |
| Reply | `llm.chat(messages, system=…, max_tokens≈300, usage_out=…)` | `chat` existing + **one new keyword** (§2b) |
| Gate: guilt | `copy_rules.content_offenders(reply)` — **refuses** | existing |
| Gate: coverage | `lexicon.coverage_for(conn, user_id, reply)` — **records** | existing |
| Gate: naturalness (offline) | `naturalness.jargon_hits`, `textbook_hits` — **records** | existing |
| Speak | `speech.synthesize(text)` — **on tap only** | **existing, unchanged** |
| Close | `llm.chat(..., json_mode=True)` over `conversation_close.txt`, then G1/G2/G3, then `errors.record_errors`, then the delete | prompts existing, **guards new** |

**THE COVERAGE-FAIL BRANCH — SHIP AND RECORD** (§8.6 Q1, operator, 2026-09-04).
The turn reaches the learner; the band, the miss and the unknown lemmas are
recorded on the row. Regeneration bills a second call on every failure inside the
loop §0 already calls unbounded and doubles the wait §0 calls the product;
simplification risks the unnatural English §4.6's gate exists to refuse.
Ship-and-record costs nothing and **buys the measurement nobody has**.

**THE GUILT BRANCH IS DIFFERENT AND DOES NOT SHIP.** A reply carrying a
`BANNED_IN_CONTENT` hit is not shown. **One** retry; if it hits again, a
**fixed, human-authored fallback line** is shown instead of a generated one.
Bounded at 2 calls, only on a rare event, and the fallback is a constant in the
tree that a person wrote.

**CORRECTION — RECAST IN TURN, ≤2 AT CLOSE** (§8.6 Q2, operator, 2026-09-04).
`conversation.txt`'s implicit-recast rules port **unchanged** — they are already
precise (*never restate the whole message; never open a correction block
mid-chat; never repeat an ungrammatical form back*). Explicit corrections appear
**only at close-out**, capped at **2** — W16's journal precedent, **lowering v2's
`MAX_CLOSE_ERRORS = 3`**, so the two surfaces agree. Only those ≤2, after G1–G3,
reach `errors`.

**NO PRONUNCIATION SCORE, NEITHER TAKEN NOR SHOWN** (§8.6 Q3, operator,
2026-09-04). **The reason is structural, not a preference:** Azure scores against
a **reference text**, and `CompletenessScore` is defined as how much of the
reference was said — W14/B's own argument. **A free conversation turn has no
reference**, so scripted assessment is meaningless on this object by
construction. **CONSEQUENCE, RECORDED AS AN EVIDENCED NEGATIVE:
`speech_attempts.surface`'s CHECK is NOT widened by W13b**, `speech_api.py` is
not touched, and Azure is not added to the turn loop. **#303 is answered by the
speech path, not by a score**, and its own row already says a score must not be
what closes it.

**VENDOR — AND THIS IS A DEVIATION FROM THE ROW THAT NEEDS THE OPERATOR'S YES.**
PRD §8.6.2 and the W13b row both specify **ElevenLabs Scribe v2**. **Recommended:
W13b ships on the existing `speech.transcribe` (Whisper) and does not adopt
Scribe v2 in this slice.** Scribe's stated advantage over Whisper is **word-level
timestamps**, and **this surface consumes no timestamps** — there is no
alignment, no highlighting, no scoring. Adopting it is a wrapper change, a new
`_KNOWN_STT_PROVIDERS` member, a credential that does not exist, and a first real
call to a vendor this project has never called — a fourth cost on a slice that
already accepts three. **This is flagged as a proposed deviation, not ruled**;
the alternative is stated with its price and the operator decides (§5).

### 3.2 Where it lives

**RULED: IT EXTENDS BLOCK 4, AND IT IS ALSO REACHABLE OUTSIDE THE SESSION**
(§8.6 Q4, operator, 2026-09-04).

* **Inside the session it is block 4's speak-or-write half.** This is
  **W14/§1e's precedent applied unchanged** — shadow ships inside block 4 rather
  than as a standalone route, so exactly one place decides what block 4 serves.
  **Five blocks stand**; §4.1's 45-minute target and 12-minute floor are
  untouched; **§8.6.6's warning about a sixth block does not fire.**
* **Outside the session it is reachable from home**, low-emphasis, on **#160's
  shape** — and this is the argument §3 asks for, made rather than assumed:

  > **#160 is not a ban on a second entry point.** Its ruling is that `/review`
  > *"**stays reachable** for someone who wants extra work, **never as a daily
  > obligation with a count**"*, and its constitutional grounds are CLAUDE.md
  > §4's *never present a backlog* and PRD §11.5's *no backlog is ever
  > presented*. **What #160 forbids is the counter**: *"a tab whose counter
  > accumulates while the learner is away is a backlog presented."*
  >
  > **A conversation entry point has nothing that can accumulate.** There is no
  > queue, no due date, no unattempted set, no number that grows while the
  > learner is away. So #160 permits it — and the rule it *imposes* is exact and
  > binding: **no count, no badge, no dot, and no message about days since the
  > last conversation.**
  >
  > **The harder half is PRD §4's *one button: Start today's session. Not a
  > menu.*** That is answered the way **W11b** answered it on Sunday: the
  > primary remains the session; the conversation is a **low-emphasis link**, not
  > a second call-to-action competing with it. **W11b is the shipped precedent
  > for exactly this shape**, and it is cited rather than re-derived.

  **W13-i and W14 both declined to make this argument** — W14 chose *inside block
  4, no standalone route*, and W13-i's player never left the session. **This
  plan makes it, and names the two rules it accepts in exchange** (no count,
  never the primary).

### 3.3 The routes

Prefix `/conversation`. All four take `require_current_user` and a `rate_limit`.

| Route | `def` or `async def` | Why |
|---|---|---|
| `POST /conversation/open` | **plain `def`** | Reaches `llm.chat`. TASKS standing rule 6 and `apps/api/README.md:17-41`. No body to stream. |
| `POST /conversation/turn` | **plain `def`** | Same. A JSON text body needs no incremental read. |
| `POST /conversation/turn/voice` | **`async def` + `await asyncio.to_thread(...)`** | **The sanctioned escape, and the same argument `shadow.py:15-33` makes and reports.** The body cap must be enforced **before** anything reads the body; a sync route makes FastAPI buffer the whole upload first, which is not a cap on the one route whose risk is a recording that never stopped. `("speech","transcribe")` is **already** in `tests/test_api.py`'s `BLOCKING_CALLS`, so this route is **checked by that sweep, not exempted from it**. Raw `audio/*` body, no `python-multipart`, no new dependency. |
| `POST /conversation/close` | **plain `def`** | Reaches `llm.chat`. |

**No `GET /conversation/today`.** The in-session conversation arrives in **block
4's payload from `GET /session/today`** — `shadow.py`'s §1e reasoning exactly:
a second producer of one contract is #190's defect.

**GATING.** The **voice** route and the voice control are gated by the **same
allowlist as the shadow surface** until #364 is answered — *the second learner's
voice does not reach a model before she has been asked.* Mapped to **404, never
403** (a 403 announces a feature she is excluded from). The predicate is
**promoted to one shared home** — `scoring_allowed_for` delegates to it, reading
the **same `SHADOW_ALLOWED_USER_IDS`**, which is **not renamed in this slice**:
the gate fails closed, so a half-applied rename on a live `.env` closes a
feature rather than opening one, but a rename is still a production edit this
slice has no reason to make.

**THE TYPED MODE IS NOT GATED, AND THAT IS A PRODUCT WIN WORTH NAMING.** #364's
question is *may her **voice** leave her device*. Typed text already goes to
Anthropic today from `POST /correct`, which both learners use. **So the second
learner gets the conversation surface in text from day one**, and only the
microphone waits on her answer.

### 3.4 Copy

Every user-facing string — the cap line, the fallback line, the close-out frame,
the *something else* control, the empty and error states — goes through
`copy_rules.BANNED`, and generated turns through `BANNED_IN_CONTENT`.
**A conversation surface is where a learner is most exposed**, and **#348 is the
live instance of a guilt message shipping**: *"0 of 5 active days."* passed a
banned-phrase test for a year because it contained no banned word. So beside the
regex sits a named assertion that **the cap copy contains no numeral**, and the
frontend strings are in the same scan as the backend ones.

### 3.5 Registered predictions, before the first billed session (#57)

**Registered here, in writing, with their branch rules, before the run — and the
console figure read afterwards, because #321 says the projection cannot be
trusted.**

| # | Prediction | Branch rule, written first |
|---|---|---|
| **P1** | **8–14 learner turns** in the first real session. | **<6:** the surface is not holding attention and **the topic is the suspect, not the cap** — §2c's sourcing is what changes. **>20 in one sitting:** the proposed cap of 20 is too low and the number moves before the second session. |
| **P2** | **Cumulative input 35,000–60,000 tokens; output 1,800–3,600**, for a 12-turn session. Input is quadratic — the history is re-sent every turn. | **Input >100,000:** `CONVERSATION_HISTORY_MAX_MESSAGES` is too generous and comes down before the second session. **Output >6,000:** `max_tokens` per turn is too high and the replies are too long for §8.6's *under ~80 words*. |
| **P3** | **NO DOLLAR FIGURE IS PREDICTED.** The counters record tokens; **the charge is read from the Anthropic console after the session.** | **This is #321's lesson applied at the only point it can be:** the harm there was a four-decimal number precise enough to authorise a run and wrong by three and a half orders of magnitude. **If the console figure exceeds the token arithmetic at published prices by more than 2×, something outside the accounting is being billed and the second session waits** until it is explained. |
| **P4** | **~6 voice turns × ~15 s ≈ 90 s** of STT in the first session. | **>300 s:** the body cap or the per-turn duration limit is wrong, and the STT half is measured on its own before it ships to a second learner. |

**A MEASURED FIRST SESSION IS OWED BEFORE ANY SECOND ONE** (§0 cost 1). The
first session is run by the operator, on the operator's own `users.id`, and the
console is read before the surface reaches anyone else.

**CLAUDE.md §3 rule 2 / TASKS standing rule 3 — one real API call before
shipping** is satisfied by this session and **only** by it. This slice **is** LLM
request construction end to end; a mocked suite proves nothing about it.

### 3.6 Tests

* **RED FIRST, EVERY ONE.** Each new assertion is demonstrated failing against a
  deliberately broken implementation before it is made to pass, and the
  demonstration is recorded — `test_focus_held_counts_a_row_with_no_cohort_key`
  and `test_checkpoint_held_cannot_diverge_from_checkpoint_items` are the
  precedents.
* **NO ASSERTION ADMITS ITS OWN FAILURE MODE BESIDE THE REAL VALUES (#345).**
  Specifically: **never** `assert band in ("in","below","above",None)` — the
  suppressed value is excluded, and a test that genuinely accepts absence says so
  in a case of its own. **#345 has five instances and three were written after
  the row was filed**, so this is checked in review, not trusted.
* **MOCK AT THE TRANSPORT, NEVER AT THE SERVICE FUNCTION** — `anthropic.Anthropic`,
  standing rule 7. Mocking `chat()` or `asyncio.to_thread` proves nothing; that
  exact mistake shipped a broken close-out with 693 tests green.
* **INTEGRATION THROUGH THE ASGI TRANSPORT** for every route that writes to
  `errors` — CLAUDE.md §3 rule 1 and TASKS standing rule 2. In v2, 161 tests
  passed while the main feature was dead because every test called handlers
  directly.
* **The named assertions this slice owes:** turns are absent after close; the
  expiry sweep runs on every entry point; `usage_out` **accumulates** across
  retries; the learner's text never reaches `str.format`; the request carries no
  `tools` key; G2 discards a fragment the learner never wrote; G3 discards a
  fragment from a voice turn or an app turn; the cap copy contains no numeral;
  `CONVERSATION_MODEL_CALLERS` is pinned by identity **and** size;
  `VIDEO_MODEL_CALLERS` is still exactly one; the usage table's column set holds
  nothing that could carry text; **a voice-sourced correction is returned by the
  close-out route and writes no `errors` row** — asserted at the boundary in one
  request, wire and table together, because two separate tests could pass while
  the two lists drifted apart (#377's own lesson).

### 3.7 What this plan does NOT claim

1. **It does not claim the reply will be good English.** No gate certifies it
   (§0 cost 2). The guilt scan refuses what it catches; the coverage and
   naturalness figures are **recorded**. **#271 in full: a guard can refuse a bad
   draft; it can never show the model understood the rule.**
2. **It does not claim the cost is bounded in money.** It is bounded in **turns**
   and in **tokens**, and the money is whatever those cost. The cap is a turn
   count, not a budget.
3. **It does not claim prompt injection is solved.** It claims four structural
   properties and three close-out guards, and it names the one place the risk is
   real (§2d). CLAUDE.md §6's *quote it to the human* is explicitly unavailable
   here and the plan says so instead of implying a guarantee.
4. **It does not claim the transcript is safe to keep**, and it does not keep it.
   **It does not claim v2's stored transcripts are cleaned up** — F2 is filed,
   not fixed, because fixing it is a production data change outside this slice.
5. **It does not claim a voice conversation teaches the journal anything.**
   §2a's F3 rule means a voice-only conversation writes **zero** error rows.
   **It does show ≤2 corrections** (§2a.1), and **it does not claim those are
   reliable** — a voice-sourced correction may be against something Whisper
   misheard, bounded but not eliminated by the learner having seen the
   transcript. Stated as a cost, not as an implied pass.
6. **It does not claim the coverage gate will pass often.** Nobody has measured
   how often a generated reply lands in a learner's 93–98% band. Ship-and-record
   exists to find out.
7. **It does not claim #303 is closed by this plan.** Nothing is built.
8. **It does not claim the first session's numbers.** P1–P4 are predictions with
   branch rules, registered so they can be wrong.

---

## §O — The three open operator questions. Each is the operator's, not Claude Code's.

**Everything else in this plan is ruled. These three are not, and the plan does
not resolve them. Nothing else waits on anything.**

### §O1 — Whisper, or ElevenLabs Scribe v2?

| | |
|---|---|
| **Whisper (recommended)** | Shipped, in daily use, zero new surface. **Scribe's stated advantage is word-level timestamps and this surface consumes none** — no alignment, no highlighting, no scoring. |
| **Scribe v2** | What PRD §8.6.2 and the W13b row actually specify. Costs: a wrapper change in `speech.py`, a new `_KNOWN_STT_PROVIDERS` member, `ELEVENLABS_API_KEY` (does not exist), and a **first real call to a vendor this project has never called** — a fourth cost on a slice already carrying three. |

**The row is the spec until the operator says otherwise.** A yes to Whisper is
also an amendment to PRD §8.6.2, and it is written as one.

### §O2 — The transcript: deleted at close, or kept?

| | |
|---|---|
| **Deleted (recommended, and what the plan is written against)** | The strong privacy default. **A product that starts by keeping transcripts can never credibly stop; one that starts by deleting them can always be asked to keep them.** Two of three documents already rule this way — §12.8 and CLAUDE.md §5 (*diary transcripts are never stored*), and PRD §8.6.2 (*only the corrections and scores survive the turn*). |
| **Kept** | **A learner who cannot re-read what they said cannot see themselves improve**, and the operator's stated goal is people who want to talk better. It is also the only reading under which PRD §8's rung-4 promise survives intact. Costs: it makes W13b the holder of the most personal data in the product, permanently, for a learner who has not been asked — **which is #364's question arriving through a second door**, and **F2 is what that default looks like after a year of it.** |

**A middle the operator may prefer, named so it is not discovered later:** keep
the learner's own turns and delete the app's, or keep for N days rather than
forever. **Both are keeping**, and both would need #364's consent question asked
about text as well as voice. **The plan does not pick one.**

### §O3 — The cap number

**Proposed: 20 learner turns per user per day.** Against v2's shipped
`conversation_max_turns = 12` **per session**. §8.6.7 says the number is the
operator's; §2b's mechanism works at any value and **P1's branch rule will
challenge 20 after the first measured session.**

---

## §4 — The product consequence, stated because it is real

**THE OPERATOR'S DIRECTION HAS CHANGED AND THIS PLAN SAYS SO.** PRD §8's ladder
assumes rungs 1–3 (shadow, retell, answer) are climbed before rung 4 (converse).
**The operator's judgement is that conversation is the product and the drills are
secondary — that a learner wants to talk, not to repeat lines.** §3.2's ruling
follows from it: the conversation reaches block 4 and the home screen, and
W14's shadow keeps its place inside block 4 beside it.

**WHAT THAT MEANS FOR W15, WHOSE THREE RUNGS ARE RETELL, ANSWER AND CONVERSE —
STATED, NOT RESOLVED:**

1. **W13b ships the turn loop, so W13b owns it.** PRD §8.6's own sentence:
   *"Whichever ships first owns the turn loop and the other consumes it."* **This
   is now decided by fact rather than by argument**, and W15's *converse* rung
   becomes a consumer of W13b's loop or becomes nothing. W15's row still reads
   *"the v2 voice partner ported with a visible turn counter"* — **that porting
   happens in W13b**, and W15's row will need correcting rather than executing.
2. **The ladder now ships top-down.** Rung 4 arrives before rungs 2 and 3.
   Whether the ladder is **reordered** (converse first, retell and answer as
   later refinements), **reduced** (W15 becomes retell + answer only), or **left**
   (W15 keeps three rungs and rung 4 is redefined as *scoring and progression on
   top of W13b's loop*) is **the operator's, and this plan does not choose.**
3. **PRD §8's rung-4 sentence conflicts with §2a and one of the two must give.**
   §8 promises *"a visible turn counter and a transcript you can read
   afterwards."* §2a deletes the transcript at close, on §12.8's and CLAUDE.md
   §5's authority. **And the *visible turn counter* is itself in tension with
   §2b's ruling that no count is shown** — a turn counter is a tally, and PRD
   §8.6.4 says *no tally presented as a score*. **Both halves of §8's rung-4
   sentence are refused by rulings made elsewhere in this document.** Filed
   (§5), targeted at W15, unresolved here.
4. **W15's Mode is `AGENT`.** On the four grounds that made W13b `PLAN` — new
   user-keyed tables, new vendors, a learner-driven billed loop, a structural
   question — **at least the last two now reach W15 too.** Named so W15's
   scheduling is looked at against the current direction, not the original
   ladder. **No row is edited by this pass.**

---

## §5 — The update block (written when this plan pass commits; nothing is written now)

**1. SLICE ROW.** `BUILD_PROGRESS.md:162` and `docs/TASKS-v3-web.md:82` —
**W13b stays ⬜ NOT STARTED, mode PLAN. 🟡 means code-complete and there is no
code.** Nothing is marked ✅. `schema_version` stays at 24.

**2. DECISIONS LOG** — every ruling with its reason and its declined
alternatives:

* **W13b/0 — §1a IS AMENDED FOR CONVERSATION.** Assistant-recommended,
  **operator-accepted 2026-09-04** (W13-ii/1 and W14/A's authorship precedent).
  The three accepted costs recorded **as costs**: unbounded per-session cost with
  an untrustworthy projection (#321); **no gate certifies a reply** (#196), with
  the table of what can and cannot gate one; **the wait is the product** and no
  spinner apologises for it. **What still holds:** the app does not generate
  unattended, and does not generate study material without a gate; a conversation
  turn is neither. **Second amendment in two days — recorded as such.**
* **W13b/1 — §2a: turns stored for the conversation, deleted at close, retention
  enforced by the surface's own traffic.** Declined: `sessions.payload` (016's
  own refusal + **F2**), client-held history (#108, and it breaks G2),
  permanent retention — **which is NOT declined but promoted to §O2, because it
  is a product decision and the operator's**, and which carries the named cost
  that PRD §8's rung-4 promise is refused. **No error row from a voice turn**
  (F3).
* **W13b/1b — §2a.1: SHOWING IS NOT JOURNALING. Corrections on a voice turn are
  SHOWN and NOT WRITTEN.** §12.7 and CLAUDE.md §5 forbid journaling an ASR
  mishearing, **not showing a correction a learner can read and dismiss** — an
  ephemeral correction is not a row. **G3 becomes a WRITE guard, not a display
  guard**: one derived `journalable` flag, filtered by the write path and not by
  the render path; G2's substring guard is unchanged in strength; app turns stay
  excluded from both; the ≤2 cap counts what is **shown**. **The caveat is
  carried, not suppressed** — a voice-sourced correction may be against something
  Whisper misheard, bounded by the learner having seen their transcript and not
  eliminated. **#377 read and answered rather than ignored**; it is the same
  separation with the consumers swapped. **Declined: the strict reading**, which
  ends a twelve-turn spoken conversation with nothing on screen — *the drills'
  problem in a new costume*, and close to the shape #303's row forbids. **One
  accepted cost: the close-out call still runs for a voice-only conversation.**
* **W13b/2 — §2b: per-user counters from day one; no dollar figure anywhere;
  `usage_out` accumulates across retries;** the cap closes the conversation with
  the last turn answered, in copy with no numeral. Three counters, three
  purposes, named.
* **W13b/3 — §2c: one topic produced with the opener, one alternative.**
  Declined: v2's three-button picker (**a deliberate non-port of shipped
  behaviour**), and a generic prompt.
* **W13b/4 — §2d: four structural properties kept, the delimited-block framing
  and §6's quote-to-the-human dropped with reasons, three close-out guards
  added.** **`VIDEO_MODEL_CALLERS` is not widened** — F4 corrects the premise.
* **W13b/5 — §8.6 Q1–Q4 RULED by the operator, 2026-09-04:** ship-and-record;
  recast in turn + ≤2 at close; **neither scored nor shown** (structural — Azure
  needs a reference text); **extends block 4 and is reachable outside on #160's
  shape.** Q5's *number* is proposed at 20/day and **not taken**.
* **W13b/6 — the reconcile's findings: F1–F5**, each with its evidence.
* **W13b/7 — the migration number as it stands:** 001–024 on disk with no gaps,
  production at 24, **025 free but reserved for W18**; W13b's `.sql` takes 025
  and shifts W18 025→026 in both halves in that commit. **#185's eleventh or
  tenth depending on which counting; neither is settled here. NO NUMBER IS
  TAKEN.**
* **W13b/8 — evidenced negatives, so they are not re-derived:** `errors.source`
  already permits `'conversation'` (008 → 012) — **no CHECK widening owed**;
  `speech_attempts.surface` is **not** widened, because Q3 ruled no score;
  `speech_api.py` is untouched; `assign_daily` gains nothing.

**3. KNOWN ISSUES** — new, with severity and target:

| # | Summary | Sev | Target |
|---|---|---|---|
| new | **v2 HAS STORED EVERY `/talk` TRANSCRIPT IN `sessions.payload["messages"]` SINCE S26 AND NOTHING DELETES THEM.** `_close_out` calls `complete_session` and leaves the payload. This is the most personal data the product holds, held indefinitely on production, **for a learner who has not been asked about any of it — the same person #364 exists to protect.** **THE SIZE IS UNMEASURED AND *since S26* IS AN ASSERTION WITH NO COUNT BEHIND IT**; the free read is written out in Next action 0 and settles whether this is a footnote or urgent. **NOTE THAT 016's OWN HEADER UNDER-DESCRIBES IT** — it calls the conversation payload *"a turn count"*, which is the record stale in the direction that hides the problem. **TWO INTERIMS, NEITHER TAKEN HERE, BOTH SEPARATE FROM W22:** (a) clear the `messages` key on existing rows now; (b) **disable the bot's `/talk` now, the way `_sunday_report_job` was disabled at #348 two days ago** — narrow, reversible, and a precedent for exactly this shape. **W22 IS THE BACKSTOP, NOT THE PLAN.** **What must not close it: W13b's own retention rule**, which governs new tables and reaches none of these rows. | **high** | **operator ruling, immediate** → W22 as backstop |
| new | **THE METERING FLAG, PRODUCT-PRINCIPLES §3.** The per-user **counter** is paid for now and is right. The **cap value** is global configuration (`CONVERSATION_MAX_TURNS_PER_DAY`) and would need to be per-user for a paid product. Cheap to move because it is config and not a column — **which is exactly why it is written down now rather than discovered then.** | low | W24 (multi-tenancy) |
| new | **PRD §8's RUNG-4 SENTENCE IS REFUSED IN BOTH HALVES BY RULINGS MADE ELSEWHERE.** *"a visible turn counter and a transcript you can read afterwards"* — the transcript is deleted (§2a, on §12.8's authority, **and §O2 puts that half in front of the operator**) and a visible counter is a tally (§8.6.4, CLAUDE.md §4). **Either §8 is amended or W15 overturns two rulings.** Not resolved by W13b. | medium | **W15** |
| new | **W13b's `.sql` WILL TAKE 025 AND SHIFT W18, AND HALF 2 CANNOT CATCH IT.** W13b has no row in the authoritative table by design, so **#130's missing both-halves check has nothing to compare** for this slice — the same is true of W15, W16, W17. Read with **#185** and **#130**. | low | W19 |
| new | **THE RETENTION SWEEP'S RESIDUAL: if the surface is never opened again, the last conversation's turns persist** until someone opens it or runs the human-run sweep. Accepted because a scheduled reaper cannot run (**#69**, `english-worker` not installed; `BUILD_PROGRESS.md:583`). **What closes it: #69, plus a reaper — or a decision that one conversation is an acceptable tail.** | low | W20 (with #69) |
| new | **PROPOSED DEVIATION AWAITING THE OPERATOR (§O1): W13b ships on Whisper, not Scribe v2.** PRD §8.6.2 and the W13b row both name Scribe v2. Its stated advantage is word-level timestamps and **this surface consumes none.** Adopting it is a wrapper change, a `_KNOWN_STT_PROVIDERS` member, a credential that does not exist, and a first call to a new vendor. **Recommended, not ruled — the row is the spec until the operator says otherwise, and a yes is an amendment to PRD §8.6.2 written as one.** | medium | **W13b (before implementation)** |
| new | **A VOICE-SOURCED CORRECTION MAY BE AGAINST SOMETHING WHISPER MISHEARD, AND IT IS SHOWN ANYWAY** (§2a.1). Bounded by the learner having seen their own transcript at the moment of the turn; **not eliminated** — a learner who did not read it can be corrected on Whisper's word. **Never written to `errors`**, so the journal is unaffected and #377's damage-shape does not recur. **What closes it: a measurement of how often Whisper's transcript diverges from what was said on this surface** — which nobody has, and which the first real sessions can produce. **What must not close it: suppressing the corrections**, which is the strict reading §2a.1 declined with its reason. | medium | W13b → W17 |

**CARRIED FORWARD, NONE DROPPED:** #57 · #69 · #76 · #108 · #130 · #160 · #169 ·
#185 · #196 · #271 · #292 · #299 · #303 · #306 · #321 · #335–#347 · #349 · #350 ·
#352 (`high`) · #354–#358 · #360 · #361 · #363 · #364 (`high`) · #365–#377.
**#348, #351, #353, #359 and #362 remain closed.**

**4. FILE INVENTORY** — **one file, and that is the entry:**
`prompts/CC-W13b-conversation-surface-PLAN.md`, the archived slice prompt and
this plan. **No code, no test, no `.sql`, no `apps/web` file, no `data/` change.**

**5. NEXT ACTION — this slice's checks plus every earlier check still unrun.
NONE DROPPED.**

0. **THE F2 READ — FREE, READ-ONLY, NO CONTENT, AND IT COMES FIRST BECAUSE IT
   COSTS NOTHING AND CHANGES THE SEVERITY OF EVERYTHING BELOW IT.** Claude Code
   has no SSH to this host, so this is a command for the operator to run, against
   the **`english` database on the production host** and no other. **It scans
   EVERY `task_type`, not only `conversation`** — that is #348's lesson applied
   (*ask what else in this product already does the thing*), and it answers
   whether anything besides `/talk` is holding turn bodies:

   ```bash
   psql -d english_bot -c "SELECT s.task_type, count(*) AS sessions, count(DISTINCT s.user_id) AS learners, sum(jsonb_array_length(s.payload -> 'messages')) AS turns_held, min(s.date) AS oldest, max(s.date) AS newest FROM sessions s WHERE CASE WHEN jsonb_typeof(s.payload -> 'messages') = 'array' THEN jsonb_array_length(s.payload -> 'messages') > 0 ELSE false END GROUP BY s.task_type ORDER BY sessions DESC;"
   ```

   **Counts and dates only. No content, and none is to be pasted into the
   record.** Paste the four numbers per row; **the ruling on the two interims is
   the operator's and nothing is cleared or disabled by this pass.**

1. **DEPLOY — #377 and #372 are both fixed and neither is live.** `0a` → backup →
   `git pull --ff-only` → `pip install -e packages/core` → **no migration** →
   restart → `sleep 5` → 401 — **and Vercel must rebuild**, or *Hear it* stays
   bare text and the stutter stays on screen.
2. **#376's cheap experiment** — two substitutions and two inflections, free on
   F0. Confirms or refutes the stated blind spot before W17 inherits it.
3. **#368's adjacency test** — the query exists, needs no new measurement.
4. **#374's track measurement** — expect most rows under `(no track)`.
5. **#364 — ASK THE SECOND LEARNER, AND ANSWER THE FOUR AZURE DATA-PROCESSING
   QUESTIONS.** Gates **#367**, the Galaxy half of **§2.5**, **and now W13b's
   voice half.** *(W13b's typed half is not gated and does not wait on this.)*
6. **The 0/0/0 row (#366)** — read it, delete it by its own id.
7. **W11b's own check, Sunday 2026-09-06 — #348's only independent proof.**
8. **W13-i's four remaining phone checks, from 2026-09-07.** **#341**, and
   **#373 depends on #341 staying shut.**
9. **#375's convention** — an issue row marked fixed names the commit.
10. **T1 · #352's 33 calls (journal aside first) · W10d commit 2 · T2 · T4.**
11. **#365 · #369 · #371 · #373 · #374 · #376.**
12. **W14's ✅ — all three acceptance criteria are met and the mark is the
    operator's.** **W11c's acceptances are all met and its ✅ is the operator's.**
13. **W13b's THREE OPERATOR DECISIONS, §O — needed before implementation opens
    and nothing else in this plan waits on anything:** **§O1** Whisper or Scribe
    v2; **§O2** the transcript deleted at close or kept; **§O3** the cap number.
    **Plus the F2 ruling from Next action 0's read** — clear the rows now,
    disable `/talk` now, both, or wait for W22.

**UNIT 2's CONTENT IS HELD on #299 and #249.** **#259 does not close and is not
narrowed.** **NO SLICE IS MARKED ✅ BY THIS PASS.**

---

## What this plan pass must not do — held

* **No code, tests, migrations or `apps/web` files.** None written.
* **No migration number taken.** 025 is identified as free-but-reserved and left.
* **No billed call.** None made.
* **#292's allow-list not widened** — and F4 shows widening it would have been
  the wrong edit.
* **No slice marked ✅.** W13b stays ⬜.
* **Nothing on production is cleared, disabled or written.** F2's read (Next
  action 0) is **read-only and names its database**; the two interims are
  written down and **neither is taken**. The bot's `/talk` stays registered.

---

## Verification of this plan pass

**There is nothing to run.** The plan is verified by being read, and by these
being true of the commit that carries it:

* the diff touches **exactly two files** — this one and `BUILD_PROGRESS.md`;
* `migrations/` still ends at `024_speech_attempts.sql`, and `schema_version`
  on production is still **24**;
* no `.sql`, no test, no `apps/web` file and no `data/` file is added or edited;
* no billed call was made, and nothing on the production host was read, written,
  cleared or disabled by this pass.

**The implementation that follows is verified by §3.5's measured first session
and by the row's own acceptance criteria** — a real conversation on a phone, text
and voice; every app turn coverage-checked with the ship-and-record branch
behaving as ruled; the day's cap refusing the turn after it in copy that passes
the banned-phrase scan **and carries no numeral**; one real API call before
shipping; the audio of a voice turn existing nowhere after the request; **the
turns existing nowhere after the close**; and the topic demonstrably reusing the
week's grammar target or the unit's lexis rather than being generic.

**AND TWO CRITERIA §2a.1 ADDS, WRITTEN HERE SO THE FIRST VOICE CONVERSATION DOES
NOT COME BACK AS A DEFECT REPORT:** **a conversation held entirely by voice ends
with corrections ON SCREEN**, and **`errors` gains no row from it** — both
checked on the same sitting, because either alone is the failure the other one
hides.

---

## Provenance

**Written 2026-09-04, committed 2026-09-05.** The four §8.6 rulings recorded in
§2 and §3 were **accepted by the operator in chat on 2026-09-04**; the record was
written the following day, and the two dates are stated separately rather than
collapsed. Send-backs **S1** (voice conversations must show something) and **S2**
(F2 needs an action, not a target) were answered before approval and are carried
in §2a.1 and in the F2 issue row. §O's three questions are the operator's and
are open at the time of this commit.
