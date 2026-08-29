"""Block 3's payload under the pacing ruling. **Pure: no database, no route.**

`_focus_block` is handed a unit, a lesson and a section index and asked what the
learner sees. The three states it must keep apart are the point of the file:

    lesson None            -> "the explanation is on its way"   (most units)
    index < len(sections)  -> that one section open
    index >= len(sections) -> PRACTICE ONLY: no new teaching, no repeat

**The third and the first must never render the same line.** That is
`BLOCK_STATES`' own `empty`-versus-`unavailable` reasoning one level in: telling
a learner *the explanation is on its way* about teaching they have already
finished is a lie the screen cannot distinguish from the truth.
"""

from __future__ import annotations

import pytest

from core.services.sessions import _focus_block


class _Unit:
    unit_number = 1
    can_do = "I can tell a friend what I did yesterday."
    grammar_targets = ({"target": "past simple"}, {"target": "time linkers"})


class _Section:
    def __init__(self, target: str) -> None:
        self.target = target


class _Lesson:
    def __init__(self, n: int) -> None:
        self.sections = tuple(_Section(f"t{i}") for i in range(n))

    def model_dump(self, **_):
        return {"unit_number": 1, "sections": [{"target": s.target} for s in self.sections]}


@pytest.fixture
def four_sections(monkeypatch):
    from core.services import lessons as lessons_service

    monkeypatch.setattr(lessons_service, "for_unit", lambda unit_number: _Lesson(4))


@pytest.fixture
def no_lesson(monkeypatch):
    from core.services import lessons as lessons_service

    monkeypatch.setattr(lessons_service, "for_unit", lambda unit_number: None)


@pytest.fixture(autouse=True)
def no_items(monkeypatch):
    from core.services import items as items_service

    monkeypatch.setattr(items_service, "focus_items", lambda *a, **k: [])


def _payload(section_index):
    state, payload = _focus_block(_Unit(), 1, section_index=section_index)
    assert state == "ready"
    return payload


def test_day_one_opens_the_first_section(four_sections) -> None:
    payload = _payload(0)
    assert payload["lesson_section"] == 0
    assert payload["teaching_complete"] is False


def test_day_three_opens_the_third_section(four_sections) -> None:
    assert _payload(2)["lesson_section"] == 2


def test_when_the_sections_run_out_block_three_shows_practice_only(
    four_sections,
) -> None:
    """**No new teaching AND no repeated section** -- the ruling's two clauses,
    one each. Repeating the last section is the behaviour it names and forbids.
    """
    payload = _payload(4)
    assert payload["teaching_complete"] is True
    assert payload["lesson_section"] is None, "no section is opened, none repeated"
    assert payload["lesson"] is not None, "the sections stay REACHABLE behind labels"


def test_no_lesson_and_teaching_complete_are_different_payloads(
    four_sections, no_lesson
) -> None:
    """The two states a learner could otherwise be shown one line for."""
    from core.services import lessons as lessons_service

    lessons_service.for_unit = lambda unit_number: None
    absent = _payload(0)
    assert absent["lesson"] is None
    assert absent["teaching_complete"] is False
    assert absent["lesson_section"] is None

    lessons_service.for_unit = lambda unit_number: _Lesson(4)
    finished = _payload(9)
    assert finished["lesson"] is not None
    assert finished["teaching_complete"] is True
    assert finished["lesson_section"] is None

    assert (absent["lesson"] is None) != (finished["lesson"] is None), (
        "a client must be able to tell 'no teaching exists' from 'you have "
        "finished the teaching' -- if these payloads ever match, it cannot"
    )


def test_a_unit_with_no_lesson_is_unchanged_from_w10(no_lesson) -> None:
    """Most units have no lesson and will for a long time. The pre-W11 screen --
    four bare labels and the line saying the explanation is on its way -- must
    render exactly as it did. **A regression here is the conditional rendering
    being wrong in the direction nobody looks.**"""
    payload = _payload(3)
    assert payload["lesson"] is None
    assert payload["lesson_section"] is None
    assert payload["teaching_complete"] is False
    assert payload["can_do"] == _Unit.can_do
    assert payload["grammar_targets"] == [
        {"target": "past simple"}, {"target": "time linkers"}
    ]


def test_a_missing_index_falls_back_to_the_first_section(four_sections) -> None:
    """`section_index=None` is the pre-W11 shape and the failure shape: if the
    entry write or the counter raised, `today()` logs it and carries on with
    None, and block 3 must still open a section rather than showing nothing."""
    assert _payload(None)["lesson_section"] == 0
