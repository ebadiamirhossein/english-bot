"""Image cards for concrete vocabulary. W13d, PRD §2.6.3.

**AN IMAGE ADDS A FACE TO A PICTURABLE WORD'S CARD AND REPLACES NOTHING.** It is
shown with the answer, never before it, and a card without one is exactly the
card it was before this slice.

This module is the POLICY, with no network and no SQL: which licences pass the
gate (`data/LICENCES.md`, W13d), how a Commons file's metadata is read into an
attribution, and which cards may carry a picture. The request lives in
`core/images/commons_api.py` (the named HTTP door) and the rows in
`core/services/lexeme_images.py`.

**WHICH WORDS ARE PICTURABLE — TASKS' OPEN QUESTION, AND HOW IT IS ANSWERED:**
a per-word operator decision, narrowed before the operator sees it.

1. **Structurally:** a phrasal verb or a collocation has no lexeme — migration
   015: *"a phrase has no lemma and never will"* — so a phrase card has
   `lexeme_id IS NULL` and cannot reach a picture. A `collocation` card is
   excluded by type even when it names a lemma (`IMAGE_CARD_TYPES`).
2. **By proposal:** only lemmas tagged `NOUN` are proposed, and only when
   Wikidata has an item whose English label IS the lemma (lower-case, exact)
   with a representative image (P18). Abstract nouns mostly fail here — Wikidata
   rarely pictures *trust* — and the POS tag is noisy (`you` is tagged NOUN), so
   this narrows and never decides.
3. **By approval:** a line in `data/lexeme_images.tsv` is the operator's
   decision. Nothing reaches a learner that a person did not look at (#271).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Mapping

#: The eight licences the W13d gate admits, spelled as Commons' `LicenseShortName`
#: spells them. **Mirrored by migration 033's CHECK**, so a loader defect cannot
#: store a ninth; `tests/test_lexeme_images.py` holds the two sets equal.
#:
#: Refused, with the reason in `data/LICENCES.md`: every NonCommercial or
#: NoDerivatives licence (not commercial / not displayable as-is), CC BY-SA
#: 1.0–2.5 (not read by the gate), the GFDL (requires the licence's full text to
#: travel with the copy), Commons' bespoke "Attribution" licence (not read), and
#: anything unrecognised.
ALLOWED_LICENCES: frozenset[str] = frozenset(
    {
        "CC0",
        "Public domain",
        "CC BY 2.0",
        "CC BY 2.5",
        "CC BY 3.0",
        "CC BY 4.0",
        "CC BY-SA 3.0",
        "CC BY-SA 4.0",
    }
)

#: No attribution is legally required for these (Commons: *"attribution is
#: recommended to give correct provenance"*), and the card credits the author
#: anyway when Commons names one.
ATTRIBUTION_FREE: frozenset[str] = frozenset({"CC0", "Public domain"})

#: The card types a picture may appear on. **Exhaustive on purpose**, the shape
#: of `SOURCE_LINE_ON_FRONT` in `apps/web/components/cards/card-face.tsx`: a
#: sixth type inherits nothing until someone rules on it.
#:
#: - `recognition`, `production`, `cloze`, `audio` — **yes**, when the card names
#:   a lemma that has an approved picture. The picture is on the ANSWER side, so
#:   it never answers the question.
#: - `collocation` — **no.** PRD §2.6.3: a picture cannot carry a collocation,
#:   and the sentence-context card already does.
IMAGE_CARD_TYPES: frozenset[str] = frozenset(
    {"recognition", "production", "cloze", "audio"}
)

#: Commons' standard thumbnail step nearest a phone card's width. The Robot
#: policy: *"Only use originals or one of our standard thumbnail sizes"*.
THUMB_WIDTH = 330

#: Mirrors migration 033's `octet_length(bytes)` CHECK.
MAX_BYTES = 262_144

#: Mirrors migration 033's `mime` CHECK.
ALLOWED_MIME: frozenset[str] = frozenset({"image/jpeg", "image/png"})

_MAGIC = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}

EXTENSION = {"image/jpeg": "jpg", "image/png": "png"}

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_CC_URL = re.compile(r"^(?:https?:)?//creativecommons\.org/(.+)$")


def plain_text(value: str | None) -> str:
    """Commons' `Artist` is HTML (a user-page link, a `<bdi>`, a Flickr anchor).
    The card shows the NAME, so tags are dropped and entities decoded."""
    if not value:
        return ""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()


def licence_url(value: str | None) -> str | None:
    """Commons returns `https://creativecommons.org/licenses/by/2.0` and
    sometimes a scheme-relative or `http:` form; the card links one spelling."""
    if not value:
        return None
    match = _CC_URL.match(value.strip())
    return f"https://creativecommons.org/{match.group(1)}" if match else None


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the gate made of one Commons file. `reason` is set iff refused."""

    licence: str
    author: str
    licence_url: str | None
    reason: str | None = None

    @property
    def admitted(self) -> bool:
        return self.reason is None


def judge(extmetadata: Mapping[str, str], mime: str) -> Verdict:
    """The licence gate, applied to one file's metadata.

    `extmetadata` is Commons' `imageinfo.extmetadata`, flattened to
    `{name: value}`. **Every refusal names its reason**, so the proposal sheet
    and `--apply` both say WHY a word has no picture rather than leaving a gap.
    """
    licence = (extmetadata.get("LicenseShortName") or "").strip()
    author = plain_text(extmetadata.get("Artist"))
    url = licence_url(extmetadata.get("LicenseUrl"))

    def refuse(reason: str) -> Verdict:
        return Verdict(licence=licence, author=author, licence_url=url, reason=reason)

    if licence not in ALLOWED_LICENCES:
        return refuse(f"licence not admitted: {licence or '(none)'}")
    # Commons writes `personality`, `trademarked` and the like here from
    # {{Personality rights}} and its siblings. Commons' reuse page: *"commercial
    # use of images of people may require the explicit agreement of the
    # subject"* — a right the file's licence cannot grant, so any flag refuses.
    restrictions = (extmetadata.get("Restrictions") or "").strip()
    if restrictions:
        return refuse(f"non-copyright restriction: {restrictions}")
    if mime not in ALLOWED_MIME:
        return refuse(f"format not admitted: {mime}")
    # An author's own credit line. Commons:Credit_line: *"Some works might have
    # specific instructions from the author on how they would like their work to
    # be attributed. Those requests must be honored"*. The card's credit is one
    # fixed shape (author · licence · Wikimedia Commons), so a file that asks for
    # another is refused rather than credited wrongly; the operator picks another.
    if plain_text(extmetadata.get("Attribution")):
        return refuse("the author specifies their own credit line")
    if licence not in ATTRIBUTION_FREE:
        if not author:
            return refuse("attribution required and no author named")
        if url is None:
            return refuse("attribution required and no licence URL")
    return Verdict(licence=licence, author=author, licence_url=url)


def bytes_match(mime: str, data: bytes) -> bool:
    """A downloaded thumbnail is the format Commons said it was."""
    magic = _MAGIC.get(mime)
    return bool(magic) and data.startswith(magic)


def shows_picture(card_type: str, lexeme_id: int | None) -> bool:
    """Whether a card may carry a picture at all, before any row is read.

    A phrase card (`lexeme_id IS NULL`) and a `collocation` card never do —
    PRD §2.6.3's *"demonstrably unchanged"* half is this function returning
    False, and `card_face` never looking further.
    """
    return lexeme_id is not None and card_type in IMAGE_CARD_TYPES
