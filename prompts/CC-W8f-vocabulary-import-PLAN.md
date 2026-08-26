# W8f — Vocabulary import: Language Reactor and Trancy

**Mode: PLAN.** Nothing below is implemented. Approve before any code is written.

---

## Context

The operator captures vocabulary daily in Language Reactor and Trancy. The only
import route in this system is the **v2 Telegram CSV handler**, which dies at W22
and has no web successor. `docs/PRD-v3-web.md` §7.1 keeps this path deliberately
— Netflix and Disney+ are "not embeddable, not scrapable", so a CSV export *is*
the mechanism for series input — yet no v3 slice owns it.

Known issue **#27** has said since S15a that "the Language Reactor half remains
unverified against a real export." Two real exports are now in hand. Parsing them
turns #27 from unverified into **measured, and it is broken**:

```
v2 `parse_csv_bytes` + `classify_csv_format` on the real LR export
  → 7 headers, 9 data rows, classify → None → file refused
actual file
  → 0 headers, 2 records, 24 tab-separated columns
```

The real export has **no header row at all**, so `csv.DictReader` consumes the
first record as headers and comma-splits a tab-delimited line; the "9 rows" are
newlines inside quoted context fields. `is_language_reactor_headers` looks for a
`Phrase` column that does not exist. **A real Language Reactor export has never
been importable.** #27 closes here with that finding, not with a shrug.

The second reason this slice exists is **#99**. W8b measured the deck at **7 of
14 work-framed cards — 50% against §4's 20% cap** (ids 16, 18, 20, 22, 24, 26,
30), and traced the cause: S24a generated a sentence around each bare Trancy
word using a prompt with no track weighting. #99's status now reads that its
"remaining surface is entirely the import paths." This slice is an import path.
It must not rebuild the generator.

**Intended outcome:** one human-run importer that reads both real formats, writes
cards carrying the sentence the learner actually met the word in, makes no model
call, and is dry by default.

---

## What the two fixtures established

Parsed first-hand. Corrections to the slice prompt are marked **▲**.

### Language Reactor — `languagereactor.csv`, 2 records, 24 tab-separated columns

▲ **No header row.** Record 0 is data (`WORD|swain|en`). Use
`csv.reader(delimiter='\t')` over `utf-8-sig`; both records parse to exactly 24
fields. The doubled quotes in column 2 are CSV escaping of **real quote
characters in the source text** (a Milton quotation inside the book), not a
parser quirk.

| # | Content | swain | devour |
|---|---|---|---|
| 0 | id | `WORD\|swain\|en` | `WORD\|devour\|en` |
| 1 | item type | `Word` | `Word` |
| 2 | **the sentence met** | *"Unknown, and like esteemed…"* | *We Americans devour eagerly…* |
| 3 | sentence in L1 | Farsi | Farsi |
| 4 | surface form | `swain` | `devour` |
| 5 | lemma | `swain` | `devour` |
| 6 | part of speech | `Noun` | `Verb` |
| 8 | L1 gloss, comma-separated | `معشوق, دلبر, یار` | `بلعیدن, خوردن, فرو بردن` |
| 9 | category | `Books` | `Books` |
| 10 | source language | `en` | `en` |
| 11 | target language | `fa` | `fa` |
| 14 | **unknown** | `6` | `0` |
| 15 | source id | `gb_20203` | `gb_20203` |
| 16 | source title | `Autobiography of Benjamin Franklin` | same |
| 17 | captured at | `2026-08-26 09:22` | `2026-08-26 09:21` |
| 18–19 | wider context + L1, 3 lines each | ✓ | ✓ |
| 23 | audio filename | `1787736123635.mp3` | `1787736112873.mp3` |

**Not established, therefore not used** (recorded, not guessed):

- **Column 14** — values `6` and `0`. Two records cannot distinguish a
  familiarity score from an offset. Not read.
- **Column 4 vs 5** — identical in both records, so the surface/lemma
  distinction cannot be confirmed. The plan reads **column 5** and states this
  as an assumption.
- **Column 11** — `fa` in both records; whether it is reliably the learner's L1
  cannot be established from two rows. See D4, which does not trust it.
- **Columns 7, 12, 13, 20, 21, 22** — empty in every record.
- **`gb_` in column 15** — prefix unresolved from the file.

▲ **The audio IS in the export.** The zip contains `media/` with both files
(`items.csv` is the CSV's name inside the zip). Further: `1787736123635.mp3` is
**Ogg/Opus data**, not MPEG — the extension lies about the container. Recorded;
**nothing is built for it.** Column 23 is parsed and carried as a filename string
only. No download, no playback, no R2 — that stays W13's.

### Trancy — `trancy.csv`, header row + 9 rows, 4 comma-separated columns

`Word, Phonetic, Translation, Date`. No sentence. Classifies correctly today as
`vocabulary`.

**It is byte-identical to `VOCABULARY LIST 2026-08-14.csv`** — verified with
`diff`. This is not *a* Trancy file; it is **the file S24a imported**. Its nine
words are exactly W8b's nine `vocabulary` chunks:

```
tier, notch, luckily, frustrate, bootstrap, proper, incapable, psychosis, convenient
```

`tier`'s Translation, exact bytes (note the leading space and the doubled space
after `;`), to be confirmed against card 17 in psql:

```
' سطح ردیف;  چیدمان در سطوح طبقه‌بندی'
```

**The S24a "1 skipped" claim was wrong.** S24a's row records *9 words → 8
imported / 1 skipped (`frustrate`)*; the file contains nine rows **including
`frustrate`**; the census counts nine `vocabulary` chunks; and `frustrate` is the
back of card 32. All nine landed. BUILD_PROGRESS currently leaves this as "either
a second import ran, or the skip did not skip" — the file settles it: **there was
one import, of nine rows, and the reply's count was wrong.** Corrected in the
record.

