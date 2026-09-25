"""Backward-compatible re-export shim for the stability module.

The engine now lives in ``smart_organizer.core.stability``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.stability import wait_for_file_stability

__all__ = ["wait_for_file_stability"]