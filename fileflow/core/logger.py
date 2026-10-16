"""
Logging configuration for FileFlow.
Provides console and rotating file logging for diagnostic and activity tracking.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_INITIALIZED = False
_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "fileflow",
    log_file: Optional[Path] = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
) -> logging.Logger:
    """
    Configure and retrieve a rotating logger for FileFlow.
    Ensures handlers are attached only to the root 'fileflow' logger to prevent duplication.
    """
    global _LOGGER_INITIALIZED

    base_logger = logging.getLogger("fileflow")
    base_logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not base_logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        base_logger.addHandler(console_handler)

        # Rotating File Handler
        if log_file is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            log_dir = base_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "fileflow.log"
        else:
            log_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            file_handler = RotatingFileHandler(
                filename=str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            base_logger.addHandler(file_handler)
        except Exception as exc:
            base_logger.warning("Could not initialize file log handler at %s: %s", log_file, exc)

    _LOGGER_INITIALIZED = True
    return logging.getLogger(name)


def get_logger(name: str = "fileflow") -> logging.Logger:
    """Retrieve a namespaced child logger under 'fileflow'."""
    base_logger = logging.getLogger("fileflow")
    if not base_logger.handlers:
        setup_logger()
    return logging.getLogger(name)
