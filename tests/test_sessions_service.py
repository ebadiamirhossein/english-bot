"""W10: the daily session's service layer.

**The two things here that no other test in the suite can see:**

1. **Whose date `sessions.date` is.** The learner's, from `users.timezone`.
   Migration 016's partial UNIQUE enforces one row per date and *cannot tell you
   the date was computed wrongly*, so the only place that convention is
   observable is a pair of requests either side of local midnight.

2. **That `empty` and `unavailable` never collapse.** A block that ran and found
   nothing, and a block that could not be built, are different facts. A learner
   told *nothing's due, go watch something* because a query fell over has been
   lied to in a way that looks identical to the truth on a screen.

Time is injected everywhere and `datetime.now()` is called nowhere below, so
nothing here can start failing on a calendar boundary (CLAUDE.md §3 rule 6).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.sessions import BLOCK_KINDS, DAILY_TASK_TYPE
from core.sessions.blocks import (
    Block,
    BlockError,
    assemble,
    breakdown_of,
    first_open_block,
    stored_state,
    visible_target,
    visible_targets,
)
from core.services import cards as cards_svc
from core.services import sessions as svc

VILNIUS = "Europe/Vilnius"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W10 Learner', 'fa', TRUE, 'B1', %s, %s, %s)
        RETURNING id
        """,
        (
            telegram_user_id,
            f"w10-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
            VILNIUS,
        ),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    yield user_id
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


# ── pure: the block shape ───────────────────────────────────────────────────


def _five(**over) -> dict:
    payloads = {kind: ("empty", {}) for kind in BLOCK_KINDS}
    payloads.update(over)
    return payloads


def test_the_five_blocks_are_prd_4_1s_five_in_order() -> None:
    blocks = assemble(_five())
    assert [b.kind for b in blocks] == list(BLOCK_KINDS)
    assert [b.n for b in blocks] == [1, 2, 3, 4, 5]


def test_a_missing_block_is_an_error_not_a_four_block_session() -> None:
    """The absence of a block and an empty block are different facts, and a
    learner can only ever see one of them."""
    with pytest.raises(BlockError, match="no payload"):
        assemble({kind: ("empty", {}) for kind in BLOCK_KINDS[:4]})


def test_a_block_number_cannot_disagree_with_its_kind() -> None:
    with pytest.raises(BlockError, match="block 1 cannot be"):
        Block(n=1, kind="close", state="empty")


def test_an_empty_block_may_not_carry_a_payload() -> None:
    """The two states collapsing by accident is exactly what this slice
    prevents, so the shape refuses it rather than the renderer ignoring it."""
    with pytest.raises(BlockError, match="carries a payload"):
        Block(n=2, kind="input", state="empty", payload={"cards": [1]})
    # `done` keeps its payload: a finished review block still shows what it was.
    assert Block(n=1, kind="review", state="done", payload={"cards": []})


def test_the_runner_opens_on_the_first_ready_block() -> None:
    blocks = assemble(
        _five(review=("done", {}), focus=("ready", {"can_do": "x"}))
    )
    assert first_open_block(blocks) == 3


def test_empty_and_unavailable_are_both_skipped_and_only_here() -> None:
    """The one place the two are treated alike, and it is stated as such: a
    learner should not be parked on a block with nothing to do in it for
    either reason. Everywhere else they say different things."""
    assert first_open_block(assemble(_five())) == 5
    assert (
        first_open_block(assemble(_five(review=("unavailable", {})))) == 5
    )


def test_the_breakdown_is_keyed_on_kind_not_on_number() -> None:
    """A stored breakdown outlives the deploy that wrote it, and a number would
    silently re-point at a different block if PRD §4.1's order ever changed."""
    blocks = assemble(_five(review=("done", {})))
    assert breakdown_of(blocks)["review"] == "done"
    assert "1" not in breakdown_of(blocks)


def test_an_unrecognised_stored_state_is_read_as_nothing_stored() -> None:
    """A breakdown from an older deploy, or hand-edited, must not stop a
    learner opening their session."""
    assert stored_state({"review": "finished"}, "review") is None
    assert stored_state("not a dict", "review") is None
    assert stored_state({"review": "done"}, "review") == "done"


# ── #171: the citation is dropped at the serialisation seam ─────────────────


class _Target:
    def __init__(self, target: str, murphy_units: str | None) -> None:
        self.target = target
        self.murphy_units = murphy_units


