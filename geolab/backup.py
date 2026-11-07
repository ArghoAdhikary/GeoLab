"""Autosave and backup copies to a cloud drive folder (Google Drive, OneDrive, Dropbox, iCloud).

GeoLab does not talk to the cloud services itself. It writes dated copies into the folder that the
service's desktop app keeps in sync, for example ``G:\\My Drive`` for Google Drive for desktop.
The service then uploads the copies. This needs no sign-in inside GeoLab, works offline (the copies
upload later), and keeps the files under the user's own account.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import string
import sys
from pathlib import Path

BACKUP_FOLDER = "GeoLab Backups"


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def detect_drives() -> dict[str, str]:
    """Synced cloud folders on this computer: {label: path}. Only folders that exist are listed."""
    found: dict[str, str] = {}
    home = _home()

    def add(label, p):
        p = Path(p)
        if p.is_dir() and str(p) not in found.values():
            found[label] = str(p)

    # Google Drive for desktop: a drive letter (G:) holding "My Drive", or a folder in the home folder
    if sys.platform == "win32":
        for letter in string.ascii_uppercase[3:]:
            for name in ("My Drive", "Meine Ablage", "Mon Drive"):
                p = Path(f"{letter}:\\{name}")
                try:
                    if p.is_dir():
                        add(f"Google Drive ({letter}:)", p)
                except OSError:
                    pass
    for name in ("Google Drive", "My Drive", "GoogleDrive"):
        add("Google Drive", home / name)
        add("Google Drive", home / name / "My Drive")
    cloud = home / "Library" / "CloudStorage"            # macOS
    if cloud.is_dir():
        for d in sorted(cloud.iterdir()):
            if d.name.startswith("GoogleDrive-"):
                add(f"Google Drive ({d.name[12:]})", d / "My Drive" if (d / "My Drive").is_dir() else d)
            elif d.name.startswith("OneDrive"):
                add(d.name.replace("-", " (", 1) + (")" if "-" in d.name else ""), d)
            elif d.name.startswith("Dropbox"):
                add("Dropbox", d)
    for var, label in (("OneDrive", "OneDrive"), ("OneDriveConsumer", "OneDrive (personal)"),
                       ("OneDriveCommercial", "OneDrive (work)")):
        if os.environ.get(var):
            add(label, os.environ[var])
    add("OneDrive", home / "OneDrive")
    add("Dropbox", home / "Dropbox")
    add("iCloud Drive", home / "iCloudDrive")
    add("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    return found


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name or "").strip(" .")
    return name[:80] or "Untitled"


def backup_copy(src, folder, stem: str | None = None, keep: int = 10, now: _dt.datetime | None = None) -> Path:
    """Copy ``src`` to ``folder/GeoLab Backups/<stem>/<stem> YYYY-MM-DD HHMM<ext>``.

    Keeps the newest ``keep`` copies of that project (0 keeps all). Returns the new copy."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(src)
    stem = safe_name(stem or src.stem)
    target = Path(folder) / BACKUP_FOLDER / stem
    target.mkdir(parents=True, exist_ok=True)
    now = now or _dt.datetime.now()
    dst = target / f"{stem} {now:%Y-%m-%d %H%M}{src.suffix}"
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    prune(target, src.suffix, keep)
    return dst


def versions(folder, stem: str, ext: str = ".slab") -> list[Path]:
    d = Path(folder) / BACKUP_FOLDER / safe_name(stem)
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.suffix.lower() == ext.lower() and p.is_file()),
                  key=lambda p: p.name, reverse=True)


def prune(target: Path, ext: str, keep: int):
    if keep <= 0:
        return []
    files = sorted((p for p in Path(target).iterdir() if p.suffix.lower() == ext.lower() and p.is_file()),
                   key=lambda p: p.name, reverse=True)
    removed = []
    for old in files[keep:]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass
    return removed


def autosave_dir() -> Path:
    """Folder for the autosaved copies of projects that have no file yet."""
    try:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    except Exception:                       # noqa: BLE001
        base = ""
    exe_dir = Path(sys.executable).parent
    if getattr(sys, "frozen", False) and (exe_dir / "portable.txt").exists():
        base = str(exe_dir / "GeoLab data")
    d = Path(base or (Path.home() / ".geolab")) / "Autosave"
    return d


def autosave_path(title: str) -> Path:
    return autosave_dir() / (safe_name(title or "Untitled") + " (autosave).slab")
