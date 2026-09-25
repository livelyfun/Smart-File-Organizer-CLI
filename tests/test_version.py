"""Tests for the single-source-of-truth version wiring.

The version literal lives only in ``smart_organizer.__version__``; the
packaging metadata and every build tool read it from there. These tests
guard that wiring rather than re-comparing two hardcoded strings.
"""

from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path

import pytest

from smart_organizer import __version__


def test_version_is_a_literal_setuptools_can_read():
    """The dynamic version directive resolves by static AST read.

    If this ever stops holding - for example if ``__version__`` becomes a
    computed expression - setuptools would have to import the package to
    resolve it, which breaks building from a clean checkout.
    """
    source = (Path(__file__).resolve().parents[1] / "src" / "smart_organizer" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert f'__version__ = "{__version__}"' in source


def test_installed_metadata_matches_package_version():
    """Installed distribution metadata must resolve to the package version."""
    try:
        distribution_version = installed_version("smart-file-organizer")
    except PackageNotFoundError:
        pytest.skip("package is not installed in this environment")

    assert distribution_version == __version__


def test_version_is_a_valid_release_identifier():
    """A malformed version breaks installers and the update feed."""
    parts = __version__.split(".")
    assert len(parts) >= 2
    assert all(part.isdigit() for part in parts[:2])
    assert all(character.isalnum() or character in ".-" for character in __version__)
