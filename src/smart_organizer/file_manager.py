"""Backward-compatible re-export shim for the file manager module.

The engine now lives in ``smart_organizer.core.file_manager``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.file_manager import (
    KNOWN_DOUBLE_EXTENSIONS,
    FileManager,
    MoveResult,
    generate_unique_destination_path,
    split_stem_and_suffix,
)

__all__ = [
    "KNOWN_DOUBLE_EXTENSIONS",
    "FileManager",
    "MoveResult",
    "generate_unique_destination_path",
    "split_stem_and_suffix",
]