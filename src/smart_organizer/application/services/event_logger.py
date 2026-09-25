"""Logger adapter that converts organizer log calls into bus events.

Implements the same protocol as the core ``OrganizerLogger`` so the
engine's ``SmartFileOrganizer`` can emit structured events without
producing any console output.
"""

from __future__ import annotations

from typing import Optional

from smart_organizer.application.services.event_bus import EventBus
from smart_organizer.application.services.events import (
    BatchCompleteEvent,
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
)
from smart_organizer.core.logger import OrganizerLoggerProtocol


class EventEmitterLogger:
    """Duck-typed ``OrganizerLogger`` that publishes events instead of printing.

    Optionally forwards to a core :class:`OrganizerLogger` (e.g. a file logger)
    for persistent storage while still emitting structured events.
    """

    def __init__(
        self,
        bus: EventBus,
        file_logger: Optional[OrganizerLoggerProtocol] = None,
    ) -> None:
        self.bus = bus
        self.file_logger = file_logger

    def log_organized(
        self,
        filename: str,
        category: str,
        dest_rel_path: str,
        full_dest_path: Optional[str] = None,
    ) -> None:
        self.bus.publish(
            FileOrganizedEvent(
                filename=filename,
                category=category,
                dest_rel_path=dest_rel_path,
                full_dest_path=full_dest_path,
            )
        )
        if self.file_logger:
            self.file_logger.log_organized(
                filename=filename,
                category=category,
                dest_rel_path=dest_rel_path,
                full_dest_path=full_dest_path,
            )

    def log_skipped(self, filename: str, reason: str) -> None:
        self.bus.publish(FileSkippedEvent(filename=filename, reason=reason))
        if self.file_logger:
            self.file_logger.log_skipped(filename, reason)

    def log_error(
        self,
        filename: str,
        error_message: str,
        category: Optional[str] = None,
    ) -> None:
        self.bus.publish(
            FileErrorEvent(
                filename=filename,
                error_message=error_message,
                category=category,
            )
        )
        if self.file_logger:
            self.file_logger.log_error(filename, error_message, category=category)

    def log_info(self, message: str) -> None:
        self.bus.publish(InfoEvent(message=message))
        if self.file_logger:
            self.file_logger.log_info(message)

    def log_batch_complete(self, stats: dict) -> None:
        """Emits a batch completion event with the given stats."""
        self.bus.publish(BatchCompleteEvent(stats=dict(stats)))