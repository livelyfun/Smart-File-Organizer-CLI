"""File Manager module for Smart File Organizer.

Handles safe file operations, destination directory creation, duplicate-safe
filename resolution, and robust error handling.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Known multi-part archive extensions for clean duplicate naming
KNOWN_DOUBLE_EXTENSIONS = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tar.z",
    ".tar.lzma",
)


@dataclass
class MoveResult:
    """Represents the outcome of a file move operation."""
    success: bool
    source_path: Path
    destination_path: Optional[Path] = None
    category: Optional[str] = None
    error_message: Optional[str] = None


def split_stem_and_suffix(filename: str) -> Tuple[str, str]:
    """Splits filename into its base stem and extension, preserving multi-part extensions like .tar.gz."""
    lower_name = filename.lower()
    for double_ext in KNOWN_DOUBLE_EXTENSIONS:
        if lower_name.endswith(double_ext):
            stem = filename[:-len(double_ext)]
            suffix = filename[-len(double_ext):]
            return stem, suffix

    path = Path(filename)
    return path.stem, path.suffix


def generate_unique_destination_path(destination_dir: Path, filename: str) -> Path:
    """Generates a non-conflicting destination file path.

    If `filename` already exists in `destination_dir`, appends ` (1)`, ` (2)`, etc.
    before the extension, preserving Unicode characters and spaces.

    Example:
        photo.jpg -> photo (1).jpg -> photo (2).jpg
        archive.tar.gz -> archive (1).tar.gz -> archive (2).tar.gz
    """
    initial_path = destination_dir / filename
    if not initial_path.exists():
        return initial_path

    stem, suffix = split_stem_and_suffix(filename)

    counter = 1
    while True:
        candidate_name = f"{stem} ({counter}){suffix}"
        candidate_path = destination_dir / candidate_name
        if not candidate_path.exists():
            return candidate_path
        counter += 1


class FileManager:
    """Manages filesystem operations for organizing files safely."""

    def __init__(self, create_dirs: bool = True):
        self.create_dirs = create_dirs

    def get_destination_dir(self, base_dir: Path, category: str) -> Path:
        """Returns the destination directory path for a category."""
        return base_dir / category

    def safe_move(
        self,
        source_path: Path | str,
        destination_dir: Path | str,
        category: Optional[str] = None,
    ) -> MoveResult:
        """Safely moves a file to the destination directory with duplicate protection.

        Args:
            source_path: The file to be moved.
            destination_dir: The target category directory.
            category: Optional name of the category.

        Returns:
            MoveResult with success status and operation details.
        """
        src = Path(source_path)
        dest_dir = Path(destination_dir)

        # 1. Verify source existence and regular file status
        if not src.exists():
            return MoveResult(
                success=False,
                source_path=src,
                category=category,
                error_message=f"Source file does not exist: {src}",
            )

        if not src.is_file():
            return MoveResult(
                success=False,
                source_path=src,
                category=category,
                error_message=f"Source path is not a regular file: {src}",
            )

        # 2. Ensure destination directory exists
        try:
            if self.create_dirs:
                dest_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return MoveResult(
                success=False,
                source_path=src,
                category=category,
                error_message=f"Permission denied creating directory: {dest_dir}",
            )
        except OSError as exc:
            return MoveResult(
                success=False,
                source_path=src,
                category=category,
                error_message=f"Filesystem error creating directory {dest_dir}: {exc}",
            )

        # 3. Generate duplicate-safe target path
        try:
            target_path = generate_unique_destination_path(dest_dir, src.name)
        except Exception as exc:
            return MoveResult(
                success=False,
                source_path=src,
                category=category,
                error_message=f"Failed to generate unique destination filename: {exc}",
            )

        # 4. Perform atomic/safe move using shutil.move (never shell commands)
        try:
            shutil.move(str(src), str(target_path))
            return MoveResult(
                success=True,
                source_path=src,
                destination_path=target_path,
                category=category,
            )
        except PermissionError:
            return MoveResult(
                success=False,
                source_path=src,
                destination_path=target_path,
                category=category,
                error_message="Permission denied while moving file",
            )
        except FileNotFoundError:
            return MoveResult(
                success=False,
                source_path=src,
                destination_path=target_path,
                category=category,
                error_message="File disappeared before move could complete",
            )
        except OSError as exc:
            return MoveResult(
                success=False,
                source_path=src,
                destination_path=target_path,
                category=category,
                error_message=f"Filesystem error during move: {exc}",
            )
