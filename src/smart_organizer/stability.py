"""File stability detection module for Smart File Organizer.

Ensures newly downloaded or written files are fully completed before moving them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional


def wait_for_file_stability(
    file_path: Path | str,
    stability_delay: float = 2.0,
    stability_checks: int = 2,
    max_wait_time: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """Waits until the file's size remains stable across consecutive checks.

    Args:
        file_path: Path to candidate file.
        stability_delay: Delay in seconds between checks.
        stability_checks: Number of consecutive identical size checks required.
        max_wait_time: Maximum total time to wait before timing out.
        sleep_fn: Sleep function (injectable for unit tests).

    Returns:
        True if the file is confirmed stable and ready, False if missing or timed out.
    """
    path = Path(file_path)

    if not path.exists():
        return False

    elapsed_time = 0.0
    consecutive_stable_count = 0
    last_size: Optional[int] = None

    while elapsed_time < max_wait_time:
        if not path.exists() or not path.is_file():
            return False

        try:
            current_size = path.stat().st_size
        except OSError:
            # File might be locked or momentarily inaccessible by OS
            return False

        if last_size is not None and current_size == last_size:
            consecutive_stable_count += 1
            if consecutive_stable_count >= stability_checks:
                return True
        else:
            last_size = current_size
            consecutive_stable_count = 0

        sleep_fn(stability_delay)
        elapsed_time += stability_delay

    return consecutive_stable_count >= stability_checks
