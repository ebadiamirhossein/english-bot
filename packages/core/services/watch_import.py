"""Subtitle CSV import (S15a folder + S15b Telegram document).

Trancy / Language Reactor exports → ``chunks`` (S7a review + Anki pool).
S24: exact five-column slang signature is mutually exclusive with Trancy/LR.
S24a: exact four-column Trancy vocabulary (no sentence) — Telegram + LLM only.
No provider SDKs. Stdlib ``csv`` only. Logs filenames and counts, never row
content (PRD §10). Both entrances share ``import_csv_rows`` / ``map_headers``.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Sequence

from core.config import load_settings
from core.db import connection
from core.services.chunks import count_due_chunks, insert_chunks
from core.services.paths import (
    PathSafetyError,
    assert_path_outside_repo,
    collision_safe_dest,
    move_collision_safe,
)
from core.services.reading import normalize_for_match

logger = logging.getLogger(__name__)

IMPORT_STABLE_AFTER = timedelta(minutes=2)
# Phrase exports are small; multi-year cumulatives fit under 5 MiB. Larger is
# almost certainly a wrong file (video, spreadsheet dump) — refuse before
# download so we never hold it in memory.
CSV_IMPORT_MAX_BYTES = 5 * 1024 * 1024
TOOL_FOLDERS = ("trancy", "language_reactor")
_TOOL_ALIASES = {
    "trancy": "trancy",
    "language_reactor": "language_reactor",
    "lr": "language_reactor",
}
_SLUG_MAX = 48
_CHUNK_TOKENS = ("word", "phrase", "expression")
_SENTENCE_TOKENS = ("sentence", "context", "subtitle")
_MEANING_TOKENS = ("translation", "meaning", "definition")
_MATERIAL_TOKENS = ("title", "video", "movie", "show")
# Whole-header signature only — never token presence (S24 / known issue #27).
SLANG_HEADER_SET = frozenset(
    {"word", "phonetic", "meaning", "example", "date"}
)
# Real Trancy vocabulary export (S24a) — four columns, no sentence.
VOCABULARY_HEADER_SET = frozenset(
    {"word", "phonetic", "translation", "date"}
)
CsvFormat = Literal["slang", "vocabulary", "trancy", "language_reactor"]

# Module-level: resets on process restart (acceptable — notify_operator
# throttles; do not put this in bot_data).
_warned_orphan_names: set[str] = set()


class WatchConfigError(ValueError):
    """WATCH_DIR set but unusable (missing, unwritable, or inside repo)."""


@dataclass(frozen=True)
class HeaderMap:
    chunk: str
    full_sentence: str
    meaning: str
    material: str | None
    phonetic: str | None = None
    format: str = "subtitle"  # slang | subtitle


@dataclass(frozen=True)
class FileImportResult:
    filename: str
    status: str  # imported | failed_headers | skipped_young | skipped_empty
    imported: int = 0
    duplicates: int = 0
    invalid: int = 0
    due_after: int | None = None
    source_tool: str = "csv"
    headers_seen: tuple[str, ...] = ()
    csv_format: str | None = None


@dataclass
class UserScanResult:
    user_id: int
    files: list[FileImportResult] = field(default_factory=list)
    settling: int = 0  # files skipped as too young

    @property
    def any_work(self) -> bool:
        return any(
            f.status in ("imported", "failed_headers") for f in self.files
        )

    @property
    def total_imported(self) -> int:
        return sum(f.imported for f in self.files)

    @property
    def total_duplicates(self) -> int:
        return sum(f.duplicates for f in self.files)

    @property
    def total_invalid(self) -> int:
        return sum(f.invalid for f in self.files)


def clear_orphan_warnings() -> None:
    """Test helper — reset the module-level orphan WARN set."""
    _warned_orphan_names.clear()


def normalize_header(name: str) -> str:
    return name.casefold().strip()


def _header_words(norm: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", norm))


def _first_matching(
    headers: Sequence[str], tokens: Sequence[str]
) -> str | None:
    """First header whose normalised words include any token (whole-word).

    Whole-word matching avoids ``title`` matching inside ``subtitle``.
    """
    for header in headers:
        norm = normalize_header(header)
        if not norm:
            continue
        words = _header_words(norm)
        for token in tokens:
            if token in words:
                return header
    return None


def normalised_header_set(headers: Sequence[str]) -> frozenset[str]:
    return frozenset(
        normalize_header(h) for h in headers if h is not None and str(h).strip()
    )


def is_slang_headers(headers: Sequence[str]) -> bool:
    """True only when the header set is exactly the five slang columns."""
    return normalised_header_set(headers) == SLANG_HEADER_SET


def is_vocabulary_headers(headers: Sequence[str]) -> bool:
    """True only for the real Trancy vocabulary four-column signature."""
    return normalised_header_set(headers) == VOCABULARY_HEADER_SET


def is_trancy_legacy_headers(headers: Sequence[str]) -> bool:
    """Word + Translation + a sentence-like column; not phrase; not vocab.

    Sentence presence is structural — not ordering-dependent vs vocabulary.
    """
    if is_slang_headers(headers) or is_vocabulary_headers(headers):
        return False
    has_word = _first_matching(headers, ("word",)) is not None
    has_phrase = _first_matching(headers, ("phrase",)) is not None
    has_translation = _first_matching(headers, ("translation",)) is not None
    has_sentence = _first_matching(headers, _SENTENCE_TOKENS) is not None
    return (
        has_word
        and has_translation
        and has_sentence
        and not has_phrase
    )


def is_language_reactor_headers(headers: Sequence[str]) -> bool:
    """Phrase + definition/context/video; never slang or vocabulary."""
    if is_slang_headers(headers) or is_vocabulary_headers(headers):
        return False
    has_phrase = _first_matching(headers, ("phrase",)) is not None
    has_definition = _first_matching(headers, ("definition",)) is not None
    has_context = _first_matching(headers, ("context", "subtitle")) is not None
    has_video = _first_matching(headers, ("video",)) is not None
    return has_phrase and (has_definition or has_context or has_video)


def _header_by_norm(headers: Sequence[str], want: str) -> str | None:
    for header in headers:
        if header is None:
            continue
        if normalize_header(header) == want:
            return header
    return None


def classify_csv_format(headers: Sequence[str]) -> CsvFormat | None:
    """Mutually exclusive: slang | vocabulary | trancy | language_reactor | None.

    Predicates are structural (vocabulary ≠ Trancy-legacy even if order flips).
    Zero or multiple matches → None — never guess.
    """
    matches: list[CsvFormat] = []
    if is_slang_headers(headers):
        matches.append("slang")
    if is_vocabulary_headers(headers):
        matches.append("vocabulary")
    if is_trancy_legacy_headers(headers):
        matches.append("trancy")
    if is_language_reactor_headers(headers):
        matches.append("language_reactor")
    if len(matches) == 1:
        return matches[0]
    return None


def map_headers(headers: Sequence[str]) -> HeaderMap | None:
    """Return a column map, or None if a required field cannot be identified.

    Vocabulary has no CSV sentence column — use ``parse_vocabulary_seed_items``
    / the Telegram LLM path instead of this mapper.
    """
    if is_vocabulary_headers(headers):
        return None
    if is_slang_headers(headers):
        word = _header_by_norm(headers, "word")
        example = _header_by_norm(headers, "example")
        meaning = _header_by_norm(headers, "meaning")
        phonetic = _header_by_norm(headers, "phonetic")
        if word is None or example is None or meaning is None:
            return None
        return HeaderMap(
            chunk=word,
            full_sentence=example,
            meaning=meaning,
            material=None,
            phonetic=phonetic,
            format="slang",
        )

    fmt = classify_csv_format(headers)
    if fmt is None or fmt == "vocabulary":
        return None

    chunk = _first_matching(headers, _CHUNK_TOKENS)
    sentence = _first_matching(headers, _SENTENCE_TOKENS)
    meaning = _first_matching(headers, _MEANING_TOKENS)
    if chunk is None or sentence is None or meaning is None:
        return None
    # Material: skip columns already claimed by required fields.
    claimed = {chunk, sentence, meaning}
    remaining = [h for h in headers if h not in claimed]
    material = _first_matching(remaining, _MATERIAL_TOKENS)
    return HeaderMap(
        chunk=chunk,
        full_sentence=sentence,
        meaning=meaning,
        material=material,
        phonetic=None,
        format="subtitle",
    )


def slugify_material(raw: str) -> str:
    s = raw.strip().casefold()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "untitled"
    return s[:_SLUG_MAX].rstrip("_") or "untitled"


def tool_from_parent(parent_name: str) -> str:
    return _TOOL_ALIASES.get(parent_name.casefold().strip(), "csv")


def detect_tool_from_headers(headers: Sequence[str]) -> str:
    """Infer tool/format from header shape (Telegram path).

    Returns ``slang``, ``vocabulary``, ``trancy``, ``language_reactor``, or
    ``csv`` when unrecognised (caller should treat unrecognised as
    failed_headers).
    """
    fmt = classify_csv_format(headers)
    if fmt is None:
        return "csv"
    return fmt


def format_meaning(meaning: str, phonetic: str | None) -> str:
    """Append phonetic to meaning when present; no schema column for IPA."""
    meaning = meaning.strip()
    if not phonetic:
        return meaning
    ipa = phonetic.strip().strip("/")
    if not ipa:
        return meaning
    return f"{meaning} (/{ipa}/)"


def source_marker(tool: str, material: str) -> str:
    return f"subtitle_{tool}_{slugify_material(material)}"


def is_stable(path: Path, *, now: datetime) -> bool:
    """True when file mtime is at least IMPORT_STABLE_AFTER old."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - mtime) >= IMPORT_STABLE_AFTER


