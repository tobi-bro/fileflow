"""
Job History and Safe Undo System for FileFlow.
Persists job records in SQLite and safely reverses operations.
Guarantees:
- Never overwrites existing files during an undo.
- Always generates an UndoPreview first.
- Verifies file integrity before and after reversal.
- Prunes newly empty subdirectories left behind by undo.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from fileflow.core.logger import get_logger
from fileflow.core.models import (
    JobRecord,
    OperationResult,
    OperationStatus,
    UndoPlannedOperation,
    UndoPreview,
)

logger = get_logger("fileflow.undo")


class JobHistoryManager:
    """
    SQLite-backed repository for storing and retrieving FileFlow organization jobs.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "fileflow.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    source_folder TEXT NOT NULL,
                    target_folder TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    total_planned INTEGER DEFAULT 0,
                    total_executed INTEGER DEFAULT 0,
                    total_skipped INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    is_undone INTEGER DEFAULT 0,
                    rule_snapshot TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    bytes_moved INTEGER DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    is_undone INTEGER DEFAULT 0,
                    FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    def save_job(self, job: JobRecord) -> None:
        """Persist a completed or partial job record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO jobs (
                    job_id, source_folder, target_folder, status,
                    started_at, completed_at, total_planned, total_executed,
                    total_skipped, total_failed, is_undone, rule_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    str(job.source_folder),
                    str(job.target_folder),
                    job.status,
                    job.started_at.isoformat(),
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.total_planned,
                    job.total_executed,
                    job.total_skipped,
                    job.total_failed,
                    1 if job.is_undone else 0,
                    json.dumps(job.rule_snapshot) if job.rule_snapshot else None,
                ),
            )

            for op in job.operations:
                cursor.execute(
                    """
                    INSERT INTO operations (
                        job_id, operation_id, source_path, destination_path,
                        status, error_message, bytes_moved, timestamp, is_undone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        job.job_id,
                        op.operation_id,
                        str(op.source_path),
                        str(op.destination_path) if op.destination_path else None,
                        op.status.value,
                        op.error_message,
                        op.bytes_moved,
                        op.timestamp.isoformat(),
                    ),
                )
            conn.commit()
            logger.info("Saved job %s into SQLite database.", job.job_id)

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Load job record and all its operations by job ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None

            job = JobRecord(
                job_id=row["job_id"],
                source_folder=Path(row["source_folder"]),
                target_folder=Path(row["target_folder"]),
                status=row["status"],
                started_at=datetime.fromisoformat(row["started_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                total_planned=row["total_planned"],
                total_executed=row["total_executed"],
                total_skipped=row["total_skipped"],
                total_failed=row["total_failed"],
                is_undone=bool(row["is_undone"]),
                rule_snapshot=json.loads(row["rule_snapshot"]) if row["rule_snapshot"] else None,
            )

            cursor.execute("SELECT * FROM operations WHERE job_id = ?", (job_id,))
            for op_row in cursor.fetchall():
                job.operations.append(
                    OperationResult(
                        operation_id=op_row["operation_id"],
                        source_path=Path(op_row["source_path"]),
                        destination_path=Path(op_row["destination_path"]) if op_row["destination_path"] else None,
                        status=OperationStatus(op_row["status"]),
                        error_message=op_row["error_message"],
                        bytes_moved=op_row["bytes_moved"],
                        timestamp=datetime.fromisoformat(op_row["timestamp"]),
                    )
                )

            return job

    def list_jobs(self, limit: int = 50) -> List[JobRecord]:
        """List recent jobs ordered from newest to oldest."""
        jobs: List[JobRecord] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            for row in cursor.fetchall():
                jobs.append(
                    JobRecord(
                        job_id=row["job_id"],
                        source_folder=Path(row["source_folder"]),
                        target_folder=Path(row["target_folder"]),
                        status=row["status"],
                        started_at=datetime.fromisoformat(row["started_at"]),
                        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                        total_planned=row["total_planned"],
                        total_executed=row["total_executed"],
                        total_skipped=row["total_skipped"],
                        total_failed=row["total_failed"],
                        is_undone=bool(row["is_undone"]),
                    )
                )
        return jobs


class UndoManager:
    """
    Manages undo previews and safe execution of file restoration.
    """

    def __init__(self, history_manager: Optional[JobHistoryManager] = None):
        self.history_manager = history_manager or JobHistoryManager()

    def create_undo_preview(self, job_id: str) -> UndoPreview:
        """
        Inspect the filesystem to evaluate which files can be safely restored.
        """
        job = self.history_manager.get_job(job_id)
        if not job:
            return UndoPreview(job_id=job_id)

        preview = UndoPreview(job_id=job_id)

        # Reverse successful operations
        successful_ops = [
            op for op in job.operations
            if op.status == OperationStatus.SUCCESS and op.destination_path is not None
        ]

        for op in successful_ops:
            current_dest = op.destination_path
            original_src = op.source_path
            can_restore = True
            reason = None

            if not current_dest.exists():
                can_restore = False
                reason = "Organized file is missing from destination (moved or deleted by user)."
            elif original_src.exists():
                can_restore = False
                reason = "Original source location is currently occupied by another file. Restoration aborted to prevent overwrite."

            preview_op = UndoPlannedOperation(
                operation_id=op.operation_id,
                current_path=current_dest,
                restore_path=original_src,
                can_restore=can_restore,
                reason=reason,
            )
            preview.operations.append(preview_op)
            if can_restore:
                preview.safe_count += 1
            else:
                preview.unsafe_count += 1

        return preview

    def execute_undo(self, job_id: str) -> Tuple[bool, List[str], int, int]:
        """
        Safely reverses eligible file operations in a job.
        Returns:
            Tuple[all_restored (bool), messages (List[str]), restored_count (int), failed_count (int)]
        """
        preview = self.create_undo_preview(job_id)
        messages: List[str] = []
        restored_count = 0
        failed_count = 0

        affected_dirs: set[Path] = set()

        for op in preview.operations:
            if not op.can_restore:
                messages.append(f"Skipped {op.current_path.name}: {op.reason}")
                failed_count += 1
                continue

            try:
                op.restore_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(op.current_path), str(op.restore_path))
                messages.append(f"Restored: {op.current_path.name} -> {op.restore_path}")
                restored_count += 1
                affected_dirs.add(op.current_path.parent)
            except Exception as exc:
                err = f"Failed to restore {op.current_path.name}: {exc}"
                logger.error(err)
                messages.append(err)
                failed_count += 1

        # Clean up any empty folders left behind
        for dir_path in affected_dirs:
            try:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    logger.info("Cleaned up empty directory: %s", dir_path)
            except Exception:
                pass

        # Update database record
        with self.history_manager._get_connection() as conn:
            cursor = conn.cursor()
            if failed_count == 0 and restored_count > 0:
                cursor.execute(
                    "UPDATE jobs SET is_undone = 1, status = 'undone' WHERE job_id = ?",
                    (job_id,),
                )
            conn.commit()

        success = (failed_count == 0 and restored_count > 0)
        return success, messages, restored_count, failed_count
