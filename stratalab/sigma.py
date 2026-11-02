"""Stress-deformation analysis (plane strain) with 6-node triangles.

* In situ: gravity turned on, displacements reset (initial stresses).
* Load-deformation: boundary loads / displacements applied in steps from the parent stresses.
* Consolidation: coupled Biot consolidation (linear elastic skeleton, excess pore pressure
  on the corner nodes), backward Euler in time.

Materials are linear elastic or elastic-perfectly plastic Mohr-Coulomb with a
non-associated flow rule (dilation angle psi), solved with the viscoplastic
algorithm of Zienkiewicz & Cormeau as used by Smith & Griffiths (Programming the
Finite Element Method). Effective stresses use the pore pressure from a water
table or a parent seepage analysis. A strength reduction factor of safety
(Griffiths & Lane 1999) is available for elastic-plastic models.

Internally stresses are tension positive with components [sx, sy, txy, sz];
results are reported compression positive, as is usual in geotechnics.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix, bmat, diags
from scipy.sparse.linalg import splu, spsolve

from .fe import GAUSS3, T3, interpolator, t3_shape, t6_shape, time_steps, to_t6
from .geometry import polyline_y, validate_geometry
from .seep import generate_mesh

M_VEC = np.array([1.0, 1.0, 0.0, 1.0])


class Mesh6:
    def __init__(self, nodes3, tris3, mats):
        self.n3 = len(nodes3)
        self.nodes3 = np.asarray(nodes3, float)
        self.tris3 = np.asarray(tris3, int)
        self.nodes, self.tris = to_t6(nodes3, tris3)
        self.mats = np.asarray(mats)
        self.nn = len(self.nodes)
        self.ne = len(self.tris)
        pts, w = GAUSS3
        self.ngp = len(w)
        X = self.nodes[self.tris]                         # ne x 6 x 2
        self.N = np.zeros((self.ngp, 6))
        self.Np = np.zeros((self.ngp, 3))
        self.B = np.zeros((self.ne, self.ngp, 4, 12))
        self.dV = np.zeros((self.ne, self.ngp))
        self.gx = np.zeros((self.ne, self.ngp))
        self.gy = np.zeros((self.ne, self.ngp))
        self.dNp = np.zeros((self.ne, self.ngp, 2, 3))   # gradients of the linear pressure shape functions
        for g, ((xi, eta), wg) in enumerate(zip(pts, w)):
            N, dxi, deta = t6_shape(xi, eta)
            self.N[g] = N
            self.Np[g] = t3_shape(xi, eta)
            J = np.stack([np.einsum("k,ekd->ed", dxi, X), np.einsum("k,ekd->ed", deta, X)], axis=1)  # ne x 2 x 2
            det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
            inv = np.stack([np.stack([J[:, 1, 1], -J[:, 0, 1]], 1), np.stack([-J[:, 1, 0], J[:, 0, 0]], 1)], 1) / det[:, None, None]
            dN = inv @ np.stack([dxi, deta])[None]          # ne x 2 x 6
            B = self.B[:, g]
            B[:, 0, 0::2] = dN[:, 0]
            B[:, 1, 1::2] = dN[:, 1]
            B[:, 2, 0::2] = dN[:, 1]
            B[:, 2, 1::2] = dN[:, 0]
            self.dV[:, g] = det * wg
            self.gx[:, g] = X[:, :, 0] @ N
            self.gy[:, g] = X[:, :, 1] @ N
            dP = inv @ np.stack([[-1.0, 1.0, 0.0], [-1.0, 0.0, 1.0]])[None]
            self.dNp[:, g] = dP
        self.dof = np.empty((self.ne, 12), int)
        self.dof[:, 0::2] = 2 * self.tris
        self.dof[:, 1::2] = 2 * self.tris + 1
        self.t3 = T3(nodes3, tris3, mats)

    def assemble(self, Ke):
        r = np.repeat(self.dof, 12, axis=1).ravel()
        c = np.tile(self.dof, (1, 12)).ravel()
        return coo_matrix((Ke.ravel(), (r, c)), shape=(2 * self.nn, 2 * self.nn)).tocsr()

    def vector(self, fe):
        return np.bincount(self.dof.ravel(), weights=fe.ravel(), minlength=2 * self.nn)

    def boundary_edges6(self):
        """Boundary edges as (a, mid, b) with the element on the left of a->b."""
        e3 = {tuple(x) for x in self.t3.boundary_edges().tolist()}
        out = []
        for t in self.tris:
            for a, b, m in ((t[0], t[1], t[3]), (t[1], t[2], t[4]), (t[2], t[0], t[5])):
                if (min(a, b), max(a, b)) in e3:
                    out.append((a, m, b))
        return out


def elastic_D(E, nu):
    f = E / ((1 + nu) * (1 - 2 * nu))
    return f * np.array([[1 - nu, nu, 0, nu], [nu, 1 - nu, 0, nu], [0, 0, (1 - 2 * nu) / 2, 0], [nu, nu, 0, 1 - nu]])


def principal(s):
    """Principal stresses (max, min) of [sx, sy, txy, sz] arrays (tension positive)."""
    c = 0.5 * (s[..., 0] + s[..., 1])
    r = np.sqrt((0.5 * (s[..., 0] - s[..., 1])) ** 2 + s[..., 2] ** 2)
    a, b, z = c + r, c - r, s[..., 3]
    return np.maximum(np.maximum(a, b), z), np.minimum(np.minimum(a, b), z)


def mc_function(s, c, sinphi, cosphi):
    """Mohr-Coulomb yield / potential function (stress units), tension positive."""
    s1, s3 = principal(s)
    return 0.5 * (s1 - s3) + 0.5 * (s1 + s3) * sinphi - c * cosphi


def mc_gradient(s, c, sinphi, cosphi, scale):
    h = 1e-6 * scale
    g = np.zeros_like(s)
    for k in range(4):
        sp = s.copy(); sm = s.copy()
        sp[..., k] += h
        sm[..., k] -= h
        g[..., k] = (mc_function(sp, c, sinphi, cosphi) - mc_function(sm, c, sinphi, cosphi)) / (2 * h)
    return g


class _Model:
    """Material arrays per element (and per Gauss point where needed)."""

    def __init__(self, project, mesh: Mesh6, srf=1.0):
        mats = {m.id: m for m in project.materials}
        ml = [mats[i] for i in mesh.mats]
        self.active = np.array([m.stress_model != "none" for m in ml])
        self.E = np.array([m.E for m in ml], float)
        self.nu = np.array([min(m.nu, 0.495) for m in ml], float)
        self.gamma = np.array([m.unit_weight for m in ml], float)
        self.plastic = np.array([m.stress_model == "elastic_plastic" for m in ml])
        undrained = np.array([m.model in ("undrained", "undrained_depth", "shansep") for m in ml])
        c = np.array([m.cohesion for m in ml], float)
        rate = np.array([m.c_rate if m.model == "undrained_depth" else 0.0 for m in ml])
        datum = np.array([m.datum for m in ml])
        self.c_gp = (c[:, None] + rate[:, None] * np.clip(datum[:, None] - mesh.gy, 0, None)) / srf
        phi = np.where(undrained, 0.0, [m.phi for m in ml])
        psi = np.where(undrained, 0.0, [m.psi for m in ml])
        phi = np.degrees(np.arctan(np.tan(np.radians(phi)) / srf))
        psi = np.minimum(psi, phi)
        self.sphi, self.cphi = np.sin(np.radians(phi)), np.cos(np.radians(phi))
        self.spsi, self.cpsi = np.sin(np.radians(psi)), np.cos(np.radians(psi))
        self.D = np.stack([elastic_D(e, n) for e, n in zip(self.E, self.nu)])
        self.D[~self.active] *= 1e-6                 # excluded regions: nearly void
        self.gamma[~self.active] = 0.0
        sp2 = self.sphi ** 2
        self.dt = float(np.min(4 * (1 + self.nu) * (1 - 2 * self.nu) / (self.E * (1 - 2 * self.nu + sp2))))
        self.k0 = np.array([m.k0 if m.k0 > 0 else m.nu / (1 - m.nu) for m in ml])


def _pore_pressure(project, analysis, x, y, seep_results):
    """Pore-water pressure (compression +, suction ignored) at points."""
    gw = project.gamma_w
    if analysis.pwp == "seepage" and seep_results:
        hp = interpolator(seep_results["nodes"], seep_results["pressure_head"])(x, y)
        return gw * np.clip(hp, 0.0, None)
    if analysis.pwp == "piezometric" and len(project.piezometric_line) >= 2:
        return gw * np.clip(polyline_y(project.piezometric_line, x) - y, 0.0, None)
    return np.zeros(np.shape(x))


def _bcs(project, mesh: Mesh6, analysis):
    """Fixed DOFs {dof: value} and external load vector from the stress boundary conditions."""
    tol = 0.1 * analysis.mesh_size
    from .geometry import dist_point_polyline
    fixed: dict[int, float] = {}
    F = np.zeros(2 * mesh.nn)
    edges6 = mesh.boundary_edges6()
    for bc in project.bcs("stress", analysis):
        nodes = [i for i, (x, y) in enumerate(mesh.nodes) if dist_point_polyline(x, y, bc.points) <= tol]
        if not nodes:
            raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node.")
        if bc.type in ("fixed_x", "fixed_xy"):
            fixed.update({2 * i: 0.0 for i in nodes})
        if bc.type in ("fixed_y", "fixed_xy"):
            fixed.update({2 * i + 1: 0.0 for i in nodes})
        if bc.type == "displacement_y":
            fixed.update({2 * i + 1: bc.value for i in nodes})
        if bc.type == "force_x":
            F[2 * np.array(nodes)] += bc.value / len(nodes)
        if bc.type == "force_y":
            F[2 * np.array(nodes) + 1] += bc.value / len(nodes)
        if bc.type in ("pressure", "shear"):
            ns = set(nodes)
            hit = False
            for a, m, b in edges6:
                if a in ns and m in ns and b in ns:
                    hit = True
                    d = mesh.nodes[b] - mesh.nodes[a]
                    L = float(np.hypot(*d))
                    t = d / L
                    n_out = np.array([t[1], -t[0]])
                    tr = -bc.value * n_out if bc.type == "pressure" else bc.value * t
                    for node, wgt in ((a, L / 6), (m, 2 * L / 3), (b, L / 6)):
                        F[2 * node] += wgt * tr[0]
                        F[2 * node + 1] += wgt * tr[1]
            if not hit:
                raise ValueError(f"Pressure boundary '{bc.name}' must lie along the outside edge of the mesh.")
    return fixed, F


class _System:
    def __init__(self, mesh, model, fixed):
        self.mesh, self.model = mesh, model
        Ke = np.einsum("egji,ejk,egkl,eg->eil", mesh.B, model.D, mesh.B, mesh.dV)
        self.K = mesh.assemble(Ke)
        ndof = 2 * mesh.nn
        self.fixed = fixed
        self.cidx = np.array(sorted(fixed), int)
        self.free = np.setdiff1d(np.arange(ndof), self.cidx)
        if len(self.cidx) < 3:
            raise ValueError("The model is not restrained. Add fixed boundary conditions (e.g. fixed x on the "
                             "sides and fixed x and y at the base).")
        self.lu = splu(self.K[self.free][:, self.free].tocsc())
        self.Kfc = self.K[self.free][:, self.cidx]

    def solve(self, F, uc):
        u = np.zeros(2 * self.mesh.nn)
        u[self.cidx] = uc
        u[self.free] = self.lu.solve(F[self.free] - self.Kfc @ uc)
        return u


def _strain(mesh, u):
    return np.einsum("egij,ej->egi", mesh.B, u[mesh.dof])


def _increment(sysm: _System, sig0, F_inc, uc_inc, plastic_iter=500, tol=1e-4):
    """Apply one load increment with viscoplastic iterations. Returns (du, sig, converged, iterations)."""
    mesh, mod = sysm.mesh, sysm.model
    evp = np.zeros_like(sig0)
    du_old = None
    pl = mod.plastic[:, None]
    for it in range(1, plastic_iter + 1):
        bdy = np.einsum("egji,ejk,egk,eg->ei", mesh.B, mod.D, evp, mesh.dV)
        du = sysm.solve(F_inc + mesh.vector(bdy), uc_inc)
        sig = sig0 + np.einsum("eij,egj->egi", mod.D, _strain(mesh, du) - evp)
        if not pl.any():
            return du, sig, True, it
        if du_old is not None and np.max(np.abs(du - du_old)) <= tol * max(np.max(np.abs(du)), 1e-30):
            return du, sig, True, it
        du_old = du
        f = mc_function(sig, mod.c_gp, mod.sphi[:, None], mod.cphi[:, None])
        f = np.where(pl & (f > 0), f, 0.0)
        if np.any(f > 0):
            sc = np.maximum(np.abs(sig).max(axis=-1), mod.c_gp + 1.0)
            dq = mc_gradient(sig, mod.c_gp, mod.spsi[:, None], mod.cpsi[:, None], sc)
            evp = evp + (mod.dt * f)[..., None] * dq
    return du, sig, False, plastic_iter


def _initial_stress(project, mesh, model, analysis, parent):
    if parent is not None and parent.results and parent.results.get("type") == "stress" \
            and len(parent.results.get("gp_stress", [])) == mesh.ne * mesh.ngp * 4:
        return np.array(parent.results["gp_stress"]).reshape(mesh.ne, mesh.ngp, 4)
    return np.zeros((mesh.ne, mesh.ngp, 4))


def _gravity_load(mesh, model, u_gp):
    """Body force of the total unit weight plus the pore pressure term (effective stress formulation)."""
    fe = np.zeros((mesh.ne, 12))
    fe[:, 1::2] = -np.einsum("e,gk,eg->ek", model.gamma, mesh.N, mesh.dV)
    fe += np.einsum("egji,j,eg,eg->ei", mesh.B, M_VEC, u_gp, mesh.dV)
    return fe


def _results(project, mesh, model, u, sig_eff, u_gp, analysis, extra=None):
    tot = sig_eff - M_VEC * u_gp[..., None]                # total, tension positive
    se = sig_eff.mean(axis=1)
    st = tot.mean(axis=1)
    f = mc_function(sig_eff, model.c_gp, model.sphi[:, None], model.cphi[:, None])
    yielded = (model.plastic & (f.max(axis=1) > -1e-3 * np.maximum(np.abs(sig_eff).max(axis=(1, 2)), 1.0))).tolist()
    n3 = mesh.n3
    from .fe import nodal_average
    corner = mesh.tris[:, :3]

    def nodal(v):
        return nodal_average(corner, v, mesh.nn)[:n3]
    s1, s3 = principal(st)
    q = np.sqrt(0.5 * ((st[:, 0] - st[:, 1]) ** 2 + (st[:, 1] - st[:, 3]) ** 2 + (st[:, 3] - st[:, 0]) ** 2) + 3 * st[:, 2] ** 2)
    pw = u_gp.mean(axis=1)
    res = {
        "type": "stress", "nodes": mesh.nodes3.tolist(), "tris": mesh.tris3.tolist(),
        "tri_material": mesh.mats.tolist(),
        "dx": u[0:2 * n3:2].tolist(), "dy": u[1:2 * n3:2].tolist(),
        # compression positive
        "sx": nodal(-st[:, 0]).tolist(), "sy": nodal(-st[:, 1]).tolist(), "txy": nodal(-st[:, 2]).tolist(),
        "sz": nodal(-st[:, 3]).tolist(), "sx_eff": nodal(-se[:, 0]).tolist(), "sy_eff": nodal(-se[:, 1]).tolist(),
        "pwp": nodal(pw).tolist(), "s1": nodal(-s3).tolist(), "s3": nodal(-s1).tolist(), "q": nodal(q).tolist(),
        "yielded": yielded,
        "elem_sx": (-st[:, 0]).tolist(), "elem_sy": (-st[:, 1]).tolist(), "elem_txy": (-st[:, 2]).tolist(),
        "gp_stress": sig_eff.ravel().tolist(),
    }
    if extra:
        res.update(extra)
    return res


def run_stress(project, analysis, progress=None, cancel=None, parent=None, seep_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if analysis.stress_type == "consolidation":
        return run_consolidation(project, analysis, progress, cancel, parent, seep_results)
    nodes3, tris3, mats = generate_mesh(project, analysis.mesh_size)
    mesh = Mesh6(nodes3, tris3, mats)
    fixed, F_bc = _bcs(project, mesh, analysis)
    if analysis.srm:
        return run_srm(project, analysis, mesh, fixed, seep_results, progress, cancel)
    model = _Model(project, mesh)
    sysm = _System(mesh, model, fixed)
    u_gp = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results)
    uc_total = np.array([fixed[i] for i in sysm.cidx])
    if analysis.stress_type == "insitu":
        sig = np.zeros((mesh.ne, mesh.ngp, 4))
        F_total = mesh.vector(_gravity_load(mesh, model, u_gp)) + F_bc
    else:
        sig = _initial_stress(project, mesh, model, analysis, parent)
        F_total = F_bc
    steps = max(1, int(analysis.load_steps)) if model.plastic.any() or analysis.stress_type == "load" else 1
    u = np.zeros(2 * mesh.nn)
    history = []
    ok = True
    for k in range(steps):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        du, sig, conv, it = _increment(sysm, sig, F_total / steps, uc_total / steps)
        u += du
        history.append({"step": k + 1, "iterations": it, "converged": conv,
                        "max_disp": float(np.max(np.hypot(u[0::2], u[1::2])))})
        ok &= conv
        if progress:
            progress(int(100 * (k + 1) / steps))
    # reactions on restrained boundaries: internal force minus applied load
    f_int = mesh.vector(np.einsum("egji,egj,eg->ei", mesh.B, sig - M_VEC * u_gp[..., None], mesh.dV))
    f_ext = F_total
    if analysis.stress_type != "insitu":
        sig0 = _initial_stress(project, mesh, model, analysis, parent)
        f_int -= mesh.vector(np.einsum("egji,egj,eg->ei", mesh.B, sig0 - M_VEC * u_gp[..., None], mesh.dV))
    R = f_int - f_ext
    reactions = {}
    tol = 0.1 * analysis.mesh_size
    from .geometry import dist_point_polyline
    for bc in project.bcs("stress", analysis):
        if bc.type in ("fixed_x", "fixed_y", "fixed_xy", "displacement_y"):
            idx = [i for i, (x, y) in enumerate(mesh.nodes) if dist_point_polyline(x, y, bc.points) <= tol]
            reactions[bc.name] = [float(R[2 * np.array(idx)].sum()), float(R[2 * np.array(idx) + 1].sum())]
    if analysis.stress_type == "insitu":
        u[:] = 0.0          # in situ displacements are not meaningful
    return _results(project, mesh, model, u, sig, u_gp, analysis,
                    {"converged": ok, "history": history, "stress_type": analysis.stress_type,
                     "reactions": reactions})


def run_srm(project, analysis, mesh, fixed, seep_results, progress=None, cancel=None):
    """Strength reduction factor of safety: the smallest strength reduction factor at which the
    gravity-loaded model fails to converge (Griffiths & Lane 1999)."""
    u_gp = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results)
    zero = np.zeros((mesh.ne, mesh.ngp, 4))

    def stable(srf):
        model = _Model(project, mesh, srf)
        sysm = _System(mesh, model, fixed)
        F = mesh.vector(_gravity_load(mesh, model, u_gp))
        uc = np.array([fixed[i] for i in sysm.cidx])
        du, sig, conv, it = _increment(sysm, zero, F, uc, plastic_iter=max(500, analysis.max_iter))
        return conv, du, sig, model

    lo, hi = 0.3, 1.0
    trials = []
    conv, *_ = stable(hi)
    trials.append((hi, conv))
    while conv and hi < 20:
        lo, hi = hi, hi * 1.5
        conv, *_ = stable(hi)
        trials.append((hi, conv))
    while hi - lo > 0.005 * hi:
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        mid = 0.5 * (lo + hi)
        conv, *_ = stable(mid)
        trials.append((mid, conv))
        if conv:
            lo = mid
        else:
            hi = mid
        if progress:
            progress(min(95, 10 * len(trials)))
    conv, du, sig, model = stable(lo)
    return _results(project, mesh, model, du, sig, u_gp, analysis,
                    {"converged": True, "srm_fos": lo, "srm_trials": trials, "stress_type": "srm"})


# ---------------------------------------------------------------------------
# Coupled consolidation (Biot)
# ---------------------------------------------------------------------------
def run_consolidation(project, analysis, progress=None, cancel=None, parent=None, seep_results=None) -> dict:
    """Linear elastic coupled consolidation. Loads (stress boundary conditions) are applied at the
    start (undrained), then excess pore pressures dissipate through drained boundaries (hydraulic
    head / pressure-head boundary conditions) over the analysis duration."""
    nodes3, tris3, mats = generate_mesh(project, analysis.mesh_size)
    mesh = Mesh6(nodes3, tris3, mats)
    model = _Model(project, mesh)
    fixed, F_bc = _bcs(project, mesh, analysis)
    mats_ = {m.id: m for m in project.materials}
    kx = np.array([mats_[i].k_sat for i in mesh.mats])
    ky = kx * np.array([mats_[i].k_ratio for i in mesh.mats])
    gw = project.gamma_w
    Ke = np.einsum("egji,ejk,egkl,eg->eil", mesh.B, model.D, mesh.B, mesh.dV)
    K = mesh.assemble(Ke)
    # coupling C (2nn x n3): integral of B^T m Np
    Ce = np.einsum("egji,j,gk,eg->eik", mesh.B, M_VEC, mesh.Np, mesh.dV)
    rows = np.repeat(mesh.dof, 3, axis=1).ravel()
    cols = np.tile(mesh.tris3, (1, 12)).ravel()
    C = coo_matrix((Ce.ravel(), (rows, cols)), shape=(2 * mesh.nn, mesh.n3)).tocsr()
    He = np.einsum("egdi,ed,egdj,eg->eij", mesh.dNp, np.stack([kx, ky], 1) / gw, mesh.dNp, mesh.dV)
    rr = np.repeat(mesh.tris3, 3, axis=1).ravel()
    cc = np.tile(mesh.tris3, (1, 3)).ravel()
    H = coo_matrix((He.ravel(), (rr, cc)), shape=(mesh.n3, mesh.n3)).tocsr()
    tol = 0.1 * analysis.mesh_size
    drained = set()
    for bc in project.bcs("hydraulic", analysis):
        if bc.type in ("head", "pressure_head", "seepage_face"):
            drained.update(mesh.t3.nodes_on(bc.points, tol))
    if not drained:
        raise ValueError("Consolidation needs at least one drained boundary: draw a hydraulic head or "
                         "pressure-head boundary condition where water can drain.")
    nd = 2 * mesh.nn
    fixed_all = dict(fixed)
    for i in drained:
        fixed_all[nd + i] = 0.0
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth)
    u = np.zeros(nd)
    p = np.zeros(mesh.n3)
    times, p_hist, settle = [0.0], [], []
    sig0 = _initial_stress(project, mesh, model, analysis, parent)

    def step(dt, F):
        # [K  -C ; -C^T  -dt H] [u ; p] = [F ; -C^T u_old]
        A = bmat([[K, -C], [-C.T, -dt * H]]).tocsr()
        rhs = np.concatenate([F, -C.T @ u])
        x = np.zeros(nd + mesh.n3)
        cidx = np.array(sorted(fixed_all), int)
        x[cidx] = [fixed_all[i] for i in cidx]
        free = np.setdiff1d(np.arange(nd + mesh.n3), cidx)
        x[free] = spsolve(A[free][:, free].tocsc(), rhs[free] - A[free][:, cidx] @ x[cidx])
        return x[:nd], x[nd:]

    top = np.argmax(mesh.nodes3[:, 1])
    u, p = step(0.0, F_bc)                                # undrained loading
    p_hist.append(p.tolist())
    settle.append(float(-u[2 * top + 1]))
    t = 0.0
    for k, dt in enumerate(steps):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        u, p = step(dt, F_bc)
        t += dt
        times.append(t)
        p_hist.append(p.tolist())
        settle.append(float(-u[2 * top + 1]))
        if progress:
            progress(int(100 * (k + 1) / len(steps)))
    sig = sig0 + np.einsum("eij,egj->egi", model.D, _strain(mesh, u))
    u_gp = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results) + np.einsum("gk,ek->eg", mesh.Np, p[mesh.tris3])
    return _results(project, mesh, model, u, sig, u_gp, analysis, {
        "converged": True, "stress_type": "consolidation", "times": times, "excess_pwp": p.tolist(),
        "excess_history": p_hist, "settlement_history": settle, "monitor_node": int(top)})
