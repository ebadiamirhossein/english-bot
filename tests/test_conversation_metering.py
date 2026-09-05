"""W13b's metering, and the line it may not cross.

**Turns, seconds, tokens and call counts are metrics. What was said is not**
(CLAUDE.md §5: logs carry user ids and route names, never message bodies; PRD
§12.8: the operator panel shows activity, never content).

Mocked at the transport (`anthropic.Anthropic`), never at `chat()` — standing
rule 7. Mocking the service function would prove nothing about the thing under
test, which is precisely how many provider responses got counted.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from core import llm

REPO = Path(__file__).resolve().parents[1]


class _Usage:
    def __init__(self, i: int, o: int) -> None:
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text: str, i: int, o: int, stop: str = "end_turn") -> None:
        self.content = [_Block(text)]
        self.usage = _Usage(i, o)
        self.stop_reason = stop


def _client(responses: list[_Response]):
    calls = {"n": 0}

    class _Messages:
        def create(self, **kwargs):
            r = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            return r

    class _Client:
        def __init__(self, **kwargs) -> None:
            self.messages = _Messages()

    return _Client, calls


def test_usage_out_accumulates_across_the_json_repair_call() -> None:
    """**ADDS INTO, NEVER ASSIGNS — the correctness point, not a style choice.**

    One `chat()` can reach the provider more than once: the backoff retries, and
    `json_mode`'s repair path makes a further call with the failed text in it.
    **Every one is billed.** A counter recording only the last response would
    under-report exactly the way #321's floor did — by excluding the part that
    costs — and it would look precise while doing it.

    RED against an `_accumulate_usage` that assigned rather than summed: `calls`
    came back 1 and the token totals were the second response's alone.
    """
    Client, calls = _client([
        _Response("not json at all", 100, 10),
        _Response('{"ok": true}', 250, 20),
    ])
    usage: dict = {}
    with patch.object(llm.anthropic, "Anthropic", Client):
        out = llm.chat([{"role": "user", "content": "x"}],
                       json_mode=True, usage_out=usage)
    assert out == {"ok": True}
    assert calls["n"] == 2, "the repair call really happened"
    assert usage["calls"] == 2
    assert usage["input_tokens"] == 350, "100 + 250, both billed"
    assert usage["output_tokens"] == 30


def test_a_truncated_response_is_counted_even_though_it_raises() -> None:
    """**The most expensive failure must not be the one that reports zero.**

    `reject_truncation` raises AFTER a response was generated and billed —
    #198's 8,000-token thinking budget is the incident. Accumulation therefore
    happens before the raise.

    RED against an implementation that counted on the way out of `chat()`: the
    counter stayed empty and the run that cost the most recorded nothing.
    """
    Client, _ = _client([_Response("half a sen", 900, 8000, stop="max_tokens")])
    usage: dict = {}
    with patch.object(llm.anthropic, "Anthropic", Client):
        with pytest.raises(llm.LLMError):
            llm.chat([{"role": "user", "content": "x"}],
                     max_tokens=8000, reject_truncation=True, usage_out=usage)
    assert usage["calls"] == 1
    assert usage["output_tokens"] == 8000


def test_omitting_usage_out_changes_nothing_for_every_existing_caller() -> None:
    """The hook is additive: the return type and every call site are untouched."""
    Client, _ = _client([_Response("hello", 5, 5)])
    with patch.object(llm.anthropic, "Anthropic", Client):
        assert llm.chat([{"role": "user", "content": "x"}]) == "hello"


def test_the_request_carries_no_tools_key() -> None:
    """§2d: no tool use, pinned at the transport rather than asserted in prose.

    A conversation turn is the learner's own text reaching a model; a tool the
    model could invoke would turn a weak threat model into a real one.
    """
    seen: dict = {}

    class _Messages:
        def create(self, **kwargs):
            seen.update(kwargs)
            return _Response("hi", 1, 1)

    class _Client:
        def __init__(self, **kwargs) -> None:
            self.messages = _Messages()

    with patch.object(llm.anthropic, "Anthropic", _Client):
        llm.chat([{"role": "user", "content": "x"}], system="s")
    assert "tools" not in seen
    assert "tool_choice" not in seen


# ── the line that does not bend ─────────────────────────────────────────────


def _string_args_of_log_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute)
                and f.attr in {"debug", "info", "warning", "error", "exception"}):
            continue
        for arg in node.args[1:]:
            out.append(ast.unparse(arg))
    return out


def test_no_log_call_in_the_conversation_slice_can_carry_a_message_body() -> None:
    """CLAUDE.md §5, enforced by reading the source rather than by convention.

    **Blunt on purpose**, the way the frontend guilt scan is: any log argument
    naming a variable that could hold a turn fails, and the fix is to log the
    count instead. A scan that tried to tell a safe string from an unsafe one is
    a scan that misses the unsafe one.

    RED against a `logger.info("... %s", text)` added to `_generate_reply`.
    """
    banned = {
        "text", "reply", "content", "learner_text", "transcript", "you_said",
        "correct_form", "explanation", "topic_label", "opener", "turn",
    }
    offenders: list[str] = []
    for path in [
        REPO / "packages/core/services/conversations.py",
        *(REPO / "packages/core/conversation").rglob("*.py"),
        REPO / "apps/api/routers/conversation.py",
    ]:
        for expr in _string_args_of_log_calls(path):
            if any(b == expr or expr.endswith(f".{b}") for b in banned):
                offenders.append(f"{path.name}: {expr}")
    assert offenders == [], (
        "logs carry user ids and counts, never message bodies (CLAUDE.md §5): "
        + "; ".join(offenders)
    )


def test_the_body_scan_catches_a_real_violation() -> None:
    """#345's shape from the other side: prove the scanner is not inert."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write('import logging\nlogger = logging.getLogger(__name__)\n'
                 'def f(text):\n    logger.info("said %s", text)\n')
        p = Path(fh.name)
    assert "text" in _string_args_of_log_calls(p)


def test_the_usage_table_holds_no_column_that_could_carry_text() -> None:
    """**Counts only, asserted against the live schema, not against the `.sql`.**

    A TEXT column added later fails this rather than the review. Reading
    `information_schema` rather than the migration file is deliberate — the
    question is what the database has, not what a file says it should.
    """
    psycopg = pytest.importorskip("psycopg")
    from core.config import load_settings
    from core.db import connection

    try:
        cm = connection()
    except Exception:  # noqa: BLE001
        pytest.skip("no database configured")
    try:
        with cm as conn:
            rows = conn.execute(
                """
                SELECT column_name, data_type
                  FROM information_schema.columns
                 WHERE table_name = 'conversation_usage'
                """
            ).fetchall()
    except psycopg.OperationalError:
        pytest.skip("database not reachable")
    if not rows:
        pytest.skip("migration 025 not applied here")
    textual = {
        r["column_name"] for r in rows
        if "char" in r["data_type"] or r["data_type"] == "text"
    }
    assert textual == set(), (
        f"conversation_usage may hold counts only; found {sorted(textual)}"
    )
    assert {r["column_name"] for r in rows} >= {
        "turns_learner", "turns_app", "llm_calls", "llm_input_tokens",
        "llm_output_tokens", "stt_seconds", "stt_calls", "tts_calls",
    }
