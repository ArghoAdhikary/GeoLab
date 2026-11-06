"""Convert a whole project between the metric (m, kN, kPa) and imperial (ft, lbf, psf) unit systems.

Lengths, pressures, unit weights, forces, conductivities and the other mechanical and hydraulic values
are converted. Thermal, contaminant and air-flow values, and time (always seconds), are left as they are;
``convert_project`` returns their names so the user can check them.
"""
from __future__ import annotations

FT = 3.280839895                  # ft per m
PSF = 20.88543423                 # psf per kPa
PCF = 6.365880354                 # pcf per kN/m3
LBF_FT = 68.52176586              # lbf/ft per kN/m (force per unit width)
LBF = 224.8089431                 # lbf per kN
LBF_FT2 = LBF * FT                # lbf.ft per kN.m

# Material fields and their dimension
MATERIAL = {
    "unit_weight": "gamma", "cohesion": "p", "cohesion_sd": "p", "unit_weight_sd": "gamma", "k_sat": "L",
    "unsat_alpha": "1/L", "c_rate": "p/L", "datum": "L", "sigma_break": "p", "sigci": "p", "cohesion_v": "p",
    "vg_alpha": "1/L", "mv": "1/p", "E": "p", "dc_K": "", "hs_E50": "p", "hs_Eur": "p", "hs_pref": "p",
    "cr": "p", "k_air": "L",
}
BC_VALUE = {"head": "L", "pressure_head": "L", "flux": "L", "nodal_flux": "L2", "infiltration": "L",
            "climate": "L", "pressure": "p", "shear": "p", "force_x": "F", "force_y": "F", "displacement_y": "L"}
ANALYSIS = ["mesh_size", "drawdown_level"]
SEARCH_L = ["entry_x1", "entry_x2", "exit_x1", "exit_x2", "grid_x1", "grid_y1", "grid_x2", "grid_y2",
            "radius_min", "radius_max", "min_depth", "tangent_y1", "tangent_y2"]
NOT_CONVERTED = ["thermal properties and boundaries", "contaminant transport properties and boundaries",
                 "air-flow properties", "time (always seconds)"]


def _factor(dim, f_len, f_p, f_gamma, f_force):
    return {"L": f_len, "1/L": 1 / f_len, "L2": f_len ** 2, "p": f_p, "1/p": 1 / f_p, "p/L": f_p / f_len,
            "gamma": f_gamma, "F": f_force, "": 1.0}[dim]


def convert_project(p, to: str) -> list[str]:
    """Convert every value of project p to the unit system 'to' (in place). Returns what was not converted."""
    if to == p.units:
        return []
    if to not in ("metric", "imperial"):
        raise ValueError(f"Unknown unit system: {to}")
    k = 1.0 if to == "imperial" else -1.0
    fl, fp, fg, ff, fF, fM = (v ** k for v in (FT, PSF, PCF, LBF_FT, LBF_FT, LBF_FT2))
    fac = lambda dim: _factor(dim, fl, fp, fg, ff)

    def pts(seq):
        return [[x * fl, y * fl] for x, y in seq]

    for m in p.materials:
        for name, dim in MATERIAL.items():
            setattr(m, name, getattr(m, name) * fac(dim))
        m.sn_table = [[a * fp, b * fp] for a, b in m.sn_table]
    for r in p.regions:
        r.points = pts(r.points)
    p.piezometric_line = pts(p.piezometric_line)
    p.mesh_lines = [pts(line) for line in p.mesh_lines]
    for pl in p.point_loads:
        pl.x *= fl
        pl.fx *= fF
        pl.fy *= fF
    for s in p.surcharges:
        s.x1, s.x2, s.q = s.x1 * fl, s.x2 * fl, s.q * fp
    for bc in p.boundary_conditions:
        bc.points = pts(bc.points)
        f = fac(BC_VALUE.get(bc.type, ""))
        bc.value *= f
        bc.fn = [[t, v * f] for t, v in bc.fn]
        if bc.type == "climate":
            bc.value2 *= fl
            bc.fn2 = [[t, v * fl] for t, v in bc.fn2]
            bc.value3 *= fl
            bc.fn3 = [[t, v * fl] for t, v in bc.fn3]
            bc.root_depth *= fl
    for r in p.reinforcements:
        r.x1, r.y1, r.x2, r.y2 = r.x1 * fl, r.y1 * fl, r.x2 * fl, r.y2 * fl
        r.capacity *= fF
        r.bond *= fp
        r.bond_length *= fl
        r.spacing *= fl
    for st in getattr(p, "structures", []):
        st.points = pts(st.points)
        st.EA *= fF
        st.EI *= fM
        st.spacing *= fl
        st.prestress *= fF
    for f in p.flux_sections:
        f.points = pts(f.points)
    for t in p.sketch_texts:
        t.x, t.y = t.x * fl, t.y * fl
    for a in p.analyses:
        for name in ANALYSIS:
            setattr(a, name, getattr(a, name) * fl)
        for name in SEARCH_L:
            setattr(a.search, name, getattr(a.search, name) * fl)
        a.search.circles = [[c[0] * fl, c[1] * fl, c[2] * fl] + list(c[3:]) for c in a.search.circles]
        a.search.polylines = [pts(pl) for pl in a.search.polylines]
        a.search.block_left = [v * fl for v in a.search.block_left]
        a.search.block_right = [v * fl for v in a.search.block_right]
        a.particles = pts(a.particles)
        a.results = None
    p.grid_spacing *= fl
    p.units = to
    return list(NOT_CONVERTED)
