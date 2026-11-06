"""Bridge between the GeoLab Mobile web UI and the GeoLab analysis engine (runs inside Pyodide).

Every function takes and returns plain JSON strings so the web worker can pass them on unchanged.
"""
from __future__ import annotations

import base64
import json
import math
import os
import tempfile

import numpy as np

from geolab import __version__
from geolab.examples import EXAMPLES, _auto_search
from geolab.fileio import load_project, save_project
from geolab.geometry import GroundProfile, bounds, validate_geometry
from geolab.model import (ANALYSIS_KINDS, MATERIAL_COLORS, PWP_MODES, SLOPE_METHODS, STRENGTH_MODELS,
                          Project, Surcharge, new_project)
from geolab.report import build_report
from geolab.slope import find_extent
from geolab.solver import solve, solve_all

P: Project = new_project()


def _ok(**kw):
    return json.dumps({"ok": True, **kw})


def _num(v):
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("Enter a number.")
    return v


# -- projects ------------------------------------------------------------------
def info():
    return _ok(version=__version__, examples=list(EXAMPLES), methods=SLOPE_METHODS, pwp=PWP_MODES,
               kinds=ANALYSIS_KINDS, strength=STRENGTH_MODELS)


def open_example(name):
    global P
    P = EXAMPLES[name]()
    return state()


def quick_slope(params_json):
    """A slope from a few numbers: height, slope ratio (H:1V), crest/toe widths, layers, water."""
    global P
    q = json.loads(params_json)
    H = _num(q.get("height", 10))
    ratio = _num(q.get("ratio", 2))
    crest = _num(q.get("crest", 20))
    toe = _num(q.get("toe", 20))
    base = _num(q.get("base", 5))
    if H <= 0 or ratio < 0 or crest <= 0 or toe <= 0 or base <= 0:
        raise ValueError("Height, widths and depth below the toe must be positive.")
    layers = q.get("layers") or [{"name": "Soil", "c": 10, "phi": 30, "gamma": 19}]
    p = new_project()
    p.materials.clear()
    p.title = q.get("title") or f"{H:g} m slope at {ratio:g}H:1V"
    x_toe, x_crest = toe, toe + ratio * H
    x_end = x_crest + crest
    y_toe, y_top = base, base + H
    ground = [(0.0, y_toe), (x_toe, y_toe), (x_crest, y_top), (x_end, y_top)]

    def clipped_top(hi, lo):
        """Ground line clipped to lo <= y <= hi, with the exact crossing points."""
        pts = []
        for (xa, ya), (xb, yb) in zip(ground, ground[1:]):
            pts.append((xa, ya))
            for lvl in (hi, lo):
                if (ya - lvl) * (yb - lvl) < 0:
                    pts.append((xa + (lvl - ya) / (yb - ya) * (xb - xa), lvl))
        pts.append(ground[-1])
        pts.sort(key=lambda t: t[0])
        return [(x, min(max(y, lo), hi)) for x, y in pts]

    n = len(layers)
    tops = [y_top]
    for lay in layers[:-1]:
        t = _num(lay.get("thickness", H / n))
        tops.append(tops[-1] - max(t, 0.1))
    tops.append(0.0)
    for i, lay in enumerate(layers):
        m = p.add_material(lay.get("name") or f"Soil {i + 1}", cohesion=_num(lay.get("c", 5)),
                           phi=_num(lay.get("phi", 30)), unit_weight=_num(lay.get("gamma", 19)),
                           color=MATERIAL_COLORS[i % len(MATERIAL_COLORS)])
        hi, lo = tops[i], max(tops[i + 1], 0.0)
        if hi <= lo + 1e-9:
            continue
        T = clipped_top(hi, lo)
        k = next(j for j, (_, y) in enumerate(T) if y > lo + 1e-9)
        start = max(k - 1, 0)
        top = T[start:]
        poly = [(top[0][0], lo), (x_end, lo)] + list(reversed(top))
        clean = []
        for pt in poly:
            if not clean or abs(pt[0] - clean[-1][0]) > 1e-9 or abs(pt[1] - clean[-1][1]) > 1e-9:
                clean.append(pt)
        if abs(clean[-1][0] - clean[0][0]) < 1e-9 and abs(clean[-1][1] - clean[0][1]) < 1e-9:
            clean.pop()
        out = []
        for j, pt in enumerate(clean):   # drop collinear points
            a0, c0 = clean[j - 1], clean[(j + 1) % len(clean)]
            if abs((pt[0] - a0[0]) * (c0[1] - a0[1]) - (pt[1] - a0[1]) * (c0[0] - a0[0])) > 1e-9:
                out.append(pt)
        if len(out) >= 3:
            p.add_region(out, m.id)
    a = p.analyses[0]
    a.method = q.get("method", "morgenstern_price")
    wt = q.get("water")
    if wt is not None and wt != "":
        d = _num(wt)  # depth of the water table below the crest
        yw = y_top - d
        p.piezometric_line = [[0.0, min(yw, y_toe)], [x_toe, min(yw, y_toe)], [x_end, yw]]
        a.pwp = "piezometric"
    sq = _num(q.get("surcharge", 0) or 0)
    if sq > 0:
        p.surcharges.append(Surcharge(x_crest + 0.1 * crest, x_crest + 0.6 * crest, sq))
    _auto_search(p, a)
    P = p
    return state()


