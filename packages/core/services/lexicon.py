"""Every query against `lexemes` and `user_lexemes`. The only place SQL lives.

`core.lexicon.*` is pure — it tokenises, lemmatises and computes a percentage
without touching a database. This module is the other half: it reads the
ledger, hands the pure code a set of lemmas, and writes back. Keeping the split
is what lets `compute_coverage` be tested without Postgres and what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted
(CLAUDE.md §2, known issue #59 stays the only exemption).

The conflict rule below is generated from `core.lexicon.states` rather than
written out twice. Two hand-maintained copies of an ordering is how a rule
quietly stops meaning what its docstring says.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from psycopg.rows import tuple_row

from core.lexicon.coverage import CoverageReport, compute_coverage
from core.lexicon.normalize import lemmatize, lexeme_rows, tokenize
from core.lexicon.states import (
    AUTHORITATIVE_SOURCES,
    COVERED_STATES,
    MAY_LOWER,
    SOURCE_RANK,
    STATE_RANK,
    validate,
)
from core.services.books import is_word_bank_item

# `errors.source` values that are keyboard-authored, and so are evidence the
# learner PRODUCES these words. `voice` and `diary` are ASR output: CLAUDE.md §5
# bars journaling mishearings, but that guard is upstream and imperfect, and a
# mishearing promoted to `known` is a permanently known word the learner never
# said. A missing row is recoverable; a wrong one is not, so they are dropped
# rather than downgraded — a `seen` row for a word the recogniser invented is
# still a false row, and readings/chunk sentences already supply that signal.
# `capture` is someone else's English by definition and is barred from the
# journal outright; a `capture` row appearing in `errors` is a data defect, and
# `harvest_v2` counts them so the slice can report it rather than swallow it.
PRODUCED_ERROR_SOURCES: tuple[str, ...] = ("quiz", "text", "reading", "conversation")
BARRED_ERROR_SOURCES: tuple[str, ...] = ("capture",)

# A lemma may be grown at runtime only from a form the learner actually
# produced. Numerals, URLs and markup residue are not vocabulary.
GROWABLE = re.compile(r"^[a-z][a-z'-]{0,63}$")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    lemma: str
    state: str
    source: str
    register: str | None = None


@dataclass(frozen=True, slots=True)
class WriteCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> int:
        return self.inserted + self.updated

    def __str__(self) -> str:
        return (
            f"{self.inserted} inserted, {self.updated} updated, "
            f"{self.unchanged} unchanged"
        )


# Every cursor below pins `tuple_row`: the shared pool is opened with
# `dict_row`, a test connection usually is not, and a service that reads by
# position must not depend on which one it was handed.
def _case(column: str) -> str:
    whens = " ".join(f"WHEN '{s}' THEN {r}" for s, r in STATE_RANK.items())
    return f"CASE {column} {whens} END"


def _in_list(sources) -> str:
    return ", ".join(f"'{name}'" for name in sorted(sources))


_AUTHORITATIVE_IN = _in_list(AUTHORITATIVE_SOURCES)
_MAY_LOWER_IN = _in_list(MAY_LOWER)

# The conflict rule, in one place.
#
#   * An AUTHORITATIVE source writes unconditionally. `review` and `placement`
#     observe the learner directly, so they own the state they write and rank
#     does not gate them at all. Rank orders *inferences*; it must not order two
#     direct measurements against each other, and between those the newer one
#     wins. Gating them would discard every FSRS lapse (equal rank) and, worse,
#     would let a monthly placement freeze out the daily reviewer for up to
#     thirty days (lower rank) — W7 would appear to work while changing nothing.
#   * Otherwise a write that **lowers** the state applies only if its source is
#     in MAY_LOWER *and* it ranks at least as high as the row it is overwriting.
#   * Otherwise a write that **raises** the state applies if it ranks at least
#     as high as the row it is overwriting.
#   * A write that changes neither state nor rank direction applies only from a
#     strictly higher rank, which just re-attributes the row.
#
# W4a added the MAY_LOWER clause. Before it, demotion was gated on rank alone,
# and `v2_encountered` at rank 1 therefore outranked the rank-0 frequency floor:
# a passive exposure pulled `known` down to `seen`, so the more a learner had
# used the app the lower their coverage read. Rank measures authority; demotion
# needs evidence of not-knowing, and those are different properties.
#
# The IS DISTINCT FROM guard carries the whole weight of idempotency, since
# nothing else gates an authoritative write: re-running any ingestion fires no
# UPDATE at all, not even `updated_at`, and the table stays byte-identical.
# `register` is coalesced and never overwritten with NULL — a write carrying no
# register signal must not erase a slang tag W13 set.
_CONFLICT = f"""
ON CONFLICT (user_id, lexeme_id) DO UPDATE
   SET state       = EXCLUDED.state,
       source      = EXCLUDED.source,
       source_rank = EXCLUDED.source_rank,
       register    = COALESCE(EXCLUDED.register, user_lexemes.register),
       updated_at  = NOW()
 WHERE (
         EXCLUDED.source IN ({_AUTHORITATIVE_IN})
      OR ({_case('EXCLUDED.state')} < {_case('user_lexemes.state')}
          AND EXCLUDED.source IN ({_MAY_LOWER_IN})
          AND EXCLUDED.source_rank >= user_lexemes.source_rank)
      OR ({_case('EXCLUDED.state')} > {_case('user_lexemes.state')}
          AND EXCLUDED.source_rank >= user_lexemes.source_rank)
      OR ({_case('EXCLUDED.state')} = {_case('user_lexemes.state')}
          AND EXCLUDED.source_rank > user_lexemes.source_rank)
       )
   AND (EXCLUDED.state,
        EXCLUDED.source,
        COALESCE(EXCLUDED.register, user_lexemes.register))
       IS DISTINCT FROM
       (user_lexemes.state, user_lexemes.source, user_lexemes.register)
