"""
Smart File Classifier for FileFlow.
Handles extension normalization, compound extensions (e.g. .tar.gz),
custom categories, executable/risky identification, and unknown file tagging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from fileflow.core.models import CategoryDefinition


def get_default_category_definitions() -> Dict[str, CategoryDefinition]:
    """Default categories specified by FileFlow specifications."""
    return {
        "Documents": CategoryDefinition(
            name="Documents",
            extensions=[".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
            destination_folder="Documents",
            is_risky=False,
            description="Text documents, office files, and portable document formats.",
        ),
        "Images": CategoryDefinition(
            name="Images",
            extensions=[".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"],
            destination_folder="Images",
            is_risky=False,
            description="Raster and vector image files.",
        ),
        "Videos": CategoryDefinition(
            name="Videos",
            extensions=[".mp4", ".mkv", ".mov", ".avi", ".webm"],
            destination_folder="Videos",
            is_risky=False,
            description="Video clips and movies.",
        ),
        "Audio": CategoryDefinition(
            name="Audio",
            extensions=[".mp3", ".wav", ".aac", ".flac", ".ogg"],
            destination_folder="Audio",
            is_risky=False,
            description="Music tracks and audio recordings.",
        ),
        "Archives": CategoryDefinition(
            name="Archives",
            extensions=[".zip", ".rar", ".7z", ".tar", ".gz", ".tar.gz", ".tar.bz2", ".tar.xz"],
            destination_folder="Archives",
            is_risky=False,
            description="Compressed archives and packed files.",
        ),
        "Code": CategoryDefinition(
            name="Code",
            extensions=[
                ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
                ".java", ".cpp", ".c", ".go", ".rs", ".json", ".yaml", ".yml", ".sql"
            ],
            destination_folder="Code",
            is_risky=False,
            description="Source code, scripts, markup, and database schemas.",
        ),
        "Spreadsheets": CategoryDefinition(
            name="Spreadsheets",
            extensions=[".csv", ".xls", ".xlsx", ".ods"],
            destination_folder="Spreadsheets",
            is_risky=False,
            description="Tabular data sheets and workbooks.",
        ),
        "Presentations": CategoryDefinition(
            name="Presentations",
            extensions=[".ppt", ".pptx", ".odp"],
            destination_folder="Presentations",
            is_risky=False,
            description="Slide decks and presentation files.",
        ),
        "Executables": CategoryDefinition(
            name="Executables",
            extensions=[".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".sh"],
            destination_folder="Executables",
            is_risky=True,
            description="Executable binaries and shell scripts (treated as risky).",
        ),
    }


class FileClassifier:
    """
    Classifies files based on their extension into user-configurable categories.
    Matches extensions case-insensitively and respects multi-part extensions.
    """

    def __init__(self, categories: Optional[Dict[str, CategoryDefinition]] = None):
        self._categories: Dict[str, CategoryDefinition] = (
            categories.copy() if categories else get_default_category_definitions()
        )
        self._rebuild_lookup()

    def _rebuild_lookup(self) -> None:
        """Rebuild quick extension-to-category lookup index."""
        self._ext_to_category: Dict[str, str] = {}
        for cat_name, cat_def in self._categories.items():
            for ext in cat_def.extensions:
                norm_ext = ext.lower().strip()
                self._ext_to_category[norm_ext] = cat_name

    @property
    def categories(self) -> Dict[str, CategoryDefinition]:
        """Return shallow copy of all registered categories."""
        return self._categories.copy()

    def extract_extension(self, path_or_name: Union[Path, str]) -> str:
        """
        Extract normalized lowercase extension from filename or Path.
        Correctly recognizes multi-part extensions (e.g. '.tar.gz', '.tar.bz2').
        """
        filename = path_or_name.name if isinstance(path_or_name, Path) else Path(path_or_name).name
        filename_lower = filename.lower()

        # Check for known compound extensions
        compound_extensions = [".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"]
        for compound in compound_extensions:
            if filename_lower.endswith(compound):
                return compound

        # Standard single extension
        suffixes = Path(filename).suffixes
        if suffixes:
            return suffixes[-1].lower()
        return ""

    def classify(self, path_or_name: Union[Path, str]) -> Tuple[str, bool, bool]:
        """
        Classifies a file by its extension.
        Returns:
            Tuple[category_name (str), is_risky (bool), is_unknown (bool)]
        """
        ext = self.extract_extension(path_or_name)
        if not ext:
            return "Other", False, True

        cat_name = self._ext_to_category.get(ext)
        if cat_name and cat_name in self._categories:
            cat_def = self._categories[cat_name]
            return cat_name, cat_def.is_risky, False

        return "Other", False, True

    def get_destination_folder(self, category_name: str) -> str:
        """Get the configured destination folder for a category."""
        if category_name in self._categories:
            return self._categories[category_name].destination_folder
        return "Other"

    def add_category(
        self,
        name: str,
        extensions: List[str],
        destination_folder: Optional[str] = None,
        is_risky: bool = False,
        description: Optional[str] = None,
    ) -> CategoryDefinition:
        """Add or overwrite a custom category."""
        dest = destination_folder or name
        cat_def = CategoryDefinition(
            name=name,
            extensions=extensions,
            destination_folder=dest,
            is_risky=is_risky,
            description=description,
        )
        self._categories[name] = cat_def
        self._rebuild_lookup()
        return cat_def

    def remove_category(self, name: str) -> bool:
        """Remove a category if present (cannot remove 'Other')."""
        if name in self._categories:
            del self._categories[name]
            self._rebuild_lookup()
            return True
        return False

    def add_extensions_to_category(self, category_name: str, extensions: List[str]) -> bool:
        """Add additional extensions to an existing category."""
        if category_name not in self._categories:
            return False
        cat = self._categories[category_name]
        combined = set(cat.extensions)
        for ext in extensions:
            norm = ext.lower().strip()
            if norm and not norm.startswith("."):
                norm = f".{norm}"
            if norm:
                combined.add(norm)
        cat.extensions = sorted(list(combined))
        self._rebuild_lookup()
        return True

    def remove_extensions_from_category(self, category_name: str, extensions: List[str]) -> bool:
        """Remove specific extensions from a category."""
        if category_name not in self._categories:
            return False
        cat = self._categories[category_name]
        to_remove = {ext.lower().strip() for ext in extensions}
        cat.extensions = [e for e in cat.extensions if e.lower().strip() not in to_remove]
        self._rebuild_lookup()
        return True

    def set_category_destination(self, category_name: str, destination_folder: str) -> bool:
        """Change the destination folder for a given category."""
        if category_name not in self._categories:
            return False
        self._categories[category_name].destination_folder = destination_folder.strip()
        return True

    def reset_to_defaults(self) -> None:
        """Reset classifier back to factory default categories."""
        self._categories = get_default_category_definitions()
        self._rebuild_lookup()
