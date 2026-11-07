"""Soil nail walls, ground anchors and a library of generic geosynthetics.

Soil nail wall (simplified, after FHWA-NHI-14-007 working practice):
* Nail force from a uniform apparent earth pressure  sigma = 0.65 Ka (gamma H + q), T = sigma Sh Sv / cos(i).
  This envelope is close to the T_max = 0.6 - 0.75 Ka gamma H measured on instrumented walls.
* Tensile capacity  T_t = As fy / FS_T (FS_T = 1.8);  pullout per metre  Q = pi D_DH q_s, allowable Q / FS_P
  (FS_P = 2.0).
* The active zone is bounded by the Rankine plane from the toe at 45 + phi/2 to the horizontal. Behind it
  the nail needs the pullout length  Lp = T FS_P / Q.  Total length = active length + Lp.
Overall and compound stability are then checked with the slope analysis (nails in Define > Reinforcement):
`apply_to_project` sets the capacity and bond of the model's nails from the design.

Ground anchor:  bond length Lb = T FS / (pi D q_s), at least 4.5 m; tendon check against 0.6 fpu.

Geosynthetics: long-term design strength  T_al = T_ult / (RF_ID RF_CR RF_D)  (FHWA-NHI-10-024 / ISO TR 20432).
The library holds typical generic products; use the manufacturer's certified values for design.
"""
from __future__ import annotations

import math

# name -> (kind, T_ult kN/m, RF_ID installation damage, RF_CR creep, RF_D durability)
GEOSYNTHETICS = {
    "HDPE uniaxial geogrid, 60 kN/m": ("geogrid", 60, 1.10, 2.60, 1.10),
    "HDPE uniaxial geogrid, 90 kN/m": ("geogrid", 90, 1.10, 2.60, 1.10),
    "HDPE uniaxial geogrid, 120 kN/m": ("geogrid", 120, 1.10, 2.60, 1.10),
    "HDPE uniaxial geogrid, 170 kN/m": ("geogrid", 170, 1.10, 2.60, 1.10),
    "PET coated geogrid, 40 kN/m": ("geogrid", 40, 1.15, 1.60, 1.15),
    "PET coated geogrid, 80 kN/m": ("geogrid", 80, 1.15, 1.60, 1.15),
    "PET coated geogrid, 200 kN/m": ("geogrid", 200, 1.15, 1.60, 1.15),
    "PET coated geogrid, 400 kN/m": ("geogrid", 400, 1.15, 1.60, 1.15),
    "PP biaxial geogrid, 30 kN/m": ("geogrid", 30, 1.20, 4.00, 1.10),
    "PP woven geotextile, 50 kN/m": ("geotextile", 50, 1.25, 4.00, 1.10),
    "PET woven geotextile, 100 kN/m": ("geotextile", 100, 1.25, 1.60, 1.15),
    "PET woven geotextile, 400 kN/m": ("geotextile", 400, 1.20, 1.60, 1.15),
    "Steel welded wire mesh, 75 kN/m": ("steel", 75, 1.00, 1.00, 1.10),
}
# bar diameter (mm) -> area (mm2); yield strength of usual nail bars 500 MPa
BARS = {20: 314, 25: 491, 28: 616, 32: 804, 36: 1018, 40: 1257}
# typical ultimate bond stress q_s (kPa), FHWA ranges (middle values) for grouted nails / anchors
BOND = {"Soft clay": 30, "Stiff clay": 70, "Silt": 50, "Loose sand": 70, "Dense sand": 140, "Gravel": 200,
        "Weathered rock": 250, "Residual soil": 90}


def geosynthetic(name: str, rf_id=None, rf_cr=None, rf_d=None) -> dict:
    kind, tult, a, b, c = GEOSYNTHETICS[name]
    a, b, c = rf_id or a, rf_cr or b, rf_d or c
    return {"name": name, "kind": kind, "T_ult": tult, "RF_ID": a, "RF_CR": b, "RF_D": c,
            "T_al": tult / (a * b * c)}


def ka(phi: float) -> float:
    return math.tan(math.radians(45 - phi / 2)) ** 2