def test_a_grammar_target_reaches_a_learner_without_its_citation() -> None:
    """#171 as extended by #183, asserted where the dict is BUILT.

    `tests/test_no_murphy_reaches_a_learner.py` scans every rendering surface;
    this is the other half — a payload that never carries the field cannot have
    it rendered by a surface nobody has written yet.
    """
    out = visible_target(_Target("must and can't", "38"))
    assert out == {"target": "must and can't"}
    assert "murphy_units" not in out


def test_the_projection_names_what_travels_rather_than_deleting_what_does_not() -> None:
    """A second operator-only field added to `GrammarTarget` later must be
    withheld by DEFAULT, not leaked until someone remembers to delete it."""
    target = _Target("third conditional", "38-39")
    target.operator_note = "some later field"  # type: ignore[attr-defined]
    assert visible_target(target) == {"target": "third conditional"}


def test_a_target_with_no_text_is_refused(_ignored=None) -> None:
    with pytest.raises(BlockError, match="no text"):
        visible_targets([_Target("   ", None)])


# ── whose date it is ────────────────────────────────────────────────────────


def test_the_session_date_is_the_learners_local_date(db, learner) -> None:
    """23:30 UTC on the 25th is 02:30 Vilnius on the 26th — and the row is the
    26th, because `sessions.date` means the learner's day for every one of the
    eleven other task types too."""
    utc_evening = datetime(2026, 8, 25, 23, 30, tzinfo=timezone.utc)
    session = svc.today(learner, now=utc_evening)
    assert session is not None
    assert session.date.isoformat() == "2026-08-26"


def test_two_requests_either_side_of_local_midnight_make_two_sessions(
    db, learner
) -> None:
    """The boundary the partial UNIQUE cannot check for you.

    21:50 UTC and 22:10 UTC on the same UTC day are 00:50 and 01:10 Vilnius on
    consecutive Vilnius days in August (UTC+3).
    """
    before = datetime(2026, 8, 25, 20, 50, tzinfo=timezone.utc)
    after = datetime(2026, 8, 25, 21, 10, tzinfo=timezone.utc)
    first = svc.today(learner, now=before)
    second = svc.today(learner, now=after)
    assert first is not None and second is not None
    assert first.date != second.date
    assert (second.date - first.date) == timedelta(days=1)
    assert first.id != second.id


def test_two_requests_either_side_of_utc_midnight_share_one_session(
    db, learner
) -> None:
    """The direction that would have been wrong under a UTC day.

    23:50 and 00:10 UTC straddle a UTC midnight and sit inside one Vilnius
    evening — 02:50 and 03:10 on the 26th. One session, not two.
    """
    before = datetime(2026, 8, 25, 23, 50, tzinfo=timezone.utc)
    after = datetime(2026, 8, 26, 0, 10, tzinfo=timezone.utc)
    first = svc.today(learner, now=before)
    second = svc.today(learner, now=after)
    assert first is not None and second is not None
    assert first.date == second.date == datetime(2026, 8, 26).date()
    assert first.id == second.id


def test_opening_the_session_twice_creates_one_row(db, learner) -> None:
    now = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)
    svc.today(learner, now=now)
    svc.today(learner, now=now)
    count = db.execute(
        "SELECT count(*) FROM sessions WHERE user_id = %s AND task_type = %s",
        (learner, DAILY_TASK_TYPE),
    ).fetchone()[0]
    assert count == 1


def test_the_worker_and_a_learner_cannot_make_two_rows(db, learner) -> None:
    """`assign_daily` pre-creating tomorrow, then the learner opening it."""
    now = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)
    local = svc.local_today(VILNIUS, now)
    svc.ensure_daily_session(learner, local, now=now)
    session = svc.today(learner, now=now)
    assert session is not None
    count = db.execute(
        "SELECT count(*) FROM sessions WHERE user_id = %s AND task_type = %s",
        (learner, DAILY_TASK_TYPE),
    ).fetchone()[0]
    assert count == 1


def test_an_unknown_user_gets_no_session(db) -> None:
    assert svc.today(-1, now=datetime(2026, 8, 26, tzinfo=timezone.utc)) is None


# ── what the blocks say ─────────────────────────────────────────────────────


NOW = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def _blocks(session) -> dict:
    return {b.kind: b for b in session.blocks}


def test_an_empty_deck_makes_block_one_empty_and_not_unavailable(db, learner) -> None:
    session = svc.today(learner, now=NOW)
    assert _blocks(session)["review"].state == "empty"


