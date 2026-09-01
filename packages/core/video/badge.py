"""The coverage badge, as a BAND TOKEN. Pure: no SQL, no HTTP, no model, no I/O.

**NO PERCENTAGE CROSSES THIS BOUNDARY, AND THAT IS THE POINT OF THE MODULE.**
The number is real, is still computed, is still written to `video_coverage` and
is still printed by both CLIs. What this returns is one of three tokens or
nothing at all, so **no client can render a figure it was never given** -- the
same shape as `core.items.projection.visible_projection`, which withholds the
answer by never handing it over rather than by asking a renderer not to show it.

WHY, AND IT IS THREE REASONS RATHER THAN A TASTE:

1. **#288 is open and unmeasured.** The assumed-known floor ranks proper nouns
   as common vocabulary -- `john` 548, `michael` 763, `paris` 1107, `sarah` 1221,
   all inside the top-2,000 floor and all in `coverage_reference()`. Every
   coverage figure this project holds is inflated by an amount **nobody has
   counted**, and the count is still W12b's untaken first measurement. The
   inflation is largest on dialogue-heavy transcripts, which is what this pool
   is (#314: eleven channels, all performed, edited or taught).
2. **#334.** `video_assignments` has no coverage column, and `score_breakdown`'s
   `coverage_fit` returns 1.0 anywhere inside the band -- so the obvious
   extraction would display **1.0 as 100%**.
3. **#330.** A percentage over a 234-character transcript measures one
   paragraph, and it lands wherever those few tokens happen to fall.

**THE ACCEPTANCE BAR IS NOT LOWERED (CLAUDE.md §3 rule 7).** No number is
adjusted, no band is widened and nothing is put behind a flag. What is declined
is DISPLAYING a figure the record knows to be wrong, and by how much it cannot
say. PRD §7.3's example copy `"94% known -- slightly hard"` is amended in place
with the old text quoted.

**THE COPY IS NOT HERE.** These tokens carry no learner-facing English; the
strings live in `apps/web/components/session/copy.ts` with every other one, so
`tests/test_web_shell.py::test_no_guilt_copy_anywhere_in_the_frontend` reaches
them.
"""

from __future__ import annotations

from core.video.score import BAND_HIGH, BAND_LOW

#: The three tokens, and the fourth answer is `None` -- *withheld*, which is a
#: different fact from any of them and must not collapse into one.
BANDS: tuple[str, ...] = ("below", "in", "above")

#: Fewer counted tokens than this and no badge is shown (#330).
#:
#: **COUNTED TOKENS AND NOT CHARACTERS, WHICH IS THE SAME SUPPRESSION COMPUTED ON
#: THE RIGHT QUANTITY.** Coverage is a proportion of counted tokens, so its
#: granularity is 1/N -- and the band it is compared against is five points wide.
#: At the 234-character transcript that produced #330 the count is roughly forty
#: tokens, a granularity of 2.5%, so **the entire 93-98% band is two
#: distinguishable steps.** A hundred tokens is the point at which the band is at
#: least five steps wide and a position inside it means something. Anchored on
#: the band's own width rather than on a video length, because the defect is
#: statistical and not editorial.
MIN_COUNTED_TOKENS = 100


def band_for(
    coverage: float,
    *,
    counted_tokens: int,
    proper_nouns_detected: bool = True,
) -> str | None:
    """Which side of PRD §2.1's band this transcript falls, or None to withhold.

    `BAND_LOW` and `BAND_HIGH` are imported from `score.py` rather than restated:
    the badge a learner reads and the term selection ranks on must not be able to
    disagree about where the band is. Two copies of one number is how they would.

    **`proper_nouns_detected=False` WITHHOLDS, AND IT IS A GUARD AGAINST A
    PROVIDER CHANGE RATHER THAN A LIVE MITIGATION -- said plainly so it does not
    read as load-bearing.** The premise it inherits -- *auto-generated captions
    are lowercase, so the proper-noun rule switches off and coverage comes back
    inflated* -- was **measured and withdrawn** on 2026-09-01: six stored
    transcripts, three from auto-generated tracks, `proper_nouns_detected` TRUE
    on all six, `casing` conventional on all six, `degraded_288 = 0`.
    `johnvc/YoutubeTranscripts` returns conventionally cased text even for
    auto-generated tracks, so the sentence is true of YouTube's own payloads and
    **false of this actor's output**.

    **So this branch has never fired and, on this actor, will not.** It is kept
    rather than deleted for the reason #288 gives for keeping `--allow-degraded`,
    `degraded_288` and the pool-starvation warning: the premise is about an
    ACTOR, and `codepoetry/youtube-transcript-ai-scraper` is in the adapter table
    and has never been measured.

    **AND IT DOES NOT ADDRESS #288**, which is this module's reason 1. The
    proper-noun inflation now applies to every row EQUALLY -- *"it now inflates
    all six equally rather than three of them differently"* -- so nothing keyed
    on casing can reach it. The ruling above stands on its three reasons and not
    on this branch.

    **AND THE FLAG WAS LOAD-BEARING IN THE OTHER DIRECTION**, which is why it is
    worth getting right: the one video that landed inside the band is
    auto-generated. Had the borrowed premise held, all three generated rows would
    have been excluded and the admissible pool would have been ZERO.
    """
    if counted_tokens < MIN_COUNTED_TOKENS:
        return None
    if not proper_nouns_detected:
        return None
    if coverage < BAND_LOW:
        return "below"
    if coverage > BAND_HIGH:
        return "above"
    return "in"
