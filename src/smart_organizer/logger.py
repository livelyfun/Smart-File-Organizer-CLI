"""Backward-compatible re-export shim for the logger module.

The engine now lives in ``smart_organizer.core.logger``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.logger import (
    OrganizerLogger,
    OrganizerLoggerProtocol,
    get_logger,
    setup_logger,
)

__all__ = [
    "OrganizerLogger",
    "OrganizerLoggerProtocol",
    "get_logger",
    "setup_logger",
]
