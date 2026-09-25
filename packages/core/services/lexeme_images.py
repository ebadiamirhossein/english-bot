"""Every query against `lexeme_images` (migration 033). W13d.

The table is GLOBAL — one approved picture per lemma, shared by every learner —
so nothing here takes a `user_id`, and nothing here may be scoped by one.

Three readers and one writer:

- `face_for` — the picture half of a card face, called by
  `core.services.cards.card_face` and nowhere else (#190: one producer);
- `image_file` — the bytes, for `GET /lexeme-images/{id}.{ext}`;
- `proposal_lemmas` — which lemmas `core.images.bank --propose` asks about;
- `replace` / `remove` — written only by `core.images.bank --load --apply`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.db import connection
from core.images import EXTENSION, shows_picture


@dataclass(frozen=True, slots=True)
class StoredImage:
    """One row as `--load` compares it against `data/lexeme_images.tsv`."""

    id: int
    lemma: str
    commons_file: str
    original_sha1: str
    licence: str
    author: str


def face_for(card_type: str, lexeme_id: int | None) -> dict | None:
    """The `image` field of a card face, or None.

    **None is the whole of PRD §2.6.3's *"demonstrably unchanged"*:** a phrase
    card, a collocation card and a word nobody approved a picture for all come
    back None, and the card face is exactly what it was before W13d plus
    `"image": null`. `shows_picture` answers the first two without a query.

    Everything the card must SHOW is here, because CC BY requires the credit to
    be VISIBLE (TASKS' W13d row): the author, the licence and a link to each.
    """
    if not shows_picture(card_type, lexeme_id):
        return None
    with connection() as conn:
        row = conn.execute(
            """
            SELECT li.id, li.mime, li.width, li.height, li.author, li.licence,
                   li.licence_url, li.source_url, l.lemma
              FROM lexeme_images li
              JOIN lexemes l ON l.id = li.lexeme_id
             WHERE li.lexeme_id = %s
            """,
            (lexeme_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "ext": EXTENSION[row["mime"]],
        "width": row["width"],
        "height": row["height"],
        "alt": row["lemma"],
        "author": row["author"] or None,
        "licence": row["licence"],
        "licence_url": row["licence_url"],
        "source_url": row["source_url"],
    }


def image_file(image_id: int) -> tuple[bytes, str] | None:
    """The stored thumbnail and its media type, or None."""
    with connection() as conn:
        row = conn.execute(
            "SELECT bytes, mime FROM lexeme_images WHERE id = %s", (image_id,)
        ).fetchone()
    if row is None:
        return None
    return bytes(row["bytes"]), row["mime"]


def proposal_lemmas(limit: int) -> list[str]:
    """Lemmas worth proposing a picture for, most frequent first.

    A NOUN-tagged lemma that some learner actually has a word card for, or that
    the syllabus teaches, and that has no picture yet. **This narrows; it never
    decides** — the tag is noisy (`you` is a NOUN in `data/lexemes.tsv`) and the
    operator's approval is what makes a word picturable.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT l.lemma
              FROM lexemes l
             WHERE l.pos = 'NOUN'
               AND length(l.lemma) >= 3
               AND NOT EXISTS (SELECT 1 FROM lexeme_images li WHERE li.lexeme_id = l.id)
               AND (
                    EXISTS (SELECT 1 FROM cards c
                             WHERE c.lexeme_id = l.id AND c.card_type <> 'collocation')
                 OR EXISTS (SELECT 1 FROM syllabus_unit_lexemes s WHERE s.lexeme_id = l.id)
               )
             ORDER BY l.freq_rank NULLS LAST, l.lemma
             LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [r["lemma"] for r in rows]


def lexeme_ids(lemmas: Sequence[str]) -> dict[str, int]:
    """`{lemma: id}` for the lemmas that exist. A TSV line naming a lemma the
    lexicon does not hold is refused by `--load`, never created."""
    if not lemmas:
        return {}
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, lemma FROM lexemes WHERE lemma = ANY(%s)", (list(lemmas),)
        ).fetchall()
    return {r["lemma"]: r["id"] for r in rows}


def stored() -> dict[str, StoredImage]:
    """Every approved picture, by lemma."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT li.id, l.lemma, li.commons_file, li.original_sha1, li.licence,
                   li.author
              FROM lexeme_images li JOIN lexemes l ON l.id = li.lexeme_id
            """
        ).fetchall()
    return {
        r["lemma"]: StoredImage(
            id=r["id"],
            lemma=r["lemma"],
            commons_file=r["commons_file"],
            original_sha1=r["original_sha1"],
            licence=r["licence"],
            author=r["author"],
        )
        for r in rows
    }


def replace(
    *,
    lexeme_id: int,
    commons_file: str,
    source_url: str,
    original_sha1: str,
    author: str,
    licence: str,
    licence_url: str | None,
    mime: str,
    width: int,
    height: int,
    data: bytes,
) -> int:
    """Store the approved picture for one lemma, replacing any earlier one.

    **Delete and insert, never update in place:** the new row takes a new id,
    so the URL a browser cached for the old picture (`immutable`, a year) can
    never serve the new one's bytes, or the old one's attribution.
    """
    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM lexeme_images WHERE lexeme_id = %s", (lexeme_id,))
            row = conn.execute(
                """
                INSERT INTO lexeme_images
                    (lexeme_id, commons_file, source_url, original_sha1, author,
                     licence, licence_url, mime, width, height, bytes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    lexeme_id,
                    commons_file,
                    source_url,
                    original_sha1,
                    author,
                    licence,
                    licence_url,
                    mime,
                    width,
                    height,
                    data,
                ),
            ).fetchone()
    return int(row["id"])


def remove(lemmas: Sequence[str]) -> int:
    """Withdraw the pictures for lemmas the operator took out of the TSV."""
    if not lemmas:
        return 0
    with connection() as conn:
        with conn.transaction():
            cur = conn.execute(
                """
                DELETE FROM lexeme_images li USING lexemes l
                 WHERE l.id = li.lexeme_id AND l.lemma = ANY(%s)
                """,
                (list(lemmas),),
            )
    return cur.rowcount
