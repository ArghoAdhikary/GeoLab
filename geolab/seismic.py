"""Quick earthquake check of a solved slope: the yield acceleration ky and the permanent (Newmark)
displacement from published regression equations - no time history and no dynamic analysis needed.

ky is the horizontal seismic coefficient that brings F down to 1. It is found on the slip surfaces kept by
the solved slope analysis (whatif.SurfacePool), so a different surface can become critical as kh grows.

Displacement (cm) from ky / amax, and the earthquake magnitude where the equation uses it:
* Jibson (2007), eq. 6:  log D = 0.215 + log[(1 - ky/amax)^2.341 (ky/amax)^-1.438]           (sd 0.510)
* Jibson (2007), eq. 7:  log D = -2.710 + log[(1 - ky/amax)^2.335 (ky/amax)^-1.478] + 0.424 M (sd 0.454)
* Ambraseys and Menu (1988), median:  log D = 0.90 + log[(1 - ky/amax)^2.53 (ky/amax)^-1.09]

amax is the peak ground acceleration (g) at the slope: the design code's value (BNBC 2020 or AS 1170.4,
Design > Design Code Settings) unless one is entered. Hazard classes after Jibson and Michael (2009).
"""
from __future__ import annotations

import math

METHODS = {
    "jibson07": "Jibson (2007), ky/amax",
    "jibson07m": "Jibson (2007), ky/amax and magnitude",
    "ambraseys88": "Ambraseys and Menu (1988)",
}
CLASSES = [(1.0, "low", "Low: less than 1 cm"), (5.0, "moderate", "Moderate: 1 to 5 cm"),
           (15.0, "high", "High: 5 to 15 cm"), (math.inf, "very high", "Very high: more than 15 cm")]


def displacement(ky: float, amax: float, M: float = 7.0, method: str = "jibson07") -> float:
    """Newmark displacement in cm. 0 when ky >= amax; inf when ky <= 0 (unstable without an earthquake)."""
    if ky <= 0:
        return math.inf
    if amax <= 0 or ky >= amax:
        return 0.0
    r = ky / amax
    if method == "jibson07":
        log_d = 0.215 + math.log10((1 - r) ** 2.341 * r ** -1.438)
    elif method == "jibson07m":
        log_d = -2.710 + math.log10((1 - r) ** 2.335 * r ** -1.478) + 0.424 * M
    elif method == "ambraseys88":
        log_d = 0.90 + math.log10((1 - r) ** 2.53 * r ** -1.09)
    else:
        raise ValueError(f"Unknown method '{method}'")
    return 10 ** log_d


def hazard(d_cm: float) -> tuple[str, str]:
    for lim, key, label in CLASSES:
        if d_cm < lim:
            return key, label
    return CLASSES[-1][1], CLASSES[-1][2]


def yield_kh(pool, hi: float = 0.8) -> dict:
    """Horizontal seismic coefficient ky that gives F = 1 on the pool's surfaces."""
    from .whatif import bisect_target
    f0 = pool.fos({"kh": 0.0})
    if not math.isfinite(f0):
        raise ValueError("No valid slip surface without an earthquake.")
    if f0 <= 1.0:
        return {"ky": 0.0, "f_static": f0, "status": "unstable"}
    x, fx, hist, status = bisect_target(lambda k: pool.fos({"kh": k}), 0.0, hi, 1.0, tol=1e-3)
    if status == "above":                     # still F > 1 at kh = hi
        return {"ky": hi, "f_static": f0, "status": "very stable"}
    return {"ky": float(x), "f_static": f0, "status": "ok", "evaluations": len(hist)}


def assess(pool, amax: float, M: float = 7.0) -> dict:
    """ky, the displacement by every method and the hazard class (by the largest of the methods)."""
    y = yield_kh(pool)
    ky = y["ky"]
    out = {"ky": ky, "amax": amax, "M": M, "f_static": y["f_static"], "status": y["status"], "methods": {}}
    for m in METHODS:
        out["methods"][m] = displacement(ky, amax, M, m)
    worst = max(out["methods"].values())
    out["displacement"] = worst
    out["hazard"], out["hazard_label"] = hazard(worst)
    out["f_pseudo"] = pool.fos({"kh": 0.5 * amax}) if amax > 0 else y["f_static"]
    return out


def code_pga(project) -> tuple[float, str]:
    from . import codes
    s = codes.seismic(codes.code_of(project), codes.settings_of(project))
    return float(s.get("pga") or 0.0), s.get("text", "")


def curve(ky: float, M: float = 7.0, method: str = "jibson07", amax_max: float = 0.8, n: int = 40):
    """Displacement against amax (for a chart)."""
    xs = [ky + (amax_max - ky) * i / (n - 1) for i in range(n)] if ky < amax_max else []
    return [(a, displacement(ky, a, M, method)) for a in xs if a > 0]


def text_report(res: dict, analysis_name: str = "", pga_text: str = "") -> str:
    L = [f"Earthquake check (yield acceleration and Newmark displacement){' - ' + analysis_name if analysis_name else ''}",
         "=" * 72]
    if pga_text:
        L.append(pga_text)
    L.append(f"Static factor of safety:          {res['f_static']:.3f}")
    if res["status"] == "unstable":
        L.append("The slope is not stable without an earthquake (F <= 1): ky = 0, it moves at once.")
        return "\n".join(L)
    L.append(f"Yield acceleration ky:            {res['ky']:.3f} g" + ("  (or more)" if res["status"] == "very stable" else ""))
    L.append(f"Peak ground acceleration amax:    {res['amax']:.3f} g   (magnitude M {res['M']:g})")
    L.append(f"Pseudo-static F at kh = amax/2:   {res['f_pseudo']:.3f}")
    L.append(f"ky / amax:                        {res['ky'] / res['amax']:.3f}" if res["amax"] > 0 else "")
    L.append("")
    L.append("Permanent displacement (median of each regression):")
    for m, d in res["methods"].items():
        L.append(f"  {METHODS[m]:<42} {d:8.1f} cm" if math.isfinite(d) else f"  {METHODS[m]:<42}      inf")
    L.append("")
    L.append(f"Hazard (Jibson and Michael 2009, largest estimate): {res['hazard_label']}")
    L.append("The regressions scatter by a factor of about 3 (one standard deviation). Run a dynamic analysis "
             "(Define > Add Analysis > Dynamic) with a site record for design.")
    return "\n".join(x for x in L if x is not None)
