#!/usr/bin/env python3
"""Build the standalone Smart File Organizer executable.

Keeps the build reproducible by running PyInstaller from a dedicated
virtual environment rather than from whatever happens to be installed on
the machine, so a stray PySide6 or an incompatible PyInstaller cannot
change what ends up in the bundle.

Typical use::

    python packaging/build.py                # build the onedir executable
    python packaging/build.py --clean        # discard previous build output
    python packaging/build.py --smoke-test   # build, then verify behaviour

Release builds should always pass ``--clean`` so the bundle cannot inherit
a stale file from an earlier build.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = ROOT / "packaging"
SPEC_FILE = PACKAGING_DIR / "pyinstaller" / "smart-organizer.spec"
BUILD_VENV = ROOT / ".build-venv"
DIST_DIR = PACKAGING_DIR / "output"
WORK_DIR = ROOT / "build"

# Install the package plus the build extra into the throwaway venv. The
# version is read from the package itself, so nothing is duplicated here.
BUILD_REQUIREMENTS = ".[build]"


def _log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def _fail(message: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"[build] ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def read_version() -> str:
    """Read the version from the single source of truth.

    Parsed statically rather than imported so this works before the
    package is installed into the build venv.
    """
    init_file = ROOT / "src" / "smart_organizer" / "__init__.py"
    if not init_file.is_file():
        _fail(f"cannot locate {init_file}")

    for line in init_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("__version__"):
            _, _, value = stripped.partition("=")
            return value.strip().strip("\"'")

    _fail("__version__ not found in smart_organizer/__init__.py")


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def create_build_venv(force: bool) -> Path:
    """Create the isolated build environment and install build deps."""
    if force and BUILD_VENV.exists():
        _log(f"removing existing build venv at {BUILD_VENV}")
        shutil.rmtree(BUILD_VENV)

    python = venv_python(BUILD_VENV)

    if not BUILD_VENV.exists():
        _log(f"creating build venv at {BUILD_VENV}")
        # venv creation on some Linux images is slow; give it room.
        venv.EnvBuilder(with_pip=True, clear=False).create(BUILD_VENV)

    if not python.is_file():
        _fail(f"build venv python not found at {python}")

    _log("installing build requirements (this may take a minute)")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--quiet",
            "pip",
        ],
        check=True,
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", BUILD_REQUIREMENTS],
        cwd=ROOT,
        check=True,
    )
    return python


def clean() -> None:
    _log("cleaning build output")
    for path in (DIST_DIR, WORK_DIR):
        if path.exists():
            shutil.rmtree(path)
    generated_version_file = SPEC_FILE.parent / "_version_info.txt"
    if generated_version_file.exists():
        generated_version_file.unlink()

    for stale in ROOT.glob("**/__pycache__"):
        if ".build-venv" in stale.parts:
            continue
        shutil.rmtree(stale, ignore_errors=True)


def check_hidden_imports(output: str) -> None:
    """Fail the build if a declared hidden import could not be found.

    PyInstaller logs an unresolvable hidden import at ERROR level and then
    carries on to produce a binary anyway. The bundle looks fine until the
    missing module is exercised at runtime, which is exactly the class of
    defect the explicit hidden imports exist to prevent, so it is treated
    as a build failure here instead.

    The message is read from the build output rather than a warn file
    because a spec-supplied warn_file is not reliably written outside the
    spec directory, and a check that silently finds nothing is worse than
    no check at all.
    """
    problems = [
        line.strip()
        for line in output.splitlines()
        if "ERROR: Hidden import" in line
    ]
    if problems:
        _log(f"{len(problems)} declared hidden import(s) could not be resolved:")
        for problem in problems:
            _log(f"  {problem}")
        _fail(
            "hidden imports named in the spec do not exist. Correct the module "
            "names, or remove them if this platform does not need them."
        )

    _log("all declared hidden imports resolved")


def run_pyinstaller(python: Path, version: str) -> Path:
    """Invoke PyInstaller and return the built executable path."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    _log(f"building smart-organizer {version} for {platform.system()} {platform.machine()}")
    _log(f"dist: {DIST_DIR}")
    _log(f"work: {WORK_DIR}")

    # Output is captured so an unresolvable hidden import can be detected.
    # PyInstaller reports those at ERROR level but still emits a binary.
    result = subprocess.run(
        [
            str(python),
            "-m",
            "PyInstaller",
            str(SPEC_FILE),
            "--noconfirm",
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(WORK_DIR),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        _fail(f"PyInstaller exited with code {result.returncode}")

    # onedir builds land at <distpath>/smart-organizer/
    bundle = DIST_DIR / "smart-organizer"
    if not bundle.is_dir():
        _fail(f"expected build output at {bundle}, but it was not produced")

    check_hidden_imports((result.stdout or "") + (result.stderr or ""))

    return bundle


def find_executable(bundle: Path) -> Path:
    """Locate the launcher inside a built bundle."""
    if os.name == "nt":
        candidate = bundle / "smart-organizer.exe"
    else:
        candidate = bundle / "smart-organizer"
    if not candidate.is_file():
        entries = sorted(p.name for p in bundle.iterdir())
        _fail(f"executable not found in {bundle}; found: {entries}")
    return candidate


def report(bundle: Path, executable: Path) -> None:
    """Print what was built, how big it is, and its checksum."""
    total = sum(f.stat().st_size for f in bundle.rglob("*") if f.is_file())
    digest = hashlib.sha256()
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        digest.update(path.relative_to(bundle).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())

    _log("")
    _log("build complete")
    _log(f"  bundle      : {bundle}")
    _log(f"  executable  : {executable}")
    _log(f"  files       : {sum(1 for _ in bundle.rglob('*') if _.is_file())}")
    _log(f"  unpacked    : {total / (1024 * 1024):.1f} MiB")
    _log(f"  tree sha256 : {digest.hexdigest()}")
    _log("")
    _log("next: python packaging/smoke_test.py " + str(executable))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="discard previous build output before building (recommended for releases)",
    )
    parser.add_argument(
        "--recreate-venv",
        action="store_true",
        help="recreate the build virtual environment from scratch",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="run the frozen-binary smoke test after building",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not SPEC_FILE.is_file():
        _fail(f"spec file not found: {SPEC_FILE}")

    if args.clean:
        clean()

    version = read_version()
    python = create_build_venv(force=args.recreate_venv)
    bundle = run_pyinstaller(python, version)
    executable = find_executable(bundle)
    report(bundle, executable)

    if args.smoke_test:
        _log("running smoke test against the frozen binary")
        smoke = PACKAGING_DIR / "smoke_test.py"
        # Run through the build venv python so pytest (if the smoke test
        # needs it) resolves consistently, but execute the artifact itself.
        result = subprocess.run([str(python), str(smoke), str(executable)], cwd=ROOT)
        if result.returncode != 0:
            _log("smoke test FAILED")
            return result.returncode
        _log("smoke test passed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
