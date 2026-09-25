"""W13c: the known-word floor is a number per learner, and the covered set is
computed from it at read time.

THE ACCEPTANCE, AS THE ROW WRITES IT: **two learners with materially different
floors receive materially different material from the same selection code and
no branch.** Asserted twice through what a learner is served — block 2's unknown
words through `GET /session/today` on the ASGI transport, and the talk topic's
unit words through `_topic_sources`, whose broad `except` would otherwise turn a
broken query into an empty list nobody notices.

Expected values are ranks read from `data/lexemes.tsv` via the dev database —
`worth` 669, `manage` 993, `rent` 1350, `flat` 1415 — and unit 1's candidates,
which all sit at rank 2001–3759. Nothing expected is derived from the code
under test (CLAUDE.md §3 rule 5).

**RED DEMONSTRATIONS (2026-09-25):**

* `test_two_floors_two_sets_of_unknown_words_on_the_same_video` and
  `test_two_floors_two_topic_word_lists` went red with `EFFECTIVE_LEDGER`'s
  floor branch changed to `fl.freq_rank <= 2000` (the old global) — both
  learners were served the same words.
* `test_the_before_after_table_shows_parity_over_w4_rows` went red with
  `materialised_ledger` changed to filter `source <> 'assumption'` — 1,198
  lemmas only-after.
* `test_a_dry_correction_writes_nothing` went red with `_correct`'s
  `conn.rollback()` changed to `conn.commit()`.
* `test_the_range_the_cli_refuses_is_the_range_the_check_refuses` went red with
  `FLOOR_RANGE = range(0, 20_000)`.
* `test_nothing_in_core_writes_an_assumption_row` went red with
  `assume_top_frequency_known` restored to `services/lexicon.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.lexicon import floor as floor_cli
from core.services import lexicon as lex
from core.services import syllabus
from core.services import video as video_svc
from core.services.conversations import _topic_sources
from core.services.lexicon import LedgerEntry
from core.services.sessions import local_today

ID_PREFIX = "w13cf"
REPO = Path(__file__).resolve().parents[1]

# Ranks 600–1,500, so a floor of 600 leaves them unknown and 3,000 covers them.
TRANSCRIPT = (
    "It was worth it in the end. We manage the rent on the flat somehow, "
    "and the trade is fine because the flat is close to work. "
) * 12


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


def _make_learner(db, floor: int, language: str):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    user_id = int(
        db.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                               cefr_level, auth_email, auth_user_id, timezone,
                               known_word_floor)
            VALUES (%s, 'W13c floor', %s, TRUE, 'B1', %s, %s, 'Europe/Vilnius', %s)
            RETURNING id
            """,
            (
                telegram_user_id,
                language,
                f"w13c-{abs(telegram_user_id)}@example.test",
                str(uuid.uuid4()),
                floor,
            ),
        ).fetchone()[0]
    )
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W13c floor', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (
            hashlib.sha256(raw.encode()).digest(),
            user_id,
            datetime.now(timezone.utc) + timedelta(days=30),
        ),
    )
    return type("L", (), {"user_id": user_id, "cookie": raw})()


@pytest.fixture
def two_learners(db):
    """Same B1 profile, different floors: 600 and 3,000."""
    low = _make_learner(db, 600, "fa")
    high = _make_learner(db, 3000, "lt")
    db.commit()
    yield low, high
    for learner in (low, high):
        uid = learner.user_id
        db.execute("DELETE FROM video_assignments WHERE user_id = %s", (uid,))
        db.execute("DELETE FROM video_coverage WHERE user_id = %s", (uid,))
    db.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (f"{ID_PREFIX}%",))
    for learner in (low, high):
        uid = learner.user_id
        for table in ("user_lexemes", "sessions", "user_unit_state", "access_requests"):
            db.execute(f"DELETE FROM {table} WHERE user_id = %s", (uid,))
        db.execute("DELETE FROM users WHERE id = %s", (uid,))
    db.commit()


def _request(path: str, cookie: str) -> httpx.Response:
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(), client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={SESSION_COOKIE_SECURE: cookie},
        ) as http:
            return await http.get(path)

    return asyncio.run(_go())


def _assign(db, learner, video_id: int) -> None:
    video_svc.assign_video(
        db,
        user_id=learner.user_id,
        video_id=video_id,
        assigned_for=local_today("Europe/Vilnius", datetime.now(timezone.utc)),
        score_breakdown={},
    )


# ── the acceptance: same code, no branch, different material ────────────────


