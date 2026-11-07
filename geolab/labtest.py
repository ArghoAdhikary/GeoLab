"""Strength parameters from laboratory tests: triaxial (CD / CU with pore pressure, or UU) and direct
shear. Fits the Mohr-Coulomb line by least squares.

* Triaxial: one row per specimen with sigma3 (cell pressure) and sigma1 at failure (or the deviator
  q = sigma1 - sigma3), and the pore pressure u at failure for CU tests. With effective stresses,
  the best line through (s', t) = ((s1'+s3')/2, (s1'-s3')/2) gives t = a + s' tan(alpha), so
  phi' = asin(tan alpha) and c' = a / cos phi'.
* Direct shear: one row per specimen with the normal stress and the peak (or residual) shear
  stress. The fitted line is tau = c' + sigma tan phi'.
* UU (undrained): Su = mean of (sigma1 - sigma3) / 2.

The fit also gives R^2. With only two specimens, the line goes through both points exactly.
"""
from __future__ import annotations

import math

import numpy as np


def _fit(x, y, force_c0=False):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2:
        raise ValueError("Enter at least two specimens.")
    if force_c0:
        slope = float((x @ y) / (x @ x))
        icpt = 0.0
    else:
        slope, icpt = np.polyfit(x, y, 1)
    pred = icpt + slope * x
    ss = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - pred) ** 2).sum()) / ss if ss > 0 else 1.0
    return float(slope), float(icpt), r2


def triaxial(rows, effective=True, force_c0=False) -> dict:
    """rows: [{"sigma3", "sigma1" or "q", "u" (optional)}]. Returns c', phi', the circles and R^2."""
    circles = []
    for r in rows:
        s3 = float(r["sigma3"])
        s1 = float(r["sigma1"]) if r.get("sigma1") not in (None, "") else s3 + float(r["q"])
        u = float(r.get("u") or 0.0) if effective else 0.0
        s3e, s1e = s3 - u, s1 - u
        if s1e < s3e:
            raise ValueError("sigma1 must be larger than sigma3.")
        circles.append({"sigma3": s3e, "sigma1": s1e, "centre": (s1e + s3e) / 2, "radius": (s1e - s3e) / 2})
    s = [c["centre"] for c in circles]
    t = [c["radius"] for c in circles]
    tan_a, a, r2 = _fit(s, t, force_c0)
    tan_a = min(max(tan_a, 0.0), 0.999)
    phi = math.degrees(math.asin(tan_a))
    c = a / math.cos(math.radians(phi)) if phi < 90 else 0.0
    return {"c": max(0.0, c), "phi": phi, "r2": r2, "circles": circles, "kind": "triaxial",
            "effective": effective, "a": a, "alpha": math.degrees(math.atan(tan_a))}


def direct_shear(rows, force_c0=False) -> dict:
    """rows: [{"sigma", "tau"}]."""
    x = [float(r["sigma"]) for r in rows]
    y = [float(r["tau"]) for r in rows]
    tanp, c, r2 = _fit(x, y, force_c0)
    return {"c": max(0.0, c), "phi": math.degrees(math.atan(max(0.0, tanp))), "r2": r2,
            "points": list(zip(x, y)), "kind": "direct_shear"}


def unconsolidated_undrained(rows) -> dict:
    su = [0.5 * ((float(r["sigma1"]) if r.get("sigma1") not in (None, "") else float(r["sigma3"]) + float(r["q"]))
                 - float(r["sigma3"])) for r in rows]
    return {"su": float(np.mean(su)), "sd": float(np.std(su, ddof=1)) if len(su) > 1 else 0.0, "values": su,
            "kind": "uu"}


def parse(text: str, kind: str = "triaxial") -> list[dict]:
    """Rows from pasted text: numbers separated by commas, tabs or spaces; a header line is skipped.

    triaxial: sigma3, sigma1 [, u]    direct shear: sigma, tau"""
    rows = []
    for line in text.splitlines():
        parts = [p for p in line.replace(",", " ").replace(";", " ").replace("\t", " ").split() if p]
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            continue
        if kind == "direct_shear" and len(nums) >= 2:
            rows.append({"sigma": nums[0], "tau": nums[1]})
        elif kind != "direct_shear" and len(nums) >= 2:
            rows.append({"sigma3": nums[0], "sigma1": nums[1], "u": nums[2] if len(nums) > 2 else 0.0})
    return rows


def text_report(res: dict) -> str:
    if res["kind"] == "uu":
        return f"Undrained shear strength Su = {res['su']:.1f} kPa (sd {res['sd']:.1f}) from {len(res['values'])} specimens"
    lines = [f"c' = {res['c']:.2f} kPa    phi' = {res['phi']:.2f} deg    R^2 = {res['r2']:.4f}"]
    if res["kind"] == "triaxial":
        lines.append("Specimens (effective stresses):" if res["effective"] else "Specimens (total stresses):")
        for c in res["circles"]:
            lines.append(f"  sigma3 {c['sigma3']:8.1f}  sigma1 {c['sigma1']:8.1f}  s' {c['centre']:8.1f}  t {c['radius']:8.1f}")
    else:
        for s, t in res["points"]:
            lines.append(f"  sigma {s:8.1f}  tau {t:8.1f}")
    return "\n".join(lines)
