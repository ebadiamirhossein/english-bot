"""Architecture boundaries, enforced by AST rather than by convention.

CLAUDE.md §2 states three rules that until W1 were satisfied only by habit.
Every check here parses the file, so a docstring mentioning "telegram"
passes and `import telegram.ext as x` fails — the exact pair a grep gets
backwards.
"""

from __future__ import annotations

import ast
import re
import tomllib
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

# W2. Not a "provider" in the LLM sense, but the same rule for the same reason:
# one door, so the library's types stay out of the services and the routes and
# swapping it is one file. `cbor2` and `cryptography` are its dependencies and
# are covered by the same check.
WEBAUTHN_LIBS = frozenset({"webauthn", "cbor2"})
WEBAUTHN_WRAPPER = CORE / "passkeys.py"

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


def test_only_the_passkeys_wrapper_imports_webauthn() -> None:
    """W2: one door for the WebAuthn library.

    A route or a service that imported ``webauthn`` directly would put the
    library's structs into the layer above it, and the verification code — the
    most security-critical code in this project — would stop having a single
    place to review.
    """
    offenders: list[str] = []
    for root in (CORE, APPS):
        for path in _python_files(root):
            if path == WEBAUTHN_WRAPPER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hit = _imported_roots(tree) & WEBAUTHN_LIBS
            if hit:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "only packages/core/passkeys.py may import the WebAuthn library: "
        + "; ".join(offenders)
    )


# requirements.txt is organised by which app needs a line: "# apps/bot",
# "# packages/core", "# apps/api (W1b)", "# tests — ...".
_SECTION_HEADER = re.compile(r"^#\s*(apps/|packages/|tests\b)")


def _dependency_names(specifiers: list[str]) -> set[str]:
    """Bare distribution names out of a list of requirement specifiers."""
    names: set[str] = set()
    for raw in specifiers:
        spec = raw.split("#", 1)[0].strip()
        if not spec:
            continue
        name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def test_requirements_mirror_core_dependencies() -> None:
    """``packages/core/pyproject.toml`` is the authority; the mirror must agree.

    ``requirements.txt`` carries a ``# packages/core`` block that repeats
    core's dependencies for the server venv. Two unchecked declarations of one
    dependency drift, and that is how a version pin quietly becomes advisory —
    so the mirror is asserted rather than trusted.

    The authority matters in the other direction too: anything ``core`` imports
    must be declared in its own ``pyproject.toml``, or ``pip install -e
    packages/core`` produces a package that cannot import itself.
    """
    pyproject = tomllib.loads(
        (CORE / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = _dependency_names(pyproject["project"]["dependencies"])

    lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    mirrored: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Only a section header moves the cursor. A note inside a section
            # is still a comment, and treating every `#` line as a boundary
            # would silently empty the block the moment someone explains it.
            if _SECTION_HEADER.match(stripped):
                in_block = stripped.lower().startswith("# packages/core")
            continue
        if in_block and stripped:
            mirrored.append(stripped)

    assert _dependency_names(mirrored) == declared, (
        "requirements.txt's '# packages/core' block and "
        "packages/core/pyproject.toml declare different dependencies"
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


# W1b. The API runs several uvicorn workers and each one is a whole process.
# A scheduler imported there runs every job once per worker: the streak
# rollover fires four times, the monthly reset fires four times (W0 risk R3).
# The worker process is the only place APScheduler belongs.
FORBIDDEN_IN_API = frozenset({"apscheduler", "telegram"})
# Neither new app may reach sideways into another app. `core` is the only
# shared code. (Known issue #60 is the same rule pointing the other way —
# core → apps — and stays open; widening this test to cover it would fail on
# pre-existing code, which is a decision for its own slice.)
SIBLING_APPS = {
    APPS / "api": ("apps.worker", "apps.bot"),
    APPS / "worker": ("apps.api", "apps.bot"),
}


def _imported_modules(tree: ast.AST) -> set[str]:
    """Full dotted module name of every import, not just its root."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module)
    return modules


def test_api_imports_no_scheduler() -> None:
    offenders: list[str] = []
    for path in _python_files(APPS / "api"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = _imported_roots(tree) & FORBIDDEN_IN_API
        if hit:
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "apps/api must not import a scheduler or Telegram — one scheduler "
        "per uvicorn worker means every job fires N times: " + "; ".join(offenders)
    )


def test_api_does_not_import_the_worker_job_table() -> None:
    """Importing the job table is how registration leaks into the web process."""
    offenders: list[str] = []
    for root, banned in SIBLING_APPS.items():
        if not root.is_dir():
            continue
        for path in _python_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            modules = _imported_modules(tree)
            hit = {
                module
                for module in modules
                for prefix in banned
                if module == prefix or module.startswith(prefix + ".")
            }
            if hit:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "apps/api, apps/worker and apps/bot share code through packages/core "
        "and nowhere else: " + "; ".join(offenders)
    )


def test_migrations_dir_is_repo_root() -> None:
    """core.db must find the numbered migrations after the W1 move."""
    from core.db import MIGRATIONS_DIR

    assert MIGRATIONS_DIR == MIGRATIONS
    assert MIGRATIONS_DIR.is_dir()
    assert sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))[0].startswith("001")
