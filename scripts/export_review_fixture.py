"""Regenerate `apps/web/components/cards/review-queue.fixture.json` and
`apps/web/e2e/fixtures/card-picture.png`. W13d.

    python scripts/export_review_fixture.py            # write both
    python scripts/export_review_fixture.py --check    # exit 1 if either is stale

**#190's shape, as `export_session_fixture.py`, with one difference that is
the point of W13d:** a card's picture is READ FROM `lexeme_images`, so the
faces cannot be built without the database the way the session's are. This
script therefore writes ONE picture row for `spoon` on the Mac dev database,
builds four card faces through the real `core.services.cards.card_face`,
serialises them through the real `ReviewQueueOut`, and deletes the row in a
`finally`. It refuses to run if `spoon` already has a picture — an operator's
approved row is never overwritten by a fixture.

**The four cards are TASKS' W13d acceptance, one each:** a picturable word
(`spoon`, recognition — the picture), an abstract word (`trust` — no picture),
a phrasal verb (`give up`, a phrase card with no lexeme — no picture) and a
collocation (`hold a spoon`, naming the pictured lemma — still no picture).

**The picture is this project's own drawing**, generated below from arithmetic
— a spoon's outline on a plain ground — so the fixture carries no third-party
image and no licence question (`data/LICENCES.md`, W13d). Its credit fields are
the recorded Commons values for `File:SpoonCollection.jpg`, because the
credit's SHAPE is what the browser test exercises. The ids are fixed numbers
(the picture's becomes 7): nothing renders on them and a database id changes on
every run.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.schemas import CardFace, DeckCountsOut, ReviewQueueOut  # noqa: E402
from core.cards.fsrs import CardState  # noqa: E402
from core.services import lexeme_images  # noqa: E402
from core.services.cards import Card, card_face  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "cards" / "review-queue.fixture.json"
PICTURE = REPO_ROOT / "apps" / "web" / "e2e" / "fixtures" / "card-picture.png"

NOW = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
FIXED_IMAGE_ID = 7
WIDTH, HEIGHT = 330, 215


def picture_png() -> bytes:
    """A spoon: an elliptical bowl and a handle, dark on a warm ground. Pure
    arithmetic, so the bytes are the same on every run and every machine."""
    ground, ink = (240, 232, 219), (92, 84, 74)
    rows = []
    for y in range(HEIGHT):
        row = bytearray([0])  # filter: none
        for x in range(WIDTH):
            bowl = ((x - 95) / 62) ** 2 + ((y - 107) / 40) ** 2 <= 1.0
            handle = 150 <= x <= 300 and abs(y - 107 - (x - 150) * 0.04) <= 7
            row += bytes(ink if (bowl or handle) else ground)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(
            ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
        )

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def _state() -> CardState:
    return CardState(
        fsrs_state="review", fsrs_step=None, stability=10.0, difficulty=5.0,
        due=NOW, last_review=NOW, lapses=0, reps=4,
    )


def _card(**over) -> Card:
    spec = dict(
        id=0, user_id=3, card_type="recognition", source_chunk_id=None,
        source_ref="vocabulary", front="", back="", context_sentence=None,
        meaning=None, neutral_equivalent=None, neutral_lexeme_id=None,
        who_says_this=None, lexeme_id=None, cue_text=None, register="neutral",
        register_source="import_default", neutral_mastered_at=None,
        state=_state(), leech_at=None,
    )
    spec.update(over)
    return Card(**spec)


def queue() -> dict:
    ids = lexeme_images.lexeme_ids(["spoon", "trust"])
    if set(ids) != {"spoon", "trust"}:
        raise SystemExit("the dev lexicon lacks spoon or trust")
    if "spoon" in lexeme_images.stored():
        raise SystemExit("spoon already has a picture on this database — refusing to touch it")
    image_id = lexeme_images.replace(
        lexeme_id=ids["spoon"],
        commons_file="File:SpoonCollection.jpg",
        source_url="https://commons.wikimedia.org/wiki/File:SpoonCollection.jpg",
        original_sha1="91572801d525fd5607d45c86b6b89aaf8ed78b32",
        author="THOR",
        licence="CC BY 2.0",
        licence_url="https://creativecommons.org/licenses/by/2.0",
        mime="image/png",
        width=WIDTH,
        height=HEIGHT,
        data=picture_png(),
    )
    try:
        cards = [
            _card(id=51, front="Could you pass me a spoon?", back="spoon",
                  meaning="قاشق", lexeme_id=ids["spoon"],
                  context_sentence="Could you pass me a spoon?"),
            _card(id=52, front="It takes years to build that kind of trust.", back="trust",
                  meaning="اعتماد", lexeme_id=ids["trust"],
                  context_sentence="It takes years to build that kind of trust."),
            _card(id=53, card_type="production", front="دست کشیدن\nDon't _____ now.",
                  back="give up", meaning="دست کشیدن"),
            _card(id=54, card_type="collocation", front="_____ a spoon properly",
                  back="hold", lexeme_id=ids["spoon"],
                  context_sentence="Hold a spoon properly."),
        ]
        faces = [card_face(c, now=NOW) for c in cards]
    finally:
        lexeme_images.remove(["spoon"])
    for face in faces:
        if face["image"] is not None:
            assert face["image"]["id"] == image_id
            face["image"]["id"] = FIXED_IMAGE_ID
    body = ReviewQueueOut(
        cards=[CardFace(**f) for f in faces],
        counts=DeckCountsOut(new_remaining=0, review_remaining=4, total_remaining=4),
        l1_language="fa",
    )
    return body.model_dump(mode="json", by_alias=True)


def rendered() -> str:
    return json.dumps(queue(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if stale")
    args = parser.parse_args(argv)
    current, png = rendered(), picture_png()
    if args.check:
        stale = [
            p for p, want in ((TARGET, current.encode()), (PICTURE, png))
            if not p.is_file() or p.read_bytes() != want
        ]
        for p in stale:
            print(f"{p} is stale — re-run without --check", file=sys.stderr)
        return 1 if stale else 0
    TARGET.write_text(current, encoding="utf-8")
    PICTURE.parent.mkdir(parents=True, exist_ok=True)
    PICTURE.write_bytes(png)
    print(f"wrote {TARGET} and {PICTURE} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
