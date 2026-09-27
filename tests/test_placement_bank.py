"""W18 — `python -m core.placement.bank`, the placement bank's build command.

User action: none — **the operator** runs it (dry → `--free --apply` → `--live`
→ `--apply`) on the host, from the launch pass's probes list. Each test names
which of those invocations it exercises. The autouse `netguard` (conftest)
makes any real provider call raise, so a dry path that sent something would fail
here rather than bill.

**Expected values are independent of the code under test:** the pseudo-word
check re-reads `data/lexemes.tsv` and `data/inflections.tsv` from disk rather
than asking the service; the ceiling is worked by hand from the slots.

**RED DEMONSTRATIONS (2026-09-25), each one edit, run, and restored:**
`NOT_A_TEST_WORD` emptied turned `test_the_real_words_are_content_words_by_band_and_tag`
red (*his* at rank 70 came back); `_refused` returning None turned
`test_apply_writes_what_passed_and_refuses_an_l1_gloss_cue` red; the audio
term removed from `calls_for` turned `test_the_ceiling_is_itemised_from_the_slots`
red; `item_types=` dropped from `run`'s `generate_drafts` call turned
`test_a_listening_cohort_sends_the_listening_contract` red.
**The rest, by a scripted mutation each:** the dry run writing the free rows;
the typed confirmation skipped; the plan ignoring what the bank holds; the
payload naming a learner's L1; the plan's `real` set without `inflections()`
(the new test that declares a generated word an inflected form — no generated
word happens to be one, so the older sample test could not see this, and a
first sweep showed it green); the content check (below); `sample` returning the
whole plan.
"""

from __future__ import annotations

import json
from collections import Counter
import re
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest

from core.config import load_settings
from core.items import generate
from core.items.gates import ValidationReport
from core.placement import bank as build
from core.placement.targets import NOT_A_TEST_WORD
from tests.test_drills import _sdk_response

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def empty_bank(db):
    assert db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0] == 0, (
        "the development bank is expected empty (the bank is built on the host)"
    )
    yield
    db.rollback()
    db.execute("DELETE FROM placement_bank WHERE model = 'w18-bank-test' OR section IN "
               "('vocabulary', 'speaking') AND NOT EXISTS (SELECT 1 FROM placement_run_items r "
               "WHERE r.bank_id = placement_bank.id)")
    db.commit()


def _tsv_words(name: str, column: int) -> frozenset[str]:
    out = set()
    for line in (DATA / name).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        out.add(line.split("\t")[column])
    return frozenset(out)


def test_the_dry_run_sends_nothing_and_writes_nothing(capsys, db, empty_bank, tmp_path) -> None:
    """`python -m core.placement.bank` — the dry run."""
    journal = tmp_path / "j.jsonl"
    assert build.main(["--journal", str(journal)]) == 0
    out = capsys.readouterr().out
    assert "dry run — nothing was sent and nothing was written." in out
    assert "calibration label on every row: uncalibrated" in out
    assert re.search(r"calls --live will make, at most: \d+", out)
    assert "rows the free sections would write: 366" in out
    assert not journal.exists()
    assert db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0] == 0


