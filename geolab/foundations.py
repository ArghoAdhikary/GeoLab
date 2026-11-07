"""Shallow foundation bearing capacity and settlement, retaining wall and cantilever sheet pile checks.

Bearing capacity: general equation (Meyerhof 1963 / Hansen 1970 / Vesic 1973 factors) with shape,
depth and load inclination factors, and the water table. Undrained (phi = 0) uses Nc = 5.14
(Skempton-type). The code check uses AS 4678 / AS 2159 style phi_g = 0.5 (Australian Standards), or
FS = 3 (BNBC 2020), from codes.BEARING.

Settlement: immediate (elastic, Ip for a flexible footing) plus primary consolidation of clay layers
(Cc, Cr, e0, preconsolidation pressure), with the stress increase from the 2:1 method.

Retaining wall (gravity or cantilever, treated as a rigid block): Rankine or Coulomb active
pressure on a vertical virtual back, a surcharge and a water table behind the wall. Checks are
sliding, overturning, bearing (Meyerhof effective width) and the eccentricity (resultant in the
middle third).

Cantilever sheet pile in sand: the simplified free-earth (cantilever) method with net pressures,
embedment from moment equilibrium about the toe, times 1.2.
"""
from __future__ import annotations

import math

GW = 9.81


# --------------------------------------------------------------------------- bearing capacity
def factors(phi: float, method: str = "vesic"):
    """(Nc, Nq, Ngamma) for the friction angle in degrees."""
    p = math.radians(phi)
    if phi <= 0:
        return 5.14, 1.0, 0.0
    nq = math.exp(math.pi * math.tan(p)) * math.tan(math.radians(45 + phi / 2)) ** 2
    nc = (nq - 1) / math.tan(p)
    if method == "meyerhof":
        ng = (nq - 1) * math.tan(1.4 * p)
    elif method == "hansen":
        ng = 1.5 * (nq - 1) * math.tan(p)
    else:
        ng = 2 * (nq + 1) * math.tan(p)
    return nc, nq, ng


def bearing(B: float, L: float, D: float, c: float, phi: float, gamma: float, water_depth: float | None = None,
            H: float = 0.0, V: float | None = None, method: str = "vesic", undrained: bool = False) -> dict:
    """Ultimate bearing pressure (kPa) of a rectangular footing B x L (L = 0 or inf: strip) at depth D.

    ``water_depth`` below the ground surface (None = deep). H, V: horizontal and vertical load for the
    inclination factors (per metre for a strip)."""
    strip = not L or L <= 0 or L > 50 * B
    L_ = B if strip else max(L, B)
    phi_ = 0.0 if undrained else phi
    nc, nq, ng = factors(phi_, method)
    p = math.radians(phi_)
    # effective unit weights and overburden with the water table
    gw = gamma - GW
    if water_depth is None or water_depth >= D + B:
        q = gamma * D
        g_eff = gamma
    elif water_depth <= D:
        q = gamma * max(0.0, water_depth) + gw * (D - max(0.0, water_depth))
        g_eff = gw
    else:
        q = gamma * D
        dz = water_depth - D
        g_eff = gw + (gamma - gw) * dz / B
    BL = 0.0 if strip else B / L_
    sc = 1 + BL * (nq / nc if nc else 0.2)
    sq = 1 + BL * math.tan(p)
    sg = max(0.6, 1 - 0.4 * BL)
    k = D / B if D <= B else math.atan(D / B)
    dc = 1 + 0.4 * k
    dq = 1 + 2 * math.tan(p) * (1 - math.sin(p)) ** 2 * k
    dg = 1.0
    ic = iq = ig = 1.0
    if H and V:
        inc = math.degrees(math.atan(abs(H) / V))
        iq = ic = (1 - inc / 90.0) ** 2
        ig = (1 - inc / phi_) ** 2 if phi_ > 0 and inc < phi_ else 0.0
    if undrained:
        qu = c * nc * sc * dc * ic + q
        terms = {"c": c * nc * sc * dc * ic, "q": q, "gamma": 0.0}
    else:
        tc = c * nc * sc * dc * ic
        tq = q * nq * sq * dq * iq
        tg = 0.5 * g_eff * B * ng * sg * dg * ig
        qu = tc + tq + tg
        terms = {"c": tc, "q": tq, "gamma": tg}
    return {"qu": qu, "net": qu - q, "Nc": nc, "Nq": nq, "Ngamma": ng, "q0": q, "terms": terms,
            "strip": strip, "method": method, "B": B, "L": L_ if not strip else None, "D": D}


