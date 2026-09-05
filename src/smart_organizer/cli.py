"""Command-line interface for Smart File Organizer.

Handles arguments, displays status messages, and manages process execution.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from typing import Optional, Sequence

from smart_organizer import __version__
from smart_organizer.config import AppConfig, load_config
from smart_organizer.logger import setup_logger
from smart_organizer.organizer import SmartFileOrganizer


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
        help="Display current application status and configuration.",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"Smart File Organizer v{__version__}",
        help="Show program's version number and exit.",
    )
    return parser


def display_status(config: AppConfig) -> None:
    """Displays detailed configuration and directory status."""
    watch_dir = config.resolved_watch_directory
    exists = watch_dir.exists()

    print(f"\nSmart File Organizer v{__version__} Status\n")
    print(f"  Watch Directory      : {watch_dir}")
    print(f"  Directory Exists     : {'Yes' if exists else 'No (Missing)'}")
    print(f"  Stability Delay      : {config.stability_delay}s")
    print(f"  Stability Checks     : {config.stability_checks} checks")
    print(f"  Max Wait Time        : {config.max_stability_wait}s")
    print(f"  Ignore Hidden Files  : {config.ignore_hidden_files}")
    print(f"  Log File             : {config.resolved_log_file or 'None'}")
    print(f"  Temporary Extensions : {', '.join(config.temporary_extensions)}")

    if config.custom_categories:
        print("\n  Custom Categories:")
        for cat, exts in config.custom_categories.items():
            print(f"    {cat:<18}: {', '.join(exts)}")
    print()


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
        display_status(config)
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

    logger = setup_logger(config.resolved_log_file)
    organizer = SmartFileOrganizer(config, logger=logger)

    if args.organize_existing:
        print(f"\nScanning existing files in:")
        print(f"  {watch_dir}\n")

        stats = organizer.organize_existing_files()

        print(
            f"\nOrganization complete: {stats['organized']} organized, "
            f"{stats['skipped']} skipped, {stats['errors']} errors.\n"
        )
        return 0 if stats["errors"] == 0 else 1

    # Live Monitoring Mode
    print(f"Smart File Organizer v{__version__}\n")
    print("Watching:")
    print(f"  {watch_dir}\n")
    print("Status:")
    print("  RUNNING\n")
    print("Waiting for new files...")
    print("Press Ctrl+C to stop.\n")

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        organizer.start_monitoring(stop_event=stop_event)
    except Exception as exc:
        print(f"\nWatcher Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if stop_event.is_set():
            print("\nStopping Smart File Organizer...")
            print("Stopped cleanly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
