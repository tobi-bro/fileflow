"""
Automated tests for RuleEngine and Presets.
"""

from datetime import datetime
from pathlib import Path
from fileflow.core.classifier import FileClassifier
from fileflow.core.models import (
    CollisionPolicy,
    Rule,
    RuleDestinationStrategy,
    ScannedFile,
)
from fileflow.core.rules import RuleEngine, get_default_presets


def make_dummy_file(
    name: str,
    category: str = "Images",
    ext: str = ".png",
    size: int = 1024,
    dt: datetime = datetime(2026, 10, 16, 12, 0),
) -> ScannedFile:
    return ScannedFile(
        path=Path(f"/fake/{name}"),
        name=name,
        stem=Path(name).stem,
        extension=ext,
        size_bytes=size,
        created_at=dt,
        modified_at=dt,
        is_hidden=False,
        is_symlink=False,
        category=category,
        is_risky=False,
        is_unknown=False,
    )


def test_rule_priority_ordering():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    # By default, screenshots rule has priority 10, file-type has priority 100
    screenshot_file = make_dummy_file("Screenshot_2026.png", category="Images", ext=".png")
    rule, dest, explanation = engine.evaluate(screenshot_file)

    assert rule is not None
    assert rule.id == "preset-screenshots"
    assert dest == "Images/Screenshots"
    assert "priority 10" in explanation

    # General image file should fall back to preset-by-file-type (priority 100)
    general_img = make_dummy_file("vacation.png", category="Images", ext=".png")
    rule2, dest2, _ = engine.evaluate(general_img)
    assert rule2 is not None
    assert rule2.id == "preset-by-file-type"
    assert dest2 == "Images"


def test_disable_rule():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    # Disable screenshots rule
    assert engine.enable_rule("preset-screenshots", enabled=False)

    screenshot_file = make_dummy_file("Screenshot_2026.png", category="Images", ext=".png")
    rule, dest, _ = engine.evaluate(screenshot_file)

    # Should now fall through to preset-by-file-type
    assert rule is not None
    assert rule.id == "preset-by-file-type"
    assert dest == "Images"


def test_reorder_rules():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    # Reorder so preset-by-file-type is first
    engine.reorder_rules(["preset-by-file-type", "preset-screenshots"])

    assert engine.rules[0].id == "preset-by-file-type"
    assert engine.rules[1].id == "preset-screenshots"

    # Now file type should win first
    screenshot_file = make_dummy_file("Screenshot_2026.png", category="Images", ext=".png")
    rule, dest, _ = engine.evaluate(screenshot_file)
    assert rule.id == "preset-by-file-type"
    assert dest == "Images"


def test_large_files_preset():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    # Enable large files preset
    engine.enable_rule("preset-large-files", enabled=True)

    large_file = make_dummy_file(
        "big_archive.zip",
        category="Archives",
        ext=".zip",
        size=150 * 1024 * 1024,  # 150 MB
    )
    rule, dest, _ = engine.evaluate(large_file)
    assert rule.id == "preset-large-files"
    assert dest == "Large_Files"


def test_date_preset():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    # Disable others, enable by-date
    engine.enable_rule("preset-screenshots", False)
    engine.enable_rule("preset-by-file-type", False)
    engine.enable_rule("preset-by-date", True)

    file_info = make_dummy_file(
        "notes.txt",
        category="Documents",
        ext=".txt",
        dt=datetime(2025, 4, 15, 10, 0),
    )
    rule, dest, _ = engine.evaluate(file_info)
    assert rule.id == "preset-by-date"
    assert dest == "2025/2025-04"


def test_custom_rule_with_filters():
    classifier = FileClassifier()
    engine = RuleEngine(classifier=classifier)

    custom_rule = Rule(
        id="custom-invoices",
        name="Tax & Invoices",
        enabled=True,
        priority=5,
        filename_patterns=["*invoice*", "*tax*"],
        destination_strategy=RuleDestinationStrategy.STATIC_FOLDER,
        destination_folder="Finance/Invoices",
    )
    engine.add_rule(custom_rule)

    invoice_file = make_dummy_file("2026_Tax_Invoice.pdf", category="Documents", ext=".pdf")
    rule, dest, explanation = engine.evaluate(invoice_file)
    assert rule.id == "custom-invoices"
    assert dest == "Finance/Invoices"
    assert "Tax & Invoices" in explanation