def test_the_real_words_are_content_words_by_band_and_tag(empty_bank) -> None:
    plan = build.plan(build.FREE)
    assert len(plan.words) == 240
    per_band = [0] * 10
    for lemma, rank, cefr in plan.words:
        per_band[(rank - 1) // 1000] += 1
        assert cefr in {"A1", "A2", "B1", "B2"}, lemma
        assert re.fullmatch(r"[a-z]{3,}", lemma), lemma
        assert lemma not in NOT_A_TEST_WORD, lemma
    assert per_band == [24] * 10
    # The dry print that found the defect listed these; none may return.
    drawn = {w for w, _, _ in plan.words}
    assert not drawn & {"his", "some", "you", "what", "sex", "haven"}


def test_the_pseudo_words_are_absent_from_every_lemma_and_every_form(empty_bank) -> None:
    plan = build.plan(build.FREE)
    assert len(plan.pseudo) == 120
    lemmas = _tsv_words("lexemes.tsv", 0)
    forms = _tsv_words("inflections.tsv", 0)
    assert not set(plan.pseudo) & (lemmas | forms)
    assert len(plan.speaking) == 6


def test_the_free_write_needs_the_count_typed_back(db, empty_bank, monkeypatch, capsys) -> None:
    """`--free --apply`: no billed call, and nothing without the typed count."""
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert build.main(["--free", "--apply"]) == 1
    assert db.execute("SELECT COUNT(*) FROM placement_bank").fetchone()[0] == 0

    monkeypatch.setattr("builtins.input", lambda _: "366")
    assert build.main(["--free", "--apply"]) == 0
    assert "written: 366 rows" in capsys.readouterr().out
    counts = dict(db.execute(
        "SELECT section || ':' || COALESCE(is_word::text, '-'), COUNT(*) "
        "FROM placement_bank GROUP BY 1").fetchall())
    assert counts == {"vocabulary:true": 240, "vocabulary:false": 120, "speaking:-": 6}
    assert db.execute(
        "SELECT COUNT(*) FROM placement_bank WHERE calibration <> 'uncalibrated'"
    ).fetchone()[0] == 0
    # A second run tops up nothing: the sections are full.
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("asked to confirm nothing"))
    assert build.main(["--free", "--apply"]) == 0


def test_the_ceiling_is_itemised_from_the_slots() -> None:
    """Worked by hand. Grammar, eight slots typed cloze/error_spot/word_bank in
    turn — 3 cloze (slot family), 3 error_spot, 2 word_bank: generation 1 +
    judge 1 + 8 probes + 2 re-probes × 3 cloze + 8 target probes = 24.
    Listening, six `listening_gap`: 1 + 1 + 0 probes + 2 × 6 (TTS + STT) + 6
    target probes = 20."""
    grammar = build._generated_plan("grammar", Counter(), ())
    first = grammar[0]
    assert [s.item_type for s in first.slots] == [
        "cloze_cued", "error_spot", "word_bank_order"] * 2 + ["cloze_cued", "error_spot"]
    assert build.calls_for(first) == 24
    listening = build._generated_plan("listening", Counter(), ())
    a2 = next(c for c in listening if c.band == "A2")
    assert len(a2.slots) == 6
    assert build.calls_for(a2) == 20


def test_the_plan_asks_for_what_is_short_and_nothing_else() -> None:
    from collections import Counter

    full = Counter({("grammar", "A2", code): 6 for code in
                    ("verb_tense_past", "subject_verb_agreement", "article_missing",
                     "preposition", "plural_countable", "word_order")})
    full[("grammar", "A2", "preposition")] = 4
    cohorts = [c for c in build._generated_plan("grammar", full, ()) if c.band == "A2"]
    assert len(cohorts) == 1
    assert [(s.error_type, s.cohort) for s in cohorts[0].slots] == [
        ("preposition", "placement"), ("preposition", "placement")]
    # No learner's language is named: the bank is shared.
    assert "learner_l1" not in cohorts[0].payload
    assert cohorts[0].payload["can_do"].startswith("A placement check at CEFR A2")


@patch("core.llm.time.sleep", return_value=None)
@patch("core.llm.anthropic.Anthropic")
def test_a_listening_cohort_sends_the_listening_contract(mock_cls, _sleep, monkeypatch, tmp_path) -> None:
    """`--live`'s request construction, mocked at the SDK. The system prompt
    carries `listening_gap`'s `transcript` field, which `SLOT_TYPES` does not."""
    from collections import Counter

    client = mock_cls.return_value
    client.messages.create.return_value = _sdk_response('{"items": []}')
    cohort = next(c for c in build._generated_plan("listening", Counter(), ()) if c.band == "A2")
    plan = build.Plan(cohorts=[cohort])
    build.run(plan, apply=False, settings=load_settings(), journal_path=tmp_path / "j.jsonl")
    kwargs = client.messages.create.call_args.kwargs
    system = kwargs["system"][0]["text"]
    assert "transcript" in system
    assert json.loads(kwargs["messages"][0]["content"]) == cohort.payload
    assert kwargs["max_tokens"] == generate.GENERATE_MAX_TOKENS


