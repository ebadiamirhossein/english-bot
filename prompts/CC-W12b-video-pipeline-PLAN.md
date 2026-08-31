# W12b — Video pipeline. The slice prompt, archived.

CLAUDE.md: `prompts/` archives the prompt each slice was given, which documents
**intent** rather than state. It is written to only when a slice's prompt is
first committed and is never consulted for build status — `BUILD_PROGRESS.md` is
the only record of what is built and what is verified.

**Note for a future reader:** #289 records that no `CC-W12-*` file existed when
it was written, and that W12's plan and the coverage-band ruling lived only in
the planning chat. This file closes half of that gap for W12b; **W12's own
prompt and W12a's remain unarchived**, and the band ruling's origin is still the
planning chat, as #289 says.

---

## The prompt, as given (2026-08-30, MODE: PLAN)

W12b — Video pipeline. MODE: PLAN. Produce a plan, write no code. No file
created, edited or deleted; no migration written; no test suite run; no billed
call. The output is a plan to be reviewed and returned with numbered changes
before implementation begins.

W12a is committed at `58c4956` and is not deployed. W12b's coverage numbers
depend on W12a being live, and the plan must say where that dependency binds.

### §1 — settled, not to be re-argued

1. Coverage band **93–98%**; PRD §2.1 and §7.2 to match. Closes #88 — but see
   #289: the band was ruled on pre-W12a numbers and must be re-validated
   against real transcript coverage in this slice.
