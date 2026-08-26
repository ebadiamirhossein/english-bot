"""#171's constraint, extended by the #183 ruling: **NO SURFACE RENDERS A
MURPHY CITATION, FROM ANY SOURCE.**

**One test, both fields, and the reason one test is enough is not tidiness.**
#171 was written about `syllabus_units.grammar_targets[].murphy_units`; #183
found that the citation a learner actually reads today comes from a *different*
column, `error_types.murphy_units`, seeded in `migrations/001_init_postgres.sql`
and copied onto every `errors` row. **Both columns are called `murphy_units`**,
so a single rule over the rendering surfaces covers both — which is why the
ruling asked for one test rather than a second version of the first.

**What this bans: a citation.** A Murphy unit or page number shown to a learner.
The operator's reason, ruled at W8g and applied unchanged at #183: most users own
no copy, and some who do own a different edition, so the number is meaningless to
nearly everyone who reads it. That it sits beside an explanation which already
stands alone makes it clutter rather than harm — and clutter for nearly every
user is not a feature.

**What this does NOT ban, and the distinction is load-bearing: a learner naming
their own book.** `/book` asks which book is being scanned and offers *Murphy*
as one answer. The learner is holding that copy — that is the one case where the
word means something to the person reading it. `texts.BTN_BOOK_MURPHY` is
allow-listed **by constant name**, with this reason, so nobody deletes it as an
oversight and nobody widens the exemption by adding a second string beside it.

**The column stays.** `error_types.murphy_units` remains an operator reference
and is still the code→units map `murphy_lookup()` doubles as the valid-error-code
set for. This rule is about what reaches a learner, not about what the database
holds — no migration, no drop.

**#164 stays open**: the three contradictions in the syllabus field are still
real, still unexplained, and the field still exists in `data/syllabus_units.json`.
This test is why they can no longer reach anybody.

**W10 EXTENDED THIS FILE RATHER THAN WRITING A SECOND ONE, and the extension is
a different KIND of check.** #171's surviving obligation was owed by whichever of
W9 or W10 shipped first, and W10 is the slice that first serialises a unit's
`grammar_targets` into a payload — block 3 of the daily session. The scan above
covers every rendering surface, which already covers W10's new components the
moment they exist. What it cannot cover is a payload: a field that arrives on the
wire and is rendered by a surface **nobody has written yet**.

So the third check below asserts at the **serialisation seam** —
`core.sessions.blocks.visible_target`, which builds the learner-visible dict by
NAMING the one field that may travel rather than by copying and deleting. That
makes withholding the default: a second operator-only field added to
`GrammarTarget` later is absent unless someone deliberately admits it, where a
copy-and-delete would leak it until someone remembered.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "apps" / "web"
TEXTS = REPO_ROOT / "apps" / "bot" / "texts.py"

#: The one place the word may appear, allow-listed BY NAME rather than by value.
#: A value allow-list ("the literal 'Murphy' is fine") would let a second
#: hardcoded string in later; a name allow-list admits exactly one assignment.
ALLOWED_TEXTS_CONSTANT = "BTN_BOOK_MURPHY"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")


def _without_comments(text: str) -> str:
    """A comment explaining why Murphy is gone must not read as showing it."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _rendering_tsx() -> dict[str, str]:
    """Every `.tsx` a learner's browser actually renders. Tests excluded."""
    out: dict[str, str] = {}
    for directory in ("app", "components"):
        root = WEB / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.tsx")):
            if path.name.endswith(".test.tsx"):
                continue
            out[str(path.relative_to(REPO_ROOT))] = _without_comments(
                path.read_text(encoding="utf-8")
            )
    return out


def _texts_string_literals() -> list[tuple[str, str]]:
    """`(constant_name, value)` for every non-docstring string in `texts.py`.

    Parsed, never grepped. `apps/bot/texts.py` is nothing but learner-facing
    copy, so its string literals ARE the surface — but its docstrings and
    comments explain the rules, and a rule explained is not a rule broken. The
    same reason `test_core_boundary.py` parses instead of grepping (#150).
    """
    tree = ast.parse(TEXTS.read_text(encoding="utf-8"))

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        name = names[0] if names else "<unnamed>"
        for inner in ast.walk(node.value):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                if id(inner) not in docstrings:
                    out.append((name, inner.value))

    # Strings built inside functions (f-strings in formatters) are not
    # assignments, so they are collected separately under the function's name.
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                if id(inner) not in docstrings:
                    out.append((f"{node.name}()", inner.value))
    return out