def instant_date(now: datetime) -> date:
    """Calendar date in UTC for due-count reporting (tests inject ``now``)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).date()


def watch_dir_configured() -> str:
    """Return stripped WATCH_DIR or empty string when unset."""
    return load_settings().watch_dir.strip()


def resolve_watch_root(watch_dir: str | None = None) -> Path:
    """Validate and return the absolute WATCH_DIR path.

    Raises WatchConfigError when set but missing/unwritable/inside repo.
    Raises ValueError when unset/empty.
    """
    raw = watch_dir if watch_dir is not None else watch_dir_configured()
    if not raw:
        raise ValueError("WATCH_DIR unset")
    try:
        root = assert_path_outside_repo(raw, label="WATCH_DIR")
    except PathSafetyError as exc:
        raise WatchConfigError(str(exc)) from exc
    if not root.is_dir():
        raise WatchConfigError(
            f"WATCH_DIR does not exist or is not a directory: {root}"
        )
    # Writable check — try creating a probe only under an existing root.
    probe = root / ".english_bot_watch_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise WatchConfigError(
            f"WATCH_DIR is not writable: {root} ({exc})"
        ) from exc
    return root


def inbox_path(root: Path, user_id: int) -> Path:
    return root / "inbox" / str(user_id)


def outbox_path(root: Path, user_id: int) -> Path:
    return root / "outbox" / str(user_id)


def processed_path(root: Path, user_id: int) -> Path:
    return root / "processed" / str(user_id)


def failed_path(root: Path, user_id: int) -> Path:
    return root / "failed" / str(user_id)


def ensure_user_layout(root: Path, user_id: int) -> None:
    """Create per-user inbox (with tool folders), outbox, processed, failed."""
    inbox = inbox_path(root, user_id)
    inbox.mkdir(parents=True, exist_ok=True)
    for tool in TOOL_FOLDERS:
        (inbox / tool).mkdir(parents=True, exist_ok=True)
    outbox_path(root, user_id).mkdir(parents=True, exist_ok=True)
    processed_path(root, user_id).mkdir(parents=True, exist_ok=True)
    failed_path(root, user_id).mkdir(parents=True, exist_ok=True)


def list_registered_user_ids() -> list[int]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id
              FROM approved_onboarded_users
             ORDER BY telegram_user_id
            """
        ).fetchall()
    return [int(r["telegram_user_id"]) for r in rows]


