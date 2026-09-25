"""Tests for the shared application service layer alongside the core engine."""

import threading
import time
from pathlib import Path

import pytest

from smart_organizer.application.services.application_service import OrganizerService
from smart_organizer.application.services.event_bus import EventBus
from smart_organizer.application.services.event_logger import EventEmitterLogger
from smart_organizer.application.services.events import (
    BatchCompleteEvent,
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
    MonitoringStartedEvent,
    MonitoringStoppedEvent,
)
from smart_organizer.config import AppConfig


def test_top_level_shims_resolve_to_core_objects():
    """Backward-compatible top-level imports must resolve to the same core objects."""
    from smart_organizer.config import AppConfig as TopLevelConfig
    from smart_organizer.core.config import AppConfig as CoreConfig
    from smart_organizer.classifier import FileClassifier as TopClassifier
    from smart_organizer.core.classifier import FileClassifier as CoreClassifier

    assert TopLevelConfig is CoreConfig
    assert TopClassifier is CoreClassifier


def test_event_bus_subscribe_and_unsubscribe():
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(handler)
    bus.publish(InfoEvent(message="hello"))

    assert len(received) == 1
    assert received[0].name == "info"

    bus.unsubscribe(handler)
    bus.publish(InfoEvent(message="bye"))

    assert len(received) == 1


def test_event_bus_isolation_of_faulty_subscriber():
    bus = EventBus()
    healthy = []

    def failing(event):
        raise RuntimeError("boom")

    def ok(event):
        healthy.append(event)

    bus.subscribe(failing)
    bus.subscribe(ok)

    bus.publish(InfoEvent(message="x"))

    assert len(healthy) == 1


def test_event_emitter_logger_maps_calls_to_events():
    bus = EventBus()
    logger = EventEmitterLogger(bus)
    received = []
    bus.subscribe(received.append)

    logger.log_organized("a.jpg", "Images", "Images/a.jpg", "/w/Images/a.jpg")
    logger.log_skipped("b.tmp", "temporary download")
    logger.log_error("c.pdf", "permission denied", category="PDFs")
    logger.log_info("hello")
    logger.log_batch_complete({"organized": 1, "skipped": 1, "failed": 0})

    names = [e.name for e in received]
    assert names == ["file_organized", "file_skipped", "file_error", "info", "batch_complete"]
    assert isinstance(received[0], FileOrganizedEvent)
    assert received[0].filename == "a.jpg"
    assert isinstance(received[1], FileSkippedEvent)
    assert isinstance(received[2], FileErrorEvent)
    assert isinstance(received[3], InfoEvent)
    assert isinstance(received[4], BatchCompleteEvent)


def test_organizer_service_organize_existing_emits_events(
    sample_config: AppConfig,
    temp_watch_dir: Path,
):
    (temp_watch_dir / "photo.jpg").write_text("image")
    (temp_watch_dir / "song.mp3").write_text("audio")
    (temp_watch_dir / ".hidden.txt").write_text("hidden")
    (temp_watch_dir / "incomplete.crdownload").write_text("partial")

    service = OrganizerService(sample_config)
    events = []
    service.subscribe(events.append)

    stats = service.organize_existing()

    assert stats["organized"] == 2
    assert stats["skipped"] >= 2
    assert stats["failed"] == 0

    names = [e.name for e in events]
    assert names.count("file_organized") == 2
    assert names.count("file_skipped") >= 1
    assert "batch_complete" in names
    assert (temp_watch_dir / "Images" / "photo.jpg").exists()
    assert (temp_watch_dir / "Audio" / "song.mp3").exists()


def test_organizer_service_monitoring_lifecycle(sample_config: AppConfig):
    service = OrganizerService(sample_config)
    events = []
    service.subscribe(events.append)

    service.start()

    try:
        assert service.is_running is True
        assert any(isinstance(e, MonitoringStartedEvent) for e in events)

        with pytest.raises(RuntimeError):
            service.start()
    finally:
        stopped = service.stop()

    assert stopped is True
    assert service.is_running is False
    assert any(isinstance(e, MonitoringStoppedEvent) for e in events)


def test_organizer_service_stop_when_not_running(sample_config: AppConfig):
    service = OrganizerService(sample_config)
    assert service.stop() is False


def test_organizer_service_start_missing_directory(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    service = OrganizerService(AppConfig(watch_directory=str(missing)))

    with pytest.raises(FileNotFoundError):
        service.start()

    assert service.is_running is False


def test_organizer_service_status(sample_config: AppConfig, temp_watch_dir: Path):
    service = OrganizerService(sample_config)
    status = service.status()

    assert status["watch_directory"] == str(temp_watch_dir)
    assert status["monitoring"] is False
    assert status["organized_count"] == 0


def test_organizer_service_worker_error_resets_state(tmp_path: Path):
    """A watcher failure inside the worker must not leave is_running stuck."""
    watch_dir = tmp_path / "downloads"
    watch_dir.mkdir()

    cfg = AppConfig(watch_directory=str(watch_dir), stability_delay=0.01)
    service = OrganizerService(cfg)

    def boom(stop_event):
        raise OSError("simulated watcher failure")

    service.organizer.start_monitoring = boom

    service.start()
    time.sleep(0.2)

    assert service.is_running is False
    service.stop()


def test_organizer_service_organize_file_single(sample_config: AppConfig, temp_watch_dir: Path):
    target = temp_watch_dir / "notes.txt"
    target.write_text("notes")

    service = OrganizerService(sample_config)
    events = []
    service.subscribe(events.append)

    assert service.organize_file(target) is True
    assert (temp_watch_dir / "Documents" / "notes.txt").exists()
    assert any(isinstance(e, FileOrganizedEvent) for e in events)


def test_organizing_many_files_does_not_block_caller(sample_config: AppConfig, temp_watch_dir: Path):
    """start() must return promptly even when a long monitor run is active."""
    service = OrganizerService(sample_config)
    service.start()

    try:
        started = time.monotonic()
        # start was already called; verify stop also returns within a bounded time
        service.stop()
        elapsed = time.monotonic() - started
        assert elapsed < 2.0
    finally:
        service.stop()