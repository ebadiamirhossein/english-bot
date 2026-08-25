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
reconstruction from nothing. `tests/test_cards_migration.py` parses this module
and fails the commit that adds a write.

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

    both                     a cloze card and a production card
    cloze_only_no_meaning    no `meaning`, so no production front exists
    production_only_no_gap   the phrase is not locatable in its sentence
    slang_recognition        source='slang', and the operator supplied a gloss
    skipped_slang_no_gloss   source='slang' with no entry in --slang-glosses
    skipped_no_face          neither card is possible

so that `both + cloze_only_no_meaning + production_only_no_gap +
slang_recognition + skipped_slang_no_gloss + skipped_no_face ==
chunks_examined`, for each learner, exactly. That identity is
what makes "nothing was silently lost" checkable rather than asserted, and the
independent verification query in the runbook computes the same sum from the
other side, without importing anything from this module.

Card-level counters run alongside it: `cloze_created` / `production_created` for
what was written, and `already_present` for what a previous run wrote.

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

    built: list[dict] = []
    if gapped is not None:
        # PRD §5 "Cloze-in-context": the mined sentence with the phrase gapped.
        built.append(dict(common, card_type="cloze", front=gapped, back=chunk))
    if meaning is not None:
        # PRD §5 "Production", with the shortfall named in the module docstring:
        # the front is an English gloss because v2 recorded no L1 one. The
        # gapped sentence rides along as the "context hint" §5 asks for, when
        # there is one.
        front = meaning if gapped is None else f"{meaning}\n{gapped}"
        built.append(dict(common, card_type="production", front=front, back=chunk))

    if not built:
        return Plan(chunk_id, user_id, (), "skipped_no_face")
    if gapped is None:
        return Plan(chunk_id, user_id, tuple(built), "production_only_no_gap")
    if meaning is None:
        return Plan(chunk_id, user_id, tuple(built), "cloze_only_no_meaning")
    return Plan(chunk_id, user_id, tuple(built), "both")


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
