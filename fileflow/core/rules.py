"""
Rule Engine and Presets for FileFlow.
Evaluates configurable rules in deterministic priority order.
Provides built-in presets:
- By File Type
- By Date
- By Type and Year
- Screenshots Separately
- Large Files Separately
"""

from __future__ import annotations

import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fileflow.core.classifier import FileClassifier
from fileflow.core.models import (
    CollisionPolicy,
    Rule,
    RuleDestinationStrategy,
    ScannedFile,
)


def get_default_presets(classifier: Optional[FileClassifier] = None) -> List[Rule]:
    """Generate default preset rules."""
    c = classifier or FileClassifier()

    return [
        Rule(
            id="preset-screenshots",
            name="Organize Screenshots Separately",
            enabled=True,
            priority=10,
            description="Isolate screenshots into Images/Screenshots folder.",
            filename_patterns=["screenshot*", "screen shot*", "captura*", "capture*", "snap_*", "prtscr*"],
            categories=["Images"],
            destination_strategy=RuleDestinationStrategy.STATIC_FOLDER,
            destination_folder="Images/Screenshots",
            conflict_policy=CollisionPolicy.AUTO_RENAME,
        ),
        Rule(
            id="preset-large-files",
            name="Organize Large Files Separately",
            enabled=False,  # Optional toggle for users
            priority=20,
            description="Group files larger than 100MB into Large_Files.",
            min_size_bytes=100 * 1024 * 1024,  # 100 MB
            destination_strategy=RuleDestinationStrategy.STATIC_FOLDER,
            destination_folder="Large_Files",
            conflict_policy=CollisionPolicy.AUTO_RENAME,
        ),
        Rule(
            id="preset-by-file-type",
            name="Organize by File Type",
            enabled=True,
            priority=100,
            description="Sort files into folders matching their category (Documents, Images, Code, etc.).",
            destination_strategy=RuleDestinationStrategy.CATEGORY_FOLDER,
            destination_folder="{category}",
            conflict_policy=CollisionPolicy.AUTO_RENAME,
        ),
        Rule(
            id="preset-by-type-and-year",
            name="Organize by File Type and Year",
            enabled=False,
            priority=110,
            description="Sort files into category subfolders grouped by year (e.g. Documents/2026).",
            destination_strategy=RuleDestinationStrategy.TYPE_AND_YEAR,
            destination_folder="{category}/{year}",
            conflict_policy=CollisionPolicy.AUTO_RENAME,
        ),
        Rule(
            id="preset-by-date",
            name="Organize by Date",
            enabled=False,
            priority=120,
            description="Group files chronologically into Year/Month folders (e.g. 2026/2026-10).",
            destination_strategy=RuleDestinationStrategy.DATE_FOLDER,
            destination_folder="{year}/{year}-{month:02d}",
            conflict_policy=CollisionPolicy.AUTO_RENAME,
        ),
    ]


