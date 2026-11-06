"""Dynamic (earthquake) analysis: plane strain, 6-node triangles, Newmark time integration.

The input acceleration time history acts at the base: the equations are written in
displacements relative to the base, M a_rel + C v_rel + K u_rel = -M r a_g(t), with the
nodes fixed by the stress boundary conditions moving with the base. Damping is Rayleigh
damping set per element from its damping ratio at the first natural frequency of the
model and five times that frequency. With equivalent linear analysis the shear modulus
and damping of each element follow hyperbolic modulus-reduction and damping curves of
the effective shear strain (0.65 x maximum), iterated until they agree.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import eigsh

from .linsolve import factorize as splu

from .fe import GAUSS6, t6_shape
from .geometry import validate_geometry
from .model import UNIT_SYSTEMS
from .seep import generate_mesh
from .sigma import Mesh6, _bcs, elastic_D


def mass_matrix(mesh: Mesh6, rho):
    pts, w = GAUSS6
    X = mesh.nodes[mesh.tris]
    Me = np.zeros((mesh.ne, 12, 12))
    for (xi, eta), wg in zip(pts, w):
        N, dxi, deta = t6_shape(xi, eta)
        J00 = X[:, :, 0] @ dxi; J01 = X[:, :, 1] @ dxi
        J10 = X[:, :, 0] @ deta; J11 = X[:, :, 1] @ deta
        det = J00 * J11 - J01 * J10
        NN = np.outer(N, N)
        blk = np.zeros((12, 12))
        blk[0::2, 0::2] = NN
        blk[1::2, 1::2] = NN
        Me += (rho * det * wg)[:, None, None] * blk[None]
    return Me


def newmark_block(times, acc_g, ky, g):
    """Rigid sliding block (Newmark 1965): permanent displacement for downslope acceleration
    history acc_g (in g) and yield acceleration ky (in g). Returns (displacement, history)."""
    t = np.asarray(times, float)
    a = np.asarray(acc_g, float)
    v = d = 0.0
    out = [0.0]
    for k in range(1, len(t)):
        dt = t[k] - t[k - 1]
        rel0 = (a[k - 1] - ky) * g if (v > 0 or a[k - 1] > ky) else 0.0
        rel1 = (a[k] - ky) * g if (v > 0 or a[k] > ky) else 0.0
        vn = v + 0.5 * (rel0 + rel1) * dt
        if vn < 0:
            # block stops during the step
            frac = v / max(v - vn, 1e-30)
            d += 0.5 * v * frac * dt
            v = 0.0
        else:
            d += 0.5 * (v + vn) * dt
            v = vn
        out.append(d)
    return d, out


def run_dynamic(project, analysis, progress=None, cancel=None, parent=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if len(analysis.motion) < 2:
        raise ValueError("A dynamic analysis needs an input acceleration time history (time, acceleration in g).")
    nodes3, tris3, mats = generate_mesh(project, analysis.mesh_size)
    mesh = Mesh6(nodes3, tris3, mats)
    g = UNIT_SYSTEMS[project.units]["g"]
    mm = {m.id: m for m in project.materials}
    ml = [mm[i] for i in mesh.mats]
    E0 = np.array([m.E for m in ml], float)
    nu = np.array([min(m.nu, 0.49) for m in ml], float)
    rho = np.array([m.unit_weight / g for m in ml], float)
    xi0 = np.array([m.damping for m in ml], float)
    xi_max = np.array([max(m.damping_max, m.damping) for m in ml], float)
    gref = np.array([m.gamma_ref for m in ml], float)
    fixed, _ = _bcs(project, mesh, analysis)
    if not fixed:
        raise ValueError("Fix the base of the model (stress boundary condition) for a dynamic analysis.")
    cidx = np.array(sorted(fixed), int)
    free = np.setdiff1d(np.arange(2 * mesh.nn), cidx)
    Me = mass_matrix(mesh, rho)
    M = mesh.assemble(Me)
    r = np.zeros(2 * mesh.nn)
    r[0::2] = 1.0                                    # horizontal shaking
    motion = sorted(analysis.motion)
    dt = float(analysis.dt)
    T = float(motion[-1][0])
    t = np.arange(0.0, T + 0.5 * dt, dt)
    ag = np.interp(t, [p[0] for p in motion], [p[1] for p in motion]) * g
    # fundamental frequency estimate for the Rayleigh coefficients (shear beam Vs / 4H)
    G0 = E0 / (2 * (1 + nu))
    Vs = np.sqrt(G0 / np.maximum(rho, 1e-12))
    Hm = float(nodes3[:, 1].max() - nodes3[:, 1].min())
    w1 = 2 * math.pi * float(np.average(Vs, weights=mesh.dV.sum(1))) / (4 * Hm)
    w2 = 5 * w1
    G = G0.copy()
    xi = xi0.copy()
    eq_hist = []
    n_iter = max(1, analysis.n_eq_iter) if analysis.equivalent_linear and np.any(gref > 0) else 1
    keep = max(1, len(t) // 400)
    for itn in range(n_iter):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        E = 2 * G * (1 + nu)
        D = np.stack([elastic_D(e, n) for e, n in zip(E, nu)])
        Ke = np.einsum("egji,ejk,egkl,eg->eil", mesh.B, D, mesh.B, mesh.dV)
        a0 = 2 * xi * w1 * w2 / (w1 + w2)
        a1 = 2 * xi / (w1 + w2)
        K = mesh.assemble(Ke)
        C = mesh.assemble(a0[:, None, None] * Me + a1[:, None, None] * Ke)
        Kf, Cf, Mf = (A[free][:, free].tocsc() for A in (K, C, M))
        Keff = (Kf + (2 / dt) * Cf + (4 / dt ** 2) * Mf).tocsc()
        lu = splu(Keff)
        Mr = (M @ r)[free]
        nf = len(free)
        u = np.zeros(nf); v = np.zeros(nf)
        a = splu(Mf).solve(-Mr * ag[0])
        max_acc = np.zeros(mesh.n3)
        max_disp = np.zeros(mesh.n3)
        gmax = np.zeros(mesh.ne)
        hist_t, hist_ax = [], []
        full = np.zeros(2 * mesh.nn)
        for k in range(1, len(t)):
            p = -Mr * ag[k]
            rhs = p + Mf @ ((4 / dt ** 2) * u + (4 / dt) * v + a) + Cf @ ((2 / dt) * u + v)
            un = lu.solve(rhs)
            vn = (2 / dt) * (un - u) - v
            an = (4 / dt ** 2) * (un - u) - (4 / dt) * v - a
            u, v, a = un, vn, an
            full[free] = a
            ax_tot = full[0:2 * mesh.n3:2] + ag[k]
            max_acc = np.maximum(max_acc, np.abs(ax_tot))
            full[free] = u
            max_disp = np.maximum(max_disp, np.hypot(full[0:2 * mesh.n3:2], full[1:2 * mesh.n3:2]))
            eps = np.einsum("egij,ej->egi", mesh.B, full[mesh.dof])
            gam = np.sqrt((eps[..., 0] - eps[..., 1]) ** 2 + eps[..., 2] ** 2).max(axis=1)
            gmax = np.maximum(gmax, gam)
            if k % keep == 0:
                hist_t.append(float(t[k]))
                hist_ax.append((ax_tot / g).tolist())
            if progress and k % 50 == 0:
                progress(int(100 * (itn + k / len(t)) / n_iter))
        if n_iter == 1:
            break
        geff = 0.65 * gmax
        ratio = np.where(gref > 0, 1 / (1 + geff / np.where(gref > 0, gref, 1)), 1.0)
        Gn = G0 * ratio
        xin = np.where(gref > 0, xi0 + (xi_max - xi0) * (1 - ratio), xi0)
        change = float(np.max(np.abs(Gn - G) / G0))
        eq_hist.append(change)
        G, xi = Gn, xin
        if change < 0.02:
            break
    # natural frequency of the final (strain-compatible) model
    try:
        w2min = eigsh(Kf, k=1, M=Mf, sigma=0, which="LM", return_eigenvectors=False)
        f1 = float(math.sqrt(max(w2min[0], 0)) / (2 * math.pi))
    except Exception:
        f1 = None
    return {"type": "dynamic", "converged": True, "nodes": nodes3.tolist(), "tris": tris3.tolist(),
            "tri_material": mats.tolist(), "max_acceleration": (max_acc / g).tolist(),
            "max_displacement": max_disp.tolist(), "G_ratio": (G / G0).tolist(), "damping": xi.tolist(),
            "max_shear_strain": gmax.tolist(), "history_times": hist_t, "history_ax": hist_ax,
            "input_times": t[::keep].tolist(), "input_acc": (ag[::keep] / g).tolist(),
            "natural_frequency": f1, "eq_iterations": eq_hist, "g": g}