def bearing_check(project, res: dict, q_applied: float) -> dict:
    from .codes import check_bearing
    return check_bearing(project, None, q_applied, res["qu"])


# --------------------------------------------------------------------------- settlement
def stress_2to1(q: float, B: float, L: float | None, z: float) -> float:
    if not L:
        return q * B / (B + z)
    return q * B * L / ((B + z) * (L + z))


def settlement(q_net: float, B: float, L: float | None, D: float, layers: list[dict], gamma_w: float = GW,
               water_depth: float = 0.0, n_sub: int = 5) -> dict:
    """Settlement (m) under a flexible footing.

    layers: [{"thickness", "gamma", "E", "nu", "Cc", "Cr", "e0", "sigma_p" (kPa, 0 = normally consolidated),
              "kind": "clay"|"sand"}] from the footing base down."""
    rows, s_imm, s_con = [], 0.0, 0.0
    z_top = 0.0
    sv_base = 0.0
    for lay in layers:
        t = float(lay["thickness"])
        for k in range(n_sub):
            dz = t / n_sub
            z = z_top + (k + 0.5) * dz
            depth = D + z
            # vertical effective stress at the middle of the sub-layer
            sv = sv_base + lay["gamma"] * (k + 0.5) * dz
            u = max(0.0, depth - water_depth) * gamma_w
            sve = max(1.0, sv + _above(layers, z_top, D) - u)
            ds = stress_2to1(q_net, B, L, z)
            imm = ds * dz / max(1.0, float(lay.get("E", 1e4))) * (1 - float(lay.get("nu", 0.3)) ** 2)
            con = 0.0
            if lay.get("kind", "sand") == "clay" and lay.get("Cc"):
                e0, cc, cr = float(lay.get("e0", 1.0)), float(lay["Cc"]), float(lay.get("Cr", 0.1 * lay["Cc"]))
                sp = float(lay.get("sigma_p") or 0.0) or sve
                s1 = sve + ds
                if s1 <= sp:
                    con = cr * dz / (1 + e0) * math.log10(s1 / sve)
                elif sve >= sp:
                    con = cc * dz / (1 + e0) * math.log10(s1 / sve)
                else:
                    con = dz / (1 + e0) * (cr * math.log10(sp / sve) + cc * math.log10(s1 / sp))
                imm = 0.0 if lay.get("drained_only") else imm
            s_imm += imm
            s_con += con
            rows.append({"z": z, "sigma_v": sve, "d_sigma": ds, "immediate": imm, "consolidation": con})
        sv_base += lay["gamma"] * t
        z_top += t
    return {"immediate": s_imm, "consolidation": s_con, "total": s_imm + s_con, "rows": rows}


def _above(layers, z_top, D):
    return 0.0 if D <= 0 else layers[0]["gamma"] * D if z_top == 0 else layers[0]["gamma"] * D


# --------------------------------------------------------------------------- retaining wall
def ka(phi: float, beta: float = 0.0, delta: float = 0.0, alpha: float = 0.0, method: str = "rankine") -> float:
    """Active earth pressure coefficient. beta: backfill slope; delta: wall friction; alpha: wall back batter
    from vertical (degrees)."""
    p, b, d, a = (math.radians(v) for v in (phi, beta, delta, alpha))
    if method == "rankine" or (delta == 0 and alpha == 0 and beta == 0):
        if beta == 0:
            return math.tan(math.pi / 4 - p / 2) ** 2
        cb, cp = math.cos(b), math.cos(p)
        root = math.sqrt(max(0.0, cb * cb - cp * cp))
        return cb * (cb - root) / (cb + root)
    num = math.cos(p - a) ** 2
    den = math.cos(a) ** 2 * math.cos(a + d) * (1 + math.sqrt(max(0.0, math.sin(p + d) * math.sin(p - b) /
                                                                  (math.cos(a + d) * math.cos(a - b))))) ** 2
    return num / den


def kp(phi: float) -> float:
    return math.tan(math.pi / 4 + math.radians(phi) / 2) ** 2


