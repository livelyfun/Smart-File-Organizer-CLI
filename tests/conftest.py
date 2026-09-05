"""Pytest configuration and shared fixtures for Smart File Organizer tests."""

from pathlib import Path
import pytest

from smart_organizer.classifier import FileClassifier
from smart_organizer.config import AppConfig
from smart_organizer.file_manager import FileManager


@pytest.fixture
def temp_watch_dir(tmp_path: Path) -> Path:
    """Provides an isolated temporary directory simulating ~/Downloads."""
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return downloads_dir


@pytest.fixture
def sample_config(temp_watch_dir: Path, tmp_path: Path) -> AppConfig:
    """Provides an AppConfig targeting the isolated temp directory."""
    log_file = tmp_path / "logs" / "test_organizer.log"
    return AppConfig(
        watch_directory=str(temp_watch_dir),
        stability_delay=0.01,
        stability_checks=2,
        max_stability_wait=1.0,
        ignore_hidden_files=True,
        log_file=str(log_file),
    )


@pytest.fixture
def classifier() -> FileClassifier:
    return FileClassifier()


@pytest.fixture
def file_manager() -> FileManager:
    return FileManager(create_dirs=True)
