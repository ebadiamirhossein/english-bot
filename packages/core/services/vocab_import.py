"""Trancy vocabulary CSV → LLM sentences → sender-only chunks (S24a/S24b).

Generation runs with no DB connection held. Persist uses insert-then-send
inside a transaction (same pattern as prep). Never writes ``errors``.
Never touches ``shared_content``. Folder path must not call this module.

S24b: one capped retry for gate failures; skipped words named in the
Telegram reply only — never in logs (PRD §10).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from core import copy
from core.db import connection
from core.llm import LLMError, chat
from core.services.chunks import count_due_chunks, insert_chunks
from core.services.reading import normalize_for_match
from core.services.watch_import import (
    existing_chunk_norms,
    parse_vocabulary_seed_items,
)

logger = logging.getLogger(__name__)


class VocabGenerationError(Exception):
    """Raised when the first-pass sentence generation fails after json_mode retry."""


VOCAB_SOURCE = "vocabulary"
VOCAB_BATCH_SIZE = 40
SKIP_LIST_CAP = 8
_MAX_TOKENS = 4000
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "vocab_sentences.txt"
)
_SKIP_REASON_EXACT = "no sentence used the exact word"
_SKIP_REASON_MISSING = "no sentence used the exact word"

_prompt_template: str | None = None


@dataclass(frozen=True)
class VocabGateFailure:
    """A seed that failed exact-word validation (for retry / reply)."""

    seed: dict[str, str]
    bad_sentence: str | None
    reason: str


def init_vocab_prompt() -> None:
    """Load the vocabulary sentence prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def _system_prompt(*, cefr_level: str, work_domain: str) -> str:
    if _prompt_template is None:
        init_vocab_prompt()
    assert _prompt_template is not None
    domain = (work_domain or "").strip() or "general"
    return _prompt_template.format(
        cefr_level=cefr_level,
        work_domain=domain,
    )


def wrap_vocab_batch(items: Sequence[dict[str, str]]) -> str:
    """User message: words + Translation glosses for sense selection."""
    lines = [
        "Generate one English sentence for each word below.",
        "Use the gloss only to choose the sense. Output English only.",
        "Use each word in EXACTLY the form given — not an inflection.",
        "",
    ]
    for i, item in enumerate(items, start=1):
        lines.append(f"{i}. word: {item['chunk']}")
        lines.append(f"   gloss: {item['meaning']}")
    return "\n".join(lines)


def wrap_vocab_retry_batch(
    failed: Sequence[VocabGateFailure],
) -> str:
    """Retry user message for words that failed the exact-form gate."""
    lines = [
        "Retry — previous sentences were discarded.",
        "Write one English sentence per word using EXACTLY the form given.",
        "Do not use an inflection or derived form. Output English only.",
        "",
    ]
    for i, item in enumerate(failed, start=1):
        seed = item.seed
        lines.append(f"{i}. word: {seed['chunk']}")
        lines.append(f"   gloss: {seed['meaning']}")
        if item.bad_sentence:
            lines.append(
                f"   previous_discarded_sentence: {item.bad_sentence}"
            )
            lines.append(
                "   (that sentence did not contain the exact word form)"
            )
        else:
            lines.append("   (no usable sentence was returned for this word)")
    return "\n".join(lines)


@dataclass(frozen=True)
class VocabDedupeResult:
    """Seeds that still need sentences after in-file + DB dedupe."""

    need: list[dict[str, str]]
    duplicates: int
    within_file_skipped: int


def dedupe_vocabulary_seeds(
    seeds: Sequence[dict[str, str]],
    *,
    existing_norms: set[str] | None = None,
    user_id: int | None = None,
) -> VocabDedupeResult:
    """Collapse within-file duplicates, then drop words already owned.

    First occurrence in the file wins. ``existing_norms`` may be injected for
    tests; otherwise load from ``user_id``.
    """
    if existing_norms is None:
        if user_id is None:
            raise ValueError("user_id or existing_norms required")
        existing_norms = existing_chunk_norms(user_id)

    seen_file: set[str] = set()
    unique: list[dict[str, str]] = []
    within_file_skipped = 0
    for seed in seeds:
        key = normalize_for_match(seed["chunk"])
        if not key:
            within_file_skipped += 1
            continue
        if key in seen_file:
            within_file_skipped += 1
            continue
        seen_file.add(key)
        unique.append(seed)

    need: list[dict[str, str]] = []
    duplicates = 0
    owned = set(existing_norms)
    for seed in unique:
        key = normalize_for_match(seed["chunk"])
        if key in owned:
            duplicates += 1
            continue
        owned.add(key)
        need.append(seed)
    return VocabDedupeResult(
        need=need,
        duplicates=duplicates,
        within_file_skipped=within_file_skipped,
    )


