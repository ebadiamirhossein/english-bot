"""Process logging setup, shared by every app.

Lifted unchanged from ``apps/bot/main.py::_configure_logging`` at W1:
console plus a rotating file handler under RUNTIME_DIR, with httpx,
httpcore and apscheduler silenced to WARNING. PRD §10: log lines carry
user ids and route names, never message bodies.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


def configure_logging(settings: Any) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = logging.Formatter("%(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def configure_console_logging(settings: Any) -> None:
    """Console handler only, idempotent. For processes systemd already captures.

    ``apps/api`` runs under uvicorn with ``--workers 2``. It must not use
    :func:`configure_logging`, which installs a ``RotatingFileHandler``: two
    worker processes rotating one file is the hazard ``apps/worker`` already
    gives itself a separate log path to avoid.

    It must configure *something*, though, and that is #117. uvicorn attaches
    handlers to the ``uvicorn.*`` loggers and leaves the **root** logger bare, so
    every ``INFO`` record from ``apps.*`` and ``core.*`` propagated to a root
    with no handler and fell through to ``logging.lastResort``, which emits
    ``WARNING`` and above. The API's start-up line was being produced and
    silently dropped, and a deployment step cited it as evidence.

    Idempotent because ``create_app`` is a factory that tests call repeatedly:
    a second call must not add a second handler and double every line.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_english_console", False) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        console._english_console = True  # type: ignore[attr-defined]
        root.addHandler(console)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
