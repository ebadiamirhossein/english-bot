"""Launch 2026-09-26, B4: `python -m core.placement.prune` — the operator's
command that removes the two unserved rows W18-R1's reading found.

User action: none — **the operator** runs it on the host, dry then `--apply`
(Next action, the post-deploy block). Every test drives `main()`, the entry
point the command line reaches, against the development database; the typed
confirmation is answered through `input`, as the operator answers it.

The rows are this file's own, written with the service's writer and removed at
teardown. **The development bank must hold nothing else** (it is built on the
host; the Mac only ever runs it dry), and the fixture asserts that.

**RED DEMONSTRATIONS (2026-09-26, a scripted mutation each, `python -B`):**
`delete_unserved_vocabulary` without its `NOT EXISTS` clause →
`test_the_delete_itself_refuses_a_served_row` red (the foreign key refused the
DELETE: an exception, where an empty answer is owed); the served row left in
the deletable list → `test_a_served_row_is_refused_and_kept` red; the dry path deleting and
committing → `test_dry_is_the_default_and_writes_nothing` red; the second-
spelling rule keeping the LATER row → three red, `test_apply_removes_exactly_
the_two` among them (*mustache* went, *moustache* stayed).
"""

from __future__ import annotations

import builtins

import psycopg
import pytest

from core.config import load_settings
from core.placement import prune
from core.services import placement as svc
from tests.support import progress_seed as seed

#: The host's three, at the ranks and tags `data/lexemes.tsv` gives them, plus
#: a word neither rule touches — in the order the draw wrote them.
ROWS = [("mustache", 5655, "B2"), ("moustache", 5894, "B2"),
        ("englishman", 8639, "B1"), ("kettle", 4012, "B1")]


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def bank(db):
    assert db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0] == 0, (
        "the development placement bank holds rows these tests did not write")
    ids = {w: svc.insert_vocabulary(db, w, is_word=True, freq_rank=r, cefr=c)
           for w, r, c in ROWS}
    db.commit()
    yield ids
    db.rollback()
    db.execute("DELETE FROM placement_run_items WHERE bank_id = ANY(%s)", (list(ids.values()),))
    db.execute("DELETE FROM placement_bank WHERE id = ANY(%s)", (list(ids.values()),))
    db.commit()


def _left(db) -> set[str]:
    return {r[0] for r in db.execute(
        "SELECT word FROM placement_bank WHERE section = 'vocabulary'").fetchall()}


def test_dry_is_the_default_and_writes_nothing(db, bank, capsys) -> None:
    assert prune.main([]) == 0
    out = capsys.readouterr().out
    assert "moustache" in out and "second spelling of 'mustache'" in out
    assert "englishman" in out and "written with a capital" in out
    assert "rows to remove: 2 · refused (served): 0" in out
    assert _left(db) == {"mustache", "moustache", "englishman", "kettle"}


def test_apply_removes_exactly_the_two(db, bank, capsys, monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda prompt: "2")
    assert prune.main(["--apply"]) == 0
    assert "deleted: 2 rows" in capsys.readouterr().out
    assert _left(db) == {"mustache", "kettle"}


def test_a_wrong_count_typed_back_deletes_nothing(db, bank, monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda prompt: "3")
    assert prune.main(["--apply"]) == 1
    assert _left(db) == {"mustache", "moustache", "englishman", "kettle"}


@pytest.fixture
def served(db, bank):
    """A learner was shown *moustache* before the prune ran."""
    user = seed.make_learner(db, "W18 prune test").user_id
    run = db.execute("INSERT INTO placement_runs (user_id) VALUES (%s) RETURNING id",
                     (user,)).fetchone()[0]
    db.execute("INSERT INTO placement_run_items (run_id, user_id, bank_id, section, position) "
               "VALUES (%s, %s, %s, 'vocabulary', 0)", (run, user, bank["moustache"]))
    db.commit()
    yield bank["moustache"]
    db.rollback()
    db.execute("DELETE FROM placement_run_items WHERE user_id = %s", (user,))
    db.commit()
    seed.drop_learner(db, user)


def test_a_served_row_is_refused_and_kept(db, bank, served, capsys, monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda prompt: "1")
    assert prune.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "REFUSED — served, kept" in out and "rows to remove: 1 · refused (served): 1" in out
    assert _left(db) == {"mustache", "moustache", "kettle"}


def test_the_delete_itself_refuses_a_served_row(db, bank, served) -> None:
    """The race the print cannot see: a row served AFTER the read. The DELETE
    carries the condition, so it answers with nothing deleted, not an error."""
    assert svc.delete_unserved_vocabulary(db, [served]) == []
    db.commit()
    assert "moustache" in _left(db)
