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
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = ROOT / "packaging"
SPEC_FILE = PACKAGING_DIR / "pyinstaller" / "smart-organizer.spec"
BUILD_VENV = ROOT / ".build-venv"
DIST_DIR = PACKAGING_DIR / "output"
WORK_DIR = ROOT / "build"

# Install the package plus the build extra into the throwaway venv. The
# version is read from the package itself, so nothing is duplicated here.
BUILD_REQUIREMENTS = ".[build]"

# The executable name, used in installer scripts and generated documentation.
APP_NAME = "smart-organizer"

# Checksums are streamed rather than read in one go: a release artifact is
# tens of megabytes, and the build should not have to hold one in memory.
CHECKSUM_CHUNK_BYTES = 1024 * 1024

# Directory the macOS DMG places at the root of its volume. scripts/install.sh
# has to find the executable inside the mounted image, so the two files must
# agree on this; tests/test_packaging_layout.py checks that they do.
DMG_VOLUME_NAME = "Smart File Organizer"


def asset_filename(installer: str, version: str) -> str:
    """Return the release asset name this build produces for a platform.

    The install scripts download these names from the release, so they are
    the one place where build and installer have to agree. Naming them here
    rather than inline in each builder keeps that agreement checkable.
    """
    if installer == "windows":
        return f"SmartFileOrganizer-{version}-setup.exe"
    if installer == "macos":
        return f"SmartFileOrganizer-{version}-macos.dmg"
    if installer == "linux":
        return f"{APP_NAME}-{version}-linux-x86_64.tar.xz"
    _fail(f"unknown platform for a release asset: {installer}")


# Text embedded in the generated installers. Kept here so the build is the
# single place that decides what users are told at install time.
_INSTALL_COMMAND = """#!/bin/sh
# Installs {app_name} into /usr/local/bin.
set -e

SOURCE="$(cd "$(dirname "$0")" && pwd)/{app_name}/{app_name}"
TARGET="/usr/local/bin/{app_name}"

if [ ! -f "$SOURCE" ]; then
    echo "error: cannot find $SOURCE" >&2
    exit 1
fi

if [ -w /usr/local/bin ]; then
    INSTALL_DIR=/usr/local/bin
else
    echo "note: /usr/local/bin needs elevated rights, using sudo."
    INSTALL_DIR=/usr/local/bin
fi

echo "Installing {app_name} to $INSTALL_DIR ..."
if [ -w "$INSTALL_DIR" ]; then
    cp -R "$SOURCE" "$INSTALL_DIR/{app_name}"
else
    sudo cp -R "$SOURCE" "$INSTALL_DIR/{app_name}"
fi

chmod +x "$TARGET"
echo "Installed. Try: {app_name} --version"
"""

_DMG_README = """Smart File Organizer {version}

This is a standalone build: it does not need Python installed.

To install, double-click install.command (or open a Terminal in this window
and run ./install.command). It copies the executable into /usr/local/bin so
you can run:

    smart-organizer

To run without installing, use the executable directly:

    ./smart-organizer/{app_name} --help

macOS may refuse to open this application because it is not notarised.
This build is unsigned, so Gatekeeper will report that the developer
cannot be verified. See docs/packaging.md in the project repository.
"""

_ARCHIVE_README = """# Smart File Organizer {version}

Standalone build: no Python required.

## Install

    ./install.sh

This copies the executable into /usr/local/bin, using sudo if that
directory is not writable. Or move it anywhere yourself and add that
directory to PATH.

## Run

    smart-organizer --help
    smart-organizer --status

## Uninstall

    sudo rm /usr/local/bin/smart-organizer
"""