def _texts_identifiers() -> set[str]:
    """Every name `texts.py` actually uses. Parsed, so prose is not code."""
    tree = ast.parse(TEXTS.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def murphy_offenders() -> list[str]:
    """Every place a Murphy citation could reach a learner. Empty is the rule.

    Returned rather than asserted inside, so the meta-test below can prove this
    scan catches a real violation without writing one to disk — the shape
    `tests/support/no_guilt.py` uses.
    """
    found: list[str] = []

    # (1) The FIELD, which is what covers both columns at once. A surface that
    #     never reads `murphy_units` cannot render one.
    for path, source in _rendering_tsx().items():
        for match in re.finditer(r"murphy_units", source):
            del match
            found.append(f"{path}: reads murphy_units")

    # (2) The WORD, because a hardcoded "Murphy 38" would pass (1).
    for path, source in _rendering_tsx().items():
        if "Murphy" in source:
            found.append(f"{path}: renders the word 'Murphy'")

    #     For `texts.py` this is an IDENTIFIER check, not a substring one. The
    #     first draft grepped the source and fired on its own docstring
    #     explaining why the field is gone -- #150 exactly, inside the test that
    #     warns about #150. Prose ABOUT a rule is not the rule being broken.
    for identifier in _texts_identifiers():
        if identifier == "murphy_units":
            found.append(f"{TEXTS.name}: reads murphy_units")
            break

    for name, value in _texts_string_literals():
        if "Murphy" in value and name != ALLOWED_TEXTS_CONSTANT:
            found.append(f"{TEXTS.name}:{name}: {value!r}")

    # (3) The PAYLOAD (W10). A surface cannot render what never arrived, and
    #     block 3 of the daily session is the first thing in this repository to
    #     serialise a unit's grammar targets at all.
    from core.sessions.blocks import visible_target

    class _Target:
        target = "must and can't for what you're fairly sure of"
        murphy_units = "38"

    projected = visible_target(_Target())
    if "murphy_units" in projected:
        found.append("core.sessions.blocks.visible_target: serialises murphy_units")
    return found


def test_no_surface_renders_a_murphy_citation_from_any_source() -> None:
    """#171 as extended by #183. The four surfaces are `write/page.tsx`,
    `components/items/explanation.tsx`, and `texts.py`'s correction block and
    S11 weekly routing — but the rule is stated over every surface, not over
    those four, so a fifth cannot be added without failing here."""
    assert murphy_offenders() == []


def test_a_grammar_target_reaches_a_learner_carrying_only_its_text() -> None:
    """#171's surviving obligation, discharged by W10 as the first slice to
    serialise `grammar_targets`.

    Asserted positively as well as negatively: the projection must still carry
    the target itself, or a payload that dropped everything would pass the ban
    and teach nothing.
    """
    from core.sessions.blocks import visible_target

    class _Target:
        target = "third conditional"
        murphy_units = "38-39"
        some_later_operator_field = "added by a future slice"

    assert visible_target(_Target()) == {"target": "third conditional"}


def test_the_real_syllabus_content_still_carries_the_operator_note() -> None:
    """**The ban must not become vacuous**, the same guard the `texts.py`
    exemption gets below.

    If `murphy_units` were ever dropped from `data/syllabus_units.json`, the
    projection above would pass for the wrong reason — there would be nothing
    left to withhold. The field is an OPERATOR NOTE and W8g's ruling kept it
    deliberately: the column stays, no migration, no drop.
    """
    from core.syllabus.content import units

    with_citations = [
        target
        for unit in units()
        for target in unit.grammar_targets
        if target.murphy_units
    ]
    # #164's inventory: 82 targets, 69 carrying a citation, 13 without.
    assert len(with_citations) == 69


def test_the_allow_listed_exemption_is_still_real() -> None:
    """The exemption must not become vacuous.

    If `BTN_BOOK_MURPHY` is renamed or its value changed, the allow-list stops
    excusing anything and starts hiding nothing — and the rule above would then
    pass for the wrong reason. Expected value is hardcoded here rather than read
    from the module (CLAUDE.md §3 rule 5): #63 is the test that broke by
    computing its fixture from the thing it was testing.
    """
    import apps.bot.texts as texts

    assert texts.BTN_BOOK_MURPHY == "Murphy"


def test_the_scan_catches_a_real_violation(monkeypatch) -> None:
    """A green scan over nothing proves nothing (CLAUDE.md §3 rule 4).

    Both halves are exercised: a surface that reads the field, and a surface
    that hardcodes the word.

    Patched through `sys.modules[__name__]` rather than by dotted string.
    `tests/` is not a package, so a string target can resolve to a SECOND copy
    of this module and the patch then lands on an object `murphy_offenders`
    never reads -- which is how the first draft of this meta-test passed its
    first assertion off a real offender in `texts.py` while the fake surface was
    never scanned at all.
    """
    monkeypatch.setattr(
        sys.modules[__name__],
        "_rendering_tsx",
        lambda: {"fake.tsx": "<p>Murphy {c.murphy_units}</p>"},
    )
    offenders = murphy_offenders()
    assert any("reads murphy_units" in o for o in offenders)
    assert any("renders the word 'Murphy'" in o for o in offenders)
