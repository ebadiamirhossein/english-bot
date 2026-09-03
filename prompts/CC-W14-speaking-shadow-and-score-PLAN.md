# W14 — Speaking I: shadow + score. PLAN ONLY.

**Mode:** PLAN. This pass produces this document and nothing else. No code, no
test, no migration, no `.sql` file, no `data/` change, no `apps/web` change, no
server step, no Azure call. `schema_version` stays at **23**. No slice is
marked ✅. **No migration number is taken.**

---

## Context — why this slice exists

PRD §8 opens *"Speaking and pronunciation — the actual bottleneck"* and has
specified four speaking surfaces since v3 was written. **None of them is
reachable from a session.** #303 (`medium`, open) states the gap and verified
its own premise in the direction that widens it: `docs/ACCOUNTS-AND-PURCHASES.md`
rules on and prices Azure Speech pronunciation assessment — *"the highest-value
purchase on this list"*, **blocking for W14** — **but in code neither Azure nor
ElevenLabs exists.** As of 2026-09-03 the Azure Speech resource exists on the **Free (F0)** tier
and its key and region sit in the host's `.env`, verified present by a count and
never printed. **No key, endpoint or region literal appears in this document or
anywhere else in the repository** — the operator holds those values. So the purchase side of #303 is
now true and the code side is still false, and W14 is the slice that closes the
Azure half.

W14 is the **first rung** of PRD §8's ladder. It is not the ladder.

---

# §0 — The reconcile

## 0.1 W14's row and its migration number — **the prompt's premise is stale**

The prompt states the Build cell reads *"Migration 022 (`speech_attempts`)"*
with a note dating it to #185's **seventh** occurrence. **It does not. Both
halves read 024, and the note says ninth.** Read as they stand now:

**`docs/TASKS-v3-web.md:85`, the W14 row, verbatim:**

> **W14** | Speaking I — shadow + score | **PLAN** | Migration 024
> (`speech_attempts`) *(was 023; shifted 2026-09-02 when W13 took 023 for
> `video_glosses` — #185's ninth occurrence on the shifted-a-row counting. Was
> 022 before that, shifted 2026-09-01 when W13-i took 021 — the eighth. Was 021
> before that — the seventh)*. Azure pronunciation assessment integration.
> Record → score → per-word colouring → per-phoneme persistence. Audio discarded
> in-request. | A deliberately mispronounced word scores visibly lower; no audio
> file exists on disk after the request; phoneme scores accumulate per user.

**`docs/TASKS-v3-web.md:132`, the authoritative table, verbatim:**

> | 024 | W14 | `speech_attempts` *(was 023; shifted 2026-09-02 when W13 took 023
> for `video_glosses`)* |

**The two halves agree, and the prompt's 022/seventh is the state as of
2026-09-01, two takes ago.** The prompt's *mechanism* is exactly right and is
what makes the drift traceable rather than mysterious: 021 → W13-i (cues),
022 → W13a (subtitle ladder, shifted nothing), 023 → W13-ii (`video_glosses`,
shifted two rows). **022 is `subtitle_ladder` and 023 is `video_glosses`, both
applied on production** — the prompt has that right, and it is what makes 022
unavailable. Highest file on disk: `migrations/023_video_glosses.sql`. Host
`schema_version` **23**.

