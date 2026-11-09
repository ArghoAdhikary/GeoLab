"""Limit-equilibrium slope stability (method of slices).

Methods: Ordinary (Fellenius), Bishop Simplified, Janbu Simplified (uncorrected and
with Janbu's f0 correction), Janbu Generalized, Spencer, Morgenstern-Price, Corps of
Engineers #1 and #2, Lowe-Karafiath and Sarma, all written in the General Limit
Equilibrium (GLE) framework of Fredlund & Krahn (1977), plus the finite element
stress method (Fredlund & Scoular 1999) when stresses from a stress analysis exist.

Sign convention used internally: slice data is mirrored when necessary so the
sliding mass always moves towards -x. A slice base angle alpha is positive when
the base rises to the right. Interslice normal force E is positive in
compression; the interslice shear X acts downwards on the slice to its left.
External horizontal forces H are positive in the direction of motion.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np

from .geometry import GroundProfile, point_in_polygon, polyline_y, vertical_intervals
from .strength import is_nonlinear, strength_at

M_ALPHA_MIN = 0.2
ALL_LE_METHODS = ("ordinary", "bishop", "janbu", "janbu_corrected", "janbu_generalized", "spencer",
                  "morgenstern_price", "corps1", "corps2", "lowe_karafiath", "sarma")


# ---------------------------------------------------------------------------
# Slip surfaces
# ---------------------------------------------------------------------------
def circle_surface(xc, yc, R, x1=None, x2=None) -> dict:
    """Circular slip surface. With x1/x2 only the arc between those x (an entry and an exit point) slides,
    as in an entry-and-exit search; the circle may dip below the ground again beyond the exit."""
    s = {"type": "circle", "xc": float(xc), "yc": float(yc), "R": float(R)}
    if x1 is not None and x2 is not None:
        s["x1"], s["x2"] = float(min(x1, x2)), float(max(x1, x2))
    return s


def polyline_surface(points) -> dict:
    return {"type": "polyline", "points": [[float(x), float(y)] for x, y in points]}


def _surface_fn(surface):
    if surface["type"] == "circle":
        xc, yc, R = surface["xc"], surface["yc"], surface["R"]

        a1, a2 = surface.get("x1"), surface.get("x2")

        def ys(x):
            x = np.asarray(x, dtype=float)
            d = np.clip(R * R - (x - xc) ** 2, 0.0, None)
            y = yc - np.sqrt(d)
            if a1 is not None:  # outside the entry-exit arc the surface is above the ground
                y = np.where((x < a1) | (x > a2), max(yc, y.max() if y.size else yc) + R, y)
            return y

        return ys, xc - R, xc + R
    pts = sorted(surface["points"], key=lambda p: p[0])
    xs = np.array([p[0] for p in pts])
    yv = np.array([p[1] for p in pts])
    return (lambda x: np.interp(x, xs, yv)), xs[0], xs[-1]


def _alpha(surface, x, ys):
    x = np.asarray(x, dtype=float)
    if surface["type"] == "circle":
        s = np.clip((x - surface["xc"]) / surface["R"], -0.999999, 0.999999)
        return np.arcsin(s)
    h = 1e-6 * max(1.0, float(np.abs(x).max()))
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
SLICE_ARRAYS = ("xm", "b", "yb", "ytop", "alpha", "l", "Wsoil", "Wext", "yg", "base_mat", "hfx",
                "hp", "hp_top", "Hx", "MHx", "Wfd", "Hfd", "MHfd")
BOUNDARY_ARRAYS = ("xb", "ytb", "ysb", "alpha_b")


@dataclass
class SliceSet:
    xm: np.ndarray        # (mirrored) x of slice mid
    xb: np.ndarray        # (mirrored) x of slice boundaries (n+1)
    b: np.ndarray
    yb: np.ndarray        # slip surface at slice mid
    ytop: np.ndarray      # ground at slice mid
    ytb: np.ndarray       # ground at boundaries (n+1)
    ysb: np.ndarray       # slip surface at boundaries (n+1)
    alpha: np.ndarray
    alpha_b: np.ndarray   # base inclination at boundaries (n+1)
    l: np.ndarray
    Wsoil: np.ndarray
    Wext: np.ndarray      # surcharges, vertical point loads, ponded water, fixed reinforcement
    yg: np.ndarray
    base_mat: np.ndarray
    area: np.ndarray      # n x nmat area of each material in each slice
    mat_ids: list
    surface: dict
    ax: float             # (mirrored) moment axis
    ay: float
    hfx: np.ndarray       # user horizontal point loads (direction of motion +)
    hp: np.ndarray        # pressure head at base
    hp_top: np.ndarray    # pressure head at the ground surface (ponded water when > 0)
    gamma_w: float
    kh: float = 0.0
    kv: float = 0.0
    pwp_mode: str = "none"
    ru: float = 0.0
    mirrored: bool = False
    Hx: np.ndarray = None    # fixed horizontal loads other than seismic (direction of motion +)
    MHx: np.ndarray = None   # their moment about the axis
    Wfd: np.ndarray = None   # factor-of-safety dependent loads (divided by F)
    Hfd: np.ndarray = None
    MHfd: np.ndarray = None
    # computed by set_strength
    W: np.ndarray = None
    H: np.ndarray = None
    MH: np.ndarray = None
    c: np.ndarray = None
    tanphi: np.ndarray = None
    tanphib: np.ndarray = None
    u: np.ndarray = None
    sv_eff: np.ndarray = None
    mats: list = field(default_factory=list)
    nl_idx: np.ndarray = None   # slices whose strength depends on the normal stress
    crack: dict | None = None

    @property
    def n(self):
        return len(self.xm)

    @property
    def up(self):
        return np.clip(self.u, 0.0, None)

    @property
    def um(self):
        return np.clip(-self.u, 0.0, None)

    def take(self, idx):
        """Keep slices idx (a contiguous range)."""
        idx = np.asarray(idx)
        bidx = np.concatenate((idx, [idx[-1] + 1]))
        for name in SLICE_ARRAYS:
            setattr(self, name, getattr(self, name)[idx].copy())
        for name in BOUNDARY_ARRAYS:
            setattr(self, name, getattr(self, name)[bidx].copy())
        self.area = self.area[idx].copy()


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
    breaks = [p[0] for r in project.regions for p in r.points]
    if surface["type"] == "polyline":
        breaks += [p[0] for p in surface["points"]]
    xb = _slice_boundaries(xl, xr, n, breaks)
    n = len(xb) - 1
    xm = 0.5 * (xb[:-1] + xb[1:])
    b = np.diff(xb)
    yb = ys(xm)
    ytop = gp.ground(xm)
    alpha = _alpha(surface, xm, ys)
    alpha_b = _alpha(surface, xb, ys)
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
    hp_top = np.zeros(n)
    if analysis.pwp in ("piezometric", "seepage") and pwp_fn is not None:
        hp = np.nan_to_num(np.asarray(pwp_fn(xm, yb), dtype=float), nan=0.0)
        hp_top = np.nan_to_num(np.asarray(pwp_fn(xm, ytop), dtype=float), nan=0.0)
    if surface["type"] == "circle":
        ax, ay = surface["xc"], surface["yc"]
    else:
        ax, ay = 0.5 * (xl + xr), float(ytop.max()) + 0.5 * (xr - xl)
    z = np.zeros(n)
    ss = SliceSet(xm=xm, xb=xb, b=b, yb=yb, ytop=ytop, ytb=gp.ground(xb), ysb=ys(xb), alpha=alpha,
                  alpha_b=alpha_b, l=b / np.cos(alpha), Wsoil=area @ np.array([mats[m].unit_weight for m in mat_ids]),
                  Wext=Wext, yg=ycent, base_mat=base_mat, area=area, mat_ids=mat_ids, surface=surface,
                  ax=ax, ay=ay, hfx=hfx, hp=hp, hp_top=hp_top, gamma_w=project.gamma_w, kh=analysis.kh,
                  kv=getattr(analysis, "kv", 0.0), pwp_mode=analysis.pwp, ru=analysis.ru,
                  Hx=z.copy(), MHx=z.copy(), Wfd=z.copy(), Hfd=z.copy(), MHfd=z.copy())
    # orient so the mass moves towards -x
    if np.sum(ss.Wsoil * np.sin(ss.alpha)) < 0:
        _mirror(ss)
    why = _tension_crack(ss, analysis)
    if why:
        return None, why
    _ponded_water(ss)
    _reinforcement(ss, project)
    set_strength(ss, project.materials)
    return ss, None


def _slice_boundaries(xl, xr, n, breaks):
    """About n slices between xl and xr, with boundaries at every break point (slip surface
    vertices and ground surface corners) so each slice base and top is a straight line."""
    width = (xr - xl) / n
    tol = 1e-3 * width
    pts = sorted({xl, xr, *(float(x) for x in breaks if xl + tol < x < xr - tol)})
    xb = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        k = max(1, int(round((b - a) / width)))
        xb += list(np.linspace(a, b, k + 1)[1:])
    return np.array(xb)


def _mirror(s: SliceSet):
    for name in SLICE_ARRAYS + BOUNDARY_ARRAYS:
        setattr(s, name, getattr(s, name)[::-1].copy())
    s.area = s.area[::-1].copy()
    s.xm, s.xb = -s.xm, -s.xb
    s.alpha, s.alpha_b = -s.alpha, -s.alpha_b
    s.ax = -s.ax
    s.mirrored = True


def _tension_crack(s: SliceSet, analysis):
    """Remove slices at the crest end that fall in the tension crack zone; add crack water force."""
    dc = getattr(analysis, "tension_crack_depth", 0.0) or 0.0
    ang = getattr(analysis, "tension_crack_angle", 0.0) or 0.0
    if dc <= 0 and ang <= 0:
        return None
    m = s.n
    while m > 2:
        k = m - 1
        deep = (s.ytb[k + 1] - s.ysb[k + 1]) < dc if dc > 0 else False  # depth at the present end face
        steep = math.degrees(s.alpha[k]) > ang if ang > 0 else False
        if not (deep or steep):
            break
        m -= 1
    if m < 3:
        return "Tension crack removes the whole sliding mass."
    if m < s.n:
        s.take(np.arange(m))
    d = float(s.ytb[-1] - s.ysb[-1])
    fw = min(max(getattr(analysis, "crack_water", 0.0) or 0.0, 0.0), 1.0)
    hw = fw * d
    Pw = 0.5 * s.gamma_w * hw * hw
    s.crack = {"x": float(-s.xb[-1] if s.mirrored else s.xb[-1]), "depth": d, "water_force": Pw}
    if Pw > 0:
        y = s.ysb[-1] + hw / 3.0
        s.Hx[-1] += Pw
        s.MHx[-1] += Pw * (y - s.ay)
    return None


def _ponded_water(s: SliceSet):
    """Water above the ground surface acts as a pressure load on the slice tops."""
    if s.pwp_mode not in ("piezometric", "seepage"):
        return
    p = s.gamma_w * np.clip(s.hp_top, 0.0, None)
    if not p.any():
        return
    dy = np.diff(s.ytb)
    s.Wext = s.Wext + p * s.b
    Hm = -p * dy                         # horizontal force in +x is p*dy; direction of motion is -x
    s.Hx = s.Hx + Hm
    s.MHx = s.MHx + Hm * (s.ytop - s.ay)


def _reinforcement(s: SliceSet, project):
    for r in getattr(project, "reinforcements", []) or []:
        sign = -1.0 if s.mirrored else 1.0
        p1 = np.array([sign * r.x1, r.y1])
        p2 = np.array([sign * r.x2, r.y2])
        L = float(np.hypot(*(p2 - p1)))
        if L <= 0:
            continue

        def g(t):
            x, y = p1 + t * (p2 - p1)
            if x < s.xb[0] or x > s.xb[-1]:
                return math.nan
            return y - float(np.interp(x, s.xb, s.ysb))
        ts = np.linspace(0.0, 1.0, 201)
        gs = np.array([g(t) for t in ts])
        hit = None
        for k in range(len(ts) - 1):
            if np.isfinite(gs[k]) and np.isfinite(gs[k + 1]) and gs[k] > 0 >= gs[k + 1]:
                a, b_ = ts[k], ts[k + 1]
                for _ in range(40):
                    mid = 0.5 * (a + b_)
                    if g(mid) > 0:
                        a = mid
                    else:
                        b_ = mid
                hit = 0.5 * (a + b_)
                break
        if hit is None:
            continue
        x, y = p1 + hit * (p2 - p1)
        beyond = (1.0 - hit) * L
        if r.type == "pile":
            T = r.capacity / max(r.spacing, 1e-9)
            k = int(np.clip(np.searchsorted(s.xb, x) - 1, 0, s.n - 1))
            u = np.array([math.cos(s.alpha[k]), math.sin(s.alpha[k])])   # up-slope, opposing motion
        else:
            bonded = min(r.bond_length, beyond) if r.type == "anchor" else beyond
            T = min(r.capacity, r.bond * bonded) / max(r.spacing, 1e-9)
            u = (p2 - p1) / L
        Fx, Fy = T * u
        k = int(np.clip(np.searchsorted(s.xb, x) - 1, 0, s.n - 1))
        Hm, V = -Fx, -Fy                  # direction of motion +, downward +
        M = Hm * (y - s.ay) - V * (x - s.xm[k])
        if r.f_dependent:
            s.Wfd[k] += V; s.Hfd[k] += Hm; s.MHfd[k] += M
        else:
            s.Wext[k] += V; s.Hx[k] += Hm; s.MHx[k] += M


def set_strength(s: SliceSet, materials, gamma=None, coh=None, phi=None):
    """(Re)compute weights, strength and pore pressure, optionally with sampled properties."""
    mats = {m.id: m for m in materials}
    ml = [mats[mid] for mid in s.mat_ids]
    if gamma is not None or coh is not None or phi is not None:
        ml = [dataclasses.replace(m, unit_weight=float(gamma[k]) if gamma is not None else m.unit_weight,
                                  cohesion=float(coh[k]) if coh is not None else m.cohesion,
                                  phi=float(phi[k]) if phi is not None else m.phi) for k, m in enumerate(ml)]
    g = np.array([m.unit_weight for m in ml])
    s.Wsoil = s.area @ g
    s.W = s.Wsoil * (1.0 + s.kv) + s.Wext
    bm = s.base_mat
    s.mats = [ml[k] for k in bm]
    if s.pwp_mode == "ru":
        s.u = s.ru * s.Wsoil / s.b
    elif s.pwp_mode in ("piezometric", "seepage"):
        s.u = s.gamma_w * s.hp
    else:
        s.u = np.zeros(s.n)
    no_water = np.array([m.model in ("undrained", "undrained_depth", "shansep", "high_strength") for m in s.mats])
    # undrained (total stress) strength ignores pore pressure; negative pressure only helps with phi_b
    s.u = np.where(no_water, 0.0, s.u)
    s.tanphib = np.array([math.tan(math.radians(m.phi_b)) for m in s.mats])
    s.sv_eff = (s.Wsoil + s.Wext) / s.b - s.up
    sn0 = s.sv_eff * np.cos(s.alpha) ** 2
    s.c = np.zeros(s.n)
    s.tanphi = np.zeros(s.n)
    for i, m in enumerate(s.mats):
        s.c[i], s.tanphi[i] = strength_at(m, sn0[i], sv_eff=s.sv_eff[i], y=s.yb[i], alpha=s.alpha[i])
    s.nl_idx = np.array([i for i, m in enumerate(s.mats) if is_nonlinear(m)], dtype=int)
    Hs = s.kh * s.Wsoil
    s.H = Hs + s.hfx + s.Hx
    s.MH = Hs * (s.yg - s.ay) + s.hfx * (s.ytop - s.ay) + s.MHx


def _update_strength(s: SliceSet, N):
    if s.nl_idx is None or len(s.nl_idx) == 0 or N is None:
        return
    sn = N / s.l - s.up
    for i in s.nl_idx:
        s.c[i], s.tanphi[i] = strength_at(s.mats[i], float(sn[i]), sv_eff=float(s.sv_eff[i]),
                                          y=float(s.yb[i]), alpha=float(s.alpha[i]))


# ---------------------------------------------------------------------------
# Factor of safety
# ---------------------------------------------------------------------------
def _terms(s: SliceSet):
    dx, dyb = s.xm - s.ax, s.yb - s.ay
    ca, sa = np.cos(s.alpha), np.sin(s.alpha)
    armN = dx * ca + dyb * sa
    armS = dx * sa - dyb * ca
    return ca, sa, armN, armS, dx


def _loads(s, F):
    return s.W + s.Wfd / F, s.H + s.Hfd / F, s.MH + s.MHfd / F


def _normal(s, F, dX, ca, sa, Wt):
    ma = np.maximum(ca + sa * s.tanphi / F, M_ALPHA_MIN)
    A = s.c * s.l - s.up * s.l * s.tanphi + s.um * s.l * s.tanphib
    return (Wt + dX - A * sa / F) / ma


def _strength(s, N):
    return s.c * s.l + np.clip(N - s.up * s.l, 0.0, None) * s.tanphi + s.um * s.l * s.tanphib


def _fm(s, N, S1, armN, armS, dx, Wt, MHt):
    den = -np.sum(-Wt * dx + MHt + N * armN)
    return np.sum(S1 * armS) / den if den > 0 else math.nan


def _ff(s, N, S1, ca, sa, Ht):
    den = np.sum(N * sa + Ht)
    return np.sum(S1 * ca) / den if den > 0 else math.nan


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


def fos_ordinary(s: SliceSet):
    ca, sa, armN, armS, dx = _terms(s)

    def step(F):
        Wt, Ht, MHt = _loads(s, F)
        N = Wt * ca - Ht * sa
        _update_strength(s, N)
        return _fm(s, N, _strength(s, N), armN, armS, dx, Wt, MHt)
    return _iterate(step, 1.0)


def fos_bishop(s: SliceSet, F0=1.0):
    ca, sa, armN, armS, dx = _terms(s)
    zero = np.zeros(s.n)

    def step(F):
        Wt, _, MHt = _loads(s, F)
        N = _normal(s, F, zero, ca, sa, Wt)
        _update_strength(s, N)
        return _fm(s, N, _strength(s, N), armN, armS, dx, Wt, MHt)
    if not np.isfinite(F0) or F0 <= 0:
        F0 = 1.0
    return _iterate(step, F0)


def fos_janbu(s: SliceSet, F0=1.0):
    ca, sa, *_ = _terms(s)
    zero = np.zeros(s.n)

    def step(F):
        Wt, Ht, _ = _loads(s, F)
        N = _normal(s, F, zero, ca, sa, Wt)
        _update_strength(s, N)
        return _ff(s, N, _strength(s, N), ca, sa, Ht)
    return _iterate(step, F0 if np.isfinite(F0) and F0 > 0 else 1.0)


def janbu_f0(s: SliceSet) -> float:
    """Janbu's empirical correction factor from the depth-to-length ratio of the sliding mass."""
    L = math.hypot(s.xb[-1] - s.xb[0], s.ysb[-1] - s.ysb[0])
    if L <= 0:
        return 1.0
    chord = s.ysb[0] + (s.xm - s.xb[0]) * (s.ysb[-1] - s.ysb[0]) / (s.xb[-1] - s.xb[0])
    d = float(np.max(chord - s.yb)) * math.cos(math.atan2(s.ysb[-1] - s.ysb[0], s.xb[-1] - s.xb[0]))
    has_c = bool(np.any(s.c > 0))
    has_phi = bool(np.any(s.tanphi > 0))
    b1 = 0.5 if (has_c and has_phi) else (0.69 if has_c else 0.31)
    r = max(d, 0.0) / L
    return 1.0 + b1 * (r - 1.4 * r * r)