def _parse_sentence_map(raw: Any, expected_words: set[str]) -> dict[str, str]:
    """Map exact input word → sentence. Unknown words ignored."""
    if not isinstance(raw, dict):
        raise VocabGenerationError("vocab sentences response is not an object")
    items = raw.get("sentences")
    if not isinstance(items, list):
        raise VocabGenerationError("vocab sentences missing sentences list")
    out: dict[str, str] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        word = entry.get("word")
        sentence = entry.get("full_sentence")
        if not isinstance(word, str) or not isinstance(sentence, str):
            continue
        word = word.strip()
        sentence = sentence.strip()
        if not word or not sentence:
            continue
        if word not in expected_words:
            continue
        if word not in out:
            out[word] = sentence
    return out


def generate_vocab_sentences(
    items: Sequence[dict[str, str]],
    *,
    cefr_level: str,
    work_domain: str,
    batch_size: int = VOCAB_BATCH_SIZE,
    chat_fn: Callable[..., str | dict] | None = None,
    user_content: str | None = None,
) -> dict[str, str]:
    """One or more batched ``chat`` calls → exact word → sentence map.

    Raises ``VocabGenerationError`` on provider/parse failure after json_mode
    repair. First-pass callers must abort the whole file on failure.
    """
    if not items:
        return {}
    call = chat_fn or chat
    system = _system_prompt(cefr_level=cefr_level, work_domain=work_domain)
    merged: dict[str, str] = {}

    # Retry path supplies a single crafted user message covering all items.
    if user_content is not None:
        expected = {item["chunk"] for item in items}
        try:
            raw = call(
                [{"role": "user", "content": user_content}],
                system=system,
                json_mode=True,
                max_tokens=_MAX_TOKENS,
            )
            return _parse_sentence_map(raw, expected)
        except (LLMError, VocabGenerationError) as exc:
            raise VocabGenerationError(str(exc)) from exc

    size = max(1, batch_size)
    for start in range(0, len(items), size):
        batch = list(items[start : start + size])
        expected = {item["chunk"] for item in batch}
        try:
            raw = call(
                [{"role": "user", "content": wrap_vocab_batch(batch)}],
                system=system,
                json_mode=True,
                max_tokens=_MAX_TOKENS,
            )
            part = _parse_sentence_map(raw, expected)
        except (LLMError, VocabGenerationError) as exc:
            raise VocabGenerationError(str(exc)) from exc
        merged.update(part)
    return merged


@dataclass(frozen=True)
class VocabValidateResult:
    chunks: list[dict[str, str]]
    failed: list[VocabGateFailure]

    @property
    def rejected(self) -> int:
        return len(self.failed)


def match_and_validate_sentences(
    seeds: Sequence[dict[str, str]],
    sentence_by_word: dict[str, str],
) -> VocabValidateResult:
    """Exact word match, then normalize_for_match word-in-sentence gate.

    Missing or altered response words count as failed. Extra response keys
    are ignored. Counts over ``seeds`` must add up.
    """
    chunks: list[dict[str, str]] = []
    failed: list[VocabGateFailure] = []
    for seed in seeds:
        word = seed["chunk"]
        sentence = sentence_by_word.get(word)
        if sentence is None:
            failed.append(
                VocabGateFailure(
                    seed=seed,
                    bad_sentence=None,
                    reason=_SKIP_REASON_MISSING,
                )
            )
            continue
        chunk_norm = normalize_for_match(word)
        if chunk_norm not in normalize_for_match(sentence):
            failed.append(
                VocabGateFailure(
                    seed=seed,
                    bad_sentence=sentence,
                    reason=_SKIP_REASON_EXACT,
                )
            )
            continue
        chunks.append(
            {
                "chunk": word,
                "full_sentence": sentence,
                "meaning": seed["meaning"],
            }
        )
    return VocabValidateResult(chunks=chunks, failed=failed)


def _retry_gate_failures(
    failed: Sequence[VocabGateFailure],
    *,
    cefr_level: str,
    work_domain: str,
    chat_fn: Callable[..., str | dict] | None,
    batch_size: int,
) -> tuple[list[dict[str, str]], list[VocabGateFailure]]:
    """One capped retry for gate failures. LLMError → keep failures as skips."""
    if not failed:
        return [], []
    seeds = [f.seed for f in failed]
    try:
        sentence_map = generate_vocab_sentences(
            seeds,
            cefr_level=cefr_level,
            work_domain=work_domain,
            batch_size=batch_size,
            chat_fn=chat_fn,
            user_content=wrap_vocab_retry_batch(failed),
        )
    except VocabGenerationError:
        # First pass already succeeded — do not abort the import.
        logger.warning(
            "vocab import retry_failed count=%s reason=llm_error",
            len(failed),
        )
        return [], list(failed)

    validated = match_and_validate_sentences(seeds, sentence_map)
    return validated.chunks, validated.failed


