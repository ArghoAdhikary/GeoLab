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
    lines = list(getattr(project, "mesh_lines", []) or [])
    lines += [st.points for st in getattr(project, "structures", []) or [] if len(st.points) >= 2]
    for line in lines:     # interior lines (drains, structures): nodes along them
        for (x1, y1), (x2, y2) in zip(line[:-1], line[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            k = max(1, int(math.ceil(L / size)))
            for j in range(k + 1):
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


KELVIN = 9.81 * 0.018016 / (8.314 * 293.15)     # g Mw / (R T): per metre of pressure head


def evaporation_ratio(hp, air_humidity=0.5):
    """Actual / potential evaporation from the surface pressure head (Wilson, Fredlund & Barbour 1994):
    the soil surface relative humidity follows Kelvin's law, hr = exp(hp g Mw / R T), and
    AE / PE = (hr - ha) / (1 - ha). Wet soil evaporates at the potential rate."""
    hr = np.exp(KELVIN * np.minimum(np.asarray(hp, float), 0.0))
    ha = min(max(air_humidity, 0.0), 0.99)
    return np.clip((hr - ha) / (1.0 - ha), 0.0, 1.0)


def feddes_alpha(hp, length_factor=1.0):
    """Root water uptake reduction (Feddes et al. 1978) from the pressure head: no uptake when
    saturated, full uptake between -0.25 m and -4 m, falling to zero at wilting (-150 m)."""
    hp = np.asarray(hp, float) / length_factor            # to metres
    a = np.ones_like(hp)
    a = np.where(hp > -0.25, np.clip(-hp / 0.25, 0.0, 1.0), a)
    a = np.where(hp < -4.0, np.clip((hp + 150.0) / 146.0, 0.0, 1.0), a)
    return a


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
            Aw = getattr(mesh, "Aw", mesh.A)          # axisymmetric: area x radius
            a = np.bincount(mesh.tris[e].ravel(), weights=np.repeat(Aw[e] / 3.0, 3), minlength=mesh.nn)
            self.w[m.id] = a / mesh.lump
        self.y = mesh.nodes[:, 1]
        self.gw = project.gamma_w
        tol = 0.1 * analysis.mesh_size
        self.bcs = []
        self.review_nodes: set[int] = set()     # potential seepage face
        self.infil_nodes: set[int] = set()      # infiltration with ponding review
        self.active: set[int] = set()           # review nodes currently held at h = y
        for bc in project.bcs("hydraulic", analysis):
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
            if bc.type in ("seepage_face", "head"):
                self.review_nodes.update(nodes)
            elif bc.type in ("infiltration", "climate"):
                self.infil_nodes.update(nodes)
        # plants on climate boundaries: root zone nodes and their share of the potential transpiration
        self.length_factor = 1.0 if project.units == "metric" else 3.28084
        self.roots = []
        for bc, nodes, edges, _m in self.bcs:
            if bc.type != "climate" or bc.root_depth <= 0 or not (bc.value3 > 0 or bc.fn3):
                continue
            xs = [p[0] for p in bc.points]
            x0, x1 = min(xs), max(xs)
            px = mesh.nodes[:, 0]
            inside = (px >= x0 - 1e-9) & (px <= x1 + 1e-9)
            z = np.where(inside, polyline_y(sorted(bc.points), px) - self.y, -1.0)
            Lr = bc.root_depth
            g = np.where((z >= -1e-9) & (z <= Lr), 2.0 * (1.0 - np.clip(z, 0, Lr) / Lr) / Lr, 0.0)
            w = mesh.lump * g
            if w.sum() <= 0:
                raise ValueError(f"Climate boundary '{bc.name}': the root zone has no mesh nodes; "
                                 "make the root depth larger than the mesh size.")
            w *= (x1 - x0) / w.sum()          # the whole zone takes up PT x the boundary width
            idx = np.nonzero(w)[0]
            self.roots.append((bc, idx, w[idx]))
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
                # nodes above the water level are not submerged: they become potential seepage face
                for i in nodes:
                    if self.y[i] <= v + 1e-9:
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
            elif bc.type == "climate":
                rain, evap = self.climate_rates(bc, edges, t, h)
                flux += self.m.edge_load(edges, rain - evap)
        for bc, idx, w in self.roots:
            flux[idx] -= self.uptake(bc, idx, w, t, h)
        for i in self.active:
            fixed.setdefault(i, self.y[i])
        return fixed, flux, None

    def uptake(self, bc, idx, w, t, h):
        """Actual root water uptake (volume per time) at the root zone nodes."""
        pt = max(bc.at3(t), 0.0)
        return pt * w * feddes_alpha(h[idx] - self.y[idx], self.length_factor)

    def climate_rates(self, bc, edges, t, h):
        """Rainfall and actual evaporation (per unit area) on each edge of a climate boundary."""
        rain = max(bc.at(t), 0.0)
        pe = max(bc.at2(t), 0.0)
        hp = np.array([0.5 * (h[a] - self.y[a] + h[b] - self.y[b]) for a, b in edges])
        return np.full(len(edges), rain), pe * evaporation_ratio(hp, bc.humidity)

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
    if not project.bcs("hydraulic", analysis):
        raise ValueError("No boundary conditions are defined. Draw at least one head boundary condition.")
    nodes, tris, tmat = generate_mesh(project, analysis.mesh_size)
    if getattr(analysis, "axisymmetric", False):
        from .seep3d import T3Axi
        mesh = T3Axi(nodes, tris, tmat)
    else:
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

    climate = {"rainfall": 0.0, "evaporation": 0.0, "runoff": 0.0, "transpiration": 0.0,
               "potential_transpiration": 0.0}

    def on_step(k, t, h, react):
        if t is None:
            return
        _, flux, _ = prob.boundary(t, h)
        dt = t - net_in[1]
        net_in[0] += dt * float(react.sum() + flux.sum())
        net_in[1] = t
        for bc, nodes, edges, _m in prob.bcs:
            if bc.type != "climate":
                continue
            L = np.array([np.hypot(*(mesh.nodes[b] - mesh.nodes[a])) for a, b in edges])
            rain, evap = prob.climate_rates(bc, edges, t, h)
            climate["rainfall"] += dt * float(np.sum(rain * L))
            climate["evaporation"] += dt * float(np.sum(evap * L))
            climate["runoff"] += dt * float(sum(-react[i] for i in nodes if i in prob.active and react[i] < 0))
        for bc, idx, w in prob.roots:
            climate["transpiration"] += dt * float(prob.uptake(bc, idx, w, t, h).sum())
            climate["potential_transpiration"] += dt * float(max(bc.at3(t), 0.0) * w.sum())
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
        if any(bc.type == "climate" for bc, *_ in prob.bcs):
            res["climate"] = climate
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
