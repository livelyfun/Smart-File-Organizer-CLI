"""Contract tests between the build and the install scripts.

The build writes release artifacts to names the install scripts then request
from GitHub, and a macOS DMG is only useful if the installer can find the
executable inside the mounted image. Nothing in either program checks the
other, so a rename on one side is a broken install for users on the other.

These are text-level assertions on purpose. The scripts are shell and
PowerShell and cannot import the build module, so the only cheap way to keep
them in agreement is to assert that the names they hardcode still match the
ones the build produces.
"""

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "packaging" / "build.py"
INSTALL_SH = ROOT / "scripts" / "install.sh"
INSTALL_PS1 = ROOT / "scripts" / "install.ps1"

VERSION = "1.2.3"

# A macOS DMG volume is named after the application, so every realistic
# mount point contains a space. Both of the samples below are the shapes
# hdiutil has used: columns padded with spaces, and columns padded with tabs.
HDIOUTIL_OUTPUT_SPACES = (
    "/dev/disk4          GPT_partition_scheme\n"
    "/dev/disk4s1        Apple_HFS                       /Volumes/Smart File Organizer\n"
)
HDIOUTIL_OUTPUT_TABS = (
    "/dev/disk4\tGPT_partition_scheme\n"
    "/dev/disk4s1\tApple_HFS\t/Volumes/Smart File Organizer\n"
)


