"""Platform utilities for cross-platform directory and path resolution.

Handles Linux, macOS, and Windows standard directories without hardcoded paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_platform_name() -> str:
    """Returns normalized platform identifier ('linux', 'darwin', 'windows', or 'unknown')."""
    if sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "darwin":
        return "darwin"
    elif sys.platform in ("win32", "cygwin"):
        return "windows"
    return "unknown"


def get_default_downloads_dir() -> Path:
    """Resolves the user's standard Downloads directory across platforms.

    Uses Path.home() as the foundation.
    - Linux: ~/Downloads (or XDG user dir if configured)
    - macOS: ~/Downloads
    - Windows: %USERPROFILE%\\Downloads
    """
    home = Path.home()

    # Check Linux XDG user dirs if available
    if sys.platform.startswith("linux"):
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        user_dirs_file = Path(xdg_config_home) / "user-dirs.dirs"
        if user_dirs_file.is_file():
            try:
                for line in user_dirs_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DOWNLOAD_DIR="):
                        val = line.split("=", 1)[1].strip('"').strip("'")
                        val = val.replace("$HOME", str(home))
                        resolved = Path(val).resolve()
                        if resolved.exists():
                            return resolved
            except Exception:
                pass

    return (home / "Downloads").resolve()


def get_config_dir() -> Path:
    """Returns standard OS-appropriate configuration directory for the application.

    - Linux: ~/.config/smart_organizer (or $XDG_CONFIG_HOME/smart_organizer)
    - macOS: ~/Library/Application Support/SmartFileOrganizer
    - Windows: %APPDATA%\\SmartFileOrganizer
    """
    home = Path.home()
    platform = get_platform_name()

    if platform == "windows":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "SmartFileOrganizer"
        return home / "AppData" / "Roaming" / "SmartFileOrganizer"

    elif platform == "darwin":
        return home / "Library" / "Application Support" / "SmartFileOrganizer"

    else:
        # Linux / Unix / BSD
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "smart_organizer"
        return home / ".config" / "smart_organizer"


def get_log_dir() -> Path:
    """Returns standard OS-appropriate log directory for the application.

    - Linux: ~/.local/state/smart_organizer or ~/.config/smart_organizer/logs
    - macOS: ~/Library/Logs/SmartFileOrganizer
    - Windows: %LOCALAPPDATA%\\SmartFileOrganizer\\Logs
    """
    home = Path.home()
    platform = get_platform_name()

    if platform == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "SmartFileOrganizer" / "Logs"
        return home / "AppData" / "Local" / "SmartFileOrganizer" / "Logs"

    elif platform == "darwin":
        return home / "Library" / "Logs" / "SmartFileOrganizer"

    else:
        # Linux / Unix
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            return Path(xdg_state) / "smart_organizer"
        return home / ".local" / "state" / "smart_organizer"


def expand_path(path_str: str | Path) -> Path:
    """Safely expands '~' and environment variables into an absolute Path."""
    expanded_str = os.path.expandvars(str(path_str))
    return Path(expanded_str).expanduser().resolve()
