"""Braced excavations: apparent earth pressure, strut loads and basal heave.

Apparent pressure envelopes (Peck 1969; Terzaghi, Peck and Mesri 1996):
* Sand:        uniform 0.65 Ka gamma H over the full height.
* Soft to medium clay (N = gamma H / Su > 4):  rises from 0 at the top to its peak at 0.25 H, then uniform;
               peak = max(gamma H (1 - 4 Su / (gamma H)), 0.3 gamma H).
* Stiff clay (N <= 4):  trapezoid 0 -> 0.25 H -> 0.75 H -> 0 at the base, peak 0.3 gamma H (0.2 - 0.4).
A crest surcharge q adds Ka q (sand) or q (clay, Ka = 1) uniformly.

Strut loads by the hinge method: the wall is simply supported between struts, the part above the first
strut cantilevers onto it, and the span below the lowest strut rests on the soil at the excavation base.
Basal heave in clay (Bjerrum and Eide 1956): FS = Nc Su / (gamma H + q), Nc after Skempton.
"""
from __future__ import annotations

import math


def ka(phi):
    return math.tan(math.radians(45 - phi / 2)) ** 2


def envelope(soil: str, H: float, gamma: float, phi: float = 30.0, su: float = 0.0, q: float = 0.0) -> dict:
    """Pressure diagram as [(depth, pressure)] points, linear between them."""
    if H <= 0:
        raise ValueError("Give the excavation depth.")
    if soil == "sand":
        K = ka(phi)
        p = 0.65 * K * gamma * H + K * q
        pts = [(0.0, p), (H, p)]
        label = f"Sand: 0.65 Ka gamma H + Ka q (Ka = {K:.3f})"
    else:
        if su <= 0:
            raise ValueError("Give the undrained strength Su of the clay.")
        N = gamma * H / su
        if N > 4:
            p = max(gamma * H * (1 - 4 * su / (gamma * H)), 0.3 * gamma * H) + q
            pts = [(0.0, 0.0), (0.25 * H, p), (H, p)]
            label = f"Soft to medium clay (gamma H / Su = {N:.1f} > 4)"
        else:
            p = 0.3 * gamma * H + q
            pts = [(0.0, 0.0), (0.25 * H, p), (0.75 * H, p), (H, 0.0)]
            label = f"Stiff clay (gamma H / Su = {N:.1f} <= 4)"
    return {"points": pts, "peak": max(v for _, v in pts), "label": label, "H": H, "soil": soil}


def pressure_at(pts, z):
    for (z0, p0), (z1, p1) in zip(pts, pts[1:]):
        if z0 <= z <= z1:
            return p0 if z1 == z0 else p0 + (p1 - p0) * (z - z0) / (z1 - z0)
    return 0.0


def _span(pts, a, b, n=200):
    """Resultant force and its depth for the pressure between depths a and b."""
    if b <= a:
        return 0.0, a
    h = (b - a) / n
    F = M = 0.0
    for i in range(n):
        z = a + (i + 0.5) * h
        f = pressure_at(pts, z) * h
        F += f
        M += f * z
    return F, (M / F if F > 0 else (a + b) / 2)


def strut_loads(env: dict, levels: list[float], spacing: float = 3.0) -> dict:
    """Load of each strut (kN per strut) for strut depths `levels` (m below the top)."""
    H = env["H"]
    lv = sorted(x for x in levels if 0 < x < H)
    if not lv:
        raise ValueError("Give at least one strut depth between the top and the base.")
    supports = lv + [H]                         # the base of the excavation is the last support
    R = [0.0] * len(supports)
    F, _ = _span(env["points"], 0.0, lv[0])     # cantilever above the first strut
    R[0] += F
    Mmax = 0.0
    for i in range(len(supports) - 1):
        a, b = supports[i], supports[i + 1]
        F, zc = _span(env["points"], a, b)
        rb = F * (zc - a) / (b - a)
        R[i] += F - rb
        R[i + 1] += rb
        w = F / (b - a)
        Mmax = max(Mmax, w * (b - a) ** 2 / 8)
    struts = [{"depth": d, "per_m": r, "load": r * spacing} for d, r in zip(lv, R[:-1])]
    return {"struts": struts, "base_reaction": R[-1], "M_max": Mmax, "spacing": spacing,
            "total": sum(R)}


def basal_heave(H: float, B: float, L: float, su: float, gamma: float, q: float = 0.0) -> dict:
    L = max(L, B) if L else 1e9
    Nc = 5 * (1 + 0.2 * min(H / B, 2.5)) * (1 + 0.2 * B / L)
    Nc = min(Nc, 9.0)
    FS = Nc * su / (gamma * H + q)
    return {"Nc": Nc, "FS": FS, "ok": FS >= 1.5}


def text_report(env: dict, st: dict | None = None, heave: dict | None = None) -> str:
    L = [f"Braced excavation, depth H = {env['H']:g} m", "=" * 72, env["label"],
         f"Peak apparent pressure {env['peak']:.1f} kPa",
         "Diagram (depth m, kPa): " + ", ".join(f"({z:.2f}, {p:.1f})" for z, p in env["points"])]
    if st:
        L += ["", f"Strut loads (struts every {st['spacing']:g} m along the wall):",
              f"{'depth m':>9}{'kN/m':>10}{'kN/strut':>11}"]
        for s in st["struts"]:
            L.append(f"{s['depth']:9.2f}{s['per_m']:10.1f}{s['load']:11.1f}")
        L.append(f"Carried by the soil below the base: {st['base_reaction']:.1f} kN/m")
        L.append(f"Largest wall bending moment (simple spans, approx.): {st['M_max']:.1f} kNm/m")
    if heave:
        L += ["", f"Basal heave (Bjerrum and Eide): Nc = {heave['Nc']:.2f}, FS = {heave['FS']:.2f}  "
                  f"-> {'OK (>= 1.5)' if heave['ok'] else 'NOT OK: below 1.5'}"]
    L += ["", "Apparent pressure envelopes are for strut design of excavations deeper than about 6 m with "
              "the water table below the base. Model the wall and its stages with a stress analysis for design."]
    return "\n".join(L)
