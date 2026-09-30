"""W33 (B): the journal's other notes and its natural version — the gates, no database.

**WHAT THE OPERATOR ASKED FOR (2026-09-30):** the daily *two that matter most*
stays the default; under it, *Show all notes* (spelling, capitals, smaller
grammar) and *Natural version* (the whole entry as a fluent friend would say
it, the changed words highlighted). **Both come from the SAME correction call**
— two structured fields, `more` and `natural` — and **neither is ever
journaled**: `record_errors` still takes `shaped.corrections` and nothing else
(the journal half is asserted through the ASGI route in `test_writing_route.py`).

The entry is SYNTHETIC and only shaped like the operator's report: a learner's
diary is never stored (CLAUDE.md §5), so no line of it is copied here.

Every expected value is hardcoded (CLAUDE.md §3 rule 5).
"""

from __future__ import annotations

from core.services import writing
from core.services.users import User
from core.writing import gates, natural

ENTRY = (
    "hi\n"
    "im good\n"
    "i have a bad headake today\n"
    "and i was at work and work a lot.\n"
    "and now preparing to go to home."
)

LABELS = {"verb_tense_past": "Past tense", "preposition": "Prepositions"}

TOP = [
    {
        "you_said": "work a lot",
        "correct_form": "worked a lot",
        "error_type": "verb_tense_past",
        "explanation": "It happened earlier today, so it's worked.",
    },
    {
        "you_said": "go to home",
        "correct_form": "go home",
        "error_type": "preposition",
        "explanation": "Home takes no to after go.",
    },
]

MORE = [
    {"you_said": "headake", "correct_form": "headache", "kind": "spelling",
     "explanation": "It's spelled with ch: headache."},
    {"you_said": "im good", "correct_form": "I'm good", "kind": "capitals",
     "explanation": "I is always a capital, and I'm needs its apostrophe."},
    {"you_said": "i have", "correct_form": "I have", "kind": "capitals",
     "explanation": "I on its own is always a capital letter."},
    {"you_said": "now preparing to", "correct_form": "now getting ready to", "kind": "phrasing",
     "explanation": "Getting ready is what people say about going home."},
]

NATURAL = (
    "Hi!\n"
    "I'm good.\n"
    "I've got a bad headache today.\n"
    "I was at work and worked a lot.\n"
    "Now I'm getting ready to go home."
)


def raw(**over) -> dict:
    body = {"is_english": True, "corrections": TOP, "more": MORE, "natural": NATURAL, "did_well": None}
    body.update(over)
    return body


def shape(body: dict, text: str = ENTRY, kind: str = "journal") -> gates.Shaped:
    return gates.shape(body, text, limit=2 if kind == "journal" else 8, labels=LABELS, kind=kind)


# ── the other notes ──────────────────────────────────────────────────────────


def test_the_top_two_stay_the_corrections_and_the_rest_are_other_notes() -> None:
    shaped = shape(raw())
    assert [c["you_said"] for c in shaped.corrections] == ["work a lot", "go to home"]
    assert [dict(n) for n in shaped.more] == [
        {"you_said": "headake", "correct_form": "headache", "kind": "spelling",
         "explanation": "It's spelled with ch: headache."},
        {"you_said": "im good", "correct_form": "I'm good", "kind": "capitals",
         "explanation": "I is always a capital, and I'm needs its apostrophe."},
        {"you_said": "i have", "correct_form": "I have", "kind": "capitals",
         "explanation": "I on its own is always a capital letter."},
        {"you_said": "now preparing to", "correct_form": "now getting ready to", "kind": "phrasing",
         "explanation": "Getting ready is what people say about going home."},
    ]


def test_a_capital_letter_note_is_a_change_although_the_journal_gates_casefold() -> None:
    """G1 casefolds on purpose (the model re-capitalises quotes); a note whose ONLY
    change is a capital must still count as a change here, or *i have → I have*
    is dropped as `no_change`."""
    shaped = shape(raw(more=[MORE[2]]))
    assert [n["correct_form"] for n in shaped.more] == ["I have"]
    assert "more_no_change" not in shaped.dropped


def test_a_note_that_changes_nothing_is_dropped() -> None:
    shaped = shape(raw(more=[{**MORE[2], "correct_form": "i have"}]))
    assert shaped.more == ()
    assert shaped.dropped.get("more_no_change") == 1


def test_a_spelling_note_is_shown_while_the_same_fix_is_never_a_correction() -> None:
    """The typo gate (G2) keeps a misspelling out of the JOURNAL; the note is display only."""
    as_correction = {"you_said": "headake", "correct_form": "headache",
                     "error_type": "verb_tense_past", "explanation": "It's spelled with ch."}
    shaped = shape(raw(corrections=[as_correction], more=[MORE[0]]))
    assert shaped.corrections == ()
    assert shaped.dropped.get("typo") == 1
    assert [n["kind"] for n in shaped.more] == ["spelling"]


def test_a_note_on_words_the_learner_did_not_write_is_dropped() -> None:
    shaped = shape(raw(more=[{**MORE[0], "you_said": "stomack"}]))
    assert shaped.more == ()
    assert shaped.dropped.get("more_not_self_produced") == 1


def test_a_note_repeating_a_correction_is_dropped() -> None:
    repeat = {"you_said": "and work a lot", "correct_form": "and worked a lot",
              "kind": "grammar", "explanation": "Past, like the rest of the day."}
    shaped = shape(raw(more=[repeat]))
    assert shaped.more == ()
    assert shaped.dropped.get("more_duplicate") == 1


