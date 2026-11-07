"""Liquefaction triggering from SPT or CPT soundings (simplified procedure).

SPT: Idriss and Boulanger (2008, 2014): fines correction, overburden correction (iterated), CRR for M 7.5
and 1 atm, magnitude scaling factor MSF and overburden factor K_sigma, stress reduction rd.
CPT: Robertson and Wride (1998) with the stress exponent of Robertson (2009): soil behaviour type index Ic,
clean-sand equivalent Qtn,cs, CRR; K_sigma after Youd et al. (2001).
The liquefaction potential index LPI (Iwasaki et al. 1978) sums the deficit over the top 20 m.

Metric units throughout: depth m, stresses kPa, unit weight kN/m3, qc and fs in kPa.
"""
from __future__ import annotations

import math

PA = 101.325
GAMMA_W = 9.81


def rd_ib(z: float, M: float) -> float:
    a = -1.012 - 1.126 * math.sin(z / 11.73 + 5.133)
    b = 0.106 + 0.118 * math.sin(z / 11.28 + 5.142)
    return math.exp(a + b * M) if z <= 34 else 0.12 * math.exp(0.22 * M)


def msf_ib(M: float) -> float:
    return min(1.8, 6.9 * math.exp(-M / 4.0) - 0.058)


def crr_spt(n1cs: float) -> float:
    n = min(n1cs, 37.5)
    v = math.exp(n / 14.1 + (n / 126.0) ** 2 - (n / 23.6) ** 3 + (n / 25.4) ** 4 - 2.8)
    return min(v, 2.0)


def delta_n_fines(fc: float) -> float:
    fc = max(fc, 0.0)
    return math.exp(1.63 + 9.7 / (fc + 0.01) - (15.7 / (fc + 0.01)) ** 2)


def rod_factor(depth: float) -> float:
    rod = depth + 1.5
    return 0.75 if rod < 4 else 0.85 if rod < 6 else 0.95 if rod < 10 else 1.0


def _stresses(rows, water_depth, gamma_default=18.0, gamma_sat_default=19.0):
    """Total and effective vertical stress at the depth of each row (rows sorted by depth)."""
    out, sv, z0 = [], 0.0, 0.0
    for r in rows:
        z = float(r["depth"])
        g_dry = float(r.get("gamma") or gamma_default)
        g_sat = float(r.get("gamma_sat") or r.get("gamma") or gamma_sat_default)
        # integrate from z0 to z, dry above the water table and saturated below
        dry = max(0.0, min(z, water_depth) - z0)
        wet = max(0.0, z - max(z0, water_depth))
        sv += g_dry * dry + g_sat * wet
        u = GAMMA_W * max(0.0, z - water_depth)
        out.append((sv, max(sv - u, 1.0), u))
        z0 = z
    return out


def _csr(sv, sve, amax, z, M):
    return 0.65 * sv / sve * amax * rd_ib(z, M)


def spt(rows: list[dict], water_depth: float, amax: float, M: float = 7.5, energy: float = 60.0,
        borehole_dia_factor: float = 1.0, sampler_factor: float = 1.0) -> dict:
    """rows: [{depth, N, fc (fines %), pi (plasticity index, optional), gamma (optional)}]."""
    rows = sorted(rows, key=lambda r: float(r["depth"]))
    st = _stresses(rows, water_depth)
    out = []
    for r, (sv, sve, u) in zip(rows, st):
        z = float(r["depth"])
        N = float(r["N"])
        fc = float(r.get("fc", 0) or 0)
        pi = r.get("pi")
        n60 = N * energy / 60.0 * rod_factor(z) * borehole_dia_factor * sampler_factor
        dn = delta_n_fines(fc)
        n1cs = n60
        for _ in range(30):                       # CN depends on (N1)60cs
            m = 0.784 - 0.0768 * math.sqrt(max(min(n1cs, 46.0), 0.0))
            cn = min((PA / sve) ** m, 1.7)
            new = cn * n60 + dn
            if abs(new - n1cs) < 1e-4:
                break
            n1cs = new
        n160 = cn * n60
        crr = crr_spt(n1cs)
        msf = msf_ib(M)
        c_sig = min(0.3, 1.0 / (18.9 - 2.55 * math.sqrt(min(n1cs, 37.0))))
        k_sig = min(1.1, 1.0 - c_sig * math.log(sve / PA))
        csr = _csr(sv, sve, amax, z, M)
        row = {"depth": z, "N": N, "N60": n60, "N160": n160, "N160cs": n1cs, "sv": sv, "sve": sve,
               "rd": rd_ib(z, M), "CSR": csr, "CRR75": crr, "MSF": msf, "Ksigma": k_sig, "fc": fc}
        note = None
        if z < water_depth:
            note = "above the water table"
        elif pi is not None and pi != "" and float(pi) >= 7:
            note = f"clay-like (PI = {float(pi):g}): not liquefiable, check cyclic softening"
        if note:
            row.update(FS=None, status="no", note=note)
        else:
            fs = crr * msf * k_sig / csr if csr > 0 else math.inf
            row.update(FS=min(fs, 5.0), status=_status(fs))
        out.append(row)
    return _finish(out, "SPT (Idriss & Boulanger)", water_depth, amax, M)