RETURNING (xmax = 0) AS inserted
"""


def wins(incoming: LedgerEntry, existing: LedgerEntry) -> bool:
    """The conflict rule in Python, for de-duplicating a batch before it is sent.

    One statement may not touch the same row twice, so a batch has to be
    reduced first. Reducing it by a *different* rule than the SQL applies is
    exactly the kind of drift this project keeps paying for, so both are
    asserted equivalent by a test.
    """
    if incoming.source in AUTHORITATIVE_SOURCES:
        return True
    incoming_rank = SOURCE_RANK[incoming.source]
    existing_rank = SOURCE_RANK[existing.source]
    incoming_state = STATE_RANK[incoming.state]
    existing_state = STATE_RANK[existing.state]
    if incoming_state < existing_state:
        return incoming.source in MAY_LOWER and incoming_rank >= existing_rank
    if incoming_state > existing_state:
        return incoming_rank >= existing_rank
    return incoming_rank > existing_rank


def _reduce(entries: Iterable[LedgerEntry]) -> list[LedgerEntry]:
    best: dict[str, LedgerEntry] = {}
    for entry in entries:
        validate(entry.source, entry.state)
        current = best.get(entry.lemma)
        if current is None or wins(entry, current):
            best[entry.lemma] = entry
        elif current.register is None and entry.register is not None:
            best[entry.lemma] = LedgerEntry(
                current.lemma, current.state, current.source, entry.register
            )
    return list(best.values())


# ── lexemes ─────────────────────────────────────────────────────────────────


def upsert_lexemes(conn, rows: Sequence[tuple[str, str, int, int, str]]) -> WriteCounts:
    """Insert or enrich reference rows. **Never deletes.**

    A row absent from the file is left alone, deliberately. A "sync" that
    removed them would cascade through `user_lexemes` and destroy ledger
    history — the one thing in this schema that cannot be rebuilt.

    A previously grown lemma appearing in a later seed file is *enriched*, not
    clobbered: the only columns written are reference metadata that was NULL,
    and `id` — what `user_lexemes` points at — is preserved by the upsert, so
    no ledger row is disturbed. The WHERE means an unchanged row is not
    rewritten at all, so a second run reports `0 inserted, 0 updated`.
    """
    if not rows:
        return WriteCounts()
    lemmas = [r[0] for r in rows]
    pos = [r[1] or None for r in rows]
    ranks = [r[2] for r in rows]
    bands = [r[3] for r in rows]
    cefr = [r[4] or None for r in rows]
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO lexemes (lemma, pos, freq_rank, freq_band, cefr)
            SELECT v.lemma, v.pos, v.freq_rank, v.freq_band, v.cefr
              FROM unnest(%s::text[], %s::text[], %s::integer[],
                          %s::smallint[], %s::text[])
                   AS v(lemma, pos, freq_rank, freq_band, cefr)
            ON CONFLICT (lemma) DO UPDATE
               SET pos       = EXCLUDED.pos,
                   freq_rank = EXCLUDED.freq_rank,
                   freq_band = EXCLUDED.freq_band,
                   cefr      = EXCLUDED.cefr,
                   origin    = 'seed'
             WHERE (lexemes.pos, lexemes.freq_rank, lexemes.freq_band,
                    lexemes.cefr, lexemes.origin)
                   IS DISTINCT FROM
                   (EXCLUDED.pos, EXCLUDED.freq_rank, EXCLUDED.freq_band,
                    EXCLUDED.cefr, 'seed')
            RETURNING (xmax = 0) AS inserted
            """,
            (lemmas, pos, ranks, bands, cefr),
        )
        touched = [row[0] for row in cur.fetchall()]
    inserted = sum(1 for flag in touched if flag)
    return WriteCounts(
        inserted=inserted,
        updated=len(touched) - inserted,
        unchanged=len(rows) - len(touched),
    )


