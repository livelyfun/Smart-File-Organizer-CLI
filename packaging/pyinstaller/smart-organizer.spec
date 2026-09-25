# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Smart File Organizer command line application.

Builds a standalone executable that bundles a Python interpreter, so
end users never have to install Python.

This spec deliberately uses ``onedir``. A one-file bundle has to extract
itself to a temporary directory on every launch, which is slow, and the
resulting single executable is a well-known source of antivirus false
positives. A directory keeps startup fast and gives the thin installers
something natural to wrap.

Run it through ``packaging/build.py`` rather than invoking PyInstaller
directly, so the version and output paths are resolved consistently.
"""

import sys
from pathlib import Path

# Globals injected by PyInstaller when it evaluates this spec.
SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from smart_organizer import __version__  # noqa: E402  (needs SRC on sys.path)

APP_NAME = "smart-organizer"

# --------------------------------------------------------------------------
# Version metadata
# --------------------------------------------------------------------------
# The version is read from the single source of truth in the package, so a
# release never has to be stamped here by hand.

WIN_VERSION_FILE = ""

if sys.platform == "win32":
    # Windows executables carry a VERSIONINFO resource. Generate it rather
    # than committing a file that would need editing on every release.
    WIN_VERSION_FILE = str(Path(SPEC_DIR).resolve() / "_version_info.txt")
    _version_tuple = tuple(int(p) for p in __version__.split(".")[:4] if p.isdigit())
    _version_tuple = (_version_tuple + (0, 0, 0, 0))[:4]
    _version_str = ".".join(str(p) for p in _version_tuple)

    Path(WIN_VERSION_FILE).write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_version_tuple},
    prodvers={_version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'Smart File Organizer Contributors'),
            StringStruct('FileDescription', 'Smart File Organizer'),
            StringStruct('FileVersion', '{_version_str}'),
            StringStruct('InternalName', '{APP_NAME}'),
            StringStruct('OriginalFilename', '{APP_NAME}.exe'),
            StringStruct('ProductName', 'Smart File Organizer'),
            StringStruct('ProductVersion', '{_version_str}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )

# --------------------------------------------------------------------------
# Hidden imports
# --------------------------------------------------------------------------
# core/watcher.py does `from watchdog.observers import Observer`, and watchdog
# resolves that through a *conditional* per-platform import. PyInstaller's
# static analysis only follows the branch matching the build machine, so a
# frozen build can otherwise succeed and then fail to watch anything at
# runtime. Each backend is therefore named explicitly.
#
# The polling observer is included on every platform on purpose: inotify
# watches run out on systems with a low fs.inotify.max_user_watches, and a
# file organiser that silently stops watching is worse than a slower one.

WATCHDOG_HIDDEN_IMPORTS = {
    "linux": [
        "watchdog.observers.inotify",
        "watchdog.observers.inotify_buffer",
        "watchdog.observers.inotify_c",
    ],
    # watchdog's darwin branch tries fsevents, then kqueue, then polling,
    # so both native backends are named explicitly.
    "darwin": [
        "watchdog.observers.fsevents",
        "watchdog.observers.kqueue",
    ],
    "win32": [
        "watchdog.observers.read_directory_changes",
        "watchdog.observers.winapi",
    ],
}

if sys.platform.startswith("linux"):
    _platform_imports = WATCHDOG_HIDDEN_IMPORTS["linux"]
elif sys.platform == "darwin":
    _platform_imports = WATCHDOG_HIDDEN_IMPORTS["darwin"]
elif sys.platform == "win32":
    _platform_imports = WATCHDOG_HIDDEN_IMPORTS["win32"]
else:
    _platform_imports = []

hiddenimports = [
    # Backward-compatible re-export shims are imported by third parties, so
    # they must survive even though the CLI does not use them.
    "smart_organizer.classifier",
    "smart_organizer.config",
    "smart_organizer.file_manager",
    "smart_organizer.logger",
    "smart_organizer.organizer",
    "smart_organizer.platform_utils",
    "smart_organizer.stability",
    "smart_organizer.watcher",
    "smart_organizer.gui",
] + _platform_imports + [
    # Portable fallback when the native backend is unavailable.
    "watchdog.observers.polling",
]

# --------------------------------------------------------------------------
# Exclusions
# --------------------------------------------------------------------------
# The CLI target must stay small and must never drag in a GUI toolkit.
# PySide6 in particular is an optional extra and is only needed by the
# desktop application target.

excludes = [
    "PySide6",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "tkinter",
    "pytest",
    "_pytest",
    "IPython",
    "notebook",
    "numpy",
    "PIL",
    "matplotlib",
    "pandas",
    "setuptools",
    "pip",
]

# A multi-resolution .ico is only meaningful for a Windows executable.
# Regenerate with: python packaging/tools/make_icon.py
ICON_FILE = str(SPEC_DIR / "app.ico") if sys.platform == "win32" else None

a = Analysis(
    [str(SRC / "smart_organizer" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=(WIN_VERSION_FILE or None),
    icon=ICON_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
