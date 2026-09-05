"""Unit tests for CLI interface."""

from pathlib import Path
import pytest

from smart_organizer.cli import build_parser, main


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
