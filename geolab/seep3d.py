"""3D seepage on an extruded section, and axisymmetric seepage.

3D: the triangle mesh of the section is extruded over the width in z into layers of 6-node
wedge (prism) elements. Steady or transient, saturated / unsaturated: the same hydraulic
functions and Picard scheme as the 2D seepage (Richards' equation for the total head), with
kz = kx. Boundary conditions drawn on the section act over the whole width or over a part of
it (z1 to z2), and wells are vertical lines at (x, z) with a fixed head or a pumping rate.

For linear wedges on a straight extrusion the element matrix splits exactly into a triangle
part and a line part:

    K = (kx Kb + ky Kc) (x) Mz  +  kz MT (x) Sz

with Kb, Kc the triangle gradient matrices, MT = A/12 [2 1 1; 1 2 1; 1 1 2] its mass matrix,
Mz = dz/6 [2 1; 1 2] and Sz = 1/dz [1 -1; -1 1].

Axisymmetric: x is the radius and the section turns about x = 0 (flow to a well, a circular
tank). Element matrices are multiplied by the radius of the element centroid; flows are
reported for the full circle (2 pi radians).
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.sparse import coo_matrix

from .fe import T3, interpolator, solve_diffusion, time_steps
from .geometry import dist_point_polyline, validate_geometry
from .seep import _SeepProblem, generate_mesh, phreatic_segments, relative_k, run_seepage, water_content

TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Axisymmetric triangles
# ---------------------------------------------------------------------------
class T3Axi(T3):
    """Triangles of an axisymmetric section: every integral carries the radius x (per radian)."""

    def __init__(self, nodes, tris, mats):
        super().__init__(nodes, tris, mats)
        if float(self.nodes[:, 0].min()) < -1e-9:
            raise ValueError("An axisymmetric model must lie at x >= 0 (x is the radius from the axis).")
        self.r = np.maximum(self.xc, 1e-9 * max(1.0, float(self.nodes[:, 0].max())))
        self.Aw = self.A * self.r
        self.lump = np.bincount(self.tris.ravel(), weights=np.repeat(self.Aw / 3.0, 3), minlength=self.nn)

    def stiffness(self, kx, ky):
        return super().stiffness(kx * self.r, ky * self.r)

    def edge_load(self, edges, q):
        f = np.zeros(self.nn)
        q = np.broadcast_to(np.asarray(q, float), (len(edges),))
        for (a, b), qq in zip(edges, q):
            L = float(np.hypot(*(self.nodes[b] - self.nodes[a])))
            ra, rb = self.nodes[a, 0], self.nodes[b, 0]
            f[a] += qq * L * (2 * ra + rb) / 6.0
            f[b] += qq * L * (ra + 2 * rb) / 6.0
        return f


def run_axisymmetric(project, analysis, progress=None, cancel=None, parent_results=None) -> dict:
    """2D seepage solved on the axisymmetric mesh; flows are for the full circle."""
    a = copy.copy(analysis)
    a.axisymmetric = True
    res = run_seepage(project, a, progress, cancel, parent_results=parent_results)
    for k in ("inflow", "outflow"):
        res[k] = float(res[k]) * TWO_PI
    res["flux_sections"] = {}        # sections are not weighted by the radius
    for k in ("storage_change", "net_inflow"):
        if k in res:
            res[k] = float(res[k]) * TWO_PI
    res["axisymmetric"] = True
    return res


# ---------------------------------------------------------------------------
# Extruded wedge mesh
# ---------------------------------------------------------------------------
class Prism:
    """Layers of linear wedges over a triangle mesh. Node id = layer * nn2 + node of the section."""

    def __init__(self, tri: T3, zs):
        self.tri = tri
        self.zs = np.asarray(zs, float)
        self.nl = len(self.zs) - 1
        self.nn2 = tri.nn
        self.nn = self.nn2 * len(self.zs)
        self.ne2 = tri.ne
        self.ne = self.ne2 * self.nl
        self.dz = np.diff(self.zs)
        self.mats = np.tile(tri.mats, self.nl)
        lay = np.repeat(np.arange(self.nl), self.ne2)
        t = np.tile(tri.tris, (self.nl, 1))
        self.conn = np.hstack([t + (lay * self.nn2)[:, None], t + ((lay + 1) * self.nn2)[:, None]])
        self.layer = lay
        self.e2 = np.tile(np.arange(self.ne2), self.nl)
        dz = self.dz[lay]
        A = tri.A[self.e2]
        MT = np.array([[2, 1, 1], [1, 2, 1], [1, 1, 2]], float) / 12.0
        self._Kxy_b = tri.Kb[self.e2]
        self._Kxy_c = tri.Kc[self.e2]
        self._MT = A[:, None, None] * MT[None]
        self._Mz = dz[:, None, None] * np.array([[2, 1], [1, 2]], float)[None] / 6.0
        self._Sz = (1.0 / dz)[:, None, None] * np.array([[1, -1], [-1, 1]], float)[None]
        self.rows = np.repeat(self.conn, 6, axis=1).ravel()
        self.cols = np.tile(self.conn, (1, 6)).ravel()
        vol = A * dz
        self.vol = vol
        self.lump = np.bincount(self.conn.ravel(), weights=np.repeat(vol / 6.0, 6), minlength=self.nn)
        self.y = np.tile(tri.nodes[:, 1], len(self.zs))
        self.x = np.tile(tri.nodes[:, 0], len(self.zs))
        self.z = np.repeat(self.zs, self.nn2)

    @staticmethod
    def _kron(T, Z):
        # local order: section node i of bottom layer (0-2), then top layer (3-5): index j*3 + i
        out = np.zeros((T.shape[0], 6, 6))
        for j in range(2):
            for l in range(2):
                out[:, 3 * j:3 * j + 3, 3 * l:3 * l + 3] = T * Z[:, j, l][:, None, None]
        return out

    def stiffness(self, kx, ky, kz=None):
        kz = kx if kz is None else kz
        Kxy = kx[:, None, None] * self._Kxy_b + ky[:, None, None] * self._Kxy_c
        Ke = self._kron(Kxy, self._Mz) + self._kron(kz[:, None, None] * self._MT, self._Sz)
        return coo_matrix((Ke.ravel(), (self.rows, self.cols)), shape=(self.nn, self.nn)).tocsr()

    def gradient(self, h):
        """Element centre gradient (gx, gy, gz)."""
        H = np.asarray(h)[self.conn]
        bot, top = H[:, :3], H[:, 3:]
        mid = 0.5 * (bot + top)
        A2 = 2 * self.tri.A[self.e2]
        gx = (self.tri.b[self.e2] * mid).sum(1) / A2
        gy = (self.tri.c[self.e2] * mid).sum(1) / A2
        gz = (top - bot).mean(1) / self.dz[self.layer]
        return gx, gy, gz

    def nodes3(self, nodes2, z1, z2):
        """3D node ids over the section nodes nodes2 between z1 and z2."""
        ks = [k for k, z in enumerate(self.zs) if z1 - 1e-9 <= z <= z2 + 1e-9]
        return [k * self.nn2 + i for k in ks for i in nodes2]

    def face_load(self, edges, q, z1, z2):
        """Nodal share of a unit flux q over the side faces of section edges between z1 and z2."""
        f = np.zeros(self.nn)
        q = np.broadcast_to(np.asarray(q, float), (len(edges),))
        for k in range(self.nl):
            za, zb = self.zs[k], self.zs[k + 1]
            if za < z1 - 1e-9 or zb > z2 + 1e-9:
                continue
            for (a, b), qq in zip(edges, q):
                L = float(np.hypot(*(self.tri.nodes[b] - self.tri.nodes[a])))
                w = 0.25 * qq * L * (zb - za)
                for i in (a, b):
                    f[k * self.nn2 + i] += w
                    f[(k + 1) * self.nn2 + i] += w
        return f


def _z_levels(width, n, extra):
    zs = set(np.linspace(0.0, width, max(1, int(n)) + 1).round(9).tolist())
    for z in extra:
        if 0 < z < width:
            zs.add(round(float(z), 9))
    zs = np.array(sorted(zs))
    keep = [zs[0]]
    for z in zs[1:]:
        if z - keep[-1] > 1e-3 * width / max(1, n):
            keep.append(z)
        else:
            keep[-1] = z if z in extra else keep[-1]
    keep[-1] = width
    return np.array(keep)


def _bc_range(bc, width):
    z1, z2 = float(getattr(bc, "z1", 0.0)), float(getattr(bc, "z2", 0.0))
    if abs(z2 - z1) < 1e-12:
        return 0.0, width
    return max(0.0, min(z1, z2)), min(width, max(z1, z2))


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
class _Seep3D(_SeepProblem):
    """Seepage problem on the wedge mesh, reusing the 2D hydraulic functions."""

    SUPPORTED = ("head", "pressure_head", "flux", "nodal_flux", "seepage_face", "infiltration")

    def __init__(self, project, analysis, tri: T3, mesh: Prism):
        self.a, self.m = analysis, mesh
        mats = {m.id: m for m in project.materials}
        self.mat_of = mats
        self.mat_list = [mats[i] for i in sorted(set(mesh.mats.tolist()))]
        self.ks = np.array([mats[i].k_sat for i in mesh.mats])
        self.kratio = np.array([mats[i].k_ratio for i in mesh.mats])
        if np.any(self.ks <= 0):
            raise ValueError("Saturated hydraulic conductivity must be positive for every material.")
        self.emask = {m.id: mesh.mats == m.id for m in self.mat_list}
        self.w = {}
        for m in self.mat_list:
            e = self.emask[m.id]
            v = np.bincount(mesh.conn[e].ravel(), weights=np.repeat(mesh.vol[e] / 6.0, 6), minlength=mesh.nn)
            self.w[m.id] = v / mesh.lump
        self.y = mesh.y
        self.gw = project.gamma_w
        self.roots = []
        width = float(mesh.zs[-1])
        tol = 0.1 * analysis.mesh_size
        self.bcs = []
        self.review_nodes, self.infil_nodes, self.active = set(), set(), set()
        for bc in project.bcs("hydraulic", analysis):
            if bc.type not in self.SUPPORTED:
                raise ValueError(f"Boundary condition '{bc.name}' ({bc.type}) is not available in 3D seepage. "
                                 "Use head, pressure head, flux, total flux, seepage face or infiltration.")
            n2 = tri.nodes_on(bc.points, tol)
            if not n2:
                raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node.")
            z1, z2 = _bc_range(bc, width)
            nodes = mesh.nodes3(n2, z1, z2)
            if not nodes:
                raise ValueError(f"Boundary condition '{bc.name}': its z range has no mesh layer.")
            self.bcs.append((bc, nodes, tri.edges_on(bc.points, tol), (z1, z2)))
            if bc.type in ("seepage_face", "head"):
                self.review_nodes.update(nodes)
            elif bc.type == "infiltration":
                self.infil_nodes.update(nodes)
        self.wells = []
        for k, w in enumerate(getattr(analysis, "wells", []) or []):
            x, z, yt, yb, kind, val = (list(w) + [0, 0, 0, 0, "head", 0][len(w):])[:6]
            if not isinstance(kind, str):          # from the settings table: 0 = fixed head, 1 = rate
                kind = "head" if float(kind) == 0 else "flow"
            yt, yb = max(float(yt), float(yb)), min(float(yt), float(yb))
            line = [[float(x), yb], [float(x), yt]]
            n2 = [i for i, (px, py) in enumerate(tri.nodes) if dist_point_polyline(px, py, line) <= tol]
            kz = int(np.argmin(np.abs(mesh.zs - float(z))))
            nodes = [kz * mesh.nn2 + i for i in n2]
            if not nodes:
                raise ValueError(f"Well {k + 1} at x = {x}, z = {z} has no mesh nodes inside the model.")
            self.wells.append((k, str(kind), float(val), nodes, (float(x), float(mesh.zs[kz]))))
        has_fixed = any(bc.type in ("head", "pressure_head") for bc, *_ in self.bcs) or \
            any(kind == "head" for _, kind, *_ in self.wells)
        if not has_fixed and not self.review_nodes:
            raise ValueError("At least one head or pressure-head boundary condition (or a well with a fixed "
                             "head) is required.")

    def conductivity(self, h):
        hp_n = (h - self.y)[self.m.conn]
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
        for bc, nodes, edges, (z1, z2) in self.bcs:
            v = bc.at(t)
            if bc.type == "head":
                for i in nodes:
                    if self.y[i] <= v + 1e-9:
                        fixed[i] = v
            elif bc.type == "pressure_head":
                for i in nodes:
                    fixed[i] = self.y[i] + v
            elif bc.type in ("flux", "infiltration"):
                flux += self.m.face_load(edges, v, z1, z2)
            elif bc.type == "nodal_flux":
                flux[nodes] += v / len(nodes)
        for _, kind, val, nodes, _xz in self.wells:
            if kind == "head":
                for i in nodes:
                    fixed[i] = val
            else:                                    # pumping rate (outflow +) shared by the screen nodes
                flux[nodes] -= val / len(nodes)
        for i in self.active:
            fixed.setdefault(i, self.y[i])
        return fixed, flux, None


def _section_mesh(project, analysis):
    """Triangle mesh of the section, with nodes along every well screen."""
    work = project
    if getattr(analysis, "wells", None):
        work = copy.copy(project)
        work.mesh_lines = list(project.mesh_lines or [])
        for w in analysis.wells:
            x, _z, yt, yb = (list(w) + [0, 0, 0, 0])[:4]
            work.mesh_lines.append([[float(x), float(min(yt, yb))], [float(x), float(max(yt, yb))]])
    nodes, tris, tmat = generate_mesh(work, analysis.mesh_size)
    return T3(nodes, tris, tmat)


def run_seepage3d(project, analysis, progress=None, cancel=None, parent_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if analysis.axisymmetric:
        raise ValueError("Choose 3D or axisymmetric, not both.")
    width = float(analysis.width3d)
    if width <= 0:
        raise ValueError("The 3D width must be positive.")
    tri = _section_mesh(project, analysis)
    extra = [float(w[1]) for w in analysis.wells or [] if len(w) > 1]
    for bc in project.bcs("hydraulic", analysis):
        z1, z2 = _bc_range(bc, width)
        extra += [z1, z2]
    zs = _z_levels(width, analysis.n_layers3d, extra)
    mesh = Prism(tri, zs)
    if mesh.nn > 400000:
        raise ValueError(f"The 3D mesh has {mesh.nn} nodes. Use a larger mesh size or fewer layers.")
    prob = _Seep3D(project, analysis, tri, mesh)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth) if analysis.transient else None
    h0 = None
    if parent_results and parent_results.get("three_d") and len(parent_results["three_d"]["head"]) == mesh.nn:
        h0 = np.asarray(parent_results["three_d"]["head"], float)
    elif analysis.initial == "water_table" and len(project.piezometric_line) >= 2:
        from .geometry import polyline_y
        h0 = np.asarray(polyline_y(project.piezometric_line, mesh.x), float)
    elif analysis.initial == "value" and steps is not None:
        h0 = np.full(mesh.nn, float(analysis.initial_value))
    if h0 is None:
        if steps is not None:
            raise ValueError("A transient 3D seepage analysis needs initial conditions: a solved parent 3D "
                             "seepage analysis, a water table or an initial head.")
        fixed, _, _ = prob.boundary(None, np.zeros(mesh.nn))
        h0 = np.full(mesh.nn, max(fixed.values()) if fixed else float(mesh.y.max()))
    times = [0.0]

    def on_step(k, t, h, react):
        if t is not None:
            times.append(float(t))
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
    rate = react + flux
    wells = []
    for k, kind, val, nodes, (x, z) in prob.wells:
        q = -float(rate[nodes].sum())               # outflow from the ground into the well +
        wells.append({"well": k + 1, "x": x, "z": z, "type": kind, "value": val, "flow": q})
    bc_flow = {}
    for bc, nodes, _e, _z in prob.bcs:
        bc_flow[bc.name] = float(rate[nodes].sum())
    hp = h - mesh.y
    out = {
        "type": "seepage", "three_d": {
            "width": width, "z": zs.tolist(), "nn2": mesh.nn2, "head": h.tolist(),
            "pressure_head": hp.tolist(), "wells": wells, "bc_flow": bc_flow,
            "elements": mesh.ne, "n_nodes": mesh.nn, "gamma_w": project.gamma_w,
        },
        "converged": converged, "iterations": it, "history": history[-200:],
        "nodes": tri.nodes.tolist(), "tris": tri.tris.tolist(), "tri_material": tri.mats.tolist(),
        "inflow": float(rate[rate > 0].sum()), "outflow": float(-rate[rate < 0].sum()),
        "flux_sections": {}, "kx_layer": None,
    }
    if steps is not None:
        out["times"] = times
    z_show = analysis.slice_z if analysis.slice_z >= 0 else (extra[0] if analysis.wells else 0.5 * width)
    out.update(_slice_fields(out, prob, mesh, h, z_show, project.gamma_w))
    return out


def _layer_values(res3, values, z):
    """Values on the section at height z (linear between the two nearest layers)."""
    zs = np.asarray(res3["z"])
    nn2 = res3["nn2"]
    V = np.asarray(values, float).reshape(len(zs), nn2)
    z = min(max(float(z), zs[0]), zs[-1])
    k = int(np.clip(np.searchsorted(zs, z) - 1, 0, len(zs) - 2))
    t = 0.0 if zs[k + 1] == zs[k] else (z - zs[k]) / (zs[k + 1] - zs[k])
    return (1 - t) * V[k] + t * V[k + 1]


def _slice_fields(res, prob, mesh, h, z, gamma_w):
    """2D fields of one section z, so the usual contour, vectors and phreatic line work."""
    res3 = res["three_d"]
    head = _layer_values(res3, h, z)
    nodes2 = np.asarray(res["nodes"])
    hp = head - nodes2[:, 1]
    tri = mesh.tri
    k = int(np.clip(np.searchsorted(mesh.zs, z) - 1, 0, mesh.nl - 1))
    kx, ky = prob.conductivity(h)
    sel = mesh.layer == k
    gx, gy = tri.gradient(head)
    th = np.zeros(len(hp))
    for m in prob.mat_list:
        e = tri.mats == m.id
        v = np.bincount(tri.tris[e].ravel(), minlength=tri.nn) > 0
        th[v] = water_content(m, hp[v], gamma_w)[0]
    return {"head": head.tolist(), "pressure_head": hp.tolist(), "pore_pressure": (hp * gamma_w).tolist(),
            "water_content": th.tolist(), "vx": (-kx[sel] * gx).tolist(), "vy": (-ky[sel] * gy).tolist(),
            "phreatic": phreatic_segments(nodes2, tri.tris, hp), "slice_z": float(z),
            "seepage_face_nodes": []}


def slice_results(res, z):
    """Copy of a 3D seepage result showing the section at z (used by the results view and by 2D
    analyses that take pore pressures from it)."""
    out = dict(res)
    res3 = res["three_d"]
    nodes2 = np.asarray(res["nodes"])
    head = _layer_values(res3, res3["head"], z)
    hp = head - nodes2[:, 1]
    out.update(head=head.tolist(), pressure_head=hp.tolist(), slice_z=float(z),
               pore_pressure=(hp * float(res3.get("gamma_w", 9.807))).tolist(),
               phreatic=phreatic_segments(nodes2, np.asarray(res["tris"]), hp))
    return out


def pressure_head_at_z(res, z):
    """Pressure head function (x, y) of the section at z."""
    res3 = res["three_d"]
    return interpolator(res["nodes"], _layer_values(res3, res3["pressure_head"], z))


def text_report(res, units) -> str:
    r3 = res["three_d"]
    L = [f"3D seepage: width {r3['width']:.1f} {units['length']}, {len(r3['z']) - 1} layers, "
         f"{r3['n_nodes']} nodes, {r3['elements']} wedge elements",
         f"Inflow {res['inflow']:.4g}, outflow {res['outflow']:.4g} {units['flux']}"]
    for w in r3["wells"]:
        L.append(f"Well {w['well']} at x = {w['x']:.2f}, z = {w['z']:.2f}: {w['type']} {w['value']:g}, "
                 f"flow into the well {w['flow']:.4g} {units['flux']}")
    for name, q in r3["bc_flow"].items():
        L.append(f"{name}: net inflow {q:.4g} {units['flux']}")
    return "\n".join(L)