def ensure_all_user_layouts(root: Path) -> None:
    for uid in list_registered_user_ids():
        ensure_user_layout(root, uid)


def _cell(row: dict[str, str | None], key: str) -> str:
    raw = row.get(key)
    if raw is None:
        return ""
    return str(raw).strip()


def existing_chunk_norms(user_id: int) -> set[str]:
    """Normalised chunk keys already owned by this user (dedupe / re-import)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT chunk FROM chunks WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()
    return {normalize_for_match(str(r["chunk"])) for r in rows if r["chunk"]}


def _existing_chunk_norms(user_id: int) -> set[str]:
    return existing_chunk_norms(user_id)


def parse_csv_text(
    text: str,
) -> tuple[list[str], list[dict[str, str | None]]]:
    """Parse CSV text into headers + row dicts. Shared by folder and Telegram."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        return [], []
    headers = [h for h in reader.fieldnames if h is not None]
    rows = list(reader)
    return headers, rows


def parse_csv_bytes(
    data: bytes,
) -> tuple[list[str], list[dict[str, str | None]]]:
    """Decode UTF-8 (with BOM) and parse. Raises UnicodeDecodeError."""
    return parse_csv_text(data.decode("utf-8-sig"))


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str | None]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return parse_csv_text(fh.read())


def import_csv_rows(
    headers: Sequence[str],
    rows: Sequence[dict[str, str | None]],
    *,
    user_id: int,
    tool: str,
    filename: str,
    now: datetime,
) -> FileImportResult:
    """Map, validate, dedupe, and insert. No filesystem side effects.

    Used by both the watched-folder path and Telegram document upload.
    """
    mapping = map_headers(headers)
    csv_format = classify_csv_format(headers)
    if mapping is None:
        logger.warning(
            "watch import failed_headers user_id=%s file=%s headers=%s",
            user_id,
            filename,
            list(headers),
        )
        return FileImportResult(
            filename=filename,
            status="failed_headers",
            headers_seen=tuple(headers),
            source_tool=tool,
            csv_format=csv_format,
        )

    existing = _existing_chunk_norms(user_id)
    # Batches keyed by source marker (per-row material → distinct Anki tags).
    batches: dict[str, list[dict[str, str]]] = {}
    imported = 0
    duplicates = 0
    invalid = 0
    is_slang = mapping.format == "slang"
    for row in rows:
        chunk = _cell(row, mapping.chunk)
        sentence = _cell(row, mapping.full_sentence)
        meaning = _cell(row, mapping.meaning)
        if not chunk:
            continue
        if not sentence or not meaning:
            invalid += 1
            continue
        chunk_norm = normalize_for_match(chunk)
        if not chunk_norm:
            invalid += 1
            continue
        if chunk_norm not in normalize_for_match(sentence):
            invalid += 1
            continue
        if chunk_norm in existing:
            duplicates += 1
            continue
        existing.add(chunk_norm)
        if is_slang:
            phonetic = (
                _cell(row, mapping.phonetic) if mapping.phonetic else ""
            )
            source = "slang"
            meaning_out = format_meaning(meaning, phonetic or None)
        else:
            mat = (
                _cell(row, mapping.material) if mapping.material else ""
            ) or "untitled"
            source = source_marker(tool, mat)
            meaning_out = meaning
        batches.setdefault(source, []).append(
            {
                "chunk": chunk,
                "full_sentence": sentence,
                "meaning": meaning_out,
            }
        )
        imported += 1

    if batches:
        with connection() as conn:
            with conn.transaction():
                for source, items in batches.items():
                    insert_chunks(
                        conn,
                        user_id,
                        source=source,
                        track=None,
                        chunks=items,
                    )

    due_day = instant_date(now)
    due = count_due_chunks(user_id, now=due_day)
    first_source = next(
        iter(batches),
        "slang" if is_slang else source_marker(tool, "untitled"),
    )
    logger.info(
        "watch import ok user_id=%s file=%s imported=%s duplicates=%s "
        "invalid=%s due=%s source=%s",
        user_id,
        filename,
        imported,
        duplicates,
        invalid,
        due,
        first_source,
    )
    return FileImportResult(
        filename=filename,
        status="imported",
        imported=imported,
        duplicates=duplicates,
        invalid=invalid,
        due_after=due,
        source_tool="slang" if is_slang else tool,
        headers_seen=tuple(headers),
        csv_format=csv_format,
    )