def _interslice_f(s: SliceSet, kind, points=None):
    t = (s.xb - s.xb[0]) / (s.xb[-1] - s.xb[0])
    if kind == "constant":
        return np.ones(s.n + 1)
    if kind == "clipped_sine":      # half-sine raised so the ends carry half the peak value
        return np.sin(np.pi * (1.0 / 6.0 + (2.0 / 3.0) * t))
    if kind == "trapezoidal":       # zero at the ends, full value over the middle half
        return np.clip(np.minimum(t, 1.0 - t) / 0.25, 0.0, 1.0)
    if kind == "user" and points:
        pts = sorted(points)
        return np.interp(t, [p[0] for p in pts], [p[1] for p in pts])
    return np.sin(np.pi * t)


def _gle_solve(s, xfun, eq, F0, tol=1e-6, it=300):
    """F from moment (eq='m') or force (eq='f') equilibrium for an interslice shear rule X = xfun(E)."""
    ca, sa, armN, armS, dx = _terms(s)
    X = np.zeros(s.n + 1)
    F = F0
    scale = max(1.0, float(np.max(np.abs(s.W))))
    for _ in range(it):
        Wt, Ht, MHt = _loads(s, F)
        dX = X[1:] - X[:-1]
        N = _normal(s, F, dX, ca, sa, Wt)
        _update_strength(s, N)
        S1 = _strength(s, N)
        Fn = _fm(s, N, S1, armN, armS, dx, Wt, MHt) if eq == "m" else _ff(s, N, S1, ca, sa, Ht)
        if not np.isfinite(Fn) or Fn <= 0:
            return math.nan, None, None
        dE = -N * sa + (S1 / Fn) * ca - Ht
        E = np.concatenate(([0.0], np.cumsum(dE)))
        Xn = xfun(E, Fn)
        Xn[0] = Xn[-1] = 0.0
        Xn = 0.5 * (X + Xn)  # under-relaxation for robustness
        if abs(Fn - F) < tol and np.max(np.abs(Xn - X)) < 1e-6 * scale:
            return Fn, N, E
        F, X = Fn, Xn
    return math.nan, None, None


