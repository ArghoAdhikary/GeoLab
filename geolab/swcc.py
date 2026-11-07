"""Estimate the soil-water characteristic curve (SWCC) and the hydraulic conductivity from the grain size.

* Sands and gravels (no liquid limit): the Modified Kovacs model (Aubertin, Mbonimpa, Bussiere &
  Chapuis 2003) from D10, D60 and the void ratio. The curve is fitted with van Genuchten (alpha, n)
  so it can be used directly in the seepage analysis. Saturated k from Chapuis (2004),
  k (cm/s) = 2.4622 [D10^2 e^3 / (1 + e)]^0.7825, with D10 in mm.
* Silts and clays: the average van Genuchten parameters and k of the USDA soil texture classes
  (Carsel & Parrish 1988), picked from the USCS symbol or the liquid limit.

These are estimates, good to within about one order of magnitude for k. Use test results when
you have them.
"""
from __future__ import annotations

import math

import numpy as np

GW_KPA_PER_CM = 0.0981          # 1 cm of water head in kPa


def mk_swcc(d10_mm: float, d60_mm: float, e: float, suction_kpa=None):
    """Degree of saturation at each suction (kPa) by the Modified Kovacs model."""
    if suction_kpa is None:
        suction_kpa = np.logspace(-1, 6, 120)
    psi_cm = np.asarray(suction_kpa, float) / GW_KPA_PER_CM
    psi0 = 1e7
    cu = max(1.0, d60_mm / max(d10_mm, 1e-6))
    d10_cm = d10_mm / 10.0
    hco = 0.75 / ((1.17 * math.log10(cu) + 1) * e * d10_cm)
    m, ac = 1.0 / cu, 0.01
    psir = 0.86 * hco ** 1.2
    psin = 1.0
    c_psi = 1 - np.log(1 + psi_cm / psir) / math.log(1 + psi0 / psir)
    c_psi = np.clip(c_psi, 0.0, 1.0)
    sc = 1 - ((hco / psi_cm) ** 2 + 1) ** m * np.exp(-m * (hco / psi_cm) ** 2)
    sa = ac * c_psi * (hco / psin) ** (2 / 3) / (e ** (1 / 3) * (psi_cm / psin) ** (1 / 6))
    sa = np.clip(sa, 0.0, 1.0)
    sr = sc + sa * (1 - sc)
    sr = np.clip(sr, 0.0, 1.0)
    return np.asarray(suction_kpa, float), sr, {"hco_cm": hco, "psir_cm": psir}


