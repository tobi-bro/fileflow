"""
Safe file organizer for FileFlow.
Executes planned operations with preflight revalidation, cancellation support,
progress reporting, and full audit logging.
"""

from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from fileflow.core.logger import get_logger
from fileflow.core.models import (
    CollisionPolicy,
    JobRecord,
    OperationResult,
    OperationStatus,
    PlannedOperation,
    PreviewPlan,
)
from fileflow.core.safety import (
    generate_unique_filename,
    validate_operation_safety,
)

logger = get_logger("fileflow.organizer")


class OrganizationExecutionCancelled(Exception):
    """Raised when an organization job is cancelled by user request."""
    pass


class SafeFileOrganizer:
    """
    Executes preview plans safely using Python's standard library.
    Never uses shell commands.
    """

    def __init__(self):
        self._cancel_requested = threading.Event()

    def request_cancellation(self) -> None:
        """Signal ongoing organization to halt after current file operation."""
        self._cancel_requested.set()
        logger.warning("Cancellation requested for file organization.")

    def reset_cancellation(self) -> None:
        """Clear cancellation state for next run."""
        self._cancel_requested.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()

    def execute_plan(
        self,
        plan: PreviewPlan,
        progress_callback: Optional[Callable[[int, int, PlannedOperation, OperationResult], None]] = None,
    ) -> JobRecord:
        """
        Execute selected operations in the PreviewPlan.
        Revalidates each operation immediately before moving.
        """
        self.reset_cancellation()

        job_record = JobRecord(
            source_folder=plan.source_folder,
            target_folder=plan.target_folder,
            status="running",
            started_at=datetime.now(),
        )

        selected_ops = [op for op in plan.operations if op.is_selected]
        job_record.total_planned = len(selected_ops)

        logger.info(
            "Starting execution of job %s with %d selected operations",
            job_record.job_id,
            len(selected_ops),
        )

        for index, op in enumerate(selected_ops, start=1):
            # Check for cancellation between operations
            if self._cancel_requested.is_set():
                logger.warning("Job %s cancelled at step %d/%d", job_record.job_id, index, len(selected_ops))
                job_record.status = "cancelled"
                break

            result = self._execute_single_operation(op, plan.source_folder)
            job_record.operations.append(result)

            if result.status == OperationStatus.SUCCESS:
                job_record.total_executed += 1
            elif result.status == OperationStatus.SKIPPED:
                job_record.total_skipped += 1
            else:
                job_record.total_failed += 1

            if progress_callback:
                try:
                    progress_callback(index, len(selected_ops), op, result)
                except Exception as exc:
                    logger.warning("Progress callback error: %s", exc)

        job_record.completed_at = datetime.now()
        if job_record.status != "cancelled":
            if job_record.total_failed == 0:
                job_record.status = "completed"
            elif job_record.total_executed > 0:
                job_record.status = "partial_failure"
            else:
                job_record.status = "failed"

        logger.info(
            "Job %s finished with status '%s'. (Executed: %d, Skipped: %d, Failed: %d)",
            job_record.job_id,
            job_record.status,
            job_record.total_executed,
            job_record.total_skipped,
            job_record.total_failed,
        )

        return job_record

    def _execute_single_operation(
        self,
        op: PlannedOperation,
        authorized_root: Path,
    ) -> OperationResult:
        """Execute and re-validate an individual file move."""
        source = op.source_path
        target = op.resolved_destination or op.proposed_destination

        # 1. Immediate preflight check: does source still exist on disk?
        if not source.exists():
            msg = f"Source file no longer exists at: {source}"
            logger.error(msg)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=None,
                status=OperationStatus.FAILED,
                error_message=msg,
            )

        # 2. Re-validate safety immediately
        is_safe, final_target, warnings, conflicts = validate_operation_safety(
            source_path=source,
            proposed_destination=target,
            authorized_root=authorized_root if target.is_relative_to(authorized_root) else None,
            policy=CollisionPolicy.AUTO_RENAME,
        )

        if not is_safe or conflicts:
            err = "; ".join(conflicts) if conflicts else "Safety validation failed."
            logger.error("Preflight failure for %s -> %s: %s", source, target, err)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=None,
                status=OperationStatus.FAILED,
                error_message=err,
            )

        # 3. If source and destination resolve to the identical file
        try:
            if source.resolve() == final_target.resolve():
                logger.info("File already at destination: %s", final_target)
                return OperationResult(
                    operation_id=op.id,
                    source_path=source,
                    destination_path=final_target,
                    status=OperationStatus.SKIPPED,
                    error_message="File already in correct destination.",
                )
        except Exception:
            pass

        # 4. Create destination directory if needed
        try:
            final_target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            msg = f"Failed to create target directory '{final_target.parent}': {exc}"
            logger.error(msg)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=final_target,
                status=OperationStatus.FAILED,
                error_message=msg,
            )

        # 5. Move the file using shutil.move (cross-platform, cross-drive support)
        try:
            file_size = source.stat().st_size
            shutil.move(str(source), str(final_target))
            logger.info("Successfully moved '%s' -> '%s'", source.name, final_target)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=final_target,
                status=OperationStatus.SUCCESS,
                bytes_moved=file_size,
            )
        except PermissionError as exc:
            msg = f"Permission denied while moving {source.name}: {exc}"
            logger.error(msg)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=final_target,
                status=OperationStatus.FAILED,
                error_message=msg,
            )
        except OSError as exc:
            msg = f"Filesystem error moving {source.name}: {exc}"
            logger.error(msg)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=final_target,
                status=OperationStatus.FAILED,
                error_message=msg,
            )
        except Exception as exc:
            msg = f"Unexpected failure moving {source.name}: {exc}"
            logger.exception(msg)
            return OperationResult(
                operation_id=op.id,
                source_path=source,
                destination_path=final_target,
                status=OperationStatus.FAILED,
                error_message=msg,
            )
