"""W4b: one translation from a Telegram id to a user id, and only one.

Since 011, ``user_id`` means ``users.id`` everywhere and ``telegram_user_id`` is
a nullable secondary identifier. That rule holds only as long as the translation
happens in one place; a second one is how the rule rots.

**Why this is a parse test rather than a convention.** The failure it prevents is
silent. A Telegram id passed into a service does not raise -- it selects zero
rows, so the feature stops working for everyone while every test stays green.
That is exactly how free correction (M2) died three times before W3, and the
whole point of giving existing learners fresh small ids at 011 was to make the
mistake loud. This test is the other half: it stops the mistake being written.

Same instrument as ``test_core_boundary`` (SQL outside services), W4's "only the
tokeniser reads the lexicon data files", and W2's one-session-resolver rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "packages" / "core"
BOT = REPO_ROOT / "apps" / "bot"
API = REPO_ROOT / "apps" / "api"

SQL_KEYWORDS = ("SELECT ", "INSERT INTO ", "UPDATE ", "DELETE FROM ")

# The two exemptions, named so nobody has to guess -- the same reason
# test_core_boundary spells its own out.
#
# `identity.py` is the resolver: translating is its whole job.
#
# `access_control.py` is exempt for a different reason, and it is not a
# concession. An access request legitimately exists *before* any `users` row --
# that is what 005 built the table for -- so `is_approved_telegram` has no
# internal id to be keyed on. `is_approved` (the post-account predicate) lives
# in the same module and is keyed on `users.id`.
CORE_SQL_EXEMPT = {
    CORE / "services" / "identity.py",
    CORE / "services" / "access_control.py",
}

# `apps/bot/identity.py` is the edge. Everything else in the bot receives an
# already-resolved id.
BOT_IDENTITY_EXEMPT = {BOT / "identity.py"}

# Reading a chat id is not reading an identity. `chat_id` is where a message
# goes; conflating the two is what made `chat_id=user_id` read as correct for
# two years, so the rule names identity attributes only.
IDENTITY_ATTRS = ("effective_user", "from_user")


def _python_files(root: Path) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*.py"))
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    ]


def _lines_inside_logging_calls(tree: ast.AST) -> set[int]:
    """Line numbers covered by a ``logger.*(...)`` call."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        target = func.value
        if isinstance(target, ast.Name) and target.id in {"logger", "logging"}:
            for inner in ast.walk(node):
                if hasattr(inner, "lineno"):
                    lines.add(inner.lineno)
    return lines


def _string_constants(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _keys_a_query_on_telegram_id(text: str) -> bool:
    """True when this SQL uses telegram_user_id as a LOOKUP KEY.

    Selecting the column is not translation -- ``users.telegram_user_id`` is a
    delivery address and several services legitimately read it as one, the same
    way they read ``timezone``. What must live in one module is *keying* on it:
    a WHERE, a JOIN predicate, or an ON CONFLICT target. That is the operation
    that turns a Telegram id into a learner, and doing it in a second place is
    what this test exists to stop.
    """
    upper = " ".join(text.upper().split())
    if "TELEGRAM_USER_ID" not in upper:
        return False
    if not any(k in upper for k in SQL_KEYWORDS):
        return False
    for marker in ("WHERE", "ON CONFLICT", " ON ", "\nON ", "AND ", "USING ("):
        idx = 0
        while True:
            idx = upper.find(marker, idx)
            if idx == -1:
                break
            # the clause runs to the next major keyword
            tail = upper[idx : idx + 200]
            if "TELEGRAM_USER_ID" in tail.split("ORDER BY")[0]:
                return True
            idx += len(marker)
    return False


def test_only_the_resolver_keys_a_query_on_a_telegram_id() -> None:
    """A query may be *keyed* on telegram_user_id in two modules, no more."""
    offenders: list[str] = []
    for path in _python_files(CORE):
        if path in CORE_SQL_EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for text in _string_constants(tree):
            if _keys_a_query_on_telegram_id(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}")
                break
    assert not offenders, (
        "SQL naming telegram_user_id outside core/services/identity.py and "
        "core/services/access_control.py: " + ", ".join(sorted(set(offenders)))
    )


def test_the_bot_reads_a_telegram_identity_in_one_module() -> None:
    """``effective_user`` / ``from_user`` are read for identity in one place.

    Two deliberate exceptions inside handlers, both about the Telegram *account*
    rather than about a learner, and both required to keep working after 011:

    * operator checks against ``OPERATOR_TELEGRAM_ID``, which names a Telegram
      account -- comparing it to an internal id would silently lock the operator
      out of ``/admin``;
    * ``/start`` and the group -1 gate, which run for somebody who has no
      ``users`` row at all.

    Both call ``apps/bot/identity.telegram_id_of`` or sit in the two modules
    below, so they are visible rather than indistinguishable from a lookup.
    """
    allowed = BOT_IDENTITY_EXEMPT | {
        BOT / "handlers" / "access.py",  # the gate: resolves once for everyone
        BOT / "handlers" / "onboarding.py",  # runs before a users row exists
        BOT / "handlers" / "admin.py",  # operator checks only
        BOT / "handlers" / "access_request.py",  # operator checks only
        BOT / "alerts.py",  # the error path: must report without a users row
    }
    offenders: list[str] = []
    for path in _python_files(BOT):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        logged = _lines_inside_logging_calls(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr != "id":
                continue
            inner = node.value
            if (
                isinstance(inner, ast.Attribute)
                and inner.attr in IDENTITY_ATTRS
                # Logging an id is not translating one. PRD §10 wants ids in the
                # logs, and a log line never selects a row.
                and node.lineno not in logged
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert not offenders, (
        "a Telegram id read as an identity outside apps/bot/identity.py: "
        + ", ".join(offenders)
    )


def test_the_session_carries_an_internal_id() -> None:
    """``AuthenticatedUser`` must not hand a Telegram id to the API.

    Before W4b this field was ``telegram_user_id``, which is precisely why the
    API could not represent a learner who had never used Telegram.
    """
    from core.services.auth import AuthenticatedUser

    names = set(AuthenticatedUser.__dataclass_fields__)
    assert "id" in names
    assert "telegram_user_id" not in names


def test_the_api_never_names_a_telegram_id() -> None:
    """``apps/api`` is web-only and must not know Telegram exists."""
    offenders: list[str] = []
    for path in _python_files(API):
        if "telegram" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "apps/api mentions telegram: " + ", ".join(offenders)
    )


def test_the_resolver_is_the_only_public_translation() -> None:
    """The resolver's surface, stated so a second one is a visible addition."""
    from core.services import identity

    exported = {
        n
        for n in dir(identity)
        if not n.startswith("_") and callable(getattr(identity, n))
    }
    assert {
        "user_id_for_telegram",
        "require_user_id_for_telegram",
        "telegram_address_for_user",
        "create_web_user",
        "save_onboarding",
    } <= exported
