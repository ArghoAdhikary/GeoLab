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
from scipy.sparse.linalg import splu

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

    def __init__(self, project, mesh: Mesh6, srf=1.0, analysis=None):
        from .structures import inactive_elements
        mats = {m.id: m for m in project.materials}
        ml = [mats[i] for i in mesh.mats]
        self.inactive = inactive_elements(project, mesh, analysis)      # not built yet / excavated
        self.active = np.array([m.stress_model != "none" for m in ml]) & ~self.inactive
        self.E = np.array([m.E for m in ml], float)
        self.nu = np.array([min(m.nu, 0.495) for m in ml], float)
        self.gamma = np.array([m.unit_weight for m in ml], float)
        self.plastic = np.array([m.stress_model == "elastic_plastic" for m in ml]) & self.active
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
    def __init__(self, mesh, model, fixed, Ks=None):
        self.mesh, self.model = mesh, model
        Ke = np.einsum("egji,ejk,egkl,eg->eil", mesh.B, model.D, mesh.B, mesh.dV)
        self.K = mesh.assemble(Ke)
        ndof = 2 * mesh.nn
        if Ks is not None and Ks.shape[0] > 0:
            ndof = Ks.shape[0]
            self.K = _pad(self.K, ndof) + Ks
        self.ndof = ndof
        self.fixed = fixed
        self.cidx = np.array(sorted(fixed), int)
        self.free = np.setdiff1d(np.arange(ndof), self.cidx)
        if len(self.cidx) < 3:
            raise ValueError("The model is not restrained. Add fixed boundary conditions (e.g. fixed x on the "
                             "sides and fixed x and y at the base).")
        self.lu = splu(self.K[self.free][:, self.free].tocsc())
        self.Kfc = self.K[self.free][:, self.cidx]

    def solve(self, F, uc):
        u = np.zeros(self.ndof)
        if len(F) < self.ndof:
            F = np.concatenate([F, np.zeros(self.ndof - len(F))])
        u[self.cidx] = uc
        u[self.free] = self.lu.solve(F[self.free] - self.Kfc @ uc)
        return u


def _pad(K, n):
    """Square sparse matrix enlarged to n x n with zeros."""
    K = K.tocoo()
    return coo_matrix((K.data, (K.row, K.col)), shape=(n, n)).tocsr()


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