def test_a_due_card_makes_block_one_ready(db, learner) -> None:
    cards_svc.create_card(
        db,
        learner,
        card_type="production",
        front="to eat quickly",
        back="devour",
        register="neutral",
        register_source="import_default",
        meaning="to eat quickly",
        state=cards_svc.CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=NOW - timedelta(days=1),
            last_review=NOW - timedelta(days=11),
            lapses=0,
            reps=4,
        ),
    )
    db.commit()
    block = _blocks(svc.today(learner, now=NOW))["review"]
    assert block.state == "ready"
    assert [c["back"] for c in block.payload["cards"]] == ["devour"]
    # #157 travels on the wire so the client holds no copy of the table.
    assert block.payload["cards"][0]["typed"] is True


def test_block_two_is_empty_because_the_video_engine_does_not_exist(
    db, learner
) -> None:
    assert _blocks(svc.today(learner, now=NOW))["input"].state == "empty"


def test_block_three_carries_labels_a_null_lesson_and_no_items(db, learner) -> None:
    """A unit with no stored lesson still serves `lesson: None`.

    **Kept unchanged by W10b, and that is the point.** Generation is human-run
    (#196), so most units have no lesson and `None` still has to mean "no lesson
    yet" rather than "this shape has no lessons". The same NULL is served for a
    stored lesson below the current `LESSON_VERSION`, which the service refuses.
    """
    block = _blocks(svc.today(learner, now=NOW))["focus"]
    assert block.state == "ready"
    assert block.payload["unit_number"] == 1
    assert block.payload["can_do"]
    assert block.payload["lesson"] is None
    assert block.payload["items"] == []
    assert block.payload["grammar_targets"]
    for target in block.payload["grammar_targets"]:
        assert set(target) == {"target"}


def test_block_three_serves_a_stored_lesson(db, learner) -> None:
    """**W10b fills the field W10 named.** #182 reaching a screen.

    The one change to `_focus_block`, exercised through the same service call a
    learner's session makes -- not by reading the dict back out of the function
    that built it.
    """
    import json as _json
    from pathlib import Path as _Path

    from core.lessons import LESSON_VERSION
    from core.lessons.schema import parse_lesson

    fixture = _Path(__file__).parent / "fixtures" / "lessons" / "specimen.json"
    lesson = parse_lesson(_json.loads(fixture.read_text()))
    payload = lesson.model_dump(mode="json")
    db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
    db.execute(
        "INSERT INTO grammar_lessons (unit_number, sections, diagrams, "
        "verification, lesson_version) VALUES (1, %s, %s, %s, %s)",
        (
            _json.dumps(payload["sections"]),
            _json.dumps(payload["diagrams"]),
            _json.dumps({"verdict": "passed"}),
            LESSON_VERSION,
        ),
    )
    db.commit()
    try:
        block = _blocks(svc.today(learner, now=NOW))["focus"]
        assert block.state == "ready"
        assert block.payload["lesson"] is not None
        served = block.payload["lesson"]
        assert len(served["sections"]) == 4

        # The lesson's sections and the block's labels name the same targets, in
        # the same order, so the disclosure headers and the sections line up.
        assert [s["target"] for s in served["sections"]] == [
            t["target"] for t in block.payload["grammar_targets"]
        ]

        # #171 holds at this seam too: a lesson carries no citation and cannot,
        # because nothing in its schema has anywhere to put one.
        assert "murphy" not in _json.dumps(served).lower()
    finally:
        db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        db.commit()


def test_a_stale_lesson_leaves_block_three_saying_it_is_on_its_way(db, learner) -> None:
    """A row below `LESSON_VERSION` must not reach a learner as teaching.

    It still satisfies every CHECK in migration 017 -- the constraint cannot see
    the version -- so this is the only place the refusal is observable.
    """
    import json as _json
    from pathlib import Path as _Path

    from core.lessons import LESSON_VERSION
    from core.lessons.schema import parse_lesson

    fixture = _Path(__file__).parent / "fixtures" / "lessons" / "specimen.json"
    payload = parse_lesson(_json.loads(fixture.read_text())).model_dump(mode="json")
    db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
    db.execute(
        "INSERT INTO grammar_lessons (unit_number, sections, diagrams, "
        "verification, lesson_version) VALUES (1, %s, %s, %s, %s)",
        (
            _json.dumps(payload["sections"]),
            _json.dumps(payload["diagrams"]),
            _json.dumps({"verdict": "passed"}),
            LESSON_VERSION - 1,
        ),
    )
    db.commit()
    try:
        block = _blocks(svc.today(learner, now=NOW))["focus"]
        assert block.payload["lesson"] is None
    finally:
        db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        db.commit()