def parse_slang_chunk_items(
    headers: Sequence[str],
    rows: Sequence[dict[str, str | None]],
) -> tuple[list[dict[str, str]], int]:
    """Validate slang rows → chunk dicts. Returns (items, invalid_count)."""
    mapping = map_headers(headers)
    if mapping is None or mapping.format != "slang":
        raise ValueError("not a slang header map")
    items: list[dict[str, str]] = []
    invalid = 0
    for row in rows:
        chunk = _cell(row, mapping.chunk)
        sentence = _cell(row, mapping.full_sentence)
        meaning = _cell(row, mapping.meaning)
        if not chunk:
            continue
        if not sentence or not meaning:
            invalid += 1
            continue
        chunk_norm = normalize_for_match(chunk)
        if not chunk_norm:
            invalid += 1
            continue
        if chunk_norm not in normalize_for_match(sentence):
            invalid += 1
            continue
        phonetic = _cell(row, mapping.phonetic) if mapping.phonetic else ""
        items.append(
            {
                "chunk": chunk,
                "full_sentence": sentence,
                "meaning": format_meaning(meaning, phonetic or None),
            }
        )
    return items, invalid


def import_csv_bytes(
    data: bytes,
    *,
    user_id: int,
    filename: str,
    now: datetime,
    tool: str | None = None,
) -> FileImportResult:
    """Import CSV bytes in memory (Telegram path). Never writes the upload."""
    headers, rows = parse_csv_bytes(data)
    resolved = tool if tool is not None else detect_tool_from_headers(headers)
    # Telegram: unrecognised / ambiguous headers are rejected (S24).
    if tool is None and classify_csv_format(headers) is None:
        return FileImportResult(
            filename=filename,
            status="failed_headers",
            headers_seen=tuple(headers),
            source_tool=resolved,
            csv_format=None,
        )
    return import_csv_rows(
        headers,
        rows,
        user_id=user_id,
        tool=resolved if resolved != "slang" else "csv",
        filename=filename,
        now=now,
    )