def nail_wall(H: float, sh: float = 1.5, sv: float = 1.5, phi: float = 30.0, gamma: float = 18.0,
              q: float = 10.0, inclination: float = 15.0, drill: float = 0.1, bar: int = 25, fy: float = 500.0,
              qs: float = 100.0, first: float | None = None, FS_T: float = 1.8, FS_P: float = 2.0,
              round_to: float = 0.5) -> dict:
    if H <= 0 or sh <= 0 or sv <= 0:
        raise ValueError("Give the wall height and the nail spacing.")
    K = ka(phi)
    sigma = 0.65 * K * (gamma * H + q)
    ci = math.cos(math.radians(inclination))
    T = sigma * sh * sv / ci
    As = BARS.get(int(bar), math.pi * bar ** 2 / 4)
    Tt = As * fy / 1000 / FS_T                      # kN
    Q = math.pi * drill * qs                         # kN/m ultimate pullout
    Lp = T * FS_P / Q
    first = sv / 2 if first is None else first
    rows, z = [], first
    theta = math.radians(45 + phi / 2)
    while z < H - 0.3:
        # active zone: from the face to the Rankine plane through the toe, along the nail
        horiz = (H - z) / math.tan(theta)
        a = math.radians(inclination)
        La = horiz / (math.cos(a) + math.sin(a) / math.tan(theta))
        rows.append({"z": z, "T": T, "La": La, "Lp": Lp, "L": La + Lp})
        z += sv
    if not rows:
        raise ValueError("The wall is too low for one row of nails at this spacing.")
    Lreq = max(r["L"] for r in rows)
    L = math.ceil(Lreq / round_to) * round_to
    return {"H": H, "Ka": K, "sigma": sigma, "T": T, "T_tensile": Tt, "tensile_ok": T <= Tt,
            "pullout_per_m": Q, "pullout_allow": Q / FS_P, "Lp": Lp, "rows": rows, "L_required": Lreq,
            "L": L, "L_over_H": L / H, "bar": bar, "As": As, "sh": sh, "sv": sv, "inclination": inclination,
            "drill": drill, "qs": qs, "FS_T": FS_T, "FS_P": FS_P}


def anchor(T: float, drill: float = 0.15, qs: float = 150.0, FS: float = 2.0, strands: int = 4,
           strand_area: float = 140.0, fpu: float = 1860.0, free: float = 5.0) -> dict:
    Q = math.pi * drill * qs
    Lb = max(T * FS / Q, 4.5)
    cap = 0.6 * strands * strand_area * fpu / 1000
    return {"T": T, "bond_length": Lb, "free_length": max(free, 4.5), "total": Lb + max(free, 4.5),
            "tendon_capacity": cap, "tendon_ok": T <= cap, "pullout_per_m": Q}


def apply_to_project(project, design: dict) -> int:
    """Set capacity (per nail) and bond (per metre) of the model's nails from the design. Returns the count."""
    n = 0
    for r in project.reinforcements:
        if r.type == "nail":
            r.capacity = design["T_tensile"]
            r.bond = design["pullout_allow"]
            r.spacing = design["sh"]
            n += 1
    return n


def apply_geosynthetic(project, g: dict, bond: float | None = None) -> int:
    n = 0
    for r in project.reinforcements:
        if r.type == "geosynthetic":
            r.capacity = g["T_al"]
            if bond is not None:
                r.bond = bond
            n += 1
    return n


def text_report(d: dict) -> str:
    L = [f"Soil nail wall, H = {d['H']:g} m, nails {d['sh']:g} m x {d['sv']:g} m at {d['inclination']:g} deg",
         "=" * 72,
         f"Ka = {d['Ka']:.3f}; apparent pressure 0.65 Ka (gamma H + q) = {d['sigma']:.1f} kPa",
         f"Design nail force T = {d['T']:.1f} kN",
         f"Bar {d['bar']} mm (As {d['As']:.0f} mm2): allowable tension {d['T_tensile']:.1f} kN  "
         f"-> {'OK' if d['tensile_ok'] else 'NOT OK: use a bigger bar or closer spacing'}",
         f"Drill hole {1000 * d['drill']:.0f} mm, q_s {d['qs']:g} kPa: pullout {d['pullout_per_m']:.1f} kN/m "
         f"(allowable {d['pullout_allow']:.1f} kN/m)",
         f"Pullout length behind the active zone Lp = {d['Lp']:.2f} m", "",
         f"{'row':>4}{'depth m':>9}{'active m':>10}{'total m':>9}"]
    for i, r in enumerate(d["rows"], 1):
        L.append(f"{i:4d}{r['z']:9.2f}{r['La']:10.2f}{r['L']:9.2f}")
    L += ["", f"Nail length: {d['L']:.1f} m for every row (L/H = {d['L_over_H']:.2f}; 0.7 - 1.0 is usual)",
          "Check overall and compound stability with a slope analysis: Use for Model sets the nails of the model."]
    return "\n".join(L)
