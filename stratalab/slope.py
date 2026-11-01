"""Limit-equilibrium slope stability (method of slices).

Methods: Ordinary (Fellenius), Bishop Simplified, Janbu Simplified (uncorrected),
Spencer and Morgenstern-Price, the last two solved with the General Limit
Equilibrium (GLE) formulation of Fredlund & Krahn (1977).

Sign convention used internally: slice data is mirrored when necessary so the
sliding mass always moves towards -x. A slice base angle alpha is positive when
the base rises to the right. Interslice normal force E is positive in
compression and interslice shear X = lambda * f(x) * E.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .geometry import GroundProfile, point_in_polygon, polyline_y, vertical_intervals

M_ALPHA_MIN = 0.2


# ---------------------------------------------------------------------------
# Slip surfaces
# ---------------------------------------------------------------------------
def circle_surface(xc, yc, R) -> dict:
    return {"type": "circle", "xc": float(xc), "yc": float(yc), "R": float(R)}


def polyline_surface(points) -> dict:
    return {"type": "polyline", "points": [[float(x), float(y)] for x, y in points]}


def _surface_fn(surface):
    if surface["type"] == "circle":
        xc, yc, R = surface["xc"], surface["yc"], surface["R"]

        def ys(x):
            x = np.asarray(x, dtype=float)
            d = np.clip(R * R - (x - xc) ** 2, 0.0, None)
            return yc - np.sqrt(d)

        return ys, xc - R, xc + R
    pts = sorted(surface["points"], key=lambda p: p[0])
    xs = np.array([p[0] for p in pts])
    yv = np.array([p[1] for p in pts])
    return (lambda x: np.interp(x, xs, yv)), xs[0], xs[-1]


def _alpha(surface, x, ys):
    if surface["type"] == "circle":
        s = np.clip((x - surface["xc"]) / surface["R"], -0.999999, 0.999999)
        return np.arcsin(s)
    h = 1e-6 * max(1.0, abs(x).max())
    return np.arctan((ys(x + h) - ys(x - h)) / (2 * h))


def find_extent(gp: GroundProfile, surface, samples=600):
    """x-range where the slip surface lies below the ground. None if the surface is invalid."""
    ys, x0, x1 = _surface_fn(surface)
    lo, hi = max(x0, gp.xmin), min(x1, gp.xmax)
    if hi - lo <= 0:
        return None
    xs = np.linspace(lo, hi, samples)
    d = gp.ground(xs) - ys(xs)
    tol = 1e-9 * max(1.0, gp.ymax - gp.ymin)
    inside = d > tol
    if not inside.any():
        return None
    # contiguous runs of points below ground; keep the one with the largest area
    best, best_area = None, 0.0
    i = 0
    n = len(xs)
    while i < n:
        if inside[i]:
            j = i
            while j + 1 < n and inside[j + 1]:
                j += 1
            area = d[i:j + 1].sum()
            if area > best_area:
                best, best_area = (i, j), area
            i = j + 1
        else:
            i += 1
    i, j = best
    if i == 0 or j == n - 1:
        return None  # surface leaves the model through a side (or wraps over the top)

    def refine(a, b):  # d(a) <= 0 < d(b) or reverse; bisect for d = 0
        fa = gp.ground(a) - ys(a)
        for _ in range(40):
            m = 0.5 * (a + b)
            fm = gp.ground(m) - ys(m)
            if (fm > tol) == (fa > tol):
                a, fa = m, fm
            else:
                b = m
        return 0.5 * (a + b)

    xl = refine(xs[i - 1], xs[i])
    xr = refine(xs[j + 1], xs[j])
    return xl, xr, float(d[i:j + 1].max())


# ---------------------------------------------------------------------------
# Slices
# ---------------------------------------------------------------------------
@dataclass
class SliceSet:
    xm: np.ndarray        # mirrored x of slice mid
    xb: np.ndarray        # mirrored x of slice boundaries (n+1)
    b: np.ndarray
    yb: np.ndarray
    ytop: np.ndarray
    alpha: np.ndarray
    l: np.ndarray
    W: np.ndarray         # total vertical load (soil + surcharge + point loads)
    Wsoil: np.ndarray
    Wext: np.ndarray
    yg: np.ndarray
    c: np.ndarray
    tanphi: np.ndarray
    u: np.ndarray
    H: np.ndarray         # horizontal force (direction of motion)
    MH: np.ndarray        # moment of horizontal forces about the axis
    ax: float             # mirrored axis
    ay: float
    base_mat: np.ndarray
    area: np.ndarray      # n x nmat area of each material in each slice
    mat_ids: list
    mirrored: bool
    surface: dict
    kh: float
    pwp_mode: str
    ru: float
    hfx: np.ndarray       # horizontal point loads per slice
    gamma_w: float
    hp: np.ndarray        # pressure head at base (before clipping)

    @property
    def n(self):
        return len(self.xm)


def build_slices(project, analysis, surface, pwp_fn=None, gp: GroundProfile | None = None,
                 n_slices=None):
    """Discretize the sliding mass. Returns (SliceSet, None) or (None, reason)."""
    gp = gp or GroundProfile(project.regions)
    ext = find_extent(gp, surface)
    if ext is None:
        return None, "Slip surface does not cut the ground surface inside the model."
    xl, xr, depth = ext
    if depth < analysis.search.min_depth:
        return None, "Slip surface is shallower than the minimum depth."
    n = int(n_slices or analysis.n_slices)
    ys, _, _ = _surface_fn(surface)
    xb = np.linspace(xl, xr, n + 1)
    xm = 0.5 * (xb[:-1] + xb[1:])
    b = np.diff(xb)
    yb = ys(xm)
    ytop = gp.ground(xm)
    alpha = _alpha(surface, xm, ys)
    mats = {m.id: m for m in project.materials}
    mat_ids = [m.id for m in project.materials]
    midx = {mid: k for k, mid in enumerate(mat_ids)}
    area = np.zeros((n, len(mat_ids)))
    ycent = np.zeros(n)
    base_mat = np.full(n, -1)
    H = gp.ymax - gp.ymin
    for i in range(n):
        x = xm[i]
        mom = 0.0
        tot = 0.0
        for r in project.regions:
            if r.material_id not in midx:
                continue
            for lo, hi in vertical_intervals(r.points, x):
                lo2, hi2 = max(lo, yb[i]), min(hi, ytop[i])
                if hi2 > lo2:
                    a = (hi2 - lo2) * b[i]
                    area[i, midx[r.material_id]] += a
                    mom += a * 0.5 * (lo2 + hi2)
                    tot += a
        ycent[i] = mom / tot if tot > 0 else 0.5 * (yb[i] + ytop[i])
        yq = yb[i] + 1e-6 * max(H, 1.0)
        for r in project.regions:
            if r.material_id in midx and point_in_polygon(x, yq, r.points):
                base_mat[i] = midx[r.material_id]
                break
        if base_mat[i] < 0:
            return None, "Slip surface passes below the model."
        if mats[mat_ids[base_mat[i]]].model == "bedrock":
            return None, "Slip surface enters an impenetrable (bedrock) material."
    gam = np.array([mats[mid].unit_weight for mid in mat_ids])
    Wsoil = area @ gam
    Wext = np.zeros(n)
    for s in project.surcharges:
        a, c_ = min(s.x1, s.x2), max(s.x1, s.x2)
        ov = np.clip(np.minimum(xb[1:], c_) - np.maximum(xb[:-1], a), 0, None)
        Wext += s.q * ov
    hfx = np.zeros(n)
    for pl in project.point_loads:
        k = np.searchsorted(xb, pl.x) - 1
        if 0 <= k < n:
            Wext[k] += pl.fy
            hfx[k] += pl.fx
    hp = np.zeros(n)
    if analysis.pwp in ("piezometric", "seepage") and pwp_fn is not None:
        hp = np.nan_to_num(np.asarray(pwp_fn(xm, yb), dtype=float), nan=0.0)
    if surface["type"] == "circle":
        ax, ay = surface["xc"], surface["yc"]
    else:
        ax, ay = 0.5 * (xl + xr), float(ytop.max()) + 0.5 * (xr - xl)
    ss = SliceSet(xm=xm, xb=xb, b=b, yb=yb, ytop=ytop, alpha=alpha, l=b / np.cos(alpha),
                  W=Wsoil + Wext, Wsoil=Wsoil, Wext=Wext, yg=ycent, c=np.zeros(n), tanphi=np.zeros(n),
                  u=np.zeros(n), H=np.zeros(n), MH=np.zeros(n), ax=ax, ay=ay, base_mat=base_mat,
                  area=area, mat_ids=mat_ids, mirrored=False, surface=surface, kh=analysis.kh,
                  pwp_mode=analysis.pwp, ru=analysis.ru, hfx=hfx, gamma_w=project.gamma_w, hp=hp)
    # orient so the mass moves towards -x
    if np.sum(ss.W * np.sin(ss.alpha)) < 0:
        ss = _mirror(ss)
    set_strength(ss, project.materials)
    return ss, None


def _mirror(s: SliceSet) -> SliceSet:
    r = lambda a: a[::-1].copy()
    s.xm, s.xb = -r(s.xm), -r(s.xb)
    for name in ("b", "yb", "ytop", "l", "W", "Wsoil", "Wext", "yg", "base_mat", "hfx", "hp"):
        setattr(s, name, r(getattr(s, name)))
    s.alpha = -r(s.alpha)
    s.area = s.area[::-1].copy()
    s.ax = -s.ax
    s.mirrored = True
    return s


def set_strength(s: SliceSet, materials, gamma=None, coh=None, phi=None):
    """(Re)compute weights, strength and pore pressure, optionally with sampled properties."""
    mats = {m.id: m for m in materials}
    ml = [mats[mid] for mid in s.mat_ids]
    g = np.array([m.unit_weight for m in ml]) if gamma is None else gamma
    c = np.array([m.cohesion for m in ml]) if coh is None else coh
    p = np.array([m.phi for m in ml]) if phi is None else phi
    undrained = np.array([m.model == "undrained" for m in ml])
    s.Wsoil = s.area @ g
    s.W = s.Wsoil + s.Wext
    bm = s.base_mat
    s.c = c[bm].astype(float)
    s.tanphi = np.where(undrained[bm], 0.0, np.tan(np.radians(p[bm])))
    if s.pwp_mode == "ru":
        s.u = s.ru * s.Wsoil / s.b
    elif s.pwp_mode in ("piezometric", "seepage"):
        s.u = s.gamma_w * np.clip(s.hp, 0.0, None)
    else:
        s.u = np.zeros(s.n)
    s.u = np.where(undrained[bm], 0.0, s.u)
    Hs = s.kh * s.Wsoil
    s.H = Hs + s.hfx
    s.MH = Hs * (s.yg - s.ay) + s.hfx * (s.ytop - s.ay)


# ---------------------------------------------------------------------------
# Factor of safety
# ---------------------------------------------------------------------------
def _terms(s: SliceSet):
    dx, dyb = s.xm - s.ax, s.yb - s.ay
    ca, sa = np.cos(s.alpha), np.sin(s.alpha)
    armN = dx * ca + dyb * sa
    armS = dx * sa - dyb * ca
    MW = -s.W * dx
    return ca, sa, armN, armS, MW


def _normal(s, F, dX, ca, sa):
    ma = ca + sa * s.tanphi / F
    ma = np.maximum(ma, M_ALPHA_MIN)
    return (s.W + dX - (s.c * s.l * sa - s.u * s.l * s.tanphi * sa) / F) / ma


def _strength(s, N):
    return s.c * s.l + np.clip(N - s.u * s.l, 0.0, None) * s.tanphi


def _fm(s, N, S1, armN, armS, MW):
    den = -np.sum(MW + s.MH + N * armN)
    return np.sum(S1 * armS) / den if den > 0 else math.nan


def _ff(s, N, S1, ca, sa):
    den = np.sum(N * sa + s.H)
    return np.sum(S1 * ca) / den if den > 0 else math.nan


def fos_ordinary(s: SliceSet):
    ca, sa, armN, armS, MW = _terms(s)
    N = s.W * ca - s.H * sa
    return _fm(s, N, _strength(s, N), armN, armS, MW)


def _iterate(fun, F0, tol=1e-6, it=200):
    F = F0
    for _ in range(it):
        Fn = fun(F)
        if not np.isfinite(Fn) or Fn <= 0:
            return math.nan
        if abs(Fn - F) < tol:
            return Fn
        F = Fn
    return math.nan


def fos_bishop(s: SliceSet, F0=1.0):
    ca, sa, armN, armS, MW = _terms(s)
    zero = np.zeros(s.n)

    def step(F):
        N = _normal(s, F, zero, ca, sa)
        return _fm(s, N, _strength(s, N), armN, armS, MW)
    F0 = fos_ordinary(s) if not np.isfinite(F0) else F0
    return _iterate(step, F0 if np.isfinite(F0) and F0 > 0 else 1.0)


def fos_janbu(s: SliceSet, F0=1.0):
    ca, sa, _, _, _ = _terms(s)
    zero = np.zeros(s.n)

    def step(F):
        N = _normal(s, F, zero, ca, sa)
        return _ff(s, N, _strength(s, N), ca, sa)
    return _iterate(step, F0)


def _interslice_f(s: SliceSet, kind):
    if kind == "constant":
        return np.ones(s.n + 1)
    t = (s.xb - s.xb[0]) / (s.xb[-1] - s.xb[0])
    return np.sin(np.pi * t)


def _gle_solve(s, lam, fx, eq, F0, tol=1e-6, it=300):
    """Factor of safety from moment (eq='m') or force (eq='f') equilibrium for a given lambda."""
    ca, sa, armN, armS, MW = _terms(s)
    X = np.zeros(s.n + 1)
    F = F0
    for _ in range(it):
        dX = X[1:] - X[:-1]
        N = _normal(s, F, dX, ca, sa)
        S1 = _strength(s, N)
        Fn = _fm(s, N, S1, armN, armS, MW) if eq == "m" else _ff(s, N, S1, ca, sa)
        if not np.isfinite(Fn) or Fn <= 0:
            return math.nan, None, None
        dE = -N * sa + (S1 / Fn) * ca - s.H
        E = np.concatenate(([0.0], np.cumsum(dE)))
        Xn = lam * fx * E
        Xn[0] = Xn[-1] = 0.0
        Xn = 0.5 * (X + Xn)  # under-relaxation for robustness
        if abs(Fn - F) < tol and np.max(np.abs(Xn - X)) < 1e-6 * max(1.0, np.max(np.abs(s.W))):
            return Fn, N, E
        F, X = Fn, Xn
    return math.nan, None, None


def fos_gle(s: SliceSet, interslice="half_sine", F0=None):
    """Spencer (interslice='constant') or Morgenstern-Price (any other interslice function)."""
    fx = _interslice_f(s, interslice)
    if F0 is None or not np.isfinite(F0):
        F0 = fos_bishop(s)
        if not np.isfinite(F0):
            F0 = 1.0
    cache = {}

    def g(lam):
        if lam not in cache:
            fm, _, _ = _gle_solve(s, lam, fx, "m", F0)
            ff, _, _ = _gle_solve(s, lam, fx, "f", F0)
            cache[lam] = (fm, ff)
        fm, ff = cache[lam]
        return fm - ff, fm, ff

    # secant iteration on lambda, then a bracketing scan as fallback
    l0, l1 = 0.0, 0.3
    g0, g1 = g(l0)[0], g(l1)[0]
    for _ in range(30):
        if not (np.isfinite(g0) and np.isfinite(g1)) or g1 == g0:
            break
        l2 = l1 - g1 * (l1 - l0) / (g1 - g0)
        if abs(l2) > 3:
            break
        l0, g0 = l1, g1
        l1 = l2
        g1, fm, ff = g(l1)
        if np.isfinite(g1) and abs(g1) < 1e-5:
            return 0.5 * (fm + ff), l1
    lams = np.linspace(-1.0, 2.0, 31)
    vals = [g(float(x))[0] for x in lams]
    roots = []
    for k in range(len(lams) - 1):
        a, b = vals[k], vals[k + 1]
        if np.isfinite(a) and np.isfinite(b) and a * b <= 0:
            roots.append((lams[k], lams[k + 1], a))
    if not roots:
        return math.nan, math.nan
    a, b, ga = min(roots, key=lambda r: abs(0.5 * (r[0] + r[1])))
    a, b = float(a), float(b)
    for _ in range(40):
        m = 0.5 * (a + b)
        gm = g(m)[0]
        if not np.isfinite(gm):
            return math.nan, math.nan
        if (gm > 0) == (ga > 0):
            a, ga = m, gm
        else:
            b = m
        if b - a < 1e-6:
            break
    _, fm, ff = g(0.5 * (a + b))
    return 0.5 * (fm + ff), 0.5 * (a + b)


def factor_of_safety(s: SliceSet, method: str, interslice="half_sine"):
    """Return (F, lambda). lambda is nan for methods without interslice shear."""
    if method == "ordinary":
        return fos_ordinary(s), math.nan
    if method == "bishop":
        return fos_bishop(s), math.nan
    if method == "janbu":
        return fos_janbu(s, F0=max(fos_ordinary(s), 0.1) if np.isfinite(fos_ordinary(s)) else 1.0), math.nan
    if method == "spencer":
        return fos_gle(s, "constant")
    if method == "morgenstern_price":
        return fos_gle(s, interslice)
    raise ValueError(f"Unknown method {method}")


def slice_table(s: SliceSet, F: float, lam: float, method: str, interslice="half_sine"):
    """Per-slice forces for reporting, in the original (unmirrored) coordinates."""
    ca, sa, *_ = _terms(s)
    X = np.zeros(s.n + 1)
    E = np.zeros(s.n + 1)
    if method in ("spencer", "morgenstern_price") and np.isfinite(lam):
        fx = _interslice_f(s, "constant" if method == "spencer" else interslice)
        _, N, E = _gle_solve(s, lam, fx, "m", F)
        if N is None:
            N = _normal(s, F, np.zeros(s.n), ca, sa)
            E = np.zeros(s.n + 1)
        X = lam * fx * E
    elif method == "ordinary":
        N = s.W * ca - s.H * sa
    else:
        N = _normal(s, F, np.zeros(s.n), ca, sa)
    S1 = _strength(s, N)
    rows = []
    order = range(s.n - 1, -1, -1) if s.mirrored else range(s.n)
    sign = -1 if s.mirrored else 1
    for k, i in enumerate(order):
        rows.append({
            "slice": k + 1, "x": float(sign * s.xm[i]), "width": float(s.b[i]), "base_y": float(s.yb[i]),
            "alpha_deg": float(math.degrees(sign * s.alpha[i])), "base_length": float(s.l[i]),
            "weight": float(s.W[i]), "pore_pressure": float(s.u[i]), "cohesion": float(s.c[i]),
            "phi_deg": float(math.degrees(math.atan(s.tanphi[i]))), "normal": float(N[i]),
            "shear_mobilized": float(S1[i] / F) if F and np.isfinite(F) else math.nan,
            "shear_strength": float(S1[i]),
            "E_left": float(E[i]), "X_left": float(X[i]),
        })
    return rows


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def candidate_surfaces(project, analysis, gp: GroundProfile):
    st = analysis.search
    out = []
    if st.mode == "grid_radius":
        xs = np.linspace(min(st.grid_x1, st.grid_x2), max(st.grid_x1, st.grid_x2), max(1, st.grid_nx))
        ys = np.linspace(min(st.grid_y1, st.grid_y2), max(st.grid_y1, st.grid_y2), max(1, st.grid_ny))
        rs = np.linspace(st.radius_min, st.radius_max, max(1, st.n_radii))
        for x in xs:
            for y in ys:
                for r in rs:
                    if r > 0:
                        out.append(circle_surface(x, y, r))
    elif st.mode == "entry_exit":
        ex = np.linspace(st.entry_x1, st.entry_x2, max(1, st.n_entry))
        xx = np.linspace(st.exit_x1, st.exit_x2, max(1, st.n_exit))
        thetas = np.radians(np.linspace(12.0, 75.0, max(1, st.n_radius)))
        for a in ex:
            p1 = np.array([a, float(gp.ground(a))])
            for c in xx:
                p2 = np.array([c, float(gp.ground(c))])
                chord = p2 - p1
                L = float(np.hypot(*chord))
                if L < 1e-6:
                    continue
                mid = 0.5 * (p1 + p2)
                nrm = np.array([-chord[1], chord[0]]) / L
                if nrm[1] < 0:
                    nrm = -nrm
                for th in thetas:
                    R = 0.5 * L / math.sin(th)
                    d = math.sqrt(max(R * R - 0.25 * L * L, 0.0))
                    cx, cy = mid + nrm * d
                    out.append(circle_surface(cx, cy, R))
    else:
        for c in st.circles:
            out.append(circle_surface(*c[:3]))
        for pl in st.polylines:
            if len(pl) >= 2:
                out.append(polyline_surface(pl))
    return out


def make_pwp_fn(project, analysis, seep_results=None):
    if analysis.pwp == "piezometric" and len(project.piezometric_line) >= 2:
        line = project.piezometric_line
        return lambda x, y: polyline_y(line, x) - y
    if analysis.pwp == "seepage" and seep_results:
        from .seep import pressure_head_interpolator
        return pressure_head_interpolator(seep_results)
    return None


def evaluate_surface(project, analysis, surface, pwp_fn, gp, method=None):
    s, why = build_slices(project, analysis, surface, pwp_fn, gp)
    if s is None:
        return None, math.nan, math.nan, why
    F, lam = factor_of_safety(s, method or analysis.method, analysis.interslice)
    return s, F, lam, None


def run_slope(project, analysis, seep_results=None, progress=None, cancel=None) -> dict:
    """Run the search and post-processing for a slope analysis. Returns a results dict."""
    from .geometry import validate_geometry
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if analysis.pwp == "seepage" and not seep_results:
        raise ValueError("Pore-water pressure is set to 'From seepage analysis' but the parent seepage "
                         "analysis has no results. Solve the parent analysis first.")
    if analysis.pwp == "piezometric" and len(project.piezometric_line) < 2:
        raise ValueError("Pore-water pressure is set to 'Piezometric line' but no line is drawn.")
    gp = GroundProfile(project.regions)
    pwp_fn = make_pwp_fn(project, analysis, seep_results)
    surfaces = candidate_surfaces(project, analysis, gp)
    if not surfaces:
        raise ValueError("The slip surface search produced no trial surfaces. Check the search settings.")
    trials = []
    best = None
    reasons: dict[str, int] = {}
    for k, surf in enumerate(surfaces):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        s, F, lam, why = evaluate_surface(project, analysis, surf, pwp_fn, gp)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
        elif np.isfinite(F):
            trials.append((float(F), surf))
            if best is None or F < best[0]:
                best = (float(F), surf, lam, s)
        else:
            reasons["Solution did not converge."] = reasons.get("Solution did not converge.", 0) + 1
        if progress and k % 20 == 0:
            progress(int(100 * (k + 1) / len(surfaces)))
    res = {"type": "slope", "method": analysis.method, "n_total": len(surfaces), "n_valid": len(trials),
           "invalid_reasons": reasons, "critical": None, "trials": []}
    if best is None:
        res["message"] = "No valid slip surface found. " + "; ".join(f"{v} x {k}" for k, v in reasons.items())
        return res
    F, surf, lam, s = best
    trials.sort(key=lambda t: t[0])
    res["trials"] = [{"fos": f, "surface": sf} for f, sf in trials[:400]]
    all_methods = {}
    for m in ("ordinary", "bishop", "janbu", "spencer", "morgenstern_price"):
        fm, lm = factor_of_safety(s, m, analysis.interslice)
        all_methods[m] = {"fos": None if not np.isfinite(fm) else float(fm),
                          "lambda": None if not np.isfinite(lm) else float(lm)}
    res["critical"] = {
        "fos": F, "lambda": None if not np.isfinite(lam) else float(lam), "surface": surf,
        "slices": slice_table(s, F, lam, analysis.method, analysis.interslice),
        "all_methods": all_methods,
        "slice_x": [float(v) for v in ((-s.xb[::-1]) if s.mirrored else s.xb)],
        "driving_direction": "right" if s.mirrored else "left",
    }
    if analysis.probabilistic:
        res["probability"] = run_probabilistic(project, analysis, s)
    if analysis.sensitivity_param:
        res["sensitivity"] = run_sensitivity(project, analysis, s)
    return res


def run_probabilistic(project, analysis, s: SliceSet) -> dict:
    """Monte Carlo on the critical surface using normal distributions of c, phi and unit weight."""
    rng = np.random.default_rng(analysis.seed)
    ml = {m.id: m for m in project.materials}
    mats = [ml[mid] for mid in s.mat_ids]
    mu_g = np.array([m.unit_weight for m in mats]); sd_g = np.array([m.unit_weight_sd for m in mats])
    mu_c = np.array([m.cohesion for m in mats]); sd_c = np.array([m.cohesion_sd for m in mats])
    mu_p = np.array([m.phi for m in mats]); sd_p = np.array([m.phi_sd for m in mats])
    n = max(10, int(analysis.n_samples))
    fs = []
    for _ in range(n):
        g = np.clip(rng.normal(mu_g, sd_g), 1e-6, None)
        c = np.clip(rng.normal(mu_c, sd_c), 0.0, None)
        p = np.clip(rng.normal(mu_p, sd_p), 0.0, 89.0)
        set_strength(s, project.materials, g, c, p)
        F, _ = factor_of_safety(s, analysis.method, analysis.interslice)
        if np.isfinite(F):
            fs.append(F)
    set_strength(s, project.materials)
    fs = np.array(fs)
    if len(fs) == 0:
        return {"n": 0}
    mean, sd = float(fs.mean()), float(fs.std(ddof=1)) if len(fs) > 1 else 0.0
    return {"n": int(len(fs)), "mean": mean, "sd": sd, "min": float(fs.min()), "max": float(fs.max()),
            "pf": float((fs < 1.0).mean()), "reliability_index": (mean - 1.0) / sd if sd > 0 else None,
            "histogram": np.histogram(fs, bins=20)[0].tolist(),
            "hist_edges": np.histogram(fs, bins=20)[1].tolist()}


def run_sensitivity(project, analysis, s: SliceSet) -> dict:
    """Vary one material property (\"<material id>:<cohesion|phi|unit_weight>\") on the critical surface."""
    try:
        mid_s, prop = analysis.sensitivity_param.split(":")
        mid = int(mid_s)
    except ValueError:
        return {"error": f"Bad sensitivity parameter '{analysis.sensitivity_param}'"}
    if prop not in ("cohesion", "phi", "unit_weight") or mid not in s.mat_ids:
        return {"error": f"Bad sensitivity parameter '{analysis.sensitivity_param}'"}
    import copy
    mats = copy.deepcopy(project.materials)
    target = next(m for m in mats if m.id == mid)
    xs = np.linspace(analysis.sensitivity_low, analysis.sensitivity_high, max(2, analysis.sensitivity_steps))
    out = []
    for v in xs:
        setattr(target, prop, float(v))
        set_strength(s, mats)
        F, _ = factor_of_safety(s, analysis.method, analysis.interslice)
        out.append(float(F) if np.isfinite(F) else None)
    set_strength(s, project.materials)
    return {"param": analysis.sensitivity_param, "values": xs.tolist(), "fos": out}
