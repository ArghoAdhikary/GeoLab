"""Pile design by hand-calculation methods: axial capacity of a single pile, pile groups and settlement.

Single pile, layer by layer (0.25 m steps):
* Clay, shaft:  fs = alpha Su. Driven piles: API RP 2GEO alpha = 0.5 psi^-0.5 (psi <= 1) or 0.5 psi^-0.25
  (psi > 1), psi = Su / sigma'v, alpha <= 1. Bored piles: alpha = 0.45 (Skempton 1959), fs <= 100 kPa.
* Sand, shaft:  fs = K tan(delta) sigma'v (beta method), K = (K/K0) (1 - sin phi'), delta = (delta/phi') phi';
  K/K0 = 1.5 driven, 0.9 bored; delta/phi' = 0.8 driven, 1.0 bored (Kulhawy 1984); fs limited as in API.
* Base:  clay qb = 9 Su; sand qb = Nq sigma'v with the API Nq and limit; a bored pile in sand mobilises
  half of it at working settlements.
Qult = Qs + Qb - W' (for compression); uplift = Qs / FS + W'. Allowable = Qult / FS.

Group: efficiency by Converse-Labarre for piles in sand (bored) and friction piles; block failure in clay
(Terzaghi and Peck): Qblock = 2 (Bg + Lg) L Su,avg + Nc Su,base Bg Lg with Nc (Skempton) <= 9.
Settlement: single pile s = D/100 + Q L / (A E) (Vesic, simplified); group s_g = s sqrt(Bg / D).
"""
from __future__ import annotations

import math

GAMMA_W = 9.81
# API RP 2GEO (sand): phi' -> (beta-limit fs kPa, Nq, qb limit kPa)
API_SAND = [(20, 67, 8, 1900), (25, 81, 12, 2900), (30, 96, 20, 4800), (35, 115, 40, 9600), (40, 115, 50, 12000)]


def _api(phi):
    phi = max(API_SAND[0][0], min(API_SAND[-1][0], phi))
    for (p0, f0, n0, q0), (p1, f1, n1, q1) in zip(API_SAND, API_SAND[1:]):
        if p0 <= phi <= p1:
            t = (phi - p0) / (p1 - p0)
            return f0 + t * (f1 - f0), n0 + t * (n1 - n0), q0 + t * (q1 - q0)
    return API_SAND[-1][1:]


def alpha_api(su, sv):
    psi = su / max(sv, 1e-6)
    a = 0.5 * psi ** -0.5 if psi <= 1 else 0.5 * psi ** -0.25
    return min(a, 1.0)


def section(D: float, shape: str = "circle"):
    """(perimeter, base area) of a pile of diameter / width D."""
    if shape == "square":
        return 4 * D, D * D
    return math.pi * D, math.pi * D * D / 4


def _layer_at(layers, z):
    top = 0.0
    for L in layers:
        t = float(L.get("thickness") or 0)
        if t <= 0 or z < top + t:
            return L
        top += t
    return layers[-1]


def axial(layers: list[dict], D: float, length: float, kind: str = "driven", shape: str = "circle",
          water_depth: float = 0.0, FS: float = 2.5, pile_gamma: float = 24.0, dz: float = 0.25) -> dict:
    """layers: dicts with thickness (0 = to the bottom), soil 'clay' or 'sand', su (kPa), phi (deg), gamma."""
    if D <= 0 or length <= 0 or not layers:
        raise ValueError("Give the pile diameter, length and at least one layer.")
    driven = kind == "driven"
    per, area = section(D, shape)
    sv = 0.0
    Qs, rows = 0.0, []
    n = max(1, int(math.ceil(length / dz)))
    h = length / n
    for i in range(n):
        zm = (i + 0.5) * h
        L = _layer_at(layers, zm)
        g = float(L.get("gamma") or 18.0)
        sv_mid = sv + g * h / 2
        u_mid = max(0.0, zm - water_depth) * GAMMA_W
        sve = max(sv_mid - u_mid, 1e-3)
        if L.get("soil", "clay").startswith("c"):
            su = float(L.get("su") or 0)
            if driven:
                fs = alpha_api(su, sve) * su
            else:
                fs = min(0.45 * su, 100.0)
        else:
            phi = float(L.get("phi") or 30)
            K0 = 1 - math.sin(math.radians(phi))
            K = (1.5 if driven else 0.9) * K0
            delta = (0.8 if driven else 1.0) * phi
            fs = min(K * math.tan(math.radians(delta)) * sve, _api(phi)[0])
        dQ = fs * per * h
        Qs += dQ
        rows.append({"z": zm, "soil": L.get("soil", "clay"), "sigma_v": sve, "fs": fs, "Qs": Qs})
        sv += g * h
    base = _layer_at(layers, length - 1e-6)
    sve_b = max(sv - max(0.0, length - water_depth) * GAMMA_W, 1e-3)
    if base.get("soil", "clay").startswith("c"):
        qb = 9.0 * float(base.get("su") or 0)
    else:
        _, Nq, qlim = _api(float(base.get("phi") or 30))
        qb = min(Nq * sve_b, qlim) * (1.0 if driven else 0.5)
    Qb = qb * area
    submerged = max(0.0, length - max(water_depth, 0.0))
    W = area * (pile_gamma * length - GAMMA_W * submerged)
    Qult = Qs + Qb - W
    return {"Qs": Qs, "Qb": Qb, "qb": qb, "W": W, "Qult": Qult, "Qall": Qult / FS, "uplift": Qs / FS + W,
            "FS": FS, "perimeter": per, "area": area, "D": D, "length": length, "kind": kind, "shape": shape,
            "rows": rows}