def open_file(name, b64):
    global P
    suffix = os.path.splitext(name)[1].lower() or ".slab"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(base64.b64decode(b64))
        path = f.name
    try:
        P = load_project(path)
    finally:
        os.unlink(path)
    return state()


def save_file():
    with tempfile.NamedTemporaryFile(suffix=".slab", delete=False) as f:
        path = f.name
    save_project(P, path)
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    name = "".join(c if c.isalnum() or c in " -_" else "_" for c in P.title).strip() or "project"
    return _ok(name=name + ".slab", b64=base64.b64encode(data).decode())


def to_json():
    return json.dumps(P.to_dict(include_results=False))


def from_json(text):
    global P
    P = Project.from_dict(json.loads(text))
    return state()


# -- editing -------------------------------------------------------------------
MATERIAL_FIELDS = {"name": str, "model": str, "unit_weight": float, "cohesion": float, "phi": float,
                   "k_sat": float, "color": str}
ANALYSIS_FIELDS = {"method": str, "pwp": str, "ru": float, "kh": float, "kv": float, "n_slices": int,
                   "name": str}


def set_material(mid, field, value):
    m = P.material(int(mid))
    if m is None or field not in MATERIAL_FIELDS:
        raise ValueError("Unknown material or field.")
    t = MATERIAL_FIELDS[field]
    v = t(value) if t is str else t(_num(value))
    if field in ("unit_weight",) and v <= 0:
        raise ValueError("Unit weight must be positive.")
    if field == "phi" and not 0 <= v < 90:
        raise ValueError("Friction angle must be between 0 and 90 degrees.")
    if field == "cohesion" and v < 0:
        raise ValueError("Cohesion cannot be negative.")
    setattr(m, field, v)
    P.clear_results()
    return state()


def set_analysis(aid, field, value):
    a = P.analysis(int(aid))
    if a is None or field not in ANALYSIS_FIELDS:
        raise ValueError("Unknown analysis or field.")
    t = ANALYSIS_FIELDS[field]
    v = t(value) if t is str else t(_num(value))
    if field == "method" and v not in SLOPE_METHODS:
        raise ValueError("Unknown method.")
    if field == "pwp" and v not in PWP_MODES:
        raise ValueError("Unknown pore-pressure option.")
    setattr(a, field, v)
    P.clear_results()
    return state()


def set_title(text):
    P.title = str(text)[:120] or "Untitled"
    return state()


