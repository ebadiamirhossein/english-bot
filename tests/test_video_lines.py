"""W31b — `core.video.lines`: cues → display lines, and the display cleaning.

Pure: no database, no model. **Every expected value is written out by hand**
(CLAUDE.md §3 rule 5) — none is computed by the function under test.

The tracks are **synthesised** to the shapes T5 measured (rolling windows whose
overlap lives only in `duration`, float seconds, a `start` on every cue). **No
committed fixture holds anyone's subtitles** (#175).
"""

from __future__ import annotations

import copy

from core.video import lines as L


def cue(text: str, start: float, duration: float | None = None) -> dict:
    c = {"text": text, "start": start}
    if duration is not None:
        c["duration"] = duration
    return c


def texts(out) -> list[str]:
    return [line.text for line in out]


# ── timing ──────────────────────────────────────────────────────────────────


def test_a_line_ends_where_the_next_begins_and_duration_overlap_is_ignored() -> None:
    cues = [
        cue("so this is", 0.0, 2.4),
        cue("a mastodon.", 1.2, 2.5),  # overlaps the first by 1.2 s — duration only
        cue("it lived in the", 2.9, 2.2),
        cue("ice age.", 5.5, 1.0),
    ]
    out = L.lines_for(cues)
    assert texts(out) == ["so this is a mastodon.", "it lived in the ice age."]
    assert (out[0].start, out[0].end) == (0.0, 2.9)
    # "ice age." (2 words, after a silence) is merged BACK into the last line:
    # a short line with nothing after it joins the one before.
    assert (out[1].start, out[1].end) == (2.9, 6.5)


def test_every_word_of_every_cue_survives_in_order() -> None:
    cues = [cue(f"w{i}", i * 0.5, 1.0) for i in range(30)]
    joined = " ".join(texts(L.lines_for(cues)))
    assert joined == " ".join(f"w{i}" for i in range(30))


def test_a_line_is_capped_at_six_seconds_or_fourteen_words() -> None:
    cues = [cue(f"w{i}", i * 0.5, 1.0) for i in range(30)]
    out = L.lines_for(cues)
    # 0.5 s per word: the 6 s cap bites at twelve words, before the word cap.
    assert [len(t.split()) for t in texts(out)] == [12, 12, 6]
    assert (out[0].start, out[0].end) == (0.0, 6.0)
    assert (out[1].start, out[1].end) == (6.0, 12.0)


def test_the_word_cap_bites_on_a_fast_speaker() -> None:
    # Distinct words per cue: four identical cues would (rightly) trip the
    # repeated-edge guard, which is a different test.
    cues = [cue(" ".join(f"{k}{n}" for n in range(5)), i * 1.0, 1.5) for i, k in enumerate("abcd")]
    assert [len(t.split()) for t in texts(L.lines_for(cues))] == [10, 10]


def test_a_silence_breaks_a_line() -> None:
    cues = [
        cue("we were talking", 0.0, 2.0),
        cue("about the rent", 1.5, 1.0),  # ends at 2.5
        cue("and then she left", 4.0, 2.0),  # starts 1.5 s after — a silence
        cue("without a word", 5.5, 1.5),
    ]
    assert texts(L.lines_for(cues)) == [
        "we were talking about the rent",
        "and then she left without a word",
    ]


def test_a_contiguous_manual_track_does_not_count_as_silence() -> None:
    # TED-Ed's shape — one cue ends exactly where the next starts. In floats
    # 2.3 + 2.9 is 5.199999999999999: a positive "gap" before 5.2 that is noise,
    # and must not read as a silence. (7.003 + 2.713 rounds UP, so it could not
    # test this — found by mutation.)
    cues = [cue("the first part of it", 2.3, 2.9), cue("goes on here", 5.2, 0.5)]
    assert texts(L.lines_for(cues)) == ["the first part of it goes on here"]


# ── the duplicate guard ─────────────────────────────────────────────────────