def process_csv_file(
    path: Path,
    *,
    user_id: int,
    tool: str,
    root: Path,
    now: datetime,
) -> FileImportResult:
    """Import one stable CSV from disk. Caller must have checked ``is_stable``."""
    filename = path.name
    headers, rows = _read_csv_rows(path)
    # S24a: vocabulary needs an LLM call — never from the scheduler job
    # (known issue #7). Telegram upload is the acceptance path.
    if is_vocabulary_headers(headers):
        logger.warning(
            "watch import refuse_vocabulary user_id=%s file=%s — "
            "Trancy vocabulary CSV (Word,Phonetic,Translation,Date); "
            "send via Telegram instead (folder path does not call the LLM)",
            user_id,
            filename,
        )
        dest = move_collision_safe(
            path, failed_path(root, user_id), now=now
        )
        logger.warning(
            "watch import refuse_vocabulary moved user_id=%s file=%s "
            "moved_to=%s",
            user_id,
            filename,
            dest.name,
        )
        return FileImportResult(
            filename=filename,
            status="refused_vocabulary",
            headers_seen=tuple(headers),
            source_tool=tool,
            csv_format="vocabulary",
        )

    result = import_csv_rows(
        headers,
        rows,
        user_id=user_id,
        tool=tool,
        filename=filename,
        now=now,
    )
    if result.status == "failed_headers":
        dest = move_collision_safe(
            path, failed_path(root, user_id), now=now
        )
        logger.warning(
            "watch import failed_headers moved user_id=%s file=%s moved_to=%s",
            user_id,
            filename,
            dest.name,
        )
        return result

    move_collision_safe(path, processed_path(root, user_id), now=now)
    return result


def parse_vocabulary_seed_items(
    headers: Sequence[str],
    rows: Sequence[dict[str, str | None]],
) -> tuple[list[dict[str, str]], int]:
    """Parse Trancy vocabulary rows → seeds without sentences.

    Returns ``(seeds, empty_or_bad_count)``. ``Date`` is ignored. Meaning
    keeps the full Translation text (semicolon-separated senses intact).
    Phonetic is appended via ``format_meaning``. Within-file duplicates are
    not collapsed here — callers dedupe before the LLM.
    """
    if not is_vocabulary_headers(headers):
        raise ValueError("not a vocabulary header map")
    word_h = _header_by_norm(headers, "word")
    meaning_h = _header_by_norm(headers, "translation")
    phonetic_h = _header_by_norm(headers, "phonetic")
    if word_h is None or meaning_h is None:
        raise ValueError("vocabulary headers missing word/translation")
    seeds: list[dict[str, str]] = []
    skipped = 0
    for row in rows:
        chunk = _cell(row, word_h)
        meaning = _cell(row, meaning_h)
        if not chunk:
            continue
        if not meaning:
            skipped += 1
            continue
        chunk_norm = normalize_for_match(chunk)
        if not chunk_norm:
            skipped += 1
            continue
        phonetic = _cell(row, phonetic_h) if phonetic_h else ""
        seeds.append(
            {
                "chunk": chunk,
                "meaning": format_meaning(meaning, phonetic or None),
            }
        )
    return seeds, skipped


