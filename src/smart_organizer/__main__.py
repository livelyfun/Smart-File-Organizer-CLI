"""Package entrypoint when executed as python -m smart_organizer."""

import sys
from smart_organizer.cli import main

if __name__ == "__main__":
    sys.exit(main())
