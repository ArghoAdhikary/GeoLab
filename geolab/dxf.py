"""AutoCAD DXF import and export (ASCII DXF, read from R12 to 2018; written as R12, which every CAD
program opens).

Import: closed polylines (LWPOLYLINE / POLYLINE with the closed flag, or whose ends meet) become
regions, and each DXF layer becomes a material. An open polyline on a layer whose name contains
"water" or "piezo" becomes the water table. LINE entities that join end to end into closed loops
are also turned into regions. Arcs and splines are not read: explode them in CAD first.

Export: regions (one layer per material), the water table, the critical slip surface and its factor
of safety, the slices, reinforcement and structures, in model units with y up.
"""
from __future__ import annotations

from pathlib import Path


# --------------------------------------------------------------------------- reading
def _pairs(text: str):
    lines = text.splitlines()
    for i in range(0, len(lines) - 1, 2):
        yield lines[i].strip(), lines[i + 1].rstrip("\r")


def read_entities(path_or_text) -> list[dict]:
    """Entities of the ENTITIES section: {"type", "layer", "points": [(x, y)], "closed"}."""
    if isinstance(path_or_text, (str, Path)) and Path(str(path_or_text)).suffix.lower() == ".dxf" \
            and Path(str(path_or_text)).exists():
        raw = Path(path_or_text).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    else:
        text = str(path_or_text)
    if text.startswith("AutoCAD Binary DXF"):
        raise ValueError("Binary DXF is not supported: save it as ASCII DXF.")
    ents, cur, poly = [], None, None
    section = None
    pairs = list(_pairs(text))
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if code == "0" and val == "SECTION":
            section = pairs[i + 1][1].strip() if i + 1 < len(pairs) else None
            i += 2
            continue
        if code == "0" and val == "ENDSEC":
            section = None
        if section != "ENTITIES":
            i += 1
            continue
        if code == "0":
            if cur is not None and cur["type"] in ("LWPOLYLINE", "LINE", "POINT"):
                ents.append(cur)
            if val == "VERTEX" and poly is not None:
                cur = {"type": "VERTEX", "x": None, "y": None}
                poly.setdefault("_v", []).append(cur)
            elif val == "SEQEND" and poly is not None:
                poly["points"] = [(v["x"], v["y"]) for v in poly.pop("_v", []) if v["x"] is not None]
                ents.append(poly)
                poly, cur = None, None
            elif val == "POLYLINE":
                poly = {"type": "POLYLINE", "layer": "0", "points": [], "closed": False}
                cur = poly
            elif val in ("LWPOLYLINE", "LINE", "POINT"):
                cur = {"type": val, "layer": "0", "points": [], "closed": False, "_x": None}
            else:
                cur = None if poly is None else cur
        elif cur is not None:
            if code == "8" and cur.get("type") != "VERTEX":
                cur["layer"] = val.strip()
            elif code == "70" and cur.get("type") in ("LWPOLYLINE", "POLYLINE"):
                cur["closed"] = bool(int(val.strip() or 0) & 1)
            elif cur["type"] == "VERTEX":
                if code == "10":
                    cur["x"] = float(val)
                elif code == "20":
                    cur["y"] = float(val)
            elif cur["type"] in ("LWPOLYLINE", "POINT"):
                if code == "10":
                    cur["_x"] = float(val)
                elif code == "20" and cur["_x"] is not None:
                    cur["points"].append((cur["_x"], float(val)))
                    cur["_x"] = None
            elif cur["type"] == "LINE":
                if code in ("10", "11"):
                    cur["_x"] = float(val)
                elif code in ("20", "21") and cur["_x"] is not None:
                    cur["points"].append((cur["_x"], float(val)))
                    cur["_x"] = None
        i += 1
    if cur is not None and cur.get("type") in ("LWPOLYLINE", "LINE", "POINT") and cur not in ents:
        ents.append(cur)
    for e in ents:
        e.pop("_x", None)
    return ents


def _close(a, b, tol):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _chain_lines(lines, tol):
    """Join LINE segments end to end into closed loops (per layer)."""
    loops = []
    segs = [list(e["points"]) for e in lines if len(e["points"]) == 2]
    while segs:
        chain = segs.pop(0)
        grown = True
        while grown and not _close(chain[0], chain[-1], tol):
            grown = False
            for k, s in enumerate(segs):
                if _close(s[0], chain[-1], tol):
                    chain.append(s[1])
                elif _close(s[1], chain[-1], tol):
                    chain.append(s[0])
                else:
                    continue
                segs.pop(k)
                grown = True
                break
        if len(chain) >= 4 and _close(chain[0], chain[-1], tol):
            loops.append(chain[:-1])
    return loops


