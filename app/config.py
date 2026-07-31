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

_REQUIRED_KEYS = ("DATABASE_URL", "TELEGRAM_BOT_TOKEN")
_PG_SCHEMES = ("postgresql", "postgres")


class ConfigError(Exception):
    """Fatal configuration error. Message names every problem found."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    telegram_bot_token: str
    db_pool_min: int = 1
    db_pool_max: int = 5
    log_level: str = "INFO"

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

    if database_url and not _is_postgres_dsn(database_url):
        errors.append(
            "DATABASE_URL must be a postgresql:// or postgres:// DSN "
            f"(got scheme {urlparse(database_url).scheme!r})"
        )

    db_pool_min = _parse_int("DB_POOL_MIN", os.environ.get("DB_POOL_MIN", "1"), errors)
    db_pool_max = _parse_int("DB_POOL_MAX", os.environ.get("DB_POOL_MAX", "5"), errors)
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip() or "INFO"

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
    settings = Settings(
        database_url=database_url,
        telegram_bot_token=telegram_bot_token,
        db_pool_min=db_pool_min,
        db_pool_max=db_pool_max,
        log_level=log_level,
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
