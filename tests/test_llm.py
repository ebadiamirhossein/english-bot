"""Unit tests for core.llm — provider is mocked; no real API calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from core.config import Settings
from core.llm import LLMError, _JSON_RAW_LOG_LIMIT, _parse_json, chat


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        llm_provider="anthropic",
        llm_model="claude-sonnet-5",
    )


def _make_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


def _status_error(status_code: int) -> anthropic.APIStatusError:
    request = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    return anthropic.APIStatusError(
        message=f"status {status_code}",
        response=response,
        body={"error": {"message": f"status {status_code}"}},
    )


def _assert_ends_on_user(create_call: MagicMock) -> None:
    """claude-sonnet-5 rejects requests that end on an assistant turn."""
    messages = create_call.kwargs["messages"]
    assert messages, "messages must not be empty"
    assert messages[-1]["role"] == "user"


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_retries_three_times_on_500_then_raises(
    mock_anthropic_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.side_effect = _status_error(500)

    with pytest.raises(LLMError):
        chat(
            [{"role": "user", "content": "hi"}],
            settings=_settings(),
        )

    assert client.messages.create.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_any_call(2.0)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_does_not_retry_on_400(
    mock_anthropic_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.side_effect = _status_error(400)

    with pytest.raises(LLMError):
        chat(
            [{"role": "user", "content": "hi"}],
            settings=_settings(),
        )

    assert client.messages.create.call_count == 1
    mock_sleep.assert_not_called()


@patch("core.llm.anthropic.Anthropic")
def test_json_mode_parses_valid_json(mock_anthropic_cls: MagicMock) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.return_value = _make_response(
        '{"ok": true, "n": 1}'
    )

    result = chat(
        [{"role": "user", "content": "hi"}],
        json_mode=True,
        settings=_settings(),
    )

    assert result == {"ok": True, "n": 1}
    assert client.messages.create.call_count == 1
    _assert_ends_on_user(client.messages.create.call_args)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_json_mode_retries_once_then_raises_on_garbage(
    mock_anthropic_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.return_value = _make_response("not-json{{{")

    with pytest.raises(LLMError, match="not valid JSON") as exc_info:
        chat(
            [{"role": "user", "content": "hi"}],
            json_mode=True,
            settings=_settings(),
        )

    # Initial call + one repair attempt (each may itself retry, but both succeed
    # at the HTTP layer with garbage bodies → exactly 2 create calls).
    assert client.messages.create.call_count == 2
    for call in client.messages.create.call_args_list:
        _assert_ends_on_user(call)
    assert "raw=" in str(exc_info.value)
    assert "not-json{{{" in str(exc_info.value)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_a_truncated_response_is_logged_before_it_is_discarded(
    mock_anthropic_cls: MagicMock,
    _mock_sleep: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#198. **The most expensive failure in the system was the only one that
    could not be diagnosed.**

    W10c's first `--live` attempt died on `stop_reason=max_tokens` at
    `output_tokens=8000` — for a task an offline measurement put at ~2,000 — and
    this path raised while **discarding the response it had just been billed
    for**. So the question that decides what to do next, *was the model writing
    prose, or forty items, or repeating itself?*, was unanswerable, and the next
    attempt had to buy the answer over again.

    **The inconsistency was inside one function:** the `json_mode` parse-failure
    path above already logs `raw=%r` before raising and this one did not, so a
    malformed response was diagnosable and a truncated one was not.

    **Head AND tail, and the count.** The head shows a preamble written before
    the JSON; **the tail shows where it actually stopped**, which is what
    separates a long-but-correct answer from a runaway; and the `item_type`
    count settles over-generation outright — this fixture asks for 8 and the
    model wrote 40.
    """
    body = (
        "Let me think about this first. "
        + '{"items":['
        + '{"item_type":"mcq","prompt_text":"x"},' * 40
    )
    client = mock_anthropic_cls.return_value
    response = _make_response(body)
    response.stop_reason = "max_tokens"
    response.usage.output_tokens = 8000
    client.messages.create.return_value = response

    with caplog.at_level("WARNING", logger="core.llm"):
        with pytest.raises(LLMError) as exc_info:
            chat(
                [{"role": "user", "content": "hi"}],
                max_tokens=8000,
                reject_truncation=True,
                settings=_settings(),
            )

    logged = caplog.text
    assert "truncated response discarded" in logged
    # How many items it was actually writing — one number, and it settles it.
    assert "item_type_count=40" in logged
    # The preamble, which `json_mode`'s tolerance for prose makes possible.
    assert "Let me think about this first" in logged
    # Where it stopped. Without this a runaway looks like a long correct answer.
    assert 'tail=' in logged
    assert logged.split("tail=")[1].startswith(("'", '"'))
    # The exception itself now carries the size, so a caller's own log is useful.
    assert "output_tokens=8000" in str(exc_info.value)
    assert f"chars={len(body)}" in str(exc_info.value)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_truncation_still_raises_and_returns_nothing(
    mock_anthropic_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    """**`reject_truncation` is not weakened by being made diagnosable.**

    Logging what was discarded must not turn a hard failure into a soft one: a
    truncated `{"items": [...]}` parses into a few good items and a silent hole,
    which is worse than a loud failure. W10c pays four billed calls for that
    loudness and the trade is deliberate.
    """
    client = mock_anthropic_cls.return_value
    response = _make_response('{"items":[{"item_type":"mcq"}')
    response.stop_reason = "max_tokens"
    client.messages.create.return_value = response

    with pytest.raises(LLMError):
        chat(
            [{"role": "user", "content": "hi"}],
            json_mode=True,
            reject_truncation=True,
            settings=_settings(),
        )


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_json_mode_parse_failure_logs_truncated_raw(
    mock_anthropic_cls: MagicMock,
    _mock_sleep: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    long_prose = "I cannot extract this. " * 40  # well over 300 chars
    assert len(long_prose) > _JSON_RAW_LOG_LIMIT
    client = mock_anthropic_cls.return_value
    client.messages.create.return_value = _make_response(long_prose)

    with caplog.at_level("WARNING", logger="core.llm"):
        with pytest.raises(LLMError) as exc_info:
            chat(
                [{"role": "user", "content": "hi"}],
                json_mode=True,
                settings=_settings(),
            )

    msg = str(exc_info.value)
    assert "raw=" in msg
    assert long_prose[:50] in msg
    assert "..." in msg
    assert long_prose not in msg  # truncated in the exception
    assert "json_mode parse failure" in caplog.text
    assert long_prose[:50] in caplog.text
    # Pure prose must not silently become an empty/fallback dict.
    assert not isinstance(exc_info.value, dict)


def test_parse_json_fenced() -> None:
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('```\n{"b": 2}\n```') == {"b": 2}


def test_parse_json_prose_preamble() -> None:
    assert _parse_json('Sure, here you go:\n{"ok": true}') == {"ok": True}


def test_parse_json_trailing_commentary() -> None:
    assert _parse_json('{"ok": true}\nHope that helps!') == {"ok": True}


def test_parse_json_pure_prose_raises_not_dict() -> None:
    with pytest.raises(LLMError, match="raw=") as exc_info:
        _parse_json("I refuse to extract this textbook page.")
    assert "raw=" in str(exc_info.value)
    # Must not return a dict on total failure.
    assert not isinstance(exc_info.value.args[0], dict)


def _jpeg_bytes() -> bytes:
    # Minimal JPEG SOI marker so sniff returns image/jpeg.
    return b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _image_blocks_from_call(create_call: MagicMock) -> list[dict]:
    messages = create_call.kwargs["messages"]
    # First user message carries the images (repair keeps them on that turn).
    for msg in messages:
        if msg["role"] != "user":
            continue
        content = msg["content"]
        if isinstance(content, list):
            return [b for b in content if b.get("type") == "image"]
    return []


@patch("core.llm.anthropic.Anthropic")
def test_images_attached_to_user_message(mock_anthropic_cls: MagicMock) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.return_value = _make_response("ok")

    chat(
        [{"role": "user", "content": "extract"}],
        images=[_jpeg_bytes()],
        settings=_settings(),
    )

    assert client.messages.create.call_count == 1
    images = _image_blocks_from_call(client.messages.create.call_args)
    assert len(images) == 1
    assert images[0]["source"]["type"] == "base64"
    assert images[0]["source"]["media_type"] == "image/jpeg"
    assert images[0]["source"]["data"]
    _assert_ends_on_user(client.messages.create.call_args)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_json_mode_repair_resends_image_blocks(
    mock_anthropic_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.side_effect = [
        _make_response("not-json{{{"),
        _make_response('{"unit_number": "12", "readable": true}'),
    ]

    result = chat(
        [{"role": "user", "content": "extract"}],
        json_mode=True,
        images=[_jpeg_bytes()],
        settings=_settings(),
    )

    assert result["unit_number"] == "12"
    assert client.messages.create.call_count == 2
    for call in client.messages.create.call_args_list:
        images = _image_blocks_from_call(call)
        assert len(images) == 1, "repair path must keep image blocks"
        _assert_ends_on_user(call)


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_json_mode_never_ends_on_assistant(
    mock_anthropic_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    """Guard: no request handed to the provider may end on assistant."""
    client = mock_anthropic_cls.return_value
    client.messages.create.side_effect = [
        _make_response("garbage"),
        _make_response('{"ok": true}'),
    ]

    chat(
        [{"role": "user", "content": "hi"}],
        json_mode=True,
        settings=_settings(),
    )

    assert client.messages.create.call_count == 2
    for call in client.messages.create.call_args_list:
        _assert_ends_on_user(call)
        roles = [m["role"] for m in call.kwargs["messages"]]
        assert roles[-1] == "user"
        # Prefill must not reappear as a trailing assistant "{" turn.
        assert not (
            call.kwargs["messages"][-1]["role"] == "assistant"
            and call.kwargs["messages"][-1].get("content") == "{"
        )
