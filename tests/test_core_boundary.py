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


# W4. `core/lexicon/` is the pure half of the lexicon: it turns text into lemmas
# and lemmas into a percentage, and it never reaches a database. Keeping it that
# way is what lets `compute_coverage` be tested without Postgres and what keeps
# `test_no_sql_outside_services` unexempted — #59 stays the only exemption in
# this file. This is a tightening of that rule, not a hole in it.
LEXICON = CORE / "lexicon"
# The offline table generator's dependencies. They are pinned in
# `scripts/requirements-lexicon-build.txt` and are NOT installed on the server,
# so an import of either from runtime code would work on a developer's machine
# and fail at boot in production.
BUILD_ONLY_LIBS = frozenset({"lemminflect", "openpyxl"})
# One reader of the lexicon tables, forever. If the seed builder parsed
# `data/lexemes.tsv` differently from the coverage path — a different header
# rule, a different filter — the ledger would silently never match what
# coverage counts, the number would read low for good, and nothing would fail.
# That is the S24 Meaning/Translation mismatch in another costume, and it
# already happened once here: a header check that matched on text rather than
# position dropped the English word `surface` with no error at all.
TOKENISER = LEXICON / "normalize.py"
LEXICON_DATA_FILES = ("lexemes.tsv", "inflections.tsv")