class RuleEngine:
    """
    Manages and evaluates organization rules in deterministic priority order.
    """

    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        classifier: Optional[FileClassifier] = None,
    ):
        self.classifier = classifier or FileClassifier()
        self.rules: List[Rule] = rules if rules is not None else get_default_presets(self.classifier)
        self._sort_rules()

    def _sort_rules(self) -> None:
        """Sort enabled rules by ascending priority value (lower number = higher precedence)."""
        self.rules.sort(key=lambda r: r.priority)

    def add_rule(self, rule: Rule) -> None:
        """Add a new rule and re-sort."""
        # Replace if ID already exists
        self.rules = [r for r in self.rules if r.id != rule.id]
        self.rules.append(rule)
        self._sort_rules()

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        initial_len = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < initial_len

    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        """Toggle enabled state of a rule."""
        for r in self.rules:
            if r.id == rule_id:
                r.enabled = enabled
                return True
        return False

    def reorder_rules(self, rule_ids_in_order: List[str]) -> None:
        """Reorder rules by assigning priority values 10, 20, 30... according to given ID list."""
        lookup = {r.id: r for r in self.rules}
        reordered: List[Rule] = []
        for index, rid in enumerate(rule_ids_in_order):
            if rid in lookup:
                rule = lookup[rid]
                rule.priority = (index + 1) * 10
                reordered.append(rule)
        # Append any unmentioned rules
        for r in self.rules:
            if r.id not in rule_ids_in_order:
                r.priority = (len(reordered) + 1) * 10
                reordered.append(r)
        self.rules = reordered
        self._sort_rules()

    def matches_rule(self, rule: Rule, file_info: ScannedFile) -> Tuple[bool, str]:
        """
        Check if a file matches a rule's filters.
        Returns:
            Tuple[matches (bool), reason (str)]
        """
        if not rule.enabled:
            return False, "Rule is disabled"

        # 1. Extension filter
        if rule.extensions is not None:
            norm_exts = {e.lower().strip() for e in rule.extensions}
            if file_info.extension.lower() not in norm_exts:
                return False, f"Extension {file_info.extension} does not match {rule.extensions}"

        # 2. Category filter
        if rule.categories is not None:
            norm_cats = {c.lower() for c in rule.categories}
            if file_info.category.lower() not in norm_cats:
                return False, f"Category {file_info.category} not in {rule.categories}"

        # 3. Filename patterns (globs, case-insensitive)
        if rule.filename_patterns is not None:
            name_lower = file_info.name.lower()
            matched_pattern = False
            for pat in rule.filename_patterns:
                if fnmatch.fnmatch(name_lower, pat.lower()):
                    matched_pattern = True
                    break
            if not matched_pattern:
                return False, f"Filename did not match patterns: {rule.filename_patterns}"

        # 4. Size filters
        if rule.min_size_bytes is not None and file_info.size_bytes < rule.min_size_bytes:
            return False, f"Size {file_info.size_bytes} < min {rule.min_size_bytes}"
        if rule.max_size_bytes is not None and file_info.size_bytes > rule.max_size_bytes:
            return False, f"Size {file_info.size_bytes} > max {rule.max_size_bytes}"

        # 5. Date filters
        if rule.modified_before is not None and file_info.modified_at >= rule.modified_before:
            return False, "Modified after cutoff"
        if rule.modified_after is not None and file_info.modified_at <= rule.modified_after:
            return False, "Modified before cutoff"

        # 6. Exclude patterns
        if rule.exclude_patterns is not None:
            name_lower = file_info.name.lower()
            for pat in rule.exclude_patterns:
                if fnmatch.fnmatch(name_lower, pat.lower()):
                    return False, f"Matches exclude pattern: {pat}"

        # 7. Include patterns
        if rule.include_patterns is not None:
            name_lower = file_info.name.lower()
            matched_inc = any(fnmatch.fnmatch(name_lower, pat.lower()) for pat in rule.include_patterns)
            if not matched_inc:
                return False, "Does not match include patterns"

        return True, f"Matched rule '{rule.name}'"

    def compute_destination_folder(self, rule: Rule, file_info: ScannedFile) -> str:
        """
        Compute target folder path relative to destination root based on rule strategy.
        Supports variables: {category}, {year}, {month}, {ext}.
        """
        year = file_info.modified_at.year
        month = file_info.modified_at.month
        clean_ext = file_info.extension.lstrip(".") or "no_ext"
        category = file_info.category

        if rule.destination_strategy == RuleDestinationStrategy.CATEGORY_FOLDER:
            # Look up configured category destination folder
            dest = self.classifier.get_destination_folder(category)
            return dest

        elif rule.destination_strategy == RuleDestinationStrategy.DATE_FOLDER:
            return f"{year}/{year}-{month:02d}"

        elif rule.destination_strategy == RuleDestinationStrategy.TYPE_AND_YEAR:
            cat_dest = self.classifier.get_destination_folder(category)
            return f"{cat_dest}/{year}"

        else:
            # Custom template or static folder
            folder_tmpl = rule.destination_folder
            formatted = folder_tmpl.format(
                category=category,
                year=year,
                month=month,
                ext=clean_ext,
            )
            return formatted

    def evaluate(self, file_info: ScannedFile) -> Tuple[Optional[Rule], str, str]:
        """
        Find first winning rule in priority order.
        Returns:
            Tuple[winning_rule (Optional[Rule]), destination_folder (str), explanation (str)]
        """
        matching_rules: List[Tuple[Rule, str]] = []

        for rule in self.rules:
            if not rule.enabled:
                continue
            is_match, reason = self.matches_rule(rule, file_info)
            if is_match:
                matching_rules.append((rule, reason))
                # Deterministic first-match policy
                dest_subfolder = self.compute_destination_folder(rule, file_info)
                explanation = f"Matched rule '{rule.name}' (priority {rule.priority})"
                return rule, dest_subfolder, explanation

        # Fallback if no rule matched
        dest_subfolder = self.classifier.get_destination_folder(file_info.category)
        return None, dest_subfolder, f"No custom rule matched. Defaulted to category '{file_info.category}'"
