"""
Filesystem scanner for FileFlow.
Discovers and profiles files within user-authorized directories safely.
"""

from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from fileflow.core.classifier import FileClassifier
from fileflow.core.logger import get_logger
from fileflow.core.models import ScannedFile
from fileflow.core.safety import is_system_or_root_path

logger = get_logger("fileflow.scanner")


def is_windows_hidden(path: Path) -> bool:
    """Check if file is marked hidden via dot-prefix or Windows file attributes."""
    if path.name.startswith("."):
        return True
    try:
        if os.name == "nt":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            # 0x02 is FILE_ATTRIBUTE_HIDDEN
            if attrs != -1 and bool(attrs & 2):
                return True
    except Exception:
        pass
    return False


class FileScanner:
    """
    Safely scans a directory and extracts file metadata without modifying anything.
    """

    def __init__(self, classifier: Optional[FileClassifier] = None):
        self.classifier = classifier or FileClassifier()

    def scan(
        self,
        directory: Path,
        recursive: bool = False,
        include_hidden: bool = False,
        follow_symlinks: bool = False,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Tuple[List[ScannedFile], List[str]]:
        """
        Scan target directory for files.
        Returns:
            Tuple[List[ScannedFile], List[error_messages]]
        """
        scanned_files: List[ScannedFile] = []
        errors: List[str] = []

        try:
            target_dir = directory.resolve()
        except Exception as exc:
            errors.append(f"Invalid directory path: {exc}")
            return scanned_files, errors

        if not target_dir.exists():
            errors.append(f"Directory does not exist: {target_dir}")
            return scanned_files, errors

        if not target_dir.is_dir():
            errors.append(f"Path is not a directory: {target_dir}")
            return scanned_files, errors

        if is_system_or_root_path(target_dir):
            errors.append(f"Scanning protected system or root directory is prohibited: {target_dir}")
            return scanned_files, errors

        logger.info("Starting scan of %s (recursive=%s, include_hidden=%s)", target_dir, recursive, include_hidden)

        iterator = target_dir.rglob("*") if recursive else target_dir.glob("*")
        scanned_count = 0

        for item in iterator:
            try:
                # Disallow symlinks unless explicitly authorized
                if item.is_symlink() and not follow_symlinks:
                    continue

                if not item.is_file():
                    continue

                # Hidden file check
                is_hidden = is_windows_hidden(item)
                if is_hidden and not include_hidden:
                    continue

                try:
                    st = item.stat()
                except (PermissionError, FileNotFoundError, OSError) as exc:
                    msg = f"Cannot read file properties for {item.name}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)
                    continue

                ext = self.classifier.extract_extension(item)
                category, is_risky, is_unknown = self.classifier.classify(item)

                created_ts = datetime.fromtimestamp(st.st_ctime)
                modified_ts = datetime.fromtimestamp(st.st_mtime)

                scanned_file = ScannedFile(
                    path=item,
                    name=item.name,
                    stem=item.stem,
                    extension=ext,
                    size_bytes=st.st_size,
                    created_at=created_ts,
                    modified_at=modified_ts,
                    is_hidden=is_hidden,
                    is_symlink=item.is_symlink(),
                    category=category,
                    is_risky=is_risky,
                    is_unknown=is_unknown,
                )

                scanned_files.append(scanned_file)
                scanned_count += 1

                if progress_callback:
                    progress_callback(scanned_count, item.name)

            except Exception as exc:
                msg = f"Unexpected error scanning {item}: {exc}"
                logger.error(msg)
                errors.append(msg)

        logger.info("Scan completed. Found %d files, encountered %d issues.", len(scanned_files), len(errors))
        return scanned_files, errors
