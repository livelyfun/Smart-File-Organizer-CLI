# Packaging and Distribution

How the standalone builds are produced, what each artifact is, and what is
not yet true about them. The short version: a build that passes CI is
verified to work, and nothing is code signed.

## Layout

```
packaging/
  build.py                      orchestrates a build end to end
  smoke_test.py                 verifies a frozen binary actually works
  pyinstaller/
    smart-organizer.spec        the onedir bundle definition
    app.ico                     multi-resolution Windows icon
  windows/smart-organizer.iss   Inno Setup installer
  tools/make_icon.py            regenerates app.ico
  output/                       build output (gitignored)
```

## Building

```bash
python packaging/build.py --clean              # bundle only
python packaging/build.py --clean --smoke-test # bundle, then verify it
python packaging/build.py --clean --installer  # bundle plus native installer
```

`--clean` discards previous output. Release builds should always use it: a
bundle that inherits a file from an earlier run is not reproducible, and the
tree checksum the build reports would be meaningless.

PyInstaller runs from a virtual environment created at `.build-venv/`, not
from whatever happens to be installed on the machine. A stray PySide6 or an
incompatible PyInstaller must not be able to change what ships.

## Artifacts

| Platform | Artifact | Built by |
| --- | --- | --- |
| Linux | `smart-organizer-<ver>-linux-x86_64.tar.xz` + `.sha256` | `tar` |
| macOS | `SmartFileOrganizer-<ver>-macos.dmg` + `.sha256` | `hdiutil` |
| Windows | `SmartFileOrganizer-<ver>-setup.exe` + `.sha256` | Inno Setup (`iscc`) |

Every artifact gets a `.sha256` sidecar from a single call site in
`build.py`, so one platform cannot ship without it. The sidecar is the format
`sha256sum` writes, and both install scripts refuse to install a download whose
digest does not match. The Build workflow fails the build if any artifact is
missing its sidecar.

Linux uses a tarball rather than an AppImage. AppImage needs FUSE to launch,
is awkward to extract without it, and expects a desktop entry that a command
line tool has no use for.

macOS ships a DMG containing the executable and an `install.command` that
puts it on PATH. There is no `.app` bundle, because a CLI gains nothing from
Finder integration and it would add a signing obligation for no benefit.

Windows needs the Inno Setup compiler, installed in CI with
`choco install innosetup`.

## Versioning

The version lives in exactly one place, `__version__` in
`src/smart_organizer/__init__.py`. `pyproject.toml` reads it through
setuptools' dynamic version directive, the spec generates the Windows
VERSIONINFO resource from it, and the installers take it as a build
parameter. A release is cut by bumping that one line.

## Why the build is strict about hidden imports

`core/watcher.py` does `from watchdog.observers import Observer`, and
watchdog resolves that through a conditional import evaluated **at module
import time**. PyInstaller's static analysis follows only the branch
matching the build machine, so a bundle can build cleanly and then be
unable to watch anything.

Each platform's backend is therefore named explicitly in the spec, and the
build fails if any of them cannot be resolved. PyInstaller reports a missing
hidden import at ERROR level and then emits a binary anyway, which is why
that case is checked rather than trusted.

The failure is not uniform across platforms, which is worth knowing:

- **Linux** raises `ModuleNotFoundError` outright; only `UnsupportedLibcError`
  is suppressed, so a missing backend is fatal.
- **Windows and macOS** catch the import failure, emit a warning, and fall
  back to polling. The binary still works, just slowly and with much more
  CPU.

A naive smoke test would therefore pass a quietly degraded Windows or macOS
build. `smoke_test.py` treats the fallback warning as a failure, so the
native backend is actually verified everywhere.

## What the smoke test checks

`--version` proving the binary starts proves almost nothing, so the smoke
test exercises behaviour instead: it organizes a file already on disk, then
starts watch mode, drops a file, and requires it to be categorized.

Live watch has no ready signal to synchronise on, because the CLI prints its
banner before the observer is scheduled. A dropped file is therefore retried
with a fresh name until it is categorized. Either the observer works or the
test fails; there is no false pass.

Shutdown is checked too. On Windows this is `CTRL_BREAK_EVENT`, because
`CREATE_NEW_PROCESS_GROUP` disables `CTRL_C_EVENT` for the new group, and the
application maps `CTRL_BREAK_EVENT` to `SIGBREAK` and stops cleanly.

Each run gets a throwaway directory and its own config file, so it never
touches real user configuration, and no watcher is left running.

## Updates are check-and-notify only

`smart-organizer --check-update` reports whether a newer release exists. It
downloads nothing, writes nothing, and cannot install anything. Tests assert
that constraint rather than leaving it to review.

This is deliberate. A self-updating installer that rewrites its own files
needs code signing to be trustworthy, and this project is not signed. An
updater that silently replaced an unsigned binary would be a downgrade in
safety.

The update check reads a small JSON manifest over verified TLS, refuses an
implausibly large response, and treats any failure as advisory. It never
blocks the user's actual work.

## Not yet done: code signing and notarization

**Nothing produced by this pipeline is signed.** Concretely:

- **macOS.** The executable and DMG are unsigned, so Gatekeeper reports that
  the developer cannot be verified, and the first launch needs an explicit
  override (right-click, Open, or `xattr -dr com.apple.quarantine <path>`).
  This is the roughest edge of the current distribution. Real distribution
  needs an Apple Developer ID, a `codesign` identity passed to the spec, and
  `xcrun notarytool` stapling.
- **Windows.** Unsigned, so SmartScreen will warn on first run and users must
  click "More info" then "Run anyway". A code-signing certificate removes
  this. The spec's `codesign_identity` and `entitlements_file` hooks are in
  place for macOS; Windows signing is configured through Inno Setup's
  `SignTool`, which is deliberately absent because an empty one is a compile
  error.
- **Linux.** Archive signing is not attempted.

Signing is the single highest-value follow-up, and it is blocked only on
having certificates.

## Release process

1. Bump `__version__` in `src/smart_organizer/__init__.py`.
2. Update `CHANGELOG` if present.
3. Merge to `main` and confirm both CI and Build workflows are green.
4. Tag `v<version>` and push the tag.
5. Attach the artifacts and their `.sha256` files to the GitHub release, and
   publish `latest.json` for the update check:

```json
{
  "version": "1.2.0",
  "published_at": "2026-01-01T00:00:00Z",
  "notes_url": "https://github.com/livelyfun/Smart-File-Organizer-CLI/releases/tag/v1.2.0"
}
```

`update_service.py` reads that manifest and nothing else, so publishing it
is the only step needed for `--check-update` to start reporting the release.
