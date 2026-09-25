"""Tests for the release checksum sidecar written by the build orchestrator.

The sidecar is what makes `scripts/install.sh` and `scripts/install.ps1`
refuse to install an unverified download, so its name, format and digest all
have to match what those two scripts parse.
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "packaging" / "build.py"


def _load_build_module():
    """Import packaging/build.py as a module.

    It is a standalone script rather than an installed package, and it is the
    only thing in the repository that produces release artifacts.
    """
    spec = importlib.util.spec_from_file_location("packaging_build", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    return _load_build_module()


def test_sidecar_name_appends_without_replacing_suffix(build, tmp_path):
    """The sidecar is appended, not substituted for the real suffix.

    Artifact names carry dotted versions, so with_suffix() would happily
    replace "-linux-x86_64" or ".0" and produce a sidecar no installer
    would ever look for.
    """
    artifact = tmp_path / "smart-organizer-1.2.0-linux-x86_64.tar.xz"
    artifact.write_bytes(b"archive contents")

    sidecar = build.write_checksum(artifact)

    assert sidecar.name == "smart-organizer-1.2.0-linux-x86_64.tar.xz.sha256"
    assert sidecar.is_file()


def test_sidecar_digest_matches_the_artifact(build, tmp_path):
    """The recorded digest is the real SHA-256 of the artifact bytes."""
    payload = b"Smart File Organizer" * 1024
    artifact = tmp_path / "SmartFileOrganizer-1.0.0-setup.exe"
    artifact.write_bytes(payload)

    sidecar = build.write_checksum(artifact)

    expected = hashlib.sha256(payload).hexdigest()
    assert sidecar.read_text(encoding="utf-8") == f"{expected}  {artifact.name}\n"


def test_sidecar_is_parsed_the_same_way_the_installers_parse_it(build, tmp_path):
    """The format is `sha256sum`'s: digest, two spaces, file name.

    install.sh reads it with awk and install.ps1 with -split '\\s+', both of
    which take the first field. Only the first field is relied on, but the
    rest is kept so `sha256sum -c` also works for a user verifying by hand.
    """
    artifact = tmp_path / "SmartFileOrganizer-1.0.0-macos.dmg"
    artifact.write_bytes(b"dmg contents")

    line = build.write_checksum(artifact).read_text(encoding="utf-8").splitlines()[0]
    fields = line.split()

    assert len(fields) == 2, "expected '<digest>  <name>', got a different field count"
    assert len(fields[0]) == 64
    assert all(char in "0123456789abcdef" for char in fields[0])
    assert fields[1] == artifact.name
    # The separator is two spaces, not a tab or a single space: this is the
    # exact layout sha256sum emits and verifies.
    assert f"  {artifact.name}" in line


def test_large_artifact_is_streamed_in_chunks(build, tmp_path):
    """A multi-chunk artifact is hashed correctly, not truncated.

    The digest is computed by reading the file in chunks, so this crosses the
    chunk boundary and would differ from a short read.
    """
    artifact = tmp_path / "big.tar.xz"
    payload = b"x" * (build.CHECKSUM_CHUNK_BYTES + 1)
    artifact.write_bytes(payload)

    sidecar = build.write_checksum(artifact)

    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(payload).hexdigest()


def test_missing_artifact_fails_the_build(build, tmp_path):
    """A builder that reports success without producing a file must not pass.

    _fail exits non-zero, so the build stops rather than publishing an
    artifact with a checksum of nothing.
    """
    with pytest.raises(SystemExit) as excinfo:
        build.write_checksum(tmp_path / "never-built.tar.xz")

    assert excinfo.value.code == 1
    assert not (tmp_path / "never-built.tar.xz.sha256").exists()


def test_rewriting_an_artifact_refreshes_its_sidecar(build, tmp_path):
    """Rebuilding over an existing artifact does not leave a stale digest."""
    artifact = tmp_path / "smart-organizer-1.0.0-linux-x86_64.tar.xz"
    artifact.write_bytes(b"first build")
    first = build.write_checksum(artifact).read_text(encoding="utf-8")

    artifact.write_bytes(b"second build, different length")
    second = build.write_checksum(artifact).read_text(encoding="utf-8")

    assert first != second
    assert second.split()[0] == hashlib.sha256(b"second build, different length").hexdigest()
