"""Launcher used by PyInstaller builds."""
import sys

from geolab.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