▲ Minor: the prompt names `bootstrap`, `staging` and `tier` as work-bias words.
`bootstrap` and `tier` are **captured Trancy words**; `staging` appears only in
**generated sentences**. Different mechanisms, and only the second is the bias.

---

## The ruling: Language Reactor primary, Trancy degraded

**Assistant-recommended, operator-accepted** — recorded with that authorship, as
the W8c glosses and the #157/#170 rulings were.

An LR row carries the sentence the learner actually met. A Trancy row carries a
bare word — which is why v2 generated a sentence around it, and that generator is
**the measured cause of the 50% work bias**. This slice does not rebuild it.

- **LR rows become cards with their real sentence.** No generation, no model call.
- **Trancy rows import word, phonetic and gloss, and no sentence.** See D6.

**No model call anywhere in this slice.** If implementation reaches for a
generator, stop and report why.

---

## Design proposals

Numbered as the slice prompt numbered them. These are proposals; approval of this
plan is what decides them.

### D1 — Cards directly, and this is the creator W13 reuses

`docs/ARCHITECTURE-v3-web.md` §6 already assigns card creation to
`POST /video/{id}/save-word → creates cards`; PRD §7.3 has the player's
Add-to-deck "create the cloze + production cards with this exact sentence and
timestamp"; and `migrations/013_cards.sql:88` says of `lexeme_id`, in its own
comment, *"W13's capture sets it."* An LR row and a tapped transcript word carry
**identical inputs**: lemma, sentence, gloss, source title, captured-at. One
creator, called by a CLI here and by a route at W13.

New pure planner `core.cards.capture.plan_for_capture(record, *, now) -> Plan`,
mirroring `migrate_chunks.plan_for_chunk` — no DB, no clock beyond `now`, so the
fan-out table is testable without Postgres (§3 rule 5). It returns card specs;
`core.services.cards.create_card` inserts them unchanged.

**Fan-out: two cards per accepted row** — `recognition` and `production`, as a
new constant `CAPTURE_CARD_TYPES` beside `CHUNK_CARD_TYPES`.

| Type | front | back | context_sentence |
|---|---|---|---|
| `recognition` | the real sentence | the L1 gloss | the real sentence |
| `production` | the L1 gloss | the lemma | the real sentence |

**No cloze card, and the reason is not W8b's.** W8b removed chunk cloze because a
v2 chunk is an idiom and a gap swallowing a whole phrase is unanswerable — that
objection does **not** apply to a single word in a real sentence. The blocker is
**#147**: `make_sentence_with_gap` replaces a *substring*, so it gaps *tier* out
of *tiers*. A cloze card built with it inherits a live open defect. Cloze is
deferred to W13 together with a whole-word gapper, stated as a cost, not omitted.

**No `production` front carries a context hint**, for the same reason — that hint
is what `make_sentence_with_gap` builds. `migrate_chunks` already has a
`production_no_hint` bucket; this is that shape.

### D2 — The ledger ceiling filters. The frequency floor does not.

**This reverses the plan's first version, and the reversal is the operator's
ruling.** The argument that lost is recorded below, because the threshold will
look re-proposable to the next reader.

Measured against `data/lexemes.tsv` (15,017 rows) for all eleven fixture words:

| word | freq_rank | band | cefr |
|---|---|---|---|
| proper | 1833 | 2 | A2 |
| luckily | 4035 | 5 | A2 |
| convenient | 4406 | 5 | A2 |
| frustrate | 6424 | 7 | — |
| devour | 6805 | 7 | — |
| notch | 7346 | 8 | — |
| incapable | 7386 | 8 | — |
| **swain** | **11886** | 12 | — |
| **psychosis** | **14342** | 15 | — |
| **tier** | **absent** | — | — |
| **bootstrap** | **absent** | — | — |

**One instrument filters, and it is the ledger:**

- **Ceiling (already known):** reject when the lemma is in
  `lexicon.known_lemmas(conn, user_id)` — states `known`/`mastered`. `proper`
  sits at rank 1833, inside the top-2,000 assumption floor, so **the ledger
  rejects it, not the rank.** A word at `seen`/`learning` is imported: meeting a
  word and not yet knowing it is precisely what a card is for.
- **Floor: none. A capture is never rejected for rarity.** `swain`, `psychosis`,
  `tier` and `bootstrap` all import.

**Why the floor was dropped.** Two errors, and the second is the one that
matters.

1. **`freq_rank IS NULL` does not mean rare.** `tier` and `bootstrap` are absent
   from a 15,017-row general-English list built from OpenSubtitles; that is a
   fact about the seed list, not about the words. Migration 010's rule — *NULL
   means "rarer than the seed list's tail", sort it last, never coerce it to
   zero* — is a **sorting** rule. Using it to **reject** silently upgrades
   "absent from our list" into "too rare to be worth a card", which the list was
   never built to say. **A missing rank is `unknown`, and unknown is not rare.**
2. **A capture is not a suggestion.** The learner met the word, did not know it,
   and looked it up. That is the strongest statement of intent this system can
   receive — stronger than a syllabus row and stronger than a frequency rank.
   `psychosis` at 14,342 came from a documentary the operator was watching.
   Refusing it means the app declines to teach a word its learner explicitly
   asked for, and says nothing about why.

**The corroboration claimed in the first version was a coincidence.** That
version read the floor's rejection of `tier` and `bootstrap` as evidence the
threshold was right, *three sections after this same plan established that those
two entered as **captures** while the work bias entered through **generated
sentences***. Unrelated mechanisms. Filtering the captured word treats the
symptom's neighbour and leaves #99's actual surface — context generation —
untouched, which this slice avoids by generating nothing at all.

**Rarity is recorded, not acted on.** `freq_rank` is already on `lexemes` and the
card links to it through `lexeme_id`, so a later slice can **deprioritise** a
rank-14,342 word in scheduling rather than refuse it at the door. Nothing new is
stored.

