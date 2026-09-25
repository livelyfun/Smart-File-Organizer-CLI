"""Domain events emitted by the shared application services.

Frontends (CLI printer, GUI widgets, tests) subscribe through the
:class:`~smart_organizer.application.services.event_bus.EventBus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OrganizerEvent:
    """Base class for all organizer events."""

    name: str = field(init=False)


@dataclass(frozen=True)
class FileOrganizedEvent(OrganizerEvent):
    """Emitted after a file is successfully moved into a category."""

    filename: str
    category: str
    dest_rel_path: str
    full_dest_path: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "file_organized")


@dataclass(frozen=True)
class FileSkippedEvent(OrganizerEvent):
    """Emitted when a file is deliberately skipped (hidden, temporary, ...)."""

    filename: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "file_skipped")


@dataclass(frozen=True)
class FileErrorEvent(OrganizerEvent):
    """Emitted when a file could not be organized."""

    filename: str
    error_message: str
    category: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "file_error")


@dataclass(frozen=True)
class MonitoringStartedEvent(OrganizerEvent):
    """Emitted when live directory monitoring begins."""

    watch_directory: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "monitoring_started")


@dataclass(frozen=True)
class MonitoringStoppedEvent(OrganizerEvent):
    """Emitted when live directory monitoring stops."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "monitoring_stopped")


@dataclass(frozen=True)
class BatchCompleteEvent(OrganizerEvent):
    """Emitted when a batch organization pass finishes."""

    stats: Dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "batch_complete")


@dataclass(frozen=True)
class InfoEvent(OrganizerEvent):
    """General informational message from the application layer."""

    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "info")


__all__ = [
    "BatchCompleteEvent",
    "FileErrorEvent",
    "FileOrganizedEvent",
    "FileSkippedEvent",
    "InfoEvent",
    "MonitoringStartedEvent",
    "MonitoringStoppedEvent",
    "OrganizerEvent",
]