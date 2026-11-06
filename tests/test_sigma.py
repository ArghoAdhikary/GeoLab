"""Stress-deformation against closed-form solutions."""
import math

import numpy as np
import pytest

from geolab.model import new_project
from geolab.sigma import run_stress
from geolab.slope import run_slope


def block(w, h, kind="stress"):
    p = new_project(kind=kind)
    m = p.materials[0]
    p.add_region([(0, 0), (w, 0), (w, h), (0, h)], m.id)
    p.add_bc("Sides", "fixed_x", 0, [(0, h), (0, 0)])
    p.add_bc("Right", "fixed_x", 0, [(w, 0), (w, h)])
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (w, 0)])
    return p, m, p.analyses[0]


def test_gravity_stresses_level_ground():
    p, m, a = block(20, 10)
    m.E, m.nu, m.unit_weight = 1e4, 0.3, 20.0
    a.stress_type, a.mesh_size = "insitu", 1.0
    r = run_stress(p, a)
    n = np.array(r["nodes"])
    mid = (np.abs(n[:, 0] - 10) < 4) & (n[:, 1] > 1) & (n[:, 1] < 9)
    sy = np.array(r["sy"])[mid]
    sx = np.array(r["sx"])[mid]
    exact = 20.0 * (10 - n[mid, 1])
    assert np.allclose(sy, exact, rtol=0.02, atol=1.0)
    assert np.allclose(sx, 0.3 / 0.7 * exact, rtol=0.02, atol=1.0)
    assert max(np.abs(r["dx"])) == 0.0        # in situ displacements reset


def test_effective_stress_below_water_table():
    p, m, a = block(20, 10)
    m.E, m.nu, m.unit_weight = 1e4, 0.3, 20.0
    a.stress_type, a.mesh_size, a.pwp = "insitu", 1.0, "piezometric"
    p.piezometric_line = [[0, 6], [20, 6]]
    r = run_stress(p, a)
    n = np.array(r["nodes"])
    k = np.argmin(np.hypot(n[:, 0] - 10, n[:, 1] - 2))
    y = n[k, 1]
    u = p.gamma_w * (6 - y)
    assert r["pwp"][k] == pytest.approx(u, rel=0.03)
    assert r["sy"][k] == pytest.approx(20 * (10 - y), rel=0.02)
    # K0 applies to effective stress
    assert r["sx_eff"][k] == pytest.approx(0.3 / 0.7 * (20 * (10 - y) - u), rel=0.03)


def test_one_dimensional_compression():
    p, m, a = block(1, 10)
    m.E, m.nu, m.unit_weight = 1e4, 0.25, 0.0
    a.stress_type, a.mesh_size, a.load_steps = "load", 0.5, 1
    p.add_bc("Load", "pressure", 100.0, [(1, 10), (0, 10)])
    r = run_stress(p, a)
    M = m.E * (1 - m.nu) / ((1 + m.nu) * (1 - 2 * m.nu))
    assert -min(r["dy"]) == pytest.approx(100 * 10 / M, rel=1e-3)
    assert r["reactions"]["Base"][1] == pytest.approx(100.0, rel=1e-3)


def test_prandtl_bearing_capacity():
    """Smooth rigid strip footing on weightless undrained clay: q = (2 + pi) su."""
    p, m, a = block(6, 4)
    m.model, m.stress_model, m.cohesion, m.phi = "undrained", "elastic_plastic", 100.0, 0.0
    m.E, m.nu, m.unit_weight = 1e5, 0.45, 0.0
    a.stress_type, a.mesh_size, a.load_steps = "load", 0.2, 12
    p.add_bc("Footing", "displacement_y", -0.06, [(0, 4), (1, 4)])
    r = run_stress(p, a)
    q = -r["reactions"]["Footing"][1] / 1.0
    assert q == pytest.approx((2 + math.pi) * 100.0, rel=0.08), q
    assert any(r["yielded"])


def gl_slope():
    """Griffiths & Lane (1999) example: 2:1 slope, c/(gamma H) = 0.05, phi = 20 deg."""
    p = new_project(kind="stress")
    m = p.materials[0]
    m.stress_model, m.cohesion, m.phi, m.psi, m.unit_weight, m.E, m.nu = "elastic_plastic", 10.0, 20.0, 0.0, 20.0, 1e5, 0.3
    p.add_region([(0, 0), (60, 0), (60, 20), (40, 20), (20, 10), (0, 10)], m.id)
    p.add_bc("Left", "fixed_x", 0, [(0, 10), (0, 0)])
    p.add_bc("Right", "fixed_x", 0, [(60, 0), (60, 20)])
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (60, 0)])
    return p


def test_strength_reduction_matches_limit_equilibrium():
    p = gl_slope()
    a = p.analyses[0]
    a.stress_type, a.srm, a.mesh_size = "insitu", True, 1.25
    r = run_stress(p, a)
    srm = r["srm_fos"]
    s = p.add_analysis("LE", kind="slope")
    s.search.mode = "auto"
    le = run_slope(p, s)["critical"]["fos"]
    assert 1.3 < srm < 1.5        # published: about 1.4
    assert srm == pytest.approx(le, rel=0.06), (srm, le)


def test_terzaghi_consolidation():
    H, q = 10.0, 100.0
    p, m, a = block(1, H)
    m.E, m.nu, m.unit_weight, m.k_sat = 1e4, 0.3, 0.0, 1e-7
    M = m.E * (1 - m.nu) / ((1 + m.nu) * (1 - 2 * m.nu))
    cv = m.k_sat * M / p.gamma_w
    Tv = 0.2
    a.stress_type, a.mesh_size = "consolidation", 0.5
    a.duration, a.n_steps, a.step_growth = Tv * H * H / cv, 40, 1.08
    p.add_bc("Load", "pressure", q, [(1, H), (0, H)])
    p.add_bc("Drained top", "head", 0.0, [(0, H), (1, H)])
    r = run_stress(p, a)
    first = np.array(r["excess_history"][0])
    assert np.median(first) == pytest.approx(q, rel=0.02)          # undrained response
    n = np.array(r["nodes"])
    pe = np.array(r["excess_pwp"])
    exact = 0.0
    for k in range(200):
        Mk = math.pi * (2 * k + 1) / 2
        exact += 2 / Mk * math.sin(Mk * 0.5) * math.exp(-Mk * Mk * Tv)
    mid = np.abs(n[:, 1] - H / 2) < 0.01
    assert pe[mid].mean() / q == pytest.approx(exact, abs=0.02)
    # degree of consolidation from settlement: U = 1 - sum 2/M^2 exp(-M^2 Tv)
    U = 1 - sum(2 / (math.pi * (2 * k + 1) / 2) ** 2 * math.exp(-(math.pi * (2 * k + 1) / 2) ** 2 * Tv) for k in range(200))
    s_inf = q * H / M
    assert r["settlement_history"][-1] == pytest.approx(r["settlement_history"][0] + U * (s_inf - r["settlement_history"][0]), rel=0.03)
