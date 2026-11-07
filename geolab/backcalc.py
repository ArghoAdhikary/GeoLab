"""Back-analysis: work backwards from what was observed to the soil parameters.

* Strength from a failure: a slope that failed had F = 1 at the time. Find the cohesion, friction angle or
  unit weight that gives F = 1 (or any target), and the whole line of (c, phi) pairs that do.
* Hydraulic conductivity from piezometers: find the k of chosen materials that makes the computed heads
  match measured ones (least squares on log10 k).
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .whatif import SurfacePool, bisect_target, confirm

PROP_RANGES = {"cohesion": (0.0, 200.0), "phi": (0.0, 50.0), "unit_weight": (10.0, 26.0)}


def back_strength(project, analysis, material_id: int, prop: str = "cohesion", target: float = 1.0,
                  lo: float | None = None, hi: float | None = None, pool: SurfacePool | None = None,
                  full_check: bool = False) -> dict:
    """Value of one property of one material that gives the target factor of safety."""
    if prop not in PROP_RANGES:
        raise ValueError(f"Back-analysis works on {', '.join(PROP_RANGES)}, not '{prop}'.")
    m = project.material(material_id)
    if m is None:
        raise ValueError(f"Material {material_id} does not exist.")
    pool = pool or SurfacePool(project, analysis)
    rlo, rhi = PROP_RANGES[prop]
    if project.units == "imperial" and prop == "cohesion":
        rhi = 4000.0
    if project.units == "imperial" and prop == "unit_weight":
        rlo, rhi = 60.0, 165.0
    lo = rlo if lo is None else lo
    hi = rhi if hi is None else hi
    key = f"m{material_id}.{prop}"
    x, F, hist, status = bisect_target(lambda v: pool.fos({key: v}), lo, hi, target, tol=1e-4)
    out = {"material": m.name, "material_id": material_id, "prop": prop, "target": target,
           "value": x, "fos": F, "status": status, "current": getattr(m, prop), "base_fos": pool.base_fos,
           "history": hist, "evaluations": pool.calls}
    if status == "ok" and full_check:
        r = confirm(project, analysis, {key: x})
        out["full_search_fos"] = r["critical"]["fos"] if r.get("critical") else None
    out["message"] = _strength_message(out, project)
    return out


def _strength_message(o, project):
    unit = {"cohesion": project.unit("pressure"), "phi": "°", "unit_weight": project.unit("unit_weight")}[o["prop"]]
    name = {"cohesion": "c", "phi": "phi", "unit_weight": "unit weight"}[o["prop"]]
    if o["status"] == "ok":
        s = f"{name} of '{o['material']}' = {o['value']:.3g} {unit} gives F = {o['fos']:.3f}"
        s += f" (now {o['current']:.3g} {unit}, F = {o['base_fos']:.3f})."
        if o.get("full_search_fos") is not None:
            s += f" A full slip-surface search with that value gives F = {o['full_search_fos']:.3f}."
        return s
    if o["status"] == "below":
        return f"F stays below {o['target']:g} over the whole range of {name}: other parameters control."
    if o["status"] == "above":
        return f"F is above {o['target']:g} over the whole range of {name}: other parameters control."
    return "No valid slip surface over the range."


def c_phi_line(project, analysis, material_id: int, target: float = 1.0, phis=None,
               pool: SurfacePool | None = None) -> dict:
    """For each friction angle, the cohesion that gives the target F: the line of (c, phi) pairs that all
    explain the observed failure. One more observation (a lab test, a second section) picks the point."""
    m = project.material(material_id)
    if m is None:
        raise ValueError(f"Material {material_id} does not exist.")
    pool = pool or SurfacePool(project, analysis)
    if phis is None:
        phis = np.linspace(max(0.0, m.phi - 12), m.phi + 8, 9)
    chi = 4000.0 if project.units == "imperial" else 200.0
    rows = []
    for ph in phis:
        f = lambda c, ph=ph: pool.fos({f"m{material_id}.phi": float(ph), f"m{material_id}.cohesion": c})
        c, F, _, status = bisect_target(f, 0.0, chi, target, tol=1e-4)
        rows.append({"phi": float(ph), "c": c if status == "ok" else (0.0 if status == "above" else None),
                     "fos": F, "status": status})
    return {"material": m.name, "target": target, "rows": rows}


# ---------------------------------------------------------------------------------------------- seepage
def head_at(results: dict, pts, time: float | None = None):
    """Total head of a seepage result at points (at a time, for transient results)."""
    from .fe import interpolator
    h = results["head"]
    if time is not None and results.get("times"):
        ts = np.asarray(results["times"])
        hh = np.asarray(results["head_history"])
        i = int(np.searchsorted(ts, time))
        if i <= 0:
            h = hh[0]
        elif i >= len(ts):
            h = hh[-1]
        else:
            w = (time - ts[i - 1]) / max(ts[i] - ts[i - 1], 1e-30)
            h = (1 - w) * hh[i - 1] + w * hh[i]
    f = interpolator(results["nodes"], h)
    pts = np.asarray(pts, float).reshape(-1, 2)
    return f(pts[:, 0], pts[:, 1])


def calibrate_k(project, analysis, observations: list, material_ids: list, max_evals: int = 60,
                progress=None) -> dict:
    """Hydraulic conductivity of the chosen materials that best matches the measured heads.

    observations: [{"x", "y", "head", "time" (optional)}]. Steady heads only depend on the ratios of k
    between materials, so with only head boundaries keep one material out (its k is the reference)."""
    from scipy.optimize import minimize

    from .seep import run_seepage
    if analysis.kind != "seepage":
        raise ValueError("Pick a seepage analysis to calibrate.")
    if not observations:
        raise ValueError("Enter at least one measured head.")
    if not material_ids:
        raise ValueError("Choose the materials whose conductivity is unknown.")
    pts = np.array([[o["x"], o["y"]] for o in observations], float)
    meas = np.array([o["head"] for o in observations], float)
    times = [o.get("time") for o in observations]
    work = copy.deepcopy(project)
    wa = work.analysis(analysis.id)
    parent = work.analysis(wa.parent_id)
    pres = None
    if parent is not None and parent.kind == "seepage":
        from .solver import _ensure
        pres = _ensure(work, parent, None)
    k0 = np.log10([work.material(i).k_sat for i in material_ids])
    seen = {}

    def misfit(logk):
        key = tuple(np.round(logk, 4))
        if key in seen:
            return seen[key][0]
        for i, lk in zip(material_ids, logk):
            work.material(i).k_sat = float(10 ** lk)
        try:
            r = run_seepage(work, wa, None, None, parent_results=pres)
        except Exception:                                # noqa: BLE001  (a bad trial is just a bad fit)
            seen[key] = (1e9, None)
            return 1e9
        calc = np.array([head_at(r, pts[j], times[j])[0] for j in range(len(pts))])
        e = float(np.sqrt(np.mean((calc - meas) ** 2)))
        seen[key] = (e, calc)
        if progress:
            progress(min(99, int(100 * len(seen) / max_evals)))
        return e

    e0 = misfit(k0)
    opt = minimize(misfit, k0, method="Nelder-Mead",
                   options={"maxfev": max_evals, "xatol": 0.01, "fatol": 1e-4,
                            "initial_simplex": np.vstack([k0] + [k0 + 0.5 * np.eye(len(k0))[j]
                                                                for j in range(len(k0))])})
    best = min(seen.items(), key=lambda kv: kv[1][0])
    logk = np.array(best[0])
    e, calc = best[1]
    return {
        "materials": [{"id": i, "name": project.material(i).name, "k_before": float(10 ** a),
                       "k_after": float(10 ** b)} for i, a, b in zip(material_ids, k0, logk)],
        "rms_before": e0, "rms_after": e, "evaluations": len(seen), "converged": bool(opt.success),
        "points": [{"x": float(p[0]), "y": float(p[1]), "measured": float(mv),
                    "computed": None if calc is None else float(c)}
                   for p, mv, c in zip(pts, meas, calc if calc is not None else [None] * len(meas))],
    }


def apply_k(project, result: dict):
    for row in result["materials"]:
        project.material(row["id"]).k_sat = row["k_after"]


def nice(v):
    return "-" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.4g}"
