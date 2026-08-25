# `data/` — provenance and licence

Retrieved and verified **2026-08-24** (W4). This file records what the sources
**actually say**, not what the W4 plan assumed. The plan's §4 table was wrong in
both rows; the verification gate caught it before any code was written, and the
corrected terms are below.

## What is committed here, and what is not

| Committed | Not committed |
|---|---|
| `lexemes.tsv`, `inflections.tsv` — the merged, filtered output | The raw inputs. They are re-downloadable from the URLs below and checked against the SHA-256 digests recorded here |
| `scripts/build_lexicon.py` — the generator | |
| `syllabus_lexemes.tsv`, `syllabus_units.json` — W8's syllabus (2026-08-25) | |
| `scripts/build_syllabus_lexemes.py` — its generator | |

## W8's syllabus content — the gate that ran on 2026-08-25

Run before any code was written, as W4's did and W7's did for `fsrs`.

**`data/syllabus_units.json` is original work.** The 24 units — can-do
statements, grammar target names, output tasks, checkpoint blueprints — were
authored for this project against `docs/PRD-v3-web.md` §3. Nothing is
transcribed from a third party.

**Murphy references are unit NUMBERS, never Murphy's text.** `English Grammar in
Use` is Cambridge's, and this repository stores pointers into it — the same
thing `error_types.murphy_units` has stored since migration 001. A page number
is a reference; a paragraph would be redistribution. **No slice may copy Murphy's
explanations, examples or exercises into this repository**, and that holds for a
commercial product and not only for a private one.

**`data/syllabus_lexemes.tsv` inherits `lexemes.tsv`'s terms.** It is a
projection of it — the same lemmas, filtered to B1/B2 above rank 2000, each
tagged with the unit that teaches it — so it is a further derivative of
FrequencyWords and CEFR-J and carries **CC BY-SA 4.0** with them. Known issue
**#87** (CEFR-J is licensed for use, not explicitly for redistribution) applies
to it exactly as it does to its parent, and is not made worse or better by it:
the unit column is ours, the lemma list is not.

The topic assignment itself was produced with `claude-sonnet-5` through
`core.llm`. Anthropic's terms assign output to the customer, so the unit column
carries no third-party claim.

That split is deliberate and load-bearing: **the merged file stays
re-derivable and therefore deletable.** If either licence has to be
unwound — at a sale, at an open-sourcing, or because a rights holder asks —
removing `data/lexemes.tsv` is a delete plus a re-run of the generator against
a different source, not a re-architecture. Nothing else in the codebase
embeds the data.

## `data/lexemes.tsv` and `data/inflections.tsv` are licensed CC BY-SA 4.0

Inherited from the frequency source. The attribution notice is repeated as
comment lines **inside each `.tsv`**, not only here, because a data file
travels separately from its repository.

This does not restrict selling the application and does not touch any code in
this repository. It does mean the two data files carry the share-alike
condition wherever they go, and that must be disclosed at a sale.

---

## Source 1 — frequency ranks and bands

**FrequencyWords**, Hermit Dave. Derived from the OpenSubtitles corpora.

- Repository: <https://github.com/hermitdave/FrequencyWords>
- File used: `content/2018/en/en_full.txt`
- Raw URL: <https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/en/en_full.txt>
- Retrieved: 2026-08-24 · 19,977,552 bytes · 1,656,996 lines
- SHA-256: `7fea67ab954e2c01df6c608c9826e594cf36f8823b3243554f88245fb75dc506`
- Upstream corpus: OpenSubtitles2018 via OPUS, <http://opus.nlpl.eu/OpenSubtitles2018.php>

### Licence — **CC BY-SA 4.0**, not MIT

The W4 plan recorded this source as MIT. **MIT covers the code only.** The
repository's `README.md` says, verbatim and in full:

> "MIT License for code.<br>CC-by-sa-4.0 for content."

The repository's `LICENSE` file is a bare MIT text, `Copyright (c) 2016 Hermit
Dave`, with no CC text alongside it — that single README line is the entire
basis for the content licence. It is thin, but it is the author's own
declaration and it points toward the more restrictive reading, so there is no
room to interpret it charitably.

**The word lists are content.** The frequency data is therefore CC BY-SA 4.0.

**Consequence the plan did not anticipate.** The plan's fallback — "frequency
bands only, CEFR approximated from rank, no share-alike anywhere" — **does not
work**, because the frequency half is itself share-alike. Escaping BY-SA would
require a different frequency source, not a narrower use of this one.

Why this source rather than SUBTLEX: it is subtitle-derived, which is the
register a conversation-first app needs, and it is what SUBTLEX is built from.
See "Rejected sources" below.

## Source 2 — CEFR level tags

**The CEFR-J Wordlist Version 1.6.** Compiled by Yukio Tono, Tokyo University
of Foreign Studies. Retrieved from <http://www.cefr-j.org/download_eng> on
2026-08-24.

- Download: <http://www.cefr-j.org/data/CEFRJ_wordlist_ver1.6.zip>
- Archive: 1,089,155 bytes · SHA-256 `c837d2c00ab8954ed8db48e79afd8ef37099570295fec36950dbf9322303a37a`
- Contained file: `CEFR-J Wordlist Ver1.6.xlsx`, 1,097,188 bytes
  · SHA-256 `e41033a12f92983012a0a6b201d4f1f860b7ba3de700c2c3b89660ea21a390e1`
- Sheet used: `ALL_sep` (one headword per row) — 7,988 entries, A1–B2
- Version 1.6, updated 2020-03-24

### Licence — a bespoke TUFS permission, **not** Creative Commons

The W4 plan recorded this source as CC BY-SA 4.0. **It is not a Creative
Commons licence at all.** The download page says, verbatim:

> "The copyright of this wordlist belongs to Tono Laboratory at TUFS"

> "the list can be used for both research and commercial purposes with a proper
> acknowledgement of the source"

Required citation format, as given on that page:

> "The CEFR-J Wordlist Version 1.6. Compiled by Yukio Tono, Tokyo University of
> Foreign Studies. Retrieved from http:XXX on dd/mm/yy."

<https://github.com/openlanguageprofiles/olp-en-cefrj>, which redistributes
version 1.5, states the same terms:

> "CEFR-J vocabulary and grammar profile datasets can be used for research and
> commercial purposes with no charge, provided that you cite the dataset
> properly."

This is **better** than the plan assumed in one respect — no share-alike, and
commercial use is explicit — and **less settled** in another: see the open
issue below.

### Open issue — no explicit redistribution grant (known issue, medium, W4)

"May be used with acknowledgement" is silent on **shipping a copy**. Committing
derived level tags to this repository is redistribution, and the Tono Lab's
statement grants *use*, not *redistribution*.

- **When the risk crystallises: at a sale, or at an open-sourcing of this
  repository.** Not now. While the repository is private and serves two
  learners, this is use.
- **Mitigation already in place:** the merged file is re-derivable and
  deletable (see above), so unwinding it is one delete and one re-run.
- **Evidence, not permission:** `openlanguageprofiles/olp-en-cefrj`
  redistributes the same dataset publicly under the same stated terms. That the
  Tono Lab tolerates redistribution is meaningful, but it is not a grant.
- **Clean resolution:** an email to Tono Laboratory asking for explicit
  redistribution permission, before either trigger event.

---

## Rejected sources, and why

| Source | Supplies | Licence | Committable here? |
|---|---|---|---|
| SUBTLEX-US | subtitle frequency | CC BY-NC-**ND** | **No.** NC bars commercial use, and ND bars derivatives — merging it into a table is itself a derivative |
| COCA (full lists) | frequency bands | proprietary, sold per-licence | **No** |
| English Vocabulary Profile | CEFR level tags | Cambridge proprietary, browse-only | **No** |
| Oxford 3000/5000 | level bands | proprietary | **No** |

## If the share-alike condition has to go

Replace **source 1** — the frequency half is what carries BY-SA. Candidates to
verify, in the order they are worth checking: an MIT/Apache-licensed
OpenSubtitles derivation, the American National Corpus frequency data, and
Peter Norvig's `count_1w.txt`. Each needs its own licence verification; none
has been done. Replacing **source 2** does not help — NGSL and NAWL, the
obvious alternatives for real CEFR tags, are themselves CC BY-SA.

## Regenerating

```bash
pip install -r scripts/requirements-lexicon-build.txt
python scripts/build_lexicon.py --frequency <dir>/en_full.txt \
                                --cefrj "<dir>/CEFR-J Wordlist Ver1.6.xlsx"
```

The script prints the SHA-256 of each input. If either differs from the digests
above, the upstream file has changed and this record must be updated before the
output is committed.