def test_a_note_of_an_unknown_kind_is_dropped() -> None:
    shaped = shape(raw(more=[{**MORE[0], "kind": "pronunciation"}]))
    assert shaped.more == ()
    assert shaped.dropped.get("more_kind") == 1


def test_a_note_whose_explanation_carries_a_banned_term_is_dropped() -> None:
    shaped = shape(raw(more=[{**MORE[0], "explanation": "You got it wrong, it's headache."}]))
    assert shaped.more == ()
    assert shaped.dropped.get("more_explanation") == 1


def test_the_other_notes_stop_at_six() -> None:
    words = ["hi", "good", "have", "bad", "today", "was", "at", "lot"]
    many = [{"you_said": w, "correct_form": w.upper(), "kind": "capitals", "explanation": "A capital."}
            for w in words]
    shaped = shape(raw(corrections=[], more=many))
    assert [n["you_said"] for n in shaped.more] == ["hi", "good", "have", "bad", "today", "was"]
    assert shaped.dropped.get("more_over_cap") == 2


def test_a_third_good_correction_is_shown_as_a_note_and_never_journaled() -> None:
    """*If the current call already returns more than two, use them* (the run prompt).
    It passed every journal gate; only the cap stopped it — so it is shown, below."""
    third = {"you_said": "now preparing to", "correct_form": "now I'm getting ready to",
             "error_type": "verb_tense_past", "explanation": "Say what's happening right now."}
    shaped = shape(raw(corrections=[*TOP, third], more=[]))
    assert len(shaped.corrections) == 2
    assert [dict(n) for n in shaped.more] == [
        {"you_said": "now preparing to", "correct_form": "now I'm getting ready to", "kind": "grammar",
         "explanation": "Say what's happening right now."},
    ]


def test_not_english_carries_no_notes_and_no_natural_version() -> None:
    shaped = shape(raw(is_english=False))
    assert shaped.more == () and shaped.natural is None


def test_the_paragraph_carries_no_notes_and_no_natural_version() -> None:
    """Thursday's paragraph already shows up to eight and its prompt asks for neither."""
    shaped = shape(raw(), kind="paragraph")
    assert shaped.more == () and shaped.natural is None


# ── the natural version ──────────────────────────────────────────────────────


def test_the_natural_version_marks_the_words_that_changed() -> None:
    assert natural.segments("im good\ni go to home", "I'm good.\nI go home.") == (
        {"text": "I'm", "changed": True},
        {"text": " good.\n", "changed": False},
        {"text": "I", "changed": True},
        {"text": " go home.", "changed": False},
    )


def test_neighbouring_changed_words_are_one_highlight() -> None:
    assert natural.segments("and now preparing to go", "and now getting ready to go") == (
        {"text": "and now ", "changed": False},
        {"text": "getting ready", "changed": True},
        {"text": " to go", "changed": False},
    )


def test_the_natural_version_survives_the_gates_with_its_highlights() -> None:
    shaped = shape(raw())
    assert shaped.natural is not None
    assert "".join(s["text"] for s in shaped.natural) == NATURAL
    assert [s["text"] for s in shaped.natural if s["changed"]] == [
        "Hi", "I'm", "I've got", "headache", "I", "worked", "Now I'm getting ready",
    ]


def test_a_natural_version_that_changes_nothing_is_absent() -> None:
    shaped = shape(raw(natural="I went home.", corrections=[], more=[]), text="I went home.")
    assert shaped.natural is None


def test_a_natural_version_that_is_not_a_string_is_absent() -> None:
    assert shape(raw(natural=None)).natural is None
    assert shape(raw(natural=["Hi"])).natural is None


def test_a_natural_version_far_longer_than_the_entry_is_dropped() -> None:
    shaped = shape(raw(natural=NATURAL + " And then" * 60))
    assert shaped.natural is None
    assert shaped.dropped.get("natural_length") == 1


def test_a_banned_term_the_learner_never_wrote_drops_the_natural_version() -> None:
    shaped = shape(raw(natural=NATURAL + " You failed today."))
    assert shaped.natural is None
    assert shaped.dropped.get("natural_content") == 1


def test_the_learners_own_banned_word_does_not_drop_their_natural_version() -> None:
    """*I should have gone home* is the learner's day, not the app's verdict —
    `should have` is a content term, so without the learner's-own rule this drops."""
    text = "i should have go home early"
    shaped = shape(raw(corrections=[], more=[], natural="I should have gone home early."), text=text)
    assert shaped.natural is not None
    assert "natural_content" not in shaped.dropped


# ── the prompt ───────────────────────────────────────────────────────────────


def _user() -> User:
    from datetime import time

    return User(
        id=0, telegram_user_id=None, name="More", native_language="fa", cefr_level="B1",
        explanation_language_fallback=False, efset_baseline=None, work_domain="general",
        why_statement=None, track_weights={"life": 50, "curiosity": 30, "work": 20},
        morning_time=time(8, 0), evening_time=time(21, 0), onboarded=True,
    )


def test_the_journal_prompt_asks_for_the_notes_and_the_natural_version() -> None:
    system = writing.build_system_prompt(_user(), "journal")
    assert '"more": [' in system
    assert '"natural":' in system
    assert "At most 6 other notes" in system
    assert "spelling, capitals, grammar, phrasing" in system
    assert "At most 2 corrections" in system


def test_the_paragraph_prompt_is_not_asked_for_either() -> None:
    system = writing.build_system_prompt(_user(), "paragraph", "Write six sentences about yesterday.")
    assert '"more"' not in system
    assert '"natural"' not in system
