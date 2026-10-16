"""
Automated tests for SafeFileOrganizer.
"""

from pathlib import Path
from fileflow.core.models import CollisionPolicy, OperationStatus
from fileflow.core.organizer import SafeFileOrganizer
from fileflow.core.planner import OrganizationPlanner
from fileflow.core.scanner import FileScanner


def test_safe_file_move_execution(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    f1 = source_dir / "notes.txt"
    f2 = source_dir / "photo.jpg"
    f1.write_text("my notes")
    f2.write_text("binary jpg data")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    organizer = SafeFileOrganizer()
    job = organizer.execute_plan(plan)

    assert job.status == "completed"
    assert job.total_executed == 2
    assert job.total_failed == 0

    # Verify destination files
    dest_txt = source_dir / "Documents" / "notes.txt"
    dest_jpg = source_dir / "Images" / "photo.jpg"

    assert dest_txt.exists()
    assert dest_txt.read_text() == "my notes"
    assert dest_jpg.exists()

    # Verify source files are no longer in root
    assert not f1.exists()
    assert not f2.exists()


def test_revalidation_handles_missing_source_file(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    f1 = source_dir / "temp.txt"
    f1.write_text("data")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    # Delete file before executing plan
    f1.unlink()

    organizer = SafeFileOrganizer()
    job = organizer.execute_plan(plan)

    assert job.total_failed == 1
    assert job.total_executed == 0
    assert job.operations[0].status == OperationStatus.FAILED
    assert "no longer exists" in job.operations[0].error_message


def test_organizer_cancellation(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    # Create 5 files
    for i in range(5):
        (source_dir / f"file_{i}.txt").write_text(f"content {i}")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    organizer = SafeFileOrganizer()

    # Cancel after 2nd file in progress callback
    def on_progress(cur, total, op, res):
        if cur >= 2:
            organizer.request_cancellation()

    job = organizer.execute_plan(plan, progress_callback=on_progress)

    assert job.status == "cancelled"
    assert job.total_executed == 2
    # The remaining files should still be at original location
    remaining = list(source_dir.glob("file_*.txt"))
    assert len(remaining) == 3


def test_destination_collision_safe_rename(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    # Destination already has a notes.txt
    docs_dir = source_dir / "Documents"
    docs_dir.mkdir()
    existing_dest = docs_dir / "notes.txt"
    existing_dest.write_text("existing old notes")

    # Source has a new notes.txt
    src_file = source_dir / "notes.txt"
    src_file.write_text("new notes")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    organizer = SafeFileOrganizer()
    job = organizer.execute_plan(plan)

    assert job.total_executed == 1
    # Existing file MUST be untouched!
    assert existing_dest.read_text() == "existing old notes"

    # New file auto-renamed to notes (1).txt
    renamed_file = docs_dir / "notes (1).txt"
    assert renamed_file.exists()
    assert renamed_file.read_text() == "new notes"