def test_block_four_carries_the_day_kind_and_nothing_else(db, learner) -> None:
    """**W16a. The two tests that stood here were REPLACED, not deleted silently.**

    They read `test_block_four_carries_the_units_written_task_only` (asserting
    `mode == "write"` and a non-empty `task`) and
    `test_block_four_shows_the_same_task_tomorrow` (W10's stated cost of #188).
    **W16a removed `task`, `unit_number` and `mode` from the payload because
    nothing rendered them** — design `1c` draws no task text — so both asserted
    fields that no longer exist. The day's task lives on `/write`.
    """
    block = _blocks(svc.today(learner, now=NOW))["output"]
    assert block.state == "ready"
    assert block.payload == {"day_kind": "journal"}


def test_block_four_is_the_paragraph_on_thursday_and_the_journal_otherwise(db, learner) -> None:
    """**W16b inverted W16a's `test_block_four_is_a_journal_on_every_day_of_a_week`**
    (quoted, #82). NOW is Wednesday 2026-08-26 at 09:00 UTC, so offset 1 is the
    learner's Thursday in Vilnius."""
    kinds = [
        _blocks(svc.today(learner, now=NOW + timedelta(days=offset)))["output"].payload["day_kind"]
        for offset in range(7)
    ]
    assert kinds == ["journal", "paragraph", "journal", "journal", "journal", "journal", "journal"]


def test_block_four_is_done_only_from_an_english_submission_for_this_session(db, learner) -> None:
    """Ruling 1, at the service. **Red demonstration:** deleting the `output`
    branch from `_derive_done` turned this red.

    Rows are inserted directly because this test is about the derivation; the
    route that writes them is tested end to end in `test_writing_route.py`.
    """
    session = svc.today(learner, now=NOW)
    assert _blocks(session)["output"].state == "ready"

    db.execute(
        """
        INSERT INTO writing_submissions
            (user_id, session_id, day_kind, local_date, is_english,
             llm_input_tokens, llm_output_tokens,
             llm_cache_creation_input_tokens, llm_cache_read_input_tokens)
        VALUES (%s, %s, 'journal', %s, FALSE, 1, 1, 0, 0)
        """,
        (learner, session.id, session.date),
    )
    db.commit()
    assert _blocks(svc.today(learner, now=NOW))["output"].state == "ready"

    db.execute(
        """
        INSERT INTO writing_submissions
            (user_id, session_id, day_kind, local_date, is_english,
             llm_input_tokens, llm_output_tokens,
             llm_cache_creation_input_tokens, llm_cache_read_input_tokens)
        VALUES (%s, NULL, 'journal', %s, TRUE, 1, 1, 0, 0)
        """,
        (learner, session.date),
    )
    db.commit()
    assert _blocks(svc.today(learner, now=NOW))["output"].state == "ready"

    db.execute(
        """
        INSERT INTO writing_submissions
            (user_id, session_id, day_kind, local_date, is_english,
             llm_input_tokens, llm_output_tokens,
             llm_cache_creation_input_tokens, llm_cache_read_input_tokens)
        VALUES (%s, %s, 'journal', %s, TRUE, 1, 1, 0, 0)
        """,
        (learner, session.id, session.date),
    )
    db.commit()
    assert _blocks(svc.today(learner, now=NOW))["output"].state == "done"


def test_block_five_counts_what_happened_and_writes_no_xp(db, learner) -> None:
    session = svc.today(learner, now=NOW)
    assert _blocks(session)["close"].payload["cards_reviewed"] == 0
    xp = db.execute(
        "SELECT xp FROM sessions WHERE id = %s", (session.id,)
    ).fetchone()[0]
    assert xp is None


# ── the two states that must never collapse ─────────────────────────────────


