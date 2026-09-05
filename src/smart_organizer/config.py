"""Configuration module for Smart File Organizer.

Handles loading, validating, creating default configuration, and managing cross-platform paths.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from smart_organizer.platform_utils import (
    expand_path,
    get_config_dir,
    get_default_downloads_dir,
    get_log_dir,
)

DEFAULT_TEMPORARY_EXTENSIONS = [
    ".crdownload",
    ".part",
    ".partial",
    ".download",
    ".tmp",
    ".crswap",
]


@dataclass
class AppConfig:
    """Application configuration container."""
    watch_directory: str = field(default_factory=lambda: str(get_default_downloads_dir()))
    stability_delay: float = 2.0
    stability_checks: int = 2
    max_stability_wait: float = 60.0
    ignore_hidden_files: bool = True
    temporary_extensions: List[str] = field(default_factory=lambda: list(DEFAULT_TEMPORARY_EXTENSIONS))
    log_file: Optional[str] = field(default_factory=lambda: str(get_log_dir() / "organizer.log"))
    custom_categories: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def resolved_watch_directory(self) -> Path:
        """Returns the fully resolved Path for the watch directory."""
        return expand_path(self.watch_directory)

    @property
    def resolved_log_file(self) -> Optional[Path]:
        """Returns the fully resolved Path for the log file, or None."""
        if not self.log_file:
            return None
        return expand_path(self.log_file)

    def to_dict(self) -> Dict[str, Any]:
        """Converts configuration to a dictionary suitable for JSON serialization."""
        return asdict(self)


def get_default_config_path() -> Path:
    """Returns the default configuration file path."""
    return get_config_dir() / "config.json"


def validate_config_data(data: Dict[str, Any]) -> None:
    """Validates configuration keys, formats, and value ranges.

    Raises:
        ValueError: If any setting is invalid.
    """
    if "watch_directory" in data:
        if not isinstance(data["watch_directory"], str) or not data["watch_directory"].strip():
            raise ValueError("Configuration 'watch_directory' must be a non-empty string.")

    if "stability_delay" in data:
        delay = data["stability_delay"]
        if not isinstance(delay, (int, float)) or delay <= 0:
            raise ValueError("Configuration 'stability_delay' must be a positive number.")

    if "stability_checks" in data:
        checks = data["stability_checks"]
        if not isinstance(checks, int) or checks < 1:
            raise ValueError("Configuration 'stability_checks' must be an integer >= 1.")

    if "max_stability_wait" in data:
        max_wait = data["max_stability_wait"]
        if not isinstance(max_wait, (int, float)) or max_wait <= 0:
            raise ValueError("Configuration 'max_stability_wait' must be a positive number.")

    if "ignore_hidden_files" in data:
        if not isinstance(data["ignore_hidden_files"], bool):
            raise ValueError("Configuration 'ignore_hidden_files' must be a boolean.")

    if "temporary_extensions" in data:
        temp_exts = data["temporary_extensions"]
        if not isinstance(temp_exts, list) or not all(isinstance(x, str) for x in temp_exts):
            raise ValueError("Configuration 'temporary_extensions' must be a list of extension strings.")

    if "log_file" in data and data["log_file"] is not None:
        if not isinstance(data["log_file"], str):
            raise ValueError("Configuration 'log_file' must be a string path or null.")

    if "custom_categories" in data:
        if not isinstance(data["custom_categories"], dict):
            raise ValueError("Configuration 'custom_categories' must be a dictionary.")
        for cat, exts in data["custom_categories"].items():
            if not isinstance(cat, str) or not isinstance(exts, list):
                raise ValueError(f"Category '{cat}' must map to a list of extension strings.")


def save_config(config: AppConfig, path: Optional[Path] = None) -> Path:
    """Saves configuration to JSON file."""
    config_file = path or get_default_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    return config_file


def load_config(
    config_path: Optional[str | Path] = None,
    watch_dir_override: Optional[str | Path] = None,
    auto_create_default: bool = True,
) -> AppConfig:
    """Loads configuration from specified or default location, applying overrides.

    If no config file exists and auto_create_default is True, a default config
    file is created in the standard configuration directory.
    """
    config = AppConfig()

    target_path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()

    if target_path.is_file():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file {target_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Config file content must be a JSON object: {target_path}")

        validate_config_data(data)

        if "watch_directory" in data:
            config.watch_directory = data["watch_directory"]
        if "stability_delay" in data:
            config.stability_delay = float(data["stability_delay"])
        if "stability_checks" in data:
            config.stability_checks = int(data["stability_checks"])
        if "max_stability_wait" in data:
            config.max_stability_wait = float(data["max_stability_wait"])
        if "ignore_hidden_files" in data:
            config.ignore_hidden_files = bool(data["ignore_hidden_files"])
        if "temporary_extensions" in data:
            config.temporary_extensions = list(data["temporary_extensions"])
        if "log_file" in data:
            config.log_file = data["log_file"]
        if "custom_categories" in data:
            config.custom_categories = data["custom_categories"]

    elif config_path:
        # Explicitly requested config file that does not exist
        raise FileNotFoundError(f"Specified configuration file not found: {target_path}")

    elif auto_create_default:
        # Auto-create default configuration on first run
        try:
            save_config(config, target_path)
        except Exception:
            pass  # Fall back to in-memory defaults if filesystem is read-only

    if watch_dir_override:
        config.watch_directory = str(watch_dir_override)

    return config
