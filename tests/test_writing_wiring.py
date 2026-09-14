"""W16a: every gate is actually CALLED on the path a learner's submission takes.

**#402's lesson, applied before the defect rather than after it.** At W13b/6 a
correct filter reached nobody: deleting `capturable`'s call site left all four
of its tests green, because they called the function directly. The tests in
`test_writing_rules.py` prove each gate is right; **these prove each gate is on
the path.** Each one replaces a single gate with a stub that refuses everything,
drives `core.services.writing.correct_submission` end to end against the dev
database, and asserts the refusal took effect.

**RED DEMONSTRATION, ONE PER GATE, BY DELETING THE CALL SITE:** removing
`if not is_self_produced(...)`, `if is_typo(...)`, `if not
explanation_is_clean(...)` and `did_well=opening_line(...)` from
`core.writing.gates.shape` — one at a time — turned exactly the matching test
below red; removing `gates.shape(...)` from `correct_submission` turned all four
red. Recorded in the decisions log.

The model is stubbed at `core.services.writing.chat`; nothing here reaches a
provider.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services import writing
from core.services.users import get_user
from core.writing import gates

TEXT = "Today I go to the dentist in the morning and it was fine after all."

PAYLOAD = {
    "is_english": True,
    "corrections": [
        {
            "you_said": "Today I go to the dentist",
            "correct_form": "Today I went to the dentist",
            "error_type": "verb_tense_past",
            "explanation": "It's already happened, so the verb moves into the past.",
        }
    ],
    "did_well": "You say how the visit turned out, which rounds it off.",
}


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
                           cefr_level, explanation_language_fallback,
                           auth_email, auth_user_id, timezone)
        VALUES (%s, 'W16a Wiring', 'fa', TRUE, 'B1', FALSE, %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, f"w16a-w-{abs(telegram_user_id)}@example.test", str(uuid.uuid4())),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    yield get_user(user_id)
    db.execute("DELETE FROM errors WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


@pytest.fixture(autouse=True)
def model(monkeypatch):
    monkeypatch.setattr(writing, "chat", lambda messages, **kwargs: PAYLOAD)


def _submit(user):
    return writing.correct_submission(
        user, TEXT, day_kind="journal", session_id=None, now=datetime.now(timezone.utc)
    )


def test_the_baseline_keeps_the_correction_and_the_line(learner) -> None:
    """Without it, every refusal below could be passing on a path that keeps nothing."""
    outcome = _submit(learner)
    assert len(outcome.corrections) == 1
    assert outcome.did_well is not None


def test_g1_is_on_the_path(learner, monkeypatch) -> None:
    monkeypatch.setattr(gates, "is_self_produced", lambda *a: False)
    outcome = _submit(learner)
    assert outcome.corrections == () and outcome.written == 0


def test_g2_is_on_the_path(learner, monkeypatch) -> None:
    monkeypatch.setattr(gates, "is_typo", lambda *a: True)
    outcome = _submit(learner)
    assert outcome.corrections == () and outcome.written == 0


def test_the_explanation_gate_is_on_the_path(learner, monkeypatch) -> None:
    monkeypatch.setattr(gates, "explanation_is_clean", lambda *a: False)
    outcome = _submit(learner)
    assert outcome.corrections == () and outcome.written == 0


def test_the_opening_line_gate_is_on_the_path(learner, monkeypatch) -> None:
    monkeypatch.setattr(gates, "opening_line", lambda raw: None)
    assert _submit(learner).did_well is None


# ── W16b: the paragraph's call sites ─────────────────────────────────────────

PARA_TEXT = "It depends of the person, and he miss his family. But he told me it was worth it."
PARA_PAYLOAD = {
    "is_english": True,
    "structure": [{"segments": [{"text": "The turn at ", "quote": False}, {"text": "But he told me", "quote": True}]}],
    "corrections": [{
        "you_said": "It depends of the person", "correct_form": "It depends on the person",
        "error_type": "preposition", "explanation": "Depend takes on in English.", "keep": "to depend on",
    }],
}


#: Thursday 12:00 in Vilnius. **Fixed, not the wall clock**, since finding (c)
#: made the service refuse a paragraph on any other day (§3 rule 6).
THURSDAY = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def _paragraph(user, monkeypatch):
    monkeypatch.setattr(writing, "chat", lambda messages, **kwargs: PARA_PAYLOAD)
    return writing.correct_submission(
        user, PARA_TEXT, day_kind="paragraph", session_id=None, now=THURSDAY
    )


def test_the_day_kind_check_is_on_the_path(learner, monkeypatch) -> None:
    """**Finding (c)'s call site, #402's lesson.** `rules.accepts_day_kind` replaced
    by a stub that refuses everything must stop a journal submission too.
    **Red demonstration:** deleting the check from `correct_submission` turned this red."""
    from core.writing import rules

    monkeypatch.setattr(rules, "accepts_day_kind", lambda kind, local: False)
    with pytest.raises(writing.WrongDayKind):
        _submit(learner)


def test_the_paragraph_baseline_keeps_structure_and_an_offer(learner, monkeypatch) -> None:
    outcome = _paragraph(learner, monkeypatch)
    assert outcome.structure is not None
    assert [o["phrase"] for o in outcome.word_offers] == ["to depend on"]


def test_the_structure_gate_is_on_the_path(learner, monkeypatch) -> None:
    """**Red demonstration:** `structure=structure_of(...)` replaced by the raw
    value in `shape` turned this red."""
    monkeypatch.setattr(gates, "structure_of", lambda raw, submitted: None)
    assert _paragraph(learner, monkeypatch).structure is None


def test_the_offer_rule_is_on_the_path(learner, monkeypatch) -> None:
    """**Red demonstration:** the `is_offerable` check skipped inside
    `offers.select` turned this red. *(This docstring first claimed `offers.select`
    bypassed in `correct_submission` — that mutation cannot turn this test red,
    because it asserts no offers and a bypass also yields none. Found by running it;
    corrected rather than left.)*"""
    from core.writing import offers

    monkeypatch.setattr(offers, "is_offerable", lambda *a, **k: False)
    assert _paragraph(learner, monkeypatch).word_offers == ()