def _iter_user_csv_files(inbox: Path) -> list[tuple[Path, str]]:
    """Return (path, tool) for CSVs in the user inbox and known tool folders."""
    found: list[tuple[Path, str]] = []
    if not inbox.is_dir():
        return found
    for path in sorted(inbox.iterdir()):
        if path.is_file() and path.suffix.casefold() == ".csv":
            found.append((path, "csv"))
        elif path.is_dir():
            tool = tool_from_parent(path.name)
            if tool == "csv" and path.name.casefold() not in _TOOL_ALIASES:
                # Unknown subfolder — skip (do not scan arbitrary trees).
                continue
            for child in sorted(path.iterdir()):
                if child.is_file() and child.suffix.casefold() == ".csv":
                    found.append((child, tool))
    return found


def scan_user_inbox(
    root: Path,
    user_id: int,
    *,
    now: datetime | None = None,
) -> UserScanResult:
    """Scan one user's inbox. Does not send Telegram messages."""
    instant = now or datetime.now(timezone.utc)
    ensure_user_layout(root, user_id)
    result = UserScanResult(user_id=user_id)
    for path, tool in _iter_user_csv_files(inbox_path(root, user_id)):
        if not is_stable(path, now=instant):
            result.settling += 1
            logger.info(
                "watch import skip_young user_id=%s file=%s",
                user_id,
                path.name,
            )
            continue
        try:
            file_result = process_csv_file(
                path,
                user_id=user_id,
                tool=tool,
                root=root,
                now=instant,
            )
        except Exception:
            logger.exception(
                "watch import error user_id=%s file=%s",
                user_id,
                path.name,
            )
            continue
        result.files.append(file_result)
    return result


def collect_root_orphans(root: Path) -> list[str]:
    """Filenames sitting in inbox/ root (never attribute). Leave in place."""
    inbox_root = root / "inbox"
    if not inbox_root.is_dir():
        return []
    orphans: list[str] = []
    for path in sorted(inbox_root.iterdir()):
        if path.is_file() and path.suffix.casefold() == ".csv":
            orphans.append(path.name)
    return orphans


def warn_root_orphans(names: Sequence[str]) -> list[str]:
    """Log WARNING once per filename (module set). Return newly warned names."""
    newly: list[str] = []
    for name in names:
        if name in _warned_orphan_names:
            continue
        _warned_orphan_names.add(name)
        newly.append(name)
        logger.warning(
            "watch import orphan inbox root file=%s — move into "
            "inbox/<telegram_user_id>/ (never auto-attributed)",
            name,
        )
    return newly


def write_anki_outbox(
    user_id: int,
    tsv_bytes: bytes,
    filename: str,
    *,
    now: datetime | None = None,
) -> Path | None:
    """Write Anki TSV to outbox. Returns path or None if unset/failed.

    Failures are logged; callers must still send Telegram and mark exported.
    """
    raw = watch_dir_configured()
    if not raw:
        return None
    try:
        root = resolve_watch_root(raw)
    except (WatchConfigError, ValueError) as exc:
        logger.warning(
            "anki outbox skip user_id=%s reason=watch_dir (%s)",
            user_id,
            exc,
        )
        return None
    try:
        ensure_user_layout(root, user_id)
        dest_dir = outbox_path(root, user_id)
        instant = now or datetime.now(timezone.utc)
        dest = collision_safe_dest(dest_dir, filename, now=instant)
        dest.write_bytes(tsv_bytes)
        logger.info(
            "anki outbox wrote user_id=%s path=%s bytes=%s",
            user_id,
            dest.name,
            len(tsv_bytes),
        )
        return dest
    except OSError as exc:
        logger.warning(
            "anki outbox write failed user_id=%s filename=%s err=%s",
            user_id,
            filename,
            exc,
        )
        return None


def paths_for_user_display(user_id: int) -> dict[str, str] | None:
    """Absolute inbox / tool paths for /import and /settings, or None if unset."""
    raw = watch_dir_configured()
    if not raw:
        return None
    try:
        root = resolve_watch_root(raw)
    except (WatchConfigError, ValueError):
        return None
    ensure_user_layout(root, user_id)
    inbox = inbox_path(root, user_id)
    return {
        "inbox": str(inbox),
        "trancy": str(inbox / "trancy"),
        "language_reactor": str(inbox / "language_reactor"),
        "outbox": str(outbox_path(root, user_id)),
    }
