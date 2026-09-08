"""Unit tests for watchdog event filtering."""

from pathlib import Path
import pytest

from smart_organizer.classifier import FileClassifier
from smart_organizer.config import AppConfig
from smart_organizer.watcher import DownloadEventHandler


def _make_handler(watch_dir: Path, dispatched: list) -> DownloadEventHandler:
    config = AppConfig(
        watch_directory=str(watch_dir),
        ignore_hidden_files=True,
    )
    classifier = FileClassifier()

    def on_ready(path: Path):
        dispatched.append(path)

    return DownloadEventHandler(config, classifier, on_ready)


def test_watcher_event_handler_ignore_rules(tmp_path: Path):
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    images_dir = watch_dir / "Images"
    images_dir.mkdir()

    handler = _make_handler(watch_dir, [])

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
    assert handler.should_ignore(watch_dir / "file.crswap") is True


class _FakeEvent:
    """Minimal fake watchdog event."""
    def __init__(self, src_path: str, dest_path: str = "", is_directory: bool = False):
        self.src_path = src_path
        self.dest_path = dest_path
        self.is_directory = is_directory


def test_on_moved_crdownload_to_final(tmp_path: Path):
    """A .crdownload → .jpg rename should trigger processing of the final path."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()

    dispatched_paths = []

    config = AppConfig(
        watch_directory=str(watch_dir),
        ignore_hidden_files=True,
        stability_delay=0.01,
        stability_checks=1,
    )
    classifier = FileClassifier()

    # Capture paths that reach _handle_path_candidate
    handled = []

    def fake_on_ready(path: Path):
        dispatched_paths.append(path)

    handler = DownloadEventHandler(config, classifier, fake_on_ready)

    # Intercept _handle_path_candidate to capture what's submitted
    original_handle = handler._handle_path_candidate
    captured = []

    def capturing_handle(path_str):
        captured.append(path_str)
        # Don't actually submit to avoid threading issues in unit test

    handler._handle_path_candidate = capturing_handle

    crdownload_path = str(watch_dir / "movie.mp4.crdownload")
    final_path = str(watch_dir / "movie.mp4")

    event = _FakeEvent(src_path=crdownload_path, dest_path=final_path)
    handler.on_moved(event)

    # The dest_path (final file) should have been forwarded for processing
    assert final_path in captured
    # The src_path should NOT be forwarded
    assert crdownload_path not in captured


def test_on_moved_src_path_cleaned_from_active_files(tmp_path: Path):
    """on_moved should discard the src_path from _active_files (defensive cleanup)."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()

    handler = _make_handler(watch_dir, [])

    src = watch_dir / "file.crdownload"
    dest = watch_dir / "file.pdf"

    # Manually insert src into _active_files to simulate a hypothetical prior registration
    import threading
    with handler._processing_lock:
        handler._active_files.add(src)

    event = _FakeEvent(src_path=str(src), dest_path=str(dest))
    handler.on_moved(event)

    # src_path must have been removed
    with handler._processing_lock:
        assert src not in handler._active_files


def test_on_created_directory_ignored(tmp_path: Path):
    """Directory creation events must be skipped."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()

    dispatched = []
    handler = _make_handler(watch_dir, dispatched)

    handled = []
    handler._handle_path_candidate = lambda p: handled.append(p)

    event = _FakeEvent(src_path=str(watch_dir / "NewFolder"), is_directory=True)
    handler.on_created(event)

    assert handled == []


def test_duplicate_event_deduplication(tmp_path: Path):
    """Two rapid on_created events for the same path should only be processed once."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()

    dispatched = []
    handler = _make_handler(watch_dir, dispatched)

    submitted = []
    original_handle = handler._handle_path_candidate

    def tracking_handle(path_str):
        submitted.append(path_str)
        original_handle(path_str)

    handler._handle_path_candidate = tracking_handle

    path = str(watch_dir / "photo.jpg")
    event = _FakeEvent(src_path=path)

    # First event adds to _active_files and submits
    handler.on_created(event)
    # Second event for the same path should be deduplicated
    handler.on_created(event)

    # Should only have been submitted once
    assert submitted.count(path) == 1
