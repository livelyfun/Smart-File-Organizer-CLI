"""Unit tests for CLI interface."""

import json
import signal
from pathlib import Path
from typing import List

import pytest

from smart_organizer.application import OrganizerService
from smart_organizer.application.services.events import (
    BatchCompleteEvent,
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
    MonitoringStartedEvent,
    MonitoringStoppedEvent,
)
from smart_organizer.cli import build_parser, main, print_event


def test_cli_parser():
    parser = build_parser()
    args = parser.parse_args(["--organize-existing", "-d", "/tmp/test", "-c", "config.json"])
    assert args.organize_existing is True
    assert args.watch_directory == "/tmp/test"
    assert args.config_file == "config.json"


def test_cli_status(capsys):
    ret = main(["--status"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Smart File Organizer" in captured.out
    assert "Watch Directory" in captured.out


def test_cli_organize_existing(tmp_path: Path, capsys):
    test_dir = tmp_path / "downloads"
    test_dir.mkdir()
    (test_dir / "sample.pdf").write_text("dummy pdf")

    ret = main(["--organize-existing", "--watch-directory", str(test_dir)])
    assert ret == 0

    assert (test_dir / "PDFs" / "sample.pdf").exists()


def test_cli_missing_watch_directory(tmp_path: Path, capsys):
    missing_dir = tmp_path / "non_existent_folder"
    ret = main(["--watch-directory", str(missing_dir)])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Watch directory does not exist" in captured.err


def test_print_event_renders_each_outcome(capsys):
    print_event(
        FileOrganizedEvent(
            filename="photo.jpg",
            category="Images",
            dest_rel_path="Images/photo.jpg",
        )
    )
    print_event(FileSkippedEvent(filename="movie.mp4.crdownload", reason="temporary download"))
    print_event(FileErrorEvent(filename="locked.bin", error_message="Permission denied"))
    print_event(InfoEvent(message="scan finished"))

    captured = capsys.readouterr()
    assert "photo.jpg \u2192 Images" in captured.out
    assert "movie.mp4.crdownload \u2192 SKIPPED (temporary download)" in captured.out
    assert "scan finished" in captured.out
    assert "locked.bin \u2192 ERROR: Permission denied" in captured.err


def test_print_event_ignores_monitoring_lifecycle(capsys):
    """The CLI prints its own banner, so lifecycle events must stay silent."""
    print_event(MonitoringStartedEvent(watch_directory="/tmp"))
    print_event(MonitoringStoppedEvent())
    print_event(BatchCompleteEvent(stats={"organized": 1}))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_cli_organize_existing_reports_each_file_exactly_once(tmp_path: Path, capsys):
    """A file must not be printed by both the file logger and the subscriber."""
    test_dir = tmp_path / "downloads"
    test_dir.mkdir()
    (test_dir / "report.pdf").write_text("x")
    (test_dir / "holiday.jpg").write_text("y")

    ret = main(["--organize-existing", "--watch-directory", str(test_dir)])
    assert ret == 0

    out = capsys.readouterr().out
    assert out.count("report.pdf \u2192 PDFs") == 1
    assert out.count("holiday.jpg \u2192 Images") == 1


def test_cli_organize_existing_uses_the_service(tmp_path: Path, monkeypatch):
    calls: List[str] = []

    def fake_organize_existing(self):
        calls.append("organize_existing")
        self.bus.publish(BatchCompleteEvent(stats={"organized": 0, "skipped": 0, "failed": 2}))
        return {"organized": 0, "skipped": 0, "failed": 2}

    monkeypatch.setattr(OrganizerService, "organize_existing", fake_organize_existing)

    ret = main(["--organize-existing", "--watch-directory", str(tmp_path)])

    assert calls == ["organize_existing"]
    assert ret == 1


def test_cli_organize_existing_still_writes_log_file(tmp_path: Path):
    """Routing through the event bus must not drop persistent logging."""
    test_dir = tmp_path / "downloads"
    test_dir.mkdir()
    (test_dir / "invoice.pdf").write_text("x")
    log_file = tmp_path / "organizer.log"
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "watch_directory": str(test_dir),
                "stability_delay": 0.01,
                "stability_checks": 2,
                "max_stability_wait": 1.0,
                "log_file": str(log_file),
            }
        ),
        encoding="utf-8",
    )

    ret = main(["--organize-existing", "--config-file", str(config_file)])

    assert ret == 0
    assert (test_dir / "PDFs" / "invoice.pdf").exists()
    logged = log_file.read_text(encoding="utf-8")
    assert "ORGANIZED" in logged
    assert "invoice.pdf" in logged


def test_cli_live_mode_exits_zero_when_interrupted(tmp_path: Path, monkeypatch, capsys):
    handlers = {}
    real_signal = signal.signal

    def capture_signal(sig, handler):
        handlers[sig] = handler
        return real_signal(sig, handler)

    monkeypatch.setattr(signal, "signal", capture_signal)

    def fake_start(self):
        handlers[signal.SIGINT](signal.SIGINT, None)

    monkeypatch.setattr(OrganizerService, "start", fake_start)

    ret = main(["--watch-directory", str(tmp_path)])

    assert ret == 0
    out = capsys.readouterr().out
    assert "Stopping Smart File Organizer..." in out
    assert "Stopped cleanly." in out


def test_cli_live_mode_reports_failure_when_watcher_dies(tmp_path: Path, monkeypatch, capsys):
    """If the watcher ends on its own, the CLI must not hang or claim success."""

    def fake_start(self):
        self.bus.publish(MonitoringStoppedEvent())

    monkeypatch.setattr(OrganizerService, "start", fake_start)

    ret = main(["--watch-directory", str(tmp_path)])

    assert ret == 1
    assert "Stopped cleanly." in capsys.readouterr().out


class TestShutdownHandlers:
    """The stop signals the CLI registers must cover the platform's."""

    def test_registers_sigint_and_sigterm(self, monkeypatch):
        from smart_organizer.cli import install_shutdown_handlers

        registered = {}
        monkeypatch.setattr(
            signal, "signal", lambda sig, handler: registered.setdefault(sig, handler)
        )

        def handler(signum, frame):  # pragma: no cover - never invoked
            pass

        install_shutdown_handlers(handler)

        assert signal.SIGINT in registered
        assert signal.SIGTERM in registered
        assert registered[signal.SIGINT] is handler
        assert registered[signal.SIGTERM] is handler

    @pytest.mark.skipif(
        not hasattr(signal, "SIGBREAK"), reason="SIGBREAK is Windows-only"
    )
    def test_registers_sigbreak_on_windows(self, monkeypatch):
        """Ctrl+Break must not kill the process mid-file-move on Windows."""
        from smart_organizer.cli import install_shutdown_handlers

        registered = {}
        monkeypatch.setattr(
            signal, "signal", lambda sig, handler: registered.setdefault(sig, handler)
        )

        def handler(signum, frame):  # pragma: no cover - never invoked
            pass

        handled = install_shutdown_handlers(handler)

        assert signal.SIGBREAK in registered
        assert signal.SIGBREAK in handled
        assert registered[signal.SIGBREAK] is handler