_LINUX_INSTALL_SH = """#!/bin/sh
# Installs {app_name} into /usr/local/bin.
set -e

SOURCE="$(cd "$(dirname "$0")" && pwd)/{app_name}/{app_name}"
INSTALL_DIR=/usr/local/bin

if [ ! -f "$SOURCE" ]; then
    echo "error: cannot find $SOURCE" >&2
    exit 1
fi

if [ -w "$INSTALL_DIR" ]; then
    cp -R "$SOURCE" "$INSTALL_DIR/{app_name}"
else
    echo "note: $INSTALL_DIR needs elevated rights, using sudo."
    sudo cp -R "$SOURCE" "$INSTALL_DIR/{app_name}"
fi

chmod +x "$INSTALL_DIR/{app_name}"
echo "Installed. Try: {app_name} --version"
"""


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


def write_checksum(artifact: Path) -> Path:
    """Write a SHA-256 sidecar next to a release artifact and return its path.

    The install scripts download this sidecar alongside the artifact and
    refuse to install anything whose digest does not match, so an artifact
    published without one is uninstallable rather than merely unverified.

    Every builder returns its artifact here instead of writing its own
    checksum. Keeping it to one call site is the point: when each builder
    emitted its own, the macOS DMG and the Windows installer were published
    with no sidecar and neither installer could run.
    """
    if not artifact.is_file():
        _fail(f"cannot checksum {artifact}: it is not a file")

    digest = hashlib.sha256()
    with open(artifact, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKSUM_CHUNK_BYTES), b""):
            digest.update(chunk)

    # Append rather than with_suffix(): a version such as "1.2.0" contains
    # dots, so with_suffix() would replace part of the name instead of adding
    # to it.
    sidecar = artifact.with_name(f"{artifact.name}.sha256")
    # Two spaces is the sha256sum format, which both installers rely on:
    # install.sh reads the first whitespace-separated field, and so does
    # install.ps1, so "sha256sum -c" also works for anyone verifying by hand.
    sidecar.write_text(f"{digest.hexdigest()}  {artifact.name}\n", encoding="utf-8")
    return sidecar


def build_windows_installer(version: str) -> Optional[Path]:
    """Compile the Inno Setup script into Setup.exe.

    Requires the Inno Setup compiler. On Windows runners it is installed
    with: choco install innosetup
    """
    if os.name != "nt":
        return None

    script = PACKAGING_DIR / "windows" / "smart-organizer.iss"
    if not script.is_file():
        _fail(f"Inno Setup script not found: {script}")

    compiler = shutil.which("iscc") or _find_inno_compiler()
    if not compiler:
        _fail(
            "Inno Setup compiler (iscc) was not found. Install it with "
            "'choco install innosetup', or build without --installer."
        )

    _log(f"compiling Inno Setup script for version {version}")
    subprocess.run(
        [compiler, f"/DAppVersion={version}", str(script)],
        cwd=script.parent,
        check=True,
    )

    setup_exe = script.parent / ".." / "output" / asset_filename("windows", version)
    setup_exe = setup_exe.resolve()
    if not setup_exe.is_file():
        _fail(f"Inno Setup reported success but {setup_exe} does not exist")
    return setup_exe


def _find_inno_compiler() -> str | None:
    """Locate iscc in the default Inno Setup install locations."""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramW6432", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6"
        / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _render(template: str, **values: str) -> str:
    """Fill a template, failing loudly on an unused placeholder.

    A silently unfilled {placeholder} would ship to users inside an
    installer, so an unexpected key is an error rather than a no-op.
    """
    try:
        return template.format(**values)
    except (KeyError, IndexError) as exc:
        _fail(f"installer template has an unfilled placeholder: {exc}")


