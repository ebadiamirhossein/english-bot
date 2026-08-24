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


# W2 narrows the blanket ban to exactly one exception, decided at W1c: the
# theme preference, which is a property of the device rather than of the
# learner. Everything else about a learner — session, progress, content — stays
# on the server (CLAUDE.md §5).
#
# The narrowing is an allow-list of ONE path and ONE key, not a deleted rule.
THEME_MODULE = "apps/web/lib/theme.ts"
THEME_KEY_CONSTANT = "THEME_STORAGE_KEY"

# Every way of reaching localStorage that this app is allowed to use. Anything
# else — `localStorage[...]`, `window.localStorage`, a destructured alias — is
# not matched here and therefore falls through to the offender list.
_STORAGE_CALL = re.compile(
    r"localStorage\s*\.\s*(getItem|setItem|removeItem)\s*\(\s*([^,)]+)"
)
_ANY_LOCAL_STORAGE = re.compile(r"localStorage")


def _storage_offenders(sources: dict[str, str]) -> list[str]:
    """Files that use browser storage in a way the narrowed rule forbids.

    Takes a {relative path: source} mapping so the meta-test below can feed it
    deliberate violations without writing files.
    """
    offenders: list[str] = []
    for rel, raw in sorted(sources.items()):
        text = _without_comments(raw)

        # sessionStorage stays banned outright, everywhere, no exceptions.
        if "sessionStorage" in text:
            offenders.append(f"{rel}: sessionStorage")

        if not _ANY_LOCAL_STORAGE.search(text):
            continue
        if rel != THEME_MODULE:
            offenders.append(f"{rel}: localStorage")
            continue

        # Inside the one allowed file, only the theme key, and only through the
        # named constant. A future localStorage.setItem("session", token) here
        # is still a violation.
        calls = _STORAGE_CALL.findall(text)
        if len(calls) != len(_ANY_LOCAL_STORAGE.findall(text)):
            offenders.append(f"{rel}: localStorage reached in an unchecked way")
        for _, argument in calls:
            if THEME_KEY_CONSTANT not in argument:
                offenders.append(
                    f"{rel}: localStorage key {argument.strip()!r} is not "
                    f"{THEME_KEY_CONSTANT}"
                )
    return offenders


def _web_sources() -> dict[str, str]:
    return {
        str(path.relative_to(REPO_ROOT)): path.read_text(encoding="utf-8")
        for path in _source_files()
    }


def test_no_browser_storage_except_the_theme() -> None:
    """CLAUDE.md §5 — nothing about a learner is kept in the browser.

    The single exception is which colour scheme the device is set to, which is
    why `lib/theme.ts` is hand-rolled rather than `next-themes`: a dependency
    would put the one permitted write inside node_modules, where this check
    cannot see it, and the exception would be unbounded in practice.
    """
    assert _storage_offenders(_web_sources()) == [], (
        "apps/web may use browser storage only in "
        f"{THEME_MODULE}, only under {THEME_KEY_CONSTANT}: "
        + "; ".join(_storage_offenders(_web_sources()))
    )


def test_the_theme_key_is_what_the_allow_list_says_it_is() -> None:
    """The allow-list names a constant; this pins the constant's value.

    Without this, renaming the constant's value to "session" would pass every
    check above.
    """
    source = (WEB / "lib" / "theme.ts").read_text(encoding="utf-8")
    assert re.search(
        rf'{THEME_KEY_CONSTANT}\s*=\s*"theme"', source
    ), "the one permitted storage key must be exactly \"theme\""


