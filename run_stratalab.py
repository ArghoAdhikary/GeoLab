"""Launcher used by PyInstaller builds."""
import sys

from stratalab.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