def _solve_lambda(s, make_xfun, F0):
    """Find lambda where moment and force factors of safety agree. Returns (F, lambda)."""
    cache = {}

    def g(lam):
        if lam not in cache:
            xf = make_xfun(lam)
            fm, _, _ = _gle_solve(s, xf, "m", F0)
            ff, _, _ = _gle_solve(s, xf, "f", F0)
            cache[lam] = (fm, ff)
        fm, ff = cache[lam]
        return fm - ff, fm, ff

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


def _start(s):
    F0 = fos_bishop(s)
    return F0 if np.isfinite(F0) else 1.0


def fos_gle(s: SliceSet, interslice="half_sine", F0=None, points=None):
    """Spencer (interslice='constant') or Morgenstern-Price (any other interslice function)."""
    fx = _interslice_f(s, interslice, points)
    F0 = F0 if F0 is not None and np.isfinite(F0) else _start(s)
    return _solve_lambda(s, lambda lam: (lambda E, F: lam * fx * E), F0)


def _inclination_methods(s: SliceSet, method):
    """Interslice force inclination tan(theta) at each boundary for the force-only methods."""
    ground = np.gradient(s.ytb, s.xb)
    if method == "corps1":
        return np.full(s.n + 1, (s.ytb[-1] - s.ytb[0]) / (s.xb[-1] - s.xb[0]))
    if method == "corps2":
        return ground
    return np.tan(0.5 * (np.arctan(ground) + s.alpha_b))   # Lowe-Karafiath


