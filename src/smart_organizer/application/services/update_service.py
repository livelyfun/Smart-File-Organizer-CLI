"""Check whether a newer release is available.

Strictly check-and-notify. This module downloads nothing, writes nothing,
and never modifies the installation. It reads a small JSON manifest over
HTTPS, compares the packaged version against the running one, and reports
what it found. Applying an update stays a decision the user makes.

That restriction is deliberate. A self-updating installer that rewrites its
own files needs code signing to be trustworthy, and this project is not
signed. An updater that silently replaced an unsigned binary would be a
downgrade in safety, not an improvement.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_MANIFEST_URL = (
    "https://livelyfun.github.io/Smart-File-Organizer-CLI/latest.json"
)

# Deliberately small. This is a metadata fetch on a user-facing command, so
# it must not hang the CLI if a proxy or captive portal is in the way.
DEFAULT_TIMEOUT_SECONDS = 5.0

MAX_MANIFEST_BYTES = 256 * 1024


class UpdateCheckError(Exception):
    """Raised when the update manifest could not be read."""


@dataclass(frozen=True)
class Release:
    """A published release as described by the manifest."""

    version: str
    notes_url: str = ""
    published_at: str = ""

    @classmethod
    def from_manifest(cls, data: dict) -> "Release":
        version = data.get("version")
        if not isinstance(version, str) or not version.strip():
            raise UpdateCheckError("manifest has no usable 'version' field")
        return cls(
            version=version.strip(),
            notes_url=str(data.get("notes_url", "")),
            published_at=str(data.get("published_at", "")),
        )


@dataclass(frozen=True)
class UpdateStatus:
    """Outcome of a check, ready to render."""

    current_version: str
    latest_version: Optional[str]
    update_available: bool

    @property
    def checked(self) -> bool:
        return self.latest_version is not None


def _parse_version(version: str) -> tuple:
    """Split a version into comparable numeric components.

    Non-numeric trailing parts such as ``1.2.0rc1`` are kept as a final
    element so pre-releases do not silently compare as greater than the
    release they precede.
    """
    parts: list = []
    for chunk in version.strip().lstrip("vV").split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            digits = "".join(c for c in chunk if c.isdigit())
            parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Return True when *latest* is a strictly newer release."""
    latest_parts = _parse_version(latest)
    current_parts = _parse_version(current)
    # Pad so 1.2 and 1.2.0 compare equal.
    length = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (length - len(latest_parts))
    current_parts += (0,) * (length - len(current_parts))
    return latest_parts > current_parts


def fetch_manifest(
    url: str = DEFAULT_MANIFEST_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Release:
    """Download and parse the release manifest.

    Raises UpdateCheckError on any failure. Callers are expected to turn
    that into an advisory message: a failed update check is never a reason
    to stop the user doing their actual work.
    """
    try:
        # A bare SSL context is used rather than an unverified one. An
        # update check that cannot authenticate its source is worthless.
        context = ssl.create_default_context()
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "smart-file-organizer-update-check",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            # Refuse an implausibly large response rather than buffering it.
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_MANIFEST_BYTES:
                raise UpdateCheckError(
                    f"manifest is {declared} bytes, refusing to download it"
                )
            payload = response.read(MAX_MANIFEST_BYTES + 1)

    except urllib.error.HTTPError as exc:
        raise UpdateCheckError(f"server returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"could not reach the update server: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpdateCheckError("the update server did not respond in time") from exc
    except ssl.SSLError as exc:
        raise UpdateCheckError(f"could not establish a secure connection: {exc}") from exc
    except OSError as exc:
        raise UpdateCheckError(f"network error: {exc}") from exc

    if len(payload) > MAX_MANIFEST_BYTES:
        raise UpdateCheckError("manifest is larger than expected; refusing to parse it")

    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(f"manifest is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise UpdateCheckError("manifest is not a JSON object")

    return Release.from_manifest(data)


def check_for_update(
    current_version: str,
    url: str = DEFAULT_MANIFEST_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> UpdateStatus:
    """Check for a newer release.

    Never raises: on any failure the returned status reports that no update
    was detected, and the caller can tell the difference via `.checked`.
    """
    try:
        release = fetch_manifest(url=url, timeout=timeout)
    except UpdateCheckError:
        return UpdateStatus(
            current_version=current_version,
            latest_version=None,
            update_available=False,
        )
    return UpdateStatus(
        current_version=current_version,
        latest_version=release.version,
        update_available=is_newer(release.version, current_version),
    )