**Where a frequency floor does belong:** proactive selection — which words the
syllabus and the daily session offer *unprompted*. That is not this path.

**Rejected rows are recorded, never silently dropped.** The dry run prints every
row with its verdict, and an accounting identity makes "nothing was lost"
checkable rather than asserted — `migrate_chunks`' bucket property:

```
imported + skipped_too_rare + skipped_already_known + skipped_duplicate
        + skipped_no_gloss  + skipped_no_sentence                       == rows_read
cards_created == 2 × imported
```

**`skipped_too_rare` is retained and is always zero.** Keeping the bucket means
reinstating a floor later is a threshold, not new plumbing — and a bucket that
reads zero on every run is a visible record that the decision was made, where a
deleted bucket would read as one never considered. A test asserts it is zero.

A learner-facing "here is what was filtered" view is **out of scope** and filed.

### D3 — Which L1 gloss

LR gives comma-separated senses (`بلعیدن, خوردن, فرو بردن`); a card front wants
one. Proposal: **`front` carries the first sense; `meaning` carries the full
string.** Nothing is discarded, so a later slice can re-choose without
re-importing. Trancy's `Translation` is split on `;` the same way.

**This rests on an assumption and it is filed as one:** that LR orders senses by
relevance to the captured context. Two records cannot establish that. New known
issue, low, W8f → W13.

Interaction with **#158** (the L1 gloss renders twice on a production card after
reveal): a production card here has `front == first sense` and `meaning == full
string`, so the two are no longer equal by construction, which is the condition
#158's outstanding `split_part` query measures. Named so the query is read
against both populations.

### D4 — `native_language` (#159): the user row wins, and a mismatch refuses the file

`users.native_language` has existed since `001_init_postgres.sql:19` and reads
`fa` / `lt` / `fa` for ids 1 / 2 / 3 (read on production 2026-08-26 under #159).
LR column 11 is the export's own target language.

**The user row wins.** On mismatch the importer **refuses the whole file before
writing anything** and names both values. It is a whole-file property, and a
gloss in a language the learner does not read is noise — S24's own reason for
never auto-sharing Trancy output: *"Operator Trancy exports carry Persian
meanings; User B is Lithuanian."* Failing loud is S15a's rule for exactly this.

This does not close #159, which is about carrying L1 onto the card *face*. It
prevents this slice from making #159 worse.

### D5 — Duplicates: three collisions, three answers

1. **Already in `lexemes`** — not a collision. `lexemes` is a shared dictionary.
   Resolution goes through `resolve_capture_lemma` (D5a ruling 1) — identity
   first, `ensure_lexeme` otherwise, **never `lemmatize`'s suffix step** — and
   the importer and the backfill call the same function.
2. **Already in the ledger** — see D2's ceiling. `known`/`mastered` → skip;
   `seen`/`learning` → import. Additionally the importer **writes the capture to
   the ledger** as `source='tapped'` (rank 2) — a capture *is* a tap. That reuses
   an existing CHECK value; no ledger migration.
3. **Already a card** — skip, and this is the idempotency case. **It does not
   work today.** `create_card`'s `ON CONFLICT (user_id, source_chunk_id,
   card_type)` cannot fire when `source_chunk_id IS NULL`, because Postgres
   treats NULLs as distinct — so a chunk-less card has **no** schema-level
   guarantee and a second run would insert duplicates silently. Migration 015
   adds the partial unique index that restores the second guarantee, and the
   importer anti-joins for the first. `migrate_chunks`' two-independent-
   guarantees property must hold here or it is not the same creator.

**Ruling embedded in that index: one captured card per (learner, lemma, card
type).** A second sighting of a word is not a second card. This binds W13 too,
and it is why it belongs in the schema rather than in the importer.

**And it hands W13 a constraint that must be filed now.** A `UniqueViolation` is
the right outcome for a human-run command that prints it. Through
`POST /video/{id}/save-word` it is a **500 for a learner who tapped a word they
had already saved** — which is not an error, it is the normal case on a second
viewing. **W13's capture path needs an "already saved" response distinct from a
failure**, and the shape of that answer is W13's to choose, not this slice's.
Filed as a known issue with W13 as the target: filed, the route meets a known
constraint; unfiled, it meets a 500 in front of a learner.

### D5a — ESTABLISHED: the anti-join cannot see the nine existing cards

**The concern is confirmed on both halves, from the code, not inferred.**

1. **`migrate_chunks` never sets `lexeme_id`.** The string `lexeme` does not
   occur in `migrate_chunks.py` or `seeding.py` at all. The card spec is built
   from `common` (`migrate_chunks.py:208-217`), which has no `lexeme_id` key, and
   `create_card`'s parameter defaults to `None`. **All 14 production cards carry
   `lexeme_id IS NULL`.**
2. **They all carry `source_chunk_id`** — `common` sets `source_chunk_id=chunk_id`
   unconditionally, for every branch.

So a chunk-derived card fails **both** clauses of the proposed scope
`source_chunk_id IS NULL AND lexeme_id IS NOT NULL`. **`captured_card_keys()` and
`cards_one_captured_card_per_lemma` are blind to every card in the deck today.**

**The uncorrected consequence, stated rather than smoothed:** step 8 would report
**9 imported, 0 skipped_duplicate**, and `--apply` would write **18 cards** — a
second `tier` production card beside card 17, and eight more like it — into a
29-card live deck. The step written as a duplicate test would have been the
thing that created the duplicates.

**The expectation was not adjusted to fit the code.** Two rulings follow, both
**operator-accepted**.

#### ESTABLISHED, second pass — the backfill resolves 7, not 9, and one of the "successes" is wrong

Measured against `data/lexemes.tsv` (15,000 lemmas) and the real
`core.lexicon.normalize.lemmatize`:

| back | in dictionary | `lemmatize()` | verdict |
|---|---|---|---|
| notch, luckily, frustrate, proper, incapable, psychosis, convenient | ✅ | itself | **7 resolve correctly, by identity** |
| **`bootstrap`** | ❌ | `None` | unresolved — no candidates |
| **`tier`** | ❌ | **`ti`** | **resolves to the WRONG lemma** |

**`tier` and `bootstrap` are genuinely absent.** Confirmed — D2's table was right.
So **identity matching resolves 7 of 9**, not 9.

**But the sharper finding is `tier`.** `lemmatize('tier')` does not return `None`.
`tier` is not a known lemma, so step 3's suffix rules strip `-er` and propose
`['ti', 'tie']`; **`ti` is in the seed list** (rank 9,856 — an artefact of an
OpenSubtitles-derived frequency list), so the "a candidate is accepted only if it
is already a known lemma" guard passes. The docstring's promise — *"it can fail to
resolve, but it cannot invent"* — holds **literally** and fails **in effect**:
`ti` was not invented, and it is not what the word means.

**Why that is worse than a miss.** `013_cards.sql:88-89` says `lexeme_id` "is what
`grade_card` writes the ledger from, with `source='review'`". A backfill through
`lemmatize` would point card 17 at `ti`, and every future grade of it would write
ledger evidence for the wrong word — into the one structure CLAUDE.md §5 calls
unrebuildable.

**And it would have looked green.** The importer would make the identical error on
the same input, so `tier` would dedup correctly *because both sides are wrong the
same way* — a guarantee passing over a corrupt value. That is the failure mode
worth naming, not the count.

#### Ruling 1 — identity is the lemma, and `lexeme_id` is backfilled

Provenance does not define a card's target; **the lemma does**. D5.3's approved
ruling already says so, and the backfill is what makes it true of the data rather
than only of rows written after today — the "a guard living only in the code that
creates cards today" failure `013_cards.sql:200-203` warns about.

New command, `retire_chunk_cloze`'s shape exactly — **dry by default, every row
printed whole, the count typed back, no `--yes`**:

```
python -m core.cards.backfill_lexemes            # prints every row and its resolution
python -m core.cards.backfill_lexemes --apply
```

**The backfill and the importer share ONE resolution function**, in
`core.services.cards`, and the asymmetry that produced this defect — D5.1 calling
`ensure_lexeme` while the backfill refused to — is removed rather than patched:

```
resolve_capture_lemma(conn, word):
  1. word is itself a known lemma            → that lexeme      (7 of the 9)
  2. otherwise ensure_lexeme(word)           → origin='grown'   (tier, bootstrap)
  never lemmatize()'s suffix candidates      → never `ti`