def ensure_lexeme(conn, lemma: str) -> int | None:
    """Add a lemma the seed list does not have, and return its id.

    The only way `lexemes` grows. It is called from an explicit tap — a form
    the learner actually selected in a transcript — after `lemmatize` has
    returned None, never from the guess path. `lemmatize` resolves; this
    creates; keeping them apart is what stops a suffix rule inventing
    vocabulary.

    Returns None for anything that is not a plausible English form.
    """
    normalised = lemma.strip().lower()
    if not GROWABLE.match(normalised):
        return None
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO lexemes (lemma, origin) VALUES (%s, 'grown')
            ON CONFLICT (lemma) DO UPDATE SET lemma = EXCLUDED.lemma
            RETURNING id
            """,
            (normalised,),
        )
        return cur.fetchone()[0]


def lexeme_ids(conn, lemmas: Sequence[str]) -> dict[str, int]:
    if not lemmas:
        return {}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT lemma, id FROM lexemes WHERE lemma = ANY(%s)", (list(lemmas),)
        )
        return {row[0]: row[1] for row in cur.fetchall()}


# ── the ledger ──────────────────────────────────────────────────────────────


def record(conn, user_id: int, entries: Iterable[LedgerEntry]) -> WriteCounts:
    """Write ledger rows under the conflict rule. Idempotent by construction.

    A lemma with no row in `lexemes` is skipped, not created: growth is
    `ensure_lexeme`, and it takes a deliberate caller.
    """
    reduced = _reduce(entries)
    if not reduced:
        return WriteCounts()
    ids = lexeme_ids(conn, [e.lemma for e in reduced])
    payload = [(ids[e.lemma], e) for e in reduced if e.lemma in ids]
    if not payload:
        return WriteCounts(unchanged=len(reduced))
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO user_lexemes
                   (user_id, lexeme_id, state, source, source_rank, register)
            SELECT %s, v.lexeme_id, v.state, v.source, v.source_rank, v.register
              FROM unnest(%s::integer[], %s::text[], %s::text[],
                          %s::smallint[], %s::text[])
                   AS v(lexeme_id, state, source, source_rank, register)
            """
            + _CONFLICT,
            (
                user_id,
                [lexeme_id for lexeme_id, _ in payload],
                [e.state for _, e in payload],
                [e.source for _, e in payload],
                [SOURCE_RANK[e.source] for _, e in payload],
                [e.register for _, e in payload],
            ),
        )
        touched = [row[0] for row in cur.fetchall()]
    inserted = sum(1 for flag in touched if flag)
    return WriteCounts(
        inserted=inserted,
        updated=len(touched) - inserted,
        unchanged=len(reduced) - len(touched),
    )


