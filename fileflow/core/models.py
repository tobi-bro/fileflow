"""
Data models and schemas for FileFlow.
Uses Pydantic for validation and serialization.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CollisionPolicy(str, Enum):
    """How to handle existing files at the destination."""
    AUTO_RENAME = "auto_rename"  # e.g. document (1).pdf
    SKIP = "skip"                # Do not move, keep original intact
    FAIL = "fail"                # Fail the operation and report error
    ASK = "ask"                  # Flag for manual user confirmation


class OperationStatus(str, Enum):
    """Status of an individual file operation."""
    PENDING = "pending"
    SELECTED = "selected"
    EXCLUDED = "excluded"
    WARNING = "warning"
    CONFLICT = "conflict"
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNDONE = "undone"


class RuleDestinationStrategy(str, Enum):
    """Strategy for determining destination folder."""
    STATIC_FOLDER = "static_folder"
    CATEGORY_FOLDER = "category_folder"
    DATE_FOLDER = "date_folder"
    TYPE_AND_YEAR = "type_and_year"
    CUSTOM_TEMPLATE = "custom_template"


class CategoryDefinition(BaseModel):
    """Definition of a file category and its associated extensions."""
    name: str
    extensions: List[str]
    destination_folder: str
    is_risky: bool = False
    description: Optional[str] = None

    @field_validator("extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, exts: Any) -> List[str]:
        if isinstance(exts, list):
            res = []
            for ext in exts:
                ext_str = str(ext).strip().lower()
                if ext_str and not ext_str.startswith("."):
                    ext_str = f".{ext_str}"
                if ext_str:
                    res.append(ext_str)
            return sorted(list(set(res)))
        return []


class ScannedFile(BaseModel):
    """Metadata of a file discovered during scanning."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    name: str
    stem: str
    extension: str  # Lowercase, e.g. '.pdf', '.tar.gz', or ''
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    is_hidden: bool = False
    is_symlink: bool = False
    category: str = "Other"
    is_risky: bool = False
    is_unknown: bool = False


class Rule(BaseModel):
    """User-defined or preset organization rule."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    enabled: bool = True
    priority: int = 100  # Lower number = evaluated earlier
    description: Optional[str] = None

    # Matching filters
    extensions: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    filename_patterns: Optional[List[str]] = None  # Globs like 'Screenshot*', '*invoice*'
    min_size_bytes: Optional[int] = None
    max_size_bytes: Optional[int] = None
    modified_before: Optional[datetime] = None
    modified_after: Optional[datetime] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None

    # Destination configuration
    destination_strategy: RuleDestinationStrategy = RuleDestinationStrategy.STATIC_FOLDER
    destination_folder: str = "Organized"
    conflict_policy: CollisionPolicy = CollisionPolicy.AUTO_RENAME

    @field_validator("extensions", mode="before")
    @classmethod
    def normalize_rule_extensions(cls, exts: Any) -> Optional[List[str]]:
        if exts is None:
            return None
        if isinstance(exts, list):
            res = []
            for ext in exts:
                ext_str = str(ext).strip().lower()
                if ext_str and not ext_str.startswith("."):
                    ext_str = f".{ext_str}"
                if ext_str:
                    res.append(ext_str)
            return sorted(list(set(res)))
        return None


class PlannedOperation(BaseModel):
    """A single proposed file move action generated during dry-run preview."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_path: Path
    proposed_destination: Path
    category: str
    matched_rule_id: Optional[str] = None
    matched_rule_name: Optional[str] = None
    rule_explanation: str = ""
    file_size: int = 0
    status: OperationStatus = OperationStatus.PENDING
    warnings: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    is_selected: bool = True
    resolved_destination: Optional[Path] = None


class PreviewPlan(BaseModel):
    """Complete dry-run preview containing all proposed operations."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    source_folder: Path
    target_folder: Path
    total_files_scanned: int = 0
    operations: List[PlannedOperation] = Field(default_factory=list)
    warnings_count: int = 0
    conflicts_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class OperationResult(BaseModel):
    """Outcome of an attempted file operation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    operation_id: str
    source_path: Path
    destination_path: Optional[Path] = None
    status: OperationStatus
    error_message: Optional[str] = None
    bytes_moved: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class JobRecord(BaseModel):
    """Persistent summary record of an organization job."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source_folder: Path
    target_folder: Path
    status: str = "pending"  # pending, running, completed, cancelled, failed, undone
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    total_planned: int = 0
    total_executed: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    is_undone: bool = False
    can_undo: bool = True
    operations: List[OperationResult] = Field(default_factory=list)
    rule_snapshot: Optional[Dict[str, Any]] = None


class UndoPlannedOperation(BaseModel):
    """A proposed reverse operation for an undo plan."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    operation_id: str
    current_path: Path
    restore_path: Path
    can_restore: bool
    reason: Optional[str] = None


class UndoPreview(BaseModel):
    """Dry-run preview before executing an undo operation."""
    job_id: str
    operations: List[UndoPlannedOperation] = Field(default_factory=list)
    safe_count: int = 0
    unsafe_count: int = 0
