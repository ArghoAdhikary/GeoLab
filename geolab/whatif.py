"""Fast re-evaluation of a solved slope: the what-if sliders, back-analysis, the design optimizer and the
design code checks all change a few numbers and ask "what is the factor of safety now?".

A full slip-surface search takes seconds. After one search, the lowest trial surfaces (plus a spread of
others, so that a deeper or shallower surface can take over when the strength changes) are kept in a
SurfacePool. Re-evaluating the pool takes a fraction of a second, and its minimum is the factor of safety
of the changed model to within the search's own resolution. `confirm()` runs the full search again.
"""
from __future__ import annotations

import copy
import math

import numpy as np

# what can be changed (key -> label); material keys look like "m3.cohesion"
CHANGES = {
    "water_dy": "Raise (+) or lower (-) the water table",
    "ru": "Pore-pressure ratio Ru",
    "load_factor": "Multiply the crest loads by",
    "kh": "Horizontal seismic coefficient kh",
    "kv": "Vertical seismic coefficient kv",
    "c_factor": "Multiply every cohesion by",
    "tanphi_factor": "Multiply every tan(phi) by",
    "reinf_length_factor": "Multiply reinforcement lengths by",
    "reinf_capacity_factor": "Multiply reinforcement capacity by",
}
MAT_PROPS = {"cohesion": "c", "phi": "phi", "unit_weight": "unit weight"}


def apply_changes(project, analysis, changes: dict | None):
    """Copies of the project and the analysis with the changes made (the originals are not touched)."""
    p = copy.deepcopy(project)
    a = p.analysis(analysis.id)
    for k, v in (changes or {}).items():
        if v is None:
            continue
        v = float(v)
        if k == "water_dy":
            p.piezometric_line = [[x, y + v] for x, y in p.piezometric_line]
        elif k == "ru":
            a.ru = v
        elif k == "kh":
            a.kh = v
        elif k == "kv":
            a.kv = v
        elif k == "load_factor":
            for s in p.surcharges:
                s.q *= v
            for pl in p.point_loads:
                pl.fx *= v
                pl.fy *= v
        elif k == "c_factor":
            for m in p.materials:
                m.cohesion *= v
                m.cr *= v
                m.c_rate *= v
        elif k == "tanphi_factor":
            for m in p.materials:
                for attr in ("phi", "phi2", "phi_r", "phi_b"):
                    ph = getattr(m, attr)
                    if ph > 0:
                        setattr(m, attr, math.degrees(math.atan(v * math.tan(math.radians(ph)))))
        elif k == "reinf_length_factor":
            for r in p.reinforcements:
                r.x2 = r.x1 + v * (r.x2 - r.x1)
                r.y2 = r.y1 + v * (r.y2 - r.y1)
                r.bond_length *= v
        elif k == "reinf_capacity_factor":
            for r in p.reinforcements:
                r.capacity *= v
                r.bond *= v
        elif k.startswith("m") and "." in k:
            mid, prop = k[1:].split(".", 1)
            m = p.material(int(mid))
            if m is None or prop not in MAT_PROPS:
                raise ValueError(f"Unknown change '{k}'")
            setattr(m, prop, v)
        else:
            raise ValueError(f"Unknown change '{k}'")
    return p, a


def _seep_results(project, analysis):
    from .solver import _ensure, ancestor
    if analysis.pwp != "seepage":
        return None
    seep = ancestor(project, analysis, "seepage")
    if seep is None:
        raise ValueError("This analysis takes pore pressures from a seepage analysis, which is missing.")
    return _ensure(project, seep, None)


