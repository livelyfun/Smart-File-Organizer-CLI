"""Backward-compatible re-export shim for the watcher module.

The engine now lives in ``smart_organizer.core.watcher``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.watcher import DirectoryWatcher, DownloadEventHandler

__all__ = ["DirectoryWatcher", "DownloadEventHandler"]