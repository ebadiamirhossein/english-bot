"""Book unit ingestion (S6).

Vision OCR parse/merge and book_units upsert. All queries scoped by user_id.
Handlers must not talk to the database directly — call these helpers.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from app.db import connection
from app.llm import LLMError, chat

logger = logging.getLogger(__name__)

MAX_PAGES_PER_BATCH = 20

_WORD_BANK_LABEL_RE = re.compile(
    r"^(verbs?|nouns?|adjectives?|adverbs?|words?)\s*:",
    re.IGNORECASE,
)
_PARENS_RE = re.compile(r"\s*\([^)]*\)\s*")
_WS_RE = re.compile(r"\s+")

_BOOK_SLUGS = {
    "murphy": "murphy",
    "vocabulary_in_use": "vocabulary_in_use",
    "marketing": "marketing",
}


@dataclass
class PageFailure:
    batch_index: int
    reason: str  # unreadable | orphan | llm | malformed


@dataclass
class MergedUnit:
    unit_number: str
    unit_title: str
    target_items: list[str] = field(default_factory=list)


def slugify_book_name(raw: str) -> str:
    """Canonical lowercased slug for Other book names."""
    s = raw.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s.strip("_")


def preset_book_slug(key: str) -> str | None:
    return _BOOK_SLUGS.get(key)


def union_target_items(*lists: list[str]) -> list[str]:
    """Preserve order; drop exact duplicate strings."""
    seen: set[str] = set()
    out: list[str] = []
    for items in lists:
        for item in items:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def _as_unit_number(value: Any) -> str | None:
    """Keep unit_number as a string; never coerce via int()."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # Model occasionally emits a number despite the prompt — stringify
        # without int truncation of labels like 12.0 → keep "12".
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def parse_ocr_payload(
    raw: Any, *, batch_index: int, user_id: int
) -> dict[str, Any] | PageFailure:
    """Validate one vision JSON object. Returns payload or a PageFailure."""
    if not isinstance(raw, dict):
        logger.warning(
            "book OCR malformed user_id=%s page=%s reason=not_object",
            user_id,
            batch_index,
        )
        return PageFailure(batch_index, "malformed")

    readable = raw.get("readable", True)
    if readable is False:
        logger.warning(
            "book OCR unreadable user_id=%s page=%s",
            user_id,
            batch_index,
        )
        return PageFailure(batch_index, "unreadable")

    unit_number = _as_unit_number(raw.get("unit_number"))
    title_raw = raw.get("unit_title")
    unit_title = title_raw.strip() if isinstance(title_raw, str) else ""
    items_raw = raw.get("target_items")
    if items_raw is None:
        target_items: list[str] = []
    elif not isinstance(items_raw, list):
        logger.warning(
            "book OCR malformed user_id=%s page=%s reason=bad_target_items",
            user_id,
            batch_index,
        )
        return PageFailure(batch_index, "malformed")
    else:
        target_items = union_target_items(
            [str(x) for x in items_raw if isinstance(x, (str, int, float))]
        )

    return {
        "unit_number": unit_number,
        "unit_title": unit_title,
        "target_items": target_items,
    }


def merge_page_results(
    page_payloads: list[tuple[int, dict[str, Any] | PageFailure | Exception]],
    *,
    user_id: int,
) -> tuple[list[MergedUnit], list[PageFailure]]:
    """Merge OCR page results into units; collect named failures."""
    units_by_number: dict[str, MergedUnit] = {}
    order: list[str] = []
    current_number: str | None = None
    failures: list[PageFailure] = []

    for batch_index, payload in page_payloads:
        if isinstance(payload, Exception):
            logger.warning(
                "book OCR page failure user_id=%s page=%s error=%s",
                user_id,
                batch_index,
                payload,
            )
            failures.append(PageFailure(batch_index, "llm"))
            continue
        if isinstance(payload, PageFailure):
            failures.append(payload)
            continue

        unit_number = payload["unit_number"]
        if unit_number is None:
            if current_number is None:
                logger.warning(
                    "book OCR orphan continuation user_id=%s page=%s",
                    user_id,
                    batch_index,
                )
                failures.append(PageFailure(batch_index, "orphan"))
                continue
            unit = units_by_number[current_number]
            unit.target_items = union_target_items(
                unit.target_items, payload["target_items"]
            )
            if payload["unit_title"] and not unit.unit_title:
                unit.unit_title = payload["unit_title"]
            continue

        # Keep as string — never int.
        number_key = str(unit_number)
        current_number = number_key
        if number_key not in units_by_number:
            units_by_number[number_key] = MergedUnit(
                unit_number=number_key,
                unit_title=payload["unit_title"] or "",
                target_items=list(payload["target_items"]),
            )
            order.append(number_key)
        else:
            unit = units_by_number[number_key]
            unit.target_items = union_target_items(
                unit.target_items, payload["target_items"]
            )
            if payload["unit_title"] and not unit.unit_title:
                unit.unit_title = payload["unit_title"]

    return [units_by_number[k] for k in order], failures


