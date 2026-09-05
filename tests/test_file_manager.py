"""Unit tests for duplicate-safe file manager."""

from pathlib import Path
import pytest

from smart_organizer.file_manager import (
    FileManager,
    generate_unique_destination_path,
    split_stem_and_suffix,
)


def test_split_stem_and_suffix():
    assert split_stem_and_suffix("photo.jpg") == ("photo", ".jpg")
    assert split_stem_and_suffix("archive.tar.gz") == ("archive", ".tar.gz")
    assert split_stem_and_suffix("backup.tar.bz2") == ("backup", ".tar.bz2")
    assert split_stem_and_suffix("LICENSE") == ("LICENSE", "")


def test_unique_destination_generation(tmp_path: Path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    # When no collision exists
    p1 = generate_unique_destination_path(dest_dir, "photo.jpg")
    assert p1.name == "photo.jpg"

    # Create photo.jpg
    p1.touch()

    # Next collision
    p2 = generate_unique_destination_path(dest_dir, "photo.jpg")
    assert p2.name == "photo (1).jpg"
    p2.touch()

    # Next collision
    p3 = generate_unique_destination_path(dest_dir, "photo.jpg")
    assert p3.name == "photo (2).jpg"


def test_unique_destination_tar_gz(tmp_path: Path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    p1 = generate_unique_destination_path(dest_dir, "archive.tar.gz")
    assert p1.name == "archive.tar.gz"
    p1.touch()

    p2 = generate_unique_destination_path(dest_dir, "archive.tar.gz")
    assert p2.name == "archive (1).tar.gz"


def test_unique_destination_unicode_and_spaces(tmp_path: Path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    name = "تقرير مالي ٢٠٢٦ 🚀.pdf"
    p1 = generate_unique_destination_path(dest_dir, name)
    assert p1.name == name
    p1.touch()

    p2 = generate_unique_destination_path(dest_dir, name)
    assert p2.name == "تقرير مالي ٢٠٢٦ 🚀 (1).pdf"


def test_unique_destination_no_extension(tmp_path: Path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    name = "LICENSE"
    p1 = generate_unique_destination_path(dest_dir, name)
    assert p1.name == "LICENSE"
    p1.touch()

    p2 = generate_unique_destination_path(dest_dir, name)
    assert p2.name == "LICENSE (1)"


def test_safe_move_success(file_manager: FileManager, tmp_path: Path):
    src = tmp_path / "test.txt"
    src.write_text("hello world")
    dest_dir = tmp_path / "Documents"

    result = file_manager.safe_move(src, dest_dir, category="Documents")
    assert result.success is True
    assert result.destination_path == dest_dir / "test.txt"
    assert not src.exists()
    assert result.destination_path.read_text() == "hello world"


def test_safe_move_with_duplicate(file_manager: FileManager, tmp_path: Path):
    dest_dir = tmp_path / "Images"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "photo.jpg").write_text("existing photo")

    src = tmp_path / "photo.jpg"
    src.write_text("new photo")

    result = file_manager.safe_move(src, dest_dir, category="Images")
    assert result.success is True
    assert result.destination_path == dest_dir / "photo (1).jpg"
    assert (dest_dir / "photo.jpg").read_text() == "existing photo"
    assert (dest_dir / "photo (1).jpg").read_text() == "new photo"


def test_safe_move_nonexistent_file(file_manager: FileManager, tmp_path: Path):
    src = tmp_path / "ghost.txt"
    dest_dir = tmp_path / "Documents"

    result = file_manager.safe_move(src, dest_dir, category="Documents")
    assert result.success is False
    assert "does not exist" in result.error_message


def test_safe_move_source_is_directory(file_manager: FileManager, tmp_path: Path):
    src = tmp_path / "some_dir"
    src.mkdir()
    dest_dir = tmp_path / "Documents"

    result = file_manager.safe_move(src, dest_dir, category="Documents")
    assert result.success is False
    assert "not a regular file" in result.error_message
