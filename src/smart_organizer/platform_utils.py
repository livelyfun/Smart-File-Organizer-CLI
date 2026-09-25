"""Backward-compatible re-export shim for the platform utilities module.

The engine now lives in ``smart_organizer.core.platform_utils``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.platform_utils import (
    expand_path,
    get_config_dir,
    get_default_downloads_dir,
    get_log_dir,
    get_platform_name,
)

__all__ = [
    "expand_path",
    "get_config_dir",
    "get_default_downloads_dir",
    "get_log_dir",
    "get_platform_name",
]