def test_the_narrowed_storage_rule_still_catches_a_real_violation() -> None:
    """CLAUDE.md §3 rule 4, applied to the rule itself.

    A narrowed check that no longer fails on anything is a deleted check with
    extra steps. Each case below is a violation the blanket ban used to catch
    and the narrowed one must still catch.
    """
    # localStorage in an ordinary component: still banned.
    assert _storage_offenders(
        {"apps/web/components/x.tsx": 'localStorage.getItem("theme");'}
    )
    # sessionStorage anywhere, including the allowed file: still banned.
    assert _storage_offenders({THEME_MODULE: 'sessionStorage.getItem("theme");'})
    # A second key inside the allowed file: banned.
    assert _storage_offenders(
        {THEME_MODULE: 'localStorage.setItem("session", token);'}
    )
    # Reaching storage some other way inside the allowed file: banned.
    assert _storage_offenders({THEME_MODULE: 'window.localStorage.clear();'})
    # And the shape the app actually uses: allowed.
    assert (
        _storage_offenders(
            {
                THEME_MODULE: (
                    "localStorage.getItem(THEME_STORAGE_KEY);"
                    "localStorage.setItem(THEME_STORAGE_KEY, theme);"
                )
            }
        )
        == []
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


def test_the_auth_screens_exist_and_the_app_shell_is_guarded() -> None:
    """W2's two new screens, and the guard in front of everything else.

    A signed-out learner opening /progress directly must land on sign-in, and
    the guard is what does that — the API refuses the data either way, but an
    unguarded shell renders an empty page instead of a way back in.
    """
    for page in ("sign-in", "enrol"):
        assert (WEB / "app" / "(auth)" / page / "page.tsx").is_file(), page
    layout = (WEB / "app" / "(app)" / "layout.tsx").read_text(encoding="utf-8")
    assert "RequireSession" in layout, "the app shell is not behind the guard"


def test_the_guard_renders_no_protected_content_while_checking() -> None:
    """The flash-of-protected-content answer.

    While the session check is in flight the guard renders a neutral splash and
    not the page — not even a skeleton, which is still the shape of protected
    content. At W2 the screens hold no learner data so this is cosmetic; from
    W3 it is real.
    """
    source = (WEB / "components" / "require-session.tsx").read_text(
        encoding="utf-8"
    )
    body = _without_comments(source)
    checking = body.index("state.kind !== \"in\"")
    guarded = body.index("SessionContext.Provider")
    assert checking < guarded, "children must render only after the check passes"


def test_the_theme_script_runs_before_paint() -> None:
    """A toggle that flashes the wrong palette on every load is a broken toggle.

    The script has to be inline in <head>; anything that waits for React paints
    light first and then flips.
    """
    layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "THEME_INIT_SCRIPT" in layout
    assert "<head>" in layout
    assert "suppressHydrationWarning" in layout, (
        "the script mutates <html> before React hydrates; without this the "
        "console fills with hydration warnings on every load"
    )


def test_dark_mode_is_class_driven_not_media_query_driven() -> None:
    """The half of the toggle that is easy to get wrong.

    If `@custom-variant dark` still keyed off `prefers-color-scheme`, the
    system preference would keep overriding the choice and the toggle would
    visibly do nothing.
    """
    # Comments stripped first: the block explaining *why* the media query was
    # dropped names it, and a scanner that reads prose as code is the trap
    # test_the_storage_check_reads_code_not_prose exists to document.
    css = _without_comments(
        (WEB / "app" / "globals.css").read_text(encoding="utf-8")
    )
    assert "@custom-variant dark (&:where(.dark, .dark *))" in css
    assert ":root.dark {" in css
    assert "@media (prefers-color-scheme: dark)" not in css, (
        "the media query must not also define the palette — the class is the "
        "single source of truth and the init script resolves 'system' onto it"
    )


def test_the_frontend_writes_no_base64url_by_hand() -> None:
    """The one piece of frontend logic whose failure is silent.

    A mangled challenge or credential id surfaces as `NotAllowedError`, which
    is also what the browser throws when the learner cancels — so a bug looks
    exactly like someone changing their mind. The native JSON bridge removes
    the code entirely; this fails if it comes back.
    """
    source = _without_comments(
        (WEB / "lib" / "webauthn.ts").read_text(encoding="utf-8")
    )
    for banned in ("atob", "btoa", "Uint8Array", "ArrayBuffer", "charCodeAt"):
        assert banned not in source, (
            f"{banned} means hand-rolled binary conversion is back; use "
            "PublicKeyCredential.parse*FromJSON() and credential.toJSON()"
        )
    assert "parseCreationOptionsFromJSON" in source
    assert "parseRequestOptionsFromJSON" in source
    assert "toJSON()" in source


# W2a. These four are **weaker than they look, and deliberately so.** There is no
# JavaScript test runner (#67), so they read source rather than rendering a
# component and clicking it. They would catch the shape of the W2 defect —
# "no session" collapsing into "no answer" — coming back, and they would not
# catch a new way of losing the same distinction. The real check is a phone.


def test_the_session_check_distinguishes_three_outcomes() -> None:
    """The W2a bug: a first visit rendered as a connectivity failure.

    `GET /health/auth` answers 200 with a literal `null` for an anonymous
    caller, which is a complete and successful answer. A nullable return type
    cannot express the difference between that and "the request failed", so the
    difference was lost at the only place left to notice it — a `catch`.
    """
    source = _without_comments((WEB / "lib" / "api.ts").read_text(encoding="utf-8"))
    for outcome in ('"signed-in"', '"anonymous"', '"unreachable"'):
        assert outcome in source, f"lib/api.ts does not name the {outcome} outcome"
    assert "SessionState" in source


def test_the_connectivity_message_is_unreachable_from_a_null_body() -> None:
    """The banner may only come from a genuine failure.

    Asserted structurally: the connectivity string is produced inside
    `request()` and inside `getAuthHealth`'s `catch`, and the branch that turns
    a `null` body into a value must not be able to reach it. If the `anonymous`
    result and the connectivity text ever appear in the same expression again,
    this fails.
    """
    source = _without_comments((WEB / "lib" / "api.ts").read_text(encoding="utf-8"))
    start = source.index("export async function getAuthHealth")
    body = source[start:]
    anonymous_line = next(
        line for line in body.splitlines() if '"anonymous"' in line
    )
    assert "Could not reach" not in anonymous_line
    assert "unreachable" not in anonymous_line


def test_get_auth_health_does_not_reject() -> None:
    """A rejected promise is what let the anonymous case fall into an error path.

    Every outcome comes back as a value the caller has to name, so
    `.catch(() => signedOut)` is no longer a thing anyone can write by accident.
    """
    source = _without_comments((WEB / "lib" / "api.ts").read_text(encoding="utf-8"))
    body = source[source.index("export async function getAuthHealth") :]
    assert "try {" in body and "catch" in body, (
        "getAuthHealth must absorb the failure and return it as a value"
    )


def test_an_unreachable_api_does_not_redirect_to_sign_in() -> None:
    """Redirecting on "API down" tells the learner to fix the wrong problem.

    Before W2a the guard sent both the anonymous visitor and the unreachable
    API to `/sign-in` — the right destination for one of them, by accident. And
    signing in is precisely the thing that cannot work while the API is down.
    """
    source = _without_comments(
        (WEB / "components" / "require-session.tsx").read_text(encoding="utf-8")
    )
    assert '"unreachable"' in source, "the guard does not model the third outcome"
    unreachable_branch = source[source.index('kind: "unreachable"') :]
    assert 'router.replace("/sign-in")' not in unreachable_branch.split("}")[0]
    assert "Try again" in source, "an unreachable state needs a way out"


def test_the_write_screen_exists_and_is_behind_the_session_guard() -> None:
    """W3's "Write anything" surface. It writes to the error journal, so it
    lives under `(app)` — everything there is behind `RequireSession`."""
    page = WEB / "app" / "(app)" / "write" / "page.tsx"
    assert page.is_file()
    layout = (WEB / "app" / "(app)" / "layout.tsx").read_text(encoding="utf-8")
    assert "RequireSession" in layout


def test_the_correction_bounds_match_the_service() -> None:
    """The frontend mirrors the bounds so a learner is not made to round-trip
    to find out a sentence was too short. Mirrors drift, so this pins them to
    the Python constants (rule 5 — the expected values are read from the other
    side, not from the file under test)."""
    from core.services.correction import MAX_CHARS, MIN_CHARS

    source = (WEB / "lib" / "limits.ts").read_text(encoding="utf-8")
    assert f"CORRECTION_MIN_CHARS = {MIN_CHARS};" in source
    assert f"CORRECTION_MAX_CHARS = {MAX_CHARS};" in source


def test_the_write_screen_never_marks_what_the_learner_wrote() -> None:
    """CLAUDE.md §4 — the one screen in the product where tone matters most.

    Striking through someone's sentence is the visual form of "you failed".
    The emphasis belongs on the better version, not on the mistake.
    """
    source = _without_comments(
        (WEB / "app" / "(app)" / "write" / "page.tsx").read_text(encoding="utf-8")
    )
    for banned in ("line-through", "text-destructive", "bg-destructive"):
        assert banned not in source, f"{banned} on the correction screen"


def test_no_red_reaches_the_correction_screen() -> None:
    """The palette has no red in it by design (apps/web/README.md), and this is
    exactly the screen someone would be tempted to add one to."""
    source = _without_comments(
        (WEB / "app" / "(app)" / "write" / "page.tsx").read_text(encoding="utf-8")
    )
    for banned in ("text-red", "bg-red", "border-red", "#f00", "rgb(255,0,0)"):
        assert banned not in source


def test_today_still_offers_one_button() -> None:
    """W3 adds a link to /write, not a second action. PRD §4: home resolves to
    one decision a day, and the session runner is that decision from W10."""
    source = (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    assert source.count("<Button") == 1
    assert 'href="/write"' in source


def test_the_correction_request_is_json_encoded() -> None:
    """A form encoding would make this a simple request, remove the CORS
    preflight, and remove the CSRF barrier the API relies on. The route answers
    415; this is the client half of the same rule."""
    source = (WEB / "lib" / "api.ts").read_text(encoding="utf-8")
    body = source[source.index("export function requestCorrection") :]
    assert '"Content-Type": "application/json"' in body
    assert "JSON.stringify" in body
    assert "FormData" not in source


def test_the_api_client_sends_credentials_on_every_call() -> None:
    """The session cookie is on a different origin from the page.

    Without `credentials: "include"` the browser sends no cookie and every
    request after sign-in is anonymous — a failure that cannot happen on a
    same-origin dev setup and appears only on the real two-origin deployment.
    """
    for module in ("api.ts", "webauthn.ts"):
        source = (WEB / "lib" / module).read_text(encoding="utf-8")
        assert 'credentials: "include"' in source, module


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