def test_apply_writes_what_passed_and_refuses_an_l1_gloss_cue(db, empty_bank, monkeypatch, tmp_path) -> None:
    """`--apply`'s write path, with the model and the gates stubbed at the seams
    W17's test uses. One item passes, one passes with an `l1_gloss` cue (refused:
    the bank is shared by two L1s), one is discarded."""
    from collections import Counter

    cohort = build._generated_plan("grammar", Counter(), ())[0]
    cohort = build.Cohort(cohort.section, cohort.band, cohort.slots[:3], cohort.candidates,
                          cohort.payload, (), cohort.item_types)
    drafts = [
        {"prompt_text": "She ___ to the market yesterday.", "answer": "went",
         "explanation": "Past simple of go."},
        {"prompt_text": "Tap the word that is wrong.", "answer": "goed",
         "tiles": ["I", "goed", "home"], "wrong_index": 1, "correction": "went"},
        {"prompt_text": "x", "answer": "y"},
    ]
    monkeypatch.setattr(generate, "generate_drafts", lambda payload, **_: drafts)

    def _gates(slots, got, **_):
        outs = []
        for n, slot in enumerate(slots):
            item = generate._draft_to_item(got[n], slot, 0) if n < 2 else None
            if n == 1:
                item = item.model_copy(update={"cue_type": "l1_gloss", "cue_text": "رفت"})
            outs.append(generate.Outcome(
                slot=slot, unit_number=0, item=item,
                report=ValidationReport("passed" if n < 2 else "discarded"),
                state="accepted" if n < 2 else "discarded"))
        return outs

    monkeypatch.setattr(generate, "verify_cohort", _gates)
    from dataclasses import replace

    settings = replace(load_settings(), llm_model="w18-bank-test")
    build.run(build.Plan(cohorts=[cohort]), apply=True, settings=settings,
              journal_path=tmp_path / "j.jsonl")
    rows = db.execute(
        "SELECT section, cefr, error_type, item->>'prompt_text', item->>'cohort', calibration "
        "FROM placement_bank").fetchall()
    assert rows == [("grammar", "A2", "verb_tense_past",
                     "She ___ to the market yesterday.", "placement", "uncalibrated")]


def test_no_target_asks_for_what_the_content_gate_refuses() -> None:
    """A target that needs a phrase `BANNED_IN_CONTENT` refuses buys items the
    free stage discards — paid for, and thrown away. **Red:** the C1 modal
    target as first written (*"needn't have, should have and could have"*)."""
    from core.copy_rules import content_offenders
    from core.placement.targets import GRAMMAR_TARGETS, LISTENING_TARGETS, all_targets

    for target in all_targets(GRAMMAR_TARGETS) + all_targets(LISTENING_TARGETS):
        assert not content_offenders(target), target


