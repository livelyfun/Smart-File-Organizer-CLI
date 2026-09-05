"""Unit tests for watchdog event filtering."""

from pathlib import Path
import pytest

from smart_organizer.classifier import FileClassifier
from smart_organizer.config import AppConfig
from smart_organizer.watcher import DownloadEventHandler


def test_watcher_event_handler_ignore_rules(tmp_path: Path):
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    images_dir = watch_dir / "Images"
    images_dir.mkdir()

    config = AppConfig(
        watch_directory=str(watch_dir),
        ignore_hidden_files=True,
    )
    classifier = FileClassifier()

    dispatched = []

    def on_ready(path: Path):
        dispatched.append(path)

    handler = DownloadEventHandler(config, classifier, on_ready)

    # 1. Root valid file -> NOT ignored
    assert handler.should_ignore(watch_dir / "photo.jpg") is False

    # 2. File in subdirectory -> IGNORED (non-recursive)
    assert handler.should_ignore(images_dir / "nested.jpg") is True

    # 3. Hidden file -> IGNORED
    assert handler.should_ignore(watch_dir / ".hidden.jpg") is True

    # 4. Known category folder name -> IGNORED
    assert handler.should_ignore(watch_dir / "Images") is True
    assert handler.should_ignore(watch_dir / "Videos") is True

    # 5. Temporary extension -> IGNORED
    assert handler.should_ignore(watch_dir / "file.crdownload") is True
    assert handler.should_ignore(watch_dir / "file.part") is True
    assert handler.should_ignore(watch_dir / "file.tmp") is True
    assert handler.should_ignore(watch_dir / "movie.mp4.crdownload") is True