@dataclass(frozen=True)
class VocabImportCounts:
    imported: int
    duplicates: int
    invalid: int
    due: int
    named_skips: tuple[tuple[str, str], ...] = ()


def format_vocab_import_reply(counts: VocabImportCounts) -> str:
    """User-facing import result; names skipped words (capped)."""
    base = copy.IMPORT_DOC_RESULT.format(
        imported=counts.imported,
        duplicates=counts.duplicates,
        invalid=counts.invalid,
        due=counts.due,
    )
    skips = counts.named_skips
    if not skips:
        return base
    shown = skips[:SKIP_LIST_CAP]
    lines = [f"• {word} — {reason}" for word, reason in shown]
    more = len(skips) - len(shown)
    if more > 0:
        lines.append(copy.IMPORT_DOC_VOCAB_SKIPS_MORE.format(n=more))
    skip_block = copy.IMPORT_DOC_VOCAB_SKIPS.format(lines="\n".join(lines))
    # Insert skip block before the due line.
    parts = base.rsplit("\n", 1)
    if len(parts) == 2:
        return f"{parts[0]}\n{skip_block}\n{parts[1]}"
    return f"{base}\n{skip_block}"


def prepare_vocabulary_import(
    headers: Sequence[str],
    rows: Sequence[dict[str, str | None]],
    *,
    user_id: int,
    cefr_level: str,
    work_domain: str,
    now: date,
    chat_fn: Callable[..., str | dict] | None = None,
    batch_size: int = VOCAB_BATCH_SIZE,
) -> tuple[list[dict[str, str]], VocabImportCounts]:
    """Parse → dedupe → generate → validate → one retry for gate failures.

    First-pass ``VocabGenerationError`` aborts (zero rows). A retry
    ``VocabGenerationError`` keeps first-pass rows and reports remaining
    words as skipped.
    """
    seeds, skipped_empty = parse_vocabulary_seed_items(headers, rows)
    deduped = dedupe_vocabulary_seeds(seeds, user_id=user_id)
    invalid = skipped_empty + deduped.within_file_skipped

    if not deduped.need:
        due = count_due_chunks(user_id, now=now)
        return [], VocabImportCounts(
            imported=0,
            duplicates=deduped.duplicates,
            invalid=invalid,
            due=due,
        )

    sentence_map = generate_vocab_sentences(
        deduped.need,
        cefr_level=cefr_level,
        work_domain=work_domain,
        batch_size=batch_size,
        chat_fn=chat_fn,
    )
    validated = match_and_validate_sentences(deduped.need, sentence_map)
    chunks = list(validated.chunks)
    still_failed = list(validated.failed)

    if still_failed:
        rescued, still_failed = _retry_gate_failures(
            still_failed,
            cefr_level=cefr_level,
            work_domain=work_domain,
            chat_fn=chat_fn,
            batch_size=batch_size,
        )
        chunks.extend(rescued)

    named_skips = tuple(
        (f.seed["chunk"], f.reason) for f in still_failed
    )
    invalid += len(named_skips)

    # Log counts and reason category only — never the words (PRD §10).
    if named_skips:
        logger.info(
            "vocab import gate_skips user_id=%s count=%s "
            "reason=exact_form_or_missing",
            user_id,
            len(named_skips),
        )

    due = count_due_chunks(user_id, now=now)
    return chunks, VocabImportCounts(
        imported=len(chunks),
        duplicates=deduped.duplicates,
        invalid=invalid,
        due=due,
        named_skips=named_skips,
    )


async def persist_vocabulary_and_send(
    *,
    user_id: int,
    chunks: Sequence[dict[str, str]],
    send: Callable[[], Awaitable[None]],
) -> int:
    """Insert vocabulary chunks, send reply, then commit.

    ``send`` is awaited inside the open transaction. If it raises, the
    transaction rolls back and zero rows remain. Generation must already
    be finished — this function must not call the LLM.
    """
    if not chunks:
        await send()
        return 0
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                user_id,
                source=VOCAB_SOURCE,
                track=None,
                chunks=chunks,
            )
            await send()
    return len(chunks)


__all__ = [
    "SKIP_LIST_CAP",
    "VOCAB_BATCH_SIZE",
    "VOCAB_SOURCE",
    "VocabDedupeResult",
    "VocabGateFailure",
    "VocabGenerationError",
    "VocabImportCounts",
    "VocabValidateResult",
    "dedupe_vocabulary_seeds",
    "format_vocab_import_reply",
    "generate_vocab_sentences",
    "init_vocab_prompt",
    "match_and_validate_sentences",
    "persist_vocabulary_and_send",
    "prepare_vocabulary_import",
    "wrap_vocab_batch",
    "wrap_vocab_retry_batch",
]
