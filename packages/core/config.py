"""Load environment into a frozen, typed Settings object.

Every environment variable in this project is read here and nowhere else.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# TELEGRAM_BOT_TOKEN is deliberately absent: apps/api and apps/worker must
# boot without a bot token. apps/bot requires it at startup instead.
_REQUIRED_KEYS = ("DATABASE_URL", "ANTHROPIC_API_KEY")
_PG_SCHEMES = ("postgresql", "postgres")
_KNOWN_STT_PROVIDERS = frozenset({"openai"})
_KNOWN_TTS_PROVIDERS = frozenset({"openai"})
_DEFAULT_RUNTIME_DIR = Path.home() / "english-bot-runtime"
_DEFAULT_LOG_MAX_BYTES = 5_000_000
_DEFAULT_LOG_BACKUP_COUNT = 3


class ConfigError(Exception):
    """Fatal configuration error. Message names every problem found."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    # Empty unless the process is apps/bot, which validates it itself.
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
    # S13 diary — separate from M3's 120s; ~60s ask with headroom.
    diary_max_seconds: int = 90
    # S26 text conversation (/talk).
    conversation_timeout_minutes: int = 30
    conversation_awaiting_topic_minutes: int = 2
    conversation_max_turns: int = 12
    conversation_history_max_messages: int = 20
    # S18 hardening — operator alerts + runtime files (optional ids).
    operator_telegram_id: int | None = None
    runtime_dir: str = ""
    log_file: str = ""
    log_max_bytes: int = _DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = _DEFAULT_LOG_BACKUP_COUNT
    instance_lock_file: str = ""
    heartbeat_file: str = ""
    alert_throttle_file: str = ""
    # S4c — empty means the folder-copy freshness check is a silent no-op.
    backup_offsite_dir: str = ""
    backup_offsite_max_age_hours: float = 48.0
    # W1c — Cloudflare R2, the real off-site copy. All five or none; a partly
    # set group is a configuration mistake and the freshness check says so.
    r2_account_id: str = ""
    r2_bucket: str = ""
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    # repr=False: this value must never reach a log line, and `logger.info("%s",
    # settings)` is one keystroke away in any file that holds a Settings
    # (CLAUDE.md §5 — logs carry user ids and route names, nothing else).
    r2_secret_access_key: str = field(default="", repr=False)
    # 24-hour backup cycle plus slack for a late cron.
    r2_max_age_hours: float = 26.0
    # Whether an unconfigured R2 is an alarm. Default true, and that direction
    # is the point: forgetting it in production keeps the alarm, forgetting it
    # on a dev machine costs one extra alert. Silence is never the default
    # (known issue #31). Dev machines set BACKUP_R2_REQUIRED=0.
    r2_required: bool = True
    # S15a — empty means watch poll / /import / Anki outbox are silent no-ops.
    watch_dir: str = ""
    # S24 — comma-separated book slugs the operator shares (empty = none).
    shared_book_slugs: tuple[str, ...] = ()
    # S8 couple challenge — empty means the whole feature is inert.
    couple_chat_id: int | None = None
    # W1b — the one browser origin apps/api trusts. Empty until the domain is
    # chosen (W2); the API then allows localhost:3000 only.
    web_origin: str = ""
    # W2 — passkey auth.
    #
    # WEBAUTHN_RP_ID must be `foundgrant.com`, NOT `app.foundgrant.com`: a
    # credential is scoped by the browser to its RP ID permanently, so scoping
    # it to the subdomain means a second subdomain can never use it and changing
    # it later costs every learner a full re-enrolment. It must be a
    # registrable-domain suffix of WEBAUTHN_ORIGIN's host — a mismatch is a
    # browser-side SecurityError with NO server-side symptom at all, which is
    # why it is validated here rather than discovered on a phone.
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "Everyday English"
    webauthn_origin: str = ""
    auth_session_days: int = 30
    auth_claim_token_hours: int = 24
    # repr=False for the same reason as the R2 secret: one `logger.info("%s",
    # settings)` would put it in a log file for good.
    auth_rate_limit_salt: str = field(default="", repr=False)
    # Local development only: http://localhost cannot carry a Secure cookie
    # consistently across browsers. Default false, and that direction is the
    # point — forgetting it in production keeps the secure cookie.
    auth_cookie_insecure: bool = False

    def database_url_for_logs(self) -> str:
        """Return DATABASE_URL with the password stripped for safe logging."""
        return _strip_password(self.database_url)


