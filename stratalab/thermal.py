"""Heat transfer by conduction with freezing and thawing (finite element, steady or transient).

Phase change uses an enthalpy formulation: the unfrozen water content decreases linearly
from the full water content at 0 degrees to zero at -freeze_range, releasing latent heat
L * theta. The modified Picard scheme of fe.solve_diffusion keeps the energy balance exact
(Celia et al. 1990), which avoids the missed-latent-heat error of apparent heat capacity
schemes with large time steps.
"""
from __future__ import annotations

import numpy as np

from .fe import DiffusionProblem, T3, interpolator, time_steps, solve_diffusion
from .geometry import validate_geometry
from .model import UNIT_SYSTEMS
from .seep import generate_mesh


def frozen_fraction(T, r):
    return np.clip(-np.asarray(T, float) / max(r, 1e-9), 0.0, 1.0)


def enthalpy(m, T, latent):
    """Volumetric enthalpy and its derivative (apparent heat capacity) of one material."""
    T = np.asarray(T, float)
    r = max(m.th_freeze_range, 1e-9)
    Cu, Cf = m.th_c, m.th_c_frozen
    Lw = latent * m.th_water
    f = frozen_fraction(T, r)
    Hm = Cu * T + Lw
    Hr = Cu * T - (Cf - Cu) * T * T / (2 * r) + Lw * (1 - f)
    H_at_r = -Cu * r - (Cf - Cu) * r / 2
    Hf = H_at_r + Cf * (T + r)
    H = np.where(T >= 0, Hm, np.where(T >= -r, Hr, Hf))
    dH = np.where(T >= 0, Cu, np.where(T >= -r, Cu + (Cf - Cu) * f + Lw / r, Cf))
    return H, dH


class _ThermalProblem(DiffusionProblem):
    chord = True
    line_search = True

    def __init__(self, project, analysis, mesh: T3):
        self.m = mesh
        mats = {m.id: m for m in project.materials}
        self.mat_list = [mats[i] for i in sorted(set(mesh.mats.tolist()))]
        self.emask = {m.id: mesh.mats == m.id for m in self.mat_list}
        self.w = {}
        for m in self.mat_list:
            e = self.emask[m.id]
            a = np.bincount(mesh.tris[e].ravel(), weights=np.repeat(mesh.A[e] / 3.0, 3), minlength=mesh.nn)
            self.w[m.id] = a / mesh.lump
        self.latent = UNIT_SYSTEMS[project.units]["latent"]
        tol = 0.1 * analysis.mesh_size
        self.bcs = []
        for bc in project.bcs("thermal", analysis):
            nodes = mesh.nodes_on(bc.points, tol)
            if not nodes:
                raise ValueError(f"Boundary condition '{bc.name}' does not touch any mesh node.")
            self.bcs.append((bc, nodes, mesh.edges_on(bc.points, tol)))
        if not self.bcs:
            raise ValueError("A thermal analysis needs at least one thermal boundary condition.")

    def conductivity(self, T):
        f = None
        k = np.zeros(self.m.ne)
        for m in self.mat_list:
            e = self.emask[m.id]
            f = frozen_fraction(T[self.m.tris[e]], m.th_freeze_range).mean(axis=1)
            k[e] = m.th_k * (1 - f) + m.th_k_frozen * f
        return k, k

    def storage(self, T):
        S = np.zeros(self.m.nn)
        dS = np.zeros(self.m.nn)
        for m in self.mat_list:
            H, dH = enthalpy(m, T, self.latent)
            S += self.w[m.id] * H
            dS += self.w[m.id] * dH
        return S, dS

    def boundary(self, t, T):
        fixed = {}
        flux = np.zeros(self.m.nn)
        R = None
        for bc, nodes, edges in self.bcs:
            if bc.type == "temperature":
                v = bc.at(t)
                fixed.update({i: v for i in nodes})
            elif bc.type == "heat_flux":
                flux += self.m.edge_load(edges, bc.at(t))
            elif bc.type == "convective":       # q = h (T_ambient - T); value = h, ambient = value2 or fn
                h = bc.value
                Ta = bc.at(t) if bc.fn else bc.value2
                Km = self.m.edge_mass(edges, h)
                rr = self.m.edge_load(edges, h * Ta)
                R = (Km, rr) if R is None else (R[0] + Km, R[1] + rr)
        return fixed, flux, R


def run_thermal(project, analysis, progress=None, cancel=None, parent_results=None) -> dict:
    problems = validate_geometry(project)
    if problems:
        raise ValueError("; ".join(problems))
    nodes, tris, tmat = generate_mesh(project, analysis.mesh_size)
    mesh = T3(nodes, tris, tmat)
    prob = _ThermalProblem(project, analysis, mesh)
    steps = time_steps(analysis.duration, analysis.n_steps, analysis.step_growth) if analysis.transient else None
    if analysis.initial == "parent" and parent_results and parent_results.get("type") == "thermal":
        T0 = interpolator(parent_results["nodes"], parent_results["temperature"])(nodes[:, 0], nodes[:, 1])
    elif steps is not None or analysis.initial == "value":
        T0 = np.full(mesh.nn, float(analysis.initial_value))
    else:
        T0 = np.zeros(mesh.nn)
    times, hist = [0.0], [T0.tolist()]
    E0 = prob.storage(T0)[0]
    energy_in = [0.0, 0.0]

    def on_step(k, t, T, react):
        if t is None:
            return
        _, flux, R = prob.boundary(t, T)
        rob = (R[1] - R[0] @ T) if R is not None else 0.0
        energy_in[0] += (t - energy_in[1]) * float(np.sum(react + flux + rob))
        energy_in[1] = t
        times.append(float(t))
        hist.append(T.tolist())
        if progress:
            progress(min(99, int(100 * (k + 1) / len(steps))))

    T, history, ok, react, it = solve_diffusion(mesh, prob, T0, steps, max_iter=analysis.max_iter,
                                                tol=analysis.tolerance, relax=1.0, cancel=cancel,
                                                on_step=on_step)
    kx, ky = prob.conductivity(T)
    gx, gy = mesh.gradient(T)
    ice = np.zeros(mesh.nn)
    for m in prob.mat_list:
        ice += prob.w[m.id] * frozen_fraction(T, m.th_freeze_range)
    res = {"type": "thermal", "converged": ok, "iterations": it, "history": history[-200:],
           "nodes": nodes.tolist(), "tris": tris.tolist(), "tri_material": tmat.tolist(),
           "temperature": T.tolist(), "frozen_fraction": ice.tolist(),
           "qx": (-kx * gx).tolist(), "qy": (-ky * gy).tolist()}
    if steps is not None:
        dE = float(np.sum(mesh.lump * (prob.storage(T)[0] - E0)))
        res.update(times=times, temperature_history=hist, energy_change=dE, energy_in=energy_in[0],
                   balance_error=abs(dE - energy_in[0]) / max(abs(dE), abs(energy_in[0]), 1e-30))
    return res
