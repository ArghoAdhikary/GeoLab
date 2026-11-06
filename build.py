"""Build a standalone app with PyInstaller.

    python build.py

Windows: dist/GeoLab/GeoLab.exe     macOS: dist/GeoLab.app
"""
import platform
import subprocess
import sys
from pathlib import Path


def make_icon_file() -> str | None:
    """Draw the app icon (same as the window icon) to build/geolab.ico for the Windows exe."""
    if platform.system() != "Windows":
        return None
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["build", "-platform", "offscreen"])
    from geolab.__main__ import make_icon
    out = Path("build")
    out.mkdir(exist_ok=True)
    path = out / "geolab.ico"
    make_icon().pixmap(256, 256).save(str(path), "ICO")
    del app
    return str(path) if path.exists() else None


args = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "GeoLab",
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
]
icon = make_icon_file()
if icon:
    args += ["--icon", icon]
if platform.system() == "Darwin":
    args += ["--osx-bundle-identifier", "io.github.geolab"]
args.append("run_geolab.py")
sys.exit(subprocess.call(args))
