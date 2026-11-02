"""Reading and writing StrataLab project files (.slab) and exports."""
from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from . import __version__
from .model import Project

FORMAT_VERSION = 1


def save_project(project: Project, path, include_results: bool = True):
    """A .slab file is a zip archive holding project.json (and a small manifest)."""
    path = Path(path)
    data = project.to_dict(include_results=include_results)
    manifest = {"app": "StrataLab", "app_version": __version__, "format_version": FORMAT_VERSION}
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("project.json", json.dumps(data))
    tmp.replace(path)


def load_project(path) -> Project:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() == ".json":
        return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
    try:
        with zipfile.ZipFile(path) as z:
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("format_version", 0) > FORMAT_VERSION:
                raise ValueError("This file was created by a newer version of StrataLab.")
            data = json.loads(z.read("project.json"))
    except zipfile.BadZipFile as e:
        raise ValueError(f"{path.name} is not a valid StrataLab project file.") from e
    except KeyError as e:
        raise ValueError(f"{path.name} is missing {e.args[0]}.") from e
    return Project.from_dict(data)


def export_json(project: Project, path):
    Path(path).write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")


def export_results_csv(project: Project, analysis, path):
    r = analysis.results
    if not r:
        raise ValueError("The analysis has no results to export.")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if r["type"] == "slope":
            crit = r.get("critical")
            if not crit:
                raise ValueError("The analysis has no valid slip surface.")
            w.writerow(["# Factor of safety", crit["fos"], "method", r["method"]])
            rows = crit["slices"]
            w.writerow(list(rows[0].keys()))
            for row in rows:
                w.writerow(list(row.values()))
        else:
            # every nodal field of the result (same length as the node list)
            n = len(r["nodes"])
            keys = [k for k, v in r.items() if isinstance(v, list) and len(v) == n and k != "nodes"
                    and v and not isinstance(v[0], (list, dict))]
            w.writerow(["node", "x", "y", *keys])
            for i, xy in enumerate(r["nodes"]):
                w.writerow([i + 1, xy[0], xy[1], *(r[k][i] for k in keys)])


def import_points_csv(path) -> list[list[float]]:
    """Read x,y pairs (one per line, header optional) for keyboard/paste style point entry."""
    pts = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            try:
                pts.append([float(row[0]), float(row[1])])
            except ValueError:
                continue
    if len(pts) < 3:
        raise ValueError("Need at least three x,y points to make a region.")
    return pts
