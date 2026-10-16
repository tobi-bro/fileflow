"""
Automated tests for OrganizationPlanner dry-run generation.
"""

from pathlib import Path
from fileflow.core.classifier import FileClassifier
from fileflow.core.models import CollisionPolicy, OperationStatus
from fileflow.core.planner import OrganizationPlanner
from fileflow.core.rules import RuleEngine
from fileflow.core.scanner import FileScanner


def test_dry_run_leaves_filesystem_completely_unmodified(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    file1 = source_dir / "statement.pdf"
    file2 = source_dir / "photo.png"
    file3 = source_dir / "installer.exe"

    file1.write_text("statement data")
    file2.write_text("photo data")
    file3.write_text("binary executable data")

    # Snapshot of directory state before planning
    items_before = sorted([p.name for p in source_dir.iterdir()])

    scanner = FileScanner()
    scanned_files, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_folder=source_dir, scanned_files=scanned_files)

    # Snapshot after planning
    items_after = sorted([p.name for p in source_dir.iterdir()])

    # Verify: NO new directories created, NO files moved or modified
    assert items_before == items_after
    assert not (source_dir / "Documents").exists()
    assert not (source_dir / "Images").exists()
    assert not (source_dir / "Executables").exists()

    # Verify plan contents
    assert len(plan.operations) == 3
    op_map = {op.source_path.name: op for op in plan.operations}

    assert op_map["statement.pdf"].category == "Documents"
    assert op_map["statement.pdf"].proposed_destination == source_dir / "Documents" / "statement.pdf"

    assert op_map["photo.png"].category == "Images"
    assert op_map["photo.png"].proposed_destination == source_dir / "Images" / "photo.png"

    # Risky file check
    assert op_map["installer.exe"].category == "Executables"
    assert any("Executable/script file" in w for w in op_map["installer.exe"].warnings)


def test_intra_plan_collision_resolution(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    # Subfolder with file having same name
    sub_dir = source_dir / "old_files"
    sub_dir.mkdir()

    f1 = source_dir / "report.pdf"
    f2 = sub_dir / "report.pdf"
    f1.write_text("report 1")
    f2.write_text("report 2")

    scanner = FileScanner()
    scanned_files, _ = scanner.scan(source_dir, recursive=True)

    planner = OrganizationPlanner()
    plan = planner.create_plan(
        source_folder=source_dir,
        scanned_files=scanned_files,
        default_policy=CollisionPolicy.AUTO_RENAME,
    )

    resolved_names = [op.resolved_destination.name for op in plan.operations if op.resolved_destination]
    assert len(resolved_names) == 2
    assert "report.pdf" in resolved_names
    assert "report (1).pdf" in resolved_names


def test_selection_controls(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    (source_dir / "doc1.pdf").write_text("doc1")
    (source_dir / "doc2.pdf").write_text("doc2")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    # Initial state: all safe operations are selected
    assert all(op.is_selected for op in plan.operations)

    # Deselect all
    planner.select_all(plan, select=False)
    assert not any(op.is_selected for op in plan.operations)

    # Toggle individual
    target_id = plan.operations[0].id
    assert planner.toggle_selection(plan, target_id) is True
    assert plan.operations[0].is_selected is True
    assert plan.operations[1].is_selected is False
