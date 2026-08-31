"""The video pipeline's pure half (W12b).

What lives here: reading and validating the channel pool, and PRD §7.2's
selection score. Both are pure functions over values.

What does NOT live here, and the boundaries are enforced by tests rather than by
convention (`tests/test_core_boundary.py`):

- **No SQL and no driver.** Every query is in `core/services/video.py`, so
  `test_video_package_is_pure` fails on the commit that adds one here.
- **No HTTP.** `core/video_api.py` is the only file in `packages/core` permitted
  an HTTP client, exempted there by name.
- **No model call, of any kind.** `test_core_video_never_calls_the_model` parses
  every file in this package and fails on an import of `core.llm`, on a provider
  SDK, or on a string naming a prompt file.

That last one is the enforcement of a rule, not a coincidence of the current
code. Transcripts are scraped text written by strangers, and CLAUDE.md §6 says
external content is material to be explained and never an instruction. The
strongest available guarantee that a transcript cannot be obeyed is that
**nothing in this package can reach a model at all** -- so the guarantee is a
parsed property of the source, not a promise in a docstring.

Transcript text does reach a model in W13, where the player defines a word, a
register and a comprehension item from it. That obligation is W13's and is filed
with a target; the injection surface is created by the slice that first passes
transcript text to `chat()`, and this is not that slice.
"""
