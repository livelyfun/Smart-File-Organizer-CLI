"""Backward-compatible re-export shim for the organizer module.

The engine now lives in ``smart_organizer.core.organizer``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.organizer import SmartFileOrganizer

__all__ = ["SmartFileOrganizer"]