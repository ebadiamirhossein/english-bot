"""Load environment into a frozen, typed Settings object.

Every environment variable in this project is read here and nowhere else.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY")
_PG_SCHEMES = ("postgresql", "postgres")
_KNOWN_STT_PROVIDERS = frozenset({"openai"})
_KNOWN_TTS_PROVIDERS = frozenset({"openai"})


class ConfigError(Exception):
    """Fatal configuration error. Message names every problem found."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    telegram_bot_token: str
    llm_api_key: str
    llm_provider: str = ""
    llm_model: str = "claude-sonnet-5"
    db_pool_min: int = 1
    db_pool_max: int = 5
    log_level: str = "INFO"
    # Voice / STT / TTS (S5). OPENAI_API_KEY is optional at load — required
    # only when speech.transcribe / synthesize actually run.
    stt_provider: str = "openai"
    tts_provider: str = "openai"
    openai_api_key: str = ""
    whisper_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_format: str = "opus"
    voice_max_seconds: int = 120
    voice_context_minutes: int = 120
    voice_max_turns: int = 10

    def database_url_for_logs(self) -> str:
        """Return DATABASE_URL with the password stripped for safe logging."""
        return _strip_password(self.database_url)


def load_settings() -> Settings:
    """Load Settings from the environment.

    Real environment variables win over values from a `.env` file so systemd
    and CI can override without editing the file.
    """
    load_dotenv(override=False)

    missing = [key for key in _REQUIRED_KEYS if not os.environ.get(key, "").strip()]
    errors: list[str] = []
    if missing:
        errors.append(
            "missing required environment variable(s): " + ", ".join(missing)
        )

    database_url = os.environ.get("DATABASE_URL", "").strip()
    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    # Provider default lives in app.llm (keeps the SDK name out of this file).
    llm_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    llm_provider = os.environ.get("LLM_PROVIDER", "").strip()
    llm_model = (
        os.environ.get("LLM_MODEL", "claude-sonnet-5").strip() or "claude-sonnet-5"
    )

    stt_provider = (
        os.environ.get("STT_PROVIDER", "openai").strip() or "openai"
    )
    tts_provider = (
        os.environ.get("TTS_PROVIDER", "openai").strip() or "openai"
    )
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    whisper_model = (
        os.environ.get("WHISPER_MODEL", "whisper-1").strip() or "whisper-1"
    )
    tts_model = os.environ.get("TTS_MODEL", "tts-1").strip() or "tts-1"
    tts_voice = os.environ.get("TTS_VOICE", "alloy").strip() or "alloy"
    tts_format = os.environ.get("TTS_FORMAT", "opus").strip() or "opus"

    if stt_provider not in _KNOWN_STT_PROVIDERS:
        errors.append(f"Unknown STT_PROVIDER: {stt_provider!r}")
    if tts_provider not in _KNOWN_TTS_PROVIDERS:
        errors.append(f"Unknown TTS_PROVIDER: {tts_provider!r}")

    if database_url and not _is_postgres_dsn(database_url):
        errors.append(
            "DATABASE_URL must be a postgresql:// or postgres:// DSN "
            f"(got scheme {urlparse(database_url).scheme!r})"
        )

    db_pool_min = _parse_int("DB_POOL_MIN", os.environ.get("DB_POOL_MIN", "1"), errors)
    db_pool_max = _parse_int("DB_POOL_MAX", os.environ.get("DB_POOL_MAX", "5"), errors)
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip() or "INFO"

    voice_max_seconds = _parse_int(
        "VOICE_MAX_SECONDS",
        os.environ.get("VOICE_MAX_SECONDS", "120"),
        errors,
    )
    voice_context_minutes = _parse_int(
        "VOICE_CONTEXT_MINUTES",
        os.environ.get("VOICE_CONTEXT_MINUTES", "120"),
        errors,
    )
    voice_max_turns = _parse_int(
        "VOICE_MAX_TURNS",
        os.environ.get("VOICE_MAX_TURNS", "10"),
        errors,
    )

    if db_pool_min is not None and db_pool_min < 1:
        errors.append(f"DB_POOL_MIN must be >= 1 (got {db_pool_min})")
    if (
        db_pool_min is not None
        and db_pool_max is not None
        and db_pool_max < db_pool_min
    ):
        errors.append(
            f"DB_POOL_MAX ({db_pool_max}) must be >= DB_POOL_MIN ({db_pool_min})"
        )

    if errors:
        raise ConfigError("; ".join(errors))

    assert db_pool_min is not None and db_pool_max is not None  # for type checker
    assert voice_max_seconds is not None
    assert voice_context_minutes is not None
    assert voice_max_turns is not None
    settings = Settings(
        database_url=database_url,
        telegram_bot_token=telegram_bot_token,
        llm_api_key=llm_api_key,
        llm_provider=llm_provider,
        llm_model=llm_model,
        db_pool_min=db_pool_min,
        db_pool_max=db_pool_max,
        log_level=log_level,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        openai_api_key=openai_api_key,
        whisper_model=whisper_model,
        tts_model=tts_model,
        tts_voice=tts_voice,
        tts_format=tts_format,
        voice_max_seconds=voice_max_seconds,
        voice_context_minutes=voice_context_minutes,
        voice_max_turns=voice_max_turns,
    )

    _warn_if_transaction_pooler(settings.database_url)
    return settings


def _parse_int(name: str, raw: str, errors: list[str]) -> int | None:
    try:
        return int(raw.strip())
    except ValueError:
        errors.append(f"{name} must be an integer (got {raw!r})")
        return None


def _is_postgres_dsn(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme in _PG_SCHEMES


def _strip_password(url: str) -> str:
    parsed = urlparse(url)
    if parsed.password is None:
        return url
    # Rebuild netloc without the password. Keep username if present.
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if parsed.username:
        netloc = f"{parsed.username}:***@{host}"
    else:
        netloc = f"***@{host}"
    return urlunparse(parsed._replace(netloc=netloc))


def _warn_if_transaction_pooler(database_url: str) -> None:
    port = urlparse(database_url).port
    if port == 6543:
        logger.warning(
            "DATABASE_URL uses port 6543 (Supabase transaction-mode pooler). "
            "ARCHITECTURE.md requires the session-mode pooler; transaction "
            "mode breaks psycopg3 prepared statements. Continuing anyway."
        )
