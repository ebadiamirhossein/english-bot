"""Database connection pool and migration runner.

Use `connection()` / `cursor()` for application queries. Migrations use a
dedicated connection (not the pool) and are invoked via:

    python -m app.db migrate
    python -m app.db status
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import ConfigError, Settings, load_settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_FILENAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
# Arbitrary lock key unique to this project — not a Postgres OID.
ADVISORY_LOCK_KEY = 0x454E474C  # 'ENGL'

_pool: ConnectionPool | None = None


def _get_pool(settings: Settings | None = None) -> ConnectionPool:
    """Return the shared pool, opening it lazily on first use."""
    global _pool
    if _pool is None:
        cfg = settings or load_settings()
        _pool = ConnectionPool(
            conninfo=cfg.database_url,
            min_size=cfg.db_pool_min,
            max_size=cfg.db_pool_max,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        logger.info(
            "Opened DB pool min=%s max=%s dsn=%s",
            cfg.db_pool_min,
            cfg.db_pool_max,
            cfg.database_url_for_logs(),
        )
    return _pool


def close_pool() -> None:
    """Close the shared pool if it was opened. Safe to call more than once."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection. Callers must not close it themselves."""
    with _get_pool().connection() as conn:
        yield conn


@contextmanager
def cursor() -> Iterator[psycopg.Cursor]:
    """Yield a cursor on a pooled connection, committing on clean exit."""
    with connection() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()


def _discover_migrations() -> list[tuple[int, Path]]:
    """Return (version, path) pairs sorted by version. Rejects bad names/dupes."""
    if not MIGRATIONS_DIR.is_dir():
        raise RuntimeError(f"migrations directory not found: {MIGRATIONS_DIR}")

    found: dict[int, Path] = {}
    bad_names: list[str] = []
    duplicates: list[str] = []

    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or path.suffix != ".sql":
            continue
        match = MIGRATION_FILENAME.match(path.name)
        if not match:
            bad_names.append(path.name)
            continue
        version = int(match.group(1))
        if version in found:
            duplicates.append(
                f"{version:03d} -> {found[version].name} and {path.name}"
            )
            continue
        found[version] = path

    problems: list[str] = []
    if bad_names:
        problems.append(
            "filename(s) not matching NNN_name.sql: " + ", ".join(bad_names)
        )
    if duplicates:
        problems.append("duplicate version number(s): " + "; ".join(duplicates))
    if problems:
        raise RuntimeError("; ".join(problems))

    return sorted(found.items(), key=lambda item: item[0])


def _ensure_schema_version(conn: psycopg.Connection) -> None:
    """Create schema_version so the runner can read applied versions before 001."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def _applied_versions(conn: psycopg.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {int(row[0]) for row in rows}


def migrate(settings: Settings | None = None) -> list[int]:
    """Apply pending migrations. Returns the list of newly applied versions."""
    cfg = settings or load_settings()
    migrations = _discover_migrations()
    applied_now: list[int] = []

    with psycopg.connect(
        cfg.database_url,
        cursor_factory=psycopg.ClientCursor,
    ) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        try:
            _ensure_schema_version(conn)
            conn.commit()

            already = _applied_versions(conn)
            pending = [(v, p) for v, p in migrations if v not in already]

            if not pending:
                logger.info("No pending migrations.")
                return []

            for version, path in pending:
                sql = path.read_text(encoding="utf-8")
                logger.info("Applying migration %03d (%s)", version, path.name)
                try:
                    # ClientCursor (simple query protocol) allows multi-statement
                    # .sql files; the default server-side cursor does not.
                    with conn.transaction():
                        conn.execute(sql)
                        conn.execute(
                            """
                            INSERT INTO schema_version (version)
                            VALUES (%s)
                            ON CONFLICT DO NOTHING
                            """,
                            (version,),
                        )
                except Exception:
                    logger.exception(
                        "Migration %03d failed; rolled back that file only",
                        version,
                    )
                    raise
                applied_now.append(version)
                logger.info("Applied migration %03d", version)

            return applied_now
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            conn.commit()


def status(settings: Settings | None = None) -> tuple[list[int], list[int]]:
    """Return (applied, pending) version lists. Read-only."""
    cfg = settings or load_settings()
    migrations = _discover_migrations()
    all_versions = [v for v, _ in migrations]

    with psycopg.connect(cfg.database_url) as conn:
        _ensure_schema_version(conn)
        conn.commit()
        already = _applied_versions(conn)

    applied = [v for v in all_versions if v in already]
    pending = [v for v in all_versions if v not in already]
    return applied, pending


def _print_status(applied: list[int], pending: list[int]) -> None:
    if applied:
        print("Applied: " + ", ".join(f"{v:03d}" for v in applied))
    else:
        print("Applied: (none)")
    if pending:
        print("Pending: " + ", ".join(f"{v:03d}" for v in pending))
    else:
        print("Pending: (none)")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"migrate", "status"}:
        print(
            "Usage: python -m app.db migrate|status",
            file=sys.stderr,
        )
        return 2

    command = args[0]
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        if command == "status":
            applied, pending = status(settings)
            _print_status(applied, pending)
            return 0

        applied_now = migrate(settings)
        if applied_now:
            print(
                "Applied: " + ", ".join(f"{v:03d}" for v in applied_now)
            )
        else:
            print("No pending migrations.")
        return 0
    except Exception as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