def load_settings(dotenv_path: str | Path | None = None) -> Settings:
    """Load Settings from the environment.

    Real environment variables win over values from a `.env` file so systemd
    and CI can override without editing the file.

    ``dotenv_path`` names the `.env` file to read. **The default is unchanged**:
    ``None`` means ``python-dotenv`` searches upward from
    ``packages/core/config.py``, which is how every process in production finds
    the repo-root `.env` no matter which directory it starts in.

    The parameter exists because that search is also a trap (known issue #64):
    it ignores a `.env` in the working directory and silently loads the repo's
    instead — and, more sharply, it defeats ``monkeypatch.delenv`` in a test.
    A test that deletes a variable to exercise a default gets the value put
    straight back from whatever the developer's `.env` happens to say, so the
    suite becomes machine-dependent: green where the line is absent, red where
    it is present. That is CLAUDE.md §3 rule 3 arriving from the other
    direction — the same failure #26 was written from.

    Passing an explicit path lets a test set configuration the way it is really
    set — a `.env` file — and get a hermetic answer.
    """
    load_dotenv(dotenv_path=dotenv_path, override=False)

    missing = [key for key in _REQUIRED_KEYS if not os.environ.get(key, "").strip()]
    errors: list[str] = []
    if missing:
        errors.append(
            "missing required environment variable(s): " + ", ".join(missing)
        )

    database_url = os.environ.get("DATABASE_URL", "").strip()
    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    # Provider default lives in core.llm (keeps the SDK name out of this file).
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
    diary_max_seconds = _parse_int(
        "DIARY_MAX_SECONDS",
        os.environ.get("DIARY_MAX_SECONDS", "90"),
        errors,
    )
    conversation_timeout_minutes = _parse_int(
        "CONVERSATION_TIMEOUT_MINUTES",
        os.environ.get("CONVERSATION_TIMEOUT_MINUTES", "30"),
        errors,
    )
    conversation_awaiting_topic_minutes = _parse_int(
        "CONVERSATION_AWAITING_TOPIC_MINUTES",
        os.environ.get("CONVERSATION_AWAITING_TOPIC_MINUTES", "2"),
        errors,
    )
    conversation_max_turns = _parse_int(
        "CONVERSATION_MAX_TURNS",
        os.environ.get("CONVERSATION_MAX_TURNS", "12"),
        errors,
    )
    conversation_history_max_messages = _parse_int(
        "CONVERSATION_HISTORY_MAX_MESSAGES",
        os.environ.get("CONVERSATION_HISTORY_MAX_MESSAGES", "20"),
        errors,
    )

    operator_telegram_id = _parse_optional_int(
        "OPERATOR_TELEGRAM_ID",
        os.environ.get("OPERATOR_TELEGRAM_ID", ""),
        errors,
    )

    runtime_dir = (
        os.environ.get("RUNTIME_DIR", "").strip()
        or str(_DEFAULT_RUNTIME_DIR)
    )
    log_file = (
        os.environ.get("LOG_FILE", "").strip()
        or str(Path(runtime_dir) / "bot.log")
    )
    log_max_bytes = _parse_int(
        "LOG_MAX_BYTES",
        os.environ.get("LOG_MAX_BYTES", str(_DEFAULT_LOG_MAX_BYTES)),
        errors,
    )
    log_backup_count = _parse_int(
        "LOG_BACKUP_COUNT",
        os.environ.get("LOG_BACKUP_COUNT", str(_DEFAULT_LOG_BACKUP_COUNT)),
        errors,
    )
    instance_lock_file = (
        os.environ.get("INSTANCE_LOCK_FILE", "").strip()
        or str(Path(runtime_dir) / "bot.lock")
    )
    heartbeat_file = (
        os.environ.get("HEARTBEAT_FILE", "").strip()
        or str(Path(runtime_dir) / "last_job_fire")
    )
    alert_throttle_file = (
        os.environ.get("ALERT_THROTTLE_FILE", "").strip()
        or str(Path(runtime_dir) / "alert_throttle.json")
    )
    backup_offsite_dir = os.environ.get("BACKUP_OFFSITE_DIR", "").strip()
    backup_offsite_max_age_hours = _parse_float(
        "BACKUP_OFFSITE_MAX_AGE_HOURS",
        os.environ.get("BACKUP_OFFSITE_MAX_AGE_HOURS", "48"),
        errors,
    )
    r2_account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    r2_bucket = os.environ.get("R2_BUCKET", "").strip()
    r2_endpoint = os.environ.get("R2_ENDPOINT", "").strip()
    r2_access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    r2_secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    r2_max_age_hours = _parse_float(
        "BACKUP_R2_MAX_AGE_HOURS",
        os.environ.get("BACKUP_R2_MAX_AGE_HOURS", "26"),
        errors,
    )
    r2_required = _parse_bool(
        "BACKUP_R2_REQUIRED",
        os.environ.get("BACKUP_R2_REQUIRED", ""),
        default=True,
        errors=errors,
    )
    if r2_endpoint and not r2_endpoint.startswith(("http://", "https://")):
        errors.append(
            "R2_ENDPOINT must be a scheme-qualified URL "
            f"(got {r2_endpoint!r})"
        )
    watch_dir = os.environ.get("WATCH_DIR", "").strip()
    shared_book_slugs = tuple(
        part.strip()
        for part in os.environ.get("SHARED_BOOK_SLUGS", "").split(",")
        if part.strip()
    )
    couple_chat_id = _parse_optional_int(
        "COUPLE_CHAT_ID",
        os.environ.get("COUPLE_CHAT_ID", ""),
        errors,
    )
    web_origin = os.environ.get("WEB_ORIGIN", "").strip()
    if web_origin and not web_origin.startswith(("http://", "https://")):
        errors.append(
            "WEB_ORIGIN must be a scheme-qualified origin "
            f"(got {web_origin!r})"
        )
    if web_origin.endswith("/"):
        errors.append(
            "WEB_ORIGIN must not end with '/' — CORS compares origins "
            f"literally (got {web_origin!r})"
        )

    # --- W2 passkey auth -------------------------------------------------
    webauthn_rp_id = os.environ.get("WEBAUTHN_RP_ID", "").strip().lower()
    webauthn_rp_name = (
        os.environ.get("WEBAUTHN_RP_NAME", "").strip() or "Everyday English"
    )
    webauthn_origin = os.environ.get("WEBAUTHN_ORIGIN", "").strip()
    if webauthn_origin and not webauthn_origin.startswith(("http://", "https://")):
        errors.append(
            "WEBAUTHN_ORIGIN must be a scheme-qualified origin "
            f"(got {webauthn_origin!r})"
        )
    if webauthn_origin.endswith("/"):
        errors.append(
            "WEBAUTHN_ORIGIN must not end with '/' — WebAuthn compares "
            f"origins literally (got {webauthn_origin!r})"
        )
    if webauthn_rp_id and webauthn_origin and not _rp_id_covers(
        webauthn_rp_id, webauthn_origin
    ):
        # The failure this prevents: the browser throws SecurityError before
        # any request is made, so the server sees nothing at all and the phone
        # shows "something went wrong".
        errors.append(
            f"WEBAUTHN_RP_ID {webauthn_rp_id!r} is not a registrable-domain "
            f"suffix of WEBAUTHN_ORIGIN {webauthn_origin!r} — the browser will "
            "refuse every ceremony with SecurityError and the server will see "
            "no request at all"
        )
    if bool(webauthn_rp_id) != bool(webauthn_origin):
        errors.append(
            "WEBAUTHN_RP_ID and WEBAUTHN_ORIGIN must be set together "
            "(auth is off when both are empty)"
        )

    auth_session_days = _parse_int(
        "AUTH_SESSION_DAYS", os.environ.get("AUTH_SESSION_DAYS", "30"), errors
    )
    auth_claim_token_hours = _parse_int(
        "AUTH_CLAIM_TOKEN_HOURS",
        os.environ.get("AUTH_CLAIM_TOKEN_HOURS", "24"),
        errors,
    )
    auth_rate_limit_salt = os.environ.get("AUTH_RATE_LIMIT_SALT", "").strip()
    auth_cookie_insecure = _parse_bool(
        "AUTH_COOKIE_INSECURE",
        os.environ.get("AUTH_COOKIE_INSECURE", ""),
        default=False,
        errors=errors,
    )
    if auth_session_days is not None and auth_session_days < 1:
        errors.append(f"AUTH_SESSION_DAYS must be >= 1 (got {auth_session_days})")
    if auth_claim_token_hours is not None and auth_claim_token_hours < 1:
        errors.append(
            f"AUTH_CLAIM_TOKEN_HOURS must be >= 1 (got {auth_claim_token_hours})"
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
    if log_max_bytes is not None and log_max_bytes < 1:
        errors.append(f"LOG_MAX_BYTES must be >= 1 (got {log_max_bytes})")
    if log_backup_count is not None and log_backup_count < 0:
        errors.append(
            f"LOG_BACKUP_COUNT must be >= 0 (got {log_backup_count})"
        )
    if (
        backup_offsite_max_age_hours is not None
        and backup_offsite_max_age_hours <= 0
    ):
        errors.append(
            "BACKUP_OFFSITE_MAX_AGE_HOURS must be > 0 "
            f"(got {backup_offsite_max_age_hours})"
        )
    if r2_max_age_hours is not None and r2_max_age_hours <= 0:
        errors.append(
            f"BACKUP_R2_MAX_AGE_HOURS must be > 0 (got {r2_max_age_hours})"
        )
    if (
        conversation_timeout_minutes is not None
        and conversation_timeout_minutes < 1
    ):
        errors.append(
            "CONVERSATION_TIMEOUT_MINUTES must be >= 1 "
            f"(got {conversation_timeout_minutes})"
        )
    if (
        conversation_awaiting_topic_minutes is not None
        and conversation_awaiting_topic_minutes < 1
    ):
        errors.append(
            "CONVERSATION_AWAITING_TOPIC_MINUTES must be >= 1 "
            f"(got {conversation_awaiting_topic_minutes})"
        )
    if conversation_max_turns is not None and conversation_max_turns < 2:
        errors.append(
            "CONVERSATION_MAX_TURNS must be >= 2 "
            f"(got {conversation_max_turns})"
        )
    if (
        conversation_history_max_messages is not None
        and conversation_history_max_messages < 2
    ):
        errors.append(
            "CONVERSATION_HISTORY_MAX_MESSAGES must be >= 2 "
            f"(got {conversation_history_max_messages})"
        )

    if errors:
        raise ConfigError("; ".join(errors))

    assert db_pool_min is not None and db_pool_max is not None  # for type checker
    assert voice_max_seconds is not None
    assert voice_context_minutes is not None
    assert voice_max_turns is not None
    assert diary_max_seconds is not None
    assert conversation_timeout_minutes is not None
    assert conversation_awaiting_topic_minutes is not None
    assert conversation_max_turns is not None
    assert conversation_history_max_messages is not None
    assert log_max_bytes is not None
    assert log_backup_count is not None
    assert backup_offsite_max_age_hours is not None
    assert r2_max_age_hours is not None
    assert r2_required is not None
    assert auth_session_days is not None
    assert auth_claim_token_hours is not None
    assert auth_cookie_insecure is not None
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
        diary_max_seconds=diary_max_seconds,
        conversation_timeout_minutes=conversation_timeout_minutes,
        conversation_awaiting_topic_minutes=conversation_awaiting_topic_minutes,
        conversation_max_turns=conversation_max_turns,
        conversation_history_max_messages=conversation_history_max_messages,
        operator_telegram_id=operator_telegram_id,
        runtime_dir=runtime_dir,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        instance_lock_file=instance_lock_file,
        heartbeat_file=heartbeat_file,
        alert_throttle_file=alert_throttle_file,
        backup_offsite_dir=backup_offsite_dir,
        backup_offsite_max_age_hours=backup_offsite_max_age_hours,
        r2_account_id=r2_account_id,
        r2_bucket=r2_bucket,
        r2_endpoint=r2_endpoint,
        r2_access_key_id=r2_access_key_id,
        r2_secret_access_key=r2_secret_access_key,
        r2_max_age_hours=r2_max_age_hours,
        r2_required=r2_required,
        watch_dir=watch_dir,
        shared_book_slugs=shared_book_slugs,
        couple_chat_id=couple_chat_id,
        web_origin=web_origin,
        webauthn_rp_id=webauthn_rp_id,
        webauthn_rp_name=webauthn_rp_name,
        webauthn_origin=webauthn_origin,
        auth_session_days=auth_session_days,
        auth_claim_token_hours=auth_claim_token_hours,
        auth_rate_limit_salt=auth_rate_limit_salt,
        auth_cookie_insecure=auth_cookie_insecure,
    )

    _warn_if_transaction_pooler(settings.database_url)
    return settings


