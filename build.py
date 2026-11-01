"""Build a standalone app with PyInstaller.

    python build.py

Windows: dist/StrataLab/StrataLab.exe     macOS: dist/StrataLab.app
"""
import platform
import subprocess
import sys

args = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "StrataLab",
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
    "run_stratalab.py",
]
if platform.system() == "Darwin":
    args[4:4] = ["--osx-bundle-identifier", "io.github.stratalab"]
sys.exit(subprocess.call(args))