def fit_van_genuchten(suction_kpa, sr, theta_s, gamma_w: float = 9.81):
    """Fit theta = theta_r + (theta_s - theta_r) / (1 + (alpha psi)^n)^(1 - 1/n), psi in m of water."""
    psi_m = np.asarray(suction_kpa) / gamma_w
    th = theta_s * np.asarray(sr)
    best = None
    for n in np.linspace(1.05, 4.0, 60):
        m = 1 - 1 / n
        for la in np.linspace(-3, 2.5, 56):
            a = 10 ** la
            se = (1 + (a * psi_m) ** n) ** (-m)
            # theta_r by least squares for this shape
            A = np.vstack([1 - se, se]).T
            sol, *_ = np.linalg.lstsq(A, th, rcond=None)
            thr = float(np.clip(sol[0], 0.0, 0.5 * theta_s))
            pred = thr + (theta_s - thr) * se
            err = float(((pred - th) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, a, n, thr)
    _, a, n, thr = best
    return {"vg_alpha": a, "vg_n": n, "theta_r": thr, "theta_s": theta_s,
            "rmse": math.sqrt(best[0] / len(th))}


# Carsel & Parrish (1988): theta_r, theta_s, alpha (1/m), n, k_sat (m/s)
CARSEL_PARRISH = {
    "sand": (0.045, 0.43, 14.5, 2.68, 8.25e-5), "loamy sand": (0.057, 0.41, 12.4, 2.28, 4.05e-5),
    "sandy loam": (0.065, 0.41, 7.5, 1.89, 1.23e-5), "loam": (0.078, 0.43, 3.6, 1.56, 2.89e-6),
    "silt": (0.034, 0.46, 1.6, 1.37, 6.94e-7), "silt loam": (0.067, 0.45, 2.0, 1.41, 1.25e-6),
    "sandy clay loam": (0.100, 0.39, 5.9, 1.48, 3.64e-6), "clay loam": (0.095, 0.41, 1.9, 1.31, 7.22e-7),
    "silty clay loam": (0.089, 0.43, 1.0, 1.23, 1.94e-7), "sandy clay": (0.100, 0.38, 2.7, 1.23, 3.33e-7),
    "silty clay": (0.070, 0.36, 0.5, 1.09, 5.56e-8), "clay": (0.068, 0.38, 0.8, 1.09, 5.56e-7),
}
USCS_TEXTURE = {"SM": "sandy loam", "SC": "sandy clay loam", "ML": "silt loam", "MH": "silty clay loam",
                "CL": "clay loam", "CH": "clay", "CL-ML": "silt loam", "SC-SM": "sandy loam", "OL": "silt loam",
                "OH": "silty clay", "SP": "sand", "SW": "sand", "SP-SM": "loamy sand", "GM": "sandy loam",
                "GC": "sandy clay loam"}


def texture_for(uscs: str | None = None, wl: float | None = None) -> str:
    if uscs and uscs.upper() in USCS_TEXTURE:
        return USCS_TEXTURE[uscs.upper()]
    if wl is None:
        return "loam"
    return "silt loam" if wl < 30 else "clay loam" if wl < 40 else "silty clay loam" if wl < 50 else "clay"


def k_sat(d10_mm: float, e: float) -> float:
    """Saturated hydraulic conductivity (m/s) of a sand or gravel, Chapuis (2004)."""
    return 2.4622 * (d10_mm ** 2 * e ** 3 / (1 + e)) ** 0.7825 / 100.0


def estimate(d10_mm: float = 0.0, d60_mm: float = 0.0, e: float = 0.7, wl: float | None = None,
             uscs: str | None = None) -> dict:
    """Everything for a material: theta_s, theta_r, van Genuchten alpha and n, k_sat and the curve."""
    suction = np.logspace(-1, 6, 120)
    plastic = bool(wl) or (uscs or "").upper() in ("ML", "MH", "CL", "CH", "CL-ML", "OL", "OH", "SC", "GC")
    if plastic or d10_mm <= 0:
        tex = texture_for(uscs, wl)
        thr, ths, a, n, ks = CARSEL_PARRISH[tex]
        if e:
            ths = e / (1 + e)
        psi_m = suction / 9.81
        se = (1 + (a * psi_m) ** n) ** (-(1 - 1 / n))
        theta = thr + (ths - thr) * se
        out = {"vg_alpha": a, "vg_n": n, "theta_r": thr, "theta_s": ths, "k_sat": ks, "rmse": 0.0,
               "method": f"Carsel & Parrish (1988), {tex}", "texture": tex}
        sr = theta / ths
    else:
        psi, sr, info = mk_swcc(d10_mm, d60_mm, e)
        theta_s = e / (1 + e)
        out = {**fit_van_genuchten(psi, sr, theta_s), "k_sat": k_sat(d10_mm, e),
               "method": "Modified Kovacs (Aubertin et al. 2003) and Chapuis (2004)", **info}
        theta = theta_s * sr
    out.update({"suction": suction.tolist(), "sr": np.asarray(sr).tolist(), "theta": np.asarray(theta).tolist(),
                "air_entry_kpa": _air_entry(suction, sr)})
    out["vg_alpha"], out["vg_n"] = float(out["vg_alpha"]), float(out["vg_n"])
    return out


def _air_entry(psi, sr):
    i = int(np.argmax(np.asarray(sr) < 0.95))
    return float(psi[i]) if i > 0 else float(psi[0])


def apply(material, est: dict):
    material.hyd_model = "van_genuchten"
    material.theta_s = round(est["theta_s"], 4)
    material.theta_r = round(est["theta_r"], 4)
    material.vg_alpha = float(f"{est['vg_alpha']:.4g}")
    material.vg_n = round(est["vg_n"], 3)
    material.k_sat = float(f"{est['k_sat']:.3g}")
