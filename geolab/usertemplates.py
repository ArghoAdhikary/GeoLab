"""Your own project templates (File > New from My Template) and the solver quality presets.

A template is a normal project file saved without results in the templates folder: your usual materials,
design code, units, analyses and drawing settings. New projects made from it start with all of them.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

QUALITY = {
    "fast": {"label": "Fast (coarser search and mesh)", "n_slices": 20, "n_entry": 6, "n_exit": 6, "n_radius": 4,
             "grid_nx": 6, "grid_ny": 6, "n_radii": 5, "mesh": 1.5},
    "normal": {"label": "Normal", "n_slices": 30, "n_entry": 10, "n_exit": 10, "n_radius": 6, "grid_nx": 10,
               "grid_ny": 10, "n_radii": 8, "mesh": 1.0},
    "fine": {"label": "Fine (more accurate, slower)", "n_slices": 50, "n_entry": 16, "n_exit": 16, "n_radius": 10,
             "grid_nx": 16, "grid_ny": 16, "n_radii": 12, "mesh": 0.6},
}


def apply_quality(analysis, level: str):
    q = QUALITY.get(level)
    if not q or level == "normal":
        return analysis
    analysis.n_slices = q["n_slices"]
    s = analysis.search
    for k in ("n_entry", "n_exit", "n_radius", "grid_nx", "grid_ny", "n_radii"):
        if hasattr(s, k):
            setattr(s, k, q[k])
    analysis.mesh_size = analysis.mesh_size * q["mesh"]
    return analysis


def templates_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "GeoLab" / "Templates"
    return d


def _name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", s).strip(" .") or "Template"


def save_template(project, name: str, folder: Path | None = None) -> Path:
    from .fileio import save_project
    d = Path(folder) if folder else templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_name(name)}.slab"
    save_project(project, path, include_results=False)
    return path


def list_templates(folder: Path | None = None) -> list[Path]:
    d = Path(folder) if folder else templates_dir()
    return sorted(d.glob("*.slab"), key=lambda p: p.stem.lower()) if d.is_dir() else []


def new_from_template(path):
    from .fileio import load_project
    p = load_project(path)
    for a in p.analyses:
        a.results = None
    if p.title == Path(path).stem:
        p.title = "Untitled"
    return p


def delete_template(path):
    Path(path).unlink(missing_ok=True)
