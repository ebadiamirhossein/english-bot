"""Regenerate `apps/web/components/write/write.fixture.json`.

    python scripts/export_write_fixture.py            # write
    python scripts/export_write_fixture.py --check    # exit 1 if stale

**#190's shape, applied to W16a from the start rather than after a crash.** The
Vitest tests and the Playwright harness render `/write` against bodies this
script builds through the REAL serialisers — `gates.shape` for what survives a
model response, `apps.api.routers.correct.result_out` for the wire, and the
pydantic response models with the route's own `exclude_none` — never against a
hand-written guess at the shape.
`tests/test_write_fixture.py::test_the_committed_write_fixture_matches_the_wire`
compares the committed keys against real ASGI response bodies.

**No database and no model are touched.** The raw model responses below are
fixed inputs; the opening lines are the two the §3 rule 2 call returned after
F1, quoted from the operator's run. The labels are migration 027's strings for
the codes used, and the key-level wire test is what holds them to the table's
shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from apps.api.routers.correct import result_out  # noqa: E402
from apps.api.schemas import (  # noqa: E402
    BlockOut,
    KeepGoingOut,
    Session,
    SessionTodayOut,
    WatchOut,
    WeekOut,
    WriteTodayOut,
)
from core.services import sessions  # noqa: E402
from core.services.video import TodayVideo  # noqa: E402
from core.services.writing import WritingOutcome  # noqa: E402
from core.writing import gates, offers, rules  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "write" / "write.fixture.json"

#: Design `1k`'s entry — the same text the probe sent.
ENTRY = (
    "Today I go to the dentist in the morning. I was very nervous because last "
    "time it hurt a lot, but this time she only clean my teeth and it was fine. "
    "After that I went to the office and we had a long meeting about the new "
    "project. My colleague Rasa explain everything twice because nobody "
    "understand the first time. In the evening I cooked soup and watched two "
    "episodes from a series. I am tired now but it was a good day."
)

#: Migration 027's `learner_label` for the codes used here.
LABELS = {"verb_tense_past": "Past tense", "preposition": "Prepositions", "word_order": "Word order"}

#: Returned by the second §3 rule 2 call, after F1 (operator's run, 2026-09-14).
LINE = "You walk us through the whole day, from the dentist to the evening soup, in a clear order."


def _c(you_said: str, correct_form: str, code: str, explanation: str) -> dict:
    return {"you_said": you_said, "correct_form": correct_form, "error_type": code, "explanation": explanation}


TENSE = _c(
    "Today I go to the dentist",
    "Today I went to the dentist",
    "verb_tense_past",
    "It's already happened, so the verb moves into the past: went.",
)
OF = _c(
    "two episodes from a series",
    "two episodes of a series",
    "preposition",
    "The episodes belong to the series, so it's of.",
)


def _correct(raw: dict, labels: dict | None = None) -> dict:
    shaped = gates.shape(raw, ENTRY, limit=rules.max_corrections("journal"), labels=labels or LABELS)
    outcome = WritingOutcome(
        is_english=shaped.is_english,
        did_well=shaped.did_well,
        corrections=shaped.corrections,
        written=len(shaped.corrections),
    )
    return result_out(outcome).model_dump(mode="json", exclude_none=True)


#: W16b — design `1n`'s paragraph, verbatim.
PARAGRAPH = (
    "I think is a good idea to move in another country for work, but it depends of "
    "the person. My cousin moved to Norway three years ago and now he earn much more "
    "money than before. But he told me that he miss his family very much, and in the "
    "winter he is alone."
)

#: Unit 1's `output_task_written`, verbatim (the probe's `PARAGRAPH_TASK`).
TASK = "Write six sentences about yesterday. Put them in order and join them with time words."

PARA_LABELS = {"preposition": "Prepositions", "subject_verb_agreement": "Subject and verb"}

PARA_RAW = {
    "is_english": True,
    "structure": [
        {"segments": [{"text": "You give your opinion in the first line and then back it with one real example, which is the right order for this kind of answer.", "quote": False}]},
        {"segments": [
            {"text": "The turn at ", "quote": False},
            {"text": "But he told me", "quote": True},
            {"text": " is the strongest part — that's where the paragraph starts to argue with itself.", "quote": False},
        ]},
    ],
    "corrections": [
        {"you_said": "it depends of the person", "correct_form": "it depends on the person", "error_type": "preposition",
         "explanation": "Depend always takes on in English, whatever follows it.", "keep": "to depend on"},
        {"you_said": "now he earn much more money", "correct_form": "now he earns much more money", "error_type": "subject_verb_agreement",
         "explanation": "He, she and it add an s to the verb in the present: he earns.", "keep": None},
        {"you_said": "he miss his family", "correct_form": "he misses his family", "error_type": "subject_verb_agreement",
         "explanation": "Same rule: with he, the verb takes an s — misses.", "keep": "to miss someone"},
    ],
}


def _paragraph(raw: dict, *, in_deck: tuple[bool, ...] = ()) -> dict:
    """Through `gates.shape(kind="paragraph")`, `offers.select` and `result_out`.

    `in_deck` is a database fact the exporter cannot compute; it is set here so
    both KeepRow states (`1o`: offer and in-deck) are drawn from one body.
    """
    shaped = gates.shape(raw, PARAGRAPH, limit=rules.max_corrections("paragraph"), labels=PARA_LABELS, kind="paragraph")
    chosen = offers.select(shaped.corrections)
    outcome = WritingOutcome(
        is_english=shaped.is_english,
        did_well=shaped.did_well,
        corrections=shaped.corrections,
        written=len(shaped.corrections),
        structure=shaped.structure,
        word_offers=tuple(
            # `token` (#419, W15): a fixed placeholder, because a real one is an
            # HMAC under the host's secret and the fixture must not depend on
            # which `.env` exported it. The client echoes it back unread.
            {"phrase": o.phrase, "sentence": o.sentence, "in_deck": in_deck[i] if i < len(in_deck) else False,
             "token": f"fixture-offer-{i}"}
            for i, o in enumerate(chosen)
        ),
    )
    return result_out(outcome).model_dump(mode="json", exclude_none=True)


def _today(**over) -> dict:
    spec = {"day_kind": rules.day_kind(date(2026, 9, 15)), "session_id": 90, "ceiling_reached": False}
    spec.update(over)
    return WriteTodayOut(**spec).model_dump(mode="json")


def _session(local_date: date = date(2026, 9, 15), *, finished: bool = False) -> dict:
    """A session whose block 4 is `_output_block`'s real ready payload.

    **W24e: ``finished``** — block 4 written (`done`, as `_derive_done` marks it
    from `writing_submissions`), every other work block empty, so
    `core.sessions.blocks.finished` is True over the same blocks the wire
    carries. Computed by that function here, never typed in.
    """
    state, payload = sessions._output_block(SimpleNamespace(unit_number=1), local_date=local_date)
    if finished:
        state = "done"
    blocks = [
        BlockOut(n=1, kind="review", state="empty", payload={}),
        BlockOut(n=2, kind="input", state="empty", payload={}),
        BlockOut(n=3, kind="focus", state="empty", payload={}),
        BlockOut(n=4, kind="output", state=state, payload=payload),
        BlockOut(n=5, kind="close", state="empty", payload={}),
    ]
    from core.sessions.blocks import Block, finished as finished_of

    return SessionTodayOut(
        session_id=90,
        date=local_date,
        l1_language="fa",
        current_block=4,
        completed=False,
        finished=finished_of(tuple(Block(n=b.n, kind=b.kind, state=b.state) for b in blocks)),
        blocks=blocks,
    ).model_dump(mode="json")


def _watch() -> dict:
    """W24e: `POST /keep-going/watch`, the player's payload from the ONE
    producer (`sessions.video_payload`). A purged-transcript video, so the
    fixture needs no database: the third state the player already renders."""
    video = TodayVideo(
        assignment_id=1, video_id=41, youtube_id="aqz-KE-bpKQ", title="A short sitcom scene",
        duration_s=212, accent="american", track="life", transcript=None,
        transcript_cues=None, transcript_lang=None, captions_kind="generated",
        resume_position_s=0, completed_at=None,
    )
    return WatchOut(l1_language="fa", video=sessions.video_payload(None, 3, video)).model_dump(mode="json")


#: W31b — a study-screen video. **Synthesised, Friends-SHAPED and nobody's
#: subtitles (#175)**: rolling cues whose overlap is in `duration` only, `>>`
#: turns, sound tags and a shouted ALL-CAPS line with names (C1), long enough
#: that the line list has to scroll.
STUDY_CUES = [
    (">> HEY, ROSS! IS THAT A", 0.0, 2.6),
    ("MASTODON? [laughter]", 1.9, 2.4),
    (">> it's a model of one. we found", 3.1, 2.8),
    ("it in the museum's basement.", 4.8, 2.5),
    (">> I told Ross it would never fit", 7.4, 2.6),
    ("through the front door.", 9.3, 2.2),
    (">> so what's its nickname?", 11.6, 2.3),
    ("[laughter] we call it Epoch.", 13.4, 2.6),
    (">> Epoch? like a period of time?", 16.1, 2.7),
    ("exactly, a very long one.", 18.3, 2.4),
    (">> you know what, it suits him.", 21.0, 2.5),
    ("he's been in that basement forever.", 22.9, 2.8),
    (">> can we move it this weekend?", 26.0, 2.4),
    ("I'll need at least four people.", 27.8, 2.6),
    (">> four people and a very big van.", 30.6, 2.7),
    ("[door slams] was that the manager?", 33.0, 2.5),
    (">> no, that was the wind. relax.", 35.8, 2.4),
    ("okay. I'm relaxed. I'm totally relaxed.", 37.6, 2.9),
    (">> you don't look relaxed at all.", 40.9, 2.5),
    ("that's because I'm standing next to a mastodon.", 42.8, 3.2),
]

#: The words this fixture's learner does not know — the highlight set.
STUDY_UNKNOWN = frozenset({"mastodon", "epoch", "nickname", "basement"})


def _watch_study() -> dict:
    """W31b: a video with a transcript and cues, through the ONE assembler
    (`sessions.assemble_video_payload`) and the real `core.video.lines`.

    **The coverage report is computed without a database** — the real
    `compute_coverage` over the transcript, with every lemma known except
    `STUDY_UNKNOWN` — because the ledger is the only part of the payload that
    needs Postgres, and the exporter touches none."""
    from core.lexicon.coverage import compute_coverage

    cues = [{"text": t, "start": a, "duration": d} for t, a, d in STUDY_CUES]
    text = " ".join(c["text"] for c in cues)
    everything = compute_coverage(text, frozenset(), ledger={}, vocabulary=frozenset())
    known = frozenset(everything.unknown_lemmas) - STUDY_UNKNOWN
    report = compute_coverage(text, known, ledger={}, vocabulary=frozenset())
    video = TodayVideo(
        assignment_id=2, video_id=44, youtube_id="aqz-KE-bpKQ", title="A sitcom scene",
        duration_s=48, accent="american", track="life", transcript=text,
        transcript_cues=cues, transcript_lang="en", captions_kind="generated",
        resume_position_s=0, completed_at=None,
    )
    return WatchOut(
        l1_language="fa", video=sessions.assemble_video_payload(video, report)
    ).model_dump(mode="json")


def _watch_untimed() -> dict:
    """W31b: the same text with NO cues — the third state: untimed lines."""
    body = _watch_study()
    from core.lexicon.coverage import compute_coverage

    video = TodayVideo(
        assignment_id=3, video_id=45, youtube_id="aqz-KE-bpKQ", title="A sitcom scene",
        duration_s=48, accent="american", track="life", transcript=body["video"]["transcript"],
        transcript_cues=None, transcript_lang="en", captions_kind="generated",
        resume_position_s=0, completed_at=None,
    )
    text = body["video"]["transcript"]
    everything = compute_coverage(text, frozenset(), ledger={}, vocabulary=frozenset())
    known = frozenset(everything.unknown_lemmas) - STUDY_UNKNOWN
    report = compute_coverage(text, known, ledger={}, vocabulary=frozenset())
    return WatchOut(
        l1_language="fa", video=sessions.assemble_video_payload(video, report)
    ).model_dump(mode="json")


def bodies() -> dict:
    return {
        "auth": Session(
            user_id=3, name="Learner", expires_at=datetime(2026, 10, 15, tzinfo=timezone.utc)
        ).model_dump(mode="json"),
        "session": _session(),
        # W24e — keep going.
        "session_finished": _session(finished=True),
        "keep_going_weekday": KeepGoingOut(options=["watch", "talk", "cards", "write"]).model_dump(mode="json"),
        "keep_going_sunday": KeepGoingOut(options=["watch"]).model_dump(mode="json"),
        "keep_going_none": KeepGoingOut(options=[]).model_dump(mode="json"),
        "watch": _watch(),
        # W31b — the study screen: timed lines, and the untimed third state.
        "watch_study": _watch_study(),
        "watch_untimed": _watch_untimed(),
        # W24e — Sunday's home, week one: `empty`, so the report renders its one
        # line and no number, and keep going is the only offer below it (R1).
        "week_sunday": WeekOut(
            week_ending=date(2026, 10, 4), sunday=True, days_with_a_session=0,
            items_answered=0, items_right=0, cards_reviewed=0, words_now_known=0,
            units_passed=0, empty=True,
        ).model_dump(mode="json"),
        "today": _today(),
        "today_no_session": _today(session_id=None),
        "today_ceiling": _today(ceiling_reached=True),
        "two": _correct({"is_english": True, "corrections": [TENSE, OF], "did_well": LINE}),
        "one": _correct({"is_english": True, "corrections": [TENSE], "did_well": LINE}),
        "clean_no_line": _correct({"is_english": True, "corrections": [], "did_well": None}),
        "no_label": _correct(
            {"is_english": True, "corrections": [TENSE], "did_well": None},
            labels={"verb_tense_past": None},
        ),
        "not_english": _correct({"is_english": False, "corrections": [], "did_well": None}),
        # W16b — 2026-09-17 is a Thursday.
        "session_paragraph": _session(date(2026, 9, 17)),
        "today_paragraph": _today(day_kind=rules.day_kind(date(2026, 9, 17)), prompt=TASK),
        "paragraph": _paragraph(PARA_RAW, in_deck=(False, True)),
        "paragraph_bare": _paragraph({**PARA_RAW, "structure": [], "corrections": [
            {**c, "keep": None} for c in PARA_RAW["corrections"]]}),
        "paragraph_one_offer": _paragraph({**PARA_RAW, "corrections": PARA_RAW["corrections"][:2]}),
    }


def rendered() -> str:
    return json.dumps(bodies(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if stale")
    args = parser.parse_args(argv)
    current = rendered()
    if args.check:
        on_disk = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if on_disk != current:
            print(f"{TARGET} is stale — re-run without --check", file=sys.stderr)
            return 1
        print(f"{TARGET} is current")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(current, encoding="utf-8")
    print(f"wrote {len(bodies())} bodies to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
