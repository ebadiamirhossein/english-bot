"""§A's regression, and §B's retirement. **Both through the service, not mocked.**

**WHY THE SUITE MISSED §A, STATED PLAINLY.** `POST /conversation/open` 500'd on
its first production call and the surface had never once opened — with 21 new
tests green. What those tests exercised:

* `test_conversation_guards.py` — **pure functions with hand-built `Turn`
  objects.** It never touches a database, so no query in the slice is reachable
  from it.
* `test_conversation_metering.py` — **`llm.chat` at the transport.** Real, and
  it proves the token accounting; it calls no service function.
* `test_session_route.py` / `test_web_shell.py` — the **payload shape** and the
  **copy**, both of which were correct.

**SO EVERY TEST WAS ON ONE SIDE OF THE SERVICE AND NONE WAS THROUGH IT.** That
is CLAUDE.md §3 rule 1 — *test through the real entry point* — and rule 4: if you
cannot say which user action a test exercises, it is decoration. The guards suite
is not decoration, but it could not have caught a bad column name and **nothing
claimed otherwise until the 500 said so.**

**THE MISSING TEST IS THE FIRST ONE BELOW: `_topic_sources` against a REAL
`syllabus_units` row, through the service.** It fails on the shipped defect.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("syllabus_units_exist")


def _conn():
    from core.db import connection

    try:
        cm = connection()
    except Exception:  # noqa: BLE001
        pytest.skip("no database configured")
    return cm


def test_topic_sources_reads_the_real_syllabus_and_does_not_raise() -> None:
    """**THE TEST THAT WOULD HAVE FAILED ON THE SHIPPED DEFECT.**

    `su.target_lexemes` does not exist and never did: the candidates live in
    `syllabus_unit_lexemes` and the per-learner list is
    `unit_candidates(unit) - known_lemmas(user)`, computed by
    `syllabus.unit_target_lexemes`.

    **This asserts the KEYS and the TYPES, not the contents.** A learner with an
    empty ledger and a learner mid-unit get different words from the same row —
    that is what PRD §3 means by *personalisation, not deviation* — so asserting
    a particular lemma would be asserting this database's state rather than the
    function's behaviour.

    **AND IT ASSERTS `grammar_target` IS A STRING OR NONE AND NEVER A DICT**,
    because the first draft read the wrong key and would have degraded to None
    on every unit silently, where §A at least raised.
    """
    import psycopg

    from core.services.conversations import _topic_sources

    try:
        with _conn() as conn:
            row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            if row is None:
                pytest.skip("no learner in this database")
            out = _topic_sources(conn, int(row["id"]))
    except psycopg.OperationalError:
        pytest.skip("database not reachable")

    assert set(out) == {"grammar_target", "unit_lexemes", "recent_words"}
    assert out["grammar_target"] is None or isinstance(out["grammar_target"], str)
    assert isinstance(out["unit_lexemes"], list)
    assert all(isinstance(w, str) for w in out["unit_lexemes"])
    assert isinstance(out["recent_words"], list)


def test_the_grammar_target_never_carries_a_murphy_citation() -> None:
    """#164 re-scoped `murphy_units` to an operator note; #171 asserts no
    surface renders it.

    The targets are `{"target": ..., "murphy_units": ...}` in one dict, so
    passing the dict through would have put a Murphy citation into the model's
    context and, from there, potentially onto a screen. **Only `target` is
    taken, and this is the assertion that holds it.**
    """
    import psycopg

    from core.services.conversations import _topic_sources

    try:
        with _conn() as conn:
            row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            if row is None:
                pytest.skip("no learner in this database")
            out = _topic_sources(conn, int(row["id"]))
    except psycopg.OperationalError:
        pytest.skip("database not reachable")

    blob = repr(out)
    assert "murphy" not in blob.lower()


def test_topic_sources_survives_a_learner_with_no_unit_state() -> None:
    """**A thin syllabus must not be a 500 — §A's actual lesson.**

    A learner with no `user_unit_state` row still gets a conversation. **What
    that produces is unit 1's candidate list, not an empty one**, because
    `current_unit` defaults to 1 and nothing is known — and that is correct: a
    learner at the start of the syllabus should draw on the start of it.

    **THE FIRST DRAFT OF THIS TEST ASSERTED `unit_lexemes == []` AND FAILED.
    THE CODE WAS RIGHT AND THE ASSERTION WAS A GUESS**, written from what I
    expected rather than from what `current_unit` documents. Recorded here
    rather than quietly corrected, because it is the same defect as §A one more
    time — reading a behaviour off an assumption instead of off the source — and
    catching it in a test is the cheap place to catch it.

    So what this holds is the thing that actually matters: **it does not
    raise**, and the shape is intact.
    """
    import psycopg

    from core.services.conversations import _topic_sources

    try:
        with _conn() as conn:
            out = _topic_sources(conn, 10_000_000)  # no such learner
    except psycopg.OperationalError:
        pytest.skip("database not reachable")
    assert set(out) == {"grammar_target", "unit_lexemes", "recent_words"}
    assert isinstance(out["unit_lexemes"], list)
    assert out["recent_words"] == []


def test_block_four_offers_no_shadow_control() -> None:
    """**§B, the operator's ruling of 2026-09-05, held by a test.**

    The shadow control is retired from block 4 because #376 measured what the
    instrument cannot see: it catches a word said as a different word and misses
    an inflectional ending, so it tells a learner they said it right when they
    did not.

    **THIS ASSERTS ABSENCE FROM THE PAYLOAD BUILDER'S SOURCE, NOT FROM A LIVE
    SESSION**, so it holds whether or not this database has a shadowable card —
    an assertion that passed because the deck happened to be empty would be
    #345's shape exactly.

    **THE CODE IS NOT DELETED AND THIS TEST DOES NOT ASK IT TO BE.** The
    companion assertion below is what keeps the two halves of the ruling apart.
    """
    from pathlib import Path

    src = Path("packages/core/services/sessions.py").read_text(encoding="utf-8")
    body = src[src.index("def _output_block") : src.index("def _close_block")]
    live = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("#")
    )
    assert 'payload["shadow"]' not in live, (
        "block 4 must not offer the shadow control (operator ruling 2026-09-05, "
        "#376) — the code stays for W17, the payload key does not"
    )


def test_the_shadow_code_is_retired_and_not_deleted() -> None:
    """**Disable, do not delete — #348's precedent, asserted from both sides.**

    Without this, the ruling reads as *remove the shadow surface* and the next
    slice tidies away `speech_attempts`, the Azure door and W17's only signal.
    **W14 is not un-marked and not reopened**; its three criteria were met and
    evidenced, and *retired from the session pending W17* is a different
    statement from *it failed*.
    """
    from pathlib import Path

    for path in (
        "packages/core/services/shadow_score.py",
        "packages/core/speech_api.py",
        "apps/api/routers/shadow.py",
        "apps/web/components/session/shadow.tsx",
        "migrations/024_speech_attempts.sql",
    ):
        assert Path(path).exists(), f"{path} must survive the retirement (#348)"