def test_the_sample_is_one_grammar_and_one_listening_cohort(capsys, empty_bank, tmp_path) -> None:
    """`--sample` (dry here): the probe's live half, 24 + 20 = 44 calls at most
    (the two cohorts `test_the_ceiling_is_itemised_from_the_slots` works by
    hand), and no free row. **Red:** `sample` returning the whole plan — the
    ceiling prints 544."""
    assert build.main(["--sample", "--journal", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "calls --live will make, at most: 44" in out
    assert "rows the free sections would write: 0" in out
    assert "cohorts: 2" in out
    with pytest.raises(SystemExit):
        build.main(["--sample", "--apply"])


def test_an_inflected_form_is_never_a_pseudo_word(empty_bank, monkeypatch) -> None:
    """The draw checks every inflected form, not only lemmas. A sample cannot
    show it (no generated word happens to be one), so one is made to be: the
    first pseudo-word the seed produces is declared an inflected form, and must
    then be absent. **Red:** the plan's `real` set without `inflections()`."""
    first = build.plan(build.FREE).pseudo[0]
    import core.lexicon.normalize as normalize

    monkeypatch.setattr(normalize, "inflections", lambda: {first: "x"})
    assert first not in build.plan(build.FREE).pseudo


# ── B4 (launch 2026-09-26): W18-R1's reading of the host's bank ─────────────
#
# **RED DEMONSTRATIONS (2026-09-26, a scripted mutation each, `python -B`):**
# the draw put back as it was before B4 → the first two tests red (the seeded
# draw holds *englishman*, *mustache* and *moustache*, exactly as the host's
# does; and *moustache* was drawn beside a banked *mustache*). The `ence$` rule
# widened to `ce$` → the spelling-key test red (it merged pairs of DIFFERENT
# words); the `tre$` rule removed → red (pairs lost); *halloween* added to
# `CAPITALISED_IN_USE` → the pool test red.

#: The 39 pairs a person read out of the 5,000-word pool on 2026-09-26, each
#: one word in two spellings. Hardcoded (§3 rule 5): a key rule that starts
#: merging two different words, or stops finding one of these, fails here.
SPELLING_PAIRS = {
    ("adviser", "advisor"), ("apologise", "apologize"), ("behavior", "behaviour"),
    ("catalog", "catalogue"), ("center", "centre"), ("civilisation", "civilization"),
    ("color", "colour"), ("defence", "defense"), ("favor", "favour"),
    ("favorite", "favourite"), ("flavor", "flavour"), ("gray", "grey"),
    ("harbor", "harbour"), ("honor", "honour"), ("honorable", "honourable"),
    ("humor", "humour"), ("enquiry", "inquiry"), ("jewellery", "jewelry"),
    ("judgement", "judgment"), ("kilometer", "kilometre"), ("labor", "labour"),
    ("licence", "license"), ("mama", "mamma"), ("marvellous", "marvelous"),
    ("meter", "metre"), ("moustache", "mustache"), ("neighbor", "neighbour"),
    ("neighborhood", "neighbourhood"), ("offence", "offense"),
    ("organisation", "organization"), ("organise", "organize"),
    ("practice", "practise"), ("program", "programme"), ("realise", "realize"),
    ("recognise", "recognize"), ("rumor", "rumour"), ("theater", "theatre"),
    ("traveler", "traveller"), ("whiskey", "whisky"),
}


def _pool_from_disk() -> set[str]:
    """The draw's pool, read from `data/lexemes.tsv` rather than the service:
    content POS, a CEFR tag, rank 1–10,000, lower-case letters, 3+."""
    out = set()
    rows = [line.split("\t") for line in (DATA / "lexemes.tsv").read_text(
        encoding="utf-8").splitlines() if line and not line.startswith("#")]
    for lemma, pos, rank, _band, cefr in (r[:5] for r in rows[1:]):
        if (rank and int(rank) <= 10_000 and cefr and pos in ("NOUN", "VERB", "ADJ", "ADV")
                and re.fullmatch(r"[a-z]{3,}", lemma)):
            out.add(lemma)
    return out


def test_no_capitalised_word_and_one_spelling_per_word_is_drawn(empty_bank) -> None:
    """User action: the learner sits the yes/no section. *englishman* shown
    lower-case, and *mustache* then *moustache*, were on the host."""
    from core.placement.targets import CAPITALISED_IN_USE, spelling_key

    drawn = [w for w, _, _ in build.plan(build.FREE).words]
    assert len(drawn) == 240
    assert not set(drawn) & CAPITALISED_IN_USE
    assert "englishman" not in drawn
    assert len({spelling_key(w) for w in drawn}) == 240


def test_a_spelling_already_banked_is_not_drawn_again(empty_bank, monkeypatch) -> None:
    """The top-up after the prune: the bank holds *mustache*; the one candidate
    left in its band is *moustache*. Nothing is drawn rather than a repeat."""
    from core.services import placement as svc

    monkeypatch.setattr(svc, "bank_rows", lambda conn: [
        {"id": 1, "section": "vocabulary", "cefr": "B2", "error_type": None,
         "word": "mustache", "is_word": True, "freq_rank": 5655,
         "content_hash": "x", "item": None},
    ])
    monkeypatch.setattr(svc, "vocabulary_candidates", lambda conn, lo, hi: (
        [("moustache", 5894, "B2")] if lo == 5001 else []))
    assert build.plan(build.FREE).words == []


def test_the_spelling_key_groups_exactly_the_reviewed_pairs() -> None:
    from core.placement.targets import spelling_key

    groups: dict[str, set[str]] = {}
    for lemma in _pool_from_disk():
        groups.setdefault(spelling_key(lemma), set()).add(lemma)
    found = {tuple(sorted(g)) for g in groups.values() if len(g) > 1}
    assert found == SPELLING_PAIRS


def test_every_capitalised_word_is_in_the_pool_it_guards() -> None:
    """A stale entry would guard nothing; each one was read out of the pool."""
    from core.placement.targets import CAPITALISED_IN_USE

    assert CAPITALISED_IN_USE <= _pool_from_disk()


# ── W24a: `--only SECTION:BAND` — one cell for ~20 calls instead of 148 ──────
#
# **RED BEFORE THE FIX (2026-09-27): `--only` did not exist, so argparse
# refused it (`SystemExit`) and every test below failed.** The C1 cell is the
# one the operator's re-read printed as the only blocker: *"NO — short
# listening C1 by 1"*, with `cohorts: 10` and `at most: 148` for the whole plan.
# **W24r (C) dropped listening C1, so these name listening A2** — the same
# shape (one cohort of six `listening_gap` slots, 20 calls); the tests read
# `listening:C1` until then.


def test_only_one_listening_cell_plans_one_cohort_and_prints_its_ceiling(
        capsys, empty_bank, tmp_path) -> None:
    """Dry, on the empty dev bank: one listening A2 cohort of six
    `listening_gap` slots, whose ceiling is **20** -- worked by hand in
    `test_the_ceiling_is_itemised_from_the_slots` (1 + 1 + 2 × 6 + 6), not
    derived from `calls_for`. No free row: `--only` names generated cells."""
    assert build.main(["--only", "listening:A2", "--journal", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "cohorts: 1" in out
    assert "calls --live will make, at most: 20" in out
    assert "rows the free sections would write: 0" in out
    assert "=== BILLED cohort 1: listening A2, 6 slots ===" in out
    assert "listening B1" not in out.split("=== BILLED", 1)[1]
    assert "dry run — nothing was sent and nothing was written." in out


def test_only_apply_asks_for_the_filtered_ceiling(capsys, empty_bank, monkeypatch, tmp_path) -> None:
    """The typed-back number is the ONE cell's ceiling, not the whole plan's."""
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "no")
    assert build.main(["--only", "listening:A2", "--apply",
                       "--journal", str(tmp_path / "j.jsonl")]) == 1
    assert prompts == ["This makes up to 20 billed calls. Type 20 to continue, "
                       "anything else to stop: "]


@pytest.mark.parametrize("bad", ["listening", "listening:C2", "speaking:B1",
                                 "vocabulary:A1", "Listening:C1", "grammar:c1"])
def test_only_refuses_a_cell_that_is_not_generated(bad) -> None:
    with pytest.raises(SystemExit):
        build.main(["--only", bad])


def test_only_refuses_free_and_sample() -> None:
    with pytest.raises(SystemExit):
        build.main(["--only", "listening:A2", "--free"])
    with pytest.raises(SystemExit):
        build.main(["--only", "listening:A2", "--sample"])


def test_only_on_a_full_cell_sends_nothing(capsys, monkeypatch, tmp_path) -> None:
    """A cell with nothing short prints so and never reaches the confirm."""
    grammar_only = build.Plan(
        cohorts=build._generated_plan("grammar", Counter(), ()), held=Counter())
    monkeypatch.setattr(build, "plan", lambda sections=build.SECTIONS: grammar_only)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("asked to confirm nothing"))
    assert build.main(["--only", "listening:A2", "--apply",
                       "--journal", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "nothing is short in listening A2 — nothing to send." in out
    assert "cohorts: 0" in out


# ── W24r (C): listening C1 dropped from the placement check (operator ruling) ─
#
# **Why:** on 2026-09-27 the host's `--only listening:C1 --apply` discarded all
# six slots with `answer_not_in_transcript` + `stem_transcript_mismatch`: the
# target asked for *could have* / *might have* "in fast speech", the generator
# spelled the reduced form into the transcript (*mighta*, *coulda*), and no
# transcript check can match an answer whose point is that it is not written
# as spoken (#463). Listening's highest band is B2.
#
# **RED BEFORE THE CHANGE (2026-09-27):** the host's counts printed *"NO — short
# listening C1 by 1"*; the plan held a listening C1 cohort; `listening:C1` was
# accepted by `--only`.


def _host_held_2026_09_27() -> Counter:
    """The operator's `section, cefr` counts of 2026-09-27 (unchanged by the
    C1 run, which wrote 0), keyed as `bank._held` keys them. The paste gives
    per-band totals, so each is spread over the band's codes round-robin, the
    way the build fills them — the readiness line sums a band's codes. Vocabulary: 240 real words (A1 26 · A2
    46 · B1 89 · B2 79 by CEFR tag), drawn 24 per frequency band by the build;
    120 pseudo-words; the six speaking prompts."""
    from core.placement.targets import GRAMMAR_TARGETS, LISTENING_TARGETS, SPEAKING_PROMPTS

    held: Counter = Counter()
    for band in range(10):
        held[("vocabulary", band)] = 24
    held[("pseudo",)] = 120
    for _cefr, prompt in SPEAKING_PROMPTS:
        held[("speaking", prompt)] = 1
    def spread(section: str, band: str, n: int, codes: list[str]) -> None:
        for i in range(n):
            held[(section, band, codes[i % len(codes)])] += 1

    for band, n in {"A2": 27, "B1": 26, "B2": 26, "C1": 27}.items():
        spread("grammar", band, n, [c for c, _ in GRAMMAR_TARGETS[band]])
    for band, n in {"A2": 6, "B1": 12, "B2": 10}.items():
        spread("listening", band, n, [c for c, _ in LISTENING_TARGETS[band]])
    # listening C1: 0 — the cell the ruling removes.
    return held


def test_the_dry_run_on_the_hosts_counts_offers_a_first_sitting(capsys, tmp_path) -> None:
    p = build.Plan(held=_host_held_2026_09_27())
    build.dry_print(p, settings=load_settings(), journal_path=tmp_path / "j.jsonl")
    out = capsys.readouterr().out
    assert "  a first sitting can be offered now: yes\n" in out
    assert "listening  C1" not in out


def test_no_c1_listening_cohort_is_planned() -> None:
    """Neither on an empty bank nor on the host's counts. On the host's counts
    the only listening shortfall is B2's two (12 wanted, 10 held: 6 per target
    wanted, 5 per target held)."""
    empty = build._generated_plan("listening", Counter(), ())
    assert {c.band for c in empty} == {"A2", "B1", "B2"}
    host = build._generated_plan("listening", _host_held_2026_09_27(), ())
    assert [(c.band, len(c.slots)) for c in host] == [("B2", 2)]
    for cohort in empty:
        for candidate in cohort.candidates:
            assert "C1" not in candidate, candidate


def test_listening_c1_is_no_longer_a_cell_only_may_name() -> None:
    with pytest.raises(SystemExit):
        build.main(["--only", "listening:C1"])