COLORS = ["#d9c49c", "#b9a37a", "#a7c49b", "#c9a28a", "#9fb7c9", "#d0b4d8", "#c8c8a0", "#8f8f8f"]


def import_dxf(path, project=None, scale: float = 1.0, flip_y: bool = False):
    """A project (or the given one, with its regions replaced) from a DXF drawing.

    Returns (project, notes)."""
    from .model import new_project
    ents = read_entities(path)
    if not ents:
        raise ValueError("No lines or polylines found in the ENTITIES section.")
    xs = [x for e in ents for x, _ in e["points"]]
    ys = [y for e in ents for _, y in e["points"]]
    size = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    tol = 1e-6 * size + 1e-9

    def tr(pts):
        return [[round(x * scale, 6), round((-y if flip_y else y) * scale, 6)] for x, y in pts]

    closed, water, notes = [], None, []
    by_layer: dict[str, list] = {}
    for e in ents:
        pts = e["points"]
        if e["type"] in ("LWPOLYLINE", "POLYLINE") and len(pts) >= 3:
            if e["closed"] or _close(pts[0], pts[-1], tol):
                if _close(pts[0], pts[-1], tol):
                    pts = pts[:-1]
                closed.append((e["layer"], pts))
            elif any(w in e["layer"].lower() for w in ("water", "piezo", "phreatic", "gwl")):
                water = sorted(pts)
        elif e["type"] in ("LWPOLYLINE", "POLYLINE") and len(pts) == 2 and \
                any(w in e["layer"].lower() for w in ("water", "piezo", "phreatic", "gwl")):
            water = sorted(pts)
        elif e["type"] == "LINE":
            by_layer.setdefault(e["layer"], []).append(e)
    for layer, ls in by_layer.items():
        if any(w in layer.lower() for w in ("water", "piezo", "phreatic", "gwl")):
            pts = sorted({p for e_ in ls for p in e_["points"]})
            if len(pts) >= 2:
                water = pts
            continue
        for loop in _chain_lines(ls, tol):
            closed.append((layer, loop))
    if not closed:
        raise ValueError("No closed shapes found. Draw each soil layer as a closed polyline (or explode the "
                         "drawing to lines that meet end to end).")
    p = project or new_project()
    p.regions = []
    mats = {}
    if project is None:
        p.materials = []
    for layer, pts in closed:
        if layer not in mats:
            m = next((m for m in p.materials if m.name == layer), None)
            if m is None:
                m = p.add_material(layer or "Soil", color=COLORS[len(mats) % len(COLORS)])
            mats[layer] = m
        area = 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                         for i in range(len(pts)))
        if abs(area) < 1e-12 * size * size:
            continue
        if area < 0:
            pts = list(reversed(pts))
        p.add_region(tr(pts), mats[layer].id)
    if water:
        p.piezometric_line = tr(water)
        for a in p.analyses:
            if a.kind == "slope" and a.pwp == "none":
                a.pwp = "piezometric"
    notes.append(f"{len(p.regions)} regions on {len(mats)} layers"
                 + (", water table" if water else "") + f" from {Path(str(path)).name if isinstance(path, (str, Path)) else 'DXF'}.")
    notes.append("Set the soil properties of each new material (Define > Materials).")
    return p, notes


# --------------------------------------------------------------------------- writing
def _aci(hex_color: str) -> int:
    """Nearest AutoCAD colour index (the 9 basic ones and greys) for a material colour."""
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, TypeError):
        return 7
    basic = {1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255), 5: (0, 0, 255),
             6: (255, 0, 255), 8: (128, 128, 128), 9: (192, 192, 192), 30: (255, 127, 0), 40: (255, 191, 0),
             42: (191, 143, 0), 32: (165, 82, 0), 52: (210, 180, 100)}
    return min(basic, key=lambda k: sum((a - b_) ** 2 for a, b_ in zip(basic[k], (r, g, b))))


def _layer_name(s: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "-_$" else "_" for ch in (s or "0"))
    return out[:60] or "0"