def overburden(project, x, y):
    """Total vertical stress from the weight of the soil columns above points (x, y)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mats = {m.id: m for m in project.materials}
    sv = np.zeros(np.broadcast(x, y).shape)
    for r in project.regions:
        m = mats.get(r.material_id)
        if m is None or m.stress_model == "none" or len(r.points) < 3:
            continue
        pts = np.asarray(r.points, float)
        ys = []
        for (x1, y1), (x2, y2) in zip(pts, np.roll(pts, -1, axis=0)):
            if x1 == x2:
                continue
            inside = ((x1 <= x) & (x < x2)) | ((x2 <= x) & (x < x1))
            ys.append(np.where(inside, y1 + (x - x1) / (x2 - x1) * (y2 - y1), np.nan))
        if len(ys) < 2:
            continue
        Y = np.sort(np.stack(np.broadcast_arrays(*ys)), axis=0)     # NaN sorts last
        for k in range(0, Y.shape[0] - 1, 2):
            length = np.clip(Y[k + 1] - np.maximum(Y[k], y), 0.0, None)
            sv += m.unit_weight * np.nan_to_num(length)
    return sv


def k0_stress(project, x, y, k0, u):
    """K0 procedure: sigma'v from the overburden, sigma'h = sigma'z = K0 sigma'v, no shear
    (effective stresses, tension positive, per Gauss point)."""
    sv_eff = np.clip(overburden(project, x, y) - u, 0.0, None)
    k = np.asarray(k0, float).reshape(-1, *([1] * (sv_eff.ndim - 1)))
    sig = np.zeros(sv_eff.shape + (4,))
    sig[..., 1] = -sv_eff
    sig[..., 0] = sig[..., 3] = -k * sv_eff
    return sig


def gravity_fe(mesh, gamma, u_gp, active=None):
    """Element body forces of the total unit weight plus the pore pressure term (effective stress
    formulation)."""
    fe = np.zeros((mesh.ne, 12))
    fe[:, 1::2] = -np.einsum("e,gk,eg->ek", gamma, mesh.N, mesh.dV)
    up = u_gp if active is None else np.where(active[:, None], u_gp, 0.0)
    fe += np.einsum("egji,j,eg,eg->ei", mesh.B, M_VEC, up, mesh.dV)
    return fe


def _gravity_load(mesh, model, u_gp):
    return gravity_fe(mesh, model.gamma, u_gp, model.active)


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
    inactive = getattr(model, "inactive", np.zeros(mesh.ne, bool))
    if inactive.any():
        live = np.zeros(mesh.nn, bool)
        live[mesh.tris[~inactive].ravel()] = True
        u = u.copy()
        u[:2 * mesh.nn][0::2][~live] = 0.0
        u[:2 * mesh.nn][1::2][~live] = 0.0
    res = {
        "type": "stress", "nodes": mesh.nodes3.tolist(), "tris": mesh.tris3.tolist(),
        "inactive": inactive.tolist(),
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
    from .structures import StructureSet, stage_load
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
    model = _Model(project, mesh, analysis=analysis)
    parent_res = parent.results if parent is not None and parent.results and         parent.results.get("type") == "stress" and analysis.stress_type != "insitu" else None
    structs = StructureSet(project, mesh, analysis, 0.1 * analysis.mesh_size, parent_res)
    u_gp = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results)
    if analysis.stress_type == "insitu" and getattr(analysis, "insitu_method", "gravity") == "k0":
        sig = k0_stress(project, mesh.gx, mesh.gy, model.k0, u_gp)
        sig[model.inactive] = 0.0
        return _results(project, mesh, model, np.zeros(2 * mesh.nn), sig, u_gp, analysis,
                        {"converged": True, "history": [], "stress_type": "insitu", "reactions": {},
                         "insitu_method": "k0", "structures": structs.results(np.zeros(structs.ndof))})
    if analysis.stress_type == "insitu":
        sig = np.zeros((mesh.ne, mesh.ngp, 4))
        F_total = mesh.vector(_gravity_load(mesh, model, u_gp)) + F_bc
    else:
        sig = _initial_stress(project, mesh, model, analysis, parent)
        F_stage, added = stage_load(project, mesh, model, analysis, parent, sig, u_gp, gravity_fe)
        sig[added] = 0.0                 # newly built regions start without stress
        sig[model.inactive] = 0.0
        F_total = F_bc + F_stage
    F_total = F_total + structs.released + structs.prestress
    sig_start = sig.copy()
    staged = bool(model.inactive.any()) or bool(structs.items)
    steps = max(1, int(analysis.load_steps)) if model.plastic.any() or analysis.stress_type == "load" else 1
    from .soilmodels import NONLINEAR_MODELS, Constitutive, solve_nonlinear
    mats_ = {m.id: m for m in project.materials}
    nonlinear = analysis.stress_type == "load" and any(
        mats_[i].stress_model in NONLINEAR_MODELS for i, on in zip(mesh.mats.tolist(), model.active) if on)
    for attempt in range(6):            # repeated only when geogrids go slack (tension only)
        sig = sig_start.copy()
        Ks = structs.stiffness() if structs.items else None
        sysm = _System(mesh, model, fixed, Ks)
        uc_total = np.array([fixed[i] for i in sysm.cidx])
        u = np.zeros(sysm.ndof)
        history = []
        ok = True
        if nonlinear:
            # Cam Clay / hyperbolic / Hardening Soil: modified Newton with sub-stepped stress integration
            cons = Constitutive(project, mesh, model, sig)
            u, sig, history, ok = solve_nonlinear(mesh, model, cons, fixed, F_total, uc_total, steps, u_gp,
                                                  max_iter=max(60, analysis.max_iter), progress=progress,
                                                  cancel=cancel, Ks=Ks)
        else:
            for k in range(steps):
                if cancel and cancel():
                    raise RuntimeError("Cancelled")
                du, sig, conv, it = _increment(sysm, sig, F_total / steps, uc_total / steps)
                u += du
                history.append({"step": k + 1, "iterations": it, "converged": conv,
                                "max_disp": float(np.max(np.hypot(u[0:2 * mesh.nn:2], u[1:2 * mesh.nn:2])))})
                ok &= conv
                if progress:
                    progress(int(100 * (k + 1) / steps))
        if not structs.compressed_geogrids(u):
            break
    sig[model.inactive] = 0.0
    # reactions on restrained boundaries: internal force minus applied load
    f_int = mesh.vector(np.einsum("egji,egj,eg->ei", mesh.B, sig - M_VEC * u_gp[..., None], mesh.dV))
    f_ext = F_total
    if analysis.stress_type != "insitu":
        f_int -= mesh.vector(np.einsum("egji,egj,eg->ei", mesh.B, sig_start - M_VEC * u_gp[..., None], mesh.dV))
    if Ks is not None:
        f_int = f_int + (Ks @ u)[:2 * mesh.nn]
    R = f_int - f_ext
    reactions = {}
    tol = 0.1 * analysis.mesh_size
    from .geometry import dist_point_polyline
    for bc in project.bcs("stress", analysis):
        if bc.type in ("fixed_x", "fixed_y", "fixed_xy", "displacement_y"):
            idx = [i for i, (x, y) in enumerate(mesh.nodes) if dist_point_polyline(x, y, bc.points) <= tol]
            reactions[bc.name] = [float(R[2 * np.array(idx)].sum()), float(R[2 * np.array(idx) + 1].sum())]
    struct_res = structs.results(u)
    if analysis.stress_type == "insitu":
        u[:] = 0.0          # in situ displacements are not meaningful
    return _results(project, mesh, model, u[:2 * mesh.nn], sig, u_gp, analysis,
                    {"converged": ok, "history": history, "stress_type": analysis.stress_type,
                     "reactions": reactions, "structures": struct_res, "staged": staged})


def run_srm(project, analysis, mesh, fixed, seep_results, progress=None, cancel=None):
    """Strength reduction factor of safety: the smallest strength reduction factor at which the
    gravity-loaded model fails to converge (Griffiths & Lane 1999)."""
    u_gp = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results)
    zero = np.zeros((mesh.ne, mesh.ngp, 4))

    from .structures import StructureSet
    structs = StructureSet(project, mesh, analysis, 0.1 * analysis.mesh_size)
    Ks = structs.stiffness() if structs.items else None

    def stable(srf):
        model = _Model(project, mesh, srf, analysis=analysis)
        sysm = _System(mesh, model, fixed, Ks)
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
    return _results(project, mesh, model, du[:2 * mesh.nn], sig, u_gp, analysis,
                    {"converged": True, "srm_fos": lo, "srm_trials": trials, "stress_type": "srm"})


# ---------------------------------------------------------------------------
# Coupled consolidation (Biot)
# ---------------------------------------------------------------------------
def run_consolidation(project, analysis, progress=None, cancel=None, parent=None, seep_results=None) -> dict:
    """Coupled consolidation. Loads (stress boundary conditions, fill placed or soil excavated in this stage,
    anchors installed) are applied at the start (undrained), then excess pore pressures dissipate through
    drained boundaries (hydraulic head / pressure-head boundary conditions) over the analysis duration.
    Elastic-plastic (Mohr-Coulomb) soil yields during consolidation (viscoplastic iterations in each time
    step); other models use their elastic E and nu."""
    from .structures import StructureSet, stage_load
    nodes3, tris3, mats = generate_mesh(project, analysis.mesh_size)
    mesh = Mesh6(nodes3, tris3, mats)
    model = _Model(project, mesh, analysis=analysis)
    fixed, F_bc = _bcs(project, mesh, analysis)
    parent_res = parent.results if parent is not None and parent.results and         parent.results.get("type") == "stress" else None
    structs = StructureSet(project, mesh, analysis, 0.1 * analysis.mesh_size, parent_res)
    mats_ = {m.id: m for m in project.materials}
    kx = np.array([mats_[i].k_sat for i in mesh.mats])
    ky = kx * np.array([mats_[i].k_ratio for i in mesh.mats])
    gw = project.gamma_w
    nd2 = 2 * mesh.nn
    Ke = np.einsum("egji,ejk,egkl,eg->eil", mesh.B, model.D, mesh.B, mesh.dV)
    K = mesh.assemble(Ke)
    nd = nd2
    if structs.items:
        Ks = structs.stiffness()
        nd = Ks.shape[0]
        K = _pad(K, nd) + Ks
    else:
        Ks = None
    # coupling C (nd x n3): integral of B^T m Np
    Ce = np.einsum("egji,j,gk,eg->eik", mesh.B, M_VEC, mesh.Np, mesh.dV)
    rows = np.repeat(mesh.dof, 3, axis=1).ravel()
    cols = np.tile(mesh.tris3, (1, 12)).ravel()
    C = coo_matrix((Ce.ravel(), (rows, cols)), shape=(nd, mesh.n3)).tocsr()
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
    fixed_all = dict(fixed)
    for i in drained:
        fixed_all[nd + i] = 0.0
    cidx = np.array(sorted(fixed_all), int)
    xc = np.array([fixed_all[i] for i in cidx])
    free = np.setdiff1d(np.arange(nd + mesh.n3), cidx)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth)
    sig0 = _initial_stress(project, mesh, model, analysis, parent)
    u_gp0 = _pore_pressure(project, analysis, mesh.gx, mesh.gy, seep_results)
    F_stage, added = stage_load(project, mesh, model, analysis, parent, sig0, u_gp0, gravity_fe)
    sig0[added] = 0.0
    sig0[model.inactive] = 0.0
    F = F_bc + F_stage + structs.released + structs.prestress
    F = np.concatenate([F, np.zeros(nd - nd2)])
    u = np.zeros(nd)
    p = np.zeros(mesh.n3)
    evp = np.zeros_like(sig0)
    plastic = bool(model.plastic.any())
    pl = model.plastic[:, None]
    yield_ok = True

    def step(dt):
        """One backward-Euler step: [K -C; -C^T -dt H] [u; p] = [F + plastic load; -C^T u_old]."""
        nonlocal evp, yield_ok
        A = bmat([[K, -C], [-C.T, -dt * H]]).tocsr()
        lu = splu(A[free][:, free].tocsc())
        Afc = A[free][:, cidx]
        u_old = u.copy()
        prev = None
        for it in range(400 if plastic else 1):
            bdy = mesh.vector(np.einsum("egji,ejk,egk,eg->ei", mesh.B, model.D, evp, mesh.dV))
            rhs = np.concatenate([F + np.concatenate([bdy, np.zeros(nd - nd2)]), -C.T @ u_old])
            x = np.zeros(nd + mesh.n3)
            x[cidx] = xc
            x[free] = lu.solve(rhs[free] - Afc @ xc)
            un = x[:nd]
            if not plastic:
                return un, x[nd:]
            if prev is not None and np.max(np.abs(un - prev)) <= 1e-4 * max(np.max(np.abs(un)), 1e-30):
                return un, x[nd:]
            prev = un
            sig = sig0 + np.einsum("eij,egj->egi", model.D, _strain(mesh, un) - evp)
            f = mc_function(sig, model.c_gp, model.sphi[:, None], model.cphi[:, None])
            f = np.where(pl & (f > 0), f, 0.0)
            if not np.any(f > 0):
                return un, x[nd:]
            sc = np.maximum(np.abs(sig).max(axis=-1), model.c_gp + 1.0)
            dq = mc_gradient(sig, model.c_gp, model.spsi[:, None], model.cpsi[:, None], sc)
            evp = evp + (model.dt * f)[..., None] * dq
        yield_ok = False
        return un, x[nd:]

    times, p_hist, dy_hist = [0.0], [], []
    u, p = step(0.0)                                      # undrained loading
    p_hist.append(p.tolist())
    dy_hist.append(u[1:2 * mesh.n3:2].copy())
    t = 0.0
    for k, dt in enumerate(steps):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        u, p = step(dt)
        t += dt
        times.append(t)
        p_hist.append(p.tolist())
        dy_hist.append(u[1:2 * mesh.n3:2].copy())
        if progress:
            progress(int(100 * (k + 1) / len(steps)))
    top = int(np.argmin(dy_hist[-1]))                     # monitor the point that settles most
    settle = [float(-d[top]) for d in dy_hist]
    sig = sig0 + np.einsum("eij,egj->egi", model.D, _strain(mesh, u) - evp)
    sig[model.inactive] = 0.0
    u_gp = u_gp0 + np.einsum("gk,ek->eg", mesh.Np, p[mesh.tris3])
    return _results(project, mesh, model, u[:nd2], sig, u_gp, analysis, {
        "converged": yield_ok, "stress_type": "consolidation", "times": times, "excess_pwp": p.tolist(),
        "excess_history": p_hist, "settlement_history": settle, "monitor_node": int(top),
        "structures": structs.results(u), "staged": bool(model.inactive.any())})
