"""Smart File Organizer - Root launcher entrypoint."""

import sys
from pathlib import Path

# Ensure src directory is on sys.path when run directly from repository root
_src_dir = Path(__file__).resolve().parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from smart_organizer.cli import main

if __name__ == "__main__":
    sys.exit(main())