def upsert_unit(
    user_id: int,
    book: str,
    unit: MergedUnit,
    *,
    studied_at: date | None = None,
) -> None:
    """Insert or update by (user_id, book, unit_number) in application code."""
    today = studied_at or date.today()
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT id, unit_title, target_items
                  FROM book_units
                 WHERE user_id = %s AND book = %s AND unit_number = %s
                 ORDER BY id
                 LIMIT 1
                """,
                (user_id, book, unit.unit_number),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO book_units (
                        user_id, book, unit_number, unit_title,
                        target_items, studied_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        user_id,
                        book,
                        unit.unit_number,
                        unit.unit_title or None,
                        json.dumps(unit.target_items),
                        today,
                    ),
                )
                return

            existing_items = row["target_items"]
            if isinstance(existing_items, str):
                try:
                    existing_items = json.loads(existing_items)
                except json.JSONDecodeError:
                    existing_items = []
            if not isinstance(existing_items, list):
                existing_items = []
            merged_items = union_target_items(
                [str(x) for x in existing_items],
                unit.target_items,
            )
            existing_title = row["unit_title"] or ""
            new_title = unit.unit_title or existing_title
            conn.execute(
                """
                UPDATE book_units
                   SET target_items = %s::jsonb,
                       unit_title = %s,
                       studied_at = %s
                 WHERE id = %s AND user_id = %s
                """,
                (
                    json.dumps(merged_items),
                    new_title or None,
                    today,
                    row["id"],
                    user_id,
                ),
            )


def persist_units(
    user_id: int,
    book: str,
    units: list[MergedUnit],
    *,
    studied_at: date | None = None,
) -> int:
    """Upsert each merged unit. Returns count written."""
    for unit in units:
        upsert_unit(user_id, book, unit, studied_at=studied_at)
    return len(units)


def ocr_one_page(
    image_bytes: bytes,
    *,
    system: str,
    chat_fn: Callable[..., Any] | None = None,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    """Call vision LLM for one page. Raises LLMError on failure."""
    call = chat_fn or chat
    result = call(
        [{"role": "user", "content": "Extract unit info from this page."}],
        system=system,
        json_mode=True,
        max_tokens=max_tokens,
        images=[image_bytes],
    )
    if not isinstance(result, dict):
        raise LLMError("OCR response was not a JSON object")
    return result


def format_page_list(indexes: list[int]) -> str:
    """Human list: '3', '3 and 7', '3, 7 and 9'."""
    if not indexes:
        return ""
    if len(indexes) == 1:
        return str(indexes[0])
    if len(indexes) == 2:
        return f"{indexes[0]} and {indexes[1]}"
    return ", ".join(str(i) for i in indexes[:-1]) + f" and {indexes[-1]}"


def format_pages_phrase(indexes: list[int]) -> str:
    """'Page 1' / 'Pages 3 and 7' / 'All 10 pages' when more than four fail."""
    if not indexes:
        return ""
    if len(indexes) > 4:
        return f"All {len(indexes)} pages"
    body = format_page_list(indexes)
    noun = "Page" if len(indexes) == 1 else "Pages"
    return f"{noun} {body}"


def _reshoot_cta(indexes: list[int], texts_module: Any) -> str:
    if len(indexes) <= 1:
        return texts_module.BOOK_SUMMARY_RESHOOT_ONE
    return texts_module.BOOK_SUMMARY_RESHOOT_MANY


def build_summary_text(
    *,
    book: str,
    units: list[MergedUnit],
    failures: list[PageFailure],
    over_cap: bool,
    texts_module: Any,
) -> str:
    """Compose user-facing summary; names batch indexes, never bare counts alone."""
    lines: list[str] = []
    if units:
        unit_bits = []
        for u in units:
            label = u.unit_number
            if u.unit_title:
                label = f"{u.unit_number} — {u.unit_title}"
            unit_bits.append(label)
        lines.append(
            texts_module.BOOK_SUMMARY_UNITS.format(
                book=book,
                units="; ".join(unit_bits),
                count=len(units),
            )
        )
    else:
        lines.append(texts_module.BOOK_SUMMARY_NO_UNITS)

    by_reason: dict[str, list[int]] = {}
    for f in failures:
        by_reason.setdefault(f.reason, []).append(f.batch_index)

    unread_idxs = sorted(
        set(by_reason.get("unreadable", [])) | set(by_reason.get("malformed", []))
    )
    llm_fail = sorted(by_reason.get("llm", []))
    orphan = sorted(by_reason.get("orphan", []))

    if unread_idxs:
        lines.append(
            texts_module.BOOK_SUMMARY_UNREADABLE.format(
                pages=format_pages_phrase(unread_idxs),
                cta=_reshoot_cta(unread_idxs, texts_module),
            )
        )
    if llm_fail:
        lines.append(
            texts_module.BOOK_SUMMARY_LLM_FAIL.format(
                pages=format_pages_phrase(llm_fail),
                cta=_reshoot_cta(llm_fail, texts_module),
            )
        )
    if orphan:
        lines.append(
            texts_module.BOOK_SUMMARY_ORPHAN.format(
                pages=format_pages_phrase(orphan)
            )
        )
    if over_cap:
        lines.append(texts_module.BOOK_SUMMARY_OVER_CAP)

    lines.append(texts_module.BOOK_SUMMARY_FOOTER)
    return "\n\n".join(lines)


def count_units_for_user(user_id: int, book: str, unit_number: str) -> int:
    """Test helper: how many rows for this unit."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM book_units
             WHERE user_id = %s AND book = %s AND unit_number = %s
            """,
            (user_id, book, unit_number),
        ).fetchone()
    return int(row["n"]) if row else 0


def get_unit_row(
    user_id: int, book: str, unit_number: str
) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, unit_title, target_items, studied_at
              FROM book_units
             WHERE user_id = %s AND book = %s AND unit_number = %s
             ORDER BY id
             LIMIT 1
            """,
            (user_id, book, unit_number),
        ).fetchone()