def fos_force_inclined(s: SliceSet, method):
    tanth = _inclination_methods(s, method)
    F, _, _ = _gle_solve(s, lambda E, F: tanth * E, "f", _start(s))
    return F


def fos_sarma(s: SliceSet):
    """Sarma (vertical slices): interslice shear X = lambda (c h + E tan phi), averaged on each boundary."""
    h = np.clip(s.ytb - s.ysb, 0.0, None)
    cb = np.concatenate(([s.c[0]], 0.5 * (s.c[:-1] + s.c[1:]), [s.c[-1]]))
    tb = np.concatenate(([s.tanphi[0]], 0.5 * (s.tanphi[:-1] + s.tanphi[1:]), [s.tanphi[-1]]))
    cb = np.minimum(cb, 1e6)
    return _solve_lambda(s, lambda lam: (lambda E, F: lam * (cb * h + np.clip(E, 0, None) * tb)), _start(s))


def fos_janbu_generalized(s: SliceSet, thrust=1.0 / 3.0, it=300, tol=1e-6):
    """Force equilibrium with interslice shear from slice moment equilibrium about the base midpoint,
    the line of thrust at a fixed fraction of the boundary height."""
    ca, sa, *_ = _terms(s)
    yt = s.ysb + thrust * np.clip(s.ytb - s.ysb, 0.0, None)
    X = np.zeros(s.n + 1)
    F = _start(s)
    for _ in range(it):
        Wt, Ht, _ = _loads(s, F)
        N = _normal(s, F, X[1:] - X[:-1], ca, sa, Wt)
        _update_strength(s, N)
        S1 = _strength(s, N)
        Fn = _ff(s, N, S1, ca, sa, Ht)
        if not np.isfinite(Fn) or Fn <= 0:
            return math.nan
        E = np.concatenate(([0.0], np.cumsum(-N * sa + (S1 / Fn) * ca - Ht)))
        xavg = ((yt[1:] - s.yb) * E[1:] - (yt[:-1] - s.yb) * E[:-1] + (s.yg - s.yb) * Ht) / s.b
        Xn = np.zeros(s.n + 1)
        Xn[1:-1] = 0.5 * (xavg[:-1] + xavg[1:])
        Xn = 0.7 * X + 0.3 * Xn
        if abs(Fn - F) < tol and np.max(np.abs(Xn - X)) < 1e-5 * max(1.0, float(np.max(np.abs(s.W)))):
            return Fn
        F, X = Fn, Xn
    return math.nan


