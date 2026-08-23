"""Single-instance guard via fcntl.flock (S18).

Kernel releases the lock when the holding process dies, so a stale lock
left by a killed process never blocks the next start forever.
"""

from __future__ import annotations

import atexit
import fcntl
import logging
import os
from pathlib import Path
from types import TracebackType
from typing import IO, Optional, Type

logger = logging.getLogger(__name__)


class InstanceLockError(RuntimeError):
    """Raised when another bot instance already holds the lock."""


class InstanceLock:
    """Exclusive flock on a lock file. Context-manager / explicit release."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fh: IO[str] | None = None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.close()
            raise InstanceLockError(
                f"Another bot instance holds the lock at {self.path}. "
                "Stop the other process before starting again."
            ) from exc
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        self._fh = fh
        atexit.register(self.release)
        logger.info(
            "Instance lock acquired path=%s pid=%s", self.path, os.getpid()
        )

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            logger.exception("Failed to unlock %s", self.path)
        try:
            fh.close()
        except OSError:
            pass
        logger.info("Instance lock released path=%s", self.path)

    def __enter__(self) -> InstanceLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.release()
