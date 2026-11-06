"""Contaminant transport: advection-dispersion with adsorption and decay, plus particle tracking.

Solves  theta R dc/dt + q.grad(c) = div(theta D grad c) - lambda theta R c  on linear
triangles with Crank-Nicolson time stepping. The Darcy flux q and water content theta come
from the parent seepage analysis. theta D = (aL - aT) q q^T/|q| + (aT |q| + theta D*) I.
Retardation R = 1 + rho_d Kd / theta; lambda = ln 2 / half-life. When the grid Peclet
number exceeds 1 an optimal streamline diffusion term is added to suppress oscillations.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix, diags
from .linsolve import factorize as splu

from .fe import T3, interpolator, time_steps
from .geometry import point_in_polygon, validate_geometry
from .seep import generate_mesh


def run_transport(project, analysis, progress=None, cancel=None, seep_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    if not seep_results:
        raise ValueError("Contaminant transport needs a solved seepage analysis as its parent (for the flow field).")
    nodes = np.asarray(seep_results["nodes"], float)
    tris = np.asarray(seep_results["tris"], int)
    tmat = np.asarray(seep_results["tri_material"])
    mesh = T3(nodes, tris, tmat)
    mats = {m.id: m for m in project.materials}
    qx = np.asarray(seep_results["vx"], float)
    qy = np.asarray(seep_results["vy"], float)
    if seep_results.get("water_content"):
        th = np.asarray(seep_results["water_content"], float)[tris].mean(axis=1)
    else:
        th = np.array([mats[i].theta_s for i in tmat], float)
    th = np.maximum(th, 1e-3)
    aL = np.array([mats[i].disp_l for i in tmat])
    aT = np.array([mats[i].disp_t for i in tmat])
    Dm = np.array([mats[i].diffusion for i in tmat])
    R = 1.0 + np.array([mats[i].dry_density * mats[i].kd for i in tmat]) / th
    hl = np.array([mats[i].half_life for i in tmat])
    lam = np.where(hl > 0, math.log(2) / np.where(hl > 0, hl, 1.0), 0.0)
    qa = np.hypot(qx, qy)
    # dispersion tensor (times theta)
    with np.errstate(invalid="ignore", divide="ignore"):
        ux = np.where(qa > 0, qx / qa, 0.0)
        uy = np.where(qa > 0, qy / qa, 0.0)
    h_e = np.sqrt(2 * mesh.A)
    v = qa / th
    Dl = aL * v + Dm
    Pe = v * h_e / np.maximum(2 * Dl, 1e-300)
    with np.errstate(invalid="ignore", divide="ignore"):
        xi = np.where(Pe > 1, 1 / np.tanh(Pe) - 1 / Pe, 0.0)
    D_sd = xi * v * h_e / 2                        # optimal streamline diffusion (1D)
    tDxx = (aL - aT) * qa * ux * ux + (aT * qa + th * Dm) + th * D_sd * ux * ux
    tDyy = (aL - aT) * qa * uy * uy + (aT * qa + th * Dm) + th * D_sd * uy * uy
    tDxy = (aL - aT) * qa * ux * uy + th * D_sd * ux * uy
    b, c = mesh.b, mesh.c
    Kd = (tDxx[:, None, None] * np.einsum("ei,ej->eij", b, b) + tDyy[:, None, None] * np.einsum("ei,ej->eij", c, c)
          + tDxy[:, None, None] * (np.einsum("ei,ej->eij", b, c) + np.einsum("ei,ej->eij", c, b))) / (4 * mesh.A)[:, None, None]
    Ka = np.repeat(((qx[:, None] * b + qy[:, None] * c) / 6.0)[:, None, :], 3, axis=1)   # row i: integral N_i q.grad N_j
    K = mesh.assemble(Kd + Ka)
    cap = np.bincount(tris.ravel(), weights=np.repeat(th * R * mesh.A / 3, 3), minlength=mesh.nn)
    dec = np.bincount(tris.ravel(), weights=np.repeat(lam * th * R * mesh.A / 3, 3), minlength=mesh.nn)
    K = K + diags(dec)
    tol = 0.1 * analysis.mesh_size
    bcs = []
    for bc in project.bcs("transport", analysis):
        nds = mesh.nodes_on(bc.points, tol)
        if not nds:
            raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node.")
        bcs.append((bc, nds, mesh.edges_on(bc.points, tol)))

    def boundary(t):
        fixed, f = {}, np.zeros(mesh.nn)
        for bc, nds, edges in bcs:
            if bc.type == "concentration":
                fixed.update({i: bc.at(t) for i in nds})
            elif bc.type == "mass_flux":
                f += mesh.edge_load(edges, bc.at(t))
        return fixed, f

    c0 = np.full(mesh.nn, float(analysis.initial_value) if analysis.initial == "value" else 0.0)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth)
    cn = c0.copy()
    t = 0.0
    times, hist = [0.0], [c0.tolist()]
    M = diags(cap)
    mass0 = float(np.sum(cap * c0))
    lu_cache = {}
    for k, dt in enumerate(steps):
        if cancel and cancel():
            raise RuntimeError("Cancelled")
        fixed, f1 = boundary(t + dt)
        _, f0 = boundary(t)
        A = (M / dt + 0.5 * K).tocsr()
        rhs = (M / dt - 0.5 * K) @ cn + 0.5 * (f0 + f1)
        cidx = np.array(sorted(fixed), int)
        free = np.setdiff1d(np.arange(mesh.nn), cidx)
        cv = np.array([fixed[i] for i in cidx])
        key = (round(dt, 12), tuple(cidx))
        if key not in lu_cache:
            lu_cache = {key: splu(A[free][:, free].tocsc())}
        cnew = np.zeros(mesh.nn)
        cnew[cidx] = cv
        cnew[free] = lu_cache[key].solve(rhs[free] - A[free][:, cidx] @ cv)
        cn = cnew
        t += dt
        times.append(float(t))
        hist.append(cn.tolist())
        if progress:
            progress(int(100 * (k + 1) / len(steps)))
    gx, gy = mesh.gradient(cn)
    res = {"type": "transport", "converged": True, "nodes": nodes.tolist(), "tris": tris.tolist(),
           "tri_material": tmat.tolist(), "concentration": cn.tolist(), "times": times,
           "concentration_history": hist, "mass_in_domain": float(np.sum(cap * cn)), "mass_initial": mass0,
           "max_grid_peclet": float(Pe.max()) if len(Pe) else 0.0}
    if analysis.particles:
        res["particles"] = track_particles(project, mesh, qx / th, qy / th, analysis.particles,
                                           analysis.duration, R)
    return res


def track_particles(project, mesh: T3, vx, vy, starts, duration, R=None, max_steps=4000):
    """Advective particle paths (pore velocity, optionally retarded). Returns paths and times."""
    from scipy.spatial import cKDTree
    nn = mesh.nn
    w = np.bincount(mesh.tris.ravel(), weights=np.repeat(mesh.A, 3), minlength=nn)
    rr = np.ones(mesh.ne) if R is None else R
    vxn = np.bincount(mesh.tris.ravel(), weights=np.repeat(mesh.A * vx / rr, 3), minlength=nn) / w
    vyn = np.bincount(mesh.tris.ravel(), weights=np.repeat(mesh.A * vy / rr, 3), minlength=nn) / w
    from scipy.interpolate import LinearNDInterpolator
    fx = LinearNDInterpolator(mesh.nodes, vxn)
    fy = LinearNDInterpolator(mesh.nodes, vyn)
    size = float(np.sqrt(np.median(mesh.A)))
    out = []
    regions = [r.points for r in project.regions]
    for x0, y0 in starts:
        p = np.array([x0, y0], float)
        path, t = [p.tolist()], 0.0
        for _ in range(max_steps):
            v = np.array([fx(*p), fy(*p)], float).ravel()
            if not np.all(np.isfinite(v)):
                break
            sp = float(np.hypot(*v))
            if sp <= 0:
                break
            dt = min(0.25 * size / sp, duration - t)
            if dt <= 0:
                break
            mid = p + 0.5 * dt * v
            vm = np.array([fx(*mid), fy(*mid)], float).ravel()
            if not np.all(np.isfinite(vm)):
                vm = v
            pn = p + dt * vm
            if not any(point_in_polygon(pn[0], pn[1], r) for r in regions):
                # step to the boundary by bisection
                lo, hi = 0.0, 1.0
                for _ in range(30):
                    m = 0.5 * (lo + hi)
                    q = p + m * dt * vm
                    if any(point_in_polygon(q[0], q[1], r) for r in regions):
                        lo = m
                    else:
                        hi = m
                p = p + lo * dt * vm
                t += lo * dt
                path.append(p.tolist())
                break
            p = pn
            t += dt
            path.append(p.tolist())
        out.append({"start": [float(x0), float(y0)], "path": path, "time": t})
    return out
