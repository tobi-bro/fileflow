"""
Automated tests for FileScanner.
Uses isolated pytest tmp_path fixtures.
"""

from pathlib import Path
import pytest
from fileflow.core.scanner import FileScanner


def test_scan_empty_directory(tmp_path: Path):
    scanner = FileScanner()
    files, errors = scanner.scan(tmp_path)
    assert len(files) == 0
    assert len(errors) == 0


def test_scan_mixed_extensions_and_uppercase(tmp_path: Path):
    # Create sample files
    (tmp_path / "document.pdf").write_text("dummy")
    (tmp_path / "IMAGE.PNG").write_text("dummy")
    (tmp_path / "song.MP3").write_text("dummy")
    (tmp_path / "script.py").write_text("dummy")
    (tmp_path / "archive.tar.gz").write_text("dummy")
    (tmp_path / "README").write_text("no extension")
    (tmp_path / "unknown.customext123").write_text("unknown")

    scanner = FileScanner()
    files, errors = scanner.scan(tmp_path)

    assert len(errors) == 0
    assert len(files) == 7

    names_to_cats = {f.name: f.category for f in files}
    assert names_to_cats["document.pdf"] == "Documents"
    assert names_to_cats["IMAGE.PNG"] == "Images"
    assert names_to_cats["song.MP3"] == "Audio"
    assert names_to_cats["script.py"] == "Code"
    assert names_to_cats["archive.tar.gz"] == "Archives"
    assert names_to_cats["README"] == "Other"
    assert names_to_cats["unknown.customext123"] == "Other"


def test_scan_hidden_files(tmp_path: Path):
    (tmp_path / "visible.txt").write_text("hello")
    (tmp_path / ".hidden_file").write_text("secret")
    (tmp_path / ".env").write_text("SECRET=1")

    scanner = FileScanner()

    # Default: hidden files ignored
    files_default, _ = scanner.scan(tmp_path, include_hidden=False)
    assert len(files_default) == 1
    assert files_default[0].name == "visible.txt"

    # With include_hidden=True
    files_hidden, _ = scanner.scan(tmp_path, include_hidden=True)
    assert len(files_hidden) == 3
    names = {f.name for f in files_hidden}
    assert ".hidden_file" in names
    assert ".env" in names


def test_scan_symlinks(tmp_path: Path):
    target_file = tmp_path / "target.txt"
    target_file.write_text("target")

    symlink_file = tmp_path / "link.txt"
    try:
        symlink_file.symlink_to(target_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported in current Windows permissions environment")

    scanner = FileScanner()

    # Symlinks skipped by default
    files, _ = scanner.scan(tmp_path, follow_symlinks=False)
    names = [f.name for f in files]
    assert "target.txt" in names
    assert "link.txt" not in names


def test_scan_nonexistent_or_file_target(tmp_path: Path):
    scanner = FileScanner()

    # Nonexistent
    files, errors = scanner.scan(tmp_path / "nonexistent_subfolder")
    assert len(files) == 0
    assert len(errors) > 0
    assert "Directory does not exist" in errors[0]

    # File target instead of folder
    file_target = tmp_path / "sample.txt"
    file_target.write_text("data")
    files2, errors2 = scanner.scan(file_target)
    assert len(files2) == 0
    assert len(errors2) > 0
    assert "Path is not a directory" in errors2[0]
