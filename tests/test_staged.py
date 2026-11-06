"""Staged construction, structural elements, Hardening Soil and plastic consolidation."""
import math

import numpy as np
import pytest

from geolab.examples import EXAMPLES, _box_supports
from geolab.model import new_project
from geolab.solver import solve
from geolab.soilmodels import hs_E
from geolab.structures import StructureSet


def _column(width=10.0, height=10.0, E=2e4, model="linear_elastic"):
    p = new_project(kind="stress")
    m = p.materials[0]
    m.stress_model, m.E, m.nu, m.unit_weight, m.cohesion, m.phi = model, E, 0.3, 20.0, 10.0, 30.0
    _box_supports(p, 0, width, height, height)
    a = p.analyses[0]
    a.stress_type, a.mesh_size = "insitu", 1.0
    return p, m, a


def test_stage_without_changes_does_not_move():
    p, m, a = _column()
    p.add_region([(0, 0), (10, 0), (10, 10), (0, 10)], m.id)
    b = p.add_analysis("Nothing happens", kind="stress", parent_id=a.id, stress_type="load", mesh_size=1.0)
    solve(p, a)
    r = solve(p, b)
    assert np.abs(r["dx"]).max() < 1e-9 and np.abs(r["dy"]).max() < 1e-9


def test_fill_stage_carries_its_own_weight_and_settles_the_ground():
    p, m, a = _column()
    p.add_region([(0, 0), (10, 0), (10, 8), (0, 8)], m.id)
    fill = p.add_region([(0, 8), (10, 8), (10, 10), (0, 10)], m.id)
    a.inactive_regions = [fill.id]
    p.bcs("stress")[0].points = [(0, 10), (0, 0)]
    b = p.add_analysis("Place 2 m of fill", kind="stress", parent_id=a.id, stress_type="load", mesh_size=1.0)
    ra = solve(p, a)
    rb = solve(p, b)
    nodes = np.array(rb["nodes"])
    # before: nothing in the fill; after: the ground settles under the 40 kPa of fill
    top = nodes[:, 1] > 9.99
    assert np.allclose(np.array(ra["sy"])[top], 0.0, atol=1.0)
    base_of_fill = np.isclose(nodes[:, 1], 8.0) & (nodes[:, 0] > 2) & (nodes[:, 0] < 8)
    assert min(np.array(rb["dy"])[base_of_fill]) < 0
    # 1D: settlement of the 8 m layer under 40 kPa, constrained modulus E(1-nu)/((1+nu)(1-2nu))
    Ec = 2e4 * 0.7 / (1.3 * 0.4)
    assert abs(-np.mean(np.array(rb["dy"])[base_of_fill]) - 40 * 8 / Ec) < 0.06 * 40 * 8 / Ec
    # vertical stress at the bottom of the ground = 10 m of soil
    bottom = (nodes[:, 1] < 1.01) & (nodes[:, 0] > 3) & (nodes[:, 0] < 7)
    assert abs(np.mean(np.array(rb["sy"])[bottom]) - 20 * 10) < 0.08 * 200


def test_excavation_heaves_the_floor():
    p, m, a = _column(width=20)
    dig = p.add_region([(0, 7), (6, 7), (6, 10), (0, 10)], m.id)
    p.add_region([(0, 0), (20, 0), (20, 10), (6, 10), (6, 7), (0, 7)], m.id)
    b = p.add_analysis("Dig", kind="stress", parent_id=a.id, stress_type="load", mesh_size=1.0,
                       inactive_regions=[dig.id])
    solve(p, a)
    r = solve(p, b)
    nodes = np.array(r["nodes"])
    floor = np.isclose(nodes[:, 1], 7.0) & (nodes[:, 0] < 5)
    assert min(np.array(r["dy"])[floor]) > 0           # unloading: the floor rises
    assert r["staged"] and any(r["inactive"])


class _FakeMesh:
    def __init__(self, nodes):
        self.nodes = np.asarray(nodes, float)
        self.nn = len(nodes)


def _cantilever(kind, n=10, L=5.0, **kw):
    p = new_project(kind="stress")
    p.add_structure(kind, [(0, 0), (L, 0)], **kw)
    mesh = _FakeMesh([(L * i / n, 0.0) for i in range(n + 1)])
    return p, mesh, StructureSet(p, mesh, p.analyses[0], 1e-6)


