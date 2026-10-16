"""
Automated tests for JobHistoryManager and UndoManager.
"""

from pathlib import Path
from fileflow.core.organizer import SafeFileOrganizer
from fileflow.core.planner import OrganizationPlanner
from fileflow.core.scanner import FileScanner
from fileflow.core.undo import JobHistoryManager, UndoManager


def test_sqlite_job_persistence_and_undo(tmp_path: Path):
    db_file = tmp_path / "test_fileflow.db"
    history = JobHistoryManager(db_path=db_file)
    undo_mgr = UndoManager(history_manager=history)

    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    f1 = source_dir / "invoice.pdf"
    f2 = source_dir / "avatar.png"
    f1.write_text("invoice content")
    f2.write_text("png content")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    organizer = SafeFileOrganizer()
    job = organizer.execute_plan(plan)

    # Save to SQLite
    history.save_job(job)

    # Verify persisted job
    loaded_job = history.get_job(job.job_id)
    assert loaded_job is not None
    assert loaded_job.total_executed == 2
    assert len(loaded_job.operations) == 2

    # 1. Preview undo
    preview = undo_mgr.create_undo_preview(job.job_id)
    assert preview.safe_count == 2
    assert preview.unsafe_count == 0

    # 2. Execute undo
    success, messages, restored, failed = undo_mgr.execute_undo(job.job_id)
    assert success is True
    assert restored == 2
    assert failed == 0

    # Verify files restored to original locations
    assert f1.exists()
    assert f1.read_text() == "invoice content"
    assert f2.exists()
    assert f2.read_text() == "png content"

    # Verify empty category directories cleaned up
    assert not (source_dir / "Documents").exists()
    assert not (source_dir / "Images").exists()

    # Verify job marked undone
    updated_job = history.get_job(job.job_id)
    assert updated_job.is_undone is True


def test_undo_prevents_overwriting_new_file(tmp_path: Path):
    db_file = tmp_path / "test_fileflow.db"
    history = JobHistoryManager(db_path=db_file)
    undo_mgr = UndoManager(history_manager=history)

    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()

    f1 = source_dir / "doc.txt"
    f1.write_text("original doc")

    scanner = FileScanner()
    scanned, _ = scanner.scan(source_dir)

    planner = OrganizationPlanner()
    plan = planner.create_plan(source_dir, scanned)

    organizer = SafeFileOrganizer()
    job = organizer.execute_plan(plan)
    history.save_job(job)

    # User creates a NEW doc.txt at the original location
    f1.write_text("brand new doc placed by user")

    # Undo preview must flag this as unsafe
    preview = undo_mgr.create_undo_preview(job.job_id)
    assert preview.safe_count == 0
    assert preview.unsafe_count == 1
    assert "currently occupied" in preview.operations[0].reason

    # Undo execution must NOT overwrite the new file
    success, messages, restored, failed = undo_mgr.execute_undo(job.job_id)
    assert success is False
    assert restored == 0
    assert failed == 1
    assert f1.read_text() == "brand new doc placed by user"
