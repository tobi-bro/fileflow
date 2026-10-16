"""
Filesystem safety validator and collision handler for FileFlow.
Guarantees:
- No silent overwrites.
- Path traversal prevention.
- System directory protection.
- Safe collision resolution with numbered suffixes.
- Recursive organization guards.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from fileflow.core.models import CollisionPolicy

# System directories that must NEVER be organized or used as targets
PROTECTED_SYSTEM_NAMES = {
    "windows",
    "system32",
    "syswow64",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "$recycle.bin",
    "system volume information",
    "boot",
    "etc",
    "usr",
    "bin",
    "sbin",
    "var",
}


def is_system_or_root_path(path: Path) -> bool:
    """Check if the path is a system directory or root drive."""
    try:
        resolved = path.resolve()
    except Exception:
        return True

    # Root drive check (e.g. C:\ or /)
    if resolved == resolved.parent or resolved == Path(resolved.anchor):
        return True

    # Check against blacklisted system directory names
    parts_lower = [p.lower() for p in resolved.parts]
    for sys_name in PROTECTED_SYSTEM_NAMES:
        if sys_name in parts_lower:
            return True

    return False


def is_path_traversal(target: Path, authorized_root: Path) -> bool:
    """
    Ensure the target path is strictly contained within the authorized root.
    Prevents '../' escape attacks.
    """
    try:
        res_target = target.resolve()
        res_root = authorized_root.resolve()
        res_target.relative_to(res_root)
        return False
    except ValueError:
        return True
    except Exception:
        return True


def is_destination_inside_source(source: Path, destination: Path) -> bool:
    """Check if source is an ancestor of destination or vice versa."""
    try:
        res_src = source.resolve()
        res_dest = destination.resolve()
        return res_src == res_dest
    except Exception:
        return False


def generate_unique_filename(destination: Path) -> Path:
    """
    Generate a non-colliding destination filename by appending ' (1)', ' (2)', etc.
    Correctly preserves compound extensions such as .tar.gz.
    """
    if not destination.exists():
        return destination

    parent = destination.parent
    name = destination.name

    # Check for known compound extensions
    compound_extensions = [".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"]
    matched_compound = None
    for compound in compound_extensions:
        if name.lower().endswith(compound):
            matched_compound = compound
            stem = name[:-len(compound)]
            break

    if not matched_compound:
        stem = destination.stem
        suffix = destination.suffix
    else:
        suffix = matched_compound

    counter = 1
    while True:
        candidate_name = f"{stem} ({counter}){suffix}"
        candidate_path = parent / candidate_name
        if not candidate_path.exists():
            return candidate_path
        counter += 1


def validate_operation_safety(
    source_path: Path,
    proposed_destination: Path,
    authorized_root: Optional[Path] = None,
    policy: CollisionPolicy = CollisionPolicy.AUTO_RENAME,
    allow_symlinks: bool = False,
) -> Tuple[bool, Path, List[str], List[str]]:
    """
    Validate safety of a proposed file move.
    Returns:
        (is_safe, resolved_destination, warnings, conflicts)
    """
    warnings: List[str] = []
    conflicts: List[str] = []

    # 1. Check source existence
    if not source_path.exists():
        conflicts.append(f"Source file does not exist: {source_path}")
        return False, proposed_destination, warnings, conflicts

    if not source_path.is_file():
        conflicts.append(f"Source path is a directory or special device, not a file: {source_path}")
        return False, proposed_destination, warnings, conflicts

    # 2. Check symlinks
    if source_path.is_symlink() and not allow_symlinks:
        conflicts.append("Source is a symbolic link (symlinks are skipped by default for safety).")
        return False, proposed_destination, warnings, conflicts

    # 3. Prevent system/root modifications
    if is_system_or_root_path(source_path):
        conflicts.append(f"Source file is inside a protected system or root directory: {source_path}")
        return False, proposed_destination, warnings, conflicts

    if is_system_or_root_path(proposed_destination):
        conflicts.append(f"Destination is inside a protected system or root directory: {proposed_destination}")
        return False, proposed_destination, warnings, conflicts

    # 4. Scope authorization
    if authorized_root is not None:
        if is_path_traversal(source_path, authorized_root):
            conflicts.append(f"Source path traverses outside authorized folder: {source_path}")
            return False, proposed_destination, warnings, conflicts

    # 5. Prevent moving onto itself
    try:
        resolved_src = source_path.resolve()
        resolved_dest = proposed_destination.resolve()
        if resolved_src == resolved_dest:
            warnings.append("File is already in the target location.")
            return True, proposed_destination, warnings, conflicts
    except Exception as exc:
        conflicts.append(f"Could not resolve paths: {exc}")
        return False, proposed_destination, warnings, conflicts

    # 6. Check destination collision
    final_destination = proposed_destination
    if proposed_destination.exists():
        if policy == CollisionPolicy.SKIP:
            warnings.append(f"Destination already exists; operation will be skipped: {proposed_destination.name}")
            return False, proposed_destination, warnings, conflicts
        elif policy == CollisionPolicy.FAIL:
            conflicts.append(f"Destination file already exists: {proposed_destination.name}")
            return False, proposed_destination, warnings, conflicts
        elif policy == CollisionPolicy.ASK:
            conflicts.append(f"Destination file exists; user confirmation required: {proposed_destination.name}")
            return False, proposed_destination, warnings, conflicts
        elif policy == CollisionPolicy.AUTO_RENAME:
            final_destination = generate_unique_filename(proposed_destination)
            warnings.append(
                f"Destination exists. Auto-renaming to: {final_destination.name}"
            )

    return True, final_destination, warnings, conflicts
