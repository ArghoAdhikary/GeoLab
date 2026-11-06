"""Advanced stress-strain models and the nonlinear stress solver that drives them.

* Modified Cam Clay (Roscoe & Burland 1968): yield surface q^2 + M^2 p'(p' - pc) = 0 with
  associated flow, isotropic hardening dpc = pc (1 + e) / (lambda - kappa) d(eps_v^p) and a
  pressure-dependent elastic bulk modulus K = (1 + e) p' / kappa.
* Duncan-Chang hyperbolic (Duncan & Chang 1970): tangent modulus
  Et = (1 - Rf SL)^2 K pa (sigma3 / pa)^n, unload-reload modulus Kur pa (sigma3 / pa)^n.
* Mohr-Coulomb elastic-perfectly plastic (cutting-plane return), linear elastic.

Stresses are effective, tension positive, components [sx, sy, txy, sz] (plane strain).
Each load step is solved with modified Newton iterations; the constitutive equations are
integrated with sub-stepping from the last converged state, so the result does not depend
on the iteration path.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse.linalg import splu

from .sigma import M_VEC, elastic_D, mc_function, mc_gradient

LINEAR, MOHR, CAMCLAY, HYPERBOLIC, VOID = 0, 1, 2, 3, 4
NONLINEAR_MODELS = ("cam_clay", "hyperbolic")
P_MIN = 1.0               # smallest mean effective stress used for stiffness (pressure units)


def D_from_KG(K, G):
    """Elastic matrices (n x 4 x 4) from bulk and shear moduli arrays."""
    K = np.asarray(K, float)[..., None, None]
    G = np.asarray(G, float)[..., None, None]
    mm = np.outer(M_VEC, M_VEC)
    P = np.diag([2.0, 2.0, 1.0, 2.0]) - (2.0 / 3.0) * mm
    return K * mm + G * P


def p_q(s):
    """Mean effective stress (compression +) and deviator stress q of tension-positive stresses."""
    p = -(s[..., 0] + s[..., 1] + s[..., 3]) / 3.0
    sm = -p
    dx, dy, dz = s[..., 0] - sm, s[..., 1] - sm, s[..., 3] - sm
    q = np.sqrt(1.5 * (dx * dx + dy * dy + dz * dz + 2 * s[..., 2] ** 2))
    return p, q


def mcc_yield(s, pc, M):
    p, q = p_q(s)
    return q * q + M * M * p * (p - pc)


def mcc_gradient(s, pc, M):
    """df/dsigma (tension-positive components) and df/dp."""
    p, q = p_q(s)
    sm = -p
    dfdp = M * M * (2 * p - pc)
    a = np.empty(s.shape)
    dev = np.stack([s[..., 0] - sm, s[..., 1] - sm, 2 * s[..., 2], s[..., 3] - sm], axis=-1)
    a[:] = dfdp[..., None] * (-M_VEC / 3.0) + 3.0 * dev        # d(q^2)/dsigma = 3 * dev
    return a, dfdp


def mcc_elastic(s, e, kappa, nu):
    p, _ = p_q(s)
    K = (1 + e) * np.maximum(p, P_MIN) / kappa
    G = 3 * K * (1 - 2 * nu) / (2 * (1 + nu))
    return D_from_KG(K, G)


def mcc_integrate(s, pc, e, deps, lam, kappa, M, nu, nsub=None):
    """Integrate Modified Cam Clay over a strain increment (vectorized). Returns (s, pc, e)."""
    s, pc, e = s.copy(), pc.copy(), e.copy()
    if nsub is None:
        nsub = int(np.clip(np.ceil(np.abs(deps).max() / 5e-4), 1, 100)) if deps.size else 1
    d = deps / nsub
    for _ in range(nsub):
        D = mcc_elastic(s, e, kappa, nu)
        ds_e = np.einsum("nij,nj->ni", D, d)
        trial = s + ds_e
        f0 = mcc_yield(s, pc, M)
        f1 = mcc_yield(trial, pc, M)
        elastic = f1 <= 1e-9 * np.maximum(pc * pc * M * M, 1.0)
        # fraction of the step that is elastic for points that cross the surface
        alpha = np.zeros(len(s))
        cross = (~elastic) & (f0 < 0)
        if cross.any():
            lo, hi = np.zeros(cross.sum()), np.ones(cross.sum())
            sc, dc, pcc = s[cross], ds_e[cross], pc[cross]
            Mc = M[cross]
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                fm = mcc_yield(sc + mid[:, None] * dc, pcc, Mc)
                lo = np.where(fm < 0, mid, lo)
                hi = np.where(fm < 0, hi, mid)
            alpha[cross] = lo
        s_new = trial.copy()
        pl = ~elastic
        if pl.any():
            sp = s[pl] + alpha[pl, None] * ds_e[pl]
            dr = (1 - alpha[pl, None]) * d[pl]
            Dp = D[pl]
            a, dfdp = mcc_gradient(sp, pc[pl], M[pl])
            p, _ = p_q(sp)
            H = M[pl] ** 2 * p * pc[pl] * (1 + e[pl]) / (lam[pl] - kappa[pl]) * dfdp
            Da = np.einsum("nij,nj->ni", Dp, a)
            den = np.einsum("ni,ni->n", a, Da) + H
            dlam = np.maximum(np.einsum("ni,nij,nj->n", a, Dp, dr) / np.where(np.abs(den) > 1e-30, den, 1e-30), 0.0)
            sp = sp + np.einsum("nij,nj->ni", Dp, dr) - dlam[:, None] * Da
            pcp = pc[pl] * np.exp((1 + e[pl]) / (lam[pl] - kappa[pl]) * dlam * dfdp)
            # drift correction back onto the yield surface
            for _ in range(3):
                f = mcc_yield(sp, pcp, M[pl])
                a, dfdp = mcc_gradient(sp, pcp, M[pl])
                p, _ = p_q(sp)
                H = M[pl] ** 2 * p * pcp * (1 + e[pl]) / (lam[pl] - kappa[pl]) * dfdp
                Da = np.einsum("nij,nj->ni", Dp, a)
                den = np.einsum("ni,ni->n", a, Da) + H
                c = f / np.where(np.abs(den) > 1e-30, den, 1e-30)
                sp = sp - c[:, None] * Da
                pcp = pcp * np.exp((1 + e[pl]) / (lam[pl] - kappa[pl]) * c * dfdp)
            s_new[pl] = sp
            pc[pl] = pcp
        e = e + (1 + e) * (d[:, 0] + d[:, 1] + d[:, 3])
        s = s_new
    return s, pc, e


def hyperbolic_Et(s, slmax, mat):
    """Tangent (or unload-reload) Young's modulus of the Duncan-Chang model, and the stress level."""
    smax, smin = _principal(s)
    s1, s3 = -smin, np.maximum(-smax, 0.0)              # compression positive
    pa = mat["pa"]
    s3e = np.maximum(s3, 0.01 * pa)
    sphi, cphi = np.sin(np.radians(mat["phi"])), np.cos(np.radians(mat["phi"]))
    qf = (2 * mat["c"] * cphi + 2 * s3 * sphi) / np.maximum(1 - sphi, 1e-6)
    sl = np.clip((s1 - s3) / np.maximum(qf, 1e-9), 0.0, 0.99)
    Ei = mat["K"] * pa * (s3e / pa) ** mat["n"]
    Et = (1 - mat["Rf"] * sl) ** 2 * Ei
    Eur = mat["Kur"] * pa * (s3e / pa) ** mat["n"]
    unloading = sl < 0.98 * slmax
    return np.where(unloading, Eur, np.maximum(Et, 1e-3 * Ei)), sl


