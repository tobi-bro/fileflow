"""
FileFlow Core Engine.
Provides shared scanning, classification, rules, preview planning, safe organization,
undo, and logging services.
"""

from fileflow.core.classifier import FileClassifier, get_default_category_definitions
from fileflow.core.logger import get_logger, setup_logger
from fileflow.core.models import (
    CategoryDefinition,
    CollisionPolicy,
    JobRecord,
    OperationResult,
    OperationStatus,
    PlannedOperation,
    PreviewPlan,
    Rule,
    RuleDestinationStrategy,
    ScannedFile,
    UndoPlannedOperation,
    UndoPreview,
)
from fileflow.core.organizer import OrganizationExecutionCancelled, SafeFileOrganizer
from fileflow.core.planner import OrganizationPlanner
from fileflow.core.rules import RuleEngine, get_default_presets
from fileflow.core.safety import (
    generate_unique_filename,
    is_path_traversal,
    is_system_or_root_path,
    validate_operation_safety,
)
from fileflow.core.scanner import FileScanner, is_windows_hidden
from fileflow.core.undo import JobHistoryManager, UndoManager

__all__ = [
    # Classifier
    "FileClassifier",
    "get_default_category_definitions",
    # Scanner
    "FileScanner",
    "is_windows_hidden",
    # Rules
    "RuleEngine",
    "get_default_presets",
    # Planner
    "OrganizationPlanner",
    # Organizer
    "SafeFileOrganizer",
    "OrganizationExecutionCancelled",
    # Safety
    "validate_operation_safety",
    "generate_unique_filename",
    "is_system_or_root_path",
    "is_path_traversal",
    # Undo & History
    "JobHistoryManager",
    "UndoManager",
    # Logger
    "setup_logger",
    "get_logger",
    # Models
    "CollisionPolicy",
    "OperationStatus",
    "RuleDestinationStrategy",
    "CategoryDefinition",
    "ScannedFile",
    "Rule",
    "PlannedOperation",
    "PreviewPlan",
    "OperationResult",
    "JobRecord",
    "UndoPlannedOperation",
    "UndoPreview",
]
