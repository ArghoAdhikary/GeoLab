"""Quick slope: a complete slope stability model from a few numbers (used by the Quick Slope dialog and
GeoLab Mobile)."""
from __future__ import annotations

import math


from .examples import _auto_search
from .model import MATERIAL_COLORS, Project, Surcharge, new_project


def _num(v):
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("Enter a number.")
    return v


def quick_slope(q: dict) -> Project:
    """A slope from a few numbers: height, slope ratio (H:1V), crest/toe widths, layers (top to bottom with
    thickness), depth of the water table below the crest, crest load. Returns a new project."""
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
    return p