def _principal(s):
    c = 0.5 * (s[..., 0] + s[..., 1])
    r = np.sqrt((0.5 * (s[..., 0] - s[..., 1])) ** 2 + s[..., 2] ** 2)
    a, b, z = c + r, c - r, s[..., 3]
    return np.maximum(np.maximum(a, b), z), np.minimum(np.minimum(a, b), z)


def hyperbolic_integrate(s, slmax, deps, mat, nsub=None):
    s, slmax = s.copy(), slmax.copy()
    if nsub is None:
        nsub = int(np.clip(np.ceil(np.abs(deps).max() / 2e-4), 1, 200)) if deps.size else 1
    d = deps / nsub
    for _ in range(nsub):
        Et, sl = hyperbolic_Et(s, slmax, mat)
        D = np.stack([elastic_D(E, n) for E, n in zip(Et, mat["nu"])]) if len(Et) else np.zeros((0, 4, 4))
        s = s + np.einsum("nij,nj->ni", D, d)
        slmax = np.maximum(slmax, sl)
    _, sl = hyperbolic_Et(s, slmax, mat)
    return s, np.maximum(slmax, sl)


def mc_integrate(s, deps, D, c, sphi, cphi, spsi, cpsi):
    """Elastic predictor and cutting-plane return to the Mohr-Coulomb surface."""
    s = s + np.einsum("nij,nj->ni", D, deps)
    for _ in range(40):
        f = mc_function(s, c, sphi, cphi)
        yl = f > 1e-8 * np.maximum(np.abs(s).max(axis=-1), 1.0)
        if not yl.any():
            break
        sc = np.maximum(np.abs(s[yl]).max(axis=-1), c[yl] + 1.0)
        a = mc_gradient(s[yl], c[yl], sphi[yl], cphi[yl], sc)
        b = mc_gradient(s[yl], c[yl], spsi[yl], cpsi[yl], sc)
        Db = np.einsum("nij,nj->ni", D[yl], b)
        den = np.einsum("ni,ni->n", a, Db)
        s[yl] = s[yl] - (f[yl] / np.where(den > 1e-30, den, 1e-30))[:, None] * Db
    return s


