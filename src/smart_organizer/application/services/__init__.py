"""Shared application services.

Coordinating services sit on top of the core engine and expose a
frontend-agnostic API plus structured events. Both the CLI and the
desktop GUI are clients of this package and nothing below it.
"""

from smart_organizer.application.services.application_service import OrganizerService
from smart_organizer.application.services.event_bus import EventBus, EventCallback
from smart_organizer.application.services.event_logger import EventEmitterLogger
from smart_organizer.application.services.events import (
    BatchCompleteEvent,
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
    MonitoringStartedEvent,
    MonitoringStoppedEvent,
    OrganizerEvent,
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