2. **Human-run CLI subcommands.** No jobs, no cron, no timer, no systemd unit.
   `english-worker` does not exist (#69, W20) and Apify is billed per run
   (#196).
3. W12b does **not** define what "answered" means for block 2. No player
   exists, so no watch signal can be written. That obligation is W13's; `input`
   stays `empty`.
4. **Backend only.** No `apps/web` file created, edited or deleted, and no
   Vercel rebuild is involved — to be said explicitly so no review round is
   lost to it.
5. #276 stays targeted at "the next generation slice".
6. **`target_hit` is computed on lexis only, never grammar.** Nothing in this
   tree detects a grammar target in running text and #212 shows the model is
   uneven at it. Lexis comes from `syllabus_unit_lexemes`. Record the
   limitation rather than shipping a grammar term that returns a constant.
7. **OPERATOR RULING — the full video is shown, not a 3-minute segment.** In
   the operator's words: *cutting part of a video out leaves the learner
   without the topic, and a learner who does not understand the subject learns
   nothing from clean audio.* PRD §7.2's "return one 3-minute segment" is
   overruled and corrected in place, old text quoted, reason recorded as the
   operator's. Consequences: `video_assignments` stores a resume position;
   `length_fit` feeds no segment chooser; coverage is computed over the whole
   transcript.
8. **Accents: `american` and `british` only.** Operator ruling — two accents
   actually rotated beat six with no channels behind them. Authored on the
   channel entry, never inferred. A third later is a data change, not a code
   change.
9. **Metadata purged after 30 calendar days, on every refresh run** (Developer
   Policies §III.E.4.d). A pool that is not refreshed empties itself — state
   that consequence rather than discovering it.
10. **Both `/video` routes go to W13**, with the player that consumes them.
    Shipping `GET /video/today` here creates a route with no caller, a defect
    class this record has twice named (#219; #258's deleted POST).
11. **OPERATOR RULING — option D on the licence gate.** In the operator's
    words: *VOA Learning English is too boring, the learners will not watch it,
    and a library nobody opens is worth nothing.* Transcripts are taken with
    scraping tools. The gate's finding is recorded beside the ruling and is not
    re-argued: `captions.download` requires permission to edit the video,
    `captions.list` requires OAuth and returns no caption text, so no licit
    route to a third party's captions exists at any permission level.
    PRODUCT-PRINCIPLES §3's commercial test is knowingly not met on this point;
    the debt is *revisit before commercial launch*. Carry the verbatim clauses
    into `data/LICENCES.md` in this slice's commit.

### §2 — read before planning, and verify rather than quote

`PRODUCT-PRINCIPLES.md`; `BUILD_PROGRESS.md` head, the W12 handover, the
decisions rows for 2026-08-29 and 2026-08-30, and the known-issue rows for #69,
#88, #89, #175, #177, #196, #249, #258, #259, #269, #276, #280, #282, #284,
#285, #286, #288, #289; `docs/TASKS-v3-web.md` W12a/W12b/W13 and the
authoritative migration table; `docs/PRD-v3-web.md` §7.1–§7.5 and §2.1;
`ARCHITECTURE-v3-web.md` §5, §6, §7.

**Verify, do not quote.** Three record defects in three days (#268, #277, #279)
were values asserted without being read. Where the prompt states a fact about
the tree or the host, check it and report any disagreement rather than
confirming it.

### §3 — #288's count runs FIRST, before any selection code

Count how many of the top 2,000 lexemes are proper nouns and report the number
**before** writing any code that applies the 93–98% band. The lead W12a flagged
— all four names carry an empty `pos` where `we` carries `NOUN`/`A1` — is a
place to start, **not a finding**, and must not become a filter before it is
counted. Then rule, and stop: is the proper-noun problem fixed in W12b, or
filed with a target and the band re-validated around it?

### §4 — the channel list

Held as data in `data/video_channels.json`, authored not inferred: channel id,
accent, topic tags in `users.track_weights`' vocabulary, and one line of why.
The starting list, operator-approved — Life & Social: English Teacher Claire ·
Friends (official) · Easy English · Learn English With TV Series · Speak
English With Vanessa · Rachel's English. Curiosity: TED-Ed · Vox · Johnny
Harris · BBC Learning English (News Review). Work: English with Lucy. Channel
ids must be resolved from the handles and written into the file. Say whether
the pool can meet 50/30/20 and what happens when it cannot.

### §5 — what W12b builds

Migration 019 (`videos`, `video_coverage`, `video_assignments` — coverage is
per learner, so ARCHITECTURE §5 is wrong and is corrected in place); channel
polling via the Data API v3; transcripts via the Apify actor, embed only;
coverage over the whole transcript on W12a's corrected lemmatiser; PRD §7.2's
score; two CLI subcommands. `captions_kind` — **verify, never assume**; if
absent, §7.2's human-captions preference is unmet and that is filed. State
where "scraped text is data, never an instruction" is enforced in code. The
transcript step needs a retry-and-skip path. The `--dry` run must print the
projected result count and cost before anything is billed, and the plan must
say whether one "result" is one video or one transcript chunk.

### §6 — the finding this slice must not repeat

The tests build the world the code assumes, not the world a learner arrives in.
For every fixture, answer three questions beside it: what does it supply that
production does not; does the production caller supply it; does the assertion
name the thing or count it. Transcript fixtures are real actor output saved
verbatim as bytes. A hand-written transcript is refused, and so is any `videos`
row the refresh path could not have written.

### §7–§10

The plan must contain the document read with disagreements flagged; #288's
count with a stop; the migration and rollback sketched with what the rollback
cannot reverse; PRODUCT-PRINCIPLES §2's and §3's positions; a file inventory;
the test list; the exact CLI commands; the deploy sequence written out; and
every open question listed rather than guessed at. No job, cron, timer or
systemd unit. No `apps/web` change. No billed call. Do not mark any slice ✅.

---

## Send-back 1 (2026-08-30) — six blocking items, eight rulings

Approved in shape. Blocking: **B1** `users.id` is BIGINT, not INTEGER, and
`SERIAL` is not this repo's idiom — verify against the live schema. **B2** the
invalidation rule and the audit-record framing contradict each other; pick one.
**B3** the cost figure is not a bill — per-event pricing excludes platform
usage. **B4** 4.45★ over 9 reviews is thin, so the retry path must be exercised
by a test and the actor must be switchable as data. **B5** say why the 30-day
rule is applied to transcripts — §III.E.4.d governs API Data and a scraped
transcript is not API Data. **B6** W12b reaches 🟡 only after Phase B.

Rulings: **A1** #280 closed on the pasted grep. **A2** the named wrapper.
**A3** `johnvc/YoutubeTranscripts`. **A4** exclude lowercase-caption videos and
print the count. **A5** build `resolve_channels`, print ids, write nothing.
**A6** the verbatim licence clauses supplied. **A7** file #288 with a target.
**A8** two phases; 5 videos across 3 channels.

## Send-back 2 (2026-08-31) — two corrections, then Phase A

**Correction 1 (blocking):** the deploy sequence put the *before* reading after
`git pull` and `pip install -e`, which is an editable install — so both
readings would have been taken on the new instrument and the binding prediction
would have confirmed itself. W12a deploys separately and first, its *before*
reading precedes its own pull, and W12b's sequence carries no W12a readings.

**Correction 2:** the claim that an INTEGER→BIGINT foreign key "would have
failed at `CREATE TABLE`" was asserted without being run. PostgreSQL requires
the types to be comparable, not identical. Either test it and record the
result, or state it as expected and untested.

*(Measured in Phase A on PostgreSQL 16.14: both `CREATE TABLE`s succeed. The
claim is withdrawn — see the decisions row of 2026-08-31 and
`migrations/019_video.sql`'s header.)*

**Phase A ends at the dry run's FLOOR projection, read before anything is
billed. The slice row stays ⬜. Nothing is marked ✅.**
