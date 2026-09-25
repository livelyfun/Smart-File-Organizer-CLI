"""Logging module for Smart File Organizer.

Handles both clean terminal reporting and structured file logging.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class OrganizerLogger:
    """Manages application logging for terminal display and file logs."""

    def __init__(self, log_file: Optional[Path] = None, quiet: bool = False):
        self.log_file = log_file
        self.quiet = quiet

        self._logger = logging.getLogger("SmartFileOrganizer")
        self._logger.setLevel(logging.INFO)
        self._logger.handlers.clear()

        if self.log_file:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
                # Format: YYYY-MM-DD HH:MM:SS | STATUS | filename | details
                formatter = logging.Formatter(
                    "%(asctime)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)
            except Exception as exc:
                sys.stderr.write(f"Warning: Could not initialize log file {self.log_file}: {exc}\n")

    def _get_time_str(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def log_organized(
        self,
        filename: str,
        category: str,
        dest_rel_path: str,
        full_dest_path: Optional[str] = None,
    ) -> None:
        """Logs a successful file organization action."""
        self._logger.info(f"ORGANIZED | {filename} | {dest_rel_path}")

        if not self.quiet:
            time_str = self._get_time_str()
            print(f"[{time_str}] {filename} → {category}")

    def log_skipped(self, filename: str, reason: str) -> None:
        """Logs a skipped file."""
        self._logger.info(f"SKIPPED | {filename} | {reason}")

        if not self.quiet:
            time_str = self._get_time_str()
            print(f"[{time_str}] {filename} → SKIPPED ({reason})")

    def log_error(
        self,
        filename: str,
        error_message: str,
        category: Optional[str] = None,
    ) -> None:
        """Logs a file organization error."""
        cat_str = f" ({category})" if category else ""
        self._logger.error(f"ERROR | {filename}{cat_str} | {error_message}")

        if not self.quiet:
            time_str = self._get_time_str()
            print(f"[{time_str}] {filename} → ERROR: {error_message}", file=sys.stderr)

    def log_info(self, message: str) -> None:
        """General information logging."""
        self._logger.info(f"INFO | {message}")


# Global logger instance
_logger_instance: Optional[OrganizerLogger] = None


def setup_logger(log_file: Optional[Path] = None, quiet: bool = False) -> OrganizerLogger:
    """Initializes and returns the global OrganizerLogger."""
    global _logger_instance
    _logger_instance = OrganizerLogger(log_file=log_file, quiet=quiet)
    return _logger_instance


def get_logger() -> OrganizerLogger:
    """Returns the current logger instance or creates a default one."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = OrganizerLogger()
    return _logger_instance