def _parse_int(name: str, raw: str, errors: list[str]) -> int | None:
    try:
        return int(raw.strip())
    except ValueError:
        errors.append(f"{name} must be an integer (got {raw!r})")
        return None


def _parse_float(name: str, raw: str, errors: list[str]) -> float | None:
    try:
        return float(raw.strip())
    except ValueError:
        errors.append(f"{name} must be a number (got {raw!r})")
        return None


_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
_FALSE_WORDS = frozenset({"0", "false", "no", "off"})


def _parse_bool(
    name: str, raw: str, *, default: bool, errors: list[str]
) -> bool | None:
    """Parse an optional boolean; empty string means unset (use *default*)."""
    stripped = raw.strip().lower()
    if not stripped:
        return default
    if stripped in _TRUE_WORDS:
        return True
    if stripped in _FALSE_WORDS:
        return False
    errors.append(
        f"{name} must be one of "
        f"{sorted(_TRUE_WORDS | _FALSE_WORDS)} (got {raw!r})"
    )
    return None


def _parse_optional_int(
    name: str, raw: str, errors: list[str]
) -> int | None:
    """Parse an optional integer; empty string means unset (None)."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        errors.append(f"{name} must be an integer (got {raw!r})")
        return None


def _rp_id_covers(rp_id: str, origin: str) -> bool:
    """True when *rp_id* is a valid Relying Party ID for pages on *origin*.

    The WebAuthn rule: the RP ID must equal the origin's effective domain or be
    a registrable-domain suffix of it. So `foundgrant.com` is valid for
    `https://app.foundgrant.com` (and is what we use, so a credential keeps
    working if a second subdomain ever appears), while `app.foundgrant.com`
    would not be valid for `https://other.foundgrant.com`.

    Deliberately does no public-suffix lookup: this is a two-domain project and
    a PSL dependency to catch `rp_id="com"` — which nobody can register anyway —
    would be more machinery than the check is worth.
    """
    host = (urlparse(origin).hostname or "").lower()
    if not host or not rp_id:
        return False
    return host == rp_id or host.endswith("." + rp_id)


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