def build_macos_dmg(bundle: Path, version: str) -> Optional[Path]:
    """Wrap the bundle in a DMG containing a guided installer.

    A plain command line tool does not need an .app bundle, so this does not
    create one. The volume instead ships the executable together with an
    install.command that puts it on PATH, which is the part users actually
    need. Unsigned: see docs/packaging.md for Gatekeeper.

    The whole staged directory is mounted at the volume root, so the
    executable ends up at <volume>/<DMG_VOLUME_NAME>/<app name> rather than in
    the root itself. That is the path scripts/install.sh copies from.
    """
    if platform.system() != "Darwin":
        return None

    stage = DIST_DIR / "dmg-root" / DMG_VOLUME_NAME
    if stage.parent.exists():
        shutil.rmtree(stage.parent)
    stage.mkdir(parents=True)

    shutil.copytree(bundle, stage / "smart-organizer", symlinks=True)
    # PyInstaller marks the launcher executable; keep that through the copy.
    launcher = stage / "smart-organizer" / "smart-organizer"
    launcher.chmod(0o755)

    (stage / "install.command").write_text(
        _INSTALL_COMMAND.format(app_name=APP_NAME),
        encoding="utf-8",
    )
    (stage / "install.command").chmod(0o755)
    (stage / "README.txt").write_text(
        _DMG_README.format(version=version, app_name=APP_NAME), encoding="utf-8"
    )

    dmg = DIST_DIR / asset_filename("macos", version)
    if dmg.exists():
        dmg.unlink()

    _log(f"creating DMG: {dmg.name}")
    subprocess.run(
        [
            "hdiutil", "create",
            "-volname", DMG_VOLUME_NAME,
            "-srcfolder", str(stage.parent),
            "-ov", "-format", "UDZO",
            str(dmg),
        ],
        check=True,
    )
    return dmg


def build_linux_archive(bundle: Path, version: str) -> Optional[Path]:
    """Package the bundle as a compressed archive.

    A tarball rather than an AppImage on purpose. AppImage needs FUSE to
    launch and awkward extraction otherwise, and it wants a desktop entry,
    which a command line tool has no use for. An archive drops cleanly into
    a PATH directory and is the more honest fit for a CLI.

    The SHA-256 sidecar is added by main() for every artifact alike.
    """
    if not platform.system().startswith("Linux"):
        return None

    archive = DIST_DIR / asset_filename("linux", version)
    # The tar member is the staging directory, so it is the asset name
    # without the archive suffix rather than a separately spelled name.
    release_name = archive.name[: -len(".tar.xz")]
    release_dir = DIST_DIR / release_name
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    shutil.copytree(bundle, release_dir / APP_NAME, symlinks=True)
    (release_dir / "LICENSE").write_text(
        (ROOT / "LICENSE").read_text(encoding="utf-8") if (ROOT / "LICENSE").is_file() else "",
        encoding="utf-8",
    )
    (release_dir / "README.md").write_text(_ARCHIVE_README.format(version=version), encoding="utf-8")
    (release_dir / "install.sh").write_text(
        _LINUX_INSTALL_SH.format(app_name=APP_NAME), encoding="utf-8"
    )
    (release_dir / "install.sh").chmod(0o755)

    _log(f"creating archive: {archive.name}")
    subprocess.run(
        ["tar", "-cJf", str(archive), "-C", str(DIST_DIR), release_name],
        check=True,
    )
    return archive


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
    parser.add_argument(
        "--installer",
        action="store_true",
        help="also build the native installer (Setup.exe, DMG, or Linux archive)",
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
        result = subprocess.run([str(python), str(smoke), str(executable)], cwd=ROOT)
        if result.returncode != 0:
            _log("smoke test FAILED")
            return result.returncode
        _log("smoke test passed")

    if args.installer:
        built: list[Path] = []
        if os.name == "nt":
            built.append(build_windows_installer(version))
        elif platform.system() == "Darwin":
            built.append(build_macos_dmg(bundle, version))
        elif platform.system().startswith("Linux"):
            built.append(build_linux_archive(bundle, version))
        for artifact in built:
            if artifact:
                _log(f"installer: {artifact}")
                # One checksum call site for every platform, so an artifact
                # can never be published without the sidecar the installers
                # require.
                _log(f"checksum:  {write_checksum(artifact)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