def factor_of_safety(s: SliceSet, method: str, interslice="half_sine", points=None):
    """Return (F, lambda). lambda is nan for methods without a lambda."""
    if method == "ordinary":
        return fos_ordinary(s), math.nan
    if method == "bishop":
        return fos_bishop(s, fos_ordinary(s)), math.nan
    if method in ("janbu", "janbu_corrected"):
        F0 = fos_ordinary(s)
        F = fos_janbu(s, F0 if np.isfinite(F0) else 1.0)
        return (F * janbu_f0(s) if method == "janbu_corrected" else F), math.nan
    if method == "janbu_generalized":
        return fos_janbu_generalized(s), math.nan
    if method == "spencer":
        return fos_gle(s, "constant")
    if method == "morgenstern_price":
        return fos_gle(s, interslice, points=points)
    if method in ("corps1", "corps2", "lowe_karafiath"):
        return fos_force_inclined(s, method), math.nan
    if method == "sarma":
        return fos_sarma(s)
    raise ValueError(f"Unknown method {method}")


def slice_table(s: SliceSet, F: float, lam: float, method: str, interslice="half_sine", points=None):
    """Per-slice forces for reporting, in the original (unmirrored) coordinates."""
    ca, sa, *_ = _terms(s)
    X = np.zeros(s.n + 1)
    E = np.zeros(s.n + 1)
    Wt, Ht, _ = _loads(s, F if F and np.isfinite(F) else 1.0)
    N = None
    if method in ("spencer", "morgenstern_price") and np.isfinite(lam):
        fx = _interslice_f(s, "constant" if method == "spencer" else interslice, points)
        _, N, E = _gle_solve(s, lambda E_, F_: lam * fx * E_, "m", F)
        if N is not None:
            X = lam * fx * E
    elif method in ("corps1", "corps2", "lowe_karafiath") and np.isfinite(F):
        tanth = _inclination_methods(s, method)
        _, N, E = _gle_solve(s, lambda E_, F_: tanth * E_, "f", F)
        if N is not None:
            X = tanth * E
    elif method == "ordinary":
        N = Wt * ca - Ht * sa
    if N is None:
        N = _normal(s, F if np.isfinite(F) else 1.0, np.zeros(s.n), ca, sa, Wt)
        E = np.zeros(s.n + 1)
        X = np.zeros(s.n + 1)
    _update_strength(s, N)
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
# Finite element stress method
# ---------------------------------------------------------------------------
def fos_finite_element(s: SliceSet, stress_fn):
    """F = sum(strength * l) / sum(mobilized shear * l) with stresses from a stress analysis.

    stress_fn(x, y) returns (sx, sy, txy, u) in original coordinates, compression positive.
    """
    sign = -1.0 if s.mirrored else 1.0
    sx, sy, txy, u = stress_fn(sign * s.xm, s.yb)
    a = s.alpha
    txy = sign * np.asarray(txy)               # mirroring flips the sign of the shear stress
    ca, sa = np.cos(a), np.sin(a)
    sn = sx * sa * sa + sy * ca * ca - 2.0 * txy * sa * ca
    tau = (sy - sx) * sa * ca + txy * (ca * ca - sa * sa)
    sn_eff = sn - np.clip(u, 0.0, None)
    strength = np.zeros(s.n)
    for i, m in enumerate(s.mats):
        c, t = strength_at(m, float(sn_eff[i]), sv_eff=float(s.sv_eff[i]), y=float(s.yb[i]), alpha=float(a[i]))
        strength[i] = c + max(sn_eff[i], 0.0) * t + max(-u[i], 0.0) * s.tanphib[i]
    mob = float(np.sum(tau * s.l))
    if abs(mob) < 1e-12:
        return math.nan, None
    local = strength / np.where(np.abs(tau) > 1e-12, np.abs(tau), np.nan)
    return float(np.sum(strength * s.l) / abs(mob)), local


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def _grid(x1, y1, x2, y2, nx, ny):
    xs = np.linspace(min(x1, x2), max(x1, x2), max(1, nx))
    ys = np.linspace(min(y1, y2), max(y1, y2), max(1, ny))
    return [(x, y) for x in xs for y in ys]