def test_a_repeated_edge_is_stripped_and_counted() -> None:
    cues = [cue("we were talking about", 0.0, 3.0), cue("talking about the rent", 1.5, 3.0)]
    report = L.derive(cues)
    assert texts(report.lines) == ["we were talking about the rent"]
    assert report.duplicates_stripped == 1


def test_a_single_repeated_word_is_not_a_duplicate() -> None:
    # "the the" is English often enough; one word is below the guard's floor.
    cues = [cue("I think that", 0.0, 2.0), cue("that is right", 1.5, 2.0)]
    report = L.derive(cues)
    assert texts(report.lines) == ["I think that that is right"]
    assert report.duplicates_stripped == 0


# ── speakers, tags and caps ─────────────────────────────────────────────────


def test_a_speaker_marker_breaks_the_line_and_is_never_shown() -> None:
    cues = [cue(">> WHAT IS THAT", 0.0, 2.0), cue(">> IT'S A MASTODON.", 1.5, 2.0)]
    out = L.lines_for(cues)
    assert texts(out) == ["What is that", "It's a mastodon."]
    assert [line.speaker_change for line in out] == [True, True]
    assert all(">>" not in line.text for line in out)


def test_a_marker_inside_a_cue_becomes_a_dash_and_starts_a_new_line() -> None:
    cues = [cue("we should go now", 0.0, 2.0), cue("okay >> no wait", 1.8, 2.0)]
    out = L.lines_for(cues)
    assert texts(out) == ["we should go now", "okay — no wait"]
    assert out[1].speaker_change is True


def test_a_sound_tag_stays_as_it_is() -> None:
    out = L.lines_for([cue("[laughter] it lived in the ice age.", 0.0, 3.0)])
    assert texts(out) == ["[laughter] it lived in the ice age."]


def test_caps_become_sentence_case_and_names_keep_their_capitals() -> None:
    """C1 (operator, 2026-09-27): *"HEY, PETER! IT'S ME, ROSS"* must render as
    *"Hey, Peter! It's me, Ross"*, not *"Hey, peter! It's me, ross"* — the
    names are restored from the same transcript's mixed-case text."""
    cues = [
        cue("I told Peter and Ross about it.", 0.0, 3.0),
        cue(">> HEY, PETER! IT'S ME, ROSS", 3.5, 3.0),
    ]
    assert texts(L.lines_for(cues)) == [
        "I told Peter and Ross about it.",
        "Hey, Peter! It's me, Ross",
    ]


def test_names_are_found_across_a_whole_transcript_not_only_a_short_one() -> None:
    """Regression: `proper_forms` once dropped names at random on a long text
    (object ids reused between two regex passes). Twenty turns, one name."""
    turns = [f">> line number {i} goes here." for i in range(20)]
    turns[7] = ">> I told Ross it would never fit."
    turns[0] = ">> HEY, ROSS! IS THAT A MASTODON?"
    transcript = " ".join(turns)
    assert L.proper_forms([transcript]).get("ross") == "Ross"
    assert texts(L.sentences_for(transcript))[0] == "Hey, Ross!"


def test_a_word_capitalised_only_at_a_sentence_start_is_not_a_name() -> None:
    cues = [cue("So we left early.", 0.0, 2.0), cue(">> WELL SO WHAT", 2.5, 2.0)]
    assert texts(L.lines_for(cues))[1] == "Well so what"


def test_a_word_seen_in_lowercase_too_is_not_treated_as_a_name() -> None:
    # *Will* the name and *will* the verb: restoring the capital would turn
    # every shouted I WILL into "I Will".
    cues = [
        cue("we told Will about it and he will call.", 0.0, 3.0),
        cue(">> I WILL GO", 3.5, 2.0),
    ]
    assert texts(L.lines_for(cues))[1] == "I will go"