def _load_build_module():
    spec = importlib.util.spec_from_file_location("packaging_build", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    return _load_build_module()


@pytest.fixture(scope="module")
def install_sh():
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_ps1():
    return INSTALL_PS1.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bash():
    return shutil.which("bash") or "bash"


@pytest.fixture(scope="module")
def build_workflow():
    """The Build workflow, which mounts the DMG it just built on macOS."""
    import yaml

    path = ROOT / ".github" / "workflows" / "build.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# A stand-in for hdiutil that validates its own arguments the way the real one
# does, and reports a mount the way macOS does. This lets the installer's
# macOS path be tested on any platform, which is the only way -mountrandom's
# missing argument could have been caught before release.
FAKE_HDIOUTIL = """#!/bin/sh
# Minimal hdiutil attach, faithful about the two things that matter here:
# an option that takes an argument, and the columns of its output.
if [ "$1" != "attach" ]; then
    echo "hdiutil: $1: unsupported" >&2
    exit 64
fi
shift
while [ $# -gt 0 ]; do
    if [ "$1" = "-mountrandom" ]; then
        shift
        if [ $# -eq 0 ]; then
            echo 'hdiutil: attach: missing "-mountrandom" argument' >&2
            exit 1
        fi
    fi
    shift
done
if [ "${FAKE_HDIOUTIL_FAILS:-0}" = "1" ]; then
    echo "/dev/disk4          GPT_partition_scheme"
    exit 1
fi
printf '/dev/disk4          GPT_partition_scheme\\n'
printf '/dev/disk4s1        Apple_HFS                       /Volumes/%s\\n' \\
    "${FAKE_HDIOUTIL_VOLUME:-Smart File Organizer}"
"""

MOUNT_POINT = "/Volumes/Smart File Organizer"


def _attach_with_fake_hdiutil(bash, tmp_path, fails=False):
    """Run attach_dmg from install.sh against a fake hdiutil on PATH."""
    tools = tmp_path / "bin"
    tools.mkdir()
    hdiutil = tools / "hdiutil"
    hdiutil.write_text(FAKE_HDIOUTIL, encoding="utf-8")
    hdiutil.chmod(0o755)
    (tmp_path / "image.dmg").write_text("not really an image")

    return subprocess.run(
        [
            bash,
            "-c",
            'set -euo pipefail; source "$1"; attach_dmg "$2"',
            "sh",
            str(INSTALL_SH),
            str(tmp_path / "image.dmg"),
        ],
        env={
            # The installer reads HOME while being sourced, and the fake
            # directory comes first so the real hdiutil cannot be reached.
            **os.environ,
            "PATH": f"{tools}:/usr/bin:/bin",
            "FAKE_HDIOUTIL_VOLUME": MOUNT_POINT.rsplit("/", 1)[1],
            "FAKE_HDIOUTIL_FAILS": "1" if fails else "0",
        },
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the installer")
def test_attach_dmg_mounts_and_reports_the_mount_point(bash, tmp_path):
    """The installer's own mount call works, argument and all.

    The volume name contains spaces, so a mount point that is truncated or
    left padded is the difference between a working install and an empty
    directory.
    """
    result = _attach_with_fake_hdiutil(bash, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == MOUNT_POINT


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the installer")
def test_attach_dmg_fails_loudly_when_the_image_will_not_mount(bash, tmp_path):
    """A mount that produces no path must not look like a successful install.

    hdiutil can exit non-zero and still print a scheme line with no mount
    point, so an empty result has to stop the install with a message rather
    than copying from a path of "".
    """
    result = _attach_with_fake_hdiutil(bash, tmp_path, fails=True)

    assert result.returncode != 0
    assert "could not mount" in result.stderr
    assert "image.dmg" in result.stderr


@pytest.mark.parametrize(
    "platform, expected",
    [
        ("windows", f"SmartFileOrganizer-{VERSION}-setup.exe"),
        ("macos", f"SmartFileOrganizer-{VERSION}-macos.dmg"),
        ("linux", f"smart-organizer-{VERSION}-linux-x86_64.tar.xz"),
    ],
)
def test_asset_names_are_defined_once(build, platform, expected):
    """The build derives every release asset name from one function."""
    assert build.asset_filename(platform, VERSION) == expected


def test_unknown_platform_is_rejected(build):
    """An unrecognised platform fails loudly instead of inventing a name."""
    with pytest.raises(SystemExit) as excinfo:
        build.asset_filename("solaris", VERSION)

    assert excinfo.value.code == 1


def test_installer_requests_the_macos_asset_the_build_produces(build, install_sh):
    """install.sh must ask for exactly the DMG name the build creates."""
    assert build.asset_filename("macos", "1.2.3") == f"SmartFileOrganizer-{VERSION}-macos.dmg"
    assert 'dmg="SmartFileOrganizer-${version}-macos.dmg"' in install_sh, (
        "scripts/install.sh no longer requests the DMG name build.py produces"
    )


def test_installer_requests_the_windows_asset_the_build_produces(build, install_ps1):
    """install.ps1 must ask for exactly the Setup.exe name the build creates."""
    assert build.asset_filename("windows", "1.2.3") == f"SmartFileOrganizer-{VERSION}-setup.exe"
    assert 'SmartFileOrganizer-$Version-setup.exe' in install_ps1, (
        "scripts/install.ps1 no longer requests the installer name build.py produces"
    )


def test_installer_agrees_on_the_linux_asset_name(build, install_sh):
    """The archive name is built from APP_NAME, so both files must spell it alike."""
    assert f'APP_NAME="{build.APP_NAME}"' in install_sh
    assert 'base="${APP_NAME}-${version}-linux-x86_64"' in install_sh
    assert 'archive="${base}.tar.xz"' in install_sh


def test_dmg_volume_directory_matches(build, install_sh):
    """The installer must look where the build actually staged the bundle.

    The build mounts a directory at the root of the DMG volume and puts the
    executable inside it, so copying from the volume root installs nothing.
    """
    match = re.search(r'^DMG_VOLUME_DIR="([^"]+)"', install_sh, re.MULTILINE)
    assert match, "scripts/install.sh no longer defines DMG_VOLUME_DIR"

    assert match.group(1) == build.DMG_VOLUME_NAME, (
        "scripts/install.sh and packaging/build.py disagree about the directory "
        "inside the DMG volume; the macOS install will copy nothing"
    )


def test_sidecar_naming_matches_how_the_installers_request_it(build, install_sh, install_ps1):
    """Each script asks for a sidecar named after the artifact it downloaded."""
    assert '"${tmp}/${archive}.sha256"' in install_sh
    assert '"${tmp}/${dmg}.sha256"' in install_sh
    assert '"$setupName.sha256"' in install_ps1

    # The build appends the suffix to the whole name, so a dotted version
    # cannot swallow part of it the way with_suffix() would.
    artifact = build.asset_filename("linux", VERSION)
    assert artifact.endswith(".tar.xz")
    assert Path(artifact).with_name(f"{artifact}.sha256").name == (
        f"smart-organizer-{VERSION}-linux-x86_64.tar.xz.sha256"
    )


def test_mountrandom_is_given_the_directory_to_mount_under(install_sh):
    """-mountrandom takes a path, and the install was broken without one.

    hdiutil fails with 'missing "-mountrandom" argument' and mounts nothing, so
    every macOS install from a release image stopped before it copied anything.
    Nothing local could catch this, because hdiutil only exists on macOS,
    which is why the Build workflow mounts the image it just built.
    """
    assert re.search(r"-mountrandom\s+\S", install_sh), (
        "scripts/install.sh passes -mountrandom without the directory to mount "
        "under; hdiutil will refuse to attach"
    )


def test_build_mounts_the_dmg_through_the_installer(build_workflow, install_sh):
    """The build check must run the installer's code, not a copy of it.

    The check exists to catch a mismatch between the two files. If it spelled
    out its own hdiutil command it would be a third thing to keep in step, and
    a change to the installer would not be checked at all.
    """
    step = None
    for candidate in build_workflow["jobs"]["build"]["steps"]:
        if candidate.get("name") == "Verify DMG layout":
            step = candidate["run"]

    assert step, "build.yml no longer verifies the DMG layout"
    assert "source scripts/install.sh" in step, (
        "the DMG check must source the installer instead of duplicating it"
    )
    assert "attach_dmg" in step
    assert "DMG_VOLUME_DIR" in step, "the path must come from the installer's own names"
    # The function the check calls is defined by the installer, not by itself.
    assert "attach_dmg()" in install_sh


def _parse_mount_point(bash, sample):
    """Run the installer's own hdiutil parser over a captured output sample."""
    result = subprocess.run(
        [
            bash,
            "-c",
            'set -euo pipefail; source "$1"; printf "%s" "$2" | parse_mount_point',
            "sh",
            str(INSTALL_SH),
            sample,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # Callers read this through command substitution, which drops the trailing
    # newline, so the comparison does too.
    return result.stdout.strip()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the parser")
@pytest.mark.parametrize("sample", [HDIOUTIL_OUTPUT_SPACES, HDIOUTIL_OUTPUT_TABS])
def test_mount_point_survives_a_volume_name_with_spaces(bash, sample):
    """The parser must not split the mount point on its own spaces.

    The volume is named after the application, so a whitespace-based split
    truncates "/Volumes/Smart File Organizer" to "/Volumes/Smart" and the
    installer then looks for a directory that is not there.
    """
    assert _parse_mount_point(bash, sample) == "/Volumes/Smart File Organizer"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the parser")
def test_mount_point_ignores_column_padding(bash):
    """Trailing padding on the line must not end up in the path."""
    sample = (
        "/dev/disk4s1        Apple_HFS                       "
        "/Volumes/Smart File Organizer     \n"
    )

    assert _parse_mount_point(bash, sample) == "/Volumes/Smart File Organizer"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the parser")
def test_mount_point_is_empty_when_nothing_mounted(bash):
    """A mount failure yields nothing, so the caller can report it.

    hdiutil prints a scheme line with no mount point when it cannot attach,
    and the installer's own message is clearer than a path of "".
    """
    sample = "/dev/disk4          GPT_partition_scheme\n"

    assert _parse_mount_point(bash, sample) == ""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the parser")
def test_installer_script_is_syntactically_valid(bash):
    """install.sh parses, so a broken edit cannot reach a release."""
    subprocess.run([bash, "-n", str(INSTALL_SH)], check=True)
