"""W16a: the writing correction's REQUEST, asserted at the provider transport.

TASKS standing rule 7: any test asserting request construction mocks at
`anthropic.Anthropic`, never above it. Mocking `chat()` proves nothing about what
leaves the process — that exact mistake shipped a broken close-out with 693
tests green. Here `core.llm.anthropic.Anthropic` is replaced, `chat()` runs for
real, and the assertions read the kwargs `messages.create` was given.

**WHAT THIS CANNOT PROVE, AND WHY THE PROBE EXISTS (CLAUDE.md §3 rule 2):** that
the provider ACCEPTS this request and that the model's answer fits the contract.
A mock accepts anything. `python -m core.writing.probe --live`, run by the
operator on the Mac, is the evidence for that half.

**RED DEMONSTRATIONS:** `reject_truncation=True` removed from
`writing.call_model` → `test_a_truncated_answer_is_refused`;
`max_tokens=rules.WRITING_MAX_TOKENS` removed → `test_the_request_as_sent`;
**after the first §3 rule 2 call:** the one-error rule deleted from the prompt
(F2), `WHERE learner_label IS NOT NULL` removed from the type query (F6), and
`native_language=user.native_language` restored in place of the name (F5) —
each turned `test_the_request_as_sent` red.

**F2 IS PINNED ON THE INSTRUCTION, NOT ON THE OUTPUT, AND THAT IS STATED.** No
gate here can tell one error from two bundled into one quote; the pin proves the
model is told, and only a read of real responses shows whether it listens.
"""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

import pytest

from core.llm import LLMError
from core.prompt_rules import ENGLISH_ONLY_RULE
from core.services import writing
from core.services.users import User

TEXT = "Today I go to the dentist in the morning."


def _learner() -> User:
    return User(
        id=0,
        telegram_user_id=None,
        name="Request",
        native_language="lt",
        cefr_level="B1",
        explanation_language_fallback=False,
        efset_baseline=None,
        work_domain="general",
        why_statement=None,
        track_weights={"life": 50, "curiosity": 30, "work": 20},
        morning_time=time(8, 0),
        evening_time=time(21, 0),
        onboarded=True,
    )


def _response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = stop_reason
    response.usage = MagicMock(
        input_tokens=900,
        output_tokens=60,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_the_request_as_sent(mock_cls, _sleep) -> None:
    client = mock_cls.return_value
    client.messages.create.return_value = _response(
        '{"is_english": true, "corrections": [], "did_well": null}'
    )
    usage: dict = {}
    raw = writing.call_model(_learner(), TEXT, "journal", usage_out=usage)

    assert raw == {"is_english": True, "corrections": [], "did_well": None}
    assert client.messages.create.call_count == 1
    kwargs = client.messages.create.call_args.kwargs

    assert kwargs["max_tokens"] == 2000
    messages = kwargs["messages"]
    assert len(messages) == 1 and messages[0]["role"] == "user"
    content = messages[0]["content"]
    content_text = content if isinstance(content, str) else content[0]["text"]
    assert content_text == f"<user_text>\n{TEXT}\n</user_text>"

    system = kwargs["system"][0]["text"]
    assert ENGLISH_ONLY_RULE in system
    assert "At most 2 corrections" in system
    assert "did_well is OPTIONAL" in system
    # F6: the spoken codes are not listed at all — not listed-then-forbidden.
    for spoken in ("pronunciation_vowel", "pronunciation_stress", "filler_overuse"):
        assert spoken not in system, spoken
    assert "verb_tense_past" in system
    # F2: one correction is one error.
    assert "Each correction fixes exactly ONE error" in system
    assert "Never bundle two errors into one correction" in system
    # F1: the line describes the entry and never rates the learner.
    assert "DESCRIBES WHAT THE ENTRY DOES, never what the learner can do" in system
    assert "No grammar terminology" in system
    # F5: the language's NAME, never the column value.
    assert "whose first language is Lithuanian" in system
    assert "first language is lt" not in system
    assert "{" not in system.replace("{{", "").split("Output contract")[0], "an unfilled placeholder"
    assert usage == {
        "calls": 1,
        "input_tokens": 900,
        "output_tokens": 60,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_a_truncated_answer_is_refused(mock_cls, _sleep) -> None:
    """A truncated array would parse into fewer corrections and a silent hole."""
    client = mock_cls.return_value
    client.messages.create.return_value = _response(
        '{"is_english": true, "corrections": [', stop_reason="max_tokens"
    )
    usage: dict = {}
    with pytest.raises(LLMError):
        writing.call_model(_learner(), TEXT, "journal", usage_out=usage)
    # The truncated response was generated and billed, so it is still counted.
    assert usage.get("calls") == 1


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_the_paragraph_request_as_sent(mock_cls, _sleep) -> None:
    """W16b — new request construction: the unit's task, the ceiling of eight,
    `structure` and `keep`. **Red demonstration:** `task=task` dropped from
    `call_model`'s `build_system_prompt` call turned this red (the prompt refused
    to build without a task)."""
    task = "Write six sentences about yesterday. Put them in order and join them with time words."
    client = mock_cls.return_value
    client.messages.create.return_value = _response(
        '{"is_english": true, "structure": [], "corrections": []}'
    )
    writing.call_model(_learner(), TEXT, "paragraph", usage_out={}, task=task)
    kwargs = client.messages.create.call_args.kwargs
    system = kwargs["system"][0]["text"]
    assert kwargs["max_tokens"] == 2000
    assert f"exactly as they were given it:\n{task}\n" in system
    assert "At most 8 corrections" in system
    assert "keep is OPTIONAL" in system
    assert "Rules for structure" in system
    assert "Each correction fixes exactly ONE error" in system
    assert "whose first language is Lithuanian" in system
    for spoken in ("pronunciation_vowel", "pronunciation_stress", "filler_overuse"):
        assert spoken not in system
    assert "did_well" not in system, "the paragraph asks for no opening line (1n draws none)"


def test_a_paragraph_prompt_without_a_task_is_refused() -> None:
    with pytest.raises(ValueError):
        writing.build_system_prompt(_learner(), "paragraph", None)
