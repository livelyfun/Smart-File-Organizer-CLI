"""Application layer for Smart File Organizer.

Shared services consumed by both the CLI and the desktop GUI. Frontends
import from here; the modules underneath stay an implementation detail.
"""

from smart_organizer.application.services import (
    BatchCompleteEvent,
    EventBus,
    EventCallback,
    EventEmitterLogger,
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
    MonitoringStartedEvent,
    MonitoringStoppedEvent,
    OrganizerEvent,
    OrganizerService,
)

__all__ = [
    "BatchCompleteEvent",
    "EventBus",
    "EventCallback",
    "EventEmitterLogger",
    "FileErrorEvent",
    "FileOrganizedEvent",
    "FileSkippedEvent",
    "InfoEvent",
    "MonitoringStartedEvent",
    "MonitoringStoppedEvent",
    "OrganizerEvent",
    "OrganizerService",
]