def known_lemmas(conn, user_id: int) -> frozenset[str]:
    """The covered set — `known` and `mastered` only (PRD §2.1)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT l.lemma
              FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id
             WHERE ul.user_id = %s AND ul.state = ANY(%s)
            """,
            (user_id, sorted(COVERED_STATES)),
        )
        return frozenset(row[0] for row in cur.fetchall())


def ledger(conn, user_id: int) -> dict[str, str]:
    """Every lemma this learner has evidence for, mapped to its state."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT l.lemma, ul.state
              FROM user_lexemes ul JOIN lexemes l ON l.id = ul.lexeme_id
             WHERE ul.user_id = %s
            """,
            (user_id,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def evidenced_known_count(conn, user_id: int) -> int:
    """"Words you know" — evidenced rows only, never the frequency floor.

    PRD §11 promises a real number against streak-day theatre. Counting
    `assumption` rows would open the figure at the floor size before the
    learner has done anything, and its first movement once a placement test
    corrected the assumption would be *downward* — precisely what the guilt ban
    and "raises announced, drops silent" exist to prevent. W19 draws the
    six-month target line on this same basis, or the line means nothing.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM user_lexemes
             WHERE user_id = %s AND state = ANY(%s) AND source <> 'assumption'
            """,
            (user_id, sorted(COVERED_STATES)),
        )
        return cur.fetchone()[0]


def coverage_for(conn, user_id: int, text: str) -> CoverageReport:
    """The number W12 selects on and W13 highlights from."""
    rows = ledger(conn, user_id)
    covered = frozenset(l for l, s in rows.items() if s in COVERED_STATES)
    return compute_coverage(
        text, covered, ledger=rows, vocabulary=frozenset(rows)
    )


# ── seeding the ledger before a placement test exists ───────────────────────


def assume_top_frequency_known(conn, user_id: int, top_n: int) -> WriteCounts:
    """Assume the commonest `top_n` lemmas known, at the weakest source rank.

    Without this every ledger is empty on day one, coverage reads 0% for
    everything, and W12's comprehensible-input band cannot be satisfied by any
    material at all — while W18's placement test, which PRD §9 says seeds the
    ledger, is fourteen slices away.

    Written as `assumption`, rank 0, so any later signal overrides it in either
    direction and the placement test can correct it down to `seen`.

    `freq_rank IS NOT NULL` keeps grown lexemes out: a word rare enough to be
    outside the seed list must never be assumed. Proper nouns do occupy some of
    the floor — the frequency list is lowercased, so `john` sits at rank 548 —
    which means the learner is assumed to know slightly fewer real words than
    `top_n` suggests. That biases the floor conservative, toward material that
    is harder rather than easier, which is the safe direction.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO user_lexemes
                   (user_id, lexeme_id, state, source, source_rank)
            SELECT %s, id, 'known', 'assumption', 0
              FROM lexemes
             WHERE freq_rank IS NOT NULL AND freq_rank <= %s
            """
            + _CONFLICT,
            (user_id, top_n),
        )
        touched = [row[0] for row in cur.fetchall()]
    inserted = sum(1 for flag in touched if flag)
    return WriteCounts(inserted=inserted, updated=len(touched) - inserted)


