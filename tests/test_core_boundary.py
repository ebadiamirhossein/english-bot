"""Architecture boundaries, enforced by AST rather than by convention.

CLAUDE.md §2 states three rules that until W1 were satisfied only by habit.
Every check here parses the file, so a docstring mentioning "telegram"
passes and `import telegram.ext as x` fails — the exact pair a grep gets
backwards.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "packages" / "core"
APPS = REPO_ROOT / "apps"
MIGRATIONS = REPO_ROOT / "migrations"

# Web/transport frameworks. `core` is imported by apps/api, apps/worker and
# apps/bot; it may never depend on any of them or on how they talk.
FORBIDDEN_IN_CORE = frozenset(
    {"fastapi", "starlette", "telegram", "uvicorn", "httpx", "requests", "aiohttp"}
)

# CLAUDE.md §2: every LLM/STT/TTS call goes through the wrappers, so swapping
# providers is one environment variable.
PROVIDER_SDKS = frozenset({"anthropic", "openai", "elevenlabs"})
WRAPPERS = frozenset({CORE / "llm.py", CORE / "speech.py"})

SQL_KEYWORDS = ("SELECT ", "INSERT INTO ", "UPDATE ", "DELETE FROM ")


def _looks_like_sql(value: str) -> bool:
    """A statement, not prose that happens to contain the word SELECT."""
    upper = " ".join(value.upper().split())
    for keyword in SQL_KEYWORDS:
        if keyword not in upper:
            continue
        if keyword == "SELECT " and " FROM " not in upper:
            continue
        if keyword == "UPDATE " and " SET " not in upper:
            continue
        return True
    return False


def _python_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    )


def _imported_roots(tree: ast.AST) -> set[str]:
    """Top-level package name of every import in the module."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (level > 0) never leave the package.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_core_imports_no_web_framework() -> None:
    offenders: list[str] = []
    for path in _python_files(CORE):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = _imported_roots(tree) & FORBIDDEN_IN_CORE
        if hit:
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "packages/core may not import a web framework, an HTTP client or "
        "Telegram (CLAUDE.md §2): " + "; ".join(offenders)
    )


def test_no_provider_sdk_outside_wrapper() -> None:
    offenders: list[str] = []
    for root in (CORE, APPS):
        for path in _python_files(root):
            if path in WRAPPERS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            roots = _imported_roots(tree)
            hit = {
                name
                for name in roots
                if name in PROVIDER_SDKS or name.startswith("azure")
            }
            if hit:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "Only core/llm.py and core/speech.py may import a provider SDK "
        "(CLAUDE.md §2): " + "; ".join(offenders)
    )


def test_no_sql_outside_services() -> None:
    """SQL lives in core/services/ and migrations/, nowhere else.

    Scope, and why it is what it is:

    * ``core/services/`` and ``migrations/`` are where SQL belongs.
    * ``core/db.py`` runs the migrations and owns ``schema_version``; its
      queries are the runner, not business logic.
    * ``core/scheduling.py`` carries ``list_candidate_users``, lifted from the
      bot scheduler at W1 with its query attached. Known issue #59: it should
      end up in a service.
    * ``apps/bot`` is excluded. Twenty-odd handlers query directly today —
      known issue #58 — and W22 deletes them with the bot. Listing them here
      as exemptions would make this test a rubber stamp.

    Everything else, including ``apps/api`` from W3, is covered. That is the
    point: a route that grows its own query fails this test on the commit
    that adds it.
    """
    exempt = {CORE / "db.py", CORE / "scheduling.py"}
    offenders: list[str] = []
    roots = [CORE, APPS]
    for root in roots:
        for path in _python_files(root):
            if path.is_relative_to(CORE / "services"):
                continue
            if path.is_relative_to(APPS / "bot"):
                continue
            if path in exempt:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant):
                    continue
                if not isinstance(node.value, str):
                    continue
                if not _looks_like_sql(node.value):
                    continue
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "SQL belongs in core/services/ or migrations/ (CLAUDE.md §2): "
        + "; ".join(offenders)
    )


def test_migrations_dir_is_repo_root() -> None:
    """core.db must find the numbered migrations after the W1 move."""
    from core.db import MIGRATIONS_DIR

    assert MIGRATIONS_DIR == MIGRATIONS
    assert MIGRATIONS_DIR.is_dir()
    assert sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))[0].startswith("001")
