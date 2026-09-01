# Recorded actor output — W12b Phase B

`video_api.py`'s module docstring has claimed since W12b Phase A that its
functions "are exercised against recorded actor output and never against the
live services." **Until 2026-09-01 no recorded output existed anywhere in this
repository and that claim was aspirational.** This directory is the first of it.

## `actor.list.001.json`

**Provenance.** Written by `core.video.refresh --live --apply … --dump` on
production, **2026-09-01**, from the first billed run of W12b Phase B. It is the
response of the actor's **free `list_only` discovery call** —
`johnvc/YoutubeTranscripts` — over the five videos of that run. It cost real
money to produce and cannot be regenerated without spending again.

**THIS FILE IS A SLICE, NOT THE RAW DUMP, AND THAT MATTERS ENOUGH TO SAY TWICE.**
The original is **14,374 bytes** and lives on the host at
`/home/bot/phase-b-fixtures/actor.list.001.json`. This copy was produced by a
`json.dumps(..., indent=2)` over a subset of each row's keys, so:

- **it is NOT byte-identical to the actor's response**, and therefore does not
  have the property #317 was ruled in to guarantee. It is re-serialised, so its
  whitespace and key order are Python's, not the actor's;
- the values and the **structure** are the actor's, untouched — in particular
  `available_transcripts`, which is the whole point of the file.

**Keys removed:** `title`, `description`, `tags`, `thumbnail_url`,
`view_count`, `like_count`, `categories`, `availability`, `was_live`,
`channel_id`, `channel_url`. **None is read by `_read_kind`, `_row_video_id`,
`_read_text` or `_first_str`**, so nothing under test can see their absence.

**The honest consequence:** this fixture is far better than a hand-written one —
its shape was discovered rather than assumed, which is exactly the defect #323
was — **but it is not the archival artefact #317 argued for.** The full original
should be retrieved from the host and committed beside it; until it is, a test
that depended on byte-level fidelity would be resting on a file that does not
have it. **No test here does, and none should be written that does without
retrieving the original first.**

**Why the note is not inside the JSON.** The file has to load as the actor's own
response shape — a bare list of row objects. A `_README` key would make it an
object, and a fixture that has to be unwrapped before use is a fixture that no
longer matches what the code receives. That is the same class of quiet
divergence the fixture exists to prevent.

**What it contains.** Five videos, and the two that matter are load-bearing for
`tests/test_video_caption_kind.py`:

| `video_id` | channel | tracks | expected kind |
|---|---|---|---|
| `y_525lzqbg0` | Friends | 1, `en` auto-generated | `generated` |
| `5E5tNu4NsxM` | Friends | 1, `en` auto-generated | `generated` |
| **`9sSD2IFGSLw`** | English with Lucy | 2, **`en-GB` manual FIRST**, `en` auto-generated second | **`manual`** |
| **`QyRqlTV60zM`** | TED-Ed | 6, **Arabic first**, all `is_generated: false` | **`manual`** |
| `ScmC5E7titM` | English with Lucy | 1, `en` auto-generated | `generated` |

Totals: **3 generated, 2 manual, 0 unknown.**

**One fact worth keeping with the file, because it is about the pipeline and not
about the fixture:** `9sSD2IFGSLw` is the only video here whose English captions
are human-written, and it is **one of the four the paid fetch lost to
`NoTranscriptFound` after ten retries (#322)**. The one track PRD §7.2 exists to
prefer is the one the block took.