def test_i_stays_capital_and_a_lone_acronym_is_untouched() -> None:
    cues = [
        cue("we watched TV all night.", 0.0, 3.0),
        cue(">> I'M SO TIRED I COULD SLEEP", 3.5, 3.0),
        cue(">> I LOVE TV", 7.0, 2.0),
    ]
    assert texts(L.lines_for(cues)) == [
        "we watched TV all night.",
        "I'm so tired I could sleep",
        # TV appears as TV in mixed-case text, so it is restored inside the run.
        "I love TV",
    ]


def test_mixed_case_text_is_never_recased() -> None:
    cues = [cue("the NHS said what", 0.0, 2.0)]
    assert texts(L.lines_for(cues)) == ["the NHS said what"]


# ── no cues, and nothing mutated ─────────────────────────────────────────────


def test_no_cues_means_no_timed_lines() -> None:
    assert L.lines_for(None) == []
    assert L.lines_for([]) == []


def test_without_cues_the_transcript_splits_into_untimed_sentences() -> None:
    out = L.sentences_for("hello there. how are you? >> I'M FINE")
    assert texts(out) == ["hello there.", "how are you?", "I'm fine"]
    assert all(line.start is None and line.end is None for line in out)


def test_the_stored_cues_are_not_touched() -> None:
    cues = [cue(">> HEY, PETER!", 0.0, 2.0), cue("we were talking about", 1.0, 3.0)]
    before = copy.deepcopy(cues)
    L.lines_for(cues)
    assert cues == before


# ── the report: the operator's three-video check (Q2) ───────────────────────


def test_the_report_names_what_the_derivation_did() -> None:
    cues = [
        cue("so this is", 0.0, 2.4),
        cue("a mastodon.", 1.2, 2.5),
        cue("it lived in the", 2.9, 2.2),
        cue("ice age.", 5.5, 1.0),
    ]
    text = L.report(44, "generated", cues, sample=2)
    # Counted by hand: pairs (0,1) and (1,2) overlap, (2,3) does not.
    assert "video 44 (generated): cues 4, overlapping pairs 2" in text
    assert "lines 2; repeated edges stripped 0; merged short lines 1" in text
    assert "breaks: speaker 0, sentence 2, silence 1, cap 0" in text
    assert "so this is a mastodon." in text


def test_the_report_says_when_there_are_no_cues() -> None:
    assert "no usable cues" in L.report(7, "manual", None)


def test_the_report_cli_reads_one_video_from_the_database(capsys) -> None:
    """User action: the operator runs `python -m core.video.lines --report
    --video N` on the host. Read-only; this row is written and removed here."""
    import secrets
    from datetime import datetime, timedelta, timezone

    import psycopg

    from core.config import load_settings
    from core.services import video as svc

    cues = [cue("we", 0.0, 1.5), cue("were talking", 1.2, 2.0)]
    youtube_id = f"rt31{secrets.token_hex(3)}"
    with psycopg.connect(load_settings().database_url) as conn:
        video_id = svc.upsert_video(
            conn, youtube_id=youtube_id, channel_id="UCw31lines00000000000000",
            accent="british", track="life", title="W31b report probe",
            duration_s=60, published_at=datetime.now(timezone.utc) - timedelta(days=1),
            now=datetime.now(timezone.utc),
        )
        svc.record_transcript(conn, video_id=video_id, text="we were talking",
                              lang="en", kind="generated", cues=cues)
        conn.commit()
    try:
        assert L.main(["--report", "--video", str(video_id)]) == 0
        out = capsys.readouterr().out
        assert f"video {video_id} (generated): cues 2, overlapping pairs 1" in out
        assert "we were talking" in out
        assert L.main(["--report", "--video", "-1"]) == 0
        assert "video -1: no such video" in capsys.readouterr().out
    finally:
        with psycopg.connect(load_settings().database_url) as conn:
            conn.execute("DELETE FROM videos WHERE youtube_id = %s", (youtube_id,))
            conn.commit()
