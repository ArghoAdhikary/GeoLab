"""Dynamic (earthquake) analysis: plane strain, 6-node triangles, Newmark time integration.

The input acceleration time history acts at the base: the equations are written in
displacements relative to the base, M a_rel + C v_rel + K u_rel = -M r a_g(t), with the
nodes fixed by the stress boundary conditions moving with the base. Damping is Rayleigh
damping set per element from its damping ratio at the first natural frequency of the
model and five times that frequency. With equivalent linear analysis the shear modulus
and damping of each element follow hyperbolic modulus-reduction and damping curves of
the effective shear strain (0.65 x maximum), iterated until they agree.

Pore pressure generation (optional, for materials with a cyclic resistance ratio): every half
cycle of horizontal shear stress in an element adds damage 0.5 / N_L, where N_L is the number of
uniform cycles that liquefies the soil at that stress ratio, from CRR(N) = CRR15 (N / 15)^-b. The
excess pore pressure ratio follows Seed, Martin and Lysmer (1976) / Booker et al. (1976):

    ru = (2 / pi) arcsin(D^(1 / (2 alpha)))

reaching 1 (liquefaction) when the damage D = sum(0.5 / N_L) reaches 1. The shear modulus of
the next iteration is reduced by sqrt(1 - ru), as the effective stress falls.
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


def ru_from_damage(D, alpha=0.7):
    """Excess pore pressure ratio from the cyclic damage D = N / N_L (Seed et al. 1976)."""
    D = np.clip(np.asarray(D, float), 0.0, 1.0)
    return (2.0 / math.pi) * np.arcsin(D ** (1.0 / (2.0 * alpha)))


def cycles_to_liquefy(csr, crr15, b=0.34):
    """Number of uniform cycles N_L at a cyclic stress ratio, from CRR(N) = CRR15 (N / 15)^-b."""
    csr = np.maximum(np.asarray(csr, float), 1e-12)
    return 15.0 * (csr / np.maximum(crr15, 1e-12)) ** (-1.0 / np.maximum(b, 1e-6))


class _Damage:
    """Half-cycle counting of the horizontal shear stress of each element."""

    def __init__(self, sv_eff, crr, b, alpha):
        self.sv, self.crr, self.b, self.alpha = sv_eff, crr, b, alpha
        self.on = crr > 0
        n = len(sv_eff)
        self.D = np.zeros(n)
        self.sign = np.zeros(n)
        self.peak = np.zeros(n)
        self.t_liq = np.full(n, np.nan)

    def _close(self, mask):
        if mask.any():
            csr = self.peak[mask] / self.sv[mask]
            self.D[mask] += 0.5 / cycles_to_liquefy(csr, self.crr[mask], self.b[mask])
            self.peak[mask] = 0.0

    def step(self, tau, t):
        sg = np.sign(tau)
        flip = self.on & (sg != 0) & (self.sign != 0) & (sg != self.sign)
        self._close(flip)
        self.sign = np.where(sg != 0, sg, self.sign)
        self.peak = np.maximum(self.peak, np.abs(tau))
        new = self.on & np.isnan(self.t_liq) & (self.D >= 1.0)
        self.t_liq[new] = t

    def finish(self):
        self._close(self.on & (self.peak > 0))
        return np.where(self.on, ru_from_damage(self.D, self.alpha), 0.0)


def _initial_effective(project, mesh):
    """Vertical effective stress before the earthquake at each element (overburden minus the
    hydrostatic pore pressure below the piezometric line)."""
    from .geometry import polyline_y
    from .sigma import overburden
    x, y = mesh.gx.mean(axis=1), mesh.gy.mean(axis=1)
    sv = overburden(project, x, y)
    u = np.zeros_like(sv)
    if len(project.piezometric_line) >= 2:
        u = project.gamma_w * np.clip(np.asarray(polyline_y(project.piezometric_line, x), float) - y, 0.0, None)
    return np.maximum(sv - u, 1e-3 * max(float(np.max(sv)), 1.0)), x, y


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
    crr = np.array([m.liq_crr for m in ml], float)
    pwp_on = bool(getattr(analysis, "pwp_generation", False)) and bool(np.any(crr > 0))
    if getattr(analysis, "pwp_generation", False) and not pwp_on:
        raise ValueError("Pore pressure generation needs a cyclic resistance ratio (CRR) for at least one "
                         "material (Materials > Dynamic).")
    if pwp_on:
        sv_eff0, _, _ = _initial_effective(project, mesh)
        liq_b = np.array([m.liq_b for m in ml], float)
        liq_a = np.array([m.liq_alpha for m in ml], float)
        n_iter = max(n_iter, 3)
    ru = np.zeros(mesh.ne)
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
        dmg = _Damage(sv_eff0, crr, liq_b, liq_a) if pwp_on else None
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
            if dmg is not None:
                dmg.step(G * eps[..., 2].mean(axis=1), t[k])
            if k % keep == 0:
                hist_t.append(float(t[k]))
                hist_ax.append((ax_tot / g).tolist())
            if progress and k % 50 == 0:
                progress(int(100 * (itn + k / len(t)) / n_iter))
        if dmg is not None:
            ru = dmg.finish()
            t_liq = dmg.t_liq
        if n_iter == 1:
            break
        geff = 0.65 * gmax
        ratio = np.where(gref > 0, 1 / (1 + geff / np.where(gref > 0, gref, 1)), 1.0)
        Gn = G0 * ratio * np.maximum(np.sqrt(np.clip(1.0 - ru, 0.0, 1.0)), 0.05)
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
    extra = {}
    if pwp_on:
        A = mesh.dV.sum(axis=1)
        liq = ru >= 0.95
        extra = {"ru": ru.tolist(), "excess_pwp": (ru * sv_eff0).tolist(), "sv_eff0": sv_eff0.tolist(),
                 "liquefied": liq.astype(int).tolist(), "liquefied_area": float(A[liq].sum()),
                 "time_liquefied": [None if not np.isfinite(v) else float(v) for v in t_liq],
                 "max_ru": float(ru.max()) if len(ru) else 0.0}
    return {**extra, "type": "dynamic", "converged": True, "nodes": nodes3.tolist(), "tris": tris3.tolist(),
            "tri_material": mats.tolist(), "max_acceleration": (max_acc / g).tolist(),
            "max_displacement": max_disp.tolist(), "G_ratio": (G / G0).tolist(), "damping": xi.tolist(),
            "max_shear_strain": gmax.tolist(), "history_times": hist_t, "history_ax": hist_ax,
            "input_times": t[::keep].tolist(), "input_acc": (ag[::keep] / g).tolist(),
            "natural_frequency": f1, "eq_iterations": eq_hist, "g": g}
