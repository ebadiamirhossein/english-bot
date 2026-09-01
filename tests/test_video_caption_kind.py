"""The caption kind, read from real recorded actor output. #323.

**THE DEFECT.** `_read_kind` looked for `transcript_type` / `is_generated` /
`generated` **at the row's top level**. The actor reports kinds inside
`available_transcripts`, **a list of track objects**, and that key was not in
`kind_keys` at all. No key matched, the loop fell through, and every video came
back `None` -> the first billed run printed **`unknown 5`** about a response that
stated every kind plainly.

**IT COULD NOT SEE A NESTED LIST BY CONSTRUCTION**, which is why this is #257's
shape rather than a typo: the check enforced the FORM of an answer -- three key
names, a bool-or-string reader, a tidy manual/generated/unknown split -- while
being structurally unable to establish its truth.

**WHY IT MATTERED, AND IT IS NOT COSMETIC.** The caption kind decides which
coverage algorithm runs: auto-generated captions are lowercase, so the
proper-noun rule switches off and coverage comes back **inflated** (#288). A
pipeline that cannot read the kind cannot apply that rule, so every coverage
figure from a generated track was wrong in the same direction with nothing
saying so.

**THE FIXTURE IS REAL RECORDED OUTPUT, NOT A CONSTRUCTION.** It came from the
first billed run via `--dump` (#317) and cost money to produce; see
`tests/fixtures/transcripts/README.md`, which also records that it is a
**slice** of the 14,374-byte original and therefore is NOT byte-identical to
the actor's response. **Nothing in this file asserts byte-level fidelity**, and
nothing here should, until the full original is committed beside it.

**A hand-written fixture was explicitly refused** when writing this, because a
fixture composed from the fields we already read would encode our assumptions
rather than the actor's behaviour -- which is the defect itself, one level up.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import httpx
import pytest

from core import video_api

ACTOR = "johnvc/YoutubeTranscripts"
FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "transcripts" / "actor.list.001.json"
)


@pytest.fixture
def kinds_from_the_recorded_run(monkeypatch):
    """Drive the REAL `list_transcripts` over the recorded response.

    Not `_read_kind` in isolation: this exercises `_row_video_id`, the adapter
    lookup and the batching too, which is the chain that actually produced
    `unknown 5` on production.

    **The reader was renamed in #324's commit and gained the track list beside
    the kind; every assertion in this file is unchanged.** That is the point of
    keeping them: #324 changed what the listing CARRIES, and #323's answers
    about what it MEANS had to stay exactly where they were.
    """
    body = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        video_api.httpx,
        "Client",
        lambda *a, **k: real_client(*a, transport=httpx.MockTransport(handler), **k),
    )

    ids = [row["video_id"] for row in json.loads(body)]
    listings = video_api.list_transcripts(ids, token="tok", actor=ACTOR)
    return {video_id: l.kind for video_id, l in listings.items()}


def test_the_recorded_run_yields_three_generated_two_manual_and_no_unknown(
    kinds_from_the_recorded_run,
) -> None:
    """The whole-file total. **`unknown 5` is what production printed.**"""
    tally = Counter(kinds_from_the_recorded_run.values())
    assert tally["generated"] == 3
    assert tally["manual"] == 2
    assert tally[None] == 0, (
        f"every kind is stated in the response; got {kinds_from_the_recorded_run}"
    )


def test_a_manual_track_listed_first_among_generated_ones_reads_manual(
    kinds_from_the_recorded_run,
) -> None:
    """**`9sSD2IFGSLw` IS THE ROW THAT DISCRIMINATES, and it is the reason the
    rule is ANY rather than FIRST or ALL.**

    Two tracks: `en-GB` with `is_generated: false` **first**, then `en`
    auto-generated. So:

    * an **any**-reader returns `manual`  <- correct
    * an **all**-reader returns `generated` (one track is generated)
    * a **last**-track reader returns `generated`

    Only the correct implementation passes. Its companion test below cannot make
    that distinction, which is why both exist.

    Worth keeping beside the assertion: this is the ONE video in the recorded set
    with human-written English captions, and it is one of the four the paid fetch
    lost to `NoTranscriptFound` after ten retries (#322). The track PRD §7.2
    exists to prefer is the one the block took.
    """
    assert kinds_from_the_recorded_run["9sSD2IFGSLw"] == "manual"


def test_a_non_english_track_listed_first_does_not_decide_the_kind(
    kinds_from_the_recorded_run,
) -> None:
    """**`QyRqlTV60zM` PROVES NOTHING ON ITS OWN, AND IS PINNED ANYWAY.**

    Six tracks, **Arabic first and English fourth, all six `is_generated:
    false`**. A first-track reader returns `manual` here and **is right by
    luck** -- it answered a LANGUAGE question when asked a KIND one and happened
    to land on the same value. **A test resting on this row alone would go green
    over the defect**, which is why the row above is the one that discriminates.

    It is pinned regardless, as the language-vs-kind case: it fixes that track
    ORDER and track LANGUAGE are both irrelevant to this question, so a future
    change that starts filtering by `language_code` before reading
    `is_generated` fails here rather than silently narrowing the rule.
    """
    assert kinds_from_the_recorded_run["QyRqlTV60zM"] == "manual"


def test_every_track_generated_reads_generated(
    kinds_from_the_recorded_run,
) -> None:
    """The single-track case, three times over. `generated` requires that tracks
    exist AND that all of them are generated -- it is never the default for a
    row the reader failed to understand, which is what `unknown` is for."""
    for video_id in ("y_525lzqbg0", "5E5tNu4NsxM", "ScmC5E7titM"):
        assert kinds_from_the_recorded_run[video_id] == "generated"


def test_an_absent_or_empty_track_list_is_unknown_and_never_generated() -> None:
    """**`unknown` keeps its meaning: the actor did not say.**

    #257's rule is that an absent field and an auto-generated track are
    different facts. A reader that returned `generated` for a row with no
    `available_transcripts` would be guessing, and the guess would switch off
    the proper-noun rule and inflate coverage (#288) on no evidence at all.
    """
    adapter = video_api.adapter_for(ACTOR)
    assert video_api._read_kind({"video_id": "x"}, adapter) is None
    assert video_api._read_kind(
        {"video_id": "x", "available_transcripts": []}, adapter
    ) is None


def test_a_top_level_kind_still_wins_over_the_track_list() -> None:
    """The FETCH response and the LIST response are different shapes, and the
    reader serves both.

    A fetch row carries `transcript_type` describing **the track actually
    delivered**; a list row carries `available_transcripts` describing **what
    exists**. When both are present the delivered one is the answer, so the flat
    keys are read first and the track list is the fallback.
    """
    adapter = video_api.adapter_for(ACTOR)
    row = {
        "video_id": "x",
        "transcript_type": "manual",
        "available_transcripts": [{"is_generated": True}],
    }
    assert video_api._read_kind(row, adapter) == "manual"
