"""CLI entry‑point: ``python -m claude-code``."""

import sys

from cli.commands import main

if __name__ == "__main__":
    sys.exit(main())
