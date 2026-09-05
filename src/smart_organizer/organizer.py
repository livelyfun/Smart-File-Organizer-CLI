"""Organizer service module for Smart File Organizer.

Coordinates file detection, filtering, classification, duplicate-safe movement,
and logging.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from smart_organizer.classifier import FileClassifier
from smart_organizer.config import AppConfig
from smart_organizer.file_manager import FileManager
from smart_organizer.logger import OrganizerLogger, setup_logger
from smart_organizer.watcher import DirectoryWatcher


class SmartFileOrganizer:
    """Core coordinator for file organization operations."""

    def __init__(self, config: AppConfig, logger: Optional[OrganizerLogger] = None):
        self.config = config
        self.logger = logger or setup_logger(self.config.resolved_log_file)
        self.classifier = FileClassifier(
            custom_categories=self.config.custom_categories,
            temporary_extensions=self.config.temporary_extensions,
        )
        self.file_manager = FileManager(create_dirs=True)

        self._stats_lock = threading.Lock()
        self.organized_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def organize_single_file(self, file_path: Path) -> bool:
        """Organizes a single file into its appropriate category directory.

        Returns:
            True if the file was moved successfully, False otherwise.
        """
        # Ensure file exists and is a regular file
        if not file_path.exists() or not file_path.is_file():
            return False

        # Ignore if file is hidden
        if self.config.ignore_hidden_files and file_path.name.startswith("."):
            with self._stats_lock:
                self.skipped_count += 1
            return False

        # Ignore temporary files
        if self.classifier.is_temporary_file(file_path):
            with self._stats_lock:
                self.skipped_count += 1
            self.logger.log_skipped(file_path.name, "temporary download")
            return False

        # Determine category
        category = self.classifier.classify_file(file_path)
        dest_dir = self.file_manager.get_destination_dir(
            self.config.resolved_watch_directory,
            category,
        )

        # Move file safely
        result = self.file_manager.safe_move(
            source_path=file_path,
            destination_dir=dest_dir,
            category=category,
        )

        if result.success and result.destination_path:
            with self._stats_lock:
                self.organized_count += 1
            rel_dest = f"{category}/{result.destination_path.name}"
            self.logger.log_organized(
                filename=file_path.name,
                category=category,
                dest_rel_path=rel_dest,
                full_dest_path=str(result.destination_path),
            )
            return True
        else:
            with self._stats_lock:
                self.error_count += 1
            err = result.error_message or "Unknown error"
            self.logger.log_error(
                filename=file_path.name,
                error_message=err,
                category=category,
            )
            return False

    def organize_existing_files(self) -> Dict[str, int]:
        """Scans the root watch directory and organizes existing files directly inside it.

        Does not recursively scan category directories.
        """
        watch_dir = self.config.resolved_watch_directory
        if not watch_dir.exists():
            error_msg = f"Watch directory does not exist: {watch_dir}"
            print(f"Error: {error_msg}", file=sys.stderr)
            return {"organized": 0, "errors": 1, "skipped": 0}

        stats = {"organized": 0, "errors": 0, "skipped": 0}

        try:
            for entry in sorted(watch_dir.iterdir()):
                # Skip subdirectories (including existing category folders)
                if entry.is_dir():
                    continue

                # Skip hidden files
                if self.config.ignore_hidden_files and entry.name.startswith("."):
                    stats["skipped"] += 1
                    continue

                # Skip temporary download files
                if self.classifier.is_temporary_file(entry):
                    self.logger.log_skipped(entry.name, "temporary download")
                    stats["skipped"] += 1
                    continue

                success = self.organize_single_file(entry)
                if success:
                    stats["organized"] += 1
                else:
                    stats["errors"] += 1

        except PermissionError:
            print(f"Permission denied accessing directory: {watch_dir}", file=sys.stderr)
            stats["errors"] += 1

        return stats

    def start_monitoring(self, stop_event: Optional[threading.Event] = None) -> None:
        """Starts live watchdog monitoring of the configured watch directory."""
        watch_dir = self.config.resolved_watch_directory
        if not watch_dir.exists():
            raise FileNotFoundError(
                f"Cannot watch directory because it does not exist: {watch_dir}\n"
                f"Please create the directory or configure a different path with --watch-directory."
            )

        watcher = DirectoryWatcher(
            config=self.config,
            classifier=self.classifier,
            on_file_ready=self.organize_single_file,
        )

        watcher.start()
        try:
            if stop_event:
                stop_event.wait()
            else:
                while True:
                    time.sleep(0.5)
        finally:
            watcher.stop()

    def get_status(self) -> Dict[str, Any]:
        """Returns runtime status and metrics."""
        with self._stats_lock:
            return {
                "watch_directory": str(self.config.resolved_watch_directory),
                "watch_directory_exists": self.config.resolved_watch_directory.exists(),
                "log_file": str(self.config.resolved_log_file) if self.config.resolved_log_file else None,
                "organized_count": self.organized_count,
                "skipped_count": self.skipped_count,
                "error_count": self.error_count,
                "stability_delay": self.config.stability_delay,
                "stability_checks": self.config.stability_checks,
            }