def move_water(dy):
    if not P.piezometric_line:
        raise ValueError("This model has no water table.")
    dy = _num(dy)
    P.piezometric_line = [[x, y + dy] for x, y in P.piezometric_line]
    P.clear_results()
    return state()


def set_surcharge(q):
    q = _num(q)
    P.surcharges.clear()
    if q > 0:
        gp = GroundProfile(P.regions, samples=400)
        xs = np.linspace(gp.x0, gp.x1, 400)
        ys = np.array([gp.ground(x) for x in xs])
        top = ys.max()
        flat = xs[ys > top - 1e-6]
        x1, x2 = float(flat.min()), float(flat.max())
        w = x2 - x1
        P.surcharges.append(Surcharge(x1 + 0.1 * w, x1 + 0.6 * w, q))
    P.clear_results()
    return state()


# -- solving -------------------------------------------------------------------
def solve_one(aid):
    a = P.analysis(int(aid))
    if a is None:
        raise ValueError("Unknown analysis.")
    problems = validate_geometry(P)
    if problems:
        raise ValueError("; ".join(problems))
    solve(P, a)
    return state()


def solve_everything():
    errs = [f"{n}: {e}" for n, e in solve_all(P) if e]
    s = json.loads(state())
    s["errors"] = errs
    return json.dumps(s)


def report(aid):
    a = P.analysis(int(aid))
    if a is None or not a.results:
        raise ValueError("Solve the analysis first.")
    return _ok(text=build_report(P, a))


# -- drawing data --------------------------------------------------------------
def _f(v):
    return None if v is None or not math.isfinite(v) else round(float(v), 4)


def _slope_draw(res):
    crit = res.get("critical")
    if not crit:
        return {"message": res.get("message", "No valid slip surface.")}
    gp = GroundProfile(P.regions, samples=600)
    sx = crit["slice_x"]
    surf = crit["surface"]

    def base_y(x):
        if surf["type"] == "circle":
            return surf["yc"] - math.sqrt(max(surf["R"] ** 2 - (x - surf["xc"]) ** 2, 0))
        pl = sorted(surf["points"])
        return float(np.interp(x, [p[0] for p in pl], [p[1] for p in pl]))

    xs = np.linspace(sx[0], sx[-1], 80)
    slip = [[round(float(x), 4), round(base_y(x), 4)] for x in xs]
    top = [[round(float(x), 4), round(float(gp.ground(x)), 4)] for x in np.linspace(sx[-1], sx[0], 80)]
    slices = [[round(x, 4), round(base_y(x), 4), round(float(gp.ground(x)), 4)] for x in sx[1:-1]]
    trials = []
    for t in res.get("trials", [])[1:60]:
        ext = find_extent(gp, t["surface"], samples=150)
        if not ext:
            continue
        s2 = t["surface"]
        x1, x2 = ext[0], ext[1]
        pts = []
        for x in np.linspace(x1, x2, 30):
            if s2["type"] == "circle":
                y = s2["yc"] - math.sqrt(max(s2["R"] ** 2 - (x - s2["xc"]) ** 2, 0))
            else:
                pl = sorted(s2["points"])
                y = float(np.interp(x, [p[0] for p in pl], [p[1] for p in pl]))
            pts.append([round(float(x), 3), round(y, 3)])
        trials.append({"fos": _f(t["fos"]), "pts": pts})
    methods = {SLOPE_METHODS.get(k, k): _f(v["fos"]) for k, v in crit["all_methods"].items()}
    out = {"fos": _f(crit["fos"]), "slip": slip, "mass": slip + top, "slices": slices, "trials": trials,
           "methods": methods, "n_valid": res.get("n_valid"), "n_total": res.get("n_total")}
    if surf["type"] == "circle":
        out["centre"] = [_f(surf["xc"]), _f(surf["yc"]), _f(surf["R"])]
    prob = res.get("probability")
    if prob and prob.get("n"):
        out["probability"] = {k: _f(v) if isinstance(v, (int, float)) else v for k, v in prob.items()
                              if not isinstance(v, list)}
    return out


