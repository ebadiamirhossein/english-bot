"""W32a — `core.services.dictionary`: the planner, the store, and the backfill run.

**Nothing here spends anything.** The transport is mocked at
`core.llm.anthropic.Anthropic` (standing rule 7) and the session netguard
refuses any socket. **Expected values are hardcoded or computed from an
independent source** (rule 5): the lexeme scope is read straight from
`data/lexemes.tsv`, never from the function under test.

**RED BEFORE THE CODE (2026-09-28):** `core.services.dictionary` did not exist.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from core.config import load_settings
from core.services import dictionary
from core.services import video as video_svc
from core.video import explain

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PREFIX = "w32adict"
LEXEMES = Path(__file__).resolve().parents[1] / "data" / "lexemes.tsv"


def _db():
    return psycopg.connect(load_settings().database_url)


@pytest.fixture
def clean_dictionary():
    yield
    with _db() as conn:
        conn.execute("DELETE FROM word_dictionary WHERE model LIKE 'w32a-test%%'")
        conn.execute("DELETE FROM word_dictionary WHERE lemma LIKE 'zqw%%'")
        conn.commit()


@pytest.fixture
def video():
    cues = [
        {"text": "Thank you, Dr. Phillips.", "start": 0.0, "duration": 2.0},
        {"text": "They're moving the parties over here.", "start": 2.0, "duration": 3.0},
        {"text": "I'm gonna grab the zqwmarker.", "start": 5.0, "duration": 2.0},
    ]
    with _db() as conn:
        vid = video_svc.upsert_video(
            conn, youtube_id=f"{PREFIX}{secrets.token_hex(2)}", channel_id="UCw32adict0000000000000",
            accent="british", track="life", title="dictionary probe", duration_s=10,
            published_at=NOW - timedelta(days=1), now=NOW,
        )
        video_svc.record_transcript(
            conn, video_id=vid, text=" ".join(c["text"] for c in cues), lang="en",
            kind="manual", cues=cues,
        )
        conn.commit()
    yield vid
    with _db() as conn:
        conn.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (f"{PREFIX}%",))
        conn.commit()


# ── the key: one tappable token → one entry ──────────────────────────────────


@pytest.mark.parametrize(
    ("token", "key"),
    [
        ("moving", "move"),     # the coverage lemma
        ("parties", "party"),   # #468's case
        ("Over", "over"),       # casefolded
        ("gonna", "gonna"),     # off-list: the surface is the key
        ("zqwmarker", "zqwmarker"),
        ("1990", None),         # a number is no word
        ("café", None),         # the page taps it; no key can hold it
    ],
)
def test_the_key_of_a_token(token, key) -> None:
    assert dictionary.key_for(token) == key


def test_a_videos_keys_skip_its_names(video) -> None:
    with _db() as conn:
        forms, names = dictionary.video_keys(conn, video)
    assert "phillips" in names and "phillips" not in forms
    assert forms["moving"] == "move" and forms["parties"] == "party"
    assert forms["gonna"] == "gonna"


# ── the backfill's scope (ruling C1) ────────────────────────────────────────


def _tagged_top(n: int) -> list[str]:
    """The top-n TAGGED lexemes by `freq_rank`, straight from the TSV."""
    rows = []
    for line in LEXEMES.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.startswith("lemma\t"):
            continue
        lemma, pos, rank, _band, _cefr = line.split("\t")
        if pos:
            rows.append((int(rank), lemma))
    return [lemma for _rank, lemma in sorted(rows)[:n]]


def test_the_scope_is_the_pool_plus_the_top_tagged_lexemes(video) -> None:
    """Top 100: the TSV's first untagged rows are *oh* (rank 56), *gonna* (87)
    and *didn* (93), so a scope that forgot the tag would hold them — the
    mutation that proved a top-50 version of this test blind (W32a)."""
    with _db() as conn:
        plan = dictionary.plan_backfill(conn, top=100, video_ids=[video])
    expected_lex = {w for w in _tagged_top(100) if explain.WORD_KEY.match(w)}
    assert "oh" not in plan.lexemes and "didn" not in plan.lexemes
    assert set(plan.lexemes) == expected_lex
    assert {"move", "party", "gonna", "zqwmarker"} <= set(plan.pool)
    assert "phillips" not in plan.pool
    assert set(plan.union) == set(plan.pool) | expected_lex
    assert plan.untagged_excluded > 0


def test_a_held_word_is_not_bought_twice(video, clean_dictionary) -> None:
    with _db() as conn:
        dictionary.insert_entry(
            conn, explain.Entry("zqwmarker", "name", (), None, None, None),
            model="w32a-test", source="backfill",
        )
        conn.commit()
        plan = dictionary.plan_backfill(conn, top=0, video_ids=[video])
    assert "zqwmarker" in plan.union and "zqwmarker" not in plan.to_buy


def test_the_insert_is_idempotent(clean_dictionary) -> None:
    entry = explain.Entry("zqwidem", "word", (explain.Sense("verb", "to test", {"fa": "آزمودن"}),),
                          "neutral", None, None)
    with _db() as conn:
        first = dictionary.insert_entry(conn, entry, model="w32a-test", source="backfill")
        second = dictionary.insert_entry(conn, entry, model="w32a-test", source="backfill")
        conn.commit()
        held = dictionary.held(conn, ["zqwidem", "zqwnothere"])
    assert (first, second) == (True, False)
    assert held == frozenset({"zqwidem"})


# ── the cost line ────────────────────────────────────────────────────────────


def test_the_ceiling_is_arithmetic_on_max_tokens() -> None:
    """20 words, Sonnet 5 at $2 / $10: one call whose ceiling is its input
    estimate plus `max_tokens` (2,000 + 20 × (60 + 3 × (45 + 2 × 80)) = 15,500)."""
    cost = dictionary.estimate(20, n_langs=2, model="claude-sonnet-5")
    assert cost.calls == 1
    assert cost.ceiling_output_tokens == 15_500
    expected = (cost.input_tokens * 2.0 + 15_500 * 10.0) / 1_000_000
    assert cost.ceiling_usd == pytest.approx(expected)
    assert cost.typical_usd < cost.ceiling_usd


def test_an_unknown_model_has_no_price() -> None:
    assert dictionary.estimate(20, n_langs=2, model="some-model").ceiling_usd is None


# ── the run ─────────────────────────────────────────────────────────────────


def _asked(kwargs) -> list[str]:
    body = "".join(m["content"] for m in kwargs["messages"])
    return body.split(explain.DICT_OPEN, 1)[1].split(explain.DICT_CLOSE, 1)[0].split()


def _answer(**kwargs):
    entries = [
        {"word": w, "kind": "word", "register": "neutral", "neutral_equivalent": None,
         "who_says_this": None,
         "senses": [{"pos": "noun", "definition": f"a {w}", "l1": {"fa": "چیز"}}]}
        for w in _asked(kwargs)
    ]
    message = MagicMock()
    block = MagicMock()
    block.text = json.dumps({"entries": entries})
    message.content = [block]
    message.stop_reason = "end_turn"
    message.usage = MagicMock(input_tokens=900, output_tokens=300,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return message


def _status(status: int, text: str = "x"):
    import anthropic

    response = MagicMock()
    response.status_code = status
    response.headers = {}
    return anthropic.APIStatusError(message=text, response=response,
                                    body={"error": {"message": text}})


WORDS = [f"zqw{c}{d}" for c in "abc" for d in "abcdefghijklm"][:25]  # two batches


@pytest.fixture
def transport():
    with patch("core.llm.anthropic.Anthropic") as cls, \
         patch("core.llm.time.sleep", return_value=None):
        yield cls.return_value


def _run(**over):
    args = {"words": WORDS, "apply": True, "concurrency": 1, "source": "backfill",
            "model": "w32a-test", "languages": ("fa",), "sleep": lambda s: None}
    args.update(over)
    return dictionary.run_backfill(**args)


def test_a_dry_run_makes_no_call_and_writes_nothing(transport, clean_dictionary) -> None:
    report = _run(apply=False)
    assert transport.messages.create.call_count == 0
    assert report.written == 0
    with _db() as conn:
        assert dictionary.held(conn, WORDS) == frozenset()


def test_an_applied_run_writes_every_word_in_batches(transport, clean_dictionary) -> None:
    transport.messages.create.side_effect = _answer
    report = _run()
    assert transport.messages.create.call_count == 2  # 25 words, 20 a call
    assert (report.written, sum(report.refused.values()), report.deferred) == (25, 0, 0)
    assert report.output_tokens == 600
    with _db() as conn:
        assert dictionary.held(conn, WORDS) == frozenset(WORDS)


def test_a_rate_limit_backs_off_and_is_never_a_refusal(transport, clean_dictionary) -> None:
    """**C3, red first.** `chat()` retries a 429 three times and then raises; the
    run must WAIT and ask again, not count 20 words refused. The same for an
    overloaded provider (529)."""
    waits: list[float] = []
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] <= 3:          # chat()'s three attempts, all rate-limited
            raise _status(429)
        if calls["n"] <= 6:          # the next three, overloaded
            raise _status(529)
        return _answer(**kwargs)

    transport.messages.create.side_effect = flaky
    report = _run(sleep=waits.append)
    assert report.written == 25
    assert sum(report.refused.values()) == 0 and report.deferred == 0
    assert waits == list(dictionary.TRANSIENT_WAITS_S[:2])


def test_a_provider_that_stays_down_defers_the_words_and_says_so(transport, clean_dictionary) -> None:
    transport.messages.create.side_effect = _status(529)
    report = _run(words=WORDS[:5])
    assert report.written == 0 and sum(report.refused.values()) == 0
    assert report.deferred == 5
    assert report.stopped == "provider unavailable"


def test_the_spend_limit_stops_the_run(transport, clean_dictionary) -> None:
    transport.messages.create.side_effect = _status(400, "You have reached your API usage limits")
    report = _run()
    assert transport.messages.create.call_count == 1
    assert report.stopped == "spend limit"
    assert report.written == 0 and report.deferred == 25


def test_refusals_are_counted_by_reason(transport, clean_dictionary) -> None:
    def half_bad(**kwargs):
        message = _answer(**kwargs)
        entries = json.loads(message.content[0].text)["entries"]
        entries[0]["register"] = "casual"
        message.content[0].text = json.dumps({"entries": entries})
        return message

    transport.messages.create.side_effect = half_bad
    report = _run(words=WORDS[:5])
    assert report.written == 4
    assert report.refused == {"register": 1}


def test_a_pilot_writes_a_report_and_no_row(transport, clean_dictionary, tmp_path) -> None:
    transport.messages.create.side_effect = _answer
    out = tmp_path / "pilot.jsonl"
    report = _run(words=WORDS[:3], pilot_out=out)
    assert report.written == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["word"] for r in rows] == WORDS[:3]
    assert rows[0]["senses"][0]["l1"] == {"fa": "چیز"}
    with _db() as conn:
        assert dictionary.held(conn, WORDS) == frozenset()


def test_the_end_line_reports_everything(transport, clean_dictionary, caplog) -> None:
    transport.messages.create.side_effect = _answer
    caplog.set_level("INFO")
    _run(words=WORDS[:5])
    line = [r.message for r in caplog.records if r.message.startswith("done ")][-1]
    for part in ("written=5", "refused=0", "deferred=0", "output_tokens=300", "calls=1"):
        assert part in line


# ── the command ─────────────────────────────────────────────────────────────


def test_the_command_is_dry_by_default_and_prints_scope_and_ceiling(transport, caplog) -> None:
    """C1 and C4: the dry run names (a), (b), their union and the untagged it
    left out, and its cost line ENDS with the ceiling in dollars — the figure
    the operator sets against the Console's limit before `--apply`."""
    from core.video import dictionary as command

    caplog.set_level("INFO")
    assert command.main(["--top", "30"]) == 0
    assert transport.messages.create.call_count == 0
    text = [r.message for r in caplog.records]
    scope = next(m for m in text if m.startswith("scope=c1"))
    for part in ("pool_words=", "tagged_lexemes=", "union=", "to_buy=", "excluded_untagged="):
        assert part in scope
    cost = next(m for m in text if m.startswith("words_this_run="))
    assert cost.split()[-1].startswith("ceiling_usd=")
    assert any("DRY RUN" in m for m in text)


def test_the_pilot_words_are_sixty_fixed_keys() -> None:
    from core.video.dictionary import PILOT_WORDS

    assert len(PILOT_WORDS) == len(set(PILOT_WORDS)) == 60
    assert all(explain.WORD_KEY.match(w) for w in PILOT_WORDS)
    assert {"over", "move", "shed", "dinosaur", "gonna"} <= set(PILOT_WORDS)