def converse_labarre(n_rows: int, n_cols: int, D: float, s: float) -> float:
    theta = math.degrees(math.atan(D / s))
    m, n = n_cols, n_rows
    return max(0.0, 1 - theta * ((n - 1) * m + (m - 1) * n) / (90 * m * n))


def nc_skempton(depth, B, L):
    nc = 5 * (1 + 0.2 * min(depth / B, 2.5)) * (1 + 0.2 * B / L)
    return min(nc, 9.0)


def group(single: dict, layers: list[dict], n_rows: int, n_cols: int, spacing: float, FS: float | None = None,
          E_pile: float = 30e6, load: float | None = None) -> dict:
    """Capacity and settlement of a rectangular group (n_rows x n_cols piles at the given spacing)."""
    D, Lp = single["D"], single["length"]
    if spacing < D:
        raise ValueError("The spacing must be at least the pile diameter.")
    FS = FS or single["FS"]
    npiles = n_rows * n_cols
    Bg = (n_cols - 1) * spacing + D
    Lg = (n_rows - 1) * spacing + D
    Bg, Lg = min(Bg, Lg), max(Bg, Lg)
    clay = all(L.get("soil", "clay").startswith("c") for L in layers)
    eta = 1.0 if (single["kind"] == "driven" and not clay) else converse_labarre(n_rows, n_cols, D, spacing)
    Q_eff = eta * npiles * single["Qult"]
    out = {"n": npiles, "Bg": Bg, "Lg": Lg, "efficiency": eta, "Q_efficiency": Q_eff, "Q_block": None}
    if clay:
        # average Su along the pile, and at the base
        su_avg = 0.0
        z = 0.0
        n = 0
        while z < Lp:
            su_avg += float(_layer_at(layers, z).get("su") or 0)
            n += 1
            z += 0.25
        su_avg /= max(n, 1)
        su_b = float(_layer_at(layers, Lp - 1e-6).get("su") or 0)
        Qblock = 2 * (Bg + Lg) * Lp * su_avg + nc_skempton(Lp, Bg, Lg) * su_b * Bg * Lg
        out["Q_block"] = Qblock
    Qg = min(Q_eff, out["Q_block"]) if out["Q_block"] is not None else Q_eff
    out["Qult"] = Qg
    out["Qall"] = Qg / FS
    out["governs"] = "block failure" if out["Q_block"] is not None and out["Q_block"] < Q_eff else "pile efficiency"
    Q1 = (load / npiles) if load else single["Qall"]
    s1 = D / 100 + Q1 * Lp / (single["area"] * E_pile)
    out["settlement_single"] = s1
    out["settlement_group"] = s1 * math.sqrt(Bg / D)
    out["load_per_pile"] = Q1
    return out


def text_report(r: dict, g: dict | None = None) -> str:
    L = [f"{r['kind'].title()} {'circular' if r['shape'] == 'circle' else 'square'} pile, D = {r['D']:g} m, "
         f"length {r['length']:g} m", "=" * 72,
         f"Shaft resistance Qs    = {r['Qs']:10.1f} kN",
         f"Base resistance  Qb    = {r['Qb']:10.1f} kN   (qb = {r['qb']:.0f} kPa)",
         f"Pile weight (buoyant)  = {r['W']:10.1f} kN",
         f"Ultimate capacity Qult = {r['Qult']:10.1f} kN",
         f"Allowable (FS {r['FS']:g})     = {r['Qall']:10.1f} kN",
         f"Allowable uplift       = {r['uplift']:10.1f} kN", "",
         f"{'z (m)':>7}{'soil':>6}{'sigma_v`':>10}{'fs kPa':>9}{'Qs kN':>10}"]
    step = max(1, len(r["rows"]) // 20)
    for x in r["rows"][::step]:
        L.append(f"{x['z']:7.2f}{x['soil'][:4]:>6}{x['sigma_v']:10.1f}{x['fs']:9.1f}{x['Qs']:10.1f}")
    if g:
        L += ["", f"Group of {g['n']} piles ({g['Bg']:.2f} x {g['Lg']:.2f} m)",
              f"  Efficiency {g['efficiency']:.3f}: {g['Q_efficiency']:.0f} kN"]
        if g["Q_block"] is not None:
            L.append(f"  Block failure: {g['Q_block']:.0f} kN")
        L += [f"  Ultimate group capacity {g['Qult']:.0f} kN ({g['governs']} governs), allowable {g['Qall']:.0f} kN",
              f"  Settlement at {g['load_per_pile']:.0f} kN per pile: single {1000 * g['settlement_single']:.1f} mm, "
              f"group {1000 * g['settlement_group']:.1f} mm"]
    L += ["", "Hand-calculation methods for preliminary design. Load tests and the project's code govern."]
    return "\n".join(L)