def retaining_wall(H: float, base: float, toe: float, stem_top: float, stem_bottom: float, base_t: float,
                   gamma_c: float = 24.0, back_phi: float = 30.0, back_gamma: float = 18.0, back_c: float = 0.0,
                   surcharge: float = 10.0, water_h: float = 0.0, beta: float = 0.0,
                   found_phi: float = 30.0, found_c: float = 0.0, found_gamma: float = 19.0, Df: float = 0.5,
                   delta_base: float | None = None, method: str = "rankine", passive: bool = False) -> dict:
    """Cantilever (or gravity, with a wide stem) concrete wall of total height H (base underside to top of
    fill). Lengths in m, stresses in kPa, forces per metre run. Returns the forces and the checks."""
    hs = H - base_t
    heel = base - toe - stem_bottom
    if heel < -1e-9:
        raise ValueError("The base is narrower than the toe plus the stem.")
    K = ka(back_phi, beta, 0.0, 0.0, method)
    # weights and lever arms about the toe
    W, M = [], []

    def add(name, w, x):
        W.append((name, w))
        M.append((name, w * x))
    add("Base", gamma_c * base * base_t, base / 2)
    add("Stem (rectangle)", gamma_c * stem_top * hs, toe + stem_bottom - stem_top / 2)
    if stem_bottom > stem_top:
        add("Stem (taper)", gamma_c * 0.5 * (stem_bottom - stem_top) * hs,
            toe + (stem_bottom - stem_top) * 2 / 3)
    add("Soil on the heel", back_gamma * heel * hs, base - heel / 2)
    if beta > 0:
        dh = heel * math.tan(math.radians(beta))
        add("Sloping fill", back_gamma * 0.5 * heel * dh, base - heel / 3)
    add("Surcharge on the heel", surcharge * heel, base - heel / 2)
    Htot = H + (heel * math.tan(math.radians(beta)) if beta > 0 else 0.0)
    # active thrust on the virtual back (vertical through the heel)
    hw = min(max(0.0, water_h), Htot)
    g_sub = back_gamma - GW
    # pressure diagram split into dry above water and submerged below, plus water
    h_dry = Htot - hw
    Pa_soil_dry = 0.5 * K * back_gamma * h_dry ** 2
    sv_wt = back_gamma * h_dry
    Pa_soil_wet = K * sv_wt * hw + 0.5 * K * g_sub * hw ** 2
    Pw = 0.5 * GW * hw ** 2
    Pq = K * surcharge * Htot
    Pc = -2 * back_c * math.sqrt(K) * Htot
    Ph_items = [("Earth pressure (above water)", Pa_soil_dry, hw + h_dry / 3),
                ("Earth pressure (below water)", Pa_soil_wet,
                 (K * sv_wt * hw * hw / 2 + 0.5 * K * g_sub * hw ** 2 * hw / 3) / Pa_soil_wet if Pa_soil_wet else 0),
                ("Water pressure", Pw, hw / 3), ("Surcharge", Pq, Htot / 2)]
    if back_c > 0:
        Ph_items.append(("Cohesion (reduces)", Pc, Htot / 2))
    if beta > 0:          # Rankine thrust is parallel to the slope: vertical part helps
        Pv = (Pa_soil_dry + Pa_soil_wet) * math.tan(math.radians(beta))
        add("Vertical part of the thrust", Pv, base)
    Ph = max(0.0, sum(p for _, p, _ in Ph_items))
    Mo = sum(p * y for _, p, y in Ph_items if p > 0) + sum(p * y for _, p, y in Ph_items if p < 0)
    sumW = sum(w for _, w in W)
    Mr = sum(m for _, m in M)
    Pp = 0.5 * kp(found_phi) * found_gamma * Df ** 2 + 2 * found_c * math.sqrt(kp(found_phi)) * Df if passive else 0.0
    d = math.radians(delta_base if delta_base is not None else 2 / 3 * found_phi)
    # uplift under the base from the water behind (triangular to zero at the toe)
    U = 0.5 * GW * hw * base if hw > 0 else 0.0
    Mu = U * base * 2 / 3
    N = sumW - U
    sliding = (N * math.tan(d) + 2 / 3 * found_c * base + Pp) / Ph if Ph > 0 else math.inf
    overturning = Mr / (Mo + Mu) if Mo + Mu > 0 else math.inf
    x_res = (Mr - Mo - Mu) / N if N > 0 else 0.0
    e = base / 2 - x_res
    B_eff = max(0.0, base - 2 * abs(e))
    q_max = N / base * (1 + 6 * e / base) if abs(e) <= base / 6 else (2 * N / (3 * max(1e-6, x_res)) if x_res > 0 else math.inf)
    q_min = N / base * (1 - 6 * e / base) if abs(e) <= base / 6 else 0.0
    bc = bearing(max(B_eff, 1e-3), 0, Df, found_c, found_phi, found_gamma, H=Ph, V=max(N, 1e-6))
    q_eff = N / max(B_eff, 1e-6)
    fos_bearing = bc["qu"] / q_eff if q_eff > 0 else math.inf
    return {"Ka": K, "weights": W, "sum_W": sumW, "M_resist": Mr, "thrust": Ph_items, "H_total": Ph,
            "M_overturn": Mo + Mu, "uplift": U, "N": N, "passive": Pp, "e": e, "B_eff": B_eff,
            "q_max": q_max, "q_min": q_min, "q_ult": bc["qu"],
            "FS_sliding": sliding, "FS_overturning": overturning, "FS_bearing": fos_bearing,
            "middle_third": abs(e) <= base / 6,
            "checks": [("Sliding", sliding, 1.5), ("Overturning", overturning, 2.0),
                       ("Bearing (effective width)", fos_bearing, 3.0)]}


