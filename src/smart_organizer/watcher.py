"""Watcher module for Smart File Organizer.

Monitors the target directory using watchdog, filters events, and schedules
asynchronous stability checks for newly created or completed download files.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from smart_organizer.classifier import FileClassifier
from smart_organizer.config import AppConfig
from smart_organizer.stability import wait_for_file_stability


class DownloadEventHandler(FileSystemEventHandler):
    """Event handler for watchdog that filters events and checks download stability."""

    def __init__(
        self,
        config: AppConfig,
        classifier: FileClassifier,
        on_file_ready: Callable[[Path], None],
    ):
        super().__init__()
        self.config = config
        self.classifier = classifier
        self.on_file_ready = on_file_ready
        self.watch_dir = config.resolved_watch_directory
        self._processing_lock = threading.Lock()
        self._active_files: Set[Path] = set()

    def should_ignore(self, path: Path) -> bool:
        """Determines if a file path should be ignored by the watcher."""
        # 1. Ignore if not directly inside the root watched directory (non-recursive check)
        try:
            if path.parent.resolve() != self.watch_dir.resolve():
                return True
        except Exception:
            return True

        # 2. Ignore hidden files
        if self.config.ignore_hidden_files and path.name.startswith("."):
            return True

        # 3. Ignore known category folders
        if path.name in self.classifier.known_categories:
            return True

        # 4. Ignore temporary/incomplete download files (.crdownload, .part, .tmp, etc.)
        if self.classifier.is_temporary_file(path):
            return True

        return False

    def _process_candidate_file_async(self, file_path: Path) -> None:
        """Runs stability check in background thread and triggers organization when ready."""
        try:
            is_stable = wait_for_file_stability(
                file_path=file_path,
                stability_delay=self.config.stability_delay,
                stability_checks=self.config.stability_checks,
                max_wait_time=self.config.max_stability_wait,
            )
            if is_stable and file_path.exists():
                self.on_file_ready(file_path)
        finally:
            with self._processing_lock:
                self._active_files.discard(file_path)

    def _handle_path_candidate(self, path_str: str) -> None:
        path = Path(path_str)

        if self.should_ignore(path):
            return

        with self._processing_lock:
            if path in self._active_files:
                return
            self._active_files.add(path)

        thread = threading.Thread(
            target=self._process_candidate_file_async,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_path_candidate(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # Downloads frequently rename from .crdownload to .pdf upon completion
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self._handle_path_candidate(dest_path)


class DirectoryWatcher:
    """Manages the watchdog observer for monitoring the Downloads folder."""

    def __init__(
        self,
        config: AppConfig,
        classifier: FileClassifier,
        on_file_ready: Callable[[Path], None],
    ):
        self.config = config
        self.watch_dir = config.resolved_watch_directory
        self.handler = DownloadEventHandler(config, classifier, on_file_ready)
        self.observer = Observer()

    def start(self) -> None:
        """Starts watching the target directory non-recursively."""
        if not self.watch_dir.exists():
            raise FileNotFoundError(f"Watch directory does not exist: {self.watch_dir}")

        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()

    def stop(self) -> None:
        """Stops the observer cleanly."""
        self.observer.stop()
        self.observer.join()