def candidate_surfaces(project, analysis, gp: GroundProfile):
    st = analysis.search
    out = []
    mode = st.mode
    if mode in ("grid_radius", "grid_tangent"):
        centers = _grid(st.grid_x1, st.grid_y1, st.grid_x2, st.grid_y2, st.grid_nx, st.grid_ny)
        if mode == "grid_radius":
            rs = np.linspace(st.radius_min, st.radius_max, max(1, st.n_radii))
            for x, y in centers:
                out += [circle_surface(x, y, r) for r in rs if r > 0]
        else:
            ts = np.linspace(min(st.tangent_y1, st.tangent_y2), max(st.tangent_y1, st.tangent_y2),
                             max(1, st.n_tangent))
            for x, y in centers:
                out += [circle_surface(x, y, y - t) for t in ts if y - t > 0]
    elif mode in ("entry_exit", "auto"):
        if mode == "auto":
            from .geometry import auto_entry_exit
            (e1, e2), (x1, x2) = auto_entry_exit(project)
        else:
            e1, e2, x1, x2 = st.entry_x1, st.entry_x2, st.exit_x1, st.exit_x2
        ex = np.linspace(e1, e2, max(1, st.n_entry))
        xx = np.linspace(x1, x2, max(1, st.n_exit))
        # radii as SLOPE/W spaces them: evenly spaced arc depths (sagitta) below the entry-exit chord,
        # from about 1.5 % to 28 % of the chord length
        nr = max(1, st.n_radius)
        sags = np.linspace(0.0145, 0.0145 + 0.262, nr) if nr > 1 else np.array([0.14])
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
                for k in sags:
                    sag = k * L
                    R = (0.25 * L * L + sag * sag) / (2.0 * sag)
                    cx, cy = mid + nrm * (R - sag)
                    out.append(circle_surface(cx, cy, R, p1[0], p2[0]))
    elif mode == "block":
        left = _grid(*st.block_left, st.block_n, st.block_n)
        right = _grid(*st.block_right, st.block_n, st.block_n)
        span = 2.0 * (gp.xmax - gp.xmin + gp.ymax - gp.ymin)
        al, ar = math.radians(st.block_angle_left), math.radians(st.block_angle_right)
        for pl in left:
            for pr in right:
                if pr[0] <= pl[0] + 1e-9:
                    continue
                out.append(polyline_surface([
                    (pl[0] - span * math.cos(al), pl[1] + span * math.sin(al)), pl, pr,
                    (pr[0] + span * math.cos(ar), pr[1] + span * math.sin(ar))]))
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


def evaluate_surface(project, analysis, surface, pwp_fn, gp, method=None, stress_fn=None):
    s, why = build_slices(project, analysis, surface, pwp_fn, gp)
    if s is None:
        return None, math.nan, math.nan, why
    method = method or analysis.method
    if method == "finite_element":
        if stress_fn is None:
            return None, math.nan, math.nan, "No stresses available for the finite element method."
        F, _ = fos_finite_element(s, stress_fn)
        return s, F, math.nan, None
    F, lam = factor_of_safety(s, method, analysis.interslice, analysis.interslice_points)
    return s, F, lam, None


def drawdown_line(project, analysis, gp):
    """Water table after a rapid drawdown: the reservoir falls to the drawdown level, the water inside
    the slope stays where it was (no time to drain), and the slope face stays saturated."""
    line = sorted(project.piezometric_line)
    xs = sorted({p[0] for p in line} | {float(x) for x in np.linspace(line[0][0], line[-1][0], 200)})
    out = []
    for x in xs:
        y0 = polyline_y(line, x)
        g = float(gp.ground(x))
        out.append([x, float(min(y0, max(analysis.drawdown_level, g)))])
    return out


def _slice_normal_shear(s, F, lam, method, analysis):
    """Effective normal stress and mobilized shear stress on each slice base (internal slice order)."""
    rows = slice_table(s, F, lam, method, analysis.interslice, analysis.interslice_points)
    if s.mirrored:
        rows = rows[::-1]
    N = np.array([r["normal"] for r in rows])
    tau = np.array([r["shear_mobilized"] for r in rows]) / s.l
    return N / s.l - s.up, tau


def rapid_drawdown_fos(project, analysis, surface, gp, method=None):
    """Three-stage rapid drawdown (Duncan, Wright and Wong 1990).

    1. Before drawdown (piezometric line = high reservoir): effective consolidation stresses on each
       slice base, sigma'fc and tau_fc, and the consolidation ratio Kc = sigma'1c / sigma'3c.
    2. After drawdown: undrained strength from the R (total stress) envelope at Kc = 1 and the effective
       envelope at Kc = Kf, interpolated on Kc. Free-draining materials (no R envelope) stay drained.
    3. Where the drained strength with the after-drawdown pore pressures is lower, it is used instead.
    Returns (slice set of the last stage, F, lambda, reason, {stage1, stage2, stage3})."""
    method = method or analysis.method
    before = lambda x, y: polyline_y(project.piezometric_line, x) - y
    after_line = drawdown_line(project, analysis, gp)
    after = lambda x, y: polyline_y(after_line, x) - y
    s1, why = build_slices(project, analysis, surface, before, gp)
    if s1 is None:
        return None, math.nan, math.nan, why, None
    F1, lam1 = factor_of_safety(s1, method, analysis.interslice, analysis.interslice_points)
    if not np.isfinite(F1):
        return None, math.nan, math.nan, "Solution did not converge.", None
    sfc, tfc = _slice_normal_shear(s1, F1, lam1, method, analysis)
    s2, why = build_slices(project, analysis, surface, after, gp)
    if s2 is None:
        return None, math.nan, math.nan, why, None
    # carry the stage 1 stresses to the stage 2 slices by position
    o1 = np.argsort(s1.xm)
    sfc2 = np.interp(s2.xm, s1.xm[o1], sfc[o1])
    tfc2 = np.interp(s2.xm, s1.xm[o1], tfc[o1])
    undrained = np.zeros(s2.n, bool)
    cu = np.zeros(s2.n)
    for i, m in enumerate(s2.mats):
        if m.cr <= 0 and m.phi_r <= 0:
            continue                                   # free draining: drained strength throughout
        sp, cp = math.sin(math.radians(m.phi)), math.cos(math.radians(m.phi))
        sr, cr_ = math.sin(math.radians(m.phi_r)), math.cos(math.radians(m.phi_r))
        sig_fc, tau_fc = max(sfc2[i], 0.0), max(tfc2[i], 0.0)
        s1c = sig_fc + tau_fc * (1 + sp) / max(cp, 1e-9)
        s3c = sig_fc + tau_fc * (sp - 1) / max(cp, 1e-9)
        d_r = m.cr * cr_ / (1 - sr)
        t_k1 = d_r + sig_fc * sr / (1 - sr)
        d_e = m.cohesion * cp / (1 - sp)
        t_kf = d_e + sig_fc * sp / (1 - sp)
        if s3c > 1e-9:
            Np = (1 + sp) / (1 - sp)
            Kf = (s3c * Np + 2 * m.cohesion * math.sqrt(Np)) / s3c
            Kc = min(s1c / s3c, Kf)
            tff = t_k1 if Kf <= 1 + 1e-9 else ((Kf - Kc) * t_k1 + (Kc - 1) * t_kf) / (Kf - 1)
        else:
            tff = t_k1
        undrained[i] = True
        cu[i] = max(tff, 0.0)
    nl = list(s2.nl_idx) if s2.nl_idx is not None else []
    if undrained.any():
        s2.c = np.where(undrained, cu, s2.c)
        s2.tanphi = np.where(undrained, 0.0, s2.tanphi)
        s2.nl_idx = np.array([i for i in nl if not undrained[i]], int)
    F2, lam2 = factor_of_safety(s2, method, analysis.interslice, analysis.interslice_points)
    if not np.isfinite(F2):
        return None, math.nan, math.nan, "Solution did not converge.", None
    # stage 3: drained strength (after-drawdown pore pressures) where it is lower
    sn2, _ = _slice_normal_shear(s2, F2, lam2, method, analysis)
    s3, _ = build_slices(project, analysis, surface, after, gp)
    drained_tau = s3.c + np.maximum(sn2, 0.0) * s3.tanphi
    use_undrained = undrained & (cu <= drained_tau)
    F3, lam3, s_out = F2, lam2, s2
    if (undrained & ~use_undrained).any():
        s3.c = np.where(use_undrained, cu, s3.c)
        s3.tanphi = np.where(use_undrained, 0.0, s3.tanphi)
        nl3 = list(s3.nl_idx) if s3.nl_idx is not None else []
        s3.nl_idx = np.array([i for i in nl3 if not use_undrained[i]], int)
        F3, lam3 = factor_of_safety(s3, method, analysis.interslice, analysis.interslice_points)
        s_out = s3
        if not np.isfinite(F3):
            return None, math.nan, math.nan, "Solution did not converge.", None
    stages = {"stage1": float(F1), "stage2": float(F2), "stage3": float(F3),
              "undrained_slices": int(use_undrained.sum()), "slices": int(s2.n)}
    return s_out, float(F3), lam3, None, stages


