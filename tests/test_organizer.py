"""Unit tests for SmartFileOrganizer service."""

from pathlib import Path
import pytest

from smart_organizer.config import AppConfig
from smart_organizer.logger import setup_logger
from smart_organizer.organizer import SmartFileOrganizer


def test_organize_existing_files_comprehensive(sample_config: AppConfig, temp_watch_dir: Path):
    files_to_create = {
        "photo.jpg": "image content",
        "movie.mp4": "video content",
        "song.mp3": "audio content",
        "doc.pdf": "pdf content",
        "notes.txt": "text content",
        "sheet.xlsx": "excel content",
        "slides.pptx": "powerpoint content",
        "archive.zip": "zip content",
        "archive.tar.gz": "tar gz content",
        "script.py": "python code",
        "app.deb": "debian package",
        "other.xyz": "misc file",
        ".hidden.txt": "hidden file",
        "active_download.crdownload": "incomplete download",
    }

    for name, content in files_to_create.items():
        (temp_watch_dir / name).write_text(content)

    # Subfolder with file that should not be touched
    sub_dir = temp_watch_dir / "Images"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "pre_existing.png").write_text("already organized")

    logger = setup_logger(sample_config.resolved_log_file, quiet=True)
    organizer = SmartFileOrganizer(sample_config, logger=logger)

    stats = organizer.organize_existing_files()

    assert stats["organized"] == 12
    assert stats["skipped"] >= 2  # hidden file + .crdownload
    assert stats["errors"] == 0

    # Verify destinations
    assert (temp_watch_dir / "Images" / "photo.jpg").exists()
    assert (temp_watch_dir / "Videos" / "movie.mp4").exists()
    assert (temp_watch_dir / "Audio" / "song.mp3").exists()
    assert (temp_watch_dir / "PDFs" / "doc.pdf").exists()
    assert (temp_watch_dir / "Documents" / "notes.txt").exists()
    assert (temp_watch_dir / "Spreadsheets" / "sheet.xlsx").exists()
    assert (temp_watch_dir / "Presentations" / "slides.pptx").exists()
    assert (temp_watch_dir / "Archives" / "archive.zip").exists()
    assert (temp_watch_dir / "Archives" / "archive.tar.gz").exists()
    assert (temp_watch_dir / "Code" / "script.py").exists()
    assert (temp_watch_dir / "Applications" / "app.deb").exists()
    assert (temp_watch_dir / "Others" / "other.xyz").exists()

    # Verify untouched files
    assert (temp_watch_dir / ".hidden.txt").exists()
    assert (temp_watch_dir / "active_download.crdownload").exists()
    assert (temp_watch_dir / "Images" / "pre_existing.png").exists()


def test_organize_existing_duplicates(sample_config: AppConfig, temp_watch_dir: Path):
    images_dir = temp_watch_dir / "Images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / "photo.jpg").write_text("version 1")

    # Put another photo.jpg in root
    (temp_watch_dir / "photo.jpg").write_text("version 2")

    logger = setup_logger(sample_config.resolved_log_file, quiet=True)
    organizer = SmartFileOrganizer(sample_config, logger=logger)
    organizer.organize_existing_files()

    assert (images_dir / "photo.jpg").read_text() == "version 1"
    assert (images_dir / "photo (1).jpg").read_text() == "version 2"


def test_organize_missing_directory(tmp_path: Path):
    missing_dir = tmp_path / "non_existent_folder"
    cfg = AppConfig(watch_directory=str(missing_dir))
    organizer = SmartFileOrganizer(cfg)
    stats = organizer.organize_existing_files()
    assert stats["errors"] == 1
