"""Air flow through the pore space (finite element, steady or transient).

Solves  (theta_a / P_abs) dP/dt = div((k_a / gamma_w) grad P)  for the gauge air pressure P,
with the air phase treated as an ideal gas at near-atmospheric pressure (density effects
and buoyancy neglected). The air conductivity falls as the soil wets up:
k_a = k_air_dry * (1 - Se)^0.5 * (1 - Se^(1/m))^(2m), m = 1 - 1/n (Mualem non-wetting
phase), with the degree of saturation Se taken from a parent seepage analysis when
there is one (otherwise the soil is treated as dry).
"""
from __future__ import annotations

import numpy as np

from .fe import DiffusionProblem, T3, interpolator, time_steps, solve_diffusion
from .geometry import validate_geometry
from .seep import generate_mesh

P_ATM = {"metric": 101.325, "imperial": 2116.2}


class _AirProblem(DiffusionProblem):
    def __init__(self, project, analysis, mesh: T3, seep_results):
        self.m = mesh
        mats = {m.id: m for m in project.materials}
        ml = [mats[i] for i in mesh.mats]
        if seep_results and seep_results.get("water_content"):
            th = interpolator(seep_results["nodes"], seep_results["water_content"])(mesh.nodes[:, 0], mesh.nodes[:, 1])
            th_e = th[mesh.tris].mean(axis=1)
        else:
            th_e = np.array([m.theta_r for m in ml])
        ts = np.array([m.theta_s for m in ml])
        tr = np.array([m.theta_r for m in ml])
        Se = np.clip((th_e - tr) / np.maximum(ts - tr, 1e-9), 0.0, 1.0)
        mm = np.array([1 - 1 / max(m.vg_n, 1.001) for m in ml])
        kr = np.sqrt(1 - Se) * (1 - Se ** (1 / mm)) ** (2 * mm)
        self.k = np.array([m.k_air for m in ml]) * np.maximum(kr, 1e-9) / project.gamma_w
        theta_a_e = np.clip(ts - th_e, 1e-4, None)
        self.cap = np.bincount(mesh.tris.ravel(), weights=np.repeat(theta_a_e * mesh.A / 3, 3),
                               minlength=mesh.nn) / mesh.lump
        self.Pabs = P_ATM.get(project.units, 101.325)
        tol = 0.1 * analysis.mesh_size
        self.bcs = []
        for bc in project.bcs("air", analysis):
            nodes = mesh.nodes_on(bc.points, tol)
            if not nodes:
                raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node.")
            self.bcs.append((bc, nodes, mesh.edges_on(bc.points, tol)))
        if not any(bc.type == "air_pressure" for bc, *_ in self.bcs):
            raise ValueError("An air flow analysis needs at least one air pressure boundary condition.")

    def conductivity(self, P):
        return self.k, self.k

    def storage(self, P):
        dS = self.cap / (self.Pabs + np.maximum(P, -0.9 * self.Pabs))
        return self.cap * np.log1p(P / self.Pabs), dS   # integral of theta_a / (Patm + P) dP

    def boundary(self, t, P):
        fixed, flux = {}, np.zeros(self.m.nn)
        for bc, nodes, edges in self.bcs:
            if bc.type == "air_pressure":
                fixed.update({i: bc.at(t) for i in nodes})
            elif bc.type == "air_flux":
                flux += self.m.edge_load(edges, bc.at(t))
        return fixed, flux, None


def run_air(project, analysis, progress=None, cancel=None, seep_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    nodes, tris, tmat = generate_mesh(project, analysis.mesh_size)
    mesh = T3(nodes, tris, tmat)
    prob = _AirProblem(project, analysis, mesh, seep_results)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth) if analysis.transient else None
    P0 = np.full(mesh.nn, float(analysis.initial_value) if analysis.initial == "value" else 0.0)
    times, hist = [0.0], [P0.tolist()]

    def on_step(k, t, P, react):
        if t is not None:
            times.append(float(t))
            hist.append(P.tolist())
            if progress:
                progress(min(99, int(100 * (k + 1) / len(steps))))

    P, history, ok, react, it = solve_diffusion(mesh, prob, P0, steps, max_iter=analysis.max_iter,
                                                tol=analysis.tolerance, cancel=cancel, on_step=on_step)
    gx, gy = mesh.gradient(P)
    _, flux, _ = prob.boundary(None if steps is None else times[-1], P)
    if steps is None:
        react = mesh.stiffness(prob.k, prob.k) @ P - flux
    rate = react + flux
    res = {"type": "air", "converged": ok, "nodes": nodes.tolist(), "tris": tris.tolist(),
           "tri_material": tmat.tolist(), "air_pressure": P.tolist(),
           "vx": (-prob.k * gx).tolist(), "vy": (-prob.k * gy).tolist(),
           "inflow": float(rate[rate > 0].sum()), "outflow": float(-rate[rate < 0].sum())}
    if steps is not None:
        res.update(times=times, pressure_history=hist)
    return res