class _W:
    def __init__(self):
        self.out = []

    def g(self, code, val):
        self.out.append(f"{code:>3}\n{val}\n")

    def poly(self, layer, pts, closed=False, color=None):
        self.g(0, "POLYLINE")
        self.g(8, layer)
        if color is not None:
            self.g(62, color)
        self.g(66, 1)
        self.g(10, "0.0")
        self.g(20, "0.0")
        self.g(30, "0.0")
        self.g(70, 1 if closed else 0)
        for x, y in pts:
            self.g(0, "VERTEX")
            self.g(8, layer)
            self.g(10, f"{x:.6f}")
            self.g(20, f"{y:.6f}")
            self.g(30, "0.0")
        self.g(0, "SEQEND")
        self.g(8, layer)

    def text(self, layer, x, y, h, s):
        self.g(0, "TEXT")
        self.g(8, layer)
        self.g(10, f"{x:.6f}")
        self.g(20, f"{y:.6f}")
        self.g(30, "0.0")
        self.g(40, f"{h:.4f}")
        self.g(1, s)


def export_dxf(project, path, analysis=None):
    """Write the model (and the slip surface of a solved slope analysis) as an R12 ASCII DXF."""
    w = _W()
    layers = {}
    for m in project.materials:
        layers[_layer_name(m.name)] = _aci(m.color)
    extra = {"WATER_TABLE": 5, "SLIP_SURFACE": 1, "SLICES": 8, "TEXT": 7, "REINFORCEMENT": 6,
             "STRUCTURES": 30, "LOADS": 6}
    layers.update(extra)
    w.g(0, "SECTION")
    w.g(2, "HEADER")
    w.g(9, "$ACADVER")
    w.g(1, "AC1009")
    w.g(9, "$INSUNITS")
    w.g(70, 6 if project.units == "metric" else 2)
    w.g(0, "ENDSEC")
    w.g(0, "SECTION")
    w.g(2, "TABLES")
    w.g(0, "TABLE")
    w.g(2, "LAYER")
    w.g(70, len(layers))
    for name, col in layers.items():
        w.g(0, "LAYER")
        w.g(2, name)
        w.g(70, 0)
        w.g(62, col)
        w.g(6, "CONTINUOUS")
    w.g(0, "ENDTAB")
    w.g(0, "ENDSEC")
    w.g(0, "SECTION")
    w.g(2, "ENTITIES")
    for r in project.regions:
        m = project.material(r.material_id)
        w.poly(_layer_name(m.name if m else "0"), r.points, closed=True)
    if project.piezometric_line:
        w.poly("WATER_TABLE", project.piezometric_line)
    for r in getattr(project, "reinforcements", []):
        w.poly("REINFORCEMENT", [(r.x1, r.y1), (r.x2, r.y2)])
    for st in getattr(project, "structures", []):
        if len(st.points) >= 2:
            w.poly("STRUCTURES", st.points)
    xs = [x for r in project.regions for x, _ in r.points] or [0, 1]
    ys = [y for r in project.regions for _, y in r.points] or [0, 1]
    h = max(max(xs) - min(xs), max(ys) - min(ys)) / 60.0
    w.text("TEXT", min(xs), max(ys) + 3 * h, 1.4 * h, project.title or "GeoLab model")
    if analysis is not None and analysis.results and analysis.results.get("critical"):
        crit = analysis.results["critical"]
        slip = slip_points(project, analysis)
        if slip:
            w.poly("SLIP_SURFACE", slip)
            mx = sum(x for x, _ in slip) / len(slip)
            my = max(y for _, y in slip)
            w.text("TEXT", mx, my + 1.5 * h, 1.6 * h, f"F = {crit['fos']:.3f}")
    w.g(0, "ENDSEC")
    w.g(0, "EOF")
    Path(path).write_text("".join(w.out), encoding="ascii", errors="replace")
    return path


def slip_points(project, analysis, n: int = 80):
    """Points of the critical slip surface of a solved slope analysis, between where it meets the ground."""
    import numpy as np

    from .geometry import GroundProfile
    from .slope import find_extent
    crit = (analysis.results or {}).get("critical") or {}
    surf = crit.get("surface")
    if not surf:
        return None
    gp = GroundProfile(project.regions, samples=400)
    ext = find_extent(gp, surf, samples=300)
    if surf.get("type") == "circle":
        if not ext:
            return None
        xs = np.linspace(ext[0], ext[1], n)
        ys = surf["yc"] - np.sqrt(np.clip(surf["R"] ** 2 - (xs - surf["xc"]) ** 2, 0, None))
        return [(float(x), float(y)) for x, y in zip(xs, ys)]
    return [(float(x), float(y)) for x, y in surf.get("points", [])]