def cpt(rows: list[dict], water_depth: float, amax: float, M: float = 7.5, a_ratio: float = 0.8) -> dict:
    """rows: [{depth, qc, fs, u2 (optional, kPa), gamma (optional)}], qc and fs in kPa."""
    rows = sorted(rows, key=lambda r: float(r["depth"]))
    st = _stresses(rows, water_depth)
    out = []
    for r, (sv, sve, u0) in zip(rows, st):
        z = float(r["depth"])
        qc, fs_ = float(r["qc"]), float(r.get("fs", 0) or 0)
        qt = qc + (1 - a_ratio) * float(r.get("u2", 0) or 0)
        qnet = max(qt - sv, 1.0)
        Fr = 100.0 * fs_ / qnet
        n = 1.0
        for _ in range(50):
            Qtn = (qnet / PA) * (PA / sve) ** n
            Ic = math.sqrt((3.47 - math.log10(max(Qtn, 1e-6))) ** 2 + (math.log10(max(Fr, 1e-3)) + 1.22) ** 2)
            n2 = min(1.0, max(0.5, 0.381 * Ic + 0.05 * sve / PA - 0.15))
            if abs(n2 - n) < 1e-4:
                break
            n = n2
        kc = 1.0 if Ic <= 1.64 else -0.403 * Ic ** 4 + 5.581 * Ic ** 3 - 21.63 * Ic ** 2 + 33.75 * Ic - 17.88
        qcs = kc * Qtn
        crr = 93 * (qcs / 1000) ** 3 + 0.08 if qcs >= 50 else 0.833 * qcs / 1000 + 0.05
        crr = min(crr, 2.0) if qcs < 160 else 2.0
        msf = msf_ib(M)
        k_sig = min(1.0, (sve / PA) ** (0.7 - 1.0))
        csr = _csr(sv, sve, amax, z, M)
        row = {"depth": z, "qc": qc, "fs": fs_, "Qtn": Qtn, "Fr": Fr, "Ic": Ic, "Kc": kc, "Qtncs": qcs,
               "sv": sv, "sve": sve, "rd": rd_ib(z, M), "CSR": csr, "CRR75": crr, "MSF": msf, "Ksigma": k_sig}
        if z < water_depth:
            row.update(FS=None, status="no", note="above the water table")
        elif Ic > 2.6:
            row.update(FS=None, status="no", note=f"clay-like (Ic = {Ic:.2f}): not liquefiable")
        else:
            f = crr * msf * k_sig / csr if csr > 0 else math.inf
            row.update(FS=min(f, 5.0), status=_status(f))
        out.append(row)
    return _finish(out, "CPT (Robertson & Wride)", water_depth, amax, M)


def _status(fs):
    return "liquefies" if fs < 1.0 else "marginal" if fs < 1.25 else "safe"


def lpi(rows) -> float:
    """Iwasaki liquefaction potential index over the top 20 m."""
    total, z_prev = 0.0, 0.0
    for r in rows:
        z = min(r["depth"], 20.0)
        dz = max(0.0, z - z_prev)
        mid = 0.5 * (z + z_prev)
        fs = r.get("FS")
        F = (1.0 - fs) if fs is not None and fs < 1.0 else 0.0
        total += F * (10.0 - 0.5 * mid) * dz
        z_prev = z
        if r["depth"] >= 20:
            break
    return total


def lpi_class(v: float) -> str:
    return "very low" if v == 0 else "low" if v <= 5 else "high" if v <= 15 else "very high"


def _finish(rows, method, wd, amax, M):
    v = lpi(rows)
    liq = [r for r in rows if r.get("status") == "liquefies"]
    return {"method": method, "water_depth": wd, "amax": amax, "M": M, "rows": rows, "LPI": v,
            "LPI_class": lpi_class(v), "n_liquefies": len(liq),
            "liquefied_depths": [(r["depth"]) for r in liq],
            "min_fs": min((r["FS"] for r in rows if r.get("FS") is not None), default=None)}


def text_report(res: dict) -> str:
    L = [f"Liquefaction triggering - {res['method']}",
         f"Water table {res['water_depth']:g} m deep, amax = {res['amax']:.3f} g, earthquake magnitude M = {res['M']:g}", ""]
    is_spt = "N160cs" in (res["rows"][0] if res["rows"] else {})
    if is_spt:
        L.append(f"{'Depth':>6}{'N':>5}{'(N1)60cs':>10}{'CSR':>7}{'CRR7.5':>8}{'MSF':>6}{'Ks':>6}{'FS':>7}  result")
    else:
        L.append(f"{'Depth':>6}{'qc':>8}{'Ic':>6}{'Qtn,cs':>8}{'CSR':>7}{'CRR7.5':>8}{'FS':>7}  result")
    for r in res["rows"]:
        fs = "-" if r.get("FS") is None else f"{r['FS']:.2f}"
        what = r.get("note") or r["status"]
        if is_spt:
            L.append(f"{r['depth']:>6.1f}{r['N']:>5.0f}{r['N160cs']:>10.1f}{r['CSR']:>7.3f}{r['CRR75']:>8.3f}"
                     f"{r['MSF']:>6.2f}{r['Ksigma']:>6.2f}{fs:>7}  {what}")
        else:
            L.append(f"{r['depth']:>6.1f}{r['qc']:>8.0f}{r['Ic']:>6.2f}{r['Qtncs']:>8.1f}{r['CSR']:>7.3f}"
                     f"{r['CRR75']:>8.3f}{fs:>7}  {what}")
    L.append("")
    L.append(f"Liquefaction potential index LPI = {res['LPI']:.1f} ({res['LPI_class']}); "
             f"{res['n_liquefies']} level(s) with FS < 1.")
    L.append("FS < 1.0 liquefies, 1.0 - 1.25 marginal. Simplified procedure: confirm with site-specific studies "
             "for important structures.")
    return "\n".join(L)
