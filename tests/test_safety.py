"""
Automated tests for Safety checks and collision management.
"""

from pathlib import Path
from fileflow.core.models import CollisionPolicy
from fileflow.core.safety import (
    generate_unique_filename,
    is_path_traversal,
    is_system_or_root_path,
    validate_operation_safety,
)


def test_system_and_root_protection():
    # Root paths
    assert is_system_or_root_path(Path("C:/"))
    assert is_system_or_root_path(Path("/"))

    # System paths
    assert is_system_or_root_path(Path("C:/Windows"))
    assert is_system_or_root_path(Path("C:/Windows/System32"))
    assert is_system_or_root_path(Path("C:/Program Files"))


def test_path_traversal_detection(tmp_path: Path):
    safe_root = tmp_path / "authorized_user_folder"
    safe_root.mkdir()

    inside_file = safe_root / "document.pdf"
    outside_file = tmp_path / "outside.pdf"
    traversal_file = safe_root / ".." / "outside.pdf"

    assert not is_path_traversal(inside_file, safe_root)
    assert is_path_traversal(outside_file, safe_root)
    assert is_path_traversal(traversal_file, safe_root)


def test_generate_unique_filename(tmp_path: Path):
    target = tmp_path / "document.pdf"
    target.write_text("v1")

    unique1 = generate_unique_filename(target)
    assert unique1 == tmp_path / "document (1).pdf"

    # Create the (1) file and test next collision
    unique1.write_text("v2")
    unique2 = generate_unique_filename(target)
    assert unique2 == tmp_path / "document (2).pdf"


def test_generate_unique_compound_filename(tmp_path: Path):
    tar_file = tmp_path / "backup.tar.gz"
    tar_file.write_text("tar data")

    unique_tar = generate_unique_filename(tar_file)
    assert unique_tar == tmp_path / "backup (1).tar.gz"


def test_validate_operation_safety_collision_policies(tmp_path: Path):
    src = tmp_path / "source.txt"
    src.write_text("source content")

    dest = tmp_path / "target.txt"
    dest.write_text("existing content")

    # 1. AUTO_RENAME policy
    safe, final_dest, warnings, conflicts = validate_operation_safety(
        source_path=src,
        proposed_destination=dest,
        policy=CollisionPolicy.AUTO_RENAME,
    )
    assert safe is True
    assert final_dest.name == "target (1).txt"
    assert len(warnings) > 0
    assert len(conflicts) == 0

    # 2. SKIP policy
    safe_skip, _, warn_skip, _ = validate_operation_safety(
        source_path=src,
        proposed_destination=dest,
        policy=CollisionPolicy.SKIP,
    )
    assert safe_skip is False
    assert any("skipped" in w for w in warn_skip)

    # 3. FAIL policy
    safe_fail, _, _, conf_fail = validate_operation_safety(
        source_path=src,
        proposed_destination=dest,
        policy=CollisionPolicy.FAIL,
    )
    assert safe_fail is False
    assert any("already exists" in c for c in conf_fail)


def test_move_onto_itself(tmp_path: Path):
    file1 = tmp_path / "same.txt"
    file1.write_text("content")

    safe, final_dest, warnings, conflicts = validate_operation_safety(
        source_path=file1,
        proposed_destination=file1,
    )
    assert safe is True
    assert any("already in the target location" in w for w in warnings)
