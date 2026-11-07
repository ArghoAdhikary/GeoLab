"""Quantities and cost of a design, and a side-by-side comparison of design options.

Quantities per metre run of the section (and for a length you enter):

* the area and volume of each material
* cut and fill between the existing ground and the design ground
* the length of reinforcement (nails, anchors, geogrids) and of structures (walls, piles)

Cost = quantity x unit rate. The rates are yours (BDT, AUD or any currency); the defaults are
placeholders only.

Compare: several projects (or analyses) in one table, with F, the code minimum and whether it
passes, the probability of failure if it was run, the quantities and the cost.
"""
from __future__ import annotations

import math

import numpy as np

DEFAULT_RATES = {"currency": "BDT", "cut": 450.0, "fill": 650.0, "reinforcement": 2500.0, "structure": 18000.0,
                 "material": {}}


def polygon_area(pts) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def ground_line(project, samples: int = 400):
    from .geometry import GroundProfile
    gp = GroundProfile(project.regions, samples=samples)
    return np.asarray(gp.xs), np.asarray(gp.top)


def cut_fill(existing, design, samples: int = 600) -> dict:
    """Areas of cut (design below existing) and fill (design above existing) per metre run.

    ``existing`` and ``design`` are projects or lists of (x, y) ground points."""
    def line(obj):
        if hasattr(obj, "regions"):
            return ground_line(obj)
        pts = sorted(obj)
        return np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    xe, ye = line(existing)
    xd, yd = line(design)
    lo, hi = max(xe.min(), xd.min()), min(xe.max(), xd.max())
    if hi <= lo:
        raise ValueError("The two ground lines do not overlap.")
    x = np.linspace(lo, hi, samples)
    d = np.interp(x, xd, yd) - np.interp(x, xe, ye)
    dx = (hi - lo) / (samples - 1)
    fill = float(np.trapezoid(np.clip(d, 0, None), dx=dx)) if hasattr(np, "trapezoid") else float(np.trapz(np.clip(d, 0, None), dx=dx))
    cut = float(np.trapezoid(np.clip(-d, 0, None), dx=dx)) if hasattr(np, "trapezoid") else float(np.trapz(np.clip(-d, 0, None), dx=dx))
    return {"cut": cut, "fill": fill, "net": fill - cut, "x": [lo, hi]}


def quantities(project, length: float = 1.0, existing=None) -> dict:
    """Areas per material, reinforcement and structure lengths; cut and fill if ``existing`` is given."""
    mats = {}
    for r in project.regions:
        m = project.material(r.material_id)
        name = m.name if m else f"Material {r.material_id}"
        mats[name] = mats.get(name, 0.0) + polygon_area(r.points)
    reinf = 0.0
    for r in getattr(project, "reinforcements", []):
        reinf += math.hypot(r.x2 - r.x1, r.y2 - r.y1)
    struct = 0.0
    for s in getattr(project, "structures", []):
        struct += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(s.points, s.points[1:]))
    out = {"length": length, "materials": {k: {"area": v, "volume": v * length} for k, v in mats.items()},
           "reinforcement_m": reinf, "structure_m": struct, "units": project.units}
    if existing is not None:
        cf = cut_fill(existing, project)
        out["cut"] = cf["cut"] * length
        out["fill"] = cf["fill"] * length
    return out


def cost(q: dict, rates: dict | None = None) -> dict:
    r = {**DEFAULT_RATES, **(rates or {})}
    items = []
    if "cut" in q:
        items.append(("Excavation (cut)", q["cut"], "m3", r["cut"]))
        items.append(("Fill", q["fill"], "m3", r["fill"]))
    if q["reinforcement_m"]:
        items.append(("Reinforcement (nails, anchors, geogrids)", q["reinforcement_m"] * q["length"], "m",
                      r["reinforcement"]))
    if q["structure_m"]:
        items.append(("Walls and piles (length in section)", q["structure_m"] * q["length"], "m",
                      r["structure"]))
    for name, rate in (r.get("material") or {}).items():
        if name in q["materials"] and rate:
            items.append((f"{name} (placed)", q["materials"][name]["volume"], "m3", float(rate)))
    rows = [{"item": n, "quantity": qty, "unit": u, "rate": rt, "amount": qty * rt} for n, qty, u, rt in items]
    return {"rows": rows, "total": sum(x["amount"] for x in rows), "currency": r["currency"]}


def compare(options: list[tuple[str, object]], rates=None, existing=None, length: float = 1.0) -> list[dict]:
    """options: [(name, project)]. One row per option and slope analysis: F, required F, pass, Pf, cost."""
    from .codes import check_slope
    rows = []
    for name, p in options:
        q = quantities(p, length, existing)
        c = cost(q, rates)
        for a in p.analyses:
            if a.kind != "slope":
                continue
            res = a.results or {}
            crit = res.get("critical") or {}
            row = {"option": name, "analysis": a.name, "fos": crit.get("fos"), "required": None, "pass": None,
                   "pf": (res.get("probability") or {}).get("pf"), "cost": c["total"], "currency": c["currency"],
                   "cut": q.get("cut"), "fill": q.get("fill"), "reinforcement": q["reinforcement_m"]}
            if crit:
                try:
                    chk = check_slope(p, a)
                    row["required"] = chk.get("required")
                    row["pass"] = chk.get("pass")
                except Exception:                    # noqa: BLE001
                    pass
            rows.append(row)
        if not any(a.kind == "slope" for a in p.analyses):
            rows.append({"option": name, "analysis": "-", "fos": None, "required": None, "pass": None, "pf": None,
                         "cost": c["total"], "currency": c["currency"], "cut": q.get("cut"), "fill": q.get("fill"),
                         "reinforcement": q["reinforcement_m"]})
    return rows


def text_compare(rows) -> str:
    head = f"{'Option':<26}{'Analysis':<30}{'F':>7}{'Need':>7}  {'Result':<8}{'Pf %':>7}{'Cost':>14}"
    out = [head, "-" * len(head)]
    for r in rows:
        f = f"{r['fos']:.3f}" if r["fos"] else "-"
        need = f"{r['required']:.2f}" if r["required"] else "-"
        res = "-" if r["pass"] is None else ("pass" if r["pass"] else "FAIL")
        pf = f"{100 * r['pf']:.2f}" if r["pf"] is not None else "-"
        out.append(f"{r['option'][:25]:<26}{r['analysis'][:29]:<30}{f:>7}{need:>7}  {res:<8}{pf:>7}"
                   f"{r['cost']:>12,.0f} {r['currency']}")
    return "\n".join(out)


def text_quantities(q: dict, c: dict) -> str:
    L = q["length"]
    out = [f"Quantities for {L:g} m of the section", "", f"{'Material':<34}{'Area m2/m':>12}{'Volume m3':>14}"]
    for k, v in q["materials"].items():
        out.append(f"{k[:33]:<34}{v['area']:12.2f}{v['volume']:14.1f}")
    if "cut" in q:
        out += ["", f"Cut {q['cut']:.1f} m3    fill {q['fill']:.1f} m3"]
    out += [f"Reinforcement {q['reinforcement_m']:.1f} m per m run    walls / piles {q['structure_m']:.1f} m in section",
            "", f"{'Cost item':<44}{'Quantity':>12}{'Rate':>12}{'Amount':>16}"]
    for r in c["rows"]:
        out.append(f"{r['item'][:43]:<44}{r['quantity']:10.1f} {r['unit']:<2}{r['rate']:12,.0f}{r['amount']:16,.0f}")
    out.append(f"{'Total':<44}{'':>24}{c['total']:16,.0f} {c['currency']}")
    return "\n".join(out)