def onboarded_user_ids(conn) -> list[int]:
    """Who the seed command applies the floor and the harvest to."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT telegram_user_id FROM approved_onboarded_users")
        return [row[0] for row in cur.fetchall()]


# W4a. The rows the W4 harvest demoted out of the frequency floor.
#
# Three conditions, all required, and the middle one does the real work:
#
#   * the row was written by an exposure source — the only ones that could have
#     demoted a floor row under the old rule;
#   * the lemma is inside the floor, `freq_rank <= top_n`. This is exact rather
#     than heuristic: the floor inserts *every* lemma at or above that rank, so
#     a lemma in that band sitting at `v2_encountered`/`v2_studied` can only be
#     an overwritten floor row — the harvest cannot have inserted it fresh;
#   * `first_seen_at` falls inside the window of that learner's surviving
#     `assumption` rows. Belt-and-braces given the condition above, and it
#     matters if the floor is ever run separately from the harvest: `NOW()` is
#     transaction time, so today the floor and the harvest share one timestamp
#     and `first_seen_at` never moves on conflict, which is what makes the
#     window identify the floor's own insert.
#
# `known`/`v2_produced` is deliberately outside the filter. Self-produced
# English is stronger evidence than the floor's hypothesis, and those rows are
# a real gain from the harvest — repairing them would be a second bug.
_DEMOTED_FLOOR_ROWS = """
  FROM user_lexemes ul
  JOIN lexemes l ON l.id = ul.lexeme_id
 WHERE ul.source IN ('v2_encountered', 'v2_studied')
   AND l.freq_rank IS NOT NULL
   AND l.freq_rank <= %s
   AND ul.first_seen_at BETWEEN
         (SELECT MIN(first_seen_at) FROM user_lexemes a
           WHERE a.user_id = ul.user_id AND a.source = 'assumption')
     AND (SELECT MAX(first_seen_at) FROM user_lexemes a
           WHERE a.user_id = ul.user_id AND a.source = 'assumption')
"""


# Printed by `python -m core.lexicon.repair` so the human can confirm the result
# against the database directly rather than trusting the command's own arithmetic.
# It lives here because it is SQL, and SQL lives in services — `core/lexicon/` is
# pure, and a query string sitting there would breach that boundary even though
# nothing executes it.
VERIFICATION_QUERY = """\
SELECT user_id,
       COUNT(*) FILTER (WHERE state IN ('known','mastered')) AS covered,
       COUNT(*) AS total
  FROM user_lexemes GROUP BY 1 ORDER BY 1;"""


def count_demoted_floor_rows(conn, top_n: int) -> list[tuple[int, int]]:
    """Per learner, how many floor lemmas the old rule demoted. Reads nothing else."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT ul.user_id, COUNT(*)" + _DEMOTED_FLOOR_ROWS
            + " GROUP BY ul.user_id ORDER BY ul.user_id",
            (top_n,),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def restore_demoted_floor_rows(conn, top_n: int) -> list[tuple[int, int]]:
    """Put them back to `known`/`assumption`, leaving `first_seen_at` alone.

    The rule change stops this happening again; it cannot undo what is already
    written, because no future write raises them — `v2_encountered` can only
    ever assert `seen`. Idempotent: a second run matches nothing, since the
    rows it repaired now read `assumption` and fall outside the filter.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            UPDATE user_lexemes SET state = 'known',
                                    source = 'assumption',
                                    source_rank = 0,
                                    updated_at = NOW()
             WHERE id IN (SELECT ul.id"""
            + _DEMOTED_FLOOR_ROWS
            + """)
            RETURNING user_id
            """,
            (top_n,),
        )
        repaired: dict[int, int] = {}
        for (user_id,) in cur.fetchall():
            repaired[user_id] = repaired.get(user_id, 0) + 1
    return sorted(repaired.items())


def coverage_totals(conn) -> list[tuple[int, int, int]]:
    """`user_id, covered, total` — the shape the human's verification query has."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT user_id,
                   COUNT(*) FILTER (WHERE state = ANY(%s)) AS covered,
                   COUNT(*) AS total
              FROM user_lexemes GROUP BY 1 ORDER BY 1
            """,
            (sorted(COVERED_STATES),),
        )
        return [tuple(row) for row in cur.fetchall()]