class Constitutive:
    """Per-Gauss-point material state for the nonlinear solver."""

    def __init__(self, project, mesh, model, sig0):
        mats = {m.id: m for m in project.materials}
        ml = [mats[i] for i in mesh.mats]
        ngp = mesh.ngp
        kind = np.array([VOID if m.stress_model == "none" else CAMCLAY if m.stress_model == "cam_clay" else
                         HYPERBOLIC if m.stress_model == "hyperbolic" else
                         MOHR if m.stress_model == "elastic_plastic" else LINEAR for m in ml])
        self.kind = np.repeat(kind, ngp)
        rep = lambda vals: np.repeat(np.asarray(vals, float), ngp)
        self.nu = rep([min(m.nu, 0.49) for m in ml])
        self.lam, self.kappa = rep([m.cc_lambda for m in ml]), rep([m.cc_kappa for m in ml])
        self.M = rep([6 * math.sin(math.radians(m.phi)) / (3 - math.sin(math.radians(m.phi))) for m in ml])
        self.hmat = {"K": rep([m.dc_K for m in ml]), "Kur": rep([m.dc_Kur for m in ml]), "n": rep([m.dc_n for m in ml]),
                     "Rf": rep([m.dc_Rf for m in ml]), "c": rep([m.cohesion for m in ml]), "phi": rep([m.phi for m in ml]),
                     "nu": self.nu, "pa": rep([101.325 if project.units == "metric" else 2116.2] * len(ml))}
        self.D_el = np.repeat(model.D, ngp, axis=0)
        self.c = model.c_gp.ravel()
        self.sphi, self.cphi = np.repeat(model.sphi, ngp), np.repeat(model.cphi, ngp)
        self.spsi, self.cpsi = np.repeat(model.spsi, ngp), np.repeat(model.cpsi, ngp)
        s = sig0.reshape(-1, 4)
        self.s = s.copy()
        p, q = p_q(s)
        pe = np.maximum(p, P_MIN)
        ocr = rep([max(m.ocr, 1.0) for m in ml])
        self.pc = ocr * (pe + q * q / (self.M ** 2 * pe))      # on (OCR = 1) or inside the yield surface
        self.e = rep([m.e0 for m in ml])
        self.slmax = np.zeros(len(s))
        if np.any((self.kind == CAMCLAY) & ~(self.lam > self.kappa)):
            raise ValueError("Modified Cam Clay needs lambda > kappa > 0.")

    def integrate(self, deps):
        """Stresses and new state for a strain increment from the committed state (not committed)."""
        s = self.s.copy()
        pc, e, slmax = self.pc.copy(), self.e.copy(), self.slmax.copy()
        k = self.kind
        for code in (LINEAR, VOID):
            m = k == code
            if m.any():
                s[m] = self.s[m] + np.einsum("nij,nj->ni", self.D_el[m], deps[m])
        m = k == MOHR
        if m.any():
            s[m] = mc_integrate(self.s[m], deps[m], self.D_el[m], self.c[m], self.sphi[m], self.cphi[m],
                                self.spsi[m], self.cpsi[m])
        m = k == CAMCLAY
        if m.any():
            s[m], pc[m], e[m] = mcc_integrate(self.s[m], self.pc[m], self.e[m], deps[m], self.lam[m],
                                              self.kappa[m], self.M[m], self.nu[m])
        m = k == HYPERBOLIC
        if m.any():
            hm = {key: v[m] for key, v in self.hmat.items()}
            s[m], slmax[m] = hyperbolic_integrate(self.s[m], self.slmax[m], deps[m], hm)
        return s, (pc, e, slmax)

    def commit(self, s, state):
        self.s = s
        self.pc, self.e, self.slmax = state

    def tangent(self, s=None, state=None):
        """Stiffness for the equilibrium iterations at a state (committed state when s is None): the
        continuum elastoplastic tangent for Cam Clay points on the yield surface, the tangent modulus for
        the hyperbolic model, elastic otherwise."""
        if s is None:
            s, (pc, e, slmax) = self.s, (self.pc, self.e, self.slmax)
        else:
            pc, e, slmax = state
        D = self.D_el.copy()
        m = self.kind == CAMCLAY
        if m.any():
            Dm = mcc_elastic(s[m], e[m], self.kappa[m], self.nu[m])
            f = mcc_yield(s[m], pc[m], self.M[m])
            on = f > -1e-3 * (self.M[m] * pc[m]) ** 2
            if on.any():
                a, dfdp = mcc_gradient(s[m][on], pc[m][on], self.M[m][on])
                p, _ = p_q(s[m][on])
                lam, kap = self.lam[m][on], self.kappa[m][on]
                H = self.M[m][on] ** 2 * p * pc[m][on] * (1 + e[m][on]) / (lam - kap) * dfdp
                Da = np.einsum("nij,nj->ni", Dm[on], a)
                den = np.einsum("ni,ni->n", a, Da) + H
                ok = den > 1e-12 * np.einsum("ni,ni->n", a, Da)
                Dep = Dm[on] - np.einsum("ni,nj->nij", Da, Da) / np.where(ok, den, 1.0)[:, None, None]
                Dm_on = Dm[on]
                Dm_on[ok] = Dep[ok]
                Dm[on] = Dm_on
            D[m] = Dm
        m = self.kind == HYPERBOLIC
        if m.any():
            hm = {key: v[m] for key, v in self.hmat.items()}
            Et, _ = hyperbolic_Et(s[m], slmax[m], hm)
            D[m] = np.stack([elastic_D(E, n) for E, n in zip(Et, self.nu[m])])
        return D


