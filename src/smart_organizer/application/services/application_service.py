"""Shared application service coordinating the core engine.

Frontend-agnostic entry point used by both the CLI and the desktop GUI.
Long-running operations (monitoring) run off the caller's thread.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional, Union

from smart_organizer.application.services.event_bus import EventBus, EventCallback
from smart_organizer.application.services.events import (
    BatchCompleteEvent,
    MonitoringStartedEvent,
    MonitoringStoppedEvent,
)
from smart_organizer.application.services.event_logger import EventEmitterLogger
from smart_organizer.core.config import AppConfig
from smart_organizer.core.logger import OrganizerLogger
from smart_organizer.core.organizer import SmartFileOrganizer


class OrganizerService:
    """Coordinates the core engine for frontends.

    Lives on top of :class:`smart_organizer.core.organizer.SmartFileOrganizer`.
    All file system business logic stays in core; this service only manages
    composition, lifecycle, and frontend notification.
    """

    def __init__(
        self,
        config: AppConfig,
        logger: Optional[OrganizerLogger] = None,
        bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config
        self.bus = bus or EventBus()
        self.logger = logger or EventEmitterLogger(self.bus)
        self._organizer: Optional[SmartFileOrganizer] = None

        self._lock = threading.Lock()
        self._running = False
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def organizer(self) -> SmartFileOrganizer:
        """Lazily builds the core organizer bound to this service's logger."""
        if self._organizer is None:
            self._organizer = SmartFileOrganizer(self.config, logger=self.logger)
        return self._organizer

    @property
    def is_running(self) -> bool:
        """Whether live monitoring is currently active."""
        with self._lock:
            return self._running

    def subscribe(self, callback: EventCallback) -> None:
        """Registers an event listener (see EventBus)."""
        self.bus.subscribe(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """Removes an event listener (see EventBus)."""
        self.bus.unsubscribe(callback)

    def start(self) -> None:
        """Starts live monitoring without blocking the calling thread.

        Raises:
            RuntimeError: If monitoring is already running.
            FileNotFoundError: If the configured watch directory does not exist.
        """
        watch_dir = self.config.resolved_watch_directory
        if not watch_dir.exists():
            raise FileNotFoundError(
                f"Cannot watch directory because it does not exist: {watch_dir}"
            )

        with self._lock:
            if self._running:
                raise RuntimeError("Monitoring is already running.")

            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._monitor_loop,
                args=(stop_event,),
                name="OrganizerWatcher",
                daemon=True,
            )
            self._stop_event = stop_event
            self._thread = thread
            self._running = True

        thread.start()
        self.bus.publish(
            MonitoringStartedEvent(watch_directory=str(self.config.resolved_watch_directory))
        )

    def _monitor_loop(self, stop_event: threading.Event) -> None:
        """Background worker running the core monitoring loop."""
        try:
            self.organizer.start_monitoring(stop_event)
        except Exception as exc:  # noqa: BLE001 - keep the watcher thread alive-safe
            self.logger.log_error(filename="", error_message=f"Watcher stopped due to error: {exc}")
        finally:
            with self._lock:
                self._running = False

    def stop(self) -> bool:
        """Stops live monitoring and waits for the watcher thread to finish.

        Returns:
            True if monitoring was running and has now been stopped.
        """
        with self._lock:
            if not self._running:
                return False
            stop_event = self._stop_event
            thread = self._thread
            self._running = False

        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

        with self._lock:
            self._stop_event = None
            self._thread = None

        self.bus.publish(MonitoringStoppedEvent())
        return True

    def organize_existing(self) -> Dict[str, int]:
        """Organizes existing files in the watch directory once and returns stats."""
        stats = self.organizer.organize_existing_files()
        self.bus.publish(BatchCompleteEvent(stats=dict(stats)))
        return stats

    def organize_file(self, path: Union[Path, str]) -> bool:
        """Organizes a single file immediately; per-file events are emitted too."""
        return self.organizer.organize_single_file(Path(path))

    def status(self) -> Dict[str, Any]:
        """Returns runtime status and metrics for frontend display."""
        status = self.organizer.get_status()
        status["monitoring"] = self.is_running
        return status