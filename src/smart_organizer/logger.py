"""Backward-compatible re-export shim for the logger module.

The engine now lives in ``smart_organizer.core.logger``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.logger import OrganizerLogger, get_logger, setup_logger

__all__ = ["OrganizerLogger", "get_logger", "setup_logger"]