# --------------------------------------------------------------------------- cantilever sheet pile in sand
def sheet_pile_cantilever(H: float, phi: float, gamma: float, surcharge: float = 0.0, factor: float = 1.2) -> dict:
    """Embedment of a cantilever sheet pile retaining H in dry sand (simplified method, net pressures).

    Solves moment equilibrium about the point of rotation with net passive Kp - Ka below dredge level,
    then adds 20 % (``factor``). Also the maximum bending moment (kNm/m)."""
    Ka, Kp = ka(phi), kp(phi)
    dK = Kp - Ka

    def moment(d):
        # active above dredge + active below, minus passive below, about the toe at depth d below dredge
        Pa1 = 0.5 * Ka * gamma * H * H
        Pq = Ka * surcharge * (H + d)
        Pa2 = Ka * gamma * H * d
        net_p = 0.5 * dK * gamma * d * d
        return (Pa1 * (d + H / 3) + Pq * (H + d) / 2 + Pa2 * d / 2 - net_p * d / 3)

    lo, hi = 0.01, 10 * H
    if moment(hi) > 0:
        raise ValueError("No embedment found: the soil is too weak for a cantilever wall.")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if moment(mid) > 0:
            lo = mid
        else:
            hi = mid
    d0 = hi
    # maximum moment at zero shear below dredge level
    Pa = 0.5 * Ka * gamma * H * H + Ka * surcharge * H
    z = math.sqrt(max(0.0, 2 * Pa / (dK * gamma))) if dK > 0 else 0.0
    Mmax = (0.5 * Ka * gamma * H * H * (z + H / 3) + Ka * surcharge * H * (z + H / 2)
            + Ka * gamma * H * z * z / 2 - dK * gamma * z ** 3 / 6)
    return {"Ka": Ka, "Kp": Kp, "d0": d0, "embedment": factor * d0, "total_length": H + factor * d0,
            "M_max": Mmax, "zero_shear_depth": z}


def wall_report(r: dict) -> str:
    lines = [f"Ka = {r['Ka']:.3f}", "", "Vertical forces (kN/m):"]
    lines += [f"  {n:<30}{w:10.1f}" for n, w in r["weights"]]
    lines += [f"  {'Total':<30}{r['sum_W']:10.1f}   uplift {r['uplift']:.1f}", "", "Horizontal forces (kN/m):"]
    lines += [f"  {n:<30}{p:10.1f}  at {y:5.2f} m" for n, p, y in r["thrust"]]
    lines += [f"  {'Total':<30}{r['H_total']:10.1f}", "",
              f"Resultant at e = {r['e']:.3f} m from the centre "
              f"({'in the middle third' if r['middle_third'] else 'OUTSIDE the middle third'})",
              f"Base pressure {r['q_min']:.1f} - {r['q_max']:.1f} kPa; ultimate bearing {r['q_ult']:.0f} kPa "
              f"on the effective width {r['B_eff']:.2f} m", ""]
    for name, fs, req in r["checks"]:
        lines.append(f"  {name:<28} FS {fs:7.2f}  (need {req:.1f})  {'OK' if fs >= req else 'NOT OK'}")
    return "\n".join(lines)
