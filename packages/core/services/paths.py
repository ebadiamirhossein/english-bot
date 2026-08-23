"""Filesystem path helpers (PRD §10 — refuse private data under the repo).

Python equivalent of ``assert_path_outside_repo`` in ``scripts/backup.sh``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class PathSafetyError(ValueError):
    """Raised when a configured path is inside the git repository."""


def repo_root() -> Path:
    """Return the repository root.

    packages/core/services/paths.py → services → core → packages → root.
    Left at parents[2] after the W1 move this returned ``packages/`` and
    every path under the repo but outside ``packages/`` would have been
    accepted as a WATCH_DIR. The existing test derives its "inside" path
    from this same function, so it could not have caught that.
    """
    return Path(__file__).resolve().parents[3]


def assert_path_outside_repo(path: Path | str, *, label: str) -> Path:
    """Resolve ``path`` and refuse if it lies under the git repo.

    The path need not exist yet; its parent must. Matches backup.sh behaviour.
    """
    target = Path(path).expanduser()
    root = repo_root().resolve()
    if target.exists():
        abs_path = target.resolve()
    else:
        parent = target.parent
        if not parent.is_dir():
            raise PathSafetyError(
                f"{label} parent does not exist: {parent}"
            )
        abs_path = (parent.resolve() / target.name)
    # Trailing slash comparison so /repo-extra is not treated as under /repo.
    if str(abs_path).startswith(str(root) + "/") or abs_path == root:
        raise PathSafetyError(
            f"{label} ({abs_path}) is inside the git repo ({root}). "
            "Refuse to store private content that could be committed (PRD §10)."
        )
    return abs_path


def collision_safe_dest(directory: Path, filename: str, *, now: datetime | None = None) -> Path:
    """Return ``directory/filename``, or a stamped name if that path exists.

    Stamp format: ``stem_YYYYMMDDTHHMMSSZ.suffix`` (UTC). Never overwrites.
    """
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / filename
    if not dest.exists():
        return dest
    instant = now or datetime.now(timezone.utc)
    stamp = instant.strftime("%Y%m%dT%H%M%SZ")
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = directory / f"{stem}_{stamp}{suffix}"
    # Extremely unlikely second collision in the same second — keep ticking.
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{stamp}_{n}{suffix}"
        n += 1
    return candidate


def move_collision_safe(
    src: Path,
    dest_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Move ``src`` into ``dest_dir`` without overwriting an existing file."""
    dest = collision_safe_dest(dest_dir, src.name, now=now)
    src.rename(dest)
    return dest
