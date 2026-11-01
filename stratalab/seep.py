"""Steady-state 2D seepage by the finite element method (linear triangles).

Solves div(k kr(p) grad h) = 0 for total head h. Saturated/unsaturated flow uses a
Gardner relative conductivity kr = exp(alpha * pressure_head) for negative pressure
head, which lets the phreatic surface develop naturally. Potential seepage faces are
handled by the standard review iteration.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.spatial import Delaunay

from .geometry import dist_point_polyline, point_in_polygon, validate_geometry

KR_MIN = 1e-6


# ---------------------------------------------------------------------------
# Mesh
# ---------------------------------------------------------------------------
def generate_mesh(project, size: float):
    """Unstructured triangle mesh of all regions. Returns (nodes, tris, tri_material_ids)."""
    if size <= 0:
        raise ValueError("Mesh size must be positive.")
    regions = [r for r in project.regions if project.material(r.material_id) is not None]
    if not regions:
        raise ValueError("No regions with materials to mesh.")
    key = lambda x, y: (round(x, 6), round(y, 6))
    pts: dict = {}
    segs = []
    for r in regions:
        n = len(r.points)
        for i in range(n):
            (x1, y1), (x2, y2) = r.points[i], r.points[(i + 1) % n]
            L = math.hypot(x2 - x1, y2 - y1)
            k = max(1, int(math.ceil(L / size)))
            for j in range(k):
                t = j / k
                x, y = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                pts.setdefault(key(x, y), (x, y))
            segs.append((x1, y1, x2, y2))
    bnd = np.array(list(pts.values()))
    xs = [p[0] for r in regions for p in r.points]
    ys = [p[1] for r in regions for p in r.points]
    gx = np.arange(min(xs) + 0.5 * size, max(xs), size)
    gy = np.arange(min(ys) + 0.5 * size * 0.866, max(ys), size * 0.866)
    interior = []
    S = np.array(segs)
    for j, y in enumerate(gy):
        off = 0.5 * size if j % 2 else 0.0
        for x in gx + off:
            if not any(point_in_polygon(x, y, r.points) for r in regions):
                continue
            # distance to all boundary segments (vectorized)
            dx, dy = S[:, 2] - S[:, 0], S[:, 3] - S[:, 1]
            L2 = np.maximum(dx * dx + dy * dy, 1e-30)
            t = np.clip(((x - S[:, 0]) * dx + (y - S[:, 1]) * dy) / L2, 0, 1)
            d = np.hypot(x - (S[:, 0] + t * dx), y - (S[:, 1] + t * dy)).min()
            if d > 0.45 * size:
                interior.append((x, y))
    nodes = np.vstack([bnd, np.array(interior).reshape(-1, 2)])
    tri = Delaunay(nodes).simplices
    keep, mats = [], []
    for t in tri:
        p = nodes[t]
        area = 0.5 * ((p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1]))
        if abs(area) < 1e-12 * size * size:
            continue
        cx, cy = p.mean(axis=0)
        for r in regions:
            if point_in_polygon(cx, cy, r.points):
                keep.append(t if area > 0 else t[[0, 2, 1]])
                mats.append(r.material_id)
                break
    if not keep:
        raise ValueError("Mesh generation produced no elements.")
    tris = np.array(keep)
    used = np.unique(tris)
    remap = -np.ones(len(nodes), dtype=int)
    remap[used] = np.arange(len(used))
    return nodes[used], remap[tris], np.array(mats)


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
def _bc_nodes(nodes, pts, tol):
    return [i for i, (x, y) in enumerate(nodes) if dist_point_polyline(x, y, pts) <= tol]


def _tributary(nodes, idx, pts):
    """Boundary length associated with each node along a polyline (for flux loads)."""
    if len(idx) == 1:
        return np.array([0.0])
    # arc-length position of each node projected on the polyline
    seg = np.array([[*pts[i], *pts[i + 1]] for i in range(len(pts) - 1)], dtype=float)
    cum = np.concatenate(([0.0], np.cumsum(np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]))))
    s = []
    for i in idx:
        x, y = nodes[i]
        best, sbest = math.inf, 0.0
        for k, (x1, y1, x2, y2) in enumerate(seg):
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy or 1e-30
            t = min(1.0, max(0.0, ((x - x1) * dx + (y - y1) * dy) / L2))
            d = math.hypot(x - x1 - t * dx, y - y1 - t * dy)
            if d < best:
                best, sbest = d, cum[k] + t * math.sqrt(L2)
        s.append(sbest)
    s = np.array(s)
    order = np.argsort(s)
    ss = s[order]
    gaps = np.diff(ss)
    trib = np.zeros(len(idx))
    trib_sorted = np.zeros(len(idx))
    trib_sorted[:-1] += 0.5 * gaps
    trib_sorted[1:] += 0.5 * gaps
    trib[order] = trib_sorted
    return trib


def run_seepage(project, analysis, progress=None, cancel=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if not project.boundary_conditions:
        raise ValueError("No boundary conditions are defined. Draw at least one head boundary condition.")
    nodes, tris, tmat = generate_mesh(project, analysis.mesh_size)
    nn, ne = len(nodes), len(tris)
    mats = {m.id: m for m in project.materials}
    ks = np.array([mats[m].k_sat for m in tmat])
    kr_ratio = np.array([mats[m].k_ratio for m in tmat])
    alpha = np.array([mats[m].unsat_alpha for m in tmat])
    if np.any(ks <= 0):
        raise ValueError("Saturated hydraulic conductivity must be positive for every material.")
    P = nodes[tris]                                   # ne x 3 x 2
    x, y = P[:, :, 0], P[:, :, 1]
    b = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], axis=1)
    c = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], axis=1)
    A = 0.5 * (b[:, 0] * c[:, 1] - b[:, 1] * c[:, 0])
    Kb = np.einsum("ei,ej->eij", b, b) / (4 * A)[:, None, None]
    Kc = np.einsum("ei,ej->eij", c, c) / (4 * A)[:, None, None]
    rows = np.repeat(tris, 3, axis=1).ravel()
    cols = np.tile(tris, (1, 3)).ravel()
    yc = y.mean(axis=1)

    tol = 0.1 * analysis.mesh_size
    fixed: dict[int, float] = {}
    flux = np.zeros(nn)
    review: set[int] = set()
    for bc in project.boundary_conditions:
        idx = _bc_nodes(nodes, bc.points, tol)
        if not idx:
            raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node. "
                             "Draw it along the edge of a region.")
        if bc.type == "head":
            for i in idx:
                fixed[i] = bc.value
        elif bc.type == "pressure_head":
            for i in idx:
                fixed[i] = nodes[i, 1] + bc.value
        elif bc.type == "flux":
            flux[idx] += bc.value * _tributary(nodes, idx, bc.points)
        elif bc.type == "seepage_face":
            review.update(i for i in idx if i not in fixed)
        else:
            raise ValueError(f"Unknown boundary condition type '{bc.type}'.")
    if not fixed:
        raise ValueError("At least one head or pressure-head boundary condition is required.")

    h = np.full(nn, max(fixed.values()))
    for i, v in fixed.items():
        h[i] = v
    active_review: set[int] = set()
    converged = False
    it = 0
    history = []
    for it in range(1, analysis.max_iter + 1):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        if analysis.unsaturated:
            hp_e = h[tris].mean(axis=1) - yc
            kr = np.where(hp_e >= 0, 1.0, np.maximum(np.exp(alpha * np.minimum(hp_e, 0)), KR_MIN))
        else:
            kr = np.ones(ne)
        kx = ks * kr
        Ke = kx[:, None, None] * (Kb + kr_ratio[:, None, None] * Kc)
        K = coo_matrix((Ke.ravel(), (rows, cols)), shape=(nn, nn)).tocsr()
        fx = dict(fixed)
        for i in active_review:
            fx[i] = nodes[i, 1]
        fidx = np.array(sorted(fx))
        fval = np.array([fx[i] for i in fidx])
        free = np.setdiff1d(np.arange(nn), fidx)
        hn = np.empty(nn)
        hn[fidx] = fval
        rhs = flux[free] - K[free][:, fidx] @ fval
        hn[free] = spsolve(K[free][:, free].tocsc(), rhs)
        if not np.all(np.isfinite(hn)):
            raise RuntimeError("The seepage solver produced invalid values. Check conductivities and boundary conditions.")
        # seepage face review
        react = K @ hn - flux
        changed = False
        for i in review:
            if i in active_review:
                if react[i] > 1e-12 * max(1.0, np.abs(react).max()):   # would need inflow: release
                    active_review.discard(i); changed = True
            elif hn[i] > nodes[i, 1] + 1e-9:
                active_review.add(i); changed = True
        dh = float(np.max(np.abs(hn - h)))
        relax = 0.6 if analysis.unsaturated else 1.0
        h = relax * hn + (1 - relax) * h if it > 1 else hn
        history.append(dh)
        if progress:
            progress(min(99, int(100 * it / analysis.max_iter)))
        if dh < analysis.tolerance and not changed:
            h = hn
            converged = True
            break
        if not analysis.unsaturated and not review:
            h = hn
            converged = True
            break
    # final consistent fields
    if analysis.unsaturated:
        hp_e = h[tris].mean(axis=1) - yc
        kr = np.where(hp_e >= 0, 1.0, np.maximum(np.exp(alpha * np.minimum(hp_e, 0)), KR_MIN))
    else:
        kr = np.ones(ne)
    kx = ks * kr
    Ke = kx[:, None, None] * (Kb + kr_ratio[:, None, None] * Kc)
    K = coo_matrix((Ke.ravel(), (rows, cols)), shape=(nn, nn)).tocsr()
    react = K @ h - flux
    fixed_all = set(fixed) | active_review
    inflow = float(sum(react[i] for i in fixed_all if react[i] > 0) + flux[flux > 0].sum())
    outflow = float(-sum(react[i] for i in fixed_all if react[i] < 0) - flux[flux < 0].sum())
    gx = (b * h[tris]).sum(axis=1) / (2 * A)
    gy = (c * h[tris]).sum(axis=1) / (2 * A)
    vx, vy = -kx * gx, -kx * kr_ratio * gy
    hp = h - nodes[:, 1]
    return {
        "type": "seepage", "converged": converged, "iterations": it, "history": history,
        "nodes": nodes.tolist(), "tris": tris.tolist(), "tri_material": tmat.tolist(),
        "head": h.tolist(), "pressure_head": hp.tolist(),
        "pore_pressure": (hp * project.gamma_w).tolist(),
        "vx": vx.tolist(), "vy": vy.tolist(), "inflow": inflow, "outflow": outflow,
        "seepage_face_nodes": sorted(int(i) for i in active_review),
        "phreatic": phreatic_segments(nodes, tris, hp),
    }


def phreatic_segments(nodes, tris, hp):
    """Zero pressure-head contour as a list of segments [[x1, y1, x2, y2], ...]."""
    return contour_segments(nodes, tris, hp, 0.0)


def contour_segments(nodes, tris, values, level):
    nodes = np.asarray(nodes); values = np.asarray(values)
    out = []
    for t in np.asarray(tris):
        v = values[t] - level
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            va, vb = v[a], v[b]
            if (va < 0) != (vb < 0):
                s = va / (va - vb)
                pa, pb = nodes[t[a]], nodes[t[b]]
                pts.append(pa + s * (pb - pa))
        if len(pts) == 2:
            out.append([float(pts[0][0]), float(pts[0][1]), float(pts[1][0]), float(pts[1][1])])
    return out


def pressure_head_interpolator(results):
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    nodes = np.asarray(results["nodes"])
    hp = np.asarray(results["pressure_head"])
    lin = LinearNDInterpolator(nodes, hp)
    near = NearestNDInterpolator(nodes, hp)

    def f(x, y):
        x = np.atleast_1d(np.asarray(x, dtype=float)); y = np.atleast_1d(np.asarray(y, dtype=float))
        v = lin(x, y)
        bad = ~np.isfinite(v)
        if bad.any():
            v[bad] = near(x[bad], y[bad])
        return v
    return f