```

- **Step 3 of `lemmatize` is deliberately not used**, and its absence is the
  ruling. Suffix stripping exists to fold *inflections* onto a lemma; a capture
  arrives as a dictionary form already, so the step buys nothing here and costs
  `tier → ti`. **`ensure_lexeme` is handed the surface word, never a
  suffix-stripped candidate.**
- Growing two rows is not a cost this pass invents: `lexemes` is explicitly
  growable, `ensure_lexeme` is "the only way `lexemes` grows", and a grown row
  carries `origin='grown'` with a **NULL `freq_rank`**, which migration 010's
  frequency floor (`WHERE freq_rank IS NOT NULL`) already refuses to assume
  known. **The dictionary gains exactly what a capture would have added anyway.**
- **The five reading and fifteen slang backs are phrases**, and a phrase fails
  `ensure_lexeme`'s `GROWABLE = ^[a-z][a-z'-]{0,63}$` on the space alone, so they
  stay NULL automatically. That is a permanent property, not a gap, and it is
  stated so nobody later "fixes" it. Where such a back *is* a single word it
  grows like any other — the rule is the token, not the provenance.
- **It refuses on a collision.** Two chunk-derived cards resolving to the same
  `(user_id, lemma, card_type)` would violate the new index; the pass counts
  those groups **before** it writes anything, and stops with the ids named rather
  than half-applying. Two independent guarantees again: the command refuses on a
  collision it read, the index refuses on one it did not.
- `chunks` is never touched, and neither is any column but `lexeme_id`.

The index therefore drops its `source_chunk_id` clause — see the migration.

**Cost, stated as a cost:** this is a production data write that was not in the
slice prompt. It is named rather than absorbed, and it is the smaller half of the
alternative, which was shipping an idempotency guarantee that does not hold.

#### Ruling 2 — the skip is row-level, not per card type

**Any existing card for this lemma skips the whole row.** Step 8 reads
`9 skipped_duplicate, 0 imported`, and remains a genuine zero-write duplicate
test.

The alternative — skip the nine production cards and create nine *recognition*
cards, which genuinely do not exist — was rejected: it turns a verification run
into a nine-card write, and D5.3's *"Already a card → skip"* reads row-level.

**Its cost, filed:** a word that already has a production card can never gain a
recognition card through import. Filed low → W13, which owns whether a
partially-carded word is topped up.

#### The pre-flight read, before the backfill

```sql
SELECT id, back, lexeme_id, source_chunk_id IS NULL AS captured
FROM cards WHERE card_type='production' ORDER BY id;
```

Expect **14 rows, every `lexeme_id` NULL, every `captured` false.** **If any row
disagrees, the finding above is wrong and this section is rewritten before
anything else proceeds.**

### D6 — What a Trancy card without a sentence looks like

`cards.context_sentence` is nullable, so it is simply absent. Front and back are
D1's minus the sentence: `recognition` front = the word + phonetic, back = the
gloss; `production` front = the gloss, back = the word. **No sentence is
invented.** The card face already renders a missing `context_sentence` — that is
what the fourteen migrated production cards do.

---

## Migration 015 — and the numbering collision

▲ `docs/TASKS-v3-web.md`'s **authoritative** migration table already assigns
**015 to W10**. The slice prompt assumed 015 was free; it is not. No file past
`014` exists, so this is a planning-table renumber, not a schema rewrite.

**W8f takes 015; W10 → 016, W12 → 017, W13a → 018, W14 → 019, W18 → 020**, all
corrected in the authoritative table and in the five affected Build columns **in
the same commit**. This is exactly W4b's precedent and its reason: `db.py`
computes pending as a set difference, so a number taken above everything claimed
would apply *after* 015 on production and *before* it on a fresh database, and
**the schema history stops being replayable**. Renumbering an applied migration
is #49; renumbering an unwritten planning row is bookkeeping (W4a's rule).

`migrations/015_capture.sql`:

```sql
ALTER TABLE cards ADD COLUMN captured_at  TIMESTAMPTZ;   -- when the learner met it
ALTER TABLE cards ADD COLUMN source_title TEXT;          -- LR column 16, verbatim

-- register_source gains a fourth, honest value.
-- 'migration_default' means "v2 had no register concept"; 'operator' claims a
-- human judged this row. Neither is true of an import that makes no model call.
ALTER TABLE cards DROP CONSTRAINT cards_register_source_check;
ALTER TABLE cards ADD  CONSTRAINT cards_register_source_check
    CHECK (register_source IN
           ('migration_default', 'detected', 'operator', 'import_default'));

-- The second idempotency guarantee. See D5.3 and D5a.
--
-- NO `source_chunk_id IS NULL` CLAUSE, and its absence is the whole ruling:
-- identity is the lemma, not the provenance. Scoped to chunk-less rows this
-- index would have been blind to all 14 cards already in the deck, because
-- `migrate_chunks` sets neither `lexeme_id` nor a NULL `source_chunk_id`, and
-- an import would have written a second `tier` card beside card 17.
--
-- `WHERE lexeme_id IS NOT NULL` still excludes the twenty phrase-backed cards
-- (slang and reading), which have no lemma and never will.
CREATE UNIQUE INDEX cards_one_card_per_lemma
    ON cards (user_id, lexeme_id, card_type)
    WHERE lexeme_id IS NOT NULL;
```

**Ordering: the index ships in 015, the backfill runs after it.** The database
then refuses a colliding backfill on its own, independently of the command's own
pre-check.

Positions this file must state in its header, per the conventions 012/013/014
follow:

- **#48 is NOT triggered** — there is no `ALTER TABLE users`, so the paired
  `approved_onboarded_users` recreate is deliberately absent. Stated rather than
  omitted, because #48 has recurred by looking inapplicable.
- **PRODUCT-PRINCIPLES §2, post-011 form** — the rule is to *confirm the keying
  and say so*, not to write the stale "enlarges the eventual migration" clause.
  `cards.user_id → users(id)` already; **this adds no user-keyed table and
  enlarges nothing.**
- **Nothing is seeded here.** Content arrives via the human-run command.
- Plain non-idempotent DDL, no guards, no `schema_version` row.
- `register` stays **NOT NULL with no default** — that absence is the acceptance
  criterion "no card exists without a register tag" and 015 must not weaken it.

**Register for imported cards:** `register='neutral'`,
`register_source='import_default'`. The cost, stated: a slang line captured from
a series would be tagged neutral and become a production card. That is **#126**
already, and TASKS W13's "Register detection on save" is where it is fixed. The
new value is what makes these rows findable in one `WHERE` — the pattern
`user_lexemes.source='assumption'` set for #93.

---

## Flagged, not solved: the licence question

**PRODUCT-PRINCIPLES §3**, whose exact wording is *"licensing is checked before
any third-party data enters the repo, and the answer must hold for a commercial
product, not only for a private one."*

- **The two committed fixtures are clean.** Both records are Gutenberg
  (`gb_20203`, *Autobiography of Benjamin Franklin*) — public domain. §3's check
  is performed, here, with its answer.
- **The path is not.** LR captures from Netflix and YouTube, and a subtitle line
  is copyrighted text. `cards.context_sentence` stores it, and 015 adds
  `source_title` and `captured_at` beside it. Storing that in a personal database
  is one thing; storing it in a product with paying users is another, and the
  schema is being built now.

Filed as a new known issue with a target — **W12/W13**, the slices that make it
real at scale. §3 calls this the "cheap now and expensive later" case exactly.
**Not this slice's to rule on**, and the plan does not rule on it.

---

## Files

**New**

| Path | Purpose |
|---|---|
| `migrations/015_capture.sql` | above |
| `packages/core/cards/exports.py` | **pure.** `parse_language_reactor`, `parse_trancy`, `detect_export_format`, `CaptureRecord`. No DB, no clock, no network. |
| `packages/core/cards/capture.py` | **pure.** `plan_for_capture(record, *, now) -> Plan`, `CAPTURE_CARD_TYPES`. **No frequency constant** — D2 ships no floor, and an unused threshold sitting in the module is an invitation to wire it up. |
| `packages/core/cards/import_vocab.py` | the human-run command. Holds **no SQL**. |
| `packages/core/cards/backfill_lexemes.py` | D5a ruling 1. Resolves `back` → `lexeme_id` on existing cards. Dry by default, refuses on collision. Holds **no SQL**. |
| `tests/test_cards_backfill_lexemes.py` | against a real database |
| `tests/fixtures/vocab_import/languagereactor.csv` | the real LR export, 2 records |
| `tests/fixtures/vocab_import/trancy.csv` | the real Trancy export, 9 rows |
| `tests/test_vocab_exports.py` | parsers against the fixtures |
| `tests/test_cards_capture.py` | the pure planner and the filter |
| `tests/test_cards_import_vocab.py` | the command, against a real database |
| `tests/test_migration_015.py` | in `test_migration_014.py`'s shape |
| `prompts/CC-W8f-vocabulary-import-PLAN.md` | this slice's prompt, archived |

**Modified**

- `packages/core/cards/__init__.py` — `CAPTURE_CARD_TYPES`, `REGISTER_SOURCES` gains `import_default`
- `packages/core/services/cards.py` — `lemmas_with_a_card(conn, user_id)` (the **row-level** anti-join, per D5a ruling 2), `cards_needing_a_lexeme(conn)` and `set_card_lexeme(conn, …)` for the backfill, and `captured_cards_for_user()` for the read-back. SQL lives only here.
- `docs/TASKS-v3-web.md` — the W8f row, the renumbered migration table, five Build columns
- `docs/PRODUCT-PRINCIPLES.md` — nothing; §3's check is recorded in BUILD_PROGRESS
- `BUILD_PROGRESS.md` — the update block

**Not touched:** `apps/bot/handlers/csv_import.py`, `core/services/watch_import.py`,
`core/services/vocab_import.py`. The v2 CSV handler is untouched and dies at W22.
Nothing Telegram.

### The command

```
python -m core.cards.import_vocab --file PATH --user N            # dry: every row printed, nothing written
python -m core.cards.import_vocab --file PATH --user N --apply    # type the count back, then write
```

`retire_chunk_cloze`'s shape exactly: **dry by default, every row printed whole,
the count typed back, no `--yes`**, and it closes by telling the operator to
confirm the counts independently in psql — *a count this command prints about its
own work is not verification of it.*

Format is **detected structurally, never from headers** — the real LR file has
none. Tab-delimited, every record exactly 24 fields, field 0 matching
`^(WORD|PHRASE)\|.+\|[a-z]{2}$` → `language_reactor`. Comma-delimited with the
exact header set `{word, phonetic, translation, date}` → `trancy`. **Exactly one
match, or refuse** — `classify_csv_format`'s own rule: zero or multiple, never
guess.

---

## Tests

Against the committed fixtures, and mirroring the patterns the repo already
enforces:

- Both fixtures parse: LR → **2 records, 24 columns each**; Trancy → **9 rows**.
- **The regression that closes #27**: the v2 path refuses the real LR export
  (`classify_csv_format → None`) and the new parser accepts it. Both asserted, so
  the defect cannot silently return.
- Embedded newlines and doubled quotes survive round-trip; the 3-line wider
  context is not truncated.
- The nine Trancy words parse to exactly W8b's nine, and `tier`'s Translation is
  asserted **byte-for-byte**, leading space included.
- The filter, in its D2 form: `proper` rejected **by the ledger**; `swain`
  (11,886), `psychosis` (14,342), `tier` (NULL) and `bootstrap` (NULL) **all
  accepted**; `devour` accepted. Expected values hardcoded, never derived from
  the function under test (§3 rule 5).
- **`test_a_missing_freq_rank_is_never_a_rejection_reason`** — a lemma with
  `freq_rank IS NULL` imports. This is the regression that holds D2's ruling; the
  first version of this plan failed it by design, so it is written as a negative
  the way `test_locked_is_not_a_storable_state` is.
- **`skipped_too_rare` is zero on every run**, asserted, so a floor cannot be
  reinstated silently.
- The accounting identity holds on every fixture run.
- **A second `--apply` writes nothing** — proven by running it twice, not asserted.
- **The partial unique index actually refuses** a second card for the same
  `(user, lemma, card_type)` (`pytest.raises(psycopg.errors.UniqueViolation)`) —
  the second guarantee proved without the module's anti-join in front. A
  phrase-backed card with `lexeme_id IS NULL` is unaffected.
- **`test_a_chunk_derived_card_is_visible_to_the_anti_join_once_backfilled`** —
  the regression for D5a. Build a card in `migrate_chunks`' exact shape
  (`source_chunk_id` set, `lexeme_id` NULL), run the backfill, then import the
  same lemma and assert **nothing is written**. Without the backfill the same
  test must show the import writing — both directions asserted, so the blindness
  cannot silently return.
- **The backfill refuses on a collision** and names the ids, with `lexeme_id`
  unchanged on every row — proved by seeding two chunk-derived production cards
  whose backs resolve to one lemma.
- **The backfill leaves phrase-backed cards NULL**, asserted as a positive so it
  reads as intended rather than as an oversight.
- **Row-level skip**: a lemma with only a `production` card skips the row and
  creates **no** `recognition` card (D5a ruling 2).
- **`test_tier_never_resolves_to_ti`** — `resolve_capture_lemma` on `tier`
  returns a **grown** lexeme whose lemma is `"tier"`, and the `ti` lexeme
  (rank 9,856) is asserted untouched. Hardcoded, not derived. The companion
  assertion records the defect it guards: `lemmatize("tier") == "ti"` today, so
  if the lemmatiser is ever fixed this test tells the reader why it existed.
- **`test_the_backfill_and_the_importer_resolve_identically`** — both call
  `resolve_capture_lemma`, asserted by source scan, so the asymmetry that caused
  this cannot reappear as two drifting copies.
- **`test_a_phrase_back_is_never_grown`** — a multi-word back leaves `lexemes`
  unchanged, proved by counting rows before and after.
- The wrong count typed back writes nothing; the default is dry and **never
  prompts** (monkeypatch `input` to raise).
- A `native_language` mismatch refuses the file and writes nothing.
- **No model call**: `core.llm` is not imported anywhere in the new modules
  (source scan), and the network guard covers the run.
- `tests/test_core_boundary.py::test_cards_package_is_pure` stays unexempted —
  no SQL in `core/cards/`. #59 remains the only exemption.
- Migration 015: read from `information_schema`/`pg_constraint`, never a
  hand-written column list; `test_the_migration_seeds_nothing`,
  `test_the_migration_touches_no_users_column`,
  `test_the_migration_writes_no_schema_version_row`, and the named-index test so
  it cannot be quietly dropped.
- No wall-clock dependence anywhere (§3 rule 6) — `now` is injected.

Full suite must stay green: **1685 passed / 6 skipped** is the current baseline,
plus the new tests.

---

## Verification

Local, before any server step:

```bash
.venv/bin/python -m pytest -q
```

Then a dry run against the committed fixture, with no database write, to confirm
the printed report and the accounting identity.

### Server steps — for the human to run

Claude Code has no SSH access to this host. `bot` from `/home/bot/english-bot`
unless stated.

1. **Backup**, immediately before the migration: `scripts/backup.sh`
2. `git pull`
3. `.venv/bin/pip install -e packages/core`
4. `.venv/bin/python -m core.db migrate` → **`schema_version` 15**
5. `.venv/bin/python -m core.db status` → `Applied: 001–015, Pending: (none)`
6. **Confirm the `tier` byte-identity before importing anything** —
   this is the evidence for the record, and it is read-only:
   ```bash
   psql english_bot -c "SELECT id, meaning = ' سطح ردیف;  چیدمان در سطوح طبقه‌بندی' AS byte_identical FROM cards WHERE back = 'tier';"
   ```
   Expect one row, `t`. **On `f`, do not stop yet — re-run with `btrim()` on both
   sides:**
   ```bash
   psql english_bot -c "SELECT id, btrim(meaning) = btrim(' سطح ردیف;  چیدمان در سطوح طبقه‌بندی') AS same_content FROM cards WHERE back = 'tier';"
   ```
   Equal after trimming → **the provenance claim holds**, and the whitespace
   difference is recorded as a v2 parser detail. The claim is that this file is
   the source of that card; it does not rest on leading whitespace surviving two
   hops. Still unequal → **that is the finding — record it and stop**, because
   the S24a correction below rests on it.
7. **Confirm the S24a correction** — nine chunks, `frustrate` among them:
   ```bash
   psql english_bot -c "SELECT count(*) FROM chunks WHERE source='vocabulary';"
   psql english_bot -c "SELECT chunk FROM chunks WHERE source='vocabulary' ORDER BY id;"
   ```
   Expect **9**, and the nine words listed above. This is what makes "all nine
   landed, the reply's count was wrong" a measurement rather than a reading.
7a. **Pre-flight read — D5a's premise, before anything writes:**
   ```bash
   psql english_bot -c "SELECT id, back, lexeme_id, source_chunk_id IS NULL AS captured FROM cards WHERE card_type='production' ORDER BY id;"
   ```
   Expect **14 rows, every `lexeme_id` NULL, every `captured` false.** **Any row
   that disagrees means D5a is wrong — stop and report before step 7b.**

7b. **Backfill `lexeme_id`, dry first:**
   ```bash
   .venv/bin/python -m core.cards.backfill_lexemes
   ```
   **Expected, for the nine vocabulary-derived backs — 9 resolved, by two
   different paths, and the split is the check:**

   ```
   identity   7   notch luckily frustrate proper incapable psychosis convenient
   grown      2   tier bootstrap        ← absent from data/lexemes.tsv, added origin='grown'
   ```

   **If `tier` resolves by identity rather than as grown, the suffix step is
   live and it has written `ti` — stop.** That is the specific corruption this
   ruling exists to prevent, and it is invisible in a total.

   **The other 20 cards cannot be predicted offline** — BUILD_PROGRESS does not
   record the slang and reading backs, so the dry run prints each with its
   resolution path and **the operator confirms none is a false resolution before
   `--apply`**. Expect most to be phrases and stay NULL. **0 collisions**; any
   collision line stops the run by design — record the ids.

   Then `--apply` and **type the count back**. Read the result back
   independently, including the two new dictionary rows:
   ```bash
   psql english_bot -c "SELECT lemma, origin, freq_rank FROM lexemes WHERE origin='grown' ORDER BY lemma;"
   ```
   ```bash
   psql english_bot -c "SELECT count(*) FILTER (WHERE lexeme_id IS NOT NULL) AS resolved, count(*) AS total FROM cards;"
   ```

8. **Dry run, Trancy — `--user 3`, and the user number is load-bearing:**
   ```bash
   .venv/bin/python -m core.cards.import_vocab --file trancy.csv --user 3
   ```
   **User 3 is who S24a imported to** — BUILD_PROGRESS line 1053: *"all 14
   production cards belong to user 3."* User 1 is Navid, whose deck is five slang
   recognition cards and nothing else, so against user 1 these nine words are
   largely **new**: the step would fail its own expectation, and on an `--apply`
   would write nine words into the wrong learner's deck.

   **Expect per bucket, not as a total**, so a wrong number names which guarantee
   failed:

   ```
   rows_read              9
   imported               0
   skipped_duplicate      9   ← the anti-join saw the existing cards. Zero here
                              ←   means step 7b did not take — the exact failure
                              ←   D5a was filed for. Stop; do not --apply.
   skipped_already_known  0   ← non-zero means the ledger, not the deck, matched
   skipped_too_rare       0   ← non-zero means a floor was reinstated by accident
   skipped_no_gloss       0
   skipped_no_sentence    0   ← Trancy carries none; see D6, it is not a skip reason
   ```

   **This is the duplicate test, run against real production data rather than a
   synthetic case.** Any deviation is the finding — record it and stop.
9. **Dry run, Language Reactor**, then `--apply` if the report reads correctly.
   Expect **2 rows read, 2 imported, 4 cards** — `swain` imports; there is no
   rarity floor (D2). **The dry-run output belongs in BUILD_PROGRESS before
   `--apply` is run.**
10. **Independent read-back in psql**, not from the command that did the work:
    ```bash
    psql english_bot -c "SELECT card_type, count(*) FROM cards GROUP BY card_type ORDER BY 1;"
    psql english_bot -c "SELECT count(*) FROM cards WHERE register_source='import_default';"
    ```
11. **Re-run `--apply`** → nothing written. Idempotency proved by running it.
12. `sudo systemctl restart english-api` (as root; `exit` back to `bot` after).
    **Never a system-wide service** — `fonderis-worker` shares this host.

---

## BUILD_PROGRESS.md update block

1. **Slice row** `| W8f | Vocabulary import: Language Reactor and Trancy | 🟡 code-complete | 2026-08-26 | … |`
   at line 130, after W8e. **Never ✅.**
2. **Decisions log** — the LR-over-Trancy ruling with its evidence and its
   *assistant-recommended, operator-accepted* authorship; D1–D6 each with its
   reason; the `tier` byte-identity; **the S24a correction**; the migration
   renumber with W4b's replayability reason; the fixtures' Gutenberg licence check.
   **D5a's two rulings and the finding that forced them** — that `migrate_chunks`
   sets no `lexeme_id` and always sets `source_chunk_id`, so the first-drafted
   index was blind to every card in the deck and an "already imported" check
   would have created the duplicates it was written to prevent. Then D5a's own
   first fix reproduced the pattern: a backfill resolving against existing
   lexemes only, blind to `tier` and `bootstrap`. **Found by review, not by a
   gate**, both times.

   **THE PATTERN, NAMED ONCE, BECAUSE THIS IS ITS FOURTH APPEARANCE:** *a
   guarantee evaluated against a set that cannot contain the thing it is about.*
   1. v2 — 161 tests green over handlers called directly, so no test could see
      the dead route (CLAUDE.md §3 rule 1).
   2. W1 — `assert_path_outside_repo`'s test computed its fixture from the same
      broken `repo_root()` it was checking (§3 rule 5).
   3. **W8f draft 1** — the unique index scoped to `source_chunk_id IS NULL`,
      blind to all 14 cards in the deck.
   4. **W8f draft 2** — the backfill scoped to existing lexemes, blind to the
      two words absent from the dictionary.

   **Two of the four are this plan, caught in review on consecutive passes**,
   which is the useful part of recording it: the pattern is not rare and it is
   not a v2 artefact. **Its next mutation is already visible here and is worse
   than blindness** — `tier → ti` is a guarantee that *sees* the row and sees it
   wrongly, and it would have read green because both sides of the comparison
   made the same error. **The check that catches this family is asking what the
   predicate cannot match, not whether it passes.**
   **D2 is recorded as a reversal, with the losing argument kept** — an
   assistant-proposed rank-8000 floor, argued down on two grounds (a NULL rank
   means *unknown*, not *rare*; and a capture is the strongest statement of
   intent the system receives). **Authorship, in the convention's own terms:
   assistant-proposed, assistant-reviewed-against, operator-accepted** — the same
   shape as W8c's five glosses. **The objection came from the reviewing
   assistant, not from the operator**, and recording it as "operator-overruled"
   would put the argument in the wrong mouth. Without this the threshold reads as
   never considered and will be re-proposed.
3. **#27 CLOSES** — the format is known from a real file, and it closes with the
   defect it was filed for finally *measured*: the v2 detector produces 7 headers
   and 9 phantom rows from a 2-record file and refuses it.
4. **New known issues** — the licence flag (medium, → W12/W13); **the capture
   path has no "already saved" answer, so `cards_one_captured_card_per_lemma`
   raises where a route must refuse politely (medium, → W13)**; LR columns
   4/7/12/13/14/20/21/22 unestablished (low); the `.mp3` extension/container
   mismatch (low); the LR sense-ordering assumption in D3 (low); no learner-facing
   view of filtered rows (low); **rarity is recorded but nothing deprioritises a
   rank-14,342 card in scheduling (low, → W10)** — D2's consequence, filed so the
   dropped floor is a deferral with an owner rather than an absence;
   **`migrate_chunks` created 14 cards with no `lexeme_id`, so every capture
   dedup was blind to the whole deck until W8f backfilled it (medium, W7 → closed
   W8f)** — filed and closed in the same slice, because a defect that existed for
   nineteen days and was found by review rather than by a gate is the kind the
   record exists to hold; **a lemma with only a production card can never gain a
   recognition card through import (low, → W13)** — D5a ruling 2's cost;
   **twenty phrase-backed cards keep `lexeme_id` NULL permanently and are
   invisible to capture dedup (low)** — correct, not a gap, filed so it is not
   later "fixed"; **`lemmatize` resolves `tier` to `ti` via its suffix step, and
   the same shape reaches anything absent from the 15,000-lemma seed list
   (medium, W4 → W12)** — see below.

   **The `lemmatize` issue is filed against W4, not W8f, because it is not
   this slice's defect and it is live today.** `core.lexicon.coverage` calls
   `lemmatize` on every transcript token, so `tier` in any text already counts
   as `ti` — and PRD §7.2 selects videos on that coverage number, which is why
   W12 is the target. W8f routes around it and does not fix it: a change to the
   lemmatiser moves every coverage figure this project has recorded, and that is
   its own slice with its own before/after. **Named rather than fixed in
   passing.**
5. **Every open issue carried** — the current table holds **120 non-closed rows**
   and none is dropped. #99's remaining surface is import paths, and this slice
   is one: state explicitly that it generates no context and so cannot inherit
   the bias.
6. **File inventory** — every file above, **including both fixtures**.
7. **Next action** — this slice's checks **plus every earlier unrun check
   reproduced in full**: W8's five content checks (**check 4 PART-RUN and
   BLOCKED ON THE BOOK, with all four questions and its query — it still blocks
   W9 and W10 via #171**; check 2 blocked); W8c's phone checks 2, 3, 4; W8b's two
   phone checks; the one remaining `split_part` read for #158; and the **21
   carried checks** including the struck-with-reason #4. Nothing carried silently.

**Stop when the update block is written. Do not start W9 or W10.**

---

## Out of scope, named rather than absorbed

Audio (column 23 is a string, nothing more) · cloze cards and the whole-word
gapper (#147) · a web import route · register detection · the L1 field on
`CardFace` (#159) · a learner-facing view of filtered rows · **rarity-aware
scheduling, which is where D2's dropped floor properly belongs** · **W13's
"already saved" response** · anything Telegram.