def optimize_surface(project, analysis, surface, F, pwp_fn, gp, stress_fn=None, budget=None):
    """Refine a slip surface by moving the vertices of an equivalent polyline (pattern search)."""
    ext = find_extent(gp, surface)
    if ext is None:
        return surface, F
    xl, xr, depth = ext
    ys, _, _ = _surface_fn(surface)
    m = 12
    xs = np.linspace(xl, xr, m + 1)
    pts = np.column_stack([xs, ys(xs)])
    pts[0, 1] = gp.ground(xl) + 1e-6
    pts[-1, 1] = gp.ground(xr) + 1e-6
    best_pts, best = pts.copy(), F
    step = 0.15 * max(depth, 1e-3)
    dxs = 0.05 * (xr - xl)
    budget = budget or getattr(analysis, "opt_iterations", 400)
    evals = 0

    def trial(p):
        nonlocal evals
        evals += 1
        if np.any(np.diff(p[:, 0]) <= 1e-9):
            return math.nan
        _, f, _, why = evaluate_surface(project, analysis, polyline_surface(p.tolist()), pwp_fn, gp,
                                        stress_fn=stress_fn)
        return f if not why and np.isfinite(f) else math.nan

    while evals < budget and step > 0.002 * max(depth, 1e-3):
        improved = False
        for k in range(m + 1):
            for d in (1.0, -1.0):
                p = best_pts.copy()
                if k in (0, m):            # end points slide along the ground surface
                    p[k, 0] += d * dxs
                    p[k, 1] = gp.ground(p[k, 0]) + 1e-6
                else:
                    p[k, 1] += d * step
                f = trial(p)
                if np.isfinite(f) and f < best - 1e-6:
                    best, best_pts, improved = f, p, True
                    break
            if evals >= budget:
                break
        if not improved:
            step *= 0.5
            dxs *= 0.5
    if best < F:
        return polyline_surface(best_pts.tolist()), best
    return surface, F


def stress_interpolator(stress_results):
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    nodes = np.asarray(stress_results["nodes"])
    data = np.column_stack([stress_results[k] for k in ("sx", "sy", "txy", "pwp")])
    lin = LinearNDInterpolator(nodes, data)
    near = NearestNDInterpolator(nodes, data)

    def f(x, y):
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        v = lin(x, y)
        bad = ~np.all(np.isfinite(v), axis=1)
        if bad.any():
            v[bad] = near(x[bad], y[bad])
        return v[:, 0], v[:, 1], v[:, 2], v[:, 3]
    return f


def excess_pwp_fn(dyn_results):
    """Excess pore pressure (x, y) after an earthquake from a dynamic analysis with pore pressure
    generation (element values at the element centres)."""
    from .fe import interpolator
    nodes = np.asarray(dyn_results["nodes"])
    tris = np.asarray(dyn_results["tris"])[:, :3]
    cen = nodes[tris].mean(axis=1)
    return interpolator(cen, dyn_results["excess_pwp"])