def test_a_failing_block_is_unavailable_and_never_empty(
    db, learner, monkeypatch
) -> None:
    """**The assertion this whole slice is arranged around.**

    A block whose builder raises must NOT read as "nothing to do". A learner
    told *nothing's due, go watch something* because a query fell over has been
    lied to, and on the screen the lie is indistinguishable from the truth.

    **This test was written because the guard did not hold without it.** The
    separation was demonstrated by collapsing `unavailable` into `empty` inside
    `_build_block` — and the suite stayed green, because every other test here
    exercises the two states through the pure block shape and none of them ever
    made a builder fail. A green test over an unreachable path proves nothing
    (CLAUDE.md §3 rule 4); this is the reachable one.
    """

    def _boom(*_args, **_kwargs):
        raise RuntimeError("the deck query fell over")

    monkeypatch.setattr(svc, "_review_block", _boom)
    session = svc.today(learner, now=NOW)
    review = _blocks(session)["review"]

    assert review.state == "unavailable"
    assert review.state != "empty"
    assert review.payload == {}


def test_one_failing_block_does_not_take_the_session_down(
    db, learner, monkeypatch
) -> None:
    """The other four are still worth having. A failure of the ROUTE is an HTTP
    error and produces neither state — that is asserted in
    `tests/test_session_route.py`."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("the deck query fell over")

    monkeypatch.setattr(svc, "_review_block", _boom)
    session = svc.today(learner, now=NOW)

    assert session is not None
    assert len(session.blocks) == 5
    assert _blocks(session)["focus"].state == "ready"
    assert _blocks(session)["output"].state == "ready"


def test_a_failed_unit_read_makes_both_its_blocks_unavailable(
    db, learner, monkeypatch
) -> None:
    """Blocks 3 and 4 share one unit read, and a read that FAILED is
    `unavailable` for both — where a unit that is simply not seeded is `empty`
    for both. Two facts from one query, kept apart."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("the syllabus read fell over")

    monkeypatch.setattr(svc, "_current_unit_row", _boom)
    session = svc.today(learner, now=NOW)

    assert _blocks(session)["focus"].state == "unavailable"
    assert _blocks(session)["output"].state == "unavailable"
    # And the deck is untouched by it.
    assert _blocks(session)["review"].state == "empty"


def test_an_unseeded_unit_is_empty_and_not_unavailable(
    db, learner, monkeypatch
) -> None:
    """The other half of the same pair: a successful read that found no unit."""
    monkeypatch.setattr(svc, "_current_unit_row", lambda *_a, **_k: None)
    session = svc.today(learner, now=NOW)

    assert _blocks(session)["focus"].state == "empty"
    assert _blocks(session)["output"].state == "empty"


# ── resume ──────────────────────────────────────────────────────────────────









def _card(db, learner, **over) -> int:
    spec = dict(
        card_type="production",
        front="to eat quickly",
        back="devour",
        register="neutral",
        register_source="import_default",
        meaning="to eat quickly",
        state=cards_svc.CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=NOW - timedelta(days=1),
            last_review=NOW - timedelta(days=11),
            lapses=0,
            reps=4,
        ),
    )
    spec.update(over)
    card_id = cards_svc.create_card(db, learner, **spec)
    db.commit()
    return card_id


def test_a_typed_answer_folds_through_the_existing_seam(db, learner) -> None:
    """`equivalence_key`, and no second normaliser. Capitalisation and edge
    punctuation fold; a different word does not."""
    card_id = _card(db, learner)
    assert cards_svc.attempt_card(learner, card_id, text="Devour.") is True
    assert cards_svc.attempt_card(learner, card_id, text="  devour  ") is True
    assert cards_svc.attempt_card(learner, card_id, text="eat") is False


def test_a_recognition_card_takes_no_typed_answer(db, learner) -> None:
    """#157's exemption, and it is principled rather than a carve-out: a
    recognition card's answer is a MEANING, and `equivalence_key` folds variants
    of a known answer — it cannot judge whether a paraphrase is the same
    definition. Grading wording would fail a learner for being right in
    different words (CLAUDE.md §4)."""
    card_id = _card(db, learner, card_type="recognition", front="devour", back="to eat quickly")
    assert cards_svc.attempt_card(learner, card_id, text="to eat quickly") is False


def test_a_typed_answer_is_stored_with_a_verdict_recomputed_here(db, learner) -> None:
    """The client never carries the verdict back (#108's shape)."""
    card_id = _card(db, learner)
    cards_svc.grade_card(
        learner, card_id, rating=3, now=NOW, typed_response="Devour"
    )
    row = db.execute(
        "SELECT typed_response, typed_matched FROM card_reviews "
        "WHERE card_id = %s",
        (card_id,),
    ).fetchone()
    assert row[0] == "Devour"
    assert row[1] is True


