# W8b — Retire the migrated cloze cards, and record what the probe found · PLAN MODE

Archived per CLAUDE.md §0: `prompts/` records the intent a slice was given, never
its state. `BUILD_PROGRESS.md` is the only record of what was built.

**Mode:** PLAN. This slice deletes rows from production and changes a card
creator — neither is additive and neither is self-contained.

---

## What this slice was

The ruling on what `core.cards.probe_cloze --live` measured on production on
2026-08-25: 14 billed calls, **6 multi-acceptable, 9 `not_recoverable`**, and the
pre-registered prediction of 6–11 multi-acceptable **MET**.

**No migration.** `schema_version` stays at 14; no `.sql` file added or edited.

## The instruction, in the terms it was given

**The prediction is not edited after the fact.** It is recorded as met, alongside
the statement that meeting it did not settle the question. *A pre-registered
prediction constrains honesty about the axis it names and says nothing about an
axis it does not.* The branch rules were written about ambiguity; the dominant
defect is that 9 of 14 cards are not answerable as authored — a different defect,
a different fix, and no branch rule was ever registered for it. W10 registers
predictions of its own, and this was named as the most transferable thing in the
slice.

**The number that decides it is the cross, not either column.** Not-recoverable
{16,20,22,30,34,36,38,40,42} ∪ multi-acceptable {18,28,32,30,40,42} = 12 ids;
2 of 14 sound — cards 24 and 26. *Confirm the arithmetic against the run output
before building on it; if it does not reproduce, that is the finding and the plan
stops there.*

**Three causes, visible in the sentences:** the gapper replaces a substring not a
whole word (`three _____s:`); it gaps whole phrases, which is structural because
a v2 chunk is an idiom; and three cards returned `0 classes`, the W5c arm C
signature — the probe is not blind but deprived.

**The ruling: retire them.** The deck goes 43 → 29, stated as a cost and not as a
cleanup. `recognition` and `production` cards are unaffected; W13 creates real
cloze cards from video lines.

**Two halves, and one without the other is worse than neither.** Without the
creator change, deletion re-satisfies `UNIQUE (user_id, source_chunk_id,
card_type)` and the next `migrate_chunks` run recreates all 14 invisibly.

**The purge:** human-run, dry by default, matching on `card_type` +
`source_chunk_id` — never a date range, never an id list — so a W13 cloze card
has no `source_chunk_id` and is untouchable **by construction, not by timing**.
The count typed back before it deletes; every row printed first. **Check
`card_reviews` before deleting anything: if any of the 14 has a grade against it,
stop and report — the ruling assumes these have never been reviewed, and if that
is false the decision changes and it is not Claude's to re-make.**

**The substring bug is filed, not fixed.** `make_sentence_with_gap` lives in
`core/services/anki.py`, the W22 boundary W8a spent a slice defending. Severity
medium, target W22, with the note that it affects a live learner path.

**The work bias, measured on live learner content for the first time:** 6 of 14.
#99 updated; #57 updated and **not** closed — a sample of one card type is not
the census it asks for.

## What the plan changed, and it was argued rather than done quietly

The prompt asked for `migrate_chunks --purge`, on the grounds that a reader
should not be able to read the creator end to end and never learn the purge
exists. The plan proposed a separate module instead, because `migrate_chunks`
carries a guarantee that it destroys nothing and a deletion path inside it makes
that guarantee read as narrower than it is. **Ruled in the plan's favour on
2026-08-25**, with the surviving half of the objection folded in: the creator's
docstring names `core.cards.retire_chunk_cloze`.

## Four changes folded in at approval

1. `migrate_chunks`' docstring names the purge module.
2. Count the malformed context hints on the 14 production cards that are
   **staying** (`front ~ '_____[a-z]'`) and put the number in #147 — a defect
   live on cards a learner opens tomorrow deserves a count, and zero is worth
   recording too because it bounds how often the bug bites.
3. **Both sound cards are Work-framed** — a *validation set* and a *context
   window* — so the remainder is 2 of 14 on the uniqueness rule and **0 of 14
   once the content rule is applied as well.** Recorded as a finding: the cross
   was computed first, and reading the survivors is what then showed it. It
   removes the last argument for keeping a subset.
4. **A gloss-less chunk now yields zero cards** — permanent, invisible until an
   import brings in chunks without glosses. Recorded in #148 as a constraint the
   import slices inherit rather than as a one-off count.

## Acceptance criteria as given

1. The `card_reviews` query returns 0 for all 14, or the slice stops.
2. `migrate_chunks` creates no `cloze` card from a chunk, asserted by a test,
   with the reason in the module.
3. The purge matches on `card_type` + `source_chunk_id`, never on dates or ids.
4. After the purge: `cards` 29, `cloze` 0, run independently of the command that
   did the work (CLAUDE.md §3 rule 5).
5. A second purge run reports nothing to do.
6. `chunks` still 29.
7. `packages/core/services/anki.py` byte-identical.
8. Suite green, reported split from a baseline of 1664.
9. No migration, no `.sql` file.

**Every server step is an explicit command for the human.** Claude Code has no
SSH access to the production host and is not to be given any.
