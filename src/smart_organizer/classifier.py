"""File classification module for Smart File Organizer.

Maps file extensions to high-level organization categories in a centralized,
case-insensitive, and cross-platform manner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

# Centralized default extension-to-category mappings
DEFAULT_CATEGORY_EXTENSIONS: Dict[str, List[str]] = {
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
        ".tiff", ".tif", ".ico", ".heic", ".heif", ".raw", ".psd",
        ".ai", ".eps",
    ],
    "Videos": [
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
        ".m4v", ".mpeg", ".mpg", ".3gp", ".ts", ".vob",
    ],
    "Audio": [
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus",
        ".wma", ".aiff", ".alac", ".mid", ".midi",
    ],
    "PDFs": [
        ".pdf",
    ],
    "Documents": [
        ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".tex",
        ".epub", ".pages", ".wpd", ".log",
    ],
    "Spreadsheets": [
        ".xls", ".xlsx", ".ods", ".csv", ".tsv", ".numbers", ".xlsm",
    ],
    "Presentations": [
        ".ppt", ".pptx", ".odp", ".key", ".pps", ".ppsx",
    ],
    "Archives": [
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
        ".tgz", ".tbz2", ".z", ".iso", ".dmg",
    ],
    "Code": [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp",
        ".cc", ".h", ".hpp", ".cs", ".rs", ".go", ".php", ".rb",
        ".swift", ".kt", ".kts", ".sh", ".bash", ".zsh", ".fish",
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".json", ".xml", ".yaml", ".yml", ".toml", ".sql",
        ".lua", ".r", ".pl", ".ini", ".conf",
    ],
    "Applications": [
        ".deb", ".rpm", ".appimage", ".exe", ".msi", ".dmg",
        ".pkg", ".apk", ".flatpakref", ".snap",
    ],
}

DEFAULT_FALLBACK_CATEGORY = "Others"


class FileClassifier:
    """Classifies files into categories based on extension rules."""

    def __init__(
        self,
        custom_categories: Optional[Dict[str, List[str]]] = None,
        temporary_extensions: Optional[List[str]] = None,
    ):
        self._extension_map: Dict[str, str] = {}
        self._category_names: Set[str] = set()
        self._temporary_extensions: Set[str] = set()

        # Load default temporary extensions
        if temporary_extensions:
            for ext in temporary_extensions:
                norm = ext.strip().lower()
                if not norm.startswith("."):
                    norm = f".{norm}"
                self._temporary_extensions.add(norm)
        else:
            self._temporary_extensions = {
                ".crdownload",
                ".part",
                ".partial",
                ".download",
                ".tmp",
                ".crswap",
            }

        # Build reverse lookup map
        self._load_mappings(DEFAULT_CATEGORY_EXTENSIONS)
        if custom_categories:
            self._load_mappings(custom_categories)

    def _load_mappings(self, category_dict: Dict[str, List[str]]) -> None:
        for category, extensions in category_dict.items():
            self._category_names.add(category)
            for ext in extensions:
                norm = ext.strip().lower()
                if not norm.startswith("."):
                    norm = f".{norm}"
                self._extension_map[norm] = category

    @property
    def known_categories(self) -> Set[str]:
        """Returns set of all known category folder names."""
        return self._category_names | {DEFAULT_FALLBACK_CATEGORY}

    def is_temporary_file(self, path: Path | str) -> bool:
        """Determines if the given file has a temporary or incomplete download extension."""
        name = Path(path).name.lower()
        # Check direct suffix
        suffix = Path(path).suffix.lower()
        if suffix in self._temporary_extensions:
            return True

        # Also check compound temporary suffixes like 'movie.mp4.crdownload'
        for temp_ext in self._temporary_extensions:
            if name.endswith(temp_ext):
                return True

        return False

    def classify_file(self, path: Path | str) -> str:
        """Determines category for a given path.

        Case-insensitive matching. Defaults to 'Others' for unknown extensions.
        """
        path_obj = Path(path)
        ext = path_obj.suffix.lower()
        if not ext:
            return DEFAULT_FALLBACK_CATEGORY

        return self._extension_map.get(ext, DEFAULT_FALLBACK_CATEGORY)


# Module default classifier instance
_DEFAULT_CLASSIFIER = FileClassifier()


def is_temporary_download(path: Path | str) -> bool:
    """Helper to check if a file is an incomplete download."""
    return _DEFAULT_CLASSIFIER.is_temporary_file(path)


def classify_file(
    path: Path | str,
    custom_categories: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Convenience helper to classify a file path."""
    if custom_categories:
        classifier = FileClassifier(custom_categories=custom_categories)
        return classifier.classify_file(path)
    return _DEFAULT_CLASSIFIER.classify_file(path)
