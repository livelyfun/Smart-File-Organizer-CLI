"""Tests for the check-and-notify update service.

The load-bearing properties here are the negative ones: a failed check must
stay advisory, the manifest must be validated, and nothing may write to the
installation.
"""

import json
import ssl
import urllib.error

import pytest

from smart_organizer import __version__
from smart_organizer.application.services.update_service import (
    MAX_MANIFEST_BYTES,
    Release,
    UpdateCheckError,
    UpdateStatus,
    check_for_update,
    fetch_manifest,
    is_newer,
)


class _FakeResponse:
    def __init__(self, payload: bytes, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def read(self, size=-1):
        if size is None or size < 0:
            return self._payload
        return self._payload[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestVersionComparison:
    @pytest.mark.parametrize(
        "latest,current,expected",
        [
            ("1.0.1", "1.0.0", True),
            ("1.1.0", "1.0.9", True),
            ("2.0.0", "1.99.99", True),
            ("1.0.0", "1.0.0", False),
            ("0.9.9", "1.0.0", False),
            ("1.2", "1.2.0", False),
            ("1.2.1", "1.2", True),
            ("v1.3.0", "1.2.0", True),
        ],
    )
    def test_is_newer(self, latest, current, expected):
        assert is_newer(latest, current) is expected


class TestManifestParsing:
    def test_parses_a_well_formed_manifest(self, monkeypatch):
        payload = json.dumps(
            {"version": "1.4.0", "notes_url": "https://example.invalid/notes"}
        ).encode("utf-8")
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        release = fetch_manifest()
        assert release.version == "1.4.0"
        assert release.notes_url.endswith("/notes")

    def test_rejects_manifest_without_a_version(self, monkeypatch):
        payload = json.dumps({"notes_url": "https://example.invalid"}).encode("utf-8")
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        with pytest.raises(UpdateCheckError):
            fetch_manifest()

    def test_rejects_non_json(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(b"<html>nope</html>")
        )
        with pytest.raises(UpdateCheckError):
            fetch_manifest()

    def test_rejects_json_that_is_not_an_object(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(b"[1, 2, 3]")
        )
        with pytest.raises(UpdateCheckError):
            fetch_manifest()

    def test_refuses_an_implausibly_large_declared_size(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **k: _FakeResponse(
                b"{}", headers={"Content-Length": str(MAX_MANIFEST_BYTES + 1)}
            ),
        )
        with pytest.raises(UpdateCheckError):
            fetch_manifest()

    def test_refuses_a_body_larger_than_the_limit(self, monkeypatch):
        # No Content-Length, so the size guard has to come from the read cap.
        oversized = b"x" * (MAX_MANIFEST_BYTES + 10)
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(oversized)
        )
        with pytest.raises(UpdateCheckError):
            fetch_manifest()


class TestFailureHandling:
    """A failed check is advisory: it reports, and never raises."""

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.HTTPError("u", 404, "Not Found", None, None),
            urllib.error.URLError("no route to host"),
            TimeoutError(),
            ssl.SSLError("bad handshake"),
            OSError("connection reset"),
        ],
    )
    def test_check_for_update_never_raises(self, monkeypatch, error):
        def _raise(*args, **kwargs):
            raise error

        monkeypatch.setattr("urllib.request.urlopen", _raise)

        status = check_for_update(__version__)
        assert isinstance(status, UpdateStatus)
        assert status.checked is False
        assert status.update_available is False
        assert status.current_version == __version__

    def test_reports_update_when_manifest_is_newer(self, monkeypatch):
        payload = json.dumps({"version": "99.0.0"}).encode("utf-8")
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        status = check_for_update(__version__)
        assert status.checked is True
        assert status.update_available is True
        assert status.latest_version == "99.0.0"

    def test_reports_up_to_date_when_manifest_matches(self, monkeypatch):
        payload = json.dumps({"version": __version__}).encode("utf-8")
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        status = check_for_update(__version__)
        assert status.checked is True
        assert status.update_available is False


class TestSafetyProperties:
    def test_uses_a_verified_tls_context(self, monkeypatch):
        """An update check that cannot authenticate its source is worthless."""
        seen = {}

        def _capture(request, timeout=None, context=None):
            seen["context"] = context
            return _FakeResponse(json.dumps({"version": "1.0.0"}).encode("utf-8"))

        monkeypatch.setattr("urllib.request.urlopen", _capture)
        fetch_manifest()

        context = seen["context"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True

    def test_module_exposes_no_download_capability(self):
        """The service must not be able to apply an update.

        This is a design constraint rather than a runtime check: a
        self-updating installer would need code signing to be trustworthy,
        and this project is unsigned.
        """
        import smart_organizer.application.services.update_service as module

        source_names = [name for name in dir(module) if not name.startswith("_")]
        forbidden = {"download", "install_update", "apply_update", "self_update"}
        assert not forbidden.intersection(source_names)

        source = module.__file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        # No filesystem writes of any kind.
        assert "open(" not in text.replace(
            "urlopen(", ""
        ), "update service must not open files for writing"
