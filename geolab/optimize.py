"""Design optimizer: "I need F = 1.5 - how flat, how wide a berm, how deep a drain, how long the nails?"

Each design variable changes the model in one direction (F goes up or down steadily with it), so the
smallest change that reaches the target is found by bisection. Variables that only change loads, water or
reinforcement re-use the solved slip surfaces (fast); variables that change the geometry rebuild the
Quick Slope model and search again (slower: about ten searches).
"""
from __future__ import annotations

import copy

from .whatif import SurfacePool, bisect_target, confirm

# key -> (label, unit kind, needs a Quick Slope model, default range)
VARIABLES = {
    "slope_ratio": ("Slope steepness (H:1V, flatter = safer)", "ratio", True, (0.5, 6.0)),
    "berm": ("Berm (bench) width at mid-height", "length", True, (0.0, 15.0)),
    "drain_depth": ("Lower the water table by (drainage)", "length", False, (0.0, 15.0)),
    "reinf_length": ("Reinforcement length (x the present length)", "factor", False, (0.2, 4.0)),
    "reinf_capacity": ("Reinforcement capacity (x the present)", "factor", False, (0.1, 10.0)),
    "max_surcharge": ("Largest crest load that still meets the target", "pressure", False, (0.0, 500.0)),
}


def available(project, analysis) -> dict:
    """The variables that make sense for this model, with the reason when one does not."""
    out = {}
    for k, (label, _, needs_quick, _) in VARIABLES.items():
        why = None
        if needs_quick and not project.quick:
            why = "Only for models made with Quick Slope (File > New Quick Slope)."
        elif k == "drain_depth" and not (analysis.pwp == "piezometric" and project.piezometric_line):
            why = "Needs a piezometric line (pore pressure = Piezometric line)."
        elif k.startswith("reinf") and not project.reinforcements:
            why = "The model has no reinforcement (Draw > Reinforcement)."
        out[k] = why
    return out


def _quick_fos(project, analysis, q: dict, coarse: bool = True) -> tuple[float, object]:
    from .quick import quick_slope
    from .solver import solve
    p = quick_slope(q)
    a = p.analyses[0]
    a.method = analysis.method
    a.kh, a.kv = analysis.kh, analysis.kv
    if coarse:
        a.search.n_entry, a.search.n_exit, a.search.n_radius = 8, 8, 4
    r = solve(p, a)
    return (r["critical"]["fos"] if r.get("critical") else float("inf")), p


def optimize(project, analysis, variable: str, target: float = 1.5, lo: float | None = None,
             hi: float | None = None, progress=None, full_check: bool = True) -> dict:
    """Smallest change of `variable` (largest, for max_surcharge) that gives F >= target."""
    if variable not in VARIABLES:
        raise ValueError(f"Unknown design variable '{variable}'.")
    label, kind, needs_quick, (dlo, dhi) = VARIABLES[variable]
    why = available(project, analysis)[variable]
    if why:
        raise ValueError(why)
    lo = dlo if lo is None else lo
    hi = dhi if hi is None else hi
    if kind == "length" and project.units == "imperial":
        hi *= 3.28
    if kind == "pressure" and project.units == "imperial":
        hi *= 20.9
    steps = []

    if needs_quick:
        base = dict(project.quick)
        q_key = "ratio" if variable == "slope_ratio" else "berm"
        if variable == "berm":
            base.setdefault("berm_at", 0.5)

        def f(x):
            q = dict(base, **{q_key: float(x)})
            F, _ = _quick_fos(project, analysis, q)
            steps.append((x, F))
            if progress:
                progress(min(95, 8 * len(steps)))
            return F
        x, F, hist, status = bisect_target(f, lo, hi, target, tol=0.01, it=9)
        out = {"variable": variable, "label": label, "target": target, "value": x, "fos": F, "status": status,
               "history": hist}
        if x is not None and full_check:
            Ff, p = _quick_fos(project, analysis, dict(base, **{q_key: float(x)}), coarse=False)
            out["full_search_fos"] = Ff
            out["project"] = p
        out["message"] = message(out, project)
        return out

    pool = SurfacePool(project, analysis)
    surcharge0 = sum(s.q for s in project.surcharges)

    def changes(x):
        if variable == "drain_depth":
            return {"water_dy": -x}
        if variable == "reinf_length":
            return {"reinf_length_factor": x}
        if variable == "reinf_capacity":
            return {"reinf_capacity_factor": x}
        return {}

    if variable == "max_surcharge":
        work = copy.deepcopy(project)
        wa = work.analysis(analysis.id)
        if not work.surcharges:
            from .geometry import auto_entry_exit
            from .model import Surcharge
            (e1, e2), _ = auto_entry_exit(work)
            work.surcharges.append(Surcharge(min(e1, e2), max(e1, e2), 0.0))
        shares = [s.q / surcharge0 if surcharge0 > 0 else 1.0 / len(work.surcharges) for s in work.surcharges]

        def f(x):
            p2 = copy.deepcopy(work)
            for s, w in zip(p2.surcharges, shares):
                s.q = float(x) * w
            F = pool.evaluate(project=p2, analysis=p2.analysis(wa.id))[0]
            steps.append((x, F))
            return F
    else:
        def f(x):
            F = pool.fos(changes(x))
            steps.append((x, F))
            return F
    x, F, hist, status = bisect_target(f, lo, hi, target, tol=1e-3)
    out = {"variable": variable, "label": label, "target": target, "value": x, "fos": F, "status": status,
           "history": hist, "base_fos": pool.base_fos}
    if x is not None and full_check and variable != "max_surcharge":
        r = confirm(project, analysis, changes(x))
        out["full_search_fos"] = r["critical"]["fos"] if r.get("critical") else None
    out["message"] = message(out, project)
    return out


