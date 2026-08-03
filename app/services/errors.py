"""Error journal writes.

S2 exposes record_errors only. due_errors / mark_result / spacing arrive in S3.
"""

from __future__ import annotations

import logging

from app.db import connection

logger = logging.getLogger(__name__)


def record_errors(user_id: int, source: str, corrections: list[dict]) -> int:
    """Insert one errors row per correction. Returns the number of rows written.

    All corrections from one message share a single transaction. Unknown
    error_type values are dropped with a warning — they do not fail the batch.
    """
    if not corrections:
        return 0

    written = 0
    with connection() as conn:
        with conn.transaction():
            type_rows = conn.execute(
                "SELECT code, murphy_units FROM error_types"
            ).fetchall()
            murphy_by_code = {
                row["code"]: row["murphy_units"] for row in type_rows
            }
            valid_codes = frozenset(murphy_by_code)

            for item in corrections:
                error_type = item.get("error_type")
                if error_type not in valid_codes:
                    logger.warning(
                        "Dropping correction with unknown error_type=%r "
                        "user_id=%s",
                        error_type,
                        user_id,
                    )
                    continue
                conn.execute(
                    """
                    INSERT INTO errors (
                        user_id,
                        source,
                        you_said,
                        correct_form,
                        error_type,
                        explanation,
                        murphy_units,
                        next_review
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_DATE + 1
                    )
                    """,
                    (
                        user_id,
                        source,
                        item["you_said"],
                        item["correct_form"],
                        error_type,
                        item.get("explanation"),
                        murphy_by_code[error_type],
                    ),
                )
                written += 1
    return written
