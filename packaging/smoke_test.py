#!/usr/bin/env python3
"""Verify a frozen Smart File Organizer build actually works.

A PyInstaller build can succeed and still produce a binary that cannot do
its job. The classic case for this application is watchdog's platform
conditional import: PyInstaller follows only the branch matching the build
machine, so a bundle built on Linux can ship without the Windows or macOS
observer and still start cleanly, then fail the first time a user drops a
file in. Checking that ``--version`` works proves nothing.

So this script exercises the real behaviour against the real artifact:

    python packaging/smoke_test.py packaging/output/smart-organizer/

Every check runs in a throwaway directory with its own config file, so it
never touches the developer's or the CI runner's real configuration, and
never leaves a watcher running behind it.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Defaults wait 2.0s x 2 checks before acting on a file. That is right for
# real downloads and far too slow for a test, so the config written below
# tightens it. Values must satisfy validate_config_data().
FAST_STABILITY = {
    "stability_delay": 0.2,
    "stability_checks": 1,
    "max_stability_wait": 5.0,
}

CATEGORY_DIR = "PDFs"
SETTLE_SECONDS = 1.5
WATCH_TIMEOUT_SECONDS = 45.0
MAX_ATTEMPTS = 5


class SmokeFailure(Exception):
    """Raised when the frozen binary fails a behavioural check."""


def _log(message: str) -> None:
    print(f"[smoke] {message}", flush=True)


class Harness:
    """Runs the frozen binary inside an isolated sandbox."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable
        self._tmp = tempfile.TemporaryDirectory(prefix="smart-organizer-smoke-")
        self.root = Path(self._tmp.name)
        self.watch = self.root / "watch"
        self.watch.mkdir(parents=True)
        self.log_file = self.root / "organizer.log"
        self.config_file = self.root / "config.json"
        self.config_file.write_text(
            json.dumps(
                {
                    "watch_directory": str(self.watch),
                    "log_file": str(self.log_file),
                    **FAST_STABILITY,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def close(self) -> None:
        """Remove the sandbox, tolerating files the OS still holds open.

        Cleanup must never be the reason a build is rejected. A locked log
        file is an artefact-teardown detail, not a verdict on the binary.
        """
        for attempt in range(3):
            try:
                self._tmp.cleanup()
                return
            except OSError:
                if attempt == 2:
                    print(
                        f"[smoke] warning: could not fully remove sandbox {self.root}; "
                        "leaving it in place",
                        flush=True,
                    )
                    return
                time.sleep(1.0)

    def run(self, *args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
        """Run the binary to completion with the sandboxed config."""
        command = [
            str(self.executable),
            *args,
            "--config-file",
            str(self.config_file),
        ]
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def categorized(self) -> list[Path]:
        """Files that have been filed into a category folder."""
        target = self.watch / CATEGORY_DIR
        if not target.is_dir():
            return []
        return sorted(p for p in target.iterdir() if p.is_file())

    def files_at_top_level(self) -> list[Path]:
        return sorted(p for p in self.watch.iterdir() if p.is_file())


def _describe(result: subprocess.CompletedProcess) -> str:
    return (
        f"exit code {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


def check_version(harness: Harness) -> None:
    """The binary runs at all and reports the packaged version."""
    result = harness.run("--version")
    if result.returncode != 0:
        raise SmokeFailure(f"--version failed: {_describe(result)}")
    if "Smart File Organizer v" not in result.stdout:
        raise SmokeFailure(f"--version output not recognised: {result.stdout!r}")
    _log(f"version reports: {result.stdout.strip()}")


def check_help(harness: Harness) -> None:
    """Argparse works, so the entry point and its arguments were bundled."""
    result = harness.run("--help")
    if result.returncode != 0:
        raise SmokeFailure(f"--help failed: {_describe(result)}")
    for expected in ("--watch-directory", "--organize-existing", "--status"):
        if expected not in result.stdout:
            raise SmokeFailure(f"--help is missing {expected}")


def check_status(harness: Harness) -> None:
    """Configuration loads from disk and the watch dir is seen as writable."""
    result = harness.run("--status")
    if result.returncode != 0:
        raise SmokeFailure(f"--status failed: {_describe(result)}")
    if "Exists (Writable)" not in result.stdout:
        raise SmokeFailure(f"--status did not confirm a writable watch dir: {result.stdout}")


def check_organize_existing(harness: Harness) -> None:
    """One-shot organization of files already on disk."""
    source = harness.watch / "existing-sample.pdf"
    source.write_bytes(b"%PDF-1.4\n% frozen build smoke test\n")

    result = harness.run("--organize-existing", timeout=120.0)
    if result.returncode != 0:
        raise SmokeFailure(f"--organize-existing failed: {_describe(result)}")

    if source.exists():
        raise SmokeFailure(
            "--organize-existing reported success but left the file in place; "
            f"top level now holds {[p.name for p in harness.files_at_top_level()]}"
        )
    categorized = [p.name for p in harness.categorized()]
    if not any(name.endswith(".pdf") for name in categorized):
        raise SmokeFailure(
            f"expected a .pdf in {CATEGORY_DIR}/, found {categorized}"
        )
    _log(f"organize-existing filed: {categorized}")


def _check_for_watcher_error(stream: str) -> None:
    """Turn a watchdog import failure into an actionable message.

    This is the exact regression the spec's explicit hidden imports exist
    to prevent, so it deserves a message that says so.
    """
    lowered = stream.lower()
    if "watcher error" in lowered:
        raise SmokeFailure(
            "the frozen binary could not start its watcher. This is almost "
            "always watchdog's platform conditional import not being bundled; "
            "check the hiddenimports list in the PyInstaller spec.\n" + stream
        )


def _popen_kwargs() -> dict:
    """Platform-specific Popen options for watch mode.

    Windows has no signals in the POSIX sense. A console control event is
    only delivered to a process that is the root of its own process group,
    so the group has to be created explicitly or the event goes nowhere.
    """
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {}


def _send_shutdown_request(process: subprocess.Popen) -> None:
    """Ask watch mode to stop the way a user would.

    The application handles SIGINT, SIGTERM and (on Windows) SIGBREAK.
    Windows has no POSIX signals: a console control event is the only
    equivalent, and it has to be sent to a process group. Note that
    CREATE_NEW_PROCESS_GROUP disables CTRL_C_EVENT for the new group, so
    CTRL_BREAK_EVENT is the event that actually gets delivered - and the
    application maps it to SIGBREAK and shuts down cleanly.
    """
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGINT)


def _terminate(process: subprocess.Popen) -> None:
    """Ask the process to stop, then make sure it actually did."""
    if process.poll() is not None:
        return
    try:
        _send_shutdown_request(process)
        process.wait(timeout=20)
    except Exception:
        # A failed graceful stop must never leave the process running: it
        # would hold its log file open and break sandbox cleanup.
        process.kill()
        process.wait(timeout=10)


# watchdog resolves its observer at import time and, on Windows and macOS,
# silently falls back to a polling implementation when the native backend
# is missing, emitting only a warning. A bundle that has lost its native
# backend therefore still works, just slowly and with far more CPU. On
# Linux the same situation raises outright. Treating a fallback warning as
# a failure means the native backend is actually verified per platform.
BACKEND_FALLBACK_MARKERS = (
    "fall back to polling",
    "fallback to polling",
    "failed to import",
)


def _check_backend_degradation(output_path: Path) -> None:
    """Fail if watchdog fell back to polling instead of using its native backend."""
    if not output_path.is_file():
        return

    text = output_path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    for marker in BACKEND_FALLBACK_MARKERS:
        if marker in lowered:
            raise SmokeFailure(
                "watchdog fell back to a polling backend, which means the native "
                "observer for this platform is not in the bundle. It would still "
                "work, but polling a busy Downloads folder is CPU-hungry. Check "
                "the per-platform hiddenimports in the PyInstaller spec.\n"
                f"--- process output ---\n{text}"
            )



def check_live_watch(harness: Harness) -> None:
    """The important one: drop a file and watch it get filed, live.

    The CLI prints its banner before the observer is actually scheduled, so
    there is no ready signal to synchronise on. Rather than sleep a guessed
    interval and hope, this drops a file, waits for it to be categorized,
    and retries with a fresh file if the event was missed. Either the
    observer works, or this fails - there is no false pass.
    """
    command = [
        str(harness.executable),
        "--config-file",
        str(harness.config_file),
    ]
    # Output goes to a file rather than a pipe so it can be inspected while
    # the process is still running, without risking a full pipe buffer
    # deadlocking a process that has no reader.
    output_path = harness.root / "watch-mode-output.log"
    output_handle = output_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdout=output_handle,
        stderr=subprocess.STDOUT,
        text=True,
        **_popen_kwargs(),
    )

    def read_output() -> str:
        return output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""

    try:
        time.sleep(SETTLE_SECONDS)

        if process.poll() is not None:
            output = read_output()
            _check_for_watcher_error(output)
            raise SmokeFailure(
                f"watch mode exited immediately (code {process.returncode}):\n{output}"
            )

        deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if time.monotonic() > deadline:
                break

            dropped = harness.watch / f"live-attempt-{attempt}.pdf"
            dropped.write_bytes(b"%PDF-1.4\n% live watch smoke test\n")
            _log(f"attempt {attempt}: dropped {dropped.name}")

            per_file_deadline = time.monotonic() + 8.0
            while time.monotonic() < per_file_deadline:
                if dropped.exists() is False:
                    break
                if process.poll() is not None:
                    output = read_output()
                    _check_for_watcher_error(output)
                    raise SmokeFailure(
                        f"watcher stopped while organizing (code {process.returncode}):\n{output}"
                    )
                time.sleep(0.1)

            if not dropped.exists():
                _log(f"attempt {attempt}: organized")
                break

            _log(f"attempt {attempt}: event missed, retrying")
        else:
            raise SmokeFailure(f"no file was categorized after {MAX_ATTEMPTS} attempts")

        if dropped.exists():
            raise SmokeFailure(
                "live watch never categorized a dropped file. The frozen "
                "binary started but is not watching - check the watchdog "
                "backend hidden imports in the spec."
            )

        if not harness.categorized():
            raise SmokeFailure("file was moved but no file ended up in a category folder")

        _log(f"live watch filed: {[p.name for p in harness.categorized()]}")

        # Clean shutdown: the stop signal is how a user ends a run, so the
        # watcher must stop without being killed.
        _terminate(process)
        if process.returncode != 0:
            raise SmokeFailure(
                f"clean shutdown returned {process.returncode}, expected 0.\n{read_output()}"
            )
        _log("clean shutdown returned 0")

        # Checked last: it is a property of the backend, not of the shutdown.
        _check_backend_degradation(output_path)

    finally:
        _terminate(process)
        output_handle.close()



CHECKS = (
    ("reports its version", check_version),
    ("exposes the CLI interface", check_help),
    ("reads configuration and writes to the watch dir", check_status),
    ("organizes files already on disk", check_organize_existing),
    ("watches the directory and organizes a new file", check_live_watch),
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(f"usage: {Path(sys.argv[0]).name} <path-to-executable>", file=sys.stderr)
        return 2

    target = Path(argv[0])
    executable = target / ("smart-organizer.exe" if os.name == "nt" else "smart-organizer")
    if not executable.is_file():
        print(f"[smoke] ERROR: no executable at {executable}", file=sys.stderr)
        return 2

    _log(f"testing {executable}")
    harness = Harness(executable)
    failures: list[str] = []

    try:
        for label, check in CHECKS:
            try:
                check(harness)
            except SmokeFailure as exc:
                failures.append(f"{label}: {exc}")
                _log(f"FAIL {label}")
                break
            except Exception as exc:  # noqa: BLE001 - report anything unexpected
                failures.append(f"{label}: unexpected {type(exc).__name__}: {exc}")
                _log(f"ERROR {label}")
                break
            _log(f"ok   {label}")
    finally:
        harness.close()

    if failures:
        print("\n[smoke] FAILED\n", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}\n", file=sys.stderr)
        return 1

    _log("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