def _lemmas_in(text: str, vocabulary: frozenset[str]) -> set[str]:
    found = set()
    for token in tokenize(text or ""):
        if token.is_numeric or token.is_filler:
            continue
        lemma = lemmatize(token.surface, vocabulary)
        if lemma is not None:
            found.add(lemma)
    return found


def harvest_v2(conn, user_id: int) -> tuple[WriteCounts, int]:
    """Populate the ledger from what v2 already recorded about this learner.

    Real evidence, already in the database, one query per source. Returns the
    write counts and the number of barred `errors` rows encountered — a
    `capture` row in the journal is a pre-existing data defect and is reported
    rather than swallowed.

    SELECT-only against every v2 table. Nothing here updates or deletes one:
    the error journal is the product.
    """
    entries: list[LedgerEntry] = []
    vocabulary: frozenset[str] = frozenset()

    with conn.cursor(row_factory=tuple_row) as cur:
        # Self-produced English. Only `you_said`: `correct_form` is the bot's
        # own wording and is no evidence of what the learner can produce.
        cur.execute(
            "SELECT you_said FROM errors WHERE user_id = %s AND source = ANY(%s)",
            (user_id, list(PRODUCED_ERROR_SOURCES)),
        )
        for (said,) in cur.fetchall():
            for lemma in _lemmas_in(said, vocabulary):
                entries.append(LedgerEntry(lemma, "known", "v2_produced"))

        cur.execute(
            "SELECT COUNT(*) FROM errors WHERE user_id = %s AND source = ANY(%s)",
            (user_id, list(BARRED_ERROR_SOURCES)),
        )
        barred = cur.fetchone()[0]

        # `presented_at` gates BOTH columns, because they are two columns of one
        # row. A fanned-out chunk that was never shown must not contribute its
        # sentence as exposure while its target phrase is correctly excluded —
        # that inverts the signal, crediting exposure that provably did not
        # happen.
        cur.execute(
            """
            SELECT chunk, full_sentence FROM chunks
             WHERE user_id = %s AND presented_at IS NOT NULL
            """,
            (user_id,),
        )
        for chunk, sentence in cur.fetchall():
            for lemma in _lemmas_in(chunk, vocabulary):
                entries.append(LedgerEntry(lemma, "learning", "v2_studied"))
            for lemma in _lemmas_in(sentence, vocabulary):
                entries.append(LedgerEntry(lemma, "seen", "v2_encountered"))

        # Word banks are what `books.dedupe_teachable_items` throws away; for a
        # known-word ledger they are the part that carries vocabulary.
        cur.execute(
            "SELECT target_items FROM book_units WHERE user_id = %s", (user_id,)
        )
        for (items,) in cur.fetchall():
            for item in items or []:
                if isinstance(item, str) and is_word_bank_item(item):
                    for lemma in _lemmas_in(item, vocabulary):
                        entries.append(LedgerEntry(lemma, "learning", "v2_studied"))

        cur.execute("SELECT body FROM readings WHERE user_id = %s", (user_id,))
        for (body,) in cur.fetchall():
            for lemma in _lemmas_in(body, vocabulary):
                entries.append(LedgerEntry(lemma, "seen", "v2_encountered"))

    return record(conn, user_id, entries), barred


def seed_rows_from_file() -> list[tuple[str, str, int, int, str]]:
    """`data/lexemes.tsv`, parsed by the same module coverage lemmatises with."""
    return [tuple(row) for row in lexeme_rows()]


__all__ = [
    "CoverageReport",
    "LedgerEntry",
    "VERIFICATION_QUERY",
    "WriteCounts",
    "assume_top_frequency_known",
    "count_demoted_floor_rows",
    "coverage_for",
    "coverage_totals",
    "ensure_lexeme",
    "evidenced_known_count",
    "harvest_v2",
    "known_lemmas",
    "ledger",
    "onboarded_user_ids",
    "lemmatize",
    "record",
    "restore_demoted_floor_rows",
    "seed_rows_from_file",
    "upsert_lexemes",
    "wins",
]
