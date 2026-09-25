"""Placeholder desktop GUI entry point (Phase 3).

In Phase 0 this only confirms the package structure. The PySide6
desktop application is implemented in Phase 3.
"""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    """Stub entry point for the future desktop application."""
    print("Smart File Organizer desktop GUI is coming in Phase 3.", file=sys.stdout)
    print("Meanwhile, use the CLI:  smart-organizer --help", file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())