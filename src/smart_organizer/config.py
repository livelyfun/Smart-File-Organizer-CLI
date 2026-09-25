"""Backward-compatible re-export shim for the configuration module.

The engine now lives in ``smart_organizer.core.config``.
This module exists so existing imports keep working.
"""

from smart_organizer.core.config import (
    DEFAULT_TEMPORARY_EXTENSIONS,
    AppConfig,
    get_default_config_path,
    load_config,
    save_config,
    validate_config_data,
)

__all__ = [
    "DEFAULT_TEMPORARY_EXTENSIONS",
    "AppConfig",
    "get_default_config_path",
    "load_config",
    "save_config",
    "validate_config_data",
]