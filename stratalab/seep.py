"""2D seepage (saturated / unsaturated groundwater flow) by the finite element method.

Solves d(theta)/dt = div(k kr grad h) for total head h (Richards' equation), steady or
transient. Unsaturated soils use Gardner or van Genuchten-Mualem functions; saturated
storage comes from the coefficient of volume compressibility (Ss = mv * gamma_w).
The phreatic surface develops naturally, and potential seepage faces and infiltration
boundaries are handled by a review iteration.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import Delaunay

from .fe import DiffusionProblem, T3, interpolator, section_flux, solve_diffusion, time_steps
from .geometry import point_in_polygon, polyline_y, validate_geometry

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
# Hydraulic functions
# ---------------------------------------------------------------------------
def water_content(m, hp, gamma_w):
    """Volumetric water content and its derivative with respect to pressure head."""
    hp = np.asarray(hp, float)
    Ss = m.mv * gamma_w
    sat = hp >= 0
    neg = np.minimum(hp, 0.0)
    if m.hyd_model == "saturated":
        return m.theta_s + Ss * hp, np.full(hp.shape, Ss)
    if m.hyd_model == "van_genuchten":
        n = max(m.vg_n, 1.001)
        mm = 1.0 - 1.0 / n
        ah = m.vg_alpha * np.abs(neg)
        base = 1.0 + ah ** n
        unsat = m.theta_r + (m.theta_s - m.theta_r) * base ** (-mm)
        d = (m.theta_s - m.theta_r) * mm * n * m.vg_alpha * ah ** (n - 1.0) * base ** (-mm - 1.0)
    else:  # Gardner-type exponential
        e = np.exp(m.unsat_alpha * neg)
        unsat = m.theta_r + (m.theta_s - m.theta_r) * e
        d = m.unsat_alpha * (m.theta_s - m.theta_r) * e
    th = np.where(sat, m.theta_s + Ss * hp, unsat)
    dth = np.where(sat, Ss, d + 1e-12)
    return th, dth


def relative_k(m, hp, unsaturated=True):
    hp = np.asarray(hp, float)
    if not unsaturated or m.hyd_model == "saturated":
        return np.ones(hp.shape)
    neg = np.minimum(hp, 0.0)
    if m.hyd_model == "van_genuchten":
        n = max(m.vg_n, 1.001)
        mm = 1.0 - 1.0 / n
        Se = (1.0 + (m.vg_alpha * np.abs(neg)) ** n) ** (-mm)
        kr = np.sqrt(Se) * (1.0 - (1.0 - Se ** (1.0 / mm)) ** mm) ** 2
    else:
        kr = np.exp(m.unsat_alpha * neg)
    return np.where(hp >= 0, 1.0, np.maximum(kr, KR_MIN))


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
class _SeepProblem(DiffusionProblem):
    def __init__(self, project, analysis, mesh: T3):
        self.a, self.m = analysis, mesh
        mats = {m.id: m for m in project.materials}
        self.mat_list = [mats[i] for i in sorted(set(mesh.mats.tolist()))]
        self.mat_of = mats
        self.ks = np.array([mats[i].k_sat for i in mesh.mats])
        self.kratio = np.array([mats[i].k_ratio for i in mesh.mats])
        if np.any(self.ks <= 0):
            raise ValueError("Saturated hydraulic conductivity must be positive for every material.")
        self.emask = {m.id: mesh.mats == m.id for m in self.mat_list}
        self.w = {}                             # nodal weight of each material in the lumped storage
        for m in self.mat_list:
            e = self.emask[m.id]
            a = np.bincount(mesh.tris[e].ravel(), weights=np.repeat(mesh.A[e] / 3.0, 3), minlength=mesh.nn)
            self.w[m.id] = a / mesh.lump
        self.y = mesh.nodes[:, 1]
        self.gw = project.gamma_w
        tol = 0.1 * analysis.mesh_size
        self.bcs = []
        self.review_nodes: set[int] = set()     # potential seepage face
        self.infil_nodes: set[int] = set()      # infiltration with ponding review
        self.active: set[int] = set()           # review nodes currently held at h = y
        for bc in project.bcs("hydraulic"):
            nodes = mesh.nodes_on(bc.points, tol)
            if not nodes:
                raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node. "
                                 "Draw it along the edge of a region.")
            edges = mesh.edges_on(bc.points, tol)
            edge_mat = []
            for a, b in edges:
                e = np.where((mesh.tris == a).any(1) & (mesh.tris == b).any(1))[0]
                edge_mat.append(mats[mesh.mats[e[0]]])
            self.bcs.append((bc, nodes, edges, edge_mat))
            if bc.type == "seepage_face":
                self.review_nodes.update(nodes)
            elif bc.type == "infiltration":
                self.infil_nodes.update(nodes)
        if not any(bc.type in ("head", "pressure_head") for bc, *_ in self.bcs) and not self.review_nodes:
            raise ValueError("At least one head or pressure-head boundary condition is required.")

    def conductivity(self, h):
        # element value = mean of the nodal relative conductivities (robust across sharp fronts)
        hp_n = (h - self.y)[self.m.tris]
        kr = np.ones(self.m.ne)
        for m in self.mat_list:
            e = self.emask[m.id]
            kr[e] = relative_k(m, hp_n[e], self.a.unsaturated).mean(axis=1)
        kx = self.ks * kr
        return kx, kx * self.kratio

    def storage(self, h):
        hp = h - self.y
        S = np.zeros(self.m.nn)
        dS = np.zeros(self.m.nn)
        for m in self.mat_list:
            th, dth = water_content(m, hp, self.gw)
            S += self.w[m.id] * th
            dS += self.w[m.id] * dth
        return S, dS

    def boundary(self, t, h):
        fixed: dict[int, float] = {}
        flux = np.zeros(self.m.nn)
        for bc, nodes, edges, edge_mat in self.bcs:
            v = bc.at(t)
            if bc.type == "head":
                for i in nodes:
                    fixed[i] = v
            elif bc.type == "pressure_head":
                for i in nodes:
                    fixed[i] = self.y[i] + v
            elif bc.type in ("flux", "infiltration"):
                flux += self.m.edge_load(edges, v)
            elif bc.type == "nodal_flux":
                flux[nodes] += v / len(nodes)
            elif bc.type == "free_drainage":          # unit downward gradient: q = -k kr
                q = [-m.k_sat * float(relative_k(m, np.array([0.5 * (h[a] - self.y[a] + h[b] - self.y[b])]),
                                                 self.a.unsaturated)[0]) for (a, b), m in zip(edges, edge_mat)]
                flux += self.m.edge_load(edges, q)
        for i in self.active:
            fixed.setdefault(i, self.y[i])
        return fixed, flux, None

    def review(self, h, react, fixed, flux):
        changed = False
        big = 1e-10 * max(1.0, float(np.abs(react).max()))
        for i in self.review_nodes | self.infil_nodes:
            if i in self.active:
                if react[i] > big:                    # would need extra inflow: release
                    self.active.discard(i)
                    changed = True
            elif h[i] > self.y[i] + 1e-9 and i not in fixed:
                self.active.add(i)
                changed = True
        return changed


def _initial_head(project, analysis, mesh, parent_results):
    x, y = mesh.nodes[:, 0], mesh.nodes[:, 1]
    if analysis.initial == "parent" and parent_results and parent_results.get("type") == "seepage":
        return interpolator(parent_results["nodes"], parent_results["head"])(x, y)
    if analysis.initial == "water_table" and len(project.piezometric_line) >= 2:
        return np.asarray(polyline_y(project.piezometric_line, x), float)
    if analysis.initial == "value":
        return np.full(mesh.nn, float(analysis.initial_value))
    return None


def run_seepage(project, analysis, progress=None, cancel=None, parent_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if not project.bcs("hydraulic"):
        raise ValueError("No boundary conditions are defined. Draw at least one head boundary condition.")
    nodes, tris, tmat = generate_mesh(project, analysis.mesh_size)
    mesh = T3(nodes, tris, tmat)
    prob = _SeepProblem(project, analysis, mesh)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth) if analysis.transient else None
    h0 = _initial_head(project, analysis, mesh, parent_results)
    if h0 is None:
        if steps is not None:
            raise ValueError("A transient seepage analysis needs initial conditions: a solved parent "
                             "seepage analysis, a water table (piezometric line) or an initial head.")
        fixed, _, _ = prob.boundary(None, np.zeros(mesh.nn))
        h0 = np.full(mesh.nn, max(fixed.values()) if fixed else float(nodes[:, 1].max()))
    saved_t, saved_h = [0.0], [h0.tolist()]
    S0 = prob.storage(h0)[0]
    net_in = [0.0, 0.0]          # cumulative inflow, previous time

    def on_step(k, t, h, react):
        if t is None:
            return
        _, flux, _ = prob.boundary(t, h)
        net_in[0] += (t - net_in[1]) * float(react.sum() + flux.sum())
        net_in[1] = t
        saved_t.append(float(t))
        saved_h.append(h.tolist())
        if progress:
            progress(min(99, int(100 * (k + 1) / len(steps))))

    unsat = analysis.unsaturated and any(m.hyd_model != "saturated" for m in prob.mat_list)
    relax = (0.6 if steps is None else 0.8) if unsat else 1.0
    h, history, converged, react, it = solve_diffusion(
        mesh, prob, h0, steps, max_iter=analysis.max_iter, tol=analysis.tolerance, relax=relax,
        cancel=cancel, on_step=on_step)
    t_end = None if steps is None else float(np.sum(steps))
    kx, ky = prob.conductivity(h)
    _, flux, _ = prob.boundary(t_end, h)
    if steps is None:
        react = mesh.stiffness(kx, ky) @ h - flux
    rate = react + flux                          # boundary inflow rate at each node
    gx, gy = mesh.gradient(h)
    vx, vy = -kx * gx, -ky * gy
    hp = h - nodes[:, 1]
    th = prob.storage(h)[0]
    res = {
        "type": "seepage", "converged": converged, "iterations": it, "history": history[-200:],
        "nodes": nodes.tolist(), "tris": tris.tolist(), "tri_material": tmat.tolist(),
        "head": h.tolist(), "pressure_head": hp.tolist(),
        "pore_pressure": (hp * project.gamma_w).tolist(), "water_content": th.tolist(),
        "vx": vx.tolist(), "vy": vy.tolist(),
        "inflow": float(rate[rate > 0].sum()), "outflow": float(-rate[rate < 0].sum()),
        "seepage_face_nodes": sorted(int(i) for i in prob.active if i in prob.review_nodes),
        "phreatic": phreatic_segments(nodes, tris, hp),
        "flux_sections": {f.name: section_flux(mesh, vx, vy, f.points) for f in project.flux_sections},
    }
    if steps is not None:
        dV = float(np.sum(mesh.lump * (th - S0)))
        res.update(times=saved_t, head_history=saved_h, storage_change=dV, net_inflow=net_in[0],
                   balance_error=abs(dV - net_in[0]) / max(abs(dV), abs(net_in[0]), 1e-30))
    return res


def phreatic_segments(nodes, tris, hp):
    """Zero pressure-head contour as a list of segments [[x1, y1, x2, y2], ...]."""
    return contour_segments(nodes, tris, hp, 0.0)


def contour_segments(nodes, tris, values, level):
    nodes = np.asarray(nodes); values = np.asarray(values)
    out = []
    for t in np.asarray(tris)[:, :3]:
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
    return interpolator(results["nodes"], results["pressure_head"])
