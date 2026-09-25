"""Command-line interface for Smart File Organizer.

Handles arguments, displays status messages, and manages process execution.

The CLI is a frontend: it owns no filesystem logic and talks to the
application service layer, rendering whatever the event bus reports.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from datetime import datetime
from typing import Optional, Sequence

from smart_organizer import __version__
from smart_organizer.application import EventBus, OrganizerService
from smart_organizer.application.services.events import (
    FileErrorEvent,
    FileOrganizedEvent,
    FileSkippedEvent,
    InfoEvent,
    MonitoringStoppedEvent,
    OrganizerEvent,
)
from smart_organizer.core.config import AppConfig, get_default_config_path, load_config
from smart_organizer.core.logger import setup_logger


def build_parser() -> argparse.ArgumentParser:
    """Constructs and returns the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="smart-organizer",
        description="Smart File Organizer - Automatically sort downloads into category folders.",
    )
    parser.add_argument(
        "--organize-existing",
        action="store_true",
        help="Organize files already sitting directly inside the watch directory once, then exit.",
    )
    parser.add_argument(
        "--watch-directory",
        "-d",
        type=str,
        default=None,
        metavar="PATH",
        help="Directory to watch or organize (default: OS standard Downloads folder).",
    )
    parser.add_argument(
        "--config-file",
        "-c",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to custom JSON configuration file.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Show current configuration and watch directory accessibility. "
            "Does not report whether the watcher process is running."
        ),
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"Smart File Organizer v{__version__}",
        help="Show program's version number and exit.",
    )
    return parser


def _timestamp() -> str:
    """Returns the current wall-clock time in the console status format."""
    return datetime.now().strftime("%H:%M:%S")


def print_event(event: OrganizerEvent) -> None:
    """Renders a domain event as a console status line.

    Monitoring lifecycle events are intentionally ignored: the CLI prints
    its own banner and shutdown notices so each appears exactly once.
    """
    if isinstance(event, FileOrganizedEvent):
        print(f"[{_timestamp()}] {event.filename} \u2192 {event.category}")
    elif isinstance(event, FileSkippedEvent):
        print(f"[{_timestamp()}] {event.filename} \u2192 SKIPPED ({event.reason})")
    elif isinstance(event, FileErrorEvent):
        print(
            f"[{_timestamp()}] {event.filename} \u2192 ERROR: {event.error_message}",
            file=sys.stderr,
        )
    elif isinstance(event, InfoEvent):
        print(f"[{_timestamp()}] {event.message}")


def display_status(config: AppConfig, custom_config_path: Optional[str] = None) -> None:
    """Displays detailed configuration and directory accessibility status."""
    watch_dir = config.resolved_watch_directory
    exists = watch_dir.exists()

    if exists:
        try:
            # Check write permission
            test_file = watch_dir / ".smart_organizer_probe"
            test_file.touch()
            test_file.unlink()
            dir_status = "Exists (Writable)"
        except Exception:
            dir_status = "Exists (Read-Only / No Write Access)"
    else:
        dir_status = "Missing (Directory does not exist)"

    config_source = custom_config_path if custom_config_path else str(get_default_config_path())

    print(f"\nSmart File Organizer v{__version__} - Configuration & Directory Status\n")
    print(f"  Watch Directory      : {watch_dir} [{dir_status}]")
    print(f"  Configuration File   : {config_source}")
    print(f"  Stability Delay      : {config.stability_delay}s")
    print(f"  Stability Checks     : {config.stability_checks} checks")
    print(f"  Max Stability Wait   : {config.max_stability_wait}s")
    print(f"  Ignore Hidden Files  : {config.ignore_hidden_files}")
    print(f"  Log File             : {config.resolved_log_file or 'None'}")
    print(f"  Temporary Extensions : {', '.join(config.temporary_extensions)}")
    print()
    print("  Note: Runtime metrics (files organized, errors) are only available")
    print("        while the watcher is actively monitoring.")

    if config.custom_categories:
        print("\n  Custom Categories:")
        for cat, exts in config.custom_categories.items():
            print(f"    {cat:<18}: {', '.join(exts)}")
    print()


def _build_service(config: AppConfig) -> OrganizerService:
    """Composes the service with a file logger and a console event renderer.

    The file logger is quiet because every visible line is produced by the
    event subscriber; without this each outcome would be printed twice.
    """
    bus = EventBus()
    service = OrganizerService(
        config,
        bus=bus,
        logger=setup_logger(config.resolved_log_file, quiet=True),
    )
    service.subscribe(print_event)
    return service


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint function."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(
            config_path=args.config_file,
            watch_dir_override=args.watch_directory,
        )
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 1

    if args.status:
        display_status(config, custom_config_path=args.config_file)
        return 0

    watch_dir = config.resolved_watch_directory

    # Verify watch directory existence
    if not watch_dir.exists():
        print(f"\nError: Watch directory does not exist:", file=sys.stderr)
        print(f"  {watch_dir}\n", file=sys.stderr)
        print(
            "Please create this directory or specify an alternative path using:\n"
            "  smart-organizer --watch-directory /path/to/folder\n",
            file=sys.stderr,
        )
        return 1

    service = _build_service(config)

    if args.organize_existing:
        print(f"\nScanning existing files in:")
        print(f"  {watch_dir}\n")

        stats = service.organize_existing()

        print(
            f"\nOrganization complete: {stats['organized']} organized, "
            f"{stats['skipped']} skipped, {stats['failed']} failed.\n"
        )
        return 0 if stats["failed"] == 0 else 1

    # Live Monitoring Mode
    print(f"Smart File Organizer v{__version__}\n")
    print("Watching:")
    print(f"  {watch_dir}\n")
    print("Status:")
    print("  RUNNING\n")
    print("Waiting for new files...")
    print("Press Ctrl+C to stop.\n")

    shutdown = threading.Event()
    interrupted = threading.Event()

    def handle_signal(signum, frame):
        interrupted.set()
        shutdown.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    def wake_on_unexpected_stop(event: OrganizerEvent) -> None:
        if isinstance(event, MonitoringStoppedEvent):
            shutdown.set()

    service.subscribe(wake_on_unexpected_stop)

    try:
        service.start()
    except Exception as exc:
        print(f"\nWatcher Error: {exc}", file=sys.stderr)
        return 1

    while not shutdown.wait(0.5):
        pass

    if interrupted.is_set():
        print("\nStopping Smart File Organizer...")

    was_running = service.stop()
    print("Stopped cleanly.")

    return 0 if interrupted.is_set() or was_running else 1


if __name__ == "__main__":
    sys.exit(main())
