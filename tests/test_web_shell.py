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


def _shipped_sources() -> dict[str, str]:
    """`_web_sources()` without the Vitest files.

    **A test that asserts a word is absent necessarily contains that word.**
    `feedback.test.tsx` checks that no wrong-answer copy says "wrong", and
    `item-card.test.tsx` checks that nothing is struck through — so a copy scan
    reading them would report both as violations and be satisfied only by
    deleting the assertions. This is the same trap `_without_comments` exists
    for, one level up: prose *about* a rule is not a breach of it, and neither
    is a test *of* it.

    Only the copy and palette scans use this. Everything structural still reads
    the whole tree.
    """
    return {
        rel: raw for rel, raw in _web_sources().items() if ".test." not in rel
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
    """PRD §4: home resolves to one button, and **W10 turns it on.**

    **The `disabled` assertion is INVERTED here, not deleted.** It was true from
    W1b until 2026-08-26 and it was load-bearing for exactly as long as the
    session runner did not exist; the button now goes somewhere, and the
    assertion becomes that it goes to the session. A deleted assertion is
    indistinguishable from one that was forgotten.
    """
    #: Comment-stripped, because home's own docstring explains that the button
    #: WAS disabled until W10 — and prose about a rule is not the rule being
    #: broken (#150, the same trap `test_no_murphy_reaches_a_learner.py` names).
    source = _without_comments(
        (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    )
    assert "Start today" in source
    assert source.count("<Button") == 1
    assert "disabled" not in source
    assert 'href="/session"' in source


def test_the_api_client_reads_its_base_url_from_the_environment() -> None:
    """A hardcoded localhost is a shell that works only on the machine that built it.

    W6 moved the read from `lib/api.ts` into `lib/env.ts` so the build-time
    guard and the runtime read sit beside each other (#80). `lib/api.ts`
    re-exports `API_BASE_URL`, so every existing caller is unchanged.
    """
    source = (WEB / "lib" / "env.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_API_URL" in source
    assert "API_BASE_URL" in (WEB / "lib" / "api.ts").read_text(encoding="utf-8")
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


def test_the_writing_bounds_match_the_service() -> None:
    """The frontend mirrors the bounds so a learner is not made to round-trip
    to find out an entry was too short. Mirrors drift, so this pins them to
    the Python constants (rule 5 — the expected values are read from the other
    side, not from the file under test).

    **W16a repointed this** from `core.services.correction` (the bot's 10/1000)
    to `core.writing.rules` (10/2000, Q-B): the web no longer calls the bot's
    correction path, and a pin against a path the screen does not use would be
    green over the wrong numbers."""
    from core.writing.rules import MAX_CHARS, MIN_CHARS

    source = (WEB / "lib" / "limits.ts").read_text(encoding="utf-8")
    assert f"WRITING_MIN_CHARS = {MIN_CHARS};" in source
    assert f"WRITING_MAX_CHARS = {MAX_CHARS};" in source


def test_the_write_screen_never_marks_what_the_learner_wrote() -> None:
    """CLAUDE.md §4 — the one screen in the product where tone matters most.

    Striking through someone's sentence is the visual form of "you failed".
    The emphasis belongs on the better version, not on the mistake.
    """
    source = _without_comments(
        (WEB / "app" / "(app)" / "write" / "page.tsx").read_text(encoding="utf-8")
        + (WEB / "components" / "write" / "writer.tsx").read_text(encoding="utf-8")
    )
    for banned in ("line-through", "text-destructive", "bg-destructive"):
        assert banned not in source, f"{banned} on the correction screen"


def test_no_red_reaches_the_correction_screen() -> None:
    """The palette has no red in it by design (apps/web/README.md), and this is
    exactly the screen someone would be tempted to add one to."""
    source = _without_comments(
        (WEB / "app" / "(app)" / "write" / "page.tsx").read_text(encoding="utf-8")
        + (WEB / "components" / "write" / "writer.tsx").read_text(encoding="utf-8")
    )
    for banned in ("text-red", "bg-red", "border-red", "#f00", "rgb(255,0,0)"):
        assert banned not in source


def test_today_still_offers_one_button() -> None:
    """W3 adds a link to /write, not a second action. PRD §4: home resolves to
    one decision a day, and the session runner **is** that decision from W10."""
    source = (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    assert source.count("<Button") == 1
    assert 'href="/write"' in source


#: Every number the deck API can put on the wire that describes what is LEFT.
#:
#: Read out of `apps/api/schemas.py`'s `DeckCountsOut` rather than remembered, so
#: a fourth count added there is covered here the day it is added.
_BACKLOG_FIELDS = ("total_remaining", "new_remaining", "review_remaining", "due_now")


def _backlog_offenders(sources: dict[str, str]) -> list[str]:
    offenders: list[str] = []
    for rel, raw in sorted(sources.items()):
        for field in _BACKLOG_FIELDS:
            if field in raw:
                offenders.append(f"{rel}: {field}")
    return offenders


def test_no_surface_presents_a_backlog_count() -> None:
    """**The W10 ruling, and it is a rule this project already had.**

    CLAUDE.md §4: *"Never present a backlog. Missed days shrink the task; they
    never pile up."* PRD §12 rule 5 repeats it: *"No backlog is ever
    presented."*

    `/review` printed *"N left today"* from W7 until 2026-08-26. That number is
    already capped, so it never showed the true overdue pile — and it was still a
    duty counter on a tab, which is the thing the rule is about. #160 retired
    `/review` as a daily obligation and moved the due deck into the session.

    **The number is not banned; RENDERING it is.** The API still sends
    `DeckCountsOut` — the session sizes block 1 from it and W19 reads it — which
    is the same standing `murphy_units` has under #187: a field on the wire that
    no surface may consume.

    **Scoped to the RENDERING surfaces — `app/` and `components/` — and `lib/`
    is excluded deliberately.** `lib/api.ts` declares `DeckCounts` because the
    API really does send those three fields; deleting them from the type while
    the payload carries them would make the TypeScript wrong in the other
    direction. That is #187's reasoning exactly, and it is why this bans a
    render rather than a word.

    Scoped to what ships, so a test asserting the absence is not itself an
    offence.
    """
    sources = {
        rel: _without_comments(raw)
        for rel, raw in _shipped_sources().items()
        if rel.startswith("apps/web/app/") or rel.startswith("apps/web/components/")
    }
    assert sources, "the web sources moved; this scan is reading nothing"
    assert _backlog_offenders(sources) == [], (
        "no learner surface may render a remaining-count (CLAUDE.md §4): "
        + "; ".join(_backlog_offenders(sources))
    )


def test_the_backlog_scan_catches_a_real_violation() -> None:
    """A green scan over nothing proves nothing (CLAUDE.md §3 rule 4).

    Demonstrated against the exact string that was on `/review` until W10.
    """
    assert _backlog_offenders(
        {"x.tsx": "<p>{counts.total_remaining} left today</p>"}
    ) == ["x.tsx: total_remaining"]
    assert _backlog_offenders({"x.tsx": "<p>{queue.due_now} due</p>"})
    assert _backlog_offenders({"x.tsx": "<p>Block 1 of 5</p>"}) == []


def test_home_carries_no_number_at_all() -> None:
    """The one screen a learner opens every day, and the one a badge would be
    added to first. A count that grows while someone is away is the visual form
    of "you are behind"."""
    source = _without_comments(
        (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    )
    for banned in ("Badge", "count", "streak", "due", "left today"):
        assert banned not in source, f"{banned} on home"


def test_the_session_screen_exists_and_is_behind_the_session_guard() -> None:
    page = WEB / "app" / "(app)" / "session" / "page.tsx"
    assert page.is_file()
    layout = (WEB / "app" / "(app)" / "layout.tsx").read_text(encoding="utf-8")
    assert "RequireSession" in layout


def test_no_red_reaches_the_session_screen() -> None:
    """The palette has no red in it by design, and a block that failed to load
    is not an alarm — it is a quiet line and a way back."""
    sources = {
        rel: _without_comments(raw)
        for rel, raw in _shipped_sources().items()
        if "components/session/" in rel or "app/(app)/session/" in rel
    }
    assert sources, "the session sources moved; this scan is reading nothing"
    for rel, raw in sources.items():
        for banned in _RED:
            assert banned not in raw, f"{banned} in {rel}"


def test_empty_and_unavailable_are_distinct_strings_in_the_copy() -> None:
    """**The one thing a learner must never see collapse.**

    A block that ran and found nothing, and a block that could not be built, are
    different facts. If the two shared a string the distinction would exist in
    the API and nowhere a person can see, which is worse than not having it —
    the payload would be right and the screen would still lie.
    """
    copy = (WEB / "components" / "session" / "copy.ts").read_text(encoding="utf-8")
    assert "NOTHING_DUE" in copy and "BLOCK_UNAVAILABLE" in copy
    import re as _re

    def _body(name: str) -> str:
        match = _re.search(rf"export const {name} = \{{(.*?)\}} as const;", copy, _re.S)
        assert match, f"{name} is not in the session copy"
        return match.group(1)

    nothing_due = _body("NOTHING_DUE")
    unavailable = _body("BLOCK_UNAVAILABLE")
    assert nothing_due.strip() and unavailable.strip()
    assert nothing_due != unavailable


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


# ─────────────────────────────────────────────────────────────────────────────
# W6. The frontend renders eleven item types for the first time, so three rules
# that were previously either theoretical or scoped to one screen become real:
# nothing may grade in TypeScript, nothing outside one map may branch on item
# type, and the no-guilt rule now has eleven components' worth of wrong-answer
# copy to hold. Each check below is meta-tested against a deliberate violation —
# a check that no longer fails on anything is a deleted check with extra steps.
# ─────────────────────────────────────────────────────────────────────────────

ITEMS_TREE = ("components/items", "lib/items.ts")

# The files that must NOT name an item type. Presentation is per type and
# answering is per response mode, so the eleven live in exactly one map
# (`components/items/presentation/index.ts`) plus the eleven files it points at.
# Test files are excluded deliberately: `renders.test.tsx` names all eleven on
# purpose, which is what makes `test_every_item_type_has_a_render_test` possible.
TYPE_FREE_FILES = (
    "apps/web/components/items/item-card.tsx",
    "apps/web/components/items/feedback.tsx",
    "apps/web/components/items/explanation.tsx",
    "apps/web/components/items/audio-button.tsx",
    "apps/web/components/items/answer/index.ts",
    "apps/web/components/items/answer/types.ts",
    "apps/web/components/items/answer/tap-answer.tsx",
    "apps/web/components/items/answer/typed-answer.tsx",
    "apps/web/components/items/answer/spoken-answer.tsx",
    "apps/web/lib/items.ts",
)


def _items_sources() -> dict[str, str]:
    """Every `.ts`/`.tsx` under the items tree, tests excluded."""
    out: dict[str, str] = {}
    for entry in ITEMS_TREE:
        target = WEB / entry
        paths = (
            [target]
            if target.is_file()
            else [p for p in sorted(target.rglob("*")) if p.is_file()]
        )
        for path in paths:
            if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
                continue
            out[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
    return out


# Every way TypeScript would fold or compare an answer. Scoped to the items tree
# rather than the whole app, so the ban means something: `toLowerCase` is a
# perfectly ordinary call elsewhere, and a blanket ban would be routed around
# rather than obeyed.
_COMPARISON = (
    "toLowerCase",
    "toLocaleLowerCase",
    "localeCompare",
    ".normalize(",
    "casefold",
    "replace(/[^",
)


def _comparison_offenders(sources: dict[str, str]) -> list[str]:
    offenders: list[str] = []
    for rel, raw in sorted(sources.items()):
        text = _without_comments(raw)
        for banned in _COMPARISON:
            if banned in text:
                offenders.append(f"{rel}: {banned}")
    return offenders


def test_no_answer_comparison_in_typescript() -> None:
    """`core/items/grading.py`'s fold is shared by the uniqueness gate and the
    grader, and a fourth fold here would let an item pass the gate and then be
    ungradable — the learner types the identical string and is marked wrong.

    The real enforcement is a capability: the projection carries no answer, so
    there is nothing to compare against. This is the belt: it fails the commit
    that starts folding a response before sending it, which is how a "just trim
    it first" convenience becomes a second definition of "the answer".
    """
    assert _comparison_offenders(_items_sources()) == [], (
        "all grading is server-side (core.items.grading.grade_text): "
        + "; ".join(_comparison_offenders(_items_sources()))
    )


def test_the_comparison_check_catches_a_real_violation() -> None:
    """CLAUDE.md §3 rule 4, applied to the rule itself."""
    assert _comparison_offenders(
        {"apps/web/lib/items.ts": "if (a.toLowerCase() === b) return true;"}
    )
    assert _comparison_offenders(
        {"apps/web/components/items/x.tsx": 'v.normalize("NFC")'}
    )
    # Prose about the rule is not a violation of it.
    assert (
        _comparison_offenders(
            {"apps/web/lib/items.ts": "// never call toLowerCase here\nconst a = 1;"}
        )
        == []
    )


def test_only_the_presentation_map_branches_on_item_type() -> None:
    """Presentation is per type; answering is per response mode.

    The W6 task row asks for one component per item type and the W5 contract
    says render from `RESPONSE_MODE`. Both hold: eleven presentation components
    over three answer components, with the eleven enumerated in exactly one map.
    A type string leaking into the shell or into an answer component is the
    eleven-way switch arriving by the back door.

    The expected values are read from `core.items.ITEM_TYPES` — the other side
    of the boundary — never from the files under test (rule 5).
    """
    from core.items import ITEM_TYPES

    offenders: list[str] = []
    for rel in TYPE_FREE_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"{rel} is listed but does not exist"
        text = _without_comments(path.read_text(encoding="utf-8"))
        for item_type in ITEM_TYPES:
            if item_type in text:
                offenders.append(f"{rel}: {item_type}")
    assert offenders == [], (
        "only components/items/presentation/index.ts and the eleven files it "
        "maps to may name an item type: " + "; ".join(offenders)
    )


def test_the_presentation_map_covers_exactly_the_eleven() -> None:
    """A type Python knows about with no component renders a fallback on a
    phone. This is where that should be caught instead."""
    from core.items import ITEM_TYPES

    source = _without_comments(
        (WEB / "components" / "items" / "presentation" / "index.ts").read_text(
            encoding="utf-8"
        )
    )
    body = source[source.index("PRESENTATIONS") :]
    body = body[body.index("{") : body.index("};")]
    mapped = set(re.findall(r"^\s{2}(\w+):\s", body, re.MULTILINE))
    assert mapped == set(ITEM_TYPES), (
        f"presentation map and core.items.ITEM_TYPES disagree: "
        f"only in map {sorted(mapped - set(ITEM_TYPES))}, "
        f"only in Python {sorted(set(ITEM_TYPES) - mapped)}"
    )


def test_the_response_mode_table_is_not_mirrored_in_typescript() -> None:
    """`response_mode` travels on the wire from `ItemPresentation`.

    A copy of `core.items.RESPONSE_MODE` here would be a table that drifts, and
    the drift would surface as an item rendered with the wrong input — which
    looks like a broken renderer rather than like stale data.
    """
    for rel, raw in _items_sources().items():
        text = _without_comments(raw)
        assert not re.search(r'"(mcq|cloze_cued)"\s*:\s*"(tap|typed|spoken)"', text), (
            f"{rel} mirrors RESPONSE_MODE; it belongs on the wire"
        )


def test_every_item_type_has_a_render_test() -> None:
    """The Vitest suite must actually render all eleven, not merely exist.

    **Deliberately not a file count.** A count is satisfied by splitting files,
    and #67's whole complaint was coverage that looks real from the outside. A
    twelfth item type added in Python fails here until somebody renders it.
    """
    from core.items import ITEM_TYPES

    tests = [
        p.read_text(encoding="utf-8")
        for p in (WEB / "components" / "items").rglob("*.test.tsx")
    ]
    assert tests, "apps/web has no item render tests"
    blob = "\n".join(tests)
    missing = [t for t in ITEM_TYPES if f'"{t}"' not in blob]
    assert missing == [], f"no render test names: {', '.join(missing)}"


def test_the_frontend_suite_is_runnable() -> None:
    """`pnpm test` has to exist, or the Python suite is green over nothing.

    A green suite standing in for a deleted one is the trap this project has
    been bitten by; #67 is open because reading source is not running it.
    """
    config = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    assert config["scripts"].get("test") == "vitest run"
    assert (WEB / "vitest.config.ts").is_file()
    assert (WEB / "vitest.setup.ts").is_file()


def test_no_guilt_copy_anywhere_in_the_frontend() -> None:
    """CLAUDE.md §4, extended from one screen to every `.tsx`.

    Blunt on purpose: the pattern runs over the whole comment-stripped source,
    so a variable named `failedCount` fails this too. Rename the variable — the
    cost of that is far below the cost of one banned word reaching a learner,
    and a scan that tries to tell copy from code is a scan that misses copy.

    **What this cannot reach is item content.** `prompt_text`, `cue_text`,
    options and tiles come from the database and, from W10, from a model. They
    are the highest-volume user-facing copy in the app and no check touches them
    (#110).
    """
    from tests.support.no_guilt import offenders

    sources = {
        rel: _without_comments(raw) for rel, raw in _shipped_sources().items()
    }
    assert offenders(sources) == [], (
        "no user-facing string may blame the learner (CLAUDE.md §4): "
        + "; ".join(offenders(sources))
    )


#: ``(module, exported copy block)`` — every place a conversation string may be
#: declared. **Named, not walked** (#257: a checker widened until it passes is a
#: checker nobody can trust). `test_the_conversation_copy_scan_covers_every_
#: surface` is what keeps the list honest as surfaces are added.
_CONVERSATION_COPY: tuple[tuple[str, str], ...] = (
    ("apps/web/components/session/copy.ts", "CONVERSATION"),
    # **W16a adds `WRITE`.** The writing screen's copy is under the same digit
    # rule as the conversation's: no count, no remaining, no length target in
    # figures (design `1d`, `1u`). RED against `short: "At least 10 characters."`.
    ("apps/web/components/session/copy.ts", "WRITE"),
    # **W13b/5a ADDS `BLOCKS`, AND #400 IS WHY.** The closing block rendered
    # *"0 cards reviewed today."* to a learner who reviewed nothing — #348's
    # shape, live — and **neither scan could see it**: the numeral is
    # interpolated in `blocks.tsx`, so the string literal in `copy.ts` is
    # innocent and the JSX-text scan is scoped to the conversation surfaces.
    # Bringing `BLOCKS` under the digit rule does not catch an interpolated
    # count either; **what it does catch is the next literal one**, which is how
    # #348 itself was written.
    ("apps/web/components/session/copy.ts", "BLOCKS"),
)

#: The files that RENDER the conversation, including the close-out. A copy block
#: declared in one of these and absent from `_CONVERSATION_COPY` is a numeral
#: check with a hole in it, which is the shape #348 shipped through for a year.
#: `close-out.tsx` is listed **before it exists** — W13b/4's close-out layout is
#: gated on reading the design file, and a guard that arrives with the file it
#: guards has already missed its moment.
_CONVERSATION_SURFACES: tuple[str, ...] = (
    "apps/web/components/session/conversation.tsx",
    "apps/web/components/session/close-out.tsx",
    "apps/web/app/(app)/talk/page.tsx",
    # W16a. The writing screen renders a learner's own words back to them and a
    # count would be the natural thing to type into it. RED against
    # `<p>Two corrections</p>` becoming `<p>2 corrections</p>` in the JSX.
    "apps/web/components/write/writer.tsx",
    "apps/web/app/(app)/write/page.tsx",
)


def test_the_conversation_cap_copy_carries_no_numeral() -> None:
    """W13b. **The banned-phrase scan is not enough here and #348 is why.**

    *"0 of 5 active days."* shipped to a learner every Sunday for a year and
    contains no banned word. A remaining-turns figure is a backlog running
    backwards; a tally of turns used is a score on someone for talking. So the
    conversation copy is asserted to contain **no digit at all**, which is a
    property a scan can hold where *is this a tally?* is not.

    RED against `capReached: "That's 30 for today."`.
    """
    import re

    offenders: list[str] = []
    for rel, const in _CONVERSATION_COPY:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert f"export const {const}" in src, f"{rel} declares no {const} block"
        # **COMMENTS STRIPPED FIRST, AND `BLOCKS` IS WHAT PROVED IT NECESSARY.**
        # This scan read raw source until W13b/5a. Widening it to `BLOCKS`
        # reported three offenders and **all three were prose**: two doc-comment
        # examples, and — the one that settles it — the literal
        # *"0 of 5 active days."*, which is #348's OWN EXAMPLE quoted in a
        # comment explaining the rule. **The scan reported the documentation of
        # the defect as the defect.** That is exactly the trap
        # `_shipped_sources` was written for: prose *about* a rule is not a
        # breach of it, and a check satisfied only by deleting the explanation
        # is a check that loses the explanation.
        block = _without_comments(src[src.index(f"export const {const}") :])
        strings = re.findall(r'"([^"]*)"', block)
        assert strings, f"the {const} copy block in {rel} was not found"
        # **`\u2019` CONTAINS DIGITS AND IS AN APOSTROPHE.** `BLOCKS` writes
        # some of its curly quotes as escapes, so scanning the raw source
        # reported `"No video today. There\u2019ll be one on Monday…"` as
        # carrying a numeral. **A scan that fires on an apostrophe is a scan
        # somebody switches off** (#257's shape), so escapes are decoded to the
        # characters they denote before the digit rule is applied.
        decoded = [
            re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
            for t in strings
        ]
        offenders += [f"{rel}: {t}" for t in decoded if re.search(r"[0-9]", t)]
    assert offenders == [], (
        "no conversation string may carry a numeral (#348, PRD §8.6.4): "
        + "; ".join(offenders)
    )


def test_no_conversation_surface_renders_a_numeral_inline() -> None:
    """W13b/4. **The block scan covers `copy.ts`; this covers the JSX.**

    #348's defect was not a bad string in a copy module — it was a **tally
    rendered to a learner**, and a close-out page is where one would naturally
    be written: *"You talked for 5 minutes"*, typed straight into the markup,
    never passing through `copy.ts` and so never reaching the block scan above.

    **WHAT THIS READS: literal text between two tags**, which is where inline
    copy lives. `className` and every other attribute sit *inside* a tag and are
    not text, so `rounded-2xl` and `max-w-[85%]` cannot reach it — that is the
    reason for the shape of the pattern rather than a happy accident.

    **THE FIRST VERSION OF THIS PATTERN WAS WRONG AND THE SUITE CAUGHT IT.** It
    read *any* `>` as a tag boundary and flagged `{words.length > 0 ? (` — a
    COMPARISON OPERATOR. So the `>` must not be preceded by a space or by
    `=!<>`, which is what separates `">` at the end of a tag from ` > ` and
    `=>` in code, and the text may not cross a newline.

    **THE COST OF THAT FIX, STATED RATHER THAN LEFT TO BE DISCOVERED:** a
    numeral in inline text broken across two lines is no longer caught. The
    realistic shape — `<p>You talked for 5 minutes</p>` — is, and a scan that
    over-reports on every comparison in the file is a scan that gets deleted.

    **WHAT IT DELIBERATELY DOES NOT READ: anything containing `{`.** The
    recording timer renders `{rec.elapsed}s`, a live counter of the seconds a
    learner has been speaking, and it is **not** what #348 forbids — that rule
    is about a tally of work done or work left, and shipped behaviour is not
    quietly redefined by a test written for something else. An interpolated
    numeral that IS a tally is not catchable here and is not claimed to be.

    RED against `<p>You talked for 5 minutes</p>` in any listed surface.
    """
    import re

    offenders: list[str] = []
    for rel in _CONVERSATION_SURFACES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
        for text in re.findall(r"(?<![\s=!<>])>([^<>{}\n]+)<", src):
            if re.search(r"[0-9]", text):
                offenders.append(f"{rel}: {text.strip()}")
    assert offenders == [], (
        "no conversation surface may render a numeral inline (#348): "
        + "; ".join(offenders)
    )


def test_the_conversation_copy_scan_covers_every_surface() -> None:
    """W13b/4. **The list above is only as good as its completeness.**

    A close-out page that declares `export const CLOSE_OUT = {…}` of its own
    would be user-facing conversation copy that
    `test_the_conversation_cap_copy_carries_no_numeral` never opens — the same
    hole #348 went through, reopened one file to the left. So a copy block in a
    conversation surface must be **named in `_CONVERSATION_COPY` or not exist**.

    This is the check that fails when the design-gated close-out lands with its
    own strings, and failing then is the entire point.
    """
    import re

    named = {const for _, const in _CONVERSATION_COPY}
    unnamed: list[str] = []
    for rel in _CONVERSATION_SURFACES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for const in re.findall(r"export const ([A-Z][A-Z0-9_]*)\s*=", src):
            if const not in named:
                unnamed.append(f"{rel}: {const}")
    assert unnamed == [], (
        "a conversation surface declares copy the numeral scan does not read; "
        "add it to _CONVERSATION_COPY (#348): " + "; ".join(unnamed)
    )


def test_the_no_guilt_scan_catches_a_real_violation() -> None:
    from tests.support.no_guilt import offenders

    assert offenders({"x.tsx": "<p>Wrong — try again</p>"})
    assert offenders({"x.tsx": "You missed three this week 😞"})
    assert offenders({"x.tsx": "Incorrect."})
    assert offenders({"x.tsx": "That’s it."}) == []


# `components/ui/` is vendored shadcn. Its `destructive` variant is part of the
# primitive and is never used by a screen in this app — asserted separately
# below — so banning the token inside those two files would fail on an unused
# variant and teach nothing.
_VENDORED_UI = "apps/web/components/ui/"

_RED = (
    "text-red",
    "bg-red",
    "border-red",
    "#f00",
    "rgb(255,0,0)",
    "text-destructive",
    "bg-destructive",
    "line-through",
)


def _red_offenders(sources: dict[str, str]) -> list[str]:
    offenders: list[str] = []
    for rel, raw in sorted(sources.items()):
        if rel.startswith(_VENDORED_UI):
            continue
        text = _without_comments(raw)
        for banned in _RED:
            if banned in text:
                offenders.append(f"{rel}: {banned}")
    return offenders


def test_no_red_anywhere_in_the_frontend() -> None:
    """The W1b palette decision, held across the whole app.

    "Never guilt" is easier to keep to when the colour for failure does not
    exist in the theme (`apps/web/README.md`). W3 asserted this for the
    correction screen; W6 adds eleven components whose entire job is telling
    someone their answer was not the one — which is exactly the screen someone
    would be tempted to add a red to.
    """
    assert _red_offenders(_shipped_sources()) == [], (
        "nothing in the palette is red by design: "
        + "; ".join(_red_offenders(_shipped_sources()))
    )


def test_no_screen_uses_the_vendored_destructive_variant() -> None:
    """The exemption above is bounded: shadcn may define it, we may not use it."""
    offenders = [
        rel
        for rel, raw in _shipped_sources().items()
        if not rel.startswith(_VENDORED_UI)
        and 'variant="destructive"' in _without_comments(raw)
    ]
    assert offenders == [], f"destructive variant used by: {', '.join(offenders)}"


def test_the_build_refuses_an_empty_api_base_url() -> None:
    """Known issue #80, closed here.

    An *unset* `NEXT_PUBLIC_API_URL` takes the localhost fallback but an
    **empty** one does not, so `API_BASE_URL` becomes `""`, every request goes
    to a relative path the deployment does not serve, and the message degrades
    to "Could not reach the API at ." — indistinguishable from the API being
    down. Vercel allows saving an empty-string variable, so it is reachable.

    **The check is build-time, and that is the point.** A throw at module load
    in `lib/env.ts` would fail the build only if that module were evaluated
    during prerender; evaluated first in the browser it white-screens a phone
    instead — a worse failure than the one being fixed. So `lib/env.ts` stays a
    pure read and `prebuild` refuses.
    """
    config = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    assert config["scripts"].get("prebuild") == "node scripts/check-env.mjs"

    guard = (WEB / "scripts" / "check-env.mjs").read_text(encoding="utf-8")
    assert "process.exit(1)" in guard
    assert 'trim() === ""' in guard, "an empty value must fail, not only an unset one"

    env_module = _without_comments((WEB / "lib" / "env.ts").read_text(encoding="utf-8"))
    assert "throw" not in env_module, (
        "lib/env.ts must stay a pure read — a module-load throw white-screens "
        "the browser instead of failing the build"
    )


def test_the_practice_screen_exists_and_is_behind_the_session_guard() -> None:
    """W6's surface. It writes attempts, so it lives under `(app)` — everything
    there is behind `RequireSession`."""
    assert (WEB / "app" / "(app)" / "practice" / "page.tsx").is_file()
    layout = (WEB / "app" / "(app)" / "layout.tsx").read_text(encoding="utf-8")
    assert "RequireSession" in layout


def test_today_still_offers_exactly_one_button_after_w6() -> None:
    """W6 adds a link to /practice, not a second action. PRD §4: home resolves
    to one decision a day, and the session runner is that decision from W10."""
    source = (WEB / "app" / "(app)" / "page.tsx").read_text(encoding="utf-8")
    assert source.count("<Button") == 1
    assert 'href="/practice"' in source
    assert 'href="/write"' in source


# ─────────────────────────────────────────────────────────────────────────────
# W8a. Two surface bans, and the rule they share.
#
# **A ban test bans surfaces, not words, and therefore never scans comments.**
# Recorded once here so the next ban inherits the rule rather than deciding it
# again — the two below were written asymmetrically in the first draft and the
# asymmetry was the whole defect: one of them would have been satisfied only by
# deleting a PRD quote that explains why every card carries its source sentence.
#
# On the TypeScript side that means `_without_comments()`. On the Python side it
# means reading string constants out of the AST and skipping docstrings, which
# is what `test_core_boundary.py` already does and what its own module docstring
# names: *"a docstring mentioning 'telegram' passes and `import telegram.ext as
# x` fails — the exact pair a grep gets backwards."*
#
# The import half of each ban lives in `test_core_boundary.py`, where import
# bans live. These two are the literal half.
# ─────────────────────────────────────────────────────────────────────────────

API = REPO_ROOT / "apps" / "api"


def _api_sources() -> dict[str, str]:
    """Every `apps/api` module, with comments and docstrings removed.

    Docstrings are dropped by walking the AST rather than by a regex, because a
    regex that strips triple-quoted strings would also strip a SQL literal and
    the scan would stop seeing the thing it exists to see.
    """
    import ast

    out: dict[str, str] = {}
    for path in sorted(API.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        raw = path.read_text(encoding="utf-8")
        tree = ast.parse(raw, filename=str(path))
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstrings.add(id(body[0].value))
        pieces: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in docstrings:
                    pieces.append(node.value)
        # Names as well as literals: `from core.cards.anki import build_tsv` is
        # neither a string constant nor a comment, and it is exactly the shape a
        # re-added export takes.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pieces += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                pieces.append(node.module)
            elif isinstance(node, ast.Attribute):
                pieces.append(node.attr)
            elif isinstance(node, ast.Name):
                pieces.append(node.id)
        out[str(path.relative_to(REPO_ROOT))] = "\n".join(pieces)
    return out


def _stripped_web_sources() -> dict[str, str]:
    """Shipped `apps/web` sources with comments removed. Tests excluded."""
    return {rel: _without_comments(raw) for rel, raw in _shipped_sources().items()}


def _banned_hits(sources: dict[str, str], terms: tuple[str, ...]) -> list[str]:
    """``{path: text}`` → one entry per banned term found, sorted by path.

    Takes a mapping rather than paths so the meta-tests can feed it deliberate
    violations without writing a file, the same shape `tests/support/no_guilt.py`
    settled on.
    """
    offenders: list[str] = []
    for rel, text in sorted(sources.items()):
        lowered = text.lower()
        for term in terms:
            if term.lower() in lowered:
                offenders.append(f"{rel}: {term}")
    return offenders


# ── the Anki ban ───────────────────────────────────────────────────────────

#: `export.tsv` is the route path and the client URL; `core.cards.anki` and
#: `deckExportUrl` are the two identifiers that carried it. `anki` on its own is
#: deliberately included: the point is that no *code* in either tree mentions it.
_ANKI = ("export.tsv", "deckExportUrl", "anki")


def test_no_anki_export_path_in_the_web_app() -> None:
    """W8a: the in-app deck is the flashcard system; there is no hand-off.

    PRD §5's Rules line specified a one-click Anki backup until 2026-08-25,
    ARCHITECTURE §6 listed the route, the TASKS W7 row carried it in both
    columns, and W7 built all three. **The documents agreed with each other and
    with the code** — so without this test the export comes back the first time
    someone reads a cached copy of PRD §5 and implements it in good faith, which
    is precisely how it arrived.

    `packages/core/services/anki.py` is the **v2 Telegram** chunk exporter, a
    live path two learners use weekly that dies at W22. It is outside both trees
    scanned here, so no exclusion is needed and none is taken.
    """
    offenders = _banned_hits(_stripped_web_sources(), _ANKI) + _banned_hits(
        _api_sources(), _ANKI
    )
    assert offenders == [], (
        "no Anki export path may exist in apps/web or apps/api (W8a; PRD §5 as "
        "corrected 2026-08-25): " + "; ".join(offenders)
    )


def test_the_anki_scan_catches_a_real_violation() -> None:
    """The meta-test. A ban that fails on nothing is a deleted ban with steps."""
    assert _banned_hits(
        {"apps/web/components/cards/reviewer.tsx": 'href={deckExportUrl()}'}, _ANKI
    ) == ["apps/web/components/cards/reviewer.tsx: deckExportUrl"]
    assert _banned_hits(
        {"apps/api/routers/cards.py": '"/cards/export.tsv"'}, _ANKI
    ) == ["apps/api/routers/cards.py: export.tsv"]
    assert _banned_hits({"apps/web/lib/api.ts": "const deck = 1;"}, _ANKI) == []


def test_the_anki_scan_does_not_read_a_comment_as_a_surface() -> None:
    """The rule this slice recorded, asserted rather than trusted.

    `card-face.tsx` carries the PRD quote *"bare word↔translation cards are why
    people quit Anki"* — the sentence that explains why every card ships with its
    source line. It records where a design came from and it is not a surface, so
    the scan must not see it. The first draft of this ban did, and the only way
    to satisfy it was to delete the quote.
    """
    commented = {
        "apps/web/components/cards/card-face.tsx": (
            "/* ...why people quit Anki. */\nexport function CardFace() {}"
        )
    }
    assert _banned_hits(
        {rel: _without_comments(raw) for rel, raw in commented.items()}, _ANKI
    ) == []


# ── the Telegram ban ───────────────────────────────────────────────────────

#: Surfaces only. `telegram` itself is in the list because in *code* — an import,
#: an identifier, a URL — it can only be a surface; the four docstrings in these
#: two trees that mention Telegram are prose about where a data shape came from,
#: and they are the record this project keeps deliberately.
_TELEGRAM = ("t.me/", "tg://", "TELEGRAM_", "bot_token", "telegram")


def test_no_telegram_surface_in_the_web_app() -> None:
    """PRODUCT-PRINCIPLES §1: no new feature, screen, alert channel or fallback
    is built for Telegram. Every teaching and identity surface is the web app.

    Run at W8a as a confirmation and kept as a check. The grep at the time found
    four hits and all four were docstrings — `apps/web/lib/api.ts:85`,
    `apps/api/main.py:88`, `apps/api/routers/correct.py:22` and
    `apps/api/schemas/__init__.py:87` — each saying that a correction *shape* is
    the one the learners already read in Telegram. No link, no deep link, no
    token, no environment variable, no import.

    The exclusion of comments and docstrings is named rather than silent, and it
    is safe because the import half of this ban is an AST check in
    `test_core_boundary.py::test_the_apps_import_no_telegram_package`: a real
    dependency is an import, and an import cannot be commented out and still run.
    """
    offenders = _banned_hits(_stripped_web_sources(), _TELEGRAM) + _banned_hits(
        _api_sources(), _TELEGRAM
    )
    assert offenders == [], (
        "no Telegram surface may exist in apps/web or apps/api "
        "(PRODUCT-PRINCIPLES §1): " + "; ".join(offenders)
    )


def test_the_telegram_scan_catches_a_real_violation() -> None:
    """The meta-test."""
    assert _banned_hits(
        {"apps/web/app/(app)/page.tsx": 'href="https://t.me/englishbot"'}, _TELEGRAM
    ) == ["apps/web/app/(app)/page.tsx: t.me/"]
    assert _banned_hits(
        {"apps/api/config.py": 'os.environ["TELEGRAM_BOT_TOKEN"]'}, _TELEGRAM
    ) == [
        "apps/api/config.py: TELEGRAM_",
        "apps/api/config.py: bot_token",
        "apps/api/config.py: telegram",
    ]


def test_the_telegram_scan_keeps_the_four_docstrings_it_found() -> None:
    """The hits W8a reported are prose, and prose survives the ban.

    A docstring saying "the same shape learners already read in Telegram" is the
    record of where a contract came from. Deleting it to satisfy a scan would
    trade a real piece of history for a green test.
    """
    prose = {
        "apps/web/lib/api.ts": (
            "/** One correction, the same shape learners already read in "
            "Telegram. */\nexport type Correction = { text: string };"
        )
    }
    assert _banned_hits(
        {rel: _without_comments(raw) for rel, raw in prose.items()}, _TELEGRAM
    ) == []


#: W11b's three surface files, named so their coverage by the scans above is an
#: assertion rather than a consequence of a glob.
_WEEK_SURFACE = (
    "apps/web/components/week/report.tsx",
    "apps/web/components/week/sunday-home.tsx",
    "apps/web/app/(app)/week/page.tsx",
)


def test_the_backlog_and_guilt_scans_reach_the_weekly_report() -> None:
    """**W11b, and this is what "the scan is extended to it" actually means.**

    A weekly report is the single most likely place in this product to smuggle
    in guilt: it is the app speaking, it is retrospective, and the natural way
    to write one is to say what did not happen. Both scans already cover
    `apps/web/app/` and `apps/web/components/` by construction — but a surface
    covered by a glob is covered until somebody moves it, and then nothing says
    so. These three paths are named.
    """
    scanned = set(_shipped_sources())
    missing = [rel for rel in _WEEK_SURFACE if rel not in scanned]
    assert missing == [], f"outside the copy scans: {', '.join(missing)}"


def test_sundays_home_carries_no_session_call_to_action() -> None:
    """PRD §4.2: *"No tasks… deliberate and non-negotiable"*, so **a Sunday that
    acquires a task is a defect** (#310's own words, quoting W11b's row).

    Asserted structurally as well as in `report.test.tsx`, because the way this
    breaks is that somebody adds a button to the Sunday branch and every
    rendering test still passes on the six other days.
    """
    source = _without_comments(
        (WEB / "components" / "week" / "sunday-home.tsx").read_text(encoding="utf-8")
    )
    sunday = source[source.index("kind === \"sunday\"") :] if "kind === \"sunday\"" in source else source
    assert "<Button" not in source, "Sunday's home may not carry a button"
    assert "Start today" not in source
    # The positive control: the branch this is asserting over really is there.
    assert "practise anyway" in sunday


def test_the_writing_components_are_inside_the_no_guilt_walk() -> None:
    """W16a. A new directory can fall outside a scan that walks named roots.

    `components/write/` sits under `components`, which `SOURCE_DIRS` walks — and
    this pins that it is actually reached rather than assuming it.
    RED with `SOURCE_DIRS = ("app", "lib")`."""
    walked = {path.relative_to(WEB).as_posix() for path in _source_files()}
    assert "components/write/writer.tsx" in walked
    assert "app/(app)/write/page.tsx" in walked
