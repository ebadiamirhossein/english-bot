"""Unit tests for app.speech — provider mocked; no real API / no disk I/O."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import openai
import pytest

from app.config import Settings
from app.speech import SpeechError, synthesize, transcribe


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        openai_api_key="test-openai-key",
        stt_provider="openai",
        tts_provider="openai",
        whisper_model="whisper-1",
        tts_model="tts-1",
        tts_voice="alloy",
        tts_format="opus",
    )


def _status_error(status_code: int) -> openai.APIStatusError:
    request = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    return openai.APIStatusError(
        message=f"status {status_code}",
        response=response,
        body={"error": {"message": f"status {status_code}"}},
    )


@patch("app.speech.time.sleep", return_value=None)
@patch("app.speech.openai.OpenAI")
def test_transcribe_passes_named_in_memory_file(
    mock_openai_cls: MagicMock, _mock_sleep: MagicMock
) -> None:
    client = mock_openai_cls.return_value
    result = MagicMock()
    result.text = "hello there"
    client.audio.transcriptions.create.return_value = result

    text = transcribe(b"ogg-bytes", settings=_settings())
    assert text == "hello there"

    kwargs = client.audio.transcriptions.create.call_args.kwargs
    file_arg = kwargs["file"]
    assert isinstance(file_arg, tuple)
    assert file_arg[0] == "voice.ogg"
    assert hasattr(file_arg[1], "read")
    assert kwargs["model"] == "whisper-1"
    assert kwargs["language"] == "en"


@patch("builtins.open")
@patch("tempfile.NamedTemporaryFile")
@patch("tempfile.mkstemp")
@patch("tempfile.TemporaryFile")
@patch("app.speech.time.sleep", return_value=None)
@patch("app.speech.openai.OpenAI")
def test_neither_function_touches_filesystem(
    mock_openai_cls: MagicMock,
    _mock_sleep: MagicMock,
    mock_tmp_file: MagicMock,
    mock_mkstemp: MagicMock,
    mock_named: MagicMock,
    mock_open: MagicMock,
) -> None:
    client = mock_openai_cls.return_value
    tr = MagicMock()
    tr.text = "hi"
    client.audio.transcriptions.create.return_value = tr
    speech = MagicMock()
    speech.content = b"audio-out"
    client.audio.speech.create.return_value = speech

    transcribe(b"in", settings=_settings())
    synthesize("hello", settings=_settings())

    mock_open.assert_not_called()
    mock_tmp_file.assert_not_called()
    mock_mkstemp.assert_not_called()
    mock_named.assert_not_called()


@patch("app.speech.time.sleep", return_value=None)
@patch("app.speech.openai.OpenAI")
def test_transcribe_retries_three_times_then_raises(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    client = mock_openai_cls.return_value
    client.audio.transcriptions.create.side_effect = _status_error(500)

    with pytest.raises(SpeechError):
        transcribe(b"x", settings=_settings())

    assert client.audio.transcriptions.create.call_count == 3
    assert mock_sleep.call_count == 2


@patch("app.speech.time.sleep", return_value=None)
@patch("app.speech.openai.OpenAI")
def test_synthesize_retries_three_times_then_raises(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    client = mock_openai_cls.return_value
    client.audio.speech.create.side_effect = _status_error(500)

    with pytest.raises(SpeechError):
        synthesize("hello", settings=_settings())

    assert client.audio.speech.create.call_count == 3
    assert mock_sleep.call_count == 2
