"""
Unit tests for FileClassifier.
"""

from pathlib import Path
from fileflow.core.classifier import FileClassifier, get_default_category_definitions


def test_default_categories_loaded():
    classifier = FileClassifier()
    categories = classifier.categories

    expected = [
        "Documents",
        "Images",
        "Videos",
        "Audio",
        "Archives",
        "Code",
        "Spreadsheets",
        "Presentations",
        "Executables",
    ]
    for exp in expected:
        assert exp in categories, f"Expected category {exp} not found"


def test_case_insensitive_classification():
    classifier = FileClassifier()

    cat, is_risky, is_unknown = classifier.classify("REPORT.PDF")
    assert cat == "Documents"
    assert not is_risky
    assert not is_unknown

    cat, is_risky, is_unknown = classifier.classify("photo.JpEg")
    assert cat == "Images"

    cat, is_risky, is_unknown = classifier.classify("SCRIPT.PS1")
    assert cat == "Executables"
    assert is_risky is True


def test_compound_extensions():
    classifier = FileClassifier()

    ext = classifier.extract_extension("archive.tar.gz")
    assert ext == ".tar.gz"

    cat, _, _ = classifier.classify("archive.tar.gz")
    assert cat == "Archives"

    ext2 = classifier.extract_extension("backup.tar.bz2")
    assert ext2 == ".tar.bz2"
    cat2, _, _ = classifier.classify("backup.tar.bz2")
    assert cat2 == "Archives"


def test_files_without_extensions():
    classifier = FileClassifier()

    ext = classifier.extract_extension("Dockerfile")
    assert ext == ""
    cat, is_risky, is_unknown = classifier.classify("Dockerfile")
    assert cat == "Other"
    assert is_unknown is True


def test_unknown_extensions():
    classifier = FileClassifier()

    cat, is_risky, is_unknown = classifier.classify("data.xyz_unsupported_ext")
    assert cat == "Other"
    assert is_unknown is True


def test_executable_risk_flag():
    classifier = FileClassifier()

    for risky_file in ["setup.exe", "install.msi", "run.bat", "deploy.cmd", "init.ps1"]:
        cat, is_risky, _ = classifier.classify(risky_file)
        assert cat == "Executables"
        assert is_risky is True


def test_custom_categories_and_extensions():
    classifier = FileClassifier()

    # Add custom 3D models category
    classifier.add_category(
        name="3D_Models",
        extensions=[".obj", ".fbx", ".stl", ".blend"],
        destination_folder="Models3D",
        is_risky=False,
    )

    cat, is_risky, is_unknown = classifier.classify("cube.obj")
    assert cat == "3D_Models"
    assert not is_risky
    assert not is_unknown
    assert classifier.get_destination_folder("3D_Models") == "Models3D"

    # Add new extension to Documents
    classifier.add_extensions_to_category("Documents", [".epub", ".mobi"])
    cat_epub, _, _ = classifier.classify("book.epub")
    assert cat_epub == "Documents"

    # Remove extension from Documents
    classifier.remove_extensions_from_category("Documents", [".epub"])
    cat_epub2, _, is_unknown2 = classifier.classify("book.epub")
    assert cat_epub2 == "Other"
    assert is_unknown2 is True


def test_reset_to_defaults():
    classifier = FileClassifier()
    classifier.add_category("CustomCat", [".foo"], "CustomFolder")
    assert "CustomCat" in classifier.categories

    classifier.reset_to_defaults()
    assert "CustomCat" not in classifier.categories