def test_beam_cantilever_matches_theory():
    P, L, EI = 10.0, 5.0, 2.0e3
    p, mesh, ss = _cantilever("beam", L=L, EA=1e6, EI=EI)
    K = ss.stiffness().toarray()
    fixed = [0, 1, ss.rot[0]]
    F = np.zeros(ss.ndof)
    F[2 * 10 + 1] = -P
    free = [i for i in range(ss.ndof) if i not in fixed]
    u = np.zeros(ss.ndof)
    u[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
    assert abs(-u[21] - P * L ** 3 / (3 * EI)) < 1e-6 * P * L ** 3 / (3 * EI)
    res = ss.results(u)[0]
    assert abs(res["max_M"] - P * L) < 1e-6 * P * L         # fixed-end moment


def test_anchor_bar_stiffness_and_spacing():
    p, mesh, ss = _cantilever("anchor", n=4, L=4.0, EA=8e4, spacing=2.0)
    K = ss.stiffness().toarray()
    fixed = [0, 1] + [2 * i + 1 for i in range(5)]
    F = np.zeros(ss.ndof)
    F[8] = 10.0
    free = [i for i in range(ss.ndof) if i not in fixed]
    u = np.zeros(ss.ndof)
    u[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
    assert abs(u[8] - 10.0 * 4.0 / (8e4 / 2.0)) < 1e-9
    assert abs(ss.results(u)[0]["max_N"] - 10.0) < 1e-6


def test_geogrid_carries_no_compression():
    p, mesh, ss = _cantilever("geogrid", n=2, L=2.0, EA=1e4)
    u = np.zeros(ss.ndof)
    u[4] = -0.01                       # push the end in: compression
    assert ss.compressed_geogrids(u)
    sid = p.structures[0].id
    assert (sid, 1) in ss.off and (sid, 0) not in ss.off      # only the pushed element goes slack
    assert ss.results(u)[0]["elements"][1]["N"] == 0.0


def test_anchored_excavation_example():
    p = EXAMPLES["Anchored excavation (staged)"]()
    for a in p.analyses:
        r = solve(p, a)
        assert r["converged"]
    names = {s["name"]: s for s in r["structures"]}
    wall, anchor = names["Sheet-pile wall"], names["Ground anchor"]
    assert wall["max_M"] > 1.0 and anchor["max_N"] > 20.0           # the anchor stays in tension
    nodes = np.array(r["nodes"])
    behind = (nodes[:, 0] > 10.5) & (nodes[:, 0] < 14) & (nodes[:, 1] > 19.9)
    assert np.array(r["dx"])[behind].min() < 0                     # ground moves towards the excavation


def test_hardening_soil_stiffness():
    mat = {"E50": np.array([2e4]), "Eur": np.array([6e4]), "m": np.array([0.5]), "pref": np.array([100.0]),
           "Rf": np.array([0.9]), "c": np.array([0.0]), "phi": np.array([30.0])}
    s = np.array([[-100.0, -100.0, 0.0, -100.0]])            # isotropic 100 kPa = p_ref
    E, sl = hs_E(s, np.zeros(1), mat)
    assert abs(E[0] - 2 * 2e4 / (2 - 0.9)) < 1e-6 and sl[0] == 0
    s4 = s * 4
    E4, _ = hs_E(s4, np.zeros(1), mat)
    assert abs(E4[0] / E[0] - 2.0) < 1e-9                      # (400 / 100) ^ 0.5
    Eu, _ = hs_E(s, np.array([0.5]), mat)
    assert abs(Eu[0] - 6e4) < 1e-6                             # unloading uses Eur


def test_hardening_soil_layer_runs_and_is_softer_with_lower_E50():
    out = []
    for E50 in (4e4, 1e4):
        p, m, a = _column(width=10, height=6, model="hardening_soil")
        m.hs_E50, m.hs_Eur, m.E = E50, 3 * E50, 3e4
        p.add_region([(0, 0), (10, 0), (10, 6), (0, 6)], m.id)
        b = p.add_analysis("Load", kind="stress", parent_id=a.id, stress_type="load", load_steps=5, mesh_size=1.0)
        p.add_bc("Fill load", "pressure", 100.0, [(10, 6), (0, 6)], analyses=[b.id])
        solve(p, a)
        r = solve(p, b)
        assert r["converged"]
        out.append(-min(r["dy"]))
    assert out[1] > 2.5 * out[0] > 0


def test_plastic_consolidation_settles_more_than_elastic():
    out = []
    for model in ("linear_elastic", "elastic_plastic"):
        p = EXAMPLES["Consolidation under a fill"]()
        m = p.materials[0]
        m.stress_model, m.cohesion, m.phi = model, 3.0, 20.0
        r = solve(p, p.analyses[0])
        out.append(r["settlement_history"][-1])
    assert out[1] > out[0] > 0