FIELD_LABELS = {"head": "Total head", "pressure_head": "Pressure head", "pore_pressure": "Pore pressure",
                "water_content": "Water content", "temperature": "Temperature", "concentration": "Concentration",
                "disp_mag": "Displacement", "dx": "x displacement", "dy": "y displacement",
                "sy": "Vertical stress", "sx": "Horizontal stress", "air_pressure": "Air pressure",
                "pwp": "Pore pressure", "excess_pwp": "Excess pore pressure"}


def _fe_draw(res):
    nodes = res.get("nodes")
    tris = res.get("tris")
    if not nodes or not tris:
        return {"message": "Solved. See the report for the results."}
    n = len(nodes)
    fields = {}
    for k, v in res.items():
        if k in ("nodes", "tris") or not isinstance(v, list) or len(v) != n or not v:
            continue
        if isinstance(v[0], (int, float)):
            fields[k] = v
        elif isinstance(v[0], list) and k in ("disp", "displacement") and len(v[0]) == 2:
            fields["disp_mag"] = [math.hypot(a, b) for a, b in v]
    if not fields and "steps" in res and res["steps"]:
        last = res["steps"][-1]
        for k, v in last.items():
            if isinstance(v, list) and len(v) == n and v and isinstance(v[0], (int, float)):
                fields[k] = v
    out_fields = {}
    for k, v in fields.items():
        arr = np.asarray(v, dtype=float)
        if not np.isfinite(arr).any() or np.nanmax(arr) == np.nanmin(arr):
            continue
        out_fields[k] = {"label": FIELD_LABELS.get(k, k.replace("_", " ")),
                         "v": [round(float(x), 5) for x in arr]}
    return {"nodes": [[round(x, 4), round(y, 4)] for x, y in nodes], "tris": tris, "fields": out_fields,
            "phreatic": res.get("phreatic") or []}


def state():
    try:
        x0, y0, x1, y1 = bounds(P.regions)
    except Exception:
        x0, y0, x1, y1 = 0, 0, 10, 10
    mats = {m.id: m for m in P.materials}
    regions = [{"pts": r.points, "color": mats[r.material_id].color if r.material_id in mats else "#cccccc",
                "mid": r.material_id} for r in P.regions]
    analyses = []
    for a in P.analyses:
        item = {"id": a.id, "name": a.name, "kind": a.kind, "kind_label": ANALYSIS_KINDS.get(a.kind, a.kind),
                "method": a.method, "pwp": a.pwp, "kh": a.kh, "ru": a.ru, "solved": bool(a.results)}
        if a.results:
            if a.kind == "slope":
                item["draw"] = _slope_draw(a.results)
            else:
                item["draw"] = _fe_draw(a.results)
        analyses.append(item)
    used = {r.material_id for r in P.regions}
    materials = [{"id": m.id, "name": m.name, "color": m.color, "model": m.model,
                  "model_label": STRENGTH_MODELS.get(m.model, m.model), "unit_weight": m.unit_weight,
                  "cohesion": m.cohesion, "phi": m.phi, "k_sat": m.k_sat, "used": m.id in used}
                 for m in P.materials]
    return _ok(title=P.title, description=P.description, units=P.units,
               u={k: P.unit(k) for k in ("length", "pressure", "unit_weight", "k")},
               bounds=[x0, y0, x1, y1], regions=regions, materials=materials,
               piezo=P.piezometric_line, surcharges=[[s.x1, s.x2, s.q] for s in P.surcharges],
               loads=[[pl.x, pl.fy] for pl in P.point_loads],
               reinforcements=[[r.x1, r.y1, r.x2, r.y2] for r in P.reinforcements],
               analyses=analyses)