def run_slope(project, analysis, seep_results=None, progress=None, cancel=None, stress_results=None,
              excess_fn=None) -> dict:
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
    stress_fn = stress_interpolator(stress_results) if stress_results else None
    if analysis.method == "finite_element" and stress_fn is None:
        raise ValueError("The finite element stress method needs a solved stress-deformation analysis "
                         "(set it as this analysis's stress parent).")
    gp = GroundProfile(project.regions)
    pwp_fn = make_pwp_fn(project, analysis, seep_results)
    if excess_fn is not None:            # after an earthquake: static + excess pore pressure
        import copy as _copy
        base, gw = pwp_fn, project.gamma_w

        def pwp_fn(x, y, base=base):
            b = base(x, y) if base is not None else np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape)
            return np.asarray(b, float) + np.asarray(excess_fn(x, y), float) / gw
        if analysis.pwp not in ("piezometric", "seepage"):
            analysis = _copy.copy(analysis)
            analysis.pwp = "piezometric"
    surfaces = candidate_surfaces(project, analysis, gp)
    if not surfaces:
        raise ValueError("The slip surface search produced no trial surfaces. Check the search settings.")
    trials = []
    best = None
    best_stages = None
    reasons: dict[str, int] = {}
    drawdown = bool(getattr(analysis, "rapid_drawdown", False))
    if drawdown:
        if len(project.piezometric_line) < 2:
            raise ValueError("Rapid drawdown needs a piezometric line drawn at the reservoir level before "
                             "drawdown (Draw > Piezometric Line).")
        if analysis.method == "finite_element":
            raise ValueError("Rapid drawdown works with the limit equilibrium methods, not the finite "
                             "element stress method.")
    for k, surf in enumerate(surfaces):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        if drawdown:
            s, F, lam, why, stages = rapid_drawdown_fos(project, analysis, surf, gp)
        else:
            s, F, lam, why = evaluate_surface(project, analysis, surf, pwp_fn, gp, stress_fn=stress_fn)
            stages = None
        if why:
            reasons[why] = reasons.get(why, 0) + 1
        elif np.isfinite(F):
            trials.append((float(F), surf))
            if best is None or F < best[0]:
                best = (float(F), surf, lam, s)
                best_stages = stages
        else:
            reasons["Solution did not converge."] = reasons.get("Solution did not converge.", 0) + 1
        if progress and k % 20 == 0:
            progress(int(90 * (k + 1) / len(surfaces)))
    res = {"type": "slope", "method": analysis.method, "n_total": len(surfaces), "n_valid": len(trials),
           "invalid_reasons": reasons, "critical": None, "trials": []}
    if best is None:
        res["message"] = "No valid slip surface found. " + "; ".join(f"{v} x {k}" for k, v in reasons.items())
        return res
    F, surf, lam, s = best
    if (analysis.optimize or analysis.search.mode == "auto") and not drawdown:
        surf2, F2 = optimize_surface(project, analysis, surf, F, pwp_fn, gp, stress_fn)
        if F2 < F:
            s, F, lam, _ = evaluate_surface(project, analysis, surf2, pwp_fn, gp, stress_fn=stress_fn)
            surf = surf2
            res["optimized_from"] = best[0]
    if progress:
        progress(95)
    trials.sort(key=lambda t: t[0])
    res["trials"] = [{"fos": f, "surface": sf} for f, sf in trials[:400]]
    all_methods = {}
    for m in ALL_LE_METHODS:
        fm, lm = factor_of_safety(s, m, analysis.interslice, analysis.interslice_points)
        all_methods[m] = {"fos": None if not np.isfinite(fm) else float(fm),
                          "lambda": None if not np.isfinite(lm) else float(lm)}
    if stress_fn is not None:
        fe, _ = fos_finite_element(s, stress_fn)
        all_methods["finite_element"] = {"fos": float(fe) if np.isfinite(fe) else None, "lambda": None}
    table_method = analysis.method if analysis.method != "finite_element" else "morgenstern_price"
    res["critical"] = {
        "fos": F, "lambda": None if not np.isfinite(lam) else float(lam), "surface": surf,
        "slices": slice_table(s, F, lam, table_method, analysis.interslice, analysis.interslice_points),
        "all_methods": all_methods,
        "slice_x": [float(v) for v in ((-s.xb[::-1]) if s.mirrored else s.xb)],
        "driving_direction": "right" if s.mirrored else "left",
        "tension_crack": s.crack,
    }
    if drawdown:
        res["drawdown"] = dict(best_stages or {}, level=float(analysis.drawdown_level),
                               line_after=drawdown_line(project, analysis, gp))
    if analysis.probabilistic and not drawdown:
        res["probability"] = run_probabilistic(project, analysis, s)
    if analysis.sensitivity_param:
        res["sensitivity"] = run_sensitivity(project, analysis, s)
    return res


def _sample(rng, dist, mu, sd):
    if dist == "lognormal":
        mu_ = np.maximum(mu, 1e-12)
        s2 = np.log(1.0 + (sd / mu_) ** 2)
        return np.where(sd > 0, rng.lognormal(np.log(mu_) - 0.5 * s2, np.sqrt(s2)), mu)
    if dist == "uniform":
        h = math.sqrt(3.0) * sd
        return rng.uniform(mu - h, mu + h)
    return rng.normal(mu, sd)


def run_probabilistic(project, analysis, s: SliceSet) -> dict:
    """Monte Carlo on the critical surface (normal, lognormal or uniform c, phi and unit weight)."""
    rng = np.random.default_rng(analysis.seed)
    ml = {m.id: m for m in project.materials}
    mats = [ml[mid] for mid in s.mat_ids]
    dist = np.array([m.distribution for m in mats])
    par = {k: (np.array([getattr(m, k) for m in mats]), np.array([getattr(m, k + "_sd") for m in mats]))
           for k in ("unit_weight", "cohesion", "phi")}
    n = max(10, int(analysis.n_samples))
    fs = []
    for _ in range(n):
        v = {}
        for k, (mu, sd) in par.items():
            v[k] = np.array([_sample(rng, dist[j], mu[j], sd[j]) for j in range(len(mats))], dtype=float)
        g = np.clip(v["unit_weight"], 1e-6, None)
        c = np.clip(v["cohesion"], 0.0, None)
        p = np.clip(v["phi"], 0.0, 89.0)
        set_strength(s, project.materials, g, c, p)
        F, _ = factor_of_safety(s, analysis.method if analysis.method != "finite_element" else "morgenstern_price",
                                analysis.interslice, analysis.interslice_points)
        if np.isfinite(F):
            fs.append(F)
    set_strength(s, project.materials)
    fs = np.array(fs)
    if len(fs) == 0:
        return {"n": 0}
    mean, sd = float(fs.mean()), float(fs.std(ddof=1)) if len(fs) > 1 else 0.0
    hist, edges = np.histogram(fs, bins=20)
    return {"n": int(len(fs)), "mean": mean, "sd": sd, "min": float(fs.min()), "max": float(fs.max()),
            "pf": float((fs < 1.0).mean()), "reliability_index": (mean - 1.0) / sd if sd > 0 else None,
            "histogram": hist.tolist(), "hist_edges": edges.tolist()}


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
    method = analysis.method if analysis.method != "finite_element" else "morgenstern_price"
    out = []
    for v in xs:
        setattr(target, prop, float(v))
        set_strength(s, mats)
        F, _ = factor_of_safety(s, method, analysis.interslice, analysis.interslice_points)
        out.append(float(F) if np.isfinite(F) else None)
    set_strength(s, project.materials)
    return {"param": analysis.sensitivity_param, "values": xs.tolist(), "fos": out}
