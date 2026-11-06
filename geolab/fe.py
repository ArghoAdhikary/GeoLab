"""Finite element building blocks shared by the field solvers.

Linear triangles (T3) for the diffusion-type problems (seepage, heat, air flow,
contaminant transport) and quadratic triangles (T6) for stress-deformation.

`solve_diffusion` handles  S(u)_t = div(K(u) grad u) + f  with Dirichlet, flux and
convective boundaries, steady or transient (backward Euler), using the modified
Picard scheme of Celia et al. (1990) so the storage term conserves mass/energy.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from .geometry import dist_point_polyline


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
class T3:
    """Linear triangle mesh with precomputed shape-function gradients."""

    def __init__(self, nodes, tris, mats):
        self.nodes = np.asarray(nodes, float)
        self.tris = np.asarray(tris, int)
        self.mats = np.asarray(mats)
        P = self.nodes[self.tris]
        x, y = P[:, :, 0], P[:, :, 1]
        self.b = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], axis=1)
        self.c = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], axis=1)
        self.A = 0.5 * (self.b[:, 0] * self.c[:, 1] - self.b[:, 1] * self.c[:, 0])
        self.Kb = np.einsum("ei,ej->eij", self.b, self.b) / (4 * self.A)[:, None, None]
        self.Kc = np.einsum("ei,ej->eij", self.c, self.c) / (4 * self.A)[:, None, None]
        self.rows = np.repeat(self.tris, 3, axis=1).ravel()
        self.cols = np.tile(self.tris, (1, 3)).ravel()
        self.xc = x.mean(axis=1)
        self.yc = y.mean(axis=1)
        self.nn = len(self.nodes)
        self.ne = len(self.tris)
        # lumped nodal area
        self.lump = np.bincount(self.tris.ravel(), weights=np.repeat(self.A / 3.0, 3), minlength=self.nn)
        self._edges = None

    def assemble(self, Ke):
        return coo_matrix((Ke.ravel(), (self.rows, self.cols)), shape=(self.nn, self.nn)).tocsr()

    def stiffness(self, kx, ky):
        return self.assemble(kx[:, None, None] * self.Kb + ky[:, None, None] * self.Kc)

    def gradient(self, u):
        u = np.asarray(u)[self.tris]
        return (self.b * u).sum(axis=1) / (2 * self.A), (self.c * u).sum(axis=1) / (2 * self.A)

    def boundary_edges(self):
        if self._edges is None:
            e = np.sort(np.vstack([self.tris[:, [0, 1]], self.tris[:, [1, 2]], self.tris[:, [2, 0]]]), axis=1)
            uniq, cnt = np.unique(e, axis=0, return_counts=True)
            self._edges = uniq[cnt == 1]
        return self._edges

    def edges_on(self, pts, tol):
        """Boundary edges lying along a polyline."""
        out = []
        for a, b in self.boundary_edges():
            pa, pb = self.nodes[a], self.nodes[b]
            m = 0.5 * (pa + pb)
            if (dist_point_polyline(*pa, pts) <= tol and dist_point_polyline(*pb, pts) <= tol
                    and dist_point_polyline(*m, pts) <= tol):
                out.append((a, b))
        return out

    def nodes_on(self, pts, tol):
        return [i for i, (x, y) in enumerate(self.nodes) if dist_point_polyline(x, y, pts) <= tol]

    def edge_load(self, edges, q):
        """Nodal equivalent of a uniform unit flux q along edges (q may be per-edge array)."""
        f = np.zeros(self.nn)
        q = np.broadcast_to(np.asarray(q, float), (len(edges),))
        for (a, b), qq in zip(edges, q):
            L = float(np.hypot(*(self.nodes[b] - self.nodes[a])))
            f[a] += 0.5 * qq * L
            f[b] += 0.5 * qq * L
        return f

    def edge_mass(self, edges, h):
        """Consistent boundary 'mass' matrix of h along edges (convective boundaries)."""
        r, c, v = [], [], []
        for a, b in edges:
            L = float(np.hypot(*(self.nodes[b] - self.nodes[a])))
            for i, j, w in ((a, a, 2), (b, b, 2), (a, b, 1), (b, a, 1)):
                r.append(i); c.append(j); v.append(h * L * w / 6.0)
        return coo_matrix((v, (r, c)), shape=(self.nn, self.nn)).tocsr()


def time_steps(duration, n, growth=1.0):
    """Step sizes summing to duration with a constant growth ratio between steps."""
    n = max(1, int(n))
    if abs(growth - 1.0) < 1e-12:
        return np.full(n, duration / n)
    w = growth ** np.arange(n)
    return duration * w / w.sum()


def solve_fixed(K, rhs, fixed: dict):
    """Solve K u = rhs with prescribed values u[i] = v."""
    nn = K.shape[0]
    u = np.zeros(nn)
    if fixed:
        fidx = np.fromiter(fixed.keys(), int)
        fval = np.fromiter(fixed.values(), float)
        u[fidx] = fval
        free = np.setdiff1d(np.arange(nn), fidx)
        Kff = K[free][:, free].tocsc()
        u[free] = spsolve(Kff, rhs[free] - K[free][:, fidx] @ fval)
    else:
        u[:] = spsolve(K.tocsc(), rhs)
    if not np.all(np.isfinite(u)):
        raise RuntimeError("The solver produced invalid values. Check material properties and boundary conditions.")
    return u


# ---------------------------------------------------------------------------
# Nonlinear diffusion
# ---------------------------------------------------------------------------
class DiffusionProblem:
    """Callbacks describing one diffusion problem; subclasses override what they need."""

    def conductivity(self, u):           # -> (kx, ky) per element
        raise NotImplementedError

    def storage(self, u):                # -> nodal stored quantity per unit volume, and its derivative
        return None, None

    def boundary(self, t, u):            # -> fixed dict, nodal flux vector, robin matrix (or None)
        raise NotImplementedError

    def review(self, u, react, fixed, flux) -> bool:
        """Adjust review boundaries (seepage faces etc.). Return True when something changed."""
        return False


def _picard(mesh, prob, u, t, dt, max_iter, tol, relax, cancel, history):
    """One steady solve or one backward-Euler step. Returns (u, converged, react, iterations)."""
    from scipy.sparse import diags
    S_old = prob.storage(u)[0] if dt is not None else None
    u_it = u.copy()
    react = np.zeros(mesh.nn)
    for it in range(1, max_iter + 1):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        kx, ky = prob.conductivity(u_it)
        K = mesh.stiffness(kx, ky)
        fixed, flux, R = prob.boundary(t, u_it)
        rhs = flux.copy()
        if R is not None:
            K = K + R[0]
            rhs = rhs + R[1]
        if dt is not None:
            S, dS = prob.storage(u_it)
            if getattr(prob, "chord", False):      # chord slope: robust across phase-change kinks
                d = u_it - u
                big = np.abs(d) > 1e-8
                dS = np.where(big, (S - S_old) / np.where(big, d, 1.0), dS)
                dS = np.maximum(dS, 1e-12)
            M = mesh.lump * dS / dt
            rhs = rhs - mesh.lump * (S - S_old) / dt + M * u_it
            K = K + diags(M)
        un = solve_fixed(K, rhs, fixed)
        if getattr(prob, "line_search", False) and dt is not None:
            un = _line_search(mesh, prob, u_it, un, t, dt, S_old, fixed)
        react = K @ un - rhs
        changed = prob.review(un, react, fixed, flux)
        du = float(np.max(np.abs(un - u_it)))
        history.append(du)
        if du < tol and not changed:
            return un, True, react, it
        u_it = relax * un + (1 - relax) * u_it if it > 1 and relax < 1 else un
    return u_it, False, react, max_iter


def _residual(mesh, prob, u, t, dt, S_old, free):
    kx, ky = prob.conductivity(u)
    K = mesh.stiffness(kx, ky)
    _, flux, R = prob.boundary(t, u)
    r = K @ u - flux
    if R is not None:
        r = r + R[0] @ u - R[1]
    r = r + mesh.lump * (prob.storage(u)[0] - S_old) / dt
    return float(np.linalg.norm(r[free]))


def _line_search(mesh, prob, u0, u1, t, dt, S_old, fixed):
    """Backtrack along u0 -> u1 until the transient residual decreases (guards against the
    two-state cycles that a kinked storage function, e.g. latent heat, can cause)."""
    free = np.ones(mesh.nn, bool)
    free[list(fixed)] = False
    r0 = _residual(mesh, prob, u0, t, dt, S_old, free)
    step = 1.0
    while step > 1.0 / 64:
        trial = u0 + step * (u1 - u0)
        trial[~free] = u1[~free]
        if _residual(mesh, prob, trial, t, dt, S_old, free) <= r0:
            return trial
        step *= 0.5
    trial = u0 + step * (u1 - u0)
    trial[~free] = u1[~free]
    return trial


def solve_diffusion(mesh: T3, prob: DiffusionProblem, u0, steps=None, max_iter=50, tol=1e-5,
                    relax=1.0, cancel=None, on_step=None, max_cuts=8):
    """Steady (steps=None) or transient solution. Returns (u, history, converged_all, react, n_iter).

    A transient step that does not converge is split in halves (up to max_cuts times)."""
    u = np.array(u0, float)
    history: list[float] = []
    if steps is None:
        u, ok, react, it = _picard(mesh, prob, u, None, None, max_iter, tol, relax, cancel, history)
        if on_step:
            on_step(0, None, u, react)
        return u, history, ok, react, it
    ok_all = True
    it_total = 0
    react = np.zeros(mesh.nn)
    t = 0.0
    for k, dt in enumerate(steps):
        t_end = t + dt
        sub = [dt]
        cuts = 0
        rate_sum = np.zeros(mesh.nn)            # time-averaged reaction over the sub-steps
        while sub:
            h = sub.pop(0)
            un, ok, r, it = _picard(mesh, prob, u, t + h, h, max_iter, tol, relax, cancel, history)
            it_total += it
            if not ok and cuts < max_cuts:
                cuts += 1
                sub[:0] = [0.5 * h, 0.5 * h]
                continue
            ok_all &= ok
            u = un
            rate_sum += r * h
            t += h
        react = rate_sum / dt
        t = t_end
        if on_step:
            on_step(k, t, u, react)
    return u, history, ok_all, react, it_total


# ---------------------------------------------------------------------------
# Quadratic triangles for stress analysis
# ---------------------------------------------------------------------------
def to_t6(nodes, tris):
    """Add mid-side nodes. Returns (nodes6, tris6) with tris6 ordered [n1, n2, n3, n12, n23, n31]."""
    nodes = np.asarray(nodes, float)
    edges = {}
    extra = []
    t6 = np.zeros((len(tris), 6), int)
    nn = len(nodes)
    for e, t in enumerate(tris):
        t6[e, :3] = t
        for k, (a, b) in enumerate(((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))):
            key = (min(a, b), max(a, b))
            if key not in edges:
                edges[key] = nn + len(extra)
                extra.append(0.5 * (nodes[a] + nodes[b]))
            t6[e, 3 + k] = edges[key]
    return np.vstack([nodes, np.array(extra).reshape(-1, 2)]), t6


# 3-point (degree 2) and 6-point (degree 4) Gauss rules on the reference triangle (area 1/2)
GAUSS3 = (np.array([[1 / 6, 1 / 6], [2 / 3, 1 / 6], [1 / 6, 2 / 3]]), np.full(3, 1 / 6))
_a, _b = 0.445948490915965, 0.091576213509771
_wa, _wb = 0.223381589678011 / 2, 0.109951743655322 / 2
GAUSS6 = (np.array([[_a, _a], [1 - 2 * _a, _a], [_a, 1 - 2 * _a], [_b, _b], [1 - 2 * _b, _b], [_b, 1 - 2 * _b]]),
          np.array([_wa, _wa, _wa, _wb, _wb, _wb]))


def t6_shape(xi, eta):
    """Shape functions and their reference derivatives for the 6-node triangle."""
    L1, L2, L3 = 1 - xi - eta, xi, eta
    N = np.array([L1 * (2 * L1 - 1), L2 * (2 * L2 - 1), L3 * (2 * L3 - 1), 4 * L1 * L2, 4 * L2 * L3, 4 * L3 * L1])
    dxi = np.array([-(4 * L1 - 1), 4 * L2 - 1, 0.0, 4 * (L1 - L2), 4 * L3, -4 * L3])
    deta = np.array([-(4 * L1 - 1), 0.0, 4 * L3 - 1, -4 * L2, 4 * L2, 4 * (L1 - L3)])
    return N, dxi, deta


def t3_shape(xi, eta):
    return np.array([1 - xi - eta, xi, eta])


def edge_t6_load(nodes, a, m, b, qn, qt=0.0):
    """Consistent nodal forces of uniform normal (qn, compression +) and tangential traction on a
    straight quadratic edge a-m-b of a body lying to the left of a->b (counter-clockwise boundary)."""
    pa, pb = nodes[a], nodes[b]
    d = pb - pa
    L = float(np.hypot(*d))
    if L == 0:
        return {}
    t = d / L
    n_out = np.array([t[1], -t[0]])          # outward normal for a CCW boundary
    trac = -qn * n_out + qt * t
    w = (L / 6.0, 4 * L / 6.0, L / 6.0)
    return {a: w[0] * trac, m: w[1] * trac, b: w[2] * trac}


def seg_tri_length(p, q, tri_pts):
    """Length of segment pq inside a triangle (Liang-Barsky clipping against the 3 edges)."""
    t0, t1 = 0.0, 1.0
    d = q - p
    P = tri_pts
    area = (P[1, 0] - P[0, 0]) * (P[2, 1] - P[0, 1]) - (P[2, 0] - P[0, 0]) * (P[1, 1] - P[0, 1])
    s = 1.0 if area > 0 else -1.0
    for i in range(3):
        a, b = P[i], P[(i + 1) % 3]
        e = b - a
        nx, ny = -e[1] * s, e[0] * s           # inward normal
        num = nx * (p[0] - a[0]) + ny * (p[1] - a[1])
        den = nx * d[0] + ny * d[1]
        if abs(den) < 1e-15:
            if num < 0:
                return 0.0
            continue
        t = -num / den
        if den > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * float(np.hypot(*d))


def section_flux(mesh: T3, vx, vy, pts):
    """Total flow across a polyline (positive to the right of the drawing direction)."""
    total = 0.0
    pts = np.asarray(pts, float)
    for k in range(len(pts) - 1):
        p, q = pts[k], pts[k + 1]
        d = q - p
        L = float(np.hypot(*d))
        if L == 0:
            continue
        n = np.array([d[1], -d[0]]) / L
        lo, hi = np.minimum(p, q), np.maximum(p, q)
        P = mesh.nodes[mesh.tris]
        cand = np.where((P[:, :, 0].max(1) >= lo[0]) & (P[:, :, 0].min(1) <= hi[0]) &
                        (P[:, :, 1].max(1) >= lo[1]) & (P[:, :, 1].min(1) <= hi[1]))[0]
        for e in cand:
            ln = seg_tri_length(p, q, P[e])
            if ln > 0:
                total += (vx[e] * n[0] + vy[e] * n[1]) * ln
    return total


def nodal_average(mesh_tris, values, nn):
    """Average element values to nodes."""
    tris = np.asarray(mesh_tris)
    s = np.bincount(tris.ravel(), weights=np.repeat(values, tris.shape[1]), minlength=nn)
    c = np.bincount(tris.ravel(), minlength=nn)
    return s / np.maximum(c, 1)


def interpolator(nodes, values):
    """Linear interpolation on the node cloud with nearest-neighbour fallback outside the hull."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    nodes = np.asarray(nodes, float)
    values = np.asarray(values, float)
    lin = LinearNDInterpolator(nodes, values)
    near = NearestNDInterpolator(nodes, values)

    def f(x, y):
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        v = lin(x, y)
        bad = ~np.isfinite(v) if v.ndim == 1 else ~np.all(np.isfinite(v), axis=-1)
        if bad.any():
            v[bad] = near(x[bad], y[bad])
        return v
    return f


def mesh_size_tol(size):
    return 0.1 * size if size > 0 else 1e-6


def hypot_len(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])
