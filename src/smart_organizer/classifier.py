"""Backward-compatible re-export shim for the classifier module.

The engine now lives in ``smart_organizer.core.classifier``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.classifier import (
    DEFAULT_CATEGORY_EXTENSIONS,
    DEFAULT_FALLBACK_CATEGORY,
    FileClassifier,
    classify_file,
    is_temporary_download,
)

__all__ = [
    "DEFAULT_CATEGORY_EXTENSIONS",
    "DEFAULT_FALLBACK_CATEGORY",
    "FileClassifier",
    "classify_file",
    "is_temporary_download",
]