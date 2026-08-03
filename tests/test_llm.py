"""Unit tests for app.llm — provider is mocked; no real API calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.config import Settings
from app.llm import LLMError, chat


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


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.anthropic.Anthropic")
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


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.anthropic.Anthropic")
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


@patch("app.llm.anthropic.Anthropic")
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


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.anthropic.Anthropic")
def test_json_mode_retries_once_then_raises_on_garbage(
    mock_anthropic_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    client = mock_anthropic_cls.return_value
    client.messages.create.return_value = _make_response("not-json{{{")

    with pytest.raises(LLMError, match="not valid JSON"):
        chat(
            [{"role": "user", "content": "hi"}],
            json_mode=True,
            settings=_settings(),
        )

    # Initial call + one repair attempt (each may itself retry, but both succeed
    # at the HTTP layer with garbage bodies → exactly 2 create calls).
    assert client.messages.create.call_count == 2


def test_images_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        chat(
            [{"role": "user", "content": "hi"}],
            images=[b"fake"],
            settings=_settings(),
        )
