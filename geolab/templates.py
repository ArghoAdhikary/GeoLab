"""Ready-made models for river banks and flood embankments (the usual problems of deltaic rivers such as
the Padma, Jamuna and Meghna, and of Australian levees).

riverbank(q): a bank with a clay top over fine sand, a scour hole at the toe and three analyses:
  1. high flood (bank saturated to the flood level),
  2. rapid drawdown after the flood (Duncan-Wright-Wong, clay undrained, sand free draining),
  3. high flood with the earthquake coefficient of the selected design code.
flood_embankment(q): a levee on soft clay: steady seepage at flood level, land-side and river-side
  stability, and the land side in an earthquake (kh from the selected design code).
"""
from __future__ import annotations

from .model import new_project
from .quick import quick_slope

RIVERBANK_DEFAULTS = {"height": 8.0, "ratio": 2.5, "scour": 2.0, "flood": 7.0, "low": 1.0, "clay_thickness": 3.0,
                      "toe": 25.0, "crest": 25.0, "base": 8.0}


def riverbank(q: dict | None = None):
    q = dict(RIVERBANK_DEFAULTS, **(q or {}))
    H = float(q["height"])
    clay_t = min(float(q["clay_thickness"]), 0.9 * H)
    flood, low = float(q["flood"]), float(q["low"])
    if not 0 <= low < flood <= H + 1e-9:
        raise ValueError("Use 0 <= low water < flood level <= bank height (levels above the river bed at the toe).")
    p = quick_slope({"height": H, "ratio": q["ratio"], "toe": q["toe"], "crest": q["crest"], "base": q["base"],
                     "scour": q["scour"],
                     "layers": [{"name": "Silty clay (bank)", "c": 6, "phi": 26, "gamma": 18.5, "thickness": clay_t},
                                {"name": "Fine sand (micaceous)", "c": 0, "phi": 31, "gamma": 19.0}],
                     "title": f"River bank {H:g} m, toe scour {float(q['scour']):g} m"})
    clay, sand = p.materials
    clay.cr, clay.phi_r = 8.0, 14.0           # consolidated-undrained (R) envelope for the drawdown
    clay.k_sat, sand.k_sat = 1e-8, 5e-5
    base = float(q["base"])
    yf, yl = base + flood, base + low
    xs = [pt[0] for r in p.regions for pt in r.points]
    x_end = max(xs)
    p.description = ("River bank with a clay top over fine sand and a scour hole at the toe. Levels are above the "
                     f"river bed at the toe: flood {flood:g} m, low water {low:g} m. Analysis 2 is the rapid "
                     "drawdown after the flood, usually the critical case for bank failures in the monsoon recession.")
    a1 = p.analyses[0]
    a1.name, a1.pwp = "1. High flood", "piezometric"
    p.piezometric_line = [[0.0, yf], [x_end, yf]]
    a2 = p.add_analysis("2. Rapid drawdown after the flood", kind="slope", pwp="piezometric", rapid_drawdown=True,
                        drawdown_level=yl, method="spencer")
    a3 = p.add_analysis("3. High flood + earthquake", kind="slope", pwp="piezometric", method=a1.method)
    from . import codes
    a3.kh = round(codes.seismic(codes.code_of(p), codes.settings_of(p))["kh"], 3)
    a1.search.n_entry = a1.search.n_exit = 8
    for a in (a2, a3):
        a.search = type(a1.search)(**vars(a1.search))
    p.quick = dict(p.quick, scour=q["scour"])
    return p


FLOOD_DEFAULTS = {"height": 5.0, "crest_width": 4.0, "river_slope": 3.0, "land_slope": 3.0, "clay": 6.0,
                  "flood": 4.2, "kh": None}


def flood_embankment(q: dict | None = None):
    q = dict(FLOOD_DEFAULTS, **(q or {}))
    H, W = float(q["height"]), float(q["crest_width"])
    rs, ls, D = float(q["river_slope"]), float(q["land_slope"]), float(q["clay"])
    hf = float(q["flood"])
    if not 0 < hf < H:
        raise ValueError("The flood level must be between the ground and the crest.")
    p = new_project(kind="seepage")
    p.title = f"Flood embankment {H:g} m on {D:g} m of soft clay"
    p.description = ("Levee on soft clay over sand. River on the left. Steady seepage at the flood level gives the "
                     "pore pressures for the land-side and river-side stability; the last analysis adds the "
                     "earthquake coefficient of the selected design code.")
    fill = p.materials[0]
    fill.name, fill.cohesion, fill.phi, fill.unit_weight, fill.k_sat = "Compacted fill", 8.0, 28.0, 19.0, 1e-7
    clay = p.add_material("Soft clay", cohesion=25.0, phi=0.0, model="undrained", unit_weight=16.5, k_sat=5e-9)
    sand = p.add_material("Sand", cohesion=0.0, phi=32.0, unit_weight=19.5, k_sat=1e-4)
    for m in (fill, clay, sand):
        m.hyd_model = "saturated"
    g = D + 6.0                                 # ground level (sand 6 m thick)
    x0 = 30.0                                   # river-side toe
    x1, x2 = x0 + rs * H, x0 + rs * H + W
    x3 = x2 + ls * H
    L = x3 + 30.0
    p.add_region([(0, 0), (L, 0), (L, 6), (0, 6)], sand.id)
    p.add_region([(0, 6), (L, 6), (L, g), (x3, g), (x0, g), (0, g)], clay.id)
    p.add_region([(x0, g), (x3, g), (x2, g + H), (x1, g + H)], fill.id)
    seep = p.analyses[0]
    seep.name, seep.mesh_size = "Seepage at flood level", 1.0
    p.add_bc("River at flood", "head", g + hf, [(0, g), (x0, g), (x0 + rs * hf, g + hf)])
    p.add_bc("River (sand)", "head", g + hf, [(0, 0), (0, g)])
    p.add_bc("Land side exit", "seepage_face", 0.0, [(x3, g), (L, g)])
    p.add_bc("Land side far", "head", g - 0.5, [(L, 0), (L, g - 0.5)])
    land = p.add_analysis("Land side at flood", kind="slope", parent_id=seep.id, pwp="seepage")
    s = land.search
    s.mode, s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2 = "entry_exit", x1, x2, x3 + 0.5, x3 + 2.5 * H
    s.n_entry = s.n_exit = 8
    s.n_radius = 4
    river = p.add_analysis("River side at flood", kind="slope", parent_id=seep.id, pwp="seepage")
    s = river.search
    s.mode, s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2 = "entry_exit", x1, x2, x0 - 2.5 * H, x0 - 0.5
    s.n_entry = s.n_exit = 8
    s.n_radius = 4
    eq = p.add_analysis("Land side, earthquake", kind="slope", parent_id=seep.id, pwp="seepage")
    eq.search = type(land.search)(**vars(land.search))
    if q.get("kh") is None:
        from . import codes
        eq.kh = round(codes.seismic(codes.code_of(p), codes.settings_of(p))["kh"], 3)
    else:
        eq.kh = float(q["kh"])
    return p
