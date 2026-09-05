"""Unit tests for stability detection module."""

import threading
import time
from pathlib import Path
import pytest

from smart_organizer.stability import wait_for_file_stability


def test_stability_stable_file(tmp_path: Path):
    test_file = tmp_path / "sample.pdf"
    test_file.write_text("fixed content")

    is_stable = wait_for_file_stability(
        test_file,
        stability_delay=0.01,
        stability_checks=2,
        max_wait_time=0.5,
    )
    assert is_stable is True


def test_stability_growing_file_until_stable(tmp_path: Path):
    test_file = tmp_path / "growing.bin"
    test_file.write_bytes(b"initial")

    def write_more():
        for i in range(3):
            time.sleep(0.02)
            try:
                with open(test_file, "ab") as f:
                    f.write(b"datachunk")
            except Exception:
                pass

    t = threading.Thread(target=write_more)
    t.start()

    is_stable = wait_for_file_stability(
        test_file,
        stability_delay=0.03,
        stability_checks=2,
        max_wait_time=2.0,
    )
    t.join()
    assert is_stable is True


def test_stability_disappearing_file(tmp_path: Path):
    test_file = tmp_path / "temporary.part"
    test_file.write_text("some data")

    def remove_file():
        time.sleep(0.02)
        if test_file.exists():
            test_file.unlink()

    t = threading.Thread(target=remove_file)
    t.start()

    is_stable = wait_for_file_stability(
        test_file,
        stability_delay=0.02,
        stability_checks=3,
        max_wait_time=1.0,
    )
    t.join()
    assert is_stable is False


def test_stability_nonexistent_file(tmp_path: Path):
    test_file = tmp_path / "does_not_exist.txt"
    assert wait_for_file_stability(test_file, stability_delay=0.01) is False