def pick_surfaces(results: dict, n: int = 30) -> list:
    """The critical surface, the lowest trials and an even spread of the rest."""
    crit = results.get("critical")
    if not crit:
        raise ValueError("Solve the slope stability analysis first.")
    trials = [t["surface"] for t in results.get("trials", [])]
    out = [crit["surface"]]
    low = max(1, n * 2 // 3)
    out += trials[:low]
    rest = trials[low:]
    if rest:
        k = n - len(out)
        if k > 0:
            idx = np.unique(np.linspace(0, len(rest) - 1, k).round().astype(int))
            out += [rest[i] for i in idx]
    return out


class SurfacePool:
    """Keeps the slip surfaces of one solved slope analysis and re-evaluates them quickly."""

    def __init__(self, project, analysis, n: int = 30, results: dict | None = None):
        if analysis.kind != "slope":
            raise ValueError("Pick a slope stability analysis.")
        if analysis.method == "finite_element":
            raise ValueError("The quick re-evaluation works with the limit equilibrium methods.")
        if getattr(analysis, "rapid_drawdown", False):
            raise ValueError("The quick re-evaluation does not cover the three-stage rapid drawdown method.")
        self.project = project
        self.analysis = analysis
        res = results if results is not None else analysis.results
        if not res or not res.get("critical"):
            from .solver import solve
            res = solve(project, analysis)
        if not res.get("critical"):
            raise ValueError(res.get("message") or "The slope analysis found no valid slip surface.")
        self.base_fos = float(res["critical"]["fos"])
        self.surfaces = pick_surfaces(res, n)
        self.seep = _seep_results(project, analysis)
        self.calls = 0

    def evaluate(self, changes: dict | None = None, project=None, analysis=None):
        """(lowest F, its surface) of the pool with the changes made. F is inf if no surface is valid."""
        from .geometry import GroundProfile
        from .slope import evaluate_surface, make_pwp_fn
        if project is None:
            project, analysis = apply_changes(self.project, self.analysis, changes)
        gp = GroundProfile(project.regions)
        pwp = make_pwp_fn(project, analysis, self.seep)
        best, surf = math.inf, None
        for s in self.surfaces:
            _, F, _, why = evaluate_surface(project, analysis, s, pwp, gp)
            if not why and np.isfinite(F) and F < best:
                best, surf = float(F), s
        self.calls += 1
        return best, surf

    def fos(self, changes: dict | None = None) -> float:
        return self.evaluate(changes)[0]


def confirm(project, analysis, changes: dict | None = None) -> dict:
    """Full slip-surface search with the changes made. Returns the slope results."""
    from .solver import solve
    p, a = apply_changes(project, analysis, changes)
    for x in p.analyses:
        if x.id == a.id:
            x.results = None
    return solve(p, a)


def bisect_target(f, lo: float, hi: float, target: float, tol: float = 1e-3, it: int = 30):
    """x in [lo, hi] where f(x) = target for a monotonic f. Returns (x, f(x), history, status) where status
    is 'ok', 'below' (target not reached anywhere: f stays under it) or 'above' (already met at both ends)."""
    flo, fhi = f(lo), f(hi)
    hist = [(lo, flo), (hi, fhi)]
    if not (np.isfinite(flo) or np.isfinite(fhi)):
        return None, None, hist, "invalid"
    increasing = fhi >= flo
    if max(flo, fhi) < target:
        x = hi if increasing else lo
        return x, max(flo, fhi), hist, "below"
    if min(flo, fhi) >= target:
        x = lo if increasing else hi
        return x, min(flo, fhi), hist, "above"
    # Illinois (modified false position): as safe as bisection, a handful of evaluations when f is smooth
    a, fa, b, fb = lo, flo - target, hi, fhi - target
    side = 0
    x, fx = (lo, flo) if flo >= target else (hi, fhi)     # the end that meets the target
    for _ in range(it):
        m = (a * fb - b * fa) / (fb - fa) if fb != fa else 0.5 * (a + b)
        if not (min(a, b) < m < max(a, b)):
            m = 0.5 * (a + b)
        fm = f(m)
        hist.append((m, fm))
        if not np.isfinite(fm):
            m = 0.5 * (a + b)
            fm = f(m)
            hist.append((m, fm))
        gm = fm - target
        if gm >= 0:
            x, fx = m, fm
        if (gm >= 0) == (fa >= 0):
            a, fa = m, gm
            if side == -1:
                fb *= 0.5
            side = -1
        else:
            b, fb = m, gm
            if side == 1:
                fa *= 0.5
            side = 1
        if abs(b - a) <= tol * max(1.0, abs(m)) or 0 <= gm <= 5e-4 * max(1.0, target):
            break
    return float(x), float(fx), sorted(hist), "ok"
