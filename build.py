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


def mkl_binaries() -> list[str]:
    """Intel MKL DLLs used by the PARDISO solver (Windows): the runtime dispatcher, the core, the
    threading layers, the CPU-specific kernels and the OpenMP runtime."""
    if platform.system() != "Windows":
        return []
    try:
        import pypardiso  # noqa: F401
    except ImportError:
        print("pypardiso is not installed: building without the MKL solver")
        return []
    import glob
    import os
    out = []
    for folder in {os.path.join(sys.prefix, "Library", "bin"), os.path.join(sys.base_prefix, "Library", "bin")}:
        for pat in ("mkl_rt*.dll", "mkl_core*.dll", "mkl_intel_thread*.dll", "mkl_sequential*.dll",
                    "mkl_tbb_thread*.dll", "mkl_def*.dll", "mkl_mc3*.dll", "mkl_avx2*.dll", "mkl_avx512*.dll",
                    "mkl_avx10*.dll", "libiomp5md.dll", "tbb12.dll", "tbbmalloc.dll"):
            out += glob.glob(os.path.join(folder, pat))
    out = sorted(set(out))
    if not any("mkl_rt" in os.path.basename(f) for f in out):
        print("MKL runtime not found: building without the MKL solver")
        return []
    size = sum(os.path.getsize(f) for f in out) / 1e6
    print(f"Bundling {len(out)} MKL files ({size:.0f} MB)")
    return out


args = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "GeoLab",
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
    "--hidden-import", "pypardiso",
    # the manual and tutorials (Markdown and pictures) inside the geolab package
    "--add-data", f"geolab/help{';' if platform.system() == 'Windows' else ':'}geolab/help",
]
SEP = ";" if platform.system() == "Windows" else ":"
help_build = Path("build") / "help"
if (help_build / "GeoLab-User-Manual.pdf").exists():
    args += ["--add-data", f"{help_build / 'GeoLab-User-Manual.pdf'}{SEP}help"]
    args += ["--add-data", f"{help_build / 'examples'}{SEP}help/examples"]
else:
    print("build/help is missing (run python build_docs.py first): building without the PDF manual and examples")
for f in mkl_binaries():
    args += ["--add-binary", f"{f}{SEP}."]
icon = make_icon_file()
if icon:
    args += ["--icon", icon]
if platform.system() == "Darwin":
    args += ["--osx-bundle-identifier", "io.github.geolab"]
args.append("run_geolab.py")
sys.exit(subprocess.call(args))
