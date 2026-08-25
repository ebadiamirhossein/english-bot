"""Every v2 `chunk` becomes cards. Human-run, idempotent, dry by default.

    python -m core.cards.migrate_chunks              # dry run, writes nothing
    python -m core.cards.migrate_chunks --apply
    python -m core.cards.migrate_chunks --apply      # second run writes nothing

**Why this is a module and not SQL inside `013_cards.sql`.** Three reasons, and
the third is the one that decided it. The seeding is a Python computation (the
v2 ladder, the difficulty clamp, py-fsrs' state enum). W4's `core.lexicon.seed`
and W4a's `core.lexicon.repair` are the precedent for a data pass over real
learner rows — dry run, then apply, then apply again. And "run it twice, the
second run writes nothing" is not a testable criterion for a file that
`schema_version` physically cannot run twice: putting the pass in the migration
would make the acceptance criterion unfalsifiable rather than satisfied.

**`chunks` IS NEVER MODIFIED.** No UPDATE, no DELETE, no column write, not even
a flag saying "migrated". Two consequences, both deliberate: the v2 review path
keeps working unchanged until W22, and the migration's own inputs survive, so a
wrong seeding mapping is an UPDATE with a stated formula rather than a
reconstruction from nothing. Held by two tests, on two different instruments:
`tests/test_core_boundary.py::test_cards_package_is_pure` reads this module's
own AST and fails the commit that adds SQL or a driver import, and
`tests/test_cards_migration.py::test_the_migration_never_touches_chunks`
snapshots six `chunks` columns either side of a real `--apply` run. (#145: this
paragraph named the wrong file for the source scan until 2026-08-25. The
guarantee was always real and always held by both; only the reference was wrong,
which is #82's shape — a document describing where something is rather than
where it is.)

---

## No `cloze` card is created from a chunk, and that is a ruling with a cost

**W8b, 2026-08-25.** This pass created a cloze card per gappable chunk from W7
until then. It no longer does, and the 14 it had already created were deleted by
`python -m core.cards.retire_chunk_cloze` — named here because a reader who finds
a creator that stopped making a card type will next ask what happened to the ones
it already made, and that answer should be in front of them rather than in the
record.

`core.cards.probe_cloze --live` measured all 14 on production: **6
multi-acceptable, 9 not answerable as authored, and 2 sound on the uniqueness
rule** — and reading those two showed both to be Work-track content (*validation
set*, *context window*), which CLAUDE.md §4 caps at 20%. **Not one of the
fourteen survived both rules.** Three causes, in the order of how much they
decided it:

1. **A v2 chunk is an idiom, so the gap swallows a whole phrase.** *hidden
   costs*, *add up*, *wear down*. A slot that removes an entire noun or verb
   phrase cannot be reconstructed from the sentence around it. This is
   structural and not a bug: an items cloze gaps one word, and a chunk cloze
   gaps the chunk, which is the whole point of the row. No cue repairs it, and a
   gate at creation would reject nearly all of them.
2. **`make_sentence_with_gap` replaces a substring, not a whole word** — it
   gapped *stage* out of *stages* and left the `s` stranded (`three _____s:`).
   Filed as **#147** and deliberately **not fixed here**: that function lives in
   `core.services.anki`, the v2 Telegram exporter and the S7a chunk-review path,
   live for two learners weekly, and opening it in a slice about the web deck is
   the scope creep CLAUDE.md §8 bans. It dies at W22 with the bot.
3. **Three cards drew no answer from the model at all.** Same signature as W5c's
   arm C on `listening_gap` (#121): the probe is not blind but *deprived*.

**The direction that survives is phrase → meaning.** `recognition` and
`production` cards are unchanged, including the gapped sentence that rides along
as §5's context hint — where the gloss carries the answer, so the hint misleads
rather than blocks. W13 creates real cloze cards from video lines, where the gap
is one word in a sentence the learner actually heard.

**The cost, written as a cost:** the deck goes **43 → 29**, and a chunk with a
gappable sentence but no gloss now produces **no card at all** where it used to
produce a cloze one. That bucket was empty on production the day this shipped
(`cloze_created` 14 = `production_created` 14, so every gappable chunk also had a
gloss), which is a fact about today's rows and not a property of the pass — see
`skipped_no_meaning` below, and **#148**: any path that creates chunks must
guarantee a gloss, or its chunks silently produce nothing.

**This module holds no SQL.** Its two reads are
`core.services.cards.chunks_to_migrate` and `.migrated_card_keys`; SQL lives
only in service functions (CLAUDE.md §2) and #59 stays the only exemption in
this project. What lives here is the decision — which chunk becomes which cards,
and with what seeded state.

**Idempotency has two independent guarantees.** `migrated_card_keys` is
subtracted before anything is planned, *and* migration 013's
`UNIQUE (user_id, source_chunk_id, card_type)` refuses a duplicate even if that
subtraction were wrong. W4a's repair is why there are two: the guarantee you can
demonstrate on the Mac is not always the one that holds on production.

**Every chunk lands in exactly one bucket**, and the counts are printed so the
independent verification query can be reconciled against them:

    production_with_hint     a gloss, and the phrase is locatable in its sentence
    production_no_hint       a gloss, but no gapped sentence to hint with
    skipped_no_meaning       gappable and no gloss — THIS CHUNK USED TO GET A
                             CLOZE CARD AND NOW GETS NOTHING (#148)
    slang_recognition        source='slang', and the operator supplied a gloss
    skipped_slang_no_gloss   source='slang' with no entry in --slang-glosses
    skipped_no_face          no gloss and nothing to gap either

so that `production_with_hint + production_no_hint + skipped_no_meaning +
slang_recognition + skipped_slang_no_gloss + skipped_no_face ==
chunks_examined`, for each learner, exactly. That identity is
what makes "nothing was silently lost" checkable rather than asserted, and the
independent verification query in the runbook computes the same sum from the
other side, without importing anything from this module.

`skipped_no_meaning` and `skipped_no_face` are kept apart although one condition
— no gloss — now decides both. The distinction is the cost measurement: the
first is a chunk this pass used to serve and no longer does, and collapsing them
would leave that number unreadable in the run output.

Card-level counters run alongside it: `production_created` for what was written,
and `already_present` for what a previous run wrote.

**Slang-sourced chunks produce no card, and that was ruled on.** PRD §8.5.4
requires every `informal`/`slang` card to show four things — the line it came
from, the meaning, the neutral equivalent, and who says this to whom — and
migration 013 holds that with a CHECK. A v2 slang chunk (S24's fan-out, marked
`source = 'slang'` by migration 007's convention) carries no neutral equivalent
and no who-says-this, so it cannot satisfy it. A slang card showing the meaning
but not the safe alternative is the card §8.5.4 calls "useless and slightly
dangerous". They are counted, reported, and left for W13's capture, which does
real register detection.

**Every other card is tagged `neutral` with `register_source =
'migration_default'`**, which is a decision with a cost and not an omission —
see `core.cards.MIGRATION_DEFAULT_REGISTER`.

**A stated shortfall.** PRD §5's production card front is "L1 gloss + context
hint", and v2 `chunks` have no L1 gloss at all: `meaning` is a plain-English
gloss. So every migrated production card is *English-gloss → English*, not
*L1 → English*, which is a weaker drill than PRD specifies. It is what the data
supports; W13 creates true L1-gloss production cards on capture. Filed rather
than fudged.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date

from core.cards import (
    MIGRATION_CARD_TYPES,
    MIGRATION_DEFAULT_REGISTER,
)
from core.cards.slang_glosses import SlangGloss, load as load_glosses, lookup
from core.cards.seeding import seed_from_v2
from core.db import connection

# Reused, not reimplemented: this is the same function `core.services.chunks.
# due_chunks` already uses to decide whether a chunk is reviewable at all, so a
# chunk that v2 could gap is a chunk this migration can gap, by construction.
#
# Since W8b its output is a HINT and never a question: no card built here has a
# gap where its answer should be. It is also the function whose substring
# matching is #147 — `three _____s:` — so some production hints are malformed
# even though the gloss beside them carries the answer. Not fixed here: it is
# `core.services.anki`, the live v2 path, and it dies at W22.
from core.services.anki import make_sentence_with_gap

logger = logging.getLogger(__name__)

#: Migration 007's convention for the S24 slang fan-out.
SLANG_SOURCE = "slang"


@dataclass(frozen=True, slots=True)
class Plan:
    """What one chunk becomes. `cards` is empty when it becomes nothing."""

    chunk_id: int
    user_id: int
    cards: tuple[dict, ...]
    bucket: str


def plan_for_chunk(
    row, *, today: date, glosses: dict[str, SlangGloss] | None = None
) -> Plan:
    """Decide one chunk's fate. Pure — no database, no clock beyond `today`.

    Pure so the whole fan-out table is testable without Postgres, which is what
    lets the migration's own rules be asserted against hand-written expectations
    rather than against a second run of itself (CLAUDE.md §3 rule 5).
    """
    chunk_id = int(row["id"])
    user_id = int(row["user_id"])
    chunk = str(row["chunk"])
    full_sentence = row["full_sentence"]
    meaning = (row["meaning"] or "").strip() or None
    source = row["source"]

    state, basis = seed_from_v2(
        times_right=row["times_right"] or 0,
        times_wrong=row["times_wrong"] or 0,
        streak_right=row["streak_right"] or 0,
        next_review=row["next_review"],
        today=today,
    )

    gapped = None
    if full_sentence and str(full_sentence).strip():
        gapped = make_sentence_with_gap(str(full_sentence), chunk)

    common = dict(
        source_chunk_id=chunk_id,
        source_ref=source,
        context_sentence=str(full_sentence) if full_sentence else None,
        meaning=meaning,
        register=MIGRATION_DEFAULT_REGISTER,
        register_source="migration_default",
        state=state,
        seed_basis=basis,
    )

    if source == SLANG_SOURCE:
        return _slang_plan(
            chunk_id,
            user_id,
            chunk=chunk,
            full_sentence=full_sentence,
            common=common,
            glosses=glosses or {},
        )

    if meaning is None:
        # NO CLOZE CARD IS BUILT HERE, and the gloss is now the only face a
        # chunk can produce. See the ruling in the module docstring: a chunk
        # cloze gaps the whole idiom, which is not recoverable from what is left
        # of the sentence around it. `gapped` is still computed above, because
        # the production card's context hint is exactly that string.
        return Plan(
            chunk_id,
            user_id,
            (),
            "skipped_no_meaning" if gapped is not None else "skipped_no_face",
        )

    # PRD §5 "Production", with the shortfall named in the module docstring: the
    # front is an English gloss because v2 recorded no L1 one. The gapped
    # sentence rides along as the "context hint" §5 asks for, when there is one.
    front = meaning if gapped is None else f"{meaning}\n{gapped}"
    card = dict(common, card_type="production", front=front, back=chunk)
    bucket = "production_no_hint" if gapped is None else "production_with_hint"
    return Plan(chunk_id, user_id, (card,), bucket)


def _slang_plan(
    chunk_id: int,
    user_id: int,
    *,
    chunk: str,
    full_sentence,
    common: dict,
    glosses: dict[str, SlangGloss],
) -> Plan:
    """One `recognition` card for a slang chunk the operator has glossed.

    **Recognition and nothing else.** PRD §8.5.2: "`slang` and `informal` cards
    are created as recognition and listening cards only." A cloze card asks the
    learner to produce the phrase into a gap, so it is not a milder form of a
    production card — it is a production card with a sentence around it.
    Migration 013's `cards_receptive_first_until_the_neutral_is_mastered` bars
    all three, so this is enforced by the schema and not only by this function.

    The face is PRD §5's recognition row: the phrase **in its mined sentence**
    on the front, the phrase and its meaning on the back, plus §8.5.4's neutral
    equivalent and who-says-this from the operator's file.

    No gloss, no card. The chunk is counted and reported so the operator can see
    exactly which phrases are still unhandled, rather than discovering a card
    with no safe alternative on a phone.
    """
    gloss = lookup(glosses, chunk)
    if gloss is None:
        return Plan(chunk_id, user_id, (), "skipped_slang_no_gloss")

    sentence = str(full_sentence) if full_sentence else None
    if not sentence or not common.get("meaning"):
        # §8.5.4's CHECK needs the line AND the meaning as well as the two the
        # operator supplied. Refusing here rather than at the INSERT keeps the
        # reason legible in the bucket table.
        return Plan(chunk_id, user_id, (), "skipped_slang_no_gloss")

    card = dict(
        common,
        card_type="recognition",
        front=sentence,
        back=chunk,
        register="slang",
        # `operator`, not `detected`: S24's share flow marked these slang and a
        # person is authoring the safe alternative now. `detected` is W13's
        # word, for a tag a register-detection pass produced from a real line.
        register_source="operator",
        neutral_equivalent=gloss.neutral_equivalent,
        who_says_this=gloss.who_says_this,
    )
    return Plan(chunk_id, user_id, (card,), "slang_recognition")


def run(
    *, apply: bool, today: date, glosses: dict[str, SlangGloss] | None = None
) -> dict[str, Counter]:
    """The pass. Returns per-user counters, keyed by the buckets above.

    A dry run reports exactly what an apply would write, because both take the
    same two queries and the same `plan_for_chunk`; the only difference is
    whether `create_card` is reached.
    """
    per_user: dict[str, Counter] = {}
    with connection() as conn:
        # Both reads go through `core.services.cards`, which is where SQL
        # lives (CLAUDE.md §2). This module decides; it does not query.
        from core.services.cards import chunks_to_migrate, migrated_card_keys

        existing = migrated_card_keys(conn, MIGRATION_CARD_TYPES)
        rows = chunks_to_migrate(conn)

        for row in rows:
            plan = plan_for_chunk(row, today=today, glosses=glosses)
            counts = per_user.setdefault(str(plan.user_id), Counter())
            counts["chunks_examined"] += 1
            counts[plan.bucket] += 1

            for spec in plan.cards:
                card_type = spec["card_type"]
                counts[f"{card_type}_planned"] += 1
                if (plan.chunk_id, card_type) in existing:
                    counts["already_present"] += 1
                    continue
                counts[f"{card_type}_pending"] += 1

                if not apply:
                    continue

                # Lazy import so a dry run needs nothing but the seeding maths.
                from core.services.cards import create_card

                with conn.transaction():
                    card_id = create_card(conn, plan.user_id, **spec)
                # `None` means the UNIQUE caught it — the second, independent
                # idempotency guarantee. It should never fire once `existing`
                # has done its job, and it is counted separately so that if it
                # ever does, the number says so instead of blending in.
                counts[
                    f"{card_type}_created" if card_id is not None
                    else "refused_by_unique"
                ] += 1
    return per_user


def _print(per_user: dict[str, Counter], *, apply: bool) -> None:
    print("APPLY" if apply else "DRY RUN — nothing was written")
    if not per_user:
        print("  (none)")
        return
    for user_id in sorted(per_user, key=int):
        counts = per_user[user_id]
        print(f"  user_id={user_id}")
        for key in sorted(counts):
            print(f"    {key:24s} {counts[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate v2 chunks into FSRS cards. Dry by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the cards (default is a dry run that writes nothing)",
    )
    parser.add_argument(
        "--slang-glosses",
        metavar="PATH",
        help=(
            "TSV of chunk / neutral_equivalent / who_says_this, written by the "
            "operator. Without it every slang chunk is skipped, which on the "
            "2026-08-25 census leaves two of three learners with an empty deck."
        ),
    )
    args = parser.parse_args(argv)

    glosses = None
    if args.slang_glosses:
        # Loaded BEFORE the database is touched, and it refuses the whole file
        # on a malformed row. A gloss file that half-parses produces a deck
        # where some slang cards carry a safe alternative and some do not, and
        # the ones that do not are exactly the rows nobody looked at.
        glosses = load_glosses(args.slang_glosses)
        print(f"{len(glosses)} slang glosses loaded from {args.slang_glosses}")
    else:
        print(
            "No --slang-glosses given: every slang chunk will be skipped. "
            "See core.cards.slang_glosses for why that is not the default "
            "outcome anyone wants."
        )

    per_user = run(apply=args.apply, today=date.today(), glosses=glosses)
    _print(per_user, apply=args.apply)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
