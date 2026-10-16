"""
Dry-run organization planner for FileFlow.
Generates a complete, verified execution plan before touching any files on disk.
Guarantees NO filesystem modifications occur during plan generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fileflow.core.classifier import FileClassifier
from fileflow.core.logger import get_logger
from fileflow.core.models import (
    CollisionPolicy,
    OperationStatus,
    PlannedOperation,
    PreviewPlan,
    Rule,
    ScannedFile,
)
from fileflow.core.rules import RuleEngine
from fileflow.core.safety import (
    generate_unique_filename,
    validate_operation_safety,
)

logger = get_logger("fileflow.planner")


class OrganizationPlanner:
    """
    Creates a dry-run PreviewPlan mapping each scanned file to a proposed destination.
    Simulates collision resolution without creating any directory or modifying files.
    """

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        classifier: Optional[FileClassifier] = None,
    ):
        self.classifier = classifier or FileClassifier()
        self.rule_engine = rule_engine or RuleEngine(classifier=self.classifier)

    def create_plan(
        self,
        source_folder: Path,
        scanned_files: List[ScannedFile],
        target_root_folder: Optional[Path] = None,
        default_policy: CollisionPolicy = CollisionPolicy.AUTO_RENAME,
    ) -> PreviewPlan:
        """
        Generate dry-run plan.
        If target_root_folder is None, organizes in-place inside source_folder.
        """
        target_root = (target_root_folder or source_folder).resolve()
        source_folder_resolved = source_folder.resolve()

        plan = PreviewPlan(
            source_folder=source_folder_resolved,
            target_folder=target_root,
            total_files_scanned=len(scanned_files),
        )

        logger.info(
            "Creating dry-run preview plan for %d files from '%s' to '%s'",
            len(scanned_files),
            source_folder_resolved,
            target_root,
        )

        # Track planned destination paths in memory to avoid intra-plan collisions
        reserved_destinations: Set[Path] = set()

        for scanned_file in scanned_files:
            winning_rule, rel_subfolder, explanation = self.rule_engine.evaluate(scanned_file)

            proposed_dir = target_root / rel_subfolder
            proposed_dest = proposed_dir / scanned_file.name

            rule_id = winning_rule.id if winning_rule else None
            rule_name = winning_rule.name if winning_rule else "Default Category"
            rule_policy = winning_rule.conflict_policy if winning_rule else default_policy

            is_safe, resolved_dest, warnings, conflicts = validate_operation_safety(
                source_path=scanned_file.path,
                proposed_destination=proposed_dest,
                authorized_root=source_folder_resolved if target_root == source_folder_resolved else None,
                policy=rule_policy,
            )

            # Intra-plan collision check (e.g. if two files map to the same name)
            if resolved_dest in reserved_destinations:
                if rule_policy == CollisionPolicy.AUTO_RENAME:
                    # Allocate safe virtual name
                    counter = 1
                    stem = resolved_dest.stem
                    suffix = resolved_dest.suffix
                    candidate = resolved_dest
                    while candidate in reserved_destinations or candidate.exists():
                        candidate = proposed_dir / f"{stem} ({counter}){suffix}"
                        counter += 1
                    resolved_dest = candidate
                    warnings.append(f"Multiple files share destination name. Auto-renamed to: {resolved_dest.name}")
                elif rule_policy == CollisionPolicy.SKIP:
                    warnings.append("Another file in this job shares the destination name; skipped.")
                    is_safe = False
                elif rule_policy == CollisionPolicy.FAIL:
                    conflicts.append("Destination name conflict with another file in this job.")
                    is_safe = False

            reserved_destinations.add(resolved_dest)

            # Determine initial status
            status = OperationStatus.PENDING
            if conflicts:
                status = OperationStatus.CONFLICT
            elif warnings:
                status = OperationStatus.WARNING

            # Flag risky files (executables/scripts) in warnings
            if scanned_file.is_risky:
                warnings.append("Executable/script file: FileFlow will organize safely without executing.")

            planned_op = PlannedOperation(
                source_path=scanned_file.path,
                proposed_destination=proposed_dest,
                category=scanned_file.category,
                matched_rule_id=rule_id,
                matched_rule_name=rule_name,
                rule_explanation=explanation,
                file_size=scanned_file.size_bytes,
                status=status,
                warnings=warnings,
                conflicts=conflicts,
                is_selected=len(conflicts) == 0,  # Auto-select safe files
                resolved_destination=resolved_dest if is_safe else None,
            )

            plan.operations.append(planned_op)
            if warnings:
                plan.warnings_count += 1
            if conflicts:
                plan.conflicts_count += 1

        logger.info(
            "Plan generated: %d operations, %d warnings, %d conflicts",
            len(plan.operations),
            plan.warnings_count,
            plan.conflicts_count,
        )

        return plan

    def select_all(self, plan: PreviewPlan, select: bool = True) -> None:
        """Select or deselect all operations in the plan (ignoring hard conflicts)."""
        for op in plan.operations:
            if op.conflicts:
                op.is_selected = False
            else:
                op.is_selected = select

    def toggle_selection(self, plan: PreviewPlan, operation_id: str) -> bool:
        """Toggle selection state of a specific operation."""
        for op in plan.operations:
            if op.id == operation_id:
                if op.conflicts and not op.is_selected:
                    # Do not allow selecting unresolved hard conflicts
                    return False
                op.is_selected = not op.is_selected
                return True
        return False