def test_lexicon_package_is_pure() -> None:
    """No SQL, no driver, and no build-only import under `core/lexicon/`."""
    offenders: list[str] = []
    for path in _python_files(LEXICON):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = _imported_roots(tree) & ({"psycopg", "psycopg_pool"} | BUILD_ONLY_LIBS)
        if hit:
            offenders.append(f"{rel}: imports {', '.join(sorted(hit))}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_sql(node.value):
                    offenders.append(f"{rel}:{node.lineno}: SQL")
    assert offenders == [], (
        "core/lexicon/ is pure: every query lives in core/services/lexicon.py, "
        "and lemminflect/openpyxl are build-only (CLAUDE.md §2): "
        + "; ".join(offenders)
    )


# W8. `core/syllabus/` is the pure half of the 24-week road: constants, the unit
# state machine, and the validation that decides whether authored content may
# ship. `core/services/syllabus.py` holds every query. Like `core/lexicon/` and
# `core/items/` it is NOT under `core/services/`, so `test_no_sql_outside_services`
# already covers it with zero new exemptions -- #59 stays the only one.
SYLLABUS = CORE / "syllabus"
# The single door to the two committed content files, exactly as `normalize.py`
# is for the lexicon's.
SYLLABUS_CONTENT = SYLLABUS / "content.py"
SYLLABUS_DATA_FILES = ("syllabus_units.json", "syllabus_lexemes.tsv")


def test_syllabus_package_is_pure() -> None:
    """No SQL and no driver under `core/syllabus/`."""
    offenders: list[str] = []
    for path in _python_files(SYLLABUS):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = _imported_roots(tree) & ({"psycopg", "psycopg_pool"} | BUILD_ONLY_LIBS)
        if hit:
            offenders.append(f"{rel}: imports {', '.join(sorted(hit))}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_sql(node.value):
                    offenders.append(f"{rel}:{node.lineno}: SQL")
    assert offenders == [], (
        "core/syllabus/ is pure: every query lives in core/services/syllabus.py "
        "(CLAUDE.md §2): " + "; ".join(offenders)
    )


def test_only_the_content_loader_reads_the_syllabus_data_files() -> None:
    """`core/syllabus/content.py` is the single door to the two content files.

    The same rule `test_only_the_tokeniser_reads_the_lexicon_data_files` holds
    for `data/lexemes.tsv`, and for the same reason: what drifts is the PARSE.
    One module reads the files and every other call site goes through it, so a
    second reader cannot quietly disagree about what a row means.

    `scripts/build_syllabus_lexemes.py` WRITES one of them and is outside the
    scanned trees, which is the same position `scripts/build_lexicon.py` holds.
    """
    offenders: list[str] = []
    for root in (CORE, APPS):
        for path in _python_files(root):
            if path == SYLLABUS_CONTENT:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            prose = _docstring_ids(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in prose:
                    continue
                if not isinstance(node.value, str):
                    continue
                if _names_a_data_file(node.value, SYLLABUS_DATA_FILES):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "core/syllabus/content.py is the only module that may read the syllabus "
        "content files -- a second parser is a second answer: "
        + "; ".join(offenders)
    )


# W5. `core/items/` is the pure half of the item validator, the same shape
# `core/lexicon/` is: it turns a draft into a verdict without reaching a
# database. `core/services/items.py` holds every query. Because `core/items/` is
# NOT under `core/services/`, `test_no_sql_outside_services` already covers it
# with **zero new exemptions** -- #59 stays the only one in this file.
ITEMS = CORE / "items"
# The two deliberately impure modules, named so nobody has to guess. `gates.py`
# is where the model-required gates live; `verify.py` is the human-run
# verification. They are exempt from the LLM/speech rule below and from nothing
# else -- in particular they may not carry SQL.
ITEMS_MODEL_CALLERS = {ITEMS / "gates.py", ITEMS / "verify.py"}

# W7. `core/cards/fsrs.py` is the only door to the scheduler, for the same
# reason `core/passkeys.py` is the only door to WebAuthn and `core/llm.py` the
# only door to a model provider: swapping the library must be one file, and
# duplicated construction drifts where tests cannot see it.
CARDS = CORE / "cards"
FSRS_WRAPPER = CARDS / "fsrs.py"
FSRS_LIBS = frozenset({"fsrs"})


def test_items_package_is_pure() -> None:
    """No SQL and no driver anywhere; no `core.llm`/`core.speech` outside two.

    If a query appeared here it would force the first new boundary exemption
    since #59, which `test_no_sql_outside_services`'s own docstring refuses. And
    if `core.llm` leaked into `checks.py` the deterministic half would stop
    being testable without a network, which is the property that lets the whole
    fixture set run under `netguard`.
    """
    offenders: list[str] = []
    for path in _python_files(ITEMS):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots = _imported_roots(tree)
        modules = _imported_modules(tree)
        if roots & {"psycopg", "psycopg_pool"}:
            offenders.append(f"{rel}: imports a database driver")
        if path not in ITEMS_MODEL_CALLERS:
            reaching = {m for m in modules if m in {"core.llm", "core.speech"}}
            if reaching:
                offenders.append(f"{rel}: imports {', '.join(sorted(reaching))}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_sql(node.value):
                    offenders.append(f"{rel}:{node.lineno}: SQL")
    assert offenders == [], (
        "core/items/ is pure: every query lives in core/services/items.py and "
        "only gates.py/verify.py may reach a provider (CLAUDE.md §2): "
        + "; ".join(offenders)
    )


def test_exactly_one_module_writes_an_item() -> None:
    """"No item reaches a learner without a validation record", structurally.

    Three layers hold that claim up: migration 012's `validation JSONB NOT NULL`
    plus its `? 'deterministic'` CHECK, `insert_item`'s refusal to write a
    report that is not `ok`, and this. **This is the layer that survives a
    refactor** -- the other two can be bypassed by a second INSERT written
    somewhere else, and nothing would fail.
    """
    writers: set[str] = set()
    for root in (CORE, APPS):
        for path in _python_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            # Prose describing the rule is not a violation of it. This test
            # caught its own docstring on the first run, which is the same trap
            # `test_only_the_tokeniser_reads_the_lexicon_data_files` solves.
            prose = _docstring_ids(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in prose:
                    continue
                if not isinstance(node.value, str):
                    continue
                statement = " ".join(node.value.upper().split())
                if re.search(r"\bINSERT INTO ITEMS\b", statement):
                    writers.add(str(path.relative_to(REPO_ROOT)))
    assert writers == {"packages/core/services/items.py"}, (
        "exactly one module may INSERT INTO items: " + ", ".join(sorted(writers))
    )


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Docstrings naming a file are prose about it, not a read of it."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _names_a_data_file(text: str, names: tuple[str, ...]) -> bool:
    """Does this string reference one of `names` as a filename, not as a suffix?

    A plain `in` test is too loose, and W8 found out how: `data/lexemes.tsv` is
    a substring of `data/syllabus_lexemes.tsv`, so the lexicon rule fired on the
    syllabus loader for reading its own file. The boundary is what makes the
    match about a FILENAME rather than about the characters in one.
    """
    return any(
        re.search(r"(?:^|[^0-9A-Za-z_])" + re.escape(name), text) for name in names
    )


def test_only_the_tokeniser_reads_the_lexicon_data_files() -> None:
    """`normalize.py` is the single door to `data/lexemes.tsv`.

    Narrower than "no second word regex anywhere", and deliberately so: this
    tree has several legitimate tokenisers that have nothing to do with English
    vocabulary — migration filenames, CSV headers, slugs — and a rule that
    caught those would need an exemption list long enough to make it a rubber
    stamp, which is exactly what `test_no_sql_outside_services` refuses to be.

    What actually drifts is the *parse*, and this catches that: one module
    reads the tables, and every other call site goes through it. The identity
    assertion in `test_lexicon_coverage.py` covers the other half — that the
    seed builder and the coverage path hold the same function object.
    """
    offenders: list[str] = []
    for root in (CORE, APPS):
        for path in _python_files(root):
            if path == TOKENISER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            prose = _docstring_ids(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in prose:
                    continue
                if not isinstance(node.value, str):
                    continue
                if _names_a_data_file(node.value, LEXICON_DATA_FILES):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "core/lexicon/normalize.py is the only module that may read the "
        "lexicon data files — a second parser is a second answer: "
        + "; ".join(offenders)
    )


def test_the_build_only_dependencies_stay_out_of_the_core_mirror() -> None:
    r"""`lemminflect` and `openpyxl` generate `data/*.tsv` on a developer's
    machine and are never installed by the deployment sequence. They live in
    `scripts/requirements-lexicon-build.txt`, which nothing here reads.

    They must not appear in requirements.txt at all. Its parser only moves its
    cursor on a comment matching `^#\s*(apps/|packages/|tests\b)`, so a
    `# dev tooling` header neither opens nor closes a section: a dev block
    placed after the `# packages/core` lines would be collected as a core
    dependency, and one placed at the end would pass only because of where it
    sits, until someone reordered the file.
    """
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for library in sorted(BUILD_ONLY_LIBS):
        assert library not in text, f"{library} belongs in the build-only file"
    pinned = (REPO_ROOT / "scripts" / "requirements-lexicon-build.txt").read_text(
        encoding="utf-8"
    )
    for library in sorted(BUILD_ONLY_LIBS):
        assert f"{library}==" in pinned, f"{library} must be pinned, not floating"


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


# ─────────────────────────────────────────────────────────────────────────────
# W6. The single-serialiser contract, in the shape of
# `test_exactly_one_module_writes_an_item` and for the same reason: the other
# layers holding it up can each be bypassed by writing new code somewhere else,
# and nothing would fail. These two are the layer that survives a refactor.
# ─────────────────────────────────────────────────────────────────────────────

#: The only modules permitted to build a learner-visible view of an item.
#: `gates.py` shows the projection to the blind solver, `verify.py` prints it in
#: a dry run, and `core/services/items.py` serves it. A fourth would mean the
#: probe and the learner are looking at different artefacts.
PROJECTORS = {
    "packages/core/items/gates.py",
    "packages/core/items/verify.py",
    "packages/core/services/items.py",
}

#: `apps/api` may not reach any of these. The first three carry the answer; the
#: last two are the provider wrappers, and a route that calls one is holding the
#: material it is sending — which for `listening_gap` **is** the answer.
FORBIDDEN_IN_API = frozenset(
    {
        "core.items.projection",
        "core.items.schema",
        "core.items.grading",
        "core.items.response",
        "core.llm",
        "core.speech",
    }
)


def test_exactly_one_module_projects_an_item() -> None:
    """"Everything learner-visible goes through `visible_projection`", structurally.

    If a second serialiser is written — in a router, in a pydantic response
    model, in a service — the blind-solver probe stops describing what a learner
    actually sees, and **every downstream number stays green while the gate
    silently measures the wrong artefact**. That is the failure the whole item
    slice exists to prevent, one level up, and it is the one most likely to
    happen by accident: a renderer that needs one more field is a one-line
    change in a route.

    W10 inherits this rather than building its own. `GET /session/today`
    hydrates five blocks through `core.services.items.presentations_for`, which
    is in the set below; a serialiser of its own would not be.
    """
    projectors: set[str] = set()
    for root in (CORE, APPS):
        for path in _python_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            # Prose describing the rule is not a violation of it — the same
            # trap `test_exactly_one_module_writes_an_item` documents.
            prose = _docstring_ids(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and id(node) in prose:
                    continue
                if isinstance(node, ast.Name) and node.id == "visible_projection":
                    projectors.add(str(path.relative_to(REPO_ROOT)))
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr == "visible_projection"
                ):
                    projectors.add(str(path.relative_to(REPO_ROOT)))
    assert projectors == PROJECTORS, (
        "exactly three modules may build a learner-visible view: "
        f"unexpected {sorted(projectors - PROJECTORS)}, "
        f"missing {sorted(PROJECTORS - projectors)}"
    )


def test_the_api_never_reaches_the_hidden_half_of_an_item() -> None:
    """A route cannot leak what it was never given — but only if it stays that way.

    `core.services.items` hands `apps/api` an `ItemPresentation`, which carries
    no answer, no accepted variants, no transcript, no rubric, no wrong index
    and no correction. That is a capability rather than a rule. This test is
    what stops the capability being routed around by importing the pure modules
    directly and rebuilding the envelope by hand.

    The two provider wrappers are here for the same reason and it is worth
    stating, because it looks like a different rule: a route that calls
    `speech.synthesize` itself must hold the text it is synthesising, and for
    `dictation` and `listening_gap` that text **is the answer**, in plain Python,
    inside `apps/api`. One exception handler that echoes context, one debug log
    line, one 500 body, and it is on the wire. So `item_audio` synthesises in
    the service and the route receives bytes.
    """
    offenders: list[str] = []
    for path in _python_files(APPS / "api"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = _imported_modules(tree) & FORBIDDEN_IN_API
        if hit:
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "apps/api receives ItemPresentation and bytes; it may not import the "
        "modules that carry an answer or reach a provider: " + "; ".join(offenders)
    )


def test_only_the_fsrs_wrapper_imports_the_scheduler() -> None:
    """W7: one door for py-fsrs.

    A service or a route that imported `fsrs` directly would put the library's
    `Card` and `Rating` objects into the layer above it, and PRD §5's scheduler
    would stop having a single place to review — or to replace. It would also
    make `enable_fuzzing=False` a per-call-site convention rather than a
    property of the system: one forgotten flag and every due date that call site
    produces becomes irreproducible, which no test would catch because the fuzz
    is small.
    """
    offenders: list[str] = []
    for root in (CORE, APPS):
        for path in _python_files(root):
            if path == FSRS_WRAPPER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hit = _imported_roots(tree) & FSRS_LIBS
            if hit:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}: {', '.join(sorted(hit))}")
    assert offenders == [], (
        "only packages/core/cards/fsrs.py may import py-fsrs: " + "; ".join(offenders)
    )


def test_cards_package_is_pure() -> None:
    """No SQL and no driver in `core/cards/`; every query is in the service.

    `migrate_chunks.py` is the human-run module of this package — the same
    standing `core.items.seed_fixtures` has — and it reaches the database only
    through `core.db.connection` and `core.services.cards.create_card`, never by
    holding a query of its own. So the purity rule stays unexempted and #59
    remains the only boundary exemption in the project.
    """
    offenders: list[str] = []
    for path in _python_files(CARDS):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imported_roots(tree) & {"psycopg", "psycopg_pool"}:
            offenders.append(f"{rel}: imports a database driver")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_sql(node.value):
                    offenders.append(f"{rel}:{node.lineno}: SQL")
    assert offenders == [], (
        "core/cards/ is pure: every query lives in core/services/cards.py "
        "(CLAUDE.md §2): " + "; ".join(offenders)
    )


def test_the_api_holds_no_scheduler_state_of_its_own() -> None:
    """`apps/api` may build a `CardState` for display, never a schedule.

    The route computes the four intervals through `core.cards.fsrs.review`,
    which copies the card before touching it — so asking "what would Easy do"
    cannot advance anything. What it must not do is write one: every persisted
    schedule goes through `core.services.cards.grade_card`, so there is exactly
    one place where a due date is decided and logged together.
    """
    offenders: list[str] = []
    for path in _python_files(APPS / "api"):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "UPDATE cards" in node.value or "INSERT INTO card_reviews" in node.value:
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "apps/api must not write a schedule; grade_card is the only writer: "
        + "; ".join(offenders)
    )