def test_a_grade_with_no_typed_answer_stores_both_as_null(db, learner) -> None:
    card_id = _card(db, learner)
    cards_svc.grade_card(learner, card_id, rating=3, now=NOW)
    row = db.execute(
        "SELECT typed_response, typed_matched FROM card_reviews WHERE card_id = %s",
        (card_id,),
    ).fetchone()
    assert row == (None, None)


def test_a_typed_string_on_an_exempt_card_type_is_discarded(db, learner) -> None:
    """A client that sent one anyway is asking for a judgement this service is
    not allowed to make."""
    card_id = _card(db, learner, card_type="recognition", front="devour", back="to eat quickly")
    cards_svc.grade_card(
        learner, card_id, rating=3, now=NOW, typed_response="to eat quickly"
    )
    row = db.execute(
        "SELECT typed_response, typed_matched FROM card_reviews WHERE card_id = %s",
        (card_id,),
    ).fetchone()
    assert row == (None, None)


def test_a_grade_inside_the_session_carries_its_session_id(db, learner) -> None:
    session = svc.today(learner, now=NOW)
    card_id = _card(db, learner)
    cards_svc.grade_card(
        learner, card_id, rating=3, now=NOW, session_id=session.id
    )
    stored = db.execute(
        "SELECT session_id FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert stored == session.id


def test_the_close_block_counts_the_sessions_own_reviews(db, learner) -> None:
    session = svc.today(learner, now=NOW)
    card_id = _card(db, learner)
    cards_svc.grade_card(learner, card_id, rating=3, now=NOW, session_id=session.id)
    assert (
        _blocks(svc.today(learner, now=NOW))["close"].payload["cards_reviewed"] == 1
    )


# ── #159 ────────────────────────────────────────────────────────────────────


def test_the_learners_l1_reaches_the_session_envelope(db, learner) -> None:
    assert svc.today(learner, now=NOW).l1_language == "fa"


def test_the_l1_rides_on_the_queue_envelope_once(db, learner) -> None:
    _card(db, learner)
    queue = cards_svc.review_queue(learner, now=NOW)
    assert queue.l1_language == "fa"
    # Once per response, never once per card.
    assert all("l1_language" not in c.face() for c in queue.cards)


# ── #258: the manual path is gone; these are what survive of its tests ──────


def test_a_done_block_stays_done_when_its_builder_would_now_say_empty(db, learner):
    """**W10's property, re-expressed against the automatic path.**

    It was `test_a_completed_block_stays_completed_across_a_reopen` and drove the
    manual `complete_block`. The property is unchanged and matters more now: a
    learner who graded every due card must not see block 1 reopen because the
    live builder finds nothing left to serve.
    """
    card_id = _card(db, learner)
    first = svc.today(learner, now=NOW)
    review = next(b for b in first.blocks if b.kind == "review")
    assert review.state == "ready"

    cards_svc.grade_card(learner, card_id, rating=3, now=NOW, session_id=first.id)
    done = svc.today(learner, now=NOW)
    assert next(b for b in done.blocks if b.kind == "review").state == "done"

    # Nothing is due any more, so the live builder would say `empty`.
    again = svc.today(learner, now=NOW + timedelta(minutes=5))
    assert next(b for b in again.blocks if b.kind == "review").state == "done"


def test_the_session_cannot_complete_while_output_cannot_self_report(db, learner):
    """**The honest consequence of the ruling, pinned rather than discovered.**

    `sessions.completed` requires all five blocks `done`. `input` serves nothing
    until W12/W13 and is `empty`; `output` hands the learner to `POST /correct`,
    which records no `session_id`, so nothing can mark it answered. **So
    `completed` stays FALSE and `minutes` is never computed** — and that is why
    #259 is NARROWED by this ruling and not repaired: `count_active_days` filters
    `completed = TRUE`, which a daily session still cannot reach.

    Written as a test so the day `POST /correct` learns about sessions, this
    fails and someone reads the reason rather than rediscovering it.
    """
    card_id = _card(db, learner)
    first = svc.today(learner, now=NOW)
    cards_svc.grade_card(learner, card_id, rating=3, now=NOW, session_id=first.id)
    svc.today(learner, now=NOW)

    row = db.execute(
        "SELECT completed, minutes FROM sessions WHERE id = %s", (first.id,)
    ).fetchone()
    assert row[0] is False, "output cannot self-report, so the session cannot end"
    assert row[1] is None, "and minutes is only computed on a completed session"