**024 is not taken by this pass.** It is taken in the commit that writes the
`.sql` file, and both halves shift in that same commit if anything below has
moved by then (#185).

## 0.2 PRD §7.3, §2.5, and what the record says about Azure

- **PRD §7.3** (the player): *"loop-a-line, slow to 0.75×, **shadow this line**
  (record → Azure pronunciation score → per-word colouring)"*. Shadow is listed
  **in the player**, beside two features W13-i reported **unmet**.
- **PRD §8** rung 1: *"**Shadow** — repeat a line from today's video. Scored per
  phoneme by Azure. Colour-coded playback of your own attempt."*
- **PRD §8**, the pronunciation paragraph: *"Azure Speech pronunciation
  assessment returns accuracy / fluency / completeness / prosody plus
  per-phoneme scores. Persist per-phoneme accuracy per user → surfaces 'your /θ/
  and /w/ are the two costing you most' and generates targeted minimal-pair
  drills."* **That consumer is W17.** W14 writes; W17 reads.
- **PRD §8**, privacy: *"audio is transcribed/scored and discarded. Never
  written to disk, never stored. Only scores and corrections survive."*
- **PRD §2.5**: per-L1 pronunciation seeds are *"a starting hypothesis, never a
  fixed diagnosis — the measured data overrides it."* `users.l1_pronunciation_seed`
  was added at 009 **nullable and inert until W14/W17** (decisions log,
  2026-08-23). **W14 does not activate it** — see §4.
- `docs/ACCOUNTS-AND-PURCHASES.md`: F0 = **5 audio hours/month free**;
  pronunciation assessment **included** in standard, not a separate charge;
  prosody an optional €0.264/hr add-on; *"Two people speaking ~5 minutes a day =
  about 5 hours a month total… Realistic cost: €0–6/month."* **Blocking for W14.**

## 0.3 `packages/core/speech.py` — what exists, what it is wired to, whether it has ever called

- **Exists:** `transcribe(audio, language, settings)` and `synthesize(text,
  voice, settings)`; `SpeechError`; a 3× backoff retry; **OpenAI only**
  (`whisper-1`, `tts-1`). Module docstring: *"Audio never touches the
  filesystem."* Provider SDKs are imported here and nowhere else, held by
  `tests/test_core_boundary.py:191`.
- **Wired to, live:** three Telegram handlers serving two learners daily
  (`shadow.py`, `voice.py`, `diary.py`), `core.items.gates.audio_round_trip`,
  and `core.services.items.item_audio` behind `GET /items/{id}/audio` (W6 ⟨R1⟩).
- **Has it ever made a call?** **Yes — to OpenAI, in production, daily.**
  **To Azure, never, and there is no code that could.** `Settings` has no
  `azure_speech_key` and no `azure_speech_region`; `_KNOWN_STT_PROVIDERS` is
  `frozenset({"openai"})`, so `STT_PROVIDER=azure` is **refused at load**.
  That is #303's finding, unchanged.

## 0.4 The hard safety rule — where it is enforced today

**It is enforced by convention, docstring and absence — not by an instrument.**
Searched: nothing under `packages/core` or `apps/api` on any audio path opens a
file, uses `tempfile`, or writes bytes to disk. `speech.py` holds audio as
`bytes` and `io.BytesIO`. `item_audio` returns `bytes` to the route, which
returns a `Response`. `apps/bot/handlers/diary.py:4` records *"Full transcript
discarded"* as a comment.

**No test asserts that no file appears.** The nearest instruments are
`test_core_boundary.py` (import bans, AST) and `test_api.py`'s plain-`def`
detector (AST with a proven-non-inert negative control). Logging discipline
holds: `speech.py` logs `model`, `bytes`, `duration_ms` — never content — and
`config.py` carries `repr=False` on every credential for exactly the reason
CLAUDE.md §5 gives.

**W14 is the slice that turns the rule into an instrument.** See §1c and §2.7.

## 0.5 `videos.transcript_cues` — a shadowed line needs a line

Inherited, not rediscovered. `packages/core/video/cues.py`'s own header, from
T5's measurement on 2026-09-01:

> **GENERATED TRACKS ARE ROLLING WINDOWS, NOT LINES.** Overlapping consecutive
> pairs: **1405/1527**, 655/714, 958/1038, 897/1034, 1471/1705, 272/317 —
> roughly **92% on every generated track measured**. Manual tracks are
> contiguous by contrast (TED-Ed: `7.003 + 4.713 = 11.716` exactly), **but all
> three assigned videos are `generated`.**
>
> **THE 92% IS WHY LOOP-A-LINE AND PER-LINE 0.75x ARE NOT HERE.** A cue interval
> is a display window, not a sentence, so "loop this line" would loop an
> arbitrary ~2.4 s slice beginning mid-clause.

W13-i reported loop-a-line and per-line 0.75× **UNMET** — *"Not adjusted, not
widened, not flag-gated"* — and **#341 is updated, not closed.** Two workarounds
are **refused on the record and the refusals stand**: merging cues into
synthetic sentences (a generated artefact presented as the transcript's own
structure), and shipping for manual tracks only (a feature that appears and
disappears on a property no learner can see).

**A second inheritance, and it is the one that decides §1b.** W13-ii's
`explain._line_for` sets a gloss's `context_sentence` to **the cue containing the
word**, and `cards.save_captured_word` copies that straight onto the card
(`packages/core/services/cards.py:1455`). So **a card saved from a video carries
a rolling-window fragment in `context_sentence`, not a sentence** — and it is
identifiable exactly, because the same writer sets
`source_ref = 'video:<id>@<seconds>'` (`_capture_source_ref`, `:1363`).

## 0.6 Every open issue targeting W14

| # | What it says about W14 | Sev | State |
|---|---|---|---|
| **#303** | The Azure half is **shared with W14**; W13b owns the row. *"the two vendors that would score speech are priced decisions, not reachable code."* | medium | ⬜ open — **W14 does not close it** |
| **#341** | Per-cue timings: four named W13 features had no data. **Updated, not closed**, at W13-i. W14 inherits the cue-boundary fact. | — | ⬜ open |
| **#53** | *"`speech_attempts` (W14) and the `sessions` extension (W10) appear in ARCHITECTURE §5 with no migration number in TASKS."* | low | ✅ closed (TASKS half) — 024 assigned |
| **#185** | 024 shifts if any slice below takes a number first. Ninth / tenth occurrence depending on counting; **open on which it means**. | — | ⬜ open |
| **#346** | `test_record_consistency`'s `_SLICE_ID` does not match a hyphen. **`W14` has no hyphen, so it does not fire here** — recorded so it is not re-derived. | — | ⬜ open |
| **#345** | An assertion whose accepted-value set contains its own failure mode. **Five instances, three written after the row was filed.** Binds every test in §2.7. | — | ⬜ open |
| **#7** | Plain `def` on any route reaching `llm`/`speech`. Binds §2.2. | high | ✅ closed (v2) — the convention it generalised is live |

Also binding, not W14-targeted: `ARCHITECTURE-v3-web.md:133` —
`speech_attempts` | *"scores only — never audio, never transcripts of the diary"*.

---

# §1 — The four rulings

## §1a — Does scoring count as generating while a learner waits?

**RULING (recommended): the standing ruling does not reach pronunciation
scoring. W14 scores in-request, with the learner present.**

**The standing ruling, verbatim (2026-08-27, operator ruling 1, and
`ARCHITECTURE-v3-web.md:294`):** *"The operator runs a command; the app never
generates while a learner waits, and never while nobody is watching."* Its
stated reason: **#196 refused a scheduled billed pipeline on the grounds that no
gate certifies an item.** W13-ii's §1a resolved tap-to-define **pre-generate** on
that basis, and made it hold *by construction* — `POST /video/{id}/save-word`
reaches no model and the netguard proves it inside the request.

**Pronunciation scoring cannot be pre-generated.** It scores audio that does not
exist until the learner speaks. So the ruling either does not reach it, or W14
cannot be built. **The argument for the first, in four parts:**

1. **No model produces content.** Azure's pronunciation assessment returns
   numbers about an acoustic signal. Nothing is authored, nothing is phrased,
   nothing is written for a learner to read as English.
2. **Nothing enters a deck or the journal.** The ruling's reason is that *no gate
   certifies an item* — and there is no item. A score is not material; it needs
   no quality gate, no naturalness gate, and no blind solver, because there is
   nothing to solve. CLAUDE.md §5's rule that only genuine self-produced errors
   reach `errors` is satisfied by W14 writing **no `errors` row at all** (v2's
   shadow already held that line: *"Never writes `errors`."*).
3. **The second half of the ruling is satisfied maximally, not narrowly.**
   *"Never while nobody is watching"* — scoring runs **only** while a learner is
   present, because it scores their live utterance. W14 is the exact inverse of
   the unattended pipeline the ruling was written against.
4. **The cost argument that carried W13-ii's §1a inverts here.** That ruling
   declined on-demand generation partly because it *"opens a per-tap money path
   with no ceiling"*. **This call is free** (§1d).

**What this ruling is NOT.** It is not a general licence for in-request work. The
boundary proposed, in words, so a later slice does not widen it by analogy:

> The ruling governs **generation** — a model producing content a learner will
> read or study. It does not govern **measurement** of something the learner has
> just produced, where no content is created, nothing enters a deck, the journal
> or the item bank, and a learner is present by construction.

**AUTHORSHIP, stated because the record requires it: the recommendation is the
assistant's. The acceptance is the operator's, and it is owed before
implementation.** W13-ii/1's precedent exactly. Until accepted, W14 does not
start. **Declined alternative:** pre-record a fixed set of learner utterances and
score them ahead of time — refused, because it is not a thing that can exist.
**Second declined alternative:** score asynchronously and show the result on the
next session — refused, because a pronunciation score delivered a day later
cannot be acted on, and *"never present a backlog"* (CLAUDE.md §4) makes a queue
of unscored attempts a defect by itself.

### The wait, and what the screen shows

**Estimate, to be replaced by measurement at the owed real call (§2.3):
~1–2 seconds** from *stop* to *scored*, for a 3–5 second clip — phone upload of
~100–160 KB, Hetzner → the Azure region round trip, and Azure's
own short-audio assessment. It is an estimate from the shape of the request, not
a number this project has measured, and **the plan says so rather than asserting
it.**

**What the screen shows meanwhile.** The line stays exactly where it was — it
does not move, blank, or get replaced by a spinner over the whole card. The
record control becomes a neutral in-progress state beneath it. **No progress
percentage, no "analysing", no counter.** Candidate copy: **"Listening back…"**
(passes `BANNED`; see §2.6). If the wait exceeds ~4 s, the same state persists
with no additional message — a message that appears because something is slow
reads as something being wrong.

## §1b — What the learner shadows, and whether the line exists

**RULING (recommended): the shadow target is a sentence from the learner's own
deck — `cards.context_sentence` — and never a transcript cue.**

**Why not a cue.** §0.5's measurement: a generated track is a rolling window,
~92% of consecutive pairs overlap, all three assigned videos are `generated`.
A cue is an arbitrary ~2.4 s slice beginning mid-clause. W13-i already reported
loop-a-line unmet on exactly this, and W14 has **a second reason W13-i did not
have**: Azure scores against a **reference text**, and `CompletenessScore` is
defined as *how much of the reference was said*. A mid-clause fragment makes
completeness meaningless by construction and makes the boundary words noisy.
**Shadowing a cue would ship an unmet feature with a score attached to it** — a
worse outcome than the honest unmet report W13-i gave. **The two standing
refusals stand and are not revisited:** no merging cues into synthetic sentences,
no manual-tracks-only behaviour.

**Why the deck sentence works.** `cards.context_sentence` is a real sentence for
every card whose provenance is not the video path: `migrate_chunks` writes
`chunks.full_sentence`, `capture` writes `record.sentence`. It is **the same
source v2's `select_shadow_sentence` used**, so this is a ported source rather
than a new one. It is a sentence the learner **chose**, which is the thing a
shadow rung wants.

**The exclusion, stated as a predicate rather than a hope.** Cards saved from a
video carry a **cue** in `context_sentence` (§0.5). They are identified exactly
by `source_ref LIKE 'video:%'`. **The selector excludes them, and a test asserts
it** (§2.7 test 7). It is the §1b ruling made structural rather than
documented — the shape `cards.promote_to_production` used when it turned a
cross-table rule into a row-local CHECK so it would survive later writers.

*(Today the exclusion selects nothing: `--apply` on the gloss pre-generation has
never run, so zero video-sourced cards exist. The predicate is written now
because the first one will appear the day T1 clears, and a selector written
against an empty table is a selector nobody checked.)*

**W14 INHERITS AN UNMET FEATURE AND SAYS SO.** PRD §7.3 places *"shadow this
line"* **inside the player**, and PRD §8 rung 1 says *"repeat a line from today's
video."* **This plan does not deliver that**, and does not approximate it.
The in-player shadow needs line boundaries the data does not have; **#341 stays
open and W14 does not repair it.** What W14 delivers is the *scoring engine and
the surface it needs* — attached to the one source in this system that is
already sentences. If the operator wants the player placement instead, the
answer is that it is blocked on #341 and no amount of W14 changes that.

**Declined third option:** generate a sentence to shadow. Refused — that is
generation while a learner waits, it re-opens §1a on the wrong side, and it
would put an ungated sentence in front of a learner.

## §1c — The audio path, and the rule it must satisfy

**The acceptance: no audio file exists on disk after the request.** An error path
that writes a temp file breaks it as surely as a success path does.

### Capture — and the two phones are different

Recorded 2026-08-23: **the learners are on an iPhone 17 and a Samsung Galaxy
A34 5G**, and four platform assumptions were corrected *before* the frontend was
written. The same lesson applies here and is larger:

- iPhone 17 / Safari `MediaRecorder` → **`audio/mp4` (AAC)**.
- Galaxy A34 / Chrome `MediaRecorder` → **`audio/webm; codecs=opus`**.

**Azure's short-audio REST endpoint does not natively accept either.** Its native
set is WAV/PCM and OGG/Opus; other containers need GStreamer alongside the
Speech SDK.

**RULING: the browser normalises to 16 kHz mono 16-bit PCM WAV before upload.**
`getUserMedia` → `MediaRecorder` → `AudioContext.decodeAudioData` (which handles
both containers) → downmix, resample, PCM-encode **in memory** → `Blob`. One
format leaves both phones, and the container question disappears.

**Declined (1): the Azure Speech SDK plus GStreamer on the host.** Refused
outright. CLAUDE.md §5: the production host is shared with `fonderis-worker` and
PostgreSQL serves both projects; installing a media framework system-wide is
exactly the class of change no slice may make. **Declined (2): server-side
`ffmpeg` transcode.** Same refusal, same reason. **Declined (3): send each
phone's native container and branch server-side.** Refused — it makes the
feature's correctness depend on a device property no learner can see, which is
the shape W13-i refused for manual-tracks-only.

### S2 — the resample is an UNTESTED ASSUMPTION, and it may fail on one of the two phones

**The risk, named before it is designed around.** Resampling to 16 kHz needs
`OfflineAudioContext` at a non-hardware rate, and **WebKit has historically
refused to construct an `OfflineAudioContext` at arbitrary sample rates**,
accepting only the device's own. If that still holds on the iPhone 17, **the
whole capture path fails on one of two devices at the one step §1c treats as
settled** — and the 2026-08-23 entry corrected four platform assumptions
*before* the frontend was written. **This is the fifth, and it is checkable for
free, today, on the actual phones.**

**Two free probes, in this order, both before any capture code is written:**

**P0a — the Azure probe, folded into §2.3's owed real call, and it may DELETE
the problem.** The same free session that records the response shape also sends
**one 48 kHz mono 16-bit PCM WAV**. **If Azure accepts the device's native rate,
no resampling is needed at all** — decode → PCM → WAV header at the native rate,
container normalisation only, and S2's risk disappears. This is the preferred
outcome, it costs one extra request in a session that is already free, and
**running it first means P0b may not be needed.**

**P0b — the device probe, free, on BOTH phones.** A throwaway page (not shipped,
not committed to `apps/web`) that reports, per device:

1. Does `new OfflineAudioContext(1, 16000, 16000)` construct without throwing?
2. Does `decodeAudioData` accept that device's own `MediaRecorder` output?
3. What `mimeType` did `MediaRecorder` actually choose? (`isTypeSupported` probe
   plus the recorder's own `mimeType` — **reported, not assumed from the browser
   name**; §1c's mp4/AAC and webm/Opus are the expectation, not a measurement.)

**The fallback, stated NOW rather than after the failure.** If a resample is
required and `OfflineAudioContext` refuses it: **linear interpolation over the
decoded `Float32Array`, hand-written** — no API, no library, a few lines. Its
one real cost is named too: downsampling 44.1/48 kHz to 16 kHz without a
low-pass stage **aliases**, and aliasing on a pronunciation scorer is not a
cosmetic loss, so the fallback carries a cheap box-average pre-filter. **P0a
passing makes the whole fallback moot, which is why it runs first.**

**A ruling that cannot run on one of two phones is not a ruling, and this
project has the phones.** If both probes fail, §1c's normalisation ruling is
withdrawn and the slice stops and reports, rather than branching per device
(which §1c already refused for a different reason).

**Consequence, stated as a positive:** **no new Python dependency.** `httpx>=0.27`
is already a runtime dependency of `packages/core` (promoted by W12b), so the
Azure REST call adds nothing to install and **no licence gate is owed** — unlike
W4's `fsrs` and W7's. `azure-cognitiveservices-speech` is **not** added.

### Transport

- `POST /shadow/{card_id}/score`, `multipart/form-data`, the WAV bytes.
- **Body cap enforced before anything else reads it.** 16 kHz mono 16-bit ⇒
  32 KB/second, so a 15-second ceiling is **~480 KB**; cap at **1 MB** and refuse
  larger with a plain message and no row written. A cap is the only defence a
  free-tier quota has against a stuck recorder.
- Rate limited on both limits (`rate_limit`, `apps/api/deps.py:162`) — this is
  the **fourth** route in the app that consumes a paid or metered external
  resource, and the third that a public client can reach.

### In-memory handling, and both paths

- The route holds `bytes`, passes them to one service function, and never names
  a path. The service passes `bytes` to `speech.assess_pronunciation`.
- **`speech.py` posts the bytes as a request body.** No `open`, no `tempfile`,
  no `pathlib.Path.write_*`, no `shutil`, anywhere on the path.
- **The failure path is specified, not left to fall out.** On timeout, on a
  non-2xx, on a malformed body, on quota exhaustion: the bytes are dropped, **no
  row is written**, and the learner sees a plain message (§2.6). Nothing is
  retried into a file, nothing is buffered for later, and **there is no
  retry-on-failure queue** — a queue of unscored attempts is a backlog.
- **Azure's response contains a recognised transcript of what the learner
  said.** It is **discarded in-request, never persisted, never logged.** There is
  deliberately **no transcript column** in `speech_attempts` (§2.1), because a
  column that existed would eventually be filled. This is CLAUDE.md §5's rule
  about speech-recognition mishearings, applied with force: the recognition is
  the machine's guess at the learner's voice and it has no business surviving
  the request.

### What is logged

`user_id` · `card_id` · route name · `audio_bytes` (length) · `duration_ms` ·
the four aggregate scores. **Never the audio. Never the recognised transcript.
Never the reference sentence** — the reference is the learner's own card content,
and CLAUDE.md §5 says logs carry user ids and route names, never message bodies.
`AZURE_SPEECH_KEY` enters `Settings` with **`repr=False`**, the discipline
`youtube_api_key` and `apify_token` already carry, for the stated reason: one
`logger.info("%s", settings)` would put a live credential in a log file for good.

### The third-party position — FLAGGED, NOT SETTLED

**The learner's voice goes to Microsoft.** PRODUCT-PRINCIPLES §3 requires the
licence and data question to be asked before third-party processing enters the
product, **and the answer must hold for a commercial product, not only a private
one.** For voice this is a **data-processing** question, not a cost one.

**Owed, and not answered by this plan:**

1. Does Azure Speech retain submitted audio by default, for how long, and for
   what purpose — and is there a setting that turns it off? *(Do not assert the
   answer from memory; read the current terms.)*
2. Where is audio processed and stored for a resource in this region, and does
   that hold on the **Free (F0)** tier specifically — free tiers sometimes carry
   different data terms from paid ones.
3. What the DPA says about voice data, and whether voice is treated as
   biometric or special-category data under GDPR in this use.
4. **Do the two learners need to be told, and to agree?** Two adults in Vilnius,
   one of them the operator. The other is a person whose voice would leave the
   country in a request they did not make.

**One consequence is immediate and is a plan instruction, not a flag:** the owed
real call in §2.3 uses **a synthetic or the operator's own voice, never the other
learner's**, and it happens **before** the surface reaches a phone. The order
matters — a data question answered after the data has been sent is not an answer.

## §1d — F0's limits are a design input

**F0: 5 audio hours per month, and concurrency is limited on the free tier.**

### The arithmetic

| | |
|---|---|
| Seconds per attempt | **5 s** (a card sentence is ~3 s said; 5 s allows a pause) |
| Attempts per session | **10** (5 lines × up to 2 attempts, v2's one-retry shape) |
| Per session | **50 s** |
| Sessions per week per learner | **5** |
| Learners | **2** |
| Per week | 50 × 5 × 2 = **500 s ≈ 8.3 min** |
| Per month (×4.33) | **≈ 36 min** |
| **Against F0's 300 min** | **≈ 12%** |

**Even at 3× this estimate — 30 attempts a session — W14 uses ~36% of F0.**
Comfortable, and the headroom is the point: it means the ceiling in §1d below is
a guard against a stuck recorder, not a rationing scheme.

**The ACCOUNTS doc's "about 5 hours a month" is the WHOLE ladder, not W14.**
It priced *"two people speaking ~5 minutes a day"* across shadow, retell, answer
and converse. **Only shadow needs Azure**; retell, answer and converse are STT
and LLM work, which go to Scribe/Whisper and Anthropic. So W14 alone fits F0
several times over, and **the thing that will eventually push against 5 hours is
W17's minimal-pair drills plus W15's rungs, not this slice.** Recorded so a later
slice does not re-derive it and does not attribute the pressure to shadow.

### Concurrency

Two learners, and sessions are not synchronised. A collision is possible and
rare. **On a concurrency refusal (429), the surface behaves exactly as it does on
any other failure**: plain message, no row, no retry queue. It is not worth a
lock, a queue, or a backoff on a two-user system, and a backoff would extend the
wait §1a bounds.

### Exhaustion — the surface says so, it does not silently stop

**A speaking surface that silently stops working is worse than one that says it
is unavailable today.** Two mechanisms, and both are needed:

1. **Our own ledger.** `speech_attempts.audio_seconds`, summed per calendar
   month across all users, is the app's estimate of Azure's counter.
   **Computed from our own WAV byte count** (`bytes / (16000 × 2)`) and **not
   from anything Azure returns** — CLAUDE.md §3 rule 5: an expected value must
   not be derived from the thing under test, and a quota guard that trusts the
   provider's own accounting cannot detect the provider disagreeing.
   Below a **soft ceiling of 240 minutes (80% of 300)** the surface is offered;
   above it, **the shadow control is not rendered** and the screen says plainly
   that scoring is unavailable this month.
2. **The provider's own refusal.** If Azure returns quota-exceeded regardless,
   the failure path in §1c handles it, with the same copy.

**The two can disagree and the plan says so** — our count is of what we sent,
Azure's is of what it billed, and rounding, retries and rejected requests can
separate them. The ledger is a guard, not a mirror. **The soft ceiling exists
precisely because it will be wrong in one direction or the other.**

### #320/#321 do not carry over, and that is said plainly

#321 measured the Anthropic cost floor **under-reporting a real charge by
~4,900×**, and #320's family is why every billed path in this project is
human-run and dry by default. **None of that applies here.** Azure pronunciation
assessment on F0 is **free**: there is no per-call charge, so there is no cost
model to be wrong. **The risk is not money; it is a quota**, and a quota is
countable in seconds we ourselves produced. **Importing the billed-path caution —
making shadow a human-run dry-by-default command — would be caution transplanted
from a problem this slice does not have**, and it would make the surface
unusable, since a learner cannot shadow a line by running a CLI. Recorded
explicitly so it is not re-argued at implementation.

## §1e — Where the surface lives (S1)

**RULING (recommended): shadow ships INSIDE block 4 (`output`) of the daily
session. No standalone route, no tab, no counter.**

**Three grounds, none of them a preference:**

1. **PRD §4.1 block 4 is literally *"Speak or write. Corrected. Errors →
   journal."*** The speak half has never existed. #303 states the gap in exactly
   those terms: *"Block 4 says **SAY SOMETHING OF YOUR OWN** and the button says
   **WRITE IT**."*
2. **#160 applies with force, and a standalone shadow screen is its worst case.**
   #160 retired `/review` as a daily duty because *"a tab whose counter
   accumulates while the learner is away is a backlog presented"*, and CLAUDE.md
   §4 forbids one. **A queue of sentences you have not yet said out loud is a
   backlog in the most literal form this product can produce.** #160 also settles
   the placement positively, not only negatively: *"Due cards surface inside the
   W10 daily session as real exercises — typed production, **spoken production**,
   cued gaps."* W14's shadow target **is** a deck card's sentence, so this is
   #160's own sentence being honoured rather than an analogy to it.
3. **W13-i faced the identical question and ruled the same way**: the player
   ships inside the session, `ARCHITECTURE §3`'s `watch/[videoId]/` route was
   **not built**, and §3 was corrected rather than left describing a directory
   that does not exist. **W14 follows that precedent, and if `ARCHITECTURE-v3-web.md`
   §3 or §6 names a standalone shadow route, it is corrected in W14's commit.**

**The block's own code already names W14 — and the plan reports which half of
that expectation W14 actually meets.** `_output_block`
(`packages/core/services/sessions.py:1444`), verbatim:

> The written half only. **Speaking is W14 (`speech_attempts`, Azure scoring) and
> W15, so `output_task_spoken` is deliberately not served here** — offering a
> task nothing can score is worse than not offering it.

**That expectation is met in part and the part matters.** `output_task_spoken` is
*"Tell me about your yesterday, from waking up to going to bed. Two minutes, no
notes."* — **PRD §8 rung 3 (Answer)**, an open response scored by a model for
content coverage. **W14 builds rung 1 (Shadow), which is not that.** So W14 gives
block 4 a *speak* surface **without serving `output_task_spoken`**; the 24
`output_task_spoken` strings stay unserved and **W15 owns them**.
**`_output_block`'s docstring is corrected in W14's commit** — in place, with the
old text quoted (#82's shape) — rather than left describing an unblocking that
did not happen.

**Block 4's copy changes, because it currently describes only the written half.**
`copy.ts:113` is `title: "Say something of your own."` / `action: "Write it"`.
Shadow is **imitation, not the learner's own language**, so presenting it under
that title would be a category error in the copy. The block presents two things —
*say this line* (W14) and the written task (`/write`, W3, ✅ verified) — and the
title widens to cover both. Exact strings go through `BANNED` (§2.6).

### What this unblocks, and what it does NOT — checked, not assumed

`speech_attempts` carries a **nullable `session_id`**, so a shadow attempt inside
block 4 is **the first `session_id`-linked log block 4 has ever had**, the same
shape the progress ping gave block 2 at W13-i. **But this plan does not claim
`output` reaches `done`, and it does not claim #259 closes. Three reasons:**

1. **`_derive_done`'s `output` clause is about the WRITTEN task, and is still
   true after W14.** Verbatim: *"`output` — **cannot self-report.** `POST /correct`
   records no `session_id`, so nothing links a correction to the sitting it
   happened in."* A shadow log is evidence for a **different** thing than the
   block's stated task. Marking `output` `done` because a learner shadowed one
   line while the written task sits unanswered would **claim a learner completed
   work they did not do** — the exact collapse `BLOCK_STATES` forbids and
   `_build_block` exists to prevent.
2. **`sessions.completed` is unreachable for a SECOND, independent reason, and
   the record does not connect it here.** `_derive_done`'s docstring says output's
   `ready` *"is why `sessions.completed` is still unreachable"*. **That is now
   only half the cause.** `complete_block` — `minutes` and `completed_at`'s only
   writer — **was removed by W11 with the button nobody tapped**
   (`packages/core/services/week.py:43`; `apps/api/schemas/__init__.py:496`). So
   `sessions.completed` on a `daily` row has **no writer at all**, and a block
   reaching `done` does not give it one. **Two independent causes; W14 clears
   neither.**
3. **Therefore #259 does not close and is not even narrowed by this slice.** Its
   mechanism is `count_active_days` (`sessions.py:401`) counting
   `completed = TRUE`, and W14 writes nothing that flag reads.

**Filed as a new issue (§3.3): the record's own explanation of why
`sessions.completed` is unreachable is stale.** It names the output block and
does not name the deleted writer, which is the larger of the two causes — so a
later slice that repaired block 4 could reasonably believe it had fixed
`completed` and would be wrong. Found by checking S1's claim rather than by a
failure.

**What W14 does give block 4:** its first `session_id`-linked log, and therefore
the first raw material for whichever slice decides what `output` `done` should
mean once the block serves two things. **That decision is not W14's** — it needs
the written half linkable too, which is `POST /correct` gaining a `session_id`,
and that is not this slice's to add.

---

# §2 — What the plan specifies

## §2.1 The table — `speech_attempts`, migration **024** (not taken by this pass)

Designed for **W17**, since W17 is the only reason it accumulates.

```
speech_attempts
  id              BIGSERIAL PRIMARY KEY
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE
  session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL
  card_id         BIGINT REFERENCES cards(id) ON DELETE SET NULL
  surface         TEXT NOT NULL CHECK (surface IN ('shadow'))
  reference_text  TEXT NOT NULL          -- what the app ASKED for
  accuracy        REAL NOT NULL CHECK (accuracy     BETWEEN 0 AND 100)
  fluency         REAL NOT NULL CHECK (fluency      BETWEEN 0 AND 100)
  completeness    REAL NOT NULL CHECK (completeness BETWEEN 0 AND 100)
  pron_score      REAL NOT NULL CHECK (pron_score   BETWEEN 0 AND 100)
  prosody         REAL          CHECK (prosody IS NULL OR prosody BETWEEN 0 AND 100)
  words           JSONB NOT NULL        -- [{word, accuracy, error_type}]
  phonemes        JSONB NOT NULL        -- [{phoneme, accuracy}]   <- W17 reads this
  audio_seconds   REAL NOT NULL CHECK (audio_seconds >= 0)
  provider        TEXT NOT NULL         -- 'azure'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

**PRODUCT-PRINCIPLES §2, stated because every slice adding a user-keyed table
must:** `user_id` keys on **`users(id)`**, the surrogate identity 011
established. No Telegram id, no new dependency on one.

**Design notes, each with its reason:**

- **No `transcript` column, and the absence is the privacy rule made
  structural.** `ARCHITECTURE-v3-web.md:133` already says *"scores only — never
  audio, never transcripts"*. A column would eventually be filled.
- **`reference_text` is the reference, never the recognition.** It denormalises
  `cards.context_sentence` deliberately: a score is uninterpretable if the card
  is edited or deleted, and `card_id` is `ON DELETE SET NULL` so the measurement
  survives the card.
- **`phonemes` as JSONB on the attempt, not a second table.** PRODUCT-PRINCIPLES
  §3 flags *"data that scales per-user × per-lemma… if it materialises rows that
  could be computed"* — a phoneme-observation table materialises exactly that.
  W17's query is a `GROUP BY` over `jsonb_array_elements`; at ~2,400 phoneme
  observations a week for two learners (~125k/year), that is a sub-second scan
  with no index. **If W17 measures otherwise, a materialised table is a
  migration with a backfill from these same rows — the JSONB loses nothing.**
  Recorded as a §3 flag at the moment the choice is made, W7's `/audio` precedent.
- **`prosody` nullable and NULL.** The €0.264/hr add-on is **not bought**. The
  column exists because PRD §8 names prosody and a later purchase should not
  need DDL; NULL means *not measured*, never *zero*, which is #330's shape.
- **`surface` with a one-value CHECK, widened by W15.** The same move
  `errors.source`'s CHECK made at 012. It is what stops a retell attempt landing
  in this table untagged before W15 has decided what a retell score means.
- **`session_id` nullable, and it is §1e's whole mechanism.** It is what makes a
  shadow attempt block 4's first `session_id`-linked log — the shape
  `card_reviews` gives block 1 and `save_progress` gives block 2. **Nullable**
  because a shadow attempt outside a daily sitting is possible and is not a
  defect. **It does not by itself make `output` reach `done`** (§1e).
- **No UNIQUE.** Repeated attempts on the same card are the feature.
- **W14 writes no `errors` row and no `item_attempts` row.** v2's shadow held
  that line and so does this. `item_attempts.graded_by = 'self'` and the W6 ⟨R2⟩
  self-mark path are **untouched** — see §4.
- **No `ALTER TABLE users`**, so #48's paired-view-recreate rule does not fire.

## §2.2 The route

**ONE new route, not two — and that follows from §1e.** The shadow line is
served **in block 4's payload from `GET /session/today`**, the way block 2's
video already arrives, so there is no `GET /shadow/today` and no second place
that decides what today's line is. `_output_block` gains the selector (§1b's
predicate) and returns the card id and sentence beside the written task.

`apps/api/routers/shadow.py`, **one route, plain `def`**:

| Route | Service function | Why plain `def` |
|---|---|---|
| `POST /shadow/{card_id}/score` | `shadow_score.score_attempt(user_id, card_id, audio, session_id)` | reaches `core.speech` (#7, wider blast radius) |

Each **parses, authorises, calls exactly one service function, serialises.** No
business logic. `apps/api` imports neither `core.speech` nor `core.items.*` —
`test_core_boundary.py::test_the_api_never_reaches_the_hidden_half_of_an_item`
fails the commit that does. `POST` is JSON/multipart with the CORS preflight
barrier W2 established, and is rate limited.

**`tests/test_api.py`'s `BLOCKING_CALLS` gains `("speech", "assess_pronunciation")`.**
Naming it here because the existing sweep would otherwise pass over a new
blocking call it does not know about — a green test over an unreachable path
(CLAUDE.md §3 rule 4).

Service: `packages/core/services/shadow_score.py`. **Not** `packages/core/services/shadow.py`,
which is v2's Telegram shadow and stays untouched until W22 (PRODUCT-PRINCIPLES §1).
All SQL lives in the service. No FastAPI import.

Wrapper: `packages/core/speech.py` gains `assess_pronunciation(audio: bytes,
reference_text: str, *, settings) -> PronunciationResult`, and
`Settings` gains `azure_speech_key` (`repr=False`) and `azure_speech_region`.
**No provider SDK anywhere else** (CLAUDE.md §2). Swapping providers stays one
environment variable.

## §2.3 CLAUDE.md §3 rule 2 — one real call is OWED, and it is FREE

**Rule 2 fires.** This is new request construction in `speech.py`, and it is a
new provider. **The one thing in this slice no test can establish from our side
is Azure's pronunciation-assessment response shape** — the exact nesting of the
four aggregate scores, the per-word list, and the per-phoneme list; whether
phonemes arrive under every word or only on request; what the granularity and
`EnableMiscue` parameters change; and what a quota refusal actually looks like on
the wire. **A mock built from a guessed shape is a mocked suite passing over a
malformed request — CLAUDE.md §3 rule 2's originating failure, verbatim.**

**On F0 the call costs nothing.** There is no reason to defer it and every reason
to make it a **stop point**:

> **The build stops after the wrapper is written and before the parser is
> finished. One real call is made against the live Azure resource with a
> synthetic or operator-owned voice (§1c), the response is recorded verbatim into
> a fixture, and the parser is written against the recording. If the shape
> differs from what the plan assumed, the plan is wrong and says so.**

This is W10c's precedent, where *"rule 2 ran and earned its keep: one real call
confirmed `max_tokens=16000` AND FOUND A BUG that would have failed at `--apply`,
on production, after a whole run was paid for."* Here the same call costs €0.

**The call is the human's to run**, because the key lives on the host and Claude
Code has no SSH access. Written as an explicit command in Next action.

## §2.4 Mocking — at the transport, never at the service function

**Standing rule 7.** The mock goes at the **HTTP boundary inside `speech.py`**
(the `httpx` call / the `_azure_assess_once` seam), so that
`assess_pronunciation`'s **request construction, retry policy, error mapping and
response parsing all execute under test**. Mocking `shadow_score.assess_...`
would leave every one of those unexercised — the shape that produced #345's fifth
instance in W13-ii.

*(Observation, not a change: `tests/test_items_route.py:654` stubs
`core.services.items.speech.synthesize` — at the service function. It predates
the standing rule. W14 does not follow it and does not rewrite it.)*

`netguard` stays armed session-wide, so a test that reached Azure would raise
rather than consume quota. **Structural, not a promise.**

## §2.5 The mispronunciation acceptance is a HUMAN check

> *"A deliberately mispronounced word scores visibly lower"* — **this cannot be
> asserted by the suite.** It is a claim about a live acoustic model's behaviour
> on a real human voice through a real phone microphone. Any test that asserted
> it would be asserting a recorded fixture, which proves the parser and nothing
> about Azure.

**Written as a phone check, on BOTH devices** — iPhone 17 / Safari and Galaxy
A34 / Chrome — because §1c's capture path differs per device and the W2 lesson is
that an iPhone-shaped check serves one learner.

**The words to try**, chosen from PRD §2.5's per-L1 contrasts:

| Say the line correctly, then repeat mispronouncing… | Contrast | Whose L1 |
|---|---|---|
| **think** → "sink" | /θ/ → /s/ | both Farsi and Lithuanian lack /θ/ |
| **west** → "vest" | /w/ → /v/ | Farsi |
| **sheep** → "ship" | /iː/ → /ɪ/ | Lithuanian |

**What counts as passing:** on the second attempt, **that word's colouring drops
and the surrounding words' does not.** A uniform drop across the whole line is a
different result and would mean the reference alignment is wrong, not that the
mispronunciation was detected — worth naming, because a test that only looked at
the overall score would have called it a pass.

**THE CHECK IS THE OPERATOR'S TO PERFORM, ON BOTH DEVICES, AND IT IS NOT HANDED
TO THE OTHER LEARNER.** It requires a voice, and §1c's four data-processing
questions are unanswered — so the only voice that may be sent to Microsoft
before they are answered is the operator's own. Stated explicitly because the
check reads like an ordinary two-phone check and the second phone is the other
learner's. **If the check needs the Galaxy A34 and the operator does not hold
it, the Android half waits for the data questions** rather than being run by its
owner as a favour.

## §2.6 Copy gates — how the score is worded

**A pronunciation score is the single most likely surface in this product to read
as judgement.** CLAUDE.md §4, and **#348 is the live instance of a guilt message
shipping.** Every string goes through `copy_rules.BANNED` (the app addressing the
learner), not `BANNED_IN_CONTENT`.

**RULING (recommended): per-word colouring is shown. The four aggregate numbers
are persisted and NOT rendered.**

- **PRD §7.3 asks for *"per-word colouring"*, not for a score.** PRD §8's
  accuracy/fluency/completeness/prosody paragraph is about **persisting** them —
  its stated payoff is W17's weak-spot surface, not a number on the attempt
  screen.
- **A number on a person's voice is the shape §4 bans.** #303 records the same
  worry from §8.6's open question 3: *"a score on every turn may be exactly the
  thing that makes someone stop speaking."* That question is W13b's to answer for
  conversation; **W14 answers it for shadow by not showing one.**
- **W17 loses nothing** — the numbers are in the table.

**The copy, candidates for the implementation to hold to:**

| Surface | Candidate | Note |
|---|---|---|
| Waiting | **"Listening back…"** | no percentage, no "analysing" |
| Result heading | **"How it sounded"** | not "Your score", not "Results" |
| A weaker word | amber tint + **"Say this one again"** on tap | **never red, never ❌ or ✗** — both are in `_SAD` and already banned |
| Retry | **"Say it again"** | v2 shipped `BTN_SHADOW_AGAIN = "Try again"`; either passes |
| Second attempt better | **"Clearer that time."** | **raises announced** |
| Second attempt worse | **nothing at all** | **drops silent** — the screen re-renders and says nothing about the change |
| Scoring unavailable | **"Scoring is off today. The line is still worth saying."** | says so plainly; no backlog, no count of unscored attempts |
| No line to shadow | v2's `SHADOW_EMPTY_POOL` shape | not "you have nothing" |

**No colour is the only signal.** Colour-only feedback fails for a colour-blind
learner; the weaker words also carry a non-colour marker (an underline), which is
the design-accessibility floor, not a nicety.

## §2.7 Tests — RED first, and each one able to fail

Written failing, against the real entry point where there is one. **No assertion
may list its own failure mode among the accepted values, and none may be unable
to fail for the reason it claims** — #345, five instances, three of them written
*after* the row was filed.

| # | Test | The trap it is written to avoid |
|---|---|---|
| 1 | Route writes exactly **one** row and returns the parsed scores, through the ASGI transport, with the recorded Azure fixture | `== 1`, never `>= 1`; the score assertions are the fixture's **exact** numbers, never `0 <= x <= 100`, and never `... or None` (#345) |
| 2 | **No file appears anywhere on the SUCCESS path** — filesystem snapshot of cwd + tmpdir + runtime dir before and after the request | the acceptance criterion, made into an instrument for the first time |
| 3 | **No file appears anywhere on the FAILURE path** — transport raises; assert the same snapshot **and** that no row was written | an error path that writes a temp file breaks the rule as surely as a success path |
| 4 | AST over `core/speech.py` and `core/services/shadow_score.py`: no `open`, `tempfile`, `Path.write_*`, `shutil` | **with a negative control proving the detector is not inert**, the `_OFFENDING_SOURCE`/`_COMPLIANT_SOURCE` shape from `test_api.py` — CLAUDE.md §3 rule 4 |
| 5 | The recognised transcript is **never persisted and never logged** — fixture's transcript carries a sentinel; assert it appears in no column and in no `caplog` record | the one thing Azure returns that this product must not keep |
| 6 | **Phoneme scores accumulate per user** — two attempts, then run W17's aggregation query; expected phoneme set **hardcoded**, not computed from the writer | CLAUDE.md §3 rule 5: a test must not derive its expected value from the function under test (W1's `assert_path_outside_repo`) |
| 7 | **The shadow target is never a cue** — seed one `source_ref='video:1@3.200'` card and one chunk card; assert only the chunk card is selectable | §1b's ruling made structural; asserts the **positive** too, so it can fail if the selector returns nothing at all |
| 8 | Every string this surface says passes `BANNED` — the copy module and the React component | #348's live instance |
| 9 | `test_api.py`'s plain-`def` sweep, with `("speech", "assess_pronunciation")` added to `BLOCKING_CALLS` | a sweep that does not know a new blocking call passes vacuously |
| 10 | Quota exhaustion: soft-ceiling path renders no control; provider-refusal path writes **no** row and shows the plain message | a surface that silently stops is the failure §1d names |
| 11 | Vitest: the recorder holds a `Blob` and **never** calls a download, `createObjectURL` save, or IndexedDB write; the wait state renders; **no aggregate number appears anywhere** | the browser half of the disk rule, and §2.6's ruling |
| 12 | **`output` does NOT reach `done` from a shadow attempt alone** — seed a session, write a `speech_attempts` row against it, re-hydrate, assert `block_breakdown->>'output'` is still `ready` | §1e's negative, asserted rather than trusted; **asserts the row was written too**, so it cannot pass by the attempt silently failing (#345) |
| 13 | **The shadow line is served in block 4's payload and there is no second selector** — assert `GET /session/today`'s output block carries the card id and sentence, and that no other route returns a shadow target | §1e: one place decides today's line |

**Test 6 is the acceptance criterion's only honest instrument in the suite; test
2/3 are the second's; the third is §2.5's phone check.** All three named, none
conflated.

### S3 — tests 2 and 3 will fail spuriously, and the RULE is written before they do

**They are the first tests in this suite whose result depends on what else is
running**, and this project has already produced the failure mode: W13-i/6 —
*"THE FIRST FULL PYTEST RUN HAD A CONCURRENT WRITER, SO ITS THREE FAILURES ARE
NOT EVIDENCE."* Two pytest processes against one database; a serial re-run
cleared it.

**The danger is not the flake. It is the reaction to it.** A snapshot test that
fails once for an unrelated reason gets its scope trimmed — cwd only, then the
tmpdir dropped — and **the instrument that finally asserts the audio rule quietly
stops asserting it while staying green.** That is #345's family arriving by
**erosion** rather than by authorship, and erosion has no author to catch.

**Three rules, written into the tests' own docstrings:**

1. **The snapshot's root is a per-test temporary directory the test itself
   creates** (`tmp_path`), with the process cwd and `settings.runtime_dir`
   pointed into it for the duration. A concurrent writer anywhere else in the
   tree cannot appear in it, which removes the flake at its source rather than
   tolerating it.
2. **A spurious failure is resolved by narrowing the snapshot's ROOT, never by
   narrowing WHAT it looks for.** Stated as a rule because the two feel identical
   at 11pm and only one of them keeps the instrument.
3. **A snapshot failure is re-run SERIALLY before it is believed** — W13-i/6's
   own rule, applied to the tests most likely to need it.

**And test 4 is the redundancy that makes erosion survivable, which is now its
stated reason rather than belt-and-braces.** The AST test reads source: it
**cannot** flake, and it cannot be weakened by a trimmed root. If tests 2 and 3
are ever narrowed away, the audio rule still has one instrument standing. **Two
instruments, different failure modes, and that is the design.**

## §2.8 What this plan does NOT claim

1. **It does not deliver PRD §7.3's in-player "shadow this line."** The target is
   a deck sentence, not a video line. **#341 stays open and is not repaired.**
2. **It does not show the four aggregate scores** to a learner. They are stored.
3. **It does not buy or enable prosody.** The column is NULL.
4. **It does not build W17** — no weak-spot detection, no minimal-pair drills, no
   *"your /θ/ and /w/ are costing you most"* surface.
5. **It does not activate `users.l1_pronunciation_seed`.** Added at 009,
   nullable, inert; it stays inert until W17 has measured data to override it
   with, which is PRD §2.5's own rule.
6. **It does not close #303.** W13b owns that row; W14 builds the Azure half
   #303 names as shared, and #303 is **updated, not closed**.
6b. **It does not make block 4's `output` reach `done`, does not make
   `sessions.completed` reachable, and does not close or narrow #259** (§1e).
   `POST /correct` still records no `session_id`, and `complete_block` — the
   only writer `completed` ever had — was removed by W11.
6c. **It does not serve `output_task_spoken`.** W14 builds rung 1 (Shadow); the
   24 spoken tasks are rung 3 (Answer) and belong to **W15**.
6d. **It does not claim the 16 kHz resample works on an iPhone.** That is an
   untested assumption with a named failure mode and two free probes ahead of
   it (§1c/S2), and a stated fallback if both go badly.
7. **It does not build W15's other three rungs** — retell, answer, converse.
   `surface`'s CHECK is deliberately one value wide.
8. **It does not answer the Azure data-processing question** (§1c). It flags it
   and orders the real call so no learner's voice is sent before it is answered.
9. **It does not claim Azure's response shape is known.** That is owed to one
   free real call, and the parser is written after it, not before.
10. **It does not claim the F0 arithmetic is Azure-confirmed.** It is our
    estimate against a published tier, and §1d says where the two can diverge.
11. **It does not claim the ~1–2 s wait as a measurement.** It is an estimate
    from the request's shape, replaced at §2.3.
12. **It does not touch v2.** `packages/core/services/shadow.py`,
    `apps/bot/handlers/shadow.py` and their tests keep serving Telegram until
    W22. The W6 ⟨R2⟩ self-mark path on `speak_repeat` / `speak_answer` is
    **unchanged** — retiring it is a decision about `item_attempts.graded_by`
    and W19's progress line, and it belongs to whichever slice puts the two
    surfaces side by side, not to this one.
13. **It takes no migration number**, makes no Azure call, writes no key,
    endpoint or region literal into the repository, and marks nothing ✅.

---

# §3 — The BUILD_PROGRESS.md update block

## 3.1 Slice row

**W14 stays ⬜ NOT STARTED, mode PLAN.** Not 🟡 — 🟡 means code-complete and
there is no code (W10b's precedent, stated in that row: *"It is ⬜ NOT STARTED,
deliberately not 🟡"*). Row note: *plan written 2026-09-03; four rulings
recommended and awaiting the operator; migration 024 not taken; no Azure call
made.*

## 3.2 Decisions log — every ruling with its reason, declined alternatives, authorship

| Entry | Content |
|---|---|
| **W14/1 — the reconcile** | The prompt's migration premise was **stale by two takes**: it read 022 / #185's seventh; both halves read **024 / ninth**, W13-i having taken 021 (eighth) and W13-ii 023 (ninth). The mechanism the prompt gave is correct and is what made the drift traceable. 022 = `subtitle_ladder`, 023 = `video_glosses`, both on production; host `schema_version` **23**. Recorded as a **correction to the prompt**, not to the record. |
| **W14/2 — §1a RULED: the standing ruling does not reach scoring** | Four-part argument (no content produced; nothing enters deck/journal/bank; *"never while nobody is watching"* satisfied maximally; the cost argument inverts because F0 is free). Boundary stated in words so it is not widened by analogy. **Declined:** pre-recording utterances (cannot exist); asynchronous scoring (unactionable, and a backlog). **Assistant-recommended; the operator's acceptance is owed and W14 does not start without it.** |
| **W14/3 — §1b RULED: the shadow target is `cards.context_sentence`, never a cue** | R12's ~92% overlap inherited, not rediscovered; a second reason W13-i did not have (Azure's `CompletenessScore` is defined over the reference). Video-sourced cards **excluded by `source_ref LIKE 'video:%'`**, asserted by a test. **The two standing refusals stand.** **W14 inherits PRD §7.3's unmet in-player shadow and says so; #341 is not repaired.** |
| **W14/4 — §1c RULED: the browser normalises to 16 kHz mono 16-bit PCM WAV** | Two learners, two phones, two containers (Safari mp4/AAC, Chrome webm/Opus), neither natively accepted by Azure's short-audio REST. **Declined:** Speech SDK + GStreamer on the host (CLAUDE.md §5, shared host); server-side ffmpeg (same); per-device branching (a feature that varies on a property no learner can see — W13-i's refusal). **Consequence, positive:** `httpx>=0.27` is already a runtime dependency, so **no new dependency and no licence gate**. |
| **W14/5 — §1d: #320/#321 do NOT carry over, said plainly** | The Azure call is **free**, so there is no cost model to under-report. The risk is a **quota**, countable in seconds we produced ourselves. Importing the billed-path human-run/dry-by-default discipline would be caution transplanted from a problem this slice does not have, and would make the surface unusable. Ledger computed from our own bytes, never from Azure's reply (CLAUDE.md §3 rule 5). Soft ceiling **240 of 300 min**. The two counters can disagree and the plan says so. |
| **W14/6 — the ACCOUNTS doc's 5 hours is the WHOLE ladder** | Only shadow needs Azure; retell/answer/converse are STT and LLM. **W14 ≈ 36 min/month ≈ 12% of F0.** Pressure on the 5 hours comes from W15 and W17, not this slice. |
| **W14/7 — §2.6 RULED: per-word colouring is shown; the four aggregates are stored and not rendered** | PRD §7.3 asks for colouring, not a score; PRD §8's four numbers are asked for as *persisted*. #303 carries §8.6's open question 3 — *a score on every turn may be exactly the thing that makes someone stop speaking* — which W13b answers for conversation and **W14 answers for shadow by not showing one.** Amber and an underline, never red, never ❌/✗ (already in `_SAD`). Raises announced, drops silent. |
| **W14/8 — §2.1: phonemes as JSONB on the attempt, not a second table** | PRODUCT-PRINCIPLES §3 flags materialised rows that could be computed. ~125k observations/year for two learners is a sub-second `jsonb_array_elements` scan. **If W17 measures otherwise, the table is a migration with a backfill from these same rows.** Flagged at the moment the choice is made, not later. |
| **W14/9 — rule 2 fires, and the call is FREE** | New provider, new request construction. **Azure's response shape is the one thing no test can establish from our side.** Written as a **stop point** before the parser, with the response recorded verbatim into a fixture. **The call uses a synthetic or operator-owned voice, never the other learner's**, because the data question (§1c) is unanswered. |
| **W14/10 — the third-party position is FLAGGED, not settled** | PRODUCT-PRINCIPLES §3: licence and data checked before third-party processing, and the answer must hold for a commercial product. Four questions listed and none answered. One consequence is immediate and is an instruction: the owed real call precedes any learner's voice leaving the device. |
| **W14/11 — mocking at the transport** | Standing rule 7; #345's fifth instance in W13-ii. `test_items_route.py:654`'s service-level stub predates the rule; **observed, not rewritten.** |
| **W14/12 — the audio-discard rule has never had an instrument** | Enforced today by convention, docstring and absence only. W14 builds it: two filesystem-snapshot tests (success **and** failure paths) plus an AST test **with a proven-non-inert negative control**. |
| **W14/13 — §1e RULED: shadow ships inside block 4, no standalone route** | PRD §4.1 block 4 is *"Speak or write"* and the speak half has never existed (#303). **#160 applies positively as well as negatively** — *"due cards surface inside the daily session as real exercises — typed production, **spoken production**, cued gaps"* — and W14's target is a deck card's sentence. **W13-i's precedent:** the player ships inside the session and ARCHITECTURE §3's unbuilt `watch/[videoId]/` was corrected rather than left. **Declined:** a standalone `/shadow` screen — a queue of sentences you have not said out loud is a backlog in the most literal form this product can produce (CLAUDE.md §4, PRD §11.5). Block 4's copy widens in the same commit, because shadow is imitation and *"Say something of your own"* describes only the written half. |
| **W14/14 — §1e: the docstring's expectation is met in PART, and the part is named** | `_output_block:1444` says *"Speaking is W14… so `output_task_spoken` is deliberately not served here."* **`output_task_spoken` is rung 3 (Answer), not rung 1 (Shadow).** W14 gives block 4 a speak surface **without serving those 24 strings**; W15 owns them. **The docstring is corrected in place in W14's commit, old text quoted** (#82's shape), rather than left describing an unblocking that did not happen. |
| **W14/15 — §1e: #259 does NOT close, and the check found the record stale** | `speech_attempts.session_id` gives block 4 its first log — **and that is not enough for `done`, on three counts checked rather than assumed.** (1) `_derive_done`'s `output` clause is about the WRITTEN task and is still true: `POST /correct` records no `session_id`. Marking `done` off a shadow log would claim work not done — `BLOCK_STATES`' forbidden collapse. (2) **`sessions.completed` has a second, independent cause the record does not connect here: `complete_block` was removed by W11** (`week.py:43`, `schemas/__init__.py:496`), so the flag has **no writer at all** on a `daily` row. (3) #259 reads that flag, so W14 writes nothing it sees. **Filed as a new issue** — see 3.3. |
| **W14/16 — §1c/S2: the 16 kHz resample is an assumption, not a ruling, until two free probes clear it** | `OfflineAudioContext` at a non-hardware rate has historically been refused by WebKit; if that holds, **the capture path fails on one of two devices at the step the plan treated as settled.** Two free probes ordered **P0a before P0b**, because P0a may delete the problem: if Azure accepts 48 kHz PCM WAV, **no resample is needed at all**. **Fallback stated in advance** — hand-written linear interpolation with a box-average pre-filter, because downsampling without a low-pass stage aliases and aliasing on a pronunciation scorer is not cosmetic. **Per-device branching stays refused** (§1c). This is the 2026-08-23 platform-assumption correction happening a fifth time, and before the frontend rather than after. |
| **W14/17 — §2.7/S3: the erosion rule for the snapshot tests, written before the first flake** | Tests 2 and 3 are the first in this suite whose result depends on what else is running; W13-i/6 already produced that failure. **The danger is the reaction, not the flake:** a trimmed scope leaves the instrument green and inert — #345's family arriving by erosion, which has no author to catch. Three rules in the docstrings: per-test `tmp_path` root; **a spurious failure narrows the ROOT, never WHAT it looks for**; re-run serially before believing it. **Test 4 (AST) is the redundancy that makes erosion survivable and that is now its stated reason** — it reads source, so it cannot flake and cannot be weakened by a trimmed root. |
| **W14/18 — §2.5's phone check is the OPERATOR's, not the other learner's** | It needs a voice, and §1c's four data questions are unanswered. **If the Android half needs a device the operator does not hold, it waits for those answers** rather than being run by its owner as a favour. |

## 3.3 Known issues

| # | New / carried | Sev | Target |
|---|---|---|---|
| **NEW** | **The audio-never-on-disk rule is asserted by nothing in the tree.** `speech.py`'s docstring says it, three live Telegram handlers rely on it, and no test would notice a temp file appearing on any of them. **Found by reading for W14's acceptance, not by a failure.** Closes when §2.7's tests 2/3/4 land — but the *existing* OpenAI paths stay uncovered even then, and that is the part worth filing. | **medium** | **W14**, and the v2 paths at **W22** |
| **NEW** | **Azure Speech's data-processing position is unknown and a learner's voice is the payload.** Four questions listed at §1c. **Blocking for the surface reaching a phone, not for the slice's code.** | **medium** | **W14 / operator** |
| **NEW** | **The two learners' phones produce different audio containers and neither is natively accepted by the target API.** Ruled around at §1c by browser-side PCM normalisation; filed because it is a fact about the fleet that W15's three remaining rungs inherit unchanged. | low | **W15** |
| **NEW** | **THE RECORD'S EXPLANATION OF WHY `sessions.completed` IS UNREACHABLE IS STALE, AND IT NAMES THE SMALLER OF TWO CAUSES.** `_derive_done`'s docstring says the `output` block staying `ready` *"is why `sessions.completed` is still unreachable"*. **The larger cause is that `complete_block` — `minutes` and `completed_at`'s only writer — was removed by W11 with the button nobody tapped**, so the flag has **no writer at all** on a `daily` row (`week.py:43`, `schemas/__init__.py:496`, both of which state it plainly; `_derive_done` does not). **The consequence is not cosmetic: a later slice that repaired block 4's log could reasonably believe it had made `completed` reachable, and would be wrong.** Found by checking §1e's claim rather than by a failure. **#259 is unaffected either way and stays open.** | **medium** | **the slice that gives `POST /correct` a `session_id`** — not W14 |
| **NEW** | **`OfflineAudioContext` at 16 kHz may be refused by WebKit, which would break the capture path on the iPhone.** Two free probes ordered ahead of any capture code (§1c/S2), P0a first because it may delete the problem entirely. Filed rather than assumed away, because it is the 2026-08-23 platform-assumption shape a fifth time. | **medium** | **W14, before implementation** |
| #303 | carried, **updated not closed** — W14 builds the Azure half it names as shared | medium | W13b |
| #341 | carried, **not repaired** — W14 inherits it and states so | — | W13/W13a |
| #185 | carried — **024 shifts if any slice below takes a number before W14 builds** | — | open |
| #345 | carried — binds all eleven tests | — | open |
| #346 | carried — **`W14` has no hyphen, so it does not fire here**; recorded so it is not re-derived | — | open |

## 3.4 File inventory

| File | Purpose | State |
|---|---|---|
| `prompts/CC-W14-speaking-shadow-and-score-PLAN.md` | The archived slice prompt. Intent, not state; never consulted for build status (CLAUDE.md preamble). | new |

**Nothing else.** No `.sql`, no `packages/core` file, no `apps/web` file, no
test, no `data/` change.

## 3.5 Next action — **none dropped**

1. **W11b's OWN CHECK, Sunday 2026-09-06 — and it carries #348's only
   independent proof.** Home shows the report and no *Start today's session*
   button; **no digit anywhere on an empty week**; **and no Telegram report
   arrives.**
2. **W13-i's FOUR REMAINING PHONE CHECKS, from 2026-09-07.** **#341** closes on
   the highlight.
3. **T1 — three assigned videos, five #316 channels.** Gates **both** billed
   runs: W13-ii's first pre-generation run and #352's five items.
4. **#352's FIVE-ITEM RUN — 33 calls, the operator's to pay for, honest
   expectation ~2 of 5.** P1–P4 registered before it; one top-up round then stop
   and report unmet; a short landing promotes F2; **#352 does not close on it.**
   - **4a. BEFORE THAT RUN: move `w11-checkpoint-journal.jsonl` aside**, to a
     path `git clean -fd` does not reach — **17,583 bytes of a previous run are
     in it and a live run appends** (#309, #342).
5. **W10d COMMIT 2 — the focus half.** `focus_held`, the focus `--fill`, F1, F2,
   the 56-item target. **#299 stays `high`** and unit 1's block 3 serves four
   items a day until it lands.
6. **#351's ONE-LINE EDIT to `docs/DEPLOYMENT.md:279-292`.** Applied by hand five
   times, worked every time, **still unwritten**.
7. **T2** and **T4**. **`0a` before any row carries a SHA (#343).**
8. **NEW, W14's own, and it is the operator's before any code:** accept or refuse
   **§1a** (scoring is measurement, not generation) and **§1b** (the shadow target
   is a deck sentence, not a cue, and PRD §7.3's in-player shadow is not
   delivered). **W14 does not start without both.**
9. **NEW, W14's own, FREE, and it runs FIRST because it may delete a design
   problem — P0a.** The rule-2 real call against the Azure Speech resource, **written
   as an explicit host command** (Claude Code has no SSH access), using a
   synthetic or operator-owned voice — **never the other learner's** — with the
   response recorded verbatim into a fixture. **Two things in one free session:**
   the response shape, **and** whether Azure accepts **48 kHz** mono 16-bit PCM
   WAV. If it does, §1c's resample is dropped and P0b may not be needed at all.
10. **NEW, W14's own, FREE, both phones — P0b**, only if P0a leaves a resample in
    the path. Does `new OfflineAudioContext(1, 16000, 16000)` construct? Does
    `decodeAudioData` accept that device's own `MediaRecorder` output? What
    `mimeType` did each recorder actually choose? **Throwaway page, not committed
    to `apps/web`.**
11. **NEW, W14's own:** the four Azure data-processing questions (§1c),
    **answered before any learner's voice leaves a device.**
12. **NEW, W14's own, at implementation:** correct `_output_block`'s docstring in
    place with the old text quoted, and check whether `ARCHITECTURE-v3-web.md`
    §3 or §6 names a standalone shadow route — correcting it in the same commit
    if so, as W13-i did for `watch/[videoId]/`.

**THE CARRIED SET, NONE DROPPED: #335 · #336 · #337 · #338 · #339 · #340 ·
#341 · #342 · #343 · #344 · #345 · #346 · #347 · #349 · #350 · #351** (🟡)
**· #352** (`high`, producible, not closed) **· #354 · #355 · #356 · #357 ·
#358.** **#348, #353 and #359 are closed.** **#169 is open throughout W10d.**

**UNIT 2's CONTENT IS HELD on #299 and #249. W11c's acceptances are all met and
its ✅ is the operator's. W14 IS NOT STARTED.**

---

# §4 — Verification (of the plan, not of code)

There is no code to verify. What this pass can be checked against:

- **`docs/TASKS-v3-web.md:85` and `:132` both read 024** — `grep -n "W14"` and
  `sed -n '132p'`. Confirmed above, verbatim.
- **`migrations/` tops out at `023_video_glosses.sql`; host `schema_version` 23**
  — `ls migrations/`, and the Next action head dated 2026-09-03.
- **No new dependency** — `httpx>=0.27` present at `requirements.txt:20` and
  `packages/core/pyproject.toml:53`.
- **`Settings` has no Azure field and `_KNOWN_STT_PROVIDERS` is `{"openai"}`** —
  `packages/core/config.py:22`, so `STT_PROVIDER=azure` is refused at load today.
- **The cue-overlap numbers are quoted from `packages/core/video/cues.py`'s own
  header**, not re-derived.
- **`source_ref = 'video:<id>@<seconds>'`** — `packages/core/services/cards.py:1363`.
- **Block 4's own code names W14** — `packages/core/services/sessions.py:1444`,
  quoted verbatim at §1e — and **PRD §4.1 block 4 is *"Speak or write"***.
- **`_derive_done`'s `output` clause still says *cannot self-report*** —
  `sessions.py:1583`; and **`complete_block` no longer exists anywhere in the
  tree**, confirmed by `grep -rn "complete_block"` returning only prose in
  `week.py:43`, `schemas/__init__.py:496`, `syllabus.py:736` and four tests.
  **That is the §1e finding, and it is why #259 does not close here.**
- **`output_task_spoken` exists 24 times in `data/syllabus_units.json`** and is
  rung 3, not rung 1 — W15's, not W14's.
- **Nothing was written outside this plan file**, and no Azure endpoint, key or
  region literal appears anywhere in the repository.
