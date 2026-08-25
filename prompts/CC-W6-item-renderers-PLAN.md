# W6 — Item renderers · PLAN MODE

Produce a plan. **Write no code, create no files, change nothing.** End your turn
with the plan and wait for written approval.

---

## 0. Read before you plan

**Documents:** `CLAUDE.md` · `BUILD_PROGRESS.md` (all of it, including the Next
action block and the known-issues table) · `docs/PRODUCT-PRINCIPLES.md` ·
`docs/TASKS-v3-web.md` (the W6 row, the W7 and W10 rows, the authoritative
migration table, and the eight standing rules) · `docs/PRD-v3-web.md` §4.3, §4.6
and §5 · `docs/ARCHITECTURE-v3-web.md` §4, §6 and §10.

**Then read the tree, because the documents lag it (known issue #82).** At
minimum:

- `packages/core/items/` — every module: `__init__.py`, `schema.py`,
  `projection.py`, `grading.py`, `checks.py`, `naturalness.py`, `repair.py`,
  `gates.py`, `verify.py`
- `packages/core/services/items.py` · `migrations/012_items.sql`
- `apps/api/main.py`, `deps.py`, `routers/`, `schemas/`
- `apps/web/app/`, `apps/web/components/`, `apps/web/lib/`, `apps/web/README.md`
- `tests/test_items_*.py`, `tests/test_migration_012.py`, `tests/test_web_shell.py`
- `tests/fixtures/items/valid.json`, `invalid.json`, `probe_only.json`

**Where a document and the tree disagree, the tree wins and the plan says so
explicitly**, naming the document and the line. This has happened more than once
in this project; do not quietly reconcile it.

---

## 1. Mode

`docs/TASKS-v3-web.md` lists W6 as **AGENT**. It is being run as **PLAN** on the
human's instruction, because W6 is the slice that fixes three contracts spanning
Python and TypeScript, and because it is the first slice whose output a human can
actually look at. Record the deviation in the decisions log with that reason.
This is not a #49-class problem — the Mode column is not the authoritative
migration table — but it is a departure from a written row and is not to be left
unrecorded.

---

## 2. What W6 is

The eleven item types rendered in `apps/web`, answerable on a phone, graded
correctly, with feedback and an explanation panel. Plus whatever API surface that
requires, and whatever test infrastructure makes the frontend genuinely covered
for the first time.

## 3. What W6 is not — the scope fence

Do not build, and say so in the plan if the design starts to want any of them:

- the session runner, block progress, resume, `GET /session/today` (**W10**)
- `assign_daily`, item generation, any worker job (**W10**)
- FSRS, cards, the reviewer (**W7**)
- the skill map, syllabus units (**W8/W9**)
- speech scoring, Azure, pronunciation (**W14**)
- any Telegram surface, ever (`PRODUCT-PRINCIPLES.md` §1)

If the slice needs something outside this fence, **name it and stop** rather than
widening (CLAUDE.md §8).

---

## 4. The three inherited contracts

These came out of W5 and W5a. They are the reason this is a PLAN slice. For each
one the plan must state **the structural mechanism** — something that fails a
test or makes the wrong thing unwritable — not a convention, a comment, or a
reviewer's attention.

### 4.1 Everything learner-visible goes through `visible_projection`

`packages/core/items/projection.py` is the single learner-visible serialiser. If
W6 writes a second one — in a router, in a pydantic response model, or in
TypeScript — then the blind-solver probe stops describing what a learner actually
sees, and **every number downstream stays green while the gate silently measures
the wrong artefact**. This is the hardest-flagged cross-slice contract in W5 and
the one most likely to be broken by accident, because a renderer that needs one
more field is a one-line change in a router.

The plan must answer: what makes a second serialiser fail? Candidate layers,
which are not alternatives to each other — state which you take, what each
catches, and what each does not:

- the service function returns a projection object and **never** the full item
  row, so the route physically cannot leak the answer (capability, not
  discipline);
- a parse test in the shape of W5's `test_exactly_one_module_writes_an_item` —
  exactly one module constructs an item response;
- an ASGI-level leak test, per type: the canonical answer and every accepted
  variant appear nowhere in the response body. `tests/test_items_projection.py`
  asserts this at the projection; the route is where a second serialiser would
  appear, so the assertion has to exist there too;
- a committed fixture of the eleven projections, produced by Python and consumed
  by the renderer tests, so a renderer that reads a field the projection does not
  carry fails on the TypeScript side and a projection change that breaks a
  renderer fails on the Python side. If you take this, say how the file is kept
  from drifting (a test that regenerates and compares, not a note in a README).

Also state **how W10 inherits this rather than building its own.** W10 hydrates
five blocks of items into `GET /session/today`; if W6's projection path is not
the one W10 will reach for, W6 has solved this for one slice only.

### 4.2 Render from `RESPONSE_MODE`, not from the type

`core.items.RESPONSE_MODE` (tap / typed / spoken) exists because W5 built it for
exactly this. There is to be no eleven-way switch in the input or grading path.

There is a tension to resolve explicitly, not silently: the W6 task row says
*"one React component per item type"*, and this says render from the response
mode. The obvious resolution is that **presentation** is per type and
**answering** is per response mode — eleven presentation components over three
answer components — but say it, name the file layout, and state the rule a
reviewer can apply: which paths may branch on type and which may not.

### 4.3 Typed answers are graded by `grade_text` and nothing else

`core/items/grading.py`'s fold is shared by the uniqueness gate and the grader.
W5's own note: if the two drift, an item passes the gate and is then ungradable —
the learner types the identical string and is marked wrong. This is the third
fold in the tree and it is pinned by assertion rather than by an import; do not
add a fourth in TypeScript.

Consequences the plan must state:

- **all grading is server-side.** No normalisation, folding, casefolding,
  punctuation stripping or answer comparison anywhere in `apps/web`. "Instant
  feedback" is one network round trip, not an optimistic client-side check —
  optimistic grading is a second definition of "the answer" by another name.
- How is the absence of TS comparison enforced? `tests/test_web_shell.py`
  already scans `apps/web` source and already strips comments before scanning.
  Extending it is the cheap structural answer; say whether you take it.
- **The phone keyboard is a second grader.** Answer inputs need
  `autocapitalize="off"`, `autocorrect="off"`, `spellcheck={false}` and a
  ≥16px font (iOS zooms below that). Autocorrect silently repairing a learner's
  spelling before it is graded is a teaching bug, not a cosmetic one, and the
  acceptance criterion *"typed items never require punctuation or capitalisation
  to match"* is about `fold` being permissive — not about the keyboard fixing
  things first.

---

## 5. Questions the plan must answer

Each one gets an answer **and its reason**. "Reasonable either way" is not an
answer; pick, and say why.

1. **The single-serialiser mechanism** — §4.1 above, including the W10
   inheritance question.
2. **Component decomposition** — §4.2 above: the layout, and the rule for which
   paths may branch on type.
3. **Grading and the keyboard** — §4.3 above, including how the TS scan is
   enforced.
4. **Routes.** Which routes does W6 add? `ARCHITECTURE-v3-web.md` §6 lists
   `POST /items/{id}/answer`; there is no read route for a single item, because
   hydration was assumed to arrive with W10. Name what you add, why it is the
   minimum, and how it will not be superseded by a second thing at W10. State
   `def` vs `async def` per standing rule 6, and say whether the answer route
   touches `llm.py` or `speech.py` at all — it should not.
5. **The error journal — the sharpest question in the slice.** `errors.source`
   was widened at 012 to include `item`. State precisely which response modes
   write to `errors` and which do not. The default is conservative: a tapped
   wrong option is a *selection*, not self-produced English; an ASR mishearing is
   explicitly banned by CLAUDE.md §5; a typed answer is the only candidate, and
   even there say what counts. **A wrong row is permanent damage; a missing one
   is recoverable.** If anything writes, standing rule 2 requires an integration
   test through the real route, through the ASGI transport. Confirm separately
   that nothing in W6 harvests into the lexicon — W5 deliberately excluded
   `item` from the harvest allow-list, and the classification is machine-checked.
6. **`item_attempts`' six unread columns.** W5 shipped `latency_ms`,
   `cue_shown`, `chosen_option`, `grade`, `graded_by`, `audio_seconds` with no
   reader, arguing that the months of history in between are gone permanently if
   they are added later. **W6 is the first slice that can write any of them.**
   State which W6 populates, which stay NULL and why. A column that is still NULL
   after W6 has lost the argument that justified it, and that should be visible
   in the record rather than discovered at W7.
7. **How does a human see eleven items on a phone?** `items` is empty by design
   until W10's `assign_daily` — the record says so plainly, and if a learner sees
   anything different after W5 something is wrong. So the human check that this
   whole slice turns on has no data. Solve it, under these constraints:
   `insert_item`'s refusal of a non-`ok` report is **not** to be weakened; no
   `status` column is to be added (W5 rejected it with reasons); a billed
   generation run is **not** an acceptance criterion (CLAUDE.md §5b) though a
   human-run command is allowed, as W5's `--live` was. Two candidate routes to
   weigh, or a better third:
   (a) a dev-only, human-run command that runs the **real** validator over the
   eleven committed fixtures and inserts what passes — genuine validation
   records, genuine route, and as a by-product **the first real accept-rate
   datum**, which the W10 row says nobody has;
   (b) rendering fixtures in the browser with no database — which verifies the
   renderers and **not** the projection or route contract, and is therefore
   exactly the trap W5a named: a verifier that measures something other than what
   it reports on.
   Say what each option licenses and what it does not.
8. **Audio and spoken types.** `dictation` and `listening_gap` need audio
   delivered to the browser; `speak_repeat` and `speak_answer` need audio
   captured from it and scored. Read the tree for what exists — TTS delivery,
   caching, any `/speech` route — rather than assuming. Speech scoring is W14
   (migration 018). If the acceptance criterion *"all 11 types render and grade
   correctly on a phone"* cannot be met as written for the spoken types, **say
   so and propose the split; do not quietly restate the criterion** (CLAUDE.md §3
   rule 7). The human rules on it, not the plan.
9. **The explanation panel and its Murphy reference.** Where does the text come
   from? Check whether `items` carries an explanation or a Murphy reference at
   all; Murphy units live in v2's `book_units` and the syllabus arrives at W8. If
   there is no source today, the panel renders what exists, the gap is **filed
   with a target**, and nothing is invented. The explanation is **never generated
   at answer time** — that is a billed call in the request path, and the whole
   pre-validation design exists so a session opens in under a second.
10. **Vitest (#67).** The record says the count of frontend logic invisible to
    the Python suite reached three at W3, and that *"the next slice that adds
    frontend logic should treat Vitest as due rather than deferred."* W6 is that
    slice, eleven times over. State the scope: what Vitest covers that a source
    scan cannot (rendering, tapping, the typed-input path, the feedback state
    machine), what stays in the Python suite, how a human runs both, and what
    happens to #67 — closed, narrowed, or carried with a reason.
11. **No-guilt copy, extended to the renderers.** CLAUDE.md §4 requires the
    banned-phrase test to cover every user-facing string, backend **and**
    frontend. Eleven components' worth of wrong-answer feedback is the highest-
    risk copy in the app so far. Say how the scan reaches every `.tsx`, and hold
    the W1b palette decision: **no red anywhere.**
12. **No migration.** 013 belongs to W7 in the authoritative table. W6 takes
    none; `schema_version` stays at **12**, and the BUILD_PROGRESS entry says so
    explicitly so a later reader does not go hunting for an 013 that never
    existed — the same note W5a wrote for the same reason. If the design turns
    out to need schema, **stop and report it**; do not improvise a number that
    collides with W7.
13. **`PRODUCT-PRINCIPLES.md` §2 and §3.** W6 is not expected to add a user-keyed
    table — confirm it does not. Flag anything introduced that is global and
    should be per-user, or per-user and could be computed.
14. **#80 — an empty `NEXT_PUBLIC_API_URL` silently produces a broken build.**
    This is a frontend slice touching the API client. Say whether W6 fixes it or
    carries it, with a reason either way.

---

## 6. Constraints that are not open for trade

- `packages/core` imports no web framework; SQL lives only in service functions;
  a route parses, authorises, calls **one** service function, serialises.
- No browser storage. `localStorage` is permitted in exactly one file under one
  key (`"theme"`); `sessionStorage` is banned outright. Item state lives in React
  state.
- Every route writing to the journal has an integration test through the ASGI
  transport — never a direct service call.
- A test must not derive its expected value from the function under test, and
  must not depend on wall-clock date.
- A green test over an unreachable path proves nothing. For every test proposed,
  be able to state which user action it exercises.
- The acceptance bar is never quietly lowered. If a number cannot be met, report
  the number and the reason and stop.
- Claude Code has **no SSH access** to the production host and is never to be
  given any. Every server step is written as an explicit command for the human to
  run, and no server action is an acceptance criterion this slice can satisfy on
  its own.
- Deployment sequence, settled: backup → pull → `pip install -e packages/core` →
  migrate → restart. Not re-argued.
- The production host is shared with `fonderis-worker`. No broad upgrades, no
  reboots, no Caddy rewrite, no destructive Postgres command without naming the
  exact database.

---

## 7. Acceptance criteria

Propose the criteria in the plan. Start from the task row and add the contract
criteria; sharpen the wording where it is loose, never loosen it.

From `docs/TASKS-v3-web.md`:

> All 11 types render and grade correctly on a phone; typed items never require
> punctuation or capitalisation to match.

Plus, at minimum:

- a test that fails if a second learner-visible serialiser exists;
- a per-type leak assertion at the HTTP boundary, not only at the projection;
- a test that fails if answer comparison appears in TypeScript;
- the eleven types rendering from the committed projections, exercised by a real
  test runner rather than a source scan;
- the no-guilt scan covering every `.tsx`;
- suite green, with the current baseline (**1275 passing / 0 failing**) stated in
  the plan and held.

**Write each criterion so that what verifies it measures the thing it reports
on.** W5a's lesson cost a slice: a harness that sampled twice and reported once
produced a coincidence, not an observation, and it wore the costume of a bug in
the code under test. Any criterion phrased as "the renderer shows X" must be
checked against the artefact the learner actually receives.

---

## 8. Human checks — they matter more in this slice than in any so far

The last four slices found their real bugs in a live check rather than in the
suite. W6 is the first slice where a human can look at the output, so propose the
checks deliberately rather than as a formality. At minimum:

- each of the eleven types opened on a real phone, answered, and the feedback
  read — from the real route against real rows, not a mocked page;
- a typed answer submitted with wrong capitalisation and trailing punctuation,
  on the phone's own keyboard with autocorrect live, marked correct;
- one-handed tap reachability, and no layout shift when the keyboard opens;
- the wrong-answer path read for guilt copy, by a person, in the app.

Say what each check would catch that no test can.

---

## 9. Deployment steps for the human

Write them as explicit copy-paste commands: the backup, the pull, the editable
install, the "no migration" confirmation (`core.db status` still reading
`Applied: 001–012, Pending: (none)`), the service restart, and whatever the
Vercel side needs. State what evidence each step should produce, so the record
can carry an evidenced result rather than a report.

---

## 10. `BUILD_PROGRESS.md` update block

The plan must include the **exact** update block implementation will write:

1. **Slice row** — W6 at 🟡 with the date and a one-line note. **Never ✅.** That
   column is the human's.
2. **Decisions log** — every decision with its reason, including the PLAN-mode
   deviation, the answers to §5, and anything considered and rejected. Write down
   *why*: months later the what is obvious from the code and the why is not.
3. **Known issues** — new ones with severity and slice; every open one carried.
   Anything found and not filed does not exist. "It belongs to a later slice" is
   a reason to file it **with a target**, never a reason not to file it.
4. **File inventory** — every new file with its purpose.
5. **Next action** — W6's human checks **plus every earlier check still unrun**,
   named individually. Nothing drops off for being old. Currently carried, and to
   be reproduced unless it has actually been run:
   - the hand-checked coverage number (unrun since W4 — the one that matters);
   - the 20-item Life sample (W5's own check; belongs to the first `assign_daily`
     run at W10, and is listed as such rather than as runnable today);
   - `/stats` in Telegram on the restructured bot (W1's, the last of that pair);
   - the four Telegram explanation paths — `/diary`, voice, `/capture`, a
     `/talk` close-out — deprioritised on 2026-08-24, not declined;
   - the S25 pre-flight counts from production;
   - #44, evening reading, until a real Mon/Wed/Fri delivery lands;
   - S8, the shared group and its seven checks;
   - the entire v2 desk-check list, unchanged.

---

## 11. What the plan should look like

Ordered sections, each decision with its reason, the file-by-file change list,
the test list with the user action each test exercises, the acceptance criteria,
the human checks, the deployment commands, and the update block. Mark clearly
anything you are unsure about or that contradicts a document — **raise it once,
plainly, and let the human rule on it.**

Then stop.
