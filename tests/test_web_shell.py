"""W1b: invariants of the web shell that are cheap to break and silent to lose.

The Python suite is the only suite this repo runs, so the handful of rules
that would otherwise depend on someone remembering them live here. These are
source-level checks, not a browser: the shell itself is a human check (open
it on a phone and install it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "apps" / "web"

# Everything we wrote; never node_modules, .next, or the generated Workbox
# service worker (which uses storage APIs of its own and is not ours).
SOURCE_DIRS = ("app", "components", "lib")
SOURCE_SUFFIXES = {".ts", ".tsx", ".css", ".mjs"}


def _source_files() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        root = WEB / directory
        if not root.is_dir():
            continue
        files += [
            path
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.suffix in SOURCE_SUFFIXES
        ]
    return files


def test_the_web_app_exists() -> None:
    """A guard for the checks below: an empty glob passes everything."""
    assert (WEB / "package.json").is_file()
    assert len(_source_files()) >= 8


# `/* ... */` and `// ...`. Stripped before scanning so a comment explaining
# why the app does not use browser storage is not read as using it — the same
# trap `test_core_boundary.py` avoids by parsing instead of grepping.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")


def _without_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def test_no_browser_storage_anywhere() -> None:
    """CLAUDE.md §5 — nothing about a learner is kept in the browser.

    This is also why dark mode follows the system rather than a toggle: a
    toggle has to remember its setting, and the two places to remember it are
    the two banned here.
    """
    offenders: list[str] = []
    for path in _source_files():
        text = _without_comments(path.read_text(encoding="utf-8"))
        for name in ("localStorage", "sessionStorage"):
            if name in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert offenders == [], (
        "apps/web may not use browser storage: " + "; ".join(offenders)
    )


def test_manifest_declares_an_installable_app() -> None:
    source = (WEB / "app" / "manifest.ts").read_text(encoding="utf-8")
    assert '"standalone"' in source, "display must be standalone to install"
    for key in ("name", "short_name", "start_url", "icons", "theme_color"):
        assert f"{key}:" in source, f"manifest is missing {key}"


def test_every_manifest_icon_file_exists() -> None:
    """A manifest pointing at a missing icon installs a blank home-screen tile."""
    source = (WEB / "app" / "manifest.ts").read_text(encoding="utf-8")
    referenced = re.findall(r'src:\s*"([^"]+)"', source)
    assert referenced, "manifest declares no icons"
    for src in referenced:
        icon = WEB / "public" / src.lstrip("/")
        assert icon.is_file(), f"manifest references a missing icon: {src}"
        assert icon.stat().st_size > 0


def test_bottom_nav_has_the_four_places_the_app_has() -> None:
    """Today · Map · Review · Progress — and a page behind each one."""
    source = (WEB / "components" / "bottom-nav.tsx").read_text(encoding="utf-8")
    entries = re.findall(r'href:\s*"([^"]+)",\s*label:\s*"([^"]+)"', source)
    assert entries == [
        ("/", "Today"),
        ("/map", "Map"),
        ("/review", "Review"),
        ("/progress", "Progress"),
    ]
    for href, _ in entries:
        page = (WEB / "app" / "(app)" / href.lstrip("/") / "page.tsx")
        assert page.is_file(), f"nav points at {href} with no page"


def test_today_offers_exactly_one_action() -> None:
    """PRD §4: home resolves to one button, and it is disabled until W10."""
    source = (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    assert "Start today" in source
    assert source.count("<Button") == 1
    assert "disabled" in source


def test_the_api_client_reads_its_base_url_from_the_environment() -> None:
    """A hardcoded localhost is a shell that works only on the machine that built it."""
    source = (WEB / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_API_URL" in source
    example = (WEB / ".env.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_API_URL" in example


def test_the_storage_check_reads_code_not_prose() -> None:
    """Prove the scanner is neither blind nor tripped by its own comments."""
    assert "localStorage" not in _without_comments(
        "/* we never touch localStorage */\nconst a = 1;\n"
    )
    assert "localStorage" not in _without_comments(
        "// localStorage is banned\nconst a = 1;\n"
    )
    assert "localStorage" in _without_comments(
        'const t = localStorage.getItem("token"); // read the token\n'
    )
