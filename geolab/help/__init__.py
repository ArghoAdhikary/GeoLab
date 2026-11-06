"""The user manual, the tutorials and the example files that ship with GeoLab.

The text is Markdown in geolab/help/manual and geolab/help/tutorials. The pictures (img/) and the PDF
manual are made by build_docs.py; when they are missing (running from source without building the
docs), the help still works without pictures.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDF_NAME = "GeoLab-User-Manual.pdf"


def _built_dir() -> Path:
    """Folder that holds the built PDF and example files."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "help"
    return HERE.parents[1] / "build" / "help"


def img_dir() -> Path:
    return HERE / "img"


def pdf_path() -> Path | None:
    p = _built_dir() / PDF_NAME
    return p if p.exists() else None


def bundled_examples_dir() -> Path | None:
    p = _built_dir() / "examples"
    return p if p.is_dir() and any(p.glob("*.slab")) else None


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def chapters() -> list[dict]:
    """Manual chapters in order: [{'title', 'path', 'text'}]."""
    out = []
    for p in sorted((HERE / "manual").glob("*.md")):
        t = _read(p)
        out.append({"title": _title(t, p.stem), "path": p, "text": t})
    return out


_EXAMPLE = re.compile(r"<!--\s*example:\s*(.+?)\s*-->")
_QUICK = re.compile(r"<!--\s*quick:\s*(\{.*?\})\s*-->", re.S)
_CHECK = re.compile(r"<!--\s*check:\s*(.+?)\s*-->")


def tutorials() -> list[dict]:
    """Tutorials in order: [{'title', 'path', 'text', 'example', 'quick', 'checks'}].

    'example' is the name of the built-in example it uses (or None), 'quick' the Quick Slope inputs,
    'checks' the results it quotes: (source, analysis index, result path, value, relative tolerance)."""
    out = []
    for p in sorted((HERE / "tutorials").glob("*.md")):
        t = _read(p)
        m = _EXAMPLE.search(t)
        q = _QUICK.search(t)
        checks = []
        for c in _CHECK.findall(t):
            src, idx, path, val, tol = [x.strip() for x in c.split("|")]
            checks.append((src, int(idx), path, float(val), float(tol)))
        out.append({"title": _title(t, p.stem), "path": p, "text": t, "example": m.group(1) if m else None,
                    "quick": json.loads(q.group(1)) if q else None, "checks": checks})
    return out


def clean_markdown(text: str, with_images: bool | None = None) -> str:
    """Markdown for display: no hidden check comments; image lines dropped when the pictures are absent."""
    text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.S)
    if with_images is None:
        with_images = img_dir().is_dir()
    if not with_images:
        text = re.sub(r"^!\[[^\]]*\]\([^)]*\)\s*$\n?", "", text, flags=re.M)
    return text.strip() + "\n"


def result_value(results: dict, path: str):
    """Pick a number out of an analysis result: 'critical.fos', 'structures.0.max_M', ... plus a few
    derived values used by the tutorials."""
    if path == "footing_pressure":
        rx = results["reactions"]
        key = next(k for k in rx if k.lower().startswith("footing"))
        return -rx[key][1] / 1.0
    if path == "settlement_first":
        return results["settlement_history"][0]
    if path == "settlement_last":
        return results["settlement_history"][-1]
    v = results
    for part in path.split("."):
        v = v[int(part)] if isinstance(v, list) else v[part]
    return v