def list_units_for_user(user_id: int) -> list[dict[str, Any]]:
    """Stored units for this user, newest studied_at first."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT book, unit_number, unit_title, studied_at, target_items
              FROM book_units
             WHERE user_id = %s
             ORDER BY studied_at DESC NULLS LAST, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def studied_murphy_unit_numbers(user_id: int) -> set[str]:
    """TEXT unit_number values the user has stored for book slug ``murphy``."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT unit_number
              FROM book_units
             WHERE user_id = %s AND book = %s
            """,
            (user_id, "murphy"),
        ).fetchall()
    return {str(r["unit_number"]) for r in rows}


def find_units_by_number(
    user_id: int, unit_number: str
) -> list[dict[str, Any]]:
    """Exact TEXT match on unit_number — never coerce via int()."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT book, unit_number, unit_title, studied_at, target_items
              FROM book_units
             WHERE user_id = %s AND unit_number = %s
             ORDER BY studied_at DESC NULLS LAST, id DESC
            """,
            (user_id, unit_number),
        ).fetchall()
    return [dict(r) for r in rows]


def is_word_bank_item(text: str) -> bool:
    """True for exercise word banks, not teachable grammar points.

    Label at start (``verbs: a, b, c``) OR, after stripping parentheticals,
    a bare short-token comma list. Parenthetical exemplars never trigger the
    comma arm — so stative-verbs items with ``(like, want, …)`` stay.
    """
    s = text.strip()
    if not s:
        return True
    if _WORD_BANK_LABEL_RE.match(s):
        return True
    outside = _PARENS_RE.sub(" ", s).strip()
    outside = _WS_RE.sub(" ", outside)
    body = _WORD_BANK_LABEL_RE.sub("", outside, count=1).strip()
    tokens = [t.strip() for t in body.split(",") if t.strip()]
    if len(tokens) < 4:
        return False
    med = statistics.median(len(t) for t in tokens)
    return med <= 6


def normalize_item_key(text: str) -> str:
    """Casefold + collapse whitespace + strip parentheticals for near-dedup."""
    s = _PARENS_RE.sub(" ", text.strip())
    s = _WS_RE.sub(" ", s).strip().casefold()
    return s


def dedupe_teachable_items(items: list[str]) -> list[str]:
    """Drop word banks and near-duplicates; preserve first-seen order."""
    kept: list[str] = []
    keys: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text or is_word_bank_item(text):
            continue
        key = normalize_item_key(text)
        if not key:
            continue
        if _is_near_duplicate(key, keys):
            continue
        keys.append(key)
        kept.append(text)
    return kept


def _is_near_duplicate(key: str, seen: list[str]) -> bool:
    for prev in seen:
        if key == prev:
            return True
        shorter, longer = (key, prev) if len(key) <= len(prev) else (prev, key)
        if len(shorter) >= 8 and shorter in longer:
            return True
    return False


def _as_item_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str)]


def teachable_items_for_unit(
    user_id: int, book: str, unit_number: str
) -> list[str]:
    row = get_unit_row(user_id, book, unit_number)
    if row is None:
        return []
    return dedupe_teachable_items(_as_item_list(row.get("target_items")))


def select_topup_items(user_id: int, need: int) -> list[dict[str, Any]]:
    """Newest units first; exhaust each unit's teachable items before the next."""
    if need <= 0:
        return []
    units = list_units_for_user(user_id)
    selected: list[dict[str, Any]] = []
    global_keys: list[str] = []
    for unit in units:
        if len(selected) >= need:
            break
        book = str(unit["book"])
        unit_number = str(unit["unit_number"])
        unit_title = str(unit.get("unit_title") or "")
        for item in dedupe_teachable_items(
            _as_item_list(unit.get("target_items"))
        ):
            if len(selected) >= need:
                break
            key = normalize_item_key(item)
            if _is_near_duplicate(key, global_keys):
                continue
            global_keys.append(key)
            selected.append(
                {
                    "book": book,
                    "unit_number": unit_number,
                    "unit_title": unit_title,
                    "item": item,
                }
            )
    return selected