def test_two_floors_two_sets_of_unknown_words_on_the_same_video(db, two_learners) -> None:
    low, high = two_learners
    now = datetime.now(timezone.utc)
    video_id = video_svc.upsert_video(
        db,
        youtube_id=f"{ID_PREFIX}00001",
        channel_id="UCw13cfloor00000000000",
        accent="british",
        track="life",
        title="A floor probe",
        duration_s=720,
        published_at=now - timedelta(days=2),
        now=now,
    )
    video_svc.record_transcript(
        db, video_id=video_id, text=TRANSCRIPT, lang="en", kind="manual"
    )
    _assign(db, low, video_id)
    _assign(db, high, video_id)
    db.commit()

    served = {}
    for learner in (low, high):
        response = _request("/session/today", learner.cookie)
        assert response.status_code == 200, response.text
        block = next(b for b in response.json()["blocks"] if b["kind"] == "input")
        served[learner.user_id] = set(block["payload"]["unknown_lemmas"])

    for word in ("worth", "manage", "rent", "flat"):
        assert word in served[low.user_id], word
        assert word not in served[high.user_id], word


def test_two_floors_two_topic_word_lists(db, two_learners) -> None:
    """Unit 1's candidates sit at rank 2001–3759: a floor of 600 leaves them
    all, a floor of 3,000 removes most — through the talk topic's own reader."""
    low, high = two_learners
    # `dict_row`, as the app's pool is opened: `_topic_sources` reads by key, and
    # its broad `except` turns a tuple row into an empty list — which is how the
    # first draft of this test failed, and why it asserts a length and not only
    # a difference.
    with psycopg.connect(load_settings().database_url, row_factory=dict_row) as conn:
        low_words = _topic_sources(conn, low.user_id)["unit_lexemes"]
        high_words = _topic_sources(conn, high.user_id)["unit_lexemes"]
    assert len(low_words) == 12
    assert low_words != high_words

    low_targets = syllabus.unit_target_lexemes(db, low.user_id, 1)
    high_targets = syllabus.unit_target_lexemes(db, high.user_id, 1)
    assert len(low_targets) == 65
    assert 0 < len(high_targets) < 65
    assert set(high_targets) < set(low_targets)
    ranks = dict(
        db.execute(
            "SELECT lemma, freq_rank FROM lexemes WHERE lemma = ANY(%s)", (high_targets,)
        ).fetchall()
    )
    assert all(rank > 3000 for rank in ranks.values())


# ── the before/after table: the ruling's gate ───────────────────────────────


def _w4_era_rows(conn, user_id: int, top_n: int) -> None:
    """What W4's floor wrote and production keeps (see test_lexicon_demotion)."""
    conn.execute(
        """
        INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank)
        SELECT %s, id, 'known', 'assumption', 0
          FROM lexemes WHERE freq_rank IS NOT NULL AND freq_rank <= %s
        """,
        (user_id, top_n),
    )


