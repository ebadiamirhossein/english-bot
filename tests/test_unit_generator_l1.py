"""#424 — the unit item generator sends the learner's first language, BY NAME.

Fixed in W15 by operator ruling (2026-09-25). Before the fix `build_payload`
sent `unit_number`, `can_do`, `track` and the slots — no language at all — so
`l1_gloss` and every `l1_to_l2_production` prompt were written in whatever
language the model guessed, and `L1ToL2ProductionItem.l1` defaulted to `fa`.
The Lithuanian-speaking learner's first unit would have been built for a Farsi
speaker.

Request construction is mocked at the provider SDK (`anthropic.Anthropic`),
never at the service function (TASKS standing rule 7). Expected values are
hardcoded (CLAUDE.md §3 rule 5).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.items import generate
from core.items.generate import bind_l1, build_payload, generate_drafts, slot_plan

UNIT_1_TARGETS = ("past simple: regular and irregular verbs",)


def _sdk_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.usage = MagicMock(input_tokens=10, output_tokens=10,
                               cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return response


def _sent_payload(mock_cls, l1: str) -> dict:
    client = mock_cls.return_value
    client.messages.create.return_value = _sdk_response('{"items": []}')
    slots = slot_plan(1, UNIT_1_TARGETS)
    generate_drafts(build_payload(1, "I can tell a friend what I did yesterday.", slots, l1=l1))
    kwargs = client.messages.create.call_args.kwargs
    return json.loads(kwargs["messages"][0]["content"]), kwargs["system"][0]["text"]


@pytest.mark.parametrize(("l1", "name"), [("fa", "Farsi"), ("lt", "Lithuanian")])
@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_each_learner_s_language_reaches_the_request_by_name(mock_cls, _sleep, l1, name) -> None:
    """The bytes sent for each learner name THAT learner's language.

    **Red method:** delete the `"learner_l1": language_name(l1)` line from
    `build_payload` — `sent["learner_l1"]` raises `KeyError` for both learners
    (demonstrated 2026-09-25: both parametrised cases failed, and so did the
    unmapped-code test, whose `ValueError` the same line raises). Before the fix the payload had no such
    key at all, which is the defect."""
    sent, system = _sent_payload(mock_cls, l1)
    assert sent["learner_l1"] == name
    assert sent["learner_l1"] != l1, "a code is never sent raw (F5)"
    # The system prompt says what the key is for, so the language reaches the
    # two fields it governs rather than sitting unexplained in the payload.
    assert "learner_l1" in system
    assert "l1_to_l2_production" in system


def test_an_unmapped_language_is_an_error_and_is_never_sent() -> None:
    """F5's rule, applied to the generator. **Red method:** make `build_payload`
    fall back to the raw code — no `ValueError`, and `"de"` would be sent."""
    with pytest.raises(ValueError, match="no language name"):
        build_payload(1, "can-do", slot_plan(1, UNIT_1_TARGETS), l1="de")


def test_the_language_is_required_at_every_call_site() -> None:
    """Keyword-only with no default, so a caller that forgets it fails at once
    rather than sending a payload with no language. **Red method:** give `l1` a
    default of `"fa"` — the call succeeds."""
    with pytest.raises(TypeError):
        build_payload(1, "can-do", slot_plan(1, UNIT_1_TARGETS))  # type: ignore[call-arg]


def test_the_production_item_is_bound_to_the_learner_not_the_model() -> None:
    """A Lithuanian learner's production draft that says `fa` — or says nothing
    and would default to `fa` — is bound to `lt` before it is parsed.
    **Red method:** make `bind_l1` a no-op — the parsed item carries `fa`."""
    slots = tuple(s for s in slot_plan(1, UNIT_1_TARGETS) if s.item_type == "l1_to_l2_production")
    assert slots, "unit 1's plan carries a production slot"
    slot = generate.Slot(index=0, item_type="l1_to_l2_production", target=slots[0].target,
                         cohort=slots[0].cohort)
    drafts = [{"prompt_text": "Vakar nuėjau į parduotuvę.", "answer": "Yesterday I went to the shop.",
               "l1": "fa", "explanation": "Past simple for a finished action.",
               "definition": "went: past of go", "l1_gloss": "nuėjau"}]
    bind_l1(drafts, (slot,), "lt")
    item = generate._draft_to_item(drafts[0], slot, 1)
    assert item.l1 == "lt"


def test_the_l1_probe_is_dry_by_default_and_names_its_calls(capsys, monkeypatch) -> None:
    """Build-run ruling 0.5. **Red method:** make the loop call
    `generate_drafts` without `--live` — the stub raises."""
    from core.items import l1_probe

    def _no_call(*_a, **_k):
        raise AssertionError("the dry probe made a call")

    monkeypatch.setattr(generate, "generate_drafts", _no_call)
    assert l1_probe.main([]) == 0
    out = capsys.readouterr().out
    assert "calls --live will make: 2" in out
    assert '"learner_l1": "Farsi"' in out and '"learner_l1": "Lithuanian"' in out
    assert "DRY RUN. Nothing was sent and nothing was written." in out


def test_the_l1_probe_uses_unit_one_s_real_can_do_and_target() -> None:
    """The probe's fixtures are the syllabus's, read independently from the file."""
    from pathlib import Path

    from core.items import l1_probe

    unit = json.loads((Path(__file__).resolve().parents[1] / "data" / "syllabus_units.json")
                      .read_text(encoding="utf-8"))[0]
    assert l1_probe.CAN_DO == unit["can_do"]
    assert l1_probe.TARGET in [t["target"] for t in unit["grammar_targets"]]