def apply(project, analysis, result: dict):
    """Make the optimized change in the project (in place) and return a description, or a new project
    for the geometry variables (result['project'])."""
    v, x = result["variable"], result["value"]
    if x is None:
        raise ValueError("Nothing to apply.")
    if v == "drain_depth":
        project.piezometric_line = [[a, b - x] for a, b in project.piezometric_line]
    elif v == "reinf_length":
        for r in project.reinforcements:
            r.x2 = r.x1 + x * (r.x2 - r.x1)
            r.y2 = r.y1 + x * (r.y2 - r.y1)
            r.bond_length *= x
    elif v == "reinf_capacity":
        for r in project.reinforcements:
            r.capacity *= x
            r.bond *= x
    elif v == "max_surcharge":
        if not project.surcharges:
            from .geometry import auto_entry_exit
            from .model import Surcharge
            (e1, e2), _ = auto_entry_exit(project)
            project.surcharges.append(Surcharge(min(e1, e2), max(e1, e2), 0.0))
        tot = sum(s.q for s in project.surcharges)
        for s in project.surcharges:
            s.q = x * (s.q / tot if tot > 0 else 1.0 / len(project.surcharges))
    project.clear_results()
    return f"{VARIABLES[v][0]}: {x:.3g}"


def message(o, project) -> str:
    u = {"ratio": "H:1V", "length": project.unit("length"), "factor": "x", "pressure": project.unit("pressure")}
    unit = u[VARIABLES[o["variable"]][1]]
    t = o["target"]
    if o["status"] == "ok":
        s = {"slope_ratio": f"A slope of {o['value']:.2f}H:1V gives F = {o['fos']:.3f}",
             "berm": f"A berm {o['value']:.2f} {unit} wide gives F = {o['fos']:.3f}",
             "drain_depth": f"Lowering the water table by {o['value']:.2f} {unit} gives F = {o['fos']:.3f}",
             "reinf_length": f"Reinforcement {o['value']:.2f} x as long gives F = {o['fos']:.3f}",
             "reinf_capacity": f"Reinforcement {o['value']:.2f} x as strong gives F = {o['fos']:.3f}",
             "max_surcharge": f"The crest can carry {o['value']:.1f} {unit} in total with F = {o['fos']:.3f}",
             }[o["variable"]]
        s += f" (target {t:g})."
        if o.get("full_search_fos") is not None:
            s += f" Checked with a full slip-surface search: F = {o['full_search_fos']:.3f}."
        return s
    if o["status"] == "above":
        return f"The target F = {t:g} is already met at the low end of the range ({o['value']:.3g} {unit})."
    if o["status"] == "below":
        return (f"F = {t:g} cannot be reached in the range: the best is F = {o['fos']:.3f} at "
                f"{o['value']:.3g} {unit}. Try another measure or a wider range.")
    return "No valid slip surface in the range."