@pytest.fixture
def ledger_user(db):
    user_id = int(
        db.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                               known_word_floor)
            VALUES (%s, 'W13c parity', 'fa', TRUE, 1200) RETURNING id
            """,
            (-secrets.randbelow(1_000_000_000) - 1,),
        ).fetchone()[0]
    )
    yield user_id
    db.rollback()


def _lemma_at(db, rank: int) -> str:
    return db.execute("SELECT lemma FROM lexemes WHERE freq_rank = %s", (rank,)).fetchone()[0]


def test_the_before_after_table_shows_parity_over_w4_rows(db, ledger_user) -> None:
    """Production's shape: W4 rows at the floor, then history on top of them —
    a tap that demoted one, a correction that re-attributed one, an exposure
    the conflict rule refused, and evidence outside the floor."""
    _w4_era_rows(db, ledger_user, 1200)
    lex.record(
        db,
        ledger_user,
        [
            LedgerEntry(_lemma_at(db, 40), "seen", "tapped"),
            LedgerEntry(_lemma_at(db, 41), "known", "correction"),
            LedgerEntry(_lemma_at(db, 42), "seen", "v2_encountered"),
            LedgerEntry(_lemma_at(db, 5000), "known", "correction"),
            LedgerEntry(_lemma_at(db, 5001), "learning", "v2_studied"),
        ],
    )
    table = floor_cli.measure(db, ledger_user)
    assert table.parity, floor_cli.render(table)
    assert len(table.covered_after) == 1200 - 1 + 1
    assert table.kept_assumption_rows == 1200 - 2


def test_a_lowered_floor_is_reported_as_a_named_difference(db, ledger_user) -> None:
    """Lowering the floor is the one way the two readings part, and the table
    names every lemma and why rather than printing a bare mismatch."""
    _w4_era_rows(db, ledger_user, 1200)
    lex.set_known_word_floor(db, ledger_user, 1000)
    table = floor_cli.measure(db, ledger_user)
    assert not table.parity
    assert len(table.only_before) == 200
    assert table.only_after == frozenset()
    assert _lemma_at(db, 1100) in table.only_before
    assert "OUTSIDE this learner's floor" in floor_cli.render(table)


def test_a_new_learner_has_no_rows_and_the_whole_floor(db, ledger_user) -> None:
    """Option (d): nothing materialised, the covered set computed."""
    assert db.execute(
        "SELECT COUNT(*) FROM user_lexemes WHERE user_id = %s", (ledger_user,)
    ).fetchone()[0] == 0
    covered = lex.known_lemmas(db, ledger_user)
    assert len(covered) == 1200
    assert _lemma_at(db, 1200) in covered
    assert _lemma_at(db, 1201) not in covered


# ── the correction path: an operator CLI, dry by default ────────────────────


@pytest.fixture
def committed_learner(db):
    user_id = int(
        db.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language, onboarded)
            VALUES (%s, 'W13c cli', 'lt', TRUE) RETURNING id
            """,
            (-secrets.randbelow(1_000_000_000) - 1,),
        ).fetchone()[0]
    )
    lex.record(db, user_id, [LedgerEntry(_lemma_at(db, 7000), "known", "correction")])
    db.commit()
    yield user_id
    db.execute("DELETE FROM user_lexemes WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def _floor_of(db, user_id: int) -> int:
    db.rollback()
    return db.execute(
        "SELECT known_word_floor FROM users WHERE id = %s", (user_id,)
    ).fetchone()[0]


def test_a_dry_correction_writes_nothing(db, committed_learner, capsys) -> None:
    assert floor_cli.main(["--user", str(committed_learner), "--set", "2500"]) == 0
    out = capsys.readouterr().out
    assert "floor 2000 → 2500" in out
    assert "covered set       2001 → 2501" in out
    assert "words you know    1 → 1" in out
    assert "DRY: rolled back" in out
    assert _floor_of(db, committed_learner) == 2000


def test_an_applied_correction_writes_and_moves_no_visible_count(
    db, committed_learner, capsys
) -> None:
    assert floor_cli.main(
        ["--user", str(committed_learner), "--set", "800", "--apply"]
    ) == 0
    assert "APPLIED." in capsys.readouterr().out
    assert _floor_of(db, committed_learner) == 800
    # The learner-visible count, read independently of the CLI's own print.
    assert db.execute(
        """
        SELECT COUNT(*) FROM user_lexemes
         WHERE user_id = %s AND state IN ('known', 'mastered')
           AND source <> 'assumption'
        """,
        (committed_learner,),
    ).fetchone()[0] == 1


def test_the_cli_refuses_out_of_range_before_the_database(db, committed_learner) -> None:
    """A CHECK violation's DETAIL prints the whole `users` row — goals text
    included — so the CLI must refuse first. Found rehearsing the command."""
    with pytest.raises(SystemExit) as exit_:
        floor_cli.main(["--user", str(committed_learner), "--set", "20001"])
    assert exit_.value.code == 2
    assert _floor_of(db, committed_learner) == 2000


def test_the_range_the_cli_refuses_is_the_range_the_check_refuses(db) -> None:
    definition = db.execute(
        """
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
         WHERE conname = 'users_known_word_floor_in_range'
        """
    ).fetchone()[0]
    low, high = (int(n) for n in re.findall(r"\d+", definition))
    assert (low, high) == (0, 20000)
    assert (lex.FLOOR_RANGE.start, lex.FLOOR_RANGE.stop - 1) == (0, 20000)


# ── migration 030 ───────────────────────────────────────────────────────────


def test_the_column_is_an_integer_defaulting_to_the_w4_floor(db) -> None:
    row = db.execute(
        """
        SELECT data_type, is_nullable, column_default
          FROM information_schema.columns
         WHERE table_name = 'users' AND column_name = 'known_word_floor'
        """
    ).fetchone()
    assert row == ("integer", "NO", "2000")


def test_the_delivery_view_carries_the_column(db) -> None:
    """#48: the view is `SELECT u.*` and freezes its columns at creation."""
    assert db.execute(
        """
        SELECT COUNT(*) FROM information_schema.columns
         WHERE table_name = 'approved_onboarded_users'
           AND column_name = 'known_word_floor'
        """
    ).fetchone()[0] == 1


# ── option (d): no `assumption` row is written by anything ──────────────────


def test_nothing_in_core_writes_an_assumption_row() -> None:
    """Kept rows stay; new ones are never written. Two ways to write one:
    SQL naming the source in an INSERT, and a `LedgerEntry` carrying it. The one
    `LedgerEntry` allowed is `_floor_entry`, the virtual row `record` compares
    against and never sends."""
    offenders = []
    for path in (REPO / "packages" / "core").rglob("*.py"):
        text = path.read_text()
        for insert in re.findall(r"INSERT INTO user_lexemes.*?(?:\"\"\"|$)", text, re.S):
            if "'assumption'" in insert:
                offenders.append(f"{path.name}: INSERT")
        for match in re.finditer(r"LedgerEntry\([^)]*[\"']assumption[\"']", text):
            before = text[: match.start()]
            enclosing = re.findall(r"^def (\w+)", before, re.M)
            if not enclosing or enclosing[-1] != "_floor_entry":
                offenders.append(f"{path.name}: LedgerEntry in {enclosing[-1:]}")
    assert offenders == []
    assert not hasattr(lex, "assume_top_frequency_known")