def solve_nonlinear(mesh, model, cons: Constitutive, fixed, F_total, uc_total, steps, u_gp,
                    max_iter=60, tol=1e-3, progress=None, cancel=None):
    """Load-controlled modified Newton solution. Returns (u, sig, history, converged)."""
    ne, ngp = mesh.ne, mesh.ngp
    cidx = np.array(sorted(fixed), int)
    free = np.setdiff1d(np.arange(2 * mesh.nn), cidx)

    def f_int(sig):
        return mesh.vector(np.einsum("egji,egj,eg->ei", mesh.B, sig.reshape(ne, ngp, 4), mesh.dV))

    f0 = f_int(cons.s)
    u = np.zeros(2 * mesh.nn)
    history, ok_all = [], True
    for k in range(steps):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        F = F_total * (k + 1) / steps
        uc = uc_total * (k + 1) / steps
        def factor(D):
            K = mesh.assemble(np.einsum("egji,egjk,egkl,eg->eil", mesh.B, D.reshape(ne, ngp, 4, 4), mesh.B, mesh.dV))
            return splu(K[free][:, free].tocsc()), K[free][:, cidx]
        lu, Kfc = factor(cons.tangent())
        du = np.zeros(2 * mesh.nn)
        du[cidx] = uc - u[cidx]
        R = F - (f_int(cons.s) - f0)
        du[free] = lu.solve(R[free] - Kfc @ du[cidx])
        scale = max(np.abs(F).max(), np.abs(f0).max() * 1e-3, 1e-9)
        conv = False
        for it in range(1, max_iter + 1):
            deps = np.einsum("egij,ej->egi", mesh.B, du[mesh.dof]).reshape(-1, 4)
            s, state = cons.integrate(deps)
            R = F - (f_int(s) - f0)
            res = float(np.abs(R[free]).max())
            if res <= tol * scale:
                conv = True
                break
            if it <= 8:                       # full Newton early on, then keep the last tangent
                lu, Kfc = factor(cons.tangent(s, state))
            ddu = np.zeros(2 * mesh.nn)
            ddu[free] = lu.solve(R[free])
            du += ddu
            if np.abs(ddu).max() <= 1e-4 * max(np.abs(du).max(), 1e-12):
                deps = np.einsum("egij,ej->egi", mesh.B, du[mesh.dof]).reshape(-1, 4)
                s, state = cons.integrate(deps)
                res = float(np.abs((F - (f_int(s) - f0))[free]).max())
                conv = True
                break
        cons.commit(s, state)
        u += du
        ok_all &= conv
        history.append({"step": k + 1, "iterations": it, "converged": conv,
                        "max_disp": float(np.max(np.hypot(u[0::2], u[1::2]))), "residual": res / scale})
        if progress:
            progress(int(100 * (k + 1) / steps))
    return u, cons.s.reshape(ne, ngp, 4), history, ok_all
