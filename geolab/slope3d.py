"""3D slope stability: the cross-section is extruded over a width, and the slip surface is an
ellipsoid of revolution about an axis parallel to the slope (z), so a slide of finite length
can be checked.

The ellipsoid  ((x - xc)^2 + (y - yc)^2) / R^2 + ((z - zc) / b)^2 = 1  cuts every section
z = const in a circle of radius R_z = R sqrt(1 - ((z - zc) / b)^2) about the same centre. The
sliding mass is cut into columns: the slices of each section circle times a strip width dz.

Factor of safety: 3D Bishop simplified (Hungr 1987). Each column is in vertical equilibrium
with no shear between columns, and the whole mass in moment equilibrium about the rotation
axis (xc, yc) parallel to z:

    N = (W - (c A - u A tan phi) sin(a) / F) / (n_y + sin(a) tan phi / F)
    F = sum[(c A + (N - u A) tan phi) R_z] / sum[W dx - M_H]

where A is the true base area of the column (its plan area / n_y), n_y the vertical component
of the base normal (it also tilts in z near the ends), a the dip of the base in the section and
dx the horizontal distance to the axis. For a very long ellipsoid every section is the same
circle and the result equals 2D Bishop simplified exactly; a slide of finite length gains
strength from its curved ends, so F3D >= F2D for the same section.

Surcharges and point loads can be limited to part of the width (a building or stockpile of
finite length), and pore pressure can come from a 3D seepage analysis.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .geometry import GroundProfile
from .slope import build_slices, circle_surface, make_pwp_fn, run_slope

N_STRIPS = 20
MIN_NY = 0.2


def _strip_z(z0, z1, zc, b, n):
    """Strip mid points and widths between z0 and z1, finer near the ends of the ellipsoid."""
    lo, hi = max(z0, zc - b), min(z1, zc + b)
    if hi <= lo:
        return np.zeros(0), np.zeros(0)
    # uniform in theta with z = zc + b sin(theta): small strips where the radius changes fast
    t0, t1 = math.asin(max(-1.0, (lo - zc) / b)), math.asin(min(1.0, (hi - zc) / b))
    th = np.linspace(t0, t1, n + 1)
    zb = zc + b * np.sin(th)
    return 0.5 * (zb[:-1] + zb[1:]), np.diff(zb)


class Model3D:
    """Everything needed to evaluate ellipsoidal slip surfaces on one extruded section."""

    def __init__(self, project, analysis, seep_results=None, n_strips=N_STRIPS, excess_fn=None):
        self.project = project
        self.a2 = copy.copy(analysis)
        self.a2.three_d = False
        self.W = float(analysis.width3d)
        if self.W <= 0:
            raise ValueError("The 3D width must be positive.")
        self.gp = GroundProfile(project.regions)
        self.n = int(n_strips)
        z1, z2 = float(analysis.load_z1), float(analysis.load_z2)
        self.band = (min(z1, z2), max(z1, z2)) if abs(z2 - z1) > 1e-9 else None
        self.unloaded = None
        if self.band is not None:
            self.unloaded = project.copy()
            self.unloaded.surcharges = []
            self.unloaded.point_loads = []
        self.seep3d = seep_results if seep_results and seep_results.get("three_d") else None
        self._pwp2d = make_pwp_fn(project, analysis, None if self.seep3d else seep_results)
        self._pwp_cache = {}
        self.excess_fn = excess_fn
        if excess_fn is not None and analysis.pwp not in ("piezometric", "seepage"):
            self.a2.pwp = "piezometric"

    def pwp_fn(self, z):
        if self.seep3d is None:
            base = self._pwp2d
        else:
            from .seep3d import pressure_head_at_z
            key = round(float(z), 3)
            if key not in self._pwp_cache:
                self._pwp_cache[key] = pressure_head_at_z(self.seep3d, z)
            base = self._pwp_cache[key]
        if self.excess_fn is None:
            return base
        ex, gw = self.excess_fn, self.project.gamma_w

        def f(x, y):
            b = base(x, y) if base is not None else np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape)
            return np.asarray(b, float) + np.asarray(ex(x, y), float) / gw
        return f

    def project_at(self, z):
        if self.band is not None and not (self.band[0] - 1e-9 <= z <= self.band[1] + 1e-9):
            return self.unloaded
        return self.project

    def columns(self, xc, yc, R, b, zc):
        """Column arrays of one ellipsoid, or None when it does not make a sliding mass."""
        zs, dz = _strip_z(0.0, self.W, zc, b, self.n)
        rows = []
        for z, w in zip(zs, dz):
            zeta = (z - zc) / b
            Rz = R * math.sqrt(max(0.0, 1.0 - zeta * zeta))
            if Rz <= 1e-6:
                continue
            s, why = build_slices(self.project_at(z), self.a2, circle_surface(xc, yc, Rz), self.pwp_fn(z), self.gp)
            if s is None:
                continue
            S = np.maximum(s.ay - s.yb, 1e-9)
            fx = np.tan(s.alpha)
            fz = R * R * zeta / (b * S)
            ny = 1.0 / np.sqrt(1.0 + fx * fx + fz * fz)
            rows.append(dict(z=z, dz=w, Rz=Rz, s=s, ny=ny, sa=np.sin(s.alpha), dx=s.xm - s.ax))
        if not rows:
            return None
        cat = lambda f: np.concatenate([f(r) for r in rows])
        s_all = [r["s"] for r in rows]
        dzs = cat(lambda r: np.full(r["s"].n, r["dz"]))
        ny = cat(lambda r: r["ny"])
        plan = cat(lambda r: r["s"].b) * dzs
        cols = dict(
            W=cat(lambda r: r["s"].W + r["s"].Wfd) * dzs,
            MH=cat(lambda r: r["s"].MH + r["s"].MHfd) * dzs,
            c=cat(lambda r: r["s"].c), tanphi=cat(lambda r: r["s"].tanphi),
            tanphib=cat(lambda r: r["s"].tanphib), up=cat(lambda r: r["s"].up), um=cat(lambda r: r["s"].um),
            ny=np.maximum(ny, MIN_NY), sa=cat(lambda r: r["sa"]), dx=cat(lambda r: r["dx"]),
            Rz=cat(lambda r: np.full(r["s"].n, r["Rz"])), A=plan / np.maximum(ny, MIN_NY),
            volume=float(sum(r["s"].area.sum() * r["dz"] for r in rows)),
            strips=[[float(r["z"]), float(r["Rz"])] for r in rows], n=int(sum(x.n for x in s_all)),
        )
        return cols

    def fos(self, xc, yc, R, b, zc, F0=1.0):
        c = self.columns(xc, yc, R, b, zc)
        if c is None:
            return math.nan, None
        return bishop_3d(c, F0), c


def bishop_3d(c, F0=1.0, tol=1e-6, it=200):
    """3D Bishop simplified (Hungr 1987) factor of safety of a set of columns."""
    A = c["A"]
    drive = float(np.sum(c["W"] * c["dx"] - c["MH"]))
    if not drive > 0:
        return math.nan
    F = F0 if np.isfinite(F0) and F0 > 0 else 1.0
    for _ in range(it):
        ma = np.maximum(c["ny"] + c["sa"] * c["tanphi"] / F, MIN_NY)
        Ac = c["c"] * A - c["up"] * A * c["tanphi"] + c["um"] * A * c["tanphib"]
        N = (c["W"] - Ac * c["sa"] / F) / ma
        T = c["c"] * A + np.clip(N - c["up"] * A, 0.0, None) * c["tanphi"] + c["um"] * A * c["tanphib"]
        Fn = float(np.sum(T * c["Rz"])) / drive
        if not np.isfinite(Fn) or Fn <= 0:
            return math.nan
        if abs(Fn - F) < tol:
            return Fn
        F = Fn
    return math.nan


def _distinct_circles(trials, k):
    out = []
    for t in trials:
        s = t["surface"]
        if s.get("type") != "circle":
            continue
        if any(abs(s["xc"] - o["xc"]) + abs(s["yc"] - o["yc"]) + abs(s["R"] - o["R"]) < 0.02 * s["R"] for o in out):
            continue
        out.append(s)
        if len(out) >= k:
            break
    return out


def run_slope3d(project, analysis, seep_results=None, progress=None, cancel=None, stress_results=None,
                excess_fn=None) -> dict:
    """2D search on the section, then ellipsoids of several lengths about the best circles, then a
    local refinement of the most critical one."""
    if analysis.method == "finite_element":
        raise ValueError("3D slope stability uses limit equilibrium (3D Bishop), not the finite element "
                         "stress method.")
    if getattr(analysis, "rapid_drawdown", False):
        raise ValueError("Rapid drawdown is not available in 3D.")
    a2 = copy.copy(analysis)
    a2.three_d = False
    a2.optimize = False
    a2.probabilistic = False
    a2.sensitivity_param = ""
    a2.method = "bishop"
    if a2.search.mode == "auto":
        a2.search = copy.copy(a2.search)
    seep2d = seep_results
    if seep_results and seep_results.get("three_d"):
        from .seep3d import slice_results
        seep2d = slice_results(seep_results, analysis.slide_center_z if analysis.slide_center_z >= 0
                               else 0.5 * analysis.width3d)
    res = run_slope(project, a2, seep2d, (lambda p: progress(int(0.3 * p))) if progress else None, cancel,
                    excess_fn=excess_fn)
    if not res.get("critical"):
        return res
    if res["critical"]["surface"].get("type") != "circle":
        raise ValueError("3D slope stability needs a circular slip surface search (entry and exit, grid "
                         "and radius, grid and tangent, or auto).")
    m3 = Model3D(project, analysis, seep_results, excess_fn=excess_fn)
    W = m3.W
    zc = float(analysis.slide_center_z) if analysis.slide_center_z >= 0 else 0.5 * W
    if m3.band is not None and analysis.slide_center_z < 0:
        zc = 0.5 * (m3.band[0] + m3.band[1])
    flat = [v[0] if isinstance(v, (list, tuple)) else v for v in (analysis.slide_lengths or [])]
    lengths = sorted(float(v) for v in flat if float(v) > 0)
    if not lengths:
        lengths = [f * W for f in (0.25, 0.5, 0.75, 1.0, 1.5)]
    F2 = float(res["critical"]["fos"])
    circles = _distinct_circles(res["trials"], 10)
    best = None
    by_len = []
    total = len(lengths) * len(circles) + 60
    done = 0
    for L in lengths:
        b = 0.5 * L
        best_L = None
        for cs in circles:
            if cancel and cancel():
                raise RuntimeError("Cancelled")
            F, cols = m3.fos(cs["xc"], cs["yc"], cs["R"], b, zc, F2)
            done += 1
            if np.isfinite(F) and (best_L is None or F < best_L[0]):
                best_L = (F, cs, b)
            if progress and done % 5 == 0:
                progress(30 + int(60 * done / total))
        by_len.append([L, None if best_L is None else float(best_L[0])])
        if best_L is not None and (best is None or best_L[0] < best[0]):
            best = best_L
    if best is None:
        res["three_d"] = {"error": "No ellipsoid of the trial lengths cuts the ground inside the width."}
        return res
    # local refinement of centre and radius (pattern search) at the critical length
    F, cs, b = best
    p = np.array([cs["xc"], cs["yc"], cs["R"]], float)
    step = 0.05 * cs["R"]
    for _ in range(60):
        if step < 0.002 * cs["R"]:
            break
        improved = False
        for k in range(3):
            for sgn in (1, -1):
                q = p.copy()
                q[k] += sgn * step
                if q[2] <= 0:
                    continue
                Fq, _ = m3.fos(q[0], q[1], q[2], b, zc, F)
                if np.isfinite(Fq) and Fq < F - 1e-6:
                    F, p, improved = Fq, q, True
        if not improved:
            step *= 0.5
    F3, cols = m3.fos(p[0], p[1], p[2], b, zc, F)
    weight = float(np.sum(cols["W"]))
    res["three_d"] = {
        "fos": float(F3), "fos_2d": F2, "ratio": float(F3 / F2) if F2 > 0 else None,
        "method": "3D Bishop simplified (Hungr 1987)", "xc": float(p[0]), "yc": float(p[1]), "R": float(p[2]),
        "length": float(2 * b), "zc": float(zc), "width": W, "by_length": by_len, "columns": cols["n"],
        "volume": cols["volume"], "weight": weight, "strips": cols["strips"],
        "load_band": list(m3.band) if m3.band else None,
    }
    res["critical"]["fos3d"] = float(F3)
    res["fos3d"] = float(F3)
    if progress:
        progress(100)
    return res


def text_report(res, units_len="m") -> str:
    t = res.get("three_d") or {}
    if "error" in t:
        return "3D: " + t["error"]
    L = [f"3D slope stability, {t['method']}",
         f"Width of the model {t['width']:.1f} {units_len}; slide centre at z = {t['zc']:.1f} {units_len}",
         f"Critical ellipsoid: centre ({t['xc']:.2f}, {t['yc']:.2f}), radius {t['R']:.2f}, length {t['length']:.1f} {units_len}",
         f"Factor of safety 3D = {t['fos']:.3f}   (2D Bishop of the section = {t['fos_2d']:.3f})",
         f"Sliding volume {t['volume']:.1f} {units_len}³, {t['columns']} columns", "",
         "Length of the slide   F (3D)"]
    for Lk, F in t["by_length"]:
        L.append(f"{Lk:>18.1f}   {'-' if F is None else f'{F:.3f}'}")
    return "\n".join(L)
