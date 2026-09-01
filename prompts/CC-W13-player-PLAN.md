# W13 — Player + interactive transcript — PLAN (mode PLAN, no code)

**Context.** Block 2 (`input`) has been `empty` since W10 and PRD §4.1 gives it a video
at the learner's coverage with an interactive transcript. W12b built the pipeline that
selects and stores those videos (migrations 019/020, `core/video/`, `core/services/video.py`,
three videos assigned on production) and deliberately shipped **no route and no player** —
so the pool exists and nothing a learner can touch reads it. W13 is the first consumer.
It is also the slice that first puts scraped third-party text in front of a model (#292),
first creates cards from arbitrary captured text (#155, #162), first writes
`video_assignments.completed_at` / `resume_position_s` (#291), and first shows a coverage
figure to a learner (#288, #334).

**This pass produces a written plan and nothing else.** No code, no test, no migration,
no `.sql` file, no `data/` change, no `apps/web` change, no server step, no billed call.
`schema_version` stays at 20. W13's row stays **⬜ NOT STARTED** — W10b's precedent: 🟡
means code-complete, and there is no code. Nothing is marked ✅.

**Tree state, read from `git` and not from memory.** Branch `main`; HEAD
`9b0a272` *"W12b closing record: the criterion is met, #329 confirmed, the row goes 🟡"*.
Working tree is **dirty**: `BUILD_PROGRESS.md` (+170 lines) and `docs/TASKS-v3-web.md`
(+52) both carry **uncommitted W12r content**. See reconcile finding R0.

---

## §0 — Reconcile against the tree

Twelve disagreements. Each is a claim in this prompt, in `BUILD_PROGRESS.md`, or in a
source file that the tree contradicts.

**R0 — W12r IS NOT COMMITTED. The prompt's "the only files this commit may touch are
`prompts/` and `BUILD_PROGRESS.md`" is already impossible in this tree.**
`git status` shows `M BUILD_PROGRESS.md` and `M docs/TASKS-v3-web.md`. The diff is W12r's
six corrections, the #185 two-countings paragraph, #335–#339, and W13's new slice row —
described throughout the record as done, and present only as a working-tree change. Any
commit made now sweeps `docs/TASKS-v3-web.md` in with it. **The operator commits W12r
before W13's plan is committed**, or W13's commit silently becomes W12r+W13.

**R1 — the by-target issue count is stale within the commit that derived it. It is 22
open, not 20; the total is 30, not 28.** W12r/4 derived *"By target column: 22 … Twenty
are open"* from a named list of 22 rows (#124…#293). **That list omits #335 and #336** —
both filed by W12r itself, both with Slice cell `**W13**`, both `⬜ open`. Verified by
re-deriving the count off the live table: 24 rows match `W13`-not-followed-by-a-letter
excluding #278, of which **22 are open** (#124 and #180 closed). With the 8 open prose
rows the triage set is **30**. This is the shape #336 itself describes — a derived figure
that did not re-read the artefact it was derived from — arriving inside the row that
files it. **No issue is retargeted or renumbered by this plan; the number is corrected in
the triage table below and filed as a new low-severity row.**

**R2 — `assignments_for` is settled from the file, and the previous session's report was
right.** `packages/core/services/video.py:520` — signature
`assignments_for(conn, user_id, *, since: date) -> list[dict]`, docstring
*"What this learner has been given, newest first. For the CLIs to print."* It is a
**range** read (`assigned_for >= since`), returns plain dicts, and carries
`assigned_for, video_id, youtube_id, title, accent, track, resume_position_s, completed_at`
— **and no transcript and no coverage**. It is not W13's read path and must not be widened
into one; W13 adds a single-day read beside it.

**R3 — `upsert_video`'s `accent` annotation contradicts migration 020.**
`services/video.py:88` declares `accent: str`, while 020 dropped `NOT NULL` and
`PoolRow.accent`, `Candidate.accent` and `_pool_row` all correctly carry `str | None`.
The one write path still types the column as non-null. Cosmetic today (`channels.py`
refuses a null before it gets here) and wrong in the direction that produced #315.

**R4 — `score.py`'s band comment is stale: it says #289 is unvalidated; #289 is closed.**
`packages/core/video/score.py:38-43`: *"THE BAND IS RULED BUT NOT YET VALIDATED (#289)."*
#289's status cell reads *"✅ ANSWERED AND CLOSED 2026-09-01 — the band is re-validated on
six real transcripts against THREE REAL LEDGERS and stands unchanged at 93–98%."*
The code comment is the pre-validation text.

**R5 — ARCHITECTURE §6 still sells a segment the operator overruled.** Line 223:
`GET /video/today → assigned video + segment + transcript + coverage`. The 2026-08-30
ruling struck the segment; 019's header says PRD §7.2 **and** ARCHITECTURE §5 were
corrected in that commit — §5 shows `~~segment start/end~~`, **§6 was not touched**.
W13 is the slice that builds this exact route, so it inherits a spec line that describes
a thing that does not exist.

**R6 — PRD §7.3 has the same untouched word, in the bullet that assigns W13 work.**
*"after the segment: 5 comprehension items, then 5 mined phrases into the deck."*
Same strike, same commit, same omission. Both R5 and R6 are corrected in place with the
old text quoted (#82's shape) in the implementation commit, not here.

**R7 — the model ban's scan root is `core/video/` and does not reach the module that
actually holds the scraped text.** `tests/test_core_boundary.py:488`
`VIDEO = CORE / "video"`; `VIDEO_MODEL_CALLERS = set()`, pinned empty at :1014.
**`packages/core/video_api.py` is outside that root** — and it is the module that fetches
transcripts from Apify (`_run_actor`, `fetch_transcripts`). It imports no model today
(checked: `httpx`, stdlib only). So the guarantee is real but narrower than
"nothing in the video path can reach a model": it covers the package, not `video_api.py`
and not `core/services/video.py`.

**R8 — `lexemes` has no definition column, so §1a's option 3 cannot produce a definition.**
`migrations/010_lexicon.sql:41-52`: `lemma, pos, freq_rank, freq_band, cefr, origin,
created_at`. Nothing glossy. A no-generation tap can show rank, CEFR band and ledger state
(`known`/`learning`/`seen`), and `cards.meaning` **if the learner already has a card** —
and for the unknown word that a tap exists to serve, it can show nothing at all. The
option as the prompt words it is not available; the honest version of it is stated in §1a.

**R9 — the slang acceptance criterion is gated by the schema, not by the UI.**
`migrations/013_cards.sql:222-228`, `cards_informal_shows_the_four_things`: an
`informal`/`slang` card **cannot be inserted** unless `context_sentence`, `meaning`,
`neutral_equivalent` **and** `who_says_this` are all non-NULL. W13's fourth criterion —
*"a slang line … produces a card showing meaning, neutral equivalent and who-says-this"* —
therefore **requires generation**. If §1a resolves to "no generation at all", that
criterion is unsatisfiable by INSERT and must be reported and dropped, not weakened
(CLAUDE.md §3 rule 7). This is the hardest coupling in the slice and the prompt does not
name it.

**R10 — the two-cards criterion does NOT collide with either unique index.**
`cards_one_card_per_lemma` is `(user_id, lexeme_id, card_type) WHERE lexeme_id IS NOT NULL`
(`015_capture.sql:121-123`), so two cards of **different `card_type`** on one lemma are
permitted — PRD §7.3's *"cloze + production"* fits. 013's
`UNIQUE (user_id, source_chunk_id, card_type)` does not bite because a video capture has
`source_chunk_id IS NULL`. What does bite is the **second tap on the same word**:
`UniqueViolation` where a route must answer politely — which is #178, already filed, and
now confirmed as the normal case rather than an edge one.

**R11 — the register panel W13 needs already exists and needs no new component.**
`apps/web/components/cards/card-face.tsx:284-300` renders a `card-register-panel` with
register, `neutral_equivalent`, `who_says_this` and the source sentence, guarded by
`register === "slang" || register === "informal"`. W13 supplies the four fields; it does
not build a second renderer. Likewise the frontend no-guilt gate already covers every
shipped `.tsx` (`tests/test_web_shell.py::test_no_guilt_copy_anywhere_in_the_frontend`),
so W13's new strings are in scope automatically.

**R12 — THERE ARE NO PER-CUE TIMINGS ANYWHERE IN THIS DATABASE, SO EVERY
TIMESTAMP-DEPENDENT FEATURE IN W13's ROW HAS NO DATA BEHIND IT.** *(Found on the
revision pass, while answering S3. It outranks S1–S5 and it changes the half this review
approved, so it is raised before anything else in the answers below.)*

**The evidence, three files:**

- `videos.transcript` is a single **`TEXT`** column (019). There is no cue table, no
  `JSONB` of segments, no start-offset column anywhere in 019 or 020.
- `video_api._read_text` (`:812-825`) returns the **first non-empty** of the adapter's
  `text_keys`, and for the ruled actor `johnvc/YoutubeTranscripts` those are
  `("non_timestamped", "transcript", "text")` — **`non_timestamped` FIRST, deliberately**
  (`:234`). When the value is instead a list of segments, the fallback branch joins
  `str(seg.get("text", ""))` and **discards every `start`** (`:819-822`).
- `refresh.py:499-505` writes `outcome.text` — that one flattened string — through
  `record_transcript` into that one `TEXT` column. Nothing else is kept.

**What has no data behind it — four features, and each is owned by exactly one half, so it
is reported unmet once and by the right slice:**

| # | Feature | Owned by | Criterion it touches |
|---|---|---|---|
| 1 | Word-clickable transcript **synced to the player** (the follow-along highlight) | **W13-i** | none of the row's four — it is a Build-column feature |
| 2 | **Loop-a-line** | **W13-i** | Build column |
| 3 | **0.75× on a line** (as against on the whole video, which needs no timings and **is** buildable) | **W13-i** | Build column |
| 4 | The **timestamp** on a created card | **W13-ii** | **acceptance criterion 1**, second half |

**So criterion 1 is reported unmet-in-half by W13-ii and by nothing else.** W13-i reports
three Build-column features held, not a criterion. Neither half reports the other's.

**Downstream and not W13's:** PRD §7.5 step 3's *"tap any line to reveal it"* inherits the
same gap and belongs to **W13a**, which is named here so W13a does not rediscover it.

**What does survive, and is what W13-i builds now:** the transcript as readable text,
unknown-word highlighting, the coverage badge, resume position, the watch signal,
whole-video 0.75×, and Add-to-deck carrying the exact **sentence** — the sentence is
recoverable from the flat text; only the offset is not.

**This contradicts §2g's no-DDL conclusion and the premise on which the player half was
approved as *reaching no model, costing nothing, needing no migration*.** It is reported
rather than worked around (CLAUDE.md §3 rule 7, and §8's *do not silently widen*). The
three ways out, with what each costs, are in §2g below. **The one that may cost nothing is
T5, added to §5** — `--dump` writes the actor response **verbatim** (`video_api.py:491-494`,
the fix for #317), so if the billed run was dumped, the timings may already be on the host
and recoverable for free.

**Checked and found to agree with the prompt** (stated so an empty result is deliberate
where it is empty): the three tables' column lists and every header ruling quoted at them;
`test_completed_at_has_no_writer_in_this_slice` (`tests/test_video_service.py:503`) and
its two assertions; `blocks.py`'s block-2 contract, `visible_target`'s naming seam and
`first_open_block`; W6's `visible_projection` / `presentations_for` contract and its
allow-list at `test_core_boundary.py:766-768`; the authoritative migration table
(021 W13a → 022 W14 → 023 W18, already shifted); `apps/api/routers/` has no `video.py`
and `main.py` registers eight routers, none of them video; the 22/8 method itself; #288's
four ranks (`john` 548, `michael` 763, `paris` 1107, `sarah` 1221); Vitest's 11 files.

---

## §1 — Three collisions, ruled

### 1a. Tap-to-define generates while a learner waits — **OPERATOR'S RULING, NOT TAKEN HERE**

The 2026-08-27 standing ruling: the app never generates while a learner waits, and never
while nobody is watching. #182's fork was decided on it as *generated once and stored,
ahead of the session*, recorded as independent of #69. All three of W13's generating
surfaces — tap-to-define, register detection on save, comprehension items — are on-demand
generation with a person watching.

**The plan does not choose.** The four options, each with its cost model and what it costs
the record:

| | What it is | Cost model | What it costs |
|---|---|---|---|
| **1** | **Pre-generate.** A human-run command produces definitions + register tags for the below-floor words of each assigned transcript before the week. | One billed pass per assigned video. Volume is bounded and knowable: 3 videos/week × 2 learners; the below-floor word list is computable free, today, from `coverage_for`. **The floor has no measured model — #290 open, #320 open, #321 ruled that the floor needs a different instrument rather than a correction — so the projection must be measured against one real charge before it is trusted.** | A tap on an unpredicted word (a name, an inflection the lemmatiser missed, a multi-word phrase) returns nothing. Honours the standing ruling in both halves. |
| **2** | **On demand, ruling amended.** The learner waits ~2–4 s per tap. | Per-tap, unbounded, driven by learner curiosity. **A money path with no ceiling and no measured floor.** #321's ruling stands: the existing floor under-reported a real charge by ~4,900×. | Satisfies the ruling's second half (never while nobody is watching) and **breaks its first**. The amendment is the operator's to make in writing; it is not a plan's to assume. |
| **3** | **No generation at all.** | Zero. | **Not available as worded — see R8.** `lexemes` holds no gloss. What this option can actually show is: ledger state, frequency rank, CEFR band, and `cards.meaning` when the learner already has a card. Register detection cannot happen (PRD §8.5.3 unmet), and **by R9 no slang card can be inserted at all**, so W13's fourth acceptance criterion is dropped with its number reported. |
| **4** | **Split by surface.** | Mixed. | The separable line the plan believes is real: **the player needs no model; capture does.** Highlighting, the badge, subtitles, resume and the watch signal are all pure reads over stored text (loop and per-line 0.75× are not — R12). Tap-to-define, Add-to-deck and register detection are the model half. This is the basis of the §3 split and it stands whichever of 1/2/3 the operator picks for the model half. |

**What the plan records as its recommendation, flagged as assistant-recommended and NOT
adopted:** option 4 for the shape, option 1 for the model half — pre-generation is the
only one that keeps the 2026-08-27 ruling whole, and it is the only one whose cost is
knowable before the first charge. **This is a recommendation, not a ruling.** No
implementation follows from it until the operator answers.

**Comprehension items are proposed OUT of W13 entirely** regardless of the answer — see
§3. They belong with PRD §7.5's movement rules, which are W13a's.

### 1b. `video_coverage` on its first read — **RULED: recompute at read time**

**Ruling: the badge recomputes coverage over the stored transcript at read time.
`video_coverage` stays an audit record and is not read by any product path.**

The reason is the original ruling's own: *"recomputation over stored text is pure CPU and
costs no external call, so the staleness class is REMOVED rather than managed"*
(019 header; repeated at `services/video.py:record_coverage`). `core.video.assign` already
recomputes on every run — the badge is doing what assignment does, one layer up. Nothing
about the table changes; the sentence *"it is never read back"* stays true, and the
`lexicon_digest` keeps meaning exactly what it means today.

**Declined: read the stored value.** It would make the table a cache on its first read and
oblige this plan to write the invalidation rule 019 deliberately did not write. That rule
would key on three inputs, none of which is tracked: `lexicon_digest` (which already
hashes `normalize.py`'s source, correctly — W12a's `-er`/`-est` deletion changed no data
file), the transcript's own identity (which the purge can null and refetch), and the
learner's ledger, which moves every time a card is graded. A guarantee nobody checks is
the family filed at #281. **Taking the stored value without ruling is the option this
section exists to refuse.**

**Consequence for #336:** its stated close — *"the per-video figures read from
`video_coverage`, joined `(user_id, video_id)`"* — is an **operator query**, not
something the badge does. #336 does not close on W13 shipping.

### 1c. #335 — the purge can empty a transcript under an assigned video — **RULED**

**Two parts, and the first is the one W13 owes unconditionally.**

**(i) The player treats an absent transcript as a first-class state, not an error.** The
`videos` row survives the purge with its `youtube_id` intact (019 header, by design), so
the video is still watchable. The screen: the embed plays; a one-line neutral statement
that the interactive transcript is not available for this one; **no coverage badge**
(coverage cannot be computed without the text, and a stale number is worse than none);
no highlighting; no tap; Add-to-deck unavailable. No guilt language, no apology, no
"expired". **This screen exists whichever way the rest is ruled**, because the purge can
also fire between the read and the next assignment.

**(ii) The close: refuse to assign a video within N days of its purge cutoff.**

**S2 — settled from the code, and the two 30-day positions read ONE clock.**
`purge_stale` (`services/video.py:259-303`) is the **only** writer that nulls a transcript
outside the fetch path — verified by grep: the three `SET transcript` sites in
`packages/core` are `record_transcript` (:184), `record_transcript_failure`'s status CASE
(:229) and this purge (:290). It has **one** caller, `refresh.py:521`. Both of its
statements — the `scanned` count and the `UPDATE` — key on
**`metadata_refreshed_at < now − days`**, and the single `UPDATE` nulls
`title, duration_s, published_at` **and** `transcript, transcript_lang, captions_kind`
together, in one statement, on that one predicate.

So the §III.E.4.d metadata cap and the conservative transcript policy are **two rulings
implemented on one timestamp**, and 019's header is right that they are different rulings
while the code gives them the same clock. **The refusal keys off
`metadata_refreshed_at`, which is the column the purge reads.** The send-back's failure
mode — a guard confidently wrong in both directions — does not arise.

*(Worth recording as a consequence, not as a defect: because they share a column,
`metadata_refreshed_at` is stamped by `upsert_video` on **every** refresh that re-reads
the video, so a refreshed row's transcript clock resets even when the transcript itself
was not re-fetched. That is the existing behaviour and W13 does not change it.)*

`core.video.assign` gains one predicate — candidates whose `metadata_refreshed_at` is
older than `RETENTION_DAYS − N` are excluded, with the exclusion printed in the ranking
table like every other exclusion. **N = 7**, so a video assigned on Monday still has its
transcript on Friday. This is #335's candidate (a).

**Declined: (b) re-fetch on read.** It spends money on a learner's tap, collides head-on
with the human-run rule (#196) and with the 2026-08-27 standing ruling, and is §1a option 2
wearing different clothes.

**Declined and forbidden: extending or removing the purge.** Thirty days is a policy
ruling written into 019's header and `data/LICENCES.md`; loosening a compliance-adjacent
position to fix a scheduling problem is the trade #335's own row forbids.

**Note against the recommendation:** (ii) is a change to `core/video/assign.py`, which is
outside a player slice's natural footprint. It is proposed here because #335 names W13 as
its owner and because the predicate is four lines. If the operator prefers it in its own
commit, (i) still ships and #335 stays open with (ii) named.

---

## §2 — What the plan specifies

### 2a. The read path, the routes, and their caller

W12b shipped no route deliberately, because a route with no caller is a defect class this
record has named twice. **W13 ships both halves or neither.**

**Service** — `packages/core/services/video.py`, new function beside `assignments_for`
(not a widening of it, per R2):

```
today_for(conn, user_id, *, on: date) -> TodayVideo | None
```

One day, one row, `LEFT JOIN videos`. Returns `youtube_id`, `title`, `duration_s`,
`transcript`, `transcript_lang`, `captions_kind`, `accent`, `track`,
`resume_position_s`, `completed_at`. Returns `None` when nothing is assigned for that
date (Tue/Thu/Sat/Sun are not video days — PRD §7.1 is Mon/Wed/Fri). A row with
`transcript IS NULL` is returned, not filtered — §1c(i) needs to distinguish
*no video today* from *a video whose transcript is gone*.

**Routes** — new `apps/api/routers/video.py`, registered in `apps/api/main.py`:

- `GET /video/today` → the assigned video, the transcript projected for the client, the
  unknown-word set, the qualitative badge (§2c). Reaches neither `llm.py` nor `speech.py`;
  written as a plain `def` regardless, matching the house convention and #7.
- `POST /video/{video_id}/save-word` → creates the two cards. **If §1a resolves to
  option 1 or 3 this route reaches no model** (it reads a pre-generated row or writes
  from existing material). **If option 2, it calls `chat()` and is a plain `def`, never
  `async def` — #7, non-negotiable.**
- `POST /video/{video_id}/progress` → `resume_position_s`, and the watch signal (§2b).
  Throttled client-side; one service call.

Each route parses, authorises, calls **one** service function, serialises (CLAUDE.md §2).

**Serialiser.** W13 writes **no second serialiser**. The transcript projection is not an
item and never touches `visible_projection`; W6's contract and
`test_exactly_one_module_projects_an_item`'s three-module allow-list are untouched.
Cards go out through `cards_service.card_face` and nothing else — #190's rule, held by
`test_only_one_function_builds_a_card_face`.

**Caller.** `core/services/sessions.py::_input_block` stops returning `("empty", {})`.
Block 2 becomes `ready` when a video is assigned for today, `empty` when none is (an
honest fact after a successful read), `unavailable` only from a caught exception —
`BLOCK_STATES`' distinction, unchanged. `apps/web/components/session/blocks.tsx`'s
`InputBlock` renders the player in place of `<Empty>`. **The player ships inside the
session and not as a standalone tab**: #160's finding is that a screen with its own
counter becomes a backlog, and CLAUDE.md §4 forbids presenting one. ARCHITECTURE §3's
`watch/[videoId]/` route is therefore **not built**, and §3 is corrected in place rather
than left describing a directory that does not exist.

### 2b. #291 — what "answered" means for a video

**S3 — #258 is named, and the plan changes to AUTOMATIC ONLY. The explicit control is
withdrawn.**

The ruling of 2026-08-29 (`BUILD_PROGRESS.md` decisions log, 2026-08-29):
*"BLOCK COMPLETION IS AUTOMATIC, THE MANUAL BUTTON IS GONE"* — operator's words,
*"a signal that requires five taps below the fold is not a signal — it is a form nobody
fills in"* — **the button, its route and its service function all deleted**, and a
**per-kind** rule established because the five blocks are not uniform: *"`review` and
`focus` are derivable from logs keyed on `session_id`; **`input` serves nothing and is
`empty`, never `done`**; `output` cannot self-report at all; `close` is a summary."*

**What `review` and `focus` had that `input` did not: a per-attempt log keyed on
`session_id`** — `card_reviews` and `item_attempts`. That is the whole of the distinction,
and the ruling's `input` clause is not a rule about block 2's nature; it is a statement
that block 2 **served nothing**, and it expires the moment W13 makes it serve something.
**W13 creates the missing log.** The progress ping is block 2's `card_reviews`.

**So the ruling is honoured by building the log, not by adding a tap**, and the plan's
first draft had it backwards. Revised:

**One producer, one caller.** `core.services.video.mark_watched(conn, user_id, video_id,
*, at: datetime)` is the only writer of `completed_at`, and the **only** path that reaches
it is the position ping reporting ≥ 90% of `duration_s`. No learner-tapped completion
control is built, and none of the deleted button, route or service function returns.
`resume_position_s` is written by the same throttled ping, clamped to `[0, duration_s]`.

**The gap, documented rather than papered over: `duration_s IS NULL` leaves no
denominator.** `length_fit` already collapses that state with `>= 1800` and the breakdown
cannot separate them (#330); **T3 measures how large the gap is** — if `2jLhZjfu5-o` has a
NULL duration then one of three currently-assigned videos can never reach `done`, and
block 2 stays `ready` forever for it. **In that state the block stays `ready` and the
session is honest about it** — the same posture `input` has held since W10, and better
than a completion inferred from nothing.

**AND THE DAY-TWO CONSEQUENCE, STATED AS A COST RATHER THAN LEFT TO BE FOUND ON A PHONE.**
A block 2 that can never reach `done` is a block `first_open_block` keeps returning, so
**that learner opens the app the next day and the next and lands on the same video, for as
long as it is assigned.** `resume_position_s` means it *resumes* rather than restarts, so
it is not the app re-offering something already watched — but it is a block that presents
as unfinished forever, which is **#188's *the app is not paying attention* on a new
surface.** The posture is still right (be honest rather than infer a completion from
nothing) and the fix is still the free metadata re-read on the refresh path, not a control
on the player — but the cost is named here so it is a decision and not a discovery. Two things that do **not** close the gap and are
refused here: writing `done` on the ping's mere existence (position is not comprehension,
and a block that served nothing being marked done is exactly what #258 forbids), and
back-filling `duration_s` from the player client (the browser reporting a duration the
refresh path never fetched is an unaudited write to a column the purge owns).

*(If T3 shows the NULL-duration case is real and common, the honest fix is a
**metadata re-read** on the refresh path — free, one quota unit per 50 ids — not a control
on the player. That is named here so it is not rediscovered as a UI problem.)*

**#190's rule is still what governs the shape** — one contract, one producer — and it is
now satisfied with one caller rather than defended across two.

**The test is amended with its reason, in the diff.**
`tests/test_video_service.py::test_completed_at_has_no_writer_in_this_slice` asserts
`completed_at IS NULL` and `resume_position_s = 0` after `assign_video`. W13 breaks it the
moment it writes. It is **renamed and rewritten**, not deleted, to
`test_assigning_a_video_does_not_complete_it` — keeping both original assertions against
`assign_video` (which still must not write either column) and adding the positive
assertion that `mark_watched` is the only thing that does. **The guarantee that survives
is the one that was actually worth having.**

**What this unblocks:** block 2's `input` stops being `empty` and can reach `done`;
`first_open_block` starts landing learners on block 2; `completed_count` starts counting it.

**What it does not:** `sessions.completed` is still unreachable, because `output` cannot
self-report (#259). The nudge ladder stays broken. **That is not W13's to fix** and is
stated here so no one reads a working block 2 as evidence that it was.

### 2c. The coverage badge — **RULED: no percentage reaches a learner**

**Ruling: the badge is qualitative. Three words, no number, ever.**

Three independent reasons, none of which is a taste:

1. **#288 is open and unmeasured.** The assumed-known floor counts proper nouns as
   vocabulary — `john` 548, `michael` 763, `paris` 1107, `sarah` 1221, all inside the
   top-2,000 floor, all in `coverage_reference()`. The inflation is largest on
   dialogue-heavy transcripts, which is exactly what this pool is (#314: eleven channels,
   all performed, edited or taught; #329: five of six real videos below the floor).
   **#288's own first measurement is still untaken.**
2. **#334.** There is no coverage column on `video_assignments`, and `score_breakdown`'s
   `coverage_fit` returns 1.0 anywhere inside 93–98% — extracting it would display
   **1.0 as 100%**. The only real figure is `video_coverage.coverage`, and §1b rules it
   recomputed rather than read.
3. **#330.** `5E5tNu4NsxM` is 17 seconds long with a 234-character transcript and a stored
   coverage of 85.7%. A percentage over 234 characters is a measurement of one paragraph,
   and it lands wherever those tokens happen to fall — including inside the band by
   accident.

**The band shown:** three labels derived from the recomputed figure against `score.py`'s
existing constants (`DROWN_FLOOR`, `BAND_LOW`, `BAND_HIGH`, `NOTHING_LEARNED_CEILING`) —
below-band / in-band / above-band, worded as difficulty and never as a score.

**S1 — the `proper_nouns_detected` suppression is corrected, and the ruling is unchanged.**
The first draft called it a live suppression *"the instrument is known to be reading
high"*. **That is the borrowed premise #288 has measured and withdrawn.** On production,
2026-09-01, over six stored transcripts **including three from auto-generated tracks**:
`proper_nouns_detected` **TRUE on all six**, `casing` conventional on all six,
`degraded_288 = 0`. `johnvc/YoutubeTranscripts` returns conventionally cased text even for
auto-generated tracks — *"YouTube auto-captions are lowercase"* is true of YouTube's
payloads and **false of this actor's output**, and the whole degraded-exclusion path
inherited it. Two consequences, both stated:

1. **The suppression has never fired and, on this actor, will not.** It is a **guard
   against a provider change**, not a live mitigation — #288's own wording. It is kept for
   the same reason `--allow-degraded`, `degraded_288` and the pool-starvation warning are
   kept rather than deleted: the premise is about *an actor*, and
   `codepoetry/youtube-transcript-ai-scraper` is in the adapter table and has never been
   measured. **It is labelled as a provider-change guard in the code and in the update
   block, so it does not read as load-bearing.**
2. **It does not address #288, which is this section's own reason 1**, and the first draft
   implied it did. The proper-noun inflation applies to **every** row equally — #288:
   *"it now inflates all six equally rather than three of them differently"* — so nothing
   keyed on casing can reach it. **The ruling stands and this suppression is not why.**
   The reasons the ruling stands are the three above, unchanged.

**And the flag was load-bearing in the other direction, which is why it is worth getting
right:** the one video that landed inside the band is auto-generated. Had the borrowed
premise held, all three generated rows would have been excluded and **the admissible pool
would have been zero.**

**The second suppression stands unaffected:** below a stated character threshold, no badge
at all (#330 — a percentage over 234 characters measures one paragraph).

**PRD §7.3's `"94% known — slightly hard"` is amended in place with the old text quoted.**
The measured number is unchanged, still written to `video_coverage`, still printed by both
CLIs, still `degraded_coverage_count`-visible to the operator. **The number is not lowered
and no bar is moved** (CLAUDE.md §3 rule 7): the plan declines to *display* a figure the
record knows to be wrong, and says by how much it cannot say.

### 2d. #292 — the prompt-injection surface

`test_core_video_never_calls_the_model` pins `VIDEO_MODEL_CALLERS` at `set()` and
`test_the_video_model_ban_is_total_and_not_an_allow_list` pins that emptiness. **W13 is
where that guarantee ends, and it must end by amendment and not by deletion.**

**Enforcement, four parts:**

1. **The transcript never enters a prompt as free text.** It enters as one delimited,
   escaped block in a user-role message, under a system prompt that states the block is
   material to be explained and that nothing in it is an instruction (CLAUDE.md §6).
   Necessary and, on its own, **insufficient** — #271 is the standing finding that a guard
   can refuse a bad draft and can never show that the model understood the rule.
2. **The structural half, which is what actually holds.** The response is schema-
   constrained: a fixed object (definition, register tag from 013's five-value enum,
   `neutral_equivalent`, `who_says_this`) validated before use. Anything unparseable is
   discarded, not repaired. **The model never chooses what is written** — the caller
   writes named columns from a validated object. No tool use, no URL fetch, no shell, no
   second call driven by the first call's output.
3. **The ban is amended to an allow-list of exactly one.** A new module — proposed
   `packages/core/video/explain.py` — becomes the single permitted member of
   `VIDEO_MODEL_CALLERS`, and `test_the_video_model_ban_is_total_and_not_an_allow_list` is
   rewritten to assert the set has **exactly that one member**, so the commit adding a
   second fails. The emptiness pin is replaced by a one-member pin, in the diff, with the
   reason written at it.
4. **The scan root is widened** to cover `core/video_api.py` (R7), so the module that
   fetches the text is inside the same fence as the modules that handle it.

**How it is tested, and what the test can and cannot show.** A committed fixture
transcript containing an injection string goes through the real path with the transport
mocked at `anthropic.Anthropic` (standing rule 7 — never at `chat()`, never at
`asyncio.to_thread`). Three assertions: the string appears in the request **only** inside
the delimited data block; the system prompt carries the data-not-instruction rule; a
model reply shaped as an instruction fails the validator and writes nothing. **What this
does not establish, stated rather than implied:** that the model obeyed the rule. It
establishes that a reply which did not is refused. #271 is the row that says why the
difference matters.

**CLAUDE.md §3 rule 2:** if W13 changes `llm.py`'s request construction, one real API call
is owed before shipping. If it only *calls* `chat()` with a new prompt, none is. **The
implementation commit states which, in the update block, before it ships.**

### 2e. Cards, register, and the four things

**What is created.** One tap → two cards of different `card_type` (PRD §7.3: cloze +
production), both carrying `context_sentence` = the exact transcript line,
`source_ref` = the video id and the timestamp offset, `source_title` = the video title,
`captured_at` = now. **R10: neither unique index refuses this.**

**Against what already exists, item by item:**

- **#178 — the route must refuse politely.** A second tap on a saved word hits
  `cards_one_card_per_lemma` and raises `UniqueViolation`, which through a route is a 500
  in front of a learner who did a normal thing. **The answer W13 chooses: the service
  returns an *already saved* result distinct from both success and failure**, and the
  route serialises it as 200 with an explicit state. The importer's row-level anti-join
  (`lemmas_with_a_card`) is reused for the pre-check; the index stays the guarantee.
- **#181 — a slang card has no lemma this schema can express.** `lexemes` has
  `lemma, pos, freq_rank, cefr, origin` and **nothing that distinguishes a sense**. Tapping
  *mid* in a transcript cannot tell whether the deck already teaches that sense.
  **W13 does not bolt a column onto `lexemes`.** The rule it adopts: a card whose register
  is `informal`/`slang` is written with `lexeme_id NULL` — outside the lemma-keyed
  guarantees, exactly as the 15 migrated recognition cards already are — and the
  already-saved check for such a capture is by `(user_id, context_sentence, front)`
  rather than by lemma. **Stated as a deferral with its cost**, not as a fix: two slang
  captures of the same phrase from two different lines will both be written. The identity
  question #181 poses is left open and its row stays open.
- **#179 — separately: `delulu` and `low-key` are absent from the seed list**, so any pass
  resolving them would grow the **shared, global** `lexemes` table. W13 does not resolve
  slang phrases to lexemes, so it does not grow it. `resolve_capture_lemma`'s
  multi-word-fails-`GROWABLE` behaviour already handles this for phrases.
- **#125 / #126 and PRD §8.5.4.** `cards_informal_shows_the_four_things` (013:222) makes
  all four a **schema fact**: an informal/slang card missing any of `context_sentence`,
  `meaning`, `neutral_equivalent`, `who_says_this` **cannot be inserted**. R9: this is why
  §1a's answer decides whether the fourth acceptance criterion is reachable at all. #126's
  re-tagging of the ~migrated `migration_default` corpus is **not** in W13 — it is one
  `WHERE register_source = 'migration_default'` away and is a separate, operator-timed
  pass. W13 writes `register_source = 'detected'`, a value 013 declared and **nothing has
  ever written**.
- **#158 — masked, not fixed, and W13 unmasks it.** The L1 gloss renders twice on a
  production card because `migrate_chunks.py:245` builds the front as
  `meaning + "\n" + gapped_hint` and `card-face.tsx` renders `card.meaning` again under
  the back. It stopped reproducing when #124's backfill changed what line 1 held.
  **W13 generates new fronts, so it can bring the duplicate back with nothing in the diff
  to explain it.** The plan's guard: the capture path **never** puts `meaning` into
  `front`. `front` is the target word or the gapped line; `meaning` is a column. Asserted
  by a Vitest case over a W13-created card face, since #154's whole-field guard is
  structurally unable to see a duplicate that lives inside one field.
- **#99 and CLAUDE.md §4's track weights.** Every import path that generates context
  inherits §4's 50/30/20, and W13 is the next one. The measured history is 50% work-framed
  (7 of 14 migrated cloze cards; 9 of 16 quiz scenarios). **W13's exposure is different in
  kind and it is stated:** the context sentence is the transcript's own line and is not
  generated, so W13 cannot re-introduce the bias in the *sentence*. Where it can is in the
  **register explanation and the who-says-this line** — free text, model-written, and
  exactly the "framing" surface #99 identifies. **The naturalness gate applies to those
  two strings** (§2f), and the W13 registered prediction (§4) includes a work-framing
  count over the first generated batch.
- **#155, #156, #162** — a one-character `back`, whether the component quotes at all, and
  the `ti`/`tru` tokeniser artefact. All three are "first slice creating cards from
  arbitrary captured text" rows and all three arrive here. `resolve_capture_lemma` already
  refuses `lemmatize` for exactly #162's reason and its docstring is the record of why;
  W13 reuses it unchanged and does not call `lemmatize` on a captured word.
- **#175 — the licence question, filed against W12/W13.** Storing a copyrighted subtitle
  line in `cards.context_sentence` in a product with paying users. **W13 does not settle
  it**; it names it as reached and carries it forward. The plan flags that W13 is the
  slice that makes it non-hypothetical, which is what 015's header predicted.

### 2f. The gates that get their first learner-facing copy

W12b was exempt because it shipped no string a learner reads. **W13 ends that.**

| Surface | No-guilt gate | Naturalness gate |
|---|---|---|
| Coverage badge (3 labels) | **Yes** — automatic, `test_no_guilt_copy_anywhere_in_the_frontend` covers every shipped `.tsx` | n/a — hand-written, reviewed as copy |
| Empty state: no video today | **Yes**, automatic | n/a |
| Empty state: transcript purged (§1c) | **Yes**, automatic — and this one needs the most care: it must not read as the learner's fault or as a failure | n/a |
| "Already saved" response copy (#178) | **Yes**, automatic | n/a |
| Definition panel text | **Yes** — but **model-generated, so the frontend scan cannot reach it (#110)**. Gated in `packages/core` via `copy_rules.BANNED_IN_CONTENT` before the row is written | **Yes** |
| Register / who-says-this line | Same — gated in core, not in the frontend | **Yes** — and this is #99's surface |
| Card front/back created by capture | Same | **Yes** |

**The split matters and is why the table has two columns.** `copy_rules.BANNED` is for
copy the app says; `BANNED_IN_CONTENT` is for English a learner reads as material, and
drops the bare words *wrong/incorrect/missed/failed/broke* because ordinary sentences
contain them. A transcript line is material. **The badge and the empty states use
`BANNED`; the definition, the register line and the card faces use `BANNED_IN_CONTENT`.**
Getting this backwards fires the check on shipped, correct content, which is how a check
gets switched off.

### 2g. Migration — **two questions, and only one of them is ruled**

**C1. This section previously read *"RULED: W13 needs no DDL, and takes no number"* while
R12 made it conditional — one document asserting both halves of one claim, which is
`test_no_row_claims_both_at_once`'s defect and the one W12r spent two passes correcting.
Restated, and the old heading is quoted here rather than deleted (#82's shape).**

| | Question | Status |
|---|---|---|
| **(a)** | What W13 **WRITES** | **RULED: no DDL, no number.** The table below establishes it column by column and it stands. |
| **(b)** | What W13 **READS** — per-cue timings (R12) | **OPEN. T5's.** Not ruled here, and not ruled by (a). |

**The consequence of (b), stated here rather than left to be re-derived:** if cues must be
stored, **W13-i takes `021`** and three unwritten rows shift by one — **W13a→022,
W14→023, W18→024** — in **both halves** of `docs/TASKS-v3-web.md`, the authoritative table
and each slice's Build cell, in the same commit as the `.sql` file. That is **#185's
eighth occurrence. The eighth is not to be taken casually, and this is the pass that
establishes whether it is needed** — which is precisely what T5 settles and what this plan
does not pre-empt.

**(a) — checked column by column, and every field W13 writes already exists:**

| What W13 writes | Column | Migration |
|---|---|---|
| watch signal | `video_assignments.completed_at` | 019 |
| resume position | `video_assignments.resume_position_s` | 019 |
| the exact line | `cards.context_sentence` | 013 |
| video id + timestamp | `cards.source_ref` (free `TEXT`) | 013 |
| video title | `cards.source_title` | 015 |
| capture time | `cards.captured_at` | 015 |
| detected register | `cards.register` + `register_source = 'detected'` | 013 (value declared, never yet written) |
| the four things | `meaning`, `neutral_equivalent`, `who_says_this` | 013 |

**So on question (a) alone, #185's eighth occurrence is not triggered: 021 stays W13a's,
022 W14's, 023 W18's, and `docs/TASKS-v3-web.md` is not renumbered in either half.**
Stated positively rather than by omission, because the prompt asked for the position either
way. **This is a statement about (a) and it does not answer (b).**

**(b) — the open question. R12, and it is not §1a's.** The table above is right about every
field W13 *writes*. It is silent about a field W13 needs to *read* and that nothing stores:
**per-cue timings.** Three ways out, and the plan takes none of them without the operator:

| | What it is | Migration | Money |
|---|---|---|---|
| **A** | **Recover from the dumps.** `--dump` writes the actor response **verbatim** (`video_api.py:491-494`). If the billed fetch was dumped, the timestamped form may already be on the host. **T5 settles it, free.** Then the timings are backfilled from the dump. | **Yes** — somewhere to put them | **No** |
| **B** | **Re-fetch with timings.** The adapter prefers `non_timestamped` at `:234`; the actor returns the timestamped form too, so this is one adapter-order change plus a billed run. | **Yes** | **Yes** — one billed event per video, and #320/#321 mean the projection cannot be trusted until one real charge is read |
| **C** | **Ship without timings.** Transcript readable and word-clickable but **not synced**; no loop-a-line; no per-line 0.75×; cards carry the sentence and **no timestamp**. | No | No |

**If DDL is taken (A or B), the shape is one column — `videos.transcript_cues JSONB` —
and not a `video_cues` table**: the cues are a property of the transcript, share its
lifecycle, and must be nulled by the same `purge_stale` statement on the same clock (S2).
That is `021`, and **#185's eighth occurrence**, shifting W13a→022, W14→023, W18→024 in
**both halves** of `docs/TASKS-v3-web.md` in the same commit. **The eighth is not to be
taken casually and this plan does not take it.**

**Option C is what the approved half can actually build today**, and it fails the
*"and timestamp"* clause of acceptance criterion 1. **Reported, not adjusted.**

**One further caveat, on §1a.** If the operator picks §1a option 1 (pre-generate), the
pre-generated definitions need somewhere to live. Three ways, in preference order:
(a) write them straight into `cards` at generation time — no DDL; (b) hold them in the
existing `video_coverage` row — **refused**, that table is an audit record and §1b just
ruled it is not repurposed; (c) a new `video_glosses` table — **this is the one case where
W13 would take 021 and shift three rows in both halves of the document**. The plan's
position: **(a), and no number.** If implementation shows (a) is not workable, that is a
stop point and comes back to the operator before a number is taken.

### 2h. The twenty-eight — which is thirty (R1)

**22 open by target column** + **8 open in prose** = **30**. Method as W12r/4's, re-derived
against the live table.

| # | Sev | Kept by W13 — what satisfies it | or Retargeted to |
|---|---|---|---|
| 335 | med | **Kept.** §1c: honest empty state (i) + assign-side refusal (ii) | — |
| 336 | low | **Kept, not closed.** §1b: the badge recomputes; the stated close is an operator query | stays open |
| 334 | — | context for 2c; already `⬜` under W12b | — |
| 293 | med | **Kept** (slang half) if §1a ≠ option 3; **else retarget** with the criterion dropped | W13-ii |
| 292 | med | **Kept.** §2d states the enforcement before transcript text reaches `chat()` | — |
| 291 | low | **Kept.** §2b defines the signal and writes both columns | — |
| 284 | med | **Kept.** §2c: no percentage; the highlight still marks names unknown — **the visible half remains and the row does not close** | stays open |
| 253 | low | **Kept.** The progress ping is the first input event with somewhere to live | — |
| 244 | med | **Retarget.** Unit 23's audio targets are a syllabus question, not a player's | W13a / operator |
| 241 | med | **Retarget.** Pragmatic-target gating belongs with work-track generation | W13a |
| 181 | med | **Kept as a stated deferral** (§2e). The row stays open | stays open |
| 179 | low | **Kept.** §2e: W13 does not grow `lexemes` from slang | — |
| 178 | med | **Kept and closed.** §2e: an *already saved* result distinct from failure | — |
| 175 | med | **Kept as reached, not settled.** The licence ruling is the operator's | operator |
| 174 | low | **Retarget.** Needs a larger series export | the series-import slice |
| 173 | low | **Retarget.** Container sniffing is the importer's | the series-import slice |
| 172 | low | **Retarget.** Same path | the series-import slice |
| 170 | low | **Retargeted with a target and a number (S5).** Its trigger is deck size, not a date; the deck was 29 at W8e and 33 at W10. **Target: the operator, at the deck-count read in W13-ii's own acceptance** — the capture slice is the one that grows the deck, so it is the one that can report the number. **What closes it: a deck of ≥ 100 cards**, at which point a due-card source is large enough that the empty-deck fallback stops running more often than the path it falls back from. If the deck reaches that another way first, it is ready earlier — which is the row's own wording. | **W13-ii → operator, at ≥ 100 cards** |
| 162 | low | **Kept.** §2e: `resolve_capture_lemma` already refuses `lemmatize` | — |
| 156 | low | **Kept.** §2e: quoting rule decided at the writer, not the component | — |
| 155 | low | **Kept.** A one-character `back` is refused at creation | — |
| 126 | med | **Retarget.** Re-tagging the migrated corpus is one `WHERE` and its own pass | a content pass |
| 125 | med | **Kept** if §1a ≠ option 3 — W13's capture is what produces the two missing fields | else W13-ii |
| **prose** | | | |
| 57 | — | **Kept as a prediction** (§4): work-framing count over W13's first generated batch | — |
| 99 | — | **Kept.** §2e/§2f: the naturalness gate over the register + who-says-this strings | — |
| 144 | — | **Retarget.** Whether a gate runs a card through `validate()` is unchanged by W13 | W10-owned |
| 158 | — | **Kept.** §2e: the front never contains `meaning`; Vitest case over a W13 card face | — |
| 159 | — | **Kept.** `l1_language` rides the envelope; the player's L1 subtitle track needs it | — |
| 167 | — | **Retarget.** Checkpoint `per_target` sum; W11's | W11 |
| 168 | — | **Retarget.** Item-type/target lists; W10c's | W10c |
| 259 | — | **Retarget, explicitly.** §2b: `output` still cannot self-report; the nudge ladder is W20's | W20 |

**Nothing in this table is executed by this pass.** The triage proposes; the
implementation commit does the retargeting, and the operator sees the proposal first.

---

## §3 — Scope, and what this plan refuses

**W13's row cannot be built as one slice.** It names nine features and pulls in a second
source pipeline. The evidence:

- The **slang acceptance criterion** says *"a slang line from a series export"* — the
  series export is the **Language Reactor / Trancy** import path (PRD §7.1's Tue/Thu),
  not the YouTube curated path this row otherwise builds. That is #172/#173/#174's
  territory and a whole second importer.
- **Comprehension items** (PRD §7.3) are the instrument PRD §7.5's ladder moves on
  (*"two comprehension checks at ≥85% → move up"*). They belong with **W13a**, which owns
  the ladder. Building them here creates a measurement with no ladder to feed.
- **Shadow-this-line** (§7.3, Azure) is explicitly W14/W15's.
- **Tap-to-define and register detection** are gated on §1a, which is an unanswered
  operator ruling. Everything else is not.

**Proposed split, keeping the W13 row exactly as W11→W11b/W11c and W12→W12a/W12b did:**

**S4 — the id. `W13e` is withdrawn; the two halves are `W13a`-style splits and are named
`W13-i` and `W13-ii`.** The record fixed the convention when W13b was added — *"the `b`
denotes scheduling position, **NOT a split of W13**"* — and W13b, W13c and W13d are all
scheduling positions while W11b/W11c and W12a/W12b are splits. Appending `e` would make
one suffix carry two meanings inside one id. **A hyphenated roman half-number reads as a
split at a glance and cannot be confused with the b/c/d series**, and it does not consume
a letter the scheduling series may still want. *Assistant-ruled; the decisions log records
the convention so the next reader is not left inferring it.* If the operator prefers
`W12a`-style lettering, the alternative that reads as a split without colliding is to
rename the row pair `W13a′`-fashion — **refused**, because `W13a` is a live, numbered,
unwritten slice and reusing its letter is worse than adding a hyphen.

| | Scope | Gated on |
|---|---|---|
| **W13-i** — the player | Embed + IFrame API; dual-subtitle transcript as **unsynced text**, English on and **L1 off by default**; unknown-word highlighting from the ledger; **qualitative** coverage badge before play (§2c); **whole-video** 0.75×; resume position; the watch signal (§2b, automatic only); block 2 wired; `GET /video/today`; `POST /video/{id}/progress`; §1c(i)'s purged-transcript state. **Reaches no model, costs nothing, and writes no column that does not exist.** **APPROVED AS SCOPED.** | nothing |
| **W13-ii** — capture and register | Tap-to-define; Add-to-deck (the two cards); register detection writing `register_source = 'detected'`; `POST /video/{id}/save-word`; #292's enforcement and the amended model-ban pin; #178's polite refusal. | **§1a's ruling** |
| **retargeted out** | Comprehension items → **W13a**. Shadow → **W14/W15**. Series-export slang → the series-import slice. | — |

**R12 holds THREE features out of W13-i, and they are named as held rather than dropped:**
the synced follow-along highlight, loop-a-line and per-line 0.75× (R12's table, rows 1–3).
**They are not in the scope cell above and they are not deleted** — they return under
§2g(b)'s option A or B, both of which take `021` and #185's eighth occurrence, and T5
decides which. **The fourth R12 feature, the card timestamp, is W13-ii's and is not
W13-i's to report.**

**W13-i as scoped above is buildable today with no model, no money and no DDL.** It is
smaller than the first draft claimed, and the difference is stated here rather than
discovered in the diff.

**What this refuses, in the open:** the fourth acceptance criterion (*a slang line
produces a card showing meaning, neutral equivalent and who-says-this*) **cannot be met by
W13 as split**, and by R9 cannot be met at all under §1a option 3. W10b's precedent applies
— **declined before it was set, rather than lowered after**. The criterion is reported
unmet with its reason, and its number is not adjusted, its band is not widened, and it is
not put behind a flag (CLAUDE.md §3 rule 7).

**What W13-as-split does meet on a phone — two of four, not three:** L1 subtitles off by
default; and the coverage badge before play (qualitative, per §2c's ruling, which itself
amends the row's implicit expectation of a percentage — **stated, not slipped in**).

**The first criterion is met by half.** W13-ii produces two cards carrying **the exact
sentence**; the **timestamp** is R12's, and until §2g is settled by T5 there is no offset
to carry. **Half a criterion is reported as half, not as met.**

---

## §4 — Registered predictions, stop points, acceptance

### Registered predictions (#57's precedent — written before any run that costs money)

Only W13-ii has a billed path. Before the first charge, and with the branch rule written
first:

- **P1.** The below-floor word count for the three assigned transcripts, computed free
  from `coverage_for`, is **predicted before it is run**; the number is written down, then
  measured. Branch: if it exceeds 300 per video, pre-generation (§1a option 1) is
  re-costed before anything is billed.
- **P2.** The measured charge for one pre-generation pass is predicted from the token
  count, then read **from the provider console** and compared. **#321's ruling is that the
  existing floor needs a different instrument, not a correction** — so a projection that
  matches within an order of magnitude is the bar for trusting it at all, and a mismatch
  is reported, not smoothed.
- **P3 (#57/#99).** Over the first generated batch of register + who-says-this lines, the
  work-framed proportion is predicted, then counted. Branch: above 20% (CLAUDE.md §4's
  cap) the prompt is changed and the batch is regenerated — the cap is not raised.

### Stop points — the operator can halt between each

1. **After the read path + `GET /video/today` + block 2 render**, before anything else.
   Verifiable on a phone with no model and no charge. **This is inside W13-i's approved
   scope and is the first thing that can be looked at.**
2. **After W13-i's remaining approved scope** — badge, highlighting, resume, watch signal,
   purged-transcript state. Still no model, no money, no DDL.
3. **Before any of R12's three held features is started** — they are gated on **T5** and
   on §2g(b), and starting one before T5 answers is spending `021` on a guess.
4. **Before §1a is answered.** W13-ii does not begin. W13-i needs nothing from it.
5. **After the model-ban amendment and the injection test** (W13-ii), before the first
   prompt runs against real transcript text.
6. **Before the first billed call** (W13-ii, or §2g(b) option B), with P1/P2 registered.
7. **Before any migration number is taken.** §2g(a) says none is needed for what W13
   writes; §2g(b) is open. If implementation reaches for a number, it stops here.

### Acceptance — what a suite can assert

- `GET /video/today` returns the assigned row for a video day and `None`-shaped for a
  non-video day, through the **ASGI transport** (CLAUDE.md §3 rule 1).
- Block 2 is `ready` with a video, `empty` without one, `unavailable` only from a caught
  exception.
- `assign_video` still writes neither `completed_at` nor `resume_position_s`;
  `mark_watched` is the only writer of the first (the amended test, §2b).
- No percentage appears in any player string (a scan, alongside the existing no-guilt scan).
- **`videos.transcript` is read for the badge and for highlighting from the SAME string**,
  so the two instruments cannot diverge (T5's fifth question).
- The badge is withheld when the transcript is below the character threshold (#330), and
  when `proper_nouns_detected` is false — **the latter is a provider-change guard that has
  never fired on this actor (S1) and the test asserts the behaviour, not a live condition.**
- A purged transcript renders the §1c state and no badge.
- `VIDEO_MODEL_CALLERS` has exactly one member; the injection fixture's assertions (§2d).
- A W13-created card face does not render `meaning` twice (#158, Vitest).
- A second tap on a saved word returns *already saved*, not a 500 (#178).
- Every W13 string passes `BANNED`; every generated string passes `BANNED_IN_CONTENT`.

### Acceptance — what only a person on a phone can check

- The video plays, and the transcript is readable beside it. **Not** the follow-along
  highlight — that is R12's, held, and is not checked here or reported unmet here.
- **L1 subtitles are off until tapped** — the row's criterion, and a default nobody can
  assert from a test the way a person can see it.
- The badge reads as difficulty and not as a score, and does not read as a judgement.
- Highlighting marks words the learner genuinely does not know — **and #284 predicts it
  will also mark names**, which is the visible half of that row and the reason it stays
  open.
- The purged-transcript screen does not read as the learner's fault.
- **Two cards carry the exact sentence** (W13-ii) — **and NOT the timestamp, which R12 removes until §2g is settled.**

---

## §5 — The free reads that are owed, and what they change here

**Claude Code runs none of these.** Every one is an operator command.
`/home/bot/english-bot`, `sudo -u bot`, `.venv/bin/python` (plain `python` is not on this
host's PATH), `set +H` first. Never `ssh bot@<host>`, never `/opt`, never
`english-worker` (#69). One at a time; stop at the first whose evidence does not match.

**Order:** commit W12r · fix the three `scp` sites (C3) · **T5** · **T3** · **T1** ·
**§1a** · T2, T4, `0a`.

**T5 is placed first only because it gates the migration question.** T3 is one line and
settles §2b's gap size and §2c's threshold, so **running T3 first costs nothing and this
plan is not to be read as forbidding it.** T1 stays ahead of §1a for its own reason (it
orders the operator's decisions, below), and `0a` stays ahead of any row carrying a SHA.

**None of them blocks W13-i, which can begin now.**

```bash
set +H; sudo -u bot psql -d english_bot -c "SELECT youtube_id, duration_s, transcript_lang, captions_kind, length(transcript) AS chars FROM videos WHERE youtube_id IN ('y_525lzqbg0','a6uHw72_BnU','2jLhZjfu5-o');"
```

*What it changes.* `length_fit` returns 0.0 for `duration_s >= 1800` **and** for
`duration_s IS NULL`, and `score_breakdown` cannot tell them apart (#330). If
`2jLhZjfu5-o` has a **NULL** duration, then **§2b's automatic 90% watch signal has no
denominator for one of the three assigned videos**, and since S3 withdrew the explicit
control there is then NO writer for it: block 2 stays `ready` for that video and can never
reach `done`. That is the documented gap, and its size is what T3 measures. It also tells §2c whether any assigned transcript is short enough to trip
the no-badge threshold.

### C3 — the transfer command T5 depends on cannot succeed, and there are THREE of it

W12b's closing record **section N** (`BUILD_PROGRESS.md:4380`) gives, for the fetch dumps
at `/home/bot/phase-b-fixtures/run2/`:

```
scp bot@<host>:/home/bot/run2.tar.gz ~/Downloads/
```

**The Environment table, in the same file at `:175`, says it cannot work:**
*"`root@78.46.240.136`. The `bot` service account has **no inbound SSH key and no
password** — reach it with `sudo -u bot -i` from root."* **This is #215's shape, live, in
the block T5 depends on** — a runbook line that has never been executed as written, with
the contradicting statement four thousand lines above it in the same document.

**The send-back named one site. A sweep of `scp ` over the file finds three, all the same
defect:** `:4380` (section N, run 2's fetch dumps), `:4790` (`scp -r bot@<host>:.../run2`),
`:5061` (`scp bot@<host>:/home/bot/phase-b-fixtures.tar.gz`). **All three are corrected in
place with the old text quoted, in the same commit as this revised plan**, and the
correction is the same in each: the account is `root`, the host is the Environment table's
`78.46.240.136` (**not** `78.46.240.196`, which #301 records as written outside version
control and not connecting), and the files under `/home/bot` are readable by root:

```bash
scp root@78.46.240.136:/home/bot/run2.tar.gz ~/Downloads/
```

**Filed as a SIGHTING on #215, not as a new row** — the row exists, its severity stays
`medium`, and a second row would be #215 wearing a different number.

**#317's outstanding half travels in the same transfer**, as section N already instructs:
`/home/bot/phase-b-fixtures/actor.list.001.json` is **14,374 bytes** and the committed
copy is a re-serialised **slice**, so the byte-identity #317 was ruled in to guarantee does
not exist yet. It is brought across with the fetch dumps and committed beside them; **no
test asserts byte-identity until the original is there**, which is section N's own ruling
and is not changed here.

### T5 — NEW. It decides §2g(b) between options A, B and C. Free.

**C2. T5 reads the response BODY, not the adapter's key list.** R12's inference —
`text_keys` naming `non_timestamped` **first and deliberately** implies a timestamped
sibling — is a claim about **our code's expectation**, not evidence about **the actor's
payload**. Those are two artefacts, this slice has five recorded instances of them
disagreeing, and #323 is one where the adapter read the response at the wrong level and
reported `unknown 5` for a question the response answered plainly. **The key list is not
evidence and T5 does not treat it as any.**

**T5.1 — all THREE dumps, reported per file. A sample of one measures the wrong thing.**
`run2/actor.fetch.001..003.json` (section N). The property T5 measures is exactly the one
that varies between them: **`captions_kind`.** #288's measurement covered six transcripts
**including three from auto-generated tracks**, and the manual/generated distinction is
what #323 read at the wrong nesting level in the first place. **If a timestamped variant is
present in the manual response and absent — or differently shaped — in the generated one,
that is the finding**, and one file would have produced a confident answer either way.
**#82 is at six sightings for exactly this**: a claim true of part of the data, written as
though it were true of all of it.

**T5.3 — `.venv/bin/python`, never `python3`.** Every host command in this record uses the
venv interpreter; `python3` *may well* resolve on Ubuntu 24.04, and *may well* is not the
standard this record holds server commands to. The path is passed rather than
`cd`-ed into, so the working directory stays the checkout.

**Step 1 — are the dumps there, and how big?**

```bash
set +H; sudo -u bot ls -l /home/bot/phase-b-fixtures/run2/
```

**Step 2 — the body of each of the three, keys and shapes, reported per file.**

```bash
set +H; cd /home/bot/english-bot && sudo -u bot .venv/bin/python - <<'PY'
import json, pathlib, hashlib
for p in sorted(pathlib.Path("/home/bot/phase-b-fixtures/run2").glob("actor.fetch.*.json")):
    d = json.loads(p.read_bytes())
    rows = d if isinstance(d, list) else [d]
    print("=" * 60); print(p.name, p.stat().st_size, "bytes,", len(rows), "row(s)")
    for r in rows:
        if not isinstance(r, dict):
            print("  non-dict row:", type(r).__name__); continue
        print("  video:", r.get("video_id") or r.get("videoId") or r.get("url"))
        print("  kind fields:", {k: r.get(k) for k in
              ("transcript_type", "is_generated", "generated", "language_code")})
        for k in sorted(r):
            v = r[k]
            if isinstance(v, list):
                print(f"  {k}: list[{len(v)}] first={v[0] if v else None!r}")
            else:
                print(f"  {k}: {type(v).__name__} {str(v)[:100]!r}")
        for k in ("transcript", "text", "captions", "segments", "non_timestamped"):
            v = r.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                joined = "".join(str(s.get("text", "")) for s in v)
                print(f"  JOINED from {k}: len={len(joined)} md5={hashlib.md5(joined.encode()).hexdigest()}")
PY
```

**T5.2 — question 5 needs the OTHER artefact, which that command does not open.** The
stored string is in Postgres; the dump is a file. Run this beside step 2 and compare
**length AND hash** — *a length match is not an identity match*, and the failure it guards
against (coverage over one string, highlighting over another) is invisible on screen and
produces two instruments that agree until they don't:

```bash
set +H; sudo -u bot psql -d english_bot -tAc "SELECT youtube_id, length(transcript), md5(transcript) FROM videos WHERE youtube_id IN ('y_525lzqbg0','a6uHw72_BnU','2jLhZjfu5-o');"
```

The `JOINED … md5=` lines from step 2 are compared against these `md5` values directly.
**Whitespace is the likely divergence** — `_read_text`'s list branch joins with `" "` while
a timestamped variant's own text may not carry the separators — so a mismatch is expected
to be informative rather than alarming, and what it settles is **which single string both
instruments must read**.

**Four questions the body must answer, and each is a finding either way:**

1. **Is a timestamped variant present at all, and what is it called?** If the dumps hold
   only `non_timestamped`, **that is the finding** — the actor was asked for text and
   returned text — and T5 moves to its **billed branch**. It is not read as an absence to
   be worked around.
2. **Does every element carry a `start`, or only some?** A partial timing set is not a
   timing set for a follow-along highlight.
3. **Is there a `duration` or an `end`, and what is the unit** — seconds, milliseconds,
   float or int? A loop needs an end, and an offset in the wrong unit is a bug that looks
   like a working feature.
4. **Are the segments per CUE or per CAPTION GROUP?** *A caption group is not a line, and
   "loop a line" means a line.* If the grouping is coarse, loop-a-line is not delivered by
   storing these timings and that must be known **before** `021` is spent on them.

**And a fifth the same read settles for free:** is the concatenated text of the timestamped
variant **byte-identical** to what `record_transcript` stored? If it is not, then coverage
computed over one and highlighting computed over the other are **two instruments on one
screen** — the same class as a stored 94% and a real 94% being indistinguishable, which is
why `video_coverage` stores its whole basis. A mismatch means the badge and the highlight
must be computed from the **same** string, and the plan says which.

**T5.4 — THE NEGATIVE BRANCH, DECIDED HERE AND NOT IN THE MOMENT. Absent dumps do not mean
option B.** Step 1 returning nothing means **the timings were never recorded**, which is a
different state from **the actor does not return them** — and only the second justifies a
billed re-fetch of the pool. Writing them as the same state is how a missing measurement
becomes a purchase. The three states and what each licenses:

| Step 1 result | What is established | What it licenses |
|---|---|---|
| Dumps present, timestamped variant present | The actor returns timings; questions 2–5 answerable | **Option A** — backfill + `021`, no charge |
| Dumps present, **only** `non_timestamped` | The actor was asked for text and returned text. **The schema question is still unanswered** | the intermediate below, **not** a pool re-fetch |
| **Dumps absent** | Nothing about the actor. Only that we did not keep the evidence | the intermediate below, **not** option B |

**The cheap intermediate, named so it is not discovered when the branch is reached: change
the adapter's `text_keys` ordering and re-fetch ONE video.** That is **one billed event,
not a run** — `fetch_transcripts` is per video (#324) — and it answers the schema question
for the price of the smallest charge this project can make. It also produces the first
dump this repository would hold of a timestamped response, which is #317's own shape
arriving usefully. **Whether it is worth taking is the operator's**, and #320/#321 apply:
the projected cost is not trustworthy, so the number that matters is the console's after
the fact, read and recorded (P2).

*What T5 changes.* Timings present, per cue, with a unit, and text reconcilable →
**option A**: a backfill plus one migration, **no billed run**. Present but coarse,
partial, or over different text → the plan says so and the affected feature is reported
unmet rather than shipped on a timing set that does not support it. Absent → **option B**,
money, and #320/#321 mean the projection cannot be trusted until one real charge is read.
Neither taken → **option C**, and the timestamp criterion is reported unmet.
**Absent dumps land on the intermediate, never straight on option B** (T5.4).

**T1 — the check W12b's 🟡 waits on, and the cheapest item here. It comes BEFORE §1a is
answered, not after** — §1a is a ruling about how to spend money on content, and #329
measured five of six real videos below the comprehensible-input floor. If the three
assigned videos are not watchable at this level, the pool question precedes the player
question and **§1a would be a decision about spending money on content nobody can use.**
**T1 therefore orders the operator's own decisions, not just W13's schedule.** Watch
`y_525lzqbg0`, `a6uHw72_BnU`, `2jLhZjfu5-o` and confirm they are watchable at this level;
do the five #316 channels (Claire, Learn English With TV Series, `@easyenglish551`,
The Office, Modern Family) at the same time and #316 closes.
*What it changes.* If the three assigned videos are **not** watchable at this level
(#329 measured five of six real videos below the comprehensible-input floor), then W13
ships a player over content the learners cannot use, and the pool question comes before
the player question. **That would be a reason to hold W13, and it is a decision the plan
cannot make from the tree.**

**T2 — `@ModernFamily`'s 404 (#333).** Free, two calls, one quota unit each.

```bash
set +H; cd /home/bot/english-bot && sudo -u bot .venv/bin/python -m core.video.resolve_channels --handle @ModernFamily
```

**T4 — what wrote `im`, `sa`, `everytime` (#332).** Free.

```bash
set +H; sudo -u bot psql -d english_bot -c "SELECT ul.user_id, l.lemma, ul.state, ul.source, ul.source_rank, ul.first_seen_at FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id WHERE l.lemma IN ('im','sa','everytime','analyze','product','tone') ORDER BY l.lemma, ul.user_id;"
```

*What T4 changes.* If those lemmas entered through **ingestion** rather than the seed, the
unknown-word highlighter will mark real words as known for whichever learner holds them —
a second, independent inflation on top of #288's, on the exact surface §2c and #284 are
about.

---

## §6 — Deploy, when there is something to deploy

**Nothing in this plan pass is deployed. `schema_version` stays at 20.** The sequence
below is settled and is not re-argued; it belongs to the implementation commit.

push-and-verify (#223) → **`0a` SHA check** (the operator's own committed step; no row in
this record carries a SHA until it is pasted — #222/#223) → `scripts/backup.sh` with no
argument (#215) → `git pull --ff-only` → `pip install -e packages/core` → migrate →
`core.db status` **pasted verbatim** → restart **the API only** → prove live with a
**`401`**, never `active (running)` (#247), never chained.

**W13 is almost entirely `apps/web`, so Vercel must rebuild before anything can be checked
on a screen.** No amount of API restarting makes a player appear. Said here, and said
again in the update block.

---

## What this plan does NOT claim

- It does **not** claim §1a is settled. Three of W13's four named features are gated on an
  operator ruling that has not been made, and the plan states options and a flagged
  recommendation rather than choosing.
- It does **not** claim the video pool is watchable. T1 is unrun and #329 measured five of
  six real videos below the floor.
- It does **not** claim to have solved prompt injection. §2d specifies a mechanism that
  refuses a bad reply; #271 is the standing finding that no test can show the model
  understood the rule.
- It does **not** claim the coverage instrument is correct. §2c declines to show a number
  **because** #288 is open and unmeasured; the underlying figure is still inflated by an
  amount nobody has counted, and #284 stays open on the visible half.
- It does **not** claim W13's row can be built. §3 says it cannot, proposes the split, and
  reports **two** acceptance criteria unmet rather than adjusting either: the fourth (slang,
  by R9's schema constraint under a no-generation §1a) and the *"and timestamp"* half of the
  first (by R12 — no per-cue timings exist).
- It does **not** claim W13-i needs no migration. **§2g(a)** rules that for the fields W13
  **writes**; **§2g(b)** — what it must **read** — is open and is T5's. Under option A or B
  it takes `021` and #185's eighth occurrence.
- It does **not** claim the actor returns a timestamped variant. That inference came from
  our adapter's key list, which is our expectation and not the actor's payload (C2). **T5
  reads the body**, and "only `non_timestamped` is there" is a finding, not an absence.
- It does **not** claim the dumps are reachable. C3 corrects three transfer commands that
  cannot succeed; **whether the files are still on the host is unverified** and T5 begins
  by establishing it.
- It does **not** claim `9b0a272` is production's HEAD. That is the local tree read from
  `git`, as asked; the handover's claim about production is unverified and `0a` is still
  owed before any row carries a SHA (#222/#223).
- It does **not** assert any host state, any SHA, or any suite run. The last recorded
  figures are W12r's — pytest 2440 passed / 6 skipped / 0 failing; Vitest 141 passed
  across 11 files — and this pass ran neither.
- It does **not** retarget any issue, take or shift any migration number, mark any slice
  ✅, or move W13 to 🟡.

---

## The `BUILD_PROGRESS.md` update block this plan commits

**Slice row.** W13 stays **⬜ NOT STARTED**, mode **PLAN**, with W10b's reason stated in the
note: 🟡 means code-complete and there is no code. No slice is marked ✅.

**Decisions log** — every ruling with its reason, its declined alternatives, and its
**authorship** (assistant-recommended vs operator-accepted are different things and a
reader in six months needs to tell them apart):

1. **§1b — `video_coverage` is recomputed at read time, not read back.** *Assistant-ruled.*
   Declined: read the stored value (would require an invalidation rule over three untracked
   inputs; #281's family).
2. **§1c — an absent transcript is a first-class player state (i); assign-side refusal at
   N=7 proposed as the close (ii).** *(i) assistant-ruled; (ii) assistant-recommended,
   operator to accept.* Declined: re-fetch on read (#196, the 2026-08-27 ruling); forbidden:
   touching the thirty days.
3. **§2c — no percentage reaches a learner; the badge is qualitative.** *Assistant-ruled*
   on #288, #334, #330. PRD §7.3's `"94% known"` amended in place with the old text quoted.
4. **§2b — the watch signal is AUTOMATIC ONLY; no learner-tapped completion control is
   built.** *Assistant-ruled, revised on send-back S3.* #258's ruling of 2026-08-29 is
   named: the manual button, its route and its service function were deleted, and the
   per-kind rule turns on whether a block has a per-attempt log keyed on `session_id`.
   **`input`'s *"serves nothing, never `done`"* clause expires when W13 makes it serve
   something, and the ruling is honoured by building the missing log — the progress ping —
   not by adding a tap.** The `duration_s IS NULL` gap is documented and T3 measures it;
   refused in its place: writing `done` on the ping's existence, and back-filling
   `duration_s` from the browser. `completed_at` keeps one producer (#190).
5. **§2d — the model ban is amended from empty to a one-member allow-list, and the scan
   root widened to `video_api.py`.** *Assistant-ruled.*
6. **§2g — W13 takes no migration number for the fields it WRITES; R12 may force one for a
   field it must READ.** *Assistant-ruled on the write side; the read side is the
   operator's, gated on T5.* Options A/B take `021` and #185's eighth occurrence
   (W13a→022, W14→023, W18→024, both halves, same commit); option C ships without timings
   and reports the criterion unmet. The `video_glosses` question under §1a option 1 remains
   a separate stop point.
7. **§2c's `proper_nouns_detected` suppression is a GUARD AGAINST A PROVIDER CHANGE, not a
   live mitigation, and it does not address #288.** *Assistant-ruled, revised on send-back
   S1.* #288's measurement — six transcripts, three auto-generated, `proper_nouns_detected`
   true on all six, `degraded_288 = 0` — withdraws the borrowed premise. The ruling that no
   percentage reaches a learner is unchanged and rests on its other three reasons.
8. **S4 — the split halves are named `W13-i` and `W13-ii`; `W13e` is withdrawn.**
   *Assistant-ruled.* The b/c/d series on W13 denotes **scheduling position, not a split**
   (recorded when W13b was added), so a letter suffix would carry two meanings inside one
   id. The convention is recorded here rather than left to be inferred.
9. **S5 — #170 is retargeted to W13-ii → the operator, closing at a deck of ≥ 100 cards.**
   *Assistant-recommended (the number), operator to accept.* "Re-check" was a deferral
   without a reader; PRODUCT-PRINCIPLES §5 requires a target.
10. **§3 — the row is split into W13-i (player) and W13-ii (capture), the original row kept;
   comprehension items → W13a, shadow → W14/W15, series-export slang → the import slice.
   The fourth acceptance criterion is reported unmet.** *Assistant-recommended, operator to
   accept.*

**Questions left to the operator, listed as unanswered rather than assumed:**
§1a's four options; §1c(ii)'s placement; #175's licence ruling; whether the split in §3 is
accepted.

**Known issues to file** (severity and target, so nothing untracked becomes forgotten):

- **new, `low`** — the by-target W13 issue count was derived at 22/20 in the same commit
  that filed #335 and #336 against W13; the live figures are **24 rows / 22 open**, total
  **30** with prose (R1). Target: whoever next derives a count.
- **new, `low`** — `upsert_video`'s `accent: str` annotation contradicts migration 020 (R3).
- **new, `low`** — `score.py`'s band comment says #289 is unvalidated; #289 is closed (R4).
- **new, `low`** — ARCHITECTURE §6 and PRD §7.3 still say "segment" after the 2026-08-30
  ruling struck it from §7.2 and §5 (R5, R6).
- **new, `medium`** — `test_core_video_never_calls_the_model`'s scan root excludes
  `core/video_api.py`, the module that fetches the scraped text (R7). Target: **W13-ii**.
- **#215 — SEVENTH SIGHTING, filed on the existing row and NOT as a new number (C3).**
  Three live `scp bot@<host>:…` instructions (`BUILD_PROGRESS.md:4380`, `:4790`, `:5061`)
  against an Environment table (`:175`) that records `bot` as having no inbound SSH key and
  no password. All three corrected in place with the old text quoted, in this commit.
  Severity unchanged at `medium`. **#317's outstanding half — the full 14,374-byte
  `actor.list.001.json` — travels in the same transfer**, and no test asserts byte-identity
  until the original is committed beside the re-serialised slice.
- **new, `high`** — **no per-cue timings are stored anywhere** (R12): `videos.transcript`
  is one `TEXT` column, `_read_text` prefers `non_timestamped` and its list branch discards
  every `start`. Loop-a-line, the synced transcript, per-line 0.75× and the *"and
  timestamp"* half of acceptance criterion 1 have no data behind them. `high` because it
  removes named features from a shipped row's criteria and cannot be fixed without either
  DDL or a billed run. Target: **W13-i**, gated on **T5**.
- **carried, all still open** — #335, #336, #337, #338, #339, and the full carried set.

**File inventory.** `prompts/CC-W13-player-PLAN.md` — this plan, archived. **And nothing
else** in `prompts/`. (`prompts/` is CLAUDE.md's one exception: it records intent, never
state, and is never consulted for build status.) The same commit edits `BUILD_PROGRESS.md`
for the update block **and for C3's three in-place corrections at `:4380`, `:4790` and
`:5061`**, with the old text quoted at each. **No code, no test, no migration, no `.sql`
file, no `data/` change, no `apps/web` change, no server step, no billed call.
`schema_version` untouched at 20.**

**Next action — this slice's checks plus every earlier check still unrun, none dropped.**
**Commit W12r first (R0)** — `docs/TASKS-v3-web.md` is dirty and would otherwise be swept
into W13's commit (R0). **2.** Fix section N's transfer command and its two siblings (C3),
then run **T5** — it decides §2g(b). **3. T3** — it changes §2b's gap size and §2c's
threshold. **4. T1** — before §1a is answered, not after; #329 measured five of six real
videos below the comprehensible-input floor. **5. §1a**, with **R8** and **R9** in front of
it: option 3 is unavailable as worded, and under any no-generation answer the fourth
criterion is unreachable by **constraint**, not by choice. **6. T2**, **T4**, and the
**`0a`** SHA read before any row carries a SHA (`9b0a272` is the **local** HEAD and says
nothing about production; the handover's production claim is still unverified).
Then: the carried set **#335–#339**; unit 2
held on **#299/#249** with the unit-1 retake outcome unreported; **W11c awaiting the
operator's ✅**; **W12b's own human check**; **W10d planned and not implemented**.
**And: W13 is almost entirely `apps/web`, so Vercel must rebuild before anything can be
checked on a screen.**
